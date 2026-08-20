"""v10 R1 — the DETERMINISTIC packager (compiler back-end).

The thinker (front-end) does the creative work: read state, pick posture, choose
and order tactical options. The resolver expands those IDs to concrete geometry
(:class:`..agency.Option` payloads). This module is the back-end: it COMPILES
that recipe into wire-format moves — a pure function with fully-defined semantics.

Why deterministic (see SEED69_FIXPLAN.md R1): every hallucination in the v9 audit
was in the LLM executor stage — wrong drop cells, multi-drop cycles on one unit,
zero-walk final-night drops, invented cell contents. The executor runs on the
SAME snapshot as the thinker (no new information), so any latitude only subtracts
value. Compiling the recipe in Python makes coordinate faithfulness and the
one-drop-per-unit hold structurally guaranteed, kills a Haiku round-trip, and
removes a whole failure surface. The LLM mover is kept ONLY as the no-recipe
fallback (handled in the harness).

The output still passes through the shared move sanitizer (legality / step
clipping / collision reroute) exactly like the LLM path did — the packager owns
the WHAT & WHERE (from the recipe) and HOW (unit/probe budgeting, contiguous
steps); the sanitizer owns final legality.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from sea_of_colours.orchestrator_2.harnesses.tabula_v7.probe_hints import (
    _orbit_harvester_ids,
)
from sea_of_colours.orchestrator_2.harnesses.tabula_v11 import (
    option_economics as econ,
)

# Kinds that each COMMIT ONE HARVESTER for a single outing (RULEBOOK §3.9.2 —
# one outing per harvester per night). ``seam`` is handled separately because a
# multi-wave campaign consumes one harvester PER non-deny wave.
_SINGLE_HARVESTER_KINDS = frozenset({"grab", "blue_grab", "chain", "hotdrop", "frontier"})
_PROBE_KINDS = frozenset({"probe", "supersede"})
# A supersede banks nothing but denies a rival's vision — worth roughly a mid
# fresh-vision gain when ranking which probes to keep under a stock shortage.
_SUPERSEDE_BASELINE_VALUE = 120.0


# Part C — when the THINKER sets ``chaff_react`` (it anticipates a chaff/EMP jam
# this night, which the last-night recap may not yet show), the packager caps
# EVERY chain to this many steps so each harvester banks and lifts inside the
# safe window instead of riding a long serpentine into the jam. The thinker's
# temporal intent thus reaches the deterministic compiler, not just the LLM mover
# fallback (the audit's #1 lever: carry the constraint through the handoff).
_CHAFF_STEP_CAP = 2


def _probe_stock(agent_view: Mapping[str, Any]) -> int:
    return int((agent_view.get("orbit") or {}).get("probe_stock") or 0)


def _cell(v: Any) -> Optional[Tuple[int, int]]:
    if isinstance(v, (list, tuple)) and len(v) == 2:
        try:
            return (int(v[0]), int(v[1]))
        except (TypeError, ValueError):
            return None
    return None


def _steps_between(
    a: Tuple[int, int], b: Tuple[int, int],
) -> List[Tuple[int, int]]:
    """Manhattan-1 waypoints from ``a`` (exclusive) to ``b`` (inclusive).

    Guarantees every emitted step is exactly one N/S/E/W cell from the last —
    the engine adjacency rule — regardless of how the recipe spaced its comb
    cells (walk x first, then y). A no-op when ``a == b``.
    """
    out: List[Tuple[int, int]] = []
    cx, cy = a
    while cx != b[0]:
        cx += 1 if b[0] > cx else -1
        out.append((cx, cy))
    while cy != b[1]:
        cy += 1 if b[1] > cy else -1
        out.append((cx, cy))
    return out


# ── value-based inventory reconciliation (RULEBOOK §3.9.2) ─────────────────
def _harvest_value(payload: Mapping[str, Any], agent_view: Mapping[str, Any]) -> float:
    """A scalar VALUE for a harvester option, engine-scored over its walk.

    ``red_pts`` dominates (it is the only thing that scores); BLUE fissile is
    worth roughly half a point each as spend-budget; GREEN is a straight
    penalty. Used to rank which runs to KEEP when there are fewer harvesters
    than selected runs — so we never drop the richer run just because the
    thinker ordered it later (the day-2 CH1-vs-GRAB1 bug)."""
    try:
        yb = econ.yield_breakdown(econ.walk_cells(payload), agent_view)
    except Exception:
        return 0.0
    return (
        float(yb.get("red_pts") or 0)
        + 0.5 * float(yb.get("blue_fissile") or 0)
        + float(yb.get("green_penalty") or 0)
    )


def _probe_priority(opt: Any) -> float:
    """Ranking value for a probe/supersede option under a stock shortage."""
    payload = getattr(opt, "payload", None) or {}
    try:
        v = float(payload.get("edge_promise") or payload.get("area_gain") or 0.0)
    except (TypeError, ValueError):
        v = 0.0
    if str(getattr(opt, "kind", "")) == "supersede":
        v = max(v, _SUPERSEDE_BASELINE_VALUE)
    return v


def _seam_wave_demand(opt: Any) -> int:
    """How many harvesters a seam campaign commits (one per non-deny wave)."""
    payload = getattr(opt, "payload", None) or {}
    return sum(
        1
        for w in (payload.get("waves") or [])
        if isinstance(w, Mapping) and not w.get("deny_only")
    )


def reconcile_selected(
    selected_options: Sequence[Any],
    agent_view: Mapping[str, Any],
) -> Tuple[List[Any], List[Dict[str, Any]]]:
    """Reconcile the thinker's selected options against LIVE inventory.

    RULEBOOK §3.9.2: each harvester makes ONE outing per night, so the seat can
    run at most ``harvesters_alive`` chains. When the thinker selects more runs
    than that (or more probes than stock), keep the HIGHEST-VALUE ones and drop
    the rest — never silently drop by plan order (the day-2 gap where the richer
    red run was cut because it came second). Seam campaigns reserve their waves'
    harvesters first (a coordinated multi-wave play); the remaining harvesters go
    to the best single-harvester runs.

    Returns ``(kept_options, report)`` where ``report`` is an ordered list of
    ``{id, kind, status, value, reason}`` covering EVERY selected option
    (``status`` ∈ ``kept`` | ``dropped``) — the structured record the harness
    persists so next turn's LAST NIGHT can show PLAN → COMPILED → DROPPED & WHY.
    """
    opts = [o for o in (selected_options or []) if o is not None]
    harvesters = len(_orbit_harvester_ids(agent_view))
    probe_stock = _probe_stock(agent_view)

    seam_demand = sum(
        _seam_wave_demand(o) for o in opts if str(getattr(o, "kind", "")) == "seam"
    )
    singles_cap = max(0, harvesters - seam_demand)

    single_opts = [
        o for o in opts if str(getattr(o, "kind", "")) in _SINGLE_HARVESTER_KINDS
    ]
    probe_opts = [o for o in opts if str(getattr(o, "kind", "")) in _PROBE_KINDS]

    dropped_reason: Dict[str, str] = {}

    if len(single_opts) > singles_cap:
        ranked = sorted(
            single_opts,
            key=lambda o: _harvest_value(getattr(o, "payload", None) or {}, agent_view),
            reverse=True,
        )
        for o in ranked[singles_cap:]:
            dropped_reason[o.option_id] = (
                f"only {harvesters} harvester(s) alive and each makes ONE "
                f"outing/night (RULEBOOK §3.9.2) — kept the higher-value run(s)"
            )

    if len(probe_opts) > probe_stock:
        ranked_p = sorted(probe_opts, key=_probe_priority, reverse=True)
        for o in ranked_p[probe_stock:]:
            dropped_reason[o.option_id] = (
                f"only {probe_stock} probe(s) in stock — kept the best {probe_stock}"
            )

    report: List[Dict[str, Any]] = []
    for o in opts:
        kind = str(getattr(o, "kind", ""))
        is_probe = kind in _PROBE_KINDS
        value = (
            round(_probe_priority(o))
            if is_probe
            else round(_harvest_value(getattr(o, "payload", None) or {}, agent_view))
        )
        oid = str(getattr(o, "option_id", "?"))
        if oid in dropped_reason:
            report.append(
                {
                    "id": oid,
                    "kind": kind,
                    "status": "dropped",
                    "value": value,
                    "reason": dropped_reason[oid],
                }
            )
        else:
            report.append(
                {"id": oid, "kind": kind, "status": "kept", "value": value, "reason": ""}
            )

    kept_options = [
        o for o in opts if str(getattr(o, "option_id", "?")) not in dropped_reason
    ]
    return kept_options, report


class _Packer:
    """Mutable budget state while compiling one night's recipe."""

    def __init__(
        self,
        agent_view: Mapping[str, Any],
        *,
        forbidden_cells: Optional[set] = None,
        live_red_cells: Optional[set] = None,
        chaff_short: bool = False,
    ) -> None:
        self.harvesters: List[str] = list(_orbit_harvester_ids(agent_view))
        self.probe_budget: int = _probe_stock(agent_view)
        self.moves: List[Dict[str, Any]] = []
        self.log: List[str] = []
        self._h_idx = 0
        self._probed_cells: set = set()
        self._drop_cells: set = set()
        # Part A1 — persistent stripped/GREEN union (fog-surviving). A drop onto
        # one of these auto-harvests green for a penalty; a step onto one is a
        # green hazard. Refuse both at compile time (the sanitizer is a backstop).
        self.forbidden: set = set(forbidden_cells or ())
        # Part A2 — the cells that are LIVE-RED for the seat right now
        # (``red_tiles[].freshness=='fresh'``). On a CONTESTED seam a blind sweep
        # must only STEP onto cells we can actually SEE are red at plan time —
        # never blind-walk a fogged neighbour that the rival may already have
        # stripped to green (the seed-56 self-harm generalised to the walk).
        self.live_red: set = set(live_red_cells or ())
        # Part C — the thinker's ``chaff_react`` temporal constraint, consumed
        # here so every chain lifts inside the safe window (not just the LLM
        # mover's advisory copy).
        self.chaff_short: bool = bool(chaff_short)

    # ── resource draws ─────────────────────────────────────────────
    def next_harvester(self) -> Optional[str]:
        if self._h_idx < len(self.harvesters):
            u = self.harvesters[self._h_idx]
            self._h_idx += 1
            return u
        return None

    def idle_harvesters(self) -> List[str]:
        return self.harvesters[self._h_idx:]

    def spend_probe(self, at: Any) -> bool:
        cell = _cell(at)
        if cell is None or self.probe_budget <= 0:
            return False
        if cell in self._probed_cells:
            return False  # never launch two probes onto the same cell
        self.moves.append({"a": "probe", "at": [cell[0], cell[1]]})
        self._probed_cells.add(cell)
        self.probe_budget -= 1
        return True

    # ── chain emit (drop -> contiguous steps -> pickup) ────────────
    def emit_chain(
        self, unit: str, drop_at: Any, comb: Sequence[Any],
        *, contested: bool = False, blind_walk: bool = False,
    ) -> bool:
        drop = _cell(drop_at)
        if drop is None:
            return False
        if drop in self._drop_cells:
            # Two options landed on the SAME cell (e.g. the thinker picked two
            # comb-shape variants of one drop, or two chains that overlap). A
            # second drop here is always a self-collision — refuse it.
            self.log.append(f"skip drop {list(drop)}: cell already has a drop")
            return False
        if drop in self.forbidden:
            # Part A1 — the landing cell is known-stripped/GREEN (survives fog).
            # Dropping here auto-harvests green for a penalty; refuse the whole
            # chain rather than burn a harvester on a guaranteed loss.
            self.log.append(
                f"skip drop {list(drop)}: known stripped/GREEN (hazard memory)"
            )
            return False
        # NOTE: value/danger-aware TAIL-TRIM is deliberately NOT done here. That
        # is the AGENT's call, not the compiler's: the OPTION MENU already flags
        # each chain's enemy-vision exposure and offers SHORT variants, so the
        # thinker sheds low-value exposed tails by picking the SHORT option (or
        # ``avoid``-ing the cells). The packager only enforces the hard, non-
        # negotiable truncations below (chaff window / known-green / contested
        # blind-walk), never a value judgement.
        self.moves.append({"a": "drop", "unit": unit, "at": [drop[0], drop[1]]})
        self._drop_cells.add(drop)
        cur = drop
        steps_emitted = 0
        for c in comb or []:
            nxt = _cell(c)
            if nxt is None or nxt == cur:
                continue
            stopped = False
            for sx, sy in _steps_between(cur, nxt):
                if self.chaff_short and steps_emitted >= _CHAFF_STEP_CAP:
                    # Part C — the thinker called chaff_react: cap the chain so it
                    # banks + lifts inside the safe window rather than riding into
                    # the jam. Stop the walk and pick up what we hold.
                    self.log.append(
                        f"chaff_react: capped chain to {_CHAFF_STEP_CAP} steps "
                        f"(early pickup)"
                    )
                    stopped = True
                    break
                if (sx, sy) in self.forbidden:
                    # Part A1 — walking onto a known stripped/GREEN cell is a
                    # hazard step. Bank what we hold and stop the walk here
                    # rather than step onto a penalty.
                    self.log.append(
                        f"truncate walk before {[sx, sy]}: known stripped/GREEN"
                    )
                    stopped = True
                    break
                if contested and not blind_walk and (sx, sy) not in self.live_red:
                    # Part A2 — on a CONTESTED (live-confirmed) rival seam, only
                    # STEP onto cells we can SEE are red at plan time. A fogged
                    # neighbour of the confirmed core may already be stripped to
                    # green; a blind sweep onto it banks a penalty. Secure the
                    # confirmed core and stop rather than blind-walk the fog.
                    self.log.append(
                        f"truncate contested walk before {[sx, sy]}: not live-red"
                    )
                    stopped = True
                    break
                # NOTE: a BLIND_WALK wave (v11 CASE-2 attack on a FOGGED rival
                # seam) deliberately steps onto FOG — the pure is jittered so the
                # sweep must range over unseen cells. The only hard refusal is the
                # ``forbidden`` known-stripped/green set above; unknown fog is the
                # accepted risk on a fresh, mass-rich rival redsign.
                self.moves.append({"a": "step", "unit": unit, "to": [sx, sy]})
                cur = (sx, sy)
                steps_emitted += 1
            if stopped:
                break
        self.moves.append({"a": "pickup", "unit": unit})
        return True


