"""Trivial orbit passthrough for tabula phase 1.

Submits an empty orbit action queue so the engine advances to the next
night. Phase 1 has no orbit LLM: builds, ships, refines, and repairs
are all deferred to later phases.

The engine's ``submit_orbit_actions`` accepts an empty list and marks
the seat as ready for orbit resolution. Once both seats submit (the
opponent seat is p2=heuristic or p2=nobody, both of which happily
submit empty), the engine resolves the orbit and phase advances.
"""

from __future__ import annotations

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
        "agent_id": "TABULA_V2",
        "runtime": "harness_in_process",
        "rationale": (
            "[orbit stub — phase-1 has no orbit LLM; submitting empty so "
            "engine advances to next night]"
        ),
        "orbit_actions_count": 0,
        "ms_elapsed": ms_elapsed,
        "submit_result": result,
    }
