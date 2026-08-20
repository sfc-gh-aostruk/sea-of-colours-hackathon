"""Lightweight, mechanical move sanitizer for the tabula_v5 harness.

The prompt does the heavy lifting of getting the LLM to plan good moves,
but three failure modes recur no matter how the doctrine is worded — they
are geometry mistakes the model makes under time pressure, not strategy
mistakes. This module is the structural guardrail that catches them AFTER
the LLM responds and BEFORE the plan is submitted to the engine:

  1. NO-BEACON / ILLEGAL DROP — a ``drop`` onto a cell that is not in
     live vision (no probe disk / friendly-unit tile) or onto a GREEN /
     synthetic-green hazard or off-grid. The engine rejects the drop and
     every step/pickup that depended on it no-ops, wasting the harvester's
     whole night. We reroute to a legal adjacent cell when one exists, or
     drop the doomed chain entirely.

  2. SELF-CRUSH (nuanced) — a ``drop`` onto a friendly probe cell that
     still has >= 2 nights of vision left AND has no loot underneath. That
     needlessly destroys future vision. We reroute the landing to an
     adjacent drop-legal cell to preserve the probe. Crushing is LEFT
     ALONE when it is justified: the probe is expiring (<= 1 night) or the
     cell holds visible RED the harvester needs to grab.

  3. HARVESTER COLLISION — two friendly harvesters routed onto the SAME
     cell collide (both damaged, ZERO parcels banked). We keep the first
     unit's claim and reroute / truncate the second.

Design principles:
  * NEVER emit a move the engine would reject. When in doubt, TRUNCATE
    (bank what's safe) rather than gamble.
  * NEVER strand a harvester on the surface — truncating a chain always
    leaves (or inserts) a pickup so the unit comes home.
  * Be transparent: every change is appended to a human-readable log the
    harness stamps into the audit rationale.

The heavy geometry helpers are shared with :mod:`.validators` so the
sanitizer and the (now-informational) validator agree on drop legality.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Set, Tuple

from sea_of_colours.orchestrator_2.harnesses.tabula_v5.validators import (
    _live_vision_cells,
    _synthetic_green_cells,
    _green_hazard_cells,
    _friendly_probe_cells,
    _world_dims,
    _initial_harvester_positions,
)
from sea_of_colours.orchestrator_2.harnesses.tabula_v5.probe_hints import (
    _visible_red,
    _orbit_harvester_ids,
)

Cell = Tuple[int, int]
Move = Mapping[str, Any]

# Manhattan-1 neighbourhood (engine adjacency = N/S/E/W, no diagonals).
_NSEW = ((1, 0), (-1, 0), (0, 1), (0, -1))


def _friendly_probe_nights(agent_view: Mapping[str, Any]) -> Dict[Cell, int]:
    """``(x, y) -> nights_remaining`` for every active friendly probe.

    Defaults a probe with no ``nights_remaining`` field to 2 (treat as
    "still valuable") so a missing field never triggers a reroute we can't
    justify. Expired probes (<= 0) are skipped.
    """
    out: Dict[Cell, int] = {}
    for e in ((agent_view.get("entities") or {}).get("mine") or []):
        if not isinstance(e, Mapping) or str(e.get("type") or "") != "probe":
            continue
        pos = e.get("pos") or e.get("at")
        if not (isinstance(pos, (list, tuple)) and len(pos) == 2):
            continue
        try:
            cell = (int(pos[0]), int(pos[1]))
        except (TypeError, ValueError):
            continue
        nr = e.get("nights_remaining")
        nights = int(nr) if isinstance(nr, (int, float)) else 2
        if nights <= 0:
            continue
        out[cell] = nights
    return out


def _euclid_disk(cx: int, cy: int, width: int, height: int) -> Set[Cell]:
    """Engine vision/drop-legal shape: Euclidean radius-4 disk."""
    out: Set[Cell] = set()
    for dx in range(-4, 5):
        for dy in range(-4, 5):
            if dx * dx + dy * dy > 16:
                continue
            x, y = cx + dx, cy + dy
            if 0 <= x < width and 0 <= y < height:
                out.add((x, y))
    return out


def _has_following_step(moves: List[Move], drop_idx: int, unit: str) -> bool:
    """True if ``unit`` has at least one ``step`` after ``drop_idx`` before
    its next ``pickup``/``drop`` — i.e. this drop starts a harvest chain, not
    a lone drop-and-lift."""
    for j in range(drop_idx + 1, len(moves)):
        mj = moves[j]
        if not isinstance(mj, Mapping):
            continue
        if str(mj.get("unit") or "") != unit:
            continue
        a = str(mj.get("a") or "")
        if a == "step":
            return True
        if a in ("pickup", "drop"):
            return False
    return False


def sanitize_moves(
    moves: List[Move],
    agent_view: Mapping[str, Any],
    *,
    chain_hints: Optional[List[Mapping[str, Any]]] = None,
    is_final_night: bool = False,
    enemy_probe_cells: Optional[Set[Cell]] = None,
) -> Tuple[List[Move], List[str]]:
    """Return ``(sanitized_moves, change_log)``.

    ``sanitized_moves`` is a new list safe to submit; ``change_log`` is a
    list of short human-readable strings describing every edit made (empty
    when the plan was already clean).

    Optional guardrails (all default off / empty so existing callers and
    tests keep their behaviour):

      * ``chain_hints`` — the heuristic RED chains for THIS night. Used by
        the deploy-all-harvesters guard (T6): any harvester left in orbit
        after the plan is spent gets the top *unused* legal chain appended
        (drop -> steps -> pickup). An idle harvester banks nothing — on the
        final night that is pure lost points; every night it is wasted EV.
      * ``is_final_night`` — when True, a ``probe`` launch that is NOT
        superseding a known enemy probe is dropped (T7): a probe on the
        last night buys vision for a night that never comes.
      * ``enemy_probe_cells`` — cells holding a known enemy probe. A
        final-night probe onto one of these is a legitimate SUPERSEDE and
        is kept.
    """
    width, height = _world_dims(agent_view)
    if width <= 0 or height <= 0:  # can't reason about geometry — pass through
        return list(moves), []

    enemy: Set[Cell] = set(enemy_probe_cells or ())

    # Every drop target anywhere in the plan. Used to spare a final-night
    # probe that is actually a HOT-DROP enabler (probe -> friendly drop into
    # its disk) rather than a wasteful frontier scout. Killing a hot-drop
    # probe strands the harvester whose drop needed that probe's vision —
    # the exact bug that deleted harvester_p1_2's whole chain on a day-7
    # final night.
    drop_targets: Set[Cell] = set()
    for _m in moves:
        if isinstance(_m, Mapping) and str(_m.get("a") or "") == "drop":
            _at = _m.get("at")
            if isinstance(_at, (list, tuple)) and len(_at) == 2:
                try:
                    drop_targets.add((int(_at[0]), int(_at[1])))
                except (TypeError, ValueError):
                    pass

    live: Set[Cell] = set(_live_vision_cells(agent_view))
    bad: Set[Cell] = _synthetic_green_cells(agent_view) | _green_hazard_cells(agent_view)
    probe_cells: Set[Cell] = _friendly_probe_cells(agent_view)
    # Frozen snapshot of the probes that existed at TURN START — used to
    # detect a probe launched onto our OWN live probe (self-supersede).
    # ``probe_cells`` is mutated below as new probes launch this turn, so
    # we cannot reuse it for that check.
    turn_start_probes: Set[Cell] = set(probe_cells)
    probe_nights = _friendly_probe_nights(agent_view)
    red: Dict[Cell, int] = _visible_red(agent_view)

    # A probe launched EARLIER in this same moves list must be tracked too,
    # otherwise a same-turn ``probe (34,18)`` -> ``drop (34,18)`` sequence
    # crushes the just-launched probe and the drop-crush check never fires
    # (the cell wasn't in ``probe_cells`` at turn start). Default a fresh
    # probe to the engine's configured lifetime so the ">= 2 nights"
    # preserve rule treats it as still-valuable.
    rules = ((agent_view.get("meta") or {}).get("rules") or {})
    try:
        fresh_probe_nights = int(rules.get("probe_lifetime_nights") or 3)
    except (TypeError, ValueError):
        fresh_probe_nights = 3

    # Per-unit lifecycle: pos is None while in orbit, a cell while on the
    # surface, and the unit is added to ``done`` once it has picked up or
    # its chain was removed/truncated.
    pos: Dict[str, Optional[Cell]] = _initial_harvester_positions(agent_view)
    done: Set[str] = set()
    # Units that received a drop this turn (or started on the surface) —
    # feeds the deploy-all-harvesters guard so we never re-deploy a unit
    # that is already working, and DO deploy one left idle in orbit.
    deployed: Set[str] = {u for u, c in pos.items() if c is not None}

    # Cells claimed by any friendly unit's route this night (collision map).
    claimed: Dict[Cell, str] = {c: u for u, c in pos.items() if c is not None}

    # Per-unit drop reroute delta. When a drop is relocated (x,y)->(nx,ny),
    # the LLM's hand-built step chain was planned from the ORIGINAL cell, so
    # every following step is now non-adjacent and would truncate. We record
    # the delta and translate the unit's subsequent steps by it — re-threading
    # the chain onto the new landing instead of amputating it (the dominant
    # source of "drift": ~68% of planned steps were lost to this).
    drop_delta: Dict[str, Cell] = {}

    out: List[Move] = []
    log: List[str] = []

    def _in_bounds(x: int, y: int) -> bool:
        return 0 <= x < width and 0 <= y < height

    def _legal_land(x: int, y: int, unit: str) -> bool:
        """A cell a harvester may DROP or STEP onto without engine rejection
        or self-harm: in-bounds, in live vision, not green, not claimed by
        a different unit."""
        if not _in_bounds(x, y):
            return False
        if (x, y) in bad:
            return False
        if (x, y) not in live:
            return False
        other = claimed.get((x, y))
        return other is None or other == unit

    def _reroute_target(cx: int, cy: int, unit: str, *, avoid_probes: bool) -> Optional[Cell]:
        for dx, dy in _NSEW:
            nx, ny = cx + dx, cy + dy
            if not _legal_land(nx, ny, unit):
                continue
            if avoid_probes and (nx, ny) in probe_cells:
                continue
            return (nx, ny)
        return None

    def _truncate(unit: str) -> None:
        """Cut a unit's chain here: bank whatever it holds with a pickup,
        then mark it done so later moves for it are dropped."""
        if unit in done:
            return
        if pos.get(unit) is not None:
            out.append({"a": "pickup", "unit": unit})
        done.add(unit)

    for idx, m in enumerate(moves):
        if not isinstance(m, Mapping):
            log.append("dropped a non-dict move")
            continue
        act = str(m.get("a") or "")

        if act == "probe":
            # Probes are in-bounds-legal to the engine, but two launches are
            # self-harm the engine happily executes:
            #   (T7a) SELF-SUPERSEDE — a probe onto a cell where we ALREADY
            #         have a live probe destroys our own probe for zero
            #         vision gain (we already see that disk). Drop it unless
            #         the cell also holds an enemy probe worth superseding.
            #   (T7b) FINAL-NIGHT FRONTIER PROBE — on the last night a probe
            #         reveals ground no harvester will ever reach. Drop it
            #         unless it lands on a known enemy probe (a legit
            #         final-night supersede/denial play).
            at = m.get("at")
            if isinstance(at, (list, tuple)) and len(at) == 2:
                try:
                    px, py = int(at[0]), int(at[1])
                except (TypeError, ValueError):
                    px = py = None
                if px is not None and _in_bounds(px, py):
                    cell = (px, py)
                    if cell in turn_start_probes and cell not in enemy:
                        log.append(
                            f"dropped probe at {cell} — would supersede our OWN "
                            f"live probe (destroys vision we already have)"
                        )
                        continue
                    if is_final_night and cell not in enemy:
                        # Keep it ONLY if it's a hot-drop enabler: a friendly
                        # drop lands inside this probe's disk (harvest THIS
                        # night). A pure frontier scout (no drop in its disk)
                        # is still wasteful on the last night — drop that.
                        disk = _euclid_disk(px, py, width, height)
                        if disk.isdisjoint(drop_targets):
                            log.append(
                                f"dropped final-night probe at {cell} — frontier "
                                f"scout with no harvest to enable (no drop in its "
                                f"disk, not an enemy supersede)"
                            )
                            continue
                        # else: a drop lands in this disk -> hot-drop enabler,
                        # keep the probe so that drop stays legal.
                    live |= _euclid_disk(px, py, width, height)
                    # Track the launch so a later same-turn drop/step onto
                    # (px,py) is treated as a crush (see report bug).
                    probe_cells.add(cell)
                    probe_nights.setdefault(cell, fresh_probe_nights)
                    out.append(m)
                    continue
            out.append(m)  # malformed probe — let the engine ignore it
            continue

        unit = str(m.get("unit") or "")

        if act == "pickup":
            if unit in done:
                log.append(f"{unit}: dropped redundant pickup after chain end")
                continue
            if pos.get(unit) is None:
                log.append(f"{unit}: dropped pickup — unit not on surface")
                continue
            out.append(m)
            done.add(unit)
            continue

        # Any drop/step for a unit whose chain we've already ended is dead.
        if unit in done:
            log.append(f"{unit}: dropped '{act}' after chain was truncated")
            continue

        if act == "drop":
            at = m.get("at")
            if not (isinstance(at, (list, tuple)) and len(at) == 2):
                log.append(f"{unit}: dropped malformed drop.at")
                done.add(unit)
                continue
            try:
                x, y = int(at[0]), int(at[1])
            except (TypeError, ValueError):
                log.append(f"{unit}: dropped drop with non-int coords")
                done.add(unit)
                continue
            if pos.get(unit) is not None:
                log.append(f"{unit}: dropped duplicate drop — already on surface")
                continue

            requested: Cell = (x, y)  # where the LLM asked to land (chain anchor)
            has_chain = _has_following_step(moves, idx, unit)

            # (T2) Nuanced self-crush reroute — probe still valuable + no loot.
            if (x, y) in probe_cells:
                nights = probe_nights.get((x, y), 2)
                has_loot = red.get((x, y), 0) > 0
                if nights >= 2 and not has_loot:
                    if has_chain:
                        # A harvest chain follows and walks through this disk.
                        # Rerouting to spare the probe would orphan the chain
                        # (its first step is planned adjacent to THIS cell), so
                        # we'd bank 1 cell instead of the whole seam. The probe
                        # is spent — its disk is being stripped now — so its
                        # residual vision is worth less than the chain. Keep the
                        # crush and the chain intact.
                        log.append(
                            f"{unit}: kept crush at {(x, y)} — harvest chain "
                            f"follows; chain worth more than the probe's residual "
                            f"vision of a disk being stripped"
                        )
                    else:
                        alt = _reroute_target(x, y, unit, avoid_probes=True)
                        if alt is not None:
                            log.append(
                                f"{unit}: rerouted lone drop {(x, y)}->{alt} to "
                                f"spare a probe ({nights} nights vision, no loot)"
                            )
                            x, y = alt
                        else:
                            log.append(
                                f"{unit}: kept crush at {(x, y)} — no legal "
                                f"adjacent landing to spare the probe"
                            )

            # (T1) Illegal drop (no vision / green / off-grid) + (T4) collision.
            if not _legal_land(x, y, unit):
                alt = _reroute_target(x, y, unit, avoid_probes=False)
                if alt is not None:
                    reason = (
                        "collision" if claimed.get((x, y)) not in (None, unit)
                        else "not drop-legal"
                    )
                    log.append(f"{unit}: rerouted drop {(x, y)}->{alt} ({reason})")
                    x, y = alt
                else:
                    log.append(
                        f"{unit}: removed drop chain at {(x, y)} — illegal and no "
                        f"legal adjacent landing"
                    )
                    done.add(unit)
                    continue

            # If the drop moved from where the LLM asked AND a chain follows,
            # record the delta so the following steps get translated to stay
            # contiguous with the new landing (re-thread, not truncate).
            if (x, y) != requested and has_chain:
                drop_delta[unit] = (x - requested[0], y - requested[1])
                log.append(
                    f"{unit}: re-threading chain by {drop_delta[unit]} after "
                    f"drop moved {requested}->{(x, y)}"
                )

            new_move = dict(m)
            new_move["at"] = [x, y]
            out.append(new_move)
            pos[unit] = (x, y)
            claimed[(x, y)] = unit
            deployed.add(unit)
            continue

        if act == "step":
            to = m.get("to")
            cur = pos.get(unit)
            if cur is None:
                log.append(f"{unit}: dropped step — unit not on surface")
                continue
            if not (isinstance(to, (list, tuple)) and len(to) == 2):
                log.append(f"{unit}: step had malformed target — truncating")
                _truncate(unit)
                continue
            try:
                tx, ty = int(to[0]), int(to[1])
            except (TypeError, ValueError):
                log.append(f"{unit}: step coords not int — truncating")
                _truncate(unit)
                continue
            # Re-thread: if this unit's drop was relocated, translate the
            # planned step by the same delta so the contiguous chain follows
            # the new landing cell instead of pointing back at the old one.
            d = drop_delta.get(unit)
            if d is not None:
                tx, ty = tx + d[0], ty + d[1]
                m = {"a": "step", "unit": unit, "to": [tx, ty]}
            cx, cy = cur
            adjacent = abs(tx - cx) + abs(ty - cy) == 1
            legal = adjacent and _in_bounds(tx, ty) and (tx, ty) not in bad
            collides = claimed.get((tx, ty)) not in (None, unit)
            if not legal or collides:
                why = (
                    "collision" if collides
                    else "green/hazard" if (tx, ty) in bad
                    else "non-adjacent/off-grid"
                )
                log.append(
                    f"{unit}: truncated chain at step->{(tx, ty)} ({why}); "
                    f"banking from {cur}"
                )
                _truncate(unit)
                continue
            # (T5) Step-onto-own-probe crush. Stepping onto a friendly probe
            # cell destroys it just like a drop does. If the probe is still
            # valuable (>= 2 nights) and there is no visible loot on the
            # cell, the step is wasteful — truncate here to bank what we
            # have and preserve the probe's vision. If the probe is expiring
            # or loot sits on the cell, allow the step (justified crush).
            if (tx, ty) in probe_cells:
                nights = probe_nights.get((tx, ty), 2)
                has_loot = red.get((tx, ty), 0) > 0
                if nights >= 2 and not has_loot:
                    log.append(
                        f"{unit}: truncated chain before step->{(tx, ty)} "
                        f"(would crush own probe, {nights} nights vision, no "
                        f"loot); banking from {cur}"
                    )
                    _truncate(unit)
                    continue
            out.append(m)
            pos[unit] = (tx, ty)
            claimed[(tx, ty)] = unit
            continue

        # Unknown action — keep it; the engine will ignore anything invalid.
        out.append(m)

    # (T6) DEPLOY-ALL-HARVESTERS. A harvester left in orbit banks nothing —
    # on the final night that is pure lost points, every night it is wasted
    # EV. For each still-idle orbit harvester, append the top UNUSED
    # heuristic chain that is legal for it (drop -> steps -> pickup). This
    # is the structural fix for the "primary/finisher only deployed one of
    # two harvesters and left the 256-pt chain on the table" failure.
    if chain_hints:
        idle = [
            u for u in _orbit_harvester_ids(agent_view)
            if u not in deployed and u not in done
        ]
        used_hint_ids: Set[int] = set()
        # Reserve one slot for a final pickup; keep the whole plan <= 21.
        _CAP = 21
        for unit in idle:
            if len(out) >= _CAP - 1:
                break
            chain = _pick_legal_chain(
                unit, chain_hints, used_hint_ids, _legal_land,
            )
            if not chain:
                continue
            dcell = chain[0]
            out.append({"a": "drop", "unit": unit, "at": [dcell[0], dcell[1]]})
            pos[unit] = dcell
            claimed[dcell] = unit
            deployed.add(unit)
            steps_added = 0
            for cx, cy in chain[1:]:
                if len(out) >= _CAP - 1:  # keep room for the pickup
                    break
                out.append({"a": "step", "unit": unit, "to": [cx, cy]})
                pos[unit] = (cx, cy)
                claimed[(cx, cy)] = unit
                steps_added += 1
            out.append({"a": "pickup", "unit": unit})
            done.add(unit)
            log.append(
                f"{unit}: deployed idle harvester on unused chain from "
                f"{dcell} (+{steps_added} steps) — was left in orbit"
            )

    # Any harvester still on the surface with no pickup would dawn-crash.
    # Insert a terminal pickup so it banks and returns.
    for unit, p in pos.items():
        if p is not None and unit not in done:
            out.append({"a": "pickup", "unit": unit})
            log.append(f"{unit}: appended missing pickup at {p} (crash guard)")
            done.add(unit)

    return out, log


def _pick_legal_chain(
    unit: str,
    chain_hints: List[Mapping[str, Any]],
    used_hint_ids: Set[int],
    legal_land,
) -> List[Cell]:
    """Pick the first unused chain hint whose cells form a legal,
    contiguous walk for ``unit`` right now. Returns the ordered cell list
    (drop first), TRUNCATED at the first cell that is illegal / non-adjacent
    / already claimed, or ``[]`` if not even the drop cell is legal.
    """
    for hint in chain_hints:
        if id(hint) in used_hint_ids:
            continue
        cells_raw = hint.get("cells") or []
        if not cells_raw:
            continue
        try:
            drop = (int(cells_raw[0][0]), int(cells_raw[0][1]))
        except (TypeError, ValueError, IndexError):
            continue
        if not legal_land(drop[0], drop[1], unit):
            continue
        used_hint_ids.add(id(hint))
        walk: List[Cell] = [drop]
        cur = drop
        for raw in cells_raw[1:]:
            try:
                nxt = (int(raw[0]), int(raw[1]))
            except (TypeError, ValueError, IndexError):
                break
            if abs(nxt[0] - cur[0]) + abs(nxt[1] - cur[1]) != 1:
                break  # non-contiguous — stop here, bank what we have
            if not legal_land(nxt[0], nxt[1], unit):
                break
            walk.append(nxt)
            cur = nxt
        return walk
    return []
