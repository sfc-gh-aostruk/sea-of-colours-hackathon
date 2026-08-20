"""Candidate compiler for SOC_RED_REAPER_PILOT_V2.

The PILOT_V2 agent's spec instructs it to *pick or compose* from a menu of
pre-validated, pre-scored moves rather than re-derive them every turn.
This module is that menu builder — pure-function, zero I/O, runs
orchestrator-side per turn before the slim prompt is built.

It produces three top-level blocks the prompt builder injects into the
STATE JSON:

* ``candidates`` — harvest chains, probe drops, supersedes, harvester
  crushes, and hot-drop pairs, each ready to copy verbatim into
  ``soc_submit_policy``'s ``p_policy``. Includes a
  ``recommended_policy.moves`` that the agent can submit unchanged on
  the fast path.
* ``threat`` — enemy probe proximity, shared-vision counts, my-fleet
  status, enemy-fleet estimate, hoard-pressure, publicity-risk, and a
  ``final_day`` flag. The agent uses this to override the recommendation.
* ``memory_summary`` — compact view onto :mod:`sea_of_colours.agent.memory`
  so the agent knows which cells the rival has *ever* had eyes on.

Design notes:

* **Reuses** the deterministic spatial helpers in
  :mod:`sea_of_colours.agent.heuristic_agent` (``_walk_and_harvest``,
  ``_cluster_score``, ``_adjacent_drop_targets``, ``_is_valid_drop``,
  ``_my_harvesters``, ``_visible_or_echo_cells``, ``_tier_mult_map``,
  ``_parcel_score``). Importing private helpers from a sibling module is
  intentional — the alternative was renaming them and breaking the
  long-tail test suite.
* **Pure**: input is the ``agent_view`` dict and an ``EnemyMemory`` mapping;
  output is JSON-serialisable. Deterministic given identical inputs.
* **Legality-validated**: every emitted move passes the same gates the
  engine uses (live/echo for drops, in-bounds for steps, fleet/per-unit
  budgets, no fog steps, no synthetic-green crossings, no enemy-harvester
  collisions). The agent can copy candidates blindly.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from sea_of_colours.orchestrator_2.harnesses.pilot_v2 import memory as _memory
from sea_of_colours.orchestrator_2.harnesses.pilot_v2 import threat_assess as _ta
from sea_of_colours.orchestrator_2.harnesses.pilot_v2 import combat as _combat
from sea_of_colours.orchestrator_2.harnesses.pilot_v2 import orbit as _orbit
from sea_of_colours.agent.heuristic_agent import (
    MAX_HARVESTER_STEPS,
    _adjacent_drop_targets,
    _drop_targetable_cells,
    _is_valid_drop,
    _manhattan,
    _my_harvesters,
    _parcel_score,
    _seat_of,
    _tier_mult_map,
    _visible_or_echo_cells,
)


# ── K scaling ────────────────────────────────────────────────────────
#
# The user wants candidate counts to scale with fleet size: 1H → K=3,
# 2H → K=5, 3H → K=6 for harvest; probes mirror this (3 / 5 / 5).
# Encoded as a small lookup so behaviour is obvious and testable.
def _k_harvest(harvester_count: int) -> int:
    return {0: 3, 1: 3, 2: 5, 3: 6}.get(int(harvester_count), 6)


def _k_probes(harvester_count: int) -> int:
    return {0: 3, 1: 3, 2: 5, 3: 5}.get(int(harvester_count), 5)


# ── tier helpers ──────────────────────────────────────────────────────
def _tier_of(value: int) -> str:
    v = int(value or 0)
    if v >= 255:
        return "pure"
    if v >= 151:
        return "mass"
    if v >= 51:
        return "vein"
    return "trace"


# ── world inspection ─────────────────────────────────────────────────
def _world_dims(agent_view: Mapping[str, Any]) -> Tuple[int, int]:
    world = agent_view.get("world") or {}
    width = int(world.get("width") or 0)
    height = int(world.get("height") or 0)
    if width and height:
        return width, height
    # fall-back for legacy view shapes — the heuristic stuffs grid info on
    # the raw view's "grid" key.
    g = agent_view.get("grid") or {}
    return int(g.get("width") or 0), int(g.get("height") or 0)


def _grid_cell(agent_view: Mapping[str, Any], x: int, y: int) -> Optional[Mapping[str, Any]]:
    """Read ``world.grid[y][x]`` defensively; ``None`` for OOB / fog / list-mode."""
    world = agent_view.get("world") or {}
    grid = world.get("grid")
    if not isinstance(grid, list):
        return None
    if not (0 <= y < len(grid)):
        return None
    row = grid[y]
    if not isinstance(row, list) or not (0 <= x < len(row)):
        return None
    cell = row[x]
    return cell if isinstance(cell, dict) else None


# ── dense-grid synthesis ─────────────────────────────────────────────
#
# CRITICAL: in production the engine sends ``world.grid = None`` and the
# RED/GREEN/BLUE data lives in top-level sparse lists (``red_tiles``,
# ``green_tiles``, ``blue_tiles``). The unit test fixtures use a dense
# grid; the eval scenarios too. Without this helper, every downstream
# consumer that reads ``world.grid`` silently sees None in production
# and returns degenerate output:
#   - ``_grid_cell`` returns None for every cell
#   - ``_avoid_step_cells`` returns an empty set → walker steps on green
#   - chain enumeration computes ``chain_red_purities = []`` → every chain
#     scores 0 RED → Doctrine 1 abandons all chains with -1000 penalty
#
# The fix is to project the sparse lists into a dense 2D structure once
# at the top of ``compile_candidates``. The synthesized view is a shallow
# copy with a fresh ``world.grid``; the input view is not mutated.
def _ensure_dense_grid(agent_view: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return ``agent_view`` with ``world.grid`` guaranteed to be a 2D list.

    No-op if the grid is already populated. Otherwise synthesize from the
    sparse top-level tile lists + entities so every downstream consumer
    can read ``_grid_cell(view, x, y)`` uniformly.
    """
    world = agent_view.get("world") or {}
    grid = world.get("grid")
    if isinstance(grid, list) and grid and isinstance(grid[0], list):
        return agent_view
    try:
        width = int(world.get("width") or 0)
        height = int(world.get("height") or 0)
    except (TypeError, ValueError):
        return agent_view
    if width <= 0 or height <= 0:
        return agent_view

    dense: List[List[Optional[Dict[str, Any]]]] = [
        [None for _ in range(width)] for _ in range(height)
    ]

    def _put_tile(x: int, y: int, cell: Dict[str, Any]) -> None:
        if 0 <= x < width and 0 <= y < height:
            dense[y][x] = cell

    # Build live/echo sets first so we can correctly tag cells as
    # ``echo=True`` when they're only in echo (NOT live). The legacy
    # ``_live_cells`` helper filters out cells with the echo flag set
    # so drop-legality under ``live_only`` mode is enforced.
    live_set: Set[Tuple[int, int]] = set()
    echo_set: Set[Tuple[int, int]] = set()
    for row in (world.get("live") or []):
        if not isinstance(row, Mapping):
            continue
        try:
            live_set.add((int(row.get("x")), int(row.get("y"))))
        except (TypeError, ValueError):
            continue
    for row in (world.get("echo") or []):
        if not isinstance(row, Mapping):
            continue
        # Skip probe-launch-only markers per §3.15 (tile stays fog).
        if row.get("via") == "probe_launch":
            continue
        try:
            xy = (int(row.get("x")), int(row.get("y")))
        except (TypeError, ValueError):
            continue
        if xy not in live_set:
            echo_set.add(xy)

    # FIRST: seed the visible area from live (no echo flag) + echo
    # (echo=True) so empty cells we can see are non-None in the dense
    # grid. ``_visible_or_echo_cells`` treats every non-None cell as
    # legal for vision; ``_live_cells`` additionally requires no echo
    # flag for drop legality under live_only mode.
    for (x, y) in live_set:
        if 0 <= x < width and 0 <= y < height and dense[y][x] is None:
            dense[y][x] = {"tile": "EMPTY", "x": x, "y": y}
    for (x, y) in echo_set:
        if 0 <= x < width and 0 <= y < height and dense[y][x] is None:
            dense[y][x] = {"tile": "EMPTY", "x": x, "y": y, "echo": True}

    # RED tiles. Mark with echo=True if the cell is in echo-only (not live).
    for r in (agent_view.get("red_tiles") or []):
        if not isinstance(r, Mapping):
            continue
        try:
            x, y = int(r.get("x")), int(r.get("y"))
        except (TypeError, ValueError):
            continue
        try:
            v = int(r.get("value") or r.get("purity") or 0)
        except (TypeError, ValueError):
            v = 0
        is_echo_only = (x, y) in echo_set and (x, y) not in live_set
        cell = {
            "tile": "RED",
            "x": x, "y": y,
            "value": v,
            "purity": int(r.get("purity") or v or 0),
            "tier": r.get("tier"),
            "freshness": r.get("freshness"),
            "square_id": r.get("square_id"),
        }
        if is_echo_only:
            cell["echo"] = True
        _put_tile(x, y, cell)

    # GREEN tiles — ``lineage`` distinguishes natural vs synthetic
    # (harvested-out RED becomes synthetic green per §3.12).
    for g in (agent_view.get("green_tiles") or []):
        if not isinstance(g, Mapping):
            continue
        try:
            x, y = int(g.get("x")), int(g.get("y"))
        except (TypeError, ValueError):
            continue
        lineage = str(g.get("lineage") or "").lower()
        _put_tile(x, y, {
            "tile": "GREEN",
            "x": x, "y": y,
            "purity": int(g.get("purity") or 255),
            "synthetic": lineage != "natural",
            "lineage": lineage,
            "square_id": g.get("square_id"),
        })

    # BLUE tiles.
    for b in (agent_view.get("blue_tiles") or []):
        if not isinstance(b, Mapping):
            continue
        try:
            x, y = int(b.get("x")), int(b.get("y"))
        except (TypeError, ValueError):
            continue
        try:
            v = int(b.get("value") or b.get("purity") or 0)
        except (TypeError, ValueError):
            v = 0
        _put_tile(x, y, {
            "tile": "BLUE",
            "x": x, "y": y,
            "value": v,
            "purity": int(b.get("purity") or v or 0),
            "freshness": b.get("freshness"),
            "square_id": b.get("square_id"),
        })

    # Entity overlay: my own units + visible enemy echoes.
    meta = agent_view.get("meta") or {}
    me = str(meta.get("player") or "")
    entities = agent_view.get("entities") or {}

    def _stamp_entity(pos: Any, owner: str, kind: str) -> None:
        if not (isinstance(pos, (list, tuple)) and len(pos) == 2):
            return
        try:
            x, y = int(pos[0]), int(pos[1])
        except (TypeError, ValueError):
            return
        if not (0 <= x < width and 0 <= y < height):
            return
        if dense[y][x] is None:
            dense[y][x] = {"tile": "EMPTY", "x": x, "y": y}
        dense[y][x]["entity"] = {
            "kind": kind,
            "type": kind,
            "owner": owner,
        }

    for e in (entities.get("mine") or []):
        if not isinstance(e, Mapping):
            continue
        kind = str(e.get("type") or e.get("kind") or "").lower()
        # Harvester ``pos`` is None when in orbit; only stamp surface units.
        pos = e.get("pos") or e.get("at")
        _stamp_entity(pos, owner=me, kind=kind)

    for e in (entities.get("echoes") or []):
        if not isinstance(e, Mapping):
            continue
        kind = str(e.get("type") or e.get("kind") or "").lower()
        owner = str(e.get("owner") or "")
        if not owner:
            # Echoes are by definition rival's — assume the "other" seat.
            owner = "p2" if me == "p1" else "p1"
        pos = e.get("pos") or e.get("at") or e.get("last_seen_pos")
        _stamp_entity(pos, owner=owner, kind=kind)

    new_world = dict(world)
    new_world["grid"] = dense
    new_view: Dict[str, Any] = dict(agent_view)
    new_view["world"] = new_world
    return new_view


def _is_synthetic_green(cell: Optional[Mapping[str, Any]]) -> bool:
    if not isinstance(cell, dict):
        return False
    return cell.get("tile") == "GREEN" and bool(cell.get("synthetic"))


def _is_enemy_harvester_cell(cell: Optional[Mapping[str, Any]], me: str) -> bool:
    if not isinstance(cell, dict):
        return False
    ent = cell.get("entity")
    if not isinstance(ent, dict):
        return False
    if str(ent.get("kind") or ent.get("type") or "").lower() != "harvester":
        return False
    return str(ent.get("owner") or "") != str(me)


def _is_enemy_probe_cell(cell: Optional[Mapping[str, Any]], me: str) -> bool:
    if not isinstance(cell, dict):
        return False
    ent = cell.get("entity")
    if not isinstance(ent, dict):
        return False
    if str(ent.get("kind") or ent.get("type") or "").lower() != "probe":
        return False
    return str(ent.get("owner") or "") != str(me)


def _is_my_probe_cell(cell: Optional[Mapping[str, Any]], me: str) -> bool:
    if not isinstance(cell, dict):
        return False
    ent = cell.get("entity")
    if not isinstance(ent, dict):
        return False
    if str(ent.get("kind") or ent.get("type") or "").lower() != "probe":
        return False
    return str(ent.get("owner") or "") == str(me)


