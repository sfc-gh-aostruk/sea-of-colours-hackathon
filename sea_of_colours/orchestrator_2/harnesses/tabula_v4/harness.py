"""tabula_v4 — night entry point.

Diff from v3: slimmed PROBING MANDATE doctrine block in
`strategies.py`. See `sea_of_colours/orchestrator_2/harnesses/
tabula_v3/V4_BACKLOG.md` item #2 for the motivation — v3 launched
7 probes over a 7-night season vs the heuristic's 18 on the same
seed, and that single gap capped the LLM agent's score potential.

v4 adds:
  * A short, concrete PROBING MANDATE section in `strategies.py`
    stating the numeric probing thresholds directly. On seed=42
    solo runs, this alone lifted LLM-authored probes from 7 (v3)
    to 11 (v4) with no harness enforcement needed.
  * New primary agent SOC_RED_REAPER_TABULA_V4 (same doctrine as
    v3 plus the slim PROBING MANDATE) and finisher
    SOC_RED_REAPER_TABULA_V4_FINISHER.

An earlier v4 iteration added a deterministic ``_augment_with_probes``
that prepended probes when the LLM under-launched. It was removed
after audit showed the LLM chose 11 of the 14 probes on its own —
the augmenter's contribution was 3, and 2 of those actively hurt
by firing on the final night. Keeping the harness purely reactive
to the LLM's plan (no forced moves) is the correct design.

Flow per turn:

  1. Close prior day's memory (reflect: fill actual_banked + crushes)
  2. Snapshot turn-start state (score, probe cells) for use next turn
  3. Read the last N memory entries → format as replay prose
  4. Build prompt (rules + state + visible red + memory + chain hints + schema)
  5. Invoke Cortex agent SOC_RED_REAPER_TABULA_V4 (single call, ~30s)
  6. Parse JSON response strictly; on failure, invoke the v4 finisher
  7. Submit the move queue via engine.submit_policy
  8. Write this turn's memory entry (plan + rationale + prediction + moves)
  9. Return an envelope compatible with the orchestrator_2 dispatcher

Only fires on planning phase. Orbit routes to :mod:`.orbit_stub`.
"""

from __future__ import annotations

import json as _json
import re
import time
from typing import Any, Dict, List, Mapping, Optional, Tuple

from sea_of_colours.orchestrator_2.cortex_invoker import CortexAgentInvoker
from sea_of_colours.orchestrator_2.harnesses.tabula_v4 import (
    heuristic_chains,
    memory,
    opponent_weapons,
    orbit_stub,
    orbit_wishlist as wishlist_mod,
    probe_hints as probe_hints_mod,
    prompt as prompt_mod,
    recorder,
    validators,
)


# ── Agent identity + budgets ───────────────────────────────────────────
AGENT_NAME = "SOC_RED_REAPER_TABULA_V4"
INNER_AGENT_LABEL = "TABULA_V4"
# The continuation finisher — a companion Cortex agent with the same
# game doctrine but a strict JSON-only response contract. Invoked
# ONLY when the primary agent's response can't be parsed. The primary
# spec's "strategic pilot" identity primes analytical prose output;
# when we asked the primary itself to "finish" its own draft it kept
# reverting to re-analysis. A dedicated finisher spec avoids that
# by having the response contract wired in at the spec level.
FINISHER_AGENT_NAME = "SOC_RED_REAPER_TABULA_V4_FINISHER"
# v3 prompt grew from ~13KB (initial) → ~25KB (opponent weapons + gated
# doctrine + last-night truth + nomadic doctrine). Bumped from 30s → 60s
# to give haiku headroom on the larger reasoning surface without falling
# to the heuristic fallback on complex nights (see days 5/7 of the solo
# normal run — those timed out on 30s).
_WALLCLOCK_S = 60
# Response cap: kept deliberately tight because haiku will otherwise
# expand into open-ended prose ("let me consider… actually…"), burning
# reasoning tokens without producing JSON. Back to 3000 now that the
# continuation retry (see ``_continuation_prompt``) handles the case
# where the primary invocation runs out of budget mid-plan — smaller
# primary cap forces the continuation path to fire more often, which
# is the desired test surface. Bump this again only if continuation
# recovery rate drops below ~80% on the failed-primary nights.
_RESPONSE_CAP = 3_000
_MAX_MOVES = 21

