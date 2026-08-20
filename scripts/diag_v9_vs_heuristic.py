#!/usr/bin/env python3
"""Instrumented 1v1: tabula_v9 vs the pure heuristic (RED_HARVEST).

Unlike ``run_versus.py`` (final totals only), this captures per-night
GROUND TRUTH for each seat so we can pin the "banked but vault empty" gap:

  * ``score``        — shipped vault score right now (only rises on catapult)
  * ``hoard_pct``    — how full the unshipped hoard is
  * ``banked``       — parcels the engine actually banked into hoard last night
                       (count + summed purity)  ← the agent's TRUE harvest
  * ``collisions``   — simultaneous-drop pile-ups this seat was in last night
                       (each one = a damaged harvester that banked ZERO)

The recap block describes the night that JUST ended, so we snapshot each
seat's view once per day and attribute the recap to ``day - 1``.

Usage::

    PYTHONPATH=. python scripts/diag_v9_vs_heuristic.py --seed 42 --days 7
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_MAX_TURN_ITERATIONS = 600
_HEURISTIC_LABELS = {"heuristic", "red_harvest"}


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="diag_v9_vs_heuristic")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--days", type=int, default=7)
    p.add_argument("--width", type=int, default=40)
    p.add_argument("--height", type=int, default=28)
    p.add_argument("--seats", default="tabula_v9,heuristic",
                   help="Comma-separated agent labels, one per seat (2-4).")
    p.add_argument("--out", default="reports/diag_v9_vs_heuristic.md")
    p.add_argument("--tag", default=None,
                   help="Short run tag folded into the season name "
                        "(e.g. phase2, redsign-fix).")
    p.add_argument("--name", default=None,
                   help="Full season name override (skips auto-naming).")
    return p


def _banked_summary(recap: Dict[str, Any]) -> Tuple[int, int]:
    """(#parcels banked into hoard last night, summed purity)."""
    rows = recap.get("my_parcels_banked") or []
    n = 0
    purity = 0
    for r in rows:
        if not isinstance(r, dict):
            n += 1
            continue
        n += 1
        purity += int(r.get("purity", r.get("value", 0)) or 0)
    return n, purity


def _collision_summary(recap: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    for c in (recap.get("my_collisions") or []):
        at = c.get("at")
        others = ",".join(str(o) for o in (c.get("others") or []))
        out.append(f"@{at} with [{others}] ({c.get('party_count')}-way)")
    return out


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    labels = [s.strip() for s in args.seats.split(",") if s.strip()]
    if not (2 <= len(labels) <= 4):
        print("need 2-4 seats", file=sys.stderr)
        return 2

    os.environ.setdefault("SOC_BACKEND", "snowflake")
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
    print(f"  DIAG 1v1 — {season_name}  (seed {args.seed}, {args.days}d)")
    for s in seats:
        print(f"    {s}: {label_for[s]}")
    print(f"  session: {session_id}")
    print("=" * 68, flush=True)

    # (day, seat) -> snapshot dict. Recap attributed to day-1 (the night that
    # ended). We snapshot the first time we see each (day, seat) at night phase.
    snaps: Dict[Tuple[int, str], Dict[str, Any]] = {}

    def _snapshot(day: int, seat: str) -> None:
        try:
            v = soc_engine.get_view(store, session_id, seat)
        except Exception as exc:  # pragma: no cover
            print(f"  [snap fail d{day} {seat}: {exc}]", flush=True)
            return
        av = v.get("agent_view") or v
        hud = av.get("hud") or {}
        recap = av.get("last_night") or {}
        n_banked, purity = _banked_summary(recap)
        collisions = _collision_summary(recap)
        night_ended = day - 1
        snaps[(night_ended, seat)] = {
            "score": int((hud.get("scores") or {}).get(seat, hud.get("score", 0)) or 0),
            "hoard_pct": float((hud.get("hoard") or {}).get("pct_full", 0.0) or 0.0),
            "banked_n": n_banked,
            "banked_purity": purity,
            "collisions": collisions,
        }

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

        # Snapshot BEFORE the night turn (recap describes the prior night).
        if phase != "orbit" and (day - 1, seat) not in snaps and day >= 1:
            _snapshot(day, seat)

        override = "heuristic" if label in _HEURISTIC_LABELS else "cortex"
        t0 = time.time()
        result = run_agent_turn(
            store, session_id, seat,
            runtime_override=override, agent_label=label,
        )
        dt = int((time.time() - t0) * 1000)
        iteration += 1

        if phase != "orbit":
            print(f"  d{day} {result.get('agent_id','?'):<14} {dt}ms", flush=True)

    # Final scores + a terminal snapshot for the last night.
    final_view = soc_engine.get_view(store, session_id, seats[0])
    fav = final_view.get("agent_view") or final_view
    scores = (fav.get("hud") or {}).get("scores") or final_view.get("scores") or {}
    last_day = int((fav.get("hud") or {}).get("day", args.days) or args.days)
    for s in seats:
        _snapshot(last_day + 1, s)

    print("\n" + "=" * 68)
    print(f"  RESULT — {season_name}")
    ranked = sorted(seats, key=lambda s: int(scores.get(s, 0)), reverse=True)
    for rank, s in enumerate(ranked, 1):
        marker = " <-- winner" if rank == 1 else ""
        print(f"    {rank}. {s} {label_for[s]:<12} {int(scores.get(s,0)):>6}{marker}")
    print("=" * 68)
    print(f"  wall time: {time.time()-started:.0f}s", flush=True)

    # Markdown report — per-seat per-night ground truth table.
    lines = [f"# Diag 1v1 — {season_name} (seed {args.seed})", ""]
    lines.append(f"session: `{session_id}`  final scores: {dict(scores)}\n")
    for rank, s in enumerate(ranked, 1):
        lines.append(f"{rank}. **{s} = {label_for[s]}** — {int(scores.get(s,0))} pts")
    lines.append("")
    all_nights = sorted({n for (n, _s) in snaps.keys() if n >= 0})
    for s in seats:
        lines.append(f"\n## {s} — {label_for[s]}\n")
        lines.append("| night | vault_score | hoard% | banked (n / purity) | collisions |")
        lines.append("|------:|------------:|-------:|--------------------:|:-----------|")
        for n in all_nights:
            snap = snaps.get((n, s))
            if not snap:
                continue
            coll = "; ".join(snap["collisions"]) or "-"
            lines.append(
                f"| {n} | {snap['score']} | {int(snap['hoard_pct']*100)}% | "
                f"{snap['banked_n']} / {snap['banked_purity']} | {coll} |"
            )
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("\n".join(lines), encoding="utf-8")
    print(f"  report: {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
