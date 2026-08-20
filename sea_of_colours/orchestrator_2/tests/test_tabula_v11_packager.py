"""R1 — deterministic packager (compiler back-end) unit tests.

Locks the guarantees that motivate dropping the LLM executor: coordinate
faithfulness, one-drop-per-unit (multi-drop impossible), contiguous Manhattan-1
steps, probe/harvester budgeting, and the completion/utilization pass.
"""

from __future__ import annotations

from sea_of_colours.orchestrator_2.harnesses.tabula_v11.agency import Option
from sea_of_colours.orchestrator_2.harnesses.tabula_v11 import packager


def _view(harvesters: int = 2, stock: int = 3):
    return {
        "orbit": {"probe_stock": stock},
        "my_assets": [
            {"id": f"harvester_p1_{i + 1}", "kind": "harvester", "state": "orbit"}
            for i in range(harvesters)
        ],
    }


def _seam(waves):
    return Option(
        option_id="SMASH_GRAB", kind="seam", title="t", detail="d",
        execute_lines=[], payload={"waves": waves},
    )


def _drops(moves):
    return [m for m in moves if m.get("a") == "drop"]


def _probes(moves):
    return [m for m in moves if m.get("a") == "probe"]


def _assert_steps_contiguous(moves):
    """Every step is exactly Manhattan-1 from the unit's previous cell."""
    pos = {}
    for m in moves:
        u = m.get("unit")
        if m.get("a") == "drop":
            pos[u] = tuple(m["at"])
        elif m.get("a") == "step":
            px, py = pos[u]
            nx, ny = m["to"]
            assert abs(nx - px) + abs(ny - py) == 1, (px, py, nx, ny)
            pos[u] = (nx, ny)


def _hotdrop(drop, comb, group="HD1"):
    return Option(
        option_id=group, kind="hotdrop", title="t", detail="d",
        execute_lines=[],
        payload={"drop_at": drop, "comb_path": comb, "group": group},
    )


def test_two_shape_variants_of_same_drop_do_not_double_deploy():
    # Thinker picks two comb-shape variants of the SAME drop cell -> the second
    # must be refused (self-collision), only one harvester consumed.
    stretch = _hotdrop([10, 10], [[11, 10], [12, 10]])
    sample = _hotdrop([10, 10], [[10, 11]])
    moves, log = packager.pack_recipe([stretch, sample], _view(harvesters=2))
    drops = _drops(moves)
    assert len(drops) == 1
    assert any("already has a drop" in ln for ln in log)


def test_distinct_drops_both_deploy():
    a = _hotdrop([10, 10], [[11, 10]])
    b = _hotdrop([20, 20], [[21, 20]])
    moves, _ = packager.pack_recipe([a, b], _view(harvesters=2))
    assert len(_drops(moves)) == 2


def test_seam_two_waves_distinct_units_and_probes_spent():
    waves = [
        {"wave": 1, "earliest_hour": 1, "drop_at": [10, 10],
         "comb_path": [[11, 10], [12, 10]], "probe_at": [9, 9],
         "supersede": [8, 8], "unit_ordinal": 0},
        {"wave": 2, "earliest_hour": 9, "drop_at": [14, 14],
         "comb_path": [], "probe_at": [13, 13], "supersede": None,
         "unit_ordinal": 1},
    ]
    moves, log = packager.pack_recipe([_seam(waves)], _view(harvesters=2, stock=3))
    drops = _drops(moves)
    assert [d["at"] for d in drops] == [[10, 10], [14, 14]]
    # Two DISTINCT harvesters — never a double-drop on one unit.
    assert len({d["unit"] for d in drops}) == 2
    # supersede (8,8) + enabler (9,9) + wave-2 probe (13,13) all launched.
    assert [p["at"] for p in _probes(moves)] == [[8, 8], [9, 9], [13, 13]]
    _assert_steps_contiguous(moves)
    # drop -> steps -> pickup ordering for wave 1.
    kinds = [m["a"] for m in moves if m.get("unit") == drops[0]["unit"]]
    assert kinds == ["drop", "step", "step", "pickup"]


def test_multi_drop_impossible_when_units_run_short():
    # Three waves but only ONE harvester alive → waves 2/3 are CUT, never a
    # second drop on the same unit (the mirror-d6 21-move hallucination class).
    waves = [
        {"wave": i, "earliest_hour": i, "drop_at": [10 + i, 10],
         "comb_path": [], "probe_at": None, "supersede": None,
         "unit_ordinal": i - 1}
        for i in (1, 2, 3)
    ]
    moves, log = packager.pack_recipe([_seam(waves)], _view(harvesters=1, stock=0))
    drops = _drops(moves)
    assert len(drops) == 1
    assert len({d["unit"] for d in drops}) == 1
    assert any("cut seam wave" in line for line in log)