# Continuation retry — invoked when the first haiku call runs out of
# budget mid-plan. Tight caps because this is a "finish what you started"
# call: haiku already spent 25KB of prompt reasoning; it just needs
# enough room to close the JSON.
_CONTINUATION_WALLCLOCK_S = 20
_CONTINUATION_RESPONSE_CAP = 2_500


# Turn-start snapshots keyed by (session_id, player) so we can compute
# banked-this-night on the NEXT turn. Process-local; fine for a single
# season run. Tests reset via ``clear_snapshots``.
_SNAPSHOTS: Dict[str, Dict[str, Any]] = {}


def _snap_key(session_id: str, player: str) -> str:
    return f"{session_id}::{player}"


def _capture_snapshot(
    session_id: str, player: str, day: int, agent_view: Mapping[str, Any],
) -> None:
    key = _snap_key(session_id, player)
    slot = _SNAPSHOTS.setdefault(key, {"score_by_day": {}, "probes_by_day": {},
                                       "moves_by_day": {}})
    hud = agent_view.get("hud") or {}
    scores = hud.get("scores") or {}
    me = ((agent_view.get("meta") or {}).get("player")) or player
    slot["score_by_day"][int(day)] = int(scores.get(me) or 0)
    entities = (agent_view.get("entities") or {}).get("mine") or []
    probe_cells = set()
    for e in entities:
        if not isinstance(e, Mapping):
            continue
        if str(e.get("type") or "") != "probe":
            continue
        pos = e.get("pos")
        if isinstance(pos, (list, tuple)) and len(pos) == 2:
            try:
                probe_cells.add((int(pos[0]), int(pos[1])))
            except (TypeError, ValueError):
                continue
    slot["probes_by_day"][int(day)] = probe_cells



def _record_moves(
    session_id: str, player: str, day: int, moves: List[Mapping[str, Any]],
) -> None:
    key = _snap_key(session_id, player)
    slot = _SNAPSHOTS.setdefault(key, {"score_by_day": {}, "probes_by_day": {},
                                       "moves_by_day": {}})
    slot["moves_by_day"][int(day)] = [dict(m) for m in moves]


def _historical_probe_targets(
    session_id: str, player: str, store: Optional[Any] = None,
) -> List[Tuple[int, int]]:
    """Every (x,y) this player has probed earlier in the season.

    Reads the process-local ``_SNAPSHOTS.moves_by_day`` first; if empty
    (e.g. a fresh process resuming a persisted season), falls back to
    parsing ``moves_summary`` from ``memory.read_recent`` which is
    hydrated from ``SOC_AGENT_MEMORY``. Feeds the compiler's
    anti-clustering filter — see ``probe_hints.top_probe_hints`` for
    why active-only was insufficient.
    """
    positions: List[Tuple[int, int]] = []
    key = _snap_key(session_id, player)
    slot = _SNAPSHOTS.get(key) or {}
    for _day, moves in (slot.get("moves_by_day") or {}).items():
        for m in moves or []:
            if not isinstance(m, Mapping):
                continue
            if str(m.get("a") or "") != "probe":
                continue
            at = m.get("at")
            if isinstance(at, (list, tuple)) and len(at) == 2:
                try:
                    positions.append((int(at[0]), int(at[1])))
                except (TypeError, ValueError):
                    continue
    if positions:
        return positions

    # Fallback: parse ``moves_summary`` strings from persisted memory.
    # Format: ``probe@[X, Y]`` (see :func:`_summarise_moves`).
    import re
    pat = re.compile(r"probe@\[(-?\d+),\s*(-?\d+)\]")
    try:
        entries = memory.read_recent(
            session_id, player, limit=99, store=store,
        )
    except Exception:
        entries = []
    for e in entries or []:
        ms = str((e or {}).get("moves_summary") or "")
        for match in pat.finditer(ms):
            try:
                positions.append((int(match.group(1)), int(match.group(2))))
            except (TypeError, ValueError):
                continue
    return positions


def clear_snapshots() -> None:
    """Test helper — reset the per-session snapshot cache."""
    _SNAPSHOTS.clear()


