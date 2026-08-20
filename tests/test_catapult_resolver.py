"""v0.9.x catapult resolver tests (RULEBOOK §4.4 / §4.5).

These cover the redesigned orbit catapults in isolation:

  - RED shipping catapult: per-parcel CREDIT bids, global rank, 20-slot
    draft, per-row TRANSIT charges (10/25/50/100) out of each parcel's
    own purity, tier-multiplier on the ORIGINAL purity.
  - Tiebreaks: equal credit bids resolve on total credits committed,
    then parcel count, then purity.
  - Overflow: bids that miss all 20 slots stay in the hoard and forfeit
    their credits.
  - Locking: ordered affordability (later bids rejected when credits
    run out) + no same-turn cascade (a ship-locked parcel can't be
    refined).
  - GREEN disposal catapult: 12 shared slots dealt round-robin by
    offer, diminishing RED-fuel cost (50/45/.../0), committed RED
    forfeit, and the endgame green liability bleeding into ``score_for``.
"""

from __future__ import annotations

from typing import List

from sea_of_colours.game.orbit_resolver import OrbitResolver
from sea_of_colours.game.policy import ShipCatapultBid, SolarJettisonBid
from sea_of_colours.game.session import (
    CATAPULT_ROW_TRANSIT,
    GREEN_ENDGAME_PENALTY,
    GameSession,
    Phase,
    RED_QUALITY_MULTIPLIER,
)
from sea_of_colours.generator import Tile


# ── Helpers ─────────────────────────────────────────────────────────


def _fresh(
    width: int = 20, height: int = 14, *,
    players: tuple = ("p1", "p2"),
    credits: int = 1000,
) -> GameSession:
    sess = GameSession.new(width, height, seed=11, players=players)
    sess.phase = Phase.ORBIT
    sess.pending_orbit_actions = {p: None for p in players}
    sess.credits = {p: int(credits) for p in players}
    sess._orbit_credits_awarded_day = int(sess.day)  # type: ignore[attr-defined]
    # Start each test from a clean hoard so stamped parcels are the
    # only contents (GameSession.new seeds nothing into hoard, but be
    # explicit so a future change can't pollute these assertions).
    for p in players:
        sess.hoard_squares[p] = []
    return sess


def _stamp_red(
    sess: GameSession, owner: str, parcels: List[tuple[str, int]],
) -> None:
    sess.hoard_squares[owner] = list(sess.hoard_squares[owner]) + [
        {
            "square_id": sid,
            "site_id": sid,
            "tile_at_harvest": int(Tile.RED),
            "purity_at_harvest": int(p),
            "origin_purity": int(p),
            "origin_tile": int(Tile.RED),
            "lineage": "natural",
        }
        for sid, p in parcels
    ]


def _stamp_green(sess: GameSession, owner: str, ids: List[str]) -> None:
    sess.hoard_squares[owner] = list(sess.hoard_squares[owner]) + [
        {
            "square_id": sid,
            "site_id": sid,
            "tile_at_harvest": int(Tile.GREEN),
            "purity_at_harvest": 255,
            "origin_purity": 255,
            "origin_tile": int(Tile.GREEN),
            "lineage": "natural",
        }
        for sid in ids
    ]


def _ship(*pairs: tuple[str, int]) -> ShipCatapultBid:
    return ShipCatapultBid(bids=tuple((str(i), int(c)) for i, c in pairs))


# ── RED catapult: single bid, row-0 transit ─────────────────────────


def test_single_bid_ships_row0_with_transit_10() -> None:
    """A lone bid wins slot 0 (row 0, transit 10). A mass-200 parcel
    ships at effective 190 and scores 190 × 1.5 = 285."""
    sess = _fresh()
    _stamp_red(sess, "p1", [("a", 200)])
    OrbitResolver().run(sess, {"p1": [_ship(("a", 50))], "p2": []})

    cat = sess.catapult_history[-1]["catapult"]
    seat = cat["seats"]["p1"]
    assert seat["awarded"] == 1
    assert sess.credits["p1"] == 1000 - 50  # credits debited at lock

    shipped = sess.shipped_squares["p1"]
    assert len(shipped) == 1
    assert int(shipped[0]["effective_purity"]) == 190
    assert shipped[0]["score_tier"] == "mass"
    assert shipped[0]["transit_charge"] == 10

    expected = round(190 * RED_QUALITY_MULTIPLIER["mass"])
    assert expected == 285
    assert sess.score_for("p1") == 285
    assert sess.cumulative_shipped_score["p1"] == 285


