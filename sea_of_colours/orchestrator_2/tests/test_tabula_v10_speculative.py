"""v10 speculative bluesign picker — per-seat cluster + drop-point variation."""

from __future__ import annotations

import random

from sea_of_colours.orchestrator_2.harnesses.tabula_v10 import speculative


def _view():
    # Three bright, comparably-lit clusters in different regions of the board.
    return {
        "world": {"width": 40, "height": 28, "fog_count": 40 * 28, "live": []},
        "blue_sign": [
            {"center": [8, 6], "cells": [[8, 6, 0.9], [9, 6, 0.8], [8, 7, 0.75]]},
            {"center": [30, 8], "cells": [[30, 8, 0.88], [31, 8, 0.82]]},
            {"center": [20, 22], "cells": [[20, 22, 0.86], [20, 23, 0.7]]},
        ],
    }


def test_returns_bluesign_hotdrops_with_expected_schema():
    hints = speculative.sample_bluesign_hotdrops(
        _view(), rng=random.Random(1), max_hints=2,
    )
    assert 1 <= len(hints) <= 2
    h = hints[0]
    assert set(h) >= {"probe_at", "drop_at", "signal_type", "comb_path", "varied"}
    assert h["signal_type"] == "blue_sign"
    assert h["varied"] is True
    # probe launched on the drop (its disk covers the K+1 landing).
    assert h["probe_at"] == h["drop_at"]


def test_seats_pick_different_first_drops():
    view = _view()
    firsts = {
        seat: tuple(
            speculative.sample_bluesign_hotdrops(
                view, rng=random.Random(500 + seat), max_hints=1,
            )[0]["drop_at"]
        )
        for seat in range(3)
    }
    # Not all three seats land on the identical brightest cell.
    assert len(set(firsts.values())) >= 2


def test_empty_without_bluesign():
    assert speculative.sample_bluesign_hotdrops(
        {"world": {"width": 40, "height": 28}}, rng=random.Random(0),
    ) == []


def test_alt_drops_are_other_cells_of_the_same_seam():
    hints = speculative.sample_bluesign_hotdrops(
        _view(), rng=random.Random(3), max_hints=1,
    )
    h = hints[0]
    drop = tuple(h["drop_at"])
    for a in h.get("alt_drops") or []:
        assert tuple(a) != drop
