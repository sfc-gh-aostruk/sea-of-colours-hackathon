"""Orbit-phase submission helpers for tabula v3.

Two callable functions:

  * :func:`submit_empty_orbit` — the phase-1 default. Submits ``[]`` so
    the engine advances but no builds / ships / refines / repairs are
    performed. Fastest but leaves parcels stuck in the hoard (they
    only bank as 50%-fire-sale at season end — see
    ``game/session.py:compute_player_score``).

  * :func:`submit_heuristic_orbit` — routes the orbit turn through
    RED_HARVEST's ``plan_orbit_actions``. This ships harvested parcels
    via the catapult (so they score with full tier×purity multiplier),
    builds new harvesters + probes when affordable, and jettisons
    greens. Used for solo runs and any live season where we actually
    care about final vault totals.

The harness picks between them per :envvar:`TABULA_V3_ORBIT_MODE`
(``"empty"`` or ``"heuristic"``, default ``"heuristic"``).
"""

from __future__ import annotations

import os
import time
from typing import Any, Mapping

from sea_of_colours.snowpark import engine as soc_engine


def submit_empty_orbit(
    store: Any, session_id: str, player: str,
) -> Mapping[str, Any]:
    """Submit an empty orbit action queue and return the audit envelope.

    The audit envelope mirrors the shape run_agent_turn() returns for
    normal turns so downstream loggers don't need a special case.
    """
    started = time.time()
    result = soc_engine.submit_orbit_actions(store, session_id, player, [])
    ms_elapsed = int((time.time() - started) * 1000)
    return {
        "ok": True,
        "agent_id": "TABULA_V3",
        "runtime": "harness_in_process",
        "rationale": (
            "[orbit stub — phase-1 has no orbit LLM; submitting empty so "
            "engine advances to next night]"
        ),
        "orbit_actions_count": 0,
        "ms_elapsed": ms_elapsed,
        "submit_result": result,
    }


def submit_heuristic_orbit(
    store: Any, session_id: str, player: str, view: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Route the orbit turn through RED_HARVEST's ``plan_orbit_actions``.

    Full playbook (from :func:`sea_of_colours.agent.heuristic_agent.plan_orbit_actions`):

      1. Repair damaged harvesters.
      2. Build a new harvester (under fleet cap + affordable).
      3. Build 2 probes (or 1 if only 1 affordable).
      4. SHIP RED via the catapult — this is the critical action; it
         moves parcels from the hoard to SHIPPED (full-score bucket).
      5. Jettison green parcels so they don't accumulate the -100 penalty.

    Falls back to :func:`submit_empty_orbit` on any exception so an
    orbit failure never blocks a season.
    """
    started = time.time()
    try:
        from sea_of_colours.agent.heuristic_agent import plan_orbit_actions
        agent_view = view.get("agent_view") or view
        actions, rationale = plan_orbit_actions(agent_view)
        result = soc_engine.submit_orbit_actions(
            store, session_id, player, list(actions),
        )
        ms_elapsed = int((time.time() - started) * 1000)
        return {
            "ok": True,
            "agent_id": "TABULA_V3",
            "runtime": "harness_in_process",
            "rationale": f"[orbit heuristic] {rationale}",
            "orbit_actions_count": len(actions),
            "ms_elapsed": ms_elapsed,
            "submit_result": result,
        }
    except Exception as exc:  # pragma: no cover — defensive fallback
        # A broken orbit heuristic must NEVER block the season. Log the
        # reason in the envelope so the multinight driver surfaces it.
        empty_env = submit_empty_orbit(store, session_id, player)
        empty_env["rationale"] = (
            f"[orbit heuristic FAILED: {type(exc).__name__}: {exc}] "
            "fell back to empty orbit — parcels will not ship this turn"
        )
        return empty_env


def submit_orbit(
    store: Any, session_id: str, player: str, view: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Dispatch the orbit turn based on ``TABULA_V3_ORBIT_MODE``.

    Default is ``"heuristic"`` (ships parcels, builds units). Set to
    ``"empty"`` to force the legacy no-op path (useful for regression
    tests where the empty-stub score is the baseline).
    """
    mode = os.environ.get("TABULA_V3_ORBIT_MODE", "heuristic").strip().lower()
    if mode == "empty":
        return submit_empty_orbit(store, session_id, player)
    return submit_heuristic_orbit(store, session_id, player, view)
