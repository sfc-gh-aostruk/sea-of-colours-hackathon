"""Unit tests for the tabula_v8 worldview restructure.

Covers the fork's new feeding-layer levers:
  * the 3-pillar section scaffold + mode contracts + directive injection;
  * the new ENEMY PROBES and WEAPON GEOMETRY board blocks;
  * the KEYSTONE collision channel — view recap -> collision-aware LAST NIGHT
    and REFLECT blocks that name the loss as LOST (not "held");
  * doctrine gating (redsign-poker rides with redsign; weapons-orbital rides
    with any live weapon threat).
"""

from __future__ import annotations

from types import SimpleNamespace

from sea_of_colours.orchestrator_2.harnesses.tabula_v8 import (
    doctrine,
    prompt as prompt_mod,
)
from sea_of_colours.snowpark import view as view_mod


def _view(width=20, height=20, **extra):
    base = {
        "world": {"width": width, "height": height, "live": []},
        "entities": {"mine": []},
        "my_assets": [],
        "red_tiles": [],
    }
    base.update(extra)
    return base


def _kwargs(**over):
    base = dict(
        agent_view=_view(),
        day=3, day_cap=7, vault_score=100,
        memory_replay="(none)\n",
        chain_hints=[],
    )
    base.update(over)
    return base


# ── section scaffold + contracts ───────────────────────────────────────
def test_three_pillar_sections_present_and_ordered():
    text = prompt_mod.build_prompt(mode="mover", **_kwargs())
    i1 = text.find("SECTION 1 - THE GAME")
    i2 = text.find("SECTION 2 - THE BOARD NOW")
    i3 = text.find("SECTION 3 - WHAT HAPPENED LAST NIGHT")
    assert -1 < i1 < i2 < i3, (i1, i2, i3)


def test_thinker_mode_reasoning_first_contract():
    text = prompt_mod.build_prompt(mode="thinker", **_kwargs())
    assert '"reasoning"' in text
    assert "OUTPUT THE JSON OBJECT NOW" not in text
    assert "reasoning\" FIRST" in text


def test_mover_mode_injects_directive_and_keeps_contract():
    text = prompt_mod.build_prompt(
        mode="mover",
        strategist_directive_block="STRATEGIST DIRECTIVE\nposture: defensive\n",
        **_kwargs(),
    )
    assert "STRATEGIST DIRECTIVE" in text
    assert "OUTPUT THE JSON OBJECT NOW" in text


def test_mover_mode_without_directive_has_no_block():
    text = prompt_mod.build_prompt(mode="mover", **_kwargs())
    assert "STRATEGIST DIRECTIVE" not in text


# ── ENEMY PROBES block (§4c) ───────────────────────────────────────────
def test_enemy_probes_block_renders_public_launches():
    av = _view(competitor_intel={
        "new_this_day": [
            {"kind": "enemy_probe_launch", "at": [12, 8], "day_seen": 2},
        ],
    })
    block = prompt_mod.format_enemy_probes_block(av, day=3)
    assert "ENEMY PROBES" in block
    assert "(12,8)" in block
    assert "SUPERSEDE" in block


def test_enemy_probes_block_empty_when_none():
    assert prompt_mod.format_enemy_probes_block(_view(), day=3) == ""


# ── WEAPON GEOMETRY block (§4d) ────────────────────────────────────────
def test_weapon_geometry_renders_when_armed():
    est = {"p2": SimpleNamespace(emps_max=3, chaff_max=0)}
    block = prompt_mod.format_weapon_geometry_block(est)
    assert "WEAPON GEOMETRY" in block
    assert "EMP" in block and "CHAFF" in block


def test_weapon_geometry_empty_when_unarmed():
    est = {"p2": SimpleNamespace(emps_max=0, chaff_max=0)}
    assert prompt_mod.format_weapon_geometry_block(est) == ""
    assert prompt_mod.format_weapon_geometry_block(None) == ""


# ── KEYSTONE: collision channel ────────────────────────────────────────
def _fake_session(*, day, collisions):
    """Minimal duck-typed GameSession for _last_night_recap."""
    marks = {}
    for at, owners in collisions:
        marks[f"{at[0]}:{at[1]}"] = {"day": day - 1, "owners": owners}
    return SimpleNamespace(
        day=day,
        asset_records={},
        harvest_log={},
        combat_events_by_day={},
        collision_marks=marks,
    )


def test_view_recap_surfaces_my_collisions_self_party_only():
    sess = _fake_session(
        day=4,
        collisions=[([2, 9], ["p1", "p2", "p3"]), ([30, 5], ["p2", "p3"])],
    )
    recap = view_mod._last_night_recap(sess, "p1", [])
    cols = recap["my_collisions"]
    assert len(cols) == 1  # the (30,5) pile-up excludes p1
    assert cols[0]["at"] == [2, 9]
    assert set(cols[0]["others"]) == {"p2", "p3"}
    assert cols[0]["party_count"] == 3


def test_view_recap_ignores_stale_day_collisions():
    sess = _fake_session(day=4, collisions=[])
    sess.collision_marks = {"2:9": {"day": 1, "owners": ["p1", "p2"]}}
    recap = view_mod._last_night_recap(sess, "p1", [])
    assert recap["my_collisions"] == []


def test_last_night_block_names_collision_as_lost():
    av = _view(last_night={
        "day_ended": 3,
        "my_orders": [], "my_assets_destroyed": [],
        "my_parcels_banked": [], "combat_events": [],
        "my_collisions": [{"at": [2, 9], "others": ["p2", "p3"], "party_count": 3}],
    })
    block = prompt_mod.format_last_night_block(av)
    assert "COLLIDED at [2,9]" in block
    assert "0 cargo" in block
    assert "NOT held in hoard" in block


def test_reflect_block_forces_collision_loss_framing():
    av = _view(last_night={
        "day_ended": 3, "my_collisions": [
            {"at": [2, 9], "others": ["p2"], "party_count": 2},
        ],
    })
    block = prompt_mod.format_reflect_block(av, None, day=4)
    assert "COLLISION LOSS" in block
    assert "LOST, not held" in block
    assert "OFFSET" in block


def test_reflect_block_no_collision_defers_to_v7():
    av = _view(last_night={"day_ended": 3, "my_collisions": []})
    block = prompt_mod.format_reflect_block(av, None, day=4)
    assert "COLLISION LOSS" not in block


# ── doctrine gating ────────────────────────────────────────────────────
def test_redsign_poker_rides_with_redsign():
    av = _view(redsign=[{"center": [2, 13], "cells": [[2, 13, 1.0]]}])
    text = prompt_mod.build_prompt(mode="thinker", **_kwargs(agent_view=av))
    assert "REDSIGN POKER" in text
    assert "HONEYPOT" in text


def test_no_redsign_no_poker():
    text = prompt_mod.build_prompt(mode="thinker", **_kwargs())
    assert "REDSIGN POKER" not in text


def test_weapons_orbital_rides_with_live_jam():
    av = _view(last_night={
        "day_ended": 2,
        "combat_events": [{"type": "chaff_jam", "victim": "p1", "hours": [6, 7, 8]}],
    })
    text = prompt_mod.build_prompt(mode="mover", **_kwargs(agent_view=av))
    assert "ORBITAL strikes" in text
    assert doctrine.DOCTRINE_BEWARE_CHAFF.split("\n", 1)[0] in text