def _has_collision(cell: Optional[Mapping[str, Any]]) -> bool:
    if not isinstance(cell, dict):
        return False
    return bool(cell.get("collision"))


def _avoid_step_cells(agent_view: Mapping[str, Any], me: str) -> Set[Tuple[int, int]]:
    """All cells a healthy harvester must NOT step onto OR drop onto.

    Hard filter applied at two places:
    - Drop-candidate validation (chain enumerator rejects drops in this set).
    - Step-target validation (walker refuses to enter these cells).

    Covers:
    - Natural green AND synthetic green (both have ``tile == "GREEN"``).
      Synthetic green is an enemy-decoy variant; engine harvests it on
      entry just like natural green, so it's zero-score waste either way.
    - Enemy harvester cells (§3.17 mutual damage).
    - Own probe cells ONLY when the underlying tile is not RED. A RED
      cell with our own probe sitting on it is walkable: the harvester
      crushes the probe on entry (~250c value lost) but harvests the
      RED (vein+ = ~150 raw → 150 banked; pure = ~255 raw × 3 ship
      mult ≈ 765 banked). The trade is net-positive for any vein-or-
      better tile, and our chain-scoring already accounts for it.
      ``grant_live_vision`` in the eval builder pins probes directly on
      RED clusters; without this carve-out the walker can't traverse
      contested seams at all.
    - Generic collision cells.
    """
    out: Set[Tuple[int, int]] = set()
    width, height = _world_dims(agent_view)
    if width <= 0 or height <= 0:
        return out
    world = agent_view.get("world") or {}
    grid = world.get("grid")
    if isinstance(grid, list):
        for y, row in enumerate(grid):
            if not isinstance(row, list):
                continue
            for x, cell in enumerate(row):
                if not isinstance(cell, dict):
                    continue
                tile = str(cell.get("tile") or "")
                # Natural green AND synthetic green — synthetic-green
                # carries tile=="GREEN" plus a `synthetic` flag, so this
                # one check hard-filters both. Do NOT downgrade to a
                # soft penalty: zero-score waste is never the right play.
                if tile == "GREEN":
                    out.add((x, y))
                if _is_enemy_harvester_cell(cell, me):
                    out.add((x, y))
                if _is_my_probe_cell(cell, me) and tile != "RED":
                    out.add((x, y))
                if _has_collision(cell):
                    out.add((x, y))
    return out


def _risky_collision_red_cells(
    agent_view: Mapping[str, Any], me: str
) -> Dict[Tuple[int, int], int]:
    """Map of RED cells occupied by an enemy harvester to the cell's RED purity.

    Doctrine 5 — these cells aren't hard-avoid; the walker can step in if
    the cell's RED value exceeds the inventory-loss cost adjusted by heat.
    """
    out: Dict[Tuple[int, int], int] = {}
    world = agent_view.get("world") or {}
    grid = world.get("grid")
    if not isinstance(grid, list):
        return out
    for y, row in enumerate(grid):
        if not isinstance(row, list):
            continue
        for x, cell in enumerate(row):
            if not isinstance(cell, dict):
                continue
            tile = str(cell.get("tile") or "")
            if tile != "RED":
                continue
            if not _is_enemy_harvester_cell(cell, me):
                continue
            try:
                purity = int(cell.get("value") or cell.get("purity") or 0)
            except (TypeError, ValueError):
                purity = 0
            if purity > 0:
                out[(x, y)] = purity
    return out


# ── walker: greedy + bounded lookahead ───────────────────────────────
#
# The legacy ``_walk_and_harvest`` is greedy: from each position it only
# steps to an *immediately adjacent* unclaimed RED. If a chain has to
# cross 1-2 empty cells to reach the next RED cluster (e.g. detour
# around a green wall), the greedy walker stops short.
#
# These two helpers extend the walker with a bounded BFS lookahead:
# after the greedy phase runs out of adjacent REDs, BFS through
# non-avoid cells up to ``remaining_steps`` deep to find the nearest
# unclaimed RED. If found, the walker pays the empty-step cost to reach
# it and resumes greedy harvesting. This produces multi-anchor chains
# that bridge gaps between RED clusters.
#
# Lives in this harness (not in heuristic_agent) so the heuristic's
# behaviour is unaffected — orchestrator_2's PILOT_V2 is the only
# consumer.
def _bfs_to_red(
    *,
    start: Tuple[int, int],
    red_positions: Mapping[Tuple[int, int], Mapping[str, Any]],
    claimed: Set[Tuple[int, int]],
    width: int,
    height: int,
    max_dist: int,
    avoid_cells: Set[Tuple[int, int]],
) -> Optional[List[Tuple[int, int]]]:
    """BFS the shortest path from ``start`` to the nearest unclaimed RED.

    Returns the path as a list of step destinations (excluding ``start``)
    if one exists within ``max_dist`` steps, walking through cells that
    are either EMPTY (not in avoid_cells) OR the destination RED itself.
    Returns ``None`` if no reachable RED.
    """
    if max_dist <= 0:
        return None
    # Standard BFS with parent map for path reconstruction.
    visited: Set[Tuple[int, int]] = {start}
    parent: Dict[Tuple[int, int], Tuple[int, int]] = {}
    frontier: List[Tuple[Tuple[int, int], int]] = [(start, 0)]
    while frontier:
        next_frontier: List[Tuple[Tuple[int, int], int]] = []
        for pos, dist in frontier:
            if dist >= max_dist:
                continue
            x, y = pos
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                cand = (x + dx, y + dy)
                if cand in visited:
                    continue
                if not (0 <= cand[0] < width and 0 <= cand[1] < height):
                    continue
                visited.add(cand)
                parent[cand] = pos
                # Hit an unclaimed RED — done, BUT only if it isn't also
                # in avoid_cells (a RED cell can be unsafe to step onto
                # if it carries an enemy harvester or other collision).
                if (
                    cand in red_positions
                    and cand not in claimed
                    and cand not in avoid_cells
                ):
                    # Reconstruct path: walk parents back to start.
                    path: List[Tuple[int, int]] = []
                    cur = cand
                    while cur != start:
                        path.append(cur)
                        cur = parent[cur]
                    path.reverse()
                    return path
                # Otherwise the cell must be passable (not green / probe /
                # enemy-harvester / collision) AND not itself a claimed RED.
                if cand in avoid_cells:
                    continue
                # Empty cells are always passable in BFS; we'll filter
                # by `avoid_cells` above. Don't traverse other RED cells
                # we already harvested (they're in `claimed`); that's
                # not strictly illegal but keeps chains tidy.
                if cand in red_positions and cand in claimed:
                    continue
                next_frontier.append((cand, dist + 1))
        frontier = next_frontier
    return None


def _walk_with_lookahead(
    *,
    start: Tuple[int, int],
    red_tiles: List[Dict[str, Any]],
    harvester_id: str,
    width: int,
    height: int,
    max_steps: int,
    claimed: Set[Tuple[int, int]],
    avoid_cells: Set[Tuple[int, int]],
    heatmap: Optional["_ta.Heatmap"] = None,
    risky_collision_cells: Optional[Mapping[Tuple[int, int], int]] = None,
) -> List[Dict[str, Any]]:
    """Walk a harvest chain with bounded lookahead between RED clusters.

    Greedy on adjacent REDs; BFS through EMPTY cells when stuck. Mutates
    ``claimed`` to record every RED grabbed. Returns the step moves
    (the caller is responsible for the surrounding ``drop`` and
    ``pickup`` moves).

    v0.9.24 — heat is a SIGNAL, not a path-avoidance penalty. The walker
    walks the full ``max_steps`` budget toward target regardless of
    local heat. Heat shapes chain *scoring* (race-bonus, offensive
    response priority) in the caller — NOT the walker. Risky-collision
    cells are still hard-blocked by ``avoid_cells`` (engine-mandated
    via §3.17), but heat doesn't add to that math here.

    Drop-in compatible with the prior signature.
    """
    moves: List[Dict[str, Any]] = []
    pos = start
    steps_used = 0
    # v0.9.24: full budget. Heat no longer truncates the chain.
    effective_max = int(max_steps)
    # Index reds for O(1) adjacency lookup.
    red_positions: Dict[Tuple[int, int], Dict[str, Any]] = {}
    for r in red_tiles:
        try:
            xy = (int(r.get("x")), int(r.get("y")))
        except (TypeError, ValueError):
            continue
        red_positions[xy] = r

    def _risky_net_value(c: Tuple[int, int]) -> Optional[float]:
        """If ``c`` is a risky-collision RED cell, return its net value (or None).

        v0.9.24: heat is NOT used here. §3.17 collision cost is a hard
        engine fact (full inventory loss); heat is a separate strike-
        likelihood signal that lives in scoring/priority, not in cell
        risk math.
        """
        if risky_collision_cells is None or c not in risky_collision_cells:
            return None
        purity = int(risky_collision_cells.get(c) or 0)
        net = float(purity) - _ta.INVENTORY_LOSS_COST
        return net

    def _adj_unclaimed_reds(p: Tuple[int, int]) -> List[Tuple[int, int]]:
        # IMPORTANT: a cell can be both RED and in avoid_cells (e.g. a
        # RED tile with an enemy harvester on it — §3.17 step-into
        # collision CANCELS the step and wrecks BOTH harvesters; the
        # RED is NOT harvested. So contested RED is ALWAYS off-limits
        # for stepping. ``risky_collision_cells`` is threaded through
        # for documentation/flag purposes only — the walker doesn't
        # override hard-avoid based on it.
        out: List[Tuple[int, int]] = []
        x, y = p
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            c = (x + dx, y + dy)
            if c in red_positions and c not in claimed and c not in avoid_cells:
                out.append(c)
        return out

    while steps_used < effective_max:
        remaining = effective_max - steps_used

        # Phase 1 — greedy: highest-purity adjacent unclaimed RED first.
        adj = _adj_unclaimed_reds(pos)
        if adj:
            adj.sort(
                key=lambda c: -(
                    int(red_positions[c].get("value")
                        or red_positions[c].get("purity") or 0)
                )
            )
            target = adj[0]
            moves.append({"a": "step", "unit": harvester_id,
                          "to": [int(target[0]), int(target[1])]})
            claimed.add(target)
            pos = target
            steps_used += 1
            continue

        # Phase 2 — lookahead BFS through empty/non-avoid cells.
        path = _bfs_to_red(
            start=pos, red_positions=red_positions, claimed=claimed,
            width=width, height=height, max_dist=remaining,
            avoid_cells=avoid_cells,
        )
        if path is None or len(path) > remaining:
            break  # Nothing reachable within budget — end chain.
        # The path's terminal cell is the unclaimed RED. Intermediate
        # cells are empty (or BFS would not have stepped through them).
        for cell in path:
            moves.append({"a": "step", "unit": harvester_id,
                          "to": [int(cell[0]), int(cell[1])]})
            steps_used += 1
        target = path[-1]
        claimed.add(target)
        pos = target

    return moves


