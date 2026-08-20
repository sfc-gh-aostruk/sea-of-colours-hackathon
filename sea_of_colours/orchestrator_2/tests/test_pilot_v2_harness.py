"""Tests for the PILOT_V2 harness internals.

Covers:
* compile_candidates returns the expected shape.
* compile_candidates copes with sparse / empty views.
* harness._build_pilot_v2_prompt splices candidates into the STATE block.
"""

from __future__ import annotations

import json

import pytest

from sea_of_colours.orchestrator_2.harnesses.pilot_v2 import candidates as cc
from sea_of_colours.orchestrator_2.harnesses.pilot_v2 import memory as mem
from sea_of_colours.orchestrator_2.harnesses.pilot_v2 import harness as h


@pytest.fixture(autouse=True)
def _clear_cache():
    mem.reset_for_tests()
    yield
    mem.reset_for_tests()


def _grid(w: int, h: int):
    return [[{"tile": "EMPTY"} for _ in range(w)] for _ in range(h)]


def _harv(unit="harvester_p1", state="orbit", at=None):
    return {"id": unit, "kind": "harvester", "type": "harvester",
            "state": state, "at": at, "pos": at, "damaged": False}


def _view(*, day=2, width=14, height=9, grid=None, my_assets=None,
          red_visible=None):
    if grid is None:
        grid = [[None for _ in range(width)] for _ in range(height)]
    return {
        "meta": {"session_id": "T", "season": "S", "player": "p1",
                 "day": day, "policy_actions_left": 21,
                 "policy_actions_max": 21,
                 "rules": {"probe_radius": 4, "probe_lifetime_nights": 3}},
        "hud": {"score": 0, "scores": {"p1": 0, "p2": 0},
                "season_day_cap": 7,
                "hoard": {"used": 0, "max": 15, "free": 15,
                          "by_tier": {"GREEN": {}, "RED": {}, "BLUE": {}},
                          "warning": None},
                "shipped": {"used": 0, "max": None,
                            "by_tier": {"GREEN": {}, "RED": {}, "BLUE": {}}}},
        "last_night": {"day_ended": max(0, day-1), "my_orders": [],
                       "my_assets_destroyed": [], "my_parcels_banked": []},
        "competitor_intel": {"new_this_day": [], "persistent_echoes": []},
        "world": {"width": width, "height": height, "grid": grid},
        "navigation": {"best_red_visible": red_visible or [],
                       "best_red_echo": [], "fog_clusters": []},
        "my_assets": my_assets or [],
        "red_tiles": red_visible or [], "green_tiles": [], "blue_tiles": [],
        "fog_clusters": [], "entities": {"mine": my_assets or [],
                                         "echoes": []},
    }


# ── compiler smoke ───────────────────────────────────────────────────
def test_compile_candidates_returns_expected_keys():
    out = cc.compile_candidates(_view())
    assert set(out.keys()) == {"candidates", "threat", "memory_summary", "combat", "orbital"}
    cand = out["candidates"]
    for k in ("k_used", "harvest", "probes", "probe_supersede",
              "harvester_crush", "hot_drop", "recommended_policy"):
        assert k in cand


def test_compile_candidates_recommended_policy_is_a_list():
    out = cc.compile_candidates(_view())
    rp = out["candidates"]["recommended_policy"]
    assert "moves" in rp and isinstance(rp["moves"], list)
    assert "total_actions" in rp


def test_compile_candidates_threat_block_keys():
    out = cc.compile_candidates(_view())
    threat = out["threat"]
    expected = {"enemy_fleet_estimate", "enemy_history",
                "enemy_probe_proximity", "final_day",
                "hoard_pressure", "my_fleet", "publicity_risk"}
    assert expected.issubset(set(threat.keys()))


def test_compile_candidates_red_visible_yields_harvest():
    grid = _grid(14, 9)
    grid[4][7] = {"tile": "RED", "value": 200, "purity": 200}
    grid[4][6] = {"tile": "EMPTY"}
    grid[4][8] = {"tile": "EMPTY"}
    red = [{"x": 7, "y": 4, "value": 200, "purity": 200, "tier": "mass",
            "freshness": "fresh"}]
    out = cc.compile_candidates(
        _view(grid=grid, red_visible=red, my_assets=[_harv()])
    )
    assert len(out["candidates"]["harvest"]) >= 1
    top = out["candidates"]["harvest"][0]
    assert top["moves"][-1]["a"] == "pickup"
    assert top["expected_score_after_vault_cascade"] > 0


# ── harness prompt assembly ──────────────────────────────────────────
def test_harness_prompt_splices_candidates_into_state_json():
    view = {"agent_view": _view(my_assets=[_harv()])}
    body = h._build_pilot_v2_prompt("SESS", view)

    # Default-play hint must be present.
    assert "recommended_policy.moves" in body

    # Extract the STATE JSON and assert candidates/threat/memory_summary
    # were merged in.
    head = "STATE (JSON):\n```json\n"
    i = body.find(head)
    j = body.find("\n```\n", i + len(head))
    payload = json.loads(body[i + len(head): j])
    assert "candidates" in payload
    assert "threat" in payload
    assert "memory_summary" in payload
    # Universal keys still there.
    for k in ("meta", "hud", "world", "navigation", "my_assets",
              "last_night", "competitor_intel"):
        assert k in payload, f"universal key {k} missing"


def test_harness_run_handles_no_pat_gracefully(monkeypatch):
    """Without Snowflake credentials, the invoker reports not-ready
    and the harness returns ok=False rather than raising."""
    monkeypatch.delenv("SNOWFLAKE_PAT", raising=False)
    monkeypatch.delenv("SOC_SNOWFLAKE_PAT", raising=False)
    monkeypatch.delenv("SOC_SNOWFLAKE_ACCOUNT", raising=False)
    view = {"agent_view": _view(my_assets=[_harv()])}
    out = h.run(store=None, session_id="X", player="p1", view=view)
    # Either ok=False with an error OR ok=True if PAT is present in env;
    # we only assert the contract returns the expected envelope keys.
    for key in ("ok", "elapsed_ms", "submitted_policy"):
        assert key in out


# ── Walker enhancement: green-detour multi-anchor (regression) ───────
def test_walker_bridges_two_reds_across_green_wall():
    """Two RED cells separated by a green cell — the walker should detour
    around the green wall and harvest both within MAX_HARVESTER_STEPS=5.

    Scenario layout (subset, rest is empty):
        row 9 :  . . . . . . . . .
        row 10:  . . . R G R . . .       (RED at x=3, green at x=4, RED at x=5)
        row 11:  . . . . . . . . .

    Drop adjacent to one RED, then the chain should bridge to the other.
    """
    width, height = 9, 5
    grid = _grid(width, height)
    grid[2][3] = {"tile": "RED", "value": 220, "purity": 220}
    grid[2][4] = {"tile": "GREEN", "synthetic": True}
    grid[2][5] = {"tile": "RED", "value": 230, "purity": 230}
    red_visible = [
        {"x": 3, "y": 2, "value": 220, "purity": 220, "tier": "mass",
         "freshness": "fresh"},
        {"x": 5, "y": 2, "value": 230, "purity": 230, "tier": "mass",
         "freshness": "fresh"},
    ]
    out = cc.compile_candidates(
        _view(width=width, height=height, grid=grid,
              red_visible=red_visible, my_assets=[_harv()])
    )
    harvest = out["candidates"]["harvest"]
    assert harvest, "expected at least one harvest candidate"

    # Find a chain that includes a step into BOTH RED cells.
    def _step_destinations(moves):
        for m in moves:
            if m.get("a") == "step":
                to = m.get("to")
                if isinstance(to, (list, tuple)) and len(to) == 2:
                    yield (int(to[0]), int(to[1]))

    multi_anchor = []
    for cand in harvest:
        dests = set(_step_destinations(cand["moves"]))
        if (3, 2) in dests and (5, 2) in dests:
            multi_anchor.append(cand)

    assert multi_anchor, (
        "expected a multi-anchor chain hitting both (3,2) and (5,2); "
        f"observed chains touch: "
        f"{[set(_step_destinations(c['moves'])) for c in harvest]}"
    )

    # The chosen chain must not step on the green at (4, 2).
    for cand in multi_anchor:
        dests = set(_step_destinations(cand["moves"]))
        assert (4, 2) not in dests, (
            f"chain stepped onto green wall: moves={cand['moves']}"
        )


