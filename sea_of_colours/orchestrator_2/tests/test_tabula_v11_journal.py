"""Tests for the v11 continuous STRATEGY JOURNAL.

Covers agent-authored intent/reflection capture from the plan JSON, the engine-
truth outcome/enemy summaries, prior-entry enrichment, the rendered journal
thread, and the journal-aware decision schema (adds intent/reflection while
keeping the decision fields leading + strict).
"""

from __future__ import annotations

from sea_of_colours.orchestrator_2.harnesses.tabula_v11 import (
    chat_schema,
    journal,
)


# ── capture intent + reflection from the plan JSON ───────────────────────────
def test_parse_intent_reflection_clean_object():
    txt = (
        '{"posture":"redsign_race","plan":["SMASH_GRAB"],'
        '"intent":"Race the north pure before p2.",'
        '"reflection":"Last night I lost a step at H09; tighten the walk.",'
        '"reasoning":"..."}'
    )
    intent, reflection = journal.parse_intent_reflection(txt)
    assert intent == "Race the north pure before p2."
    assert "H09" in reflection


def test_parse_intent_reflection_missing_fields():
    intent, reflection = journal.parse_intent_reflection('{"posture":"aggressive"}')
    assert intent == ""
    assert reflection == ""


def test_parse_intent_reflection_salvage_from_truncated_tail():
    # Unterminated JSON (reasoning tail clipped) — regex salvage still recovers
    # the earlier intent/reflection strings.
    txt = (
        '{"posture":"aggressive","intent":"Bank the east vein chain.",'
        '"reflection":"Chaff jammed my H12 pickup.","reasoning":"the seam is'
    )
    intent, reflection = journal.parse_intent_reflection(txt)
    assert intent == "Bank the east vein chain."
    assert "Chaff" in reflection


# ── engine-truth summaries ───────────────────────────────────────────────────
def _last_night_memory():
    return {
        "actual": {"red_pts": 206, "parcels": 5, "blue_fissile": 0,
                   "green_cells": 0, "red_tiers": {"vein": 5}},
        "execution_log": [
            {"kind": "own", "tag": "drop", "outcome": "ok"},
            {"kind": "own", "tag": "step", "outcome": "failed"},
            {"kind": "orbital", "tag": "probe", "outcome": "ok"},
        ],
        "what_you_saw": [
            "H02 p2 launched a probe (12,23) (public)",
            "H06 p2 moved a harvester seen (24,21) (in your vision)",
        ],
    }


def test_outcome_summary_counts_banked_and_failures():
    s = journal.outcome_summary(_last_night_memory())
    assert "banked red +206 (5 parcel(s))" in s
    assert "1 FAILED move(s)" in s


def test_enemy_summary_joins_seen_lines():
    s = journal.enemy_summary(_last_night_memory())
    assert "launched a probe" in s
    assert "(24,21)" in s


def test_enrich_prior_entry_folds_outcome_and_reflection():
    prior = {"day": 3, "intent": "Grab the north pure."}
    out = journal.enrich_prior_entry(
        prior, _last_night_memory(), reflection="Worked; tighten the walk.",
    )
    assert out is prior
    assert "banked red +206" in prior["happened"]
    assert "probe" in prior["enemy_seen"]
    assert prior["reflection"] == "Worked; tighten the walk."


def test_enrich_prior_entry_none_is_noop():
    assert journal.enrich_prior_entry(None, _last_night_memory()) is None


# ── render the continuous thread ─────────────────────────────────────────────
def test_render_journal_shows_full_thread_oldest_first():
    entries = [
        {"day": 2, "intent": "Scout west with two probes.",
         "happened": "banked red +0 (0 parcel(s))",
         "enemy_seen": "H03 p2 launched a probe (5,5) (public)",
         "reflection": "Too passive; commit a harvester next night."},
        {"day": 3, "intent": "Grab the north pure with SMASH_GRAB.",
         "happened": "banked red +206 (5 parcel(s)); 1 FAILED move(s)"},
    ]
    block = journal.render_journal(entries)
    assert "STRATEGY JOURNAL" in block
    # Oldest first.
    assert block.index("Day 2") < block.index("Day 3")
    assert 'Day 2 INTENT: "Scout west with two probes."' in block
    assert "REFLECT: \"Too passive" in block
    assert "banked red +206" in block


def test_render_journal_empty_prompts_first_intent():
    block = journal.render_journal([])
    assert "no prior nights" in block
    assert "first turn" in block


def test_render_journal_falls_back_to_plan_this_turn_for_intent():
    block = journal.render_journal([{"day": 1, "plan_this_turn": "aggressive: HD1"}])
    assert 'INTENT: "aggressive: HD1"' in block


# ── journal-aware decision schema ────────────────────────────────────────────
def test_v11_decision_schema_adds_intent_and_reflection():
    schema = chat_schema.DECISION_RESPONSE_FORMAT["json_schema"]["schema"]
    props = schema["properties"]
    assert "intent" in props and props["intent"] == {"type": "string"}
    assert "reflection" in props and props["reflection"] == {"type": "string"}
    # Decision still leads + strict + posture required (containment invariants).
    assert list(props).index("posture") < list(props).index("intent")
    assert list(props).index("intent") < list(props).index("reasoning")
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["posture"]