def test_tier_multiplier_keys_off_original_purity() -> None:
    """Transit shaves a pure-255 to 245 but it keeps its ×3 (the tier
    multiplier reads the ORIGINAL purity, not the post-transit value)."""
    sess = _fresh()
    _stamp_red(sess, "p1", [("pure", 255)])
    OrbitResolver().run(sess, {"p1": [_ship(("pure", 100))], "p2": []})

    shipped = sess.shipped_squares["p1"][0]
    assert int(shipped["effective_purity"]) == 245
    assert shipped["score_tier"] == "pure"
    # 245 × 3.0 = 735 (NOT 245 × 1.5 that a "mass" tier would give).
    assert sess.score_for("p1") == 735


# ── Ranking determines which row (and so the transit charge) ────────


def test_credit_rank_pushes_lowballer_into_row1() -> None:
    """Five 100-credit bids monopolise row 0; a lone 10-credit bid is
    pushed into row 1 (transit 25)."""
    sess = _fresh()
    _stamp_red(sess, "p1", [(f"hi{i}", 200) for i in range(5)])
    _stamp_red(sess, "p2", [("low", 100)])
    OrbitResolver().run(
        sess,
        {
            "p1": [_ship(*[(f"hi{i}", 100) for i in range(5)])],
            "p2": [_ship(("low", 10))],
        },
    )
    cat = sess.catapult_history[-1]["catapult"]
    slots = cat["slot_assignments"]
    assert len(slots) == 20
    for s in slots[0:5]:
        assert s["seat"] == "p1"
        assert s["transit_charge"] == 10
    s5 = slots[5]
    assert s5["seat"] == "p2"
    assert s5["row"] == 1
    assert s5["transit_charge"] == 25
    assert int(s5["effective_purity"]) == 75  # 100 - 25
    assert s5["tier"] == "vein"
    assert float(s5["score"]) == 75.0


def test_equal_bids_tiebreak_on_total_credits_committed() -> None:
    """Two 30-credit bids tie. The seat that committed MORE total
    credits wins the better (earlier) slot — even with lower purity."""
    sess = _fresh()
    # p1 commits 30 + 5 = 35 total; its 30-bid parcel is only purity 100.
    _stamp_red(sess, "p1", [("p1-hi", 100), ("p1-lo", 80)])
    # p2 commits 30 total; its parcel is HIGHER purity 200.
    _stamp_red(sess, "p2", [("p2", 200)])
    OrbitResolver().run(
        sess,
        {
            "p1": [_ship(("p1-hi", 30), ("p1-lo", 5))],
            "p2": [_ship(("p2", 30))],
        },
    )
    slots = sess.catapult_history[-1]["catapult"]["slot_assignments"]
    # Slot 0 goes to p1 (higher total credits) despite lower purity.
    assert slots[0]["seat"] == "p1"
    assert slots[0]["parcel"]["square_id"] == "p1-hi"
    assert slots[1]["seat"] == "p2"
    assert slots[2]["seat"] == "p1"  # the 5-credit straggler


# ── Transit can zero a parcel ───────────────────────────────────────


def test_transit_zeroes_parcel_below_charge() -> None:
    """A purity-8 parcel in row 0 (charge 10) scores 0 but still ships
    (slot consumed, no further charge), flagged transit_zeroed."""
    sess = _fresh()
    _stamp_red(sess, "p1", [("tiny", 8)])
    OrbitResolver().run(sess, {"p1": [_ship(("tiny", 40))], "p2": []})

    slot0 = sess.catapult_history[-1]["catapult"]["slot_assignments"][0]
    assert slot0["seat"] == "p1"
    assert slot0["shipped"] is True
    assert int(slot0["effective_purity"]) == 0
    assert float(slot0["score"]) == 0.0
    assert slot0.get("disposition") == "transit_zeroed"
    assert sess.score_for("p1") == 0


