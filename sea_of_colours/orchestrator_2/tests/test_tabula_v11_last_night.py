"""Tests for the v11 MEMORY OF LAST NIGHT block (harness-only rebuild).

Covers the observer-visibility filter on the replay-frame-sourced execution log,
order extraction from the opening frame, engine-scored actual-yield aggregation,
the rendered block (orders/expected, a FAILED line, R/B/G actual-vs-expected,
what-you-saw), the day-1 / no-frames degrade path, and the harness expected-yield
stamp.
"""

from __future__ import annotations

from types import SimpleNamespace

from sea_of_colours.orchestrator_2.harnesses.tabula_v11 import (
    digest,
    harness as v11h,
    last_night as ln,
)


# ── fixtures ────────────────────────────────────────────────────────────────
WIDTH, HEIGHT = 4, 2  # 8 cells, row-major index = y * WIDTH + x


def _cells(visible_indices):
    """A row-major cells_player list: terrain at ``visible_indices``, else fog."""
    return [
        {"kind": "terrain"} if i in visible_indices else {"kind": "fog"}
        for i in range(WIDTH * HEIGHT)
    ]


def _opening_frame():
    return {
        "tag": "open",
        "owner": None,
        "hour": 0,
        "scheduled_orders": {
            "p1": [
                {"idx": 0, "label": "drop harvester_p1 @(0,0)",
                 "action": "drop", "unit": "harvester_p1", "target": [0, 0]},
                {"idx": 1, "label": "probe @(3,1)", "action": "probe",
                 "target": [3, 1]},
                {"idx": 2, "label": "invalid policy entry", "action": "invalid",
                 "reason": "bad"},
            ],
            "p2": [
                {"idx": 0, "label": "drop harvester_p2 @(2,1)",
                 "action": "drop", "unit": "harvester_p2", "target": [2, 1]},
            ],
        },
    }


def _frames():
    return [
        _opening_frame(),
        # own drop, ok
        {"tag": "drop", "owner": "p1", "hour": 1,
         "attempted": "drop harvester_p1 @(0,0)", "outcome": "ok",
         "caption": "p1: dropped harvester_p1 @(0,0)"},
        # enemy probe launch — PUBLIC, always shown (no vision needed)
        {"tag": "probe", "owner": "p2", "hour": 2,
         "attempted": "probe @(3,1)", "outcome": "ok",
         "caption": "p2: probe @(3,1)"},
        # own step FAILED
        {"tag": "waste", "owner": "p1", "hour": 3,
         "attempted": "step harvester_p1 → (2,0)", "outcome": "failed",
         "caption": "p1: step harvester_p1 → (2,0) — not adjacent"},
        # enemy step at (1,0) [idx 1] — INSIDE p1 vision -> shown
        {"tag": "step", "owner": "p2", "hour": 4,
         "attempted": "step harvester_p2 → (1,0)", "outcome": "ok",
         "caption": "p2: step harvester_p2 → (1,0)",
         "cells_player_p1": _cells({1})},
        # enemy step at (3,0) [idx 3] — OUTSIDE p1 vision -> withheld
        {"tag": "step", "owner": "p2", "hour": 5,
         "attempted": "step harvester_p2 → (3,0)", "outcome": "ok",
         "caption": "p2: step harvester_p2 → (3,0)",
         "cells_player_p1": _cells({1})},
    ]


def _agent_view():
    return {
        "meta": {"seat": "p1"},
        "world": {"width": WIDTH, "height": HEIGHT, "live": []},
        "last_night": {
            "day_ended": 3,
            "my_parcels_banked": [
                {"tile": "RED", "purity": 255, "from": [0, 0]},
                {"tile": "RED", "purity": 100, "from": [1, 0]},
                {"tile": "BLUE", "purity": 80, "from": [2, 0]},
                {"tile": "GREEN", "purity": 0, "from": [3, 0]},
            ],
            "incoming_attacks": [],
            "my_denials": [],
        },
    }


# ── execution-log visibility filter ─────────────────────────────────────────
def test_execution_log_own_always_included_with_outcome():
    log = ln.read_execution_log(_frames(), "p1", width=WIDTH, height=HEIGHT)
    own = [e for e in log if e["kind"] == "own"]
    assert {e["tag"] for e in own} == {"drop", "waste"}
    failed = [e for e in own if e["outcome"] == "failed"]
    assert len(failed) == 1
    assert failed[0]["cell"] == (2, 0)
    assert "not adjacent" in failed[0]["reason"]


