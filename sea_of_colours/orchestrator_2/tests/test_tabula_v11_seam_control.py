"""v10 Phase 2 — redsign seam-control pattern generator.

Pins ring enumeration, the two-case named patterns (CASE 1 SMASH_GRAB / CASE 2
BLIND_GRAB+UNBEATEN_FLANK+WALK_IN), anti-crush geometry, weapon-driven cadence
(EMP spacing + flank-outside-blast, chaff backup note), and region de-dup.
"""

from __future__ import annotations

from sea_of_colours.game.weapons import EMP_RADIUS, EMP_CLOUD_HOURS
from sea_of_colours.orchestrator_2.harnesses.tabula_v7 import probe_hints
from sea_of_colours.orchestrator_2.harnesses.tabula_v7.probe_hints import _covers
from sea_of_colours.orchestrator_2.harnesses.tabula_v11 import seam_control as sc


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
def test_case1_emits_three_per_harvester_patterns_with_anti_crush_geometry():
    av = _view(mine=True)
    patterns = sc.build_seam_menu(av, _hints(av, mine=True))
    ids = [p.pattern_id for p in patterns]
    # CASE 1 is a per-harvester MENU: the SURE grab first, then the greedy H1
    # FULL_SWEEP alternative (offered when the visible seam is walkable), then the
    # mass + late-sweep ring waves.
    assert ids[0] == "SMASH_GRAB"
    assert "SECURE_MASS" in ids and "LATE_SWEEP" in ids
    assert "FULL_SWEEP" in ids
    sweep = next(p for p in patterns if p.pattern_id == "FULL_SWEEP")
    # Same first harvester as SMASH_GRAB (mutually exclusive), lifts, and actually
    # rides more than the sure grab.
    assert sweep.waves[0].unit_ordinal == 0 and sweep.waves[0].pickup_after is True
    assert len(sweep.waves[0].comb_path) >= 2
    assert all(p.mine is True for p in patterns)
    smash = patterns[0]
    assert smash.waves[0].earliest_hour == 1  # H1 smash is immediate
    # every wave with a fresh probe is drop-legal AND never crushes it.
    for p in patterns:
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


def test_case1_full_sweep_is_offered_with_honest_gamble_framing():
    """A visible own seam offers FULL_SWEEP alongside SMASH_GRAB: same first
    harvester, a LONGER walk than the sure grab, and a note that names it a GAMBLE
    scaling with players + season (offered, not decided deterministically)."""
    av = _view(mine=True)
    av["red_tiles"] = [
        {"x": 10, "y": 10, "purity": 255},   # pure core / beacon
        {"x": 9, "y": 10, "purity": 200},    # mass ring around it
        {"x": 11, "y": 10, "purity": 190},
        {"x": 10, "y": 9, "purity": 180},
        {"x": 10, "y": 11, "purity": 170},
    ]
    patterns = sc.build_seam_menu(av, _hints(av, mine=True))
    by_id = {p.pattern_id: p for p in patterns}
    assert "SMASH_GRAB" in by_id and "FULL_SWEEP" in by_id
    smash, sweep = by_id["SMASH_GRAB"], by_id["FULL_SWEEP"]
    # The sweep rides MORE than the sure grab, on the SAME first harvester.
    assert len(sweep.waves[0].comb_path) > len(smash.waves[0].comb_path)
    assert sweep.waves[0].unit_ordinal == smash.waves[0].unit_ordinal == 0
    note = sweep.waves[0].note.lower()
    assert "gamble" in note
    assert "more rivals" in note or "more players" in note.replace("rivals", "players")
    assert "season" in note


def test_case1_full_sweep_trimmed_short_under_weapons():
    """Under weapons the FULL_SWEEP is trimmed to the chaff-window length so it
    still lifts inside the safe window (the doctrine leans SMASH_GRAB there)."""
    av = _view(mine=True, chaff=True)
    av["red_tiles"] = [
        {"x": 10, "y": 10, "purity": 255},
        {"x": 9, "y": 10, "purity": 200},
        {"x": 11, "y": 10, "purity": 190},
        {"x": 10, "y": 9, "purity": 180},
        {"x": 10, "y": 11, "purity": 170},
    ]
    patterns = {p.pattern_id: p for p in sc.build_seam_menu(av, _hints(av, mine=True))}
    if "FULL_SWEEP" in patterns:  # only when a walkable seam remains under danger
        assert len(patterns["FULL_SWEEP"].waves[0].comb_path) <= sc._CHAFF_CHAIN_STEPS


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