# ── Public entry point ────────────────────────────────────────────────
def run(
    *, store: Any, session_id: str, player: str, view: Mapping[str, Any],
) -> Dict[str, Any]:
    """Drive one arena turn. Returns the dispatcher audit envelope."""
    started = time.time()
    phase = str(
        view.get("phase")
        or (view.get("agent_view", {}).get("meta", {}) or {}).get("phase")
        or ""
    ).lower()
    if phase == "orbit":
        # Route through the orbit dispatcher — heuristic RED_HARVEST by
        # default (ships parcels, builds harvesters+probes, jettisons
        # greens). Env var ``TABULA_V3_ORBIT_MODE=empty`` reverts to the
        # legacy no-op stub for regression tests.
        return orbit_stub.submit_orbit(store, session_id, player, view)

    agent_view = view.get("agent_view") or {}
    meta = agent_view.get("meta") or {}
    hud = agent_view.get("hud") or {}
    day = int(meta.get("day") or hud.get("day") or 0)
    day_cap = int(hud.get("season_day_cap") or 7)
    scores = hud.get("scores") or {}
    vault_score = int(scores.get(player) or 0)
    season_name = str(hud.get("season_name") or "")

    # 1. Close prior day's memory with the outcome the engine just resolved.
    snap = _SNAPSHOTS.get(_snap_key(session_id, player), {})
    recorder.close_prior_day_if_needed(
        session_id, player,
        current_day=day,
        turn_start_score_by_day=snap.get("score_by_day", {}),
        turn_start_probes_by_day=snap.get("probes_by_day", {}),
        moves_submitted_by_day=snap.get("moves_by_day", {}),
        store=store,
        season_name=season_name,
    )

    # 2. Snapshot this turn's start state for next turn's reflection.
    _capture_snapshot(session_id, player, day, agent_view)

    # 3. Read the last 3 memory entries and format as replay prose.
    prior_entries = memory.read_recent(session_id, player, limit=3, store=store)
    memory_replay = memory.format_replay(prior_entries)

    # 4. Build the prompt.
    chain_hints = heuristic_chains.top_chain_hints(agent_view, max_chains=3)
    probe_hints = probe_hints_mod.top_probe_hints(
        agent_view,
        max_hints=3,
        historical_probe_positions=_historical_probe_targets(
            session_id, player, store=store,
        ),
    )
    hot_drop_hints = probe_hints_mod.top_hot_drop_hints(agent_view, max_hints=2)

    # Opponent-weapon estimates — fold this turn's station_intel +
    # activity into last turn's estimate, then hand to the wishlist
    # compiler so ``beware_emp`` / ``beware_chaff`` / ``beware_mines``
    # can fire when any opponent likely has stock. See
    # :mod:`.opponent_weapons` for the inference logic.
    weapon_estimates = opponent_weapons.update_estimates(
        session_id, player, agent_view,
    )

    # Wishlist — deterministic tactical priorities from station_intel +
    # hoard + last night. In v3 phase 1 we compute fresh at planning time
    # (equivalent to the orbit-turn compilation because inputs don't
    # materially shift between orbit resolution and next-night planning).
    # A later revision will persist the orbit-turn's wishlist and read
    # it here so we can compare "orbit's view" vs "night's view" honestly.
    wishlist = wishlist_mod.compute_wishlist(
        agent_view,
        day=day,
        opponent_weapon_estimates=weapon_estimates,
    )

    # Blue hints only when the wishlist explicitly asks for them (or
    # when blue tiles are visible AND we have >=2 harvesters). Keeps
    # the prompt clean when blue isn't on the menu.
    want_blue = any(e.tag == "grab_blue" for e in wishlist.entries)
    blue_hints = (
        heuristic_chains.top_blue_chain_hints(agent_view, max_chains=2)
        if want_blue else []
    )

    prompt_text = prompt_mod.build_prompt(
        agent_view=agent_view,
        day=day, day_cap=day_cap, vault_score=vault_score,
        memory_replay=memory_replay,
        chain_hints=chain_hints,
        probe_hints=probe_hints,
        hot_drop_hints=hot_drop_hints,
        blue_hints=blue_hints,
        wishlist=wishlist,
        opponent_weapon_estimates=weapon_estimates,
    )

    # 5. Invoke the arena Cortex agent.
    #    We hand the invoker a completion predicate: as soon as a full
    #    balanced JSON object containing ``"moves"`` has streamed, close
    #    the SSE socket. Kills the haiku "re-emit the same object three
    #    times" pattern that saturated the response cap in prior tests.
    invoker = CortexAgentInvoker(
        agent_name=AGENT_NAME,
        text_completion_predicate=_arena_json_complete,
    )
    result = invoker.invoke(
        prompt_text,
        wallclock_cap_s=_WALLCLOCK_S,
        response_cap_bytes=_RESPONSE_CAP,
    )
    response_text = str(result.get("response") or "")

    # 6. Parse JSON. On failure, fall back to heuristic chain hint.
    #    We do NOT validate individual moves here anymore — that was
    #    too punitive. The engine already rejects individual illegal
    #    moves in a submitted plan (bad drops, off-grid steps, etc.)
    #    while executing the legal ones in order. A harness-side
    #    validator that treats ANY invalid move as a full plan
    #    failure was masking the LLM's intent (e.g. discarding a
    #    valid probe launch just because the follow-up drop was
    #    illegal), and turned partial success into total fallback.
    decision, decision_error = _extract_decision_json(response_text)
    fallback_used = False
    fallback_reason = ""  # populated when fallback triggers
    continuation_used = False
    if decision_error or not decision.get("moves"):
        # 6a. Continuation retry — hand the primary's partial output to
        #     the dedicated FINISHER agent. The finisher's spec is a
        #     JSON-only completion service: same game doctrine as the
        #     primary but with a stripped response contract that
        #     forbids prose. Retrying with the primary itself failed
        #     because its own spec identity ("strategic pilot") kept
        #     defaulting back to re-analysis.
        if response_text.strip():
            continuation_used = True
            cont_prompt = _continuation_prompt(response_text)
            finisher_invoker = CortexAgentInvoker(agent_name=FINISHER_AGENT_NAME)
            cont_result = finisher_invoker.invoke(
                cont_prompt,
                wallclock_cap_s=_CONTINUATION_WALLCLOCK_S,
                response_cap_bytes=_CONTINUATION_RESPONSE_CAP,
            )
            cont_text = str(cont_result.get("response") or "")
            cont_decision, cont_err = _extract_decision_json(cont_text)
            if not cont_err and cont_decision.get("moves"):
                decision = cont_decision
                response_text_continuation = cont_text
            else:
                response_text_continuation = cont_text
                fallback_used = True
                fallback_reason = (
                    f"finisher_failed: {cont_err or 'missing moves'}"
                )
                decision = _heuristic_fallback_decision(chain_hints, day)
        else:
            response_text_continuation = ""
            fallback_used = True
            fallback_reason = (
                f"parse: {decision_error}" if decision_error
                else "parse: missing 'moves' key"
            )
            decision = _heuristic_fallback_decision(chain_hints, day)
    else:
        response_text_continuation = ""

    proposed = list(decision.get("moves") or [])

    # 8. Cap at 21 slots (engine ceiling), submit via engine.
    final_moves = proposed[:_MAX_MOVES]
    _record_moves(session_id, player, day, final_moves)

    from sea_of_colours.snowpark import engine as soc_engine
    submit_result = soc_engine.submit_policy(store, session_id, player, final_moves)

    # 9. Write this turn's memory entry (agent-authored fields only;
    #    actual_banked + crushes get filled in on NEXT turn's reflection).
    entry = memory.new_entry(
        day,
        plan_this_turn=str(decision.get("plan_this_turn") or ""),
        rationale=str(decision.get("rationale") or ""),
        predicted_outcome=(decision.get("predicted_outcome") or {}),
        moves_summary=_summarise_moves(final_moves),
        memory_note=str(decision.get("memory_note") or ""),
    )
    memory.save_entry(session_id, player, entry, store=store, season_name=season_name)

    ms_elapsed = int((time.time() - started) * 1000)
    return {
        "ok": True,
        "agent_id": INNER_AGENT_LABEL,
        "runtime": "harness_in_process",
        "rationale": (
            f"[plan={decision.get('plan_this_turn','')[:80]}] "
            f"[predicted={_pred_label(decision)}] "
            f"[fallback={fallback_used}"
            + (f":{fallback_reason[:120]}" if fallback_used else "")
            + f"]"
            + (" [continuation=recovered]"
               if (continuation_used and not fallback_used) else "")
            + f" moves={len(final_moves)}"
        ),
        "moves": final_moves,
        "submitted_policy": True,
        "wallclock_capped": bool(result.get("wallclock_capped")),
        "ms_elapsed": ms_elapsed,
        # Raw text captured for audit — dispatcher lifts this into
        # ``DispatchResult.response`` which the audit writer stamps into
        # ``SOC_AGENT_INVOCATION.response_text``. Without this, fallback
        # forensics on parse/validate failures are impossible (see days
        # 3/5/7 of the solo normal run — silent fallbacks with no visible
        # LLM output).
        "response": response_text,
        "extras": {
            "inner_agent": AGENT_NAME,
            "plan_label": str(decision.get("plan_this_turn") or "")[:80],
            "predicted_outcome": decision.get("predicted_outcome"),
            "reflection_on_last_night": decision.get("reflection_on_last_night"),
            "materialized_count": len(final_moves),
            "fallback_used": fallback_used,
            "fallback_reason": fallback_reason,
            "continuation_used": continuation_used,
            "continuation_response_chars": len(response_text_continuation),
            "prompt_chars": len(prompt_text),
            "response_chars": len(response_text),
            "submit_result": submit_result,
            # 32KB slice of the prompt — audit writer caps at
            # ``PROMPT_EXCERPT_CHAR_CAP`` (also 32KB) so this is a no-op
            # truncation for typical prompts (~25KB).
            "prompt_excerpt": prompt_text[:32_000],
        },
    }