def test_execution_log_enemy_probe_is_public():
    log = ln.read_execution_log(_frames(), "p1", width=WIDTH, height=HEIGHT)
    orbital = [e for e in log if e["kind"] == "orbital"]
    assert len(orbital) == 1
    assert orbital[0]["tag"] == "probe"
    assert orbital[0]["cell"] == (3, 1)


def test_execution_log_enemy_field_gated_by_vision():
    log = ln.read_execution_log(_frames(), "p1", width=WIDTH, height=HEIGHT)
    enemy = [e for e in log if e["kind"] == "enemy"]
    # Only the in-vision step at (1,0) survives; the (3,0) step is withheld.
    assert len(enemy) == 1
    assert enemy[0]["cell"] == (1, 0)
    assert enemy[0]["hour"] == 4


def test_execution_log_withholds_enemy_when_snapshot_missing():
    frames = [
        {"tag": "step", "owner": "p2", "hour": 4,
         "attempted": "step harvester_p2 → (1,0)", "outcome": "ok"},
    ]
    log = ln.read_execution_log(frames, "p1", width=WIDTH, height=HEIGHT)
    assert [e for e in log if e["kind"] == "enemy"] == []


# ── orders ──────────────────────────────────────────────────────────────────
def test_read_orders_from_opening_frame_skips_invalid():
    orders = ln.read_orders(_frames(), "p1")
    assert orders == ["drop harvester_p1 @(0,0)", "probe @(3,1)"]


def _frames_with_hoard():
    """Frames whose OPEN hoard holds one old parcel and DAWN holds two new ones.

    Reproduces the reported bug: the view's ``my_parcels_banked`` is empty even
    though the hoard clearly grew last night. The dawn−open delta is the truth.
    """
    open_f = _opening_frame()
    open_f["hoard"] = {"p1": {"count": 1, "sites": [
        {"id": "s_old", "cell": [9, 9], "tile_at_harvest": 2, "purity_at_harvest": 50},
    ]}}
    dawn = {"tag": "dawn", "owner": None, "hour": 22,
            "hoard": {"p1": {"count": 3, "sites": [
                {"id": "s_old", "cell": [9, 9], "tile_at_harvest": 2,
                 "purity_at_harvest": 50},
                {"id": "s_new1", "cell": [0, 0], "tile_at_harvest": 2,
                 "purity_at_harvest": 255},
                {"id": "s_new2", "cell": [1, 0], "tile_at_harvest": 3,
                 "purity_at_harvest": 80},
            ]}}}
    return [open_f, *_frames()[1:], dawn]


# ── actual yield ────────────────────────────────────────────────────────────
def test_actual_yield_scores_with_engine_model():
    act = ln.actual_yield(_agent_view())
    # pure(255): (255-10)*3.0=735 ; vein(100): (100-10)*1.0=90 -> 825
    assert act["red_pts"] == 825
    assert act["red_tiers"] == {"pure": 1, "vein": 1}
    assert act["blue_fissile"] == 80
    assert act["green_penalty"] == -100
    assert act["parcels"] == 4


def test_banked_from_frames_diffs_hoard_by_id():
    new = ln.banked_from_frames(_frames_with_hoard(), "p1")
    assert {s["id"] for s in new} == {"s_new1", "s_new2"}


def test_actual_yield_prefers_hoard_delta_over_empty_view_channel():
    av = _agent_view()
    av["last_night"]["my_parcels_banked"] = []  # the bug: view channel empty
    act = ln.actual_yield(av, _frames_with_hoard(), "p1")
    assert act["parcels"] == 2                       # only the two NEW parcels
    assert act["red_pts"] == 735                     # pure(255): (255-10)*3.0
    assert act["red_tiers"] == {"pure": 1}
    assert act["blue_fissile"] == 80


def test_actual_yield_falls_back_to_view_without_hoard_delta():
    # Frames present but no hoard growth -> use my_parcels_banked as before.
    act = ln.actual_yield(_agent_view(), _frames(), "p1")
    assert act["red_pts"] == 825


