"""R1 — deterministic packager (compiler back-end) unit tests.

Locks the guarantees that motivate dropping the LLM executor: coordinate
faithfulness, one-drop-per-unit (multi-drop impossible), contiguous Manhattan-1
steps, probe/harvester budgeting, and the completion/utilization pass.
"""

from __future__ import annotations

from sea_of_colours.orchestrator_2.harnesses.tabula_v10.agency import Option
from sea_of_colours.orchestrator_2.harnesses.tabula_v10 import packager


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