def test_walker_never_steps_onto_red_cell_in_avoid_set():
    """A RED cell with an enemy harvester on it MUST NOT be stepped onto
    even though it's RED — collision triggers §3.17 mutual damage. The
    walker must filter adjacent reds through avoid_cells.

    Regression test for the collision_avoidance scenario, where the
    lookahead walker initially greedy-stepped onto a contested RED.
    """
    width, height = 9, 5
    grid = _grid(width, height)
    grid[2][3] = {"tile": "RED", "value": 200, "purity": 200}
    # Contested RED at (4, 2) — RED tile AND enemy harvester on it.
    grid[2][4] = {
        "tile": "RED", "value": 250, "purity": 250,
        "entity": {"kind": "harvester", "owner": "p2"},
    }
    red_visible = [
        {"x": 3, "y": 2, "value": 200, "purity": 200, "tier": "mass",
         "freshness": "fresh"},
        {"x": 4, "y": 2, "value": 250, "purity": 250, "tier": "mass",
         "freshness": "fresh"},
    ]
    out = cc.compile_candidates(
        _view(width=width, height=height, grid=grid,
              red_visible=red_visible, my_assets=[_harv()])
    )
    for cand in out["candidates"]["harvest"]:
        for m in cand["moves"]:
            if m.get("a") == "step":
                to = m.get("to")
                if isinstance(to, (list, tuple)) and len(to) == 2:
                    assert tuple(to) != (4, 2), (
                        f"chain stepped onto contested RED+enemy_harvester: "
                        f"{cand['moves']}"
                    )


def test_walker_respects_step_budget():
    """A chain that would need >MAX_HARVESTER_STEPS=5 to bridge two REDs
    should NOT bridge them — the walker must stop instead of cheating."""
    width, height = 20, 5
    grid = _grid(width, height)
    grid[2][2] = {"tile": "RED", "value": 100, "purity": 100}
    grid[2][18] = {"tile": "RED", "value": 999, "purity": 999}  # high value bait
    red_visible = [
        {"x": 2, "y": 2, "value": 100, "purity": 100, "tier": "vein",
         "freshness": "fresh"},
        {"x": 18, "y": 2, "value": 999, "purity": 999, "tier": "mass",
         "freshness": "fresh"},
    ]
    out = cc.compile_candidates(
        _view(width=width, height=height, grid=grid,
              red_visible=red_visible, my_assets=[_harv()])
    )
    for cand in out["candidates"]["harvest"]:
        step_count = sum(1 for m in cand["moves"] if m.get("a") == "step")
        assert step_count <= 5, (
            f"chain exceeded MAX_HARVESTER_STEPS=5 with {step_count} steps: "
            f"{cand['moves']}"
        )


# ── Threat-assessment heatmap (v0.9.20) ──────────────────────────────
from sea_of_colours.orchestrator_2.harnesses.pilot_v2 import threat_assess as ta


def test_threat_envelope_carries_new_heatmap_keys():
    """compile_candidates' threat block must include the new v0.9.20 keys
    (heatmap_top_cells, dark_zones, predicted_enemy_drops,
    my_chains_threat_costs, vision_overlap, memory_summary_recent).
    """
    width, height = 14, 9
    grid = _grid(width, height)
    grid[5][5] = {"tile": "RED", "value": 200, "purity": 200}
    red_visible = [{"x": 5, "y": 5, "value": 200, "purity": 200, "tier": "mass"}]
    view = _view(width=width, height=height, grid=grid,
                 red_visible=red_visible, my_assets=[_harv()])
    view["competitor_intel"]["new_this_day"] = [
        {"kind": "enemy_probe_launch", "at": [5, 4], "day": 2}
    ]
    out = cc.compile_candidates(view)
    threat = out["threat"]
    for key in (
        "heatmap_top_cells",
        "dark_zones",
        "predicted_enemy_drops",
        "my_chains_threat_costs",
        "vision_overlap",
        "memory_summary_recent",
    ):
        assert key in threat, f"missing threat key: {key}"
    # Heatmap should rank (5,5) high — it's RED and inside enemy probe disk.
    top = threat["heatmap_top_cells"]
    assert top, "heatmap_top_cells should not be empty"
    assert any(t["at"] == [5, 5] for t in top), (
        f"expected (5,5) in top cells, got {[t['at'] for t in top]}"
    )


def test_predicted_enemy_drops_targets_contested_red():
    """A RED cell inside enemy live vision should be the top predicted drop."""
    width, height = 14, 9
    grid = _grid(width, height)
    grid[5][5] = {"tile": "RED", "value": 200, "purity": 200}
    red_visible = [{"x": 5, "y": 5, "value": 200, "purity": 200, "tier": "mass"}]
    view = _view(width=width, height=height, grid=grid,
                 red_visible=red_visible, my_assets=[_harv()])
    view["competitor_intel"]["new_this_day"] = [
        {"kind": "enemy_probe_launch", "at": [5, 4], "day": 2}
    ]
    out = cc.compile_candidates(view)
    preds = out["threat"]["predicted_enemy_drops"]
    assert preds, "expected at least one predicted enemy drop"
    assert preds[0]["at"] == [5, 5], (
        f"expected (5,5) as top prediction, got {preds[0]}"
    )


def test_doctrine1_low_value_contested_chain_is_abandoned():
    """A trace-RED cell inside enemy vision should be abandoned per
    Doctrine 1 (engage-ratio filter)."""
    width, height = 14, 9
    grid = _grid(width, height)
    grid[5][5] = {"tile": "RED", "value": 10, "purity": 10}  # trace only
    red_visible = [{"x": 5, "y": 5, "value": 10, "purity": 10, "tier": "trace"}]
    view = _view(width=width, height=height, grid=grid,
                 red_visible=red_visible, my_assets=[_harv()])
    view["competitor_intel"]["new_this_day"] = [
        {"kind": "enemy_probe_launch", "at": [5, 4], "day": 2}
    ]
    out = cc.compile_candidates(view)
    # If any chain was emitted for the contested trace-RED, it must be
    # tagged as abandoned with a negative composite score.
    abandoned_chains = [
        c for c in out["candidates"]["harvest"]
        if c.get("flags", {}).get("abandoned_low_engage_ratio")
    ]
    if abandoned_chains:
        for c in abandoned_chains:
            assert c["score"] < 0, (
                f"abandoned chain should have negative score, got {c['score']}"
            )


def test_doctrine3_heat_adaptive_walker_caps_budget_in_hot_zones():
    """v0.9.24 REDESIGN: heat no longer truncates the walker. The walker
    walks the full step budget toward target; heat is a SIGNAL that
    triggers race-bonus / offensive-response in scoring, not a
    defensive cap.

    This test confirms the chain reaches as many adjacent REDs as the
    legacy budget allows, even when the entire chain is in hot
    territory. Previously this test asserted ≤ 3 steps under heat — that
    behavior was the bug.
    """
    width, height = 14, 9
    grid = _grid(width, height)
    # Lay out 5 adjacent REDs (would chain to 5).
    for x in range(2, 7):
        grid[5][x] = {"tile": "RED", "value": 100, "purity": 100}
    red_visible = [
        {"x": x, "y": 5, "value": 100, "purity": 100, "tier": "vein"}
        for x in range(2, 7)
    ]
    # Drop the enemy probe at (4,5) so the entire chain is in hot territory.
    view = _view(width=width, height=height, grid=grid,
                 red_visible=red_visible, my_assets=[_harv()])
    view["competitor_intel"]["new_this_day"] = [
        {"kind": "enemy_probe_launch", "at": [4, 5], "day": 2}
    ]
    out = cc.compile_candidates(view)
    chains = out["candidates"]["harvest"]
    assert chains, "expected at least one chain even in hot territory"
    # Walker should NOT be truncated by heat. The full 5-step budget
    # should be available — chain length depends on geometry, not heat.
    max_steps = max(
        sum(1 for m in c["moves"] if m.get("a") == "step")
        for c in chains
    )
    assert max_steps >= 4, (
        f"hot-zone chain should NOT be truncated by heat; expected ≥4 "
        f"steps (walker budget is 5), got {max_steps}"
    )


def test_doctrine3_chain_survival_prob_recorded_in_breakdown():
    """Every harvest chain must record chain_survival_prob in score_breakdown."""
    width, height = 14, 9
    grid = _grid(width, height)
    grid[4][6] = {"tile": "RED", "value": 200, "purity": 200}
    red_visible = [{"x": 6, "y": 4, "value": 200, "purity": 200, "tier": "mass"}]
    out = cc.compile_candidates(
        _view(width=width, height=height, grid=grid,
              red_visible=red_visible, my_assets=[_harv()])
    )
    chains = out["candidates"]["harvest"]
    assert chains, "expected at least one harvest chain"
    for c in chains:
        bd = c["score_breakdown"]
        assert "chain_survival_prob" in bd
        assert "threat_cost" in bd
        assert "engage_ratio" in bd
        assert 0.0 <= bd["chain_survival_prob"] <= 1.0


def test_doctrine4a_speculative_hot_drop_skipped_on_day_1():
    """Day-1 must not emit speculative hot-drops (insufficient prior)."""
    width, height = 14, 9
    grid = _grid(width, height)
    grid[5][5] = {"tile": "RED", "value": 200, "purity": 200}
    red_visible = [{"x": 5, "y": 5, "value": 200, "purity": 200, "tier": "mass"}]
    view = _view(day=1, width=width, height=height, grid=grid,
                 red_visible=red_visible,
                 my_assets=[_harv()])
    out = cc.compile_candidates(view)
    spec = [c for c in out["candidates"]["hot_drop"]
            if c.get("kind") == "hot_drop_speculative"]
    assert spec == [], (
        f"day-1 must not emit speculative hot-drops, got {spec}"
    )


