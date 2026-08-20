"""Atomic combat candidates for PILOT_V3 (v0.9.25).

Emits single-action combat candidates that the Cortex agent composes
into multi-turn plays. The harness provides MECHANICAL FACTS — the
agent reasons about sequencing.

Currently emitted:

* ``emp_launch`` candidates — fire an EMP SALVO of three missiles
  (per RULEBOOK §5 + ``EMP_MISSILES_PER_LAUNCH``). One launch drains
  one stock and spawns three radius-2 clouds at the chosen target
  cells. The compiler emits several salvo patterns per primary
  target so the agent can pick the spatial strategy:

  * **concentrated** — 3 missiles tile the area around the primary
    target, saturating ~30 cells with cloud coverage.
  * **spread** — 1 missile per top-3 enemy concentration; maximises
    enemy-unit denial across the map.
  * **pure_cover** — primary on enemy + 2 around a contested pure /
    mass RED cluster; denies *and* tiles the high-value zone.
  * **drop_block_combo** — primary on enemy + 2 at predicted enemy
    drop cells (combines EMP with §3.17 case 1 denial).

The atomic-candidate philosophy:

* We do NOT bundle multi-turn sequences ("drop + emp + wait + pickup").
  Sequencing is the agent's job — it has the harvest chains, hot-drop
  pairs, crush candidates, and combat candidates as Lego blocks.

* Each candidate carries a ``responds_to_signal`` reference plus an
  ``expected_effect`` block with mechanical numbers (cargo at risk,
  cloud hours, blue cost). The agent's spec teaches reasoning patterns
  (race / pre-empt / counter-build / decoy) but never prescribes a
  canonical answer.

* The agent's prompt MUST quote the signal when accepting/rejecting
  a combat candidate. This forces explicit reasoning, not pattern-
  matching on the candidate score alone.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from sea_of_colours.orchestrator_2.harnesses.pilot_v3 import threat_assess as _ta


# ── EMP launch mechanics (mirrored from sea_of_colours.game.weapons) ──
EMP_COST_BLUE_PURITY = 200
EMP_COST_CREDITS = 250
EMP_RADIUS = 2              # Manhattan; each cloud covers 2*r*(r+1)+1 = 13 cells
EMP_CLOUD_HOURS = 8
EMP_MISSILES_PER_LAUNCH = 3  # one launch fires 3 simultaneous missiles


def _manhattan(a: Tuple[int, int], b: Tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _disk_cells(centre: Tuple[int, int], radius: int) -> Set[Tuple[int, int]]:
    """Manhattan radius-r disk centred on ``centre``."""
    cx, cy = centre
    out: Set[Tuple[int, int]] = set()
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if abs(dx) + abs(dy) <= radius:
                out.add((cx + dx, cy + dy))
    return out


def _salvo_cells(targets: Sequence[Tuple[int, int]]) -> Set[Tuple[int, int]]:
    """Union of all radius-r disks across ``targets``."""
    out: Set[Tuple[int, int]] = set()
    for t in targets:
        out |= _disk_cells(t, EMP_RADIUS)
    return out


def _units_in_cells(
    units: Sequence[Mapping[str, Any]],
    cells: Set[Tuple[int, int]],
) -> List[Dict[str, Any]]:
    """Return unit rows whose ``at`` is in the set."""
    out: List[Dict[str, Any]] = []
    for u in units:
        at = u.get("at") if isinstance(u, Mapping) else None
        if not (isinstance(at, (list, tuple)) and len(at) == 2):
            continue
        try:
            ux, uy = int(at[0]), int(at[1])
        except (TypeError, ValueError):
            continue
        if (ux, uy) in cells:
            out.append({
                "unit_id": str(u.get("unit_id") or u.get("id") or ""),
                "at": [ux, uy],
                "kind": str(u.get("kind") or ""),
            })
    return out


def _grid_cell_value(agent_view: Mapping[str, Any], x: int, y: int) -> int:
    """Best RED purity at (x,y), or 0 if not RED."""
    world = agent_view.get("world") or {}
    grid = world.get("grid")
    if isinstance(grid, list) and 0 <= y < len(grid):
        row = grid[y]
        if isinstance(row, list) and 0 <= x < len(row):
            cell = row[x]
            if isinstance(cell, dict) and str(cell.get("tile") or "") == "RED":
                try:
                    return int(cell.get("value") or cell.get("purity") or 0)
                except (TypeError, ValueError):
                    return 0
    return 0


def _disk_red_value(
    agent_view: Mapping[str, Any],
    centre: Tuple[int, int],
) -> int:
    """Ship-weighted RED value sitting in the radius-r disk centred on ``centre``."""
    total = 0
    cx, cy = centre
    for dy in range(-EMP_RADIUS, EMP_RADIUS + 1):
        for dx in range(-EMP_RADIUS, EMP_RADIUS + 1):
            if abs(dx) + abs(dy) > EMP_RADIUS:
                continue
            v = _grid_cell_value(agent_view, cx + dx, cy + dy)
            if v >= 255:
                total += int(v * 3.0)  # pure ships 3.0×
            elif v >= 151:
                total += int(v * 1.5)  # mass ships 1.5×
            elif v >= 1:
                total += v
    return total


def _candidate_centres(
    agent_view: Mapping[str, Any],
    enemy_probes: Sequence[Mapping[str, Any]],
    enemy_harvesters: Sequence[Mapping[str, Any]],
    width: int,
    height: int,
    heatmap: Optional[Any] = None,
) -> List[Tuple[Tuple[int, int], str]]:
    """Collect candidate target cells: enemy probes, enemy harvesters,
    high-value RED clusters, and heatmap top cells. De-duplicated,
    in-bounds."""
    centres: List[Tuple[Tuple[int, int], str]] = []
    seen: Set[Tuple[int, int]] = set()

    def _push(xy: Tuple[int, int], kind: str) -> None:
        x, y = xy
        if not (0 <= x < width and 0 <= y < height):
            return
        if xy in seen:
            return
        seen.add(xy)
        centres.append((xy, kind))

    for ep in enemy_probes:
        at = ep.get("at") if isinstance(ep, Mapping) else None
        if isinstance(at, (list, tuple)) and len(at) == 2:
            try:
                _push((int(at[0]), int(at[1])), "enemy_probe")
            except (TypeError, ValueError):
                continue
    for eh in enemy_harvesters:
        at = eh.get("at") if isinstance(eh, Mapping) else None
        if isinstance(at, (list, tuple)) and len(at) == 2:
            try:
                _push((int(at[0]), int(at[1])), "enemy_harvester")
            except (TypeError, ValueError):
                continue
    # Top-value RED cells (mass / pure tier) — useful as "tile the area"
    # secondary targets, especially when the agent decides to deny rivals
    # access to a juicy cluster.
    world = agent_view.get("world") or {}
    grid = world.get("grid")
    red_value_cells: List[Tuple[int, Tuple[int, int]]] = []
    if isinstance(grid, list):
        for y, row in enumerate(grid):
            if not isinstance(row, list):
                continue
            for x, cell in enumerate(row):
                if isinstance(cell, dict) and str(cell.get("tile") or "") == "RED":
                    try:
                        v = int(cell.get("value") or cell.get("purity") or 0)
                    except (TypeError, ValueError):
                        v = 0
                    if v >= _ta.MASS_PURITY_THRESHOLD:
                        red_value_cells.append((v, (x, y)))
    red_value_cells.sort(key=lambda r: -r[0])
    for _v, xy in red_value_cells[:6]:
        _push(xy, "high_value_red")
    # Heatmap top cells (where rivals are likely to strike).
    if heatmap is not None and getattr(heatmap, "width", 0) > 0:
        try:
            for cell in heatmap.top_cells(6):
                at = cell.get("at") if isinstance(cell, Mapping) else cell
                if not (isinstance(at, (list, tuple)) and len(at) == 2):
                    continue
                xy = (int(at[0]), int(at[1]))
                _push(xy, "heat_hotspot")
        except (AttributeError, TypeError, ValueError, IndexError):
            pass

    return centres


def _pick_salvo_variants(
    primary: Tuple[int, int],
    other_centres: Sequence[Tuple[Tuple[int, int], str]],
    width: int,
    height: int,
) -> List[Tuple[List[Tuple[int, int]], str]]:
    """Compose up to 3 salvo variants for a given primary target.

    Each variant returns a 3-cell salvo + a short pattern label:
    * ``concentrated`` — three missiles cluster around primary
      (tile the area).
    * ``spread`` — primary + two distinct distant targets.
    * ``pair_with_top`` — primary + the two highest-priority other
      centres.
    """
    variants: List[Tuple[List[Tuple[int, int]], str]] = []
    px, py = primary

    # Concentrated: primary + two cells offset to tile around it.
    # Offsets keep the disks overlapping ~50% so the union covers ~25
    # cells in a tight cluster. (radius 2 disks centered 3 apart leave
    # a thin gap; centered 2 apart over-overlaps; 3 is the sweet spot.)
    offsets = [(0, 0), (3, 0), (0, 3)]
    conc: List[Tuple[int, int]] = []
    for dx, dy in offsets:
        cx, cy = px + dx, py + dy
        if 0 <= cx < width and 0 <= cy < height:
            conc.append((cx, cy))
    if len(conc) == 3:
        variants.append((conc, "concentrated"))

    # Spread: primary + two cells from other_centres maximising pairwise
    # Manhattan distance (so the three disks barely overlap).
    if len(other_centres) >= 2:
        # Greedy pick: choose centre farthest from primary, then farthest
        # from {primary, first_pick}.
        candidates_xy = [c for (c, _k) in other_centres if c != primary]
        if candidates_xy:
            second = max(candidates_xy, key=lambda c: _manhattan(c, primary))
            remaining = [c for c in candidates_xy if c != second]
            if remaining:
                third = max(
                    remaining,
                    key=lambda c: min(_manhattan(c, primary), _manhattan(c, second)),
                )
                variants.append(([primary, second, third], "spread"))

    # Pair-with-top: primary + next two highest-priority centres
    # (top of the centre list).
    if len(other_centres) >= 2:
        top_two = [c for (c, _k) in other_centres if c != primary][:2]
        if len(top_two) == 2:
            salvo = [primary] + top_two
            # Dedupe in case spread already produced the same triple.
            if not any(set(salvo) == set(v[0]) for v in variants):
                variants.append((salvo, "pair_with_top"))

    return variants


def _rival_cargo_at_risk(
    enemy_units_in_cells: Sequence[Mapping[str, Any]],
) -> int:
    """Rough proxy: enemy surface harvesters × 4 parcels @ ~150 avg.

    Probes don't carry cargo. Harvesters frozen mid-night lose movement
    + risk §3.17 collision on dispatch.
    """
    surface_harvesters = sum(
        1 for u in enemy_units_in_cells
        if u.get("kind") in ("harvester", "")
    )
    return surface_harvesters * 4 * 150


def compile_emp_launch_candidates(
    *,
    agent_view: Mapping[str, Any],
    enemy_probes: Sequence[Mapping[str, Any]],
    enemy_harvesters: Sequence[Mapping[str, Any]],
    my_surface_harvesters: Sequence[Mapping[str, Any]],
    weapon_stock: Mapping[str, int],
    blue_purity_available: int,
    credits_available: int,
    heatmap: Optional[Any] = None,
    emp_signal: Optional[Mapping[str, Any]] = None,
    k: int = 4,
) -> List[Dict[str, Any]]:
    """Emit atomic EMP-salvo candidates (3 missiles per launch).

    Each candidate carries:

    * ``moves`` — single ``emp_launch`` action with the 3-cell salvo
      in the wire format ``{"a": "emp_launch", "at": [[x1,y1], [x2,y2], [x3,y3]]}``.
    * ``targets`` — explicit list of all 3 target cells.
    * ``pattern`` — short label (``concentrated`` / ``spread`` /
      ``pair_with_top``) describing the spatial strategy.
    * ``expected_effect`` — UNION coverage across the 3 disks: total
      cells, enemy units caught, our units caught, RED value denied.
    * ``responds_to_signal`` — pointer to ``compute_emp_threat_signal``
      so the agent reasons about its read of rival weapon intent.
    * ``affordability`` — stock + purchase costs.
    * ``reasoning_hints`` — race / pre-empt / counter-build / decoy.
    """
    world = agent_view.get("world") or {}
    try:
        width = int(world.get("width") or 0)
        height = int(world.get("height") or 0)
    except (TypeError, ValueError):
        width, height = 0, 0
    if width <= 0 or height <= 0:
        return []

    in_stock = int(weapon_stock.get("emp", 0) or 0)
    can_afford_build = (
        blue_purity_available >= EMP_COST_BLUE_PURITY
        and credits_available >= EMP_COST_CREDITS
    )

    centres = _candidate_centres(
        agent_view, enemy_probes, enemy_harvesters,
        width=width, height=height, heatmap=heatmap,
    )
    if not centres:
        return []

    # Build the union of all known enemy unit rows for coverage scoring.
    all_enemy_units: List[Dict[str, Any]] = []
    for ep in enemy_probes:
        if isinstance(ep, Mapping):
            all_enemy_units.append({**dict(ep), "kind": "probe"})
    for eh in enemy_harvesters:
        if isinstance(eh, Mapping):
            all_enemy_units.append({**dict(eh), "kind": "harvester"})

    # Generate variants per primary centre, then score each (primary,
    # variant) combo and keep the top K candidates.
    raw: List[Dict[str, Any]] = []
    # Limit primaries to enemy-bearing centres FIRST to avoid wasted EMPs.
    primary_pool = [(c, k_) for (c, k_) in centres
                    if k_ in ("enemy_probe", "enemy_harvester")]
    if not primary_pool:
        return []
    for primary, primary_kind in primary_pool:
        # Other_centres for variant composition — exclude the primary.
        others = [(c, k_) for (c, k_) in centres if c != primary]
        for salvo, pattern in _pick_salvo_variants(primary, others, width, height):
            union = _salvo_cells(salvo)
            enemy_in = _units_in_cells(all_enemy_units, union)
            if not enemy_in:
                # Pointless EMP; nothing to disable across the whole salvo.
                continue
            ours_in = _units_in_cells(my_surface_harvesters, union)
            denial_red_value = sum(
                _disk_red_value(agent_view, t) for t in salvo
            )
            cargo_at_risk = _rival_cargo_at_risk(enemy_in)
            local_heat_sum = 0.0
            if heatmap is not None and getattr(heatmap, "width", 0) > 0:
                for t in salvo:
                    try:
                        local_heat_sum += float(heatmap.value_xy(t) or 0.0)
                    except (AttributeError, TypeError, ValueError):
                        pass
            mean_heat = local_heat_sum / max(1, len(salvo))
            offensive_response_adj = _ta.OFFENSIVE_RESPONSE_BONUS * mean_heat
            self_freeze_penalty = 200 * len(ours_in)
            # v1.8 — enemy-unit denial bonus. Each enemy unit frozen by
            # the salvo (probe or harvester) is worth ~2000 doctrinal
            # points: freezing a probe blinds ~25 vision-cells for 8h and
            # freezing a harvester denies a night of movement. Without
            # this bonus the ranker prefers "spread" salvos that hit our
            # own high-value RED (inflating denial_red_value) over
            # "pair_with_top" salvos that cover multiple enemy centres
            # in a corridor. That produced empirically wrong picks in
            # the emp_covers_corridor_during_harvest / two_harvesters
            # scenarios — the corridor variant was correct but scored
            # too low to be chosen.
            enemy_denial_bonus = 2000 * len(enemy_in)
            base_score = (
                denial_red_value
                + cargo_at_risk
                + offensive_response_adj
                + enemy_denial_bonus
            )
            score = base_score - self_freeze_penalty

            signal_payload: Dict[str, Any] = {}
            if emp_signal:
                # v0.9.29 — widened to include the granular BLUE tracking
                # threat_assess now emits (pip band, grade change, signal_basis).
                # These let the agent reason about rival build DETECTION at a
                # finer resolution than the coarse `confidence` scalar:
                # a 4-pip drop within a grade is a strong build signal even
                # when the grade label hasn't moved. The season-total launch
                # count lets the agent detect a rival that habitually builds
                # weapons vs. one that never has.
                signal_payload = {
                    "rival_built_weapon": bool(emp_signal.get("rival_built_weapon", False)),
                    "confidence": float(emp_signal.get("confidence", 0.0) or 0.0),
                    "reason": str(emp_signal.get("reason", "")),
                    "signal_basis": str(emp_signal.get("signal_basis", "") or ""),
                    "rival_blue_grade_now": emp_signal.get("rival_blue_grade_now"),
                    "rival_blue_grade_prev": emp_signal.get("rival_blue_grade_prev"),
                    "rival_blue_band_drop": int(emp_signal.get("rival_blue_band_drop") or 0),
                    "rival_blue_pip_now": emp_signal.get("rival_blue_pip_now"),
                    "rival_blue_pip_prev": emp_signal.get("rival_blue_pip_prev"),
                    "rival_blue_pip_drop": int(emp_signal.get("rival_blue_pip_drop") or 0),
                    "rival_emp_launches_last_night": int(
                        emp_signal.get("rival_emp_launches_last_night", 0) or 0
                    ),
                    "rival_emp_launches_season_total": int(
                        emp_signal.get("rival_emp_launches_season_total", 0) or 0
                    ),
                }

            raw.append({
                "primary": primary,
                "primary_kind": primary_kind,
                "pattern": pattern,
                "targets": [list(s) for s in salvo],
                "score": float(score),
                "enemy_in": enemy_in,
                "ours_in": ours_in,
                "denial_red_value": int(denial_red_value),
                "cargo_at_risk": int(cargo_at_risk),
                "mean_heat": float(mean_heat),
                "offensive_response_adj": float(offensive_response_adj),
                "self_freeze_penalty": float(self_freeze_penalty),
                "union_cells": len(union),
                "signal_payload": signal_payload,
            })

    if not raw:
        return []

    raw.sort(key=lambda r: -float(r["score"]))

    candidates: List[Dict[str, Any]] = []
    for r in raw[:k]:
        salvo = [(int(t[0]), int(t[1])) for t in r["targets"]]
        primary = salvo[0]
        extras = salvo[1:]
        # Wire format: salvo as a list of [x,y] pairs in ``at``.
        move_at = [list(s) for s in salvo]
        candidates.append({
            "id": f"EMP{len(candidates)}",
            "kind": "emp_launch",
            "at": list(primary),  # back-compat — primary target
            "extra_ats": [list(t) for t in extras],
            "targets": move_at,
            "pattern": r["pattern"],
            "primary_kind": r["primary_kind"],
            "moves": [{"a": "emp_launch", "at": move_at}],
            "score": round(r["score"], 2),
            "expected_effect": {
                "missiles_per_launch": EMP_MISSILES_PER_LAUNCH,
                "cloud_radius": EMP_RADIUS,
                "cloud_hours": EMP_CLOUD_HOURS,
                "union_cells_covered": r["union_cells"],
                "enemy_units_in_salvo": r["enemy_in"],
                "enemy_unit_count": len(r["enemy_in"]),
                "our_units_in_salvo": r["ours_in"],
                "self_freeze_unit_count": len(r["ours_in"]),
                "denial_red_value_in_salvo": r["denial_red_value"],
                "rival_cargo_at_risk": r["cargo_at_risk"],
                "mean_heat_across_targets": round(r["mean_heat"], 3),
                "offensive_response_adj": round(r["offensive_response_adj"], 2),
                "self_freeze_penalty": round(r["self_freeze_penalty"], 2),
            },
            "affordability": {
                # v0.9.28 — top-level, unambiguous. `can_fire` = stock OR
                # afford-to-build. Placed FIRST so LLMs iterating the JSON
                # see it before the confusing purchase-only sub-flag. Prior
                # bug: agent read `purchase_now_possible: false` and skipped
                # the EMP even when `fires_from_stock: true` (stock=1). The
                # OR-derived can_fire removes that ambiguity.
                "can_fire": bool(in_stock >= 1 or can_afford_build),
                "reason": (
                    "stock" if in_stock >= 1
                    else ("build" if can_afford_build else "none")
                ),
                "in_stock": in_stock,
                "fires_from_stock": in_stock >= 1,
                "purchase_blue_cost": EMP_COST_BLUE_PURITY,
                "purchase_credit_cost": EMP_COST_CREDITS,
                "purchase_now_possible": can_afford_build,
            },
            "responds_to_signal": "compute_emp_threat_signal",
            "signal_payload": r["signal_payload"],
            "intent": (
                f"EMP salvo ({r['pattern']}) — primary at {primary}, "
                f"covers {r['union_cells']} cells, freezes "
                f"{len(r['enemy_in'])} enemy unit(s) for {EMP_CLOUD_HOURS}h. "
                f"Self-freeze cost: {len(r['ours_in'])} of our units."
            ),
            "reasoning_hints": [
                "Race: fire NOW to bank pure before rival's EMP lands.",
                "Pre-empt: if signal_payload.confidence ≥ 0.7, beat them to the launch.",
                "Counter-build: rival spent BLUE → their economy is weaker; ignore + outpace.",
                "Decoy: fire spread pattern at low-value clusters to bait their reaction.",
                "Skip: if our denial is small AND no enemy cargo at risk, EMP is wasted cost.",
                "Pattern choice: concentrated saturates one zone; spread denies three; pair_with_top is balanced.",
            ],
        })

    return candidates


__all__ = [
    "EMP_COST_BLUE_PURITY",
    "EMP_COST_CREDITS",
    "EMP_RADIUS",
    "EMP_CLOUD_HOURS",
    "EMP_MISSILES_PER_LAUNCH",
    "compile_emp_launch_candidates",
]
