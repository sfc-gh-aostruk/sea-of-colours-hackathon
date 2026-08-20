"""tabula_v8 — night entry point (true fork).

v8 is the consolidation release on the CURRENT stack (haiku, inference API).
It is no longer a thin env-shim over v7: it owns its turn loop and its
FEEDING layer (the 3-pillar worldview prompt in :mod:`.prompt`, the doctrine
in :mod:`.doctrine`), while reusing v7's proven COMPUTATION layer (hint
compilers, sanitizer, wishlist, memory, weapon inference, recorder) by import.

What v8 changes vs v7:
  * Restructured prompt — RULES/DOCTRINE / BOARD-NOW / LAST-NIGHT sections,
    with new ENEMY PROBES + WEAPON GEOMETRY blocks and the collision-aware
    LAST NIGHT / REFLECT blocks (the keystone fix for the redsign-poker
    blind spot).
  * The CONTAINED TWO-CALL SPLIT is native and on by default: a reasoning-
    first thinker (inference API, hard cap) hands a directive to the moves-
    first mover (inference API, schema-guaranteed). Set ``TABULA_V8_SINGLE=1``
    to run mover-only for an A/B.

Flow per turn mirrors v7: close prior-day memory, snapshot, read memory,
build the v8 prompt, (thinker ->) mover, parse/sanitize, submit, persist,
return the dispatcher envelope (with per-sub-agent audit rows).
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Mapping

from sea_of_colours.orchestrator_2.cortex_invoker import CortexAgentInvoker
from sea_of_colours.orchestrator_2.cortex_chat import CortexChatInvoker
from sea_of_colours.orchestrator_2.harnesses.tabula_v7 import (
    chat_schema,
    directive as directive_mod,
    harness as v7h,
    heuristic_chains,
    memory,
    move_sanitizer,
    opponent_weapons,
    orbit_stub,
    probe_hints as probe_hints_mod,
    recorder,
)
from sea_of_colours.orchestrator_2.harnesses.tabula_v7 import (
    orbit_wishlist as wishlist_mod,
)
from sea_of_colours.orchestrator_2.harnesses.tabula_v8 import prompt as prompt_mod

# ── Agent identity ─────────────────────────────────────────────────────
INNER_AGENT_LABEL = "TABULA_V8"
THINKER_AGENT_LABEL = "TABULA_V8_THINKER"
# The rare JSON-finisher fallback reuses v7's dedicated finisher spec.
FINISHER_AGENT_NAME = v7h.FINISHER_AGENT_NAME

# Budgets carried over from v7's contained-split config (measured on seed 42).
_THINKER_CHAT_MODEL = v7h._THINKER_CHAT_MODEL
_THINKER_CHAT_MAX_TOKENS = v7h._THINKER_CHAT_MAX_TOKENS
_THINKER_CHAT_WALLCLOCK_S = v7h._THINKER_CHAT_WALLCLOCK_S
_MOVER_CHAT_MODEL = v7h._MOVER_CHAT_MODEL
_MOVER_CHAT_MAX_TOKENS = v7h._MOVER_CHAT_MAX_TOKENS
_WALLCLOCK_S = v7h._WALLCLOCK_S
_CONTINUATION_WALLCLOCK_S = v7h._CONTINUATION_WALLCLOCK_S
_CONTINUATION_RESPONSE_CAP = v7h._CONTINUATION_RESPONSE_CAP
_MIN_FINISHER_RED_VALUE = v7h._MIN_FINISHER_RED_VALUE
_MAX_MOVES = v7h._MAX_MOVES


def _split_on() -> bool:
    """v8 runs the contained split by default; ``TABULA_V8_SINGLE=1`` disables."""
    return os.environ.get("TABULA_V8_SINGLE", "0").strip().lower() not in (
        "1", "true", "yes",
    )


def clear_snapshots() -> None:
    """Test helper — v8 shares v7's process-local snapshot cache."""
    v7h.clear_snapshots()


