"""Prompt assembly for tabula.

Combines four blocks into one prompt:

1. RULES_SUMMARY (from :mod:`.rules`, static)
2. YOUR STATE — day, vault_score, harvesters_alive, probes_alive, visible RED cells
3. YOUR MEMORY — last 3 memory entries formatted as prose
4. HEURISTIC SUGGESTIONS — top-3 chain hints from :mod:`.heuristic_chains`
5. ACTION SCHEMA — strict JSON output contract

Phase 1 output schema (v3 with predict/reflect):
{
  "reflection_on_last_night": {                 -- null on night 1
    "predicted": "high|medium|low",
    "actual": <int>,
    "gap_reason": "one sentence"
  } | null,
  "plan_this_turn": "one sentence",
  "rationale": "one line on WHY",
  "predicted_outcome": {
    "banked_pts_estimate": "high|medium|low",
    "what_could_go_wrong": "one sentence"
  },
  "moves": [ ... wire-format moves ... ],
  "memory_note": "one sentence, past tense, what I did"
}
"""

from __future__ import annotations

from typing import Any, List, Mapping, Sequence

from sea_of_colours.orchestrator_2.harnesses.tabula_v2.rules import (
    RULES_SUMMARY,
)


_ACTION_SCHEMA = """\
ACTION SCHEMA — output ONE JSON object starting with the open-brace
character. NO prose before the JSON. Fields:

  reflection_on_last_night: null on night 1; otherwise an object with:
    predicted: "high" | "medium" | "low"   (what you said last night)
    actual: integer                        (what the engine banked)
    gap_reason: "one sentence explaining any mismatch"

  plan_this_turn: string, one sentence.

  rationale: string, one line — WHY this plan beats alternatives.

  predicted_outcome:
    banked_pts_estimate: "high" | "medium" | "low"
      high   ≈ ≥ 1500 points banked this night
      medium ≈ 500–1500 points banked
      low    ≈ < 500 points OR high-uncertainty chain
    what_could_go_wrong: "one sentence naming the biggest risk"

  moves: list of wire-format actions. Each is one of:
    {"a":"drop",   "unit":"harvester_p1", "at":[x,y]}
    {"a":"step",   "unit":"harvester_p1", "to":[x,y]}
    {"a":"pickup", "unit":"harvester_p1"}
    {"a":"probe",  "at":[x,y]}
  Chain grammar: drop → step* → pickup PER harvester. Probes anywhere.

  memory_note: string, one sentence past tense, what you did this turn.
"""


def format_state_block(
    agent_view: Mapping[str, Any],
    *,
    day: int,
    day_cap: int,
    vault_score: int,
) -> str:
    """Compact YOUR STATE block. Only fields phase 1 uses."""
    entities = (agent_view.get("entities") or {}).get("mine") or []
    harvesters = [
        {
            "id": e.get("id"),
            "state": "surface" if e.get("pos") else "orbit",
            "at": e.get("pos"),
        }
        for e in entities
        if isinstance(e, Mapping) and str(e.get("type") or "") == "harvester"
    ]
    probes = [
        {
            "id": e.get("id"),
            "at": e.get("pos"),
            "nights_remaining": e.get("nights_remaining"),
        }
        for e in entities
        if isinstance(e, Mapping) and str(e.get("type") or "") == "probe"
    ]

    return (
        f"YOUR STATE (day {day} of {day_cap}):\n"
        f"  vault_score: {int(vault_score)}\n"
        f"  harvesters_alive: {harvesters}\n"
        f"  probes_alive: {probes}\n"
    )


def format_visible_red_block(agent_view: Mapping[str, Any]) -> str:
    """Compact list of RED cells you can currently see, with purity+tier."""
    world = agent_view.get("world") or {}
    rows: List[str] = []
    sg_rows: List[str] = []
    for row in (world.get("live") or []):
        if not isinstance(row, Mapping):
            continue
        tile = str(row.get("tile") or "")
        try:
            x, y = int(row["x"]), int(row["y"])
        except (TypeError, KeyError, ValueError):
            continue
        if tile == "RED":
            p = int(row.get("purity") or 0)
            tier = _tier(p)
            rows.append(f"    ({x},{y}) {tier} purity={p}")
        elif tile == "GREEN" and row.get("lineage") == "synthetic":
            sg_rows.append(f"({x},{y})")
    if not rows and not sg_rows and isinstance(world.get("grid"), list):
        for y, r in enumerate(world["grid"]):
            if not isinstance(r, list):
                continue
            for x, cell in enumerate(r):
                if not isinstance(cell, Mapping):
                    continue
                if str(cell.get("tile") or "") == "RED":
                    p = int(cell.get("purity") or 0)
                    rows.append(f"    ({x},{y}) {_tier(p)} purity={p}")
                elif str(cell.get("tile") or "") == "GREEN" and cell.get("synthetic"):
                    sg_rows.append(f"({x},{y})")
    body = "VISIBLE RED CELLS:\n"
    body += ("\n".join(rows) if rows else "    (none in current LOS)") + "\n"
    body += "SYNTHETIC-GREEN (do not step): " + (
        ", ".join(sg_rows) if sg_rows else "(none)"
    ) + "\n"
    return body


