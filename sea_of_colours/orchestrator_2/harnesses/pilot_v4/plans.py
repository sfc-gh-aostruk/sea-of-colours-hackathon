"""Sea of Colours — strategic plan taxonomy for the two-agent split.

The STRATEGIC agent picks ONE of these labels each turn based on the
situation. The TACTICAL agent takes the label + the harness's candidate
list and composes the specific move queue to submit.

Shared single source of truth: both Cortex agent specs reference this
list in their prompts, and the two-call rig uses these labels to parse
and validate the strategist's output.

The set is deliberately small (8) so the strategist has meaningful
choices without paralysis, and covers the shape of every night/orbit
turn we've observed across the seed-42 fixtures.
"""

from __future__ import annotations

from typing import Dict


# label → (short-description-for-strategist, tactic-hint-for-tactician)
PLAN_TAXONOMY: Dict[str, Dict[str, str]] = {
    "harvest_pure": {
        "description": "Chase MASS+/PURE chains. Score dominates; ignore denial slots.",
        "tactic_hint": "Pick the top harvest chain with any MASS or PURE cell in cells_traversed.",
        "phase": "planning",
    },
    "harvest_mixed": {
        "description": "Standard VEIN/MASS mixed chain revenue. The default play.",
        "tactic_hint": "Use candidates.recommended_policy.moves verbatim.",
        "phase": "planning",
    },
    "denial_dominant": {
        "description": "Supersede / crush / drop-block focus. Deny the rival; minimal harvest.",
        "tactic_hint": "Prioritise probe_supersede, harvester_crush, drop_block over harvest chains.",
        "phase": "planning",
    },
    "emp_race": {
        "description": "Pre-empt or race a rival EMP. Fire immediately if we can afford it.",
        "tactic_hint": "If emp_launch[0].affordability.can_fire == true, queue emp_launch first.",
        "phase": "planning",
    },
    "vault_flush_orbit": {
        "description": "ORBIT-only. Vault is under pressure; ship + refine consume all slots.",
        "tactic_hint": "Use orbital.recommended_orbit_policy.actions verbatim.",
        "phase": "orbit",
    },
    "probe_seed": {
        "description": "Coverage expansion. Few harvests, spend actions on probes.",
        "tactic_hint": "Take top 2-3 candidates.probes; skip low-score harvest chains.",
        "phase": "planning",
    },
    "defensive_repair": {
        "description": "ORBIT-only. Damaged harvesters; repair takes priority over spending.",
        "tactic_hint": "Repair every damaged harvester first, then top-up probes if slots remain.",
        "phase": "orbit",
    },
    "fleet_rebuild": {
        "description": "ORBIT-only. Harvester count below 2. Build a harvester first; ship/refine wait a turn.",
        "tactic_hint": "First orbit action = build_harvester(count=1). Ship/refine only if slots remain.",
        "phase": "orbit",
    },
    "final_day_push": {
        "description": "Final night. Maximum banked value; probes give zero future return.",
        "tactic_hint": "Pick harvest chain with highest expected_score_after_vault_cascade. Skip probes.",
        "phase": "planning",
    },
}


PLAN_LABELS = tuple(PLAN_TAXONOMY.keys())


def labels_for_phase(phase: str) -> tuple:
    """Plan labels valid in the given phase ('planning' or 'orbit')."""
    p = "orbit" if str(phase).lower() == "orbit" else "planning"
    return tuple(label for label, info in PLAN_TAXONOMY.items() if info.get("phase") == p)


def prompt_line_for_strategist(phase: str = "planning") -> str:
    """Render the phase-appropriate plan list for the STRATEGIC agent prompt.

    Only the plans that are legal in ``phase`` are shown, so the strategist
    cannot pick an orbit-only plan (fleet_rebuild, vault_flush_orbit,
    defensive_repair) during a Nox turn, or a night plan during orbit.
    """
    lines = ["Available plan labels — pick EXACTLY ONE:"]
    for label in labels_for_phase(phase):
        lines.append(f"  - {label}: {PLAN_TAXONOMY[label]['description']}")
    return "\n".join(lines)


def tactic_hint_for(label: str) -> str:
    """Return the tactician's cheat-sheet line for a given plan label.

    Falls back to an empty string if the strategist hallucinated a label
    outside the taxonomy — the tactician will then just default to
    recommended_policy.
    """
    entry = PLAN_TAXONOMY.get(label)
    return entry["tactic_hint"] if entry else ""
