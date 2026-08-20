"""True single-seat SOLO driver for the tabula_v5 harness.

Unlike run_season.py (hardcoded to p1+p2), this initialises the engine
with players=["p1"] only so there is no opponent seat, and drives every
turn through orchestrator_2's runtime with the tabula_v5 harness.

Usage:
    PYTHONPATH=. python3 scripts/run_solo_v5.py --season V5b_SOLO_seed42_d7 --seed 42 --days 7
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))


def _main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", required=True)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--width", type=int, default=40)
    ap.add_argument("--height", type=int, default=28)
    args = ap.parse_args()

    os.environ.setdefault("SOC_BACKEND", "snowflake")
    os.environ.setdefault("SOC_CONNECTION", "lucasaws1")

    from sea_of_colours.snowpark.backend import get_store
    from sea_of_colours.snowpark import engine as soc_engine
    from sea_of_colours.orchestrator_2.runtime import run_agent_turn
    from sea_of_colours.game.session import Phase

    store = get_store()
    players = ["p1"]
    agents = {"p1": "tabula_v5"}

    info = soc_engine.init_session(
        store,
        seed=args.seed,
        width=args.width,
        height=args.height,
        season_day_cap=args.days,
        players=players,
        agents=agents,
        season_name=args.season,
    )
    session_id = info["session_id"]
    print(f"session_id={session_id} season={args.season} seed={args.seed}")

    MAX_ITER = 200
    started = time.time()
    iteration = 0

    while iteration < MAX_ITER:
        status = soc_engine.get_session_status(store, session_id)
        if status.get("phase") == Phase.SEASON_COMPLETE.value:
            break
        pending = status.get("pending") or {}
        seat = next((s for s in players if not pending.get(s, False)), None)
        if seat is None:
            soc_engine.run_night(store, session_id)
            iteration += 1
            continue
        run_agent_turn(store, session_id, seat, agent_label="tabula_v5")
        iteration += 1

    view = soc_engine.get_view(store, session_id, "p1")
    scores = view.get("scores") or {}
    print(f"final score p1={scores.get('p1', 0)}")
    print(f"iterations={iteration} wall={round(time.time() - started, 1)}s")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
