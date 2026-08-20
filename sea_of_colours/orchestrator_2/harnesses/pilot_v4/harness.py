"""SOC_RED_REAPER_PILOT_V4 — two-phase *agentic* harness (haiku-4.5).

Design goal (2026-07): keep the two-phase split that PILOT_V3 introduced,
but put the *thinking* back. V3 collapsed into a single terse strategist
call whose output the harness rubber-stamped (``TACTICAL_LLM_ENABLED =
False``); V2 rambled because one call did all the analysis + composition.
V4 keeps BOTH phases as genuine — but bounded — LLM calls:

    1. STRATEGIST (``SOC_RED_REAPER_STRATEGIST_V4``, ~25s):
       reads STATE + the compiled candidate menu + threat/combat +
       redsign/blue_sign, reasons briefly, and commits to ONE plan label
       plus a short INTENT + PRIORITIES. No tools.

    2. TACTICIAN (``SOC_RED_REAPER_TACTICIAN_V4``, ~45s):
       reads the strategist's plan + the menu, then PICKS + ORDERS +
       lightly EDITS candidates (trim a chain to free slots) that best
       serve the plan. Emits a JSON selection. No tools.

    3. HARNESS: materialises the selection into a legal move queue,
       enforces invariants (≤ MAX_MOVES slots; *every* deployed / newly
       dropped harvester gets a pickup, or it dies at Aurora), and submits.
       Any parse / validation miss falls back to the always-legal doctrine
       ``recommended_policy`` (planning) / ``recommended_orbit_policy``
       (orbit).

The candidate compilers (``candidates`` / ``orbit`` / ``combat`` /
``threat_assess``) do all the spatial math — that is the "options menu"
the agents reason over. Nothing in the orchestrator imports from here; it
only knows this module's locator string.
"""

from __future__ import annotations

import json as _json
import re
import time
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from sea_of_colours.orchestrator_2.cortex_invoker import CortexAgentInvoker
from sea_of_colours.orchestrator_2.envelope import build_universal_envelope
from sea_of_colours.orchestrator_2.harnesses.pilot_v4.candidates import (
    compile_candidates,
)
from sea_of_colours.orchestrator_2.harnesses.pilot_v4.orbit import (
    compile_orbit_candidates,
)
from sea_of_colours.orchestrator_2.harnesses.pilot_v4 import rival_arsenal
from sea_of_colours.orchestrator_2.harnesses.pilot_v4.plans import (
    PLAN_LABELS,
    labels_for_phase,
    prompt_line_for_strategist,
)


# ── Agent identities + budgets ──────────────────────────────────────
INNER_CORTEX_AGENT = "SOC_RED_REAPER_PILOT_V4"  # audit-compat label
STRATEGIC_AGENT = "SOC_RED_REAPER_STRATEGIST_V4"
TACTICAL_AGENT = "SOC_RED_REAPER_TACTICIAN_V4"

_STRATEGIC_WALLCLOCK_S = 28
_TACTICAL_WALLCLOCK_S = 45
# haiku tends to write a short analysis BEFORE the committed footer even when
# told to lead with it. Fighting that wastes the footer; instead we feed a
# tiny brief (short analysis) and give enough capture room that the
# DIAGNOSIS/PLAN footer that FOLLOWS the analysis always lands and parses.
_STRATEGIC_RESPONSE_CAP = 10_000
_TACTICAL_RESPONSE_CAP = 8_000

MAX_MOVES = 21  # per-Nox policy slot cap (RULEBOOK §3.10, v0.9.9)

_PLANNING_VERBS = frozenset({"drop", "step", "pickup", "probe", "emp_launch"})
_ORBIT_VERBS = frozenset({
    "repair", "build_probe", "build_harvester", "build_emp", "build_chaff",
    "build_mine", "ship_catapult", "refine", "solar_jettison",
})


# ── Strategist doctrine ─────────────────────────────────────────────
# The "why" the user asked to bake in: RED PURE and REDSIGN economics,
# plus the BLUE blind-drop heuristic for spare harvesters. These are
# grounded in RULEBOOK §3.1 (scoring), §2.2 (purity tiers), §4.11
# (redsign), §3.5 (blue).
_STRATEGIST_HEAD = (
    "ROLE = STRATEGIST for Sea of Colours. NO tools. Budget ~20s.\n"
    "Your DOCTRINE lives in your system prompt (core loop, redsign race,\n"
    "chaff defence, contested-drop playbook, multi-harvester rule, blue\n"
    "economy). This turn brief only carries STATE — do NOT re-derive the\n"
    "doctrine, APPLY it. Keep analysis to a few short lines.\n\n"
    "DECISION BRIEF fields you MUST consult before picking a plan:\n"
    "  • my_harvesters[]  — per-unit {id, state, at, cargo, carrying_red,\n"
    "    damaged}. ANY damaged=true ⇒ `defensive_repair` this orbit BEFORE\n"
    "    infra spend — a damaged asset wastes tomorrow's Nox.\n"
    "  • weapon_stock     — {emp, chaff, mine}. Own EMP ≥ 1 + enemy near a\n"
    "    contested seam ⇒ `emp_race`/`denial_dominant`.\n"
    "  • credits, blue_purity_total — orbit affordability + BLUE spend.\n"
    "  • hoard.red_score_potential — shippable RED value. `vault_flush_orbit`\n"
    "    priority ladder (in this order): (a) red_score_potential ≥ 500, or\n"
    "    (b) ≥ 3 RED parcels in hoard, or (c) hoard.pct_full ≥ 0.7. Only\n"
    "    shipped RED scores — a hoard sitting on 6 pure parcels while you\n"
    "    build another probe is the single biggest tempo bleed we track.\n"
    "  • enemy_echoes[]   — last-seen enemy positions (stale probe intel).\n"
    "  • live_enemies[]   — enemy units CURRENTLY in your LOS with exact\n"
    "    positions. An entry here adjacent to a pure seam ⇒ contested;\n"
    "    consider denial before the harvest chain.\n"
    "  • redsign_cells[]  — public pure-seam beacon; race it if present.\n"
    "  • recent_emp_events, recent_chaff_events — what the rival did last\n"
    "    Nox. Chaff last night + no build ⇒ safer long chains; EMP-heavy\n"
    "    rival ⇒ build own chaff (`defensive_repair`/`fleet_rebuild`).\n"
    "  • combat_costs     — BUILD cost is paid in orbit; FIRING an\n"
    "    in-stock weapon costs NOTHING beyond the action slot. If\n"
    "    weapon_stock.emp >= 1 you CAN fire an EMP this Nox regardless\n"
    "    of credits — do NOT confuse build cost with fire cost.\n"
    "  • top_harvest / interdiction / emp — pre-scored candidate menu; the\n"
    "    tactician will pick from it. Their scores + can_fire flags are\n"
    "    ground truth, not vibes.\n\n"
    "PICK ONE plan from the list below; the tactician expands it.\n"
)