# ── full block ──────────────────────────────────────────────────────────────
def test_build_and_format_block():
    prior = {"day": 3, "expected_yield": {
        "red_pts": 255, "blue_fissile": 120, "green_penalty": 0}}
    mem = ln.build(_frames(), _agent_view(), prior, day=4)
    block = ln.format_block(mem)
    assert "LAST NIGHT (day 3)" in block
    assert "drop harvester_p1 @(0,0)" in block          # order
    assert "expected: red ~+255" in block                # committed expectation
    assert "FAILED" in block                             # the failed step
    assert "red +825" in block                           # actual, engine-scored
    assert "[exp ~+255]" in block                        # side-by-side
    assert "WHAT YOU SAW" in block                       # enemy/orbital section
    assert "launched a probe" in block                   # public orbital line
    assert "REFLECT" in block


def test_block_includes_prior_intent_and_banked_red():
    prior = {"day": 3,
             "intent": "Grab the (0,0) jackpot then strip the east seam.",
             "expected_yield": {"red_pts": 255}}
    av = _agent_view()
    av["last_night"]["my_parcels_banked"] = []  # view channel empty (the bug)
    mem = ln.build(_frames_with_hoard(), av, prior, day=4)
    assert mem["intent"].startswith("Grab the (0,0) jackpot")
    block = ln.format_block(mem)
    assert "YOUR INTENT WAS:" in block
    assert "Grab the (0,0) jackpot" in block
    assert "red +735" in block                      # banked red now shows
    assert "2 parcel(s) banked" in block


def test_build_degrades_without_frames():
    av = _agent_view()
    av["last_night"]["my_orders"] = [
        {"text": "p1: drop harvester_p1 @(5,5)", "outcome": "ok"},
    ]
    mem = ln.build([], av, None, day=4)
    assert mem["degraded"] is True
    own = [e for e in mem["execution_log"] if e["kind"] == "own"]
    assert own and own[0]["cell"] == (5, 5)
    block = ln.format_block(mem)
    assert "reconstructed from the summary channels" in block


# ── per-step harvest annotation (grounds reflection, kills the green-wake
#    hallucination where the agent read its OWN harvest wake as a -100 penalty) ──
def test_execution_log_annotates_drop_with_banked_red_and_wake():
    block = ln.format_block(ln.build(_frames(), _agent_view(), None, day=4))
    assert "H01 drop (0,0)" in block
    # the drop auto-harvested the pure at (0,0): show the value it BANKED and that
    # the cell is now the agent's own (harmless) green wake — not a penalty.
    assert (
        "harvested RED value 735 (pure p255) — now SYNTHETIC-GREEN in your wake"
        in block
    )


def test_failed_step_gets_no_harvest_annotation():
    mem = ln.build(_frames(), _agent_view(), None, day=4)
    failed = [
        e for e in mem["execution_log"]
        if e["kind"] == "own" and e["outcome"] == "failed"
    ]
    assert failed and "harvest" not in failed[0]


def test_fmt_harvest_variants():
    assert "harvested RED value 735 (pure p255)" in ln._fmt_harvest(
        {"tile": "RED", "purity": 255})
    assert "harvested BLUE 80 fissile" in ln._fmt_harvest(
        {"tile": "BLUE", "purity": 80})
    assert "-100" in ln._fmt_harvest({"tile": "GREEN", "purity": 0})


def test_clean_red_walk_never_reads_as_a_green_penalty():
    """The reported bug: a night that banked only RED (green 0) but whose cells
    are green NOW (the harvester's own wake). Each step must annotate as a RED
    harvest — nothing in the block may read as a -100 green penalty."""
    frames = [
        {"tag": "open", "owner": None, "hour": 0, "scheduled_orders": {"p1": [
            {"idx": 0, "label": "drop harvester_p1 @(0,0)", "action": "drop",
             "unit": "harvester_p1", "target": [0, 0]}]}},
        {"tag": "drop", "owner": "p1", "hour": 1,
         "attempted": "drop harvester_p1 @(0,0)", "outcome": "ok"},
        {"tag": "step", "owner": "p1", "hour": 2,
         "attempted": "step harvester_p1 → (1,0)", "outcome": "ok"},
    ]
    view = {
        "meta": {"seat": "p1"},
        "world": {"width": WIDTH, "height": HEIGHT, "live": []},
        "last_night": {"day_ended": 2, "incoming_attacks": [], "my_denials": [],
                       "my_parcels_banked": [
                           {"tile": "RED", "purity": 165, "from": [0, 0]},
                           {"tile": "RED", "purity": 103, "from": [1, 0]}]},
    }
    block = ln.format_block(ln.build(frames, view, None, day=3))
    assert "green 0" in block                       # zero green banked
    assert "-100" not in block                       # nothing reads as a penalty
    assert "harvested RED value 93 (vein p103)" in block  # (103-10)*1.0


