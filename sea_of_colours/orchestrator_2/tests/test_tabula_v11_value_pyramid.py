"""v11 Phase 1 — VALUE PYRAMID + force-surfaced grabs.

Locks the top-of-pyramid guarantee the seed-69 diagnostics demanded: a pure the
seat can SEE (LIVE) or REACH (ECHO, walk-in) always becomes a top-priority GRAB,
regardless of redsign — killing the "saw the pure, banked zero" dead turns.
"""

from __future__ import annotations

from sea_of_colours.orchestrator_2.harnesses.tabula_v11 import (
    agency,
    packager,
    value_pyramid as vp,
)


def _view(*, live_cells, red_tiles, blue_tiles=None, width=40, height=28):
    """Minimal agent_view: world.live drives coverage; red_tiles carry freshness."""
    return {
        "world": {
            "width": width, "height": height,
            "live": [{"x": x, "y": y, "tile": "EMPTY"} for (x, y) in live_cells],
        },
        "red_tiles": list(red_tiles),
        "blue_tiles": list(blue_tiles or []),
        "my_assets": [
            {"id": "harvester_p1_1", "kind": "harvester", "state": "orbit"},
            {"id": "harvester_p1_2", "kind": "harvester", "state": "orbit"},
        ],
        "orbit": {"probe_stock": 3},
    }


def _red(x, y, purity, fresh=True):
    return {"x": x, "y": y, "purity": purity, "freshness": "fresh" if fresh else "stale"}


# ── provenance ────────────────────────────────────────────────────────────
def test_provenance_splits_fresh_live_from_stale_echo():
    av = _view(
        live_cells=[(10, 10)],
        red_tiles=[_red(10, 10, 255, fresh=True), _red(20, 12, 255, fresh=False)],
    )
    cands = {c.cell: c for c in vp.build_candidates(av)}
    assert cands[(10, 10)].provenance == vp.LIVE
    assert cands[(10, 10)].tier == "pure"
    assert cands[(10, 10)].drop_legal is True
    assert cands[(20, 12)].provenance == vp.ECHO
    assert cands[(20, 12)].drop_legal is False


# ── SMASH: live drop-legal pure ────────────────────────────────────────────
def test_live_droplegal_pure_force_surfaces_smash():
    av = _view(
        live_cells=[(10, 10), (11, 10), (10, 11)],
        red_tiles=[_red(10, 10, 255), _red(11, 10, 180)],
    )
    grabs = vp.force_surface_grabs(av)
    smash = [g for g in grabs if g.action == "SMASH"]
    assert smash, grabs
    assert smash[0].target == (10, 10)
    assert smash[0].drop_at == (10, 10)  # drop ON the pure, auto-harvest
    assert smash[0].provenance == vp.LIVE


# ── WALK_IN: echo pure walkable from live frontier ─────────────────────────
def test_echo_pure_walkable_force_surfaces_walk_in():
    # pure at (12,10) is ECHO (not in world.live); live frontier at (10,10)/(11,10)
    # is one/two steps away → a walk-in must be offered (no probe needed).
    av = _view(
        live_cells=[(10, 10), (11, 10)],
        red_tiles=[_red(12, 10, 255, fresh=False)],
    )
    grabs = vp.force_surface_grabs(av)
    walk = [g for g in grabs if g.action == "WALK_IN"]
    assert walk, grabs
    g = walk[0]
    assert g.target == (12, 10)
    assert g.drop_at in {(10, 10), (11, 10)}      # dropped on a live cell
    assert g.cells and g.cells[0] != g.drop_at    # walks toward the pure
    assert (12, 10) in g.cells                     # path lands ON the pure


def test_unreachable_pure_without_probe_is_skipped():
    # ECHO pure far from any live cell → no walk-in within the hold budget → skip
    # (a probe is needed; that is seam_control / probe-hint territory, not Phase 1).
    av = _view(
        live_cells=[(0, 0)],
        red_tiles=[_red(30, 20, 255, fresh=False)],
    )
    grabs = vp.force_surface_grabs(av)
    assert not [g for g in grabs if g.tier == "pure"]


# ── dedup against the existing menu ────────────────────────────────────────
def test_pure_already_targeted_is_not_double_offered():
    av = _view(live_cells=[(10, 10)], red_tiles=[_red(10, 10, 255)])
    grabs = vp.force_surface_grabs(av, existing_targets={(10, 10)})
    assert not grabs  # a seam/chain already lands here → no duplicate grab


