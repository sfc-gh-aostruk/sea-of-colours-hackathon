#!/usr/bin/env python3
"""How many pure(255) RED cells does a board get, and how clumped are they?

A pure is the jackpot the whole redsign mechanic is built around, so a
seed that hands out a slab of them next to each other is not "lucky", it
is a different game. This measures the distribution before/after any
de-clustering change.

Scratch harness, like the other ``scripts/_*.py`` — not a test.

Usage::

    python scripts/_mapgen_pure_census.py [n_seeds] [width height] [seats]

``seats`` (v1.28) sets the floor the way ``GameSession.new`` does,
``max(2, seats)`` — pass 4 to measure the board a full table actually gets.

NOTE the size. ``GenerationParams`` defaults to 80x50, but ``/api/game/new``
serves 40x28 — that is the board people actually play, and it clusters far
less than the default does. Measuring the wrong one overstates the problem
by a wide margin.
"""
from __future__ import annotations

import sys
from collections import Counter, deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sea_of_colours.generator import GenerationParams, Tile, generate_grid  # noqa: E402


def pures(grid) -> list[tuple[int, int]]:
    return [
        (x, y)
        for y, row in enumerate(grid)
        for x, c in enumerate(row)
        if c.tile == Tile.RED and c.purity >= 255
    ]


def clumps(cells: list[tuple[int, int]]) -> list[int]:
    """Sizes of 8-connected groups of pure cells."""
    todo = set(cells)
    out: list[int] = []
    while todo:
        seed = todo.pop()
        q, n = deque([seed]), 1
        while q:
            x, y = q.popleft()
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    p = (x + dx, y + dy)
                    if p in todo:
                        todo.discard(p)
                        q.append(p)
                        n += 1
        out.append(n)
    return sorted(out, reverse=True)


def closest_pair(cells: list[tuple[int, int]]) -> int | None:
    """Smallest CHEBYSHEV gap between any two pures, or None if fewer than 2.

    Chebyshev (king moves) is the metric v1.24's separation rule uses, because
    the question it answers is "can one probe disk cover both jackpots".
    """
    if len(cells) < 2:
        return None
    return min(
        max(abs(a[0] - b[0]), abs(a[1] - b[1]))
        for i, a in enumerate(cells)
        for b in cells[i + 1:]
    )


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    w = int(sys.argv[2]) if len(sys.argv) > 3 else 40
    h = int(sys.argv[3]) if len(sys.argv) > 3 else 28
    # v1.28 — the floor is per-House now (``max(2, seats)``, set by
    # GameSession.new), so the census has to be told which seat count it is
    # measuring or it only ever reports the 2-player board. This is the
    # script the RULEBOOK's "100% of seeds at every floor" claim comes from.
    seats = int(sys.argv[4]) if len(sys.argv) > 4 else 2
    want = max(2, seats)
    tot = Counter()
    clump_hist = Counter()
    worst = (0, -1)
    boards_with_a_clump = 0
    pure_counts = []
    gaps: list[int] = []
    lonely = 0          # boards below the count floor
    crowded = (999, -1)  # tightest pair seen, and where

    for seed in range(n):
        grid = generate_grid(GenerationParams(
            width=w, height=h, seed=seed, min_pure_count=want,
        ))
        ps = pures(grid)
        pure_counts.append(len(ps))
        cl = clumps(ps)
        for size in cl:
            clump_hist[size] += 1
        tot["pures"] += len(ps)
        if cl and cl[0] > worst[0]:
            worst = (cl[0], seed)
        if any(s > 1 for s in cl):
            boards_with_a_clump += 1
        if len(ps) < want:
            lonely += 1
        gap = closest_pair(ps)
        if gap is not None:
            gaps.append(gap)
            if gap < crowded[0]:
                crowded = (gap, seed)

    pure_counts.sort()
    print(f"seeds: {n}   board {w}x{h}   seats {seats} -> floor {want}")
    print(f"pures per board: min {pure_counts[0]}  "
          f"median {pure_counts[n // 2]}  "
          f"mean {tot['pures'] / n:.1f}  max {pure_counts[-1]}")
    print(f"boards with 2+ pures touching: {boards_with_a_clump} "
          f"({100.0 * boards_with_a_clump / n:.0f}%)")
    print(f"worst clump: {worst[0]} cells (seed {worst[1]})")
    # v1.24 separation rule (§2.2): >= min_pure_count pures, no pair closer
    # than min_pure_separation Chebyshev cells.
    print(f"\nboards below the floor of {want}: {lonely} "
          f"({100.0 * lonely / n:.0f}%)")
    if gaps:
        gaps.sort()
        print(f"closest pure pair per board (chebyshev): "
              f"min {gaps[0]}  median {gaps[len(gaps) // 2]}  max {gaps[-1]}")
        print(f"tightest pair overall: {crowded[0]} cells (seed {crowded[1]})")
    print("\nclump-size histogram (8-connected groups, all boards):")
    for size in sorted(clump_hist):
        bar = "#" * min(60, clump_hist[size])
        print(f"  {size:3d} cells : {clump_hist[size]:5d} {bar}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
