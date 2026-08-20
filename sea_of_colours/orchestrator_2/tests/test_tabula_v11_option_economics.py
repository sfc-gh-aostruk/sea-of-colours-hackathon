"""Unit tests for tabula_v11 option_economics — the numbers behind the menu.

Covers the yield math (engine scoring model: RED tier multiplier + best-row
transit, BLUE=fissile, GREEN=-100), crush detection (your probe vs an enemy
probe), collision risk (enemy vision x cell value + weapon bump), and the walk
extraction across every option shape.
"""

from __future__ import annotations

from types import SimpleNamespace

from sea_of_colours.orchestrator_2.harnesses.tabula_v11 import (
    option_economics as oe,
)


def _view(live=(), *, mine=(), enemy=(), width=40, height=28):
    """Assemble a minimal agent_view.

    ``live``  — iterable of (tile, x, y, purity) rows for world.live.
    ``mine``  — iterable of (x, y) friendly probe centres.
    ``enemy`` — iterable of (x, y) enemy probe launches.
    """
    return {
        "world": {
            "width": width, "height": height,
            "live": [
                {"tile": t, "x": x, "y": y, "purity": p}
                for (t, x, y, p) in live
            ],
        },
        "entities": {
            "mine": [{"type": "probe", "pos": [x, y]} for (x, y) in mine],
        },
        "competitor_intel": {
            "new_this_day": [
                {"kind": "enemy_probe_launch", "at": [x, y], "day_seen": 1}
                for (x, y) in enemy
            ],
        },
        "red_tiles": [],
    }


# ── yield ───────────────────────────────────────────────────────────────────
def test_yield_red_uses_engine_tier_and_best_row_transit():
    """RED score = max(0, purity-10) x MULT[tier]: pure 735, mass 285, vein 90,
    trace(50) 30 -> 1140; tiers tallied; blue is fissile-only; green is -100."""
    live = [
        ("RED", 1, 1, 255),   # pure  -> (255-10)*3.0 = 735
        ("RED", 2, 1, 200),   # mass  -> (200-10)*1.5 = 285
        ("RED", 3, 1, 100),   # vein  -> (100-10)*1.0 = 90
        ("RED", 4, 1, 50),    # trace -> (50-10)*0.75 = 30
        ("BLUE", 5, 1, 120),  # fissile, 0 score
        ("GREEN", 6, 1, 255),  # -100 penalty
    ]
    av = _view(live)
    cells = [(1, 1), (2, 1), (3, 1), (4, 1), (5, 1), (6, 1), (10, 10)]
    yb = oe.yield_breakdown(cells, av)
    assert yb["red_pts"] == 1140
    assert yb["red_tiers"] == {"pure": 1, "mass": 1, "vein": 1, "trace": 1}
    assert yb["blue_fissile"] == 120
    assert yb["green_penalty"] == -100
    assert yb["green_cells"] == 1
    assert yb["unknown_cells"] == 1          # (10,10) is fog
    assert yb["banked"] == 6                 # 6 coloured cells, under hold cap


def test_yield_flags_cells_past_the_hold_cap():
    """More than 6 coloured cells: only 6 bank; the rest are flagged over-hold."""
    live = [("RED", i, 0, 100) for i in range(8)]
    av = _view(live)
    yb = oe.yield_breakdown([(i, 0) for i in range(8)], av)
    assert yb["banked"] == oe.HOLD_CAPACITY == 6
    assert yb["over_hold"] == 2


def test_yield_all_fog_is_unknown_not_zero():
    """A blind hot-drop walk over fog reports unknown, never a fake red yield."""
    av = _view([])
    yb = oe.yield_breakdown([(5, 5), (5, 6), (5, 7)], av)
    assert yb["red_pts"] == 0
    assert yb["unknown_cells"] == 3
    assert not yb["red_tiers"]


# ── crush ────────────────────────────────────────────────────────────────────
def test_crush_self_on_own_probe_centre():
    """A harvester walk that lands on YOUR probe centre crushes it (bad)."""
    av = _view([("RED", 5, 5, 100)], mine=[(5, 5)])
    payload = {"drop_at": [5, 5], "cells": [[5, 5], [5, 6]]}
    rep = oe.crush_report(payload, av)
    assert (5, 5) in rep["self"]
    assert rep["enemy"] == []


