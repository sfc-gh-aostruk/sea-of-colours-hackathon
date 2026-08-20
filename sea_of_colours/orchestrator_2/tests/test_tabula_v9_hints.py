"""Unit tests for the v9 ranked/contested hint metadata (Workstream B).

The shared compilers in ``tabula_v7.probe_hints`` gained additive
competitive-choice keys — ``contested`` / ``alt_drops`` / ``supersede`` on hot
drops, ``contested`` on probe placements — WITHOUT changing the primary pick
(so frozen v6/v7/v8 are unaffected). v9 renders them via a TACTICAL OPTIONS
block. These tests pin both the additive data and the render, and assert the
options-only stance (deterministic offsets, no hidden RNG).
"""

from __future__ import annotations

from sea_of_colours.orchestrator_2.harnesses.tabula_v7 import probe_hints
from sea_of_colours.orchestrator_2.harnesses.tabula_v9 import prompt as prompt_mod


def _hot_drop_view(*, enemy_at=None):
    """Minimal view that yields one redsign hot-drop hint."""
    av = {
        "world": {"width": 24, "height": 24, "live": [], "fog_count": 500},
        "orbit": {"probe_stock": 2},
        "my_assets": [
            {"id": "harvester_p1_1", "kind": "harvester", "state": "orbit"},
        ],
        "redsign": [{"center": [10, 10], "cells": [[10, 10, 1.0]], "hour": 3}],
        "blue_tiles": [],
    }
    if enemy_at is not None:
        av["competitor_intel"] = {
            "new_this_day": [
                {"kind": "enemy_probe_launch", "at": list(enemy_at), "day_seen": 2},
            ],
        }
    return av


# ── hot-drop additive metadata ─────────────────────────────────────────
def test_hot_drop_redsign_is_contested_with_seam_alternatives():
    hints = probe_hints.top_hot_drop_hints(_hot_drop_view(), max_hints=1)
    assert hints, "expected a redsign hot-drop hint"
    h = hints[0]
    assert h["signal_type"] == "redsign"
    assert h["contested"] is True
    # Offset seam options are provided (diversity of OPTIONS, not one pick).
    assert h["alt_drops"], "contested beacon should offer offset seam drops"
    # Each alt is a distinct, adjacent seam cell (Manhattan dist 1-2), never
    # the advertised beacon itself.
    for a in h["alt_drops"]:
        assert a != [10, 10]
        assert 1 <= abs(a[0] - 10) + abs(a[1] - 10) <= 2


def test_hot_drop_primary_pick_unchanged_by_additive_keys():
    """Back-compat: probe_at/drop_at are exactly what v7/v8 already read."""
    h = probe_hints.top_hot_drop_hints(_hot_drop_view(), max_hints=1)[0]
    # Original contract keys still present + well-formed.
    for k in ("signal_type", "probe_at", "drop_at", "area_gain", "unit",
              "note", "target_in_fog", "comb_path"):
        assert k in h
    # Probe never centres on the drop (the anti-crush guarantee is intact).
    assert h["probe_at"] != h["drop_at"]


def test_hot_drop_supersede_option_when_enemy_probe_covers_beacon():
    h = probe_hints.top_hot_drop_hints(
        _hot_drop_view(enemy_at=[10, 10]), max_hints=1,
    )[0]
    assert h["contested"] is True
    assert h["supersede"] == [10, 10]


def test_hot_drop_no_supersede_when_no_enemy():
    h = probe_hints.top_hot_drop_hints(_hot_drop_view(), max_hints=1)[0]
    assert h["supersede"] is None


def test_hot_drop_alternatives_are_deterministic():
    """Options-only stance: same board -> same offsets (no hidden RNG)."""
    a = probe_hints.top_hot_drop_hints(_hot_drop_view(), max_hints=1)[0]
    b = probe_hints.top_hot_drop_hints(_hot_drop_view(), max_hints=1)[0]
    assert a["alt_drops"] == b["alt_drops"]


# ── probe-placement contested flag ─────────────────────────────────────
def test_probe_hint_contested_flag_on_redsign_seed():
    av = {
        "world": {"width": 24, "height": 24, "live": [], "fog_count": 500},
        "redsign": [{"center": [10, 10], "cells": [[10, 10, 1.0]], "hour": 3}],
    }
    hints = probe_hints.top_probe_hints(av, max_hints=3)
    assert hints
    assert any(h.get("extends_from") == "redsign" and h.get("contested")
               for h in hints)


# ── v9 render ──────────────────────────────────────────────────────────
def test_tactics_block_renders_offsets_and_supersede():
    hints = probe_hints.top_hot_drop_hints(
        _hot_drop_view(enemy_at=[10, 10]), max_hints=1,
    )
    block = prompt_mod.format_hint_tactics_block(hints, [])
    assert "TACTICAL OPTIONS" in block
    # Raw (un-personalized) contested redsign renders the CASE 2 offset menu.
    assert "CASE 2" in block
    assert "other seam cells if blocked" in block
    assert "SUPERSEDE" in block


def test_tactics_block_empty_when_nothing_contested():
    assert prompt_mod.format_hint_tactics_block([], []) == ""
    # A non-contested hint produces no tactics noise.
    plain = [{"signal_type": "blue_sign", "drop_at": [3, 3], "contested": False}]
    assert prompt_mod.format_hint_tactics_block(plain, []) == ""