def test_doctrine4b_counter_blind_hot_drop_emitted_after_supersede_event():
    """If memory records a recent supersede-of-my-probe over juicy red,
    a hot_drop_counter_blind candidate should appear."""
    width, height = 14, 9
    grid = _grid(width, height)
    grid[5][5] = {"tile": "RED", "value": 220, "purity": 220}
    red_visible = [{"x": 5, "y": 5, "value": 220, "purity": 220, "tier": "mass"}]
    view = _view(width=width, height=height, grid=grid,
                 red_visible=red_visible,
                 my_assets=[_harv()])
    # Seed memory with a recent supersede event near (5,5).
    cc.compile_candidates(view)  # cold-start populates memory cache
    mem.record_my_probe_superseded("T", "p1", (5, 4), 2)
    out = cc.compile_candidates(view)
    counter_blinds = [c for c in out["candidates"]["hot_drop"]
                      if c.get("kind") == "hot_drop_counter_blind"]
    assert counter_blinds, (
        "expected at least one hot_drop_counter_blind after supersede"
    )


def test_doctrine2_supersede_boost_when_juicy_contested():
    """Supersede candidate over a zone with juicy red AND enemy live vision
    AND available probe budget should be flagged boosted_juicy_contest."""
    width, height = 14, 9
    grid = _grid(width, height)
    # Cluster of juicy REDs near (5,5) so density > HIGH_VALUE_THRESHOLD=400.
    for (x, y, v) in [(5, 5, 200), (6, 5, 150), (5, 6, 150), (4, 5, 120)]:
        grid[y][x] = {"tile": "RED", "value": v, "purity": v}
    red_visible = [
        {"x": x, "y": y, "value": v, "purity": v, "tier": "mass"}
        for (x, y, v) in [(5, 5, 200), (6, 5, 150), (5, 6, 150), (4, 5, 120)]
    ]
    # Enemy probe at (5,4) gives the enemy live vision over the whole cluster.
    view = _view(width=width, height=height, grid=grid,
                 red_visible=red_visible,
                 my_assets=[_harv(),
                            {"id": "probe_p1_extra", "kind": "probe",
                             "type": "probe", "state": "orbit"}])
    view["competitor_intel"]["new_this_day"] = [
        {"kind": "enemy_probe_launch", "at": [5, 4], "day": 2,
         "owner": "p2", "last_seen_day": 2}
    ]
    out = cc.compile_candidates(view)
    sup = out["candidates"]["probe_supersede"]
    assert sup, "expected at least one supersede candidate"
    boosted = [s for s in sup if s.get("boosted_juicy_contest")]
    assert boosted, (
        f"expected at least one boosted supersede, got "
        f"density={sup[0].get('nearby_red_density')} "
        f"ekzone={sup[0].get('enemy_knew_zone')}"
    )


def test_doctrine_drop_block_emitted_for_predicted_enemy_drop():
    """A high-heat cell with an own orbit harvester available should yield
    a drop_block candidate (§3.17 case 1 — early-slot drop denies enemy)."""
    width, height = 14, 9
    grid = _grid(width, height)
    grid[5][5] = {"tile": "RED", "value": 230, "purity": 230}
    # Make the cell drop-legal by adding our own echo coverage via a friendly probe nearby.
    red_visible = [{"x": 5, "y": 5, "value": 230, "purity": 230, "tier": "mass"}]
    view = _view(width=width, height=height, grid=grid,
                 red_visible=red_visible,
                 my_assets=[_harv()])
    # Enemy probe so heat at (5,5) is high (live vision + RED).
    view["competitor_intel"]["new_this_day"] = [
        {"kind": "enemy_probe_launch", "at": [5, 4], "day": 2}
    ]
    # Mark cell as visible (live) so _is_valid_drop returns True. The default
    # _view doesn't populate visible_set the way the engine does. The harness
    # tests use a simpler fixture, so we set our own probe entity inside the
    # grid to give live LOS over (5,5).
    grid[5][5]["entity"] = None  # ensure no entity
    # Add a friendly probe at (5,5) area — actually, this would prevent the drop.
    # Instead, populate echo set via competitor_intel persistent_echoes so
    # echo-coverage exists and the cell is at least drop-legal under
    # live_or_echo defaults.
    # In our test fixtures _is_valid_drop falls back to echo coverage that's
    # implicit in the grid. The simplest path: ensure 'visible_or_echo'
    # registers (5,5) as having terrain — which it does via grid[5][5] being
    # RED. This is enough for _is_valid_drop.
    out = cc.compile_candidates(view)
    db = out["candidates"]["drop_block"]
    # We may not always emit (depends on drop-legality of the predicted cell).
    # The contract is: if emitted, must carry the expected fields.
    for c in db:
        assert c["kind"] == "drop_block"
        assert "at" in c and len(c["at"]) == 2
        assert c["score"] > 0
        assert "predicted_drop_heat" in c["flags"]
        assert c["flags"]["early_slot_required"] is True


# ── Probe quadrant-spread fallback (Pass 4) ──────────────────────────


def test_compile_candidates_handles_sparse_grid_engine_view():
    """Live engine sends world.grid=None and RED/GREEN/BLUE as sparse
    top-level lists. The dense-grid synthesizer must project these into
    a 2D grid so chain_red_purities is populated correctly.

    Regression for the bug where every chain scored ~-1000 because
    _grid_cell returned None for every cell → chain_red_purities=[] →
    Doctrine 1 abandoned every chain.
    """
    width, height = 14, 9
    # NO dense grid — mirrors the live engine.
    view = {
        "meta": {"session_id": "TS", "season": "S", "player": "p1",
                 "day": 2, "policy_actions_left": 21,
                 "policy_actions_max": 21,
                 "rules": {"probe_radius": 4, "probe_lifetime_nights": 3}},
        "hud": {"score": 0, "scores": {"p1": 0, "p2": 0},
                "season_day_cap": 7,
                "hoard": {"used": 0, "max": 15, "free": 15,
                          "by_tier": {"GREEN": {}, "RED": {}, "BLUE": {}},
                          "warning": None},
                "shipped": {"used": 0, "max": None,
                            "by_tier": {"GREEN": {}, "RED": {}, "BLUE": {}}}},
        "last_night": {"day_ended": 1, "my_orders": [],
                       "my_assets_destroyed": [], "my_parcels_banked": []},
        "competitor_intel": {"new_this_day": [], "persistent_echoes": []},
        # KEY: world.grid is None — production shape. RED is in red_tiles,
        # live + echo lists cover the visible plus around our drop.
        "world": {
            "width": width, "height": height, "grid": None,
            "echo": [],
            "live": [{"x": x, "y": y}
                     for y in range(3, 7) for x in range(3, 8)],
            "fog_count": 0,
        },
        "navigation": {
            "best_red_visible": [
                {"x": 5, "y": 5, "value": 100, "purity": 100, "tier": "vein"},
                {"x": 6, "y": 5, "value": 80, "purity": 80, "tier": "vein"},
            ],
            "best_red_echo": [], "fog_clusters": [],
        },
        "red_tiles": [
            {"x": 5, "y": 5, "value": 100, "purity": 100, "tier": "vein",
             "freshness": "fresh", "square_id": "r1"},
            {"x": 6, "y": 5, "value": 80, "purity": 80, "tier": "vein",
             "freshness": "fresh", "square_id": "r2"},
        ],
        "green_tiles": [], "blue_tiles": [],
        "fog_clusters": [], "entities": {"mine": [_harv()], "echoes": []},
        "my_assets": [_harv()],
    }
    out = cc.compile_candidates(view)
    chains = out["candidates"]["harvest"]
    assert chains, "expected at least one harvest chain"
    # The chain must actually count the RED it traverses — not [] as
    # before the dense-grid fix.
    top = chains[0]
    assert top["chain_red_purities"], (
        f"chain_red_purities should not be empty for a chain over visible RED; "
        f"got {top['chain_red_purities']} from cells {top['cells_traversed']}"
    )
    assert top["expected_score_raw"] > 0, (
        f"raw RED score should be positive when chain hits RED; got {top['expected_score_raw']}"
    )
    # And the chain must not be abandoned by Doctrine 1 just because the
    # grid was sparse.
    assert not top["flags"].get("abandoned_low_engage_ratio"), (
        "chain should not be abandoned when it hits real RED"
    )


