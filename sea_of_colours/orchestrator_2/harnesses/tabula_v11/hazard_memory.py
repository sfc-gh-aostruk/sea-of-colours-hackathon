"""v11 Phase 3 / Part A1 — the PERSISTENT stripped/green hazard memory.

The seed-56 collapse (v11 → 75 pts) was a self-inflicted bleed: the agent
blind-dropped onto a rival's redsign pure that a rival harvester had already
STRIPPED to synthetic green on a prior night. By the time v11 dropped, the cell
was green — but FOGGED to v11 — so nothing at plan time flagged it, and the
engine auto-harvested green for −100/parcel.

The precaution exploits one fact: **green is monotonic.** A cell that has turned
GREEN (harvested → synthetic, or a natural hazard) never becomes valuable again.
So the union of every green cell the seat has EVER seen is a safe, growing "do
not drop/step here" set — even for cells now hidden by fog. This module
accumulates that union per (session, seat) and hands it to the deterministic
packager (which refuses to compile a drop/step onto it) and the move sanitizer
(as a backstop `bad` set that survives fog, unlike the view-only green helpers).

Storage mirrors :mod:`.memory`: a process-local cache always (tests / offline
eval) plus a best-effort ``SOC_AGENT_MEMORY`` row under a dedicated KIND so the
union survives process restarts within a season. A write failure never crashes
the turn.

NOTE: this closes the SELF/observed-green case. A rival stripping a pure while
it is fogged to us is never observed as green — that case is closed structurally
by Part B (do not send a harvester blind onto a fogged rival seam).
"""

from __future__ import annotations

import json as _json
from typing import Any, Mapping, Optional, Set, Tuple

from sea_of_colours.orchestrator_2.harnesses.tabula_v7.validators import (
    _synthetic_green_cells,
    _green_hazard_cells,
)

Cell = Tuple[int, int]

# KIND row key in SOC_AGENT_MEMORY (one authoritative union per session+seat).
_KIND = "arena:hazard_cells"

# Process-local cache: (session_id, player) -> set[Cell]. Always populated so
# tests and offline eval accumulate without a live Snowflake session.
_CACHE: dict = {}


def _cache_key(session_id: str, player: str) -> str:
    return f"{session_id}::{player}"


def view_green_cells(agent_view: Mapping[str, Any]) -> Set[Cell]:
    """Every GREEN cell (synthetic harvested + natural hazard) in THIS view."""
    return set(_synthetic_green_cells(agent_view)) | set(
        _green_hazard_cells(agent_view)
    )


def load(
    session_id: str, player: str, *, store: Optional[Any] = None,
) -> Set[Cell]:
    """The accumulated hazard union for the seat (fog-surviving).

    Reads the process cache first; hydrates from Snowflake once if empty.
    """
    key = _cache_key(session_id, player)
    if key in _CACHE:
        return set(_CACHE[key])
    hydrated = _hydrate(session_id, player, store=store)
    _CACHE[key] = set(hydrated)
    return set(hydrated)


def accumulate(
    session_id: str,
    player: str,
    agent_view: Mapping[str, Any],
    *,
    store: Optional[Any] = None,
    season_name: Optional[str] = None,
) -> Set[Cell]:
    """Fold this view's green cells into the seat's union and return the union.

    Idempotent and monotonic: cells only ever get added. Persists best-effort;
    a write failure is swallowed so the turn never crashes on memory I/O.
    """
    key = _cache_key(session_id, player)
    union = load(session_id, player, store=store)
    fresh = view_green_cells(agent_view)
    new = fresh - union
    union |= fresh
    _CACHE[key] = set(union)
    if new:  # only pay the write when the union actually grew
        _persist(session_id, player, union, store=store, season_name=season_name)
    return set(union)


# ── persistence (best-effort; mirrors memory.py) ────────────────────────
def _persist(
    session_id: str,
    player: str,
    union: Set[Cell],
    *,
    store: Optional[Any] = None,
    season_name: Optional[str] = None,
) -> None:
    try:
        from sea_of_colours.snowpark.backend import get_store, SOC_BACKEND
        if SOC_BACKEND != "snowflake":
            return
        sf_store = store if store is not None else get_store()
        session = getattr(sf_store, "session", None)
        if session is None:
            return
        payload = _json.dumps(
            {"cells": [[int(x), int(y)] for (x, y) in sorted(union)]}
        )
        session.sql(
            """
            MERGE INTO SOC_AGENT_MEMORY t
            USING (SELECT ? AS session_id, ? AS season_name, ? AS player,
                          ? AS kind, PARSE_JSON(?) AS payload) s
            ON t.session_id = s.session_id AND t.player = s.player AND t.kind = s.kind
            WHEN MATCHED THEN UPDATE SET payload = s.payload,
                                         season_name = s.season_name,
                                         updated_at = CURRENT_TIMESTAMP()
            WHEN NOT MATCHED THEN INSERT (session_id, season_name, player, kind, payload, updated_at)
                VALUES (s.session_id, s.season_name, s.player, s.kind, s.payload, CURRENT_TIMESTAMP())
            """,
            params=[session_id, season_name or "", player, _KIND, payload],
        ).collect()
    except Exception:
        pass


def _hydrate(
    session_id: str, player: str, *, store: Optional[Any] = None,
) -> Set[Cell]:
    out: Set[Cell] = set()
    try:
        from sea_of_colours.snowpark.backend import get_store, SOC_BACKEND
        if SOC_BACKEND != "snowflake":
            return out
        sf_store = store if store is not None else get_store()
        session = getattr(sf_store, "session", None)
        if session is None:
            return out
        rows = session.sql(
            """
            SELECT PAYLOAD FROM SOC_AGENT_MEMORY
            WHERE session_id = ? AND player = ? AND kind = ?
            """,
            params=[session_id, player, _KIND],
        ).collect()
        for r in rows:
            payload = r["PAYLOAD"]
            if isinstance(payload, str):
                try:
                    payload = _json.loads(payload)
                except Exception:
                    continue
            for c in (payload or {}).get("cells") or []:
                if isinstance(c, (list, tuple)) and len(c) == 2:
                    try:
                        out.add((int(c[0]), int(c[1])))
                    except (TypeError, ValueError):
                        continue
    except Exception:
        pass
    return out


def clear_cache() -> None:
    """Test helper — reset the process-local union between fixtures."""
    _CACHE.clear()
