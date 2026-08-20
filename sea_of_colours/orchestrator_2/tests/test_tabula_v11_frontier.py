"""v10 frontier-probe placement — fuzzy, enemy-aware, edge-seeking.

Proves the day-1 centre pile-up is broken: seats spread across the board, avoid
known enemy landings, never re-probe their own ground, and the picks vary with
the seat while still always offering something when fog remains.
"""

from __future__ import annotations

import random

from sea_of_colours.orchestrator_2.harnesses.tabula_v11 import frontier


def _day1_view(width: int = 40, height: int = 28):
    # All fog, no LOS, no signals — the day-1 board where v1-9 all probe centre.
    return {
        "world": {"width": width, "height": height, "fog_count": width * height,
                  "live": []},
        "entities": {"mine": []},
    }


def _rng(seat: int) -> random.Random:
    return random.Random(1000 + seat)


def setup_function(_fn):
    frontier.reset()


def _cheby(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def test_day1_offers_multiple_spread_probes_not_just_centre():
    view = _day1_view()
    hints = frontier.select_frontier_probes(
        view, session_id="s", seat_index=0, rng=_rng(0), max_hints=3,
    )
    assert len(hints) >= 2
    cells = [tuple(h["at"]) for h in hints]
    # A seat's own picks are min-separated (never stacked).
    for i in range(len(cells)):
        for j in range(i + 1, len(cells)):
            assert _cheby(cells[i], cells[j]) >= 5
    # Not all clustered on the exact map centre.
    assert not all(c == (20, 14) for c in cells)


def test_seats_open_in_different_regions():
    view = _day1_view()
    firsts = {
        seat: tuple(
            frontier.select_frontier_probes(
                view, session_id="s", seat_index=seat, rng=_rng(seat), max_hints=3,
            )[0]["at"]
        )
        for seat in (0, 1, 2)
    }
    # Three seats -> three distinct opening probes (sector bias + per-seat rng).
    assert len({firsts[0], firsts[1], firsts[2]}) == 3


def test_enemy_landings_are_avoided():
    view = _day1_view()
    # Record a dense enemy presence in the top-left; frontier should steer away.
    enemy_view = {
        "competitor_intel": {
            "new_this_day": [
                {"kind": "enemy_probe_launch", "at": [6, 6], "day_seen": 1},
                {"kind": "enemy_probe_launch", "at": [8, 8], "day_seen": 1},
            ]
        }
    }
    frontier.record_enemy_landings("s", "p1", enemy_view, day=1)
    hints = frontier.select_frontier_probes(
        view, session_id="s", seat_index=0, rng=_rng(0), max_hints=3, player="p1",
    )
    # No pick sits on top of the enemy cluster.
    for h in hints:
        assert _cheby(tuple(h["at"]), (6, 6)) >= 3
        assert _cheby(tuple(h["at"]), (8, 8)) >= 3


def test_own_history_not_reprobed():
    view = _day1_view()
    own = [(16, 10), (22, 16)]
    hints = frontier.select_frontier_probes(
        view, session_id="s", seat_index=0, rng=_rng(0), max_hints=3,
        own_history=own,
    )
    for h in hints:
        for p in own:
            assert _cheby(tuple(h["at"]), p) >= 4


def test_avoid_cells_barred_like_own_probes():
    # The seam attack's planned probe cells are fed in as avoid_cells; a frontier
    # probe must never stack next to one (that ground is already lit).
    view = _day1_view()
    avoid = [(16, 10), (22, 16)]
    hints = frontier.select_frontier_probes(
        view, session_id="s", seat_index=0, rng=_rng(0), max_hints=3,
        avoid_cells=avoid,
    )
    for h in hints:
        for p in avoid:
            assert _cheby(tuple(h["at"]), p) >= 4


def test_empty_when_no_fog():
    view = {"world": {"width": 40, "height": 28, "fog_count": 0, "live": []}}
    assert frontier.select_frontier_probes(
        view, session_id="s", seat_index=0, rng=_rng(0),
    ) == []


def test_enemy_memory_accumulates_across_turns():
    frontier.record_enemy_landings("s", "p1", {
        "competitor_intel": {"new_this_day": [
            {"kind": "enemy_probe_launch", "at": [3, 3], "day_seen": 1}]}
    }, day=1)
    frontier.record_enemy_landings("s", "p1", {
        "competitor_intel": {"new_this_day": [
            {"kind": "enemy_probe_launch", "at": [30, 20], "day_seen": 2}]}
    }, day=2)
    acc = frontier.enemy_landings("s", "p1")
    assert (3, 3) in acc and (30, 20) in acc


def test_enemy_memory_is_per_seat():
    frontier.record_enemy_landings("s", "p1", {
        "competitor_intel": {"new_this_day": [
            {"kind": "enemy_probe_launch", "at": [3, 3], "day_seen": 1}]}
    }, day=1)
    # p2 saw a different enemy cell; the two seats' records are independent.
    assert frontier.enemy_landings("s", "p2") == set()


def test_hints_have_frontier_schema():
    view = _day1_view()
    h = frontier.select_frontier_probes(
        view, session_id="s", seat_index=0, rng=_rng(0), max_hints=1,
    )[0]
    assert set(h) >= {"at", "area_gain", "edge_promise", "extends_from", "contested"}
    assert h["extends_from"] == "frontier"
    assert h["area_gain"] > 0