# ── Public entry point ─────────────────────────────────────────────────
def run(
    *, store: Any, session_id: str, player: str, view: Mapping[str, Any],
) -> Dict[str, Any]:
    """Drive one v8 arena turn. Returns the dispatcher audit envelope."""
    started = time.time()
    phase = str(
        view.get("phase")
        or (view.get("agent_view", {}).get("meta", {}) or {}).get("phase")
        or ""
    ).lower()
    if phase == "orbit":
        return orbit_stub.submit_orbit(store, session_id, player, view)

    agent_view = view.get("agent_view") or {}
    meta = agent_view.get("meta") or {}
    hud = agent_view.get("hud") or {}
    day = int(meta.get("day") or hud.get("day") or 0)
    day_cap = int(hud.get("season_day_cap") or 7)
    scores = hud.get("scores") or {}
    vault_score = int(scores.get(player) or 0)
    season_name = str(hud.get("season_name") or "")

    # 1. Close prior day's memory with the engine-resolved outcome.
    snap = v7h._SNAPSHOTS.get(v7h._snap_key(session_id, player), {})
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
    v7h._capture_snapshot(session_id, player, day, agent_view)

    # 3. Read memory + the prior-day entry that grounds the REFLECT block.
    prior_entries = memory.read_recent(session_id, player, limit=3, store=store)
    memory_replay = memory.format_replay(prior_entries)
    prior_day_entry = next(
        (e for e in reversed(prior_entries) if int(e.get("day") or 0) == day - 1),
        None,
    )

    # 4. Precompute the deterministic hint menu (reused from v7).
    chain_hints = heuristic_chains.top_chain_hints(agent_view, max_chains=3)
    probe_hints = probe_hints_mod.top_probe_hints(
        agent_view,
        max_hints=3,
        historical_probe_positions=v7h._historical_probe_targets(
            session_id, player, store=store,
        ),
    )
    hot_drop_hints = probe_hints_mod.top_hot_drop_hints(agent_view, max_hints=2)
    supersede_hints = (
        probe_hints_mod.top_supersede_hints(agent_view, max_hints=4)
        if int(day) >= int(day_cap) else []
    )
    weapon_estimates = opponent_weapons.update_estimates(
        session_id, player, agent_view,
    )
    wishlist = wishlist_mod.compute_wishlist(
        agent_view, day=day, opponent_weapon_estimates=weapon_estimates,
    )
    want_blue = any(e.tag == "grab_blue" for e in wishlist.entries)
    blue_hints = (
        heuristic_chains.top_blue_chain_hints(agent_view, max_chains=2)
        if want_blue else []
    )

    prompt_kwargs: Dict[str, Any] = dict(
        agent_view=agent_view,
        day=day, day_cap=day_cap, vault_score=vault_score,
        memory_replay=memory_replay,
        chain_hints=chain_hints,
        probe_hints=probe_hints,
        hot_drop_hints=hot_drop_hints,
        blue_hints=blue_hints,
        supersede_hints=supersede_hints,
        wishlist=wishlist,
        opponent_weapon_estimates=weapon_estimates,
        prior_day_entry=prior_day_entry,
    )

    # 4b. CONTAINED THINKER (reasoning-first, inference API, hard cap).
    directive_block = ""
    thinker_used = False
    thinker_directive = None
    thinker_reasoning = ""
    thinker_response_chars = 0
    thinker_ms = 0
    thinker_prompt = ""
    if _split_on():
        thinker_used = True
        thinker_prompt = prompt_mod.build_prompt(mode="thinker", **prompt_kwargs)
        thinker_started = time.time()
        thinker_invoker = CortexChatInvoker(
            model=_THINKER_CHAT_MODEL,
            response_format=chat_schema.DECISION_RESPONSE_FORMAT,
            max_completion_tokens=_THINKER_CHAT_MAX_TOKENS,
        )
        thinker_result = thinker_invoker.invoke(
            thinker_prompt, wallclock_cap_s=_THINKER_CHAT_WALLCLOCK_S,
        )
        thinker_text = str(thinker_result.get("response") or "")
        raw_directive, thinker_reasoning = directive_mod.parse_directive_json(
            thinker_text,
        )
        thinker_ms = int((time.time() - thinker_started) * 1000)
        thinker_response_chars = len(thinker_text)
        thinker_directive = directive_mod.sanitize_directive(
            raw_directive, agent_view,
        )
        directive_block = directive_mod.format_directive_block(thinker_directive)

    prompt_text = prompt_mod.build_prompt(
        mode="mover", strategist_directive_block=directive_block, **prompt_kwargs,
    )

    # 5. CONTAINED MOVER (moves-first, inference API, schema-guaranteed).
    invoker = CortexChatInvoker(
        model=_MOVER_CHAT_MODEL,
        response_format=chat_schema.MOVES_RESPONSE_FORMAT,
        max_completion_tokens=_MOVER_CHAT_MAX_TOKENS,
    )
    result = invoker.invoke(prompt_text, wallclock_cap_s=_WALLCLOCK_S)
    response_text = str(result.get("response") or "")

    # 6. Parse JSON; on failure, finisher retry then heuristic net.
    decision, decision_error = v7h._extract_decision_json(response_text)
    fallback_used = False
    fallback_reason = ""
    continuation_used = False
    response_text_continuation = ""
    if decision_error or not decision.get("moves"):
        if response_text.strip():
            continuation_used = True
            cont_prompt = v7h._continuation_prompt(
                response_text,
                day=day, day_cap=day_cap,
                orbit_harvesters=probe_hints_mod._orbit_harvester_ids(agent_view),
                chain_hints=chain_hints,
                supersede_hints=supersede_hints,
            )
            finisher_invoker = CortexAgentInvoker(agent_name=FINISHER_AGENT_NAME)
            cont_result = finisher_invoker.invoke(
                cont_prompt,
                wallclock_cap_s=_CONTINUATION_WALLCLOCK_S,
                response_cap_bytes=_CONTINUATION_RESPONSE_CAP,
            )
            cont_text = str(cont_result.get("response") or "")
            response_text_continuation = cont_text
            cont_decision, cont_err = v7h._extract_decision_json(cont_text)
            if not cont_err and cont_decision.get("moves"):
                decision = cont_decision
            else:
                fallback_used = True
                fallback_reason = f"finisher_failed: {cont_err or 'missing moves'}"
                decision = v7h._heuristic_fallback_decision(chain_hints, day)
        else:
            fallback_used = True
            fallback_reason = (
                f"parse: {decision_error}" if decision_error
                else "parse: missing 'moves' key"
            )
            decision = v7h._heuristic_fallback_decision(chain_hints, day)

    proposed = list(decision.get("moves") or [])

    # 7. Mechanical move sanitizer (skip the already-legal heuristic plan).
    sanitizer_log: List[str] = []
    if not fallback_used and proposed:
        is_final_night = int(day) >= int(day_cap)
        enemy_probe_cells = {
            (int(h["probe_at"][0]), int(h["probe_at"][1]))
            for h in supersede_hints
            if isinstance(h.get("probe_at"), (list, tuple))
            and len(h["probe_at"]) == 2
        }
        proposed, sanitizer_log = move_sanitizer.sanitize_moves(
            proposed,
            agent_view,
            chain_hints=chain_hints,
            is_final_night=is_final_night,
            enemy_probe_cells=enemy_probe_cells,
        )
        if continuation_used and chain_hints:
            if v7h._plan_red_value(proposed, agent_view) <= _MIN_FINISHER_RED_VALUE:
                fallback_used = True
                fallback_reason = "finisher_low_value: swapped to heuristic chain"
                decision = v7h._heuristic_fallback_decision(chain_hints, day)
                proposed = list(decision.get("moves") or [])
                sanitizer_log.append(
                    "swapped finisher plan -> heuristic (finisher banked ~no "
                    "reachable RED while chains were available)"
                )

    # 8. Cap + submit.
    final_moves = proposed[:_MAX_MOVES]
    v7h._record_moves(session_id, player, day, final_moves)

    from sea_of_colours.snowpark import engine as soc_engine
    submit_result = soc_engine.submit_policy(store, session_id, player, final_moves)

    # 9. Persist this turn's memory entry.
    entry = memory.new_entry(
        day,
        plan_this_turn=str(decision.get("plan_this_turn") or ""),
        rationale=str(decision.get("rationale") or ""),
        predicted_outcome=(decision.get("predicted_outcome") or {}),
        moves_summary=v7h._summarise_moves(final_moves),
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
            f"[predicted={v7h._pred_label(decision)}] "
            f"[fallback={fallback_used}"
            + (f":{fallback_reason[:120]}" if fallback_used else "")
            + "]"
            + (" [continuation=recovered]"
               if (continuation_used and not fallback_used) else "")
            + (f" [sanitized={len(sanitizer_log)}]" if sanitizer_log else "")
            + (f" [thinker={thinker_directive.posture}"
               + (";chaff" if thinker_directive.chaff_react else "") + "]"
               if thinker_directive
               else (" [thinker=none]" if thinker_used else ""))
            + f" moves={len(final_moves)}"
        ),
        "moves": final_moves,
        "submitted_policy": True,
        "wallclock_capped": bool(result.get("wallclock_capped")),
        "ms_elapsed": ms_elapsed,
        "response": response_text,
        "extras": {
            "inner_agent": INNER_AGENT_LABEL,
            "plan_label": str(decision.get("plan_this_turn") or "")[:80],
            "predicted_outcome": decision.get("predicted_outcome"),
            "reflection_on_last_night": decision.get("reflection_on_last_night"),
            "materialized_count": len(final_moves),
            "fallback_used": fallback_used,
            "fallback_reason": fallback_reason,
            "sanitizer_changes": sanitizer_log,
            "continuation_used": continuation_used,
            "continuation_response_chars": len(response_text_continuation),
            "thinker_used": thinker_used,
            "thinker_directive": (
                {
                    "posture": thinker_directive.posture,
                    "targets": thinker_directive.targets,
                    "chaff_react": thinker_directive.chaff_react,
                    "avoid": thinker_directive.avoid,
                    "note": thinker_directive.note,
                }
                if thinker_directive else None
            ),
            "thinker_response_chars": thinker_response_chars,
            "thinker_api": "chat" if thinker_used else "",
            "thinker_reasoning": thinker_reasoning,
            "thinker_ms": thinker_ms,
            "sub_invocations": (
                [
                    {
                        "label": THINKER_AGENT_LABEL,
                        "kind": "thinker",
                        "api": "chat",
                        "response_text": thinker_reasoning,
                        "rationale": (
                            f"[posture={thinker_directive.posture}"
                            + (";chaff" if thinker_directive.chaff_react else "")
                            + f"] targets={thinker_directive.targets}"
                            if thinker_directive else "[thinker=no directive]"
                        ),
                        "ms_elapsed": thinker_ms,
                        "prompt_excerpt": (thinker_prompt[:32_000]
                                           if thinker_used else ""),
                    }
                ]
                if thinker_used else []
            ),
            "mover_api": "chat",
            "mover_capped": bool(result.get("capped")),
            "prompt_chars": len(prompt_text),
            "response_chars": len(response_text),
            "submit_result": submit_result,
            "prompt_excerpt": prompt_text[:32_000],
        },
    }