def test_crush_enemy_on_supersede():
    """A probe launched onto an ENEMY probe centre supersedes it (good denial)."""
    av = _view([], enemy=[(10, 10)])
    payload = {"probe_at": [10, 10]}
    rep = oe.crush_report(payload, av)
    assert (10, 10) in rep["enemy"]
    assert rep["self"] == []


# ── self-crush verdict (BOTH gates: loot tier + future probe utility) ────────
def _view_probe_nights(tile, x, y, purity, nights):
    """A view with one live cell that also carries a friendly probe (with a set
    nights_remaining) sitting on it — the loot-on-your-own-probe case."""
    return {
        "world": {"width": 40, "height": 28,
                  "live": [{"tile": tile, "x": x, "y": y, "purity": purity}]},
        "entities": {"mine": [
            {"type": "probe", "pos": [x, y], "nights_remaining": nights},
        ]},
        "red_tiles": [],
    }


def test_self_crush_pure_is_take_because_extracting_seam():
    # pure(255) under your probe, 3 nights left, mid-season: banking the pure IS
    # extracting the seam -> the disk is being consumed anyway -> TAKE (OR gate).
    av = _view_probe_nights("RED", 5, 5, 255, nights=3)
    econ = oe.annotate({"drop_at": [5, 5], "cells": [[5, 5]]}, av, day=3, day_cap=7)
    note = " ".join(econ["crush_self_notes"]).lower()
    assert "take" in note and "avoid" not in note


def test_self_crush_vein_still_useful_is_worthwhile_not_avoid():
    # A high-value VEIN under a still-useful probe with NO mass/pure in the walk:
    # the loot tier alone clears the OR gate -> WORTHWHILE, never a blanket avoid.
    av = _view_probe_nights("RED", 5, 5, 120, nights=3)
    econ = oe.annotate({"drop_at": [5, 5], "cells": [[5, 5]]}, av, day=3, day_cap=7)
    note = " ".join(econ["crush_self_notes"]).lower()
    assert "worthwhile" in note and "avoid" not in note


def test_self_crush_trace_probe_still_useful_is_avoid():
    # Only a trace cell under a still-useful probe, nothing rich in the walk ->
    # NEITHER gate clears -> AVOID (the one case we protect the disk).
    av = _view_probe_nights("RED", 5, 5, 30, nights=3)
    econ = oe.annotate({"drop_at": [5, 5], "cells": [[5, 5]]}, av, day=3, day_cap=7)
    note = " ".join(econ["crush_self_notes"]).lower()
    assert "avoid" in note


def test_self_crush_trace_passover_is_fine_when_extracting_seam():
    # A trace cell sits under your probe but the SAME walk banks a pure elsewhere
    # -> you are stripping the seam, so the disk is consumed anyway: not AVOID.
    av = {
        "world": {"width": 40, "height": 28, "live": [
            {"tile": "RED", "x": 5, "y": 5, "purity": 30},    # trace, under probe
            {"tile": "RED", "x": 6, "y": 5, "purity": 255},   # pure elsewhere
        ]},
        "entities": {"mine": [
            {"type": "probe", "pos": [5, 5], "nights_remaining": 3},
        ]},
        "red_tiles": [],
    }
    econ = oe.annotate({"drop_at": [5, 5], "cells": [[5, 5], [6, 5]]}, av, day=3, day_cap=7)
    note = " ".join(econ["crush_self_notes"]).lower()
    assert "avoid" not in note and "no live vision is lost" in note


def test_self_crush_final_night_high_value_is_take():
    # Final night -> the probe's vision is worthless; a pure under it -> TAKE.
    av = _view_probe_nights("RED", 5, 5, 255, nights=2)
    econ = oe.annotate({"drop_at": [5, 5], "cells": [[5, 5]]}, av, day=7, day_cap=7)
    note = " ".join(econ["crush_self_notes"]).lower()
    assert "final night" in note and "take" in note
    assert "avoid" not in note


def test_self_crush_expiring_probe_high_value_is_free_trade():
    # Probe expires after tonight (1 night left) -> crushing costs no future
    # vision; a mass cell under it -> TAKE.
    av = _view_probe_nights("RED", 5, 5, 200, nights=1)
    econ = oe.annotate({"drop_at": [5, 5], "cells": [[5, 5]]}, av, day=3, day_cap=7)
    note = " ".join(econ["crush_self_notes"]).lower()
    assert "take" in note and "avoid" not in note


