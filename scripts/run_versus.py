#!/usr/bin/env python3
"""Head-to-head season: route each seat to a different agent version.

Runs ONE season on ONE map with up to four seats, each bound to a specific
agent version via its game-config label (``tabula_v9`` / ``tabula_v8`` /
``tabula_v7`` / ``tabula_v6`` / ``heuristic``). Because all seats share the
same seed/map, the final scores are a fair head-to-head.

Prints the final scoreline plus a per-seat turn digest (posture / fallback /
moves) so you can see HOW each version played, not just the totals.

Requires the Snowflake backend + a PAT (cortex versions reach the view via
SOC_GET_VIEW and call the inference/agents APIs).

Usage::

    PYTHONPATH=. python scripts/run_versus.py --seed 42 \
        --seats tabula_v9,tabula_v8,tabula_v7
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_MAX_TURN_ITERATIONS = 600
_HEURISTIC_LABELS = {"heuristic", "red_harvest"}


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="run_versus")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--seats", default="tabula_v9,tabula_v8,tabula_v7",
                   help="Comma-separated agent labels, one per seat (2-4).")
    p.add_argument("--days", type=int, default=None)
    p.add_argument("--width", type=int, default=40)
    p.add_argument("--height", type=int, default=28)
    p.add_argument("--out", default=None)
    p.add_argument("--tag", default=None,
                   help="Short run tag folded into the season name "
                        "(e.g. phase2, redsign-fix).")
    p.add_argument("--name", default=None,
                   help="Full season name override (skips auto-naming).")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    labels = [s.strip() for s in args.seats.split(",") if s.strip()]
    if not (2 <= len(labels) <= 4):
        print("need 2-4 seats", file=sys.stderr)
        return 2

    os.environ.setdefault("SOC_BACKEND", "snowflake")
    # Ensure v7/v6 seats run their DEFAULT (single-call) config; v8's wrapper
    # flips to the contained split only for its own turn and restores after.
    os.environ.setdefault("TABULA_V7_MODE", "single")

    if os.environ["SOC_BACKEND"].lower() != "snowflake":
        print("preflight: cortex versions need SOC_BACKEND=snowflake", file=sys.stderr)
        return 2
    from sea_of_colours.orchestrator_2.cortex_chat import CortexChatInvoker
    if not CortexChatInvoker().is_ready():
        print("preflight: no Snowflake PAT/account found.", file=sys.stderr)
        return 2

    from sea_of_colours.game.session import Phase
    from sea_of_colours.snowpark import backend as soc_backend
    from sea_of_colours.snowpark import engine as soc_engine
    from sea_of_colours.orchestrator_2.runtime import run_agent_turn

    soc_backend.reset_for_tests()
    store = soc_backend.get_store()

    seats = [f"p{i+1}" for i in range(len(labels))]
    label_for = dict(zip(seats, labels))
    agents_for_init = {s: label_for[s] for s in seats}

    from _season_naming import make_season_name
    wanted_name = make_season_name(
        labels, args.seed, args.days, tag=args.tag, override=args.name,
    )
    info = soc_engine.init_session(
        store, seed=args.seed, width=args.width, height=args.height,
        season_day_cap=args.days, players=seats, agents=agents_for_init,
        season_name=wanted_name,
    )
    session_id = info["session_id"]
    season_name = info.get("season_name") or wanted_name
    print("=" * 68)
    print(f"  VERSUS SEASON — {season_name}  (seed {args.seed})")
    for s in seats:
        print(f"    {s}: {label_for[s]}")
    print(f"  session: {session_id}")
    print("=" * 68, flush=True)

    # Per-seat turn digest.
    digest: Dict[str, List[str]] = defaultdict(list)
    iteration = 0
    started = time.time()
    while iteration < _MAX_TURN_ITERATIONS:
        status = soc_engine.get_session_status(store, session_id)
        if status.get("phase") == Phase.SEASON_COMPLETE.value:
            break
        pending = status.get("pending") or {}
        seat = next((s for s in seats if not pending.get(s, False)), None)
        if seat is None:
            soc_engine.run_night(store, session_id)
            iteration += 1
            continue

        day = int(status.get("day", 0))
        phase = str(status.get("phase") or "")
        label = label_for[seat]
        override = "heuristic" if label in _HEURISTIC_LABELS else "cortex"
        t0 = time.time()
        result = run_agent_turn(
            store, session_id, seat,
            runtime_override=override, agent_label=label,
        )
        dt = int((time.time() - t0) * 1000)
        iteration += 1

        if phase != "orbit":
            extras = result.get("extras") or {}
            posture = ""
            if isinstance(extras, dict):
                d = extras.get("thinker_directive") or {}
                posture = (d or {}).get("posture") or ""
            tag = (f"d{day} {result.get('agent_id','?')}: "
                   f"{'posture=' + posture + ' ' if posture else ''}"
                   f"{'FELLBACK ' if result.get('fell_back') else ''}{dt}ms")
            digest[seat].append(tag)
            print("  " + tag, flush=True)

    # Final scoreline.
    final_view = soc_engine.get_view(store, session_id, seats[0])
    scores = final_view.get("scores") or {}
    print("\n" + "=" * 68)
    print(f"  RESULT — {season_name}")
    ranked = sorted(seats, key=lambda s: int(scores.get(s, 0)), reverse=True)
    for rank, s in enumerate(ranked, 1):
        marker = " <-- winner" if rank == 1 else ""
        print(f"    {rank}. {s} {label_for[s]:<12} {int(scores.get(s,0)):>6}{marker}")
    print("=" * 68)
    print(f"  wall time: {time.time()-started:.0f}s", flush=True)

    if args.out:
        lines = [f"# Versus season — {season_name} (seed {args.seed})", ""]
        lines.append(f"session: `{session_id}`  scores: {dict(scores)}\n")
        for rank, s in enumerate(ranked, 1):
            lines.append(f"{rank}. **{s} = {label_for[s]}** — {int(scores.get(s,0))} pts")
        lines.append("\n## Per-seat planning digest\n")
        for s in seats:
            lines.append(f"### {s} — {label_for[s]}")
            for t in digest[s]:
                lines.append(f"- {t}")
            lines.append("")
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text("\n".join(lines), encoding="utf-8")
        print(f"  report: {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
