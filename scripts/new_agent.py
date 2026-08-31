#!/usr/bin/env python3
"""Mint a new agent by forking V12 — the first thing you run at the hackathon.

    python scripts/new_agent.py --team redwatch --name reaper

That copies the shipped V12 harness to
``sea_of_colours/orchestrator_2/harnesses/redwatch_reaper/``, repoints its
imports, and writes an ``agent.json`` declaring it. Restart the server and
``REDWATCH_REAPER`` is in the New Game dropdown, playable against V12.

**Your agent is one directory.** Registration is discovery over
``agent.json`` (v1.39), so nothing outside your fork is touched when it
is created and nothing outside it needs to change again. That is what
lets forty teams push to one repo without conflicting, and what makes
the end-of-day league a directory scan instead of forty merges.

**Why fork instead of editing V12 in place.** V12 is the baseline you are
trying to beat. Edit it directly and you lose the control: "better than
before" becomes unmeasurable, matches against other teams are no longer
like-for-like, and `git diff` stops telling you what you changed. The
copy costs a second and keeps the comparison honest.

Naming is ``<team>_<agent>`` so a room full of forks stays legible and
two teams can't collide on ``reaper``.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_HARNESSES = _REPO / "sea_of_colours" / "orchestrator_2" / "harnesses"
_SOURCE = _HARNESSES / "tabula_v12"
_REGISTRY = _REPO / "sea_of_colours" / "orchestrator_2" / "binding_registry.py"

_SOURCE_NAME = "tabula_v12"

# Same rule as a Python identifier, minus the right to be weird: the name
# becomes a package directory, a dict key, and a Snowflake-ish agent
# constant, so keep it to lowercase ascii.
_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def _die(msg: str) -> "NoReturn":  # type: ignore[valid-type]
    print(f"error: {msg}", file=sys.stderr)
    raise SystemExit(2)


def _validate(part: str, field: str) -> str:
    part = part.strip().lower()
    if not _NAME_RE.match(part):
        _die(
            f"--{field} must be lowercase letters, digits and underscores, "
            f"starting with a letter (got {part!r})"
        )
    if part.endswith("_"):
        _die(f"--{field} must not end with an underscore (got {part!r})")
    return part


def _copy_harness(dest: Path, label: str, *, dry_run: bool) -> int:
    """Copy V12 and repoint its self-imports at the new package."""
    files = [
        p for p in sorted(_SOURCE.rglob("*"))
        if p.is_file()
        and "__pycache__" not in p.parts
        and p.suffix in {".py", ".md"}
    ]
    if dry_run:
        return len(files)

    for src in files:
        rel = src.relative_to(_SOURCE)
        out = dest / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        text = src.read_text(encoding="utf-8")
        # Two substitutions, both needed.
        #
        # Lowercase covers imports: every module self-references by
        # absolute path, so there are no relative imports to fix.
        #
        # Uppercase covers identity, which is easy to overlook and does
        # real damage if you do. `INNER_AGENT_LABEL = "TABULA_V12"` is
        # what lands in the audit trail, so an unrenamed fork files its
        # turns under V12's name — and the whole point is comparing the
        # two. It also namespaces the `TABULA_V12_*` env toggles, so two
        # forks on one machine can be tuned independently.
        text = text.replace(_SOURCE_NAME, label)
        text = text.replace(_SOURCE_NAME.upper(), label.upper())
        out.write_text(text, encoding="utf-8")
    return len(files)


def _check_registrable(label: str) -> None:
    """Fail before anything is written, not halfway through."""
    # Built-ins are the one thing a fork must not shadow: take the
    # ``tabula_v12`` label and you become the baseline everyone is scored
    # against, which is exactly the comparison the fork exists to make.
    text = _REGISTRY.read_text(encoding="utf-8")
    code = "\n".join(line.split("#", 1)[0] for line in text.splitlines())
    if f'"{label}"' in code:
        _die(
            f"{label!r} is a built-in agent name — pick another --team or "
            f"--name so your agent is scored separately from it"
        )
    existing = _HARNESSES / label / "agent.json"
    if existing.exists():
        _die(
            f"{existing.relative_to(_REPO)} already exists — pick another "
            f"--name, or delete that directory first"
        )


def _write_manifest(dest: Path, team: str, name: str, menu_label: str,
                    *, dry_run: bool) -> None:
    """Declare the fork inside its own directory.

    This is the whole of registration (v1.39). Nothing shared is edited,
    which is what makes forty teams pushing to one repo work: two agents
    can never touch the same file, so two agents can never conflict. It
    is also what makes the end-of-day league collation a directory scan
    rather than a merge.
    """
    if dry_run:
        return
    payload = {
        "team": team,
        "name": name,
        "menu_label": menu_label,
        "entry": "harness:run",
        "needs_llm": True,
    }
    (dest / "agent.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="new_agent",
        description="Fork the V12 harness into your own registered agent.",
    )
    ap.add_argument("--team", required=True, help="Your team name, e.g. redwatch")
    ap.add_argument("--name", required=True, help="Your agent name, e.g. reaper")
    ap.add_argument(
        "--menu-label", default=None,
        help="Text shown in the New Game dropdown (default: auto).",
    )
    ap.add_argument(
        "--dry-run", action="store_true",
        help="Report what would be created without writing anything.",
    )
    args = ap.parse_args(argv)

    team = _validate(args.team, "team")
    name = _validate(args.name, "name")
    label = f"{team}_{name}"
    const = f"SOC_{label.upper()}"
    dest = _HARNESSES / label
    menu_label = args.menu_label or (
        f"{label.upper()} — {team}'s agent (needs a Snowflake PAT · slow)"
    )

    if not _SOURCE.is_dir():
        _die(f"source harness missing: {_SOURCE}")
    if dest.exists():
        _die(f"{dest.relative_to(_REPO)} already exists — pick another --name")
    # Every check that can fail runs before the first file is written, so
    # a rejected name never leaves a half-copied package behind.
    _check_registrable(label)

    n = _copy_harness(dest, label, dry_run=args.dry_run)
    try:
        _write_manifest(dest, team, name, menu_label, dry_run=args.dry_run)
    except BaseException:
        if not args.dry_run and dest.exists():
            shutil.rmtree(dest)
        raise

    rel = dest.relative_to(_REPO)
    if args.dry_run:
        print(f"--dry-run: would create {rel}/ ({n} files + agent.json)")
        print(f"--dry-run: would register {label!r} by discovery")
        return 0

    print(f"created  {rel}/  ({n} files, forked from tabula_v12)")
    print(f"declared  {rel}/agent.json  ->  {label}")
    print()
    print("Everything your agent is lives in that one directory. Nothing")
    print("outside it was touched, and nothing outside it needs to be —")
    print("that is what lets the whole room push to one repo.")
    print()
    print("next:")
    print("  1. restart the server (python run_web.py)")
    print(f"  2. NEW GAME -> pick {label.upper()} for a rival seat")
    print(f"  3. read {rel}/README.md — the two gaps V12 ships with are")
    print("     the exercise; that file says exactly where they live")
    print()
    print("  score it against the redsign battles:")
    print(f"    python scripts/soc.py suite --agent {label}")
    print()
    print("  publish it (your folder only):")
    print(f"    python scripts/soc.py push")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
