"""Headless season runner — orchestrator_2 variant.

Thin wrapper around ``scripts.run_season`` that swaps the runtime
import so PILOT_V2 (and any other agent bound in
``orchestrator_2.binding_registry``) routes through the harness with
its candidates + threat + memory envelope.

Identical CLI to ``run_season.py`` — see ``--help`` there.

Usage::

    PYTHONPATH=. SOC_BACKEND=snowflake \\
        python scripts/run_season_v2.py \\
            --p1 cortex --p2 heuristic \\
            --cortex-agent SOC_RED_REAPER_PILOT_V2 \\
            --days 7
"""

from __future__ import annotations

import sys

# Patch the runtime import BEFORE run_season is imported, so the
# ``from sea_of_colours.agent.runtime import run_agent_turn`` inside
# run_season's main() resolves to our orchestrator_2 implementation.
import sea_of_colours.agent.runtime as _legacy_runtime
from sea_of_colours.orchestrator_2.runtime import (
    run_agent_turn as _v2_run_agent_turn,
)
from sea_of_colours.snowpark import engine as _soc_engine


def _v2_run_agent_turn_legacy_shape(store, session_id, player, runtime_override=None):
    """Wrap orchestrator_2's runtime so its response dict matches the
    legacy contract that ``run_season.py`` reads.

    Legacy keys ``run_season.py`` consumes:
    - ``moves``           : list (for ``len()``)
    - ``submitted``       : bool
    - ``night_resolved``  : bool

    orchestrator_2.runtime returns:
    - ``submitted_policy`` : bool          → maps to ``submitted``
    - ``extras["moves_count"]`` : int      → expanded to a placeholder list
    - night_resolved        : not tracked  → derived from session phase
                                              change pre/post call.
    """
    pre = _soc_engine.get_session_status(store, session_id) or {}
    pre_day = int(pre.get("day", 0))

    result = _v2_run_agent_turn(store, session_id, player, runtime_override=runtime_override)

    post = _soc_engine.get_session_status(store, session_id) or {}
    post_day = int(post.get("day", pre_day))
    night_resolved = post_day > pre_day

    # Adapt response.
    submitted = bool(result.get("submitted_policy")) or bool(result.get("ok"))
    moves_count = 0
    extras = result.get("extras") or {}
    if isinstance(extras, dict):
        moves_count = int(extras.get("moves_count") or 0)
    # Display reads len(result["moves"]); fabricate a stub list.
    result["moves"] = [None] * moves_count
    result["submitted"] = submitted
    result["night_resolved"] = night_resolved
    return result


# Substitute the symbol the season runner imports.
_legacy_runtime.run_agent_turn = _v2_run_agent_turn_legacy_shape


def main() -> int:
    """Defer to the legacy season runner's main with the patched runtime."""
    from scripts.run_season import main as _legacy_main
    return _legacy_main()


if __name__ == "__main__":
    sys.exit(main())
