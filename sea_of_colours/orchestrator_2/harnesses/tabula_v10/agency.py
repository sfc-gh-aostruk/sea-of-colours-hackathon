"""v10 agency layer — the curated option MENU and the ID -> geometry RESOLVER.

This is the seam that turns "Python decides, agent transcribes" into "Python
CURATES, agent SELECTS, mover PACKAGES". Every tactical choice the harness has
already compiled — redsign seam PATTERNS, hot drops, probe placements, juice
chains, supersedes — is registered under a STABLE, human-legible ID this turn:

    SMASH_GRAB / BLIND_GRAB / UNBEATEN_FLANK / WALK_IN   (seam patterns)
    HD1 HD2 ...   hot drops
    PR1 PR2 ...   probe placements
    CH1 CH2 ...   juice chains
    SS1 SS2 ...   supersedes

Flow:
  1. ``build_registry`` assembles the ID -> :class:`Option` map from the already
     ranked hints + seam patterns (geometry stays deterministic).
  2. ``format_menu_block`` renders the menu for the THINKER prompt — it reasons
     over ownership / players / weapons and returns an ordered ``plan`` of IDs.
  3. ``resolve_plan`` validates the thinker's chosen IDs against the registry
     (unknown IDs are dropped — the menu is the source of truth).
  4. ``format_execute_block`` renders the selected options, in the thinker's
     order, as a verbatim "EXECUTE THESE" recipe for the MOVER to package into
     moves. Low transcription risk: the mover copies pre-built geometry.

The registry MUST be rebuilt identically for the thinker prompt and the resolve
step (same inputs -> same IDs), so the harness builds it once per night.
"""

from __future__ import annotations

import re
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from sea_of_colours.orchestrator_2.harnesses.tabula_v10 import comb_shapes
from sea_of_colours.orchestrator_2.harnesses.tabula_v10.seam_control import (
    SeamPattern,
)
from sea_of_colours.orchestrator_2.harnesses.tabula_v7.probe_hints import (
    _grid_dims,
    _vision_disk,
    _visible_red,
)

# Comb-shape variants offered per hot drop (the user's "length/area is the
# agent's choice"). Suffix keeps the ID short + legible; the thinker picks one.
_SHAPE_META = {
    "STRETCH": ("L", "stretch — long line, MAX intel/area (may leave the disk)"),
    "SWEEP": ("T", "sweep — TIGHT dense harvest around the drop"),
    "SAMPLE": ("Q", "sample — quick 2-step in/out (hot/CONTESTED grab)"),
}
_SHAPE_ORDER = ("STRETCH", "SWEEP", "SAMPLE")


@dataclass
class Option:
    """A single selectable tactical option with pre-filled geometry."""

    option_id: str
    kind: str            # "seam" | "hotdrop" | "probe" | "chain" | "supersede"
    title: str           # compact menu label
    detail: str          # "when to pick me" context for the menu
    execute_lines: List[str] = field(default_factory=list)
    payload: Dict[str, Any] = field(default_factory=dict)

    def menu_line(self) -> str:
        detail = f" — {self.detail}" if self.detail else ""
        return f"  [{self.option_id}] {self.title}{detail}"


# ── helpers ─────────────────────────────────────────────────────────────
def _xy(v: Any) -> Optional[str]:
    if isinstance(v, (list, tuple)) and len(v) == 2:
        try:
            return f"({int(v[0])},{int(v[1])})"
        except (TypeError, ValueError):
            return None
    return None


def _walk(cells: Sequence[Any]) -> str:
    out = []
    for c in cells or []:
        s = _xy(c)
        if s:
            out.append(s)
    return " ".join(out)


# ── registry construction ───────────────────────────────────────────────
def _seam_option(p: SeamPattern) -> Option:
    # Surface the wave-1 DROP cell in the menu line so the pure-grab reads as a
    # CONCRETE target (not vague prose) — otherwise the thinker gravitates to the
    # raw hot-drop coords and misses the pure (the day-2 whiff).
    detail = p.when
    if p.waves:
        d = p.waves[0].drop_at
        detail = f"wave-1 drop ({int(d[0])},{int(d[1])}) — {p.when}"
    return Option(
        option_id=p.pattern_id,
        kind="seam",
        title=p.title,
        detail=detail,
        execute_lines=p.execute_block().splitlines(),
        payload=p.to_dict(),
    )


