"""Orbit-phase settlement (v0.9.x, RULEBOOK §4).

Each game-day starts in :data:`Phase.ORBIT`. Each seat may queue up
to :data:`MAX_ORBIT_ACTIONS` actions (build / repair / refine /
ship_catapult / green flush). Once every seat locks, this resolver:

1. Awards Orbit credits (idempotent per-day).
2. Applies each seat's actions in **declaration order** under the
   LOCKING model (RULEBOOK §4.3): credits/blue are debited and
   parcels reserved the instant an action is programmed, so a later
   action can't reuse a resource an earlier one committed and a
   same-turn refine output can't be shipped/re-refined (no cascade).
   This pass returns each seat's locked RED-catapult bids and
   green-flush commitment.
3. Settles the **RED shipping catapult** (RULEBOOK §4.4): every
   per-parcel CREDIT bid is pooled into one global queue ranked
   credits-DESC (tiebreaks: total credits committed, parcel count,
   purity), the top 20 win slots in 4 rows of 5, and each row applies
   a flat RED-purity TRANSIT charge (:data:`CATAPULT_ROW_TRANSIT`) out
   of the parcel's own purity. Score = max(0, purity - transit) x
   tier-mult(ORIGINAL purity). Bids that miss all 20 slots stay in
   the hoard and forfeit their credits.
4. Settles the **GREEN disposal catapult** (RULEBOOK §4.5): 12 shared
   slots dealt round-robin by RED-fuel offer; per-slot cost diminishes
   by global slot index (cheaper when many houses flush together).
   Committed RED is forfeit. Undisposed vault green bleeds score at
   season end (:data:`GREEN_ENDGAME_PENALTY`).
5. Transitions ``phase`` to :data:`Phase.PLANNING` so the night
   submission window opens.

The resolver writes structured log rows (``[orbit] ...``) and
appends one ``catapult_history`` entry per call so the agent view
can surface ``last_catapult_results`` next turn.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple, TYPE_CHECKING

from sea_of_colours.game.policy import (
    BuildChaffAction,
    BuildEmpAction,
    BuildHarvesterAction,
    BuildMineAction,
    BuildProbeAction,
    MAX_ORBIT_ACTIONS,
    OrbitAction,
    OrbitWasteAction,
    RefineAction,
    RefineCascadeAction,
    RepairAction,
    ShipCatapultBid,
    SolarJettisonBid,
)

if TYPE_CHECKING:
    from sea_of_colours.game.session import GameSession, PlayerId


# v0.9.6 — N-seat aware. The resolver derives iteration order from
# ``sess.players`` on every ``run`` so 3- and 4-seat sessions resolve
# the same way 2-seat ones do. The constant stays as a legacy default
# for any caller that bypasses ``run`` (unit tests poking helpers
# directly).
PLAYERS_ORDER: Tuple[str, ...] = ("p1", "p2")


def _parcel_key(parcel: Mapping[str, Any]) -> str:
    return str(parcel.get("square_id") or parcel.get("site_id") or "")


def _parcel_purity(parcel: Mapping[str, Any]) -> int:
    raw = (
        parcel.get("purity_at_harvest")
        if isinstance(parcel.get("purity_at_harvest"), (int, float))
        else parcel.get("origin_purity")
        if isinstance(parcel.get("origin_purity"), (int, float))
        else parcel.get("purity")
    )
    try:
        v = int(raw) if raw is not None else 0
    except (TypeError, ValueError):
        v = 0
    return max(0, min(255, v))


def _parcel_tile(parcel: Mapping[str, Any]) -> int:
    raw = parcel.get("tile_at_harvest")
    if raw is None:
        raw = parcel.get("origin_tile")
    try:
        return int(raw) if raw is not None else 0
    except (TypeError, ValueError):
        return 0


def _is_red(parcel: Mapping[str, Any]) -> bool:
    # RED = Tile.RED = 2. Avoid importing Tile to keep this module
    # cycle-light.
    return _parcel_tile(parcel) == 2


def _is_green(parcel: Mapping[str, Any]) -> bool:
    # GREEN = Tile.GREEN = 1.
    return _parcel_tile(parcel) == 1


def _tier_label(p: int) -> str:
    if p <= 50:
        return "trace"
    if p <= 150:
        return "vein"
    if p <= 254:
        return "mass"
    return "pure"


def _summarize_inventory(parcels: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """v0.9.1 — public summary of a catapult inventory.

    Used by the agent view + replay catapult modal so the public
    learns WHAT shipped (counts, tiers, total purity) without
    leaking parcel provenance / lineage / origin coords. Returns
    a stable shape even for empty inventories so the renderer can
    branch on ``count == 0`` to show the "empty" marker.
    """
    parcels = list(parcels or [])
    color_counts = {"red": 0, "green": 0, "blue": 0}
    tier_counts = {"trace": 0, "vein": 0, "mass": 0, "pure": 0}
    total_purity = 0
    for p in parcels:
        tile = _parcel_tile(p)
        purity = _parcel_purity(p)
        total_purity += purity
        if tile == 2:
            color_counts["red"] += 1
        elif tile == 1:
            color_counts["green"] += 1
        elif tile == 3:
            color_counts["blue"] += 1
        tier_counts[_tier_label(purity)] += 1
    return {
        "count": len(parcels),
        "total_purity": int(total_purity),
        "color_counts": color_counts,
        "tier_counts": tier_counts,
    }


class OrbitResolver:
    """Pure data-mutation engine — owns no state of its own."""

    def run(
        self,
        sess: "GameSession",
        queues: Mapping[str, Sequence[OrbitAction]],
    ) -> None:
        from sea_of_colours.game.session import (
            Phase,
            cast_player,
        )

        sess.log_info(f"[orbit] day {sess.day} — orbit settlement begins")

        sess.award_orbit_credits()

        # v0.9.6 — derive seat list from the session so N-seat games
        # are first-class. The tuple is captured once at the top so
        # every helper sees a stable iteration order.
        seats: Tuple[str, ...] = tuple(sess.players)

        # 1) Per-seat action application in DECLARED ORDER, with the
        #    v0.9.x locking model: credits/blue are debited and parcels
        #    reserved the instant an action is programmed, so a later
        #    action can't reuse a resource an earlier one already
        #    committed (RULEBOOK §4.3). The pass returns each seat's
        #    locked RED-catapult bids and green-flush commitment for the
        #    global drafts below.
        ship_commitments: Dict[str, List[Dict[str, Any]]] = {}
        green_commitments: Dict[str, Dict[str, Any]] = {}
        for p in seats:
            actions = list(queues.get(p, []) or [])
            sc, gc = self._apply_seat_actions(
                sess, cast_player(p, allowed=seats), actions,
            )
            ship_commitments[p] = sc
            green_commitments[p] = gc

        # 2) RED shipping catapult: global per-parcel credit-bid draft
        #    over 20 slots with per-row transit charges (RULEBOOK §4.4).
        catapult_result = self._settle_catapult(
            sess, ship_commitments, seats=seats,
        )

        # 3) GREEN disposal catapult: 12 shared slots dealt round-robin
        #    by offer, diminishing RED-fuel cost (RULEBOOK §4.5).
        jett_result = self._settle_green(
            sess, green_commitments, seats=seats,
        )

        # v0.9.1 — stamp public inventory summaries onto each section
        # (per-seat AND per-catapult totals) so the replay modal can
        # render "Catapult this day: 5 parcels Σ430p · trace 2 · vein 3"
        # without exposing private provenance keys.
        self._stamp_public_inventories(
            catapult_result, parcels_key="shipped_parcels",
        )
        self._stamp_public_inventories(
            jett_result, parcels_key="jettisoned_parcels",
        )

        sess.catapult_history.append({
            "day": int(sess.day),
            "catapult": catapult_result,
            "jettison": jett_result,
        })

        # v0.9.11 — stamp the post-settlement ("post"-orbital) station
        # readings for every seat, keyed by the settlement day so the
        # Post-Orbital Briefing report (and replay scrubber) can show
        # how each platform looked after shipping/jettison resolved.
        try:
            sess.station_obs_by_day.setdefault(str(int(sess.day)), {})[
                "post"
            ] = sess.station_observation_snapshot()
        except Exception:  # pragma: no cover — never block settlement
            pass

        # 4) Flip phase + clear locks. The final settlement orbit ends
        #    the season outright (RULEBOOK §4); every other orbit hands
        #    off to the night planning window.
        sess.pending_orbit_actions = {p: None for p in seats}
        if getattr(sess, "final_orbit", False):
            sess.pending_policies = {p: None for p in seats}
            sess.phase = Phase.SEASON_COMPLETE
            sess.log_info(
                f"[seasonComplete] {sess.season_name or sess.session_id} — "
                f"final settlement orbit resolved; season over."
            )
        else:
            sess.phase = Phase.PLANNING
            sess.log_info(
                f"[orbit] day {sess.day} — settlement complete; planning opens"
            )

    # ── Per-seat action application ──────────────────────────────────

    def _apply_seat_actions(
        self,
        sess: "GameSession",
        player: "PlayerId",
        actions: Sequence[OrbitAction],
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Apply one seat's queued actions in DECLARED ORDER under the
        v0.9.x locking model (RULEBOOK §4.3).

        Returns ``(ship_commitments, green_commitment)``:

        * ``ship_commitments`` — list of ``{"parcel_id", "parcel",
          "credits", "purity"}`` for each RED parcel whose credit bid
          was locked (credits already debited / forfeit).
        * ``green_commitment`` — ``{"budget", "green_parcels"}`` where
          ``budget`` is the RED purity already burned (forfeit) and
          ``green_parcels`` the GREEN parcels reserved to flush.

        Locking rules:

        * ``eligible`` is the set of parcel ids present in the vault at
          the START of this seat's pass — outputs minted by a
          same-turn refine are NOT eligible to ship or re-refine
          (no cascade).
        * ``committed`` tracks parcels reserved by a ship bid (still in
          the hoard until catapult settlement) and parcels consumed by
          refine / burned for green fuel (detected via hoard diff).
        """
        ship_commitments: List[Dict[str, Any]] = []
        green_commitment: Dict[str, Any] = {"budget": 0, "green_parcels": []}

        eligible: Set[str] = {
            _parcel_key(p) for p in sess.hoard_squares.get(player, [])
        }
        committed: Set[str] = set()

        def _refresh_consumed() -> None:
            # Any originally-eligible parcel that has vanished from the
            # hoard (refine input, blue/red burned) is now spent — lock
            # it so a later action can't reference it.
            live = {_parcel_key(p) for p in sess.hoard_squares.get(player, [])}
            committed.update(eligible - live)

        # v1.x — the terminal settlement orbit runs an uncapped "refinery
        # run": no 3-slot action cap, refine outputs cascade same-turn
        # (eligible is re-read live below), and refine folds the whole tier
        # (uncapped). RULEBOOK §4.3.1.
        final_refinery = bool(getattr(sess, "final_orbit", False))

        applied = 0
        for act in actions:
            if not final_refinery and applied >= MAX_ORBIT_ACTIONS:
                sess.log_error(
                    f"[orbit] {player}: action over {MAX_ORBIT_ACTIONS}-slot cap "
                    f"({act.tag}) — dropped"
                )
                continue

            if isinstance(act, OrbitWasteAction):
                sess.log_error(
                    f"[orbit] {player}: invalid action — {act.reason}"
                )
                continue

            if final_refinery:
                # Terminal pass: every parcel currently in the vault is
                # eligible (refined outputs included) so refine/ship can
                # cascade within the same turn. ``committed`` still fences
                # off anything a ship / green bid already reserved.
                eligible = {
                    _parcel_key(p) for p in sess.hoard_squares.get(player, [])
                }
            else:
                _refresh_consumed()

            if isinstance(act, ShipCatapultBid):
                self._commit_ship_bid(
                    sess, player, act, eligible, committed, ship_commitments,
                )
                applied += 1
                continue
            if isinstance(act, SolarJettisonBid):
                self._commit_green_flush(
                    sess, player, act, committed, green_commitment,
                )
                applied += 1
                continue

            if isinstance(act, BuildHarvesterAction):
                ok, msg = sess.apply_build_harvester(player)
            elif isinstance(act, BuildProbeAction):
                ok, msg = sess.apply_build_probe(
                    player, count=int(getattr(act, "count", 1) or 1),
                )
            # v0.9.3 — three new build actions for the interdiction
            # weapons (RULEBOOK §5.0). Each pays blue + credits NOW
            # and pushes the count into ``weapon_stock``; the night-
            # phase launch moves drain that stock instead of paying
            # at launch time.
            elif isinstance(act, BuildEmpAction):
                ok, msg = sess.apply_build_emp(
                    player, count=int(getattr(act, "count", 1) or 1),
                )
            elif isinstance(act, BuildMineAction):
                ok, msg = sess.apply_build_mine(
                    player, count=int(getattr(act, "count", 1) or 1),
                )
            elif isinstance(act, BuildChaffAction):
                ok, msg = sess.apply_build_chaff(
                    player, count=int(getattr(act, "count", 1) or 1),
                )
            elif isinstance(act, RepairAction):
                ok, msg = sess.apply_repair(player, act.unit)
            elif isinstance(act, RefineAction):
                # Normal orbit: no same-turn cascade — refine may only
                # consume parcels in the vault at turn start that aren't
                # already locked. Final orbit: ``eligible`` was re-read live
                # above (cascade allowed) and the caps are lifted.
                avail = eligible - committed
                if act.source_tier:
                    ok, msg = sess.apply_refine_all(
                        player, act.source_tier, eligible_ids=avail,
                        uncapped=final_refinery,
                    )
                else:
                    ok, msg = sess.apply_refine(
                        player, act.inputs, eligible_ids=avail,
                        uncapped=final_refinery,
                    )
            elif isinstance(act, RefineCascadeAction):
                # One-click terminal refinery run — final orbit only.
                if not final_refinery:
                    sess.log_error(
                        f"[orbit] {player}: refine_cascade is only valid on "
                        f"the final settlement orbit — dropped"
                    )
                    applied += 1
                    continue
                ok, msg = sess.apply_refine_cascade(
                    player, act.target_tier, blocked_ids=committed,
                )
            else:
                sess.log_error(
                    f"[orbit] {player}: unhandled action type {act.tag}"
                )
                applied += 1
                continue

            if ok:
                sess.log_info(f"[orbit] {msg}")
            else:
                sess.log_error(f"[orbit] {msg}")
            applied += 1

        return ship_commitments, green_commitment

    # ── Per-parcel bid / green-flush locking ─────────────────────────

    def _commit_ship_bid(
        self,
        sess: "GameSession",
        player: "PlayerId",
        bid: "ShipCatapultBid",
        eligible: Set[str],
        committed: Set[str],
        ship_commitments: List[Dict[str, Any]],
    ) -> None:
        """Validate + lock one RED-catapult bid (credits forfeit now).

        v1.x — an ``auto`` bid (final orbit only) has no explicit ids: it
        bids ``auto_credits`` on the seat's best ``auto_count`` (0 = all)
        RED parcels by tier-weighted value, chosen from the CURRENT
        (post-refine) hoard so freshly-refined parcels can ship.
        """
        hoard = sess.hoard_squares.get(player, [])
        by_id = {_parcel_key(p): p for p in hoard}

        if getattr(bid, "auto", False):
            if not bool(getattr(sess, "final_orbit", False)):
                sess.log_error(
                    f"[orbit] {player}: auto ship bid is only valid on the "
                    f"final settlement orbit — dropped"
                )
                return
            from sea_of_colours.game.session import RED_QUALITY_MULTIPLIER

            cands: List[Tuple[float, str]] = []
            for p in hoard:
                pid = _parcel_key(p)
                if not pid or pid in committed or pid not in eligible:
                    continue
                if not _is_red(p):
                    continue
                pur = _parcel_purity(p)
                tier = sess._tier_for_purity(pur)
                cands.append((pur * RED_QUALITY_MULTIPLIER.get(tier, 1.0), pid))
            cands.sort(key=lambda t: -t[0])
            n = (
                bid.auto_count
                if bid.auto_count and bid.auto_count > 0
                else len(cands)
            )
            bids_iter: List[Tuple[str, int]] = [
                (pid, int(bid.auto_credits)) for _, pid in cands[:n]
            ]
        else:
            bids_iter = [(str(pid), max(0, int(cr))) for pid, cr in bid.bids]

        for pid, credits in bids_iter:
            pid = str(pid)
            credits = max(0, int(credits))
            if pid not in eligible:
                sess.log_error(
                    f"[orbit] {player}: ship bid on {pid} rejected — "
                    f"not in vault at turn start (no same-turn cascade)"
                )
                continue
            if pid in committed:
                sess.log_error(
                    f"[orbit] {player}: ship bid on {pid} rejected — "
                    f"parcel already locked this turn"
                )
                continue
            parcel = by_id.get(pid)
            if parcel is None:
                sess.log_error(
                    f"[orbit] {player}: ship bid on {pid} rejected — "
                    f"parcel no longer in hoard"
                )
                continue
            if not _is_red(parcel):
                sess.log_error(
                    f"[orbit] {player}: ship bid on {pid} rejected — "
                    f"only RED parcels score on the catapult"
                )
                continue
            if not sess.spend_credits(player, credits):
                sess.log_error(
                    f"[orbit] {player}: ship bid on {pid} rejected — "
                    f"insufficient credits for {credits}cr bid "
                    f"(have {sess.credits.get(player, 0)}cr)"
                )
                continue
            committed.add(pid)
            ship_commitments.append({
                "parcel_id": pid,
                "parcel": dict(parcel),
                "credits": int(credits),
                "purity": _parcel_purity(parcel),
            })
            sess.log_info(
                f"[orbit] {player}: locked ship bid on {pid} "
                f"@ {credits}cr (purity {_parcel_purity(parcel)})"
            )

    def _commit_green_flush(
        self,
        sess: "GameSession",
        player: "PlayerId",
        bid: "SolarJettisonBid",
        committed: Set[str],
        green_commitment: Dict[str, Any],
    ) -> None:
        """Lock a green-flush: burn the committed RED fuel (forfeit) and
        reserve up to ``green_parcels`` GREEN parcels to dispose of."""
        red_fuel = max(0, int(bid.red_fuel))
        want_green = max(0, int(bid.green_parcels))

        # Reserve GREEN parcels (any order — green is uniformly toxic).
        already = {_parcel_key(p) for p in green_commitment["green_parcels"]}
        greens = [
            p for p in sess.hoard_squares.get(player, [])
            if _is_green(p)
            and _parcel_key(p) not in committed
            and _parcel_key(p) not in already
        ]
        picked = greens[:want_green]
        for g in picked:
            committed.add(_parcel_key(g))
            green_commitment["green_parcels"].append(dict(g))

        # Burn the RED fuel NOW (forfeit), skipping any parcel already
        # locked for shipping. Returns the actual purity burned.
        burned = self._burn_fuel_avoiding(sess, player, red_fuel, set(committed))
        green_commitment["budget"] = int(green_commitment.get("budget", 0)) + int(burned)

        sess.log_info(
            f"[orbit] {player}: green flush committed — burned {burned} RED "
            f"fuel, reserved {len(picked)} green parcel(s)"
        )

    @staticmethod
    def _stamp_public_inventories(
        section: Mapping[str, Any], parcels_key: str,
    ) -> None:
        """Inject a public ``inventory`` summary into a settlement
        section (in-place).

        Per-seat: each ``seats[<seat>]`` entry gains
        ``inventory`` derived from its ``parcels_key`` list (empty if
        the seat didn't ship / jettison anything). Section root also
        gains an aggregate ``inventory`` summing across both seats.
        """
        if not isinstance(section, dict):
            return
        all_parcels: List[Mapping[str, Any]] = []
        seats = section.get("seats")
        if isinstance(seats, dict):
            for seat, seat_block in seats.items():
                if not isinstance(seat_block, dict):
                    continue
                parcels = seat_block.get(parcels_key) or []
                seat_block["inventory"] = _summarize_inventory(parcels)
                all_parcels.extend(parcels)
        section["inventory"] = _summarize_inventory(all_parcels)

    @staticmethod
    def _last_of(
        actions: Sequence[OrbitAction], cls: type,
    ) -> Optional[Any]:
        chosen: Optional[Any] = None
        for a in actions:
            if isinstance(a, cls):
                chosen = a
        return chosen

    # ── Shipping catapult (v0.9.6, RULEBOOK §4.4) ────────────────────

    def _settle_catapult(
        self,
        sess: "GameSession",
        commitments: Mapping[str, List[Dict[str, Any]]],
        *,
        seats: Optional[Tuple[str, ...]] = None,
    ) -> Dict[str, Any]:
        """v0.9.x RED shipping catapult — per-parcel credit-bid draft.

        ``commitments[seat]`` is the list of locked bids produced by
        :meth:`_apply_seat_actions` (credits already debited/forfeit),
        each ``{"parcel_id", "parcel", "credits", "purity"}``.

        1. Pool every seat's per-parcel bid into one global queue.
        2. Rank DESC by credit bid; ties break on (a) the seat's TOTAL
           credits committed, (b) the seat's parcel count, (c) parcel
           purity, then canonical seat order for determinism.
        3. The top 20 bids win slots in row-major order (4 rows x 5).
           Each row applies a flat RED-purity TRANSIT CHARGE
           (:data:`CATAPULT_ROW_TRANSIT`) out of the parcel's own
           purity.
        4. score = max(0, purity - transit) x tier-mult(ORIGINAL
           purity). A row whose charge >= purity scores 0, no extra
           charge.
        5. Winners move to ``shipped_squares`` (stamped
           ``effective_purity`` + ``score_tier``); bids that miss all
           20 slots stay in the hoard and forfeit their credits.
        """
        from sea_of_colours.game.session import (
            CATAPULT_ROW_COUNT,
            CATAPULT_ROW_TRANSIT,
            CATAPULT_SLOTS_PER_ROW,
            RED_QUALITY_MULTIPLIER,
        )

        def _tier_of(purity: int) -> str:
            p = max(0, min(255, int(purity)))
            if p <= 0:
                return "empty"
            if p <= 50:
                return "trace"
            if p <= 150:
                return "vein"
            if p <= 254:
                return "mass"
            return "pure"

        seat_list: Tuple[str, ...] = (
            seats if seats is not None else tuple(sess.players)
        )
        seat_rank: Dict[str, int] = {s: i for i, s in enumerate(seat_list)}

        rows = int(CATAPULT_ROW_COUNT)
        slots_per_row = int(CATAPULT_SLOTS_PER_ROW)
        total_slots = rows * slots_per_row
        transit = tuple(int(t) for t in CATAPULT_ROW_TRANSIT)

        def _transit_for(row_idx: int) -> int:
            return int(transit[row_idx]) if 0 <= row_idx < len(transit) else 0

        # Per-seat aggregates for the tiebreak ladder.
        seat_total_credits: Dict[str, int] = {
            s: sum(int(c["credits"]) for c in commitments.get(s, []))
            for s in seat_list
        }
        seat_total_parcels: Dict[str, int] = {
            s: len(commitments.get(s, [])) for s in seat_list
        }

        out: Dict[str, Any] = {
            "slots_total": total_slots,
            "slots_per_row": slots_per_row,
            "row_count": rows,
            "row_transit": [int(t) for t in transit],
            "rows": [],
            "slots_awarded": 0,
            "seats": {
                p: {
                    "submitted": bool(commitments.get(p)),
                    "awarded": 0,
                    "parcels_offered": seat_total_parcels[p],
                    "credits_committed": seat_total_credits[p],
                    "shipped_parcels": [],
                    "score_shipped": 0.0,
                }
                for p in seat_list
            },
            "overflow": [],
            # v0.9.x flat per-slot ledger for the orbital summary modal:
            #     {"slot", "row", "seat"|None, "credits", "transit_charge",
            #      "purity", "shipped", "parcel"|None, "tier"|None,
            #      "effective_purity"|None, "tier_multiplier"|None,
            #      "score"|None, "disposition"?}
            "slot_assignments": [],
        }

        # Step 1: flatten every locked bid into a global queue.
        entries: List[Dict[str, Any]] = []
        for seat in seat_list:
            for c in commitments.get(seat, []):
                entries.append({
                    "seat": seat,
                    "parcel_id": str(c["parcel_id"]),
                    "parcel": dict(c["parcel"]),
                    "credits": int(c["credits"]),
                    "purity": int(c["purity"]),
                })

        # Step 2: rank. Every comparator DESC except the canonical
        # seat-order stabiliser (ASC) so the draft is deterministic.
        entries.sort(key=lambda e: (
            -e["credits"],
            -seat_total_credits[e["seat"]],
            -seat_total_parcels[e["seat"]],
            -e["purity"],
            seat_rank[e["seat"]],
        ))

        winners = entries[:total_slots]
        losers = entries[total_slots:]

        # Step 3+4: assign winners to slots, apply transit, score.
        per_seat_score: Dict[str, float] = {s: 0.0 for s in seat_list}
        slot_assignments: List[Dict[str, Any]] = []
        for slot_idx, e in enumerate(winners):
            row_idx = slot_idx // slots_per_row
            charge = _transit_for(row_idx)
            seat = e["seat"]
            purity = int(e["purity"])
            effective = max(0, purity - charge)
            origin_tier = _tier_of(purity)
            mult = float(RED_QUALITY_MULTIPLIER.get(origin_tier, 1.0))
            score = float(effective * mult) if effective > 0 else 0.0

            pid = e["parcel_id"]
            hoard = sess.hoard_squares.get(seat, [])
            sess.hoard_squares[seat] = [
                p for p in hoard if _parcel_key(p) != pid
            ]
            shipped_bay = sess.shipped_squares.get(seat, [])
            entry: Dict[str, Any] = {
                "slot": int(slot_idx),
                "row": int(row_idx),
                "seat": str(seat),
                "credits": int(e["credits"]),
                "transit_charge": int(charge),
                "purity": int(purity),
                "shipped": False,
                "parcel": dict(e["parcel"]),
                "tier": origin_tier,
                "effective_purity": int(effective),
                "tier_multiplier": mult,
                "score": float(score),
            }
            # SHIPPED is uncapped (v0.9.x): a permanent public record, so
            # every winning parcel is always recorded — no bay-full drop.
            row = dict(e["parcel"])
            row["effective_purity"] = int(effective)
            row["score_tier"] = origin_tier
            row["transit_charge"] = int(charge)
            row["tier_multiplier"] = mult
            row["score"] = float(score)
            row["catapult_shipped"] = True
            row["shipped_on_day"] = int(getattr(sess, "day", 0))
            sess.shipped_squares[seat] = shipped_bay + [row]
            entry["shipped"] = True
            if effective <= 0:
                entry["disposition"] = "transit_zeroed"
            per_seat_score[seat] += score
            seat_block = out["seats"][seat]
            seat_block["awarded"] = int(seat_block.get("awarded", 0)) + 1
            seat_block["shipped_parcels"].append(dict(row))
            out["slots_awarded"] += 1
            slot_assignments.append(entry)

        # Pad to a full grid so the modal always renders total_slots cells.
        for s in range(len(slot_assignments), total_slots):
            slot_assignments.append({
                "slot": int(s),
                "row": int(s // slots_per_row),
                "seat": None,
                "credits": 0,
                "transit_charge": _transit_for(s // slots_per_row),
                "purity": None,
                "shipped": False,
                "parcel": None,
                "tier": None,
                "effective_purity": None,
                "tier_multiplier": None,
                "score": None,
            })
        out["slot_assignments"] = slot_assignments

        # Per-row breakdown for the replay overlay.
        for r in range(rows):
            out["rows"].append({
                "row": r,
                "transit_charge": _transit_for(r),
                "slot_count": sum(
                    1 for sa in slot_assignments
                    if sa.get("row") == r and sa.get("seat") is not None
                ),
                "seats": {
                    s: sum(
                        1 for sa in slot_assignments
                        if sa.get("row") == r and sa.get("seat") == s
                        and sa.get("shipped")
                    )
                    for s in seat_list
                    if any(
                        sa.get("row") == r and sa.get("seat") == s
                        for sa in slot_assignments
                    )
                },
            })

        # Overflow: bids that missed all 20 slots. Parcel stays in the
        # hoard; the credit bid is already forfeit (debited at lock).
        for e in losers:
            out["overflow"].append({
                "seat": e["seat"],
                "parcel_id": e["parcel_id"],
                "credits": int(e["credits"]),
                "parcel": dict(e["parcel"]),
            })
            sess.log_error(
                f"[orbit] {e['seat']}: ship bid on {e['parcel_id']} missed "
                f"all {total_slots} slots — not shipped, "
                f"{e['credits']}cr forfeit"
            )

        # Finalise per-seat score + cumulative season counter.
        for seat in seat_list:
            out["seats"][seat]["score_shipped"] = float(per_seat_score[seat])
            won = int(out["seats"][seat]["awarded"])
            if won > 0:
                sess.log_info(
                    f"[orbit] {seat}: catapult shipped {won} parcel(s) for "
                    f"{per_seat_score[seat]:.0f} score"
                )

        if not hasattr(sess, "cumulative_shipped_score"):
            sess.cumulative_shipped_score = {}  # type: ignore[attr-defined]
        for seat in seat_list:
            sess.cumulative_shipped_score.setdefault(seat, 0.0)
            sess.cumulative_shipped_score[seat] = float(
                sess.cumulative_shipped_score.get(seat, 0.0)
                + float(per_seat_score[seat])
            )

        return out

    # ── Green disposal catapult (v0.9.x, RULEBOOK §4.5) ──────────────

    def _settle_green(
        self,
        sess: "GameSession",
        commitments: Mapping[str, Dict[str, Any]],
        *,
        seats: Optional[Tuple[str, ...]] = None,
    ) -> Dict[str, Any]:
        """GREEN disposal catapult — 12 shared slots, round-robin draft.

        ``commitments[seat]`` is ``{"budget", "green_parcels"}`` from
        :meth:`_apply_seat_actions`: ``budget`` RED purity already
        burned (forfeit) and the GREEN parcels reserved to flush.

        Houses are ranked by ``budget`` DESC and the 12 slots dealt
        round-robin in that order. Each global slot ``s`` (0-indexed)
        costs ``max(0, GREEN_SLOT_COST_BASE - GREEN_SLOT_COST_STEP*s)``
        RED. A house pays its dealt slots IN ORDER from its budget,
        flushing one green per affordable slot, and STOPS at the first
        slot it can't afford. Because more houses flushing together
        spreads the cheaper later slots around, each house clears more
        green per RED committed. Leftover budget is forfeit.
        """
        from sea_of_colours.game.session import (
            GREEN_CATAPULT_SLOTS,
            GREEN_SLOT_COST_BASE,
            GREEN_SLOT_COST_STEP,
        )

        seat_list: Tuple[str, ...] = (
            seats if seats is not None else tuple(sess.players)
        )
        seat_rank: Dict[str, int] = {s: i for i, s in enumerate(seat_list)}
        total_slots = int(GREEN_CATAPULT_SLOTS)

        def _slot_cost(s: int) -> int:
            return max(
                0,
                int(GREEN_SLOT_COST_BASE) - int(GREEN_SLOT_COST_STEP) * int(s),
            )

        out: Dict[str, Any] = {
            "slots_total": total_slots,
            "slots_used": 0,
            "seats": {
                p: {"submitted": False, "awarded": 0} for p in seat_list
            },
            "slot_assignments": [],
        }

        participants: List[str] = []
        for seat in seat_list:
            c = commitments.get(seat) or {}
            budget = int(c.get("budget", 0) or 0)
            greens = list(c.get("green_parcels") or [])
            out["seats"][seat] = {
                "submitted": bool(greens or budget),
                "awarded": 0,
                "budget": budget,
                "green_committed": len(greens),
                "jettisoned_parcels": [],
                "fuel_spent": 0,
                "fuel_forfeit": budget,
            }
            if budget > 0 and greens:
                participants.append(seat)

        if not participants:
            return out

        participants.sort(key=lambda s: (
            -int(commitments[s].get("budget", 0) or 0), seat_rank[s],
        ))
        n = len(participants)

        # Deal global slots 0..total-1 round-robin: slot s -> rank s % n.
        dealt: Dict[str, List[int]] = {s: [] for s in participants}
        for s in range(total_slots):
            dealt[participants[s % n]].append(s)

        slot_owner: Dict[int, Dict[str, Any]] = {}
        for seat in participants:
            c = commitments[seat]
            budget = int(c.get("budget", 0) or 0)
            greens = list(c.get("green_parcels") or [])
            spent = 0
            flushed: List[Dict[str, Any]] = []
            gi = 0
            for s in dealt[seat]:
                if gi >= len(greens):
                    break
                cost = _slot_cost(s)
                if budget - spent < cost:
                    break
                spent += cost
                parcel = greens[gi]
                gi += 1
                flushed.append(dict(parcel))
                slot_owner[s] = {
                    "seat": seat, "cost": cost, "parcel": dict(parcel),
                }

            if flushed:
                to_drop: Set[str] = {_parcel_key(p) for p in flushed}
                new_hoard: List[Dict[str, Any]] = []
                for p in sess.hoard_squares.get(seat, []):
                    k = _parcel_key(p)
                    if k in to_drop:
                        to_drop.discard(k)
                        continue
                    new_hoard.append(p)
                sess.hoard_squares[seat] = new_hoard

            out["seats"][seat].update({
                "awarded": len(flushed),
                "jettisoned_parcels": flushed,
                "fuel_spent": int(spent),
                "fuel_forfeit": int(budget),
            })
            out["slots_used"] += len(flushed)
            sess.log_info(
                f"[orbit] {seat}: green catapult flushed {len(flushed)} "
                f"parcel(s) for {spent} RED (budget {budget} committed, "
                f"forfeit)"
            )

        for s in range(total_slots):
            owner = slot_owner.get(s)
            out["slot_assignments"].append({
                "slot": int(s),
                "cost": _slot_cost(s),
                "seat": owner["seat"] if owner else None,
                "flushed": bool(owner),
                "parcel": owner["parcel"] if owner else None,
            })

        return out

    # ── Hoard utilities ──────────────────────────────────────────────

    @staticmethod
    def _available_red_purity(
        sess: "GameSession", seat: str,
    ) -> int:
        """Sum the RED-tile purity available in this seat's hoard.

        Only RED parcels can serve as catapult fuel (GREEN and BLUE
        cannot be used as a propellant in this iteration). The
        resolver burns the LOWEST purity RED first so a seat doesn't
        accidentally torch their ``pure`` keepers as kindling.
        """
        return sum(
            _parcel_purity(p)
            for p in sess.hoard_squares.get(seat, [])
            if _is_red(p)
        )

    @staticmethod
    def _burn_fuel_avoiding(
        sess: "GameSession",
        seat: str,
        fuel_red_purity: int,
        excluded_ids: Set[str],
    ) -> int:
        """Catapult fuel-burn helper (v0.9.6).

        Same lowest-purity-first burn order as :meth:`_burn_fuel_from_hoard`
        BUT skips any RED parcel whose square-id is in ``excluded_ids``
        (those parcels are the ones being shipped — they can't double
        as fuel). Returns the actual RED purity burned; the caller is
        responsible for cannibalising the shortfall (if any) across
        the shipping parcels.
        """
        if fuel_red_purity <= 0:
            return 0
        hoard = sess.hoard_squares.get(seat, [])
        reds: List[Tuple[int, int]] = [
            (i, _parcel_purity(p))
            for i, p in enumerate(hoard)
            if _is_red(p) and _parcel_key(p) not in excluded_ids
        ]
        reds.sort(key=lambda r: r[1])  # lowest-purity first
        remaining = int(fuel_red_purity)
        burned = 0
        to_remove_idx: List[int] = []
        for idx, purity in reds:
            if remaining <= 0:
                break
            if purity <= remaining:
                to_remove_idx.append(idx)
                burned += purity
                remaining -= purity
            else:
                hoard[idx]["origin_purity"] = int(purity - remaining)
                hoard[idx]["purity_at_harvest"] = int(purity - remaining)
                hoard[idx]["partial_fuel_burn"] = True
                burned += remaining
                remaining = 0
                break
        if to_remove_idx:
            removed_set = set(to_remove_idx)
            sess.hoard_squares[seat] = [
                p for i, p in enumerate(hoard) if i not in removed_set
            ]
        return int(burned)

    @staticmethod
    def _burn_fuel_from_hoard(
        sess: "GameSession", seat: str, fuel_red_purity: int,
    ) -> bool:
        """Remove RED parcels (lowest-purity-first) totalling
        ``fuel_red_purity``. Returns True on success, False if the
        hoard didn't have enough RED purity.

        Partial-purity parcels are split: if a parcel with purity 80
        would put us 30 over the requested fuel, we deduct 30 from
        its purity and keep it. This matches the user's "burn fuel,
        keep change" intent.
        """
        if fuel_red_purity <= 0:
            return True
        hoard = sess.hoard_squares.get(seat, [])
        reds = [
            (i, _parcel_purity(p)) for i, p in enumerate(hoard) if _is_red(p)
        ]
        reds.sort(key=lambda r: r[1])  # lowest-purity first
        remaining = int(fuel_red_purity)
        total_available = sum(p for _, p in reds)
        if total_available < remaining:
            return False
        to_remove_idx: List[int] = []
        for idx, purity in reds:
            if remaining <= 0:
                break
            if purity <= remaining:
                to_remove_idx.append(idx)
                remaining -= purity
            else:
                # Trim this parcel's purity in-place.
                hoard[idx]["origin_purity"] = int(purity - remaining)
                hoard[idx]["purity_at_harvest"] = int(purity - remaining)
                hoard[idx]["partial_fuel_burn"] = True
                remaining = 0
                break
        if to_remove_idx:
            removed_set = set(to_remove_idx)
            sess.hoard_squares[seat] = [
                p for i, p in enumerate(hoard) if i not in removed_set
            ]
        return True
