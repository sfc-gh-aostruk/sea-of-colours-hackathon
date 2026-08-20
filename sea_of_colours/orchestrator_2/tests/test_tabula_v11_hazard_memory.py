"""Part A1 — the persistent, fog-surviving stripped/GREEN hazard memory.

Locks the monotonic-union behaviour that lets the packager/sanitizer forbid a
drop/step onto a cell we have EVER seen green, even one now hidden by fog (the
seed-56 blind-drop-onto-rival-stripped-green collapse).
"""

from __future__ import annotations

import pytest

from sea_of_colours.orchestrator_2.harnesses.tabula_v11 import (
    hazard_memory as hz,
)


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch):
    # Keep the unit tests purely in-process: no Snowflake read/write so the
    # monotonic-union behaviour is asserted against the cache alone (a live DB
    # would leak rows across tests and mask the logic).
    hz.clear_cache()
    monkeypatch.setattr(hz, "_persist", lambda *a, **k: None)
    monkeypatch.setattr(hz, "_hydrate", lambda *a, **k: set())
    yield
    hz.clear_cache()


def _view(green_cells):
    """A minimal view whose ``world.live`` marks ``green_cells`` synthetic GREEN."""
    return {
        "world": {
            "width": 40, "height": 28,
            "live": [
                {"x": x, "y": y, "tile": "GREEN", "lineage": "synthetic"}
                for (x, y) in green_cells
            ],
        }
    }


def test_view_green_cells_reads_synthetic_and_hazard():
    view = {
        "world": {
            "live": [
                {"x": 1, "y": 1, "tile": "GREEN", "lineage": "synthetic"},
                {"x": 2, "y": 2, "tile": "GREEN", "lineage": "natural"},
                {"x": 3, "y": 3, "tile": "RED"},
            ]
        }
    }
    assert hz.view_green_cells(view) == {(1, 1), (2, 2)}


def test_accumulate_is_monotonic_across_turns():
    # Night 1 sees (1,1); night 2 sees (2,2) but NOT (1,1) (it went to fog).
    u1 = hz.accumulate("S", "p1", _view([(1, 1)]))
    assert (1, 1) in u1
    u2 = hz.accumulate("S", "p1", _view([(2, 2)]))
    # (1,1) survives even though it is no longer in the current view (fog).
    assert (1, 1) in u2 and (2, 2) in u2


def test_load_returns_the_accumulated_union():
    hz.accumulate("S", "p1", _view([(4, 5), (6, 7)]))
    assert hz.load("S", "p1") == {(4, 5), (6, 7)}


def test_seats_are_isolated():
    hz.accumulate("S", "p1", _view([(1, 1)]))
    hz.accumulate("S", "p2", _view([(9, 9)]))
    assert hz.load("S", "p1") == {(1, 1)}
    assert hz.load("S", "p2") == {(9, 9)}


def test_empty_view_returns_empty_union():
    assert hz.accumulate("S", "p1", _view([])) == set()