# ── Overflow beyond 20 slots ────────────────────────────────────────


def test_overflow_beyond_20_slots_forfeits_credits() -> None:
    """21 bids: the 20 highest-purity ship, the lowest overflows (stays
    in hoard) and its credit bid is still forfeit."""
    sess = _fresh()
    _stamp_red(sess, "p1", [(f"r{i}", 100 + i) for i in range(21)])
    OrbitResolver().run(
        sess,
        {"p1": [_ship(*[(f"r{i}", 10) for i in range(21)])], "p2": []},
    )
    cat = sess.catapult_history[-1]["catapult"]
    assert cat["seats"]["p1"]["awarded"] == 20
    assert len(cat["overflow"]) == 1
    # Lowest purity (r0 = 100) loses the purity tiebreak and overflows.
    assert cat["overflow"][0]["parcel_id"] == "r0"
    hoard_ids = {p["square_id"] for p in sess.hoard_squares["p1"]}
    assert hoard_ids == {"r0"}
    # All 21 credit bids were debited (forfeit even for the overflow).
    assert sess.credits["p1"] == 1000 - 21 * 10


# ── Locking: ordered affordability ──────────────────────────────────


def test_ordered_affordability_rejects_later_bids() -> None:
    """100 credits, five 25-credit bids in order: the first four lock,
    the fifth is rejected (credits exhausted) and stays in the hoard."""
    sess = _fresh(credits=100)
    _stamp_red(sess, "p1", [(f"s{i}", 60 + i) for i in range(5)])
    OrbitResolver().run(
        sess,
        {"p1": [_ship(*[(f"s{i}", 25) for i in range(5)])], "p2": []},
    )
    cat = sess.catapult_history[-1]["catapult"]
    assert cat["seats"]["p1"]["awarded"] == 4
    assert sess.credits["p1"] == 0
    # The fifth bid (s4) never locked → still in the hoard.
    hoard_ids = {p["square_id"] for p in sess.hoard_squares["p1"]}
    assert hoard_ids == {"s4"}


# ── Locking: no same-turn cascade ───────────────────────────────────


def test_ship_locked_parcel_is_not_refined_same_turn() -> None:
    """A parcel locked by a ship bid can't be consumed by a later
    refine action in the same Orbit pass."""
    sess = _fresh()
    # Six trace parcels; ``keep`` is ship-locked, the other five are
    # the refine pool (refine cap is 5).
    _stamp_red(sess, "p1", [("keep", 50)] + [(f"t{i}", 50) for i in range(5)])
    from sea_of_colours.game.policy import RefineAction

    OrbitResolver().run(
        sess,
        {
            "p1": [
                _ship(("keep", 50)),
                RefineAction(inputs=(), source_tier="trace"),
            ],
            "p2": [],
        },
    )
    # ``keep`` shipped (transit 10 → effective 40); the five t* were
    # refined away (consumed) and replaced by a vein output.
    shipped_ids = {p["square_id"] for p in sess.shipped_squares["p1"]}
    assert "keep" in shipped_ids
    hoard_ids = {p["square_id"] for p in sess.hoard_squares["p1"]}
    assert "keep" not in hoard_ids
    assert not (hoard_ids & {f"t{i}" for i in range(5)})  # all consumed
    # A refined (vein) output now sits in the hoard.
    assert any(
        int(p.get("origin_purity", 0)) > 50
        for p in sess.hoard_squares["p1"]
    )


# ── Transit ramp tunable ────────────────────────────────────────────


def test_transit_charges_strictly_increase() -> None:
    """The per-row transit ramp must be monotonic so later (cheaper to
    win) rows are harsher on the parcel."""
    transit = list(CATAPULT_ROW_TRANSIT)
    assert transit == sorted(transit)
    assert transit[0] < transit[-1]
    assert transit == [10, 25, 50, 100]


# ── GREEN disposal catapult ─────────────────────────────────────────