def _hotdrop_option(
    idx: int,
    h: Mapping[str, Any],
    *,
    id_suffix: str = "",
    shape_blurb: str = "",
) -> Option:
    probe = _xy(h.get("probe_at"))
    drop = _xy(h.get("drop_at"))
    walk = _walk(h.get("comb_path") or [])
    sig = str(h.get("signal_type") or "signal")
    unit = str(h.get("unit") or "a harvester")
    oid = f"HD{idx}{id_suffix}"
    line = f"{oid}: probe {probe} -> drop {drop}"
    if walk:
        line += f" -> walk {walk}"
    line += f"  (unit {unit})"
    exec_lines = [line]
    sup = _xy(h.get("supersede"))
    if sup:
        exec_lines.append(
            f"  FIRST MOVE: probe {sup} to SUPERSEDE the finder's probe "
            "(blind them before you drop — do NOT skip this)"
        )
    detail = f"{sig} hot drop"
    if shape_blurb:
        detail += f", {shape_blurb}"
    if h.get("contested"):
        detail += ", CONTESTED"
    return Option(
        option_id=oid,
        kind="hotdrop",
        title=f"{sig} hot drop {drop or '?'}",
        detail=detail,
        execute_lines=exec_lines,
        payload=dict(h),
    )


def _num_xy(v: Any) -> Optional[Tuple[int, int]]:
    """Numeric (x, y) from a [x, y]/(x, y) pair — unlike ``_xy`` which formats
    a display string. Returns None for anything else."""
    if isinstance(v, (list, tuple)) and len(v) == 2:
        try:
            return int(v[0]), int(v[1])
        except (TypeError, ValueError):
            return None
    return None


def _hotdrop_value_cells(
    h: Mapping[str, Any], agent_view: Mapping[str, Any],
) -> List[Tuple[int, int]]:
    """Visible value (red + blue) inside the hot drop's probe disk.

    SWEEP/SAMPLE combs bias their walk toward these cells. Without them the
    combs walked blind and could route AROUND the very cluster the drop landed
    on (the "walked around its own live blue" bug). We rank red by purity and
    append any blue tiles in the disk so a bluesign hot drop sweeps its cluster.
    """
    probe = _num_xy(h.get("probe_at")) or _num_xy(h.get("drop_at"))
    if probe is None:
        return []
    width, height = _grid_dims(agent_view)
    disk = set(_vision_disk(probe[0], probe[1], width, height))
    red = _visible_red(agent_view)
    cells = sorted((c for c in red if c in disk), key=lambda c: -red[c])
    seen = set(cells)
    for row in (agent_view.get("blue_tiles") or []):
        if not isinstance(row, Mapping):
            continue
        try:
            c = (int(row["x"]), int(row["y"]))
        except (TypeError, KeyError, ValueError):
            continue
        if c in disk and c not in seen:
            cells.append(c)
            seen.add(c)
    return cells


def _hotdrop_shape_options(
    idx: int, h: Mapping[str, Any], agent_view: Mapping[str, Any],
) -> List[Option]:
    """Expand one hot drop into its comb-shape variants (STRETCH/SWEEP/SAMPLE).

    Same probe+drop, three walks the thinker chooses between. A shape with an
    empty walk (boxed in by green/edge) is skipped; if none survive we fall back
    to the drop's own precompiled comb as a single plain HDn so the drop is never
    lost. Each variant shares ``group`` so the packager treats them as one drop.
    """
    variants = comb_shapes.comb_variants(
        agent_view, h.get("probe_at"), h.get("drop_at"),
        value_cells=_hotdrop_value_cells(h, agent_view),
    )
    opts: List[Option] = []
    for shape in _SHAPE_ORDER:
        comb = variants.get(shape) or []
        if not comb and shape != "SAMPLE":
            continue
        suffix, blurb = _SHAPE_META[shape]
        payload = dict(h)
        payload["comb_path"] = comb
        payload["shape"] = shape
        payload["group"] = f"HD{idx}"
        opts.append(_hotdrop_option(idx, payload, id_suffix=suffix, shape_blurb=blurb))
    if not opts:
        opts.append(_hotdrop_option(idx, h))
    return opts