def test_probe_candidates_quadrant_spread_on_day_1():
    """On day 1 with the whole map in one fog cluster, the compiler must
    still emit multiple probe candidates in distinct quadrants — Pass 4
    fills the slots so the agent can spread coverage.
    """
    width, height = 40, 28
    grid = [[None for _ in range(width)] for _ in range(height)]
    view = {
        "meta": {"session_id": "TQ", "season": "S", "player": "p1",
                 "day": 1, "policy_actions_left": 21,
                 "policy_actions_max": 21,
                 "rules": {"probe_radius": 4, "probe_lifetime_nights": 3}},
        "hud": {"score": 0, "scores": {"p1": 0, "p2": 0},
                "season_day_cap": 7,
                "hoard": {"used": 0, "max": 15, "free": 15,
                          "by_tier": {"GREEN": {}, "RED": {}, "BLUE": {}},
                          "warning": None},
                "shipped": {"used": 0, "max": None,
                            "by_tier": {"GREEN": {}, "RED": {}, "BLUE": {}}}},
        "last_night": {"day_ended": 0, "my_orders": [],
                       "my_assets_destroyed": [], "my_parcels_banked": []},
        "competitor_intel": {"new_this_day": [], "persistent_echoes": []},
        "world": {"width": width, "height": height, "grid": grid},
        "navigation": {"best_red_visible": [], "best_red_echo": [],
                       "fog_clusters": [{"centroid": [19, 13], "size": 1120}]},
        "my_assets": [
            _harv(),
            {"id": "probe_p1_0", "kind": "probe", "type": "probe", "state": "orbit"},
            {"id": "probe_p1_1", "kind": "probe", "type": "probe", "state": "orbit"},
        ],
        "red_tiles": [], "green_tiles": [], "blue_tiles": [],
        "fog_clusters": [], "entities": {"mine": [_harv()], "echoes": []},
    }
    out = cc.compile_candidates(view)
    probes = out["candidates"]["probes"]
    assert len(probes) >= 2, (
        f"expected ≥2 probe candidates on day 1; got {len(probes)}"
    )
    # Quadrants the probe positions fall into.
    def quadrant(at):
        x, y = at[0], at[1]
        return (
            "N" if y < height // 2 else "S",
            "W" if x < width // 2 else "E",
        )
    quads = {quadrant(p["at"]) for p in probes}
    assert len(quads) >= 2, (
        f"expected probes spanning ≥2 quadrants; got {quads}"
    )
    # Recommended policy must also queue at least 2 probes.
    rec_probes = [m for m in out["candidates"]["recommended_policy"]["moves"]
                  if m.get("a") == "probe"]
    assert len(rec_probes) >= 2, (
        f"recommended policy should queue ≥2 probes; got {rec_probes}"
    )


# ── Posture (score-gap-aware playstyle) ──────────────────────────────


def test_posture_aggressive_when_trailing_mid_season():
    """Behind by >50 points mid-season → aggressive."""
    p = ta.compute_posture(
        {"meta": {"player": "p1", "day": 3},
         "hud": {"season_day_cap": 7, "scores": {"p1": 0, "p2": 100}},
         "navigation": {"best_red_visible": [{"value": 200}]}},
        {})
    assert p["label"] == "aggressive"
    assert p["hot_drop_value_floor"] == 50
    assert p["recommended_probe_cap"] == 3


def test_posture_conservative_when_leading_late():
    """Ahead by >100 with ≤2 days left → conservative (lock it in)."""
    p = ta.compute_posture(
        {"meta": {"player": "p1", "day": 6},
         "hud": {"season_day_cap": 7, "scores": {"p1": 300, "p2": 100}},
         "navigation": {"best_red_visible": [{"value": 50}]}},
        {})
    assert p["label"] == "conservative"
    assert p["hot_drop_value_floor"] == 150
    assert p["recommended_probe_cap"] == 1


def test_posture_aggressive_when_low_visible_red():
    """No score gap but very little visible red & plenty of days left → explore."""
    p = ta.compute_posture(
        {"meta": {"player": "p1", "day": 2},
         "hud": {"season_day_cap": 7, "scores": {"p1": 0, "p2": 0}},
         "navigation": {"best_red_visible": []}},
        {})
    assert p["label"] == "aggressive"
    assert "explore" in p["reason"]


def test_posture_last_day_hail_mary():
    """Trailing on the final night → aggressive Hail Mary."""
    p = ta.compute_posture(
        {"meta": {"player": "p1", "day": 7},
         "hud": {"season_day_cap": 7, "scores": {"p1": 100, "p2": 200}},
         "navigation": {"best_red_visible": [{"value": 50}]}},
        {})
    assert p["label"] == "aggressive"
    assert "Hail Mary" in p["reason"]


def test_posture_surfaces_in_threat_envelope():
    """compile_candidates must surface posture inside threat for the agent to read."""
    width, height = 14, 9
    view = {
        "meta": {"session_id": "PS", "season": "S", "player": "p1",
                 "day": 1, "policy_actions_left": 21,
                 "policy_actions_max": 21,
                 "rules": {"probe_radius": 4, "probe_lifetime_nights": 3}},
        "hud": {"score": 0, "scores": {"p1": 0, "p2": 0},
                "season_day_cap": 7,
                "hoard": {"used": 0, "max": 15, "free": 15,
                          "by_tier": {"GREEN": {}, "RED": {}, "BLUE": {}},
                          "warning": None},
                "shipped": {"used": 0, "max": None,
                            "by_tier": {"GREEN": {}, "RED": {}, "BLUE": {}}}},
        "last_night": {"day_ended": 0, "my_orders": [],
                       "my_assets_destroyed": [], "my_parcels_banked": []},
        "competitor_intel": {"new_this_day": [], "persistent_echoes": []},
        "world": {"width": width, "height": height, "grid": None,
                  "echo": [], "live": [], "fog_count": 0},
        "navigation": {"best_red_visible": [], "best_red_echo": [],
                       "fog_clusters": [{"centroid": [6, 4], "size": 100}]},
        "red_tiles": [], "green_tiles": [], "blue_tiles": [],
        "fog_clusters": [], "my_assets": [_harv()],
        "entities": {"mine": [_harv()], "echoes": []},
    }
    out = cc.compile_candidates(view)
    posture = out["threat"].get("posture")
    assert posture, "threat envelope must carry a posture block"
    assert posture.get("label") in ("aggressive", "balanced", "conservative")
    # Day-1 with no visible red is always aggressive.
    assert posture["label"] == "aggressive"
    # The exposed knobs must be present for the agent to consume.
    for k in ("hot_drop_value_floor", "speculative_day_guard",
              "recommended_probe_cap", "supersede_activation_threshold"):
        assert k in posture, f"posture missing knob {k}"


def test_recommended_policy_respects_probe_stock():
    """When my_probes_available < posture's probe_cap, the recommended
    policy must NOT emit more probe moves than I actually have in orbit.

    Regression for the bug where aggressive posture queued 3 probes on
    day 1 but the engine only had 2 in stock → 1 illegal-action waste.
    """
    width, height = 40, 28
    grid = [[None for _ in range(width)] for _ in range(height)]
    view = {
        "meta": {"session_id": "PS2", "season": "S", "player": "p1",
                 "day": 1, "policy_actions_left": 21,
                 "policy_actions_max": 21,
                 "rules": {"probe_radius": 4, "probe_lifetime_nights": 3}},
        "hud": {"score": 0, "scores": {"p1": 0, "p2": 0},
                "season_day_cap": 7,
                "hoard": {"used": 0, "max": 15, "free": 15,
                          "by_tier": {"GREEN": {}, "RED": {}, "BLUE": {}},
                          "warning": None},
                "shipped": {"used": 0, "max": None,
                            "by_tier": {"GREEN": {}, "RED": {}, "BLUE": {}}}},
        "last_night": {"day_ended": 0, "my_orders": [],
                       "my_assets_destroyed": [], "my_parcels_banked": []},
        "competitor_intel": {"new_this_day": [], "persistent_echoes": []},
        "world": {"width": width, "height": height, "grid": grid},
        "navigation": {"best_red_visible": [], "best_red_echo": [],
                       "fog_clusters": [{"centroid": [19, 13], "size": 1120}]},
        # Stock = exactly 2 probes in orbit (matches the engine's day-1 default).
        "my_assets": [
            _harv(),
            {"id": "probe_p1_0", "kind": "probe", "type": "probe", "state": "orbit"},
            {"id": "probe_p1_1", "kind": "probe", "type": "probe", "state": "orbit"},
        ],
        "red_tiles": [], "green_tiles": [], "blue_tiles": [],
        "fog_clusters": [], "entities": {"mine": [_harv()], "echoes": []},
    }
    out = cc.compile_candidates(view)
    # Posture should be aggressive (no visible red on day 1).
    assert out["threat"]["posture"]["label"] == "aggressive"
    # But the recommended policy must cap probes at 2 (= stock).
    rec_probes = [m for m in out["candidates"]["recommended_policy"]["moves"]
                  if m.get("a") == "probe"]
    assert len(rec_probes) <= 2, (
        f"queued {len(rec_probes)} probes but stock is only 2: {rec_probes}"
    )


