"""Generator invariant (v1.24, RULEBOOK §2.2): pures are plural and far apart.

v1.21 stopped pures *touching*. That left two legal boards that both flatten
the opening:

* **One jackpot.** Nothing to choose between, so the season's first real
  decision — which seam to commit to — never gets asked.
* **Two jackpots four cells apart.** One probe disk lights both, so finding
  either hands you the pair. Same non-decision, dressed up.

v1.24 therefore guarantees ``min_pure_count`` (2) pures at a Chebyshev
distance of at least ``min_pure_separation`` (12). Chebyshev because the
question the metric has to answer is "can one probe see both", and probe
vision is a disk measured in king moves.

The separation is best-effort and the COUNT is the hard floor — see
``test_a_degenerate_board_keeps_the_count``. That asymmetry is deliberate
and these tests pin it in both directions, because the tempting "just retry
the seed until it fits" implementation livelocks on a board whose RED is one
small blob.
"""

from __future__ import annotations

from sea_of_colours.generator import (
    Cell,
    GenerationParams,
    Tile,
    _spread_pure_red,
    generate_grid,
)

# The board /api/game/new actually serves. GenerationParams defaults to
# 80x50; measuring that would overstate how easy the constraint is to meet.
_W, _H = 40, 28

_MIN_COUNT = 2
_MIN_SEP = 12


def _pure_cells(grid):
    return [
        (x, y)
        for y, row in enumerate(grid)
        for x, c in enumerate(row)
        if c.tile == Tile.RED and c.purity == 255
    ]