# ── mass + blue ────────────────────────────────────────────────────────────
def test_best_live_mass_force_surfaces_grab():
    av = _view(
        live_cells=[(5, 5), (6, 5)],
        red_tiles=[_red(5, 5, 200), _red(6, 5, 160)],
    )
    grabs = vp.force_surface_grabs(av)
    mass = [g for g in grabs if g.action == "GRAB_MASS"]
    assert mass and mass[0].target == (5, 5)


def test_rich_live_blue_force_surfaces_grab_with_spare_harvester():
    av = _view(
        live_cells=[(7, 7)],
        red_tiles=[],
        blue_tiles=[{"x": 7, "y": 7, "purity": 220}],
    )
    # No strong red chains (0) but a harvester alive → spare unit → blue surfaces.
    grabs = vp.force_surface_grabs(
        av, harvesters_alive=1, strong_chain_count=0,
    )
    blue = [g for g in grabs if g.action == "GRAB_BLUE"]
    assert blue and blue[0].colour == "BLUE"


# ── blue gate: only when a spare harvester exists or orbital asks ───────────
def test_blue_not_surfaced_when_no_spare_harvester():
    # 1 harvester and 1 strong red chain → no spare → blue is NOT surfaced.
    av = _view(
        live_cells=[(7, 7)],
        red_tiles=[],
        blue_tiles=[{"x": 7, "y": 7, "purity": 220}],
    )
    grabs = vp.force_surface_grabs(
        av, harvesters_alive=1, strong_chain_count=1, blue_requested=False,
    )
    assert not [g for g in grabs if g.action == "GRAB_BLUE"], grabs


def test_blue_surfaced_when_spare_harvester_beyond_strong_chains():
    # 2 harvesters, 1 strong red chain → a spare unit → blue surfaces and says so.
    av = _view(
        live_cells=[(7, 7)],
        red_tiles=[],
        blue_tiles=[{"x": 7, "y": 7, "purity": 220}],
    )
    grabs = vp.force_surface_grabs(
        av, harvesters_alive=2, strong_chain_count=1, blue_requested=False,
    )
    blue = [g for g in grabs if g.action == "GRAB_BLUE"]
    assert blue and "spare harvester" in blue[0].note


def test_blue_surfaced_when_orbital_requests_it_even_without_spare():
    # Orbital "grab_blue" overrides the spare-harvester rule: blue vault is low.
    av = _view(
        live_cells=[(7, 7)],
        red_tiles=[],
        blue_tiles=[{"x": 7, "y": 7, "purity": 220}],
    )
    grabs = vp.force_surface_grabs(
        av, harvesters_alive=1, strong_chain_count=1, blue_requested=True,
    )
    blue = [g for g in grabs if g.action == "GRAB_BLUE"]
    assert blue and "orbital" in blue[0].note


# ── agency wiring + packager compile ───────────────────────────────────────
def test_build_registry_surfaces_grab_kind_at_top():
    av = _view(
        live_cells=[(10, 10), (11, 10), (10, 11)],
        red_tiles=[_red(10, 10, 255)],
    )
    reg = agency.build_registry(agent_view=av)
    assert "GRAB1" in reg
    assert reg["GRAB1"].kind == "grab"
    # menu renders the PRIORITY RED GRABS header first
    menu = agency.format_menu_block(reg)
    assert "PRIORITY RED GRABS" in menu
    assert menu.index("PRIORITY RED GRABS") < (menu.index("PROBE") if "PROBE" in menu else len(menu))


def test_grab_compiles_to_a_drop_on_the_pure():
    av = _view(
        live_cells=[(10, 10), (11, 10), (10, 11)],
        red_tiles=[_red(10, 10, 255)],
    )
    reg = agency.build_registry(agent_view=av)
    moves, _log = packager.pack_recipe([reg["GRAB1"]], av)
    drops = [m for m in moves if m.get("a") == "drop"]
    assert len(drops) == 1
    assert tuple(drops[0]["at"]) == (10, 10)