def _pack_seam(pk: _Packer, payload: Mapping[str, Any]) -> None:
    """A multi-wave redsign campaign: each wave gets its own harvester."""
    waves = sorted(
        (w for w in (payload.get("waves") or []) if isinstance(w, Mapping)),
        key=lambda w: (int(w.get("wave") or 0), int(w.get("earliest_hour") or 0)),
    )
    for w in waves:
        # Part B — a DENY-ONLY wave commits NO harvester: it only spends its
        # supersede + confirm probe (blind the finder, light a fogged rival seam
        # for a real strike tomorrow). Never a blind harvester drop onto green.
        if w.get("deny_only"):
            if w.get("supersede") is not None:
                pk.spend_probe(w.get("supersede"))
            if w.get("probe_at") is not None:
                pk.spend_probe(w.get("probe_at"))
            continue
        unit = pk.next_harvester()
        if unit is None:
            pk.log.append(
                f"cut seam wave {w.get('wave')}: no harvester left (fleet sized)"
            )
            continue
        if w.get("supersede") is not None:
            pk.spend_probe(w.get("supersede"))
        if w.get("probe_at") is not None:
            pk.spend_probe(w.get("probe_at"))
        # Part A2 — a contested (live-confirmed) wave may only sweep across cells
        # confirmed live-red at plan time; a BLIND_WALK wave (fogged CASE-2
        # attack) may step onto fog, refusing only known-green (see emit_chain).
        pk.emit_chain(
            unit, w.get("drop_at"), w.get("comb_path") or [],
            contested=bool(w.get("contested")),
            blind_walk=bool(w.get("blind_walk")),
        )


