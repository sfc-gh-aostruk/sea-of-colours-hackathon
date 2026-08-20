"""tabula — night entry point.

Flow per turn:

  1. Close prior day's memory (reflect: fill actual_banked + crushes)
  2. Snapshot turn-start state (score, probe cells) for use next turn
  3. Read the last N memory entries → format as replay prose
  4. Build prompt (rules + state + visible red + memory + chain hints + schema)
  5. Invoke Cortex agent SOC_RED_REAPER_TABULA (single call, ~30s)
  6. Parse JSON response strictly; on failure, use heuristic fallback
  7. Validate each move (drop LOS, step adjacency, pickup, probe)
  8. Submit the validated move queue via engine.submit_policy
  9. Write this turn's memory entry (plan + rationale + prediction + moves)
 10. Return an envelope compatible with the orchestrator_2 dispatcher

Only fires on planning phase. Orbit routes to :mod:`.orbit_stub`.
"""

from __future__ import annotations

import json as _json
import re
import time
from typing import Any, Dict, List, Mapping, Optional, Tuple

from sea_of_colours.orchestrator_2.cortex_invoker import CortexAgentInvoker
from sea_of_colours.orchestrator_2.harnesses.tabula import (
    heuristic_chains,
    memory,
    orbit_stub,
    prompt as prompt_mod,
    recorder,
    validators,
)


# ── Agent identity + budgets ───────────────────────────────────────────
AGENT_NAME = "SOC_RED_REAPER_TABULA"
INNER_AGENT_LABEL = "TABULA"
_WALLCLOCK_S = 30
_RESPONSE_CAP = 3_000
_MAX_MOVES = 21


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
        return orbit_stub.submit_empty_orbit(store, session_id, player)

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
    prompt_text = prompt_mod.build_prompt(
        agent_view=agent_view,
        day=day, day_cap=day_cap, vault_score=vault_score,
        memory_replay=memory_replay,
        chain_hints=chain_hints,
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
    decision, decision_error = _extract_decision_json(response_text)
    fallback_used = False
    if decision_error or not decision.get("moves"):
        fallback_used = True
        decision = _heuristic_fallback_decision(chain_hints, day)

    # 7. Validate moves. If ANY invalid, retry once with error injected;
    #    else fall back to heuristic recommended chain.
    proposed = list(decision.get("moves") or [])
    validations = validators.validate_moves(proposed, agent_view)
    invalid = [(i, r, m) for i, (ok, r, m) in enumerate(validations) if not ok]
    if invalid and not fallback_used:
        # Retry once with the specific validator error surfaced.
        err_summary = "; ".join(f"move[{i}]: {r}" for i, r, _ in invalid[:3])
        retry_prompt = (
            prompt_text
            + f"\n\nRETRY: your previous moves failed validation: {err_summary}\n"
            "Correct them and output ONE JSON object per the schema. GO:\n"
        )
        result = invoker.invoke(
            retry_prompt,
            wallclock_cap_s=_WALLCLOCK_S,
            response_cap_bytes=_RESPONSE_CAP,
        )
        response_text = str(result.get("response") or "")
        retry_decision, retry_err = _extract_decision_json(response_text)
        if not retry_err and retry_decision.get("moves"):
            proposed = list(retry_decision.get("moves") or [])
            validations = validators.validate_moves(proposed, agent_view)
            invalid = [(i, r, m) for i, (ok, r, m) in enumerate(validations) if not ok]
            if not invalid:
                decision = retry_decision
    if invalid:
        # Retry didn't recover or wasn't attempted — heuristic fallback.
        fallback_used = True
        decision = _heuristic_fallback_decision(chain_hints, day)
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
            f"[fallback={fallback_used}] moves={len(final_moves)}"
        ),
        "moves": final_moves,
        "submitted_policy": True,
        "wallclock_capped": bool(result.get("wallclock_capped")),
        "ms_elapsed": ms_elapsed,
        "extras": {
            "inner_agent": AGENT_NAME,
            "plan_label": str(decision.get("plan_this_turn") or "")[:80],
            "predicted_outcome": decision.get("predicted_outcome"),
            "reflection_on_last_night": decision.get("reflection_on_last_night"),
            "materialized_count": len(final_moves),
            "fallback_used": fallback_used,
            "prompt_chars": len(prompt_text),
            "response_chars": len(response_text),
            "submit_result": submit_result,
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


def _extract_decision_json(text: str) -> Tuple[Dict[str, Any], Optional[str]]:
    """Find the first top-level JSON object in ``text`` and parse it."""
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.I).strip()
        raw = re.sub(r"\s*```$", "", raw).strip()
    decoder = _json.JSONDecoder()
    for match in re.finditer(r"\{", raw):
        try:
            parsed, _ = decoder.raw_decode(raw[match.start():])
        except Exception:
            continue
        if isinstance(parsed, dict) and "moves" in parsed:
            return parsed, None
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