def test_steps_interpolated_to_manhattan_1():
    # comb cell two cells away from the drop → packager interpolates the gap.
    waves = [{"wave": 1, "earliest_hour": 1, "drop_at": [10, 10],
              "comb_path": [[10, 12]], "probe_at": None, "supersede": None,
              "unit_ordinal": 0}]
    moves, _ = packager.pack_recipe([_seam(waves)], _view(harvesters=1, stock=0))
    steps = [tuple(m["to"]) for m in moves if m.get("a") == "step"]
    assert steps == [(10, 11), (10, 12)]
    _assert_steps_contiguous(moves)


def test_probe_budget_respected():
    pr1 = Option("PR1", "probe", "t", "d", [], {"at": [1, 1]})
    pr2 = Option("PR2", "probe", "t", "d", [], {"at": [2, 2]})
    moves, log = packager.pack_recipe(
        [pr1, pr2], _view(harvesters=0, stock=1), complete=False,
    )
    assert [p["at"] for p in _probes(moves)] == [[1, 1]]
    assert any("cut probe" in line for line in log)


def test_chain_and_supersede_compile():
    ch = Option("CH1", "chain", "t", "d", [],
                {"drop_at": [4, 4], "cells": [[5, 4]]})
    ss = Option("SS1", "supersede", "t", "d", [], {"probe_at": [7, 7]})
    moves, _ = packager.pack_recipe(
        [ch, ss], _view(harvesters=1, stock=1), complete=False,
    )
    assert _drops(moves)[0]["at"] == [4, 4]
    assert [p["at"] for p in _probes(moves)] == [[7, 7]]


def test_completion_deploys_idle_harvester_and_spends_probes():
    # One chain uses harvester #1; #2 is idle → completion deploys it on the
    # offered chain hint, and the leftover probe lands on the offered supersede.
    ch = Option("CH1", "chain", "t", "d", [],
                {"drop_at": [20, 20], "cells": []})
    moves, log = packager.pack_recipe(
        [ch], _view(harvesters=2, stock=1),
        chain_hints=[{"drop_at": [5, 5], "cells": [[6, 5]]}],
        supersede_hints=[{"probe_at": [7, 7]}],
    )
    drops = _drops(moves)
    assert {tuple(d["at"]) for d in drops} == {(20, 20), (5, 5)}
    assert len({d["unit"] for d in drops}) == 2
    assert [7, 7] in [p["at"] for p in _probes(moves)]
    assert any("completion" in line for line in log)


def test_completion_never_double_uses_a_drop_cell():
    # The chain hint duplicates the already-used drop cell → completion must NOT
    # re-drop it (no idle chain available) so the idle unit simply stays orbital.
    ch = Option("CH1", "chain", "t", "d", [], {"drop_at": [5, 5], "cells": []})
    moves, _ = packager.pack_recipe(
        [ch], _view(harvesters=2, stock=0),
        chain_hints=[{"drop_at": [5, 5], "cells": []}],
    )
    assert len(_drops(moves)) == 1


def test_no_recipe_returns_empty():
    moves, log = packager.pack_recipe([], _view())
    assert moves == []


# ── Part A1: persistent stripped/GREEN guard ────────────────────────────
def test_forbidden_drop_cell_refuses_whole_chain():
    # The landing cell is a known stripped/GREEN cell (survives fog) -> the whole
    # chain is refused, no harvester burned on a guaranteed green penalty.
    hd = _hotdrop([10, 10], [[11, 10]])
    moves, log = packager.pack_recipe(
        [hd], _view(harvesters=1), forbidden_cells={(10, 10)},
    )
    assert _drops(moves) == []
    assert any("known stripped/GREEN" in ln for ln in log)


def test_forbidden_step_truncates_walk_and_still_picks_up():
    # Drop is fine, but the walk would step onto a known GREEN cell -> bank what
    # we hold and stop before it (never step onto the penalty), keep the pickup.
    waves = [{"wave": 1, "earliest_hour": 1, "drop_at": [10, 10],
              "comb_path": [[13, 10]], "probe_at": None, "supersede": None,
              "unit_ordinal": 0}]
    moves, log = packager.pack_recipe(
        [_seam(waves)], _view(harvesters=1, stock=0),
        forbidden_cells={(12, 10)},
    )
    steps = [tuple(m["to"]) for m in moves if m.get("a") == "step"]
    assert steps == [(11, 10)]  # stopped before the forbidden (12,10)
    assert moves[-1]["a"] == "pickup"
    assert any("truncate walk" in ln for ln in log)


def test_no_forbidden_cells_is_a_no_op():
    hd = _hotdrop([10, 10], [[11, 10]])
    a, _ = packager.pack_recipe([hd], _view(harvesters=1))
    b, _ = packager.pack_recipe([hd], _view(harvesters=1), forbidden_cells=set())
    assert a == b


