"""Per-seat driver: routes each seat to its own harness via agent_label.

The default run_season.py hardcodes agents_for_init to {"cortex":"cortex", "heuristic":"red_harvest"},
which means both cortex seats share the same SOC_CORTEX_AGENT and can't differ. This driver
overrides two things:

1. soc_engine.init_session — force GameSession.agents to the labels we want ("tabula_v5" / "tabula_v4").
2. orchestrator_2.runtime.run_agent_turn — extract that label from the game session on each turn
   and pass it as agent_label= to resolve_binding, so step-0 (per-seat label) wins.

Usage:
    PYTHONPATH=. python3 scripts/run_per_seat.py \\
        --season V5b_vs_V4_seed42_d7 \\
        --p1-label tabula_v5 --p2-label tabula_v4 --seed 42
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))


def _main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", required=True)
    ap.add_argument("--p1-label", required=True)
    ap.add_argument("--p2-label", required=True)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--days", type=int, default=7)
    args = ap.parse_args()

    p1_label = args.p1_label
    p2_label = args.p2_label

    os.environ.setdefault("SOC_BACKEND", "snowflake")
    os.environ.setdefault("SOC_CONNECTION", "lucasaws1")

    # Patch legacy runtime import BEFORE run_season sees it.
    import sea_of_colours.agent.runtime as _legacy_runtime  # noqa: F401
    from sea_of_colours.orchestrator_2.runtime import run_agent_turn as _v2_run
    from sea_of_colours.snowpark import engine as _soc_engine

    import json as _json

    def _extract_agent_label(store, session_id: str, player: str):
        try:
            sess = store.load_session(session_id)
        except Exception:
            return None
        if not sess:
            return None
        js = sess.get("json_state") or {}
        if isinstance(js, str):
            try:
                js = _json.loads(js)
            except Exception:
                js = {}
        agents = js.get("agents") or {}
        return agents.get(player)

    def _v2_shim(store, session_id, player, runtime_override=None):
        pre = _soc_engine.get_session_status(store, session_id) or {}
        pre_day = int(pre.get("day", 0))
        # Extract this seat's label from the game session and pass through.
        lbl = _extract_agent_label(store, session_id, player)
        res = _v2_run(store, session_id, player,
                      runtime_override=runtime_override,
                      agent_label=lbl)
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

    # Force GameSession.agents to the labels we want.
    _orig_init = _soc_engine.init_session

    def _patched_init(store, **kw):
        agents = dict(kw.get("agents") or {})
        agents["p1"] = p1_label
        agents["p2"] = p2_label
        kw["agents"] = agents
        return _orig_init(store, **kw)

    _soc_engine.init_session = _patched_init  # type: ignore[assignment]

    # Now stage argv for run_season and call its main.
    is_cortex = lambda lbl: lbl != "red_harvest" and lbl not in ("heuristic", "human")
    p1_runtime = "cortex" if is_cortex(p1_label) else "heuristic"
    p2_runtime = "cortex" if is_cortex(p2_label) else "heuristic"

    sys.argv = [
        "run_per_seat",
        "--p1", p1_runtime, "--p2", p2_runtime,
        "--cortex-agent", "SOC_RED_REAPER_TABULA_V5",  # banner label; per-seat routing overrides
        "--seed", str(args.seed),
        "--days", str(args.days),
        "--season-name", args.season,
        "-q",
    ]

    # scripts.run_season also stubs its own soc_engine import — patch that too.
    import scripts.run_season as rs
    if hasattr(rs, "soc_engine"):
        rs.soc_engine.init_session = _patched_init  # type: ignore[attr-defined]

    return rs.main()


if __name__ == "__main__":
    sys.exit(_main())