# The phase-appropriate plan list is spliced between HEAD and TAIL at run
# time (planning turns must not see orbit-only plans and vice-versa).
_STRATEGIST_TAIL = (
    "\n\nOUTPUT CONTRACT — you MAY write a brief analysis first (a few short\n"
    "lines, no markdown headers, no candidate-by-candidate ladder), but you\n"
    "MUST finish with these four lines exactly. The PLAN line is mandatory —\n"
    "if you omit the footer your choice is lost and doctrine is used instead:\n\n"
    "  DIAGNOSIS: <one sentence — day X/7, my score vs rival, key tension>\n"
    "  PLAN: <exactly one label from the list above>\n"
    "  INTENT: <1-2 sentences — what to prioritise and why (name redsign /\n"
    "    pure / blue / denial when relevant)>\n"
    "  PRIORITIES: <1-4 candidate IDs (H0, P1, S0, EMP0…) or coordinates>\n\n"
    "Keep it tight — trust the menu, don't recompute scores. End with the\n"
    "four lines.\n\n"
    "STATE (skim, don't dwell):\n\n"
)

_STRATEGIST_POSTAMBLE = (
    "\n═══════════════════════════════════════════════════════════\n"
    "END OF BRIEF. Keep any analysis to a few lines, then finish with the "
    "four lines DIAGNOSIS / PLAN / INTENT / PRIORITIES. The PLAN line is "
    "mandatory. Go:\n"
)


# ── Tactician doctrine ──────────────────────────────────────────────
_TACTICIAN_PREAMBLE_TMPL = (
    "ROLE = TACTICIAN for Sea of Colours seat \"{seat}\", phase \"{phase}\".\n"
    "Output ONE JSON object, starting immediately with the open-brace\n"
    "character. Any prose before the JSON is discarded; any prose after\n"
    "the closing brace is discarded. Skip the meta-analysis of your role\n"
    "or the schema — go straight to the JSON.\n\n"
    "Your DOCTRINE (multi-harvester rule, chaff-awareness, EMP timing) lives\n"
    "in your system prompt. Apply it; do NOT re-derive it in prose.\n\n"
    "STRATEGIST:\n{strategist_note}\n\n"
    "SCHEMA:\n"
    "  {{\"plan\":\"<label>\",\"selections\":[{{\"id\":\"H0\"}},{{\"id\":\"P1\",\"trim_to\":3}}],\"rationale\":\"one short sentence\"}}\n"
    "  - id: MENU candidate ID (or \"recommended_policy\" for the doctrine queue).\n"
    "  - trim_to (optional int): keep only first N moves of that candidate.\n"
    "  - Multi-harvester: if >= 2 alive harvesters, include ONE candidate per\n"
    "    unit (their ids differ — H0_harvester_p1 vs H0_harvester_p1_2).\n"
    "  - Fallback if unsure: {{\"plan\":\"{plan}\",\"selections\":[{{\"id\":\"recommended_policy\"}}],\"rationale\":\"accept doctrine\"}}.\n"
    "  - Hard cap: at most {max_moves} action slots across ALL picks.\n\n"
)

_TACTICIAN_ORBIT_PREAMBLE_TMPL = (
    "ROLE = TACTICIAN for Sea of Colours seat \"{seat}\", ORBIT phase.\n"
    "Output ONE JSON object starting with the open-brace character. Skip\n"
    "meta-analysis of your role or the schema — go straight to the JSON.\n"
    "Apply doctrine from your system prompt (ship-when-full, repair damaged,\n"
    "BLUE is spend currency); do NOT re-derive it.\n\n"
    "STRATEGIST:\n{strategist_note}\n\n"
    "SCHEMA:\n"
    "  {{\"plan\":\"<label>\",\"selections\":[{{\"id\":\"O0\"}},{{\"id\":\"O2\"}}],\"rationale\":\"one short sentence\"}}\n"
    "  - id: an ORBIT OPTION id, or \"recommended_orbit_policy\".\n"
    "  - Fallback: {{\"plan\":\"{plan}\",\"selections\":[{{\"id\":\"recommended_orbit_policy\"}}],\"rationale\":\"accept doctrine\"}}.\n"
    "  - Hard cap: at most {max_actions} orbit-action slots.\n\n"
)

_TACTICIAN_POSTAMBLE = (
    "\n═══════════════════════════════════════════════════════════\n"
    "OUTPUT THE JSON OBJECT NOW. Start with the open-brace character.\n"
    "No prose, no markdown, no code fences before the JSON. GO:\n"
)


# ── Strategist parsing ──────────────────────────────────────────────
_PLAN_RE = re.compile(
    r"\bPLAN(?:\s+LABEL)?\s*:?\s*\**\s*(?:This matches\s*)?\**\s*(" +
    "|".join(re.escape(l) for l in PLAN_LABELS) + r")",
    re.I,
)


def _parse_strategist_plan(text: str) -> str:
    m = _PLAN_RE.search(text or "")
    return m.group(1).lower() if m else ""


def _line_after(text: str, key: str) -> str:
    for line in (text or "").splitlines():
        if re.match(rf"^\s*\**\s*{key}\b", line, flags=re.I):
            return line.split(":", 1)[-1].strip().strip("*").strip()
    return ""


def _compact_strategist_note(text: str, *, default_plan: str = "harvest_mixed") -> str:
    """Distil the strategist output to the 4 fields the tactician needs.

    Prevents the tactician from inheriting rambling / cut-off prose.
    """
    plan = _parse_strategist_plan(text) or default_plan
    intent = _line_after(text, "INTENT") or "realise the plan with the best validated candidates"
    priorities = _line_after(text, "PRIORITIES") or _line_after(text, "TOP") or "recommended_policy"
    return f"PLAN: {plan}\nINTENT: {intent}\nPRIORITIES: {priorities}"