# ── Part A2: contested sweep steps only onto live-red cells ─────────────
def test_contested_sweep_truncates_at_first_fogged_step():
    # A contested blind-grab: the drop lands on the confirmed core, but its
    # sweep would step onto a fogged neighbour (not live-red) -> stop there
    # rather than blind-walk onto a cell the rival may have stripped to green.
    waves = [{"wave": 1, "earliest_hour": 1, "drop_at": [10, 10],
              "comb_path": [[13, 10]], "probe_at": None, "supersede": None,
              "contested": True, "unit_ordinal": 0}]
    moves, log = packager.pack_recipe(
        [_seam(waves)], _view(harvesters=1, stock=0),
        live_red_cells={(10, 10), (11, 10)},  # (12,10)/(13,10) are fogged
    )
    steps = [tuple(m["to"]) for m in moves if m.get("a") == "step"]
    assert steps == [(11, 10)]  # stopped before the fogged (12,10)
    assert moves[-1]["a"] == "pickup"
    assert any("contested walk" in ln and "not live-red" in ln for ln in log)


def test_contested_sweep_keeps_all_live_red_steps():
    waves = [{"wave": 1, "earliest_hour": 1, "drop_at": [10, 10],
              "comb_path": [[12, 10]], "probe_at": None, "supersede": None,
              "contested": True, "unit_ordinal": 0}]
    moves, _ = packager.pack_recipe(
        [_seam(waves)], _view(harvesters=1, stock=0),
        live_red_cells={(10, 10), (11, 10), (12, 10)},
    )
    steps = [tuple(m["to"]) for m in moves if m.get("a") == "step"]
    assert steps == [(11, 10), (12, 10)]  # every step is confirmed live-red


def test_blind_walk_wave_steps_through_fog_but_refuses_known_green():
    # v11 CASE-2 attack: a BLIND_WALK wave deliberately combs a FOGGED rival seam,
    # so it steps onto cells that are NOT live-red (fog) — the live-red gate does
    # not apply. It still refuses a KNOWN stripped/green cell (hazard memory).
    waves = [{"wave": 1, "earliest_hour": 1, "drop_at": [10, 10],
              "comb_path": [[14, 10]], "probe_at": None, "supersede": None,
              "blind_walk": True, "contested": True, "unit_ordinal": 0}]
    moves, log = packager.pack_recipe(
        [_seam(waves)], _view(harvesters=1, stock=0),
        live_red_cells={(10, 10)},        # neighbours are fog — walked anyway
        forbidden_cells={(13, 10)},        # ...except the known-green cell
    )
    steps = [tuple(m["to"]) for m in moves if m.get("a") == "step"]
    assert steps == [(11, 10), (12, 10)]   # walked fog, stopped before known-green
    assert moves[-1]["a"] == "pickup"
    assert any("known stripped/GREEN" in ln for ln in log)


def test_non_contested_wave_ignores_live_red_gate():
    # A non-contested (own-seam) wave sweeps freely — the live-red gate is only
    # for contested rival blind grabs, so a fogged step is fine here.
    waves = [{"wave": 1, "earliest_hour": 1, "drop_at": [10, 10],
              "comb_path": [[12, 10]], "probe_at": None, "supersede": None,
              "contested": False, "unit_ordinal": 0}]
    moves, _ = packager.pack_recipe(
        [_seam(waves)], _view(harvesters=1, stock=0),
        live_red_cells={(10, 10)},  # neighbours fogged, but wave isn't contested
    )
    steps = [tuple(m["to"]) for m in moves if m.get("a") == "step"]
    assert steps == [(11, 10), (12, 10)]


# ── Part C: thinker chaff_react caps every chain (early lift) ───────────
def test_chaff_short_caps_chain_and_still_picks_up():
    waves = [{"wave": 1, "earliest_hour": 1, "drop_at": [10, 10],
              "comb_path": [[16, 10]], "probe_at": None, "supersede": None,
              "unit_ordinal": 0}]
    moves, log = packager.pack_recipe(
        [_seam(waves)], _view(harvesters=1, stock=0), chaff_short=True,
    )
    steps = [tuple(m["to"]) for m in moves if m.get("a") == "step"]
    assert len(steps) == packager._CHAFF_STEP_CAP  # capped, not the full run
    assert moves[-1]["a"] == "pickup"
    assert any("chaff_react" in ln for ln in log)


def test_chaff_short_off_rides_full_chain():
    waves = [{"wave": 1, "earliest_hour": 1, "drop_at": [10, 10],
              "comb_path": [[16, 10]], "probe_at": None, "supersede": None,
              "unit_ordinal": 0}]
    moves, _ = packager.pack_recipe(
        [_seam(waves)], _view(harvesters=1, stock=0), chaff_short=False,
    )
    steps = [tuple(m["to"]) for m in moves if m.get("a") == "step"]
    assert len(steps) > packager._CHAFF_STEP_CAP


