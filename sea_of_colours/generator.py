"""Turn noise fields and band masks into a ``Grid`` of biome tiles.

The compositing order matches the brief: red mountains first, then green
diagonal bands (which overwrite red so the bands stay clean), then blue
dotted concentrations on top of everything.

Every cell carries a ``purity`` value in ``[0, 255]`` alongside its ``tile``
type, but red and blue compute it from very different shapes:

* **Red is a seam.** Cells are chosen with the same thresholded ridge noise as
  before; **purity** is fixed only after ``GREEN`` and ``BLUE`` are painted, from
  (a) **Manhattan depth** — how many steps a red cell sits from the *visible*
  red/unred boundary — and (b) the stored ridge coordinate ``t``, shaped as a
  blend of ``t ** red_gamma`` and a linear ``t`` term (``red_ridge_linear``) so
  typical ``t`` values are not all crushed into trace; thicker cores can reach
  **mass** and, when depth and ridge both cooperate, occasional **pure** (``255``).
  One-pixel-wide seams never reach ``255``.
* **Blue is a pocket.** A Chebyshev distance transform picks the geometric
  center of each connected blue blob (the dist-transform peak), and
  every other cell is graded by its Chebyshev distance *from that peak*.
  The peak cell reaches purity ``255`` (solid ``deep``); outer cells fall
  into lower bands. ``blue_gamma`` is the falloff exponent (``1.0`` = linear).
* **Green is a band** (v0.8.0). The generator rolls 1–3 same-orientation
  bands (snap-to-8 angle set: 0, 22.5°, 45°, 67.5°, 90°, 112.5°, 135°,
  157.5°), spaces their centers along the perpendicular axis, and
  paints cells whose ``smoothstep(half_width, 0, perp_distance) *
  noise`` exceeds the threshold. Pre-v0.8.0 ``band_depth`` is honoured
  as a fallback for the legacy polar-bands look when ``green_band_count_choices``
  resolves to an empty tuple.

Green still defaults to full purity (``255``) until it gets its own tier
rules.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from enum import IntEnum
from typing import List, Tuple

from sea_of_colours.noise import Field, fbm_2d, ridge_transform


class Tile(IntEnum):
    EMPTY = 0
    GREEN = 1
    RED = 2
    BLUE = 3


@dataclass(slots=True)
class Cell:
    """A single grid cell: which biome it belongs to and how pure that biome is.

    ``purity`` is a saturation/intensity scalar in ``[0, 255]``. For RED cells
    this is interpreted as the red channel value (so 0 ≈ black, 255 = pure
    red). EMPTY cells use purity 0; other tiles default to 255 until their
    own purity rules are added.
    """

    tile: Tile
    purity: int = 0


Grid = List[List[Cell]]


# Snap-to-8 orientation set for the v0.8.0 green bands. Picking one of
# eight discrete angles keeps the bands looking crisp on a low-res
# grid; freely sampled angles produce aliasing under integer cell math.
GREEN_BAND_ORIENTATIONS: Tuple[float, ...] = tuple(
    i * math.pi / 8.0 for i in range(8)
)
"""Snap-to-8: 0°, 22.5°, 45°, 67.5°, 90°, 112.5°, 135°, 157.5°."""

GREEN_BAND_COUNT_CHOICES: Tuple[int, ...] = (1, 2, 3)
GREEN_BAND_HALF_WIDTH: float = 1.5
GREEN_BAND_JITTER: float = 0.1


@dataclass
class GenerationParams:
    """Knobs exposed to the CLI for tuning the topography."""

    width: int = 80
    height: int = 50
    seed: int = 0

    green_strength: float = 1.0
    #: DEPRECATED (v0.8.0). Pre-band-gen knob — controlled the half-depth
    #: of the polar mask as a fraction of height. Retained so existing
    #: CLI / config callers don't crash; the new generator ignores it.
    band_depth: float = 0.18
    #: Discrete count choices for the diagonal green bands. The
    #: generator rolls one of these uniformly per session.
    green_band_count_choices: Tuple[int, ...] = field(
        default_factory=lambda: GREEN_BAND_COUNT_CHOICES,
    )
    #: Half-width of each band in cell units. ``1.5`` → ~3 cells thick.
    green_band_half_width: float = GREEN_BAND_HALF_WIDTH
    #: Jitter applied to each band center as a fraction of the per-band
    #: spacing. ``0.1`` = bands can shift ±10% off their ideal slot.
    green_band_jitter: float = GREEN_BAND_JITTER
    #: Discrete orientation set the generator picks from.
    green_band_orientations: Tuple[float, ...] = field(
        default_factory=lambda: GREEN_BAND_ORIENTATIONS,
    )

    red_coverage: float = 0.30
    ridges: bool = True
    red_gamma: float = 5.0
    #: Manhattan steps from visible red boundary at which depth credit saturates.
    red_depth_ref: float = 3.0
    #: Blend ``ridge = (1-f)*t**gamma + f*t`` (``f`` in ``[0, 1]``). A nonzero
    #: ``f`` lifts mid-range ``t`` so seam interiors reach vein/mass more often.
    red_ridge_linear: float = 0.28
    #: Added to ``t ** red_gamma`` in thick cells so cores can hit 255 without
    #: requiring ``t == 1`` (rare in floating noise). Only applied for
    #: ``d >= red_pure_min_depth``.
    red_core_boost: float = 0.35
    #: Minimum depth (inclusive) before purity may be solid ``pure`` (255).
    red_pure_min_depth: int = 3

    blue_density: float = 0.03
    blue_smooth_iters: int = 1
    blue_gamma: float = 1.0
    #: Minimum purity for ANY generated BLUE cell. The depth gradient is
    #: remapped into ``[blue_min_purity, 255]`` instead of ``[0, 255]``
    #: so pocket-edge cells are still meaningfully fissile rather than
    #: worthless purity-0 tiles that look blue but fund nothing. Set to
    #: 0 to restore the legacy "edges fade to nothing" behaviour.
    blue_min_purity: int = 40

    #: Guarantee at least one pure (255) RED cell per generation. Natural pures
    #: only form in thick seam cores (depth >= ``red_pure_min_depth`` with the
    #: ridge saturated), so many seeds produce none — leaving a board with no
    #: redsign to contest. When True, :func:`generate_grid` deterministically
    #: promotes the strongest RED core (peak cell + up to two of its richest
    #: neighbours) to pure. Set False to restore the raw noise output.
    ensure_pure_red: bool = True


def _percentile_threshold(field: Field, top_fraction: float) -> float:
    """Return the value above which ``top_fraction`` of cells lie."""
    if top_fraction <= 0.0:
        return float("inf")
    if top_fraction >= 1.0:
        return float("-inf")
    flat = [v for row in field for v in row]
    flat.sort()
    idx = int(len(flat) * (1.0 - top_fraction))
    idx = max(0, min(len(flat) - 1, idx))
    return flat[idx]


def _smoothstep(edge: float, distance: float) -> float:
    """Smoothstep falloff from 1 at ``distance == 0`` to 0 at
    ``distance >= edge``. Standard cubic Hermite ``3t^2 - 2t^3`` on
    ``t = 1 - d/edge``.
    """
    if edge <= 0.0:
        return 1.0 if distance <= 0.0 else 0.0
    t = 1.0 - max(0.0, distance) / edge
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    return t * t * (3.0 - 2.0 * t)


def _green_band_mask(params: GenerationParams) -> Field:
    """Build the per-cell mask for v0.8.0 diagonal green bands.

    Rolls 1–3 same-orientation bands at one of the snap-to-8 angles,
    spaces their centers along the perpendicular axis with small
    jitter, and returns a ``[0..1]`` mask whose value is the largest
    smoothstep falloff to any band's center line.

    Reproducibility: the RNG seed is derived from ``params.seed`` so
    a fixed seed always rolls the same bands.
    """
    width = params.width
    height = params.height
    half_w = max(0.5, float(params.green_band_half_width))
    jitter_max = max(0.0, float(params.green_band_jitter))
    band_count_choices = tuple(params.green_band_count_choices) or (1, 2, 3)
    orientations = tuple(params.green_band_orientations) or (0.0,)

    # Dedicated child RNG so green band selection doesn't perturb the
    # RED / BLUE noise seeds (which use ``params.seed + N_000`` already).
    rng = random.Random(params.seed * 7919 + 1009)
    band_count = rng.choice(band_count_choices)
    theta = rng.choice(orientations)
    sin_t = math.sin(theta)
    cos_t = math.cos(theta)

    # Perpendicular-axis projection range: corners give the extrema.
    corners = [
        0.0 * sin_t - 0.0 * cos_t,
        (width - 1) * sin_t - 0.0 * cos_t,
        0.0 * sin_t - (height - 1) * cos_t,
        (width - 1) * sin_t - (height - 1) * cos_t,
    ]
    perp_min, perp_max = min(corners), max(corners)
    span = max(1e-6, perp_max - perp_min)
    # Evenly-spaced band centers along the perpendicular axis,
    # inset slightly from the edges so a single band doesn't grow
    # against the map border.
    centers: List[float] = []
    for i in range(band_count):
        base = perp_min + span * (i + 0.5) / band_count
        jitter = rng.uniform(-jitter_max, jitter_max) * (span / band_count)
        centers.append(base + jitter)

    mask: Field = [[0.0] * width for _ in range(height)]
    for y in range(height):
        for x in range(width):
            perp = x * sin_t - y * cos_t
            best = 0.0
            for c in centers:
                d = abs(perp - c)
                m = _smoothstep(half_w, d)
                if m > best:
                    best = m
            mask[y][x] = best
    return mask


def _red_edge_manhattan_depth(grid: Grid, width: int, height: int) -> List[List[int]]:
    """Minimum 4-neighbour steps from each RED cell to a non-RED cell.

    Used as a thickness proxy on the **final** map so polar bands and blue
    pockets reshape seam topology before purity is assigned.
    """
    inf = width + height + 100
    dist: List[List[int]] = [[inf] * width for _ in range(height)]
    q: List[tuple[int, int]] = []

    for y in range(height):
        for x in range(width):
            if grid[y][x].tile != Tile.RED:
                continue
            is_edge = False
            for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                ny, nx = y + dy, x + dx
                if not (0 <= ny < height and 0 <= nx < width):
                    is_edge = True
                    break
                if grid[ny][nx].tile != Tile.RED:
                    is_edge = True
                    break
            if is_edge:
                dist[y][x] = 1
                q.append((y, x))

    head = 0
    while head < len(q):
        y, x = q[head]
        head += 1
        d = dist[y][x]
        nd = d + 1
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            ny, nx = y + dy, x + dx
            if not (0 <= ny < height and 0 <= nx < width):
                continue
            if grid[ny][nx].tile != Tile.RED:
                continue
            if nd < dist[ny][nx]:
                dist[ny][nx] = nd
                q.append((ny, nx))
    return dist


def _finalize_red_purity(
    grid: Grid,
    ridge_t: List[List[float]],
    params: GenerationParams,
) -> None:
    """Set RED purity from ridge noise × visible seam thickness (depth)."""
    width = params.width
    height = params.height
    gamma = max(0.1, params.red_gamma)
    depth_ref = max(0.5, params.red_depth_ref)
    pure_floor = max(1, int(params.red_pure_min_depth))
    boost_max = max(0.0, float(params.red_core_boost))
    lin = max(0.0, min(1.0, float(params.red_ridge_linear)))

    dist = _red_edge_manhattan_depth(grid, width, height)
    inf = width + height + 100

    for y in range(height):
        for x in range(width):
            if grid[y][x].tile != Tile.RED:
                continue
            d = dist[y][x]
            if d >= inf:
                d = 1 + min(x, y, width - 1 - x, height - 1 - y)
            depth_factor = min(1.0, float(d) / depth_ref)
            t = ridge_t[y][x]
            if t < 0.0:
                t = 0.0
            elif t > 1.0:
                t = 1.0
            curved = t**gamma
            ridge = (1.0 - lin) * curved + lin * t
            boost = 0.0
            if d >= pure_floor and boost_max > 0.0:
                denom = max(1e-6, depth_ref - float(pure_floor) + 1.0)
                boost = boost_max * min(
                    1.0, float(d - pure_floor + 1) / denom
                )
            combined = min(1.0, ridge + boost)
            raw = 255.0 * depth_factor * combined
            p = int(round(raw))
            if p < 0:
                p = 0
            elif p > 255:
                p = 255
            if d < pure_floor:
                p = min(p, 254)
            grid[y][x] = Cell(Tile.RED, p)


def _apply_red(
    grid: Grid,
    params: GenerationParams,
    ridge_t: List[List[float]],
) -> None:
    """Paint RED cells and record normalized ridge coordinate ``t`` per cell.

    Purity is assigned later by :func:`_finalize_red_purity` so it respects
    topology after ``GREEN`` / ``BLUE`` overpaint.
    """
    if params.red_coverage <= 0.0:
        return

    base_scale = max(8.0, min(params.width, params.height) / 4.0)
    field = fbm_2d(
        params.width,
        params.height,
        base_scale=base_scale,
        octaves=4,
        persistence=0.5,
        lacunarity=2.0,
        seed=params.seed + 1_000,
    )
    if params.ridges:
        field = ridge_transform(field)

    threshold = _percentile_threshold(field, params.red_coverage)
    span = max(1e-6, 1.0 - threshold)

    for y in range(params.height):
        row = grid[y]
        frow = field[y]
        trow = ridge_t[y]
        for x in range(params.width):
            val = frow[x]
            if val >= threshold:
                t = (val - threshold) / span
                if t < 0.0:
                    t = 0.0
                elif t > 1.0:
                    t = 1.0
                trow[x] = t
                row[x] = Cell(Tile.RED, 0)


def _apply_green(grid: Grid, params: GenerationParams) -> None:
    """Paint diagonal bands by combining a band mask with fBm noise.

    v0.8.0 — replaces the polar ``_edge_mask`` with
    :func:`_green_band_mask`. The fBm noise layer and the
    ``threshold`` rule are unchanged so a tuned ``green_strength``
    still controls overall coverage.
    """
    if params.green_strength <= 0.0:
        return
    if not params.green_band_count_choices:
        return

    base_scale = max(4.0, params.width / 12.0)
    noise = fbm_2d(
        params.width,
        params.height,
        base_scale=base_scale,
        octaves=3,
        persistence=0.5,
        lacunarity=2.0,
        seed=params.seed + 2_000,
    )
    mask = _green_band_mask(params)

    threshold = 0.35 / max(0.01, params.green_strength)
    for y in range(params.height):
        row = grid[y]
        nrow = noise[y]
        mrow = mask[y]
        for x in range(params.width):
            if mrow[x] * nrow[x] >= threshold:
                row[x] = Cell(Tile.GREEN, 255)


def _smooth_blue(grid: Grid, width: int, height: int, iters: int) -> None:
    """Cellular-automata smoothing: keep BLUE cells with >= 2 BLUE neighbors."""
    for _ in range(iters):
        snapshot = [[c.tile for c in row] for row in grid]
        for y in range(height):
            for x in range(width):
                if snapshot[y][x] != Tile.BLUE:
                    continue
                neighbors = 0
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        if dx == 0 and dy == 0:
                            continue
                        nx, ny = x + dx, y + dy
                        if 0 <= nx < width and 0 <= ny < height:
                            if snapshot[ny][nx] == Tile.BLUE:
                                neighbors += 1
                if neighbors < 2:
                    grid[y][x] = Cell(Tile.EMPTY, 0)


def _blue_distance_field(grid: Grid, width: int, height: int) -> List[List[int]]:
    """Chebyshev distance from each BLUE cell to the nearest non-BLUE or boundary.

    Computed with the standard two-pass distance-transform sweep: forward
    pass touches only previously visited neighbors, backward pass closes the
    other half. Non-blue cells keep distance ``0``; blue cells get ``>= 1``.
    The grid boundary counts as non-blue, so cells on the edge of the map
    can never sit deeper than ``1``.
    """
    inf = width + height + 1
    dist: List[List[int]] = [
        [inf if grid[y][x].tile == Tile.BLUE else 0 for x in range(width)]
        for y in range(height)
    ]

    for y in range(height):
        for x in range(width):
            if dist[y][x] == 0:
                continue
            best = dist[y][x]
            for dy, dx in ((-1, -1), (-1, 0), (-1, 1), (0, -1)):
                ny, nx = y + dy, x + dx
                if 0 <= ny < height and 0 <= nx < width:
                    candidate = dist[ny][nx] + 1
                    if candidate < best:
                        best = candidate
                else:
                    if 1 < best:
                        best = 1
            dist[y][x] = best

    for y in range(height - 1, -1, -1):
        for x in range(width - 1, -1, -1):
            if dist[y][x] == 0:
                continue
            best = dist[y][x]
            for dy, dx in ((1, 1), (1, 0), (1, -1), (0, 1)):
                ny, nx = y + dy, x + dx
                if 0 <= ny < height and 0 <= nx < width:
                    candidate = dist[ny][nx] + 1
                    if candidate < best:
                        best = candidate
                else:
                    if 1 < best:
                        best = 1
            dist[y][x] = best

    return dist


def _apply_blue(grid: Grid, params: GenerationParams) -> None:
    """Sprinkle dotted concentrations and compute per-pocket water depth.

    Two stages, deliberately split so the blob *shapes* and the *depths*
    don't fight each other:

    1. Noise-threshold + optional CA smoothing decides which cells are
       BLUE.
    2. Walk each connected component once: the cell with the highest
       distance-transform value is the pocket's peak (its geometric
       center), and every other cell's purity is graded by its Chebyshev
       distance *from that single peak*. The peak reaches purity ``255``
       (solid ``deep``); other cells spread across the lower purity bands
       defined in :mod:`sea_of_colours.render`.

    The falloff exponent ``blue_gamma`` controls how quickly purity drops
    with distance from the peak (1.0 = linear; >1 grows the shallow edge;
    <1 keeps more cells near deep).
    """
    if params.blue_density <= 0.0:
        return

    width = params.width
    height = params.height

    base_scale = max(4.0, width / 16.0)
    field = fbm_2d(
        width,
        height,
        base_scale=base_scale,
        octaves=3,
        persistence=0.5,
        lacunarity=2.0,
        seed=params.seed + 3_000,
    )
    threshold = _percentile_threshold(field, params.blue_density)
    for y in range(height):
        row = grid[y]
        frow = field[y]
        for x in range(width):
            if frow[x] >= threshold:
                row[x] = Cell(Tile.BLUE, 0)

    if params.blue_smooth_iters > 0:
        _smooth_blue(grid, width, height, params.blue_smooth_iters)

    dist = _blue_distance_field(grid, width, height)
    gamma = max(0.1, params.blue_gamma)
    visited: List[List[bool]] = [[False] * width for _ in range(height)]

    for y0 in range(height):
        for x0 in range(width):
            if visited[y0][x0] or grid[y0][x0].tile != Tile.BLUE:
                continue

            stack = [(y0, x0)]
            comp: List[tuple] = []
            peak_y, peak_x = y0, x0
            peak_d = dist[y0][x0]
            while stack:
                y, x = stack.pop()
                if visited[y][x]:
                    continue
                visited[y][x] = True
                comp.append((y, x))
                if dist[y][x] > peak_d:
                    peak_d = dist[y][x]
                    peak_y, peak_x = y, x
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        if dy == 0 and dx == 0:
                            continue
                        ny, nx = y + dy, x + dx
                        if 0 <= ny < height and 0 <= nx < width:
                            if (
                                not visited[ny][nx]
                                and grid[ny][nx].tile == Tile.BLUE
                            ):
                                stack.append((ny, nx))

            ref = max(2, peak_d + 1)
            # Remap the depth gradient into ``[floor, 255]`` so even the
            # shallowest pocket-edge cell carries usable fissile value
            # (a purity-0 BLUE tile renders blue but funds nothing — a
            # trap, RULEBOOK §2.4).
            floor = max(0, min(255, int(params.blue_min_purity)))
            span = 255.0 - float(floor)
            for cy, cx in comp:
                cheb = max(abs(cy - peak_y), abs(cx - peak_x))
                t = cheb / ref
                if t < 0.0:
                    t = 0.0
                elif t > 1.0:
                    t = 1.0
                purity = int(floor + ((1.0 - t) ** gamma) * span)
                if purity < floor:
                    purity = floor
                elif purity > 255:
                    purity = 255
                grid[cy][cx] = Cell(Tile.BLUE, purity)


def _ensure_pure_red(grid: Grid, params: GenerationParams) -> None:
    """Guarantee at least one pure (255) RED cell on the board.

    Natural pures only occur in thick seam cores (see :func:`_finalize_red_purity`),
    so many seeds produce a board with no redsign to contest. If none exists, this
    deterministically promotes the strongest RED core to pure: the richest RED cell
    (peak, tie-broken by coordinates) plus up to two of its richest 8-neighbours,
    so the guaranteed pure reads as a small natural seam rather than an isolated
    cell. No-op when a pure already exists or the board carries no RED at all.
    Purely a function of the already-assigned purities — no RNG, so it is
    seed-stable.
    """
    width, height = params.width, params.height
    reds: List[Tuple[int, int, int]] = []  # (purity, y, x)
    for y in range(height):
        for x in range(width):
            c = grid[y][x]
            if c.tile != Tile.RED:
                continue
            if c.purity >= 255:
                return  # a natural pure already exists — leave the map untouched
            reds.append((c.purity, y, x))
    if not reds:
        return  # no RED on the board — nothing to promote (e.g. red_coverage 0)

    # Peak = richest cell; ties resolved by coordinates for determinism.
    reds.sort(key=lambda r: (-r[0], r[1], r[2]))
    _, py, px = reds[0]
    grid[py][px] = Cell(Tile.RED, 255)

    # Grow a tiny core: promote up to two of the peak's richest RED neighbours.
    neighbours: List[Tuple[int, int, int]] = []
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy == 0 and dx == 0:
                continue
            ny, nx = py + dy, px + dx
            if not (0 <= ny < height and 0 <= nx < width):
                continue
            c = grid[ny][nx]
            if c.tile == Tile.RED and c.purity < 255:
                neighbours.append((c.purity, ny, nx))
    neighbours.sort(key=lambda r: (-r[0], r[1], r[2]))
    for _, ny, nx in neighbours[:2]:
        grid[ny][nx] = Cell(Tile.RED, 255)


def generate_grid(params: GenerationParams) -> Grid:
    """Generate a topography grid by compositing the three biome layers."""
    if params.width <= 0 or params.height <= 0:
        raise ValueError("width and height must be positive")

    grid: Grid = [
        [Cell(Tile.EMPTY, 0) for _ in range(params.width)]
        for _ in range(params.height)
    ]
    ridge_t: List[List[float]] = [
        [0.0 for _ in range(params.width)] for _ in range(params.height)
    ]
    _apply_red(grid, params, ridge_t)
    _apply_green(grid, params)
    _apply_blue(grid, params)
    _finalize_red_purity(grid, ridge_t, params)
    if params.ensure_pure_red:
        _ensure_pure_red(grid, params)
    return grid
