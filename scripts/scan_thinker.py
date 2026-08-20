#!/usr/bin/env python3
"""Scan the tabula_v7 CONTAINED THINKER's reasoning across scenarios.

The v7 two-call split's thinker now runs on the Cortex *inference* API with a
reasoning-FIRST json-schema and a hard token cap (the containment fix, applied
to the thinker instead of only the mover — see harness ``_thinker_api``). This
tool drives real headless seasons with that contained thinker enabled and dumps,
for every planning night, the thinker's captured chain-of-thought alongside the
directive it produced and the moves the mover ultimately played.

It exists to answer the one question the split lives or dies on: **does the
contained thinker actually REASON** (contest / supersede / stagger / hold), or
does it just narrate? Read the ``reasoning`` blocks in the report and judge.

Scenarios are produced by varying the board (seed) and the number of heuristic
opponents (1-3 — the "up to 3 other players" case). Each season naturally walks
the thinker through uncontested nights, contested-redsign nights, post-chaff
nights, and final-convert nights.

Requires the Snowflake backend + a PAT (cortex agents reach the view via
SOC_GET_VIEW and the thinker calls the inference API). With no creds it prints a
clear preflight message and exits 2 — the harness/schema wiring is still exercised
by the unit tests in tests/test_tabula_v7_contained_thinker.py.

Usage::

    PYTHONPATH=. python scripts/scan_thinker.py --seeds 42,7,101 --opponents 1
    PYTHONPATH=. python scripts/scan_thinker.py --seed 42 --count 3 --opponents 3
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# The agent under scan and its thinker sub-agent label (must match the harness).
_CORTEX_AGENT = "SOC_RED_REAPER_TABULA_V7"
_MAX_TURN_ITERATIONS = 400


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="scan_thinker",
        description="Run seasons with the contained thinker and dump its reasoning.",
    )
    g = p.add_mutually_exclusive_group()
    g.add_argument("--seeds", default=None,
                   help="Comma-separated seed list, e.g. '42,7,101'.")
    g.add_argument("--seed", type=int, default=None,
                   help="Base seed (with --count, runs seed, seed+1, ...).")
    p.add_argument("--count", type=int, default=1,
                   help="How many consecutive seeds to run from --seed (default 1).")
    p.add_argument("--opponents", type=int, default=1, choices=(1, 2, 3),
                   help="Heuristic opponents facing the thinker (default 1).")
    p.add_argument("--days", type=int, default=None,
                   help="Planning days per season (default engine default = 7).")
    p.add_argument("--width", type=int, default=40)
    p.add_argument("--height", type=int, default=28)
    p.add_argument("--out", default=None,
                   help="Report path (default reports/thinker_scan_<ts>.md).")
    return p


def _resolve_seeds(args: argparse.Namespace) -> List[int]:
    if args.seeds:
        return [int(s) for s in args.seeds.split(",") if s.strip()]
    base = args.seed if args.seed is not None else 42
    return [int(base) + i for i in range(max(1, int(args.count)))]


def _scan_one_season(
    *, seed: int, opponents: int, days: Optional[int], width: int, height: int,
) -> Dict[str, Any]:
    """Run one season; return {seed, season_name, session_id, nights:[...]}.

    Each night entry: {day, posture, targets, chaff_react, avoid, note,
    reasoning, thinker_ms, moves_summary, mover_rationale, fell_back}.
    """
    from sea_of_colours.game.session import Phase
    from sea_of_colours.snowpark import backend as soc_backend
    from sea_of_colours.snowpark import engine as soc_engine
    from sea_of_colours.orchestrator_2.runtime import run_agent_turn

    soc_backend.reset_for_tests()
    store = soc_backend.get_store()

    seats = ["p1"] + [f"p{i}" for i in range(2, 2 + opponents)]
    runtime_for = {"p1": "cortex"}
    for s in seats[1:]:
        runtime_for[s] = "heuristic"
    agents_for_init = {"p1": "cortex", **{s: "red_harvest" for s in seats[1:]}}

    info = soc_engine.init_session(
        store, seed=seed, width=width, height=height,
        season_day_cap=days, players=seats, agents=agents_for_init,
    )
    session_id = info["session_id"]
    season_name = info.get("season_name") or "(unnamed)"

    nights: List[Dict[str, Any]] = []
    iteration = 0
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

        pre_day = int(status.get("day", 0))
        pre_phase = str(status.get("phase") or "")
        result = run_agent_turn(
            store, session_id, seat, runtime_override=runtime_for[seat],
        )
        iteration += 1

        # Only the thinker seat's PLANNING turns carry a directive.
        if seat != "p1" or pre_phase == "orbit":
            continue
        extras = result.get("extras") or {}
        if not isinstance(extras, dict) or not extras.get("thinker_used"):
            continue
        d = extras.get("thinker_directive") or {}
        nights.append({
            "day": pre_day,
            "posture": (d or {}).get("posture"),
            "targets": (d or {}).get("targets"),
            "chaff_react": (d or {}).get("chaff_react"),
            "avoid": (d or {}).get("avoid"),
            "note": (d or {}).get("note"),
            "reasoning": str(extras.get("thinker_reasoning") or ""),
            "thinker_ms": int(extras.get("thinker_ms") or 0),
            "thinker_api": extras.get("thinker_api"),
            "moves_summary": _summarise(result.get("moves") or extras.get("materialized_count")),
            "mover_rationale": str(result.get("rationale") or "")[:300],
            "fell_back": bool(result.get("fell_back")),
        })

    final_view = soc_engine.get_view(store, session_id, "p1")
    scores = final_view.get("scores") or {}
    return {
        "seed": seed,
        "opponents": opponents,
        "season_name": season_name,
        "session_id": session_id,
        "scores": scores,
        "nights": nights,
    }


def _summarise(moves: Any) -> str:
    if isinstance(moves, int):
        return f"{moves} moves"
    if not isinstance(moves, list):
        return str(moves)
    parts: List[str] = []
    for m in moves:
        if not isinstance(m, dict):
            continue
        a = str(m.get("a") or "")
        if a == "drop":
            parts.append(f"drop@{m.get('at')}")
        elif a == "step":
            parts.append(f"->{m.get('to')}")
        elif a == "pickup":
            parts.append("pickup")
        elif a == "probe":
            parts.append(f"probe@{m.get('at')}")
    return ", ".join(parts) or "(none)"


def _render_report(seasons: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    lines.append("# Contained-thinker reasoning scan\n")
    lines.append(
        "Each night below shows the tabula_v7 contained thinker's captured "
        "chain-of-thought (`reasoning`, generated FIRST under a hard token cap) "
        "and the directive it handed the mover. Read the reasoning: is it "
        "actually deciding (contest / supersede / stagger / hold), or narrating?\n"
    )
    for s in seasons:
        lines.append(f"\n## seed {s['seed']} — {s['season_name']} "
                     f"({s['opponents']} opponent(s))")
        lines.append(f"session: `{s['session_id']}`  scores: {s['scores']}\n")
        if not s["nights"]:
            lines.append("_No thinker nights captured (all turns fell back or "
                         "the thinker returned no directive)._\n")
            continue
        for n in s["nights"]:
            lines.append(f"### day {n['day']}  —  posture=`{n['posture']}`"
                         f"  chaff_react={n['chaff_react']}  "
                         f"({n['thinker_ms']}ms, api={n['thinker_api']})")
            if n["targets"]:
                lines.append(f"- targets: {n['targets']}")
            if n["avoid"]:
                lines.append(f"- avoid: {n['avoid']}")
            if n["note"]:
                lines.append(f"- note: {n['note']}")
            lines.append(f"- mover played: {n['moves_summary']}"
                         + ("  **[FELL BACK]**" if n["fell_back"] else ""))
            reasoning = n["reasoning"].strip() or "_(empty — no CoT captured)_"
            lines.append("\n> " + reasoning.replace("\n", "\n> ") + "\n")
    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)

    # Contained thinker + contained mover, both on the inference API.
    os.environ["TABULA_V7_MODE"] = "split"
    os.environ["TABULA_V7_THINKER_API"] = "chat"
    os.environ["TABULA_V7_MOVER_API"] = "chat"
    os.environ.setdefault("SOC_BACKEND", "snowflake")
    os.environ["SOC_CORTEX_AGENT"] = _CORTEX_AGENT

    # Preflight: cortex needs Snowflake + a PAT.
    backend = os.environ["SOC_BACKEND"].lower()
    if backend != "snowflake":
        print(f"preflight: SOC_BACKEND={backend!r} — the thinker needs the "
              "snowflake backend (view via SOC_GET_VIEW). Set SOC_BACKEND="
              "snowflake.", file=sys.stderr)
        return 2
    from sea_of_colours.orchestrator_2.cortex_chat import CortexChatInvoker
    if not CortexChatInvoker().is_ready():
        print("preflight: no Snowflake PAT/account found (SNOWFLAKE_PAT env or "
              "~/.ssh/sf_config). The thinker cannot call the inference API. "
              "The wiring is still covered by tests/test_tabula_v7_contained_"
              "thinker.py.", file=sys.stderr)
        return 2

    seeds = _resolve_seeds(args)
    print(f"scanning contained thinker over {len(seeds)} season(s): {seeds} "
          f"vs {args.opponents} heuristic opponent(s)", flush=True)

    seasons: List[Dict[str, Any]] = []
    for seed in seeds:
        t0 = time.time()
        print(f"  seed {seed} ...", flush=True)
        try:
            res = _scan_one_season(
                seed=seed, opponents=args.opponents, days=args.days,
                width=args.width, height=args.height,
            )
        except Exception as exc:  # keep going across seeds
            print(f"    seed {seed} failed: {exc}", file=sys.stderr, flush=True)
            continue
        seasons.append(res)
        print(f"    {len(res['nights'])} thinker night(s) captured in "
              f"{time.time()-t0:.0f}s", flush=True)

    report = _render_report(seasons)
    out = args.out or str(
        _REPO_ROOT / "reports" / f"thinker_scan_{int(time.time())}.md"
    )
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(report, encoding="utf-8")
    print(f"\nreport written: {out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
