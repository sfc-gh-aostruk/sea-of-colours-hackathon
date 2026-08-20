"""v10 Fix A — seat-differentiated, ownership-aware hot-drop dispersion.

Proves distinct seats fan out onto DISTINCT seam cells (breaking the
symmetric drop collision) and that a seat's OWN redsign keeps the
smash-and-grab primary.
"""

from __future__ import annotations

from sea_of_colours.orchestrator_2.harnesses.tabula_v10 import hint_dispersion


def _view(mine: bool = False):
    return {
        "world": {"width": 40, "height": 28},
        "redsign": [
            {
                "id": "redsign-0",
                "center": [2, 13],
                "cells": [[2, 9, 255], [2, 12, 240], [3, 14, 210]],
                "mine": mine,
            }
        ],
    }


def _contested_redsign_hint():
    return {
        "signal_type": "redsign",
        "contested": True,
        "probe_at": [2, 11],
        "drop_at": [2, 9],
        "alt_drops": [[2, 14], [3, 14], [2, 12]],
        "comb_path": [],
    }


def test_seat_index_maps_arena_seats():
    assert hint_dispersion.seat_index("p1") == 0
    assert hint_dispersion.seat_index("p2") == 1
    assert hint_dispersion.seat_index("p3") == 2


def test_rivals_fan_out_to_distinct_cells():
    view = _view(mine=False)
    drops = {}
    for seat in ("p1", "p2", "p3"):
        out = hint_dispersion.personalize_hot_drops(
            [_contested_redsign_hint()], view, seat,
        )
        drops[seat] = tuple(out[0]["drop_at"])
    # The whole point: three seats -> three DISTINCT seam cells.
    assert len({drops["p1"], drops["p2"], drops["p3"]}) == 3
    # Lead seat KEEPS the smash-and-grab primary (the pure guess); flankers
    # pincer the seam centre (2,13) from distinct bearings (E then S).
    assert drops["p1"] == (2, 9)
    assert drops["p2"] == (5, 13)     # E flank of the centre
    assert drops["p3"] == (2, 16)     # S flank of the centre


def test_flank_wave_sweeps_inward_toward_the_pure():
    view = _view(mine=False)
    out = hint_dispersion.personalize_hot_drops(
        [_contested_redsign_hint()], view, "p2",
    )[0]
    assert out["seat_offset"] == [5, 13]
    assert out["mine"] is False
    assert out["approach_bearing"] == [1, 0]         # approached from the east
    # Comb sweeps INWARD, stopping one cell shy of the contested pure (2,13).
    assert out["comb_path"] == [[3, 13]]


def test_my_redsign_keeps_smash_and_grab():
    view = _view(mine=True)
    out = hint_dispersion.personalize_hot_drops(
        [_contested_redsign_hint()], view, "p1",
    )[0]
    # CASE 1: I found it -> primary drop stays on the pure, no seat offset.
    assert out["mine"] is True
    assert out["drop_at"] == [2, 9]
    assert "seat_offset" not in out


def test_non_contested_public_beacon_still_fans_out():
    # R3: a FRESH day-1 broadcast is not yet "contested" but is still public and
    # raced by all seats — it must fan out too (the seed-69 day-1 pile-up).
    view = _view(mine=False)
    hint = _contested_redsign_hint()
    hint["contested"] = False
    lead = hint_dispersion.personalize_hot_drops([hint], view, "p1")[0]
    rival = hint_dispersion.personalize_hot_drops([hint], view, "p3")[0]
    assert lead["drop_at"] == [2, 9]      # lead seat keeps the pure guess
    assert rival["drop_at"] != [2, 9]     # rival fans to a distinct cell
    assert rival.get("mine") is False     # still attributed


def test_bluesign_fans_out_for_rival_seats_but_not_lead():
    # R3 generalized: a public bluesign/fog hot-drop is raced too, so it fans for
    # non-lead seats. The lead seat keeps the primary; ownership is never stamped
    # on a non-redsign hint.
    view = _view(mine=False)
    hint = {
        "signal_type": "blue_sign",
        "probe_at": [10, 10],
        "drop_at": [11, 11],
        "alt_drops": [[12, 12]],
    }
    lead = hint_dispersion.personalize_hot_drops([dict(hint)], view, "p1")[0]
    rival = hint_dispersion.personalize_hot_drops([dict(hint)], view, "p3")[0]
    assert lead["drop_at"] == [11, 11]        # lead unchanged
    assert rival["drop_at"] != [11, 11]       # rival fans out
    assert "mine" not in lead and "mine" not in rival


def _cheby(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def test_untyped_fog_hotdrop_fans_out_on_day1():
    # The day-1 failure: no redsign in view yet, hot-drop has no signal_type.
    view = {"world": {"width": 40, "height": 28}, "redsign": []}
    hint = {"probe_at": [33, 19], "drop_at": [35, 21], "alt_drops": []}
    drops = {
        seat: tuple(
            hint_dispersion.personalize_hot_drops([dict(hint)], view, seat)[0]["drop_at"]
        )
        for seat in ("p1", "p2", "p3")
    }
    assert drops["p1"] == (35, 21)                       # lead keeps primary
    assert len({drops["p1"], drops["p2"], drops["p3"]}) == 3   # all distinct
    # And ≥3 apart so short comb walks can't clip (the residual day-1 issue).
    assert _cheby(drops["p1"], drops["p2"]) >= 3
    assert _cheby(drops["p1"], drops["p3"]) >= 3
    assert _cheby(drops["p2"], drops["p3"]) >= 3


def test_known_redsign_seats_separated_by_min_sep():
    # A clustered day-1 redsign broadcast (public at planning): seats must still
    # separate ≥3 even though it's classed redsign (tight ring alone gave 1-apart).
    view = _view(mine=False)  # redsign region present, not discovered by me
    hint = {
        "signal_type": "redsign",
        "probe_at": [33, 19],
        "drop_at": [35, 21],
        "alt_drops": [[34, 21], [35, 20]],
    }
    drops = {
        seat: tuple(
            hint_dispersion.personalize_hot_drops([dict(hint)], view, seat)[0]["drop_at"]
        )
        for seat in ("p1", "p2", "p3")
    }
    assert _cheby(drops["p1"], drops["p2"]) >= 3
    assert _cheby(drops["p1"], drops["p3"]) >= 3
    assert _cheby(drops["p2"], drops["p3"]) >= 3


def test_probes_fan_out_for_rival_seats():
    view = {"world": {"width": 40, "height": 28}}
    hints = [{"at": [33, 19]}, {"at": [20, 10]}]
    lead = hint_dispersion.personalize_probes(hints, view, "p1")
    r2 = hint_dispersion.personalize_probes(hints, view, "p2")
    r3 = hint_dispersion.personalize_probes(hints, view, "p3")
    assert lead[0]["at"] == [33, 19]              # lead unchanged
    firsts = {tuple(lead[0]["at"]), tuple(r2[0]["at"]), tuple(r3[0]["at"])}
    assert len(firsts) == 3                        # three distinct probe cells
