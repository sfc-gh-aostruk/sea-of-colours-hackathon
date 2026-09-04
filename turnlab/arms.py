"""What a seat is holding when the night starts.

A frozen board carries whatever its season had, and for the boards
minted so far that is nothing — no EMP, no chaff, an empty hoard. Which
makes one question unaskable: does this agent do anything different when
you hand it a weapon? That is the question the redsign nights were built
around, and "buy an EMP on day one" is the exercise a fork is set.

So a rack is a property of *opening* a board, never of the board. The
board stays the fixed point it has to be, and two runs of the same night
can then differ by exactly one thing.

The four racks are the ones the battles ladder used, and the numbers are
restated here rather than imported. Battles is on its way out and the
lab is meant to outlive it; a dependency pointing at code being deleted
is worse than a second copy of four small tuples.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, MutableMapping


@dataclass(frozen=True)
class Rack:
    """Ordnance handed to one seat, plus the BLUE to build more."""

    id: str
    emp: int = 0
    chaff: int = 0
    #: Weapon-build fuel, as hoard purity. Zero on every shipped rack —
    #: see :data:`RACKS`. Kept because closing the procurement gap would
    #: want it back, and ``_give_blue`` is not code worth rediscovering.
    blue: int = 0
    note: str = ""


#: One of each, at most. The ladder handed out pairs, which turned every
#: run into a question about salvo economics when the question worth
#: asking is simpler: given a weapon, does this agent fire it at all? A
#: second round only lets a fork look decisive by spending twice.
#:
#: And no BLUE, since v1.43. A rack used to arrive with 200–455 purity of
#: build fuel, on the reasoning that stock lets a seat fire what it was
#: given while BLUE lets it make more. In this lab it cannot: weapons are
#: built by orbit actions (``BuildEmpAction`` / ``BuildChaffAction``) and
#: a frozen turn is a night, with ``turn.settle`` submitting empty orbit
#: actions afterwards. So the fuel was never spendable — it just sat in
#: the hoard as two fat parcels, taking vault slots, showing up in the
#: percept and moving the score.
#:
#: That made the one comparison the racks exist for dishonest: armed
#: versus unarmed was also richer versus poorer, and a fork that shipped
#: more looked like a fork that used its EMP well. Arming now changes
#: exactly one thing.
RACKS: tuple[Rack, ...] = (
    Rack("empty", note="no ordnance — the board exactly as it was frozen"),
    Rack("chaff", chaff=1,
         note="one chaff: can cancel a lift, or strand a committed rival"),
    Rack("emp", emp=1,
         note="one EMP: can deny ground for eight hours and time a walk-in"),
    Rack("both", emp=1, chaff=1,
         note="one of each — if the play does not change, nothing was learned"),
)

BY_ID: dict[str, Rack] = {r.id: r for r in RACKS}

DEFAULT = "empty"


def get(rack_id: str) -> Rack:
    try:
        return BY_ID[str(rack_id or DEFAULT)]
    except KeyError:
        raise KeyError(
            f"no rack named {rack_id!r}. Available: " + ", ".join(BY_ID)
        ) from None


def arm(blob: MutableMapping[str, Any], seat: str, rack_id: str) -> Rack:
    """Stamp a rack onto a session blob, in place.

    Writes the stockpile directly rather than running an orbit phase,
    which is the same shortcut the eval builder takes: the point is to
    watch an agent *use* a weapon, not to make it buy one first.
    """
    rack = get(rack_id)
    stock = blob.setdefault("weapon_stock", {})
    stock[str(seat)] = {"emp": int(rack.emp), "chaff": int(rack.chaff)}
    if rack.blue:
        _give_blue(blob, str(seat), rack.blue)
    return rack


def _give_blue(blob: MutableMapping[str, Any], seat: str, purity_total: int) -> None:
    """Fill the seat's hoard with BLUE parcels summing to ``purity_total``.

    Mirrors ``give_blue_purity`` in the eval builder, including the
    ``*_at_harvest`` keys — without those the parcels read as
    ``colour=EMPTY`` downstream and go uncounted, which looks exactly
    like arming silently not working.
    """
    from sea_of_colours.game.session import HOARD_CAPACITY
    from sea_of_colours.generator import Tile

    hoard = blob.setdefault("hoard_squares", {})
    parcels = list(hoard.get(seat) or [])
    remaining = max(0, int(purity_total))
    i = len(parcels)
    # A hoard that overflows its capacity is not a state the engine can
    # reach on its own, so don't hand it one; drop the excess instead.
    while remaining > 0 and len(parcels) < HOARD_CAPACITY:
        chunk = min(255, remaining)
        parcels.append({
            "site_id": f"blue-{seat}-lab-{i}",
            "origin_tile": int(Tile.BLUE),
            "origin_purity": chunk,
            "tile_at_harvest": int(Tile.BLUE),
            "purity_at_harvest": chunk,
        })
        remaining -= chunk
        i += 1
    hoard[seat] = parcels


def stock_of(blob: Any) -> dict[str, dict[str, int]]:
    """Every seat's actual ordnance, read off the session."""
    out: dict[str, dict[str, int]] = {}
    for seat, held in (blob.get("weapon_stock") or {}).items():
        if not isinstance(held, dict):
            continue
        emp, chaff = int(held.get("emp") or 0), int(held.get("chaff") or 0)
        if emp or chaff:
            out[str(seat)] = {"emp": emp, "chaff": chaff}
    return out