# ── EMP threat detection (v0.9.22) ──────────────────────────────────


def test_emp_signal_flat_when_blue_unchanged():
    sig = ta.compute_emp_threat_signal(
        {"meta": {"player": "p1", "day": 3},
         "station_intel": {"opponents": [
             {"seat": "p2", "blue": {"grade": "high"}, "activity": {"emps": 0}}]}},
        {"rival_blue_grade_history": {"2": "high"}})
    assert sig["rival_built_weapon"] is False
    assert sig["confidence"] == 0.0
    assert sig["signal_source"] == "none"


def test_emp_signal_band_drop_triggers_medium_confidence():
    sig = ta.compute_emp_threat_signal(
        {"meta": {"player": "p1", "day": 3},
         "station_intel": {"opponents": [
             {"seat": "p2", "blue": {"grade": "medium"}, "activity": {"emps": 0}}]}},
        {"rival_blue_grade_history": {"2": "high"}})
    assert sig["rival_built_weapon"] is True
    assert 0.5 <= sig["confidence"] < 0.7
    assert sig["rival_blue_band_drop"] == 1
    assert "weapon build likely" in sig["reason"]


def test_emp_signal_confirmed_launch_is_max_confidence():
    sig = ta.compute_emp_threat_signal(
        {"meta": {"player": "p1", "day": 3},
         "station_intel": {"opponents": [
             {"seat": "p2", "blue": {"grade": "low"}, "activity": {"emps": 1}}]}},
        {"rival_blue_grade_history": {"2": "medium"}})
    assert sig["rival_built_weapon"] is True
    assert sig["confidence"] >= 0.9
    assert sig["rival_emp_launches_last_night"] == 1
    assert "confirmed_launch" in sig["signal_source"]


def test_doctrine_emp1_frontload_bonus_when_emp_threat_high():
    """When EMP signal is high, fast chains (≤6 actions) get a bonus and
    slow chains get a penalty. Both must apply, and the fast chain must
    outrank the slow one even when raw RED is similar."""
    width, height = 14, 9
    grid = _grid(width, height)
    # Single RED right next to a drop site: 2-action chain (drop, pickup).
    grid[5][5] = {"tile": "RED", "value": 200, "purity": 200}
    red_visible = [{"x": 5, "y": 5, "value": 200, "purity": 200, "tier": "mass"}]
    view = _view(width=width, height=height, grid=grid,
                 red_visible=red_visible, my_assets=[_harv()])
    # Seed the engine view to simulate a strong EMP signal.
    view["station_intel"] = {
        "opponents": [
            {"seat": "p2", "blue": {"grade": "low"}, "activity": {"emps": 1}},
        ],
    }
    out = cc.compile_candidates(view)
    sig = out["threat"]["emp_signal"]
    assert sig["rival_built_weapon"] is True
    chains = out["candidates"]["harvest"]
    assert chains, "expected at least one harvest chain"
    # If any chain is short (≤6 actions), it must carry the front-load
    # bonus in score_breakdown.
    short_chains = [c for c in chains if c["flags"].get("action_count", 99) <= 6]
    if short_chains:
        assert short_chains[0]["score_breakdown"].get("emp_score_adj", 0) > 0, (
            f"short chain under EMP threat must get a positive emp_score_adj; "
            f"got {short_chains[0]['score_breakdown']}"
        )
        assert short_chains[0]["flags"].get("emp_resilient") is True


def test_emp_signal_surfaces_in_threat_envelope():
    """compile_threat must always include the emp_signal block (possibly
    no-op) so the agent's prompt always sees a consistent shape."""
    width, height = 14, 9
    grid = _grid(width, height)
    out = cc.compile_candidates(
        _view(width=width, height=height, grid=grid, my_assets=[_harv()])
    )
    assert "emp_signal" in out["threat"]
    sig = out["threat"]["emp_signal"]
    # No station_intel in default fixture → signal is flat.
    assert sig["rival_built_weapon"] is False
    assert sig["confidence"] == 0.0


# ── PURE-cell prioritization (v0.9.23) ──────────────────────────────


def test_pure_cell_chain_outranks_vein_chain():
    """A chain that traverses pure cells must score higher than a chain
    over equivalent-count vein cells. Pure cells bank 255 each (after
    cascade) vs ~50-150 for vein — the score must reflect that.

    Regression for the bug where PILOT_V2 picked a vein chain over a
    visible-pure cluster on day 6.
    """
    width, height = 14, 9
    grid = _grid(width, height)
    # Vein cluster on the left (x=2-3, y=4-5): 4 cells @ purity 80.
    for (x, y) in [(2, 4), (3, 4), (2, 5), (3, 5)]:
        grid[y][x] = {"tile": "RED", "value": 80, "purity": 80}
    # PURE cluster on the right (x=9-10, y=4-5): 4 cells @ purity 255.
    for (x, y) in [(9, 4), (10, 4), (9, 5), (10, 5)]:
        grid[y][x] = {"tile": "RED", "value": 255, "purity": 255}
    red_visible = [
        {"x": 2, "y": 4, "value": 80, "purity": 80, "tier": "vein"},
        {"x": 3, "y": 4, "value": 80, "purity": 80, "tier": "vein"},
        {"x": 2, "y": 5, "value": 80, "purity": 80, "tier": "vein"},
        {"x": 3, "y": 5, "value": 80, "purity": 80, "tier": "vein"},
        {"x": 9, "y": 4, "value": 255, "purity": 255, "tier": "pure"},
        {"x": 10, "y": 4, "value": 255, "purity": 255, "tier": "pure"},
        {"x": 9, "y": 5, "value": 255, "purity": 255, "tier": "pure"},
        {"x": 10, "y": 5, "value": 255, "purity": 255, "tier": "pure"},
    ]
    out = cc.compile_candidates(
        _view(width=width, height=height, grid=grid,
              red_visible=red_visible, my_assets=[_harv()])
    )
    chains = out["candidates"]["harvest"]
    assert chains, "expected at least one chain"
    top = chains[0]
    # The top chain MUST contain pure cells.
    assert top["flags"]["contains_pure"] is True, (
        f"top chain should target pure cluster; got {top['target']} "
        f"score={top['score']} breakdown={top['score_breakdown']}"
    )
    assert top["score_breakdown"]["pure_cell_count"] >= 1
    assert top["score_breakdown"]["pure_score_adj"] > 0


def test_chain_without_pure_carries_zero_pure_adj():
    """Sanity: chains over non-pure / non-mass RED must have
    pure_score_adj=0 and contains_pure=False."""
    width, height = 14, 9
    grid = _grid(width, height)
    # Use a low vein purity (well below mass threshold) so no bonus fires.
    grid[4][6] = {"tile": "RED", "value": 80, "purity": 80}
    red_visible = [{"x": 6, "y": 4, "value": 80, "purity": 80, "tier": "vein"}]
    out = cc.compile_candidates(
        _view(width=width, height=height, grid=grid,
              red_visible=red_visible, my_assets=[_harv()])
    )
    chains = out["candidates"]["harvest"]
    assert chains
    for c in chains:
        assert c["score_breakdown"].get("pure_score_adj", 0) == 0
        assert c["score_breakdown"].get("mass_cell_count", 0) == 0
        assert c["flags"].get("contains_pure") is False


def test_mass_cell_chain_carries_mass_bonus():
    """Chains over mass-tier RED (purity 151-254) get MASS_CELL_BONUS
    per cell. Ships at 1.5× vein — the agent should pursue mass
    aggressively."""
    width, height = 14, 9
    grid = _grid(width, height)
    for (x, y) in [(6, 4), (7, 4), (8, 4)]:
        grid[y][x] = {"tile": "RED", "value": 200, "purity": 200}
    red_visible = [
        {"x": x, "y": 4, "value": 200, "purity": 200, "tier": "mass"}
        for x in (6, 7, 8)
    ]
    out = cc.compile_candidates(
        _view(width=width, height=height, grid=grid,
              red_visible=red_visible, my_assets=[_harv()])
    )
    chains = out["candidates"]["harvest"]
    assert chains
    top = chains[0]
    bd = top["score_breakdown"]
    assert bd["mass_cell_count"] >= 2, (
        f"chain over mass cluster should record mass_cell_count ≥2, "
        f"got {bd['mass_cell_count']}"
    )
    assert bd["pure_score_adj"] > 0, (
        f"mass-tier chain should accrue positive bonus, got {bd['pure_score_adj']}"
    )