# ── Helpers ────────────────────────────────────────────────────────────
def _arena_json_complete(accum: str) -> bool:
    """Text-completion predicate for the arena's streaming SSE loop.

    Returns True once the accumulated response contains at least one
    balanced JSON object that carries the required ``moves`` field.
    Used to close the SSE socket the moment the model has emitted a
    parseable decision — killing the "same JSON three times" haiku
    hedge that used to saturate the response cap.

    Cheap by design: only calls ``json.JSONDecoder.raw_decode`` when
    braces balance and ``"moves"`` has appeared, so the fast path
    for partial streams is a simple substring check.
    """
    if '"moves"' not in accum:
        return False
    # Balance check first — cheap and eliminates 99% of false positives.
    open_count = accum.count("{")
    close_count = accum.count("}")
    if open_count < 1 or close_count < open_count:
        return False
    # Confirm with a real decoder pass. Look for the first `{` that
    # starts a parseable object containing "moves".
    decoder = _json.JSONDecoder()
    for match in re.finditer(r"\{", accum):
        try:
            parsed, _ = decoder.raw_decode(accum[match.start():])
        except Exception:
            continue
        if isinstance(parsed, dict) and "moves" in parsed:
            return True
    return False


def _continuation_prompt(partial_response: str) -> str:
    """Build a minimal 'complete this plan' prompt for the FINISHER agent.

    The finisher's spec already carries the schema, move formats, and
    Manhattan-1 rule — so this prompt just hands over the primary's
    partial output. Keep it small so the finisher spends its 20s
    wallclock on JSON emission, not re-reading long context.
    """
    # Trim the partial response — if the primary spent 6KB on prose,
    # the tail is what matters (it's where the last logical plan lives).
    trimmed = partial_response.strip()
    if len(trimmed) > 3_000:
        trimmed = trimmed[-3_000:]

    return (
        "PARTIAL DRAFT FROM PRIMARY STRATEGIST (ran out of budget "
        "before closing its JSON — reconstruct its plan):\n"
        "\n"
        "=== BEGIN PARTIAL ===\n"
        f"{trimmed}\n"
        "=== END PARTIAL ===\n"
        "\n"
        "Read the partial above, extract the moves the primary was "
        "committing to, and emit ONE complete JSON object per your "
        "response contract. JSON only. Start with the open-brace "
        "character. GO:\n"
    )


