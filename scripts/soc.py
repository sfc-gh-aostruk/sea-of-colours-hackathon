#!/usr/bin/env python3
"""``soc`` — the one command for the hackathon.

    python scripts/soc.py new --team redwatch --name reaper
    python scripts/soc.py suite --agent redwatch_reaper
    python scripts/soc.py why redwatch_reaper two_pures_poker
    python scripts/soc.py push
    python scripts/soc.py league

There is deliberately one entry point. The kit has a fair amount behind
it — a scenario suite, a fork minter, a submission path, a league — and
discovering four separate scripts is four chances to not find the third
one. ``soc`` with no arguments lists everything it can do.

**Written to be driven by an agent.** Most attendees will be improving
their agent through a coding assistant rather than by hand, so the
assistant is a first-class user of this CLI. That means: every error
names the fix, every subcommand explains what it is for in ``--help``,
and output is plain text an LLM can read back without parsing tricks.
``--json`` is there for when it wants structure instead.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

# Every scenario runs in memory. Set before the engine is imported so
# backend auto-detection cannot wander off to a live account and start
# writing rows because somebody happened to have a config file.
os.environ.setdefault("SOC_BACKEND", "memory")


def _die(msg: str, *, fix: str = "") -> None:
    print(f"error: {msg}", file=sys.stderr)
    if fix:
        print(f"  fix: {fix}", file=sys.stderr)
    raise SystemExit(2)


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=_REPO, capture_output=True, text=True, check=False
    ).stdout.strip()


def _changed_paths() -> list[str]:
    """Every path git considers modified or untracked.

    Uses ``-z`` and does not strip: porcelain's status field is two
    columns wide and the first is often a space, so any leading-
    whitespace trim silently eats the first character of the first
    filename — which reads as a mysteriously missing file rather than
    as a parsing bug.
    """
    raw = subprocess.run(
        ["git", "status", "--porcelain", "-z", "--untracked-files=all"],
        cwd=_REPO, capture_output=True, text=True, check=False,
    ).stdout
    out: list[str] = []
    for entry in raw.split("\0"):
        if len(entry) > 3:
            out.append(entry[3:])
    return out


# ── new ─────────────────────────────────────────────────────────────


def cmd_new(args) -> int:
    """Mint your agent. Step one, and it touches nothing but your folder."""
    from scripts import new_agent

    argv = ["--team", args.team, "--name", args.name]
    if args.menu_label:
        argv += ["--menu-label", args.menu_label]
    return new_agent.main(argv)


# ── suite ───────────────────────────────────────────────────────────


def cmd_suite(args) -> int:
    """Score an agent against the redsign battles."""
    from sea_of_colours.evals.battles import boards, ladder, report, runner

    picked = _pick_boards(boards, args.board)
    rungs = (
        [ladder.get_rung(r) for r in args.rung.split(",")]
        if args.rung and args.rung != "all"
        else list(ladder.up_to(args.up_to))
    )
    loadouts = (
        [ladder.get_loadout(l) for l in args.loadout.split(",")]
        if args.loadout != "all"
        else list(ladder.LOADOUTS)
    )

    total = len(picked) * len(rungs) * len(loadouts) * args.runs
    print(
        f"running {len(picked)} board(s) x {len(rungs)} rung(s) x "
        f"{len(loadouts)} loadout(s) x {args.runs} run(s) = {total} turns "
        f"as {args.agent}",
        file=sys.stderr,
    )

    card_dir = Path(args.cards) if args.cards else None

    def tick(res):
        mark = "ok  " if res.rate == 1.0 else ("~   " if res.flaky else "FAIL")
        print(f"  {mark} {res.battle_id:<46} {res.score:>4.0%}", file=sys.stderr)

    result = runner.run_suite(
        picked, rungs, loadouts,
        agent=args.agent, runs=args.runs, card_dir=card_dir,
        on_battle=None if args.json else tick,
    )

    if args.json:
        print(json.dumps(_as_json(result), indent=2))
    else:
        print()
        print(report.render(result, verbose=args.verbose))
        if card_dir:
            print(f"  cards written to {card_dir}/")
    return 0 if result.clean == len(result.battles) else 1


def _pick_boards(boards, spec: str):
    if not spec or spec == "all":
        return list(boards.BOARDS)
    out = []
    for name in spec.split(","):
        try:
            out.append(boards.get(name.strip()))
        except KeyError as exc:
            _die(str(exc))
    return out


def _as_json(result) -> dict:
    return {
        "agent": result.agent,
        "score": round(result.score, 4),
        "clean": result.clean,
        "battles": [
            {
                "id": b.battle_id,
                "board": b.board.id,
                "rung": b.rung.id,
                "loadout": b.loadout.id,
                "rate": round(b.rate, 3),
                "score": round(b.score, 3),
                "failures": [
                    {"check": n, "count": c} for n, c in b.recurring_failures()
                ],
            }
            for b in result.battles
        ],
        "by_rung": {k: {"clean": v[0], "total": v[1]}
                    for k, v in result.by_rung().items()},
        "weapons_fired": result.weapons_fired(),
    }


# ── why ─────────────────────────────────────────────────────────────


def cmd_why(args) -> int:
    """Explain one board: the question, the canonical, and what happened.

    The command to reach for when the suite says a board failed and the
    next question is "what was it supposed to do".
    """
    from sea_of_colours.evals.battles import boards, ladder, report, runner

    board = _pick_boards(boards, args.board)[0]

    print()
    print("═" * 74)
    print(f"  {board.id}   ·   day {board.day}   ·   {board.shape}")
    print("═" * 74)
    print()
    print(_para("THE QUESTION", board.question))
    print(_para("THE CANONICAL PLAY", board.canonical))
    if board.baseline:
        print(_para("WHAT STOCK V12 DID", board.baseline))
    note = board.expect.get("note")
    if note:
        print(_para("HOW IT IS SCORED", str(note)))
    print("  Predicates: " + ", ".join(
        k for k in board.expect if k != "note") + "\n")

    if not args.agent:
        return 0

    res = runner.run_battle(
        board, ladder.get_rung(args.rung), ladder.get_loadout(args.loadout),
        agent=args.agent, runs=args.runs,
    )
    print("─" * 74)
    print(f"  {args.agent.upper()} AT {args.rung.upper()}")
    print("─" * 74)
    print()
    for run in res.runs:
        print(f"  run {run.run_index}: "
              f"{'passed' if run.passed else 'failed'} "
              f"({run.score:.0%} of checks, {run.seconds}s)")
        for move in run.moves:
            print(f"      {json.dumps(move)}")
        for check in run.checks:
            print(f"      {check}")
        if run.rationale:
            print(report._wrap("      " + run.rationale[:600], 66, 6))
        print()
    return 0


def _para(title: str, body: str) -> str:
    import textwrap

    wrapped = textwrap.fill(" ".join(body.split()), width=68,
                            initial_indent="  ", subsequent_indent="  ")
    return f"  {title}\n{wrapped}\n"


# ── list ────────────────────────────────────────────────────────────


def cmd_list(args) -> int:
    """Everything the kit knows about: boards, rungs, loadouts, agents."""
    from sea_of_colours.evals.battles import boards, ladder
    from sea_of_colours.orchestrator_2 import binding_registry as br

    print("\n  BOARDS")
    for b in boards.BOARDS:
        print(f"    {b.id:<24} day {b.day}  {b.shape}")
    print("\n  RUNGS (easiest first)")
    for r in ladder.up_to(ladder.ORDER[-1]):
        print(f"    {r.id:<24} {r.summary}")
    print("\n  LOADOUTS")
    for l in ladder.LOADOUTS:
        print(f"    {l.id:<24} {l.note}")
    print("\n  AGENTS")
    for a in br.selectable_agents():
        print(f"    {a['value']:<24} {a['label']}")
    print()
    return 0


# ── doctor ──────────────────────────────────────────────────────────


def cmd_doctor(args) -> int:
    """Check the kit is sound before blaming your agent."""
    from sea_of_colours.orchestrator_2 import agent_manifest
    from sea_of_colours.orchestrator_2 import binding_registry as br

    problems: list[str] = list(br.DISCOVERY_PROBLEMS)
    found, more = agent_manifest.discover()
    problems += [p for p in more if p not in problems]

    print(f"  python           {sys.version.split()[0]}")
    print(f"  backend          {os.environ.get('SOC_BACKEND')}")
    print(f"  agents found     {len(found)} discovered, "
          f"{len(br.AGENT_LABEL_BINDINGS)} routable")
    for man in found:
        print(f"                   {man.label}  ({man.directory.name}/)")

    pat = bool(os.environ.get("SOC_SNOWFLAKE_PAT") or
               os.environ.get("SNOWFLAKE_PAT"))
    print(f"  LLM credentials  {'present' if pat else 'absent'}"
          f"{'' if pat else '  (heuristic agents still run)'}")

    if problems:
        print("\n  PROBLEMS")
        for p in problems:
            print(f"    - {p}")
        return 1
    print("\n  No problems found.")
    return 0


# ── push ────────────────────────────────────────────────────────────


def cmd_push(args) -> int:
    """Publish your agent — your folder, and nothing else.

    The guarantee this enforces is what makes a shared repo survive a
    room of forty: if everyone's diff is confined to their own
    directory, nobody's push can break anybody else's agent, and the
    end-of-day collation is a merge that cannot conflict.

    It is a check rather than an instruction because instructions do not
    survive a deadline.
    """
    from sea_of_colours.orchestrator_2 import agent_manifest

    found, problems = agent_manifest.discover()
    if problems:
        for p in problems:
            print(f"  warning: {p}", file=sys.stderr)

    mine = _resolve_agent(found, args.agent)
    rel = mine.directory.relative_to(_REPO).as_posix()

    changed = _changed_paths()
    stray = [f for f in changed if not f.startswith(rel)]
    if stray and not args.force:
        print(f"error: changes outside {rel}/:", file=sys.stderr)
        for f in stray[:20]:
            print(f"  {f}", file=sys.stderr)
        print(
            "\n  Your agent must be self-contained so the whole room can "
            "share one\n  repo. Move what you need into your own directory, "
            "revert the rest\n  (git checkout -- <path>), and push again.\n"
            "\n  If a change outside really is necessary, it is a change to "
            "the kit\n  rather than to your agent — raise it, do not "
            "--force it in.",
            file=sys.stderr,
        )
        return 2

    if not changed:
        print("  nothing to push — no changes in "
              f"{rel}/ since the last commit")
        return 0

    message = args.message or f"{mine.label}: update agent"
    if args.dry_run:
        print(f"  --dry-run: would commit {len(changed)} file(s) under {rel}/")
        print(f"  --dry-run: would push to {args.remote} {_branch()}")
        return 0

    subprocess.run(["git", "add", "--", rel], cwd=_REPO, check=True)
    subprocess.run(["git", "commit", "-m", message], cwd=_REPO, check=True)
    subprocess.run(["git", "push", args.remote, _branch()], cwd=_REPO, check=True)
    print(f"\n  pushed {mine.label}. It is now in the league.")
    return 0


def _branch() -> str:
    return _git("rev-parse", "--abbrev-ref", "HEAD") or "main"


def _resolve_agent(found, requested: str | None):
    if requested:
        for man in found:
            if man.label == requested:
                return man
        _die(
            f"no agent named {requested!r}",
            fix="run `python scripts/soc.py list` to see what exists, or "
                "`soc new --team <team> --name <name>` to mint one",
        )
    forks = [m for m in found if m.label != "tabula_v12"]
    if len(forks) == 1:
        return forks[0]
    if not forks:
        _die(
            "no agent of your own was found",
            fix="python scripts/soc.py new --team <team> --name <name>",
        )
    _die(
        f"{len(forks)} agents found, so I cannot tell which is yours",
        fix="pass --agent <label>, one of: "
            + ", ".join(sorted(m.label for m in forks)),
    )


# ── league ──────────────────────────────────────────────────────────


def cmd_league(args) -> int:
    """Score every submitted agent on the same boards and rank them.

    The entrant list is the set of directories with a manifest, which is
    why registration had to stop being a shared file: nobody can be left
    out of the league by a merge going wrong.
    """
    from sea_of_colours.evals.battles import boards, ladder, report, runner
    from sea_of_colours.orchestrator_2 import agent_manifest

    found, problems = agent_manifest.discover()
    for p in problems:
        print(f"  warning: {p}", file=sys.stderr)

    entrants = [m.label for m in found]
    if args.include_baseline:
        entrants.append("red_harvest")
    if not entrants:
        _die("no agents to run", fix="mint one with `soc new`")

    picked = _pick_boards(boards, args.board)
    rungs = list(ladder.up_to(args.up_to))
    loadouts = [ladder.get_loadout(l) for l in args.loadout.split(",")]

    results = []
    for label in entrants:
        print(f"  running {label}...", file=sys.stderr)
        results.append(
            runner.run_suite(
                picked, rungs, loadouts,
                agent=label, runs=args.runs,
                card_dir=Path(args.cards) / label if args.cards else None,
            )
        )
    print()
    print(report.league_table(results))
    if args.json:
        Path(args.json).write_text(
            json.dumps([_as_json(r) for r in results], indent=2),
            encoding="utf-8",
        )
        print(f"  wrote {args.json}")
    return 0


# ── wiring ──────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="soc",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="cmd")

    n = sub.add_parser("new", help="mint your agent (start here)")
    n.add_argument("--team", required=True)
    n.add_argument("--name", required=True)
    n.add_argument("--menu-label", default=None)
    n.set_defaults(fn=cmd_new)

    s = sub.add_parser("suite", help="score an agent against the redsign battles")
    s.add_argument("--agent", default="red_harvest")
    s.add_argument("--board", default="all", help="comma-separated, or 'all'")
    s.add_argument("--rung", default=None,
                   help="comma-separated rungs; overrides --up-to")
    s.add_argument("--up-to", default="armed",
                   help="run every rung up to this one (default: armed)")
    s.add_argument("--loadout", default="empty",
                   help="comma-separated, or 'all'")
    s.add_argument("--runs", type=int, default=1,
                   help="attempts per battle; >1 exposes flakiness")
    s.add_argument("--cards", default=None,
                   help="directory to write per-run cards into")
    s.add_argument("--json", action="store_true")
    s.add_argument("-v", "--verbose", action="store_true")
    s.set_defaults(fn=cmd_suite)

    w = sub.add_parser("why", help="explain a board, and optionally play it")
    w.add_argument("board")
    w.add_argument("agent", nargs="?", default=None)
    w.add_argument("--rung", default="quiet")
    w.add_argument("--loadout", default="empty")
    w.add_argument("--runs", type=int, default=1)
    w.set_defaults(fn=cmd_why)

    sub.add_parser("list", help="boards, rungs, loadouts, agents").set_defaults(
        fn=cmd_list
    )
    sub.add_parser("doctor", help="check the kit before blaming your agent"
                   ).set_defaults(fn=cmd_doctor)

    pu = sub.add_parser("push", help="publish your agent (your folder only)")
    pu.add_argument("--agent", default=None)
    pu.add_argument("-m", "--message", default=None)
    pu.add_argument("--remote", default="origin")
    pu.add_argument("--dry-run", action="store_true")
    pu.add_argument("--force", action="store_true",
                    help=argparse.SUPPRESS)
    pu.set_defaults(fn=cmd_push)

    lg = sub.add_parser("league", help="run every submitted agent and rank them")
    lg.add_argument("--board", default="all")
    lg.add_argument("--up-to", default="armed")
    lg.add_argument("--loadout", default="empty")
    lg.add_argument("--runs", type=int, default=1)
    lg.add_argument("--cards", default=None)
    lg.add_argument("--json", default=None)
    lg.add_argument("--include-baseline", action="store_true", default=True)
    lg.set_defaults(fn=cmd_league)

    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "fn", None):
        parser.print_help()
        return 0
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