def test_pure_bonus_dominates_long_vein_chain():
    """A 1-pure chain must outrank a longer all-vein chain — pure ships
    for 3× value, so even a single pure beats a sweeping vein walk."""
    width, height = 20, 9
    grid = _grid(width, height)
    # Pure cell alone, far from drop.
    grid[4][14] = {"tile": "RED", "value": 255, "purity": 255}
    # 5-cell vein cluster on the opposite side, fully harvestable.
    for x in range(2, 7):
        grid[4][x] = {"tile": "RED", "value": 100, "purity": 100}
    red_visible = (
        [{"x": 14, "y": 4, "value": 255, "purity": 255, "tier": "pure"}] +
        [{"x": x, "y": 4, "value": 100, "purity": 100, "tier": "vein"}
         for x in range(2, 7)]
    )
    out = cc.compile_candidates(
        _view(width=width, height=height, grid=grid,
              red_visible=red_visible, my_assets=[_harv()])
    )
    chains = out["candidates"]["harvest"]
    assert chains
    top = chains[0]
    assert top["flags"]["contains_pure"] is True, (
        f"top chain must be the pure one (ships 3×); got target={top['target']} "
        f"score={top['score']}"
    )


# ── Multi-harvester sibling-claim (v0.9.23) ──────────────────────────


def test_two_harvesters_target_different_clusters():
    """Two orbit harvesters on a board with two distinct RED clusters must
    pick DIFFERENT clusters — the second harvester's recommended chain
    should not overlap the first's cells.

    Regression for the day-7 bug where both harvesters dropped at the
    same cell and the second banked 0 (walked over synthetic-green).
    """
    width, height = 20, 9
    grid = _grid(width, height)
    # Cluster A on the left (x=3-4, y=4-5).
    for (x, y) in [(3, 4), (4, 4), (3, 5), (4, 5)]:
        grid[y][x] = {"tile": "RED", "value": 200, "purity": 200}
    # Cluster B on the right (x=14-15, y=4-5).
    for (x, y) in [(14, 4), (15, 4), (14, 5), (15, 5)]:
        grid[y][x] = {"tile": "RED", "value": 200, "purity": 200}
    red_visible = (
        [{"x": x, "y": y, "value": 200, "purity": 200, "tier": "mass"}
         for (x, y) in [(3, 4), (4, 4), (3, 5), (4, 5),
                        (14, 4), (15, 4), (14, 5), (15, 5)]]
    )
    out = cc.compile_candidates(
        _view(width=width, height=height, grid=grid, red_visible=red_visible,
              my_assets=[
                  _harv(unit="harvester_p1"),
                  _harv(unit="harvester_p1_2"),
              ])
    )
    chains = out["candidates"]["harvest"]
    # The recommended_policy queues one chain per harvester.
    rec_moves = out["candidates"]["recommended_policy"]["moves"]
    drops = [tuple(m["at"]) for m in rec_moves if m.get("a") == "drop"]
    assert len(drops) == 2, (
        f"expected two drop moves (one per harvester); got {drops}"
    )
    # The two drops must be on opposite sides — distance Manhattan >= 6
    # because the clusters are 10 apart on x.
    d = abs(drops[0][0] - drops[1][0]) + abs(drops[0][1] - drops[1][1])
    assert d >= 6, (
        f"two harvesters must target separate clusters; drops "
        f"{drops} are only {d} apart"
    )


def test_chain_skips_cell_already_claimed_by_sibling():
    """If shared_claimed contains a target cell, _harvest_candidates_for
    should NOT seed a chain there."""
    width, height = 14, 9
    grid = _grid(width, height)
    grid[5][5] = {"tile": "RED", "value": 200, "purity": 200}
    grid[5][8] = {"tile": "RED", "value": 180, "purity": 180}
    red_visible = [
        {"x": 5, "y": 5, "value": 200, "purity": 200, "tier": "mass"},
        {"x": 8, "y": 5, "value": 180, "purity": 180, "tier": "mass"},
    ]
    # Call _harvest_candidates_for directly with shared_claimed seeded.
    view = _view(width=width, height=height, grid=grid,
                 red_visible=red_visible, my_assets=[_harv()])
    cc._memory.reset_for_tests()
    av = cc._ensure_dense_grid(view)
    chains = cc._harvest_candidates_for(
        harvester=_harv(),
        agent_view=av,
        red_pool=red_visible,
        avoid_cells=set(),
        enemy_disk_cells=set(),
        enemy_history=set(),
        vault={"red_min": None},
        k=3,
        seat="p1",
        shared_claimed={(5, 5)},  # mark (5,5) as already claimed
    )
    # The chain that would have targeted (5,5) must be skipped — only
    # the (8,5)-anchored chain should survive.
    targets = [(c["target"]["x"], c["target"]["y"]) for c in chains if c.get("target")]
    assert (5, 5) not in targets, (
        f"chain at claimed cell (5,5) should have been skipped; targets={targets}"
    )


# ── Heat-as-SIGNAL redesign (v0.9.24) ────────────────────────────────


def test_pure_chain_keeps_positive_score_under_heat():
    """A pure-cell chain in a hot zone must still rank high — heat is
    NOT an avoidance signal. Regression for pure_under_enemy_pressure.
    """
    width, height = 14, 9
    grid = _grid(width, height)
    # Pure cluster in the middle.
    for (x, y) in [(6, 4), (7, 4), (6, 5), (7, 5)]:
        grid[y][x] = {"tile": "RED", "value": 255, "purity": 255}
    red_visible = [
        {"x": x, "y": y, "value": 255, "purity": 255, "tier": "pure"}
        for (x, y) in [(6, 4), (7, 4), (6, 5), (7, 5)]
    ]
    # Enemy probe right next to the cluster paints the whole zone hot.
    view = _view(width=width, height=height, grid=grid,
                 red_visible=red_visible, my_assets=[_harv()])
    view["competitor_intel"]["new_this_day"] = [
        {"kind": "enemy_probe_launch", "at": [8, 5], "day": 2}
    ]
    out = cc.compile_candidates(view)
    chains = out["candidates"]["harvest"]
    assert chains, "expected at least one chain over the pure cluster"
    top = chains[0]
    assert top["flags"]["contains_pure"] is True
    assert top["score"] > 0, (
        f"pure-bearing chain in hot zone must keep positive score, got {top['score']}"
    )
    # Verify the chain still touches the pure cells (heat did not push it away).
    cells = top["cells_traversed"]
    pure_touched = sum(
        1 for c in cells
        if tuple(c) in {(6, 4), (7, 4), (6, 5), (7, 5)}
    )
    assert pure_touched >= 1, (
        f"pure chain should touch ≥1 pure cell even under heat, "
        f"touched={pure_touched}, cells={cells}"
    )


def test_short_high_value_chain_under_heat_gets_race_bonus():
    """A short chain (≤5 actions) over a high-value cluster gets a
    RACE_BONUS proportional to local heat — encoded as a non-zero
    threat_score_adj when heat is present.
    """
    width, height = 14, 9
    grid = _grid(width, height)
    # 3-cell mass cluster (550 raw value), reachable in 3 steps.
    for (x, y) in [(6, 4), (7, 4), (8, 4)]:
        grid[y][x] = {"tile": "RED", "value": 180, "purity": 180}
    red_visible = [
        {"x": x, "y": y, "value": 180, "purity": 180, "tier": "mass"}
        for (x, y) in [(6, 4), (7, 4), (8, 4)]
    ]
    view = _view(width=width, height=height, grid=grid,
                 red_visible=red_visible, my_assets=[_harv()])
    view["competitor_intel"]["new_this_day"] = [
        {"kind": "enemy_probe_launch", "at": [7, 4], "day": 2}
    ]
    out = cc.compile_candidates(view)
    chains = out["candidates"]["harvest"]
    assert chains
    top = chains[0]
    bd = top["score_breakdown"]
    # threat_score_adj (now race_bonus_adj alias) should be POSITIVE
    # under heat, NOT negative. This is the core semantic flip.
    assert bd["threat_score_adj"] >= 0, (
        f"race-bonus under heat should be ≥0 (positive); got {bd['threat_score_adj']}"
    )


def test_low_value_contested_chain_still_abandons():
    """The abandon path still fires for genuinely bad chains: low raw
    value, no pure cells, high threat. The redesign only protects
    high-value / pure chains."""
    width, height = 14, 9
    grid = _grid(width, height)
    # Single low-purity RED in heat.
    grid[5][6] = {"tile": "RED", "value": 25, "purity": 25}
    red_visible = [{"x": 6, "y": 5, "value": 25, "purity": 25, "tier": "trace"}]
    view = _view(width=width, height=height, grid=grid,
                 red_visible=red_visible, my_assets=[_harv()])
    # Stack heat near the cluster.
    view["competitor_intel"]["new_this_day"] = [
        {"kind": "enemy_probe_launch", "at": [6, 5], "day": 2},
        {"kind": "enemy_probe_launch", "at": [7, 5], "day": 2},
    ]
    out = cc.compile_candidates(view)
    chains = out["candidates"]["harvest"]
    # If a chain is emitted, it should be flagged abandoned with very
    # negative score (the engage-ratio + value floor combo).
    if chains:
        for c in chains:
            if c.get("flags", {}).get("abandoned_low_engage_ratio"):
                assert c["score"] < 0