def test_green_solo_flush_diminishing_cost() -> None:
    """Solo house commits 112 RED to flush 4 green. Slots cost 50, 45,
    40… so it clears 2 (50+45=95) and stalls before the 40 slot."""
    sess = _fresh()
    _stamp_red(sess, "p1", [("fuel", 200)])  # enough RED to burn 112
    _stamp_green(sess, "p1", [f"g{i}" for i in range(4)])
    OrbitResolver().run(
        sess,
        {"p1": [SolarJettisonBid(green_parcels=4, red_fuel=112)], "p2": []},
    )
    green = sess.catapult_history[-1]["jettison"]
    seat = green["seats"]["p1"]
    assert seat["awarded"] == 2
    assert seat["fuel_spent"] == 95
    assert seat["fuel_forfeit"] == 112  # all committed RED forfeit
    # 2 green flushed, 2 still toxic in the vault.
    assert sess.vault_green_count("p1") == 2


def test_green_collective_flush_clears_more_per_house() -> None:
    """Two houses flushing together each clear MORE than they would
    solo, because the cheaper later slots get spread between them."""
    sess = _fresh()
    for seat in ("p1", "p2"):
        _stamp_red(sess, seat, [(f"{seat}-fuel", 200)])
        _stamp_green(sess, seat, [f"{seat}-g{i}" for i in range(4)])
    OrbitResolver().run(
        sess,
        {
            "p1": [SolarJettisonBid(green_parcels=4, red_fuel=120)],
            "p2": [SolarJettisonBid(green_parcels=4, red_fuel=120)],
        },
    )
    green = sess.catapult_history[-1]["jettison"]
    # p1 (rank 0) takes slots 0,2,4,6 → 50,40,30,20: 120 buys 3.
    # p2 (rank 1) takes slots 1,3,5,7 → 45,35,25,15: 120 buys 4.
    assert green["seats"]["p1"]["awarded"] == 3
    assert green["seats"]["p2"]["awarded"] == 4
    assert green["slots_used"] == 7
    # Both beat the solo result (a lone 120 only clears 2).
    assert sess.vault_green_count("p1") == 1
    assert sess.vault_green_count("p2") == 0


def test_green_endgame_penalty_bleeds_into_score() -> None:
    """Undisposed vault green is a standing −100 each in ``score_for``;
    flushing it removes the liability."""
    sess = _fresh()
    _stamp_green(sess, "p1", ["g0", "g1"])
    assert sess.score_for("p1") == -2 * GREEN_ENDGAME_PENALTY == -200

    # Ship a mass-200 parcel (+285) and the net reflects both.
    _stamp_red(sess, "p1", [("m", 200)])
    OrbitResolver().run(sess, {"p1": [_ship(("m", 50))], "p2": []})
    assert sess.score_for("p1") == 285 - 200


# ── Cumulative scoreboard + hydrate round-trip ──────────────────────


def test_cumulative_shipped_score_bumps_per_settlement() -> None:
    """The session scoreboard counter advances each settlement and stays
    in sync with ``score_for`` (no green held)."""
    sess = _fresh()
    _stamp_red(sess, "p1", [("a", 200), ("b", 180)])
    OrbitResolver().run(sess, {"p1": [_ship(("a", 30), ("b", 30))], "p2": []})
    first = sess.catapult_history[-1]["catapult"]["seats"]["p1"]["score_shipped"]
    assert first > 0
    assert sess.cumulative_shipped_score["p1"] == first

    sess.phase = Phase.ORBIT
    sess.pending_orbit_actions = {p: None for p in sess.players}
    sess.credits = {p: 1000 for p in sess.players}
    sess._orbit_credits_awarded_day = int(sess.day)  # type: ignore[attr-defined]
    _stamp_red(sess, "p1", [("c", 120)])
    OrbitResolver().run(sess, {"p1": [_ship(("c", 40))], "p2": []})
    second = sess.catapult_history[-1]["catapult"]["seats"]["p1"]["score_shipped"]
    assert sess.cumulative_shipped_score["p1"] == first + second
    assert sess.score_for("p1") == int(round(first + second))