# ── Tactician parsing ───────────────────────────────────────────────
def _extract_decision_json(text: str) -> Tuple[Dict[str, Any], Optional[str]]:
    """Parse the tactician's JSON object, tolerating code fences + prose."""
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.I).strip()
        raw = re.sub(r"\s*```$", "", raw).strip()
    decoder = _json.JSONDecoder()
    for match in re.finditer(r"\{", raw):
        try:
            parsed, _ = decoder.raw_decode(raw[match.start():])
        except Exception:
            continue
        if isinstance(parsed, dict) and "selections" in parsed:
            return parsed, None
    return {}, "no_json_object"


# ── Candidate lookup ────────────────────────────────────────────────
def _candidate_lists(cands: Mapping[str, Any]) -> Sequence[Sequence[Mapping[str, Any]]]:
    return (
        cands.get("harvest") or [],
        cands.get("probes") or [],
        cands.get("probe_supersede") or [],
        cands.get("harvester_crush") or [],
        cands.get("hot_drop") or [],
        cands.get("drop_block") or [],
        cands.get("emp_launch") or [],
    )


def _find_candidate(cands: Mapping[str, Any], choice: str) -> Optional[Mapping[str, Any]]:
    choice = (choice or "").strip()
    if not choice:
        return None
    for group in _candidate_lists(cands):
        for cand in group:
            cid = str((cand or {}).get("id") or "")
            if cid == choice or cid.startswith(choice + "_") or cid.startswith(choice + "__"):
                return cand
    return None


# ── Pickup invariant + slot cap ─────────────────────────────────────
def _deployed_harvester_ids(agent_view: Mapping[str, Any]) -> List[str]:
    out: List[str] = []
    for a in (agent_view.get("my_assets") or []):
        if not isinstance(a, Mapping):
            continue
        if str(a.get("kind") or "").lower() != "harvester":
            continue
        if str(a.get("state") or "").lower() in ("deployed", "surface"):
            uid = str(a.get("id") or "")
            if uid:
                out.append(uid)
    return out


