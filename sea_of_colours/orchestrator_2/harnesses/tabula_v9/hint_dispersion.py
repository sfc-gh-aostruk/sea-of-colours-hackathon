"""v9 Fix A — seat-differentiated, ownership-aware hot-drop dispersion.

THE PROBLEM (measured, seed 42):
    ``probe_hints.top_hot_drop_hints`` is a PURE function of the board, and
    every agent version imports the same module. Given one public REDSIGN
    beacon, all seats compute the byte-identical ``drop_at`` AND the identical
    nearest-first ``alt_drops``. So even when the agent obediently "offsets onto
    the seam", every seat offsets onto the SAME seam cell -> SIMULTANEOUS DROP
    COLLISION -> 0 banked for everyone (observed n-way on the shared beacon, and
    still 2-way on the offset cells night 7 of the 1v1).

    You cannot break a symmetric collision by handing every player the same
    ranked menu in the same order. It needs either per-seat asymmetry or the
    mine/not-mine poker producing genuinely DIFFERENT primary plays.

THE FIX (v9-only, deterministic — NO hidden RNG on the final placement):
    * Attach engine-truth ownership (``mine``) to each redsign hot-drop by
      matching it to the redsign region it targets.
    * MY redsign  -> CASE 1: leave the primary drop on/adjacent the pure. I
      found it, I move first; smash-and-grab is correct.
    * NOT my redsign -> CASE 2: each seat is assigned a DIFFERENT seam offset,
      chosen by rotating the (already deterministic) ``alt_drops`` list by a
      stable index derived from the seat's own id. p1 leads with offset 0, p2
      with offset 1, p3 with offset 2 — so three rivals fan out onto three
      distinct seam cells instead of stacking. The assignment is a stable,
      explainable "approach angle", not a coin flip.

This only rewrites v9's hint payloads in-process; the shared compiler and the
frozen v6/v7/v8 harnesses are untouched.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from sea_of_colours.orchestrator_2.harnesses.tabula_v7.probe_hints import (
    _comb_path,
    _grid_dims,
    _known_green_cells,
    _redsign_cells,
)

# Chebyshev radius within which a redsign hot-drop is considered to be
# "targeting" a given redsign region (the vision disk half-width).
_REGION_MATCH_RADIUS = 4


def seat_index(player: str) -> int:
    """Stable per-seat rotation index.

    ``p1``/``p2``/``p3``/``p4`` map to 0/1/2/3 (the common arena seating), so
    the fan-out is trivially legible in a head-to-head. Any other id falls back
    to a stable hash so the property (distinct seats -> distinct index) holds.
    """
    s = str(player or "").strip().lower()
    if len(s) == 2 and s[0] == "p" and s[1].isdigit():
        return max(0, int(s[1]) - 1)
    return abs(hash(s)) % 97


def _region_center(region: Mapping[str, Any]) -> Optional[Tuple[float, float]]:
    c = region.get("center")
    if isinstance(c, (list, tuple)) and len(c) == 2:
        try:
            return float(c[0]), float(c[1])
        except (TypeError, ValueError):
            return None
    return None


def _hint_target(hint: Mapping[str, Any]) -> Optional[Tuple[int, int]]:
    """Best estimate of the beacon cell a hot-drop is chasing.

    The primary ``drop_at`` sits on or 1 cell off the beacon, so it is a
    reliable anchor for matching the hint back to its redsign region.
    """
    d = hint.get("drop_at")
    if isinstance(d, (list, tuple)) and len(d) == 2:
        try:
            return int(d[0]), int(d[1])
        except (TypeError, ValueError):
            return None
    return None


def _match_ownership(
    hint: Mapping[str, Any], regions: Sequence[Mapping[str, Any]],
) -> Optional[bool]:
    """Return the ``mine`` flag of the redsign region this hint targets.

    ``None`` when no region is close enough to attribute (leave ownership
    unknown rather than guess).
    """
    target = _hint_target(hint)
    if target is None:
        return None
    tx, ty = target
    best: Optional[Tuple[float, bool]] = None
    for r in regions:
        if not isinstance(r, Mapping):
            continue
        ctr = _region_center(r)
        if ctr is None:
            continue
        dist = max(abs(tx - ctr[0]), abs(ty - ctr[1]))
        if dist <= _REGION_MATCH_RADIUS and (best is None or dist < best[0]):
            best = (dist, bool(r.get("mine")))
    return None if best is None else best[1]


def personalize_hot_drops(
    hints: Sequence[Mapping[str, Any]],
    agent_view: Mapping[str, Any],
    player: str,
) -> List[Dict[str, Any]]:
    """Return v9 hot-drop hints with ownership + seat-differentiated offsets.

    Non-destructive: operates on shallow copies so the shared compiler's cached
    output is never mutated. Non-redsign / non-contested hints pass through with
    only a ``mine`` annotation (when attributable).
    """
    regions = list(agent_view.get("redsign") or [])
    width, height = _grid_dims(agent_view)
    green = _known_green_cells(agent_view)
    value_cells = list(_redsign_cells(agent_view).keys())
    idx = seat_index(player)

    out: List[Dict[str, Any]] = []
    for h in hints or []:
        if not isinstance(h, Mapping):
            continue
        hint = dict(h)
        is_redsign = str(hint.get("signal_type") or "") == "redsign"

        mine = _match_ownership(hint, regions) if is_redsign else None
        if mine is not None:
            hint["mine"] = bool(mine)

        # CASE 2 fan-out: a rival's (or unclaimed) contested redsign beacon.
        # Assign THIS seat a distinct seam offset so seats don't stack.
        if is_redsign and hint.get("contested") and mine is not True:
            alts = [
                (int(a[0]), int(a[1]))
                for a in (hint.get("alt_drops") or [])
                if isinstance(a, (list, tuple)) and len(a) == 2
            ]
            if alts:
                rot = idx % len(alts)
                assigned = alts[rot]
                probe = hint.get("probe_at")
                # Re-anchor the primary drop onto this seat's assigned seam cell
                # and reorder the menu so the assignment leads.
                hint["drop_at"] = [assigned[0], assigned[1]]
                hint["alt_drops"] = [[c[0], c[1]] for c in alts[rot:] + alts[:rot]]
                hint["seat_offset"] = [assigned[0], assigned[1]]
                if isinstance(probe, (list, tuple)) and len(probe) == 2:
                    hint["comb_path"] = _comb_path(
                        int(probe[0]), int(probe[1]), assigned,
                        width, height, green, value_cells, max_steps=6,
                    )
        out.append(hint)
    return out
