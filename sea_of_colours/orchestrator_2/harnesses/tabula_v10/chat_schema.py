"""v10 chat schemas — hermetic-ish overrides on top of the v7 specs.

v10 runs a CONTAINED TWO-STAGE thinker (THINK prose -> PLAN decision) BEFORE the
mover, so by the time the mover runs the reasoning already exists. The v7 mover
schema still forces the mover to (re)write ``reflection_on_last_night`` /
``plan_this_turn`` / ``rationale`` / ``predicted_outcome`` / ``memory_note`` —
a wall of prose the model spends 25-99s generating (the A4 latency wart). v10's
mover only needs to PACKAGE the thinker's committed plan into moves, so its
schema is trimmed to ``moves`` (+ an optional one-line ``note``). The reflection
/ plan / rationale surfaced for memory + audit are sourced from the THINKER
instead (see harness).

The decision (thinker) schema is re-exported unchanged.
"""

from __future__ import annotations

from sea_of_colours.orchestrator_2.harnesses.tabula_v7.chat_schema import (  # noqa: F401
    _MOVE_ITEM,
    DECISION_RESPONSE_FORMAT,
)

# Moves-only mover schema. ``additionalProperties: False`` means a strict
# structured-output model emits ONLY ``moves`` (+ the optional ``note``) — it
# CANNOT wander into the prose fields, which is what collapses the latency.
_V10_MOVES_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "moves": {"type": "array", "items": _MOVE_ITEM},
        # optional, one line — a cheap escape hatch for a single caveat; the
        # prompt tells the mover to leave it empty unless something was cut.
        "note": {"type": "string"},
    },
    "required": ["moves"],
}

MOVES_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {"name": "soc_tabula_v10_moves", "schema": _V10_MOVES_SCHEMA},
}
