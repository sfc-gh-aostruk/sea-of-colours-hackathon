"""v9 chain-hint post-filter (A8) + lean moves-only mover schema (A4)."""

from __future__ import annotations

from sea_of_colours.orchestrator_2.harnesses.tabula_v9 import chain_filter
from sea_of_colours.orchestrator_2.harnesses.tabula_v9 import chat_schema


def _chain(unit, cells, purities):
    return {
        "unit": unit,
        "drop_at": list(cells[0]),
        "cells": [list(c) for c in cells],
        "purities": list(purities),
        "length": len(cells),
    }


# ── A8: value floor ──────────────────────────────────────────────────────
def test_floor_drops_trace_only_chains_when_a_real_chain_exists():
    real = _chain("h1", [(1, 1), (1, 2)], [200, 180])
    trace = _chain("h2", [(9, 9), (9, 10)], [3, 5])
    out = chain_filter.dedupe_and_floor([trace, real])
    units = [h["unit"] for h in out]
    assert "h1" in units
    assert "h2" not in units


def test_floor_never_strips_to_empty_when_all_trace():
    trace_a = _chain("h1", [(1, 1), (1, 2)], [3, 4])
    trace_b = _chain("h2", [(9, 9)], [2])
    out = chain_filter.dedupe_and_floor([trace_a, trace_b])
    assert out, "must keep something as a safety net even if all sub-floor"


# ── A8: body-overlap dedupe ───────────────────────────────────────────────
def test_body_overlap_dedupe_drops_the_near_duplicate_dig():
    rich = _chain("h1", [(5, 5), (5, 6), (5, 7), (5, 8)], [255, 200, 180, 160])
    # begins one cell apart but then walks the SAME seam cells -> a double-dig.
    dup = _chain("h2", [(5, 6), (5, 7), (5, 8)], [200, 180, 160])
    out = chain_filter.dedupe_and_floor([rich, dup])
    assert [h["unit"] for h in out] == ["h1"]


def test_disjoint_chains_both_survive():
    a = _chain("h1", [(5, 5), (5, 6)], [255, 200])
    b = _chain("h2", [(20, 20), (20, 21)], [255, 200])
    out = chain_filter.dedupe_and_floor([a, b])
    assert len(out) == 2


def test_empty_input_returns_empty():
    assert chain_filter.dedupe_and_floor([]) == []


# ── A4: lean mover schema ─────────────────────────────────────────────────
def test_v9_mover_schema_is_moves_only():
    schema = chat_schema.MOVES_RESPONSE_FORMAT["json_schema"]["schema"]
    assert schema["required"] == ["moves"]
    # ONLY moves + an optional note — no reflection/plan/rationale prose fields
    # (that is what collapsed the 25-99s mover latency).
    assert set(schema["properties"]) == {"moves", "note"}
    assert schema["additionalProperties"] is False


def test_v9_mover_schema_name_is_distinct_from_v7():
    assert chat_schema.MOVES_RESPONSE_FORMAT["json_schema"]["name"] == (
        "soc_tabula_v9_moves"
    )