def _extract_decision_json(text: str) -> Tuple[Dict[str, Any], Optional[str]]:
    """Find the first top-level JSON object in ``text`` and parse it.

    Two-pass recovery so we don't lose the LLM's plan to a single
    misplaced brace:

      1. Standard: strip any markdown fence, walk each ``{`` position,
         return the first balanced object that carries a ``moves`` key.

      2. Salvage (when pass 1 fails): scan the raw text for a
         ``"moves":\\s*\\[ ... \\]`` array on its own and treat that as
         the decision. Observed on day 5 of the arena_solo_normal run
         where haiku emitted a valid moves array but closed the
         wrapping object one brace too early — the array survived
         verbatim outside the malformed object.
    """
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.I).strip()
        raw = re.sub(r"\s*```$", "", raw).strip()
    decoder = _json.JSONDecoder()

    # Pass 1 — find a balanced object that has ``moves``.
    for match in re.finditer(r"\{", raw):
        try:
            parsed, _ = decoder.raw_decode(raw[match.start():])
        except Exception:
            continue
        if isinstance(parsed, dict) and "moves" in parsed:
            return parsed, None

    # Pass 2 — salvage a bare ``"moves": [...]`` array.
    moves_match = re.search(r'"moves"\s*:\s*(\[)', raw)
    if moves_match:
        start = moves_match.start(1)
        try:
            arr, _ = decoder.raw_decode(raw[start:])
        except Exception:
            arr = None
        if isinstance(arr, list):
            # Try to also recover ``plan_this_turn`` / ``rationale`` from
            # the malformed prefix so the memory entry isn't blank.
            def _grab(field: str) -> str:
                m = re.search(rf'"{field}"\s*:\s*"([^"]*)"', raw)
                return m.group(1) if m else ""
            recovered = {
                "moves": arr,
                "plan_this_turn": _grab("plan_this_turn") or "[recovered]",
                "rationale": _grab("rationale")
                    or "recovered moves array from malformed JSON",
                "predicted_outcome": {
                    "banked_pts_estimate": "medium",
                    "what_could_go_wrong": "recovered from malformed JSON",
                },
                "reflection_on_last_night": None,
                "memory_note": _grab("memory_note")
                    or "[recovered from malformed JSON]",
            }
            return recovered, None

    return {}, "no_json_object"


