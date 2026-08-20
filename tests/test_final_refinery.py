"""v1.x — terminal "Final Refinery" run (RULEBOOK §4.3.1).

On the final settlement orbit a seat may:
  * cascade its whole RED vault up the tier ladder in one turn (trace →
    vein → mass), limited only by BLUE — no 5-parcel / 3-action caps;
  * ship the freshly-refined parcels the SAME turn via an AUTO bid
    (their ids don't exist until settlement, so explicit id bids can't
    name them).

Everything here is gated to ``final_orbit``; normal orbits keep the
capped, next-turn refine and reject the auto / cascade shapes.
"""

from __future__ import annotations

import os

os.environ.setdefault("SOC_BACKEND", "memory")

from sea_of_colours.generator import Tile
from sea_of_colours.game.orbit_resolver import OrbitResolver
from sea_of_colours.game.policy import (
    RefineCascadeAction,
    ShipCatapultBid,
    parse_orbit_actions,
)
from sea_of_colours.game.session import GameSession, Phase


def _red(sid: str, purity: int, owner: str = "p1") -> dict:
    return {
        "square_id": sid,
        "site_id": sid,
        "owner": owner,
        "tile_at_harvest": int(Tile.RED),
        "origin_tile": int(Tile.RED),
        "purity_at_harvest": int(purity),
        "origin_purity": int(purity),
    }


def _tiers(parcels) -> list:
    return [GameSession._tier_for_purity(GameSession._parcel_purity(p)) for p in parcels]


# ── parsing ──────────────────────────────────────────────────────────
def test_parse_refine_cascade_and_auto_ship() -> None:
    acts, errs = parse_orbit_actions(
        [
            {"a": "refine_cascade", "target_tier": "mass"},
            {"a": "ship_catapult", "auto": True, "credits": 12, "count": 3},
        ]
    )
    assert not errs
    assert isinstance(acts[0], RefineCascadeAction) and acts[0].target_tier == "mass"
    assert isinstance(acts[1], ShipCatapultBid)
    assert acts[1].auto and acts[1].auto_credits == 12 and acts[1].auto_count == 3


def test_parse_orbit_actions_cap_override() -> None:
    raw = [{"a": "refine", "source_tier": "trace"}] * 6
    # Default keeps the 3-slot cap; final orbit passes max_actions=None.
    assert len(parse_orbit_actions(raw)[0]) == 3
    assert len(parse_orbit_actions(raw, max_actions=None)[0]) == 6


# ── uncapped refine ──────────────────────────────────────────────────
def test_refine_uncapped_lifts_five_slot_limit() -> None:
    sess = GameSession.new(20, 14, seed=101)
    sess.blue_bank["p1"] = 100000
    ids = [f"t{i}" for i in range(8)]
    sess.hoard_squares["p1"] = [_red(i, 50) for i in ids]

    # Capped path rejects 8 inputs.
    ok, _ = sess.apply_refine("p1", ids)
    assert not ok
    # Uncapped path folds all 8.
    ok, _ = sess.apply_refine("p1", ids, uncapped=True)
    assert ok


# ── cascade concentrates + conserves purity ──────────────────────────
def test_refine_cascade_folds_trace_into_mass_and_conserves_purity() -> None:
    sess = GameSession.new(20, 14, seed=102)
    sess.blue_bank["p1"] = 100000
    sess.hoard_squares["p1"] = [_red(f"t{i}", 50) for i in range(8)]  # Σ400
    before = sum(GameSession._parcel_purity(p) for p in sess.hoard_squares["p1"])

    ok, _ = sess.apply_refine_cascade("p1", "mass")
    assert ok

    after_parcels = sess.hoard_squares["p1"]
    after = sum(GameSession._parcel_purity(p) for p in after_parcels)
    assert after == before  # purity conserved exactly
    assert "mass" in _tiers(after_parcels)  # concentrated up to mass
    assert len(after_parcels) < 8  # fewer, higher-tier parcels


def test_refine_cascade_respects_target_vein() -> None:
    sess = GameSession.new(20, 14, seed=103)
    sess.blue_bank["p1"] = 100000
    sess.hoard_squares["p1"] = [_red(f"t{i}", 50) for i in range(8)]
    ok, _ = sess.apply_refine_cascade("p1", "vein")
    assert ok
    # Stops at vein — nothing promoted to mass.
    assert "mass" not in _tiers(sess.hoard_squares["p1"])