def _probe_option(idx: int, h: Mapping[str, Any]) -> Option:
    at = _xy(h.get("at"))
    frm = str(h.get("extends_from") or "fog")
    detail = f"extends {frm}"
    if h.get("contested"):
        detail += ", CONTESTED"
    return Option(
        option_id=f"PR{idx}",
        kind="probe",
        title=f"probe {at or '?'}",
        detail=detail,
        execute_lines=[f"PR{idx}: launch a probe at {at}"],
        payload=dict(h),
    )


def _chain_option(idx: int, h: Mapping[str, Any]) -> Option:
    drop = _xy(h.get("drop_at"))
    cells = _walk(h.get("cells") or [])
    length = int(h.get("length") or 0)
    unit = str(h.get("unit") or "a harvester")
    line = f"CH{idx}: drop {drop} then walk {cells}  (unit {unit})"
    return Option(
        option_id=f"CH{idx}",
        kind="chain",
        title=f"juice chain {drop or '?'} (x{length})",
        detail="known-red walk, no probe needed",
        execute_lines=[line],
        payload=dict(h),
    )


def _supersede_option(idx: int, h: Mapping[str, Any]) -> Option:
    at = _xy(h.get("probe_at"))
    return Option(
        option_id=f"SS{idx}",
        kind="supersede",
        title=f"supersede enemy probe {at or '?'}",
        detail="land your probe on theirs to blind it (yours survives)",
        execute_lines=[f"SS{idx}: launch a probe onto {at} to supersede the enemy probe"],
        payload=dict(h),
    )


# ── frontier hot-drop (gated last-resort) ───────────────────────────────
# Purity floor below which known RED counts as "trace-only" (nothing worth a
# real chain). Mirrors the engine's vein floor so the gate matches scoring.
try:  # pragma: no cover - defensive import
    from sea_of_colours.orchestrator_2.harnesses.tabula_v7.probe_hints import (
        _VEIN_MIN_PURITY as _TRACE_CEIL,
    )
except Exception:  # pragma: no cover
    _TRACE_CEIL = 51

_FRONTIER_WALK = 3  # blind sample — a short walk, mover trims to danger/hours


def _best_known_red_purity(
    chain_hints: Sequence[Mapping[str, Any]], agent_view: Mapping[str, Any],
) -> int:
    """Peak purity of any RED the seat already knows it can harvest.

    Reads the compiled chain hints (their per-cell purities) and the visible-red
    tiles. This is the yield the frontier hot-drop is gated against: if the best
    known red is only trace, a blind drop into promising fog can beat it.
    """
    best = 0
    for h in chain_hints or []:
        for p in (h.get("purities") or []):
            try:
                best = max(best, int(p))
            except (TypeError, ValueError):
                continue
    for t in (agent_view.get("red_tiles") or []):
        if isinstance(t, Mapping):
            try:
                best = max(best, int(t.get("purity") or 0))
            except (TypeError, ValueError):
                continue
    return best