# ── CASE 1 walk-in-from-live (echo pure, no probe) ───────────────────────
def _walkin_view(*, live, probe_stock=0, green=None, red=None):
    """A MINE redsign whose echo pure sits OUTSIDE live coverage (no covering
    probe), with a live frontier (``world.live``) to walk in from."""
    av = {
        "world": {
            "width": 30, "height": 30, "fog_count": 800,
            "live": [{"x": x, "y": y} for (x, y) in live],
        },
        "probe_stock": probe_stock,
        "entities": {"mine": []},            # NO covering probe -> not drop-legal
        "my_assets": [
            {"id": "harvester_p1_1", "kind": "harvester", "state": "orbit"},
        ],
        "redsign": [{
            "center": [10, 10], "cells": [[10, 10, 1.0]], "hour": 3, "mine": True,
        }],
        "blue_tiles": [],
        # echo pure at the beacon (visible-red channel carries echo too).
        "red_tiles": red or [{"x": 10, "y": 10, "purity": 255}],
        "last_night": {},
    }
    return av


def test_case1_walkin_when_pure_is_echo_and_no_probe():
    """The day-3 strand: mine pure known via echo, probe_stock=0, pure not
    drop-legal. The menu must offer a WALK-IN (drop on the live frontier, walk
    onto the pure) — NOT a probe-gated smash the packager cannot emit."""
    av = _walkin_view(live=[(12, 10), (11, 10), (10, 12)], probe_stock=0)
    patterns = sc.build_seam_menu(av, [])
    ids = [p.pattern_id for p in patterns]
    assert "WALKIN_GRAB" in ids
    grab = next(p for p in patterns if p.pattern_id == "WALKIN_GRAB")
    w1 = grab.waves[0]
    assert w1.probe_at is None                      # no probe needed
    assert tuple(w1.drop_at) in {(12, 10), (11, 10), (10, 12)}  # a live cell
    assert tuple(w1.comb_path[-1]) == (10, 10)      # walks onto the pure
    assert w1.pickup_after is True
    # every walk-in wave is probe-free (survives the probe budget).
    for p in patterns:
        for w in p.waves:
            assert w.probe_at is None and w.supersede is None


def test_case1_walkin_double_walks_the_pure():
    """Two live frontiers -> a SECOND walk-in onto the SAME pure (the EMP hedge),
    from a different drop cell."""
    av = _walkin_view(live=[(12, 10), (11, 10), (10, 12), (8, 10)], probe_stock=0)
    patterns = sc.build_seam_menu(av, [])
    ids = [p.pattern_id for p in patterns]
    assert "WALKIN_GRAB" in ids and "WALKIN_SECURE" in ids
    grab = next(p for p in patterns if p.pattern_id == "WALKIN_GRAB")
    secure = next(p for p in patterns if p.pattern_id == "WALKIN_SECURE")
    # distinct approach cells, both ending their walk on the pure.
    assert tuple(grab.waves[0].drop_at) != tuple(secure.waves[0].drop_at)
    assert (10, 10) in [tuple(c) for c in secure.waves[0].comb_path]


def test_case1_starves_when_pure_unreachable_and_no_probe():
    """Echo pure, NO live frontier to walk from, NO probe -> offer nothing rather
    than geometry the sanitizer would silently delete."""
    av = _walkin_view(live=[], probe_stock=0)
    assert sc.build_seam_menu(av, []) == []


def test_probe_budget_drops_rival_patterns_when_no_probe():
    """A rival's fogged seam needs a fresh probe to contest; with stock 0 every
    rival pattern is undroppable, so the menu offers none."""
    av = _view(mine=False, enemy_at=[10, 10])
    av["probe_stock"] = 0
    assert sc.build_seam_menu(av, _hints(av, mine=False)) == []


