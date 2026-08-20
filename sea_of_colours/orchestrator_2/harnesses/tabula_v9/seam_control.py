"""v9 Phase 2 — redsign seam-control PATTERN generator.

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
    * ``SMASH_GRAB``     wave 1 drop on/adjacent the pure at H1, extract H2 —
                         the main safety; I know where the pure is, move first.
    * later waves: a fresh probe near the core after the EMP window, then a
                   longer-chain flank from a new angle (pure red is dense).

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


def _mine_patterns(
    agent_view: Mapping[str, Any],
    hint: Mapping[str, Any],
    beacon: Tuple[int, int],
    threat: Mapping[str, Any],
) -> List[SeamPattern]:
    """CASE 1 — I found it: smash-and-grab, then press wider from new angles."""
    width, height = _grid_dims(agent_view)
    green = _known_green_cells(agent_view)
    emp = _emp_near(beacon, threat.get("emp_cells") or [])
    spacing = _EMP_CLOUD_HOURS if emp else 0

    # The GRAB is the DROP: LAND on the pure/mass core (auto-harvested, F7) and
    # SECURE it FAST. Length is DANGER-GATED (0 steps under threat/contest), never
    # a 6-cell walk over the jackpot. DROP-FIRST: because this redsign is MINE, a
    # friendly probe already revealed the pure — land on that EXACT cell and drop
    # STRAIGHT when it is already covered (never re-probe to a fog cell that lands
    # short of the pure — the day-2 whiff).
    drop1, probe1, wave1_probe, value_cells = _wave1_grab_geometry(
        agent_view, beacon, hint,
    )
    contested = bool(hint.get("contested"))
    grab_steps = _grab_steps(threat, contested=contested, emp=emp)
    comb1 = _comb_path(
        probe1[0], probe1[1], drop1, width, height, green, value_cells,
        max_steps=grab_steps,
    )
    core_visioned = wave1_probe is None
    approach = _dir_name(probe1, beacon)

    # wave 2: fresh probe near the core after the EMP window, opposite angle.
    d2 = _OPPOSITE.get(approach, "W")
    probe2 = _flank_probe(beacon, d2, width, height, avoid_center=emp)
    drop2 = _drop_toward(beacon, probe2, width, height)
    comb2 = _comb_path(probe2[0], probe2[1], drop2, width, height, green, value_cells)

    # wave 3: longer-chain flank from a third bearing (pure red is dense).
    d3 = _PERP.get(approach, "S")
    probe3 = _flank_probe(beacon, d3, width, height, dist=4, avoid_center=emp)
    drop3 = _drop_toward(beacon, probe3, width, height)
    comb3 = _comb_path(probe3[0], probe3[1], drop3, width, height, green, value_cells)

    note1 = (
        "you know the pure — DROP ON the core cell (it auto-harvests = the grab) "
        "and PICK UP FAST to bank it before rivals arrive"
    )
    if core_visioned:
        note1 += "; it is already in live vision, so drop STRAIGHT (no probe)"
    if grab_steps == 0:
        note1 += "; danger present -> take ZERO extra steps, just drop + pickup"
    note1 += "; strip the wider seam on later waves / a 2nd harvester"
    if threat.get("chaff_seen"):
        note1 += " (chaff about: keep wave 2 as your backup)"

    waves = [
        SeamWave(1, _H_SMASH, drop1, comb1, probe_at=wave1_probe,
                 direction=approach, unit_ordinal=0, note=note1,
                 pickup_after=True),
        SeamWave(2, _H_POST_EMP + spacing, drop2, comb2, probe_at=probe2,
                 direction=d2, unit_ordinal=1,
                 note="re-probe the core after the EMP window from the far side"),
        SeamWave(3, _H_WALK_IN + spacing, drop3, comb3, probe_at=probe3,
                 direction=d3, unit_ordinal=2,
                 note="longer chain from a third angle — mop the dense seam"),
    ]
    return [SeamPattern(
        pattern_id="SMASH_GRAB",
        kind="SMASH_GRAB",
        beacon=beacon,
        mine=True,
        title="Smash-and-grab (your pure)",
        when="you discovered this seam; take the pure on wave 1, press wider after",
        rationale=(
            "Engine-truth says this beacon is yours, so you already know where "
            "the pure sits. Landing wave 1 immediately banks it before any rival "
            "can converge; later waves harvest the dense red around it."
        ),
        waves=waves,
    )]


def _rival_patterns(
    agent_view: Mapping[str, Any],
    hint: Mapping[str, Any],
    beacon: Tuple[int, int],
    threat: Mapping[str, Any],
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
    drop_f = _drop_toward(beacon, probe_f, width, height)
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
    drop_w = _drop_toward(beacon, probe_w, width, height)
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


def build_seam_menu(
    agent_view: Mapping[str, Any],
    hot_drop_hints: Sequence[Mapping[str, Any]],
    *,
    max_beacons: int = 2,
) -> List[SeamPattern]:
    """Build the redsign pattern menu from the (already ranked) hot-drop hints.

    One beacon -> its CASE-1 or CASE-2 patterns. When several beacons are live
    we keep the first ``max_beacons`` (freshest/best hints) and suffix pattern
    IDs with the beacon so they stay unique (``SMASH_GRAB``, ``SMASH_GRAB#2``).
    Returns an empty list when no redsign is in play (callers skip the block).
    """
    regions = _redsign_regions(agent_view)
    threat = _threat_context(agent_view)
    patterns: List[SeamPattern] = []
    seen_beacons: List[Tuple[int, int]] = []

    for hint in hot_drop_hints or []:
        if not isinstance(hint, Mapping):
            continue
        if str(hint.get("signal_type") or "") != "redsign":
            continue
        beacon = _hint_beacon(hint)
        if beacon is None:
            continue
        # De-dup by REGION, not by cell: two hot-drops on adjacent cells of the
        # SAME redsign smear must not spawn duplicate ``#2`` pattern sets.
        if any(
            max(abs(beacon[0] - b[0]), abs(beacon[1] - b[1])) <= _REGION_MATCH_RADIUS
            for b in seen_beacons
        ):
            continue
        seen_beacons.append(beacon)

        mine = hint.get("mine")
        if mine is None:
            mine = _match_mine(beacon, regions)

        if mine is True:
            group = _mine_patterns(agent_view, hint, beacon, threat)
        else:
            group = _rival_patterns(agent_view, hint, beacon, threat)

        # Keep IDs unique across multiple beacons.
        suffix = "" if len(seen_beacons) == 1 else f"#{len(seen_beacons)}"
        for p in group:
            if suffix:
                p.pattern_id = f"{p.pattern_id}{suffix}"
            patterns.append(p)

        if len(seen_beacons) >= max_beacons:
            break

    return patterns
