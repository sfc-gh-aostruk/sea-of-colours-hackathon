"""v11 Phase 1 — the VALUE PYRAMID: provenance-tagged value + force-surfaced grabs.

The seed-69 diagnostics showed v10 could SEE a pure and still offer no way to
take it: a LIVE pure not wrapped in a redsign pattern, or an ECHO pure one cell
from live, fell through every precondition-gated menu family and the turn banked
zero. The root cause is that "value" and "how you reach it" were computed
implicitly across five modules with no single, coherent model.

This module makes the top of the pyramid explicit and UNCONDITIONAL:

    IF YOU CAN SEE A PURE IN LIVE — grab it (SMASH).
    IF A PURE IS IN ECHO / on the edge of live AND walkable — walk in and grab it.
    IF the best thing you can see is LIVE MASS — chain it.

...regardless of redsign ownership or whether the seam machinery fired. Provenance
comes straight from the engine view (``red_tiles[].freshness``: ``fresh`` = LIVE,
``stale`` = ECHO) so there is no guessing.

Scope (Phase 1): only value the seat can actually SEE (LIVE + ECHO red, rich
LIVE blue). EXPECTED value (redsign fog, needs a probe to pin the exact cell) is
left to :mod:`.seam_control` (walk-in / probe-grab patterns) and the probe hints.
The grabs produced here are ``chain``-shaped (drop + contiguous walk) so the
existing deterministic packager compiles them with no new machinery.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from sea_of_colours.orchestrator_2.harnesses.tabula_v7.probe_hints import (
    _grid_dims,
    _known_green_cells,
    _tier_name,
    _visible_red,
)
from sea_of_colours.orchestrator_2.harnesses.tabula_v11.seam_control import (
    _HOLD_CAP_STEPS,
    _live_cells,
    _mass_tail,
    _walkin_from_live,
)

# Provenance tiers (engine truth from red_tiles[].freshness).
LIVE = "LIVE"
ECHO = "ECHO"
EXPECTED = "EXPECTED"  # redsign fog — not force-surfaced here (see seam_control)

# Value tiers mirror the engine purity bands (probe_hints._tier_name).
_PURE_MIN = 255
_MASS_MIN = 151
# Rich blue worth a grab — matches the sanitizer's blue-loot floor so we never
# surface a blue the corrector would then reroute around.
_BLUE_GRAB_MIN = 192
# A juice chain counts as a "strong" red claim on a harvester when it banks at
# least this many red points. Blue is only surfaced when orbital asks for it OR
# the seat has MORE harvesters than strong red chains (a spare unit that would
# otherwise idle / gather low-yield red) — see ``force_surface_grabs``.
_STRONG_CHAIN_RED_MIN = 150
# Short mass halo to sweep after banking the pure (kept tight — the pure is the
# prize; a long tail exposes the unit to weapons). The thinker/packager can trim.
_SMASH_TAIL = 3


@dataclass
class ValueCandidate:
    """One value cell the seat can SEE, tagged with provenance + default action."""

    cell: Tuple[int, int]
    purity: int
    tier: str            # pure | mass | vein | trace
    colour: str          # RED | BLUE
    provenance: str      # LIVE | ECHO
    drop_legal: bool     # under live coverage AND not green → can drop NOW


@dataclass
class GrabSpec:
    """A force-surfaced, ready-to-compile grab (chain-shaped: drop + walk)."""

    action: str                       # SMASH | WALK_IN | GRAB_MASS | GRAB_BLUE
    target: Tuple[int, int]           # the pure/mass/blue cell we are taking
    drop_at: Tuple[int, int]          # where the harvester lands
    cells: List[Tuple[int, int]]      # ordered walk (ends on / past the target)
    tier: str
    provenance: str
    colour: str = "RED"
    purity: int = 0
    note: str = ""                    # why this grab is surfaced (e.g. blue gate)


# ── provenance helpers ──────────────────────────────────────────────────
def _red_by_provenance(
    agent_view: Mapping[str, Any],
) -> Tuple[Dict[Tuple[int, int], int], Dict[Tuple[int, int], int]]:
    """Split ``red_tiles`` into (LIVE, ECHO) purity maps by ``freshness``."""
    live: Dict[Tuple[int, int], int] = {}
    echo: Dict[Tuple[int, int], int] = {}
    for row in (agent_view.get("red_tiles") or []):
        if not isinstance(row, Mapping):
            continue
        try:
            x, y = int(row["x"]), int(row["y"])
            p = int(row.get("purity") or 0)
        except (TypeError, KeyError, ValueError):
            continue
        if p <= 0:
            continue
        if str(row.get("freshness") or "") == "fresh":
            live[(x, y)] = p
        else:
            echo[(x, y)] = p
    return live, echo


def _rich_blue(agent_view: Mapping[str, Any]) -> Dict[Tuple[int, int], int]:
    """LIVE blue tiles at/above the grab floor, keyed (x, y) -> purity."""
    out: Dict[Tuple[int, int], int] = {}
    for row in (agent_view.get("blue_tiles") or []):
        if not isinstance(row, Mapping):
            continue
        try:
            x, y = int(row["x"]), int(row["y"])
            p = int(row.get("purity") or 0)
        except (TypeError, KeyError, ValueError):
            continue
        if p >= _BLUE_GRAB_MIN:
            out[(x, y)] = p
    return out


def build_candidates(agent_view: Mapping[str, Any]) -> List[ValueCandidate]:
    """The provenance-tagged value pyramid for THIS view (observability + tests).

    Ranked richest-first, LIVE before ECHO within a tier. Pure > mass > vein for
    red; rich blue is appended below red (it is loot but red always wins a tie).
    """
    live, echo = _red_by_provenance(agent_view)
    green = _known_green_cells(agent_view)
    live_cells = _live_cells(agent_view)

    def _cand(cell, p, prov) -> ValueCandidate:
        return ValueCandidate(
            cell=cell, purity=p, tier=_tier_name(p), colour="RED",
            provenance=prov,
            drop_legal=(cell in live_cells and cell not in green),
        )

    cands: List[ValueCandidate] = [_cand(c, p, LIVE) for c, p in live.items()]
    cands += [_cand(c, p, ECHO) for c, p in echo.items()]
    cands.sort(key=lambda c: (0 if c.provenance == LIVE else 1, -c.purity, c.cell[1], c.cell[0]))

    for c, p in sorted(_rich_blue(agent_view).items(), key=lambda kv: -kv[1]):
        cands.append(ValueCandidate(
            cell=c, purity=p, tier="blue", colour="BLUE", provenance=LIVE,
            drop_legal=(c in live_cells and c not in green),
        ))
    return cands


# ── force-surfaced grabs ─────────────────────────────────────────────────
def force_surface_grabs(
    agent_view: Mapping[str, Any],
    *,
    existing_targets: Set[Tuple[int, int]] = frozenset(),
    max_pure: int = 2,
    max_mass: int = 1,
    max_blue: int = 1,
    blue_requested: bool = False,
    harvesters_alive: Optional[int] = None,
    strong_chain_count: int = 0,
) -> List[GrabSpec]:
    """Ready-to-compile grabs for any SEEN pure/mass/blue not already targeted.

    * PURE (LIVE or ECHO): SMASH if drop-legal now, else WALK_IN from the nearest
      live frontier if walkable. Not-walkable pures are skipped (a probe is
      needed — that is seam_control / probe-hint territory, Phase 2).
    * MASS (LIVE, drop-legal): a plain chain grab when a rich mass cell isn't
      already covered.
    * BLUE (LIVE, drop-legal, rich): a HIGH-YIELD BLUE grab, surfaced only when it
      would NOT steal a harvester from red — i.e. orbital asks for it
      (``blue_requested``) OR the seat has more harvesters than strong red chains
      (``harvesters_alive`` > ``strong_chain_count``), so a spare unit that would
      otherwise idle / gather low-yield red goes to blue instead.

    ``existing_targets`` are cells already targeted by the seam/hot-drop/chain
    menu; we skip any grab whose target OR drop cell collides so we never
    double-offer the same value.
    """
    width, height = _grid_dims(agent_view)
    green = _known_green_cells(agent_view)
    live_cells = _live_cells(agent_view)
    live, echo = _red_by_provenance(agent_view)
    covered: Set[Tuple[int, int]] = set(existing_targets)
    specs: List[GrabSpec] = []

    # 1. PURES — richest first, LIVE preferred over ECHO.
    pures = [(c, p, LIVE) for c, p in live.items() if p >= _PURE_MIN]
    pures += [(c, p, ECHO) for c, p in echo.items() if p >= _PURE_MIN]
    pures.sort(key=lambda t: (0 if t[2] == LIVE else 1, -t[1], t[0][1], t[0][0]))

    n_pure = 0
    for cell, p, prov in pures:
        if n_pure >= max_pure or cell in covered:
            continue
        if cell in live_cells and cell not in green:
            tail = _mass_tail(agent_view, cell, green, width, height, {cell}, _SMASH_TAIL)
            specs.append(GrabSpec(
                action="SMASH", target=cell, drop_at=cell, cells=tail,
                tier="pure", provenance=prov, purity=p,
            ))
            covered.add(cell)
            covered.update(tail)
            n_pure += 1
            continue
        wk = _walkin_from_live(
            agent_view, cell, green, width, height,
            avoid_drops=covered, max_steps=_HOLD_CAP_STEPS,
        )
        if wk is None:
            continue  # needs a probe — leave to seam_control / probe hints
        drop, path = wk
        tail = _mass_tail(
            agent_view, cell, green, width, height, set(path) | {drop}, 2,
        )
        specs.append(GrabSpec(
            action="WALK_IN", target=cell, drop_at=drop, cells=list(path) + tail,
            tier="pure", provenance=prov, purity=p,
        ))
        covered.add(drop)
        covered.add(cell)
        covered.update(tail)
        n_pure += 1

    # 2. Best LIVE MASS (drop-legal) not already covered.
    masses = sorted(
        ((c, p) for c, p in live.items()
         if _MASS_MIN <= p < _PURE_MIN and c in live_cells
         and c not in green and c not in covered),
        key=lambda kv: (-kv[1], kv[0][1], kv[0][0]),
    )
    for cell, p in masses[:max_mass]:
        tail = _mass_tail(agent_view, cell, green, width, height, {cell}, _HOLD_CAP_STEPS)
        specs.append(GrabSpec(
            action="GRAB_MASS", target=cell, drop_at=cell, cells=tail,
            tier="mass", provenance=LIVE, purity=p,
        ))
        covered.add(cell)
        covered.update(tail)

    # 3. Rich LIVE BLUE (drop-legal) — HIGH-YIELD BLUE. Only surface it when it
    #    would NOT steal a harvester from red: orbital asks, OR there is a spare
    #    harvester beyond the strong red chains it could otherwise run.
    spare_harvester = (
        harvesters_alive is not None and harvesters_alive > strong_chain_count
    )
    if blue_requested or spare_harvester:
        if blue_requested:
            blue_note = (
                "orbital requests blue (blue vault low) — worth a harvester tonight"
            )
        else:
            blue_note = (
                f"spare harvester ({harvesters_alive}) beyond {strong_chain_count} "
                f"strong red chain(s) — grab blue rather than waste it on low-yield red"
            )
        blues = sorted(
            ((c, p) for c, p in _rich_blue(agent_view).items()
             if c in live_cells and c not in green and c not in covered),
            key=lambda kv: (-kv[1], kv[0][1], kv[0][0]),
        )
        for cell, p in blues[:max_blue]:
            tail = _mass_tail(agent_view, cell, green, width, height, {cell}, 2)
            specs.append(GrabSpec(
                action="GRAB_BLUE", target=cell, drop_at=cell, cells=tail,
                tier="blue", provenance=LIVE, colour="BLUE", purity=p,
                note=blue_note,
            ))
            covered.add(cell)
            covered.update(tail)

    return specs