def _frontier_hotdrop_option(
    agent_view: Mapping[str, Any],
    chain_hints: Sequence[Mapping[str, Any]],
    probe_hints: Sequence[Mapping[str, Any]],
    *,
    has_seam: bool,
    has_hotdrop: bool,
) -> Optional[Option]:
    """A blind hot-drop into the best echo/fog cluster — ONLY as a last resort.

    Gate (all must hold): no redsign seam pattern and no bluesign/redsign hot
    drop are on offer (those are strictly better targets), AND the best RED the
    seat already knows is trace-only (< the vein floor), AND there is a promising
    fog target (a probe hint with echo/seam promise). Otherwise returns None so
    the option never appears when real red is available — exactly the user's
    "only if there is nothing beyond trace" gate.
    """
    if has_seam or has_hotdrop:
        return None
    if _best_known_red_purity(chain_hints, agent_view) >= _TRACE_CEIL:
        return None

    best = None
    for h in probe_hints or []:
        if not isinstance(h, Mapping):
            continue
        at = h.get("at")
        if not (isinstance(at, (list, tuple)) and len(at) == 2):
            continue
        ep = int(h.get("edge_promise") or 0)
        if ep <= 0:
            continue
        if best is None or ep > best[0]:
            best = (ep, (int(at[0]), int(at[1])), h)
    if best is None:
        return None

    ep, (tx, ty), hint = best
    world = agent_view.get("world") or {}
    w = int(world.get("width") or 40)
    hgt = int(world.get("height") or 28)
    # A short blind sample walk from the drop cell, kept in-bounds. Fixed bearing
    # (E then S) — it is blind terrain, so this is only a suggestion the mover
    # trims; the DROP cell auto-harvests whatever is under it.
    walk: List[str] = []
    cx, cy = tx, ty
    for dx, dy in ((1, 0), (1, 0), (0, 1)):
        nx, ny = min(max(cx + dx, 0), w - 1), min(max(cy + dy, 0), hgt - 1)
        if (nx, ny) != (cx, cy):
            walk.append(f"({nx},{ny})")
            cx, cy = nx, ny
        if len(walk) >= _FRONTIER_WALK:
            break
    line = f"FR1: probe ({tx},{ty}) -> drop ({tx},{ty})"
    if walk:
        line += " -> walk " + " ".join(walk)
    line += "  (unit a harvester; blind sample — pick up when the hold fills)"
    return Option(
        option_id="FR1",
        kind="frontier",
        title=f"frontier hot-drop ({tx},{ty})",
        detail=(
            "LAST RESORT — known red is trace-only; blind-drop into the best "
            f"echo (edge_promise={ep}) to sample fresh red rather than idle a unit"
        ),
        execute_lines=[line],
        payload=dict(hint),
    )


def build_registry(
    *,
    agent_view: Mapping[str, Any],
    seam_patterns: Sequence[SeamPattern] = (),
    hot_drop_hints: Sequence[Mapping[str, Any]] = (),
    probe_hints: Sequence[Mapping[str, Any]] = (),
    chain_hints: Sequence[Mapping[str, Any]] = (),
    supersede_hints: Sequence[Mapping[str, Any]] = (),
) -> "OrderedDict[str, Option]":
    """Assemble the ordered ID -> Option registry for this night.

    Order (and thus menu order): seam patterns first (the redsign centrepiece),
    then hot drops, probes, chains, supersedes.
    """
    reg: "OrderedDict[str, Option]" = OrderedDict()

    for p in seam_patterns or []:
        if isinstance(p, SeamPattern):
            opt = _seam_option(p)
            reg[opt.option_id] = opt

    # A REDSIGN hot-drop hint is ALREADY represented by a seam PATTERN
    # (SMASH_GRAB / BLIND_GRAB), which lands ON the pure. Registering it AGAIN as
    # a raw HDn is a trap: those HD cells sit NEAR the jittered smear, 2-3 cells
    # SHORT of the pure, and the thinker picks the concrete-looking HD over the
    # pattern (the day-2 whiff — banked trace, missed the 765 pure). So drop
    # redsign HDs from the raw menu whenever seam patterns exist; keep BLUESIGN
    # hot-drops (night-1 blue has no pattern representation).
    kept_hotdrops = [
        h for h in (hot_drop_hints or [])
        if isinstance(h, Mapping)
        and not (str(h.get("signal_type") or "") == "redsign" and seam_patterns)
    ]
    for i, h in enumerate(kept_hotdrops, start=1):
        for opt in _hotdrop_shape_options(i, h, agent_view):
            reg[opt.option_id] = opt

    for i, h in enumerate(probe_hints or [], start=1):
        if isinstance(h, Mapping):
            opt = _probe_option(i, h)
            reg[opt.option_id] = opt

    for i, h in enumerate(chain_hints or [], start=1):
        if isinstance(h, Mapping):
            opt = _chain_option(i, h)
            reg[opt.option_id] = opt

    for i, h in enumerate(supersede_hints or [], start=1):
        if isinstance(h, Mapping):
            opt = _supersede_option(i, h)
            reg[opt.option_id] = opt

    # FRONTIER hot-drop (gated last resort): only added when there is no better
    # target on the board (no seam / hot drop) AND known red is trace-only.
    frontier = _frontier_hotdrop_option(
        agent_view, chain_hints, probe_hints,
        has_seam=bool(seam_patterns), has_hotdrop=bool(hot_drop_hints),
    )
    if frontier is not None:
        reg[frontier.option_id] = frontier

    return reg


