#!/usr/bin/env python3
"""Mint a new agent by forking V12 — the first thing you run at the hackathon.

    python scripts/new_agent.py --team redwatch --name reaper

That copies the shipped V12 harness to
``sea_of_colours/orchestrator_2/harnesses/redwatch_reaper/``, repoints its
imports, and registers it in ``binding_registry``. Restart the server and
``REDWATCH_REAPER`` is in the New Game dropdown, playable against V12.

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
import re
import shutil
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_HARNESSES = _REPO / "sea_of_colours" / "orchestrator_2" / "harnesses"
_SOURCE = _HARNESSES / "tabula_v12"
_REGISTRY = _REPO / "sea_of_colours" / "orchestrator_2" / "binding_registry.py"

_SOURCE_NAME = "tabula_v12"
_KNOWN_ANCHOR = "    # SOC_NEW_AGENT_ANCHOR"
_LABEL_ANCHOR = "    # SOC_NEW_AGENT_LABEL_ANCHOR"

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
    text = _REGISTRY.read_text(encoding="utf-8")
    # Ignore comments: the anchors carry a worked example, and matching
    # that would refuse the very name the docs tell people to try.
    code = "\n".join(
        line.split("#", 1)[0] for line in text.splitlines()
    )
    if f'"{label}"' in code:
        _die(
            f"{label!r} is already registered in binding_registry.py — "
            f"pick another --name, or remove the old entry first"
        )
    for anchor in (_KNOWN_ANCHOR, _LABEL_ANCHOR):
        if anchor not in text:
            _die(
                f"anchor {anchor.strip()} missing from binding_registry.py — "
                f"register by hand (see orchestrator_2/README.md)"
            )


def _register(label: str, const: str, menu_label: str, *, dry_run: bool) -> None:
    text = _REGISTRY.read_text(encoding="utf-8")

    known_entry = (
        f'    "{const}": AgentBinding(\n'
        f'        kind="harness_in_process",\n'
        f'        locator="sea_of_colours.orchestrator_2.harnesses.'
        f'{label}.harness:run",\n'
        f'        agent_label="{label.upper()}",\n'
        f'        menu_label="{menu_label}",\n'
        f"        needs_llm=True,\n"
        f"    ),\n"
    )
    label_entry = f'    "{label}": KNOWN_AGENT_BINDINGS["{const}"],\n'

    text = text.replace(_KNOWN_ANCHOR, known_entry + _KNOWN_ANCHOR, 1)
    text = text.replace(_LABEL_ANCHOR, label_entry + _LABEL_ANCHOR, 1)

    if not dry_run:
        _REGISTRY.write_text(text, encoding="utf-8")


def main() -> int:
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
    args = ap.parse_args()

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
        _register(label, const, menu_label, dry_run=args.dry_run)
    except BaseException:
        if not args.dry_run and dest.exists():
            shutil.rmtree(dest)
        raise

    rel = dest.relative_to(_REPO)
    if args.dry_run:
        print(f"--dry-run: would create {rel}/ ({n} files)")
        print(f"--dry-run: would register {label!r} as {const}")
        return 0

    print(f"created  {rel}/  ({n} files, forked from tabula_v12)")
    print(f"registered  {label}  ->  {const}")
    print()
    print("next:")
    print("  1. restart the server (python run_web.py)")
    print(f"  2. NEW GAME -> pick {label.upper()} for a rival seat")
    print(f"  3. read {rel}/README.md — the two gaps V12 ships with are")
    print("     the exercise; that file says exactly where they live")
    print()
    print("  benchmark it once it plays:")
    print(f"    python -m sea_of_colours.orchestrator_2.evals.cli \\")
    print(f"        --config {label} --runtime cortex --backend memory")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
