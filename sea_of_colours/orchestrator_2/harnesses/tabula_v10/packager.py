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


class _Packer:
    """Mutable budget state while compiling one night's recipe."""

    def __init__(self, agent_view: Mapping[str, Any]) -> None:
        self.harvesters: List[str] = list(_orbit_harvester_ids(agent_view))
        self.probe_budget: int = _probe_stock(agent_view)
        self.moves: List[Dict[str, Any]] = []
        self.log: List[str] = []
        self._h_idx = 0
        self._probed_cells: set = set()
        self._drop_cells: set = set()

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
        self.moves.append({"a": "drop", "unit": unit, "at": [drop[0], drop[1]]})
        self._drop_cells.add(drop)
        cur = drop
        for c in comb or []:
            nxt = _cell(c)
            if nxt is None or nxt == cur:
                continue
            for sx, sy in _steps_between(cur, nxt):
                self.moves.append({"a": "step", "unit": unit, "to": [sx, sy]})
                cur = (sx, sy)
        self.moves.append({"a": "pickup", "unit": unit})
        return True


def _pack_seam(pk: _Packer, payload: Mapping[str, Any]) -> None:
    """A multi-wave redsign campaign: each wave gets its own harvester."""
    waves = sorted(
        (w for w in (payload.get("waves") or []) if isinstance(w, Mapping)),
        key=lambda w: (int(w.get("wave") or 0), int(w.get("earliest_hour") or 0)),
    )
    for w in waves:
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
        pk.emit_chain(unit, w.get("drop_at"), w.get("comb_path") or [])


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
    "chain": _pack_chain,
    "probe": _pack_probe,
    "supersede": _pack_supersede,
    "frontier": _pack_frontier,
}


def _complete_utilization(
    pk: _Packer,
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
        chosen = None
        for h in chain_hints or []:
            drop = _cell(h.get("drop_at"))
            if drop is not None and drop not in pk._drop_cells:
                chosen = h
                break
        if chosen is None:
            break
        # Consume the pool slot so idle_harvesters() shrinks in lock-step.
        pk.next_harvester()
        pk.emit_chain(unit, chosen.get("drop_at"), chosen.get("cells") or [])
        pk.log.append(f"completion: deployed idle {unit} onto offered chain")

    if pk.probe_budget > 0:
        for h in list(supersede_hints or []) + list(probe_hints or []):
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
    complete: bool = True,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Compile the thinker's resolved recipe into wire moves (deterministic).

    ``selected_options`` is the priority-ordered list of :class:`..agency.Option`
    from ``resolve_plan``. Returns ``(moves, log)``. When ``complete`` is set, the
    utilization pass guarantees every alive harvester and probe is deployed from
    offered geometry. Returns an empty move list when there is no recipe — the
    caller then falls back to the LLM mover.
    """
    pk = _Packer(agent_view)
    for opt in selected_options or []:
        kind = getattr(opt, "kind", None)
        payload = getattr(opt, "payload", None) or {}
        fn = _DISPATCH.get(str(kind))
        if fn is not None:
            fn(pk, payload)
    if complete:
        _complete_utilization(
            pk,
            chain_hints=chain_hints,
            probe_hints=probe_hints,
            supersede_hints=supersede_hints,
        )
    return pk.moves, pk.log