def test_blue_grab_renders_in_its_own_group_when_spare_harvester():
    # A rich blue with a spare harvester (and no strong red chain) surfaces as a
    # blue_grab under the HIGH-YIELD BLUE GRABS header, and compiles like a chain.
    av = _view(
        live_cells=[(7, 7)],
        red_tiles=[],
        blue_tiles=[{"x": 7, "y": 7, "purity": 220}],
    )
    reg = agency.build_registry(agent_view=av, harvesters_alive=1)
    blue = [o for o in reg.values() if o.kind == "blue_grab"]
    assert blue, list(reg)
    menu = agency.format_menu_block(reg, harvesters_alive=1)
    assert "HIGH-YIELD BLUE GRABS" in menu
    moves, _log = packager.pack_recipe([blue[0]], av)
    assert [m for m in moves if m.get("a") == "drop"]


def test_blue_grab_absent_when_no_spare_harvester_and_strong_red():
    # A strong red chain claims the only harvester → no blue group surfaces.
    av = _view(
        live_cells=[(30, 6), (31, 6), (32, 6)],
        red_tiles=[_red(32, 6, 255), _red(31, 6, 200), _red(30, 6, 160)],
        blue_tiles=[{"x": 7, "y": 7, "purity": 220}],
    )
    reg = agency.build_registry(
        agent_view=av,
        chain_hints=[{
            "drop_at": [32, 6], "cells": [[32, 6], [31, 6], [30, 6]],
            "purities": [255, 200, 160], "length": 3,
        }],
        harvesters_alive=1,
    )
    assert not [o for o in reg.values() if o.kind == "blue_grab"], list(reg)


# ── Phase 2: probe-budget awareness (menu-side; orbit untouched) ────────────
def test_probe_cost_helper_matches_packager_spend_sites():
    grab = agency.Option("GRAB1", "grab", "t", "d", [], {"drop_at": [1, 1], "cells": []})
    chain = agency.Option("CH1", "chain", "t", "d", [], {"drop_at": [1, 1], "cells": []})
    probe = agency.Option("PR1", "probe", "t", "d", [], {"at": [2, 2]})
    ss = agency.Option("SS1", "supersede", "t", "d", [], {"probe_at": [3, 3]})
    hd = agency.Option("HD1", "hotdrop", "t", "d", [], {"probe_at": [4, 4], "drop_at": [5, 5]})
    hd_ss = agency.Option("HD2", "hotdrop", "t", "d", [], {"probe_at": [4, 4], "supersede": [6, 6]})
    seam = agency.Option("SMASH_GRAB", "seam", "t", "d", [], {"waves": [
        {"wave": 1, "drop_at": [7, 7]},                    # walk-in wave, 0 probe
        {"wave": 2, "drop_at": [8, 8], "probe_at": [9, 9]},  # probe-flanked, 1
    ]})
    assert agency._option_probe_cost(grab) == 0
    assert agency._option_probe_cost(chain) == 0
    assert agency._option_probe_cost(probe) == 1
    assert agency._option_probe_cost(ss) == 1
    assert agency._option_probe_cost(hd) == 1
    assert agency._option_probe_cost(hd_ss) == 2
    assert agency._option_probe_cost(seam) == 1


def test_menu_shows_budget_header_and_zero_probe_grab_tag():
    av = _view(
        live_cells=[(10, 10), (11, 10), (10, 11)],
        red_tiles=[_red(10, 10, 255)],
    )
    reg = agency.build_registry(agent_view=av)
    menu = agency.format_menu_block(reg, probe_stock=2)
    assert "PROBE BUDGET: you have 2 probe(s)" in menu
    # the force-surfaced pure grab is a zero-probe play → tagged "no probe"
    grab_line = next(ln for ln in menu.splitlines() if ln.strip().startswith("[GRAB1]"))
    assert "no probe" in grab_line


def test_menu_shows_harvester_budget_cap():
    # The concrete at-plan-time guardrail: tell the agent how many harvesters it
    # has and cap the number of runs it may select (RULEBOOK §3.9.2), so it does
    # not commit runs for harvesters it does not have.
    av = _view(
        live_cells=[(10, 10), (11, 10), (10, 11)],
        red_tiles=[_red(10, 10, 255)],
    )
    reg = agency.build_registry(agent_view=av)
    menu = agency.format_menu_block(reg, probe_stock=2, harvesters_alive=1)
    assert "HARVESTER BUDGET: you have 1 harvester(s) alive" in menu
    assert "AT MOST 1 harvest run" in menu
    assert "ONE outing per night" in menu