def _pack_hotdrop(pk: _Packer, payload: Mapping[str, Any]) -> None:
    drop = _cell(payload.get("drop_at"))
    if drop is not None and drop in pk._drop_cells:
        # Don't burn a harvester on a drop cell already claimed (dup shape variant).
        pk.log.append(f"skip hot-drop: {list(drop)} already has a drop")
        return
    unit = pk.next_harvester()
    if unit is None:
        pk.log.append("cut hot-drop: no harvester left")
        return
    if payload.get("supersede") is not None:
        pk.spend_probe(payload.get("supersede"))
    if payload.get("probe_at") is not None:
        pk.spend_probe(payload.get("probe_at"))
    pk.emit_chain(unit, payload.get("drop_at"), payload.get("comb_path") or [])


def _pack_chain(pk: _Packer, payload: Mapping[str, Any]) -> None:
    drop = _cell(payload.get("drop_at"))
    if drop is not None and drop in pk._drop_cells:
        pk.log.append(f"skip juice chain: {list(drop)} already has a drop")
        return
    unit = pk.next_harvester()
    if unit is None:
        pk.log.append("cut juice chain: no harvester left")
        return
    pk.emit_chain(unit, payload.get("drop_at"), payload.get("cells") or [])


def _pack_probe(pk: _Packer, payload: Mapping[str, Any]) -> None:
    if not pk.spend_probe(payload.get("at")):
        pk.log.append("cut probe: no stock left")