def _heuristic_fallback_decision(
    chain_hints: List[Mapping[str, Any]], day: int,
) -> Dict[str, Any]:
    """Compose a minimal decision from the top chain hint.

    Used when the LLM response can't be parsed or every proposed move
    fails validation. Emits a legal drop → step* → pickup chain from
    the top-scored heuristic hint. If no hint is available, emits an
    empty move queue (engine treats as pass — safer than a bad move).
    """
    if not chain_hints:
        return {
            "plan_this_turn": "[fallback] no chain hints available; passing.",
            "rationale": "compiler produced zero chains",
            "predicted_outcome": {"banked_pts_estimate": "low",
                                  "what_could_go_wrong": "no harvest attempted"},
            "moves": [],
            "memory_note": "[fallback] compiler had nothing; skipped night.",
        }
    top = chain_hints[0]
    unit = top.get("unit") or "harvester_p1"
    cells = list(top.get("cells") or [])
    if not cells:
        return {"plan_this_turn": "[fallback] hint had no cells", "rationale": "",
                "predicted_outcome": {"banked_pts_estimate": "low",
                                      "what_could_go_wrong": "hint empty"},
                "moves": [], "memory_note": "[fallback] empty hint."}
    moves: List[Dict[str, Any]] = [{"a": "drop", "unit": unit, "at": list(cells[0])}]
    for cell in cells[1:]:
        moves.append({"a": "step", "unit": unit, "to": list(cell)})
    moves.append({"a": "pickup", "unit": unit})
    return {
        "plan_this_turn": f"[fallback] follow top heuristic chain via {unit}",
        "rationale": "LLM parse/validate failed; used heuristic top chain",
        "predicted_outcome": {"banked_pts_estimate": "medium",
                              "what_could_go_wrong": "heuristic didn't consider EV"},
        "moves": moves,
        "memory_note": f"[fallback] executed heuristic chain via {unit} on day {day}.",
    }


def _summarise_moves(moves: List[Mapping[str, Any]]) -> str:
    """Compact one-line summary of a move queue for memory storage."""
    parts: List[str] = []
    for m in moves:
        a = str(m.get("a") or "")
        if a == "drop":
            parts.append(f"drop@{m.get('at')}")
        elif a == "step":
            parts.append(f"step->{m.get('to')}")
        elif a == "pickup":
            parts.append(f"pickup({m.get('unit')})")
        elif a == "probe":
            parts.append(f"probe@{m.get('at')}")
        else:
            parts.append(a)
    return ", ".join(parts)


def _pred_label(decision: Mapping[str, Any]) -> str:
    po = decision.get("predicted_outcome") or {}
    return str(po.get("banked_pts_estimate") or "?")
