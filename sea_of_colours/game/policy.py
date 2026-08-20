"""Player policy schema for the orchestrator.

A *policy* is an ordered list of moves. You may submit up to
``MAX_QUEUE_LEN`` entries — and you can throw anything in there: malformed
JSON, syntactically valid but semantically illegal moves, etc. The
simulator processes the queue in order, **skipping invalid items**
(they're surfaced as yellow error lines in the log next to the attempted
action) and applying at most :data:`MAX_MOVES` *valid* moves per player
per night. Invalid moves no longer burn a tick — see
:class:`sea_of_colours.game.simulator.NightSimulator`.

Move tags::

    probe    {"a": "probe",  "at": [x, y]}
    drop     {"a": "drop",   "unit": <harvester_id>, "at": [x, y]}
    step     {"a": "step",   "unit": <harvester_id>, "to": [x, y]}
    pickup   {"a": "pickup", "unit": <harvester_id>}

The legacy ``deploy_probe`` / per-entity object schema is gone. Lifters are
implied: drop / pickup target a harvester directly and the owning player's
orblift is looked up at execution time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, List, Literal, Optional, Tuple, Union


MAX_MOVES: int = 21
"""Per-player per-night cap on *applied* (valid) policy actions across the
whole fleet (drop / step / pickup / probe all count as one action each).

The number is sized for 3 harvesters at full tilt:
``3 × (drop + 5 step + pickup) = 3 × 7 = 21``. So a player who manages a
3-harvester wing has no headroom for extra probes that night — choosing
between probes and a richer harvest pattern is a real trade-off. A
player with one or two harvesters has plenty of slots left for probes.

NOTE: this is the *fleet-wide* policy budget, NOT the per-harvester
step limit. Each harvester is independently capped at 5 steps per
night (RULEBOOK §3.x). The simulator enforces both: it skips invalid
items without burning a tick, then applies up to MAX_MOVES *valid*
moves until the queue is empty or the cap is hit."""

MAX_QUEUE_LEN: int = 100
"""Hard cap on raw queue length the orchestrator will accept per player.