def _enforce_pickup_invariant(
    moves: List[Dict[str, Any]], agent_view: Mapping[str, Any]
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Guarantee every surface harvester gets a pickup (else it dies).

    A harvester is "on the surface this Nox" if it was already deployed at
    turn start OR it receives a ``drop`` in the queue. Any such unit lacking
    a ``pickup`` gets one appended (budget permitting). Returns the repaired
    queue + the list of unit ids we had to repair (for audit).
    """
    on_surface = set(_deployed_harvester_ids(agent_view))
    picked_up = set()
    for m in moves:
        verb = str(m.get("a") or "")
        unit = str(m.get("unit") or "")
        if verb == "drop" and unit:
            on_surface.add(unit)
        if verb == "pickup" and unit:
            picked_up.add(unit)
    repaired: List[str] = []
    for unit in on_surface:
        if unit in picked_up:
            continue
        if len(moves) >= MAX_MOVES:
            break  # no slot left; the engine will strike, but we tried
        moves.append({"a": "pickup", "unit": unit})
        repaired.append(unit)
    return moves, repaired


def _trim_candidate_moves(cand_moves: Sequence[Mapping[str, Any]], trim_to: Optional[int]) -> List[Dict[str, Any]]:
    out = [dict(m) for m in cand_moves]
    if not isinstance(trim_to, int) or trim_to <= 0 or trim_to >= len(out):
        return out
    kept = out[:trim_to]
    # Preserve the terminal pickup so trimming never strands the harvester.
    if out and out[-1].get("a") == "pickup" and (not kept or kept[-1].get("a") != "pickup"):
        kept.append(out[-1])
    return kept


def _materialize_planning(
    *,
    decision: Mapping[str, Any],
    expected_seat: str,
    compiled: Mapping[str, Any],
    agent_view: Mapping[str, Any],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    cands = compiled.get("candidates") or {}
    recommended = cands.get("recommended_policy") or {}
    fallback = [dict(m) for m in (recommended.get("moves") or [])]
    fallback, _ = _enforce_pickup_invariant(fallback, agent_view)
    info: Dict[str, Any] = {"fallback_used": False, "fallback_reason": "",
                            "selected_ids": [], "trimmed": [], "pickup_repaired": [],
                            "skipped_conflicts": []}

    selections = decision.get("selections")
    if not isinstance(selections, list) or not selections:
        info.update(fallback_used=True, fallback_reason="no_selections")
        return fallback, info

    def _units_of(mvs: Sequence[Mapping[str, Any]]) -> set:
        return {str(m.get("unit")) for m in mvs if m.get("unit")}

    moves: List[Dict[str, Any]] = []
    committed_units: set = set()  # a harvester may be committed to ONE chain/Nox
    for sel in selections:
        if not isinstance(sel, Mapping):
            continue
        sid = str(sel.get("id") or "").strip()
        if not sid:
            continue
        if sid == "recommended_policy":
            for m in (recommended.get("moves") or []):
                if len(moves) < MAX_MOVES:
                    moves.append(dict(m))
            committed_units |= _units_of(recommended.get("moves") or [])
            info["selected_ids"].append(sid)
            continue
        cand = _find_candidate(cands, sid)
        if cand is None:
            continue  # unknown id — skip; harness stays legal
        trim_to = sel.get("trim_to")
        cand_moves = _trim_candidate_moves(cand.get("moves") or [], trim_to)
        # One-commitment-per-harvester: H0/H1/H2 are usually alternative
        # chains for the SAME unit — selecting more than one would drop that
        # harvester at several cells in one Nox (illegal). Skip any candidate
        # whose unit is already committed.
        cand_units = _units_of(cand_moves)
        if cand_units & committed_units:
            info["skipped_conflicts"].append(str(cand.get("id")))
            continue
        if isinstance(trim_to, int):
            info["trimmed"].append({"id": cand.get("id"), "trim_to": trim_to})
        for m in cand_moves:
            if len(moves) < MAX_MOVES:
                moves.append(m)
        committed_units |= cand_units
        info["selected_ids"].append(str(cand.get("id")))

    # Verb legality — any illegal verb means we don't trust the queue.
    for idx, m in enumerate(moves):
        if str(m.get("a") or "") not in _PLANNING_VERBS:
            info.update(fallback_used=True, fallback_reason=f"illegal_verb:{m.get('a')}")
            return fallback, info

    if not moves:
        info.update(fallback_used=True, fallback_reason="no_valid_selections")
        return fallback, info

    moves, repaired = _enforce_pickup_invariant(moves, agent_view)
    info["pickup_repaired"] = repaired
    return moves[:MAX_MOVES], info


# ── Orbit option flattening + materialization ───────────────────────
# ── Plan → verb re-rank (v1.9) ──────────────────────────────────────
# When the strategist commits to a plan_label, the tactician's
# ``recommended_orbit_policy`` fallback should lead with an action that
# realises that plan — not whatever priority-ladder default the compiler
# put first. Otherwise a pilot that correctly picks
# ``defensive_repair`` still ships out with the default
# ``[build_probe, build_mine]`` recommended queue and never repairs.
_PLAN_VERB_HINTS: Dict[str, Tuple[str, ...]] = {
    "vault_flush_orbit": ("ship_catapult", "solar_jettison", "refine",
                          "refine_cascade"),
    "defensive_repair":  ("repair", "ship_catapult"),
    "fleet_rebuild":     ("build_harvester", "build_probe"),
    "emp_race":          ("build_emp",),
    "denial_dominant":   ("build_chaff", "build_emp", "build_mine"),
}


def _rerank_orbit_recommendation(
    orbital: Mapping[str, Any], plan_label: str,
) -> Dict[str, Any]:
    """Return a shallow-copied ``orbital`` block whose
    ``recommended_orbit_policy.actions`` list is reordered to lead with
    the action whose verb (`a` field) matches the strategist's plan.

    Non-matching actions retain their prior order after the promoted
    entries. If no entry matches, the input is returned unchanged
    (safe fallback).
    """
    if not plan_label:
        return dict(orbital)
    verbs = _PLAN_VERB_HINTS.get(plan_label.strip().lower())
    if not verbs:
        return dict(orbital)
    rec = (orbital.get("recommended_orbit_policy") or {})
    actions = list(rec.get("actions") or [])
    if not actions:
        return dict(orbital)
    verb_set = set(verbs)
    lead: List[Dict[str, Any]] = []
    rest: List[Dict[str, Any]] = []
    for act in actions:
        if isinstance(act, Mapping) and str(act.get("a") or "") in verb_set:
            lead.append(dict(act))
        else:
            rest.append(dict(act))
    if not lead:
        return dict(orbital)
    new_rec = dict(rec)
    new_rec["actions"] = lead + rest
    new_orbital = dict(orbital)
    new_orbital["recommended_orbit_policy"] = new_rec
    return new_orbital


def _flatten_orbit_options(orbital: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Assign synthetic O# ids to selectable orbit actions.

    The recommended list comes first (so O0.. mirror doctrine order), then
    notable alternatives from the sub-blocks the tactician might prefer.
    """
    options: List[Dict[str, Any]] = []
    seen: set = set()

    def _add(action: Optional[Mapping[str, Any]], label: str) -> None:
        if not isinstance(action, Mapping):
            return
        key = _json.dumps(action, sort_keys=True)
        if key in seen:
            return
        seen.add(key)
        options.append({"id": f"O{len(options)}", "label": label, "action": dict(action)})

    rec = (orbital.get("recommended_orbit_policy") or {}).get("actions") or []
    for a in rec:
        _add(a, "doctrine")
    enablers = orbital.get("play_enablers") or {}
    for r in (enablers.get("repair_candidates") or []):
        _add(r.get("action") if isinstance(r, Mapping) else r, "repair")
    _add((enablers.get("harvester_purchase") or {}).get("action"), "build_harvester")
    _add((enablers.get("probe_purchase") or {}).get("action"), "build_probe")
    vp = orbital.get("vault_pressure") or {}
    _add((vp.get("ship") or {}).get("action"), "ship_red")
    for opt in ((vp.get("refine") or {}).get("options") or [])[:1]:
        _add(opt.get("action") if isinstance(opt, Mapping) else opt, "refine")
    off = orbital.get("offensive_blue") or {}
    _add((off.get("emp_purchase") or {}).get("action"), "build_emp")
    _add((off.get("chaff_purchase") or {}).get("action"), "build_chaff")
    _add((off.get("mine_purchase") or {}).get("action"), "build_mine")
    return options


def _materialize_orbit(
    *,
    decision: Mapping[str, Any],
    orbital: Mapping[str, Any],
    options: Sequence[Mapping[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    recommended = orbital.get("recommended_orbit_policy") or {}
    fallback = [dict(a) for a in (recommended.get("actions") or [])]
    max_actions = int(orbital.get("max_actions") or 5)
    info: Dict[str, Any] = {"fallback_used": False, "fallback_reason": "", "selected_ids": []}

    selections = decision.get("selections")
    if not isinstance(selections, list) or not selections:
        info.update(fallback_used=True, fallback_reason="no_selections")
        return fallback[:max_actions], info

    by_id = {str(o["id"]): o for o in options}
    actions: List[Dict[str, Any]] = []
    for sel in selections:
        if not isinstance(sel, Mapping):
            continue
        sid = str(sel.get("id") or "").strip()
        if sid in ("recommended_orbit_policy", "recommended_policy"):
            for a in (recommended.get("actions") or []):
                if len(actions) < max_actions:
                    actions.append(dict(a))
            info["selected_ids"].append("recommended_orbit_policy")
            continue
        opt = by_id.get(sid)
        if opt is None:
            continue
        if len(actions) < max_actions:
            actions.append(dict(opt["action"]))
            info["selected_ids"].append(sid)

    for a in actions:
        if str(a.get("a") or "") not in _ORBIT_VERBS:
            info.update(fallback_used=True, fallback_reason=f"illegal_verb:{a.get('a')}")
            return fallback[:max_actions], info

    if not actions:
        info.update(fallback_used=True, fallback_reason="no_valid_selections")
        return fallback[:max_actions], info
    return actions[:max_actions], info


# ── STATE assembly ──────────────────────────────────────────────────
def _scrub_submit_instruction(base: str) -> str:
    return base.replace(
        "Read STATE below, then CALL soc_submit_policy on your FIRST "
        'tool call with p_policy as a JSON STRING: {"moves":[...]}.\n',
        "Read STATE below. Do NOT call tools; the harness validates your "
        "choice and submits it.\n",
    )


def _splice_state(session_id: str, view: Mapping[str, Any], *, is_orbit: bool) -> Tuple[str, Dict[str, Any]]:
    """Return (prompt_body, compiled_or_orbital) with extras spliced into STATE.

    Adds candidates/threat/combat/memory (night) or orbital (both) PLUS
    redsign/blue_sign — which the universal envelope drops but the V4
    doctrine needs — into the STATE JSON.
    """
    base = _scrub_submit_instruction(build_universal_envelope(session_id, view))
    agent_view = view.get("agent_view") or {}
    try:
        extras = compile_candidates(agent_view) if not is_orbit else {"orbital": compile_orbit_candidates(agent_view)}
    except Exception:
        extras = {}

    open_s = "STATE (JSON):\n```json\n"
    close_s = "\n```\n"
    i = base.find(open_s)
    j = base.find(close_s, i + len(open_s)) if i >= 0 else -1
    if i < 0 or j < 0:
        return base, extras
    try:
        state = _json.loads(base[i + len(open_s): j])
    except Exception:
        return base, extras

    if is_orbit:
        state["orbital"] = extras.get("orbital") or {}
    else:
        for key in ("candidates", "combat", "threat", "memory_summary"):
            if key in extras:
                state[key] = extras[key]
    # Splice the doctrine-relevant signals the envelope omits.
    for key in ("redsign", "blue_sign"):
        val = agent_view.get(key)
        if val:
            state[key] = val

    new_state = _json.dumps(state, ensure_ascii=False, separators=(",", ":"))
    return base[:i] + open_s + new_state + close_s + base[j + len(close_s):], extras


def _summarize_candidate(cand: Mapping[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "id": cand.get("id"),
        "score": cand.get("score", cand.get("expected_score_after_vault_cascade")),
        "moves": len(cand.get("moves") or []),
    }
    for key in ("unit", "kind", "at", "tier", "rationale_hint"):
        if key in cand:
            out[key] = cand.get(key)
    # EMP candidates: surface whether we can actually fire + the key effect,
    # so the tactician doesn't queue an unaffordable / self-freezing salvo.
    aff = cand.get("affordability")
    if isinstance(aff, Mapping):
        out["can_fire"] = bool(aff.get("can_fire"))
    eff = cand.get("expected_effect")
    if isinstance(eff, Mapping):
        out["enemy_hit"] = eff.get("enemy_unit_count")
        out["self_freeze"] = eff.get("self_freeze_unit_count")
    return {k: v for k, v in out.items() if v not in (None, "")}


def _tactician_menu(compiled: Mapping[str, Any],
                    arsenal_summary: Optional[Mapping[str, Any]] = None) -> str:
    """Build the tactician's candidate menu.

    v1.9 iteration note — the season regression run showed that
    tightening the per-category caps (6→3) starved the pilot of options
    and cut score from 1905 → 192. Restored to 6, but with the
    recommended_policy payload slimmed to a rationale hint + move count
    (the tactician can pick the whole thing by ID rather than seeing
    each move). Prompt savings come from the recommended_policy slim,
    not from menu truncation.
    """
    cands = compiled.get("candidates") or {}
    rec_raw = cands.get("recommended_policy") or {}
    if isinstance(rec_raw, Mapping):
        rec_summary: Dict[str, Any] = {
            "moves_count": len(rec_raw.get("moves") or []),
        }
        for hint_key in ("rationale_hint", "notes", "score", "expected_score"):
            if hint_key in rec_raw:
                rec_summary[hint_key] = rec_raw.get(hint_key)
    else:
        rec_summary = {}
    menu: Dict[str, Any] = {"recommended_policy": rec_summary}
    for key in ("harvest", "probes", "probe_supersede", "harvester_crush",
                "hot_drop", "drop_block", "emp_launch"):
        rows = [_summarize_candidate(c) for c in (cands.get(key) or [])[:6]]
        if rows:
            menu[key] = rows
    menu["threat"] = compiled.get("threat") or {}
    # Combat block: EMP mechanics (cost, radius, cloud hours) + our weapon
    # stock + blue available — the tactician needs these to sequence
    # emp_launch / denial candidates, not just harvest.
    menu["combat"] = compiled.get("combat") or {}
    if arsenal_summary and arsenal_summary.get("opponents"):
        menu["arsenal"] = arsenal_summary
    return "MENU (JSON):\n```json\n" + _json.dumps(menu, ensure_ascii=False, separators=(",", ":")) + "\n```\n"


def _tactician_orbit_menu(orbital: Mapping[str, Any], options: Sequence[Mapping[str, Any]]) -> str:
    menu = {
        "recommended_orbit_policy": orbital.get("recommended_orbit_policy") or {},
        "options": [{"id": o["id"], "label": o["label"], "action": o["action"]} for o in options],
        "max_actions": orbital.get("max_actions"),
        "trivial": orbital.get("trivial"),
    }
    return "ORBIT OPTIONS (JSON):\n```json\n" + _json.dumps(menu, ensure_ascii=False, separators=(",", ":")) + "\n```\n"


def _strategist_brief(view: Mapping[str, Any], extras: Mapping[str, Any], *, is_orbit: bool,
                       arsenal_summary: Optional[Mapping[str, Any]] = None) -> str:
    """A decision-relevant brief for the strategist.

    v1.9 — expanded to project doctrine-critical FIXTURE state directly from
    ``agent_view`` (weapon_stock, credits, per-harvester damage/cargo,
    enemy echoes, redsign cells, last-night EMP/chaff events, hoard
    summary). The prior ~12-field summary omitted these and forced the
    strategist to reason about state it couldn't see; the comprehension
    baseline traced 5 of 8 failures back to that projection gap.

    Growing the brief from ~500 B to ~2 KB is still well inside haiku's
    prompt budget — the doctrine text in ``_STRATEGIST_HEAD`` dominates
    the prompt, not this JSON.
    """
    agent_view = view.get("agent_view") or {}
    meta = agent_view.get("meta") or {}
    hud = agent_view.get("hud") or {}
    scores = hud.get("scores") or {}
    me = meta.get("player") or "p1"
    my_score = scores.get(me)
    rival_score = next((v for k, v in scores.items() if k != me), None)

    # ── Per-harvester roster ── from entities.mine (has damaged +
    # carrying_red + cargo_count that my_assets doesn't surface).
    entities = agent_view.get("entities") or {}
    mine = entities.get("mine") or []
    harvesters: List[Dict[str, Any]] = []
    for e in mine:
        if not isinstance(e, Mapping):
            continue
        if str(e.get("type") or "") != "harvester":
            continue
        pos = e.get("pos")
        harvesters.append({
            "id": e.get("id"),
            "at": pos if isinstance(pos, (list, tuple)) else None,
            "state": "surface" if pos else "orbit",
            "cargo_count": int(e.get("cargo_count") or 0),
            "carrying_red": bool(e.get("carrying_red")),
            "damaged": bool(e.get("damaged")),
        })

    # ── Enemy last-seen positions ── from entities.echoes.
    echoes = entities.get("echoes") or []
    enemy_echoes: List[Dict[str, Any]] = []
    for e in echoes:
        if not isinstance(e, Mapping):
            continue
        enemy_echoes.append({
            "id": e.get("id"),
            "type": e.get("type"),
            "last_seen_pos": e.get("last_seen_pos"),
        })

    # ── Live (currently-in-LOS) enemy units ── walk world block. This is
    # separate from ``entities.echoes`` (which is stale probe intel only).
    # A pilot standing next to an enemy harvester will find NO entry in
    # echoes but SHOULD find one here — the omission is what silently
    # broke ``contested_pure_with_own_emp`` in baseline v3.
    world = agent_view.get("world") or {}
    live_enemies: List[Dict[str, Any]] = []
    # List-mode: world.live[] carries entity payloads with full ids.
    for row in (world.get("live") or []):
        if not isinstance(row, Mapping):
            continue
        ent = row.get("entity")
        if not isinstance(ent, Mapping):
            continue
        if str(ent.get("owner") or "") == str(me):
            continue
        try:
            xy = [int(row.get("x")), int(row.get("y"))]
        except (TypeError, ValueError):
            continue
        live_enemies.append({
            "id": ent.get("id"),
            "kind": ent.get("kind"),
            "at": xy,
            "carrying": ent.get("carrying"),
        })
    # Grid-mode: world.grid[y][x] cells carry a slim entity dict (no id).
    # We only fall through here when live[] wasn't provided (grid mode
    # replaces the block entirely — see _render_world_grid).
    if not live_enemies and isinstance(world.get("grid"), list):
        grid_rows = world["grid"]
        for y, row in enumerate(grid_rows):
            if not isinstance(row, list):
                continue
            for x, cell in enumerate(row):
                if not isinstance(cell, Mapping):
                    continue
                ent = cell.get("entity")
                if not isinstance(ent, Mapping):
                    continue
                if str(ent.get("owner") or "") == str(me):
                    continue
                live_enemies.append({
                    "kind": ent.get("kind"),
                    "at": [x, y],
                    "carrying": ent.get("carrying"),
                })

    # ── Orbit-block economics (available EVERY turn, not just orbit) ──
    orbit = agent_view.get("orbit") or {}
    weapon_stock = orbit.get("weapon_stock") or {}
    credits = orbit.get("credits")
    blue_purity_total = orbit.get("blue_purity_total")

    # ── Hoard summary — count-by-tier + shippable RED score potential ──
    hoard_parcels = orbit.get("hoard_parcels") or []
    red_count = sum(1 for p in hoard_parcels if str(p.get("colour") or "") == "RED")
    green_count = sum(1 for p in hoard_parcels if str(p.get("colour") or "") == "GREEN")
    blue_count = sum(1 for p in hoard_parcels if str(p.get("colour") or "") == "BLUE")
    red_score_potential = sum(int(p.get("score") or 0) for p in hoard_parcels
                              if str(p.get("colour") or "") == "RED")
    hoard_block = hud.get("hoard") or {}
    hoard_summary = {
        "used": hoard_block.get("used"),
        "cap": hoard_block.get("cap"),
        "pct_full": hoard_block.get("pct_full"),
        "warning": hoard_block.get("warning"),
        "red_parcels": red_count,
        "green_parcels": green_count,
        "blue_parcels": blue_count,
        "red_score_potential": red_score_potential,
    }

    # ── Last-night combat events (EMP clouds / chaff flares) ──
    last_night = agent_view.get("last_night") or {}
    combat_events = last_night.get("combat_events") or []
    recent_emp: List[Dict[str, Any]] = []
    recent_chaff: List[Dict[str, Any]] = []
    for ev in combat_events:
        if not isinstance(ev, Mapping):
            continue
        etype = str(ev.get("type") or "")
        if etype in ("emp", "emp_hit"):
            recent_emp.append({
                "type": etype,
                "owner": ev.get("owner") or ev.get("by"),
                "cells": ev.get("cells") or [],
                "hours": ev.get("hours") or [],
                "victim": ev.get("victim"),
            })
        elif etype in ("chaff", "chaff_jam"):
            recent_chaff.append({
                "type": etype,
                "owner": ev.get("owner") or ev.get("by"),
                "hours": ev.get("hours") or [],
                "victim": ev.get("victim"),
            })

    # ── Redsign beacon cells (flattened) ──
    redsign_raw = agent_view.get("redsign") or []
    redsign_cells: List[List[int]] = []
    for r in redsign_raw:
        if not isinstance(r, Mapping):
            continue
        for c in (r.get("cells") or []):
            if isinstance(c, (list, tuple)) and len(c) >= 2:
                try:
                    redsign_cells.append([int(c[0]), int(c[1])])
                except (TypeError, ValueError):
                    pass

    brief: Dict[str, Any] = {
        "day": meta.get("day"),
        "season_day_cap": hud.get("season_day_cap") or 7,
        "phase": "orbit" if is_orbit else "planning",
        "my_score": my_score,
        "rival_score": rival_score,
        # ── Raw fixture state (v1.9 expansion) ──
        "my_harvesters": harvesters,
        "harvesters_alive": len(harvesters),
        "weapon_stock": {
            "emp": int(weapon_stock.get("emp") or 0),
            "mine": int(weapon_stock.get("mine") or 0),
            "chaff": int(weapon_stock.get("chaff") or 0),
        },
        "credits": credits,
        "blue_purity_total": blue_purity_total,
        "hoard": hoard_summary,
        "enemy_echoes": enemy_echoes,
        "live_enemies": live_enemies,
        "redsign_present": bool(redsign_raw),
        "redsign_cells": redsign_cells[:24],  # cap to keep the brief compact
        "blue_sign_present": bool(agent_view.get("blue_sign")),
        "recent_emp_events": recent_emp,
        "recent_chaff_events": recent_chaff,
        # ── Explicit combat-cost clarifier (v1.9) ──
        # Rulebook §5.1/§5.2: BUILD cost is paid in orbit to add a
        # weapon to weapon_stock; FIRING an in-stock weapon costs
        # NOTHING beyond the action slot. Baseline v3 showed the
        # strategist conflating these ("EMP costs 200 blue + 250
        # credits so I can't fire it") which blocked #8. Naming both
        # numbers in the brief kills that confusion.
        "combat_costs": {
            "emp_build": {"blue": 200, "credits": 250},
            "emp_fire":  {"cost": "FREE if weapon_stock.emp >= 1"},
            "chaff_build": {"blue": 255, "credits": 250},
            "chaff_fire":  {"cost": "FREE if weapon_stock.chaff >= 1"},
            "mine_build": {"blue": 200, "credits": 250},
            "mine_fire":  {"cost": "FREE if weapon_stock.mine >= 1"},
        },
    }
    if is_orbit:
        orbital = extras.get("orbital") or {}
        brief["orbit_trivial"] = orbital.get("trivial")
        brief["recommended_orbit_actions"] = len((orbital.get("recommended_orbit_policy") or {}).get("actions") or [])
    else:
        cands = (extras.get("candidates") or {})
        redsign_present = bool(redsign_raw)

        def _top_with_risk(key: str, n: int = 3) -> List[Dict[str, Any]]:
            out: List[Dict[str, Any]] = []
            for c in (cands.get(key) or [])[:n]:
                row: Dict[str, Any] = {
                    "id": c.get("id"),
                    "score": c.get("score", c.get("expected_score_after_vault_cascade")),
                    "tier": c.get("tier") or c.get("kind"),
                    "unit": c.get("unit"),
                }
                sb = c.get("score_breakdown") or {}
                if "threat_cost" in sb:
                    row["threat_cost"] = sb.get("threat_cost")
                if "chain_survival_prob" in sb:
                    row["survival"] = sb.get("chain_survival_prob")
                # Per-candidate contested-drop risk scoring (arsenal-aware).
                risk = rival_arsenal.score_candidate_risk(
                    {**c, "threat_cost": sb.get("threat_cost", 0.0)},
                    arsenal_summary,
                    redsign_present=redsign_present,
                    redsign_cells=redsign_cells,
                )
                row["risk"] = risk
                out.append({k: v for k, v in row.items() if v not in (None, "")})
            return out

        brief["top_harvest"] = _top_with_risk("harvest", n=4)
        brief["top_probes"] = [
            {"id": c.get("id"), "score": c.get("score", c.get("expected_score_after_vault_cascade"))}
            for c in (cands.get("probes") or [])[:2]
        ]
        # Interdiction toolkit availability — so the strategist can reason
        # about denial (esp. contesting a public redsign), not just harvest.
        emp = (cands.get("emp_launch") or [])
        top_emp = emp[0] if emp else {}
        combat = extras.get("combat") or {}
        mech = combat.get("emp_mechanics") or {}
        eff = (top_emp.get("expected_effect") or {}) if isinstance(top_emp, Mapping) else {}
        aff = (top_emp.get("affordability") or {}) if isinstance(top_emp, Mapping) else {}
        brief["interdiction"] = {
            "hot_drop": len(cands.get("hot_drop") or []),
            "harvester_crush": len(cands.get("harvester_crush") or []),
            "probe_supersede": len(cands.get("probe_supersede") or []),
            "drop_block": len(cands.get("drop_block") or []),
            "emp_launch": len(emp),
        }
        brief["emp"] = {
            "available": bool(emp),
            "can_fire": bool(aff.get("can_fire")),
            "top_score": top_emp.get("score") if isinstance(top_emp, Mapping) else None,
            "enemy_units_hit": eff.get("enemy_unit_count"),
            "self_freeze": eff.get("self_freeze_unit_count"),
            "cost_blue": mech.get("cost_blue_purity"),
            "cost_credits": mech.get("cost_credits"),
            "radius": mech.get("radius_chebyshev"),
            "cloud_hours": mech.get("cloud_hours"),
        }
        brief["blue_available"] = combat.get("my_blue_purity_available")
        brief["threat"] = extras.get("threat") or {}
        # Self-utilisation telemetry — did every alive harvester act last Nox?
        brief["core_loop"] = rival_arsenal.harvester_utilization(agent_view)
    # Rival arsenal signals — chaff/emp capability + last-Nox firings.
    # The strategist uses these to time pickups vs the 3-hour chaff jam.
    if arsenal_summary and arsenal_summary.get("opponents"):
        brief["arsenal"] = arsenal_summary
    return "DECISION BRIEF (JSON):\n```json\n" + _json.dumps(brief, ensure_ascii=False, separators=(",", ":")) + "\n```\n"


# ── Entry point ─────────────────────────────────────────────────────
def run(*, store, session_id: str, player: str, view: Mapping[str, Any]) -> Dict[str, Any]:
    """Drive one PILOT_V4 turn. Returns the dispatcher audit envelope."""
    started = time.time()
    phase = str(
        view.get("phase")
        or (view.get("agent_view", {}).get("meta", {}) or {}).get("phase")
        or ""
    ).lower()
    is_orbit = phase == "orbit"
    agent_view = view.get("agent_view") or {}

    strat_inv = CortexAgentInvoker(agent_name=STRATEGIC_AGENT)
    tact_inv = CortexAgentInvoker(agent_name=TACTICAL_AGENT)
    if not strat_inv.is_ready() or not tact_inv.is_ready():
        return {
            "ok": False,
            "elapsed_ms": int((time.time() - started) * 1000),
            "submitted_policy": False,
            "error": (
                "Cortex invoker not ready for PILOT_V4 (missing PAT/account "
                "or STRATEGIST_V4/TACTICIAN_V4 agents not deployed)"
            ),
            "extras": {"inner_agent": INNER_CORTEX_AGENT},
        }

    base_prompt, extras = _splice_state(session_id, view, is_orbit=is_orbit)

    # Ingest rival arsenal signals (blue-band history + observed weapon
    # events → estimated stocks + chaff/emp capability flags). Cheap,
    # process-local; safe to call every turn.
    try:
        arsenal_summary = rival_arsenal.update_and_summarize(session_id, agent_view)
    except Exception:
        arsenal_summary = {}

    # ── 1) STRATEGIST ──
    # Feed a TINY decision brief, not the full menu/grid — that is what keeps
    # haiku from writing an analytical wall. It still reasons (in-context) to
    # pick the doctrine; its DIAGNOSIS/INTENT lines carry the compressed logic.
    # The plan list is filtered to the current phase so it can't pick an
    # orbit-only plan at night (or vice-versa).
    strat_phase = "orbit" if is_orbit else "planning"
    strategic_prompt = (
        _STRATEGIST_HEAD
        + prompt_line_for_strategist(strat_phase)
        + _STRATEGIST_TAIL
        + _strategist_brief(view, extras, is_orbit=is_orbit,
                            arsenal_summary=arsenal_summary)
        + _STRATEGIST_POSTAMBLE
    )
    s_result = strat_inv.invoke(
        strategic_prompt,
        wallclock_cap_s=_STRATEGIC_WALLCLOCK_S,
        response_cap_bytes=_STRATEGIC_RESPONSE_CAP,
    )
    strategist_raw = str(s_result.get("response") or "")
    _default_plan = "vault_flush_orbit" if is_orbit else "harvest_mixed"
    strategist_note = _compact_strategist_note(strategist_raw, default_plan=_default_plan)
    plan_label = _parse_strategist_plan(strategist_note)

    # ── 2) TACTICIAN ──
    if is_orbit:
        orbital = extras.get("orbital") or {}
        # v1.9 — reorder the recommended_orbit_policy so it LEADS with
        # the option matching the strategist's plan_label. Without this
        # the tactician often accepts "recommended_orbit_policy" as-is,
        # and the recommended queue (e.g. [build_probe, build_mine]) has
        # no relation to whether the strategist chose vault_flush_orbit
        # or defensive_repair. Baseline v3-v7 showed this drift landing
        # ~30% of the time even when the strategist named the correct
        # plan. See PLAN_VERB_HINTS below for the label→verb map.
        orbital = _rerank_orbit_recommendation(orbital, plan_label)
        options = _flatten_orbit_options(orbital)
        tactical_prompt = (
            _TACTICIAN_ORBIT_PREAMBLE_TMPL.format(
                seat=player, strategist_note=strategist_note,
                max_actions=int(orbital.get("max_actions") or 5),
                plan=plan_label or "vault_flush_orbit",
            )
            + _tactician_orbit_menu(orbital, options)
            + _TACTICIAN_POSTAMBLE
        )
    else:
        compiled = extras if "candidates" in extras else {}
        tactical_prompt = (
            _TACTICIAN_PREAMBLE_TMPL.format(
                seat=player, phase="planning", strategist_note=strategist_note,
                max_moves=MAX_MOVES, plan=plan_label or "harvest_mixed",
            )
            + _tactician_menu(compiled, arsenal_summary=arsenal_summary)
            + _TACTICIAN_POSTAMBLE
        )
    t_result = tact_inv.invoke(
        tactical_prompt,
        wallclock_cap_s=_TACTICAL_WALLCLOCK_S,
        response_cap_bytes=_TACTICAL_RESPONSE_CAP,
    )
    decision, decision_error = _extract_decision_json(str(t_result.get("response") or ""))

    # ── 3) HARNESS materialize + validate + submit ──
    try:
        from sea_of_colours.snowpark import engine as soc_engine
        if is_orbit:
            orbital = extras.get("orbital") or {}
            options = _flatten_orbit_options(orbital)
            if decision_error:
                materialized = [dict(a) for a in ((orbital.get("recommended_orbit_policy") or {}).get("actions") or [])]
                validation = {"fallback_used": True, "fallback_reason": decision_error, "selected_ids": []}
            else:
                materialized, validation = _materialize_orbit(
                    decision=decision, orbital=orbital, options=options)
            submit_result = soc_engine.submit_orbit_actions(store, session_id, player, materialized)
            submit_tool_name = "soc_submit_orbit_actions"
        else:
            compiled = extras if "candidates" in extras else {}
            if decision_error:
                rec = ((compiled.get("candidates") or {}).get("recommended_policy") or {}).get("moves") or []
                materialized = [dict(m) for m in rec]
                materialized, _ = _enforce_pickup_invariant(materialized, agent_view)
                validation = {"fallback_used": True, "fallback_reason": decision_error, "selected_ids": []}
            else:
                materialized, validation = _materialize_planning(
                    decision=decision, expected_seat=player,
                    compiled=compiled, agent_view=agent_view)
            submit_result = soc_engine.submit_policy(store, session_id, player, materialized)
            submit_tool_name = "soc_submit_policy"
        submit_ok = bool((submit_result or {}).get("ok", True))
        submit_errors = list((submit_result or {}).get("errors") or [])
    except Exception as exc:  # pragma: no cover - defensive
        materialized = []
        validation = {"fallback_used": True, "fallback_reason": f"submit_exception:{exc}"}
        submit_tool_name = "soc_submit_orbit_actions" if is_orbit else "soc_submit_policy"
        submit_ok = False
        submit_errors = [str(exc)]

    combined_ms = int((s_result.get("elapsed_ms") or 0) + (t_result.get("elapsed_ms") or 0))
    rationale = (
        f"[STRATEGIST plan={plan_label or 'unparsed'}] {strategist_raw}\n\n"
        f"[TACTICIAN] {t_result.get('response') or ''}\n"
        f"[HARNESS submit={submit_tool_name} count={len(materialized)} "
        f"fallback={validation.get('fallback_used')} reason={validation.get('fallback_reason')}]"
    )
    return {
        "ok": bool(s_result.get("ok")) and bool(t_result.get("ok")) and submit_ok,
        "elapsed_ms": combined_ms or int((time.time() - started) * 1000),
        "submitted_policy": submit_ok,
        "tool_calls": [{
            "name": submit_tool_name,
            "args": {"seat": player, "count": len(materialized), "source": "harness_validated_decision"},
        }],
        "response": str(t_result.get("response") or ""),
        "wallclock_capped": bool(s_result.get("wallclock_capped") or t_result.get("wallclock_capped")),
        "rationale": rationale[:2000],
        "error": t_result.get("error") or s_result.get("error"),
        "extras": {
            "inner_agent": INNER_CORTEX_AGENT,
            "strategic_agent": STRATEGIC_AGENT,
            "tactical_agent": TACTICAL_AGENT,
            "plan_label": plan_label,
            "plan_explicit": bool(_parse_strategist_plan(strategist_raw)),
            "strategist_ok": bool(s_result.get("ok")),
            "strategist_error": s_result.get("error"),
            "tactician_ok": bool(t_result.get("ok")),
            "strategist_ms": int(s_result.get("elapsed_ms") or 0),
            "tactician_ms": int(t_result.get("elapsed_ms") or 0),
            "strategist_note": strategist_raw[:10000],
            "strategist_note_compact": strategist_note,
            "prompt_chars": len(strategic_prompt) + len(tactical_prompt),
            "prompt_excerpt": tactical_prompt,
            "hallucinated_tools": t_result.get("hallucinated_tools") or [],
            "tool_errors": (t_result.get("tool_errors") or []) + (s_result.get("tool_errors") or []),
            "decision": decision,
            "decision_error": decision_error,
            "decision_validation": validation,
            "materialized_count": len(materialized),
            "submit_errors": submit_errors,
        },
    }
