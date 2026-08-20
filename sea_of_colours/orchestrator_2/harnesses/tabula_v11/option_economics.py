"""v11 option economics — the numbers behind every menu option.

The v10/v11 OPTION MENU used to render an option as bare coordinates + a probe
cost. The model then had to reconstruct the walk, guess the yield, and cross-
reference a separate DROP-LEGAL block by eye to learn a cell was watched. This
module computes, deterministically, the facts that decision needs so the menu
can carry them inline — making the menu the single source of truth:

  * WALK      — the ordered cells a harvester would drop on + step through.
  * YIELD     — expected score contribution, broken out by colour, using the
                ENGINE's real scoring model (not the harness proxy):
                  RED   score = max(0, purity - transit) x MULT[tier(purity)]
                  BLUE  scores 0 (it is the fissile spend surface, not standings)
                  GREEN costs GREEN_ENDGAME_PENALTY (-100) per banked parcel
                Transit is row-dependent (10/25/50/100) and unknown at night, so
                we report the BEST-ROW (transit=10) upper bound and label it.
  * CRUSH     — probe centres the maneuver lands on: YOUR probe (bad, lose your
                own vision) vs an ENEMY probe (good, a supersede/denial).
  * COLLISION — how exposed the maneuver is to a rival crash, per the user's
                model: a cell an enemy probe SEES, weighted by how VALUABLE it is
                (mass/pure under enemy vision = a magnet, so HIGH), bumped when a
                rival holds EMP/chaff (timing/weapon risk on the pickup).

Pure functions over ``agent_view`` + an option ``payload``. Reuses the frozen
v7 geometry helpers (``_vision_disk`` / ``_enemy_probe_cells`` / ``_grid_dims``)
so the disk math matches the engine exactly.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from sea_of_colours.orchestrator_2.harnesses.tabula_v7.probe_hints import (
    _enemy_probe_cells,
    _grid_dims,
    _redsign_cells,
    _vision_disk,
)

Cell = Tuple[int, int]

# ── engine scoring constants (mirrored from sea_of_colours/game/session.py) ──
# RED tier-quality multiplier applied at ship time.
RED_QUALITY_MULTIPLIER: Dict[str, float] = {
    "trace": 0.75,
    "vein": 1.0,
    "mass": 1.5,
    "pure": 3.0,
}
# Transit charge per catapult row (10/25/50/100). We cannot know which row a
# parcel lands in at night, so the menu reports the BEST-ROW (cheapest) case as
# the honest upper bound and labels it "best row".
BEST_ROW_TRANSIT = 10
# Standing liability per undisposed vault-GREEN parcel.
GREEN_ENDGAME_PENALTY = 100
# Engine outing budget: a drop banks its own cell + up to 5 steps.
HOLD_CAPACITY = 6


def _tier(purity: int) -> str:
    """Engine tier bands (session._tier_for_purity): trace<=50, vein<=150,
    mass<=254, pure=255."""
    p = max(0, min(255, int(purity or 0)))
    if p <= 0:
        return "empty"
    if p <= 50:
        return "trace"
    if p <= 150:
        return "vein"
    if p <= 254:
        return "mass"
    return "pure"


def _red_ship_points(purity: int) -> float:
    """Best-row ship points for a RED cell of ``purity`` — the engine formula
    ``max(0, purity - transit) x MULT[tier(purity)]`` with transit=best row.
    Tier for the multiplier comes from the ORIGINAL purity, not post-transit."""
    p = int(purity or 0)
    mult = RED_QUALITY_MULTIPLIER.get(_tier(p), 1.0)
    effective = max(0, p - BEST_ROW_TRANSIT)
    return effective * mult


# ── board index ─────────────────────────────────────────────────────────
def _cell_index(agent_view: Mapping[str, Any]) -> Dict[Cell, Tuple[str, int]]:
    """Map ``(x, y) -> (tile, purity)`` for every cell in LIVE vision.

    Sourced from ``world.live`` (RED/BLUE/GREEN with purity), with a fallback to
    the top-level ``red_tiles`` / ``blue_tiles`` lists so fixtures that only
    project those still score. Cells NOT in this index are fog/unknown — a hot
    drop into them is blind, and we report the yield as unknown rather than
    inventing a number.
    """
    idx: Dict[Cell, Tuple[str, int]] = {}
    for row in ((agent_view.get("world") or {}).get("live") or []):
        if not isinstance(row, Mapping):
            continue
        tile = str(row.get("tile") or "").upper()
        if tile not in ("RED", "BLUE", "GREEN"):
            continue
        try:
            x, y = int(row["x"]), int(row["y"])
            p = int(row.get("purity") or 0)
        except (TypeError, KeyError, ValueError):
            continue
        idx[(x, y)] = (tile, p)
    # Fallback projections (fixtures / older shapes). Never overwrite a live row.
    for row in (agent_view.get("red_tiles") or []):
        if not isinstance(row, Mapping):
            continue
        try:
            x, y = int(row["x"]), int(row["y"])
            p = int(row.get("purity") or 0)
        except (TypeError, KeyError, ValueError):
            continue
        idx.setdefault((x, y), ("RED", p))
    for row in (agent_view.get("blue_tiles") or []):
        if not isinstance(row, Mapping):
            continue
        try:
            x, y = int(row["x"]), int(row["y"])
            p = int(row.get("purity") or row.get("value") or 0)
        except (TypeError, KeyError, ValueError):
            continue
        idx.setdefault((x, y), ("BLUE", p))
    return idx


# ── walk extraction ──────────────────────────────────────────────────────
def _as_cell(v: Any) -> Optional[Cell]:
    if isinstance(v, (list, tuple)) and len(v) == 2:
        try:
            return int(v[0]), int(v[1])
        except (TypeError, ValueError):
            return None
    return None


def walk_cells(payload: Mapping[str, Any]) -> List[Cell]:
    """The ordered cells a HARVESTER would bank on this option (drop + steps).

    Empty for probe/supersede options (they bank nothing). Handles every deploy
    shape: chain/grab (``cells`` — full path incl. drop), hot drop (``drop_at`` +
    ``comb_path``), and seam patterns (each non-deny wave's ``drop_at`` +
    ``comb_path``). Deduped, order-preserving.
    """
    out: List[Cell] = []
    seen: Set[Cell] = set()

    def _push(c: Optional[Cell]) -> None:
        if c is not None and c not in seen:
            seen.add(c)
            out.append(c)

    # Seam patterns: walk every wave that actually drops a harvester.
    waves = payload.get("waves")
    if isinstance(waves, list) and waves:
        for w in waves:
            if not isinstance(w, Mapping) or w.get("deny_only"):
                continue
            _push(_as_cell(w.get("drop_at")))
            for c in (w.get("comb_path") or []):
                _push(_as_cell(c))
        return out

    # Chain / grab: ``cells`` already includes the drop as its first entry.
    cells = payload.get("cells")
    if isinstance(cells, list) and cells:
        _push(_as_cell(payload.get("drop_at")))
        for c in cells:
            _push(_as_cell(c))
        return out

    # Hot drop / frontier: drop cell then the precompiled comb.
    drop = _as_cell(payload.get("drop_at"))
    if drop is not None:
        _push(drop)
        for c in (payload.get("comb_path") or []):
            _push(_as_cell(c))
    return out


def probe_cells(payload: Mapping[str, Any]) -> List[Cell]:
    """The cells this option launches a PROBE onto (for crush/supersede math).

    Covers a plain probe/supersede (``at`` / ``probe_at``), a hot drop's own
    reveal probe (``probe_at`` + any ``supersede``), and seam waves' probes.
    """
    out: List[Cell] = []
    seen: Set[Cell] = set()

    def _push(c: Optional[Cell]) -> None:
        if c is not None and c not in seen:
            seen.add(c)
            out.append(c)

    waves = payload.get("waves")
    if isinstance(waves, list) and waves:
        for w in waves:
            if not isinstance(w, Mapping):
                continue
            _push(_as_cell(w.get("probe_at")))
            _push(_as_cell(w.get("supersede")))
        return out

    _push(_as_cell(payload.get("at")))
    _push(_as_cell(payload.get("probe_at")))
    _push(_as_cell(payload.get("supersede")))
    return out


# ── yield ─────────────────────────────────────────────────────────────────
def yield_breakdown(
    cells: Sequence[Cell], agent_view: Mapping[str, Any],
) -> Dict[str, Any]:
    """Expected banked yield over ``cells``, broken out by colour.

    Returns:
      red_pts        — best-row ship points from RED cells (float, rounded int)
      red_tiers      — {tier: count} of harvested RED cells
      blue_fissile   — summed BLUE purity (fissile budget; 0 score)
      green_penalty  — -100 per harvested GREEN cell (negative int)
      green_cells    — count of harvested GREEN cells
      unknown_cells  — harvested cells not in live vision (blind fog steps)
      banked         — coloured cells that actually bank (<= HOLD_CAPACITY)
      over_hold      — banked coloured cells beyond the 6-parcel hold (won't bank)
    """
    idx = _cell_index(agent_view)
    red_pts = 0.0
    red_tiers: Dict[str, int] = {}
    blue_fissile = 0
    green_cells = 0
    unknown = 0
    coloured = 0  # RED/BLUE/GREEN cells (each banks a parcel, hold-capped)
    for c in cells:
        entry = idx.get(c)
        if entry is None:
            unknown += 1
            continue
        tile, purity = entry
        coloured += 1
        if tile == "RED":
            red_pts += _red_ship_points(purity)
            t = _tier(purity)
            red_tiers[t] = red_tiers.get(t, 0) + 1
        elif tile == "BLUE":
            blue_fissile += int(purity)
        elif tile == "GREEN":
            green_cells += 1
    return {
        "red_pts": int(round(red_pts)),
        "red_tiers": red_tiers,
        "blue_fissile": int(blue_fissile),
        "green_penalty": -GREEN_ENDGAME_PENALTY * green_cells,
        "green_cells": green_cells,
        "unknown_cells": unknown,
        "banked": min(coloured, HOLD_CAPACITY),
        "over_hold": max(0, coloured - HOLD_CAPACITY),
    }


# ── crush ───────────────────────────────────────────────────────────────
def _friendly_probe_centres(agent_view: Mapping[str, Any]) -> Set[Cell]:
    out: Set[Cell] = set()
    for e in ((agent_view.get("entities") or {}).get("mine") or []):
        if not isinstance(e, Mapping) or str(e.get("type") or "") != "probe":
            continue
        pos = e.get("pos") or e.get("at")
        c = _as_cell(pos)
        if c is not None:
            out.add(c)
    return out


def _enemy_probe_centres(agent_view: Mapping[str, Any]) -> Set[Cell]:
    out: Set[Cell] = set()
    for row in _enemy_probe_cells(agent_view):
        c = _as_cell(row.get("at"))
        if c is not None:
            out.add(c)
    return out


def _friendly_probe_nights(agent_view: Mapping[str, Any]) -> Dict[Cell, Optional[int]]:
    """Map each friendly probe centre -> its ``nights_remaining`` (``None`` when
    the field is absent). Used to judge whether crushing a probe actually costs
    any FUTURE vision."""
    out: Dict[Cell, Optional[int]] = {}
    for e in ((agent_view.get("entities") or {}).get("mine") or []):
        if not isinstance(e, Mapping) or str(e.get("type") or "") != "probe":
            continue
        c = _as_cell(e.get("pos") or e.get("at"))
        if c is None:
            continue
        nr = e.get("nights_remaining")
        out[c] = int(nr) if isinstance(nr, (int, float)) else None
    return out


# A probe with <= this many nights left will not survive to the NEXT planning
# night, so crushing it costs no future vision.
_NEAR_EXPIRY_NIGHTS = 1


def self_crush_verdicts(
    self_hits: Sequence[Cell],
    agent_view: Mapping[str, Any],
    *,
    walk: Optional[Sequence[Cell]] = None,
    day: Optional[int] = None,
    day_cap: Optional[int] = None,
) -> List[str]:
    """A per-cell verdict for each of YOUR probes this maneuver lands on.

    Crushing your own probe is WORTHWHILE when EITHER gate clears (it is an OR,
    not an AND):
      * LOOT TIER — the cell under the probe is high value (vein/mass/pure). A
        pure is worth far more than a probe's future vision, so grabbing it
        justifies the crush on its own. (A bare trace does NOT.)
      * FUTURE PROBE UTILITY — you will not need this disk's vision next night:
        it is about to EXPIRE, it is the FINAL night, or you are EXTRACTING the
        SEAM it covers this very outing (the walk already banks mass/pure here,
        so the disk is being consumed anyway).

    Only when NEITHER clears — a bare trace pass-over of a still-useful probe —
    is the verdict AVOID (reroute / land adjacent). ``day``/``day_cap`` are
    optional; without them the final-night signal is simply unused (expiry still
    applies via ``nights_remaining``).
    """
    idx = _cell_index(agent_view)
    nights = _friendly_probe_nights(agent_view)
    final_night = (
        day is not None and day_cap is not None and int(day) >= int(day_cap)
    )
    # "Extracting the seam now": this outing already banks a mass/pure RED cell,
    # so the probe's coverage is being consumed this night regardless.
    extracting_seam = any(
        idx.get(c, ("", 0))[0] == "RED" and _tier(idx[c][1]) in ("mass", "pure")
        for c in (walk or [])
    )
    notes: List[str] = []
    for c in self_hits:
        tile, purity = idx.get(c, ("", 0))
        tier = _tier(purity) if tile == "RED" else "empty"
        high_value = tile == "RED" and tier in ("vein", "mass", "pure")
        nr = nights.get(c)
        # The reason the disk is NOT needed next night (None -> still useful).
        if final_night:
            reason = "it is the FINAL night — its vision is worthless now"
        elif nr is not None and nr <= _NEAR_EXPIRY_NIGHTS:
            reason = f"it is about to expire ({nr} night(s) left) — its vision is nearly spent"
        elif extracting_seam:
            reason = "you strip the seam it covers this outing, so its coverage is already being consumed"
        else:
            reason = None
        not_needed = reason is not None
        cell_s = f"({c[0]},{c[1]})"
        if high_value:
            tail = (
                f"; {reason}, so TAKE it"
                if not_needed
                else " — a WORTHWHILE trade (a pure/mass/high vein outweighs the "
                "disk's future vision; land ADJACENT only if a neighbour holds "
                "equal value and you will re-work this seam)"
            )
            notes.append(
                f"lands on YOUR probe {cell_s} to bank {tier}({purity}){tail}"
            )
        elif not_needed:
            notes.append(
                f"passes over YOUR probe {cell_s} — {reason}, so no live vision is lost"
            )
        else:
            notes.append(
                f"CRUSHES YOUR probe {cell_s} for only {tier or 'empty'} — AVOID: "
                f"reroute / land ADJACENT and keep the disk's vision for next night"
            )
    return notes


def crush_report(
    payload: Mapping[str, Any], agent_view: Mapping[str, Any],
    *, harvest_cells: Optional[Sequence[Cell]] = None,
) -> Dict[str, List[Cell]]:
    """Probe centres this maneuver lands on.

    ``self`` — a harvester drop/step OR a new probe landing on YOUR OWN probe
        centre: you lose that probe's remaining vision (bad).
    ``enemy`` — a probe of yours landing on an ENEMY probe centre: a SUPERSEDE
        (their vision dies, yours survives) — cheap denial (good).
    """
    friendly = _friendly_probe_centres(agent_view)
    enemy = _enemy_probe_centres(agent_view)
    hcells = list(harvest_cells if harvest_cells is not None else walk_cells(payload))
    pcells = probe_cells(payload)

    self_hits: List[Cell] = []
    enemy_hits: List[Cell] = []
    for c in hcells:
        if c in friendly and c not in self_hits:
            self_hits.append(c)
    for c in pcells:
        if c in enemy and c not in enemy_hits:
            enemy_hits.append(c)
        if c in friendly and c not in self_hits:
            self_hits.append(c)
    return {"self": self_hits, "enemy": enemy_hits}


# ── collision risk ─────────────────────────────────────────────────────────
def _enemy_vision(agent_view: Mapping[str, Any]) -> Set[Cell]:
    """Union of every enemy probe's live-vision disk."""
    width, height = _grid_dims(agent_view)
    seen: Set[Cell] = set()
    for (ex, ey) in _enemy_probe_centres(agent_view):
        seen.update(_vision_disk(ex, ey, width, height))
    return seen


def _enemy_armed(weapon_estimates: Optional[Mapping[str, Any]]) -> bool:
    for e in (weapon_estimates or {}).values():
        if getattr(e, "emps_max", 0) > 0 or getattr(e, "chaff_max", 0) > 0:
            return True
    return False


# Chebyshev dilation of the broadcast smear so the PUBLIC footprint covers the
# exact pure + its immediate ring even though the smear is a jittered smear.
_REDSIGN_PUBLIC_RADIUS = 2


def _redsign_public_cells(agent_view: Mapping[str, Any]) -> Set[Cell]:
    """The PUBLIC redsign footprint — contested REGARDLESS of enemy probe vision.

    A redsign is broadcast to EVERY seat (§3.15): the moment a pure(255) is minted
    the whole map gets the warning, so probe vision is irrelevant to whether a
    rival knows to race that seam. We take the broadcast smear cells and dilate
    them a little to cover the exact pure and the mass ring the fight is really
    over. Empty until a redsign is live.
    """
    base = _redsign_cells(agent_view)
    if not base:
        return set()
    width, height = _grid_dims(agent_view)
    out: Set[Cell] = set()
    r = _REDSIGN_PUBLIC_RADIUS
    for (x, y) in base:
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                nx, ny = x + dx, y + dy
                if 0 <= nx < width and 0 <= ny < height:
                    out.add((nx, ny))
    return out


def collision_risk(
    cells: Sequence[Cell],
    agent_view: Mapping[str, Any],
    weapon_estimates: Optional[Mapping[str, Any]] = None,
) -> Tuple[str, str]:
    """(level, reason) for a maneuver over ``cells``.

    Per the user's model: risk is a function of whether a rival KNOWS the cell
    AND how VALUABLE it is (a mass/pure cell a rival can reach is a magnet for a
    contesting drop -> a mutual-kill collision). A rival holding EMP/chaff bumps
    the level and adds a timing warning (the pickup can be jammed).

    A rival "knows" a cell in TWO ways:
      * probe VISION — an enemy probe disk covers it, OR
      * a PUBLIC REDSIGN — the pure was broadcast to every seat (§3.15), so the
        seam is contested even with NO enemy probe on it. "No enemy vision" is a
        TRAP on a redsign: everyone got the warning and is racing you to it.

    LOW  — nothing you touch is watched OR on a public redsign.
    MED  — a watched cell you touch is only trace/vein/blue value.
    HIGH — a public-redsign cell, a watched mass/pure cell, or a weapon bump.
    """
    watched = _enemy_vision(agent_view)
    public = _redsign_public_cells(agent_view)
    vision_hit = [c for c in cells if c in watched]
    public_hit = [c for c in cells if c in public]
    if not vision_hit and not public_hit:
        return "LOW", "no cell you touch is under enemy vision"

    idx = _cell_index(agent_view)
    armed = _enemy_armed(weapon_estimates)

    if public_hit:
        # The redsign is public — probe vision is irrelevant; every seat is racing
        # this pure. HIGH risk, but a redsign seam is also MASS-RICH, so the
        # reward + denial are high too. This is a genuine GAMBLE, not a
        # prohibition: a fast smash-and-lift is the sure play, while sweeping the
        # whole seam banks far more but exposes a longer walk to a collision/jam
        # that zeroes UNLIFTED cargo — a risk that grows with more rivals and
        # later in the season. The thinker weighs value vs risk (CASE 1 vs CASE 2
        # is the doctrine's separate ownership call).
        level = "HIGH"
        reason = (
            f"PUBLIC redsign — EVERY seat got the broadcast and is racing this "
            f"pure, so {public_hit[0]} is CONTESTED regardless of probe vision; "
            "the seam is MASS-RICH (high reward + denial), so weigh a fast "
            "smash-and-lift (sure) against sweeping the whole seam (far more "
            "points, but a longer walk risks a collision/jam that zeroes unlifted "
            "cargo — a risk that rises with more rivals and later in the season)"
        )
    else:
        high_value = [c for c in vision_hit if idx.get(c, ("", 0))[0] == "RED"
                      and _tier(idx[c][1]) in ("mass", "pure")]
        if high_value:
            level = "HIGH"
            reason = (
                f"{len(vision_hit)} cell(s) under enemy vision incl. mass/pure "
                f"{high_value[0]} — a rival can see the value and contest the drop"
            )
        else:
            level = "MED"
            reason = (
                f"{len(vision_hit)} cell(s) under enemy vision (trace/vein/blue value)"
            )

    if armed:
        if level == "MED":
            level = "HIGH"
        reason += "; a rival holds EMP/chaff — stagger the wave and lift EARLY (pickup can be jammed)"
    return level, reason


# ── one-call annotation ────────────────────────────────────────────────────
def annotate(
    payload: Mapping[str, Any],
    agent_view: Mapping[str, Any],
    weapon_estimates: Optional[Mapping[str, Any]] = None,
    *,
    day: Optional[int] = None,
    day_cap: Optional[int] = None,
) -> Dict[str, Any]:
    """Compute the full economics dict for one option payload.

    Returns ``{walk, length, yield, crush, crush_self_notes, risk}`` where
    ``risk`` is a ``(level, reason)`` tuple and ``crush_self_notes`` are the
    per-cell verdicts for any of YOUR probes the maneuver lands on (tier +
    future-utility aware). Deploy options get a real walk/yield; probe-only
    options get an empty walk (they bank nothing) but still carry crush/risk.
    """
    walk = walk_cells(payload)
    yb = yield_breakdown(walk, agent_view)
    crush = crush_report(payload, agent_view, harvest_cells=walk)
    self_notes = self_crush_verdicts(
        crush.get("self") or [], agent_view, walk=walk, day=day, day_cap=day_cap,
    )
    risk = collision_risk(walk or probe_cells(payload), agent_view, weapon_estimates)
    return {
        "walk": walk,
        "length": len(walk),
        "yield": yb,
        "crush_self_notes": self_notes,
        "crush": crush,
        "risk": risk,
    }
