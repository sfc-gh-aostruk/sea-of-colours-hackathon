#!/usr/bin/env python3
"""How many pure(255) RED cells does a board get, and how clumped are they?

A pure is the jackpot the whole redsign mechanic is built around, so a
seed that hands out a slab of them next to each other is not "lucky", it
is a different game. This measures the distribution before/after any
de-clustering change.

Scratch harness, like the other ``scripts/_*.py`` — not a test.

Usage::

    python scripts/_mapgen_pure_census.py [n_seeds] [width height]

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


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    w = int(sys.argv[2]) if len(sys.argv) > 3 else 40
    h = int(sys.argv[3]) if len(sys.argv) > 3 else 28
    tot = Counter()
    clump_hist = Counter()
    worst = (0, -1)
    boards_with_a_clump = 0
    pure_counts = []

    for seed in range(n):
        grid = generate_grid(GenerationParams(width=w, height=h, seed=seed))
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

    pure_counts.sort()
    print(f"seeds: {n}   board {w}x{h}")
    print(f"pures per board: min {pure_counts[0]}  "
          f"median {pure_counts[n // 2]}  "
          f"mean {tot['pures'] / n:.1f}  max {pure_counts[-1]}")
    print(f"boards with 2+ pures touching: {boards_with_a_clump} "
          f"({100.0 * boards_with_a_clump / n:.0f}%)")
    print(f"worst clump: {worst[0]} cells (seed {worst[1]})")
    print("\nclump-size histogram (8-connected groups, all boards):")
    for size in sorted(clump_hist):
        bar = "#" * min(60, clump_hist[size])
        print(f"  {size:3d} cells : {clump_hist[size]:5d} {bar}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
