"""v9 Phase 2 — redsign seam-control pattern generator.

Pins ring enumeration, the two-case named patterns (CASE 1 SMASH_GRAB / CASE 2
BLIND_GRAB+UNBEATEN_FLANK+WALK_IN), anti-crush geometry, weapon-driven cadence
(EMP spacing + flank-outside-blast, chaff backup note), and region de-dup.
"""

from __future__ import annotations

from sea_of_colours.game.weapons import EMP_RADIUS, EMP_CLOUD_HOURS
from sea_of_colours.orchestrator_2.harnesses.tabula_v7 import probe_hints
from sea_of_colours.orchestrator_2.harnesses.tabula_v7.probe_hints import _covers
from sea_of_colours.orchestrator_2.harnesses.tabula_v9 import seam_control as sc


def _view(*, mine=False, enemy_at=None, emp_at=None, chaff=False, cells=None):
    av = {
        "world": {"width": 30, "height": 30, "live": [], "fog_count": 800},
        "orbit": {"probe_stock": 3},
        "my_assets": [
            {"id": "harvester_p1_1", "kind": "harvester", "state": "orbit"},
        ],
        "redsign": [{
            "center": [10, 10],
            "cells": cells or [[10, 10, 1.0]],
            "hour": 3,
            "mine": mine,
        }],
        "blue_tiles": [],
        "red_tiles": [],
        "last_night": {},
    }
    # A redsign that is MINE means a friendly probe already revealed the pure —
    # model that covering probe so drop-straight (drop-legal) geometry can fire.
    if mine:
        av["entities"] = {"mine": [
            {"id": "probe_p1_1", "type": "probe", "pos": [12, 11],
             "nights_remaining": 2},
        ]}
    if enemy_at is not None:
        av["competitor_intel"] = {
            "new_this_day": [
                {"kind": "enemy_probe_launch", "at": list(enemy_at), "day_seen": 2},
            ],
        }
    ln = {}
    if emp_at is not None:
        ln["emp_scars"] = [{"at": list(emp_at), "hours": [8, 9]}]
    if chaff:
        ln["incoming_attacks"] = [{"type": "chaff_jam", "by": ["p2"]}]
    av["last_night"] = ln
    return av


def _hints(av, *, mine=None):
    hd = probe_hints.top_hot_drop_hints(av, max_hints=2)
    if mine is not None:
        for h in hd:
            h["mine"] = mine
    return hd


# ── ring enumeration ────────────────────────────────────────────────────
def test_ring_enumerates_value_cells_ranked_by_purity():
    av = _view()
    av["red_tiles"] = [
        {"x": 9, "y": 10, "purity": 120},
        {"x": 11, "y": 10, "purity": 250},
    ]
    ring = sc.enumerate_value_ring(av, (10, 10), (10, 10))
    assert ring
    # smear centre is treated as pure(255) and outranks the visible 250/120.
    assert ring[0]["at"] == [10, 10]
    assert ring[0]["purity"] == 255
    purities = [c["purity"] for c in ring]
    assert purities == sorted(purities, reverse=True)


def test_ring_empty_off_seam():
    av = _view()
    # a probe far from any red / smear sees no value cells.
    assert sc.enumerate_value_ring(av, (10, 10), (28, 28)) == []


# ── CASE 1 (mine) ────────────────────────────────────────────────────────
def test_case1_emits_smash_grab_with_anti_crush_geometry():
    av = _view(mine=True)
    patterns = sc.build_seam_menu(av, _hints(av, mine=True))
    ids = [p.pattern_id for p in patterns]
    assert ids == ["SMASH_GRAB"]
    p = patterns[0]
    assert p.mine is True
    assert p.waves[0].earliest_hour == 1  # wave-1 smash is immediate
    # every wave with a fresh probe is drop-legal AND never crushes it.
    for w in p.waves:
        if w.probe_at is not None:
            assert w.probe_at != w.drop_at
            assert _covers(w.probe_at[0], w.probe_at[1], w.drop_at[0], w.drop_at[1])


def test_case1_wave1_drops_on_core_and_secures_short():
    """The grab is the DROP: wave 1 lands ON the richest reachable cell
    (auto-harvest), keeps the securing comb SHORT, drops STRAIGHT (no probe) when
    the core is already in live vision, and picks up immediately."""
    av = _view(mine=True)
    av["red_tiles"] = [
        {"x": 10, "y": 10, "purity": 255},  # the pure core (also the beacon)
        {"x": 9, "y": 10, "purity": 120},
        {"x": 11, "y": 10, "purity": 90},
    ]
    p = sc.build_seam_menu(av, _hints(av, mine=True))[0]
    w1 = p.waves[0]
    # Lands directly on the pure core cell (banked as free parcel #1).
    assert tuple(w1.drop_at) == (10, 10)
    # DROP-FIRST: the pure is already visible red, so no probe is needed.
    assert w1.probe_at is None
    # Secured short: at most the short-grab step budget before pickup.
    assert len(w1.comb_path) <= sc._SHORT_GRAB_STEPS
    # It IS a grab: pick up immediately after landing.
    assert w1.pickup_after is True
    assert "auto-harvest" in w1.note or "FAST" in w1.note