# ── harness expected-yield stamp (from the COMPILED route) ──────────────────
def test_harness_expected_yield_from_compiled_moves():
    # Expected is now scored over the ACTUAL compiled drop/step cells, so it can
    # never over-credit a run the packager dropped (the day-2 gap).
    av = {
        "world": {
            "width": WIDTH, "height": HEIGHT,
            "live": [
                {"x": 0, "y": 0, "tile": "RED", "purity": 255},
                {"x": 1, "y": 0, "tile": "RED", "purity": 100},
            ],
        },
    }
    moves = [
        {"a": "drop", "unit": "h", "at": [0, 0]},
        {"a": "step", "unit": "h", "to": [1, 0]},
        {"a": "pickup", "unit": "h"},
    ]
    exp = v11h._expected_yield_from_moves(moves, av)
    assert exp["red_pts"] == 825  # (255-10)*3.0 + (100-10)*1.0
    assert exp["blue_fissile"] == 0
    assert exp["green_penalty"] == 0


def test_harness_expected_yield_ignores_dropped_run():
    # A drop the packager never emitted contributes nothing to expected.
    av = {
        "world": {
            "width": WIDTH, "height": HEIGHT,
            "live": [{"x": 5, "y": 5, "tile": "RED", "purity": 255}],
        },
    }
    # No drop/step touches (5,5) -> expected red is 0, matching a route that
    # never visits the rich cell.
    moves = [{"a": "probe", "at": [5, 5]}]
    exp = v11h._expected_yield_from_moves(moves, av)
    assert exp["red_pts"] == 0


# ── reconciliation report (PLAN -> COMPILED -> DROPPED) ─────────────────────
def test_last_night_renders_dropped_runs_from_reconciliation():
    prior = {
        "expected_yield": {"red_pts": 461, "blue_fissile": 0, "green_penalty": 0},
        "reconciliation": [
            {"id": "CH1", "kind": "chain", "status": "kept", "value": 461,
             "reason": ""},
            {"id": "GRAB1", "kind": "grab", "status": "dropped", "value": 201,
             "reason": "only 1 harvester(s) alive and each makes ONE outing/night "
                       "(RULEBOOK §3.9.2) — kept the higher-value run(s)"},
        ],
    }
    mem = ln.build([], {"last_night": {"day_ended": 2}}, prior, day=3)
    assert any(r.get("status") == "dropped" for r in mem["reconciliation"])
    block = ln.format_block(mem)
    assert "PACKAGER RECONCILED YOUR PLAN" in block
    assert "DROPPED [GRAB1]" in block
    assert "one outing" in block.lower() or "§3.9.2" in block


def test_last_night_no_reconciliation_section_when_nothing_dropped():
    prior = {"reconciliation": [
        {"id": "CH1", "kind": "chain", "status": "kept", "value": 461, "reason": ""},
    ]}
    mem = ln.build([], {"last_night": {"day_ended": 2}}, prior, day=3)
    block = ln.format_block(mem)
    assert "PACKAGER RECONCILED YOUR PLAN" not in block


# ── asset-destruction surfacing (my_assets_destroyed) ───────────────────────
def test_narrate_losses_surfaces_lost_harvester():
    av = {
        "last_night": {
            "my_assets_destroyed": [
                {"id": "harvester_p1_2", "kind": "harvester", "at": [4, 4],
                 "reason": "aurora_strand"},
            ],
        },
    }
    lines = digest.narrate_losses(av)
    assert lines and "harvester_p1_2" in lines[0]
    assert "LOST" in lines[0]
    assert "SPILLED" in lines[0] or "spill" in lines[0].lower()


def test_what_you_saw_includes_lost_harvester():
    av = {
        "last_night": {
            "my_assets_destroyed": [
                {"id": "harvester_p1_2", "kind": "harvester", "at": [4, 4],
                 "reason": "aurora_strand"},
            ],
        },
    }
    lines = ln._what_you_saw(av, [])
    assert any("harvester_p1_2" in ln_ and "LOST" in ln_ for ln_ in lines)
