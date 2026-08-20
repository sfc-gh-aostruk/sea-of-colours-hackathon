"""Season-scoped agent memory — used by SOC_RED_REAPER_PILOT_V2.

The candidate compiler (:mod:`sea_of_colours.agent.candidates`) needs to know
"has the rival ever had eyes on this cell?" so it can flag candidate drops
that land on already-telegraphed territory. The engine maintains
``competitor_intel.persistent_echoes`` for the *current* sighting state, but
that fades as echoes age out. We keep our own monotonically-growing record so
the agent has a true season-long history.

Backend choice — pragmatic, not architectural:

* **Process-local cache** keyed by ``(session_id, player)``. Fast, no schema
  touch, survives across turns within a single uvicorn worker.
* **Cold-start bootstrap** from ``agent_view.competitor_intel.persistent_echoes``
  the first time we see a session. The engine's persistent_echoes are
  Snowflake-backed and outlive any single Python process, so a fresh worker
  reconstructs most of the history immediately.
* **No SocStore plumbing.** The ``SOC_AGENT_MEMORY`` table declared in
  ``snowflake/soc_schema.sql`` is reserved for a future v2 of this module
  that wants true cross-process durability for in-flight spec changes.

Schema of the per-(session, player) record::

    {
        "season_name":      str,
        "session_id":       str,
        "player":           str,
        "last_updated_day": int,
        "cells": {
            "x,y": {
                "first_day":     int,    # day we first observed an enemy probe disk here
                "last_day":      int,    # most recent day
                "count":         int,    # how many distinct nights it's been observed
            },
            ...
        },
        # Threat-assessment extensions (v0.9.20):
        "enemy_harvester_positions": {
            "<day>": [[x, y], ...]   # known enemy harvester cells per day
        },
        "enemy_drops_observed": [
            {"day": int, "at": [x, y], "near_red_value": int}
        ],
        "my_probes_superseded": [
            {"zone": [x, y], "day_superseded": int}
        ],
        "fog_red_revealed_history": [
            {"day": int, "at": [x, y], "value": int}
        ],
    }
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

# Process-local cache. NOT thread-safe by design — uvicorn single-worker
# pattern (the README spells out "Run a single worker, no --reload" for
# multiplayer) is the supported deployment, and the per-turn submit lock
# already serialises mutations against this dict.
_MEMORY_CACHE: Dict[Tuple[str, str], Dict[str, Any]] = {}


def _key(session_id: str, player: str) -> Tuple[str, str]:
    return (str(session_id), str(player))


def _empty(season_name: str, session_id: str, player: str) -> Dict[str, Any]:
    return {
        "season_name": season_name or "",
        "session_id": session_id,
        "player": player,
        "last_updated_day": 0,
        "cells": {},
        # Threat-assessment extensions (v0.9.20).
        "enemy_harvester_positions": {},
        "enemy_drops_observed": [],
        "my_probes_superseded": [],
        "fog_red_revealed_history": [],
        # EMP threat tracking (v0.9.22). We need a per-turn snapshot of
        # the rival's BLUE-purity grade (from station_intel.opponents) so
        # we can detect a band drop between consecutive turns — that's
        # the consumption-event signal for "rival built a weapon".
        "rival_blue_grade_history": {},
        # Finer 150/pip BLUE band (0..5) per turn — sharper than the 4-band
        # grade for spotting an ~200-BLUE EMP spend across a turn.
        "rival_blue_band_history": {},
        "rival_emp_launches_history": {},
    }


def _ensure_cell(memory: Dict[str, Any], xy: Tuple[int, int], day: int) -> None:
    """Stamp (or refresh) one cell observation."""
    key = f"{int(xy[0])},{int(xy[1])}"
    cells = memory["cells"]
    rec = cells.get(key)
    if rec is None:
        cells[key] = {
            "first_day": int(day),
            "last_day": int(day),
            "count": 1,
        }
    else:
        rec["last_day"] = max(int(rec.get("last_day", day)), int(day))
        # Distinct-day count: only bump if last_day moved.
        if int(rec["last_day"]) != int(rec.get("first_day", day)):
            rec["count"] = int(rec.get("count", 1)) + 1


def _disk_cells(
    centre: Tuple[int, int],
    radius: int,
    width: int,
    height: int,
) -> Iterable[Tuple[int, int]]:
    """Euclidean disk (|dx|² + |dy|² ≤ radius²) clipped to the board."""
    cx, cy = int(centre[0]), int(centre[1])
    r2 = int(radius) * int(radius)
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dx * dx + dy * dy > r2:
                continue
            x, y = cx + dx, cy + dy
            if 0 <= x < width and 0 <= y < height:
                yield (x, y)


def _enemy_probe_positions(agent_view: Mapping[str, Any]) -> List[Tuple[Tuple[int, int], int]]:
    """Pull (at, last_seen_day) pairs from competitor_intel.

    The engine surfaces enemy probes in two places that matter to us:

    * ``competitor_intel.new_this_day[*].kind == "enemy_probe_launch"`` —
      this turn's launches (always visible per RULEBOOK §3.15).
    * ``competitor_intel.persistent_echoes[*].kind == "enemy_probe"`` —
      older sightings still on the seat's memory.

    Returns a list of ``((x, y), day)`` tuples, deduplicated to the latest
    ``day`` per cell.
    """
    intel = agent_view.get("competitor_intel") or {}
    rows: List[Tuple[Tuple[int, int], int]] = []
    for r in (intel.get("new_this_day") or []):
        if not isinstance(r, dict):
            continue
        kind = str(r.get("kind", "")).lower()
        if "probe" not in kind:
            continue
        at = r.get("at")
        if not (isinstance(at, (list, tuple)) and len(at) == 2):
            continue
        try:
            x, y = int(at[0]), int(at[1])
        except (TypeError, ValueError):
            continue
        day = int(r.get("day") or r.get("last_seen_day") or 0)
        rows.append(((x, y), day))
    for r in (intel.get("persistent_echoes") or []):
        if not isinstance(r, dict):
            continue
        kind = str(r.get("kind", "")).lower()
        if "probe" not in kind:
            continue
        at = r.get("at")
        if not (isinstance(at, (list, tuple)) and len(at) == 2):
            continue
        try:
            x, y = int(at[0]), int(at[1])
        except (TypeError, ValueError):
            continue
        day = int(r.get("last_seen_day") or 0)
        rows.append(((x, y), day))
    # Dedup keeping the latest day per cell.
    latest: Dict[Tuple[int, int], int] = {}
    for at, day in rows:
        if day >= latest.get(at, -1):
            latest[at] = day
    return list(latest.items())


def _enemy_harvester_positions(agent_view: Mapping[str, Any], me: str) -> List[Tuple[int, int]]:
    """Pull (x, y) cells currently occupied by visible enemy harvesters.

    Looks at the dense ``world.grid`` rows and at any
    ``competitor_intel.harvesters`` snapshot the engine surfaces.
    """
    cells: List[Tuple[int, int]] = []
    seen: set = set()

    # 1. Dense grid: scan visible cells for harvester entities owned by a non-me seat.
    world = agent_view.get("world") or {}
    grid = world.get("grid") or []
    for row in grid:
        if not isinstance(row, (list, tuple)):
            continue
        for cell in row:
            if not isinstance(cell, Mapping):
                continue
            ents = cell.get("entities") or []
            for ent in ents:
                if not isinstance(ent, Mapping):
                    continue
                kind = str(ent.get("kind") or ent.get("type") or "").lower()
                if "harvester" not in kind:
                    continue
                owner = str(ent.get("owner") or ent.get("player") or "")
                if not owner or owner == me:
                    continue
                try:
                    x, y = int(cell.get("x")), int(cell.get("y"))
                except (TypeError, ValueError):
                    continue
                xy = (x, y)
                if xy in seen:
                    continue
                seen.add(xy)
                cells.append(xy)

    # 2. competitor_intel.harvesters (if the engine surfaces it).
    intel = agent_view.get("competitor_intel") or {}
    for r in (intel.get("harvesters") or []):
        if not isinstance(r, Mapping):
            continue
        at = r.get("at") or r.get("pos")
        if not (isinstance(at, (list, tuple)) and len(at) == 2):
            continue
        try:
            x, y = int(at[0]), int(at[1])
        except (TypeError, ValueError):
            continue
        xy = (x, y)
        if xy in seen:
            continue
        seen.add(xy)
        cells.append(xy)

    return cells


def update_memory(agent_view: Mapping[str, Any]) -> Dict[str, Any]:
    """Merge this turn's enemy probe sightings into our running record.

    Pure of side effects on the input. Mutates the process-local cache.
    Returns the updated memory dict (the same object stored in the cache,
    so subsequent ``snapshot()`` calls see this turn's writes).

    Bootstrap: on first call for a ``(session_id, player)`` we seed the
    cache from ``competitor_intel.persistent_echoes`` so a fresh worker
    process inherits whatever long-term sightings the engine retained.
    """
    meta = agent_view.get("meta") or {}
    session_id = str(meta.get("session_id") or "")
    player = str(meta.get("player") or "")
    season_name = str(meta.get("season") or "")
    day = int(meta.get("day") or 0)

    if not session_id or not player:
        # Defensive: without a key we can't cache; build a one-shot dict.
        return _empty(season_name, session_id, player)

    cache_key = _key(session_id, player)
    memory = _MEMORY_CACHE.get(cache_key)
    if memory is None:
        memory = _empty(season_name, session_id, player)
        _MEMORY_CACHE[cache_key] = memory
        # Seed from persistent_echoes so we don't lose prior days when a
        # process restarts mid-season.
        for (at, seen_day) in _enemy_probe_positions(agent_view):
            _stamp_disk(memory, at, seen_day, agent_view)

    # Always merge this turn's observations.
    for (at, seen_day) in _enemy_probe_positions(agent_view):
        _stamp_disk(memory, at, max(seen_day, day), agent_view)

    # Threat-assessment extensions (v0.9.20).
    # 1) Record enemy harvester positions for this day.
    enemy_h_cells = _enemy_harvester_positions(agent_view, me=player)
    if enemy_h_cells:
        eh_map: Dict[str, Any] = memory.setdefault("enemy_harvester_positions", {})
        # Keys are stringified day numbers for JSON friendliness.
        eh_map[str(day)] = [[int(x), int(y)] for (x, y) in enemy_h_cells]
        # Cap history to last 14 days to keep payload bounded.
        if len(eh_map) > 14:
            kept = sorted(eh_map.keys(), key=lambda k: int(k))[-14:]
            memory["enemy_harvester_positions"] = {k: eh_map[k] for k in kept}

    # 2) Record THIS turn's enemy probe launches as observed drops (probe = drop
    # of a vision asset; enemy harvester drops are private per §3.15 so probe
    # launches are the closest proxy we can track).
    intel = agent_view.get("competitor_intel") or {}
    for r in (intel.get("new_this_day") or []):
        if not isinstance(r, Mapping):
            continue
        kind = str(r.get("kind") or "").lower()
        if "probe_launch" not in kind:
            continue
        at = r.get("at")
        if not (isinstance(at, (list, tuple)) and len(at) == 2):
            continue
        try:
            x, y = int(at[0]), int(at[1])
        except (TypeError, ValueError):
            continue
        near_red = 0
        # Pull nearby red value from navigation.best_red_visible if available.
        nav = agent_view.get("navigation") or {}
        for rt in (nav.get("best_red_visible") or []):
            try:
                rx, ry = int(rt.get("x")), int(rt.get("y"))
            except (TypeError, ValueError):
                continue
            if abs(rx - x) + abs(ry - y) <= 3:
                near_red = max(near_red, int(rt.get("value") or rt.get("purity") or 0))
        memory.setdefault("enemy_drops_observed", []).append({
            "day": int(day),
            "at": [int(x), int(y)],
            "near_red_value": int(near_red),
        })
    # Cap observed drops to last 30 entries.
    obs = memory.get("enemy_drops_observed") or []
    if len(obs) > 30:
        memory["enemy_drops_observed"] = obs[-30:]

    # 3) Snapshot rival's BLUE-purity grade from station_intel for EMP
    # threat detection (v0.9.22). A band drop between consecutive turns
    # signals weapon consumption. Also capture the per-night EMP launch
    # count (retrospective confirmation that EMPs are in play).
    station_intel = agent_view.get("station_intel") or {}
    for opp in (station_intel.get("opponents") or []):
        if not isinstance(opp, Mapping):
            continue
        seat = str(opp.get("seat") or "")
        if not seat or seat == player:
            continue
        blue_obs = opp.get("blue") or {}
        blue_grade = str((blue_obs.get("grade") or "")).lower()
        if blue_grade:
            memory.setdefault("rival_blue_grade_history", {})[str(day)] = blue_grade
        blue_band = blue_obs.get("band")
        if blue_band is not None:
            try:
                memory.setdefault("rival_blue_band_history", {})[str(day)] = int(blue_band)
            except (TypeError, ValueError):
                pass
        try:
            emp_count = int(((opp.get("activity") or {}).get("emps") or 0))
        except (TypeError, ValueError):
            emp_count = 0
        if emp_count > 0:
            memory.setdefault("rival_emp_launches_history", {})[str(day)] = emp_count

    memory["last_updated_day"] = max(memory.get("last_updated_day", 0), day)
    memory["season_name"] = season_name or memory.get("season_name", "")
    return memory


def _stamp_disk(
    memory: Dict[str, Any],
    centre: Tuple[int, int],
    day: int,
    agent_view: Mapping[str, Any],
) -> None:
    """Stamp every cell inside the probe's Euclidean disk into memory."""
    world = agent_view.get("world") or {}
    width = int(world.get("width") or 0)
    height = int(world.get("height") or 0)
    if width <= 0 or height <= 0:
        return
    radius = int(((agent_view.get("meta") or {}).get("rules") or {}).get("probe_radius") or 4)
    for cell in _disk_cells(centre, radius, width, height):
        _ensure_cell(memory, cell, day)


def snapshot(session_id: str, player: str) -> Dict[str, Any]:
    """Return the cached memory for a ``(session_id, player)`` (or empty)."""
    cache_key = _key(session_id, player)
    cached = _MEMORY_CACHE.get(cache_key)
    if cached is not None:
        return cached
    return {
        "season_name": "",
        "session_id": str(session_id),
        "player": str(player),
        "last_updated_day": 0,
        "cells": {},
        "enemy_harvester_positions": {},
        "enemy_drops_observed": [],
        "my_probes_superseded": [],
        "fog_red_revealed_history": [],
    }


def summarise(memory: Mapping[str, Any], current_day: int, *, hot_top_n: int = 6) -> Dict[str, Any]:
    """Produce the compact prompt-ready summary.

    The full ``cells`` dict can run to thousands of entries on a 40×28
    map by season end; we never want to paste all of it into the LLM
    prompt. The summary is what the slim prompt actually carries.
    """
    cells: Mapping[str, Any] = (memory or {}).get("cells") or {}
    total = len(cells)
    fresh_3 = 0
    recent: List[Tuple[str, int]] = []
    for key, rec in cells.items():
        last_day = int(rec.get("last_day", 0))
        if current_day - last_day <= 3:
            fresh_3 += 1
        recent.append((key, last_day))
    recent.sort(key=lambda kv: -kv[1])
    hot = [
        {"at": [int(k.split(",", 1)[0]), int(k.split(",", 1)[1])], "last_day": d}
        for (k, d) in recent[:hot_top_n]
    ]
    return {
        "cells_ever_seen_by_enemy_count": total,
        "fresh_observation_count_last_3_days": fresh_3,
        "hot_cells": hot,
        "as_of_day": int(current_day),
        # Threat-assessment extensions (v0.9.20).
        "recent_enemy_harvester_count": _recent_enemy_harvester_count(memory, current_day),
        "recent_observed_drops_count": _recent_observed_drops_count(memory, current_day),
        "my_probes_superseded_recent": _superseded_recent_summary(memory, current_day),
    }


def _recent_enemy_harvester_count(memory: Mapping[str, Any], current_day: int, *, lookback: int = 2) -> int:
    """How many distinct enemy-harvester cells we observed in the last ``lookback`` days."""
    eh = (memory or {}).get("enemy_harvester_positions") or {}
    seen: set = set()
    for k, cells in eh.items():
        try:
            d = int(k)
        except (TypeError, ValueError):
            continue
        if current_day - d > lookback:
            continue
        for xy in cells or []:
            if isinstance(xy, (list, tuple)) and len(xy) == 2:
                try:
                    seen.add((int(xy[0]), int(xy[1])))
                except (TypeError, ValueError):
                    continue
    return len(seen)


def _recent_observed_drops_count(memory: Mapping[str, Any], current_day: int, *, lookback: int = 3) -> int:
    """How many enemy probe-launch observations we recorded in the last ``lookback`` days."""
    obs = (memory or {}).get("enemy_drops_observed") or []
    n = 0
    for r in obs:
        if not isinstance(r, Mapping):
            continue
        try:
            d = int(r.get("day") or 0)
        except (TypeError, ValueError):
            continue
        if current_day - d <= lookback:
            n += 1
    return n


def _superseded_recent_summary(memory: Mapping[str, Any], current_day: int, *, lookback: int = 2) -> List[Dict[str, Any]]:
    """List recent supersede-of-my-probe events (Doctrine 4b feeder)."""
    rows = (memory or {}).get("my_probes_superseded") or []
    out: List[Dict[str, Any]] = []
    for r in rows:
        if not isinstance(r, Mapping):
            continue
        try:
            d = int(r.get("day_superseded") or 0)
        except (TypeError, ValueError):
            continue
        if current_day - d > lookback:
            continue
        zone = r.get("zone")
        if not (isinstance(zone, (list, tuple)) and len(zone) == 2):
            continue
        try:
            out.append({
                "zone": [int(zone[0]), int(zone[1])],
                "days_ago": int(current_day) - d,
            })
        except (TypeError, ValueError):
            continue
    return out


def record_my_probe_superseded(
    session_id: str,
    player: str,
    zone: Tuple[int, int],
    day_superseded: int,
) -> None:
    """Append a "my probe was superseded by the enemy" event to memory.

    Called from the harness when it observes the enemy supersede event in
    competitor_intel. Keeps a bounded ring buffer (last 12 entries).
    """
    cache_key = _key(session_id, player)
    memory = _MEMORY_CACHE.get(cache_key)
    if memory is None:
        return
    rows = memory.setdefault("my_probes_superseded", [])
    rows.append({
        "zone": [int(zone[0]), int(zone[1])],
        "day_superseded": int(day_superseded),
    })
    if len(rows) > 12:
        memory["my_probes_superseded"] = rows[-12:]


def enemy_harvester_recent_positions(
    memory: Mapping[str, Any],
    current_day: int,
    *,
    lookback: int = 2,
) -> List[Tuple[int, int]]:
    """Return distinct enemy harvester cells seen in the last ``lookback`` days."""
    eh = (memory or {}).get("enemy_harvester_positions") or {}
    seen: set = set()
    out: List[Tuple[int, int]] = []
    for k, cells in eh.items():
        try:
            d = int(k)
        except (TypeError, ValueError):
            continue
        if current_day - d > lookback:
            continue
        for xy in cells or []:
            if isinstance(xy, (list, tuple)) and len(xy) == 2:
                try:
                    p = (int(xy[0]), int(xy[1]))
                except (TypeError, ValueError):
                    continue
                if p in seen:
                    continue
                seen.add(p)
                out.append(p)
    return out


def cells_seen_set(memory: Mapping[str, Any]) -> set:
    """Return a ``set[(x, y)]`` for fast membership queries by the compiler."""
    out: set = set()
    for key in (memory or {}).get("cells") or {}:
        try:
            xs, ys = key.split(",", 1)
            out.add((int(xs), int(ys)))
        except (ValueError, TypeError):
            continue
    return out


def reset_for_tests() -> None:
    """Clear the process-local cache. Test-only escape hatch."""
    _MEMORY_CACHE.clear()