def test_case1_danger_gates_grab_to_zero_steps():
    """Under danger (chaff), the CASE-1 grab takes ZERO extra steps — just drop
    on the pure and pick up (secure the jackpot before it can be spilled)."""
    av = _view(mine=True, chaff=True)
    av["red_tiles"] = [
        {"x": 10, "y": 10, "purity": 255},
        {"x": 9, "y": 10, "purity": 200},
        {"x": 11, "y": 10, "purity": 180},
    ]
    p = sc.build_seam_menu(av, _hints(av, mine=True))[0]
    w1 = p.waves[0]
    assert tuple(w1.drop_at) == (10, 10)
    assert w1.comb_path == []          # no walk under danger
    assert w1.pickup_after is True


def test_case1_lands_on_pure_even_when_hint_probe_falls_short():
    """Regression (the day-2 whiff): the fog hint's probe lands SHORT of the
    pure, but an existing probe already covers the visible pure. Wave 1 must drop
    STRAIGHT on the pure — never re-probe to the hint's short cell."""
    av = _view(mine=True)
    # The pure is offset from the smear centre and covered by an EXISTING probe
    # (centre far from the pure but within r4) — as on the real board.
    av["entities"] = {"mine": [
        {"id": "probe_p1_1", "type": "probe", "pos": [13, 12],
         "nights_remaining": 2},  # covers (11,11): dx=2,dy=1 -> 5 <= 16
    ]}
    av["red_tiles"] = [
        {"x": 11, "y": 11, "purity": 255},  # the pure, offset from smear (10,10)
        {"x": 10, "y": 11, "purity": 150},
    ]
    hints = _hints(av, mine=True)
    for h in hints:                      # force a short/blind hint probe
        h["probe_at"] = [7, 8]           # (7,8) does NOT cover (11,11)
    p = sc.build_seam_menu(av, hints)[0]
    w1 = p.waves[0]
    assert tuple(w1.drop_at) == (11, 11)   # the pure, not the hint's short cell
    assert w1.probe_at is None             # already covered -> drop straight
    assert w1.pickup_after is True


def test_case2_blind_grab_drops_on_value_not_trace():
    """BLIND_GRAB wave 1 lands on the best reachable value cell, not a trace
    edge, and still supersedes + stays drop-legal + short."""
    av = _view(mine=False, enemy_at=[10, 10])
    av["red_tiles"] = [
        {"x": 10, "y": 10, "purity": 255},
        {"x": 12, "y": 11, "purity": 30},  # trace edge — must NOT be the drop
    ]
    blind = next(
        p for p in sc.build_seam_menu(av, _hints(av, mine=False))
        if p.kind == "BLIND_GRAB"
    )
    w1 = blind.waves[0]
    assert tuple(w1.drop_at) == (10, 10)
    assert w1.supersede == (10, 10)
    assert _covers(w1.probe_at[0], w1.probe_at[1], w1.drop_at[0], w1.drop_at[1])
    # Here the pure is VISIBLE (red_tiles) -> it is a KNOWN target, so the grab
    # snatches it straight (no sweep needed).
    assert w1.comb_path == []
    assert w1.pickup_after is True


def test_case2_blind_grab_sweeps_when_pure_is_fogged():
    """The usual rival case: the pure is FOGGED, so the drop is a guess off the
    jittered smear. The grab must comb a SHORT sweep (never 0) to actually land
    the pure — 'a bit more than one move'."""
    av = _view(mine=False, enemy_at=[10, 10])  # no red_tiles -> pure is fogged
    blind = next(
        p for p in sc.build_seam_menu(av, _hints(av, mine=False))
        if p.kind == "BLIND_GRAB"
    )
    w1 = blind.waves[0]
    assert 1 <= len(w1.comb_path) <= sc._BLIND_SWEEP_STEPS
    assert w1.pickup_after is True


def test_case2_blind_grab_sweep_floors_but_never_zero_under_danger():
    """Danger (chaff) trims the blind sweep to the FLOOR, but not to zero — a
    single-cell blind grab banks trace for nothing."""
    av = _view(mine=False, enemy_at=[10, 10], chaff=True)  # fogged + chaff
    blind = next(
        p for p in sc.build_seam_menu(av, _hints(av, mine=False))
        if p.kind == "BLIND_GRAB"
    )
    w1 = blind.waves[0]
    assert 1 <= len(w1.comb_path) <= sc._BLIND_SWEEP_FLOOR