def disclose(session_id: str, agent: str, blob: Any) -> int:
    """Tell each seat what the others are *actually* holding.

    V12 does not know a rival's stock; it infers it, by watching that
    rival's blue-purity band drop between nights and reasoning about what
    could have been built with the difference. That is a good mechanic
    and it is useless here twice over. A frozen turn has no previous
    night to difference against, so the estimator has no anchor; and a
    rack is granted outright rather than bought, so there is no blue
    spend to notice even if it did. The result was a board where you
    armed a seat with an EMP and every agent on it still read
    ``emp: none observed`` — planning a night that was not the night.

    So the lab states the arsenal instead of making it guessable. The
    estimator is seeded with exact ranges (``min == max == stock``)
    before the harness runs, and ``update_estimates`` folds this turn's
    observations onto that footing rather than onto nothing.

    This is deliberately more than a real seat would know, and that is
    the trade the lab exists to make: the question here is "given an
    accurate picture, does this agent behave differently?", not "can it
    infer a rack from two nights of pip arithmetic?". A fork tested
    against a rival it cannot see is not being tested.

    Seeded per invocation against the throwaway clone's id, so it cannot
    reach a live season's estimates.
    """
    from . import recall

    mod = recall.fork_module(agent, "_v7.opponent_weapons")
    if mod is None:
        return 0

    stock = stock_of(blob)
    if not stock:
        return 0

    seats = [str(s) for s in (blob.get("players") or [])] or list(stock)
    seeded = 0
    for viewer in seats:
        estimates = {}
        for seat, held in stock.items():
            if seat == viewer:
                continue
            estimates[seat] = mod.WeaponEstimate(
                seat=seat,
                emps_min=held["emp"], emps_max=held["emp"],
                chaff_min=held["chaff"], chaff_max=held["chaff"],
                inferences=[
                    f"lab: {seat} is holding "
                    + " + ".join(
                        part for part in (
                            f"{held['emp']} EMP" if held["emp"] else "",
                            f"{held['chaff']} chaff" if held["chaff"] else "",
                        ) if part
                    )
                    + " (stated by the board, not inferred)"
                ],
            )
        if estimates:
            mod.store_estimates(session_id, viewer, estimates)
            seeded += len(estimates)
    return seeded


def catalogue() -> list[dict[str, Any]]:
    """The racks, for the launcher's pickers."""
    return [
        {
            "id": r.id,
            "emp": r.emp,
            "chaff": r.chaff,
            "blue": r.blue,
            "note": r.note,
            "label": (
                "no weapons" if r.id == "empty"
                else " + ".join(
                    part for part in (
                        f"{r.emp} EMP" if r.emp else "",
                        f"{r.chaff} chaff" if r.chaff else "",
                    ) if part
                )
            ),
        }
        for r in RACKS
    ]