def test_cumulative_shipped_score_survives_hydrate_roundtrip() -> None:
    """The cumulative field round-trips through ``to_dict`` →
    ``from_dict``."""
    sess = _fresh()
    _stamp_red(sess, "p1", [("a", 200)])
    OrbitResolver().run(sess, {"p1": [_ship(("a", 60))], "p2": []})
    expected = sess.cumulative_shipped_score["p1"]
    assert expected > 0
    revived = GameSession.from_dict(sess.to_dict())
    assert revived.cumulative_shipped_score["p1"] == expected


# ── v0.9.x SHIPPED public record (uncapped + score + lineage) ───────


def test_shipped_row_carries_score_and_multiplier() -> None:
    """The stored shipped row records the yielded score + tier
    multiplier (not just the recompute inputs) for the public ledger."""
    sess = _fresh()
    _stamp_red(sess, "p1", [("a", 200)])
    OrbitResolver().run(sess, {"p1": [_ship(("a", 50))], "p2": []})
    row = sess.shipped_squares["p1"][0]
    assert row["transit_charge"] == 10
    assert row["effective_purity"] == 190
    assert row["tier_multiplier"] == RED_QUALITY_MULTIPLIER["mass"]
    assert round(row["score"]) == 285
    assert row["catapult_shipped"] is True


def test_shipped_is_uncapped_no_overflow_drop() -> None:
    """SHIPPED is an unbounded record: a parcel ships even when the
    bay already holds far more than the old 25-slot cap, and no
    ``overflow_bay_full`` disposition is produced."""
    sess = _fresh()
    # Pre-fill the bay well past the legacy cap.
    sess.shipped_squares["p1"] = [
        {"square_id": f"old-{i}", "effective_purity": 10,
         "score_tier": "trace", "transit_charge": 0}
        for i in range(40)
    ]
    _stamp_red(sess, "p1", [("new", 200)])
    OrbitResolver().run(sess, {"p1": [_ship(("new", 50))], "p2": []})
    assert len(sess.shipped_squares["p1"]) == 41
    cat = sess.catapult_history[-1]["catapult"]
    dispositions = [
        sa.get("disposition") for sa in cat["slot_assignments"]
    ]
    assert "overflow_bay_full" not in dispositions
    assert sess.shipped_squares["p1"][-1]["square_id"] == "new"


def test_refined_parcel_lineage_survives_shipping() -> None:
    """A refined parcel keeps its ``refined_from`` lineage when shipped,
    so the public ledger can show what it was refined from."""
    sess = _fresh()
    sess.hoard_squares["p1"] = [{
        "square_id": "refined-mass-x-0001",
        "site_id": "refined-mass-x-0001",
        "tile_at_harvest": int(Tile.RED),
        "purity_at_harvest": 200,
        "origin_purity": 200,
        "origin_tile": int(Tile.RED),
        "lineage": "refined",
        "refined_from": ["seed-a", "seed-b", "seed-c"],
    }]
    OrbitResolver().run(
        sess, {"p1": [_ship(("refined-mass-x-0001", 50))], "p2": []},
    )
    row = sess.shipped_squares["p1"][0]
    assert row["lineage"] == "refined"
    assert row["refined_from"] == ["seed-a", "seed-b", "seed-c"]


def test_shipped_record_is_all_seat_and_public() -> None:
    """The agent view's ``shipped_record`` aggregates EVERY seat's
    shipments, owner-tagged, with full detail incl. ids/lineage."""
    from sea_of_colours.snowpark.view import build_agent_view

    sess = _fresh()
    _stamp_red(sess, "p1", [("p1-a", 200)])
    _stamp_red(sess, "p2", [("p2-a", 120)])
    OrbitResolver().run(
        sess,
        {"p1": [_ship(("p1-a", 80))], "p2": [_ship(("p2-a", 40))]},
    )
    view = build_agent_view(sess, "p1", [])
    record = view["shipped_record"]
    owners = {r["owner"] for r in record}
    assert owners == {"p1", "p2"}
    # Full detail is public — a rival's parcel id is present (no masking).
    rival = [r for r in record if r["owner"] == "p2"][0]
    assert rival["square_id"] == "p2-a"
