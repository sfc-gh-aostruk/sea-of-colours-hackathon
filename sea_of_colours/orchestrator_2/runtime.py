"""Thin runtime for orchestrator_2.

The orchestrator's only public function: :func:`run_agent_turn`. It does
five things, in order:

1. Loads the per-seat view via :func:`soc_engine.get_view`.
2. If the phase is ORBIT, delegates to the legacy heuristic
   :func:`plan_orbit_actions` and exits. Orbit phase is universal —
   no agent reasons about it directly.
3. Resolves the seat's :class:`AgentBinding` via the binding registry.
4. Calls :func:`dispatcher.dispatch_turn` with the universal envelope.
5. Reconciles ``SOC_POLICY_QUEUE``; on missed submission, falls back to
   the heuristic so the night still resolves.
6. Writes one row to ``SOC_AGENT_INVOCATION`` and returns the envelope.

Nothing in this module names a specific agent. ``PILOT_V2`` is not
mentioned; ``RED_HARVEST`` only as the fallback. Every other agent
identity lives in the binding registry or inside a harness.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

from sea_of_colours.agent.heuristic_agent import (
    plan_moves as _heuristic_plan_moves,
)
from sea_of_colours.agent.heuristic_agent import plan_orbit_actions
from sea_of_colours.agent.runtime import HEURISTIC_AGENT_NAME
from sea_of_colours.orchestrator_2 import audit as _audit
from sea_of_colours.orchestrator_2.binding_registry import (
    HEURISTIC_BINDING,
    resolve_binding,
)
from sea_of_colours.orchestrator_2.dispatcher import dispatch_turn
from sea_of_colours.snowpark import engine as soc_engine
from sea_of_colours.snowpark import snapshot as soc_snapshot


def _seat_has_pending(store, session_id: str, player: str) -> bool:
    """Did this seat lock a policy for the current day?"""
    try:
        status = soc_engine.get_session_status(store, session_id) or {}
        pending = status.get("pending") or {}
        return bool(pending.get(player, False))
    except Exception:  # pragma: no cover - defensive
        return False


def _heuristic_fallback(
    *,
    store,
    session_id: str,
    player: str,
    view: Dict[str, Any],
    reason: str,
) -> Dict[str, Any]:
    """Land a policy when Cortex / a harness didn't submit.

    v0.9.27 — Try the harness's compiled ``candidates.recommended_policy``
    FIRST. It's the harness's own best-guess plan, already legal and
    tuned for RED-seeking (drop_blocks routed first, top harvest per
    harvester, balanced probes, supersede when juicy). Only if that
    compile fails or emits an empty queue do we drop to the legacy
    RED_HARVEST heuristic, which biases toward BLUE topup on failure —
    a worse plan than the harness's recommended composition.
    """
    agent_view = view.get("agent_view") or {}

    # Try the harness's own recommended policy first.
    recommended_moves = []
    try:
        from sea_of_colours.orchestrator_2.harnesses.pilot_v2.candidates import (
            compile_candidates,
        )
        compiled = compile_candidates(agent_view) or {}
        rec = ((compiled.get("candidates") or {}).get("recommended_policy") or {})
        maybe = rec.get("moves") if isinstance(rec, dict) else None
        if isinstance(maybe, list) and maybe:
            recommended_moves = maybe
    except Exception:
        recommended_moves = []

    if recommended_moves:
        soc_engine.submit_policy(store, session_id, player, recommended_moves)
        return {
            "agent_id": HEURISTIC_AGENT_NAME,
            "runtime": "heuristic_fallback",
            "rationale": (
                f"FALLBACK ({reason}) — used harness "
                f"recommended_policy ({len(recommended_moves)} moves): "
                f"drop_blocks routed first, top harvest per harvester, "
                f"balanced probes."
            ),
            "moves_count": len(recommended_moves),
            "ok": True,
        }

    # Second-line fallback: legacy RED_HARVEST heuristic. Only fires when
    # the harness's own compile failed — genuinely rare.
    moves, rationale = _heuristic_plan_moves(agent_view)
    soc_engine.submit_policy(store, session_id, player, moves)
    return {
        "agent_id": HEURISTIC_AGENT_NAME,
        "runtime": "heuristic_fallback",
        "rationale": (
            f"FALLBACK ({reason}) — recommended_policy empty; "
            f"used RED_HARVEST heuristic: " + (rationale or "")
        ),
        "moves_count": len(moves),
        "ok": True,
    }


def run_agent_turn(
    store,
    session_id: str,
    player: str,
    runtime_override: Optional[str] = None,
    agent_label: Optional[str] = None,
) -> Dict[str, Any]:
    """End-to-end turn for one seat in orchestrator_2.

    Mirrors the public contract of
    :func:`sea_of_colours.agent.runtime.run_agent_turn` so existing
    callers (eval runner, run_season, FastAPI handlers) can be pointed
    at orchestrator_2 by changing only the import.

    ``agent_label`` lets a caller pin the seat's binding from the game
    config (``GameSession.agents``) — the live server passes
    ``"pilot_v2"`` here so the harness is selected without env vars.
    """
    started = time.time()
    view = soc_engine.get_view(store, session_id, player)
    agent_view = view.get("agent_view") or {}
    day = int(view.get("day", agent_view.get("hud", {}).get("day", 0)))

    # Freeze the board the instant before a seat plans, when SOC_SNAPSHOT_PREFIX
    # is set. This is the only moment the pre-decision state exists — the
    # session blob is overwritten as the night resolves.
    soc_snapshot.maybe_take(
        store, session_id, day, player, str(view.get("phase") or "")
    )

    # ── Orbit phase: binding-aware dispatch. ──────────────────────────
    #
    # v1.8 — orbit is no longer forced through the heuristic. When the
    # seat's binding declares a harness (e.g. PILOT_V2), we route the
    # orbit turn through it so the same Cortex agent that plays the
    # night also owns weapon purchases, harvester builds, refinement,
    # and shipping. The heuristic remains the fallback path for seats
    # without a harness binding and as the safety net when a harness
    # binding fails to submit.
    if str(view.get("phase") or "") == "orbit":
        binding = resolve_binding(
            store, session_id, player,
            runtime_override=runtime_override, agent_label=agent_label,
        )
        if binding.kind == "heuristic":
            # RED_HARVEST_LITE (the hackathon "no weapons" tutorial
            # opponent, binding_registry.HEURISTIC_LITE_BINDING) never
            # builds chaff/EMP in orbit either — same playbook otherwise.
            weapons_enabled = binding.locator != "RED_HARVEST_LITE"
            agent_id = binding.agent_label or HEURISTIC_AGENT_NAME
            orbit_actions, rationale = plan_orbit_actions(
                agent_view, weapons_enabled=weapons_enabled,
            )
            soc_engine.submit_orbit_actions(store, session_id, player, orbit_actions)
            ms_elapsed = int((time.time() - started) * 1000)
            soc_engine.save_agent_rationale(
                store,
                session_id,
                day,
                agent_id,
                player,
                rationale,
                runtime="heuristic",
                tool_calls=[{"name": "soc_submit_orbit_actions",
                             "args": {"action_count": len(orbit_actions)}}],
                ms_elapsed=ms_elapsed,
            )
            return {
                "agent_id": agent_id,
                "runtime": "heuristic",
                "rationale": rationale,
                "orbit_actions_count": len(orbit_actions),
                "ms_elapsed": ms_elapsed,
                "ok": True,
            }
        # Harness / cortex binding — route through the same dispatcher
        # that handles the night phase. The harness reads meta.phase
        # and switches to the orbit prompt + orbit tool.
        dispatch = dispatch_turn(
            store=store, session_id=session_id, player=player,
            view=view, binding=binding,
        )
        landed = dispatch.submitted_policy
        if not landed:
            time.sleep(0.2)
            landed = _seat_has_pending(store, session_id, player)
        if not landed:
            # Harness missed — fall back to heuristic so orbit still resolves.
            orbit_actions, rationale = plan_orbit_actions(agent_view)
            soc_engine.submit_orbit_actions(store, session_id, player, orbit_actions)
            ms_elapsed = int((time.time() - started) * 1000)
            # Audit the miss so we can see PILOT_V2 was invoked but didn't submit.
            from sea_of_colours.orchestrator_2.dispatcher import DispatchResult
            fb_result = DispatchResult(
                ok=False,
                elapsed_ms=ms_elapsed,
                submitted_policy=True,
                rationale=f"[fallback after {binding.kind} orbit miss] {rationale}",
                extras={"binding_kind": binding.kind, "fell_back": True,
                        "phase": "orbit"},
            )
            _audit.write_invocation(
                store=store, session_id=session_id, player=player,
                day=day, binding=binding, result=fb_result,
            )
            soc_engine.save_agent_rationale(
                store,
                session_id,
                day,
                HEURISTIC_AGENT_NAME,
                player,
                f"[fallback after {binding.kind} orbit miss] {rationale}",
                runtime="heuristic",
                tool_calls=[{"name": "soc_submit_orbit_actions",
                             "args": {"action_count": len(orbit_actions)}}],
                ms_elapsed=ms_elapsed,
            )
            return {
                "agent_id": HEURISTIC_AGENT_NAME,
                "runtime": "heuristic",
                "rationale": f"[fallback] {rationale}",
                "orbit_actions_count": len(orbit_actions),
                "ms_elapsed": ms_elapsed,
                "ok": True,
            }
        # Happy path — harness submitted successfully. Write audit.
        ms_elapsed = dispatch.elapsed_ms or int((time.time() - started) * 1000)
        _audit.write_invocation(
            store=store, session_id=session_id, player=player,
            day=day, binding=binding, result=dispatch,
        )
        return {
            "agent_id": binding.agent_label,
            "runtime": binding.kind,
            "rationale": dispatch.rationale,
            "orbit_actions_count": 0,  # dispatch doesn't count — audit tool_calls does
            "ms_elapsed": ms_elapsed,
            "submitted_policy": dispatch.submitted_policy,
            "ok": bool(dispatch.ok),
            # v1.9 — propagate the harness's extras dict so the eval
            # runner can read ``plan_label`` / ``decision.selections`` /
            # ``materialized_count`` for coherence assertions on orbit
            # turns. Without this the orbit branch dropped the entire
            # extras block and every orbit scenario reported
            # ``no plan_label extracted by runner``.
            "extras": dispatch.extras,
        }

    # ── Planning phase: binding-driven dispatch. ───────────────────────
    binding = resolve_binding(
        store, session_id, player,
        runtime_override=runtime_override, agent_label=agent_label,
    )
    dispatch = dispatch_turn(
        store=store, session_id=session_id, player=player,
        view=view, binding=binding,
    )

    # ── Reconcile: did the agent actually land a policy row? ───────────
    landed = dispatch.submitted_policy
    if not landed and binding.kind != "heuristic":
        # Warehouse-commit visibility race: re-poll after a brief beat.
        time.sleep(0.2)
        landed = _seat_has_pending(store, session_id, player)
        if not landed:
            time.sleep(0.8)
            landed = _seat_has_pending(store, session_id, player)

    if not landed and binding.kind != "heuristic":
        # ── E1 (seed-69 day-1 double night-resolution) — RETRY IN PLACE.
        #
        # A cold-start miss on the FIRST cortex call of the season (the
        # Inference-API client warming up its connection/auth) returned
        # submitted_policy=False in ~3s WITHOUT running the pipeline. The
        # old code dropped straight to the heuristic fallback below, which
        # SUBMITTED a placeholder policy. Once every seat had a placeholder
        # the night resolved (Nox #1) — and then the retried cortex turns
        # (picked up again off a stale session read) submitted their REAL
        # policies and resolved the SAME day a SECOND time (Nox #2). That
        # double-resolution is the "teleport"/reset-probe-counter corruption.
        #
        # The transient miss self-heals on retry (proven: the day-1 retry
        # ran the full THINK→PLAN→MOVE pipeline and submitted). Re-dispatch
        # the REAL binding ONCE here so the seat keeps ownership of its turn
        # and no premature fallback submission is made. Reaching this point
        # already means the re-poll saw no pending row, so a retry cannot
        # double-submit for this seat.
        retry = dispatch_turn(
            store=store, session_id=session_id, player=player,
            view=soc_engine.get_view(store, session_id, player),
            binding=binding,
        )
        if retry.submitted_policy:
            dispatch = retry
            landed = True
        else:
            time.sleep(0.2)
            landed = _seat_has_pending(store, session_id, player)
            if landed:
                dispatch = retry

    if not landed and binding.kind != "heuristic":
        # Cortex agent or harness missed twice — fire the safety-net
        # heuristic so the night can still resolve.
        fb = _heuristic_fallback(
            store=store, session_id=session_id, player=player,
            view=view,
            reason=f"binding={binding.kind} did not submit",
        )
        ms_elapsed = int((time.time() - started) * 1000)
        # Audit BOTH the missed dispatch and the fallback. The audit row
        # carries the agent_label of the *intended* binding so the UI
        # shows which agent was supposed to play.
        from sea_of_colours.orchestrator_2.dispatcher import DispatchResult
        fb_result = DispatchResult(
            ok=False,
            elapsed_ms=ms_elapsed,
            submitted_policy=True,
            rationale=fb["rationale"],
            extras={"binding_kind": binding.kind, "fell_back": True,
                    "moves_count": fb.get("moves_count", 0)},
        )
        _audit.write_invocation(
            store=store, session_id=session_id, player=player,
            day=day, binding=binding, result=fb_result,
        )
        return {
            "agent_id": fb["agent_id"],
            "runtime": "heuristic_fallback",
            "rationale": fb["rationale"],
            "binding_kind": binding.kind,
            "binding_label": binding.agent_label,
            "ms_elapsed": ms_elapsed,
            "ok": True,
            "fell_back": True,
        }

    # ── Happy path: agent submitted (or the heuristic binding ran). ────
    ms_elapsed = dispatch.elapsed_ms or int((time.time() - started) * 1000)
    _audit.write_invocation(
        store=store, session_id=session_id, player=player,
        day=day, binding=binding, result=dispatch,
    )
    return {
        "agent_id": binding.agent_label or binding.locator,
        "runtime": binding.kind,
        "rationale": dispatch.rationale or dispatch.response[:400],
        "response": dispatch.response,
        "tool_calls": dispatch.tool_calls,
        "binding_kind": binding.kind,
        "binding_locator": binding.locator,
        "binding_label": binding.agent_label,
        "ms_elapsed": ms_elapsed,
        "submitted_policy": dispatch.submitted_policy,
        "wallclock_capped": dispatch.wallclock_capped,
        "ok": dispatch.ok,
        "error": dispatch.error,
        "extras": dispatch.extras,
    }
