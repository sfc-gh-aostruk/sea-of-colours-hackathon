"""v10 comb shapes — three harvest walks the thinker chooses between.

A hot drop is BLIND: the probe reveals the disk, the harvester drops, but the
whole walk is committed up front. The right walk depends on WHY you dropped, and
that is a tactical judgement — so instead of one canned serpentine, v10 offers
the same drop as a small MENU of comb shapes and lets the thinker pick the
length/area to suit the situation (the user's model):

* STRETCH — a straight-ish line OUTWARD from the drop, allowed to leave the probe
            disk, maximising length / area / fresh intel. Use when the payload
            location is unknown and you want to see and sweep the most ground.
* SWEEP   — a compact serpentine that spends all its steps in a TIGHT area around
            the drop, maximising harvest if you have landed on the cluster.
* SAMPLE  — a quick 2-step in/out. Use on a hot/CONTESTED redsign where you grab
            what you can and lift before a rival collision or chaff zeroes you.

All three respect the engine outing budget: a drop banks its own cell plus up to
5 steps (``HARVESTER_HOLD_CAPACITY`` = 6 cells). Steps avoid known green, never
revisit, and stay on-board; STRETCH may leave the disk (movement needs no
coverage — only the DROP does), SWEEP/SAMPLE hug the disk around the value.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from sea_of_colours.orchestrator_2.harnesses.tabula_v7.probe_hints import (
    _comb_path,
    _grid_dims,
    _known_green_cells,
)

# Outing budget: drop + up to 5 steps = 6 cells (engine HARVESTER_HOLD_CAPACITY).
_MAX_STEPS = 5
_SAMPLE_STEPS = 2


def _xy(v: Any) -> Optional[Tuple[int, int]]:
    if isinstance(v, (list, tuple)) and len(v) == 2:
        try:
            return int(v[0]), int(v[1])
        except (TypeError, ValueError):
            return None
    return None


def _stretch_path(
    start: Tuple[int, int],
    width: int,
    height: int,
    bad: Set[Tuple[int, int]],
    *,
    max_steps: int = _MAX_STEPS,
) -> List[List[int]]:
    """A long straight-ish walk toward the most open direction (max fresh intel).

    Primary axis = the cardinal with the most room to the wall; a lateral wobble
    every third step widens the swathe so it combs area, not just a bare line.
    """
    x0, y0 = start
    room = {
        (1, 0): width - 1 - x0, (-1, 0): x0,
        (0, 1): height - 1 - y0, (0, -1): y0,
    }
    primary = max(room, key=lambda d: room[d])
    # Lateral axis is perpendicular to primary; pick the side with more room.
    if primary[0] != 0:
        lateral = (0, 1) if room[(0, 1)] >= room[(0, -1)] else (0, -1)
    else:
        lateral = (1, 0) if room[(1, 0)] >= room[(-1, 0)] else (-1, 0)

    path: List[List[int]] = []
    cur = start
    visited: Set[Tuple[int, int]] = {start}
    for i in range(max_steps):
        order = [lateral, primary] if i % 3 == 2 else [primary, lateral]
        moved = False
        for step in order:
            nx, ny = cur[0] + step[0], cur[1] + step[1]
            n = (nx, ny)
            if not (0 <= nx < width and 0 <= ny < height):
                continue
            if n in visited or n in bad:
                continue
            path.append([nx, ny])
            visited.add(n)
            cur = n
            moved = True
            break
        if not moved:
            break
    return path


def comb_variants(
    agent_view: Mapping[str, Any],
    probe_at: Any,
    drop_at: Any,
    *,
    value_cells: Sequence[Tuple[int, int]] = (),
) -> Dict[str, List[List[int]]]:
    """Return ``{"STRETCH": [...], "SWEEP": [...], "SAMPLE": [...]}`` combs.

    ``probe_at`` anchors the SWEEP/SAMPLE disk (they hug the revealed area);
    ``drop_at`` is the walk start. ``value_cells`` biases SWEEP/SAMPLE toward a
    known cluster (empty for a blind bluesign/fog drop). Any shape may come back
    empty (e.g. boxed in by green/edge) — the caller keeps the non-empty ones.
    """
    width, height = _grid_dims(agent_view)
    green = _known_green_cells(agent_view)
    drop = _xy(drop_at)
    probe = _xy(probe_at) or drop
    if drop is None or probe is None:
        return {"STRETCH": [], "SWEEP": [], "SAMPLE": []}
    vcells = [c for c in (value_cells or []) if isinstance(c, tuple)]

    sweep = _comb_path(
        probe[0], probe[1], drop, width, height, green, vcells, max_steps=_MAX_STEPS,
    )
    sample = _comb_path(
        probe[0], probe[1], drop, width, height, green, vcells, max_steps=_SAMPLE_STEPS,
    )
    stretch = _stretch_path(drop, width, height, green, max_steps=_MAX_STEPS)
    return {"STRETCH": stretch, "SWEEP": sweep, "SAMPLE": sample}
