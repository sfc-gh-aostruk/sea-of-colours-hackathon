"""Multi-night persistent testing rig for Tabula v2.

Plays the ``arena_persistent`` scenario end-to-end across 4 nights:

  Night 1 (setup): board is entirely fog. The agent must probe to
                   reveal RED cells (no legal drops possible).
  Nights 2-4      : agent harvests what its probes revealed on prior
                    nights AND lays additional probes as needed.
                    Vision from night-1 probes persists for 3 nights.

The rig drives the real engine turn loop via
:func:`sea_of_colours.orchestrator_2.runtime.run_agent_turn` so all
mid-night resolution, orbit stubs, probe expiry, and score banking
happen naturally. After the final night, prints a per-night breakdown
plus a final endgame summary.

**IMPORTANT**: this rig is for Tabula v2 (``SOC_RED_REAPER_TABULA_V2``)
only. The v1 testing rig (single-turn ``arena_day1``/``arena_day2``/
``arena_day3`` scenarios + ``tabula_hallucination_audit.py``) remains
unmodified and continues to be the v1 regression harness.

Run:
    SOC_BACKEND=memory python3 scripts/tabula_v2_multinight.py

Env:
    ``SOC_BACKEND``           = memory (default) | snowpark
    ``TABULA_V2_SEATS``       = comma-list of seat/agent pairs, default:
                                ``p1=tabula_v2,p2=heuristic``
    ``TABULA_V2_MAX_ITERS``   = safety cap on turn iterations (default 40)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List, Mapping

os.environ.setdefault("SOC_BACKEND", "memory")

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sea_of_colours.evals import get_scenario  # noqa: E402
from sea_of_colours.game.session import Phase  # noqa: E402
from sea_of_colours.snowpark import engine as soc_engine  # noqa: E402
from sea_of_colours.orchestrator_2.runtime import run_agent_turn  # noqa: E402


def _peek_pending(store, session_id: str, seat: str) -> List[Dict[str, Any]]:
    """Hydrate the session and read what seat just submitted this turn.

    The dispatcher's public return type is a boolean submitted_policy
    flag, so we peek at the raw session's pending_policies to get the
    actual move list back for logging. Read-only.
    """
    try:
        sess = soc_engine._hydrate_session(store, session_id)
    except Exception:
        return []
    pending = sess.pending_policies.get(seat) or []
    out: List[Dict[str, Any]] = []
    for m in pending:
        # ``Move`` dataclasses have a to_wire()-like shape via .asdict or
        # attribute access. Support both.
        d = getattr(m, "__dict__", None)
        if d:
            out.append(dict(d))
        elif isinstance(m, Mapping):
            out.append(dict(m))
    return out


# ─── snapshot helpers ──────────────────────────────────────────────────


def _snapshot(store, session_id: str, seat: str) -> Dict[str, Any]:
    """Compact view snapshot — day, red_visible count, fog, probes, harvesters."""
    view = soc_engine.get_view(store, session_id, seat)
    av = view.get("agent_view") or {}
    world = av.get("world") or {}
    entities = (av.get("entities") or {}).get("mine") or []
    probes_alive = [
        {"id": e.get("id"), "at": e.get("pos"), "nights_remaining": e.get("nights_remaining")}
        for e in entities
        if isinstance(e, Mapping) and e.get("type") == "probe"
    ]
    # Harvester state comes from ``my_assets`` — ``entities.mine`` reports
    # state=None for orbit-state harvesters, which is misleading. The
    # harness itself reads ``my_assets`` to enumerate drop-eligible
    # harvesters, so we match its source.
    my_assets = av.get("my_assets") or []
    harvesters_alive = [
        {"id": a.get("id"), "state": a.get("state"), "at": a.get("pos")}
        for a in my_assets
        if isinstance(a, Mapping) and a.get("kind") == "harvester"
    ]
    return {
        "day": av.get("meta", {}).get("day"),
        "phase": view.get("phase"),
        "red_visible": len(av.get("red_tiles") or []),
        "fog_count": world.get("fog_count"),
        "probe_stock": (av.get("orbit") or {}).get("probe_stock"),
        "probes_alive": probes_alive,
        "vault_score": av.get("hud", {}).get("scores", {}).get(seat) if isinstance(av.get("hud", {}).get("scores"), dict) else av.get("hud", {}).get("score"),
        "harvesters_alive": harvesters_alive,
    }


def _fmt_snapshot(snap: Mapping[str, Any]) -> str:
    probes = snap["probes_alive"]
    probe_str = ", ".join(
        f"{p['id']}@{tuple(p['at']) if p['at'] else '?'} nr={p.get('nights_remaining')}"
        for p in probes
    ) or "(none)"
    # Harvester stock breakdown by state (orbit vs deployed vs anything else).
    harvs = snap.get("harvesters_alive") or []
    hv_by_state: Dict[str, int] = {}
    for h in harvs:
        st = str(h.get("state") or "?")
        hv_by_state[st] = hv_by_state.get(st, 0) + 1
    hv_summary = ",".join(f"{k}={v}" for k, v in sorted(hv_by_state.items())) or "none"
    return (
        f"day={snap['day']} phase={snap['phase']}  "
        f"red_visible={snap['red_visible']}  fog={snap['fog_count']}  "
        f"probe_stock={snap['probe_stock']}  "
        f"harvesters={len(harvs)}({hv_summary})  "
        f"vault={snap['vault_score']}  "
        f"probes=[{probe_str}]"
    )


# ─── runner ────────────────────────────────────────────────────────────


def run_multinight(
    scenario_name: str = "arena_persistent",
    p1_label: str = "tabula_v2",
    p2_label: str = "heuristic",
    max_iters: int = 40,
) -> Dict[str, Any]:
    scenario = get_scenario(scenario_name)
    store, session_id = scenario.build()

    print(f"\n{'='*70}\nTabula v2 multi-night rig — scenario={scenario_name}")
    print(f"session_id={session_id}  p1={p1_label}  p2={p2_label}")
    print(f"{'='*70}\n")

    # Register the seat labels so run_agent_turn can dispatch correctly.
    seat_labels = {"p1": p1_label, "p2": p2_label}
    per_turn_log: List[Dict[str, Any]] = []

    initial_snap = _snapshot(store, session_id, "p1")
    print(f"START  {_fmt_snapshot(initial_snap)}\n")

    iteration = 0
    while iteration < max_iters:
        status = soc_engine.get_session_status(store, session_id)
        phase = status.get("phase")
        if phase == Phase.SEASON_COMPLETE.value:
            print("\n=== SEASON COMPLETE ===")
            break

        pending = status.get("pending") or {}
        # Iterate over the ACTUAL seats in this session (from
        # ``get_session_status``) rather than a hardcoded pair — solo
        # scenarios (``arena_solo``) have only ["p1"], and the engine
        # rejects turns for seats it doesn't know about.
        active_seats = tuple(status.get("players") or ("p1", "p2"))
        seat = next(
            (s for s in active_seats if not pending.get(s, False)),
            None,
        )
        if seat is None:
            # All seats submitted but phase didn't advance — force resolve.
            soc_engine.run_night(store, session_id)
            iteration += 1
            continue

        pre_snap = _snapshot(store, session_id, seat)
        agent_label = seat_labels[seat]

        t0 = time.time()
        # p2 uses the heuristic (no cortex call needed).
        runtime_override = "heuristic" if agent_label == "heuristic" else None
        result = run_agent_turn(
            store,
            session_id,
            seat,
            runtime_override=runtime_override,
            agent_label=None if agent_label == "heuristic" else agent_label,
        )
        elapsed = time.time() - t0

        submitted = result.get("submitted_policy")
        # ``submitted_policy`` from the dispatcher is a bool. Re-read the
        # session's pending_policies to get the actual move list back.
        moves = _peek_pending(store, session_id, seat) if submitted else []
        counts = {"drop": 0, "step": 0, "pickup": 0, "probe": 0}
        for m in moves:
            if isinstance(m, Mapping):
                counts[m.get("a") or m.get("kind")] = counts.get(m.get("a") or m.get("kind"), 0) + 1

        if seat == "p1":
            print(f"[day {pre_snap['day']} phase {pre_snap['phase']}] p1={agent_label}  {elapsed:.1f}s  submitted_policy={submitted}")
            print(f"  {_fmt_snapshot(pre_snap)}")
            print(f"  submitted {len(moves)} moves: drop={counts['drop']} step={counts['step']} pickup={counts['pickup']} probe={counts['probe']}")
            for m in moves:
                print(f"    {m}")
            per_turn_log.append({
                "day": pre_snap["day"], "seat": seat, "agent_label": agent_label,
                "elapsed_s": round(elapsed, 1),
                "counts": counts, "moves": moves,
                "runtime": result.get("runtime"),
                "response_preview": (result.get("response") or "")[:200],
            })
        else:
            print(f"[day {pre_snap['day']}] p2=heuristic submitted {len(moves)} moves")

        iteration += 1

    end_snap = _snapshot(store, session_id, "p1")
    print(f"\nEND    {_fmt_snapshot(end_snap)}")

    endgame = soc_engine.get_endgame_summary(store, session_id)
    scores = endgame.get("scores") or endgame.get("final_scores") or {}
    print(f"\nFINAL SCORES: {scores}")

    return {
        "session_id": session_id,
        "per_turn": per_turn_log,
        "final_scores": scores,
        "endgame": endgame,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", default="arena_persistent")
    parser.add_argument("--p1", default="tabula_v2", help="agent label for p1")
    parser.add_argument("--p2", default="heuristic", help="agent label for p2")
    parser.add_argument("--max-iters", type=int, default=40)
    parser.add_argument("--dump-json", help="write per-turn log to this path")
    args = parser.parse_args()

    result = run_multinight(
        scenario_name=args.scenario,
        p1_label=args.p1,
        p2_label=args.p2,
        max_iters=args.max_iters,
    )

    if args.dump_json:
        with open(args.dump_json, "w") as f:
            json.dump({
                "session_id": result["session_id"],
                "per_turn": result["per_turn"],
                "final_scores": result["final_scores"],
            }, f, indent=2, default=str)
        print(f"\nWrote per-turn log to {args.dump_json}")


if __name__ == "__main__":
    main()