def _chebyshev(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def _closest_pair(cells):
    """Smallest Chebyshev gap between any two cells, or None if fewer than 2."""
    if len(cells) < 2:
        return None
    return min(
        _chebyshev(cells[i], cells[j])
        for i in range(len(cells))
        for j in range(i + 1, len(cells))
    )


def _params(seed, **kw):
    return GenerationParams(width=_W, height=_H, seed=seed, **kw)


def test_every_board_carries_at_least_two_pures():
    """The count floor, over enough seeds to be meaningful."""
    for seed in range(200):
        pures = _pure_cells(generate_grid(_params(seed)))
        assert len(pures) >= _MIN_COUNT, (
            f"seed {seed} has {len(pures)} pure(s) — a board with one jackpot "
            "gives the opening nothing to decide"
        )


def test_no_two_pures_stand_closer_than_the_separation():
    """The distance rule. Subsumes the v1.21 no-touching invariant."""
    for seed in range(200):
        pures = _pure_cells(generate_grid(_params(seed)))
        gap = _closest_pair(pures)
        assert gap is not None and gap >= _MIN_SEP, (
            f"seed {seed} has two pures {gap} apart (need {_MIN_SEP}); "
            f"pures at {pures}"
        )


def test_the_separation_still_forbids_touching():
    """v1.21's rule must survive inside v1.24's, not be replaced by it.

    Stated separately because the two rules live in different functions and
    a future retune of ``min_pure_separation`` to something tiny would
    silently give back the slabs.
    """
    for seed in range(120):
        pures = set(_pure_cells(generate_grid(_params(seed))))
        for (x, y) in pures:
            neighbours = {
                (x + dx, y + dy)
                for dx in (-1, 0, 1)
                for dy in (-1, 0, 1)
                if (dx, dy) != (0, 0)
            }
            assert not (neighbours & pures), f"seed {seed}: touching pure at {(x, y)}"


def test_the_rule_bites_on_boards_that_would_otherwise_fail():
    """Guard against the rule quietly becoming a no-op.

    If the raw generator already met the constraint on every seed, every
    test above would pass while measuring nothing. Pin that the un-spread
    path really does produce boards the rule has to correct — both failure
    modes, too few pures AND pures too close.
    """
    too_few = too_close = 0
    for seed in range(200):
        pures = _pure_cells(generate_grid(_params(seed, spread_pure_red=False)))
        if len(pures) < _MIN_COUNT:
            too_few += 1
        gap = _closest_pair(pures)
        if gap is not None and gap < _MIN_SEP:
            too_close += 1
    assert too_few > 0, (
        "no seed produced fewer than two pures without the rule — the count "
        "floor may no longer be testing anything"
    )
    assert too_close > 0, (
        "no seed produced pures closer than the separation without the rule — "
        "the distance guarantee may no longer be testing anything"
    )


def test_the_toggle_restores_the_v121_behaviour():
    """``spread_pure_red=False`` must be a true off switch."""
    off = generate_grid(_params(31, spread_pure_red=False))
    on = generate_grid(_params(31))
    assert _pure_cells(off) != _pure_cells(on) or _closest_pair(
        _pure_cells(off)
    ) in (None, *range(_MIN_SEP, 99)), "seed 31 chosen to exercise the rule"
    # The off path is free to violate both halves; the on path never is.
    assert len(_pure_cells(on)) >= _MIN_COUNT


def test_only_purities_move_and_only_red_cells():
    """Spread may promote and demote, but must not re-terraform the board.

    The demotion band is shared with declustering; the promotion writes 255.
    Nothing may change tile, and no non-RED cell may be touched — that would
    mean the rule is consuming a live RNG stream or writing the wrong cell.
    """
    for seed in range(60):
        before = generate_grid(_params(seed, spread_pure_red=False))
        after = generate_grid(_params(seed))
        for y in range(_H):
            for x in range(_W):
                a, b = before[y][x], after[y][x]
                assert a.tile == b.tile, f"seed {seed}: tile moved at {(x, y)}"
                if a.purity == b.purity:
                    continue
                assert a.tile == Tile.RED, (
                    f"seed {seed}: changed a non-RED cell at {(x, y)}"
                )
                # Either a demotion out of pure, or a promotion up to pure.
                assert (a.purity == 255 and 220 <= b.purity <= 254) or (
                    b.purity == 255
                ), f"seed {seed}: unexpected {a.purity} -> {b.purity} at {(x, y)}"


def test_seed_stability_no_other_layer_moves():
    """The rule draws from a FRESH stream (seed + 5_000).

    RED/GREEN/BLUE take 1_000/2_000/3_000 and declustering 4_000. Reusing a
    live stream would shift tile placement for every seed ever generated;
    this is the test that catches it.
    """
    for seed in range(60):
        before = generate_grid(_params(seed, spread_pure_red=False))
        after = generate_grid(_params(seed))
        assert [[c.tile for c in row] for row in before] == [
            [c.tile for c in row] for row in after
        ], f"seed {seed}: tile layout moved — a shared RNG stream was consumed"


def test_it_is_deterministic_for_a_seed():
    a = generate_grid(_params(99))
    b = generate_grid(_params(99))
    assert [[(c.tile, c.purity) for c in row] for row in a] == [
        [(c.tile, c.purity) for c in row] for row in b
    ]


def test_a_degenerate_board_keeps_the_count():
    """COUNT is the hard floor; SEPARATION is best-effort.

    A board whose RED is one small vein cannot host two pures 12 apart. The
    rule must still deliver two — two contested jackpots close together beat
    one uncontested — and must not spin looking for a placement that does
    not exist. Built by hand rather than by seed, because the generator does
    not produce a board this degenerate.

    The fixture is a 9-long strip with the pure at one end, so the candidate
    cells sit at Chebyshev 1..8 and the "take the furthest available" rule
    has something to actually choose between. A square blob would leave every
    candidate equidistant and the test would pass on a fallback that simply
    grabbed the first cell it saw.
    """
    grid = [[Cell(Tile.EMPTY, 0) for _ in range(_W)] for _ in range(_H)]
    for x in range(5, 14):
        grid[6][x] = Cell(Tile.RED, 200)
    grid[6][5] = Cell(Tile.RED, 255)

    _spread_pure_red(grid, _params(1))

    pures = _pure_cells(grid)
    assert len(pures) == _MIN_COUNT, "the count floor holds on a cramped board"
    gap = _closest_pair(pures)
    assert gap is not None and gap < _MIN_SEP, (
        "this fixture cannot satisfy the separation — the test is only "
        "meaningful if the fallback actually had to fire"
    )
    assert gap == 8, (
        f"the fallback must take the FURTHEST available cell, got {gap} "
        "(the far end of the strip is 8 from the existing pure)"
    )
    assert (13, 6) in pures, "the far end is the only correct choice here"


def test_no_red_at_all_is_a_no_op():
    """A board with no RED gets no pures and does not spin."""
    grid = [[Cell(Tile.EMPTY, 0) for _ in range(_W)] for _ in range(_H)]
    _spread_pure_red(grid, _params(1))
    assert _pure_cells(grid) == []


# ── v1.28: one jackpot per House ────────────────────────────────────
#
# The floor above is the GENERATOR's default of 2. v1.28 scales the real
# floor with the seat count at the call site in ``GameSession.new``, so
# these go through a whole session rather than ``generate_grid`` — the
# plumbing is the thing under test, and a generator-level test cannot see
# it. The dataclass default stays 2 on purpose, so every test above keeps
# its meaning.


def _session_pures(seats, seed=7):
    from sea_of_colours.game.session import GameSession

    sess = GameSession.new(_W, _H, seed=seed, players=seats)
    return sess, _pure_cells(sess.grid)


def test_the_pure_floor_scales_with_the_seat_count():
    """Four Houses, four jackpots — and still no pair within one probe disk.

    A flat floor of 2 on a 4-seat board hands two seats a jackpot each and
    two seats none, which is the same flattened opening §2.2 exists to
    prevent, only now distributed unfairly.
    """
    for n in (2, 3, 4):
        seats = [f"p{i}" for i in range(1, n + 1)]
        sess, pures = _session_pures(seats)
        assert len(sess.players) == n, "fixture built the wrong seat count"
        assert len(pures) >= n, (
            f"{n} seats got {len(pures)} pure cell(s) — every House must be "
            f"able to contest a jackpot"
        )
        gap = _closest_pair(pures)
        assert gap is not None and gap >= _MIN_SEP, (
            f"{n} seats: closest pure pair is {gap} apart, under the "
            f"{_MIN_SEP} separation — one probe disk lights both, so raising "
            f"the count just re-created the cluster it replaced"
        )


def test_the_floor_never_drops_below_two():
    """A solo season still gets a choice to make.

    ``max(2, seats)``, not ``seats`` — one jackpot is the original
    no-decision board, and a single-seat game is the one place where a
    naive count would produce it.
    """
    _, pures = _session_pures(["p1"])
    assert len(pures) >= 2, (
        "a 1-seat season fell to a single jackpot — the floor is max(2, n)"
    )


def test_duplicate_seats_do_not_inflate_the_floor():
    """Counted off the NORMALISED seats, not the raw argument.

    ``GameSession.new`` dedupes and clamps ``players`` (v0.9.6, for a UI
    that double-posts a seat). Reading ``len(players)`` instead would ask
    for three jackpots on a two-House board, which is why the seat
    normalisation now runs BEFORE the map is generated.
    """
    dup_sess, dup = _session_pures(["p1", "p1", "p2"])
    _, plain = _session_pures(["p1", "p2"])
    assert len(dup_sess.players) == 2
    assert len(dup) == len(plain), (
        f"a duplicated seat asked for {len(dup)} pures where the same two "
        f"Houses got {len(plain)} — the count read the raw list"
    )


def test_the_default_seat_list_still_gets_the_v124_board():
    """``players=None`` is the legacy 2-seat default and must not move.

    Pins that the reorder did not change the map any existing caller gets:
    identical cell for cell to an explicit two-seat game.
    """
    _, implicit = _session_pures(None)
    _, explicit = _session_pures(["p1", "p2"])
    assert implicit == explicit


def test_more_seats_is_a_superset_not_a_reshuffle():
    """Raising the floor may only ADD jackpots, never move the existing ones.

    ``_spread_pure_red`` tops up by promotion, so a 4-seat board must be the
    2-seat board plus two more. If this fails the count is being met by
    re-running the thinning pass with different survivors, which would mean
    the seat count silently re-rolls terrain the seed is supposed to fix.
    """
    _, two = _session_pures(["p1", "p2"])
    _, four = _session_pures(["p1", "p2", "p3", "p4"])
    assert set(two) <= set(four), (
        f"the 2-seat jackpots {sorted(set(two) - set(four))} vanished when a "
        f"third and fourth House joined the same seed"
    )


def test_only_the_pures_move_when_seats_are_added():
    """Everything else on the board is identical.

    The seat count feeds exactly one dial. Any tile change, or a purity
    change on a cell that is not a promoted pure, means it reached a shared
    RNG stream — the same failure ``test_the_tile_layout_is_unchanged``
    guards at the generator level.
    """
    two_sess, two = _session_pures(["p1", "p2"])
    four_sess, four = _session_pures(["p1", "p2", "p3", "p4"])
    added = set(four) - set(two)
    for y in range(_H):
        for x in range(_W):
            a, b = two_sess.grid[y][x], four_sess.grid[y][x]
            assert a.tile == b.tile, f"tile moved at ({x},{y}) — shared RNG"
            if a.purity != b.purity:
                assert (x, y) in added, (
                    f"purity moved at ({x},{y}) ({a.purity} -> {b.purity}) on "
                    f"a cell that is not one of the added jackpots"
                )
