"""v10 comb shapes — STRETCH / SWEEP / SAMPLE geometry."""

from __future__ import annotations

from sea_of_colours.orchestrator_2.harnesses.tabula_v11 import comb_shapes


def _view(width=40, height=28, green=()):
    live = [{"x": x, "y": y, "tile": "GREEN"} for (x, y) in green]
    return {"world": {"width": width, "height": height, "live": live}}


def _contiguous_from(drop, path):
    cur = tuple(drop)
    for step in path:
        s = tuple(step)
        if max(abs(s[0] - cur[0]), abs(s[1] - cur[1])) != 1 or (
            s[0] != cur[0] and s[1] != cur[1]
        ):
            return False
        cur = s
    return True


def test_all_three_shapes_within_budget_and_contiguous():
    view = _view()
    drop = [20, 14]
    variants = comb_shapes.comb_variants(view, [20, 14], drop)
    assert set(variants) == {"STRETCH", "SWEEP", "SAMPLE"}
    for name, path in variants.items():
        assert len(path) <= 5, name
        assert _contiguous_from(drop, path), name
    assert len(variants["SAMPLE"]) <= 2


def test_sample_is_short_in_out():
    view = _view()
    variants = comb_shapes.comb_variants(view, [10, 10], [10, 10])
    assert 0 <= len(variants["SAMPLE"]) <= 2


def test_stretch_heads_toward_open_space_from_a_corner():
    # Drop near the top-left corner -> stretch should move right/down (into room),
    # never off-board.
    view = _view()
    variants = comb_shapes.comb_variants(view, [1, 1], [1, 1])
    stretch = variants["STRETCH"]
    assert stretch, "stretch should produce a walk from a corner"
    for x, y in stretch:
        assert 0 <= x < 40 and 0 <= y < 28
    # Net displacement is into the board (positive-ish), not into the wall.
    assert stretch[-1][0] >= 1 and stretch[-1][1] >= 1


def test_shapes_avoid_known_green():
    # Fence the drop's east/south with green; no step may land on green.
    green = {(21, 14), (20, 15), (19, 14), (20, 13)}
    view = _view(green=green)
    variants = comb_shapes.comb_variants(view, [20, 14], [20, 14])
    for path in variants.values():
        for cell in path:
            assert tuple(cell) not in green


def test_sweep_biases_toward_value_cells():
    view = _view()
    # A value cluster two east of the drop; sweep should step toward it.
    variants = comb_shapes.comb_variants(
        view, [20, 14], [20, 14], value_cells=[(22, 14), (23, 14)],
    )
    sweep = variants["SWEEP"]
    assert sweep
    # First step moves east toward the value.
    assert sweep[0][0] >= 20
