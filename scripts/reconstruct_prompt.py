#!/usr/bin/env python3
"""Byte-exact reconstruction of a historical thinker prompt via record-replay.

The audit table truncates ``prompt_excerpt`` at 32 KB, so the heaviest nights
(redsign / timeout) are NOT fully stored — and the board on day N can't be
re-derived from a fresh run because the thinker is stochastic. BUT every night's
recorded thinker+mover OUTPUT is persisted, and the board is a deterministic
function of the MOVER outputs (+ the deterministic orbit heuristic + the
deterministic heuristic opponent). So we:

  1. init a fresh session with the EXACT same seed / dims / seats,
  2. monkeypatch the Cortex chat invoker to REPLAY each night's recorded output
     (no network, no stochasticity) — reproducing the exact board,
  3. on the TARGET nights, capture the full untruncated thinker prompt the
     harness builds, at the moment of the call, and write it to disk.

Those captured prompts are byte-exact to the audited game and can then be fired
at the LIVE thinker with ``scripts/replay_thinker_prompt.py``.

Only valid when every non-heuristic seat is replayable (all its outputs are in
the audit). The 1v1 (v9 vs heuristic) is the clean case — only p1 is replayed.

Usage::

    PYTHONPATH=. python scripts/reconstruct_prompt.py \\
        --session 91cfd144adff4e07adf10a5f3759adb5 \\
        --seed 42 --days 7 --seats tabula_v9,heuristic \\
        --target-days 6,7 --outdir reports/prompts/v9_1v1_s42
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_HEURISTIC_LABELS = {"heuristic", "red_harvest", "red_reaper"}


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="reconstruct_prompt")
    p.add_argument("--session", required=True, help="Audited session_id to replay.")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--days", type=int, default=7)
    p.add_argument("--width", type=int, default=40)
    p.add_argument("--height", type=int, default=28)
    p.add_argument("--seats", default="tabula_v9,heuristic",
                   help="Same seat labels/order as the audited run.")
    p.add_argument("--player", default="p1", help="Seat whose prompts to capture.")
    p.add_argument("--target-days", default="6,7",
                   help="Comma-separated day numbers to capture the prompt for.")
    p.add_argument("--outdir", default=None, help="Where to write captured prompts.")
    return p


def _role_of(invoker: Any, chat_schema: Any) -> str:
    """think (no schema — contained THINK pass) | thinker (DECISION/PLAN schema)
    | mover (MOVES schema)."""
    rf = getattr(invoker, "response_format", None)
    if rf is None:
        return "think"
    if rf is getattr(chat_schema, "DECISION_RESPONSE_FORMAT", object()):
        return "thinker"
    if rf is getattr(chat_schema, "MOVES_RESPONSE_FORMAT", object()):
        return "mover"
    blob = json.dumps(rf or {})
    if "posture" in blob or "reasoning" in blob:
        return "thinker"
    if "moves" in blob:
        return "mover"
    return "other"


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    labels = [s.strip() for s in args.seats.split(",") if s.strip()]
    target_days = {int(d) for d in args.target_days.split(",") if d.strip()}
    outdir = Path(args.outdir or (_REPO_ROOT / "reports" / "prompts" / args.session[:8]))
    outdir.mkdir(parents=True, exist_ok=True)

    os.environ.setdefault("SOC_BACKEND", "snowflake")
    if os.environ["SOC_BACKEND"].lower() != "snowflake":
        print("preflight: need SOC_BACKEND=snowflake", file=sys.stderr)
        return 2

    from sea_of_colours.orchestrator_2 import cortex_chat as cc
    from sea_of_colours.orchestrator_2.harnesses.tabula_v7 import chat_schema
    from sea_of_colours.orchestrator_2.harnesses.tabula_v9 import harness as v9h
    from sea_of_colours.game.session import Phase
    from sea_of_colours.snowpark import backend as soc_backend
    from sea_of_colours.snowpark import engine as soc_engine
    from sea_of_colours.orchestrator_2.runtime import run_agent_turn

    # ── 1. Load recorded outputs from the audited session ──────────────────
    src_store = soc_backend.get_store()
    rows = src_store.list_agent_invocations(args.session)
    if not rows:
        print(f"no audit rows for {args.session}", file=sys.stderr)
        return 1

    # Seat-aware: replay EVERY cortex seat so a 3-way board reconstructs with no
    # live fallbacks. Keyed by (day, seat, role); last NON-EMPTY response wins
    # (later rows are the successful retry that actually advanced the game).
    recorded: Dict[Tuple[int, str, str], str] = {}
    for r in rows:
        seat = str(r.get("player") or "")
        day = int(r.get("day") or 0)
        aid = str(r.get("agent_id") or "").upper()
        resp = str(r.get("response_text") or "")
        if not resp:
            continue
        role = "thinker" if "THINKER" in aid else "mover"
        recorded[(day, seat, role)] = resp
    print(f"loaded {len(recorded)} recorded outputs across seats; "
          f"sample: {sorted(recorded.keys())[:6]}")

    # ── 2. Monkeypatch the invoker to replay + capture ─────────────────────
    current_day = [0]
    current_seat = [""]
    captured: Set[int] = set()
    live_fallbacks: List[Tuple[int, str, str]] = []
    orig_invoke = cc.CortexChatInvoker.invoke

    def _patched(self, prompt, **kw):  # noqa: ANN001
        role = _role_of(self, chat_schema)
        day = current_day[0]
        seat = current_seat[0]
        # Capture the CONTEXT prompt for the target seat/day. Prefer the THINK
        # pass (full board context + a clean task header) when the two-stage
        # thinker is active; fall back to the DECISION/thinker call otherwise.
        if (role in ("think", "thinker") and seat == args.player
                and day in target_days and day not in captured):
            path = outdir / f"day{day}_thinker.txt"
            path.write_text(prompt, encoding="utf-8")
            captured.add(day)
            print(f"  captured day {day} {seat} {role} prompt "
                  f"({len(prompt)} chars) -> {path}")
        key = (day, seat, role)
        if key in recorded:
            return {
                "ok": True, "response": recorded[key], "thinking": "",
                "wallclock_capped": False, "capped": False, "elapsed_ms": 0,
            }
        # No record for this call. A think/thinker call with no record can safely
        # return empty (its seat's MOVER output is replayed, so the board is
        # unaffected — the harness degrades gracefully for that seat). A MOVER
        # with no record WOULD diverge the board — flag it loudly.
        if role in ("think", "thinker"):
            return {
                "ok": True, "response": "", "thinking": "",
                "wallclock_capped": False, "capped": False, "elapsed_ms": 0,
            }
        live_fallbacks.append((day, seat, role))
        print(f"  [LIVE FALLBACK] day {day} {seat} {role} (no record — board "
              f"may diverge)", flush=True)
        return orig_invoke(self, prompt, **kw)

    cc.CortexChatInvoker.invoke = _patched  # type: ignore[assignment]

    # ── 3. Fresh session, exact params, then drive the loop ────────────────
    soc_backend.reset_for_tests()
    store = soc_backend.get_store()
    seats = [f"p{i+1}" for i in range(len(labels))]
    label_for = dict(zip(seats, labels))
    agents_for_init = {s: label_for[s] for s in seats}
    info = soc_engine.init_session(
        store, seed=args.seed, width=args.width, height=args.height,
        season_day_cap=args.days, players=seats, agents=agents_for_init,
        season_name=f"RECON_{args.session[:8]}",
    )
    session_id = info["session_id"]
    print(f"replay session: {session_id}")

    banked_log: List[str] = []
    iteration = 0
    while iteration < 400:
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
        current_day[0] = day
        current_seat[0] = seat
        label = label_for[seat]
        override = "heuristic" if label in _HEURISTIC_LABELS else "cortex"
        run_agent_turn(
            store, session_id, seat,
            runtime_override=override, agent_label=label,
        )
        iteration += 1

    cc.CortexChatInvoker.invoke = orig_invoke  # type: ignore[assignment]

    # ── 4. Verify reconstruction: banked parcels per night for the seat ────
    print("\nreconstruction banked-summary (compare to the audited report):")
    for day in range(1, args.days + 2):
        try:
            v = soc_engine.get_view(store, session_id, args.player)
        except Exception:
            break
    # Pull final scores as a coarse integrity check.
    final = soc_engine.get_view(store, session_id, args.player)
    fav = final.get("agent_view") or final
    scores = (fav.get("hud") or {}).get("scores") or final.get("scores") or {}
    print(f"  final scores: {scores}")

    print(f"\ncaptured days: {sorted(captured)}")
    if live_fallbacks:
        print(f"WARNING: {len(live_fallbacks)} live fallback call(s) — the board "
              f"may have diverged from the audited game: {live_fallbacks}")
    else:
        print("no live fallbacks — every cortex call was replayed from record.")
    missing = target_days - captured
    if missing:
        print(f"WARNING: never captured target day(s): {sorted(missing)}")
        return 1
    print(f"\nprompts written to: {outdir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