def test_case2_blind_grab_drops_on_value_not_trace():
    """BLIND_GRAB wave 1 lands on the best reachable value cell, not a trace
    edge, and still supersedes + stays drop-legal + short.

    Part B: the seam is LIVE-confirmed (``freshness='fresh'`` red on it), so the
    aggressive contest fires — a fogged seam would be CONTEST_DENY instead."""
    av = _view(mine=False, enemy_at=[10, 10])
    av["red_tiles"] = [
        {"x": 10, "y": 10, "purity": 255, "freshness": "fresh"},
        {"x": 12, "y": 11, "purity": 30, "freshness": "fresh"},  # trace edge — NOT the drop
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


def test_case2_fogged_rival_offers_blind_attack_plus_demoted_deny():
    """v11 doctrine: the usual rival case — the pure is FOGGED (no LIVE red on the
    seam) but a redsign is fresh + mass-rich, so we ATTACK by default. The menu
    offers a BLIND_GRAB (a real blind-walk attack) and a second-bearing
    UNBEATEN_FLANK, PLUS a DEMOTED CONTEST_DENY (deny-only) alternative."""
    av = _view(mine=False, enemy_at=[10, 10])  # no LIVE red -> pure is fogged
    patterns = sc.build_seam_menu(av, _hints(av, mine=False))
    kinds = [p.kind for p in patterns]
    assert kinds == ["BLIND_GRAB", "UNBEATEN_FLANK", "CONTEST_DENY"]
    blind = patterns[0].waves[0]
    # It is a real blind-walk attack (steps through fog), NOT a deny-only wave.
    assert blind.deny_only is False
    assert blind.blind_walk is True
    assert blind.pickup_after is True
    assert blind.comb_path                      # a bounded blind walk, not zero
    # CONTEST_DENY is still available as the demoted certainty play.
    deny = patterns[-1].waves[0]
    assert deny.deny_only is True
    assert deny.supersede == (10, 10)


def test_case2_fogged_rival_attacks_but_shortens_under_danger():
    """Danger (chaff) does not cancel the attack on a fogged rival seam — it
    trims the blind walk to the floor and keeps the demoted CONTEST_DENY."""
    av = _view(mine=False, enemy_at=[10, 10], chaff=True)  # fogged + chaff
    patterns = sc.build_seam_menu(av, _hints(av, mine=False))
    kinds = [p.kind for p in patterns]
    assert "BLIND_GRAB" in kinds and "CONTEST_DENY" in kinds
    blind = next(p for p in patterns if p.kind == "BLIND_GRAB").waves[0]
    assert blind.blind_walk is True
    assert len(blind.comb_path) <= sc._BLIND_SWEEP_FLOOR   # chaff trims the walk


def test_case2_fogged_blind_grab_supersedes_off_beacon_finder():
    """When the finder's probe sits OFF the beacon (the real board), the fogged
    BLIND_GRAB lands its ONE covering probe ON the finder — blinding them AND
    making the drop legal (free denial, one probe)."""
    finder = (13, 12)
    av = _view(
        mine=False, enemy_at=list(finder),
        cells=[[10, 10, 1.0], [11, 11, 1.0], [12, 12, 1.0], [13, 12, 1.0]],
    )  # fogged pure (no LIVE red); finder off the beacon centre
    blind = next(
        p for p in sc.build_seam_menu(av, _hints(av, mine=False))
        if p.kind == "BLIND_GRAB"
    )
    w1 = blind.waves[0]
    assert w1.blind_walk is True
    assert w1.supersede == finder                 # blind the finder for free
    assert w1.probe_at is None                     # one probe (the supersede covers)
    assert _covers(finder[0], finder[1], w1.drop_at[0], w1.drop_at[1])
    assert tuple(w1.drop_at) != finder             # drop is distinct (no self-crush)


def test_case2_fogged_attack_scales_to_probe_stock():
    """Inventory-scaled attack (the user's matrix): 1 probe surfaces only the H1
    BLIND_GRAB (+ maybe the demoted deny); 2 probes surface the two-bearing
    attack BLIND_GRAB + UNBEATEN_FLANK as well."""
    av = _view(mine=False, enemy_at=[10, 10])       # fogged rival seam

    one = [p.kind for p in sc.build_seam_menu(av, _hints(av, mine=False), probe_stock=1)]
    assert "BLIND_GRAB" in one
    assert "UNBEATEN_FLANK" not in one              # 2nd bearing needs a 2nd probe

    two = [p.kind for p in sc.build_seam_menu(av, _hints(av, mine=False), probe_stock=2)]
    assert "BLIND_GRAB" in two and "UNBEATEN_FLANK" in two
    assert "CONTEST_DENY" in two                    # deny stays visible alongside


# ── CASE 2 (not mine) ────────────────────────────────────────────────────
def test_case2_emits_three_waves_of_the_poker():
    # LIVE-confirmed rival seam (Part B) -> the aggressive three-wave contest.
    av = _view(mine=False, enemy_at=[10, 10])
    av["red_tiles"] = [{"x": 10, "y": 10, "purity": 255, "freshness": "fresh"}]
    patterns = sc.build_seam_menu(av, _hints(av, mine=False))
    ids = [p.pattern_id for p in patterns]
    assert ids == ["BLIND_GRAB", "UNBEATEN_FLANK", "WALK_IN"]
    blind = patterns[0]
    # BLIND_GRAB supersedes the finder's probe on the beacon.
    assert blind.waves[0].supersede == (10, 10)


def test_case2_geometry_is_drop_legal():
    av = _view(mine=False, enemy_at=[10, 10])
    av["red_tiles"] = [{"x": 10, "y": 10, "purity": 255, "freshness": "fresh"}]
    for p in sc.build_seam_menu(av, _hints(av, mine=False)):
        for w in p.waves:
            if w.probe_at is not None:
                assert w.probe_at != w.drop_at
                assert _covers(*w.probe_at, w.drop_at[0], w.drop_at[1])


# ── A3: chaff-window pickup timing (short later waves, lift early) ───────
def _rich_live_seam(*, chaff):
    """A LIVE-confirmed rival seam with a dense red ring so the later secured
    waves would otherwise build a long comb (max out at 6 steps)."""
    av = _view(mine=False, enemy_at=[10, 10], chaff=chaff)
    tiles = []
    for x in range(6, 15):
        for y in range(6, 15):
            tiles.append({"x": x, "y": y, "purity": 200, "freshness": "fresh"})
    av["red_tiles"] = tiles
    return av


def test_a3_no_chaff_lets_later_waves_ride_a_longer_chain():
    av = _rich_live_seam(chaff=False)
    pats = {p.kind: p for p in sc.build_seam_menu(av, _hints(av, mine=False))}
    flank = pats["UNBEATEN_FLANK"].waves[0]
    walk = pats["WALK_IN"].waves[0]
    # Quiet board -> the secured waves are NOT force-shortened / early-lifted.
    assert flank.pickup_after is False
    assert walk.pickup_after is False
    # A rich ring should give at least one of them a chain longer than the
    # chaff cap (proving the cap below is chaff-gated, not always-on).
    assert max(len(flank.comb_path), len(walk.comb_path)) > sc._CHAFF_CHAIN_STEPS


def test_a3_chaff_shortens_later_waves_and_lifts_early():
    av = _rich_live_seam(chaff=True)
    pats = {p.kind: p for p in sc.build_seam_menu(av, _hints(av, mine=False))}
    for kind in ("UNBEATEN_FLANK", "WALK_IN"):
        w = pats[kind].waves[0]
        assert len(w.comb_path) <= sc._CHAFF_CHAIN_STEPS, kind
        assert w.pickup_after is True, kind
        assert "A3" in w.note


def test_a3_mine_late_sweep_shortens_under_weapons():
    # CASE-1 LATE_SWEEP also keeps its chain short + lifts early under chaff.
    av = _view(mine=True, chaff=True)
    av["red_tiles"] = [
        {"x": x, "y": y, "purity": 200, "freshness": "fresh"}
        for x in range(6, 15) for y in range(6, 15)
    ]
    pats = {p.kind: p for p in sc.build_seam_menu(av, _hints(av, mine=True))}
    late = pats["LATE_SWEEP"].waves[0]
    assert len(late.comb_path) <= sc._CHAFF_CHAIN_STEPS
    assert late.pickup_after is True


# ── M3: CASE-2 anchored to the FINDER's probe ────────────────────────────
def test_case2_supersede_anchors_to_finder_probe_off_beacon():
    """When the discoverer's probe sits OFF the jittered beacon centre (but
    inside the smear), the contest supersedes THAT probe cell, not the beacon —
    on a LIVE-confirmed seam (BLIND_GRAB) or a fogged one (CONTEST_DENY alike)."""
    av = _view(
        mine=False, enemy_at=[13, 12],
        cells=[[10, 10, 1.0], [11, 11, 1.0], [12, 12, 1.0], [13, 12, 1.0]],
    )
    av["red_tiles"] = [{"x": 10, "y": 10, "purity": 255, "freshness": "fresh"}]
    blind = next(
        p for p in sc.build_seam_menu(av, _hints(av, mine=False))
        if p.kind == "BLIND_GRAB"
    )
    assert blind.waves[0].supersede == (13, 12)


def test_case2_fogged_deny_supersedes_and_confirms_toward_finder():
    """Part B: on a FOGGED rival seam, CONTEST_DENY supersedes the finder's probe
    and lights a confirm probe that leans toward the finder (nearest the pure),
    committing no harvester drop."""
    beacon = (10, 10)
    finder = (13, 12)
    av = _view(
        mine=False, enemy_at=list(finder),
        cells=[[10, 10, 1.0], [11, 11, 1.0], [12, 12, 1.0], [13, 12, 1.0]],
    )  # fogged pure (no LIVE red)
    deny = next(
        p for p in sc.build_seam_menu(av, _hints(av, mine=False))
        if p.kind == "CONTEST_DENY"
    )
    w1 = deny.waves[0]
    assert w1.deny_only is True
    assert w1.supersede == finder
    pa = w1.probe_at
    assert pa is not None and _covers(pa[0], pa[1], beacon[0], beacon[1])
    # the confirm probe sits on the finder's side of the beacon.
    d_finder = abs(pa[0] - finder[0]) + abs(pa[1] - finder[1])
    d_beacon_finder = abs(beacon[0] - finder[0]) + abs(beacon[1] - finder[1])
    assert d_finder < d_beacon_finder


# ── weapon-driven cadence ────────────────────────────────────────────────
def test_emp_spaces_later_waves_and_flanks_outside_blast():
    # LIVE-confirmed seams (Part B) so the flank wave exists to be EMP-spaced.
    near = _view(mine=False, enemy_at=[10, 10], emp_at=[11, 10])
    far = _view(mine=False, enemy_at=[10, 10])
    for av in (near, far):
        av["red_tiles"] = [{"x": 10, "y": 10, "purity": 255, "freshness": "fresh"}]
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
    # LIVE-confirmed seam so BLIND_GRAB fires and carries the chaff backup note.
    av = _view(mine=False, enemy_at=[10, 10], chaff=True)
    av["red_tiles"] = [{"x": 10, "y": 10, "purity": 255, "freshness": "fresh"}]
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


def test_planned_probe_cells_unions_wave_probes_and_supersedes():
    """The harness feeds these to the frontier sampler so exploration probes
    can't stack next to a probe the seam attack already commits."""
    av = _view(mine=False, enemy_at=[13, 12],
               cells=[[10, 10, 1.0], [13, 12, 1.0]])
    patterns = sc.build_seam_menu(av, _hints(av, mine=False))
    cells = sc.planned_probe_cells(patterns)
    # Every probe_at / supersede across every wave is surfaced, deduped.
    expected = set()
    for p in patterns:
        for w in p.waves:
            for c in (w.probe_at, w.supersede):
                if c is not None:
                    expected.add((int(c[0]), int(c[1])))
    assert set(cells) == expected and len(cells) == len(set(cells))
    assert expected  # a fogged rival seam commits at least one probe


def test_planned_supersede_cells_only_covers_wave_supersedes():
    """Only the cells a wave lands ON a rival probe (``supersede``) — NOT covering
    ``probe_at`` cells. The harness feeds these to the SUPERSEDE builder so a
    stand-alone SS never re-offers a blind the seam attack already performs."""
    av = _view(mine=False, enemy_at=[13, 12],
               cells=[[10, 10, 1.0], [13, 12, 1.0]])
    patterns = sc.build_seam_menu(av, _hints(av, mine=False))
    ss_cells = set(sc.planned_supersede_cells(patterns))
    expected = {
        (int(w.supersede[0]), int(w.supersede[1]))
        for p in patterns for w in p.waves if w.supersede is not None
    }
    assert ss_cells == expected
    # The enemy finder at (13,12) is what a BLIND_GRAB blinds -> it is surfaced,
    # and it is a strict subset of the full planned-probe set.
    assert ss_cells <= set(sc.planned_probe_cells(patterns))


def test_fogged_rival_region_yields_blind_attack_without_a_hint():
    """The dual-redsign gap at the single level: a rival's redsign known ONLY as
    a region (fog, no hot-drop hint) must still produce a CASE-2 play — v11 makes
    that the blind ATTACK (blind-grab + flank) plus the demoted CONTEST_DENY."""
    av = _view(mine=False)          # one rival region at (10,10), no hints passed
    patterns = sc.build_seam_menu(av, [])
    assert {p.kind for p in patterns} == {
        "BLIND_GRAB", "UNBEATEN_FLANK", "CONTEST_DENY",
    }
    assert all(p.mine is not True for p in patterns)


def test_dual_redsign_mine_first_rival_suffixed():
    """MINE + a RIVAL beacon at once: the own set keeps the base IDs (priority),
    the rival's (fogged) set is suffixed #2 — the blind-attack pair plus the
    demoted CONTEST_DENY#2 — the menu the DUAL fork needs."""
    av = _view(mine=True)                     # own region at (10,10), covered probe
    av["redsign"].append({                    # a rival's find, still in fog
        "center": [25, 25], "cells": [[25, 25, 1.0]], "hour": 4, "mine": False,
    })
    patterns = sc.build_seam_menu(av, [])
    ids = [p.pattern_id for p in patterns]
    # own seam first (priority), base IDs; rival seam second, #2 suffix.
    assert ids[:3] == ["SMASH_GRAB", "SECURE_MASS", "LATE_SWEEP"]
    assert "BLIND_GRAB#2" in ids               # the rival seam is ATTACKED, not just denied
    assert "CONTEST_DENY#2" in ids             # demoted certainty fallback still present
    mine_ids = [p.pattern_id for p in patterns if p.mine is True]
    assert mine_ids == ["SMASH_GRAB", "SECURE_MASS", "LATE_SWEEP"]


# ── R3 anti-crowd: mirror seats fan out on the same rival beacon ─────────
def test_r3_mirror_seats_get_distinct_blind_grab_cells():
    # LIVE-confirmed seam so the aggressive BLIND_GRAB fires and seats fan its
    # drop cell (a fogged seam is CONTEST_DENY with no drop to fan).
    av = _view(mine=False, enemy_at=[12, 11])
    av["red_tiles"] = [{"x": 10, "y": 10, "purity": 255, "freshness": "fresh"}]

    def _blind_drop(seat):
        blind = next(
            p for p in sc.build_seam_menu(
                av, _hints(av, mine=False), seat_index=seat,
            )
            if p.kind == "BLIND_GRAB"
        )
        return tuple(blind.waves[0].drop_at)

    lead = _blind_drop(0)
    r1 = _blind_drop(1)
    r2 = _blind_drop(2)
    # Lead seat keeps the triangulated primary; rivals fan to distinct cells.
    assert len({lead, r1, r2}) == 3
