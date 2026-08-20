"""Solo smoke-test runner for tabula_v11 (ONE seat, no opponents).

Runs v11 by itself on a 1-player game so we can verify the harness executes a
full season end-to-end after the Phase-3 changes (A1 persistent green guard +
Part B CONTEST_DENY) without exceptions, and eyeball the per-night engine log
for green penalties / crashes / aurora losses. A solo board has no rivals, so
CASE-2 (Part B) is not exercised here — this is the "does it still run and not
harm itself" smoke test the fuller vs-heuristic / mirror sweep builds on.

Usage::

    SOC_BACKEND=snowflake python scripts/run_solo_v11.py            # seeds 69,2,56
    SOC_BACKEND=snowflake python scripts/run_solo_v11.py --seeds 69 # just one
    python scripts/run_solo_v11.py --days 7 --tag SMOKE
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import List, Optional

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_AGENT = "SOC_RED_REAPER_TABULA_V11"


def _run_one(seed: int, *, days: Optional[int], tag: str) -> dict:
    from sea_of_colours.orchestrator_2.runtime import run_agent_turn
    from sea_of_colours.game.session import SEASON_DAY_CAP, Phase
    from sea_of_colours.snowpark import backend as soc_backend
    from sea_of_colours.snowpark import engine as soc_engine

    soc_backend.reset_for_tests()
    store = soc_backend.get_store()

    season_name = f"V11_SOLO_{tag}_s{seed}"
    info = soc_engine.init_session(
        store, seed=seed, width=40, height=28,
        season_name=season_name, season_day_cap=days,
        players=["p1"], agents={"p1": "cortex"},
    )
    session_id = info["session_id"]
    cap = int(info.get("season_day_cap") or SEASON_DAY_CAP)
    print(f"\n=== SOLO v11 | season={season_name} | session={session_id} | "
          f"seed={seed} | cap={cap} ===", flush=True)

    started = time.time()
    green_hits = 0
    crash_hits = 0
    aurora_hits = 0
    iterations = 0
    MAX_ITERS = 400
    while iterations < MAX_ITERS:
        status = soc_engine.get_session_status(store, session_id)
        if status.get("phase") == Phase.SEASON_COMPLETE.value:
            break
        pending = status.get("pending") or {}
        if pending.get("p1", False):
            soc_engine.run_night(store, session_id)
            iterations += 1
            continue
        pre = int((soc_engine.get_session_status(store, session_id) or {}).get("day", 0))
        res = run_agent_turn(store, session_id, "p1", runtime_override="cortex")
        post = soc_engine.get_session_status(store, session_id) or {}
        post_day = int(post.get("day", pre))
        resolved = post_day > pre
        ms = int(res.get("ms_elapsed", 0))
        print(f"  [day {pre}] {res.get('agent_id','?'):<12} {ms:>6}ms "
              f"submit={'Y' if res.get('submitted_policy') or res.get('ok') else 'N'}"
              f"{'  NIGHT_RESOLVED' if resolved else ''}", flush=True)
        if resolved:
            rows = store.list_log(session_id, day_from=pre, day_to=pre)
            for r in rows:
                t = str(r.get("text", "")).lower()
                if "green" in t and ("penal" in t or "harvest" in t):
                    green_hits += 1
                    print(f"      GREEN? · {r.get('text','')}", flush=True)
                if "collision" in t or "crush" in t:
                    crash_hits += 1
                if "aurora" in t or "destroyed" in t or "dawn" in t:
                    aurora_hits += 1
        iterations += 1

    view = soc_engine.get_view(store, session_id, "p1")
    score = int((view.get("scores") or {}).get("p1", 0))
    elapsed = time.time() - started
    print(f"  --> FINAL p1 score={score} | green_flags={green_hits} "
          f"crash={crash_hits} aurora={aurora_hits} | wall={elapsed:.1f}s",
          flush=True)
    return {"seed": seed, "session_id": session_id, "score": score,
            "green": green_hits, "crash": crash_hits, "aurora": aurora_hits,
            "wall_s": round(elapsed, 1), "season": season_name}


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="run_solo_v11")
    p.add_argument("--seeds", type=int, nargs="*", default=[69, 2, 56])
    p.add_argument("--days", type=int, default=None)
    p.add_argument("--tag", default="SMOKE")
    args = p.parse_args(argv)

    os.environ.setdefault("SOC_BACKEND", "snowflake")
    os.environ["SOC_CORTEX_AGENT"] = _AGENT

    results = []
    for seed in args.seeds:
        try:
            results.append(_run_one(seed, days=args.days, tag=args.tag))
        except Exception as e:  # keep going so one bad seed doesn't kill the set
            import traceback
            print(f"  !! seed {seed} FAILED: {e}", flush=True)
            traceback.print_exc()
            results.append({"seed": seed, "error": str(e)})

    print("\n==================== SOLO v11 SUMMARY ====================", flush=True)
    for r in results:
        if "error" in r:
            print(f"  seed {r['seed']}: ERROR {r['error']}", flush=True)
        else:
            print(f"  seed {r['seed']:>3}: score={r['score']:>5} "
                  f"green={r['green']} crash={r['crash']} aurora={r['aurora']} "
                  f"wall={r['wall_s']}s  ({r['season']})", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
