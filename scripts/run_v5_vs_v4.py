"""Ad-hoc driver: run a season with different agent labels per seat.

Reuses run_season's plumbing but replaces the hardcoded
_STRATEGY_SLUG mapping so that agents_for_init passes the exact
AGENT_LABEL_BINDINGS key ("tabula_v5", "tabula_v4") into
GameSession.agents. That way resolve_binding's step-0
agent_label lookup routes each seat to its correct harness.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

# CLI: python scripts/run_v5_vs_v4.py <season_name> <p1_label> <p2_label> [seed]
season = sys.argv[1] if len(sys.argv) > 1 else "V5b_vs_V4_seed42_d7"
p1_label = sys.argv[2] if len(sys.argv) > 2 else "tabula_v5"
p2_label = sys.argv[3] if len(sys.argv) > 3 else "tabula_v4"
seed = int(sys.argv[4]) if len(sys.argv) > 4 else 42

os.environ.setdefault("SOC_BACKEND", "snowflake")
os.environ.setdefault("SOC_CONNECTION", "lucasaws1")

# Patch runtime to orchestrator_2's before run_season imports.
import sea_of_colours.agent.runtime as _legacy_runtime  # noqa: F401
from sea_of_colours.orchestrator_2.runtime import run_agent_turn as _v2_run
from sea_of_colours.snowpark import engine as _soc_engine


def _v2_shim(store, session_id, player, runtime_override=None):
    pre = _soc_engine.get_session_status(store, session_id) or {}
    pre_day = int(pre.get("day", 0))
    res = _v2_run(store, session_id, player, runtime_override=runtime_override)
    post = _soc_engine.get_session_status(store, session_id) or {}
    post_day = int(post.get("day", pre_day))
    night_resolved = post_day > pre_day
    submitted = bool(res.get("submitted_policy")) or bool(res.get("ok"))
    moves_count = int((res.get("extras") or {}).get("moves_count") or 0)
    return {
        "moves": [None] * moves_count,
        "submitted": submitted,
        "night_resolved": night_resolved,
        "rationale": res.get("rationale") or "",
        "agent_id": res.get("agent_id"),
    }


_legacy_runtime.run_agent_turn = _v2_shim  # type: ignore[assignment]

# Now patch run_season's _STRATEGY_SLUG BEFORE importing it, so the
# label we picked lands in GameSession.agents where resolve_binding's
# step-0 lookup finds it.
import scripts.run_season as rs

# Monkeypatch the module-level dict resolver used at init.
_ORIG_MAIN = rs.main


def main() -> int:
    # Force our labels into agents_for_init by swapping the runtime
    # names for actual label strings. run_season.main() builds
    # agents_for_init from _STRATEGY_SLUG[runtime_for[player]].
    # Instead we just override the args globally.
    argv = [
        "run_season_v2",
        "--p1", "cortex", "--p2", "cortex",
        "--cortex-agent", "SOC_RED_REAPER_TABULA_V5",  # not consulted per-seat, just for banner
        "--seed", str(seed),
        "--days", "7",
        "--season-name", season,
        "-q",
    ]
    sys.argv = argv

    # Reach into run_season and swap the strategy slug map so cortex
    # seats get the exact label the AGENT_LABEL_BINDINGS resolver expects.
    rs._STRATEGY_SLUG = {"heuristic": "red_harvest", "cortex": "__PER_SEAT__"}

    # And hijack agents_for_init construction: patch dict lookup so it
    # returns the correct label per seat.
    _real_dict_lookup = dict.get

    # Simplest: monkeypatch the agents_for_init line by replacing
    # the whole main() with a patched version. Copy-paste is uglier.
    # Instead, we can patch by making _STRATEGY_SLUG a defaultdict-like
    # returning the correct label per player. But main() only calls it
    # via .get(runtime_for[s], "red_harvest") where s is p1/p2.
    class _PerSeatSlug(dict):
        _p_map = {"p1": p1_label, "p2": p2_label}
        _current_seat = None
        def get(self, key, default=None):
            # This class is called as _STRATEGY_SLUG.get(runtime_for[s], default),
            # where key is "cortex" or "heuristic". We need per-seat resolution but
            # only see the runtime string here. Instead, override the dict-comp:
            return super().get(key, default)

    # Simpler approach: post-hoc mutate the game session after init_session
    # returns. Hook by wrapping soc_engine.init_session.
    from sea_of_colours.snowpark import engine as eng
    _orig_init = eng.init_session

    def _patched_init(store, **kw):
        # Force per-seat labels regardless of what caller passed.
        agents = dict(kw.get("agents") or {})
        agents["p1"] = p1_label
        agents["p2"] = p2_label
        kw["agents"] = agents
        return _orig_init(store, **kw)

    eng.init_session = _patched_init
    # ALSO patch the imported symbol inside run_season if it grabbed a
    # local reference.
    if hasattr(rs, "soc_engine"):
        rs.soc_engine.init_session = _patched_init  # type: ignore[attr-defined]

    return _ORIG_MAIN()


if __name__ == "__main__":
    sys.exit(main())
