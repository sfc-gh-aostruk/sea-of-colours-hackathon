"""Tests for the binding registry — the fairness gate.

Pins:
1. The default with nothing set is heuristic.
2. SOC_BINDING_<player> env vars are honoured.
3. KNOWN_AGENT_BINDINGS maps SOC_CORTEX_AGENT correctly for PILOT_V2.
4. Unknown SOC_CORTEX_AGENT names with runtime_override="cortex"
   produce a bare cortex_agent binding.
5. Heuristic override short-circuits everything.
"""

from __future__ import annotations

import os

import pytest

from sea_of_colours.orchestrator_2 import binding_registry as br


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in (
        "SOC_BINDING_P1", "SOC_BINDING_P2",
        "SOC_CORTEX_AGENT", "SOC_AGENT_RUNTIME",
    ):
        monkeypatch.delenv(key, raising=False)
    yield


def test_default_resolves_to_heuristic():
    b = br.resolve_binding(store=None, session_id="s", player="p1")
    assert b is br.HEURISTIC_BINDING
    assert b.kind == "heuristic"


def test_env_per_player_override_parses(monkeypatch):
    monkeypatch.setenv(
        "SOC_BINDING_P1",
        "harness_in_process:my_mod.path:run:MY_LABEL",
    )
    b = br.resolve_binding(store=None, session_id="s", player="p1")
    assert b.kind == "harness_in_process"
    # The locator is everything between the first and last colon (locator + label allowed via 3-part).
    assert b.locator == "my_mod.path"
    assert b.agent_label == "run:MY_LABEL"


def test_known_agent_maps_pilot_v2(monkeypatch):
    monkeypatch.setenv("SOC_CORTEX_AGENT", "SOC_RED_REAPER_PILOT_V2")
    b = br.resolve_binding(store=None, session_id="s", player="p1")
    assert b.kind == "harness_in_process"
    assert b.locator.endswith("pilot_v2.harness:run")
    assert b.agent_label == "PILOT_V2"


def test_unknown_cortex_agent_with_override_becomes_bare(monkeypatch):
    monkeypatch.setenv("SOC_CORTEX_AGENT", "SOC_HYPOTHETICAL_FUTURE_AGENT")
    b = br.resolve_binding(
        store=None, session_id="s", player="p1",
        runtime_override="cortex",
    )
    assert b.kind == "cortex_agent"
    assert b.locator == "SOC_HYPOTHETICAL_FUTURE_AGENT"


def test_heuristic_override_short_circuits(monkeypatch):
    """Even with a known agent registered, runtime_override='heuristic' wins."""
    monkeypatch.setenv("SOC_CORTEX_AGENT", "SOC_RED_REAPER_PILOT_V2")
    b = br.resolve_binding(
        store=None, session_id="s", player="p1",
        runtime_override="heuristic",
    )
    assert b is br.HEURISTIC_BINDING


def test_legacy_agents_not_claimed_by_orchestrator_2(monkeypatch):
    """PILOT v1 / GRID_FAST / etc. should NOT be claimed — they live in v1."""
    for agent_name in (
        "SOC_RED_REAPER", "SOC_RED_REAPER_PILOT",
        "SOC_RED_REAPER_GRID_FAST", "SOC_RED_REAPER_LIST_V2",
    ):
        monkeypatch.setenv("SOC_CORTEX_AGENT", agent_name)
        b = br.resolve_binding(store=None, session_id="s", player="p1")
        # Falls through to heuristic — orchestrator_2 doesn't own these.
        assert b.kind == "heuristic", f"{agent_name} unexpectedly claimed by orchestrator_2"