def _tier(purity: int) -> str:
    # Canonical engine bands — must match sea_of_colours/game/orbit_resolver.py::_tier_label
    # and sea_of_colours/agent/heuristic_agent.py:143. ONLY purity==255 is pure.
    p = int(purity or 0)
    if p >= 255:
        return "pure"
    if p >= 151:
        return "mass"
    if p >= 51:
        return "vein"
    return "trace"


def format_chain_hints_block(hints: Sequence[Mapping[str, Any]]) -> str:
    """Render the heuristic chain hints WITHOUT numeric scores."""
    if not hints:
        return "HEURISTIC SUGGESTIONS: (compiler produced no chains this turn)\n"
    lines = ["HEURISTIC SUGGESTIONS (starting points — pick, alter, or ignore):"]
    for i, h in enumerate(hints):
        unit = h.get("unit")
        cells = h.get("cells") or []
        tiers = h.get("tiers") or []
        purities = h.get("purities") or []
        cell_summary = ", ".join(
            f"({c[0]},{c[1]}) {tiers[j] if j < len(tiers) else '?'} "
            f"p={purities[j] if j < len(purities) else '?'}"
            for j, c in enumerate(cells)
        )
        lines.append(f"  Chain {chr(ord('A')+i)}: unit={unit} cells=[{cell_summary}]")
    lines.append("  (YOU compute EV using the tier table in RULES; scores are NOT provided.)")
    return "\n".join(lines) + "\n"


def format_setup_night_advisory(
    agent_view: Mapping[str, Any],
    day: int,
    day_cap: int,
) -> str:
    """Big fat advisory the prompt prepends when the agent has NO vision.

    Fires when the visible world is entirely fog — i.e. no visible RED
    cells AND no friendly probes on the surface. This is the "setup
    night" situation: the ONLY legal productive action is to launch
    probes. Drops fail because there is no live-vision cell to land on,
    steps do nothing without a harvester on the surface, and pickups
    are impossible without a harvester holding cargo. Say all of this
    to the agent so it doesn't burn hours trying illegal drops or
    passing the night.

    Returns an empty string when the agent DOES have vision (probes
    alive OR any red_tiles visible OR any friendly surface unit) so
    the advisory does not fire spuriously on days 2+.
    """
    red_visible = len(agent_view.get("red_tiles") or [])
    entities = (agent_view.get("entities") or {}).get("mine") or []
    friendly_probes = [
        e for e in entities
        if isinstance(e, Mapping) and str(e.get("type") or "") == "probe"
        and e.get("pos")  # on the surface
    ]
    friendly_surface_units = [
        e for e in entities
        if isinstance(e, Mapping)
        and str(e.get("type") or "") in ("harvester", "probe")
        and e.get("pos")
    ]
    if red_visible > 0 or friendly_probes or friendly_surface_units:
        return ""

    probe_stock = int((agent_view.get("orbit") or {}).get("probe_stock") or 0)
    world = agent_view.get("world") or {}
    fog_count = int(world.get("fog_count") or 0)

    lines = [
        "!!! SETUP NIGHT — YOU HAVE NO VISION !!!",
        "",
        f"  Every cell on the {world.get('width', '?')}x{world.get('height', '?')} "
        f"grid is fog. red_visible=0, no friendly probes are on the surface, "
        f"no harvester is on the surface. fog_count={fog_count}.",
        "",
        f"  You cannot DROP a harvester — drops require a live-vision cell "
        f"and there are none. You cannot STEP or PICKUP — those need a "
        f"harvester on the surface. The engine will REJECT any drop this "
        f"night.",
        "",
        f"  The ONLY productive action is PROBE. You have probe_stock="
        f"{probe_stock}. A probe reveals an 81-cell disk for 3 nights, so a "
        f"probe launched TONIGHT (day {day} of {day_cap}) provides vision on "
        f"nights {day+1}, {day+2}, and beyond up to its expiry.",
        "",
        "  RECOMMENDED SETUP-NIGHT PLAN:",
        "    * Launch 2 or 3 probes in DIFFERENT quadrants of the grid. "
        "One probe covers 81 cells (~7% of the board), so spreading probes "
        "unlocks more territory than stacking them.",
        "    * Blind-probe candidates: PROBE PLACEMENT HINTS below shows "
        "the best area_gain options. On night 1 all candidates have "
        "edge_promise=0 because there are no LOS edges yet — pick by "
        "area_gain alone.",
        "    * DO NOT submit an empty ``moves`` list. Passing on night 1 "
        "wastes the whole season — nights 2, 3, 4 will have nothing to "
        "harvest.",
        "    * DO NOT submit drop/step/pickup moves this night. The engine "
        "will reject them and you will bank zero.",
        "",
        "!!! End setup-night advisory !!!",
    ]
    return "\n".join(lines) + "\n"