def _pack_supersede(pk: _Packer, payload: Mapping[str, Any]) -> None:
    if not pk.spend_probe(payload.get("probe_at")):
        pk.log.append("cut supersede: no stock left")


def _pack_frontier(pk: _Packer, payload: Mapping[str, Any]) -> None:
    at = _cell(payload.get("at"))
    if at is None:
        return
    unit = pk.next_harvester()
    if unit is None:
        pk.log.append("cut frontier hot-drop: no harvester left")
        return
    pk.spend_probe(at)               # un-fog the blind cell
    pk.emit_chain(unit, at, [])      # drop auto-harvests; pick up (short/no walk)


_DISPATCH = {
    "seam": _pack_seam,
    "hotdrop": _pack_hotdrop,
    # v11 Phase-1 force-surfaced VALUE-PYRAMID grab — drop + contiguous walk,
    # identical wire shape to a juice chain, so it compiles through _pack_chain.
    "grab": _pack_chain,
    "blue_grab": _pack_chain,
    "chain": _pack_chain,
    "probe": _pack_probe,
    "supersede": _pack_supersede,
    "frontier": _pack_frontier,
}


def _complete_utilization(
    pk: _Packer,
    agent_view: Mapping[str, Any],
    *,
    chain_hints: Sequence[Mapping[str, Any]],
    probe_hints: Sequence[Mapping[str, Any]],
    supersede_hints: Sequence[Mapping[str, Any]],
) -> None:
    """R1 completion pass — "all harvesters dropped, all probes used".

    A GUARANTEE, not a judgement (see the design note): after the committed plan,
    deploy any still-idle harvester onto the best UNUSED offered chain, and spend
    any leftover probe stock on offered probe / supersede targets. Draws only
    from already-offered geometry, so it can never invent an off-menu cell.
    """
    for unit in pk.idle_harvesters():
        # Deploy the idle unit onto the HIGHEST-VALUE unused offered chain (not
        # merely the first listed), so "use all harvesters" also means "use them
        # on the best remaining geometry".
        candidates = [
            h
            for h in (chain_hints or [])
            if _cell(h.get("drop_at")) is not None
            and _cell(h.get("drop_at")) not in pk._drop_cells
        ]
        if not candidates:
            break
        chosen = max(candidates, key=lambda h: _harvest_value(h, agent_view))
        # Consume the pool slot so idle_harvesters() shrinks in lock-step.
        pk.next_harvester()
        pk.emit_chain(unit, chosen.get("drop_at"), chosen.get("cells") or [])
        pk.log.append(f"completion: deployed idle {unit} onto offered chain")

    if pk.probe_budget > 0:
        # Supersedes first (cheap denials), then remaining probe targets ranked
        # by promise, so leftover stock lands on the BEST offered cells.
        ranked_probes = sorted(
            (probe_hints or []),
            key=lambda h: float(h.get("edge_promise") or h.get("area_gain") or 0),
            reverse=True,
        )
        for h in list(supersede_hints or []) + ranked_probes:
            if pk.probe_budget <= 0:
                break
            at = h.get("probe_at") if "probe_at" in h else h.get("at")
            if pk.spend_probe(at):
                pk.log.append("completion: spent leftover probe on offered target")


