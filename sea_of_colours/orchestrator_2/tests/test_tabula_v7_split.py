"""Unit tests for the v7 two-call reasoning split.

Covers the pieces that make the split safe and comparable to single-call v6:
  * directive parse (reasoning-first / DECISION-last), sanitize, and render;
  * the thinker completion predicate;
  * build_prompt's ``mode`` switch and strategist-directive injection.

The live two-call orchestration itself is exercised end-to-end by the season
runner; here we lock in the deterministic plumbing.
"""

from __future__ import annotations

from sea_of_colours.orchestrator_2.harnesses.tabula_v7 import (
    directive as dm,
    prompt as prompt_mod,
)


def _view(width=20, height=20):
    return {
        "world": {"width": width, "height": height, "live": []},
        "entities": {"mine": []},
        "my_assets": [],
        "red_tiles": [],
    }


# ── directive parsing ──────────────────────────────────────────────────
def test_parse_reasoning_first_decision_last():
    text = (
        "Let me think. Last night we banked less than predicted because a "
        "chaff jam cancelled the hour-5 pickup. The opponent still shows "
        "chaff stock, so I should play safe and pull pickups early.\n"
        'DECISION: {"posture":"defensive","targets":[[12,3],[14,5]],'
        '"chaff_react":true,"avoid":[[7,4]],"note":"chaff seen; short chains"}'
    )
    d = dm.parse_directive(text)
    assert d is not None
    assert d.posture == "defensive"
    assert d.targets == [(12, 3), (14, 5)]
    assert d.chaff_react is True
    assert d.avoid == [(7, 4)]
    assert "chaff" in d.note


def test_parse_takes_last_decision():
    text = (
        'I first thought DECISION: {"posture":"aggressive","targets":[]} '
        "but on reflection the beacon is worth racing.\n"
        'DECISION: {"posture":"redsign_race","targets":[[9,9]]}'
    )
    d = dm.parse_directive(text)
    assert d is not None
    assert d.posture == "redsign_race"
    assert d.targets == [(9, 9)]


def test_parse_none_when_no_decision():
    assert dm.parse_directive("just some reasoning, never decided") is None


def test_parse_none_on_malformed_json():
    assert dm.parse_directive('DECISION: {posture: not-json}') is None


# ── directive sanitize ─────────────────────────────────────────────────
def test_sanitize_clamps_targets_and_bounds():
    raw = dm.Directive(
        posture="defensive",
        targets=[(5, 5), (99, 99), (5, 5), (1, 1), (2, 2)],  # dup + OOB + >3
        chaff_react=True,
        avoid=[(-1, 0), (3, 3)],
        note="x",
    )
    d = dm.sanitize_directive(raw, _view(width=20, height=20))
    assert d is not None
    # (99,99) out of bounds dropped, dup removed, capped at 3
    assert d.targets == [(5, 5), (1, 1), (2, 2)]
    # (-1,0) out of bounds dropped
    assert d.avoid == [(3, 3)]


def test_sanitize_coerces_unknown_posture_to_default():
    raw = dm.Directive(posture="berserk", targets=[], chaff_react=False)
    d = dm.sanitize_directive(raw, _view())
    assert d.posture == "aggressive"


def test_sanitize_none_passes_through():
    assert dm.sanitize_directive(None, _view()) is None


# ── directive render ───────────────────────────────────────────────────
def test_format_block_contains_decision_fields():
    d = dm.Directive(
        posture="defensive", targets=[(12, 3)], chaff_react=True,
        avoid=[(7, 4)], note="short chains",
    )
    block = dm.format_directive_block(d)
    assert "STRATEGIST DIRECTIVE" in block
    assert "defensive" in block
    assert "(12,3)" in block
    assert "chaff_react: YES" in block
    assert "(7,4)" in block


def test_format_block_empty_when_none():
    assert dm.format_directive_block(None) == ""


# ── thinker completion predicate ───────────────────────────────────────
def test_predicate_true_only_after_decision():
    partial = "still reasoning about the board, no decision yet"
    assert dm.decision_line_complete(partial) is False
    full = partial + '\nDECISION: {"posture":"aggressive","targets":[]}'
    assert dm.decision_line_complete(full) is True


# ── build_prompt mode switch ───────────────────────────────────────────
def _common_kwargs():
    return dict(
        agent_view=_view(),
        day=3, day_cap=7, vault_score=100,
        memory_replay="(none)\n",
        chain_hints=[],
    )


def test_thinker_mode_emits_reasoning_first_contract_not_moves_schema():
    text = prompt_mod.build_prompt(mode="thinker", **_common_kwargs())
    # Contained-thinker contract: reasoning FIRST, then decision fields.
    assert '"reasoning"' in text
    assert "STRATEGIST" in text
    # The mover's closing instruction must NOT be present in thinker mode.
    assert "OUTPUT THE JSON OBJECT NOW" not in text


def test_mover_mode_injects_directive_block():
    d = dm.Directive(posture="defensive", targets=[(12, 3)], chaff_react=True)
    block = dm.format_directive_block(d)
    text = prompt_mod.build_prompt(
        mode="mover", strategist_directive_block=block, **_common_kwargs()
    )
    assert "STRATEGIST DIRECTIVE" in text
    assert "defensive" in text
    assert "OUTPUT THE JSON OBJECT NOW" in text  # mover contract intact


def test_mover_mode_without_directive_has_no_block():
    text = prompt_mod.build_prompt(mode="mover", **_common_kwargs())
    assert "STRATEGIST DIRECTIVE" not in text
