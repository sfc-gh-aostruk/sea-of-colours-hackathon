"""Read-only ADVISOR for tabula_v11 — "what would v11 do here, and why?".

You play a seat yourself (in the live web UI, as a ``human`` seat) and, at any
NIGHT-planning state, point this at the same session to see the v11 harness's
reasoning for that exact board — WITHOUT it touching the game. It runs the full
THINK -> PLAN pipeline via ``harness.run(..., submit=False)`` so nothing is
submitted and no turn memory/snapshot is written; the seat stays yours.

Workflow
--------
1. Start the game server and create a game with your seat as ``human``.
2. Play a turn up to the NIGHT-planning decision (before you submit moves).
3. In another terminal, run this against the session + your seat and read the
   card it prints. Paste the card into the chat and we diagnose together.

Usage
-----
    # find your session id
    SOC_BACKEND=snowflake python scripts/advise_v11.py --list

    # get v11's reasoning for the current night state of seat p1
    SOC_BACKEND=snowflake python scripts/advise_v11.py --session <SID> --seat p1

    # also print the option menu, resolved geometry + packed moves
    python scripts/advise_v11.py --session <SID> --seat p1 --full

    # write the card to a file (handy for pasting) and/or dump raw JSON
    python scripts/advise_v11.py --session <SID> --seat p1 --out card.txt --json

Notes
-----
* The thinker is a live Cortex (LLM) call, so this needs Snowflake/Cortex
  access — the same dependency as playing a cortex seat.
* Covers NIGHT planning (where the THINK/PLAN reasoning lives). ORBIT turns are
  skipped (they'd submit); advance to night to inspect the thinker.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_AGENT = "SOC_RED_REAPER_TABULA_V11"
_RULE = "=" * 72
_SUBRULE = "-" * 72


def _wrap(text: str, indent: str = "  ") -> str:
    out: List[str] = []
    for para in str(text or "").splitlines() or [""]:
        if not para.strip():
            out.append("")
            continue
        out.extend(
            textwrap.wrap(
                para, width=96, initial_indent=indent, subsequent_indent=indent,
            )
            or [indent]
        )
    return "\n".join(out)


def _list_sessions(store: Any) -> int:
    from sea_of_colours.snowpark import engine as soc_engine

    payload = soc_engine.list_sessions(store)
    rows = payload.get("sessions") or []
    if not rows:
        print("no sessions found", flush=True)
        return 0
    print(f"{'SESSION_ID':<40} {'DAY':>3} {'PHASE':<10} SEASON", flush=True)
    print(_SUBRULE, flush=True)
    for r in rows:
        print(
            f"{str(r.get('session_id','')):<40} "
            f"{str(r.get('day','?')):>3} "
            f"{str(r.get('phase','?')):<10} "
            f"{r.get('season_name') or ''}",
            flush=True,
        )
    return 0


def _pick_seat(status: Dict[str, Any], seat_arg: Optional[str]) -> Optional[str]:
    players = list(status.get("players") or [])
    agents = dict(status.get("agents") or {})
    if seat_arg:
        return seat_arg if seat_arg in players else None
    # Prefer the (first) human seat — that's the one you're playing.
    for p in players:
        if str(agents.get(p, "")).lower() == "human":
            return p
    return players[0] if players else None


def _board_summary(agent_view: Dict[str, Any]) -> str:
    """Compact read of what the harness actually saw (for correlation)."""
    red = agent_view.get("red_tiles") or []
    live = sum(1 for t in red if str(t.get("freshness") or "") == "fresh")
    echo = len(red) - live
    # Live redsign broadcasts live under the ``redsign`` (singular) key — the
    # ``redsigns``/``red_signs`` names never populate, so the header always read 0
    # even with a redsign live. Count the actual broadcast regions.
    signs = (
        agent_view.get("redsign")
        or agent_view.get("redsigns")
        or agent_view.get("red_signs")
        or []
    )
    # Enemy probes are surfaced via competitor_intel (public launches +
    # persistent echoes), NOT a top-level ``enemy_probes`` key — count them the
    # same way the ENEMY PROBES / SUPERSEDES blocks do so the header matches the
    # prompt (was always 0 before, even when supersede targets existed).
    _ci = agent_view.get("competitor_intel") or {}
    _probe_cells = {
        (int(r["at"][0]), int(r["at"][1]))
        for src in ("new_this_day", "persistent_echoes")
        for r in (_ci.get(src) or [])
        if isinstance(r, dict)
        and str(r.get("kind") or "").startswith("enemy_probe")
        and isinstance(r.get("at"), (list, tuple))
        and len(r["at"]) >= 2
    }
    enemy_probes = list(_probe_cells)
    probe_stock = (
        agent_view.get("probe_stock")
        or (agent_view.get("orbit") or {}).get("probe_stock")
        or 0
    )
    return (
        f"red_tiles={len(red)} (live={live} echo={echo})  "
        f"redsigns={len(signs)}  enemy_probes={len(enemy_probes)}  "
        f"probe_stock={probe_stock}"
    )


def _sub(extras: Dict[str, Any], kind: str) -> Dict[str, Any]:
    for s in extras.get("sub_invocations") or []:
        if str(s.get("kind") or "") == kind:
            return s
    return {}


def _render_card(
    *, session_id: str, seat: str, status: Dict[str, Any],
    agent_view: Dict[str, Any], res: Dict[str, Any], full: bool,
    show_prompt: bool = False,
) -> str:
    extras = res.get("extras") or {}
    day = int(agent_view.get("meta", {}).get("day")
              or agent_view.get("hud", {}).get("day") or 0)
    cap = int(agent_view.get("hud", {}).get("season_day_cap") or 7)
    score = int((agent_view.get("hud", {}).get("scores") or {}).get(seat, 0))
    pending = bool((status.get("pending") or {}).get(seat, False))
    directive = extras.get("thinker_directive") or {}

    lines: List[str] = []
    lines.append(_RULE)
    lines.append(f"  v11 ADVISOR — {seat}  |  day {day}/{cap}  |  score {score}")
    lines.append(f"  session {session_id}")
    lines.append(
        f"  seat status: {'ALREADY SUBMITTED (showing what v11 would have done)' if pending else 'YOUR MOVE (not yet submitted)'}"
    )
    lines.append(f"  board v11 saw: {_board_summary(agent_view)}")
    lines.append(
        f"  thinker: api={extras.get('thinker_api') or '-'} "
        f"ms={extras.get('thinker_ms') or 0} "
        f"retried={extras.get('thinker_retried')}"
    )
    lines.append(_RULE)

    if show_prompt:
        # EXACTLY what the model receives, verbatim (includes the worldview,
        # doctrine, memory replay, and the options menu — the whole input).
        think_prompt = extras.get("thinker_prompt") or ""
        lines.append("")
        lines.append(_RULE)
        lines.append("  EXACTLY WHAT THE AGENT RECEIVES — THINK PROMPT (verbatim)")
        lines.append(_RULE)
        for pl in str(think_prompt).splitlines():
            lines.append(pl)
        plan_prompt = extras.get("plan_prompt") or ""
        if plan_prompt:
            lines.append("")
            lines.append(_SUBRULE)
            lines.append("  PLAN PROMPT (verbatim — sent after THINK, adds the think analysis)")
            lines.append(_SUBRULE)
            for pl in str(plan_prompt).splitlines():
                lines.append(pl)
    else:
        menu_block = extras.get("option_menu_block") or ""
        if menu_block:
            lines.append("")
            lines.append("OPTIONS OFFERED (heuristic-surfaced menu the thinker chose from):")
            for ml in str(menu_block).splitlines():
                lines.append(f"  {ml}" if ml.strip() else "")

    lines.append("")
    lines.append(_RULE)
    lines.append("  THE AGENT THINKING")
    lines.append(_RULE)
    lines.append("STAGE 1 — THINK (bounded reasoning):")
    think = extras.get("thinker_reasoning") or ""
    if not think:
        think = "(no THINK prose — thinker off, empty, or fell through to the mover)"
    lines.append(_wrap(think))

    lines.append("")
    lines.append("STAGE 2 — PLAN (the decision it committed to):")
    if directive:
        lines.append(f"  posture   : {directive.get('posture')}")
        if directive.get("plan"):
            lines.append(f"  plan IDs  : {', '.join(str(p) for p in directive['plan'])}")
        if directive.get("targets"):
            lines.append(f"  targets   : {directive['targets']}")
        if directive.get("avoid"):
            lines.append(f"  avoid     : {directive['avoid']}")
        lines.append(f"  chaff_react: {directive.get('chaff_react')}")
        if directive.get("situational"):
            lines.append(f"  situational: {directive['situational']}")
        if directive.get("note"):
            lines.append("  note:")
            lines.append(_wrap(directive["note"], indent="    "))
    else:
        lines.append("  (no structured directive — see raw PLAN below)")
    plan_raw = _sub(extras, "plan").get("response_text") or ""
    if plan_raw:
        lines.append("  raw PLAN JSON:")
        lines.append(_wrap(plan_raw, indent="    "))

    # Courtesy footer: what that reasoning actually compiled to, so we can
    # correlate the words with the moves when diagnosing.
    moves = res.get("moves") or []
    lines.append("")
    lines.append(_SUBRULE)
    lines.append(f"  -> compiled to {len(moves)} move(s)  "
                 f"[exec={'packager' if extras.get('packager_used') else 'mover'}"
                 f"{'; fallback' if extras.get('fallback_used') else ''}]")
    if extras.get("selected_option_ids"):
        lines.append(f"  -> selected options: {', '.join(str(o) for o in extras['selected_option_ids'])}")
    if extras.get("sanitizer_changes"):
        lines.append("  -> corrector/sanitizer:")
        for s in extras["sanitizer_changes"][:8]:
            lines.append(f"       · {s}")

    if full:
        lines.append("")
        lines.append(_SUBRULE)
        lines.append("  FULL detail")
        if extras.get("packager_log"):
            lines.append("  packager log:")
            for s in extras["packager_log"][:20]:
                lines.append(f"       · {s}")
        lines.append("  moves:")
        for m in moves:
            lines.append(f"       {json.dumps(m)}")

    lines.append(_RULE)
    return "\n".join(lines)


def _advise(args: argparse.Namespace) -> int:
    from sea_of_colours.snowpark import backend as soc_backend
    from sea_of_colours.snowpark import engine as soc_engine
    from sea_of_colours.orchestrator_2.harnesses.tabula_v11 import harness as v11

    store = soc_backend.get_store()  # attach; NEVER reset (that wipes state)

    if args.list:
        return _list_sessions(store)

    if not args.session:
        print("error: --session <id> is required (or use --list)", flush=True)
        return 2

    status = soc_engine.get_session_status(store, args.session)
    if not status.get("players"):
        print(f"error: session {args.session} not found", flush=True)
        return 2

    seat = _pick_seat(status, args.seat)
    if not seat:
        print(f"error: could not resolve seat (players={status.get('players')})",
              flush=True)
        return 2

    phase = str(status.get("phase") or "").lower()
    if phase == "orbit":
        print(
            f"seat {seat} is in ORBIT phase — the advisor covers NIGHT planning "
            "reasoning. Advance to night and re-run to inspect the thinker.",
            flush=True,
        )
        return 0
    if status.get("is_season_complete"):
        print("season is complete — nothing to advise.", flush=True)
        return 0

    view = soc_engine.get_view(store, args.session, seat)
    agent_view = view.get("agent_view") or {}

    print(f"running v11 read-only advisor for {seat} @ {args.session} ...",
          flush=True)
    res = v11.run(
        store=store, session_id=args.session, player=seat, view=view,
        submit=False,
    )
    if res.get("submitted_policy"):
        # Defensive: should never happen with submit=False.
        print("WARNING: advisor reported submitted_policy=True — aborting print "
              "so we don't mislead you.", flush=True)
        return 1

    card = _render_card(
        session_id=args.session, seat=seat, status=status,
        agent_view=agent_view, res=res, full=args.full,
        show_prompt=args.prompt,
    )
    print("\n" + card, flush=True)

    if args.out:
        Path(args.out).write_text(card + "\n", encoding="utf-8")
        print(f"\n(card written to {args.out})", flush=True)
    if args.json:
        blob = {"session_id": args.session, "seat": seat, "moves": res.get("moves"),
                "extras": res.get("extras")}
        out_json = (args.out + ".json") if args.out else "advise_v11.json"
        Path(out_json).write_text(json.dumps(blob, indent=2, default=str),
                                  encoding="utf-8")
        print(f"(raw trace written to {out_json})", flush=True)
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="advise_v11", description=__doc__)
    p.add_argument("--session", help="session id to advise (see --list)")
    p.add_argument("--seat", help="seat to advise (default: your human seat, else p1)")
    p.add_argument("--list", action="store_true", help="list sessions and exit")
    p.add_argument("--full", action="store_true",
                   help="also print the packager log + packed moves")
    p.add_argument("--prompt", action="store_true",
                   help="print the EXACT prompt(s) the model receives, verbatim")
    p.add_argument("--out", help="write the card to this file too")
    p.add_argument("--json", action="store_true",
                   help="also dump the raw trace to <out>.json / advise_v11.json")
    args = p.parse_args(argv)

    os.environ.setdefault("SOC_BACKEND", "snowflake")
    os.environ.setdefault("SOC_CORTEX_AGENT", _AGENT)
    return _advise(args)


if __name__ == "__main__":
    sys.exit(main())
