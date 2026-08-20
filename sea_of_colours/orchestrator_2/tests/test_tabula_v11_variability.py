"""v10 Phase 1 — seeded tie-break variability in the shared hint compilers.

Pins the four guarantees:
  * frozen-safety   — rng=None path is deterministic + unchanged for v6/v7/v8.
  * reproducibility — same seed -> same output (auditable, replayable).
  * divergence      — different seat seeds fan out onto different picks.
  * never-trade-down — the tie shuffle only reorders within an epsilon band.
"""

from __future__ import annotations

import random

from sea_of_colours.orchestrator_2.harnesses.tabula_v7 import probe_hints
from sea_of_colours.orchestrator_2.harnesses.tabula_v7.probe_hints import (
    _tie_shuffle,
)


# ── the tie-shuffle primitive ──────────────────────────────────────────
def test_tie_shuffle_reproducible():
    items = list(range(20))
    items.sort(reverse=True)
    a = _tie_shuffle(list(items), lambda x: float(x), random.Random(7), 2.0)
    b = _tie_shuffle(list(items), lambda x: float(x), random.Random(7), 2.0)
    assert a == b


def test_tie_shuffle_never_trades_down_past_epsilon():
    rng = random.Random(123)
    eps = 3.0
    for _ in range(200):
        vals = sorted((rng.uniform(0, 50) for _ in range(30)), reverse=True)
        out = _tie_shuffle(list(vals), lambda x: x, random.Random(rng.random()), eps)
        # Invariant: for any earlier position i and later j, key(i) >= key(j)-eps.
        for i in range(len(out)):
            for j in range(i + 1, len(out)):
                assert out[i] >= out[j] - eps - 1e-9


def test_tie_shuffle_keeps_distinct_tiers_ordered():
    # Two clear tiers separated by > epsilon must never interleave.
    items = [100.0, 99.5, 99.0, 10.0, 9.5, 9.0]
    out = _tie_shuffle(list(items), lambda x: x, random.Random(1), 2.0)
    assert set(out[:3]) == {100.0, 99.5, 99.0}
    assert set(out[3:]) == {10.0, 9.5, 9.0}


# ── views with many equally-good candidates ────────────────────────────
def _multi_redsign_view():
    """All-fog board with a wide redsign smear -> many equal hot-drop targets."""
    return {
        "world": {"width": 30, "height": 30, "live": [], "fog_count": 800},
        "orbit": {"probe_stock": 3},
        "my_assets": [
            {"id": "harvester_p1_1", "kind": "harvester", "state": "orbit"},
        ],
        "redsign": [{
            "center": [15, 15],
            "cells": [[8, 8, 1.0], [22, 22, 1.0], [8, 22, 1.0],
                      [22, 8, 1.0], [15, 15, 1.0]],
            "hour": 3,
        }],
        "blue_tiles": [],
    }


def _multi_fog_view():
    """All-fog board with several equal fog clusters -> equal probe candidates."""
    return {
        "world": {"width": 30, "height": 30, "live": [], "fog_count": 800},
        "fog_clusters": [
            {"centroid": [5, 5], "nearest_visible_edge": [6, 6]},
            {"centroid": [24, 24], "nearest_visible_edge": [23, 23]},
            {"centroid": [5, 24], "nearest_visible_edge": [6, 23]},
            {"centroid": [24, 5], "nearest_visible_edge": [23, 6]},
        ],
    }


# ── frozen-safety (rng=None) ───────────────────────────────────────────
def test_probe_hints_none_path_deterministic_and_unchanged():
    v = _multi_fog_view()
    a = probe_hints.top_probe_hints(v, max_hints=3)
    b = probe_hints.top_probe_hints(v, max_hints=3, rng=None)
    c = probe_hints.top_probe_hints(v, max_hints=3)
    assert a == b == c  # adding the param did not change the frozen path


def test_hot_drop_none_path_deterministic_and_unchanged():
    v = _multi_redsign_view()
    a = probe_hints.top_hot_drop_hints(v, max_hints=2)
    b = probe_hints.top_hot_drop_hints(v, max_hints=2, rng=None)
    assert a == b


# ── reproducibility (same seed -> same output) ─────────────────────────
def test_probe_hints_seeded_reproducible():
    v = _multi_fog_view()
    a = probe_hints.top_probe_hints(v, max_hints=3, rng=random.Random(42))
    b = probe_hints.top_probe_hints(v, max_hints=3, rng=random.Random(42))
    assert a == b


def test_hot_drop_seeded_reproducible():
    v = _multi_redsign_view()
    a = probe_hints.top_hot_drop_hints(v, max_hints=2, rng=random.Random(42))
    b = probe_hints.top_hot_drop_hints(v, max_hints=2, rng=random.Random(42))
    assert a == b


# ── divergence (different seeds fan out) ───────────────────────────────
def test_probe_hints_diverge_across_seeds():
    v = _multi_fog_view()
    firsts = set()
    for s in range(16):
        hints = probe_hints.top_probe_hints(v, max_hints=1, rng=random.Random(s))
        if hints:
            firsts.add(tuple(hints[0]["at"]))
    assert len(firsts) > 1, "seeded probe hints should not all pick the same cell"


def test_hot_drop_diverges_across_seeds():
    v = _multi_redsign_view()
    firsts = set()
    for s in range(16):
        hints = probe_hints.top_hot_drop_hints(v, max_hints=1, rng=random.Random(s))
        if hints:
            firsts.add(tuple(hints[0]["drop_at"]))
    assert len(firsts) > 1, "seeded hot-drops should not all pick the same cell"


# ── never invents materially worse candidates ──────────────────────────
def test_seeded_hot_drop_stays_on_redsign():
    """With redsign present, no seed should demote to a worse (bluesign) pick."""
    v = _multi_redsign_view()
    for s in range(16):
        hints = probe_hints.top_hot_drop_hints(v, max_hints=1, rng=random.Random(s))
        assert hints
        assert hints[0]["signal_type"] == "redsign"