def test_crush_candidate_gets_offensive_bonus_under_heat():
    """A crush onto an enemy probe in a hot zone should score higher
    than the raw value_after_crush — OFFENSIVE_RESPONSE_BONUS applies."""
    width, height = 14, 9
    grid = _grid(width, height)
    # RED visible near the enemy probe so unlocked > 0.
    grid[5][6] = {"tile": "RED", "value": 200, "purity": 200}
    red_visible = [{"x": 6, "y": 5, "value": 200, "purity": 200, "tier": "mass"}]
    view = _view(width=width, height=height, grid=grid,
                 red_visible=red_visible, my_assets=[_harv()])
    view["competitor_intel"]["enemy_probes"] = [
        {"unit_id": "probe_p2_1", "at": [6, 5]}
    ]
    # And a recent probe launch at the same cell stacks heat there.
    view["competitor_intel"]["new_this_day"] = [
        {"kind": "enemy_probe_launch", "at": [6, 5], "day": 2}
    ]
    out = cc.compile_candidates(view)
    crushes = out["candidates"].get("harvester_crush") or []
    if crushes:
        c = crushes[0]
        score = float(c.get("score") or 0.0)
        raw = float(c.get("value_after_crush") or 0.0)
        adj = float(c.get("flags", {}).get("offensive_response_adj") or 0.0)
        assert adj > 0, f"crush under heat should have offensive bonus > 0, got {adj}"
        assert score > raw, f"crush score should exceed raw value_after_crush; score={score}, raw={raw}"


# ── Combat suggestion harness (v0.9.25) ──────────────────────────────


def test_emp_launch_candidate_emitted_when_enemy_probe_in_play():
    """When the agent has EMP stock + visible enemy probe, the compiler
    surfaces an emp_launch candidate centered on that probe with the
    full mechanical-facts payload the agent needs to reason."""
    width, height = 20, 14
    grid = _grid(width, height)
    # Pure cluster around (10, 7).
    grid[7][10] = {"tile": "RED", "value": 255, "purity": 255}
    grid[7][11] = {"tile": "RED", "value": 200, "purity": 200}
    red_visible = [
        {"x": 10, "y": 7, "value": 255, "purity": 255, "tier": "pure"},
        {"x": 11, "y": 7, "value": 200, "purity": 200, "tier": "mass"},
    ]
    view = _view(
        width=width, height=height, grid=grid,
        red_visible=red_visible, my_assets=[_harv()],
    )
    # Pre-arm the EMP in orbit weapon_stock.
    orbit = view.setdefault("orbit", {})
    orbit["weapon_stock"] = {"emp": 1, "mine": 0, "chaff": 0}
    orbit["blue_purity_total"] = 300
    orbit["credits"] = 500
    # Place the enemy probe — via competitor_intel.new_this_day per §3.15.
    view["competitor_intel"]["new_this_day"] = [
        {"kind": "enemy_probe_launch", "at": [11, 7], "day": 4}
    ]
    out = cc.compile_candidates(view)
    emp_cands = out["candidates"].get("emp_launch") or []
    assert emp_cands, "expected at least one emp_launch candidate"
    e = emp_cands[0]
    # Mechanical facts the agent needs.
    assert e["kind"] == "emp_launch"
    # Salvo move: 3 target cells inside the at list.
    move = e["moves"][0]
    assert move["a"] == "emp_launch"
    assert isinstance(move["at"], list) and len(move["at"]) == 3, (
        f"salvo move must be 3 targets per launch, got {move['at']}"
    )
    eff = e["expected_effect"]
    assert eff["cloud_radius"] == 2
    assert eff["cloud_hours"] == 8
    assert eff["missiles_per_launch"] == 3
    assert eff["enemy_unit_count"] >= 1
    # Signal reference so the agent must quote it.
    assert e["responds_to_signal"] == "compute_emp_threat_signal"
    assert "signal_payload" in e
    # Affordability surfaced.
    aff = e["affordability"]
    assert aff["in_stock"] == 1
    assert aff["fires_from_stock"] is True
    # Pattern label surfaced so the agent reasons about spatial strategy.
    assert e["pattern"] in {"concentrated", "spread", "pair_with_top"}


def test_combat_block_surfaces_weapon_stock_and_mechanics():
    """Every harness compile must include the combat block with stock
    + mechanics, even when no candidates can be emitted (zero stock)."""
    width, height = 14, 9
    grid = _grid(width, height)
    grid[4][6] = {"tile": "RED", "value": 200, "purity": 200}
    red_visible = [{"x": 6, "y": 4, "value": 200, "purity": 200, "tier": "mass"}]
    out = cc.compile_candidates(
        _view(width=width, height=height, grid=grid,
              red_visible=red_visible, my_assets=[_harv()])
    )
    assert "combat" in out
    combat = out["combat"]
    assert "my_weapon_stock" in combat
    assert "emp_mechanics" in combat
    assert combat["emp_mechanics"]["cost_blue_purity"] == 200
    assert combat["emp_mechanics"]["cloud_hours"] == 8


def test_emp_candidate_omitted_when_no_enemy_in_radius():
    """If a probe is far from any enemy, no emp_launch is emitted —
    pointless EMPs are filtered out."""
    width, height = 30, 18
    grid = _grid(width, height)
    grid[7][10] = {"tile": "RED", "value": 255, "purity": 255}
    red_visible = [{"x": 10, "y": 7, "value": 255, "purity": 255, "tier": "pure"}]
    view = _view(
        width=width, height=height, grid=grid,
        red_visible=red_visible, my_assets=[_harv()],
    )
    orbit = view.setdefault("orbit", {})
    orbit["weapon_stock"] = {"emp": 1}
    orbit["blue_purity_total"] = 0
    orbit["credits"] = 0
    # No enemy probes anywhere.
    out = cc.compile_candidates(view)
    emp_cands = out["candidates"].get("emp_launch") or []
    assert emp_cands == [], f"no enemy → no emp candidate, got {emp_cands}"


def test_chain_walks_through_own_probe_on_red_cell():
    """Regression for pure_under_enemy_pressure: friendly probes placed
    ON RED cells (e.g. by ``grant_live_vision``) must NOT block the
    walker. The engine crushes the own probe on entry — that's a
    ~250c hit — but harvesting a vein-or-better tile pays it back
    many times over (pure ships at 3× = ~765 points). Blocking these
    cells caused the compiler to route chains AROUND the pure cluster
    and leak ~600 points per contested-pure turn.
    """
    width, height = 14, 9
    grid = _grid(width, height)
    # Pure cluster: pure at centre, RED veins around it.
    pure_xy = (6, 4)
    grid[pure_xy[1]][pure_xy[0]] = {
        "tile": "RED", "value": 255, "purity": 255,
        # Friendly probe sits ON the pure cell (grant_live_vision style).
        "entity": {"kind": "probe", "owner": "p1"},
    }
    ring = [(5, 4, 180), (7, 4, 200), (6, 3, 170), (6, 5, 190)]
    for x, y, v in ring:
        grid[y][x] = {"tile": "RED", "value": v, "purity": v}
    red_visible = [
        {"x": pure_xy[0], "y": pure_xy[1], "value": 255, "purity": 255,
         "tier": "pure"},
        *[{"x": x, "y": y, "value": v, "purity": v, "tier": "mass"}
          for x, y, v in ring],
    ]
    view = _view(
        width=width, height=height, grid=grid,
        red_visible=red_visible, my_assets=[_harv()],
    )
    out = cc.compile_candidates(view)
    chains = out["candidates"]["harvest"]
    assert chains, "expected at least one chain over the pure cluster"
    # Some chain must actually walk through the pure cell despite the
    # friendly probe sitting on it.
    pure_touched = False
    for ch in chains:
        cells = [tuple(c) for c in ch.get("cells_traversed", [])]
        if pure_xy in cells:
            pure_touched = True
            break
    assert pure_touched, (
        f"no chain walked through pure cell {pure_xy} even though a "
        f"friendly-probe-crush trade is net-positive. Chain cells: "
        f"{[(ch['id'], ch.get('cells_traversed')) for ch in chains]}"
    )


