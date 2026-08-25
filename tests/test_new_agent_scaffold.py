"""Minting a fork is the first thing an attendee does (v1.12).

``scripts/new_agent.py`` copies V12, renames its identity, and registers
the binding. If it half-works the failure lands on someone with an hour
to spend, so the contract is pinned here: validation rejects bad names
*before* writing, and the shipped registry keeps the anchors the script
edits.

The copy itself is exercised through ``--dry-run``. Running it for real
would mutate the repo mid-suite, and the interesting failure modes
(refusing bad input, leaving no partial state) are all pre-write.
"""

from __future__ import annotations

import os

os.environ.setdefault("SOC_BACKEND", "memory")

import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server.app import app

_REPO = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO / "scripts" / "new_agent.py"
_REGISTRY = _REPO / "sea_of_colours" / "orchestrator_2" / "binding_registry.py"
_HARNESSES = _REPO / "sea_of_colours" / "orchestrator_2" / "harnesses"

client = TestClient(app)


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_SCRIPT), *args],
        capture_output=True, text=True, cwd=_REPO,
    )


def test_dry_run_reports_without_writing() -> None:
    before = sorted(p.name for p in _HARNESSES.iterdir())
    registry_before = _REGISTRY.read_text(encoding="utf-8")

    r = _run("--team", "unittest", "--name", "probe", "--dry-run")

    assert r.returncode == 0, r.stderr
    assert "would create" in r.stdout
    assert "unittest_probe" in r.stdout
    assert sorted(p.name for p in _HARNESSES.iterdir()) == before
    assert _REGISTRY.read_text(encoding="utf-8") == registry_before


def test_capitalisation_is_normalised_not_rejected() -> None:
    """``--team Redwatch`` is a reasonable thing to type; lowercase it
    rather than making someone read an error to learn the convention."""
    r = _run("--team", "Redwatch", "--name", "Reaper", "--dry-run")
    assert r.returncode == 0, r.stderr
    assert "redwatch_reaper" in r.stdout
    assert "SOC_REDWATCH_REAPER" in r.stdout


@pytest.mark.parametrize(
    "team,name",
    [
        ("red watch", "reaper"),  # spaces are not importable
        ("red-watch", "reaper"),  # hyphens are not importable
        ("9team", "reaper"),      # cannot start a Python module with a digit
        ("redwatch", "reaper!"),  # punctuation
        ("redwatch_", "reaper"),  # would produce a double underscore
    ],
)
def test_unusable_names_are_refused(team: str, name: str) -> None:
    """The label becomes a package directory and a dict key, so anything
    that isn't a plain identifier has to fail loudly and early."""
    r = _run("--team", team, "--name", name, "--dry-run")
    assert r.returncode != 0, f"{team}/{name} should have been refused"
    assert "error:" in r.stderr


def test_existing_name_is_refused_before_any_copy() -> None:
    """tabula_v12 is already registered; the guard must fire on the
    registry check, not after copying 44 files over the original."""
    r = _run("--team", "tabula", "--name", "v12", "--dry-run")
    assert r.returncode != 0
    assert "already" in r.stderr


def test_registry_keeps_the_anchors_the_script_edits() -> None:
    """The script refuses to guess where the dicts end. If someone
    reformats the registry and drops these, minting breaks."""
    text = _REGISTRY.read_text(encoding="utf-8")
    assert "# SOC_NEW_AGENT_ANCHOR" in text
    assert "# SOC_NEW_AGENT_LABEL_ANCHOR" in text


def test_roster_endpoint_serves_the_registry() -> None:
    """The New Game dropdown is built from this, so a fork appears
    without a frontend edit."""
    from sea_of_colours.orchestrator_2.binding_registry import selectable_agents

    r = client.get("/api/meta/agents")
    assert r.status_code == 200
    served = r.json()["agents"]
    assert served == selectable_agents()
    assert {a["value"] for a in served} >= {"human", "tabula_v12"}


def test_frontend_no_longer_hardcodes_the_roster() -> None:
    """A hardcoded list is allowed to survive *as a fallback*, but the
    render path must read the fetched roster or forks stay invisible."""
    src = (_REPO / "server" / "static" / "app.js").read_text(encoding="utf-8")
    assert "/api/meta/agents" in src
    assert "agentRoster()" in src