def test_self_crush_no_day_info_still_takes_high_value():
    # Without day/day_cap, a pure grab still clears the OR gate (extracting) and
    # never blanket-avoids a high-value grab.
    av = _view_probe_nights("RED", 5, 5, 255, nights=3)
    econ = oe.annotate({"drop_at": [5, 5], "cells": [[5, 5]]}, av)
    note = " ".join(econ["crush_self_notes"]).lower()
    assert "take" in note and "avoid" not in note


# ── collision risk ─────────────────────────────────────────────────────────
def test_risk_low_when_nothing_watched():
    av = _view([("RED", 1, 1, 100)], enemy=[(30, 20)])
    level, _ = oe.collision_risk([(1, 1)], av)
    assert level == "LOW"


def test_risk_med_for_low_value_cell_under_enemy_vision():
    av = _view([("RED", 11, 10, 30)], enemy=[(10, 10)])  # trace under enemy disk
    level, reason = oe.collision_risk([(11, 10)], av)
    assert level == "MED"
    assert "enemy vision" in reason


def test_risk_high_for_mass_cell_under_enemy_vision():
    av = _view([("RED", 11, 10, 200)], enemy=[(10, 10)])  # mass under enemy disk
    level, reason = oe.collision_risk([(11, 10)], av)
    assert level == "HIGH"
    assert "mass/pure" in reason


def test_risk_weapon_bump_lifts_med_to_high():
    av = _view([("RED", 11, 10, 30)], enemy=[(10, 10)])
    armed = {"p2": SimpleNamespace(emps_max=1, chaff_max=0)}
    level, reason = oe.collision_risk([(11, 10)], av, armed)
    assert level == "HIGH"
    assert "EMP/chaff" in reason


# A PUBLIC redsign is contested regardless of probe vision — "no enemy vision" is
# a trap when everyone got the broadcast (the exact bug behind riding CH1 over the
# pure because the menu read LOW).
def test_risk_high_on_public_redsign_without_any_enemy_vision():
    av = _view([("RED", 11, 10, 255)])  # NO enemy probe anywhere
    av["redsign"] = [{"center": [11, 10], "cells": [[11, 10, 5]], "hour": 3}]
    level, reason = oe.collision_risk([(11, 10)], av)
    assert level == "HIGH"
    assert "PUBLIC redsign" in reason
    assert "regardless of probe vision" in reason


def test_risk_public_redsign_footprint_covers_the_ring():
    # A ring cell within the dilated broadcast footprint is publicly contested too.
    av = _view([("RED", 13, 10, 200)])
    av["redsign"] = [{"cells": [[11, 10, 5]], "hour": 3}]  # centre (11,10), (13,10) within r2
    level, reason = oe.collision_risk([(13, 10)], av)
    assert level == "HIGH"
    assert "PUBLIC redsign" in reason


def test_risk_low_far_from_redsign_and_unwatched():
    av = _view([("RED", 1, 1, 100)])
    av["redsign"] = [{"cells": [[30, 20, 5]], "hour": 3}]
    level, _ = oe.collision_risk([(1, 1)], av)
    assert level == "LOW"


# ── walk extraction ─────────────────────────────────────────────────────────
def test_walk_cells_chain_includes_drop_then_steps():
    payload = {"drop_at": [5, 5], "cells": [[5, 5], [5, 6], [5, 7]]}
    assert oe.walk_cells(payload) == [(5, 5), (5, 6), (5, 7)]


def test_walk_cells_hotdrop_is_drop_plus_comb():
    payload = {"drop_at": [2, 2], "comb_path": [[2, 3], [2, 4]]}
    assert oe.walk_cells(payload) == [(2, 2), (2, 3), (2, 4)]


def test_walk_cells_seam_skips_deny_only_waves():
    payload = {"waves": [
        {"drop_at": [3, 3], "comb_path": [[3, 4], [3, 5]]},
        {"deny_only": True, "drop_at": [9, 9]},
    ]}
    assert oe.walk_cells(payload) == [(3, 3), (3, 4), (3, 5)]


def test_annotate_bundles_walk_yield_crush_risk():
    av = _view([("RED", 5, 5, 255), ("RED", 5, 6, 100)])
    payload = {"drop_at": [5, 5], "cells": [[5, 5], [5, 6]]}
    econ = oe.annotate(payload, av)
    assert econ["walk"] == [(5, 5), (5, 6)]
    assert econ["length"] == 2
    assert econ["yield"]["red_pts"] == 735 + 90
    assert econ["crush"] == {"self": [], "enemy": []}
    assert econ["risk"][0] == "LOW"