# ── CASE 2 (not mine) ────────────────────────────────────────────────────
def test_case2_emits_three_waves_of_the_poker():
    av = _view(mine=False, enemy_at=[10, 10])
    patterns = sc.build_seam_menu(av, _hints(av, mine=False))
    ids = [p.pattern_id for p in patterns]
    assert ids == ["BLIND_GRAB", "UNBEATEN_FLANK", "WALK_IN"]
    blind = patterns[0]
    # BLIND_GRAB supersedes the finder's probe on the beacon.
    assert blind.waves[0].supersede == (10, 10)


def test_case2_geometry_is_drop_legal():
    av = _view(mine=False, enemy_at=[10, 10])
    for p in sc.build_seam_menu(av, _hints(av, mine=False)):
        for w in p.waves:
            if w.probe_at is not None:
                assert w.probe_at != w.drop_at
                assert _covers(*w.probe_at, w.drop_at[0], w.drop_at[1])


# ── M3: CASE-2 anchored to the FINDER's probe ────────────────────────────
def test_case2_supersede_anchors_to_finder_probe_off_beacon():
    """When the discoverer's probe sits OFF the jittered beacon centre (but
    inside the smear), BLIND_GRAB supersedes THAT probe cell, not the beacon."""
    av = _view(
        mine=False, enemy_at=[13, 12],
        cells=[[10, 10, 1.0], [11, 11, 1.0], [12, 12, 1.0], [13, 12, 1.0]],
    )
    blind = next(
        p for p in sc.build_seam_menu(av, _hints(av, mine=False))
        if p.kind == "BLIND_GRAB"
    )
    assert blind.waves[0].supersede == (13, 12)


def test_case2_blind_drop_triangulates_toward_finder():
    """The blind drop is pulled toward the finder's probe (where the pure was
    revealed), not left on the beacon centre (M3 triangulation)."""
    beacon = (10, 10)
    finder = (13, 12)
    av = _view(
        mine=False, enemy_at=list(finder),
        cells=[[10, 10, 1.0], [11, 11, 1.0], [12, 12, 1.0], [13, 12, 1.0]],
    )  # fogged pure (no red_tiles)
    blind = next(
        p for p in sc.build_seam_menu(av, _hints(av, mine=False))
        if p.kind == "BLIND_GRAB"
    )
    drop = tuple(blind.waves[0].drop_at)
    d_finder = abs(drop[0] - finder[0]) + abs(drop[1] - finder[1])
    d_beacon_finder = abs(beacon[0] - finder[0]) + abs(beacon[1] - finder[1])
    assert d_finder < d_beacon_finder
    # still a legal, coverable drop off its own fresh probe.
    pa = blind.waves[0].probe_at
    assert pa is not None and _covers(pa[0], pa[1], drop[0], drop[1])


# ── weapon-driven cadence ────────────────────────────────────────────────
def test_emp_spaces_later_waves_and_flanks_outside_blast():
    near = _view(mine=False, enemy_at=[10, 10], emp_at=[11, 10])
    far = _view(mine=False, enemy_at=[10, 10])
    flank_near = next(
        p for p in sc.build_seam_menu(near, _hints(near, mine=False))
        if p.kind == "UNBEATEN_FLANK"
    )
    flank_far = next(
        p for p in sc.build_seam_menu(far, _hints(far, mine=False))
        if p.kind == "UNBEATEN_FLANK"
    )
    # EMP present -> the later wave is pushed past the cloud window.
    assert flank_near.waves[0].earliest_hour == flank_far.waves[0].earliest_hour + EMP_CLOUD_HOURS
    # ...and its fresh probe is still drop-legal (covers the beacon) and is not
    # sitting on the EMP scar centre (blast-clearance is best-effort by angle).
    pa = flank_near.waves[0].probe_at
    assert pa is not None
    assert _covers(pa[0], pa[1], 10, 10)
    assert (pa[0], pa[1]) != (11, 10)


def test_chaff_adds_backup_note_to_blind_grab():
    av = _view(mine=False, enemy_at=[10, 10], chaff=True)
    blind = next(
        p for p in sc.build_seam_menu(av, _hints(av, mine=False))
        if p.kind == "BLIND_GRAB"
    )
    assert "backup" in blind.waves[0].note.lower()


# ── region de-dup + empty ────────────────────────────────────────────────
def test_same_region_does_not_spawn_duplicate_patterns():
    # two smear cells of ONE region must not yield #2 duplicates.
    av = _view(mine=False, enemy_at=[10, 10], cells=[[10, 10, 1.0], [11, 10, 1.0]])
    patterns = sc.build_seam_menu(av, _hints(av, mine=False))
    assert not any(p.pattern_id.endswith("#2") for p in patterns)


def test_no_redsign_yields_empty_menu():
    av = _view()
    av["redsign"] = []
    assert sc.build_seam_menu(av, []) == []
