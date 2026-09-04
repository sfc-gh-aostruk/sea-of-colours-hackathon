"""Lab boards — saved engine state, frozen the moment before a decision.

A board is a **snapshot**: a complete, inert session written by
:func:`snapshot.take` just before a seat planned. That is the whole
idea, and it is worth being blunt about why, because two earlier
versions of this file got it wrong in instructive ways.

The first version had a human read a season's agent cards and type the
board back in — "pure at (34,19), mass at (33,19) purity 219, the other
two are probably 200". Half of it landed in an ``inferred`` dict
because it was guesswork.

The second pointed at a real night in a finished season and read the
position out of its ``tag="open"`` replay frame. That is exact for
*looking* at, and the lab still does it for history. But a frame is
rendered paint — ``bg``/``ch``/``fg`` — with no tile and no purity, so
nothing can be *played* from one.

That much still stands. What used to be written here next did not: the
claim that a finished season is therefore unreachable, and that only a
season someone remembered to snapshot can yield boards. It is false, and
it cost this package a lot of pointless minting. A season does not have
to be *read back* — it can be **re-walked**. The seed, both seats' night
orders for every day, and the orbit settlements are all archived
forever, and the engine has no nondeterminism, so replaying them
reproduces the season exactly rather than approximately. See
:mod:`turnlab.rewalk`, which does it and checks itself doing it.

So there are two kinds of board, and they are interchangeable here:

* a **snapshot** — state the engine froze mid-season, via ``mint``;
* a **re-walk** — state the engine rebuilt from a finished season, via
  ``rewalk``, which is how you grab day 4 of a game played last week.

Either way, what a board holds is a real session the engine wrote.
Cloning one and playing it is the engine playing it.

Boards are discovered rather than declared, so minting a new set makes
them appear without editing this file. :data:`NOTES` is the one
hand-written part — the editorial claim about why a night is worth
studying, which is the only thing a machine cannot read off the board.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from . import store as _store_mod

#: Snapshot ids begin with this. Set by ``mint(prefix=...)``, and shared
#: with the store, which routes sessions on the same prefix.
LAB_PREFIX = _store_mod.BOARD_PREFIX


@dataclass(frozen=True)
class Board:
    """One frozen decision, backed by saved engine state."""

    #: The snapshot session id. This *is* the board.
    id: str
    #: Calendar day the freeze was taken on.
    day: int
    #: The seat that was about to plan.
    seat: str
    #: The season the freeze was cut from, for provenance.
    source: str = ""
    #: Who really held the seat when the season was played.
    played_by: str = ""
    #: The season this came from, in the words a person would use.
    #: ``mint`` writes its own name here; ``rewalk`` writes the real
    #: season's. Either way it is what makes a list of boards readable.
    season: str = ""
    #: The hand-written note, when there is one.
    note: Optional["Note"] = None
    #: Every seat the position actually has. Read off the session rather
    #: than inferred, because the two kinds of board disagree: a minted
    #: set writes one row per seat, a re-walked one writes a single row
    #: for the whole night.
    players: tuple[str, ...] = ()
    #: The map seed the season was played on. Read off the session, never
    #: written into a note: it is what makes a board reproducible, so a
    #: hand-typed copy that drifts is worse than no copy at all.
    seed: Optional[int] = None

    @property
    def label(self) -> str:
        # A named board is called what its note calls it. Failing that, a
        # re-walked board carries the real season's name, and
        # "CONTROL_s42_file, day 5" is what a person picks out of a list of
        # two hundred. A *snapshot* board's season_name is the engine's own
        # bookkeeping ("REPLAY:LAB:LAB_OFFLINE_4242:d2:p1") and would make a
        # worse label than no label, so only the marker rewalk writes counts.
        if self.note is not None and self.note.name:
            return self.note.name
        stem, sep, _ = self.season.partition(" · day ")
        return f"{stem}, day {self.day}" if sep else f"day {self.day} · {self.seat}"

    @property
    def castable(self) -> tuple[str, ...]:
        """The seats an agent may be cast into.

        Every canonical seat, unless a note deliberately narrows it. A
        board is a position, and a position is only itself when all of it
        can move: freezing a night to test one seat's attack still needs
        the seat being attacked to take its turn, or the night that
        resolves is one nobody would have played (v1.42).
        """
        if self.note is not None and self.note.seats:
            return self.note.seats
        return self.players

    def as_dict(self) -> dict:
        note = self.note
        return {
            "id": self.id,
            "day": self.day,
            "seat": self.seat,
            "source": self.source,
            "played_by": self.played_by,
            "season": self.season,
            "label": self.label,
            "name": note.name if note else "",
            "state": note.state if note else "",
            "why": note.why if note else "",
            "tests": note.tests if note else "",
            "castable": list(self.castable),
            "players": list(self.players),
            # Derived, both of them. The launcher shows "3 seats · seed
            # 55792121" under every board, and it is worth reading that
            # as fact rather than as caption.
            "seats_n": len(self.players),
            "seed": self.seed,
        }


@dataclass(frozen=True)
class Note:
    """What a board is called, what it is, and what it is for.

    Split three ways on purpose. ``state`` is a claim about the position
    and must be checkable against the board — every figure in the ones
    below was read off the saved session, not remembered. ``why`` is the
    editorial half and cannot be derived from anything; it is the reason
    somebody bothered to freeze this night. Keeping them apart means a
    wrong number is a bug you can find, rather than an opinion.
    """

    name: str
    state: str = ""
    why: str = ""
    #: One line, for the list. What this board is *for* — the thing you
    #: would learn by running a fork on it that you would not learn
    #: anywhere else. Player count and seed are NOT written here: they
    #: are read off the session (see :class:`Board`), because a hand-typed
    #: number is a number that will eventually be wrong.
    tests: str = ""
    #: Seats worth casting an agent into. Empty means all of them.
    #: The lab will happily let you play any seat — this is advice about
    #: which seats make the board mean what it is supposed to mean, and
    #: the reason is always in ``why``.
    seats: tuple[str, ...] = ()


#: Editorial notes, keyed ``<source>_d<day>``.
#:
#: Keyed by the night rather than the board id because the two kinds of
#: board disagree about how many ids a night has: a re-walked one writes
#: a single row for the whole position, a minted one writes a row per
#: seat. Keying on the id meant a minted night needed the same blurb
#: typed twice, and the second copy is the one that goes stale.
#:
#: Optional by design — a board with nothing interesting to say about it
#: is still a board.
NOTES: Mapping[str, Note] = {
    "dd868733_d1": Note(
        name="Vanilla Opener · day 1",
        tests="the cold open — no map, no seam, no history, just an opening move",
        state=(
            "Turn one, and nothing has happened yet. Both seats are in "
            "orbit with no harvester on the ground, two probes each, 250 "
            "blue and no credits. The board is unprobed, no redsign has "
            "blazed, and the score is 0-0. There is no last night, so "
            "there is nothing to remember and nothing to react to."
        ),
        why=(
            "The purest test in the library, and the only one where an "
            "agent's opening theory is the whole answer. Everywhere else "
            "a fork can be carried by the position; here the board is "
            "the same for both seats and the only input is doctrine. "
            "Where does it throw its first two probes, and does it bother "
            "putting a harvester down at all? Being day 1, it is also the "
            "one board where an empty STRATEGY JOURNAL is correct rather "
            "than a bug."
        ),
    ),
    # ── seed 50 (b67deb8d): the contested trio ──────────────────────
    #
    # These three replaced a day-2 and day-3 pair that had to be retired.
    # Their season was minted before minting was reproducible, and their
    # snapshots were taken before `snapshot.take` could copy replay
    # frames on a file store — so they carried no last night, and could
    # not be re-made to fix it because "seed 4242" no longer produced
    # the season they came from. Both faults are fixed at the source;
    # this set is reproducible (`mint(seed=50, days=4)`) and framed.
    "b67deb8d_d2": Note(
        name="Early Redsign Battle · day 2 · dual discovery",
        tests="both seats found the same seam on night one — who commits, who blinks",
        state=(
            "The RED SIGN blazed on night 1 near (~19,~10) — a fat seam, "
            "42 cells — and both seats' opening probes found it. p1 can "
            "see 22 of its cells, p2 15. Nothing has been harvested, "
            "nothing shipped, the score is 0-0, no weapon exists on the "
            "board, and both harvesters are still in orbit with a fresh "
            "rack of 4 probes bought at dawn."
        ),
        why=(
            "A contested seam with symmetric information, which is the "
            "hardest version of the problem: both seats can see it, both "
            "know the other can, and neither has a weapon to settle it. "
            "The interesting divergence is nerve. What actually happened "
            "next is that both committed and p1 won the exchange 6 "
            "parcels to 1 — so there is a known-good answer to beat, and "
            "a known-bad one to avoid."
        ),
    ),
    "b67deb8d_d3": Note(
        name="Beaten to the Seam · day 3",
        tests="you just lost a race 6-to-1, and a second seam is up with you better placed",
        state=(
            "Night 2 was the race for the (~19,~10) seam and p2 lost it. "
            "Both dropped on it — p2 first, at (18,12) — but p2 lifted "
            "after a single parcel while p1 stayed down for six, and the "
            "seam is now spent. p1 shipped 1522, p2 shipped 249. A "
            "second seam blazed mid-night near (~37,~16), 35 cells, and "
            "p2 has the better view of it: 53 cells against p1's 42. p2 "
            "holds 500 credits to p1's 250; both have 4 probes."
        ),
        why=(
            "The board for the question every fork eventually has to "
            "answer: you are behind, you know exactly why, and the next "
            "chance is already on the table. p2 is the seat to cast — it "
            "is losing 6-to-1 but is better placed on the new seam, so "
            "an agent that only reads the scoreboard plays it "
            "differently from one that reads the map. Cast p1 to ask the "
            "opposite question: does a fork defend a lead it did not "
            "plan for?"
        ),
    ),
    "b67deb8d_d4": Note(
        name="Second Wind · day 4",
        tests="the trailing seat just banked the best lift of the game and doubled its fleet",
        state=(
            "Both seats worked the (~37,~16) seam on night 3 and this "
            "time p2 got the better of it: 2 parcels for 1094 against "
            "p1's 5 for 718, closing the score to 2240-1342. p2 spent "
            "everything it had on a second harvester and now runs two to "
            "p1's one, with 0 credits to p1's 750. A third seam blazed "
            "at the very end of the night near (~4,~4), 31 cells, right "
            "across the map from everything that has happened so far."
        ),
        why=(
            "The only board in the library where a fleet is asymmetric, "
            "which changes the question from 'where do I go' to 'do I "
            "split'. p2 can cover the new far seam and hold the middle "
            "at once, and has no credits left if it is wrong; p1 has one "
            "harvester, a healthy lead and enough cash to react. Two "
            "genuinely different problems on the same frozen night."
        ),
    ),
    "1afcd68d_d4": Note(
        name="After the Gold Rush · day 4",
        tests="both seams are spent and p1 has two harvesters — what does an agent do with no jackpot",
        state=(
            "Two redsigns blazed on night 1, near (~30,~3) and (~35,~22), "
            "and both were exhausted by the end of night 2. What is left "
            "is an ordinary map and a close race: p2 leads 2464 to 2112. "
            "p1 has spent everything — no credits, no blue — but fields a "
            "second harvester and holds two parcels and a chaff flare. p2 "
            "has 500 credits, 250 blue, an empty vault and one harvester. "
            "Both have 4 probes; p2 has scouted harder, on 301 cells of "
            "intel to p1's 194."
        ),
        why=(
            "The only board here with no jackpot to chase, which makes it "
            "the control for every other one: an agent that is only ever "
            "tested on redsign nights is being tested on the rarest kind "
            "of night there is. Most turns of most seasons look like "
            "this. It is also the only position with two harvesters on "
            "one seat, so it is the place to find out whether a fork can "
            "actually run a pair or just runs one twice."
        ),
    ),
    "cfa9912d_d6": Note(
        name="Vetus Lantern · day 6 · late redsign race",
        tests="the leader is discovered and cannot hide — blind attack, EMP denial, chaff",
        state=(
            "Three seats, day 6, and the leader is exposed. p1 is ahead on "
            "2901 to p2's 1669 and p3's 1459, and is the only seat still "
            "holding anything — three parcels in the vault against two empty "
            "ones. Both trailing seats spent day 5 watching it: p2 and p3 "
            "each logged five p1 probe launches, so p1's positions are known "
            "ground rather than a guess. The racks are lopsided and nearly "
            "bare. p2 has the only EMP, p1 has the only chaff, and p3 has no "
            "weapon at all — but p3 is the only seat with credits (250) and "
            "blue (250) left to buy one, while p1 has neither and p2 has 50 "
            "blue. Ten probes are down and three redsigns are live."
        ),
        why=(
            "A classic late-night redsign race, and the best board here for "
            "the three things V12 never does: attacking blind, denying with "
            "an EMP, and spending a chaff flare. The leader is discovered "
            "and cannot cover itself, one seat holds the only EMP, and the "
            "only chaff belongs to the seat everyone is chasing. Cast p1 "
            "too: it can see the redsign, so a night where it sits still "
            "is not the night this board is about — testing p2's attack "
            "means something only if the seat being attacked also moves. "
            "Note that p1 was played by a human, so it brings no agent "
            "journal of its own into the turn; it has the engine's record "
            "of last night like everyone else, but no remembered intent."
        ),
        # Every canonical seat, deliberately (v1.42). This was p2/p3 while
        # the reasoning was "p1 has no journal, so casting it compares a
        # fork against a blank history" — true, and beside the point. A
        # frozen turn is a position, and a position with a seat missing
        # resolves a night nobody would have played.
    ),
}


def _parse(session_id: str) -> Optional[tuple[str, int, str]]:
    """Pull ``(source, day, seat)`` out of ``LAB_dd868733_d2_p1``.

    Returns None for anything not shaped like a snapshot, so a stray
    session in the store cannot become a board by accident.
    """
    parts = session_id.split("_")
    if len(parts) < 4:
        return None
    source, day_part, seat = parts[1], parts[-2], parts[-1]
    if not day_part.startswith("d") or not day_part[1:].isdigit():
        return None
    if not (seat.startswith("p") and seat[1:].isdigit()):
        return None
    return source, int(day_part[1:]), seat


#: ``(store, board id) -> (seats, seed)``, cached for the life of the
#: process. Safe to hold forever: a frozen board is frozen, so these are
#: properties of the file, not of when you asked.
#:
#: Keyed by the store as well as the id, because board ids are only
#: unique within a store — a test's temporary store holds boards named
#: exactly like the real ones, and keying on the id alone let an empty
#: one answer for the real lab.
_FACTS: dict[tuple[str, str], tuple[tuple[str, ...], Optional[int]]] = {}


def _facts(store: Any, session_id: str) -> tuple[tuple[str, ...], Optional[int]]:
    """What this board's position actually is: its seats and its seed.

    Costs one session read the first time a board is seen. Worth it for
    the roster alone: the alternative is inferring it from how many board
    rows share a day, which is right for a minted set (a row per seat)
    and wrong for a re-walked one (one row, three seats) — and got a
    3-seat night offered as a 1-seat one. The seed comes along free,
    which is the point of reading rather than typing it.
    """
    key = (str(getattr(store, "dir", "") or id(store)), session_id)
    hit = _FACTS.get(key)
    if hit is not None:
        return hit

    seats: tuple[str, ...] = ()
    seed: Optional[int] = None
    try:
        row = store.load_session(session_id) or {}
        blob = row.get("json_state")
        if isinstance(blob, (str, bytes)):
            blob = json.loads(blob)
        blob = blob or {}
        seats = tuple(blob.get("players") or ())
        raw = blob.get("seed")
        seed = int(raw) if isinstance(raw, (int, float, str)) and str(raw).lstrip("-").isdigit() else None
    except Exception:
        # A board that will not load is a board the launcher should still
        # list — the seat picker degrades, the page does not.
        seats, seed = (), None

    # Only remember an answer, not a failure: a board that would not load
    # this once should be retried, not written off for the process.
    if seats:
        _FACTS[key] = (seats, seed)
    return seats, seed


def discover(store: Any, *, prefix: str = LAB_PREFIX) -> list[Board]:
    """Every frozen board in ``store``, ordered by day then seat.

    Reads the session list, plus one read per board for its roster —
    cached, so a page load pays it once per board per process.
    """
    try:
        rows = store.list_sessions() or []
    except Exception:
        return []

    out: list[Board] = []
    for row in rows:
        sid = str(row.get("session_id") or "")
        if not sid.startswith(prefix):
            continue
        parsed = _parse(sid)
        if parsed is None:
            continue
        source, day, seat = parsed
        seats, seed = _facts(store, sid)
        out.append(
            Board(
                id=sid,
                day=day,
                seat=seat,
                source=source,
                season=str(row.get("season_name") or ""),
                # Keyed by the night — season plus day. A minted night
                # has a board id per seat and a re-walked one has a
                # single id, and both describe the same position, so
                # keying on the id would mean writing a minted night's
                # blurb twice. It is always the second copy that rots.
                note=NOTES.get(f"{source}_d{day}"),
                players=seats,
                seed=seed,
            )
        )
    out.sort(key=lambda b: (b.season, b.day, b.seat))
    return out


def get(board_id: str, store: Any) -> Board:
    """One board by id."""
    for board in discover(store):
        if board.id == board_id:
            return board
    raise KeyError(f"no lab board {board_id!r}")