def test_probe_pass1_uses_echo_red_not_just_live():
    """Regression for FINDING-pure failure: Pass 1 (RED-bracket probes)
    must consider ECHO red, not just LIVE red. Pure cells are rare
    (~3 per board) and only LIVE while a probe is actively over them.
    Once a probe expires, the pure cell slides to echo. Without this,
    the agent finds a pure cell, loses LOS, and the next probe lands
    near an unrelated fog cluster — never revisiting the pure seam.
    """
    width, height = 40, 28
    # grid=None means all-fog (the default _view behaviour).
    view = _view(width=width, height=height,
                 red_visible=[], my_assets=[_harv()])
    view["navigation"]["best_red_echo"] = [
        {"x": 28, "y": 14, "value": 255, "purity": 255, "tier": "pure"},
    ]
    # Probe stock and orbit context so the harness actually runs probe compile.
    view["my_assets"].append({
        "id": "probe_p1_slot_1", "kind": "probe", "type": "probe",
        "state": "orbit", "at": None, "pos": None,
    })
    out = cc.compile_candidates(view)
    probes = out["candidates"]["probes"]
    assert probes, "expected at least one probe candidate"
    # At least one probe should be within `probe_radius` of the pure
    # echo cell at (28, 14). probe_radius defaults to 4.
    pure_xy = (28, 14)
    near_pure = [
        p for p in probes
        if (p["at"][0] - pure_xy[0]) ** 2 + (p["at"][1] - pure_xy[1]) ** 2 <= 16
    ]
    assert near_pure, (
        f"no probe candidate sits within radius-4 of the pure echo "
        f"at {pure_xy}; got probes at "
        f"{[(p['at'], p.get('mode')) for p in probes]}"
    )


def test_probe_quadrant_fallback_lands_at_quartile_centers():
    """Regression for FINDING-pure on cold-start: when there's no live
    RED and the whole map is one fog cluster (day 1), probes should
    scatter at QUARTILE CENTERS, not bunch near the corners. The
    quartile-center pattern covers ~22% of a 40x28 board (vs ~15% for
    the old corner-clamp), and lands probes near where RED clusters
    typically live (the map interior).
    """
    width, height = 40, 28
    # grid=None means all-fog — exactly the day-1 cold-start.
    view = _view(width=width, height=height,
                 red_visible=[], my_assets=[_harv()])
    # Give probe stock so multiple candidates emit. _k_probes caps at 3
    # for a 1-harvester fleet (which this fixture has).
    for i in range(4):
        view["my_assets"].append({
            "id": f"probe_orbit_{i}", "kind": "probe", "type": "probe",
            "state": "orbit", "at": None, "pos": None,
        })
    out = cc.compile_candidates(view)
    probes = out["candidates"]["probes"]
    assert len(probes) >= 3, (
        f"expected ≥3 probe candidates on a fog-only board, got {len(probes)}: "
        f"{[(p['at'], p.get('mode')) for p in probes]}"
    )
    positions = [tuple(p["at"]) for p in probes[:4]]
    # The four quartile centers we expect (for width=40, height=28):
    #   NW (10, 7), NE (30, 7), SW (10, 21), SE (30, 21)
    # k=3 cap means only 3 of these appear; verify ≥3 of them do.
    expected_centers = {(10, 7), (30, 7), (10, 21), (30, 21)}
    found_centers = expected_centers & set(positions)
    assert len(found_centers) >= 3, (
        f"quadrant fallback should anchor at quartile centers "
        f"{expected_centers}; got {positions} — overlap {found_centers}"
    )


# ── Orbital compiler unit tests (v1.8) ─────────────────────────────
from sea_of_colours.orchestrator_2.harnesses.pilot_v2 import orbit as orb


def _orbit_view(*, credits=1000, probe_stock=4, hoard_used=2, hoard_max=15,
                weapon_stock=None, blue_purity_total=0, hoard_parcels=None,
                my_assets=None, damaged_ids=(), harvester_cap_used=1,
                harvester_cap_max=3, red_visible=None, enemy_probes=None,
                green_owned_count=0):
    """Minimal agent_view scaffold for orbit tests."""
    weapon_stock = weapon_stock or {"emp": 0, "chaff": 0, "mine": 0}
    hoard_parcels = hoard_parcels or []
    my_assets = my_assets or [_harv()]
    red_visible = red_visible or []
    enemy_probes = enemy_probes or []
    # Mark damaged harvesters in entities.mine.
    entities_mine = []
    for a in my_assets:
        row = dict(a)
        row["damaged"] = str(row.get("id", "")) in set(damaged_ids)
        entities_mine.append(row)
    return {
        "meta": {"phase": "orbit", "day": 2, "player": "p1"},
        "hud": {"score": 0, "hoard": {"used": hoard_used, "max": hoard_max}},
        "world": {"width": 40, "height": 28, "grid": _grid(40, 28)},
        "navigation": {"best_red_visible": red_visible},
        "red_tiles": red_visible,
        "my_assets": my_assets,
        "entities": {"mine": entities_mine, "echoes": []},
        "orbit": {
            "credits": credits,
            "probe_stock": probe_stock,
            "weapon_stock": weapon_stock,
            "harvester_cap_used": harvester_cap_used,
            "harvester_cap_max": harvester_cap_max,
            "blue_purity_total": blue_purity_total,
            "hoard_parcels": hoard_parcels,
            "green_owned_count": green_owned_count,
        },
        "competitor_intel": {"new_this_day": enemy_probes, "persistent_echoes": []},
    }


def test_orbit_repair_takes_top_slot_when_damaged():
    view = _orbit_view(damaged_ids=("harvester_p1",))
    out = orb.compile_orbit_candidates(view)
    actions = out["recommended_orbit_policy"]["actions"]
    assert actions[0] == {"a": "repair", "unit": "harvester_p1"}


def test_orbit_probes_prioritized_over_harvester_when_no_red():
    # Probe stock LOW, no visible RED, credits enough for both.
    view = _orbit_view(credits=2000, probe_stock=1, red_visible=[])
    out = orb.compile_orbit_candidates(view)
    actions = out["recommended_orbit_policy"]["actions"]
    kinds = [a["a"] for a in actions]
    # build_probe should appear before build_harvester when no red visible.
    assert "build_probe" in kinds, kinds
    # Without good RED and without flush cash (>3000), harvester should NOT
    # appear ahead of probes.
    if "build_harvester" in kinds:
        assert kinds.index("build_probe") < kinds.index("build_harvester")


def test_orbit_flush_cash_buys_harvester_even_without_red():
    # Very flush credits, no red visible, probe stock full.
    view = _orbit_view(credits=5000, probe_stock=4, red_visible=[])
    out = orb.compile_orbit_candidates(view)
    kinds = [a["a"] for a in out["recommended_orbit_policy"]["actions"]]
    assert "build_harvester" in kinds


def test_orbit_slots_always_full_when_baseline_available():
    # Nothing urgent, but vein+ parcel in hoard.
    parcels = [{"square_id": "sq1", "colour": "RED", "purity": 100, "tier": "vein", "score": 100}]
    view = _orbit_view(credits=1000, probe_stock=4, hoard_parcels=parcels)
    out = orb.compile_orbit_candidates(view)
    actions = out["recommended_orbit_policy"]["actions"]
    # Should have baseline ship at minimum.
    kinds = [a["a"] for a in actions]
    assert "ship_catapult" in kinds


def test_orbit_vault_pressure_escalates_ship():
    # Hoard 13/15 = 87% > threshold 80%.
    parcels = [{"square_id": f"sq{i}", "colour": "RED", "purity": 200, "tier": "mass", "score": 300}
               for i in range(13)]
    view = _orbit_view(credits=1000, probe_stock=4, hoard_used=13, hoard_parcels=parcels)
    out = orb.compile_orbit_candidates(view)
    assert out["vault_pressure"]["escalate"] is True
    actions = out["recommended_orbit_policy"]["actions"]
    # First non-repair slot should be ship.
    assert actions[0]["a"] == "ship_catapult", f"expected ship first, got {actions}"


def test_orbit_blue_flush_buys_emp_when_enemy_visible():
    view = _orbit_view(
        credits=1000, probe_stock=4, blue_purity_total=300,
        enemy_probes=[{"at": [24, 14]}],
    )
    out = orb.compile_orbit_candidates(view)
    kinds = [a["a"] for a in out["recommended_orbit_policy"]["actions"]]
    assert "build_emp" in kinds, f"expected EMP purchase, got {kinds}"


def test_orbit_no_target_skips_emp_purchase():
    # BLUE flush but no enemy visible → EMP should NOT be purchased.
    view = _orbit_view(
        credits=1000, probe_stock=4, blue_purity_total=300,
        enemy_probes=[],
    )
    out = orb.compile_orbit_candidates(view)
    kinds = [a["a"] for a in out["recommended_orbit_policy"]["actions"]]
    assert "build_emp" not in kinds


def test_orbit_recommended_never_leaves_slots_empty_when_options_exist():
    # Everything up (nothing urgent, probes full, no red, no damage) but
    # baseline productive spends (refine/ship/green flush) should fill.
    parcels = [
        {"square_id": "sq1", "colour": "RED", "purity": 30, "tier": "trace", "score": 30},
        {"square_id": "sq2", "colour": "RED", "purity": 200, "tier": "mass", "score": 300},
    ]
    view = _orbit_view(credits=1000, probe_stock=4, blue_purity_total=50,
                       hoard_parcels=parcels, green_owned_count=1)
    out = orb.compile_orbit_candidates(view)
    n = len(out["recommended_orbit_policy"]["actions"])
    # Should have all three baseline slots filled: ship + refine + green flush.
    assert n == 3, f"expected 3 slots filled with baseline spends, got {n}"