def format_fog_and_echo_block(agent_view: Mapping[str, Any]) -> str:
    """Expose the fog map + echo hints so the LLM can reason about what
    it CAN'T see yet — the prerequisite for making probe decisions.

    Shows fog_count, up to 2 largest fog_clusters (centroid + nearest
    visible edge + size), and up to 5 best_red_echo cells if any.
    """
    world = agent_view.get("world") or {}
    fog_count = int(world.get("fog_count") or 0)
    probe_stock = int((agent_view.get("orbit") or {}).get("probe_stock") or 0)

    clusters = [c for c in (agent_view.get("fog_clusters") or []) if isinstance(c, Mapping)]
    clusters_sorted = sorted(clusters, key=lambda c: int(c.get("size") or 0), reverse=True)[:2]

    echo = [
        row for row in (((agent_view.get("navigation") or {}).get("best_red_echo")) or [])
        if isinstance(row, Mapping)
    ][:5]

    lines = ["FOG + ECHO (what you CAN'T see):"]
    lines.append(f"  fog_count: {fog_count}  probe_stock: {probe_stock}")
    if clusters_sorted:
        lines.append("  top_fog_clusters:")
        for c in clusters_sorted:
            centroid = c.get("centroid") or [None, None]
            nve = c.get("nearest_visible_edge") or [None, None]
            size = c.get("size")
            lines.append(
                f"    centroid=({centroid[0]},{centroid[1]}) size={size} "
                f"nearest_visible_edge=({nve[0]},{nve[1]})"
            )
    else:
        lines.append("  top_fog_clusters: (none — you see everything)")
    if echo:
        lines.append("  best_red_echo (traces beyond LOS — a probe here reveals real cells):")
        for row in echo:
            lines.append(
                f"    ({row.get('x')},{row.get('y')}) purity_est={row.get('purity') or row.get('value')}"
            )
    else:
        lines.append("  best_red_echo: (no echoes surfaced this turn)")
    return "\n".join(lines) + "\n"


def format_probe_hints_block(hints: Sequence[Mapping[str, Any]]) -> str:
    """Render probe-placement candidates the LLM can consider.

    Two ints per candidate: ``area_gain`` (new fog cells the disk would
    reveal) and ``edge_promise`` (purity-weighted seam-extension signal
    plus any echo cells inside the disk). NO combined score — the LLM
    picks its own tradeoff between raw territory gain and seam extension.
    """
    if not hints:
        return "PROBE PLACEMENT HINTS: (no fog to un-cover — probes not useful this turn)\n"
    lines = ["PROBE PLACEMENT HINTS (candidates — you may alter, reorder, or ignore):"]
    for i, h in enumerate(hints):
        at = h.get("at") or [None, None]
        lines.append(
            f"  Probe {chr(ord('A')+i)}: at=({at[0]},{at[1]}) "
            f"area_gain={h.get('area_gain')} "
            f"edge_promise={h.get('edge_promise')} "
            f"seed={h.get('extends_from')}"
        )
    lines.append(
        "  (area_gain = new cells revealed. edge_promise = purity-weighted "
        "seam extension + echo inside disk. YOU trade them off.)"
    )
    return "\n".join(lines) + "\n"


def build_prompt(
    *,
    agent_view: Mapping[str, Any],
    day: int,
    day_cap: int,
    vault_score: int,
    memory_replay: str,
    chain_hints: Sequence[Mapping[str, Any]],
    probe_hints: Sequence[Mapping[str, Any]] = (),
) -> str:
    """Assemble the full Tabula v2 prompt (harvest + probe intelligence)."""
    # The setup-night advisory only fires when the agent has literally
    # no vision — the strongest possible signal to say "your only move
    # is to probe". It's placed BEFORE RULES so it lands in the model's
    # first bytes and shapes everything that follows.
    setup_advisory = format_setup_night_advisory(agent_view, day, day_cap)

    return (
        setup_advisory
        + RULES_SUMMARY
        + "\n"
        + format_state_block(agent_view, day=day, day_cap=day_cap, vault_score=vault_score)
        + "\n"
        + format_visible_red_block(agent_view)
        + "\n"
        + format_fog_and_echo_block(agent_view)
        + "\n"
        + f"YOUR MEMORY (agent-authored, oldest first):\n{memory_replay}\n\n"
        + format_chain_hints_block(chain_hints)
        + "\n"
        + format_probe_hints_block(probe_hints)
        + "\n"
        + _ACTION_SCHEMA
        + "\nOUTPUT THE JSON OBJECT NOW. Start with the open-brace character. GO:\n"
    )