# ── menu render (for the thinker prompt) ────────────────────────────────
_KIND_HEADERS = [
    ("seam", "REDSIGN PATTERNS (multi-wave campaigns — pick & order by case)"),
    ("hotdrop", "HOT DROPS (probe+drop into fresh fog this night)"),
    ("probe", "PROBE PLACEMENTS (open fresh vision)"),
    ("chain", "JUICE CHAINS (walk known red, no probe)"),
    ("supersede", "SUPERSEDES (blind an enemy probe)"),
    ("frontier", "FRONTIER HOT-DROP (last resort — known red is trace-only)"),
]


def format_menu_block(registry: "Mapping[str, Option]") -> str:
    """Render the ID'd option menu for the THINKER to select from.

    Empty when the registry is empty. Grouped by kind for legibility; every
    line leads with the stable ID the thinker must echo into ``plan``.
    """
    if not registry:
        return ""
    by_kind: Dict[str, List[Option]] = {}
    for opt in registry.values():
        by_kind.setdefault(opt.kind, []).append(opt)

    lines: List[str] = [
        "OPTION MENU (SELECT by ID — put the IDs you choose, in execution "
        "order, into \"plan\"; the geometry is pre-filled for you):",
    ]
    for kind, header in _KIND_HEADERS:
        opts = by_kind.get(kind)
        if not opts:
            continue
        lines.append(f" {header}:")
        for opt in opts:
            lines.append(opt.menu_line())
    return "\n".join(lines) + "\n"


# ── plan recovery (prose CoT -> ordered IDs) ────────────────────────────
def recover_plan_from_prose(
    reasoning: str, registry: "Mapping[str, Option]", *, max_ids: int = 6,
) -> List[str]:
    """Salvage an ordered plan from the thinker's PROSE when the JSON ``plan``
    came back empty (F4/O8: the thinker names ``BLIND_GRAB`` / ``SS1`` in its
    chain-of-thought but forgets to echo the IDs into the structured field, so
    ``resolve_plan([])`` returns nothing and the decisive seam geometry — incl.
    the finder-probe supersede — never reaches the mover).

    We scan the reasoning for EXACT registry IDs (token-bounded, case-insensitive
    — ``#`` and ``_`` count as ID chars so ``SMASH_GRAB`` and ``BLIND_GRAB#2`` are
    matched whole and not as substrings of each other), and return the IDs in the
    order they FIRST appear (that ordering encodes the thinker's wave priority),
    deduped and capped. Returns [] when nothing recognisable is present — the
    caller then falls back to the classic directive block exactly as before, so
    this can only ADD a recovered plan, never corrupt a good one.
    """
    if not reasoning or not registry:
        return []
    text = reasoning.upper()
    hits: List[tuple] = []
    for oid in registry:
        oid_u = oid.upper()
        pat = re.compile(
            r"(?<![A-Z0-9_#])" + re.escape(oid_u) + r"(?![A-Z0-9_#])"
        )
        m = pat.search(text)
        if m is not None:
            hits.append((m.start(), oid))
    hits.sort(key=lambda t: t[0])
    out: List[str] = []
    for _pos, oid in hits:
        if oid not in out:
            out.append(oid)
        if len(out) >= max_ids:
            break
    return out


# ── resolver (thinker plan -> mover recipe) ─────────────────────────────
# A coordinate decoration the thinker sometimes bolts onto a bare id, e.g.
# ``PR1_at_22_18`` / ``PR1@(22,18)`` / ``PR1 at 22,18`` instead of ``PR1``. We
# strip it so the id still resolves rather than being dropped as unknown (which
# silently lost probes — the night-6 "0 probes launched" wart).
_ID_DECORATION = re.compile(r"(?i)[ _]?(?:at[_ ]?|@)\(?\d+[\d ,_)]*$")


def _normalize_option_id(raw: str) -> str:
    """Bare option id: upper-cased, with any trailing coordinate tail stripped."""
    key = raw.strip().upper()
    return _ID_DECORATION.sub("", key).strip("_ ")