def test_refine_cascade_needs_blue() -> None:
    sess = GameSession.new(20, 14, seed=104)
    sess.blue_bank["p1"] = 0
    sess.hoard_squares["p1"] = [_red(f"t{i}", 50) for i in range(4)]
    ok, _ = sess.apply_refine_cascade("p1", "mass")
    assert not ok  # no blue → nothing folds


# ── full final orbit: cascade THEN auto-ship in one turn ─────────────
def test_final_orbit_cascade_then_auto_ship_ships_refined_mass() -> None:
    sess = GameSession.new(20, 14, seed=105)
    sess.phase = Phase.ORBIT
    sess.final_orbit = True
    sess.blue_bank["p1"] = 100000
    sess.credits["p1"] = 100000
    sess.hoard_squares["p1"] = [_red(f"t{i}", 50) for i in range(8)]

    ok, _ = sess.stash_orbit_actions(
        "p1",
        [
            {"a": "refine_cascade", "target_tier": "mass"},
            {"a": "ship_catapult", "auto": True, "credits": 25},
        ],
    )
    assert ok
    sess.stash_orbit_actions("p2", [])
    assert sess.maybe_resolve_orbit_if_ready()

    shipped = sess.shipped_squares.get("p1", [])
    assert shipped, "auto ship should have shipped the refined parcels"
    assert any(r.get("score_tier") == "mass" for r in shipped)
    # Nothing high-value left stranded in the vault (all shipped).
    assert sess.score_for("p1") > 0


def test_final_orbit_more_than_three_actions_allowed() -> None:
    sess = GameSession.new(20, 14, seed=106)
    sess.phase = Phase.ORBIT
    sess.final_orbit = True
    sess.blue_bank["p1"] = 100000
    sess.credits["p1"] = 100000
    sess.hoard_squares["p1"] = [_red(f"t{i}", 50) for i in range(10)]
    # 4 actions (> MAX_ORBIT_ACTIONS=3) all survive on the final orbit.
    ok, _ = sess.stash_orbit_actions(
        "p1",
        [
            {"a": "refine", "source_tier": "trace"},
            {"a": "refine", "source_tier": "trace"},
            {"a": "refine_cascade", "target_tier": "mass"},
            {"a": "ship_catapult", "auto": True, "credits": 25},
        ],
    )
    assert ok
    assert len(sess.pending_orbit_actions["p1"]) == 4


# ── gating: cascade / auto-ship are terminal-only ────────────────────
def test_cascade_and_auto_ship_dropped_off_final_orbit() -> None:
    sess = GameSession.new(20, 14, seed=107)
    sess.phase = Phase.ORBIT
    sess.final_orbit = False
    sess.blue_bank["p1"] = 100000
    sess.credits["p1"] = 100000
    sess.hoard_squares["p1"] = [_red(f"t{i}", 50) for i in range(8)]

    # Parse accepts them, but the resolver refuses off the final orbit.
    sess.pending_orbit_actions = {
        "p1": [
            RefineCascadeAction(target_tier="mass"),
            ShipCatapultBid(auto=True, auto_credits=25),
        ],
        "p2": [],
    }
    OrbitResolver().run(sess, dict(sess.pending_orbit_actions))
    # Cascade refused → vault untouched (still 8 trace); nothing shipped.
    assert len(sess.hoard_squares["p1"]) == 8
    assert not sess.shipped_squares.get("p1")


# ── heuristic agent emits the terminal refinery line ─────────────────
def test_heuristic_plans_final_refinery() -> None:
    from sea_of_colours.agent.heuristic_agent import plan_orbit_actions

    view = {
        "orbit": {
            "final_orbit": True,
            "credits": 400,
            "blue_purity_total": 500,
            "actions_max": 20,
            "hoard_parcels": [
                {"colour": "RED", "purity": 40, "square_id": f"t{i}"}
                for i in range(6)
            ]
            + [{"colour": "GREEN", "purity": 60, "square_id": "g1"}],
        }
    }
    actions, _why = plan_orbit_actions(view)
    tags = [a["a"] for a in actions]
    assert "refine_cascade" in tags  # spend blue to fold trace up
    ship = next(a for a in actions if a["a"] == "ship_catapult")
    assert ship.get("auto") is True  # auto-ship the refined output
    assert "solar_jettison" in tags  # flush the green
