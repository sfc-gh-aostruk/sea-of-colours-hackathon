"""R4 — harvester economy gate (orbit phase) unit tests."""

from __future__ import annotations

from sea_of_colours.orchestrator_2.harnesses.tabula_v10 import orbit as orb


def _view(*, credits, cap_used=1, cap_max=3, probe_stock=0, died=0,
          harvester_cost=1500, probe_cost=500):
    ln = {}
    if died:
        ln["my_assets_destroyed"] = [{"kind": "harvester"} for _ in range(died)]
    return {
        "orbit": {
            "credits": credits,
            "harvester_cap_used": cap_used,
            "harvester_cap_max": cap_max,
            "actions_max": 3,
            "probe_stock": probe_stock,
            "ship_prices": {
                "harvester_build": harvester_cost, "probe_build": probe_cost,
            },
        },
        "last_night": ln,
    }


def _has(actions, a):
    return any(x.get("a") == a for x in actions)


def test_no_gate_when_fleet_healthy_late_game():
    av = _view(credits=2000, cap_used=3, cap_max=3)
    base = [{"a": "build_probe", "count": 3}]
    out, notes = orb.apply_economy_gate(av, list(base), day=6)
    assert out == base
    assert notes == []


def test_recovery_build_injected_after_death_when_affordable():
    av = _view(credits=1600, cap_used=1, died=1)
    base = [{"a": "repair", "unit": "harvester_p1_1"},
            {"a": "build_probe", "count": 3}]
    out, notes = orb.apply_economy_gate(av, list(base), day=6)
    assert _has(out, "build_harvester")
    # Harvester seated AFTER the repair.
    assert [a["a"] for a in out].index("build_harvester") == 1
    # Probes trimmed to the floor (stock 0 -> keep 2), freeing a slot/credits.
    pb = [a for a in out if a["a"] == "build_probe"]
    assert pb and pb[0]["count"] == 2


def test_early_single_harvester_conserves_when_unaffordable():
    # Day 3, one harvester, not enough for a build this turn → trim probes and
    # conserve toward next turn (no unaffordable build fabricated).
    av = _view(credits=1100, cap_used=1, probe_stock=0)
    base = [{"a": "build_probe", "count": 4}]
    out, notes = orb.apply_economy_gate(av, list(base), day=3)
    assert not _has(out, "build_harvester")
    pb = [a for a in out if a["a"] == "build_probe"]
    assert pb and pb[0]["count"] == 2      # floor kept, 2 trimmed
    assert any("conserving" in n for n in notes)


def test_no_gate_when_late_and_two_harvesters():
    av = _view(credits=1600, cap_used=2, cap_max=3)
    base = [{"a": "build_probe", "count": 3}]
    out, notes = orb.apply_economy_gate(av, list(base), day=5)
    assert out == base and notes == []


def test_never_exceeds_cap():
    av = _view(credits=3000, cap_used=3, cap_max=3, died=1)
    base = [{"a": "build_probe", "count": 3}]
    out, notes = orb.apply_economy_gate(av, list(base), day=2)
    assert not _has(out, "build_harvester")


def test_respects_existing_build_in_base_plan():
    av = _view(credits=1600, cap_used=1, died=1)
    base = [{"a": "build_harvester"}, {"a": "build_probe", "count": 3}]
    out, notes = orb.apply_economy_gate(av, list(base), day=2)
    # Base already builds — gate is a no-op (probes untouched).
    assert out == base and notes == []


def test_probe_floor_respected_when_stock_already_high():
    # Stock already at floor → all speculative probe builds trimmed.
    av = _view(credits=1100, cap_used=1, probe_stock=2)
    base = [{"a": "build_probe", "count": 2}]
    out, notes = orb.apply_economy_gate(av, list(base), day=3)
    assert not _has(out, "build_probe")
    assert any("conserving" in n for n in notes)