def pack_recipe(
    selected_options: Sequence[Any],
    agent_view: Mapping[str, Any],
    *,
    chain_hints: Sequence[Mapping[str, Any]] = (),
    probe_hints: Sequence[Mapping[str, Any]] = (),
    supersede_hints: Sequence[Mapping[str, Any]] = (),
    forbidden_cells: Optional[set] = None,
    live_red_cells: Optional[set] = None,
    chaff_short: bool = False,
    complete: bool = True,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Compile the thinker's resolved recipe into wire moves (deterministic).

    ``selected_options`` is the priority-ordered list of :class:`..agency.Option`
    from ``resolve_plan``. Returns ``(moves, log)``. When ``complete`` is set, the
    utilization pass guarantees every alive harvester and probe is deployed from
    offered geometry. Returns an empty move list when there is no recipe — the
    caller then falls back to the LLM mover.

    ``forbidden_cells`` (Part A1) is the persistent stripped/GREEN union — no
    drop or step is ever compiled onto one of these, even under fog.
    ``live_red_cells`` (Part A2) is the seat's LIVE-red set — a contested wave's
    sweep may only step onto these cells. ``chaff_short`` (Part C) is the
    thinker's ``chaff_react`` flag — every chain is capped so it lifts inside the
    safe window.
    """
    pk = _Packer(
        agent_view,
        forbidden_cells=forbidden_cells,
        live_red_cells=live_red_cells,
        chaff_short=chaff_short,
    )
    for opt in selected_options or []:
        kind = getattr(opt, "kind", None)
        payload = getattr(opt, "payload", None) or {}
        fn = _DISPATCH.get(str(kind))
        if fn is not None:
            fn(pk, payload)
    if complete:
        _complete_utilization(
            pk,
            agent_view,
            chain_hints=chain_hints,
            probe_hints=probe_hints,
            supersede_hints=supersede_hints,
        )
    return pk.moves, pk.log
