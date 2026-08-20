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

from sea_of_colours.orchestrator_2.harnesses.tabula.rules import (
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


def build_prompt(
    *,
    agent_view: Mapping[str, Any],
    day: int,
    day_cap: int,
    vault_score: int,
    memory_replay: str,
    chain_hints: Sequence[Mapping[str, Any]],
) -> str:
    """Assemble the full phase-1 arena prompt."""
    return (
        RULES_SUMMARY
        + "\n"
        + format_state_block(agent_view, day=day, day_cap=day_cap, vault_score=vault_score)
        + "\n"
        + format_visible_red_block(agent_view)
        + "\n"
        + f"YOUR MEMORY (agent-authored, oldest first):\n{memory_replay}\n\n"
        + format_chain_hints_block(chain_hints)
        + "\n"
        + _ACTION_SCHEMA
        + "\nOUTPUT THE JSON OBJECT NOW. Start with the open-brace character. GO:\n"
    )