# ── Part B: deny-only seam wave (confirm+deny, no harvester drop) ────────
def test_deny_only_seam_wave_spends_probes_but_drops_no_harvester():
    waves = [{"wave": 1, "earliest_hour": 1, "drop_at": [10, 10],
              "comb_path": [], "probe_at": [12, 10], "supersede": [10, 10],
              "deny_only": True, "unit_ordinal": 0}]
    moves, _ = packager.pack_recipe(
        [_seam(waves)], _view(harvesters=2, stock=3), complete=False,
    )
    # No harvester committed — only the supersede + confirm probe fire.
    assert _drops(moves) == []
    assert [p["at"] for p in _probes(moves)] == [[10, 10], [12, 10]]


# ── RULEBOOK §3.9.2: value-based inventory reconciliation ────────────────────
def _view_live(harvesters=1, stock=2, live=None):
    return {
        "orbit": {"probe_stock": stock},
        "world": {"width": 40, "height": 28, "live": list(live or [])},
        "my_assets": [
            {"id": f"harvester_p1_{i + 1}", "kind": "harvester", "state": "orbit"}
            for i in range(harvesters)
        ],
    }


def test_reconcile_keeps_higher_value_run_when_harvesters_short():
    # The day-2 gap: one harvester, two runs selected. The packager must keep
    # the RICHER run (CH1 red) and drop the lower-value one (GRAB1 blue) — NOT
    # cut by plan order.
    live = [
        {"x": 8, "y": 5, "tile": "RED", "purity": 255},   # CH1: pure red, huge
        {"x": 8, "y": 0, "tile": "BLUE", "purity": 402},  # GRAB1: blue fissile
    ]
    av = _view_live(harvesters=1, stock=2, live=live)
    grab = Option("GRAB1", "grab", "t", "d", [], {"drop_at": [8, 0], "cells": [[8, 0]]})
    ch = Option("CH1", "chain", "t", "d", [], {"drop_at": [8, 5], "cells": [[8, 5]]})
    # Plan order puts GRAB1 first (the old code would keep GRAB1, drop CH1).
    kept, report = packager.reconcile_selected([grab, ch], av)
    assert {o.option_id for o in kept} == {"CH1"}
    dropped = [r for r in report if r["status"] == "dropped"]
    assert [r["id"] for r in dropped] == ["GRAB1"]
    assert "one outing" in dropped[0]["reason"].lower() or "harvester" in dropped[0]["reason"]


def test_reconcile_no_op_when_inventory_sufficient():
    live = [{"x": 8, "y": 5, "tile": "RED", "purity": 255}]
    av = _view_live(harvesters=2, stock=2, live=live)
    grab = Option("GRAB1", "grab", "t", "d", [], {"drop_at": [8, 0], "cells": [[8, 0]]})
    ch = Option("CH1", "chain", "t", "d", [], {"drop_at": [8, 5], "cells": [[8, 5]]})
    kept, report = packager.reconcile_selected([grab, ch], av)
    assert {o.option_id for o in kept} == {"GRAB1", "CH1"}
    assert all(r["status"] == "kept" for r in report)


def test_reconcile_caps_probes_to_best_by_promise():
    av = _view_live(harvesters=0, stock=1, live=[])
    p_lo = Option("PR1", "probe", "t", "d", [], {"at": [1, 1], "edge_promise": 50})
    p_hi = Option("PR2", "probe", "t", "d", [], {"at": [2, 2], "edge_promise": 400})
    kept, report = packager.reconcile_selected([p_lo, p_hi], av)
    assert {o.option_id for o in kept} == {"PR2"}
    dropped = [r for r in report if r["status"] == "dropped"]
    assert [r["id"] for r in dropped] == ["PR1"]


def test_reconcile_end_to_end_drops_lower_value_run_from_moves():
    live = [
        {"x": 8, "y": 5, "tile": "RED", "purity": 255},
        {"x": 8, "y": 0, "tile": "BLUE", "purity": 402},
    ]
    av = _view_live(harvesters=1, stock=0, live=live)
    grab = Option("GRAB1", "grab", "t", "d", [], {"drop_at": [8, 0], "cells": [[8, 0]]})
    ch = Option("CH1", "chain", "t", "d", [], {"drop_at": [8, 5], "cells": [[8, 5]]})
    kept, _report = packager.reconcile_selected([grab, ch], av)
    moves, _log = packager.pack_recipe(kept, av, complete=False)
    # Only the richer CH1 (8,5) is compiled — one harvester, one outing.
    assert [d["at"] for d in _drops(moves)] == [[8, 5]]