Generous on purpose — the rules let players "log whatever you want into
your policy" — but a finite ceiling so a runaway agent can't blow up the
server. Items beyond this index are silently dropped at parse time."""

# NOTE (v0.6.0): the historical ``HARVEST_CAP`` (5 RED→GREEN conversions
# per player per night) was removed when harvesting was extended to all
# colours (§3.12). The natural limit is now the harvester's 6-parcel hold
# capacity (drop + 5 steps), so a per-night colour cap is redundant. A
# back-compat sentinel is preserved below for legacy importers that
# reach for the name; setting it to ``MAX_QUEUE_LEN`` effectively
# disables the cap without making downstream branches crash.
HARVEST_CAP: int = MAX_QUEUE_LEN
"""DEPRECATED (v0.6.0): no per-color harvest cap. Held at MAX_QUEUE_LEN
for back-compat with v0.5 tests that import the name."""


MoveTag = Literal[
    "probe",
    "drop",
    "step",
    "pickup",
    "wait",
    "emp_launch",
    "mine_lay",
    "chaff_flare",
    "waste",
]


@dataclass(frozen=True)
class ProbeMove:
    at: Tuple[int, int]
    tag: MoveTag = "probe"


@dataclass(frozen=True)
class DropMove:
    unit: str
    at: Tuple[int, int]
    tag: MoveTag = "drop"


@dataclass(frozen=True)
class StepMove:
    unit: str
    to: Tuple[int, int]
    tag: MoveTag = "step"


@dataclass(frozen=True)
class PickupMove:
    unit: str
    tag: MoveTag = "pickup"


@dataclass(frozen=True)
class WaitMove:
    """A no-op that consumes one of the 21 hour slots without acting.

    The bedrock of v0.9 hour-scheduling: a player who wants to drop at
    hour 10 pads their queue with 9 ``WaitMove``s first. WAITs also
    surface during EMP / chaff resolution as the engine-substituted
    action for a disabled / chaffed seat — the simulator tags those
    frames distinctly (``empd`` / ``chaffed``) so the watcher can tell
    a voluntary wait from a forced one.
    """

    tag: MoveTag = "wait"


@dataclass(frozen=True)
class EmpLaunchMove:
    """Fire an orbital EMP salvo (RULEBOOK §5, v0.9).

    One launch fires ``EMP_MISSILES_PER_LAUNCH`` simultaneous missiles
    for one stock/cost. ``at`` is the primary target; ``extra_ats``
    holds the rest of the salvo. Each target spawns its own Manhattan
    radius-``EMP_RADIUS`` cloud for ``EMP_CLOUD_HOURS`` of the SAME
    night. Any harvester sitting in a cloud cell at the start of a
    subsequent hour gets its action replaced by a WAIT (logged as
    ``tag="empd"``); any PROBE/MINE caught in the blast is destroyed.
    Friendly fire is on. Open action: every seat sees the launch + cloud.
    """

    at: Tuple[int, int]
    extra_ats: Tuple[Tuple[int, int], ...] = ()
    tag: MoveTag = "emp_launch"

    @property
    def ats(self) -> Tuple[Tuple[int, int], ...]:
        """Full salvo (primary target first)."""
        return (self.at,) + tuple(self.extra_ats)


@dataclass(frozen=True)
class MineLayMove:
    """Drop a caltrop mine on ``at`` (RULEBOOK §5, v0.9).

    Cost debited on apply. Stores a hidden mine at the tile (only
    the owner sees it by default; a probe witness records it into
    the other seat's intel echo). Any harvester (own or opponent's)
    stepping into the tile has its move cancelled, becomes damaged,
    and the mine is removed. No harvest happens on the cancelled
    step.
    """

    at: Tuple[int, int]
    tag: MoveTag = "mine_lay"


@dataclass(frozen=True)
class ChaffFlareMove:
    """Fire an orbital chaff flare (RULEBOOK §5, v0.9).

    Cost debited on apply. At the hour this move occupies (and for
    ``CHAFF_DURATION_HOURS - 1`` subsequent hours) every OTHER seat's
    hour-N action is cancelled (replay tag ``"chaffed"``). The
    triggerer's chaff itself proceeds; the triggerer's *later* hours
    are NOT affected. Open action.
    """

    tag: MoveTag = "chaff_flare"


@dataclass(frozen=True)
class WasteMove:
    """A queue slot the parser kept because it was structurally bad.

    Carries the original payload + a human reason for replay captions.
    """

    reason: str
    raw: Any = None
    tag: MoveTag = "waste"


Move = Union[
    ProbeMove,
    DropMove,
    StepMove,
    PickupMove,
    WaitMove,
    EmpLaunchMove,
    MineLayMove,
    ChaffFlareMove,
    WasteMove,
]


def _pair(obj: Any) -> Optional[Tuple[int, int]]:
    if not isinstance(obj, list) or len(obj) != 2:
        return None
    try:
        return int(obj[0]), int(obj[1])
    except (TypeError, ValueError):
        return None


def _parse_one(raw: Any) -> Move:
    if not isinstance(raw, dict):
        return WasteMove(reason="move must be an object", raw=raw)
    action = raw.get("a") or raw.get("action")
    if not isinstance(action, str):
        return WasteMove(reason="move missing 'a' field", raw=raw)
    action = action.lower()

    if action == "probe":
        xy = _pair(raw.get("at"))
        if xy is None:
            return WasteMove(reason="probe.at must be [x,y]", raw=raw)
        return ProbeMove(at=xy)

    if action == "drop":
        unit = raw.get("unit")
        xy = _pair(raw.get("at"))
        if not isinstance(unit, str) or not unit:
            return WasteMove(reason="drop.unit missing", raw=raw)
        if xy is None:
            return WasteMove(reason="drop.at must be [x,y]", raw=raw)
        return DropMove(unit=unit, at=xy)

    if action == "step":
        unit = raw.get("unit")
        to = _pair(raw.get("to"))
        if not isinstance(unit, str) or not unit:
            return WasteMove(reason="step.unit missing", raw=raw)
        if to is None:
            return WasteMove(reason="step.to must be [x,y]", raw=raw)
        return StepMove(unit=unit, to=to)

    if action == "pickup":
        unit = raw.get("unit")
        if not isinstance(unit, str) or not unit:
            return WasteMove(reason="pickup.unit missing", raw=raw)
        return PickupMove(unit=unit)

    if action == "wait":
        # No payload required. The hour-stamp the simulator assigns
        # is implicit (slot index). Extra fields in ``raw`` are
        # silently ignored so a frontend that adds ``{"a": "wait",
        # "for_hour": 10}`` for debugging round-trips cleanly.
        return WaitMove()

    if action in ("emp", "emp_launch", "emp-launch"):
        raw_at = raw.get("at")
        # Accept either a single ``[x,y]`` or a salvo ``[[x,y], ...]``.
        targets: List[Tuple[int, int]] = []
        if (
            isinstance(raw_at, list)
            and raw_at
            and all(isinstance(t, list) for t in raw_at)
        ):
            for t in raw_at:
                p = _pair(t)
                if p is not None:
                    targets.append(p)
        else:
            p = _pair(raw_at)
            if p is not None:
                targets.append(p)
        if not targets:
            return WasteMove(
                reason="emp_launch.at must be [x,y] or [[x,y], ...]",
                raw=raw,
            )
        return EmpLaunchMove(at=targets[0], extra_ats=tuple(targets[1:]))

    if action in ("mine", "mine_lay", "mine-lay"):
        xy = _pair(raw.get("at"))
        if xy is None:
            return WasteMove(reason="mine_lay.at must be [x,y]", raw=raw)
        return MineLayMove(at=xy)

    if action in ("chaff", "chaff_flare", "chaff-flare"):
        return ChaffFlareMove()

    return WasteMove(reason=f"unknown action '{action}'", raw=raw)


def parse_moves(payload: Any) -> Tuple[List[Move], List[str]]:
    """Return ``(moves, hard_errors)``.

    ``hard_errors`` is only populated when the payload itself is malformed
    (not a list / dict, etc.). Per-entry parse failures become
    :class:`WasteMove` markers — the simulator surfaces them as yellow
    error lines but they no longer consume a tick (RULEBOOK §3.10).

    Queue length is capped at :data:`MAX_QUEUE_LEN`; entries beyond that
    are silently dropped at parse time.
    """

    if payload is None:
        return [], []

    if isinstance(payload, dict):
        seq = payload.get("moves")
    else:
        seq = payload

    if seq is None:
        return [], []

    if not isinstance(seq, list):
        return [], ["policy 'moves' must be a list"]

    out: List[Move] = []
    for raw in seq[:MAX_QUEUE_LEN]:
        out.append(_parse_one(raw))
    return out, []


def move_to_wire(m: Move) -> dict:
    """Round-trip a parsed move back to the JSON shape (for echo/debug)."""
    if isinstance(m, ProbeMove):
        return {"a": "probe", "at": list(m.at)}
    if isinstance(m, DropMove):
        return {"a": "drop", "unit": m.unit, "at": list(m.at)}
    if isinstance(m, StepMove):
        return {"a": "step", "unit": m.unit, "to": list(m.to)}
    if isinstance(m, PickupMove):
        return {"a": "pickup", "unit": m.unit}
    if isinstance(m, WaitMove):
        return {"a": "wait"}
    if isinstance(m, EmpLaunchMove):
        if m.extra_ats:
            return {
                "a": "emp_launch",
                "at": [list(t) for t in m.ats],
            }
        return {"a": "emp_launch", "at": list(m.at)}
    if isinstance(m, MineLayMove):
        return {"a": "mine_lay", "at": list(m.at)}
    if isinstance(m, ChaffFlareMove):
        return {"a": "chaff_flare"}
    return {"a": "waste", "reason": m.reason}


def moves_to_wire(moves: Iterable[Move]) -> List[dict]:
    return [move_to_wire(m) for m in moves]


# ── Orbit actions (v0.8.0) ───────────────────────────────────────────
#
# The Orbit phase runs once per game-day before PRAXIS (RULEBOOK §4).
# Each seat may declare up to :data:`MAX_ORBIT_ACTIONS` actions in any
# combination of build / repair / refine / ship-auction / ship-tithe /
# solar-jettison. The orchestrator parses the seat's submission into
# this discriminated union; the resolver (sea_of_colours.game.
# orbit_resolver.OrbitResolver) walks the validated list and applies
# them in a fixed order (builds/repair/refine first, then catapult
# settlement).


MAX_ORBIT_ACTIONS: int = 3
"""Per-seat per-turn cap on Orbit phase actions (parser drops the
rest). Re-exported from :mod:`sea_of_colours.game.session` for
back-compat with callers that import it from here."""


OrbitTag = Literal[
    "build_harvester",
    "build_probe",
    "build_emp",
    "build_mine",
    "build_chaff",
    "repair",
    "refine",
    # v1.x — final-orbit "refinery run": one action cascades every RED
    # parcel up as far as the seat's BLUE allows (trace→vein→mass).
    # Only honoured on the terminal settlement orbit (RULEBOOK §4.3.1).
    "refine_cascade",
    # v0.9.6 — ``ship_auction`` and ``ship_tithe`` are gone; one
    # ``ship_catapult`` lane replaces both (RULEBOOK §4.4). Old
    # replay frames carrying the legacy tags now parse as
    # OrbitWasteAction (the catch-all "unknown orbit action" branch).
    "ship_catapult",
    "solar_jettison",
    "orbit_waste",
]


@dataclass(frozen=True)
class BuildHarvesterAction:
    """Mint a new harvester in orbit (paid via credits)."""

    tag: OrbitTag = "build_harvester"


@dataclass(frozen=True)
class BuildProbeAction:
    """Top up the seat's probe stock by ``count`` (paid via credits).

    v0.9.1 — accepts an explicit ``count`` so a single Orbit-action
    slot can mint multiple probes. ``count`` defaults to 1 for
    back-compat with v0.8.x callers and persisted sessions; the
    resolver clamps it to ``max(1, count)``. v1.2 — the buy PARTIAL-
    FILLS: it mints as many probes as the seat can afford rather than
    rejecting the whole batch, and logs a red amendment line when the
    order is trimmed to budget (only a batch that can't afford even one
    probe is a hard rejection).
    """

    count: int = 1
    tag: OrbitTag = "build_probe"


@dataclass(frozen=True)
class BuildEmpAction:
    """v0.9.3 — Construct ``count`` EMP warheads in orbit.

    Cost: ``count × (EMP_COST_BLUE_PURITY + EMP_COST_CREDITS)``. The
    resolver refuses the entire batch if the seat can't pay it in
    one go (matches the BuildProbeAction "no partial fill" rule).
    On success, ``count`` is added to ``weapon_stock[seat]["emp"]``
    and the matching ``EmpLaunchMove`` during PRAXIS drains the
    stock instead of debiting resources live.
    """

    count: int = 1
    tag: OrbitTag = "build_emp"


@dataclass(frozen=True)
class BuildMineAction:
    """v0.9.3 — Construct ``count`` caltrop mines in orbit.

    Cost: ``count × (MINE_COST_BLUE_PURITY + MINE_COST_CREDITS)``.
    On success, ``count`` is added to ``weapon_stock[seat]["mine"]``;
    each ``MineLayMove`` during the night drains one. Mines per
    BUILD batch is independent of ``MINES_PER_BUY`` (which scales
    one lay action into multiple tiles via batch shapes).
    """

    count: int = 1
    tag: OrbitTag = "build_mine"


@dataclass(frozen=True)
class BuildChaffAction:
    """v0.9.3 — Construct ``count`` orbital chaff flares.

    Cost: ``count × (CHAFF_COST_BLUE_PURITY + CHAFF_COST_CREDITS)``.
    Each ``ChaffFlareMove`` during the night drains one from
    ``weapon_stock[seat]["chaff"]``.
    """

    count: int = 1
    tag: OrbitTag = "build_chaff"


@dataclass(frozen=True)
class RepairAction:
    """Repair a damaged harvester in orbit (paid via credits)."""

    unit: str = ""
    tag: OrbitTag = "repair"


@dataclass(frozen=True)
class RefineAction:
    """Promote parcels of one source tier into the next tier up.

    Two input modes (v0.9.1):

    - ``source_tier="trace"`` / ``"vein"`` — refine EVERY RED parcel of
      that tier in the seat's hoard in one click. The preferred path.
    - ``inputs=("sq-1","sq-2",...)`` — legacy v0.8 path that takes
      explicit square-ids. Kept for back-compat with persisted v0.8
      sessions and the JSON expert pane; the resolver still honours
      it identically.

    Purity is always conserved exactly: the sum of input purities is
    partitioned into N output parcels at target-tier max purity plus
    an optional residual at ``S mod M`` in the source tier.
    """

    inputs: Tuple[str, ...] = ()
    source_tier: Optional[str] = None
    tag: OrbitTag = "refine"


@dataclass(frozen=True)
class RefineCascadeAction:
    """v1.x — one-click terminal "refinery run" (RULEBOOK §4.3.1).

    Cascades EVERY eligible RED parcel up the tier ladder as far as the
    seat's BLUE reserve allows: all trace → vein, then all vein
    (including the just-minted ones) → mass, stopping at ``target_tier``
    or when the blue runs out. Purity is conserved at each step; the
    result is the fewest, highest-tier parcels the seat can afford —
    ideal fuel for the final ship draft.

    Honoured **only on the final settlement orbit**; on any earlier
    orbit the resolver drops it (the normal capped, next-turn
    :class:`RefineAction` still applies). ``target_tier`` is ``"vein"``
    or ``"mass"`` (default ``"mass"`` = refine all the way up).
    """

    target_tier: str = "mass"
    tag: OrbitTag = "refine_cascade"


@dataclass(frozen=True)
class ShipCatapultBid:
    """v0.9.x per-parcel credit-bid catapult declaration (RULEBOOK §4.4).

    The seat names SPECIFIC RED parcels to ship and the CREDIT bid it
    offers for each one. ``bids`` is an ordered tuple of
    ``(parcel_id, credits)``. Credits are debited (forfeit) the
    instant the action is programmed — bidding locks both the parcel
    and the credits so they can't be reused by a later action this
    turn.

    The resolver pools every seat's per-parcel bid into one global
    queue ranked by credits DESC and fills 20 slots (4 rows x 5).
    Each row applies a flat RED-purity TRANSIT CHARGE
    (:data:`CATAPULT_ROW_TRANSIT`) taken out of the parcel's own
    purity. Score = (purity - transit) x tier-multiplier of the
    ORIGINAL purity. Parcels that miss all 20 slots do not ship and
    their credit bid is forfeit.
    """

    bids: Tuple[Tuple[str, int], ...] = ()
    # v1.x — final-orbit AUTO ship. Because refined parcels get their
    # ids minted at settlement time, a seat can't pre-name them; an
    # auto bid says "bid ``auto_credits`` on my best ``auto_count`` RED
    # parcels (0 = all), chosen by tier-weighted value AFTER the
    # refinery run resolves". Honoured only on the terminal orbit; the
    # explicit ``bids`` path is unchanged everywhere else.
    auto: bool = False
    auto_credits: int = 0
    auto_count: int = 0
    tag: OrbitTag = "ship_catapult"


@dataclass(frozen=True)
class SolarJettisonBid:
    """Green-catapult flush declaration (RULEBOOK §4.5).

    The seat commits ``red_fuel`` RED-purity (forfeit whether or not
    every slot is used) and nominates up to ``green_parcels`` GREEN
    parcels to dispose of. The resolver ranks houses by total
    ``red_fuel`` offered, deals 12 shared slots round-robin in that
    order, and each house flushes one green per slot it can still
    afford from its committed fuel (per-slot cost diminishes by
    global slot index, :data:`GREEN_SLOT_COST_BASE` /
    :data:`GREEN_SLOT_COST_STEP`). More houses flushing together makes
    each parcel cheaper.

    Tag kept as ``solar_jettison`` for wire/back-compat; the old
    ``max_red_burn`` / ``max_parcels`` keys map onto ``red_fuel`` /
    ``green_parcels``.
    """

    green_parcels: int = 0
    red_fuel: int = 0
    tag: OrbitTag = "solar_jettison"


@dataclass(frozen=True)
class OrbitWasteAction:
    """A queue slot the parser kept because it was structurally bad.

    Mirrors :class:`WasteMove` for Orbit submissions — surfaced as a
    yellow log line by the resolver but does not consume any of the
    seat's 3 action slots.
    """

    reason: str = ""
    raw: Any = None
    tag: OrbitTag = "orbit_waste"


OrbitAction = Union[
    BuildHarvesterAction,
    BuildProbeAction,
    BuildEmpAction,
    BuildMineAction,
    BuildChaffAction,
    RepairAction,
    RefineAction,
    RefineCascadeAction,
    ShipCatapultBid,
    SolarJettisonBid,
    OrbitWasteAction,
]


def _parse_orbit_one(raw: Any) -> OrbitAction:
    if not isinstance(raw, dict):
        return OrbitWasteAction(reason="orbit action must be an object", raw=raw)
    action = raw.get("a") or raw.get("action")
    if not isinstance(action, str):
        return OrbitWasteAction(reason="orbit action missing 'a' field", raw=raw)
    a = action.lower()

    if a in ("build_harvester", "build-harvester", "buildharvester"):
        return BuildHarvesterAction()

    if a in ("build_probe", "build-probe", "buildprobe"):
        raw_count = raw.get("count", raw.get("n"))
        try:
            count = int(raw_count) if raw_count is not None else 1
        except (TypeError, ValueError):
            count = 1
        return BuildProbeAction(count=max(1, count))

    # v0.9.3 — Build interdiction weapons (RULEBOOK §5.0). Same
    # batch-count shape as ``build_probe``: missing/invalid counts
    # clamp to 1, single-pay-or-bust at the resolver.
    if a in ("build_emp", "build-emp", "buildemp"):
        raw_count = raw.get("count", raw.get("n"))
        try:
            count = int(raw_count) if raw_count is not None else 1
        except (TypeError, ValueError):
            count = 1
        return BuildEmpAction(count=max(1, count))

    if a in ("build_mine", "build-mine", "buildmine"):
        raw_count = raw.get("count", raw.get("n"))
        try:
            count = int(raw_count) if raw_count is not None else 1
        except (TypeError, ValueError):
            count = 1
        return BuildMineAction(count=max(1, count))

    if a in ("build_chaff", "build-chaff", "buildchaff"):
        raw_count = raw.get("count", raw.get("n"))
        try:
            count = int(raw_count) if raw_count is not None else 1
        except (TypeError, ValueError):
            count = 1
        return BuildChaffAction(count=max(1, count))

    if a == "repair":
        unit = raw.get("unit")
        if not isinstance(unit, str) or not unit:
            return OrbitWasteAction(reason="repair.unit missing", raw=raw)
        return RepairAction(unit=unit)

    if a == "refine":
        # v0.9.1 — accept the new ``source_tier`` shape first; fall back
        # to the legacy ``inputs`` list. ``source_tier`` is preferred:
        # it lets the resolver refine every RED parcel of that tier in
        # one click without the seat hand-picking ids.
        tier_raw = raw.get("source_tier") or raw.get("tier")
        if isinstance(tier_raw, str) and tier_raw.strip():
            tier = tier_raw.strip().lower()
            if tier in ("trace", "vein"):
                return RefineAction(source_tier=tier)
            return OrbitWasteAction(
                reason=f"refine.source_tier must be 'trace' or 'vein' (got '{tier_raw}')",
                raw=raw,
            )
        inputs = raw.get("inputs")
        if not isinstance(inputs, list) or not inputs:
            return OrbitWasteAction(
                reason="refine needs source_tier='trace'|'vein' OR inputs=[...]",
                raw=raw,
            )
        ids = tuple(str(x) for x in inputs if isinstance(x, (str, int)) and str(x))
        if not ids:
            return OrbitWasteAction(reason="refine.inputs had no usable ids", raw=raw)
        return RefineAction(inputs=ids)

    if a in ("refine_cascade", "refine-cascade", "refinery", "refine_all_up"):
        # v1.x — terminal refinery run. Optional ``target_tier`` caps how
        # far up the ladder to push (default 'mass' = all the way).
        tier_raw = raw.get("target_tier") or raw.get("target") or "mass"
        tier = str(tier_raw).strip().lower() if isinstance(tier_raw, str) else "mass"
        if tier not in ("vein", "mass"):
            tier = "mass"
        return RefineCascadeAction(target_tier=tier)

    if a in ("ship_catapult", "ship-catapult", "shipcatapult"):
        # v0.9.x per-parcel credit-bid shipping (RULEBOOK §4.4). Bid
        # shape (preferred)::
        #
        #     {"a": "ship_catapult",
        #      "bids": [{"id": "sq_..", "credits": 25}, ...]}
        #
        # Convenience uniform shape (one credit value for a list of
        # ids)::
        #
        #     {"a": "ship_catapult", "parcels": ["sq_..", ..],
        #      "credits": 25}
        from sea_of_colours.game.session import (
            CATAPULT_ROW_COUNT,
            CATAPULT_SLOTS_PER_ROW,
        )

        cap = int(CATAPULT_ROW_COUNT) * int(CATAPULT_SLOTS_PER_ROW)

        # v1.x — AUTO ship (final orbit): "bid C credits on my best N RED
        # parcels (0 = all), picked after the refinery run". Lets a seat
        # ship freshly-refined parcels whose ids don't exist until
        # settlement. Shape: {"a":"ship_catapult","auto":true,
        # "credits":C,"count":N} or {"parcels":"all","credits":C}.
        _parcels_raw = raw.get("parcels")
        _auto_flag = bool(raw.get("auto")) or (
            isinstance(_parcels_raw, str)
            and _parcels_raw.strip().lower() in ("all", "best", "auto")
        )
        if _auto_flag:
            uni = raw.get("credits", raw.get("credits_per_parcel", raw.get("bid")))
            try:
                uni_i = int(uni) if uni is not None else 0
            except (TypeError, ValueError):
                uni_i = 0
            cnt = raw.get("count", raw.get("n"))
            try:
                cnt_i = int(cnt) if cnt is not None else 0
            except (TypeError, ValueError):
                cnt_i = 0
            return ShipCatapultBid(
                auto=True, auto_credits=max(0, uni_i), auto_count=max(0, cnt_i),
            )

        pairs: list = []
        raw_bids = raw.get("bids")
        if isinstance(raw_bids, list):
            for item in raw_bids:
                if not isinstance(item, dict):
                    continue
                pid = item.get("id") or item.get("parcel_id") or item.get("square_id")
                cr = item.get("credits", item.get("bid", item.get("credit")))
                if pid is None:
                    continue
                try:
                    cr_i = int(cr) if cr is not None else 0
                except (TypeError, ValueError):
                    cr_i = 0
                pairs.append((str(pid), max(0, cr_i)))
        else:
            ids = raw.get("parcels", raw.get("ids"))
            uni = raw.get("credits", raw.get("credits_per_parcel", raw.get("bid")))
            try:
                uni_i = int(uni) if uni is not None else 0
            except (TypeError, ValueError):
                uni_i = 0
            if isinstance(ids, list):
                for pid in ids:
                    if pid is None:
                        continue
                    pairs.append((str(pid), max(0, uni_i)))
        if not pairs:
            return OrbitWasteAction(
                reason="ship_catapult had no usable (id, credits) bids",
                raw=raw,
            )
        return ShipCatapultBid(bids=tuple(pairs[:cap]))

    if a in ("solar_jettison", "solar-jettison", "jettison", "green_catapult"):
        # v0.9.x green-catapult flush. Preferred keys ``green_parcels``
        # / ``red_fuel``; legacy ``max_parcels`` / ``max_red_burn`` map
        # onto them for back-compat.
        gp = raw.get("green_parcels", raw.get("max_parcels", raw.get("green")))
        try:
            gp_i = int(gp) if gp is not None else 0
        except (TypeError, ValueError):
            gp_i = 0
        rf = raw.get("red_fuel", raw.get("max_red_burn", raw.get("fuel", raw.get("max"))))
        try:
            rf_i = int(rf) if rf is not None else 0
        except (TypeError, ValueError):
            return OrbitWasteAction(
                reason="green_catapult.red_fuel not an int", raw=raw,
            )
        return SolarJettisonBid(
            green_parcels=max(0, gp_i), red_fuel=max(0, rf_i),
        )

    return OrbitWasteAction(reason=f"unknown orbit action '{action}'", raw=raw)


def parse_orbit_actions(
    payload: Any,
    *,
    max_actions: Optional[int] = MAX_ORBIT_ACTIONS,
) -> Tuple[List[OrbitAction], List[str]]:
    """Return ``(actions, hard_errors)`` from a raw Orbit submission.

    Accepts either ``{"actions": [...]}`` or a bare list. Items past
    ``max_actions`` are silently dropped. Per-item parse failures become
    :class:`OrbitWasteAction` markers and are surfaced by the resolver
    as yellow log lines (they do NOT consume a slot).

    ``max_actions=None`` disables truncation — the caller
    (``GameSession.submit_orbit``) passes this on the **final settlement
    orbit** so the terminal refinery run isn't capped at 3 actions
    (RULEBOOK §4.3.1).
    """
    if payload is None:
        return [], []
    if isinstance(payload, dict):
        seq = payload.get("actions") or payload.get("orbit_actions")
    else:
        seq = payload
    if seq is None:
        return [], []
    if not isinstance(seq, list):
        return [], ["orbit submission 'actions' must be a list"]
    trimmed = seq if max_actions is None else seq[:max_actions]
    out: List[OrbitAction] = []
    for raw in trimmed:
        out.append(_parse_orbit_one(raw))
    return out, []


def orbit_action_to_wire(a: OrbitAction) -> dict:
    if isinstance(a, BuildHarvesterAction):
        return {"a": "build_harvester"}
    if isinstance(a, BuildProbeAction):
        out: dict = {"a": "build_probe"}
        # Only emit the count field when it's a batch — keeps the wire
        # shape clean for the legacy single-probe path and stops the
        # v0.8 prompt-side parser from tripping on an unknown key.
        if int(getattr(a, "count", 1) or 1) > 1:
            out["count"] = int(a.count)
        return out
    # v0.9.3 — symmetric serialiser for the three new weapon-build
    # actions. Same "skip count when 1" rule as build_probe.
    if isinstance(a, BuildEmpAction):
        out = {"a": "build_emp"}
        if int(getattr(a, "count", 1) or 1) > 1:
            out["count"] = int(a.count)
        return out
    if isinstance(a, BuildMineAction):
        out = {"a": "build_mine"}
        if int(getattr(a, "count", 1) or 1) > 1:
            out["count"] = int(a.count)
        return out
    if isinstance(a, BuildChaffAction):
        out = {"a": "build_chaff"}
        if int(getattr(a, "count", 1) or 1) > 1:
            out["count"] = int(a.count)
        return out
    if isinstance(a, RepairAction):
        return {"a": "repair", "unit": a.unit}
    if isinstance(a, RefineAction):
        if a.source_tier:
            return {"a": "refine", "source_tier": str(a.source_tier)}
        return {"a": "refine", "inputs": list(a.inputs)}
    if isinstance(a, RefineCascadeAction):
        return {"a": "refine_cascade", "target_tier": str(a.target_tier)}
    if isinstance(a, ShipCatapultBid):
        if getattr(a, "auto", False):
            return {
                "a": "ship_catapult",
                "auto": True,
                "credits": int(a.auto_credits),
                "count": int(a.auto_count),
            }
        return {
            "a": "ship_catapult",
            "bids": [
                {"id": str(pid), "credits": int(cr)} for pid, cr in a.bids
            ],
        }
    if isinstance(a, SolarJettisonBid):
        return {
            "a": "solar_jettison",
            "green_parcels": int(a.green_parcels),
            "red_fuel": int(a.red_fuel),
        }
    return {"a": "orbit_waste", "reason": getattr(a, "reason", "")}


def orbit_actions_to_wire(actions: Iterable[OrbitAction]) -> List[dict]:
    return [orbit_action_to_wire(a) for a in actions]