def resolve_plan(
    plan_ids: Sequence[str], registry: "Mapping[str, Option]",
) -> List[Option]:
    """Expand the thinker's chosen IDs to concrete options, in its order.

    Case-insensitive match against the registry; a bare-id fallback strips any
    coordinate decoration the thinker appended (``PR1_at_22_18`` -> ``PR1``).
    Unknown / duplicate IDs are dropped (the menu is authoritative). Returns []
    when nothing resolves.
    """
    if not plan_ids or not registry:
        return []
    upper = {k.upper(): v for k, v in registry.items()}
    out: List[Option] = []
    seen: set = set()
    for raw in plan_ids:
        if not isinstance(raw, str):
            continue
        key = raw.strip().upper()
        opt = upper.get(key) or upper.get(_normalize_option_id(raw))
        if opt is None or opt.option_id in seen:
            continue
        seen.add(opt.option_id)
        out.append(opt)
    return out


# Option kinds that actually DEPLOY a harvester (bank RED). Probes/supersedes
# alone bank nothing — the final-night collapse was a plan of only these.
_DEPLOY_KINDS = frozenset({"seam", "hotdrop", "chain", "frontier"})


def ensure_final_night_deploy(
    selected: Sequence[Option],
    registry: "Mapping[str, Option]",
    *,
    alive_harvesters: int,
    is_final_night: bool,
) -> Tuple[List[Option], bool]:
    """R5 — guarantee the final-night plan actually deploys a harvester.

    After a chain loss the thinker sometimes picks an all-probes/supersede plan
    on the LAST night — probes only pay off on a tomorrow that never comes, so
    the seat banks zero (the vs-HEUR d7 defensive collapse). This is a thinker
    posture bug the deterministic packager cannot fix (it faithfully compiles a
    no-deploy plan). When it is the final night and a harvester is alive but the
    resolved plan deploys none, prepend the best available deploy option (registry
    order: seam > hot-drop > chain > frontier). No-op otherwise. Returns
    ``(options, injected)``.
    """
    out = list(selected)
    if not is_final_night or alive_harvesters <= 0:
        return out, False
    if any(o.kind in _DEPLOY_KINDS for o in out):
        return out, False
    for opt in registry.values():
        if opt.kind in _DEPLOY_KINDS:
            return [opt] + out, True
    return out, False


def format_execute_block(selected: Sequence[Option]) -> str:
    """Render the resolved options as a PRIORITY-ORDERED recipe for the MOVER.

    The list is the thinker's committed plan, in PRIORITY order (item 1 first).
    The mover PACKAGES it — it owns the mechanics (which unit runs which item,
    the exact hour each move lands, trimming to fit the 21h night / 6-parcel hold
    / legality) but it does NOT re-plan: it may not drop a higher item, re-target
    a cell, or turn a probe into a drop (or vice-versa), or add an off-menu move.

    Empty when nothing was selected (the harness then falls back to the classic
    strategist-directive block, preserving v7/v8 behaviour).
    """
    if not selected:
        return ""
    n = len(selected)
    lines = [
        "EXECUTE THIS PLAN — it is your reasoning pass's committed decision, in "
        "PRIORITY ORDER (item 1 = highest priority). You are the PACKAGER, not a "
        "planner. Your job and ONLY your job:",
        "  * WHAT & WHERE are FIXED. Emit EVERY probe / supersede / drop / walk "
        "line below as a real move. Do NOT drop an item, move a target cell, turn "
        "a probe into a drop (or the reverse), or add ANY move that is not listed "
        "(no off-menu hot drops, no extra probes to 'use every unit' — the plan "
        "already sized the fleet).",
        "  * HOW & WHEN are YOURS. Assign each item to a specific unit, choose the "
        "hour each move lands, and interleave the items across the night.",
        "  * IF SOMETHING MUST GIVE, CUT FROM THE BOTTOM. When hours / units / "
        f"probes run short, drop the LAST item(s) first (item {n} before item "
        f"{n - 1} …), and within a kept item shorten its WALK TAIL — never skip "
        "or shorten a higher-priority item to fit a lower one. Item 1 lands.",
        "  * Legality still binds: if an exact drop cell is not drop-legal, use "
        "the nearest legal cell from the SAME item's geometry — do not re-target "
        "to a different objective.",
        "PLAN (priority order):",
    ]
    for i, opt in enumerate(selected, start=1):
        for j, line in enumerate(opt.execute_lines):
            prefix = f" {i}. " if j == 0 else "     "
            lines.append(f"{prefix}{line}")
    return "\n".join(lines) + "\n"