# ── enemy probe inspection ───────────────────────────────────────────
def _known_enemy_probes(agent_view: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Surface every enemy probe we currently know about.

    Sources, in priority order:

    * ``world.grid`` cells with an ``entity.kind == "probe"`` belonging to
      a non-self owner — these are LIVE sightings inside our LOS.
    * ``competitor_intel.new_this_day[*].kind == "enemy_probe_launch"`` —
      orbital publicity (RULEBOOK §3.15) for this hour's launches.
    * ``competitor_intel.persistent_echoes[*].kind ~= "probe"`` — older
      sightings the engine still stamps onto our memory.

    Returns dicts with ``at``, ``last_seen_day``, and ``source``.
    """
    me = str((agent_view.get("meta") or {}).get("player") or "")
    out: Dict[Tuple[int, int], Dict[str, Any]] = {}
    width, height = _world_dims(agent_view)

    world = agent_view.get("world") or {}
    grid = world.get("grid")
    cur_day = int((agent_view.get("meta") or {}).get("day") or 0)
    if isinstance(grid, list):
        for y, row in enumerate(grid):
            if not isinstance(row, list):
                continue
            for x, cell in enumerate(row):
                if _is_enemy_probe_cell(cell, me):
                    out[(x, y)] = {
                        "at": [x, y],
                        "last_seen_day": cur_day,
                        "source": "live",
                    }

    intel = agent_view.get("competitor_intel") or {}
    for r in intel.get("new_this_day") or []:
        if not isinstance(r, dict):
            continue
        if "probe" not in str(r.get("kind") or "").lower():
            continue
        at = r.get("at")
        if not (isinstance(at, (list, tuple)) and len(at) == 2):
            continue
        try:
            x, y = int(at[0]), int(at[1])
        except (TypeError, ValueError):
            continue
        if width and height and not (0 <= x < width and 0 <= y < height):
            continue
        existing = out.get((x, y))
        rec = {
            "at": [x, y],
            "last_seen_day": int(r.get("day") or r.get("last_seen_day") or cur_day),
            "source": "fresh_publicity",
        }
        if existing is None or rec["last_seen_day"] >= existing["last_seen_day"]:
            out[(x, y)] = rec

    for r in intel.get("persistent_echoes") or []:
        if not isinstance(r, dict):
            continue
        if "probe" not in str(r.get("kind") or "").lower():
            continue
        at = r.get("at")
        if not (isinstance(at, (list, tuple)) and len(at) == 2):
            continue
        try:
            x, y = int(at[0]), int(at[1])
        except (TypeError, ValueError):
            continue
        if (x, y) in out:
            continue
        out[(x, y)] = {
            "at": [x, y],
            "last_seen_day": int(r.get("last_seen_day") or 0),
            "source": "persistent_echo",
        }
    return list(out.values())


def _enemy_probe_disk_cells(
    agent_view: Mapping[str, Any], probes: Sequence[Mapping[str, Any]]
) -> Set[Tuple[int, int]]:
    """Union of cells inside every known enemy probe's Euclidean disk."""
    width, height = _world_dims(agent_view)
    if width <= 0 or height <= 0:
        return set()
    radius = int(((agent_view.get("meta") or {}).get("rules") or {}).get("probe_radius") or 4)
    r2 = radius * radius
    out: Set[Tuple[int, int]] = set()
    for p in probes:
        at = p.get("at")
        if not (isinstance(at, (list, tuple)) and len(at) == 2):
            continue
        try:
            cx, cy = int(at[0]), int(at[1])
        except (TypeError, ValueError):
            continue
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if dx * dx + dy * dy > r2:
                    continue
                x, y = cx + dx, cy + dy
                if 0 <= x < width and 0 <= y < height:
                    out.add((x, y))
    return out


# ── §3.14 vault cascade simulation ───────────────────────────────────
def _cascade_red_value(incoming_purity: int, vault_red_min: Optional[int]) -> int:
    """Return the score this incoming RED parcel actually banks after cascade.

    Per §3.14: a RED parcel into a vault that already holds RED only
    displaces the lowest-purity vault RED IFF the incoming RED *strictly
    exceeds* it; otherwise the incoming RED is JETTISONED (zero score).
    """
    if vault_red_min is None:
        return int(incoming_purity)
    return int(incoming_purity) if int(incoming_purity) > int(vault_red_min) else 0


def _vault_state(agent_view: Mapping[str, Any]) -> Dict[str, Any]:
    hud = agent_view.get("hud") or {}
    hoard = hud.get("hoard") or {}
    by_tier = hoard.get("by_tier") or {}
    red = by_tier.get("RED") or {}
    blue = by_tier.get("BLUE") or {}
    return {
        "hoard_used": int(hoard.get("used") or hoard.get("count") or 0),
        "hoard_max": int(hoard.get("max") or hoard.get("capacity") or 0),
        "warning": hoard.get("warning"),
        "red_min": int(red["purity_min"]) if isinstance(red.get("purity_min"), int) else None,
        "red_max": int(red["purity_max"]) if isinstance(red.get("purity_max"), int) else None,
        "blue_count": int(blue.get("count") or 0),
        "free": int(hoard.get("free") or 0),
    }


# ── harvest candidate compilation ────────────────────────────────────
def _score_target(
    target: Dict[str, Any],
    candidates_pool: List[Dict[str, Any]],
    mult_map: Dict[str, float],
    *,
    max_steps: int,
) -> float:
    """Cluster-aware target ranking — sum of tier-weighted neighbours / (1+d)."""
    tx, ty = int(target["x"]), int(target["y"])
    total = 0.0
    for r in candidates_pool:
        try:
            d = _manhattan((int(r["x"]), int(r["y"])), (tx, ty))
        except (KeyError, TypeError, ValueError):
            continue
        if d <= max_steps:
            total += _parcel_score(r, mult_map) / (1 + d)
    return total


def _harvest_candidates_for(
    *,
    harvester: Mapping[str, Any],
    agent_view: Mapping[str, Any],
    red_pool: List[Dict[str, Any]],
    avoid_cells: Set[Tuple[int, int]],
    enemy_disk_cells: Set[Tuple[int, int]],
    enemy_history: Set[Tuple[int, int]],
    vault: Dict[str, Any],
    k: int,
    seat: str,
    heatmap: Optional["_ta.Heatmap"] = None,
    risky_collision_cells: Optional[Mapping[Tuple[int, int], int]] = None,
    emp_signal: Optional[Mapping[str, Any]] = None,
    shared_claimed: Optional[Set[Tuple[int, int]]] = None,
) -> List[Dict[str, Any]]:
    """Top-K complete chains for one harvester (drop+steps+pickup or surface walk)."""
    width, height = _world_dims(agent_view)
    if width <= 0 or height <= 0:
        return []

    harv_id = str(harvester.get("id") or "harvester_p1")
    pos_raw = harvester.get("at") if harvester.get("at") is not None else harvester.get("pos")
    damaged = bool(harvester.get("damaged"))
    state = str(harvester.get("state") or "").lower()
    surface = pos_raw is not None and state in ("deployed", "surface")
    # Drop-legality gate: use _drop_targetable_cells (which is LIVE-only
    # under live_only mode). Earlier this was _visible_or_echo_cells
    # which let echo cells through and produced chains the engine then
    # refused at PRAXIS time (the "no live sensor beacon" failures).
    drop_targetable = _drop_targetable_cells(agent_view)
    mult_map = _tier_mult_map(agent_view)

    # Damaged + surface — only legal move is pickup.
    if damaged and surface:
        return [{
            "id": f"{harv_id}__pickup",
            "unit": harv_id,
            "kind": "damaged_pickup",
            "target": None,
            "moves": [{"a": "pickup", "unit": harv_id}],
            "expected_score_raw": 0,
            "expected_score_after_vault_cascade": 0,
            "chain_red_purities": [],
            "slots_used": 0,
            "cells_traversed": [pos_raw],
            "score_breakdown": {"note": "damaged — pickup only"},
            "score": -1.0,
            "flags": {
                "damaged": True,
                "enemy_can_see_drop": False,
                "enemy_has_ever_seen_drop": False,
                "synthetic_green_crossings": 0,
                "route_through_collision": False,
            },
        }]

    if damaged:
        # Damaged in orbit — orbit phase repairs it, no night chain.
        return []

    # Sort red_pool by cluster value to seed candidates.
    if not red_pool:
        return []
    # Sort red_pool by cluster value to seed candidates. Pure cells get
    # a one-shot bias so chains starting near them are enumerated FIRST
    # — the chain-scoring bonus (below) is large enough that we want
    # them on the K-shortlist by default.
    def _seed_sort_key(r: Mapping[str, Any]) -> float:
        base = _score_target(r, red_pool, mult_map, max_steps=MAX_HARVESTER_STEPS)
        try:
            purity = int(r.get("value") or r.get("purity") or 0)
        except (TypeError, ValueError):
            purity = 0
        pure_bias = 500.0 if purity >= _ta.PURE_PURITY_THRESHOLD else 0.0
        return -(base + pure_bias)

    sorted_red = sorted(red_pool, key=_seed_sort_key)
    out: List[Dict[str, Any]] = []
    seen_targets: Set[Tuple[int, int]] = set()
    sibling_claimed: Set[Tuple[int, int]] = set(shared_claimed or set())

    for tgt in sorted_red:
        if len(out) >= k:
            break
        try:
            tx, ty = int(tgt["x"]), int(tgt["y"])
        except (KeyError, TypeError, ValueError):
            continue
        target_xy = (tx, ty)
        if target_xy in seen_targets:
            continue
        # Doctrine: don't seed a chain at a target a sibling harvester
        # has already claimed in this turn's plan. Picking the same
        # target produces a chain that walks through synthetic-green
        # cells the first harvester turned out — banking zero.
        if target_xy in sibling_claimed:
            continue
        seen_targets.add(target_xy)

        # Build a chain. We need:
        # - a drop cell (orbital harvester) OR start_pos (surface harvester)
        # - up to MAX_HARVESTER_STEPS step moves toward target (greedy)
        # - terminal pickup
        chain_moves: List[Dict[str, Any]] = []
        cells: List[Tuple[int, int]] = []
        chain_kind: str

        if surface:
            chain_kind = "surface_walk"
            start = (int(pos_raw[0]), int(pos_raw[1]))
            cells.append(start)
            # Use _walk_with_lookahead so the chain can bridge gaps
            # between RED clusters (e.g. detour around green walls).
            red_copy = [dict(r) for r in red_pool]  # local mutable copy
            claimed_local: Set[Tuple[int, int]] = set(shared_claimed or set())
            steps = _walk_with_lookahead(
                start=start,
                red_tiles=red_copy,
                harvester_id=harv_id,
                width=width,
                height=height,
                max_steps=MAX_HARVESTER_STEPS,
                claimed=claimed_local,
                avoid_cells=avoid_cells,
                heatmap=heatmap,
                risky_collision_cells=risky_collision_cells,
            )
            for m in steps:
                chain_moves.append(m)
                to = m.get("to")
                if isinstance(to, (list, tuple)) and len(to) == 2:
                    cells.append((int(to[0]), int(to[1])))
            if not steps:
                # No reachable RED from current position. Skip this target.
                continue
        else:
            chain_kind = "orbit_drop"
            # Adjacent drop preferred; if target is a visible RED, do NOT
            # drop on it (auto-harvest wastes the drop tile).
            adj = _adjacent_drop_targets(target_xy, width=width, height=height, seat=seat)
            drop_at: Optional[Tuple[int, int]] = None
            for cand in adj:
                if cand in avoid_cells:
                    continue
                if not _is_valid_drop(agent_view, cand, drop_targetable):
                    continue
                drop_at = cand
                break
            if drop_at is None:
                continue
            chain_moves.append({"a": "drop", "unit": harv_id, "at": list(drop_at)})
            cells.append(drop_at)
            red_copy = [dict(r) for r in red_pool]
            claimed_local = set(shared_claimed or set())
            steps = _walk_with_lookahead(
                start=drop_at,
                red_tiles=red_copy,
                harvester_id=harv_id,
                width=width,
                height=height,
                max_steps=MAX_HARVESTER_STEPS,
                claimed=claimed_local,
                avoid_cells=avoid_cells,
                heatmap=heatmap,
                risky_collision_cells=risky_collision_cells,
            )
            for m in steps:
                chain_moves.append(m)
                to = m.get("to")
                if isinstance(to, (list, tuple)) and len(to) == 2:
                    cells.append((int(to[0]), int(to[1])))

        chain_moves.append({"a": "pickup", "unit": harv_id})

        # Score the chain: which cells in `cells` are RED, what's their purity.
        chain_red_purities: List[int] = []
        synthetic_green_crossings = 0
        route_through_collision = False
        for c in cells:
            grid_cell = _grid_cell(agent_view, c[0], c[1])
            if grid_cell is None:
                continue
            tile = str(grid_cell.get("tile") or "")
            if tile == "RED":
                purity = int(grid_cell.get("value") or grid_cell.get("purity") or 0)
                chain_red_purities.append(purity)
            elif _is_synthetic_green(grid_cell):
                synthetic_green_crossings += 1
            if _has_collision(grid_cell):
                route_through_collision = True

        red_score_raw = sum(chain_red_purities)
        red_score_cascaded = sum(
            _cascade_red_value(p, vault.get("red_min"))
            for p in sorted(chain_red_purities, reverse=True)
        )

        # Drop-cell publicity / history flags
        drop_xy: Tuple[int, int] = cells[0] if cells else target_xy
        enemy_can_see_drop = drop_xy in enemy_disk_cells
        enemy_has_ever_seen_drop = drop_xy in enemy_history

        # Composite score
        cluster_bonus = _score_target(
            tgt, red_pool, mult_map, max_steps=MAX_HARVESTER_STEPS
        )
        enemy_penalty = 80 if enemy_can_see_drop else 0
        publicity_penalty = 30 if enemy_has_ever_seen_drop and not enemy_can_see_drop else 0
        green_penalty = 60 * synthetic_green_crossings
        vault_jettison_penalty = (red_score_raw - red_score_cascaded)
        route_len_penalty = 5 * max(0, len(cells) - 1 - len(chain_red_purities))

        # v0.9.24 — heat as SIGNAL, not avoidance penalty.
        #
        # Heat marks where the rival is likely to strike. The model is:
        # * Compute mean heat along the chain (for shaping bonuses + abandon).
        # * Do NOT apply a survival-weighted expected-value penalty —
        #   that pushed our chain off pure cells in contested zones.
        # * Apply RACE_BONUS to short high-value chains under heat:
        #   "get in and out before they swing".
        # * Abandon ONLY when the chain is genuinely bad (low raw value
        #   AND high threat AND no pure cells). Pure-bearing chains
        #   never abandon.
        threat_cost = 0.0
        mean_heat = 0.0
        engage_r = 0.0
        survive_p = 1.0
        race_bonus_adj = 0.0
        abandoned = False
        risky_collision_used = any(c in (risky_collision_cells or {}) for c in cells)
        pure_in_chain = any(
            int(p) >= _ta.PURE_PURITY_THRESHOLD for p in chain_red_purities
        )
        if heatmap is not None and heatmap.width > 0 and cells:
            threat_cost = sum(heatmap.value_xy(c) for c in cells)
            mean_heat = threat_cost / max(1, len(cells))
            engage_r = _ta.engage_ratio(float(red_score_raw), threat_cost)
            survive_p = _ta.chain_survival_prob(heatmap, cells)
            # RACE_BONUS — short, high-value chains under heat get a
            # positive nudge. This replaces the old defensive penalty.
            action_count_preview = len(chain_moves)
            qualifies_value = (
                pure_in_chain or float(red_score_cascaded) >= _ta.RACE_BONUS_MIN_VALUE
            )
            qualifies_length = action_count_preview <= _ta.RACE_BONUS_MAX_ACTIONS
            if qualifies_value and qualifies_length:
                race_bonus_adj = _ta.RACE_BONUS * mean_heat
            # Abandon gate — only fires when the chain is genuinely
            # low-value AND contested. Pure-bearing chains are protected.
            if (
                not pure_in_chain
                and threat_cost > 0.5
                and engage_r < _ta.ABANDON_THRESHOLD
                and float(red_score_cascaded) < _ta.RACE_BONUS_MIN_VALUE
            ):
                abandoned = True
                race_bonus_adj -= _ta.ABANDON_PENALTY

        score = (
            float(red_score_cascaded)
            + 0.5 * cluster_bonus
            - enemy_penalty
            - publicity_penalty
            - green_penalty
            - vault_jettison_penalty
            - route_len_penalty
            + race_bonus_adj
        )

        # Alias for back-compat in score_breakdown (rename without
        # breaking downstream readers that grep the rationale logs).
        threat_score_adj = race_bonus_adj

        # Doctrine D-EMP-1 — front-load bonus / long-chain penalty when
        # an EMP threat is active. Chain ends with pickup; the action
        # count == hour at which the harvester is safely off-surface.
        # Chains finishing by hour 6 (EMP_FRONTLOAD_HOURS) are EMP-resilient.
        action_count = len(chain_moves)
        emp_resilient = action_count <= _ta.EMP_FRONTLOAD_HOURS
        emp_score_adj = 0.0
        emp_confidence = float((emp_signal or {}).get("confidence") or 0.0)
        if emp_confidence >= 0.5 and emp_signal and emp_signal.get("rival_built_weapon"):
            if emp_resilient:
                emp_score_adj = _ta.EMP_FRONTLOAD_BONUS * emp_confidence
            else:
                emp_score_adj = -_ta.EMP_LONGCHAIN_PENALTY * emp_confidence
        score += emp_score_adj

        # PURE-cell prioritization (v0.9.23, retuned v0.9.25).
        #
        # Pure cells ship for ~765 (255 × 3.0); mass for ~300 (200 × 1.5).
        # The raw-purity chain score severely undervalues both. Bonuses
        # bridge the gap so the compiler picks shipping-value-maximising
        # chains, not raw-purity-maximising chains. Within reason: the
        # walker still respects collision avoid_cells, so this is
        # aggressive scoring not suicidal pathing.
        pure_cell_count = sum(
            1 for p in chain_red_purities if int(p) >= _ta.PURE_PURITY_THRESHOLD
        )
        mass_cell_count = sum(
            1 for p in chain_red_purities
            if _ta.MASS_PURITY_THRESHOLD <= int(p) < _ta.PURE_PURITY_THRESHOLD
        )
        pure_score_adj = 0.0
        if pure_cell_count > 0:
            pure_score_adj = (
                _ta.PURE_CELL_BONUS * pure_cell_count
                + _ta.PURE_CHAIN_PRIORITY_BONUS
            )
        if mass_cell_count > 0:
            pure_score_adj += _ta.MASS_CELL_BONUS * mass_cell_count
        score += pure_score_adj

        out.append({
            "id": f"H{len(out)}_{harv_id}",
            "unit": harv_id,
            "kind": chain_kind,
            "target": {
                "x": tx,
                "y": ty,
                "value": int(tgt.get("value") or tgt.get("purity") or 0),
                "tier": _tier_of(int(tgt.get("value") or tgt.get("purity") or 0)),
            },
            "moves": chain_moves,
            "expected_score_raw": int(red_score_raw),
            "expected_score_after_vault_cascade": int(red_score_cascaded),
            "chain_red_purities": chain_red_purities,
            "slots_used": min(6, len(chain_red_purities)),
            "cells_traversed": [list(c) for c in cells],
            "score_breakdown": {
                "red_cascaded": int(red_score_cascaded),
                "cluster_bonus": round(cluster_bonus, 2),
                "enemy_penalty": int(enemy_penalty),
                "publicity_penalty": int(publicity_penalty),
                "green_penalty": int(green_penalty),
                "vault_jettison_penalty": int(vault_jettison_penalty),
                "route_len_penalty": int(route_len_penalty),
                "threat_cost": round(threat_cost, 3),
                "engage_ratio": round(engage_r, 3),
                "chain_survival_prob": round(survive_p, 3),
                "threat_score_adj": round(threat_score_adj, 2),
                "emp_score_adj": round(emp_score_adj, 2),
                "pure_score_adj": round(pure_score_adj, 2),
                "pure_cell_count": int(pure_cell_count),
                "mass_cell_count": int(mass_cell_count),
            },
            "score": round(score, 2),
            "flags": {
                "enemy_can_see_drop": bool(enemy_can_see_drop),
                "enemy_has_ever_seen_drop": bool(enemy_has_ever_seen_drop),
                "synthetic_green_crossings": int(synthetic_green_crossings),
                "route_through_collision": bool(route_through_collision),
                "damaged": False,
                "abandoned_low_engage_ratio": bool(abandoned),
                "risky_collision_used": bool(risky_collision_used),
                "emp_resilient": bool(emp_resilient),
                "action_count": int(action_count),
                "contains_pure": bool(pure_cell_count > 0),
            },
        })

    out.sort(key=lambda c: -c["score"])
    return out[:k]


# ── probe candidates ─────────────────────────────────────────────────
def _probe_candidates(
    *,
    agent_view: Mapping[str, Any],
    enemy_disk_cells: Set[Tuple[int, int]],
    enemy_history: Set[Tuple[int, int]],
    enemy_probes: List[Dict[str, Any]],
    used_drops: List[Tuple[int, int]],
    k: int,
) -> List[Dict[str, Any]]:
    """Top-K probe placements ranked by fog yield + RED-bracket bonus."""
    width, height = _world_dims(agent_view)
    if width <= 0 or height <= 0:
        return []
    radius = int(((agent_view.get("meta") or {}).get("rules") or {}).get("probe_radius") or 4)
    r2 = radius * radius
    visible = _visible_or_echo_cells(agent_view)
    fog_cells = {
        (x, y)
        for y in range(height)
        for x in range(width)
        if (x, y) not in visible
    }

    nav = agent_view.get("navigation") or {}
    # v0.9.26 — Pass 1 (RED bracket) should fire for ECHO red too, not just
    # LIVE-visible red. Pure cells are rare (3-4 per 40x28 board) so the
    # window when they're LIVE is tiny — but the echo memory persists.
    # Probing near a pure echo re-establishes LOS on the seam we glimpsed
    # and lets the chain compiler emit a chain that touches the pure on
    # subsequent nights. Without this fix, the agent finds a pure cell
    # on day N, loses LOS, and never returns to it.
    red_seed_pool: List[Mapping[str, Any]] = []
    for r in (nav.get("best_red_visible") or []):
        red_seed_pool.append(r)
    for r in (nav.get("best_red_echo") or []):
        red_seed_pool.append(r)
    for r in (agent_view.get("red_tiles") or []):
        red_seed_pool.append(r)
    # De-duplicate by (x,y) preserving the highest-purity entry.
    red_visible: List[Mapping[str, Any]] = []
    _seen_red_pts: Set[Tuple[int, int]] = set()
    for r in red_seed_pool:
        if not isinstance(r, Mapping):
            continue
        try:
            rx, ry = int(r.get("x")), int(r.get("y"))
        except (TypeError, ValueError):
            continue
        if (rx, ry) in _seen_red_pts:
            continue
        _seen_red_pts.add((rx, ry))
        red_visible.append(r)
    fog_clusters = nav.get("fog_clusters") or agent_view.get("fog_clusters") or []
    min_sep = max(6, radius)

    # Existing own probes: avoid stacking near them.
    own_probes: List[Tuple[int, int]] = []
    for ent in (agent_view.get("entities") or {}).get("mine") or []:
        if (ent or {}).get("type") == "probe":
            pos = ent.get("pos") or ent.get("at")
            if isinstance(pos, (list, tuple)) and len(pos) == 2:
                try:
                    own_probes.append((int(pos[0]), int(pos[1])))
                except (TypeError, ValueError):
                    pass

    placed: List[Tuple[int, int]] = list(used_drops)
    placed.extend(own_probes)

    def _too_close(pt: Tuple[int, int]) -> bool:
        return any(_manhattan(pt, q) < min_sep for q in placed)

    def _fog_yield(pt: Tuple[int, int]) -> int:
        n = 0
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if dx * dx + dy * dy > r2:
                    continue
                if (pt[0] + dx, pt[1] + dy) in fog_cells:
                    n += 1
        return n

    def _adjacent_red_max(pt: Tuple[int, int]) -> int:
        best = 0
        for r in red_visible:
            try:
                rx, ry = int(r["x"]), int(r["y"])
            except (KeyError, TypeError, ValueError):
                continue
            if (pt[0] - rx) ** 2 + (pt[1] - ry) ** 2 <= r2:
                best = max(best, int(r.get("value") or r.get("purity") or 0))
        return best

    candidates: List[Dict[str, Any]] = []
    seen: Set[Tuple[int, int]] = set()

    # Pass 1: RED-bracket — cells just inside the disk of a visible RED.
    for r in red_visible:
        try:
            rx, ry = int(r["x"]), int(r["y"])
        except (KeyError, TypeError, ValueError):
            continue
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if dx * dx + dy * dy > r2:
                    continue
                x, y = rx + dx, ry + dy
                if not (0 <= x < width and 0 <= y < height):
                    continue
                if (x, y) in seen:
                    continue
                fy = _fog_yield((x, y))
                if fy == 0:
                    continue
                seen.add((x, y))
                candidates.append({
                    "_pt": (x, y),
                    "fog_yield": fy,
                    "adjacent_red_max_value": _adjacent_red_max((x, y)),
                    "mode": "red_bracket",
                })

    # Pass 2: largest fog clusters.
    for cluster in fog_clusters:
        anchor = cluster.get("centroid") or cluster.get("nearest_visible_edge")
        if not (isinstance(anchor, (list, tuple)) and len(anchor) == 2):
            continue
        try:
            x, y = int(anchor[0]), int(anchor[1])
        except (TypeError, ValueError):
            continue
        if not (0 <= x < width and 0 <= y < height):
            continue
        if (x, y) in seen:
            continue
        seen.add((x, y))
        candidates.append({
            "_pt": (x, y),
            "fog_yield": _fog_yield((x, y)),
            "adjacent_red_max_value": _adjacent_red_max((x, y)),
            "mode": "largest_cluster",
        })

    # Pass 3: enemy-disk break — drop a probe inside an enemy probe's disk
    # to contest visibility (and possibly supersede next turn).
    for ep in enemy_probes:
        at = ep.get("at")
        if not (isinstance(at, (list, tuple)) and len(at) == 2):
            continue
        try:
            ex, ey = int(at[0]), int(at[1])
        except (TypeError, ValueError):
            continue
        for dy in range(-1, 2):
            for dx in range(-1, 2):
                if dx == 0 and dy == 0:
                    continue
                x, y = ex + dx, ey + dy
                if not (0 <= x < width and 0 <= y < height):
                    continue
                if (x, y) in seen:
                    continue
                seen.add((x, y))
                candidates.append({
                    "_pt": (x, y),
                    "fog_yield": _fog_yield((x, y)),
                    "adjacent_red_max_value": _adjacent_red_max((x, y)),
                    "mode": "enemy_disk_overlap_break",
                })

    # Pass 4 — quadrant-spread fallback. When passes 1-3 produce fewer
    # than ``k`` viable candidates (common on day 1 when the whole map
    # is one fog cluster), seed up to one extra candidate per quadrant.
    #
    # v0.9.26 — anchor each quadrant at its QUARTILE CENTER, not at the
    # corner-clamped "highest fog_yield" cell. With no visible RED to
    # bracket and one whole-map fog cluster, fog_yield is nearly uniform
    # across the interior, so the old code's "max fog_yield" tie-break
    # picked whichever cell came first in iteration order — which was
    # the (radius, radius) corner of each quadrant. That clustered the
    # 4 probes in a tight grid offset from the corners, covering ~15%
    # of the map. Quartile centers ((1/4, 1/4), (3/4, 1/4), (1/4, 3/4),
    # (3/4, 3/4)) cover ~22% with the same probe count and crucially
    # span the centre of the map where RED clusters most often live.
    if len(candidates) < k:
        quartile_centers = [
            (width // 4,     height // 4),       # NW
            (3 * width // 4, height // 4),       # NE
            (width // 4,     3 * height // 4),   # SW
            (3 * width // 4, 3 * height // 4),   # SE
        ]
        for (qx, qy) in quartile_centers:
            if len(candidates) >= k:
                break
            # Clamp to legal probe placement (interior, away from edges).
            x = max(radius, min(qx, width - radius - 1))
            y = max(radius, min(qy, height - radius - 1))
            if (x, y) in seen:
                continue
            # Sep filter against already-emitted candidates.
            if any(
                _manhattan((x, y), c["_pt"]) < min_sep
                for c in candidates
            ):
                continue
            fy = _fog_yield((x, y))
            if fy <= 0:
                continue
            seen.add((x, y))
            candidates.append({
                "_pt": (x, y),
                "fog_yield": fy,
                "adjacent_red_max_value": _adjacent_red_max((x, y)),
                "mode": "quadrant_fallback",
            })

    # Score and rank: fog_yield + adjacent_red bonus, with sep penalty.
    scored: List[Dict[str, Any]] = []
    for c in candidates:
        pt = c["_pt"]
        sep_ok = not _too_close(pt)
        bonus = int(c["adjacent_red_max_value"])
        score = c["fog_yield"] * 10 + bonus
        if not sep_ok:
            score -= 200
        scored.append({
            **c,
            "min_sep_ok": sep_ok,
            "score": score,
            "enemy_can_see_drop_via_publicity": True,  # always true per §3.15
            "enemy_has_ever_seen_pt": pt in enemy_history,
        })
    scored.sort(key=lambda c: -c["score"])

    out: List[Dict[str, Any]] = []
    used: Set[Tuple[int, int]] = set()
    for c in scored:
        if len(out) >= k:
            break
        pt = c["_pt"]
        if pt in used or not c["min_sep_ok"]:
            continue
        used.add(pt)
        out.append({
            "id": f"P{len(out)}",
            "at": list(pt),
            "mode": c["mode"],
            "fog_yield": int(c["fog_yield"]),
            "adjacent_red_max_value": int(c["adjacent_red_max_value"]),
            "min_sep_ok": True,
            "score": int(c["score"]),
            "flags": {
                "enemy_can_see_drop_via_publicity": True,
                "enemy_has_ever_seen_pt": bool(c["enemy_has_ever_seen_pt"]),
            },
        })
    return out


# ── supersede / crush candidates ─────────────────────────────────────
def _supersede_candidates(
    *,
    agent_view: Mapping[str, Any],
    enemy_probes: Sequence[Mapping[str, Any]],
    nav_red_pool: List[Dict[str, Any]],
    k: int = 2,
    heatmap: Optional["_ta.Heatmap"] = None,
    my_probes_available: int = 0,
) -> List[Dict[str, Any]]:
    """Probes-on-enemy-probes (RULEBOOK §3.16). Voids their disk, keeps yours.

    Doctrine 2 — when the superseded zone has high RED density AND high
    enemy_knowledge (they have eyes on juicy red) AND we have probe
    budget to spare, boost the supersede score and stamp an intent
    flagging the two-move (preempt now, drop tomorrow).
    """
    width, height = _world_dims(agent_view)
    radius = int(((agent_view.get("meta") or {}).get("rules") or {}).get("probe_radius") or 4)
    r2 = radius * radius
    out: List[Dict[str, Any]] = []
    for ep in enemy_probes:
        at = ep.get("at")
        if not (isinstance(at, (list, tuple)) and len(at) == 2):
            continue
        try:
            x, y = int(at[0]), int(at[1])
        except (TypeError, ValueError):
            continue
        if width and height and not (0 <= x < width and 0 <= y < height):
            continue
        # Value unlocked = max RED purity inside the disk we'd inherit.
        unlocked = 0
        for r in nav_red_pool:
            try:
                rx, ry = int(r["x"]), int(r["y"])
            except (KeyError, TypeError, ValueError):
                continue
            if (rx - x) ** 2 + (ry - y) ** 2 <= r2:
                unlocked = max(unlocked, int(r.get("value") or r.get("purity") or 0))

        # Doctrine 2 — compute zone-level red density and enemy_knowledge
        # and apply the juicy-contest boost when conditions are met.
        nearby_red_density = 0
        for r in nav_red_pool:
            try:
                rx, ry = int(r["x"]), int(r["y"])
            except (KeyError, TypeError, ValueError):
                continue
            if abs(rx - x) + abs(ry - y) <= 3:
                nearby_red_density += int(r.get("value") or r.get("purity") or 0)
        enemy_knew_zone = 0.0
        if heatmap is not None and heatmap.width > 0:
            zone_cells = [
                (cx, cy)
                for cy in range(max(0, y - 2), min(heatmap.height, y + 3))
                for cx in range(max(0, x - 2), min(heatmap.width, x + 3))
            ]
            ek_values = [heatmap.layer_enemy_knowledge[cy][cx] for (cx, cy) in zone_cells]
            if ek_values:
                enemy_knew_zone = sum(ek_values) / len(ek_values)

        boosted = False
        intent: Optional[str] = None
        followup_hint: Optional[str] = None
        score_value = float(unlocked)
        if (
            nearby_red_density > _ta.HIGH_VALUE_THRESHOLD
            and enemy_knew_zone > 0.5
            and my_probes_available > 0
        ):
            boosted = True
            score_value *= _ta.JUICY_CONTEST_BOOST
            intent = (
                "preempt enemy day-1 vision over juicy red; "
                "denies their drop and sets up ours tomorrow"
            )
            # Find the strongest RED inside the zone to project the followup.
            best_target: Optional[Tuple[int, int, int]] = None
            for r in nav_red_pool:
                try:
                    rx, ry = int(r["x"]), int(r["y"])
                    rv = int(r.get("value") or r.get("purity") or 0)
                except (KeyError, TypeError, ValueError):
                    continue
                if (rx - x) ** 2 + (ry - y) ** 2 <= r2:
                    if best_target is None or rv > best_target[2]:
                        best_target = (rx, ry, rv)
            if best_target is not None:
                followup_hint = f"expected_drop_target=({best_target[0]},{best_target[1]})"

        # §3.16 — recommend supersede land at action slot >= 2 to avoid
        # mutual annihilation if enemy probes the same cell at slot 1.
        out.append({
            "id": f"S{len(out)}",
            "at": [x, y],
            "enemy_probe_last_seen_day": int(ep.get("last_seen_day") or 0),
            "value_unlocked": int(unlocked),
            "moves": [{"a": "probe", "at": [x, y]}],
            "score": round(score_value, 2),
            "nearby_red_density": int(nearby_red_density),
            "enemy_knew_zone": round(enemy_knew_zone, 3),
            "boosted_juicy_contest": bool(boosted),
            "intent": intent,
            "followup_hint": followup_hint,
            "action_slot_advice": "place at action slot >= 2 to avoid §3.16 mutual annihilation",
        })
    out.sort(key=lambda c: -float(c.get("score", c.get("value_unlocked", 0))))
    return out[:k]


def _crush_candidates(
    *,
    agent_view: Mapping[str, Any],
    enemy_probes: Sequence[Mapping[str, Any]],
    nav_red_pool: List[Dict[str, Any]],
    my_orbit_harvesters: Sequence[Mapping[str, Any]],
    seat: str,
    k: int = 2,
    heatmap: Optional["_ta.Heatmap"] = None,
) -> List[Dict[str, Any]]:
    """Drop a harvester onto a known enemy probe square (in our LIVE LOS).

    The harvester crushes the probe (RULEBOOK §3.17 doesn't apply —
    harvester-on-probe is one-sided). The drop is only legal if the cell
    is ``_is_valid_drop``. Then we add a pickup so we don't dawn-die.

    v0.9.24 — under high local heat, crush gets an OFFENSIVE_RESPONSE_BONUS:
    the enemy probe at this cell is part of the strike signature, so
    removing it both denies their LOS and removes future heat.
    """
    if not my_orbit_harvesters:
        return []
    width, height = _world_dims(agent_view)
    visible_set = _drop_targetable_cells(agent_view)
    radius = int(((agent_view.get("meta") or {}).get("rules") or {}).get("probe_radius") or 4)
    r2 = radius * radius
    out: List[Dict[str, Any]] = []
    used_units: Set[str] = set()
    for ep in enemy_probes:
        if len(out) >= k:
            break
        at = ep.get("at")
        if not (isinstance(at, (list, tuple)) and len(at) == 2):
            continue
        try:
            x, y = int(at[0]), int(at[1])
        except (TypeError, ValueError):
            continue
        if width and height and not (0 <= x < width and 0 <= y < height):
            continue
        # Pick first available orbit harvester not already used in another crush.
        unit_id: Optional[str] = None
        for h in my_orbit_harvesters:
            hid = str(h.get("id") or "")
            if not hid or hid in used_units:
                continue
            unit_id = hid
            break
        if unit_id is None:
            break
        # Drop must be live-legal.
        if not _is_valid_drop(agent_view, (x, y), visible_set):
            continue
        # Value released: best RED in the now-claimed disk.
        unlocked = 0
        for r in nav_red_pool:
            try:
                rx, ry = int(r["x"]), int(r["y"])
            except (KeyError, TypeError, ValueError):
                continue
            if (rx - x) ** 2 + (ry - y) ** 2 <= r2:
                unlocked = max(unlocked, int(r.get("value") or r.get("purity") or 0))
        used_units.add(unit_id)
        # v0.9.24 — offensive response bonus tied to local heat.
        local_heat = 0.0
        if heatmap is not None and heatmap.width > 0:
            local_heat = float(heatmap.value_xy((x, y)) or 0.0)
        offensive_response_adj = _ta.OFFENSIVE_RESPONSE_BONUS * local_heat
        score = float(unlocked) + offensive_response_adj
        out.append({
            "id": f"C{len(out)}",
            "unit": unit_id,
            "at": [x, y],
            "value_after_crush": int(unlocked),
            "score": score,
            "moves": [
                {"a": "drop", "unit": unit_id, "at": [x, y]},
                {"a": "pickup", "unit": unit_id},
            ],
            "legal_under_live_only": True,
            "flags": {
                "local_heat": round(local_heat, 3),
                "offensive_response_adj": round(offensive_response_adj, 2),
            },
        })
    out.sort(key=lambda c: -float(c.get("score") or c["value_after_crush"]))
    return out[:k]


# ── hot-drop pairs (§3.9.8) ──────────────────────────────────────────
def _hot_drop_pairs(
    *,
    agent_view: Mapping[str, Any],
    nav_red_pool: List[Dict[str, Any]],
    nav_red_echo_pool: List[Dict[str, Any]],
    my_orbit_harvesters: Sequence[Mapping[str, Any]],
    avoid_cells: Set[Tuple[int, int]],
    enemy_disk_cells: Set[Tuple[int, int]],
    seat: str,
    k: int = 2,
    heatmap: Optional["_ta.Heatmap"] = None,
    memory: Optional[Mapping[str, Any]] = None,
    current_day: int = 0,
    posture: Optional[Mapping[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Same-night probe + drop pairs (§3.9.8).

    Emits up to three flavours:

    * ``hot_drop_echo_revisit`` (always available): re-probe a high-value
      RED that we knew about but no longer have live coverage on.
    * ``hot_drop_speculative`` (Doctrine 4a): gamble a probe into a
      high-red_magnet, low-enemy_knowledge fog cell. Only emitted from
      day ``SPECULATIVE_HOT_DROP_DAY_GUARD`` onwards.
    * ``hot_drop_counter_blind`` (Doctrine 4b): emit a recovery probe
      after a recent supersede-of-my-probe over juicy red.

    Per §3.9.8 — the probe validates the drop in the same hour because
    drop legality is judged against the hour-start live snapshot
    (§3.9.7).
    """
    if not my_orbit_harvesters:
        return []
    width, height = _world_dims(agent_view)
    out: List[Dict[str, Any]] = []

    # Posture-aware thresholds. Defaults match the legacy "balanced" tier.
    posture_label = (posture or {}).get("label", "balanced")
    hot_drop_value_floor = int(
        (posture or {}).get("hot_drop_value_floor", _ta.HOT_DROP_VALUE_FLOOR["balanced"])
    )
    speculative_day_guard = int(
        (posture or {}).get("speculative_day_guard", _ta.SPECULATIVE_HOT_DROP_DAY_GUARD)
    )

    # ── Variant: echo-revisit (legacy default) ───────────────────────
    candidates = sorted(
        list(nav_red_echo_pool),
        key=lambda r: -int(r.get("value") or r.get("purity") or 0),
    )
    used_units: Set[str] = set()
    for tgt in candidates:
        if len(out) >= k:
            break
        try:
            tx, ty = int(tgt["x"]), int(tgt["y"])
        except (KeyError, TypeError, ValueError):
            continue
        value = int(tgt.get("value") or tgt.get("purity") or 0)
        if value < hot_drop_value_floor:
            break
        adj = _adjacent_drop_targets((tx, ty), width=width, height=height, seat=seat)
        drop_at: Optional[Tuple[int, int]] = None
        for cand in adj:
            if cand in avoid_cells:
                continue
            drop_at = cand
            break
        if drop_at is None:
            continue
        unit_id: Optional[str] = None
        for h in my_orbit_harvesters:
            hid = str(h.get("id") or "")
            if not hid or hid in used_units:
                continue
            unit_id = hid
            break
        if unit_id is None:
            break
        used_units.add(unit_id)
        probe_at = drop_at
        step_to = (tx, ty) if _manhattan(drop_at, (tx, ty)) == 1 else None
        moves: List[Dict[str, Any]] = [
            {"a": "probe", "at": [probe_at[0], probe_at[1]]},
            {"a": "drop", "unit": unit_id, "at": [drop_at[0], drop_at[1]]},
        ]
        if step_to is not None:
            moves.append({"a": "step", "unit": unit_id, "to": [step_to[0], step_to[1]]})
        moves.append({"a": "pickup", "unit": unit_id})
        out.append({
            "id": f"HOT{len(out)}",
            "kind": "hot_drop_echo_revisit",
            "unit": unit_id,
            "target": {"x": tx, "y": ty, "value": value, "tier": _tier_of(value)},
            "probe_at": list(probe_at),
            "drop_at": list(drop_at),
            "moves": moves,
            "score": value,
            "action_slots": list(range(1, len(moves) + 1)),
            "flags": {
                "enemy_can_see_via_probe_publicity": True,
                "drop_inside_enemy_disk": drop_at in enemy_disk_cells,
            },
        })

    # ── Variant 4b: counter-blind hot-drop (priority over speculative) ────
    if memory is not None:
        recent_super = [
            r for r in (memory.get("my_probes_superseded") or [])
            if isinstance(r, Mapping)
            and current_day - int(r.get("day_superseded") or 0) <= _ta.COUNTER_BLIND_LOOKBACK_DAYS
        ]
        for r in recent_super:
            if len(out) >= k + 4:
                break
            zone = r.get("zone")
            if not (isinstance(zone, (list, tuple)) and len(zone) == 2):
                continue
            try:
                zx, zy = int(zone[0]), int(zone[1])
            except (TypeError, ValueError):
                continue
            # Only worth recovering if there's juicy RED still in the zone.
            best_red: Optional[Tuple[int, int, int]] = None
            for rt in nav_red_pool + nav_red_echo_pool:
                try:
                    rx, ry = int(rt["x"]), int(rt["y"])
                    rv = int(rt.get("value") or rt.get("purity") or 0)
                except (KeyError, TypeError, ValueError):
                    continue
                if abs(rx - zx) + abs(ry - zy) <= 3 and rv >= 100:
                    if best_red is None or rv > best_red[2]:
                        best_red = (rx, ry, rv)
            if best_red is None:
                continue
            unit_id = None
            for h in my_orbit_harvesters:
                hid = str(h.get("id") or "")
                if not hid or hid in used_units:
                    continue
                unit_id = hid
                break
            if unit_id is None:
                break
            used_units.add(unit_id)
            adj = _adjacent_drop_targets((best_red[0], best_red[1]), width=width, height=height, seat=seat)
            drop_at = None
            for cand in adj:
                if cand in avoid_cells:
                    continue
                drop_at = cand
                break
            if drop_at is None:
                continue
            probe_at = drop_at
            step_to = (best_red[0], best_red[1]) if _manhattan(drop_at, (best_red[0], best_red[1])) == 1 else None
            moves = [
                {"a": "probe", "at": [probe_at[0], probe_at[1]]},
                {"a": "drop", "unit": unit_id, "at": [drop_at[0], drop_at[1]]},
            ]
            if step_to is not None:
                moves.append({"a": "step", "unit": unit_id, "to": [step_to[0], step_to[1]]})
            moves.append({"a": "pickup", "unit": unit_id})
            days_ago = max(0, current_day - int(r.get("day_superseded") or 0))
            urgency = 1.5 if days_ago <= 1 else 1.0
            out.append({
                "id": f"HOTCB{len([c for c in out if c.get('kind') == 'hot_drop_counter_blind'])}",
                "kind": "hot_drop_counter_blind",
                "unit": unit_id,
                "target": {"x": best_red[0], "y": best_red[1], "value": best_red[2], "tier": _tier_of(best_red[2])},
                "probe_at": list(probe_at),
                "drop_at": list(drop_at),
                "moves": moves,
                "score": float(best_red[2]) * urgency,
                "action_slots": list(range(1, len(moves) + 1)),
                "intent": f"recover vision over juicy zone superseded {days_ago}d ago",
                "flags": {
                    "enemy_can_see_via_probe_publicity": True,
                    "drop_inside_enemy_disk": drop_at in enemy_disk_cells,
                    "counter_blind_recovery": True,
                },
            })

    # ── Variant 4a: speculative into fog ─────────────────────────────
    # Day guard is posture-aware: aggressive=day 1+, balanced=day 2+,
    # conservative=day 3+ (lockdown). When trailing on the final night,
    # the posture flips to aggressive and lets us gamble on fog reads.
    if (
        heatmap is not None
        and heatmap.width > 0
        and current_day >= speculative_day_guard
        and len(out) < k + 2
    ):
        # Find fog-ish cells with high red_magnet prior and low enemy_knowledge.
        # Use the heatmap's per-layer arrays for the prior shape.
        spec_candidates: List[Tuple[float, int, int]] = []
        for y in range(heatmap.height):
            for x in range(heatmap.width):
                rm = heatmap.layer_red_magnet[y][x]
                ek = heatmap.layer_enemy_knowledge[y][x]
                if rm >= _ta.FOG_GAMBLE_THRESHOLD and ek < 0.3:
                    spec_candidates.append((rm, x, y))
        spec_candidates.sort(key=lambda t: -t[0])
        for rm, tx, ty in spec_candidates[:3]:
            if (tx, ty) in avoid_cells:
                continue
            unit_id = None
            for h in my_orbit_harvesters:
                hid = str(h.get("id") or "")
                if not hid or hid in used_units:
                    continue
                unit_id = hid
                break
            if unit_id is None:
                break
            used_units.add(unit_id)
            adj = _adjacent_drop_targets((tx, ty), width=width, height=height, seat=seat)
            drop_at = None
            for cand in adj:
                if cand in avoid_cells:
                    continue
                drop_at = cand
                break
            if drop_at is None:
                continue
            probe_at = drop_at
            step_to = (tx, ty) if _manhattan(drop_at, (tx, ty)) == 1 else None
            moves = [
                {"a": "probe", "at": [probe_at[0], probe_at[1]]},
                {"a": "drop", "unit": unit_id, "at": [drop_at[0], drop_at[1]]},
            ]
            if step_to is not None:
                moves.append({"a": "step", "unit": unit_id, "to": [step_to[0], step_to[1]]})
            moves.append({"a": "pickup", "unit": unit_id})
            estimated_value = int(rm * 255)  # rough — prior strength → purity estimate
            out.append({
                "id": f"HOTSPEC{len([c for c in out if c.get('kind') == 'hot_drop_speculative'])}",
                "kind": "hot_drop_speculative",
                "unit": unit_id,
                "target": {"x": tx, "y": ty, "value": estimated_value, "tier": _tier_of(estimated_value)},
                "probe_at": list(probe_at),
                "drop_at": list(drop_at),
                "moves": moves,
                "score": float(estimated_value) * 0.7,  # 0.7 = uncertainty discount
                "action_slots": list(range(1, len(moves) + 1)),
                "confidence": "medium" if rm >= 0.75 else "low",
                "flags": {
                    "enemy_can_see_via_probe_publicity": True,
                    "drop_inside_enemy_disk": drop_at in enemy_disk_cells,
                    "speculative": True,
                },
            })

    # v0.9.24 — OFFENSIVE_RESPONSE_BONUS: hot-drops are an aggressive
    # response to enemy presence. Boost each variant's score by local
    # heat at the drop cell so high-heat zones favour hot-drop over
    # passive harvest.
    if heatmap is not None and heatmap.width > 0:
        for c in out:
            drop_at = c.get("drop_at")
            if not (isinstance(drop_at, (list, tuple)) and len(drop_at) == 2):
                continue
            try:
                dx, dy = int(drop_at[0]), int(drop_at[1])
            except (TypeError, ValueError):
                continue
            local_heat = float(heatmap.value_xy((dx, dy)) or 0.0)
            adj = _ta.OFFENSIVE_RESPONSE_BONUS * local_heat
            c["score"] = float(c.get("score") or 0.0) + adj
            flags = c.setdefault("flags", {})
            flags["local_heat"] = round(local_heat, 3)
            flags["offensive_response_adj"] = round(adj, 2)
        out.sort(key=lambda c: -float(c.get("score") or 0.0))

    return out


# ── drop-block candidates (§3.17 case 1) ─────────────────────────────
def _drop_block_candidates(
    *,
    agent_view: Mapping[str, Any],
    heatmap: Optional["_ta.Heatmap"],
    predicted_drops: Sequence[Mapping[str, Any]],
    my_orbit_harvesters: Sequence[Mapping[str, Any]],
    avoid_cells: Set[Tuple[int, int]],
    seat: str,
    k: int = 2,
) -> List[Dict[str, Any]]:
    """Pre-emptive drop onto a cell the enemy is expected to drop on (§3.17 case 1).

    If we drop a harvester onto cell C at an earlier action slot than the
    enemy's drop, their drop **fails** and their harvester stays damaged
    in orbit. Score = harvest value here + denial value + damage bonus.
    """
    if not my_orbit_harvesters or not predicted_drops:
        return []
    width, height = _world_dims(agent_view)
    visible_set = _drop_targetable_cells(agent_view)
    out: List[Dict[str, Any]] = []
    used_units: Set[str] = set()
    for pred in predicted_drops:
        if len(out) >= k:
            break
        at = pred.get("at")
        heat = float(pred.get("heat") or 0.0)
        if heat < _ta.DROP_BLOCK_HEAT_FLOOR:
            continue
        if not (isinstance(at, (list, tuple)) and len(at) == 2):
            continue
        try:
            x, y = int(at[0]), int(at[1])
        except (TypeError, ValueError):
            continue
        if (x, y) in avoid_cells:
            continue
        if not _is_valid_drop(agent_view, (x, y), visible_set):
            continue
        # Cell's own RED purity (if any).
        cell = _grid_cell(agent_view, x, y)
        harvest_value = 0
        if isinstance(cell, dict):
            tile = str(cell.get("tile") or "")
            if tile == "RED":
                try:
                    harvest_value = int(cell.get("value") or cell.get("purity") or 0)
                except (TypeError, ValueError):
                    harvest_value = 0
        # Denial value: rough estimate of what enemy would harvest here.
        denial_value = int(float(pred.get("score") or 0.0) * 255)
        unit_id: Optional[str] = None
        for h in my_orbit_harvesters:
            hid = str(h.get("id") or "")
            if not hid or hid in used_units:
                continue
            unit_id = hid
            break
        if unit_id is None:
            break
        used_units.add(unit_id)
        # v0.9.24 — OFFENSIVE_RESPONSE_BONUS: heat is a signal to lean
        # INTO offensive plays, not away. Drop-block is the canonical
        # offensive response at high-heat predicted-drop cells.
        offensive_response_adj = _ta.OFFENSIVE_RESPONSE_BONUS * heat
        out.append({
            "id": f"DB{len(out)}",
            "kind": "drop_block",
            "unit": unit_id,
            "at": [x, y],
            "harvest_value": int(harvest_value),
            "denial_value": int(denial_value),
            "harvester_damage_bonus": int(_ta.DROP_BLOCK_HARVESTER_DAMAGE_BONUS),
            "moves": [
                {"a": "drop", "unit": unit_id, "at": [x, y]},
                {"a": "pickup", "unit": unit_id},
            ],
            "action_slots": [1, 2],
            "score": float(
                harvest_value + denial_value
                + _ta.DROP_BLOCK_HARVESTER_DAMAGE_BONUS
                + offensive_response_adj
            ),
            "intent": "drop onto predicted enemy drop cell BEFORE their drop slot → §3.17 case 1 denies their drop",
            "flags": {
                "early_slot_required": True,
                "predicted_drop_heat": round(heat, 3),
                "offensive_response_adj": round(offensive_response_adj, 2),
            },
        })
    out.sort(key=lambda c: -float(c.get("score", 0)))
    return out[:k]


# ── threat compilation ───────────────────────────────────────────────
def compile_threat(
    agent_view: Mapping[str, Any],
    *,
    harvest: List[Dict[str, Any]],
    probe_choices: List[Dict[str, Any]],
    enemy_probes: List[Dict[str, Any]],
    enemy_disk_cells: Set[Tuple[int, int]],
    enemy_history: Set[Tuple[int, int]],
    vault: Dict[str, Any],
    heatmap: Optional["_ta.Heatmap"] = None,
    predicted_drops: Optional[Sequence[Mapping[str, Any]]] = None,
    memory_summary: Optional[Mapping[str, Any]] = None,
    posture: Optional[Mapping[str, Any]] = None,
    probe_budget: Optional[Mapping[str, Any]] = None,
    emp_signal: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    meta = agent_view.get("meta") or {}
    hud = agent_view.get("hud") or {}
    me = str(meta.get("player") or "")
    cur_day = int(meta.get("day") or 0)
    season_cap = int(hud.get("season_day_cap") or 7)

    # My fleet status from my_assets.
    my_assets = agent_view.get("my_assets") or []
    h_orbit = h_surface = h_damaged = h_destroyed = 0
    probes_deployed = 0
    probes_min_remain = None
    for a in my_assets:
        if not isinstance(a, dict):
            continue
        kind = str(a.get("kind") or "").lower()
        state = str(a.get("state") or "").lower()
        if kind == "harvester":
            if state == "destroyed":
                h_destroyed += 1
            elif a.get("damaged"):
                h_damaged += 1
            elif state in ("deployed", "surface"):
                h_surface += 1
            elif state == "orbit":
                h_orbit += 1
        if kind == "probe" and state in ("deployed", "surface"):
            probes_deployed += 1
            nr = a.get("nights_remaining")
            if isinstance(nr, int):
                probes_min_remain = nr if probes_min_remain is None else min(probes_min_remain, nr)

    # Reconcile probe count against the live grid: ``my_assets`` only
    # tracks asset *records*, but the engine surfaces deployed probes as
    # ``entities.mine`` rows + ``world.grid[*].entity`` cells. If those
    # disagree (the v0.9.18 case where probes are in the grid but no
    # asset record carries state="deployed"), the agent will spot the
    # mismatch and stall. Take the MAX of the two views so the threat
    # block reports a probe count consistent with what the agent sees in
    # the grid.
    probes_in_grid = 0
    grid_probe_cells: Set[Tuple[int, int]] = set()
    world = agent_view.get("world") or {}
    grid = world.get("grid")
    if isinstance(grid, list):
        for row in grid:
            if not isinstance(row, list):
                continue
            for cell in row:
                if not isinstance(cell, dict):
                    continue
                ent = cell.get("entity")
                if not isinstance(ent, dict):
                    continue
                if str(ent.get("kind") or ent.get("type") or "").lower() != "probe":
                    continue
                if str(ent.get("owner") or "") != str(me):
                    continue
                probes_in_grid += 1
    probes_in_entities = 0
    for ent in (agent_view.get("entities") or {}).get("mine") or []:
        if (ent or {}).get("type") == "probe":
            probes_in_entities += 1
    probes_deployed = max(probes_deployed, probes_in_grid, probes_in_entities)

    # Enemy fleet estimate from competitor_intel.
    intel = agent_view.get("competitor_intel") or {}
    new_today = intel.get("new_this_day") or []
    persistent = intel.get("persistent_echoes") or []
    enemy_probes_seen = len({(p["at"][0], p["at"][1]) for p in enemy_probes})
    enemy_harvesters_witnessed = sum(
        1 for r in new_today if "harvester" in str(r.get("kind") or "").lower()
    )

    # Per-candidate flags propagated up.
    candidates_with_enemy_can_see_drop = [
        c["id"] for c in harvest if c.get("flags", {}).get("enemy_can_see_drop")
    ]
    candidates_with_enemy_has_ever_seen_drop = [
        c["id"] for c in harvest if c.get("flags", {}).get("enemy_has_ever_seen_drop")
    ]

    # Hoard pressure / vault cascade.
    hoard = hud.get("hoard") or {}
    next_jettison = None
    if vault.get("blue_count", 0) > 0:
        next_jettison = "BLUE"
    elif vault.get("red_min") is not None and vault.get("hoard_used", 0) >= vault.get("hoard_max", 1):
        next_jettison = "RED"
    candidates_at_risk = [
        c["id"]
        for c in harvest
        if c.get("expected_score_after_vault_cascade", 0) < c.get("expected_score_raw", 0)
    ]

    # Shared vision between my live LOS and enemy probe disks.
    visible = _visible_or_echo_cells(agent_view)
    shared_vision_cells_count = sum(1 for c in visible if c in enemy_disk_cells)

    # Nearest enemy probe to my candidate chains.
    nearest = []
    for ep in enemy_probes:
        at = ep.get("at")
        if not (isinstance(at, (list, tuple)) and len(at) == 2):
            continue
        ex, ey = int(at[0]), int(at[1])
        # Min distance to any chain cell across all my candidates.
        best = None
        for cand in harvest:
            for c in cand.get("cells_traversed") or []:
                d = abs(c[0] - ex) + abs(c[1] - ey)
                best = d if best is None else min(best, d)
        nearest.append({
            "at": list(at),
            "dist": best if best is not None else -1,
            "last_seen_day": int(ep.get("last_seen_day") or 0),
            "source": ep.get("source", "unknown"),
        })
    nearest.sort(key=lambda r: (r["dist"] if r["dist"] >= 0 else 1_000_000))

    # Publicity risk: which of my own probe placements telegraph future moves.
    my_publicly_telegraphed_targets = []
    for ent in (agent_view.get("entities") or {}).get("mine") or []:
        if (ent or {}).get("type") != "probe":
            continue
        pos = ent.get("pos") or ent.get("at")
        if isinstance(pos, (list, tuple)) and len(pos) == 2:
            try:
                my_publicly_telegraphed_targets.append({
                    "at": [int(pos[0]), int(pos[1])],
                    "last_probe_day": cur_day,
                })
            except (TypeError, ValueError):
                pass

    return {
        "enemy_probe_proximity": {
            "nearest_to_my_targets": nearest[:6],
            "shared_vision_cells_count": int(shared_vision_cells_count),
            "candidates_with_enemy_can_see_drop": candidates_with_enemy_can_see_drop,
        },
        "enemy_history": {
            "candidates_with_enemy_has_ever_seen_drop": candidates_with_enemy_has_ever_seen_drop,
        },
        "my_fleet": {
            "harvesters_orbit": h_orbit,
            "harvesters_surface": h_surface,
            "harvesters_damaged": h_damaged,
            "harvesters_destroyed_this_season": h_destroyed,
            "probes_deployed": probes_deployed,
            "probes_nights_remaining_min": probes_min_remain,
        },
        "enemy_fleet_estimate": {
            "probes_seen_count": enemy_probes_seen,
            "harvesters_witnessed": int(enemy_harvesters_witnessed),
            "persistent_echoes_count": len(persistent),
        },
        "hoard_pressure": {
            "used": int(hoard.get("used") or hoard.get("count") or 0),
            "max": int(hoard.get("max") or hoard.get("capacity") or 0),
            "warning": hoard.get("warning"),
            "next_jettison_tier": next_jettison,
            "vault_red_min_purity": vault.get("red_min"),
            "candidates_at_risk_of_jettison": candidates_at_risk,
        },
        "publicity_risk": {
            "my_visible_probes_count": probes_deployed,
            "my_publicly_telegraphed_targets": my_publicly_telegraphed_targets[:6],
        },
        "final_day": int(cur_day) >= int(season_cap),
        # ── Threat-assessment extensions (v0.9.20) — additive ────────
        "heatmap_top_cells": (
            heatmap.top_cells(8) if (heatmap is not None and heatmap.width > 0) else []
        ),
        "dark_zones": (
            heatmap.dark_zones() if (heatmap is not None and heatmap.width > 0) else []
        ),
        "predicted_enemy_drops": list(predicted_drops or []),
        "my_chains_threat_costs": [
            {
                "id": c["id"],
                "threat_cost": float((c.get("score_breakdown") or {}).get("threat_cost") or 0.0),
                "chain_survival_prob": float((c.get("score_breakdown") or {}).get("chain_survival_prob") or 1.0),
                "abandoned_low_engage_ratio": bool((c.get("flags") or {}).get("abandoned_low_engage_ratio")),
            }
            for c in harvest
        ],
        "vision_overlap": {
            "shared_cells_with_enemy_current": int(shared_vision_cells_count),
            "my_chains_in_dark_zones": [
                c["id"] for c in harvest
                if heatmap is not None and heatmap.width > 0
                and all(
                    heatmap.value(cell[0], cell[1]) <= _ta.DARK_ZONE_HEAT_CEILING
                    for cell in (c.get("cells_traversed") or [])
                )
            ],
        },
        "memory_summary_recent": dict(memory_summary or {}),
        "posture": dict(posture or {}),
        "probe_budget": dict(probe_budget or {}),
        "emp_signal": dict(emp_signal or {}),
    }


# ── recommended_policy assembly ──────────────────────────────────────
_FLEET_ACTION_CAP = 21


def _recommend(
    *,
    harvest: List[Dict[str, Any]],
    probes: List[Dict[str, Any]],
    hot_drops: List[Dict[str, Any]],
    supersedes: List[Dict[str, Any]],
    final_day: bool,
    my_harvester_ids: Sequence[str],
    drop_blocks: Optional[List[Dict[str, Any]]] = None,
    emp_launches: Optional[List[Dict[str, Any]]] = None,
    posture: Optional[Mapping[str, Any]] = None,
    my_probes_available: int = 99,
) -> Dict[str, Any]:
    """Concatenate the best one-chain-per-harvester + 1-2 probes within budget.

    Drop-block candidates (§3.17 case 1) and hot-drop variants are
    considered first because they consume specific orbital units; the
    remaining harvesters fall through to the standard chain loop.

    Posture (when provided) swings two knobs:
    * ``recommended_probe_cap``: aggressive=3, balanced=2, conservative=1.
    * ``supersede_activation_threshold``: aggressive=40, balanced=80,
      conservative=120.

    ``my_probes_available`` caps the probe count by what's actually in
    orbital stock so we don't queue probes the engine will refuse.
    """
    moves: List[Dict[str, Any]] = []
    rationale_bits: List[str] = []
    used_units: Set[str] = set()

    probe_cap = int(
        (posture or {}).get("recommended_probe_cap",
                            _ta.RECOMMENDED_PROBE_CAP["balanced"])
    )
    # The supersede slot also consumes a probe. Reserve one slot for
    # supersede so we don't accidentally exhaust the stock on fog probes
    # and lose the §3.16 play.
    supersede_reserve = 1 if (supersedes and not final_day) else 0
    probe_cap = max(0, min(probe_cap, int(my_probes_available) - supersede_reserve))

    supersede_threshold = float(
        (posture or {}).get("supersede_activation_threshold",
                            _ta.SUPERSEDE_ACTIVATION_THRESHOLD["balanced"])
    )

    # 1) Drop-blocks first — they deny enemy drops AND grab the cell. The
    #    rationale is that an early-slot block is strictly higher EV than
    #    a chain that the enemy might intercept.
    for db in (drop_blocks or []):
        unit = str(db.get("unit") or "")
        if not unit or unit in used_units:
            continue
        db_moves = list(db.get("moves") or [])
        if not db_moves:
            continue
        if len(moves) + len(db_moves) > _FLEET_ACTION_CAP:
            break
        moves.extend(db_moves)
        used_units.add(unit)
        rationale_bits.append(f"{db['id']} drop-block (score={db.get('score', 0):.0f})")

    # 2) Per-harvester top pick (best-scored chain that uses an unclaimed unit).
    for h_id in my_harvester_ids:
        if h_id in used_units:
            continue
        for cand in harvest:
            if cand.get("unit") != h_id or h_id in used_units:
                continue
            cand_moves = list(cand.get("moves") or [])
            if not cand_moves:
                continue
            if len(moves) + len(cand_moves) > _FLEET_ACTION_CAP:
                break
            moves.extend(cand_moves)
            used_units.add(h_id)
            rationale_bits.append(f"{cand['id']} (score={cand.get('score', 0)})")
            break

    # 3) Hot-drop swap — if the best hot-drop (any variant) scores higher
    #    than the placed chain for the same unit, swap. Includes the new
    #    speculative / counter-blind / echo-revisit variants.
    if hot_drops:
        # Sort by score (descending) — gets best across all variants.
        hd_sorted = sorted(hot_drops, key=lambda h: -float(h.get("score", 0)))
        best_hd = hd_sorted[0]
        unit = str(best_hd.get("unit") or "")
        if unit and unit in used_units:
            best_h = next(
                (c for c in harvest if c.get("unit") == unit),
                None,
            )
            if best_h is not None and float(best_hd.get("score", 0)) > float(best_h.get("score", 0)):
                moves = [m for m in moves if m.get("unit") != unit]
                hd_moves = list(best_hd.get("moves") or [])
                if len(moves) + len(hd_moves) <= _FLEET_ACTION_CAP:
                    moves.extend(hd_moves)
                    rationale_bits.append(
                        f"{best_hd['id']} swap [{best_hd.get('kind', 'hot_drop')}]"
                    )

    # 3.5) EMP salvo — auto-append when doctrine conditions are met.
    #      Denial is NOT fungible with harvest revenue; the scoring math
    #      already prices denial. If the harness's own gate passes, the
    #      queue includes both harvest AND emp — the 21-slot budget
    #      accommodates. Mirrors the auto-inclusion pattern of
    #      drop_blocks and supersede: harness decides, agent may swap.
    #
    #      Gate: top emp_launch candidate has can_fire=true, positive
    #      score, and covers ≥1 enemy unit in its salvo union. This
    #      keeps us from queueing wasted EMPs when the salvo hits fog.
    if emp_launches:
        top_emp = emp_launches[0]
        afford = top_emp.get("affordability") or {}
        effect = top_emp.get("expected_effect") or {}
        can_fire = bool(afford.get("can_fire"))
        emp_score = float(top_emp.get("score", 0) or 0)
        enemy_in_salvo = int(effect.get("enemy_unit_count", 0) or 0)
        if (
            can_fire
            and emp_score > 0
            and enemy_in_salvo >= 1
            and len(moves) + 1 <= _FLEET_ACTION_CAP
        ):
            emp_at = list(top_emp.get("targets") or [])
            if len(emp_at) == 3:
                moves.append({"a": "emp_launch", "at": [list(t) for t in emp_at]})
                rationale_bits.append(
                    f"emp_launch [{top_emp.get('pattern', 'salvo')}] "
                    f"(score={emp_score:.0f}, {enemy_in_salvo} enemy in salvo)"
                )

    # 4) Top probes — count capped by posture (aggressive=3, balanced=2, conservative=1).
    if not final_day:
        probe_count = 0
        for p in probes:
            if probe_count >= probe_cap:
                break
            if len(moves) + 1 > _FLEET_ACTION_CAP:
                break
            moves.append({"a": "probe", "at": list(p.get("at") or [])})
            rationale_bits.append(f"{p['id']}")
            probe_count += 1

        # 5) Supersede slot — activation threshold from posture.
        if supersedes and (probe_count + supersede_reserve) <= int(my_probes_available):
            top_s = supersedes[0]
            # Use score (which carries the JUICY_CONTEST_BOOST) if present,
            # else fall back to value_unlocked.
            s_score = float(top_s.get("score", top_s.get("value_unlocked", 0)))
            # Juicy-contest boost lowers the threshold by an extra 20.
            effective_threshold = supersede_threshold
            if top_s.get("boosted_juicy_contest"):
                effective_threshold = max(0.0, effective_threshold - 20.0)
            if s_score >= effective_threshold:
                if len(moves) + 1 <= _FLEET_ACTION_CAP:
                    moves.append({"a": "probe", "at": list(top_s.get("at") or [])})
                    tag = "supersede"
                    if top_s.get("boosted_juicy_contest"):
                        tag = "supersede [juicy-contest]"
                    rationale_bits.append(f"{top_s['id']} {tag}")

    return {
        "moves": moves,
        "total_actions": len(moves),
        "rationale_hint": "; ".join(rationale_bits),
    }


# ── public entry point ──────────────────────────────────────────────
def compile_candidates(agent_view: Mapping[str, Any]) -> Dict[str, Any]:
    """Build the full ``candidates`` + ``threat`` + ``memory_summary`` payload.

    Pure function. Updates the process-local memory cache as a side
    effect (via :mod:`sea_of_colours.agent.memory`).
    """
    meta = agent_view.get("meta") or {}
    hud = agent_view.get("hud") or {}
    cur_day = int(meta.get("day") or 0)
    seat = str(meta.get("player") or _seat_of(agent_view))

    # CRITICAL — synthesize a dense ``world.grid`` from sparse tile lists
    # if the engine sent ``world.grid = None``. Every downstream consumer
    # (`_grid_cell`, `_avoid_step_cells`, `_risky_collision_red_cells`,
    # chain enumeration) reads the dense grid; without this projection
    # those helpers silently degrade in production. Test fixtures pass a
    # dense grid and this call is a no-op for them.
    agent_view = _ensure_dense_grid(agent_view)

    # Update memory FIRST so threat/history checks see this turn's sightings.
    memory = _memory.update_memory(agent_view)
    enemy_history = _memory.cells_seen_set(memory)

    # Enemy probe info derived from view + memory.
    enemy_probes = _known_enemy_probes(agent_view)
    enemy_disk_cells = _enemy_probe_disk_cells(agent_view, enemy_probes)

    # Fleet & pools.
    harvesters = _my_harvesters(agent_view)
    healthy_harvesters = [h for h in harvesters if not h.get("damaged")]
    orbit_harvesters = [h for h in healthy_harvesters if h.get("pos") is None and h.get("at") is None]
    fleet_count = len(healthy_harvesters)
    if fleet_count == 0 and harvesters:
        # All harvesters damaged — still need to emit damaged_pickup for them.
        fleet_count = len(harvesters)

    nav = agent_view.get("navigation") or {}
    red_pool: List[Dict[str, Any]] = list(nav.get("best_red_visible") or [])
    red_echo_pool: List[Dict[str, Any]] = list(nav.get("best_red_echo") or [])
    if not red_pool and not red_echo_pool:
        red_pool = list(agent_view.get("red_tiles") or [])

    avoid_cells = _avoid_step_cells(agent_view, seat)
    risky_collision_cells = _risky_collision_red_cells(agent_view, seat)
    vault = _vault_state(agent_view)
    k_h = _k_harvest(fleet_count)
    k_p = _k_probes(fleet_count)

    # Threat-assessment heatmap (v0.9.20). Computed once and threaded
    # through every downstream consumer (chains, supersede, hot-drop,
    # drop_block, threat envelope).
    heatmap = _ta.compute_heatmap(agent_view, memory)
    predicted_drops = _ta.predicted_enemy_drops(heatmap, agent_view, memory, k=3)

    # Posture (score-gap-aware playstyle). Knobs threaded into hot-drop
    # emission and recommended-policy assembly.
    posture = _ta.compute_posture(agent_view, memory)

    # EMP threat signal (v0.9.22). Reads station_intel + memory to detect
    # rival weapon consumption between settlements.
    emp_signal = _ta.compute_emp_threat_signal(agent_view, memory)

    # How many probes we have to spare. The live engine carries the
    # count at ``orbit.probe_stock`` (NOT in ``my_assets`` — those
    # entries are only for built/deployed units). We also count any
    # orbit-state probe entries as a fallback for test fixtures that
    # encode stock as my_assets rows.
    my_probes_available = 0
    orbit_block = agent_view.get("orbit") or {}
    try:
        my_probes_available = int(orbit_block.get("probe_stock") or 0)
    except (TypeError, ValueError):
        my_probes_available = 0
    if my_probes_available == 0:
        for a in (agent_view.get("my_assets") or []):
            if not isinstance(a, dict):
                continue
            if (str(a.get("kind") or "").lower() == "probe"
                    and str(a.get("state") or "").lower() == "orbit"):
                my_probes_available += 1

    # Agentic probe-budget block (v0.9.21). The agent needs to see its
    # stock + the posture's suggested usage + an explicit advice line so
    # it can decide whether to deploy all, some, or none — NOT just
    # blindly take the recommended_policy. Probes are vital under
    # aggressive posture (no visible red); they're expensive to waste
    # under conservative posture (save for supersede / next turn).
    posture_label = posture["label"]
    probe_cap = int(_ta.RECOMMENDED_PROBE_CAP[posture_label])
    suggested_use = max(0, min(probe_cap, my_probes_available))
    advice_parts: List[str] = [
        f"You have {my_probes_available} probe(s) in orbit.",
        f"Posture is {posture_label}; suggested use this turn: {suggested_use}.",
    ]
    if posture_label == "aggressive" and my_probes_available > 0:
        advice_parts.append(
            "AGGRESSIVE: probes are vital — no/low visible red. Deploy as many as you can; "
            "fog reveal compounds across turns."
        )
    elif posture_label == "conservative" and my_probes_available > 1:
        advice_parts.append(
            "CONSERVATIVE: hold ≥1 probe back for supersede or next-turn flexibility."
        )
    elif posture_label == "balanced":
        advice_parts.append(
            "BALANCED: deploy enough to keep map vision rolling but keep 1 in reserve "
            "for an enemy-probe supersede opportunity."
        )
    if my_probes_available == 0:
        advice_parts.append(
            "NO PROBES IN STOCK — orbit phase next dawn will build more (~250c each). "
            "Plan harvest-only this night."
        )
    probe_budget = {
        "stock_in_orbit": int(my_probes_available),
        "posture_label": posture_label,
        "posture_recommended_use": suggested_use,
        "candidate_count": 0,  # filled in once we've computed `probes`
        "advice": " ".join(advice_parts),
    }

    # Per-harvester chain candidates. Thread a ``shared_claimed`` set
    # across siblings so harvester #2's top chain doesn't collide with
    # harvester #1's RED targets. Without this, two orbital harvesters
    # both pick the same drop+chain and the second walks over
    # already-harvested synthetic-green cells banking zero.
    harvest_all: List[Dict[str, Any]] = []
    shared_claimed: Set[Tuple[int, int]] = set()
    for h in (harvesters if harvesters else []):
        chains = _harvest_candidates_for(
            harvester=h,
            agent_view=agent_view,
            red_pool=red_pool if red_pool else red_echo_pool,
            avoid_cells=avoid_cells,
            enemy_disk_cells=enemy_disk_cells,
            enemy_history=enemy_history,
            vault=vault,
            k=k_h,
            seat=seat,
            heatmap=heatmap,
            risky_collision_cells=risky_collision_cells,
            emp_signal=emp_signal,
            shared_claimed=shared_claimed,
        )
        harvest_all.extend(chains)
        # Stamp the TOP chain's cells (the one most likely to be picked
        # by recommended_policy) into shared_claimed for the next sibling.
        if chains:
            top = chains[0]
            for c in (top.get("cells_traversed") or []):
                if isinstance(c, (list, tuple)) and len(c) == 2:
                    try:
                        shared_claimed.add((int(c[0]), int(c[1])))
                    except (TypeError, ValueError):
                        continue

    # Probe candidates.
    used_drops: List[Tuple[int, int]] = []
    for cand in harvest_all:
        for m in cand.get("moves") or []:
            if m.get("a") == "drop":
                at = m.get("at")
                if isinstance(at, (list, tuple)) and len(at) == 2:
                    used_drops.append((int(at[0]), int(at[1])))
    probes = _probe_candidates(
        agent_view=agent_view,
        enemy_disk_cells=enemy_disk_cells,
        enemy_history=enemy_history,
        enemy_probes=enemy_probes,
        used_drops=used_drops,
        k=k_p,
    )
    # Backfill how many probe candidates we ended up with so the agent
    # sees "stock=2, candidate options=4 → I can pick which 2 to use".
    probe_budget["candidate_count"] = len(probes)
    probe_budget["surplus_options"] = max(0, len(probes) - my_probes_available)

    supersedes = _supersede_candidates(
        agent_view=agent_view,
        enemy_probes=enemy_probes,
        nav_red_pool=red_pool,
        heatmap=heatmap,
        my_probes_available=my_probes_available,
    )
    crushes = _crush_candidates(
        agent_view=agent_view,
        enemy_probes=enemy_probes,
        nav_red_pool=red_pool,
        my_orbit_harvesters=orbit_harvesters,
        seat=seat,
        heatmap=heatmap,
    )
    hot_drops = _hot_drop_pairs(
        agent_view=agent_view,
        nav_red_pool=red_pool,
        nav_red_echo_pool=red_echo_pool,
        my_orbit_harvesters=orbit_harvesters,
        avoid_cells=avoid_cells,
        enemy_disk_cells=enemy_disk_cells,
        seat=seat,
        heatmap=heatmap,
        memory=memory,
        current_day=cur_day,
        posture=posture,
    )
    drop_blocks = _drop_block_candidates(
        agent_view=agent_view,
        heatmap=heatmap,
        predicted_drops=predicted_drops,
        my_orbit_harvesters=orbit_harvesters,
        avoid_cells=avoid_cells,
        seat=seat,
    )

    memory_summary = _memory.summarise(memory, cur_day)

    # Threat compiled against the candidates we just built.
    threat = compile_threat(
        agent_view,
        harvest=harvest_all,
        probe_choices=probes,
        enemy_probes=enemy_probes,
        enemy_disk_cells=enemy_disk_cells,
        enemy_history=enemy_history,
        vault=vault,
        heatmap=heatmap,
        predicted_drops=predicted_drops,
        memory_summary=memory_summary,
        posture=posture,
        probe_budget=probe_budget,
        emp_signal=emp_signal,
    )

    # Combat candidates (v0.9.25). Atomic emp_launch candidates surfaced
    # alongside the other menus; the agent reasons about sequencing.
    weapon_stock = (orbit_block.get("weapon_stock") or {}) if isinstance(orbit_block, Mapping) else {}
    try:
        blue_purity_available = int(orbit_block.get("blue_purity_total") or 0)
    except (TypeError, ValueError):
        blue_purity_available = 0
    try:
        credits_available = int(
            (orbit_block.get("credits") or
             (agent_view.get("hud") or {}).get("credits") or 0)
        )
    except (TypeError, ValueError):
        credits_available = 0
    # Surface (deployed) harvesters — at-risk if we self-freeze.
    my_surface_harvesters: List[Dict[str, Any]] = []
    for a in (agent_view.get("my_assets") or []):
        if not isinstance(a, Mapping):
            continue
        if str(a.get("kind") or "").lower() != "harvester":
            continue
        state = str(a.get("state") or "").lower()
        if state not in ("deployed", "surface"):
            continue
        my_surface_harvesters.append({
            "unit_id": str(a.get("id") or ""),
            "at": a.get("at") or a.get("pos"),
            "kind": "harvester",
        })
    emp_launches = _combat.compile_emp_launch_candidates(
        agent_view=agent_view,
        enemy_probes=enemy_probes,
        enemy_harvesters=[],  # not surfaced reliably — see §0.4
        my_surface_harvesters=my_surface_harvesters,
        weapon_stock=weapon_stock,
        blue_purity_available=blue_purity_available,
        credits_available=credits_available,
        heatmap=heatmap,
        emp_signal=emp_signal,
    )

    # Recommended policy.
    my_harvester_ids = [str(h.get("id") or "") for h in (harvesters or [])]
    recommended = _recommend(
        harvest=harvest_all,
        probes=probes,
        hot_drops=hot_drops,
        supersedes=supersedes,
        final_day=threat.get("final_day", False),
        my_harvester_ids=my_harvester_ids,
        drop_blocks=drop_blocks,
        emp_launches=emp_launches,
        posture=posture,
        my_probes_available=my_probes_available,
    )

    return {
        "candidates": {
            "k_used": {"harvest": k_h, "probes": k_p},
            "harvest": harvest_all,
            "probes": probes,
            "probe_supersede": supersedes,
            "harvester_crush": crushes,
            "hot_drop": hot_drops,
            "drop_block": drop_blocks,
            "emp_launch": emp_launches,
            "recommended_policy": recommended,
        },
        "combat": {
            "my_weapon_stock": dict(weapon_stock) if isinstance(weapon_stock, Mapping) else {},
            "my_blue_purity_available": int(blue_purity_available),
            "my_credits_available": int(credits_available),
            "emp_mechanics": {
                "cost_blue_purity": _combat.EMP_COST_BLUE_PURITY,
                "cost_credits": _combat.EMP_COST_CREDITS,
                "radius_chebyshev": _combat.EMP_RADIUS,
                "cloud_hours": _combat.EMP_CLOUD_HOURS,
                "blocks_all_movement_in_cloud": True,
                "fires_in_hour_H_clears_in_hour_H_plus_cloud_hours": True,
            },
        },
        "threat": threat,
        "memory_summary": memory_summary,
        "orbital": _orbit.compile_orbit_candidates(agent_view),
    }
