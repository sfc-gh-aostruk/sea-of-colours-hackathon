"""v9 Fix A — seat-differentiated, ownership-aware hot-drop dispersion.

Proves distinct seats fan out onto DISTINCT seam cells (breaking the
symmetric drop collision) and that a seat's OWN redsign keeps the
smash-and-grab primary.
"""

from __future__ import annotations

from sea_of_colours.orchestrator_2.harnesses.tabula_v9 import hint_dispersion


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
    # And each leads with its rotated assignment.
    assert drops["p1"] == (2, 14)
    assert drops["p2"] == (3, 14)
    assert drops["p3"] == (2, 12)


def test_seat_offset_and_reordered_menu():
    view = _view(mine=False)
    out = hint_dispersion.personalize_hot_drops(
        [_contested_redsign_hint()], view, "p2",
    )[0]
    assert out["seat_offset"] == [3, 14]
    assert out["mine"] is False
    # Menu rotated so the assignment leads.
    assert out["alt_drops"][0] == [3, 14]


def test_my_redsign_keeps_smash_and_grab():
    view = _view(mine=True)
    out = hint_dispersion.personalize_hot_drops(
        [_contested_redsign_hint()], view, "p1",
    )[0]
    # CASE 1: I found it -> primary drop stays on the pure, no seat offset.
    assert out["mine"] is True
    assert out["drop_at"] == [2, 9]
    assert "seat_offset" not in out


def test_non_contested_passes_through_with_ownership():
    view = _view(mine=False)
    hint = _contested_redsign_hint()
    hint["contested"] = False
    out = hint_dispersion.personalize_hot_drops([hint], view, "p3")[0]
    assert out["drop_at"] == [2, 9]  # untouched
    assert out.get("mine") is False  # still attributed


def test_bluesign_hint_untouched():
    view = _view(mine=False)
    hint = {
        "signal_type": "blue_sign",
        "contested": True,
        "probe_at": [10, 10],
        "drop_at": [11, 11],
        "alt_drops": [[12, 12]],
    }
    out = hint_dispersion.personalize_hot_drops([hint], view, "p2")[0]
    assert out["drop_at"] == [11, 11]
    assert "mine" not in out
