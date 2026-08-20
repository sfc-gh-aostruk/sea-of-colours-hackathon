"""Self-contained chain hint compiler for Tabula.

Builds a small set of harvest-chain "hints" the prompt can echo to the
LLM as *suggestions* (scores stripped — the LLM computes EV itself using
the RULES tier table).

Deliberately self-contained: this module reads ``agent_view`` directly
and does not depend on any other harness. Keeping Tabula as a clean
base means no reach-across into pilot_v4/etc — future extensions can
add smarter compilers without disturbing this floor.

Algorithm (per turn):

1. Read all visible RED cells (in probe LOS) with their purity.
2. Read the set of harvester units currently in orbit (the drops we
   might make this turn).
3. For each RED cell, run a short greedy Chebyshev-1 walk that at each
   step picks the highest-purity unvisited RED neighbor. Cap chain
   length at ``max_chain_length`` (default 6 cells including the drop).
4. Score each chain by the sum of purity × tier_mult (internal only —
   the LLM never sees this score).
5. Return the top ``max_chains`` chains, one per harvester unit, with
   ``score`` stripped from the returned payload.

The output shape matches what :mod:`.prompt` renders. Every hint
carries only factual per-cell data (coords, tier label, purity) — no
recommended ordering, no EV, no "pick this one" nudges. The agent is
free to alter, reorder, extend, shorten, or ignore.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence, Set, Tuple


# Canonical engine bands — must match ``game/orbit_resolver.py::_tier_label``
# and ``agent/heuristic_agent.py``. ONLY purity == 255 is pure.
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


def _extract_red_cells(agent_view: Mapping[str, Any]) -> Dict[Tuple[int, int], int]:
    """Map ``(x, y) -> purity`` for every RED cell currently in LOS."""
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


def _orbit_harvesters(agent_view: Mapping[str, Any]) -> List[str]:
    """Harvester unit ids that are currently in orbit and can be dropped."""
    out: List[str] = []
    for u in (agent_view.get("my_assets") or []):
        if not isinstance(u, Mapping):
            continue
        if u.get("kind") == "harvester" and u.get("state") == "orbit":
            uid = u.get("id")
            if isinstance(uid, str):
                out.append(uid)
    return out


def _neighbors(xy: Tuple[int, int]) -> List[Tuple[int, int]]:
    x, y = xy
    return [
        (x + dx, y + dy)
        for dx in (-1, 0, 1)
        for dy in (-1, 0, 1)
        if not (dx == 0 and dy == 0)
    ]


def _greedy_chain(
    start: Tuple[int, int],
    red: Mapping[Tuple[int, int], int],
    max_len: int,
) -> List[Tuple[int, int]]:
    """Grow a chain from ``start`` by hopping to the highest-purity
    Chebyshev-1 RED neighbor not yet visited. Stops when no RED
    neighbor remains or ``max_len`` cells have been picked."""
    if start not in red:
        return []
    chain: List[Tuple[int, int]] = [start]
    visited: Set[Tuple[int, int]] = {start}
    while len(chain) < max_len:
        best: Tuple[int, int] = None  # type: ignore[assignment]
        best_p = -1
        for n in _neighbors(chain[-1]):
            if n in visited or n not in red:
                continue
            p = red[n]
            if p > best_p:
                best = n
                best_p = p
        if best is None:
            break
        chain.append(best)
        visited.add(best)
    return chain


def _chain_score(chain: Sequence[Tuple[int, int]], red: Mapping[Tuple[int, int], int]) -> float:
    total = 0.0
    for xy in chain:
        p = red.get(tuple(xy), 0)
        total += p * _TIER_MULT.get(_tier_name(p), 1.0)
    return total


def top_chain_hints(
    agent_view: Mapping[str, Any],
    *,
    max_chains: int = 3,
    max_chain_length: int = 6,
) -> List[Dict[str, Any]]:
    """Return up to ``max_chains`` harvest-chain hints, one per harvester.

    Each hint carries:
      * ``unit`` — harvester id the chain is scoped to
      * ``drop_at`` — [x, y] of the drop cell
      * ``cells`` — ordered [[x, y], ...] the chain would harvest (drop
        cell first, then each step's destination)
      * ``tiers`` — parallel list of tier names ("pure", "mass", ...)
      * ``purities`` — parallel list of ints so the LLM can compute EV
      * ``length`` — chain length (drop + steps, excluding pickup)

    NO ``score`` field. NO recommended ordering flag. The LLM ranks by
    re-computing sum(purity × tier_mult) from the RULES block.
    """
    red = _extract_red_cells(agent_view)
    if not red:
        return []
    harvesters = _orbit_harvesters(agent_view)
    if not harvesters:
        return []

    # Build candidate chains from every RED cell.
    candidates: List[Tuple[float, List[Tuple[int, int]]]] = []
    for start in red:
        chain = _greedy_chain(start, red, max_chain_length)
        if len(chain) < 2:
            # Single-cell chains are still valid drops but rarely useful;
            # keep them so the LLM at least sees a hint per hot cell.
            if len(chain) == 1:
                candidates.append((_chain_score(chain, red), chain))
            continue
        candidates.append((_chain_score(chain, red), chain))

    # Sort by internal EV, then dedupe overlapping starts. We rotate
    # through harvesters so the returned hints suggest different units
    # rather than stacking all top chains on one id.
    candidates.sort(key=lambda t: t[0], reverse=True)

    hints: List[Dict[str, Any]] = []
    used_starts: Set[Tuple[int, int]] = set()
    for i, (_score, chain) in enumerate(candidates):
        if chain[0] in used_starts:
            continue
        unit = harvesters[i % len(harvesters)]
        purities = [int(red[tuple(xy)]) for xy in chain]
        tiers = [_tier_name(p) for p in purities]
        hints.append({
            "unit": unit,
            "drop_at": [int(chain[0][0]), int(chain[0][1])],
            "cells": [[int(xy[0]), int(xy[1])] for xy in chain],
            "tiers": tiers,
            "purities": purities,
            "length": len(chain),
        })
        used_starts.add(chain[0])
        if len(hints) >= max_chains:
            break
    return hints
