"""Offline structural tests for the PILOT_V4 two-phase harness.

No network. A ``FakeInvoker`` stands in for Cortex so we exercise every
harness stage deterministically:

* compiler shape + STATE splicing (incl. redsign / blue_sign the envelope
  drops).
* tactician JSON parsing (valid / fenced / prose-wrapped / garbage).
* candidate lookup (exact + prefix ids).
* trim keeps the terminal pickup.
* pickup invariant repairs deployed AND newly-dropped harvesters, and
  respects the 21-slot cap.
* planning materialization: selections → moves, illegal verb → fallback,
  unknown id skip, empty → fallback.
* orbit option flattening + materialization.
* run() end-to-end for BOTH planning and orbit with a mocked submit.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from sea_of_colours.orchestrator_2.harnesses.pilot_v4 import candidates as cc
from sea_of_colours.orchestrator_2.harnesses.pilot_v4 import memory as mem
from sea_of_colours.orchestrator_2.harnesses.pilot_v4 import rival_arsenal as arsenal
from sea_of_colours.orchestrator_2.harnesses.pilot_v4 import harness as h


@pytest.fixture(autouse=True)
def _clear_cache():
    mem.reset_for_tests()
    arsenal.reset_for_tests()
    yield
    mem.reset_for_tests()
    arsenal.reset_for_tests()


def _grid(w, ht):
    return [[{"tile": "EMPTY"} for _ in range(w)] for _ in range(ht)]


def _harv(unit="harvester_p1", state="orbit", at=None):
    return {"id": unit, "kind": "harvester", "type": "harvester",
            "state": state, "at": at, "pos": at, "damaged": False}


def _view(*, day=2, width=14, height=9, grid=None, my_assets=None,
          red_visible=None, redsign=None, blue_sign=None):
    if grid is None:
        grid = [[None for _ in range(width)] for _ in range(height)]
    return {
        "meta": {"session_id": "T", "season": "S", "player": "p1", "day": day,
                 "policy_actions_left": 21, "policy_actions_max": 21,
                 "rules": {"probe_radius": 4, "probe_lifetime_nights": 3}},
        "hud": {"score": 0, "scores": {"p1": 0, "p2": 0}, "season_day_cap": 7,
                "hoard": {"used": 0, "max": 15, "free": 15,
                          "by_tier": {"GREEN": {}, "RED": {}, "BLUE": {}}, "warning": None},
                "shipped": {"used": 0, "max": None,
                            "by_tier": {"GREEN": {}, "RED": {}, "BLUE": {}}}},
        "last_night": {"day_ended": max(0, day - 1), "my_orders": [],
                       "my_assets_destroyed": [], "my_parcels_banked": []},
        "competitor_intel": {"new_this_day": [], "persistent_echoes": []},
        "world": {"width": width, "height": height, "grid": grid},
        "navigation": {"best_red_visible": red_visible or [], "best_red_echo": [],
                       "best_blue": [], "fog_clusters": []},
        "my_assets": my_assets or [],
        "red_tiles": red_visible or [], "green_tiles": [], "blue_tiles": [],
        "fog_clusters": [], "entities": {"mine": my_assets or [], "echoes": []},
        "redsign": redsign or [], "blue_sign": blue_sign or [],
    }


# ── compiler + splicing ──────────────────────────────────────────────
def test_compile_candidates_shape():
    out = cc.compile_candidates(_view())
    assert set(out.keys()) == {"candidates", "threat", "memory_summary", "combat", "orbital"}


def test_splice_state_injects_menu_and_signals():
    view = {"phase": "planning", "agent_view": _view(
        my_assets=[_harv()],
        redsign=[{"id": "rs1", "center": [5, 5]}],
        blue_sign=[{"id": "bs1", "center": [2, 2]}],
    )}
    body, extras = h._splice_state("SESS", view, is_orbit=False)
    assert "CALL soc_submit_policy" not in body
    i = body.find("STATE (JSON):\n```json\n") + len("STATE (JSON):\n```json\n")
    j = body.find("\n```\n", i)
    payload = json.loads(body[i:j])
    for k in ("candidates", "threat", "combat", "memory_summary",
              "redsign", "blue_sign", "meta", "world", "my_assets"):
        assert k in payload, f"missing {k}"
    assert payload["redsign"] == [{"id": "rs1", "center": [5, 5]}]
    assert payload["blue_sign"] == [{"id": "bs1", "center": [2, 2]}]


def test_splice_state_orbit_injects_orbital():
    view = {"phase": "orbit", "agent_view": _view(my_assets=[_harv()])}
    body, extras = h._splice_state("SESS", view, is_orbit=True)
    assert "orbital" in extras
    i = body.find("STATE (JSON):\n```json\n") + len("STATE (JSON):\n```json\n")
    j = body.find("\n```\n", i)
    payload = json.loads(body[i:j])
    assert "orbital" in payload


# ── tactician JSON parsing ───────────────────────────────────────────
def test_parse_json_plain():
    d, err = h._extract_decision_json('{"plan":"harvest_mixed","selections":[{"id":"H0"}],"rationale":"x"}')
    assert err is None and d["selections"] == [{"id": "H0"}]


def test_parse_json_fenced():
    d, err = h._extract_decision_json('```json\n{"plan":"p","selections":[{"id":"P0"}]}\n```')
    assert err is None and d["selections"][0]["id"] == "P0"


def test_parse_json_prose_wrapped():
    d, err = h._extract_decision_json('Here is my pick: {"plan":"p","selections":[{"id":"H1"}]} done.')
    assert err is None and d["selections"][0]["id"] == "H1"


def test_parse_json_garbage():
    d, err = h._extract_decision_json("I think we should harvest a lot this turn.")
    assert err == "no_json_object" and d == {}


# ── candidate lookup + trim ──────────────────────────────────────────
def _cands():
    return {
        "recommended_policy": {"moves": [{"a": "probe", "at": [1, 1]}]},
        "harvest": [{"id": "H0_harvester_p1", "unit": "harvester_p1",
                     "moves": [{"a": "drop", "unit": "harvester_p1", "at": [3, 3]},
                               {"a": "step", "unit": "harvester_p1", "to": [4, 3]},
                               {"a": "step", "unit": "harvester_p1", "to": [5, 3]},
                               {"a": "pickup", "unit": "harvester_p1"}]}],
        "probes": [{"id": "P0", "moves": [{"a": "probe", "at": [7, 7]}]}],
    }


def test_find_candidate_prefix():
    assert h._find_candidate(_cands(), "H0")["id"] == "H0_harvester_p1"
    assert h._find_candidate(_cands(), "P0")["id"] == "P0"
    assert h._find_candidate(_cands(), "ZZ9") is None


def test_trim_preserves_pickup():
    moves = _cands()["harvest"][0]["moves"]
    trimmed = h._trim_candidate_moves(moves, trim_to=2)
    assert trimmed[-1]["a"] == "pickup", "trim must keep terminal pickup"
    assert len(trimmed) == 3  # drop, step, + preserved pickup


def test_trim_noop_when_large():
    moves = _cands()["harvest"][0]["moves"]
    assert h._trim_candidate_moves(moves, trim_to=99) == moves


# ── pickup invariant ─────────────────────────────────────────────────
def test_pickup_invariant_repairs_deployed_harvester():
    av = _view(my_assets=[_harv(unit="hA", state="deployed")])
    moves, repaired = h._enforce_pickup_invariant([{"a": "probe", "at": [1, 1]}], av)
    assert repaired == ["hA"]
    assert {"a": "pickup", "unit": "hA"} in moves


def test_pickup_invariant_repairs_dropped_harvester():
    av = _view(my_assets=[])
    moves, repaired = h._enforce_pickup_invariant(
        [{"a": "drop", "unit": "hB", "at": [2, 2]}], av)
    assert repaired == ["hB"]
    assert {"a": "pickup", "unit": "hB"} in moves


def test_pickup_invariant_noop_when_already_present():
    av = _view(my_assets=[_harv(unit="hC", state="deployed")])
    moves, repaired = h._enforce_pickup_invariant([{"a": "pickup", "unit": "hC"}], av)
    assert repaired == []


def test_pickup_invariant_respects_slot_cap():
    av = _view(my_assets=[_harv(unit="hD", state="deployed")])
    full = [{"a": "probe", "at": [i, 0]} for i in range(h.MAX_MOVES)]
    moves, repaired = h._enforce_pickup_invariant(full, av)
    assert len(moves) == h.MAX_MOVES  # cannot exceed cap
    assert repaired == []


# ── planning materialization ─────────────────────────────────────────
def test_materialize_planning_picks_and_orders():
    compiled = {"candidates": _cands()}
    av = _view(my_assets=[_harv(unit="harvester_p1", state="orbit")])
    moves, info = h._materialize_planning(
        decision={"selections": [{"id": "P0"}, {"id": "H0"}]},
        expected_seat="p1", compiled=compiled, agent_view=av)
    assert info["fallback_used"] is False
    assert moves[0]["a"] == "probe"  # P0 ordered first
    assert any(m["a"] == "drop" for m in moves)
    assert moves[-1]["a"] == "pickup"


def test_materialize_planning_trim_frees_slots():
    compiled = {"candidates": _cands()}
    av = _view(my_assets=[_harv(unit="harvester_p1", state="orbit")])
    moves, info = h._materialize_planning(
        decision={"selections": [{"id": "H0", "trim_to": 2}]},
        expected_seat="p1", compiled=compiled, agent_view=av)
    # trimmed to drop+step then pickup preserved
    assert [m["a"] for m in moves] == ["drop", "step", "pickup"]
    assert info["trimmed"] == [{"id": "H0_harvester_p1", "trim_to": 2}]


def test_materialize_planning_illegal_verb_falls_back():
    compiled = {"candidates": {
        "recommended_policy": {"moves": [{"a": "probe", "at": [0, 0]}]},
        "harvest": [{"id": "BAD", "moves": [{"a": "self_destruct", "unit": "x"}]}],
    }}
    moves, info = h._materialize_planning(
        decision={"selections": [{"id": "BAD"}]},
        expected_seat="p1", compiled=compiled, agent_view=_view())
    assert info["fallback_used"] is True
    assert info["fallback_reason"].startswith("illegal_verb")
    assert moves == [{"a": "probe", "at": [0, 0]}]


def test_materialize_planning_skips_second_chain_for_same_harvester():
    """H0/H1 are alternative chains for the SAME unit — only one is kept."""
    compiled = {"candidates": {
        "recommended_policy": {"moves": []},
        "harvest": [
            {"id": "H0_harvester_p1", "unit": "harvester_p1",
             "moves": [{"a": "drop", "unit": "harvester_p1", "at": [3, 3]},
                       {"a": "pickup", "unit": "harvester_p1"}]},
            {"id": "H1_harvester_p1", "unit": "harvester_p1",
             "moves": [{"a": "drop", "unit": "harvester_p1", "at": [9, 9]},
                       {"a": "pickup", "unit": "harvester_p1"}]},
        ],
    }}
    av = _view(my_assets=[_harv(unit="harvester_p1", state="orbit")])
    moves, info = h._materialize_planning(
        decision={"selections": [{"id": "H0"}, {"id": "H1"}]},
        expected_seat="p1", compiled=compiled, agent_view=av)
    drops = [m for m in moves if m["a"] == "drop"]
    assert len(drops) == 1, "same harvester must be dropped at most once"
    assert info["skipped_conflicts"] == ["H1_harvester_p1"]
    assert info["fallback_used"] is False


def test_materialize_planning_unknown_id_skipped_then_fallback():
    compiled = {"candidates": {"recommended_policy": {"moves": [{"a": "probe", "at": [0, 0]}]}}}
    moves, info = h._materialize_planning(
        decision={"selections": [{"id": "NOPE"}]},
        expected_seat="p1", compiled=compiled, agent_view=_view())
    assert info["fallback_used"] is True
    assert info["fallback_reason"] == "no_valid_selections"


def test_materialize_planning_empty_selections_falls_back():
    compiled = {"candidates": {"recommended_policy": {"moves": [{"a": "probe", "at": [0, 0]}]}}}
    moves, info = h._materialize_planning(
        decision={"selections": []}, expected_seat="p1",
        compiled=compiled, agent_view=_view())
    assert info["fallback_reason"] == "no_selections"


# ── orbit ────────────────────────────────────────────────────────────
def _orbital():
    return {
        "recommended_orbit_policy": {"actions": [{"a": "refine", "source_tier": "trace"}]},
        "play_enablers": {
            "repair_candidates": [{"action": {"a": "repair", "unit": "h1"}}],
            "harvester_purchase": {"action": {"a": "build_harvester", "count": 1}},
            "probe_purchase": {"action": {"a": "build_probe", "count": 1}},
        },
        "vault_pressure": {"ship": {"action": {"a": "ship_catapult", "parcel": "p1"}},
                           "refine": {"options": [{"action": {"a": "refine", "source_tier": "vein"}}]}},
        "offensive_blue": {"emp_purchase": {"action": {"a": "build_emp"}}},
        "max_actions": 5, "trivial": False,
    }


def test_flatten_orbit_options_assigns_ids_and_dedups():
    opts = h._flatten_orbit_options(_orbital())
    ids = [o["id"] for o in opts]
    assert ids[0] == "O0" and len(ids) == len(set(ids))
    labels = {o["label"] for o in opts}
    assert {"doctrine", "repair", "build_harvester", "ship_red"}.issubset(labels)


def test_materialize_orbit_picks_options():
    orbital = _orbital()
    opts = h._flatten_orbit_options(orbital)
    build_h = next(o["id"] for o in opts if o["label"] == "build_harvester")
    repair = next(o["id"] for o in opts if o["label"] == "repair")
    actions, info = h._materialize_orbit(
        decision={"selections": [{"id": repair}, {"id": build_h}]},
        orbital=orbital, options=opts)
    assert info["fallback_used"] is False
    assert [a["a"] for a in actions] == ["repair", "build_harvester"]


def test_materialize_orbit_recommended():
    orbital = _orbital()
    opts = h._flatten_orbit_options(orbital)
    actions, info = h._materialize_orbit(
        decision={"selections": [{"id": "recommended_orbit_policy"}]},
        orbital=orbital, options=opts)
    assert actions == [{"a": "refine", "source_tier": "trace"}]


def test_materialize_orbit_respects_cap():
    orbital = _orbital()
    orbital["max_actions"] = 2
    opts = h._flatten_orbit_options(orbital)
    sel = [{"id": o["id"]} for o in opts]
    actions, info = h._materialize_orbit(decision={"selections": sel}, orbital=orbital, options=opts)
    assert len(actions) <= 2


# ── interdiction surfacing (doctrine-gap fixes) ──────────────────────
def test_orbit_options_include_chaff_and_mine():
    orbital = _orbital()
    orbital["offensive_blue"] = {
        "emp_purchase": {"action": {"a": "build_emp"}},
        "chaff_purchase": {"action": {"a": "build_chaff"}},
        "mine_purchase": {"action": {"a": "build_mine"}},
    }
    labels = {o["label"] for o in h._flatten_orbit_options(orbital)}
    assert {"build_emp", "build_chaff", "build_mine"}.issubset(labels)


def test_tactician_menu_includes_combat_block():
    compiled = {"candidates": _cands(), "combat": {"emp_mechanics": {"cost_blue_purity": 250, "radius_chebyshev": 1}},
                "threat": {}}
    menu = h._tactician_menu(compiled)
    assert "combat" in menu
    assert "emp_mechanics" in menu


def test_summarize_emp_candidate_surfaces_can_fire_and_effect():
    cand = {
        "id": "EMP0", "kind": "emp_launch", "score": 42.0,
        "moves": [{"a": "emp_launch", "at": [[3, 3]]}],
        "affordability": {"can_fire": True},
        "expected_effect": {"enemy_unit_count": 2, "self_freeze_unit_count": 0},
    }
    out = h._summarize_candidate(cand)
    assert out["can_fire"] is True
    assert out["enemy_hit"] == 2
    assert out["self_freeze"] == 0


def test_strategist_brief_surfaces_interdiction_and_emp():
    cands = {
        "harvest": [{"id": "H0", "score": 100, "tier": "mass"}],
        "probes": [],
        "hot_drop": [{"id": "HOT0"}],
        "harvester_crush": [{"id": "CR0"}],
        "probe_supersede": [{"id": "SUP0"}],
        "drop_block": [],
        "emp_launch": [{"id": "EMP0", "score": 42.0,
                        "affordability": {"can_fire": True},
                        "expected_effect": {"enemy_unit_count": 1, "self_freeze_unit_count": 0}}],
    }
    combat = {"my_blue_purity_available": 250,
              "emp_mechanics": {"cost_blue_purity": 250, "cost_credits": 40,
                                "radius_chebyshev": 1, "cloud_hours": 4}}
    view = {"agent_view": _view(my_assets=[_harv()])}
    body = h._strategist_brief(view, {"candidates": cands, "combat": combat}, is_orbit=False)
    assert "interdiction" in body
    assert "hot_drop" in body
    # emp block carries can_fire + cost + radius so the strategist can reason
    assert '"can_fire":true' in body
    assert '"cost_blue":250' in body
    assert '"radius":1' in body


# ── rival arsenal tracker ────────────────────────────────────────────
def _view_with_station(seat="p1", day=3, opp_band=3, opp_grade="high",
                       combat_events=None):
    v = _view(day=day)
    v["station_intel"] = {
        "self": {"seat": seat, "blue": {"band": 0, "grade": "none"}},
        "opponents": [{"seat": "p2",
                       "blue": {"band": opp_band, "grade": opp_grade},
                       "fullness": {"grade": "half"},
                       "activity": {"dropped": 1, "picked_up": 1}}],
        "night_day": day - 1,
    }
    v["last_night"] = {"day_ended": day - 1, "combat_events": combat_events or [],
                       "my_orders": [], "my_assets_destroyed": [], "my_parcels_banked": []}
    return v


def test_arsenal_records_band_and_flags_chaff_capable():
    v = _view_with_station(day=2, opp_band=3, opp_grade="high")  # 450+ blue
    summary = arsenal.update_and_summarize("S1", v)
    assert len(summary["opponents"]) == 1
    op = summary["opponents"][0]
    assert op["seat"] == "p2"
    assert op["blue_band_now"] == 3
    assert op["chaff_capable_now"] is True
    assert op["emp_capable_now"] is True
    assert op["built_weapon_last_orbit"] is False  # first snapshot, no history


def test_arsenal_detects_band_drop_as_built_weapon():
    # Turn 1: rival at band 3 (high).
    arsenal.update_and_summarize("S2", _view_with_station(day=2, opp_band=3))
    # Turn 2: rival at band 1 (medium/low, spent ~2 pips ~= 300+ blue).
    summary = arsenal.update_and_summarize("S2", _view_with_station(day=3, opp_band=1, opp_grade="medium"))
    op = summary["opponents"][0]
    assert op["blue_band_delta"] == -2
    assert op["built_weapon_last_orbit"] is True
    assert op["likely_weapon_built"] == "chaff"  # 2-pip drop is chaff


def test_arsenal_one_pip_drop_defaults_to_emp():
    arsenal.update_and_summarize("S3", _view_with_station(day=2, opp_band=2))
    summary = arsenal.update_and_summarize("S3", _view_with_station(day=3, opp_band=1))
    op = summary["opponents"][0]
    assert op["likely_weapon_built"] == "emp"


def test_arsenal_ingests_public_chaff_flare_event():
    # Rival fired a chaff at hour 6 last Nox — public event.
    summary = arsenal.update_and_summarize("S4", _view_with_station(
        day=5, opp_band=1,
        combat_events=[{"type": "chaff", "owner": "p2", "hour": 6}]))
    op = summary["opponents"][0]
    fired = op["weapons_fired_last_nox"]
    assert len(fired) == 1 and fired[0]["kind"] == "chaff" and fired[0]["hour"] == 6


def test_arsenal_stock_decrements_on_observed_firing():
    # Build a chaff (band 3 → 1) then fire it — stock should end at 0.
    arsenal.update_and_summarize("S5", _view_with_station(day=2, opp_band=3))
    arsenal.update_and_summarize("S5", _view_with_station(day=3, opp_band=1))
    summary = arsenal.update_and_summarize("S5", _view_with_station(
        day=4, opp_band=1,
        combat_events=[{"type": "chaff", "owner": "p2", "hour": 6}]))
    op = summary["opponents"][0]
    # chaff_built (1 from day-3 drop) - chaff_fired (1 observed) = 0
    assert op["estimated_stock"]["chaff"] == 0


def test_arsenal_ignores_own_events():
    # If the "rival" event is us, don't record it against a rival.
    summary = arsenal.update_and_summarize("S6", _view_with_station(
        day=5, opp_band=1,
        combat_events=[{"type": "chaff", "owner": "p1", "hour": 6}]))
    op = summary["opponents"][0]
    assert op["weapons_fired_last_nox"] == []


def test_strategist_brief_carries_arsenal_when_provided():
    v = {"agent_view": _view(my_assets=[_harv()])}
    body = h._strategist_brief(
        v, {"candidates": {"harvest": [], "probes": []}, "combat": {}},
        is_orbit=False,
        arsenal_summary={"opponents": [{"seat": "p2", "chaff_capable_now": True}]})
    assert "arsenal" in body
    assert "chaff_capable_now" in body


# ── contested-drop risk scoring ──────────────────────────────────────
def test_risk_score_low_when_rival_dark():
    cand = {"id": "H0", "threat_cost": 0.2, "cells_traversed": [[5, 5]]}
    arsenal_sum = {"opponents": [{"seat": "p2",
                                   "emp_capable_now": False,
                                   "chaff_capable_now": False,
                                   "estimated_stock": {"emp": 0, "chaff": 0}}]}
    r = arsenal.score_candidate_risk(cand, arsenal_sum, redsign_present=False)
    assert r["emp_risk"] < 0.2
    assert r["chaff_risk"] < 0.2
    assert r["hedges"] == []


def test_risk_score_high_when_rival_capable_and_telegraphed():
    cand = {"id": "H0", "threat_cost": 4.0, "cells_traversed": [[5, 5]]}
    arsenal_sum = {"opponents": [{"seat": "p2",
                                   "emp_capable_now": True,
                                   "chaff_capable_now": True,
                                   "estimated_stock": {"emp": 1, "chaff": 1},
                                   "built_weapon_last_orbit": True,
                                   "likely_weapon_built": "emp"}]}
    r = arsenal.score_candidate_risk(cand, arsenal_sum, redsign_present=True)
    assert r["emp_risk"] >= 0.5
    assert r["chaff_risk"] >= 0.5
    assert "short_chain_trim_to_4" in r["hedges"]
    assert "late_deploy_after_cloud" in r["hedges"]


def test_risk_score_contested_pure_adds_own_chaff_hedge():
    cand = {"id": "H0", "threat_cost": 3.0, "cells_traversed": [[5, 5]]}
    arsenal_sum = {"opponents": [{"seat": "p2",
                                   "emp_capable_now": True,
                                   "chaff_capable_now": False,
                                   "estimated_stock": {"emp": 0, "chaff": 0}}]}
    r = arsenal.score_candidate_risk(cand, arsenal_sum,
                                      redsign_present=True,
                                      redsign_cells=[[5, 5]])
    assert r["contested_pure"] is True
    assert "consider_own_chaff_to_deny_rival_pickup" in r["hedges"]


def test_risk_score_picks_worst_rival_across_opponents():
    cand = {"id": "H0", "threat_cost": 3.0, "cells_traversed": [[5, 5]]}
    arsenal_sum = {"opponents": [
        {"seat": "p2", "emp_capable_now": False, "chaff_capable_now": False,
         "estimated_stock": {"emp": 0, "chaff": 0}},
        {"seat": "p3", "emp_capable_now": True, "chaff_capable_now": True,
         "estimated_stock": {"emp": 2, "chaff": 1}},
    ]}
    r = arsenal.score_candidate_risk(cand, arsenal_sum, redsign_present=False)
    # Should be dominated by p3 (the capable rival).
    assert r["emp_risk"] >= 0.5


# ── harvester utilisation telemetry ──────────────────────────────────
def test_harvester_util_marks_idle_when_no_drop_last_nox():
    av = _view(my_assets=[_harv(unit="harvester_p1", state="orbit"),
                          _harv(unit="harvester_p1_2", state="orbit")])
    av["last_night"] = {"my_orders": [
        {"text": "p1 dropped harvester_p1 at (5, 5)", "outcome": "ok"},
    ]}
    util = arsenal.harvester_utilization(av)
    assert util["harvesters_alive"] == 2
    assert util["wasted_units_last_nox"] == 1
    used_map = {u["unit"]: u["used_last_nox"] for u in util["per_unit"]}
    assert used_map["harvester_p1"] is True
    assert used_map["harvester_p1_2"] is False


def test_harvester_util_all_used_when_all_dropped():
    av = _view(my_assets=[_harv(unit="harvester_p1"),
                          _harv(unit="harvester_p1_2"),
                          _harv(unit="harvester_p1_3")])
    av["last_night"] = {"my_orders": [
        {"text": "p1 dropped harvester_p1 at (1, 1)"},
        {"text": "p1 dropped harvester_p1_2 at (2, 2)"},
        {"text": "p1 dropped harvester_p1_3 at (3, 3)"},
    ]}
    util = arsenal.harvester_utilization(av)
    assert util["wasted_units_last_nox"] == 0


def test_strategist_brief_planning_includes_risk_and_core_loop():
    view = {"agent_view": _view(my_assets=[_harv()],
                                 red_visible=[{"x": 5, "y": 5, "value": 200,
                                                "tier": "mass", "freshness": "fresh"}])}
    extras = {
        "candidates": {
            "harvest": [{"id": "H0", "score": 100, "tier": "mass",
                          "score_breakdown": {"threat_cost": 3.5,
                                              "chain_survival_prob": 0.6}}],
            "probes": [], "hot_drop": [], "harvester_crush": [],
            "probe_supersede": [], "drop_block": [], "emp_launch": [],
        },
        "combat": {"my_blue_purity_available": 250,
                    "emp_mechanics": {"cost_blue_purity": 200, "cost_credits": 250,
                                       "radius_chebyshev": 2, "cloud_hours": 8}},
    }
    arsenal_summary = {"opponents": [{"seat": "p2", "chaff_capable_now": True,
                                       "emp_capable_now": True,
                                       "estimated_stock": {"emp": 1, "chaff": 0}}]}
    body = h._strategist_brief(view, extras, is_orbit=False,
                                arsenal_summary=arsenal_summary)
    assert "top_harvest" in body
    # per-candidate risk block is spliced
    assert "emp_risk" in body
    assert "hedges" in body
    # core-loop status is present so strategist sees utilisation
    assert "core_loop" in body
    assert "wasted_units_last_nox" in body


# ── strategist parsing ───────────────────────────────────────────────
def test_parse_strategist_plan_and_compact():
    raw = ("Some reasoning here.\nDIAGNOSIS: day 3/7 behind\nPLAN: harvest_pure\n"
           "INTENT: chase the redsign core for a 765-pt parcel\nPRIORITIES: H0, H1")
    assert h._parse_strategist_plan(raw) == "harvest_pure"
    note = h._compact_strategist_note(raw)
    assert "PLAN: harvest_pure" in note
    assert "redsign" in note
    assert "H0, H1" in note


def test_compact_strategist_defaults_on_missing():
    note = h._compact_strategist_note("no structure at all")
    assert "PLAN: harvest_mixed" in note


# ── run() end to end (mocked Cortex + submit) ────────────────────────
class _FakeInvoker:
    strat_response = "DIAGNOSIS: d\nPLAN: harvest_mixed\nINTENT: bank vein\nPRIORITIES: H0"
    tact_response = '{"plan":"harvest_mixed","selections":[{"id":"recommended_policy"}],"rationale":"x"}'

    def __init__(self, *, agent_name):
        self.agent_name = agent_name

    def is_ready(self):
        return True

    def invoke(self, prompt, **kwargs):
        if "STRATEGIST" in self.agent_name:
            return {"ok": True, "response": self.strat_response, "elapsed_ms": 10}
        return {"ok": True, "response": self.tact_response, "elapsed_ms": 20, "tool_calls": []}


def test_run_planning_submits(monkeypatch):
    view = {"phase": "planning", "agent_view": _view(my_assets=[_harv()])}
    with patch.object(h, "CortexAgentInvoker", _FakeInvoker), \
         patch("sea_of_colours.snowpark.engine.submit_policy") as submit:
        submit.return_value = {"ok": True}
        out = h.run(store=None, session_id="S", player="p1", view=view)
    assert out["submitted_policy"] is True
    assert out["extras"]["plan_label"] == "harvest_mixed"
    assert submit.call_args.args[2] == "p1"  # correct seat


def test_run_orbit_submits(monkeypatch):
    _FakeInvoker.tact_response = '{"plan":"vault_flush_orbit","selections":[{"id":"recommended_orbit_policy"}],"rationale":"x"}'
    view = {"phase": "orbit", "agent_view": _view(my_assets=[_harv()])}
    with patch.object(h, "CortexAgentInvoker", _FakeInvoker), \
         patch("sea_of_colours.snowpark.engine.submit_orbit_actions") as submit:
        submit.return_value = {"ok": True}
        out = h.run(store=None, session_id="S", player="p1", view=view)
    assert out["submitted_policy"] is True
    assert submit.called


def test_run_not_ready_returns_error(monkeypatch):
    class NotReady(_FakeInvoker):
        def is_ready(self):
            return False
    view = {"phase": "planning", "agent_view": _view()}
    with patch.object(h, "CortexAgentInvoker", NotReady):
        out = h.run(store=None, session_id="S", player="p1", view=view)
    assert out["ok"] is False
    assert "not ready" in (out["error"] or "").lower()


def test_run_tactician_garbage_falls_back_to_doctrine(monkeypatch):
    class Garbage(_FakeInvoker):
        def invoke(self, prompt, **kwargs):
            if "STRATEGIST" in self.agent_name:
                return {"ok": True, "response": self.strat_response, "elapsed_ms": 10}
            return {"ok": True, "response": "I cannot decide, sorry.", "elapsed_ms": 20, "tool_calls": []}
    view = {"phase": "planning", "agent_view": _view(my_assets=[_harv()])}
    with patch.object(h, "CortexAgentInvoker", Garbage), \
         patch("sea_of_colours.snowpark.engine.submit_policy") as submit:
        submit.return_value = {"ok": True}
        out = h.run(store=None, session_id="S", player="p1", view=view)
    assert out["submitted_policy"] is True
    assert out["extras"]["decision_error"] == "no_json_object"
    assert out["extras"]["decision_validation"]["fallback_used"] is True
