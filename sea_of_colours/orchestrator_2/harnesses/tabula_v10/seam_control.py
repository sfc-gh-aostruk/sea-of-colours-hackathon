"""v10 Phase 2 — redsign seam-control PATTERN generator.

This is the heart of "agency-first" redsign poker. Instead of the harness
hard-coding ONE offset drop (Fix A) and hoping the agent copies it, we emit a
MENU of named, fully-resolved tactical PATTERNS around each live redsign. Each
pattern is a multi-wave campaign with pre-filled geometry (probe cells, drop
cells, comb walks), an hour cadence, and a "when to pick me" note. The THINKER
selects and orders pattern IDs by reasoning over ownership / players / weapons;
the resolver expands the chosen IDs back to this concrete geometry for the
mover. Geometry stays deterministic (reliable transcription); strategy moves
into the agent (taught by doctrine, not enforced here).

The two cases (from the user's poker book, weapon-free baseline):

  CASE 1 — the redsign is MINE (I discovered it, engine-truth ``mine=True``):
    * ``SMASH_GRAB``     H1 belly-flop ON the pure (auto-harvest), pick up fast —
                         THE priority; I know where the pure is, move first.
    * ``SECURE_MASS``    H2 a SHORT strip of the visible mass ring from the far
                         side (or re-hit the pure under weapons — agent's call).
    * ``LATE_SWEEP``     H3 a late, bigger pattern over the dense seam.
    Each is one wave = one harvester, so the thinker composes the fleet (and in
    the DUAL case can send later harvesters at a rival beacon instead).

  CASE 2 — NOT my redsign (a rival found it; ``mine`` False/unknown):
    * ``BLIND_GRAB``     supersede the finder's probe, then a short blind drop
                         with pickup ~H4-5 — imprecise smash-and-grab.
    * ``UNBEATEN_FLANK`` a fresh probe on the OPPOSITE axis to the contested
                         approach, longer chain post-EMP (H8-10) — the secured
                         bank away from the pile-up.
    * ``WALK_IN``        outer mop-up: walk in from slightly outside on a third
                         angle late (H11-16); pure red bleeds into good red.

Cadence is nudged by observed weapons (defensive read only, per plan scope):
chaff seen -> keep a backup wave; EMP scar near the seam -> space the waves past
the cloud window and flank the probe OUTSIDE the blast radius.

Patterns are EXEMPT from the nomadic separation filter (they intentionally
cluster on the seam — that is the whole point of a redsign campaign).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from sea_of_colours.orchestrator_2.harnesses.tabula_v7.probe_hints import (
    _comb_path,
    _covers,
    _enemy_probe_cells,
    _grid_dims,
    _known_green_cells,
    _redsign_cells,
    _tier_name,
    _vision_disk,
    _visible_red,
    _PROBE_RADIUS,
    _TIER_MULT,
)
from sea_of_colours.orchestrator_2.harnesses.tabula_v7.validators import (
    _live_vision_cells,
)

try:  # keep geometry honest against the real engine dials when available
    from sea_of_colours.game.weapons import (
        EMP_RADIUS as _EMP_RADIUS,
        EMP_CLOUD_HOURS as _EMP_CLOUD_HOURS,
    )
except Exception:  # pragma: no cover - defensive fallback
    _EMP_RADIUS, _EMP_CLOUD_HOURS = 4, 6

# Chebyshev radius within which a redsign hot-drop / scar is attributed to a
# given beacon (the probe vision half-width).
_REGION_MATCH_RADIUS = 4

# Baseline cadence (hours) — the "poker" timing. Later waves clear the EMP
# window; chaff/EMP reads shift these at build time.
_H_SMASH = 1
_H_BLIND_PICKUP = 4
_H_POST_EMP = 9
_H_WALK_IN = 12

# I4/I6 (secure-the-pure short-grab): wave 1 LANDS on the richest reachable core
# cell (the drop cell is auto-harvested — F7) and takes only a short comb before
# the mover picks up, so the pure banks early instead of riding an exposed
# 6-cell chain. Later waves work the wider seam.
_SHORT_GRAB_STEPS = 2

# SECURE_MASS (CASE-1 H2): a SHORT strip of the visible MASS ring around the
# pure — a secured second bank, not a seam crawl. Trimmed to the floor under
# danger. LATE_SWEEP (H3) is the only own-seam wave allowed a full-length comb.
_MASS_SHORT_STEPS = 3

# BLIND grab sweep (CASE 2, rival beacon we have NOT un-fogged): the broadcast is
# a JITTERED smear, so the single best-guess drop cell is rarely the exact pure.
# A blind grab therefore combs a SHORT sweep across the top smear candidates to
# actually bank the pure — "a bit more than one move". Still bounded (never a
# full seam strip), and danger only trims it to the floor, never to zero: a
# 0-step blind grab lands one guessed cell and usually banks trace for nothing.
_BLIND_SWEEP_STEPS = 3
_BLIND_SWEEP_FLOOR = 2

_DIRS: Dict[str, Tuple[int, int]] = {
    "N": (0, -1), "S": (0, 1), "E": (1, 0), "W": (-1, 0),
    "NE": (1, -1), "NW": (-1, -1), "SE": (1, 1), "SW": (-1, 1),
}
_OPPOSITE = {
    "N": "S", "S": "N", "E": "W", "W": "E",
    "NE": "SW", "SW": "NE", "NW": "SE", "SE": "NW",
}
# A perpendicular "third angle" for WALK_IN, so all three CASE-2 waves attack
# from genuinely different bearings.
_PERP = {
    "N": "E", "S": "W", "E": "S", "W": "N",
    "NE": "SE", "SW": "NW", "NW": "NE", "SE": "SW",
}


def _grab_steps(threat: Mapping[str, Any], *, contested: bool,
                emp: Optional[Tuple[int, int]]) -> int:
    """Danger-gated wave-1 length for a SMASH/BLIND grab.

    The grab is the DROP (auto-harvest); the walk is optional. Under any danger
    — chaff seen, an EMP scar near the seam, or a contested beacon — take ZERO
    extra steps and pick up immediately (secure the jackpot before it can be
    spilled). Only when the board is clearly quiet do we take the short 1-2 step
    tail. This is NOT a seam strip; the wider seam is a later wave / 2nd unit.
    """
    if threat.get("chaff_seen") or emp is not None or contested:
        return 0
    return _SHORT_GRAB_STEPS


def _blind_grab_steps(threat: Mapping[str, Any], *,
                      emp: Optional[Tuple[int, int]]) -> int:
    """Sweep length for a BLIND grab on a rival beacon we cannot see.

    Unlike a SMASH_GRAB (we KNOW the pure -> land straight on it, 0-step is fine),
    a blind grab's drop cell is a GUESS off the jittered smear. It must comb a
    short sweep across the neighbouring smear candidates to actually bank the
    pure — one square rarely nails it. Danger (chaff / EMP) trims the sweep to
    the FLOOR but never to zero (a 0-step blind grab is a wasted, exposed unit).
    """
    if threat.get("chaff_seen") or emp is not None:
        return _BLIND_SWEEP_FLOOR
    return _BLIND_SWEEP_STEPS


# R3 anti-crowd: mirror seats compute the SAME finder-triangulated blind drop,
# so v10-vs-v10-vs-v10 dogpiles the exact cell (mirror d2/d6 mutual-kill). Seat 0
# keeps the triangulated primary; later seats shift both drop AND enabler probe
# by a distinct bearing (same delta -> the probe disk still covers the drop).
_SEAT_RING: List[Tuple[int, int]] = [
    (0, 0), (1, 0), (0, 1), (-1, 0), (0, -1),
    (1, 1), (-1, -1), (1, -1), (-1, 1),
]


def _seat_offset_geom(
    drop: Tuple[int, int],
    probe: Tuple[int, int],
    seat_index: int,
    width: int,
    height: int,
    green: "set",
) -> Tuple[Tuple[int, int], Tuple[int, int]]:
    """Fan a CASE-2 blind grab by seat so mirror seats don't stack one cell.

    Applies the SAME bearing delta to ``drop`` and ``probe`` (coverage preserved),
    clamped in-bounds, skipping the shift if the drop would land on known green.
    Seat 0 (or any offset that resolves to no move) returns the inputs unchanged.
    """
    if seat_index <= 0:
        return drop, probe
    dx, dy = _SEAT_RING[seat_index % len(_SEAT_RING)]
    if (dx, dy) == (0, 0):
        return drop, probe
    ndrop = (_clamp(drop[0] + dx, 0, width - 1), _clamp(drop[1] + dy, 0, height - 1))
    if ndrop in green or ndrop == drop:
        return drop, probe
    nprobe = (
        _clamp(probe[0] + dx, 0, width - 1),
        _clamp(probe[1] + dy, 0, height - 1),
    )
    return ndrop, nprobe


def _sign(v: float) -> int:
    return (v > 0) - (v < 0)


def _clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


def _dir_name(frm: Tuple[int, int], to: Tuple[int, int]) -> str:
    """8-way compass bearing from ``frm`` toward ``to`` (defaults to E)."""
    dx, dy = _sign(to[0] - frm[0]), _sign(to[1] - frm[1])
    for name, vec in _DIRS.items():
        if vec == (dx, dy):
            return name
    return "E"


@dataclass
class SeamWave:
    """One resolved wave of a seam pattern — ready for the mover to package."""

    wave: int
    earliest_hour: int
    drop_at: Tuple[int, int]
    comb_path: List[Tuple[int, int]] = field(default_factory=list)
    probe_at: Optional[Tuple[int, int]] = None
    supersede: Optional[Tuple[int, int]] = None
    direction: str = ""
    unit_ordinal: int = 0
    note: str = ""
    pickup_after: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "wave": self.wave,
            "earliest_hour": self.earliest_hour,
            "drop_at": [int(self.drop_at[0]), int(self.drop_at[1])],
            "comb_path": [[int(x), int(y)] for x, y in self.comb_path],
            "pickup_after": bool(self.pickup_after),
            "probe_at": (
                [int(self.probe_at[0]), int(self.probe_at[1])]
                if self.probe_at is not None else None
            ),
            "supersede": (
                [int(self.supersede[0]), int(self.supersede[1])]
                if self.supersede is not None else None
            ),
            "direction": self.direction,
            "unit_ordinal": self.unit_ordinal,
            "note": self.note,
        }


@dataclass
class SeamPattern:
    """A named, multi-wave redsign campaign the thinker can select by ID."""

    pattern_id: str
    kind: str
    beacon: Tuple[int, int]
    mine: Optional[bool]
    title: str
    when: str
    rationale: str
    waves: List[SeamWave] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pattern_id": self.pattern_id,
            "kind": self.kind,
            "beacon": [int(self.beacon[0]), int(self.beacon[1])],
            "mine": self.mine,
            "title": self.title,
            "when": self.when,
            "rationale": self.rationale,
            "waves": [w.to_dict() for w in self.waves],
        }

    def menu_line(self) -> str:
        """One compact line for the option menu the thinker reads."""
        bx, by = self.beacon
        return (
            f"  [{self.pattern_id}] {self.title} @({bx},{by}) — {self.when}"
        )

    def execute_block(self) -> str:
        """A verbatim EXECUTE recipe for the mover once this pattern is chosen."""
        bx, by = self.beacon
        lines = [f"{self.pattern_id} — {self.title} (redsign @({bx},{by})):"]
        for w in self.waves:
            head = f"  wave {w.wave} @H{w.earliest_hour}+"
            bits: List[str] = []
            if w.supersede is not None:
                bits.append(
                    f"SUPERSEDE probe at ({w.supersede[0]},{w.supersede[1]})"
                )
            if w.probe_at is not None:
                bits.append(f"probe ({w.probe_at[0]},{w.probe_at[1]})")
            bits.append(f"drop ({w.drop_at[0]},{w.drop_at[1]})")
            if w.comb_path:
                walk = " ".join(f"({x},{y})" for x, y in w.comb_path)
                bits.append(f"walk {walk}")
            elif w.pickup_after:
                bits.append("walk NONE")
            if w.pickup_after:
                bits.append("PICK UP NOW (fast grab — do not linger)")
            note = f"  [{w.note}]" if w.note else ""
            lines.append(f"{head} {'; '.join(bits)}{note}")
        return "\n".join(lines)


# ── redsign / weapon context ───────────────────────────────────────────
def _redsign_regions(agent_view: Mapping[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in (agent_view.get("redsign") or []):
        if not isinstance(r, Mapping):
            continue
        c = r.get("center")
        if isinstance(c, (list, tuple)) and len(c) == 2:
            try:
                out.append({
                    "center": (int(round(float(c[0]))), int(round(float(c[1])))),
                    "mine": bool(r.get("mine")) if "mine" in r else None,
                })
            except (TypeError, ValueError):
                continue
    return out


def _threat_context(agent_view: Mapping[str, Any]) -> Dict[str, Any]:
    """Coarse, defensive-only weapon read from the last-night recap.

    ``emp_cells``  — live EMP scar centres (route/flank outside their blast).
    ``chaff_seen`` — a chaff jam hit us last night (keep a backup wave).
    """
    recap = agent_view.get("last_night") or {}
    emp_cells: List[Tuple[int, int]] = []
    for scar in (recap.get("emp_scars") or []):
        at = scar.get("at") if isinstance(scar, Mapping) else None
        if isinstance(at, (list, tuple)) and len(at) == 2:
            try:
                emp_cells.append((int(at[0]), int(at[1])))
            except (TypeError, ValueError):
                continue
    chaff_seen = False
    for atk in (recap.get("incoming_attacks") or []):
        if isinstance(atk, Mapping) and "chaff" in str(atk.get("type") or "").lower():
            chaff_seen = True
    return {"emp_cells": emp_cells, "chaff_seen": chaff_seen}


def _emp_near(beacon: Tuple[int, int], emp_cells: Sequence[Tuple[int, int]]) -> Optional[Tuple[int, int]]:
    """The closest EMP scar within blast+match range of the beacon, if any."""
    best: Optional[Tuple[float, Tuple[int, int]]] = None
    for c in emp_cells:
        d = max(abs(c[0] - beacon[0]), abs(c[1] - beacon[1]))
        if d <= _EMP_RADIUS + _REGION_MATCH_RADIUS and (best is None or d < best[0]):
            best = (d, c)
    return None if best is None else best[1]


# ── geometry ───────────────────────────────────────────────────────────
def enumerate_value_ring(
    agent_view: Mapping[str, Any],
    beacon: Tuple[int, int],
    probe_at: Tuple[int, int],
    *,
    max_cells: int = 8,
) -> List[Dict[str, Any]]:
    """Drop-legal value cells inside ``probe_at``'s disk, richest-first.

    value = (probe Euclidean disk) INTERSECT (visible red purity OR redsign
    smear). Ranked by ``purity x tier`` then proximity to the beacon (the pure
    seam is densest at the broadcast centre). Redsign smear cells with no
    visible purity are treated as pure(255) candidates — that IS what the
    beacon advertises.
    """
    width, height = _grid_dims(agent_view)
    disk = set(_vision_disk(probe_at[0], probe_at[1], width, height))
    red = _visible_red(agent_view)
    smear = _redsign_cells(agent_view)
    ranked: List[Tuple[float, int, Tuple[int, int]]] = []
    for cell in disk:
        purity = red.get(cell)
        if purity is None and cell in smear:
            purity = 255
        if not purity:
            continue
        tier = _tier_name(int(purity))
        score = float(purity) * _TIER_MULT.get(tier, 1.0)
        # nearer the beacon breaks ties (denser seam).
        prox = -(abs(cell[0] - beacon[0]) + abs(cell[1] - beacon[1]))
        ranked.append((score, prox, cell))
    ranked.sort(key=lambda t: (t[0], t[1]), reverse=True)
    out: List[Dict[str, Any]] = []
    for score, _prox, cell in ranked[:max_cells]:
        purity = red.get(cell) or 255
        out.append({
            "at": [int(cell[0]), int(cell[1])],
            "purity": int(purity),
            "tier": _tier_name(int(purity)),
            "score": round(score, 1),
        })
    return out


def _flank_probe(
    beacon: Tuple[int, int],
    direction: str,
    width: int,
    height: int,
    *,
    dist: int = 3,
    avoid_center: Optional[Tuple[int, int]] = None,
) -> Tuple[int, int]:
    """A fresh probe cell off the beacon along ``direction`` that COVERS it.

    Drop-legality is mandatory: the returned probe always keeps the beacon
    inside its Euclidean r4 disk (so a drop there is legal) and is never the
    beacon itself (anti-crush). A DIAGONAL direction can only reach ~2 cells
    before leaving the disk, so we cap the reach per direction and search from
    the farthest covering cell inward. Clearing an EMP blast is best-effort: we
    return the farthest covering cell that also clears the blast, else the
    farthest covering cell.
    """
    vec = _DIRS.get(direction, (1, 0))
    step_len = (vec[0] ** 2 + vec[1] ** 2) ** 0.5 or 1.0
    # Max whole steps that keep the beacon inside the Euclidean r4 disk.
    max_cover = max(1, int(_PROBE_RADIUS / step_len))
    hi = max(1, min(int(dist), max_cover))
    farthest_cover: Optional[Tuple[int, int]] = None
    for d in range(hi, 0, -1):
        px = _clamp(beacon[0] + vec[0] * d, 0, width - 1)
        py = _clamp(beacon[1] + vec[1] * d, 0, height - 1)
        cand = (px, py)
        if cand == beacon or not _covers(px, py, beacon[0], beacon[1]):
            continue
        if farthest_cover is None:
            farthest_cover = cand
        clear = (
            avoid_center is None
            or max(abs(px - avoid_center[0]), abs(py - avoid_center[1])) > _EMP_RADIUS
        )
        if clear:
            return cand
    if farthest_cover is not None:
        return farthest_cover
    # Last resort: one step along the direction (covers unless it lands on the
    # beacon after clamping, in which case nudge east).
    px = _clamp(beacon[0] + vec[0], 0, width - 1)
    py = _clamp(beacon[1] + vec[1], 0, height - 1)
    if (px, py) == beacon:
        px = _clamp(beacon[0] + 1, 0, width - 1)
    return (px, py)


def _drop_toward(
    beacon: Tuple[int, int],
    probe_at: Tuple[int, int],
    width: int,
    height: int,
) -> Tuple[int, int]:
    """A drop cell one step off the beacon toward the probe (drop-legal, seam)."""
    dx, dy = _sign(probe_at[0] - beacon[0]), _sign(probe_at[1] - beacon[1])
    cand = (_clamp(beacon[0] + dx, 0, width - 1), _clamp(beacon[1] + dy, 0, height - 1))
    if cand != probe_at and _covers(probe_at[0], probe_at[1], cand[0], cand[1]):
        return cand
    return beacon


def _value_drop(
    agent_view: Mapping[str, Any],
    beacon: Tuple[int, int],
    probe_at: Tuple[int, int],
    width: int,
    height: int,
) -> Tuple[int, int]:
    """The RICHEST drop-legal cell in ``probe_at``'s disk, else geometric.

    Flank/walk-in waves used to drop one geometric step off the JITTERED beacon
    (``_drop_toward``) — a blind guess that ignored the live purity the wave's
    own probe reveals ("blind walk of its own live"). When we actually have
    vision (own redsign) or a smear to triangulate (rival redsign),
    :func:`enumerate_value_ring` ranks the cells in the probe's disk by live
    value; land on the best one. We skip the probe centre so the wave never
    self-crushes the probe it just launched to enable the drop; if the only
    value sits on the centre we fall back to the geometric seam cell.
    """
    for cand in enumerate_value_ring(agent_view, beacon, probe_at, max_cells=6):
        at = cand.get("at")
        if not isinstance(at, (list, tuple)) or len(at) != 2:
            continue
        cell = (int(at[0]), int(at[1]))
        if cell != probe_at:
            return cell
    return _drop_toward(beacon, probe_at, width, height)


def _own_active_probe_centers(agent_view: Mapping[str, Any]) -> List[Tuple[int, int]]:
    """Live friendly probe cells — each makes its Euclidean r4 disk drop-legal."""
    out: List[Tuple[int, int]] = []
    ents = (agent_view.get("entities") or {}).get("mine") or []
    for e in ents:
        if not isinstance(e, Mapping) or str(e.get("type") or "") != "probe":
            continue
        nr = e.get("nights_remaining")
        if isinstance(nr, (int, float)) and int(nr) <= 0:
            continue
        pos = e.get("pos") or e.get("at")
        if isinstance(pos, (list, tuple)) and len(pos) == 2:
            try:
                out.append((int(pos[0]), int(pos[1])))
            except (TypeError, ValueError):
                continue
    return out


def _drop_legal_now(agent_view: Mapping[str, Any], cell: Tuple[int, int]) -> bool:
    """True iff a live friendly probe already covers ``cell`` (drop-straight OK)."""
    return any(
        _covers(cx, cy, cell[0], cell[1])
        for (cx, cy) in _own_active_probe_centers(agent_view)
    )


# ── walk-in-from-live geometry (no probe needed) ────────────────────────
# The engine gates only the INITIAL drop on live/echo coverage; every STEP
# afterward is unrestricted (it just cannot land on green). So an echo pure
# that sits OUTSIDE live coverage is still reachable on foot: drop on the
# nearest live-legal, non-green frontier cell and WALK IN through fog to the
# pure — no fresh probe required. This is the fix for the "0 moves" strand
# (probe_stock=0 + echo pure => menu offered only undroppable probe-drops).
_HOLD_CAP_STEPS = 5  # drop + up to 5 steps = 6-parcel hold (RULEBOOK §3)


def _live_cells(agent_view: Mapping[str, Any]) -> "set":
    try:
        return set(_live_vision_cells(agent_view))
    except Exception:  # pragma: no cover - defensive
        return set()


def _walk_path_to(
    start: Tuple[int, int],
    goal: Tuple[int, int],
    green: "set",
    width: int,
    height: int,
    max_steps: int,
) -> Optional[List[Tuple[int, int]]]:
    """Shortest NSEW path ``start``->``goal`` (<= ``max_steps`` steps) whose STEP
    cells avoid green. Returns the ordered step cells (excluding ``start``,
    INCLUDING ``goal``) or ``None`` if the goal is unreachable within budget.
    """
    if start == goal:
        return []
    from collections import deque
    prev: Dict[Tuple[int, int], Optional[Tuple[int, int]]] = {start: None}
    q = deque([start])
    while q:
        cur = q.popleft()
        for dx, dy in _NSEW_ORDER:
            nc = (cur[0] + dx, cur[1] + dy)
            if not (0 <= nc[0] < width and 0 <= nc[1] < height) or nc in prev:
                continue
            if nc != goal and nc in green:
                continue  # steps may not land on a green hazard
            prev[nc] = cur
            if nc == goal:
                path: List[Tuple[int, int]] = []
                node: Optional[Tuple[int, int]] = nc
                while node is not None and prev[node] is not None:
                    path.append(node)
                    node = prev[node]
                path.reverse()
                return path if len(path) <= max_steps else None
            q.append(nc)
    return None


def _walkin_from_live(
    agent_view: Mapping[str, Any],
    pure: Tuple[int, int],
    green: "set",
    width: int,
    height: int,
    *,
    avoid_drops: "set" = frozenset(),
    max_steps: int = _HOLD_CAP_STEPS,
) -> Optional[Tuple[Tuple[int, int], List[Tuple[int, int]]]]:
    """Nearest live-legal, non-green frontier cell that can WALK to ``pure``.

    Returns ``(drop_cell, path_to_pure)`` where the path ends ON the pure
    (auto-harvested on arrival) or ``None`` when the pure is not walkable from
    any live cell within the hold budget. ``avoid_drops`` lets a second wave
    pick a DIFFERENT frontier so the two harvesters approach on disjoint paths.
    """
    live = _live_cells(agent_view)
    cands = [
        c for c in live
        if c not in green and c != pure and c not in avoid_drops
    ]
    # nearest first (short walk = fewer hours exposed), deterministic tie-break.
    cands.sort(key=lambda c: (abs(c[0] - pure[0]) + abs(c[1] - pure[1]), c[1], c[0]))
    for drop in cands[:32]:
        path = _walk_path_to(drop, pure, green, width, height, max_steps)
        if path is not None:
            return drop, path
    return None


def _mass_tail(
    agent_view: Mapping[str, Any],
    frm: Tuple[int, int],
    green: "set",
    width: int,
    height: int,
    used: "set",
    n: int,
) -> List[Tuple[int, int]]:
    """Extend a walk past the pure into the surrounding MASS (up to ``n`` steps).

    Mass usually rings the pure, so after banking the pure we keep walking to
    grab it: prefer visible-red neighbours (richest first), else blind-walk the
    ring (any non-green neighbour) since the halo is usually there. Contiguous
    NSEW steps only; never revisits a used/green cell.
    """
    red = _visible_red(agent_view)
    tail: List[Tuple[int, int]] = []
    cur = frm
    seen = set(used) | {frm}
    for _ in range(max(0, n)):
        nbrs = [
            (cur[0] + dx, cur[1] + dy) for dx, dy in _NSEW_ORDER
        ]
        nbrs = [
            c for c in nbrs
            if 0 <= c[0] < width and 0 <= c[1] < height
            and c not in green and c not in seen
        ]
        if not nbrs:
            break
        # richest visible red first; else the ring cell nearest to staying put
        nbrs.sort(key=lambda c: (-int(red.get(c, 0)), abs(c[0] - frm[0]) + abs(c[1] - frm[1])))
        nxt = nbrs[0]
        tail.append(nxt)
        seen.add(nxt)
        cur = nxt
    return tail


_NSEW_ORDER = ((1, 0), (-1, 0), (0, 1), (0, -1))


def _known_core(
    agent_view: Mapping[str, Any],
    beacon: Tuple[int, int],
    *,
    radius: int = 6,
) -> Optional[Tuple[Tuple[int, int], int]]:
    """The pure you already REVEALED: richest VISIBLE-red cell near the beacon.

    A redsign that is mine (or otherwise in our LOS) means a friendly probe has
    already un-fogged the pure — so we know its exact cell and do not need to
    re-probe blindly toward the jittered smear. Returns ``(cell, purity)`` of the
    top purity x tier cell within Chebyshev ``radius`` of the beacon, or ``None``
    when nothing red is visible there yet (pure still fogged -> blind geometry).
    """
    red = _visible_red(agent_view)
    best: Optional[Tuple[float, int, Tuple[int, int]]] = None
    for cell, purity in red.items():
        if max(abs(cell[0] - beacon[0]), abs(cell[1] - beacon[1])) > radius:
            continue
        tier = _tier_name(int(purity))
        score = float(purity) * _TIER_MULT.get(tier, 1.0)
        if best is None or score > best[0]:
            best = (score, int(purity), cell)
    return None if best is None else (best[2], best[1])


def _wave1_grab_geometry(
    agent_view: Mapping[str, Any],
    beacon: Tuple[int, int],
    hint: Mapping[str, Any],
    *,
    force_probe: bool = False,
) -> Tuple[Tuple[int, int], Tuple[int, int], Optional[Tuple[int, int]], List[Tuple[int, int]]]:
    """Resolve wave-1 grab geometry: (drop, probe_context, wave1_probe, value_cells).

    The GRAB is the DROP — it must LAND ON the pure. If a friendly probe has
    already revealed the pure (``_known_core``), we drop STRAIGHT on that exact
    cell (no fresh probe) whenever it is currently drop-legal; only add a covering
    probe when the pure is revealed but no longer disk-covered. When the pure is
    still fogged we fall back to the hint's blind fog geometry (a probe near the
    smear, drop on the best in-disk cell). ``force_probe`` keeps a wave-1 probe
    for the contested rival case (we stage behind our own fresh probe).
    """
    width, height = _grid_dims(agent_view)
    core = _known_core(agent_view, beacon)
    if core is not None:
        drop1 = core[0]
        covering = [
            p for p in _own_active_probe_centers(agent_view)
            if _covers(p[0], p[1], drop1[0], drop1[1])
        ]
        if covering and not force_probe:
            wave1_probe: Optional[Tuple[int, int]] = None
            probe_ctx = covering[0]
        else:
            probe_ctx = _flank_probe(drop1, "E", width, height)
            wave1_probe = probe_ctx
        ring = enumerate_value_ring(agent_view, beacon, probe_ctx)
    else:
        probe_ctx = tuple(hint.get("probe_at") or _flank_probe(beacon, "E", width, height))
        ring = enumerate_value_ring(agent_view, beacon, probe_ctx)
        drop1 = _best_core_cell(ring, probe_ctx, beacon)
        wave1_probe = None if tuple(drop1) in _visible_red(agent_view) else probe_ctx
    value_cells = [tuple(c["at"]) for c in ring] or list(_redsign_cells(agent_view).keys())
    return drop1, probe_ctx, wave1_probe, value_cells


def _freshest_enemy_probe_in_smear(
    agent_view: Mapping[str, Any], beacon: Tuple[int, int],
) -> Optional[Tuple[int, int]]:
    """The freshest enemy probe cell sitting INSIDE the redsign smear (M3).

    A rival beacon is minted BY a rival probe that landed on/near the pure, and
    that launch is PUBLIC (§3.15 — surfaced via ``_enemy_probe_cells`` now that
    the seed-69 E2 view/merge bug is fixed). So the discoverer's probe is the
    single best triangulation anchor we have for the fogged pure: the pure is
    within the probe's r4 disk. Returns the freshest such cell within the beacon
    match radius, or ``None`` when no enemy probe is known there (true blind).
    """
    for e in _enemy_probe_cells(agent_view):  # freshest first
        at = e.get("at") if isinstance(e, Mapping) else None
        if not (isinstance(at, (list, tuple)) and len(at) == 2):
            continue
        try:
            c = (int(at[0]), int(at[1]))
        except (TypeError, ValueError):
            continue
        if max(abs(c[0] - beacon[0]), abs(c[1] - beacon[1])) <= _REGION_MATCH_RADIUS:
            return c
    return None


def _triangulated_blind_geometry(
    agent_view: Mapping[str, Any],
    beacon: Tuple[int, int],
    finder: Tuple[int, int],
) -> Tuple[Tuple[int, int], Tuple[int, int], List[Tuple[int, int]]]:
    """CASE-2 blind grab geometry anchored to the FINDER's probe (M3).

    Instead of guessing off the jittered beacon centre, we approach from the
    finder's bearing (our fresh probe covers the beacon from their side, so it
    un-fogs the same pure pocket) and DROP on the smear/red candidate closest to
    the finder's probe — that is where the discoverer's own drop revealed the
    pure. Returns ``(drop, probe, value_cells)``.
    """
    width, height = _grid_dims(agent_view)
    approach_dir = _dir_name(beacon, finder)
    probe1 = _flank_probe(beacon, approach_dir, width, height)
    ring = enumerate_value_ring(agent_view, beacon, probe1)
    # Drop on the in-disk candidate NEAREST the finder's probe (highest pure
    # likelihood), never the probe cell itself (anti-crush).
    best: Optional[Tuple[int, Tuple[int, int]]] = None
    for c in ring:
        at = c.get("at")
        if not (isinstance(at, (list, tuple)) and len(at) == 2):
            continue
        cell = (int(at[0]), int(at[1]))
        if cell == tuple(probe1):
            continue
        d = abs(cell[0] - finder[0]) + abs(cell[1] - finder[1])
        if best is None or d < best[0]:
            best = (d, cell)
    drop1 = best[1] if best is not None else _drop_toward(beacon, probe1, width, height)
    value_cells = [tuple(c["at"]) for c in ring] or list(_redsign_cells(agent_view).keys())
    return drop1, probe1, value_cells


def _best_core_cell(
    ring: Sequence[Mapping[str, Any]],
    probe_at: Tuple[int, int],
    beacon: Tuple[int, int],
) -> Tuple[int, int]:
    """The richest cell to LAND ON for wave 1 (I4/I6 + F7 auto-harvest).

    ``ring`` is already ranked purity x tier descending and every cell sits in
    ``probe_at``'s disk (drop-legal). We pick the top cell that isn't the probe
    cell itself (anti-crush) so the harvester drops directly ON the pure/mass
    core and banks it as free parcel #1, rather than landing on a trace edge and
    walking in (the F5 zero-pures signature). Falls back to the beacon when the
    ring is empty (no visible/broadcast value in the disk).
    """
    for c in ring:
        at = c.get("at")
        if not (isinstance(at, (list, tuple)) and len(at) == 2):
            continue
        cell = (int(at[0]), int(at[1]))
        if cell != tuple(probe_at):
            return cell
    return beacon


# ── pattern builders ───────────────────────────────────────────────────
def _hint_beacon(hint: Mapping[str, Any]) -> Optional[Tuple[int, int]]:
    d = hint.get("drop_at")
    if isinstance(d, (list, tuple)) and len(d) == 2:
        try:
            return int(d[0]), int(d[1])
        except (TypeError, ValueError):
            return None
    return None


def _match_hint(
    beacon: Tuple[int, int], hints: Sequence[Mapping[str, Any]],
) -> Optional[Mapping[str, Any]]:
    """The redsign hot-drop hint nearest ``beacon`` within the match radius.

    A live region uses its matching hint for richer geometry (probe_at,
    supersede, contested, live drop targeting). A fogged region with no hint
    falls back to a synthesised centre hint in :func:`build_seam_menu`.
    """
    best: Optional[Tuple[int, Mapping[str, Any]]] = None
    for h in hints:
        b = _hint_beacon(h)
        if b is None:
            continue
        d = max(abs(b[0] - beacon[0]), abs(b[1] - beacon[1]))
        if d <= _REGION_MATCH_RADIUS and (best is None or d < best[0]):
            best = (d, h)
    return None if best is None else best[1]


def _match_mine(
    beacon: Tuple[int, int], regions: Sequence[Mapping[str, Any]],
) -> Optional[bool]:
    best: Optional[Tuple[float, Optional[bool]]] = None
    for r in regions:
        ctr = r.get("center")
        if not isinstance(ctr, tuple):
            continue
        d = max(abs(beacon[0] - ctr[0]), abs(beacon[1] - ctr[1]))
        if d <= _REGION_MATCH_RADIUS and (best is None or d < best[0]):
            best = (d, r.get("mine"))
    return None if best is None else best[1]


def _walkin_mine_patterns(
    agent_view: Mapping[str, Any],
    beacon: Tuple[int, int],
    pure: Tuple[int, int],
    first: Tuple[Tuple[int, int], List[Tuple[int, int]]],
    threat: Mapping[str, Any],
    *,
    width: int,
    height: int,
    green: "set",
    emp: Optional[Tuple[int, int]],
    spacing: int,
    weapons: bool,
) -> List[SeamPattern]:
    """CASE 1, WALK-IN mode — the (echo) pure is known but sits OUTSIDE live
    coverage, and there is a live frontier cell we can WALK in from (no fresh
    probe needed; steps are not vision-gated).

    A direct smash-grab is EMP-proof (the drop resolves in one hour) — but a
    WALK to the pure spans hours, so EMP can interdict it. The pure is too
    valuable to trust to one interdictable chain, so we DOUBLE-WALK it:

      * ``WALKIN_GRAB``   H1 — drop on the nearest live frontier, walk straight
                          onto the pure, grab, pick up FAST (secure it first).
      * ``WALKIN_SECURE`` staggered — a SECOND harvester walks the SAME pure from
                          a different frontier (EMP hedge: if H1 was jammed this
                          still banks the jackpot; if H1 succeeded you knowingly
                          take a green — worth it) then reaches into the MASS.
      * ``WALKIN_LATE``   late — a third, staggered walk-in to the pure that then
                          sweeps the surrounding mass halo.
    """
    drop1, path1 = first
    dir1 = _dir_name(drop1, pure)
    grab = SeamPattern(
        pattern_id="WALKIN_GRAB",
        kind="WALKIN_GRAB",
        beacon=beacon,
        mine=True,
        title="Walk-in grab your pure (H1)",
        when=f"drop live @({drop1[0]},{drop1[1]}), walk onto the pure, grab fast",
        rationale=(
            "The pure is yours but sits outside a live probe disk. The initial "
            "drop needs live coverage; steps do NOT — so land on the nearest "
            "live frontier cell and WALK straight onto the pure (auto-harvest), "
            "then pick up immediately. No probe needed. THE priority move."
        ),
        waves=[SeamWave(
            1, _H_SMASH, drop1, list(path1), probe_at=None,
            direction=dir1, unit_ordinal=0, pickup_after=True,
            note=(
                "drop on the LIVE frontier cell, then walk the fog steps onto "
                "your pure and PICK UP FAST — a walk-in can be EMP-jammed, so "
                "WALKIN_SECURE doubles it for safety"
            ),
        )],
    )
    patterns = [grab]

    used = {drop1, *path1}
    second = _walkin_from_live(
        agent_view, pure, green, width, height, avoid_drops=used,
    )
    if second is not None:
        drop2, path2 = second
        tail_budget = max(0, _HOLD_CAP_STEPS - len(path2))
        tail_n = _SHORT_GRAB_STEPS if weapons else tail_budget
        tail2 = _mass_tail(
            agent_view, pure, green, width, height,
            used | {drop2, *path2}, min(tail_budget, tail_n),
        )
        note2 = (
            "SECOND walk-in onto the SAME pure from a different frontier — the "
            "EMP hedge. If the H1 grab was jammed, this banks the jackpot; if it "
            "already landed, re-hitting takes a green (worth it to be SURE). "
            "After the pure, walk on into the surrounding MASS"
        )
        patterns.append(SeamPattern(
            pattern_id="WALKIN_SECURE",
            kind="WALKIN_SECURE",
            beacon=beacon,
            mine=True,
            title="Double-walk the pure + mass (EMP hedge)",
            when="2nd harvester: re-walk the pure from another angle, then mass",
            rationale=(
                "A walk-in is interdictable; the pure is too valuable to risk on "
                "one chain. A second harvester walks the same pure from a "
                "disjoint frontier and, once it is banked, reaches into the mass "
                "ring that usually surrounds the pure."
            ),
            waves=[SeamWave(
                1, _H_POST_EMP + spacing, drop2, list(path2) + tail2,
                probe_at=None, direction=_dir_name(drop2, pure),
                unit_ordinal=1, pickup_after=True, note=note2,
            )],
        ))

    third = _walkin_from_live(
        agent_view, pure, green, width, height,
        avoid_drops=used | (set(second[1]) | {second[0]} if second else set()),
    )
    if third is not None:
        drop3, path3 = third
        tail3 = _mass_tail(
            agent_view, pure, green, width, height,
            used | {drop3, *path3}, max(0, _HOLD_CAP_STEPS - len(path3)),
        )
        patterns.append(SeamPattern(
            pattern_id="WALKIN_LATE",
            kind="WALKIN_LATE",
            beacon=beacon,
            mine=True,
            title="Late walk-in the seam (pure + mass halo)",
            when="3rd harvester / late: walk the pure then sweep the mass halo",
            rationale=(
                "A late third-bearing walk-in scoops the pure and the wider mass "
                "once the early grabs are committed, and leaves great vision for "
                "tomorrow."
            ),
            waves=[SeamWave(
                1, _H_WALK_IN + spacing, drop3, list(path3) + tail3,
                probe_at=None, direction=_dir_name(drop3, pure),
                unit_ordinal=2, pickup_after=True,
                note="late, staggered; walk the pure then blind-walk the halo",
            )],
        ))
    return patterns


def _mine_patterns(
    agent_view: Mapping[str, Any],
    hint: Mapping[str, Any],
    beacon: Tuple[int, int],
    threat: Mapping[str, Any],
    *,
    probe_stock: int = 99,
) -> List[SeamPattern]:
    """CASE 1 — I found it. THREE per-harvester options, chosen by how the pure
    is REACHABLE this night:

      * pure is drop-legal NOW (a live probe covers it) -> the classic EMP-proof
        ``SMASH_GRAB`` (belly-flop) + ``SECURE_MASS`` + ``LATE_SWEEP``.
      * pure is fogged/echo but WALKABLE from a live frontier (no probe) -> the
        ``WALKIN_*`` trio (drop live, walk in; double-walk the pure vs EMP).
      * pure is fogged/echo, not walkable, but we hold a probe -> the probe-
        flanked trio (existing geometry).
      * pure is fogged/echo, not walkable, and NO probe -> [] (starvation; the
        thinker spends the fleet elsewhere rather than on undroppable geometry).

    Each pattern is ONE wave = ONE harvester, so the thinker composes the fleet
    itself (and, in the DUAL case, can send later harvesters at a rival beacon).
    """
    width, height = _grid_dims(agent_view)
    green = _known_green_cells(agent_view)
    emp = _emp_near(beacon, threat.get("emp_cells") or [])
    spacing = _EMP_CLOUD_HOURS if emp else 0
    contested = bool(hint.get("contested"))
    weapons = bool(threat.get("chaff_seen")) or emp is not None

    # Reachability fork: a KNOWN pure (live or echo) that is NOT drop-legal now
    # is still walkable from the live frontier — prefer that over burning a probe
    # (and it is the ONLY play when probe_stock is 0, the "0 moves" strand).
    core = _known_core(agent_view, beacon)
    if core is not None and not _drop_legal_now(agent_view, core[0]):
        walk = _walkin_from_live(agent_view, core[0], green, width, height)
        if walk is not None:
            return _walkin_mine_patterns(
                agent_view, beacon, core[0], walk, threat,
                width=width, height=height, green=green, emp=emp,
                spacing=spacing, weapons=weapons,
            )
        if probe_stock < 1:
            # Echo pure, no live frontier to walk from, no probe to light it —
            # genuinely unreachable this night. Offer nothing rather than a
            # bare drop the sanitizer will silently delete.
            return []
    elif core is None and probe_stock < 1:
        # Own redsign still fully fogged (no live/echo pure to walk to) and no
        # probe to light it — the flanked trio below would be all probe-drops
        # the packager can't emit. Starvation: offer nothing.
        return []

    # ── H1 SMASH_GRAB — the GRAB is the DROP: LAND on the pure/mass core
    # (auto-harvested, F7) and SECURE it FAST. Length is DANGER-GATED (0 steps
    # under threat/contest). DROP-FIRST: this redsign is MINE, so a friendly probe
    # already revealed the pure — land on that EXACT cell and drop STRAIGHT when it
    # is already covered (never re-probe to a fog cell short of the pure).
    drop1, probe1, wave1_probe, value_cells = _wave1_grab_geometry(
        agent_view, beacon, hint,
    )
    grab_steps = _grab_steps(threat, contested=contested, emp=emp)
    comb1 = _comb_path(
        probe1[0], probe1[1], drop1, width, height, green, value_cells,
        max_steps=grab_steps,
    )
    core_visioned = wave1_probe is None
    approach = _dir_name(probe1, beacon)
    note1 = (
        "you know the pure — DROP ON the core cell (it auto-harvests = the grab) "
        "and PICK UP FAST to bank it before rivals arrive"
    )
    if core_visioned:
        note1 += "; it is already in live vision, so drop STRAIGHT (no probe)"
    if grab_steps == 0:
        note1 += "; danger present -> take ZERO extra steps, just drop + pickup"
    if threat.get("chaff_seen"):
        note1 += " (chaff about: keep SECURE_MASS as your backup)"
    smash = SeamPattern(
        pattern_id="SMASH_GRAB",
        kind="SMASH_GRAB",
        beacon=beacon,
        mine=True,
        title="Smash-and-grab your pure (H1)",
        when="H1: land ON your pure, auto-harvest the jackpot, pick up fast",
        rationale=(
            "Engine-truth says this beacon is yours, so you already know where "
            "the pure sits. Landing H1 immediately banks it before any rival can "
            "converge. This is THE priority move — always take it first."
        ),
        waves=[SeamWave(
            1, _H_SMASH, drop1, comb1, probe_at=wave1_probe,
            direction=approach, unit_ordinal=0, note=note1, pickup_after=True,
        )],
    )

    # ── H2 SECURE_MASS — a SHORT strip of the visible MASS ring around the pure.
    # The pure is one cell; the points live in the mass around it. Under weapons
    # the agent may instead RE-HIT the pure for safety (doctrine — geometry stays
    # the mass strip so the two harvesters never share the pure cell).
    d2 = _OPPOSITE.get(approach, "W")
    probe2 = _flank_probe(beacon, d2, width, height, avoid_center=emp)
    drop2 = _value_drop(agent_view, beacon, probe2, width, height)
    mass_steps = _SHORT_GRAB_STEPS if (contested or weapons) else _MASS_SHORT_STEPS
    comb2 = _comb_path(
        probe2[0], probe2[1], drop2, width, height, green, value_cells,
        max_steps=mass_steps,
    )
    note2 = (
        "harvest the visible MASS ringing the pure — keep it SHORT (a secured "
        "second bank from the far side, not a seam crawl); land on the richest "
        "mass cell and lift"
    )
    if weapons:
        note2 += (
            "; weapons about — you MAY instead re-hit the pure for safety "
            "(worth banking a green to be SURE the jackpot is yours)"
        )
    secure = SeamPattern(
        pattern_id="SECURE_MASS",
        kind="SECURE_MASS",
        beacon=beacon,
        mine=True,
        title="Secure the mass ring (H2)",
        when="2nd harvester: SHORT strip of the mass around your pure",
        rationale=(
            "The pure is a single cell; the seam's points are in the mass ring. A "
            "second harvester banks that ring on a short secured chain from the "
            "opposite angle. If weapons threaten the grab, re-hitting the pure is "
            "the safe alternative — the agent decides."
        ),
        waves=[SeamWave(
            1, _H_POST_EMP + spacing, drop2, comb2, probe_at=probe2,
            direction=d2, unit_ordinal=1, note=note2,
        )],
    )

    # ── H3 LATE_SWEEP — a late, bigger pattern from a third bearing over the
    # dense seam (the only own-seam wave allowed a full-length comb).
    d3 = _PERP.get(approach, "S")
    probe3 = _flank_probe(beacon, d3, width, height, dist=4, avoid_center=emp)
    drop3 = _value_drop(agent_view, beacon, probe3, width, height)
    comb3 = _comb_path(probe3[0], probe3[1], drop3, width, height, green, value_cells)
    note3 = (
        "late, bigger pattern from a third bearing — mop the dense seam. With "
        "MULTIPLE weapons in play, repeat the mass+pure for redundancy; else "
        "chase the juiciest separated vein/mass"
    )
    late = SeamPattern(
        pattern_id="LATE_SWEEP",
        kind="LATE_SWEEP",
        beacon=beacon,
        mine=True,
        title="Late sweep the seam (H3)",
        when="3rd harvester / late: bigger pattern over the dense seam",
        rationale=(
            "Pure red bleeds into a dense halo. A late third-bearing sweep scoops "
            "the wider seam once the pure and near-mass are secured, and leaves "
            "great vision for tomorrow."
        ),
        waves=[SeamWave(
            1, _H_WALK_IN + spacing, drop3, comb3, probe_at=probe3,
            direction=d3, unit_ordinal=2, note=note3,
        )],
    )

    return [smash, secure, late]


def _rival_patterns(
    agent_view: Mapping[str, Any],
    hint: Mapping[str, Any],
    beacon: Tuple[int, int],
    threat: Mapping[str, Any],
    *,
    seat_index: int = 0,
) -> List[SeamPattern]:
    """CASE 2 — a rival found it: blind grab, secured flank, then walk-in."""
    width, height = _grid_dims(agent_view)
    green = _known_green_cells(agent_view)
    emp = _emp_near(beacon, threat.get("emp_cells") or [])
    spacing = _EMP_CLOUD_HOURS if emp else 0

    # BLIND_GRAB: overwrite the finder's probe, then a short blind drop. We stage
    # behind our OWN fresh probe (force_probe) — but if we happen to already see
    # the pure, land on that exact cell rather than a blind in-disk guess.
    #
    # M3: anchor CASE-2 geometry to the discoverer's PROBE, not the jittered
    # beacon. The finder's probe (now visible after the E2 fix) is the best pure
    # triangulation we have — supersede THAT cell and drop toward it.
    finder = _freshest_enemy_probe_in_smear(agent_view, beacon)
    sup = hint.get("supersede")
    supersede = (
        (int(sup[0]), int(sup[1]))
        if isinstance(sup, (list, tuple)) and len(sup) == 2 else finder
    )
    core_visible = _known_core(agent_view, beacon) is not None
    if not core_visible and finder is not None:
        # Triangulate the fogged pure from the finder's bearing.
        drop1, probe1, value_cells = _triangulated_blind_geometry(
            agent_view, beacon, finder,
        )
    else:
        drop1, probe1, _wave1_probe, value_cells = _wave1_grab_geometry(
            agent_view, beacon, hint, force_probe=True,
        )
    # R3: fan the blind grab by seat so mirror seats attack distinct cells.
    drop1, probe1 = _seat_offset_geom(
        drop1, probe1, seat_index, width, height, green,
    )
    approach = _dir_name(probe1, beacon)
    # Two sub-cases. If we can already SEE the pure (rare for a rival beacon), it
    # is a KNOWN target -> snatch it like a smash (danger-gated, 0 ok). If it is
    # still fogged (the usual case), the drop is a GUESS off the jittered smear,
    # so comb a SHORT SWEEP across the top candidates to actually bank the pure —
    # "a bit more than one move" — never zero.
    core_seen = core_visible
    if core_seen:
        grab_steps = _grab_steps(threat, contested=True, emp=emp)
    else:
        grab_steps = _blind_grab_steps(threat, emp=emp)
    comb1 = _comb_path(
        probe1[0], probe1[1], drop1, width, height, green, value_cells,
        max_steps=grab_steps,
    )
    if core_seen:
        note_blind = (
            "you can SEE the pure here — DROP ON it (auto-harvest = the grab) and "
            "PICK UP IMMEDIATELY; no need to sweep"
        )
    else:
        note_blind = (
            "blind snatch — the beacon is a JITTERED smear, so one drop cell "
            "rarely IS the pure: DROP on the richest guess, then COMB a SHORT "
            "sweep (2-3 cells) across the neighbouring candidates to actually "
            "bank the pure, and PICK UP right after. Deny them + take the core "
            "fast — do NOT ride a long chain, a contested seam gets crashed"
        )
        if finder is not None:
            note_blind += (
                f"; the finder's probe is at ({finder[0]},{finder[1]}) — the pure "
                "is near IT, so this grab is aimed at the finder's cell (not the "
                "beacon centre) and supersedes it to blind them"
            )
    if threat.get("chaff_seen"):
        note_blind += " (chaff about — keep the sweep to the floor + flank backup)"
    blind = SeamPattern(
        pattern_id="BLIND_GRAB",
        kind="BLIND_GRAB",
        beacon=beacon,
        mine=False,
        title="Blind grab (contest the finder)",
        when="you can reach the beacon now; blind the finder's probe and snatch",
        rationale=(
            "The rival is piggybacking their own probe. Supersede it to blind "
            "them, then take a blind drop and a SHORT SWEEP (2-3 cells) — the "
            "smear is jittered, so a single cell rarely nails the pure; the "
            "sweep raises the hit chance — then pick up early. You deny them and "
            "bank the core even if the exact pure eludes the first cell."
        ),
        waves=[SeamWave(
            1, _H_SMASH, drop1, comb1, probe_at=probe1, supersede=supersede,
            direction=approach, unit_ordinal=0, note=note_blind,
            pickup_after=True,
        )],
    )

    # UNBEATEN_FLANK: fresh probe on the OPPOSITE axis, secured bank post-EMP.
    d_flank = _OPPOSITE.get(approach, "W")
    probe_f = _flank_probe(beacon, d_flank, width, height, avoid_center=emp)
    drop_f = _value_drop(agent_view, beacon, probe_f, width, height)
    comb_f = _comb_path(probe_f[0], probe_f[1], drop_f, width, height, green, value_cells)
    flank = SeamPattern(
        pattern_id="UNBEATEN_FLANK",
        kind="UNBEATEN_FLANK",
        beacon=beacon,
        mine=False,
        title="Unbeaten flank (secured bank)",
        when="the beacon cell is a pile-up; come in from the opposite axis, later",
        rationale=(
            "Everyone crashes the advertised cell. A fresh probe on the far side "
            "reaches the same seam from an uncontested angle after the EMP "
            "window — the wave nobody is fighting for."
        ),
        waves=[SeamWave(
            1, _H_POST_EMP + spacing, drop_f, comb_f, probe_at=probe_f,
            direction=d_flank, unit_ordinal=1,
            note="uncontested approach; longer chain into the dense seam",
        )],
    )

    # WALK_IN: outer mop-up from a third bearing, late.
    d_walk = _PERP.get(approach, "S")
    probe_w = _flank_probe(beacon, d_walk, width, height, dist=4, avoid_center=emp)
    drop_w = _value_drop(agent_view, beacon, probe_w, width, height)
    comb_w = _comb_path(probe_w[0], probe_w[1], drop_w, width, height, green, value_cells)
    walk = SeamPattern(
        pattern_id="WALK_IN",
        kind="WALK_IN",
        beacon=beacon,
        mine=False,
        title="Walk-in (outer mop-up)",
        when="third harvester / late night; sweep the good red around the pure",
        rationale=(
            "Pure red bleeds into plenty of good red. A late walk-in from a "
            "third bearing scoops that halo even if the pure itself is contested "
            "— and leaves you great vision for tomorrow."
        ),
        waves=[SeamWave(
            1, _H_WALK_IN + spacing, drop_w, comb_w, probe_at=probe_w,
            direction=d_walk, unit_ordinal=2,
            note="slightly outside, different angle — bank the halo",
        )],
    )
    return [blind, flank, walk]


def _pattern_probe_cost(p: SeamPattern) -> int:
    """How many fresh probe launches a pattern consumes (probe_at + supersede)."""
    cost = 0
    for w in p.waves:
        if w.probe_at is not None:
            cost += 1
        if w.supersede is not None:
            cost += 1
    return cost


def build_seam_menu(
    agent_view: Mapping[str, Any],
    hot_drop_hints: Sequence[Mapping[str, Any]],
    *,
    max_beacons: int = 2,
    seat_index: int = 0,
    probe_stock: Optional[int] = None,
) -> List[SeamPattern]:
    """Build the redsign pattern menu — REGION-driven so a rival's fogged beacon
    is on the menu too (the dual-redsign gap).

    The old menu was driven only by the ranked hot-drop HINTS, so a redsign that
    never produced a drop hint (a rival's discovery still in fog) generated NO
    pattern — the thinker could SEE the second beacon but had nothing to select
    for it, and both harvesters converged on the one beacon that did. We now
    enumerate the authoritative live regions (``agent_view['redsign']``), pair
    each with its nearest redsign hint for richer geometry (fogged regions get a
    synthesised centre hint), then FOLD IN any redsign hint a region did not
    already cover so nothing the old path produced is lost.

    Ordering: MINE first (smash-grab is THE priority), then rivals. IDs of the
    second source are suffixed ``#2`` so they stay unique (``SMASH_GRAB`` for the
    own seam, ``BLIND_GRAB#2`` for the rival's). Empty when no redsign is in play.
    """
    regions = _redsign_regions(agent_view)
    threat = _threat_context(agent_view)
    # Probe budget for this night (view carries it; tests without the key get a
    # generous default so existing fixtures keep offering the full trio).
    ps = (
        probe_stock if probe_stock is not None
        else int((agent_view.get("probe_stock", 99)) or 0)
    )

    red_hints = [
        h for h in (hot_drop_hints or [])
        if isinstance(h, Mapping)
        and str(h.get("signal_type") or "") == "redsign"
        and _hint_beacon(h) is not None
    ]

    # Assemble ordered SOURCES = {beacon, mine, hint}, de-duped by region so two
    # smear cells of the SAME beacon never spawn a duplicate pattern set.
    sources: List[Dict[str, Any]] = []
    seen: List[Tuple[int, int]] = []

    def _covered(b: Tuple[int, int]) -> bool:
        return any(
            max(abs(b[0] - s[0]), abs(b[1] - s[1])) <= _REGION_MATCH_RADIUS
            for s in seen
        )

    for r in regions:
        beacon = r.get("center")
        if not isinstance(beacon, tuple) or _covered(beacon):
            continue
        seen.append(beacon)
        hint = _match_hint(beacon, red_hints)
        mine = r.get("mine")
        if mine is None and hint is not None:
            mine = hint.get("mine")
        if mine is None:
            mine = _match_mine(beacon, regions)
        sources.append({
            "beacon": beacon,
            "mine": mine,
            "hint": hint or {"drop_at": [beacon[0], beacon[1]], "mine": mine},
        })

    # Fold in hint-only beacons the regions did not cover (keeps the old
    # hint-driven behaviour for fixtures/views without a ``redsign`` region list).
    for hint in red_hints:
        beacon = _hint_beacon(hint)
        if beacon is None or _covered(beacon):
            continue
        seen.append(beacon)
        mine = hint.get("mine")
        if mine is None:
            mine = _match_mine(beacon, regions)
        sources.append({"beacon": beacon, "mine": mine, "hint": hint})

    # MINE first (priority), then rivals; stable within each group.
    sources.sort(key=lambda s: 0 if s.get("mine") is True else 1)

    patterns: List[SeamPattern] = []
    emitted = 0  # count NON-EMPTY groups so suffixing tracks what's shown, not
    #             the raw source index (a starved own-seam must not push the
    #             rival group to a misleading "#2").
    for src in sources[:max_beacons]:
        beacon, hint, mine = src["beacon"], src["hint"], src.get("mine")
        if mine is True:
            group = _mine_patterns(agent_view, hint, beacon, threat, probe_stock=ps)
        elif ps < 1:
            # A rival's seam can only be contested with a fresh probe (blind the
            # finder + light the fogged pure). With no probe in stock every rival
            # pattern is undroppable — don't offer geometry the packager can't
            # emit and the sanitizer would silently delete.
            group = []
        else:
            group = _rival_patterns(
                agent_view, hint, beacon, threat, seat_index=seat_index,
            )
        if not group:
            continue
        suffix = "" if emitted == 0 else f"#{emitted + 1}"
        for p in group:
            if suffix:
                p.pattern_id = f"{p.pattern_id}{suffix}"
            patterns.append(p)
        emitted += 1

    # PROBE BUDGET (the user's "only one probe -> you can do only one of these"
    # guard). Walk the assembled patterns in menu order and drop any probe-gated
    # pattern once the night's probe stock is spent — walk-in patterns cost 0 and
    # always survive, so the fleet is never stranded on undroppable geometry.
    budget = ps
    kept: List[SeamPattern] = []
    for p in patterns:
        cost = _pattern_probe_cost(p)
        if cost == 0:
            kept.append(p)
            continue
        if budget >= cost:
            budget -= cost
            kept.append(p)
        # else: no probes left for this probe-gated pattern -> drop it.
    return kept
