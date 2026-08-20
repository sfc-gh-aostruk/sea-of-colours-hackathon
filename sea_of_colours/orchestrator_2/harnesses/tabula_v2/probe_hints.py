"""Probe placement hint compiler for Tabula v2.

Answers: given the current fog of war, where should we drop a probe?

Design goal
-----------
Probes are cheap information. A probe launched onto ``(x, y)`` reveals a
Chebyshev-4 disk (81 cells) for the next 3 nights. Two scoring signals
tell us whether a candidate is worth the hour:

1. **AREA_GAIN**
   How many currently-fog cells the disk would reveal. Bigger = more
   information gained. Overlapping with existing LOS is wasted budget.

2. **EDGE_PROMISE**
   Extra value when the disk extends outward from LOS edges that
   already show high-purity RED (seams tend to continue past visible
   boundaries), or when the disk covers cells the engine has flagged
   in ``navigation.best_red_echo``.

The LLM sees ``area_gain`` and ``edge_promise`` as separate ints — no
combined score field, mirroring the "candidates as hints" rule. It's
free to rank, alter, or ignore.

Self-contained
--------------
Reads ``agent_view`` directly. No reach into pilot_v4 / other harnesses.
Keeps Tabula v2 on the same clean-base architecture v1 established.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence, Set, Tuple

# Probe disk radius (Chebyshev). Must match the engine's probe FOV rule.
_PROBE_RADIUS = 4

# Extra weight per unit of edge promise, used ONLY for our internal
# ranking of candidates (the LLM never sees this). Set high enough that
# a 200-purity mass neighbour tips a candidate over one that only wins
# on raw area. Purely a candidate-ordering knob.
_EDGE_WEIGHT = 0.05

_TIER_MULT = {"trace": 0.75, "vein": 1.0, "mass": 1.5, "pure": 3.0}


def _tier_name(purity: int) -> str:
    p = int(purity or 0)
    if p >= 255:
        return "pure"
    if p >= 151:
        return "mass"
    if p >= 51:
        return "vein"
    return "trace"


def _grid_dims(agent_view: Mapping[str, Any]) -> Tuple[int, int]:
    world = agent_view.get("world") or {}
    try:
        return int(world.get("width") or 40), int(world.get("height") or 28)
    except (TypeError, ValueError):
        return 40, 28


def _los_cells(agent_view: Mapping[str, Any]) -> Set[Tuple[int, int]]:
    """Cells currently in live vision (a probe disk or a friendly unit).

    Reads ``world.live[]`` which each cell inside LOS is enumerated in.
    """
    out: Set[Tuple[int, int]] = set()
    for row in ((agent_view.get("world") or {}).get("live") or []):
        if not isinstance(row, Mapping):
            continue
        try:
            out.add((int(row["x"]), int(row["y"])))
        except (TypeError, KeyError, ValueError):
            continue
    return out


def _fog_clusters(agent_view: Mapping[str, Any]) -> List[Dict[str, Any]]:
    return [c for c in (agent_view.get("fog_clusters") or []) if isinstance(c, Mapping)]


def _echo_cells(agent_view: Mapping[str, Any]) -> Dict[Tuple[int, int], int]:
    """Best-red echo readings (cells hinted at beyond LOS). Keyed by
    (x, y) to purity estimate."""
    out: Dict[Tuple[int, int], int] = {}
    for row in (((agent_view.get("navigation") or {}).get("best_red_echo")) or []):
        if not isinstance(row, Mapping):
            continue
        try:
            out[(int(row["x"]), int(row["y"]))] = int(row.get("purity") or row.get("value") or 0)
        except (TypeError, KeyError, ValueError):
            continue
    return out


def _visible_red(agent_view: Mapping[str, Any]) -> Dict[Tuple[int, int], int]:
    """Every RED cell currently in LOS with its purity."""
    out: Dict[Tuple[int, int], int] = {}
    for row in (agent_view.get("red_tiles") or []):
        if not isinstance(row, Mapping):
            continue
        try:
            x, y = int(row["x"]), int(row["y"])
            p = int(row.get("purity") or 0)
        except (TypeError, KeyError, ValueError):
            continue
        if p > 0:
            out[(x, y)] = p
    return out


def _disk(cx: int, cy: int, width: int, height: int) -> List[Tuple[int, int]]:
    r = _PROBE_RADIUS
    return [
        (x, y)
        for x in range(max(0, cx - r), min(width, cx + r + 1))
        for y in range(max(0, cy - r), min(height, cy + r + 1))
    ]


def _seed_candidates(
    agent_view: Mapping[str, Any],
    width: int,
    height: int,
    los: Set[Tuple[int, int]],
) -> Set[Tuple[int, int]]:
    """Small candidate set: fog centroids, nearest-visible-edge points,
    every echo cell, and one-step-outside every high-purity visible RED
    cell (to test seam extension)."""
    seeds: Set[Tuple[int, int]] = set()

    for cluster in _fog_clusters(agent_view):
        centroid = cluster.get("centroid")
        if isinstance(centroid, (list, tuple)) and len(centroid) == 2:
            seeds.add((int(centroid[0]), int(centroid[1])))
        nve = cluster.get("nearest_visible_edge")
        if isinstance(nve, (list, tuple)) and len(nve) == 2:
            seeds.add((int(nve[0]), int(nve[1])))

    for xy in _echo_cells(agent_view):
        seeds.add(xy)

    # Extend outward from high-purity visible reds — if the seam continues
    # into fog, probing the far side of the red cell surfaces it.
    red = _visible_red(agent_view)
    ranked_reds = sorted(red.items(), key=lambda kv: kv[1], reverse=True)[:6]
    for (rx, ry), _ in ranked_reds:
        for dx in (-4, -3, 0, 3, 4):
            for dy in (-4, -3, 0, 3, 4):
                if dx == 0 and dy == 0:
                    continue
                cx, cy = rx + dx, ry + dy
                if 0 <= cx < width and 0 <= cy < height:
                    seeds.add((cx, cy))

    # Filter out obviously silly seeds: cells fully inside LOS provide
    # no area_gain by construction. We keep them if they're an echo
    # (echo cells are in fog by definition), otherwise drop them.
    echoes = set(_echo_cells(agent_view).keys())
    return {xy for xy in seeds if xy in echoes or xy not in los}


def _score_candidate(
    at: Tuple[int, int],
    width: int,
    height: int,
    los: Set[Tuple[int, int]],
    red: Mapping[Tuple[int, int], int],
    echoes: Mapping[Tuple[int, int], int],
) -> Tuple[int, int, List[Tuple[int, int]]]:
    """Return (area_gain, edge_promise, disk_cells) for a candidate."""
    disk_cells = _disk(at[0], at[1], width, height)
    area_gain = sum(1 for c in disk_cells if c not in los)

    # Edge promise: (a) visible red immediately outside the disk (seam
    # extension), plus (b) echo cells inside the disk that would resolve
    # to real red once probed. Both weighted by tier_mult × purity so
    # a pure hint dominates a trace hint.
    edge = 0.0
    disk_set = set(disk_cells)
    # (a) Visible red just outside the disk boundary (Chebyshev-adjacent
    # to any disk cell but not inside the disk itself).
    for (rx, ry), purity in red.items():
        if (rx, ry) in disk_set:
            continue
        # Chebyshev-1 to any disk cell? Cheap check: dist to (at[0],at[1])
        # in (_PROBE_RADIUS, _PROBE_RADIUS+1].
        d = max(abs(rx - at[0]), abs(ry - at[1]))
        if d == _PROBE_RADIUS + 1:
            edge += purity * _TIER_MULT.get(_tier_name(purity), 1.0)
    # (b) Echo cells inside the disk.
    for (ex, ey), purity in echoes.items():
        if (ex, ey) in disk_set:
            edge += purity * _TIER_MULT.get(_tier_name(purity), 1.0)

    return area_gain, int(round(edge)), disk_cells


def top_probe_hints(
    agent_view: Mapping[str, Any],
    *,
    max_hints: int = 3,
) -> List[Dict[str, Any]]:
    """Return up to ``max_hints`` probe-placement candidates.

    Each hint carries:
      * ``at`` — [x, y] of the probe drop
      * ``area_gain`` — # fog cells the disk would reveal
      * ``edge_promise`` — purity-weighted seam-extension value
      * ``extends_from`` — short label describing why this cell was seeded
        ("fog_centroid", "los_edge", "echo", "seam_extension")

    NO combined score. LLM ranks by re-reading area_gain + edge_promise
    against its own doctrine (RULES probe strategy section).

    Empty return means the board has no useful probes right now (either
    no fog at all, or every candidate has area_gain == 0). The LLM is
    trusted to spend its probe elsewhere or skip.
    """
    width, height = _grid_dims(agent_view)
    los = _los_cells(agent_view)
    if not los:
        # No LOS state — degenerate; skip.
        return []

    fog_count = int(((agent_view.get("world") or {}).get("fog_count")) or 0)
    if fog_count == 0:
        return []

    red = _visible_red(agent_view)
    echoes = _echo_cells(agent_view)

    seeds = _seed_candidates(agent_view, width, height, los)
    if not seeds:
        return []

    # Bucket the seeds by why they were suggested, so we can attach a
    # readable ``extends_from`` label for the prompt.
    labels: Dict[Tuple[int, int], str] = {}
    for cluster in _fog_clusters(agent_view):
        centroid = cluster.get("centroid")
        if isinstance(centroid, (list, tuple)) and len(centroid) == 2:
            labels.setdefault((int(centroid[0]), int(centroid[1])), "fog_centroid")
        nve = cluster.get("nearest_visible_edge")
        if isinstance(nve, (list, tuple)) and len(nve) == 2:
            labels.setdefault((int(nve[0]), int(nve[1])), "los_edge")
    for xy in echoes:
        labels.setdefault(xy, "echo")

    scored: List[Tuple[float, int, int, Tuple[int, int], str]] = []
    for at in seeds:
        area_gain, edge_promise, _ = _score_candidate(at, width, height, los, red, echoes)
        if area_gain == 0 and edge_promise == 0:
            continue
        internal_rank = area_gain + _EDGE_WEIGHT * edge_promise
        scored.append((internal_rank, area_gain, edge_promise, at, labels.get(at, "seam_extension")))

    scored.sort(key=lambda t: t[0], reverse=True)

    # De-duplicate near-identical placements (candidates whose disks
    # overlap >75%) so the LLM sees genuinely distinct options.
    hints: List[Dict[str, Any]] = []
    taken_disks: List[Set[Tuple[int, int]]] = []
    for _rank, area_gain, edge_promise, at, label in scored:
        disk_set = set(_disk(at[0], at[1], width, height))
        if any(len(disk_set & taken) / max(1, len(disk_set)) > 0.75 for taken in taken_disks):
            continue
        hints.append({
            "at": [int(at[0]), int(at[1])],
            "area_gain": int(area_gain),
            "edge_promise": int(edge_promise),
            "extends_from": label,
        })
        taken_disks.append(disk_set)
        if len(hints) >= max_hints:
            break

    return hints
