"""SOC_RED_REAPER_PILOT_V3's standalone harness.

This module is the **only public surface** the orchestrator sees. The
orchestrator looks up the binding for PILOT_V3 (via the binding
registry), gets the locator
``"sea_of_colours.orchestrator_2.harnesses.pilot_v3.harness:run"``, and
calls :func:`run` with the universal STATE envelope.

Everything PILOT_V3 needs lives inside this package:

* :mod:`.candidates` — pre-compiled menu of legal scored moves
  (harvest chains, probes, supersedes, harvester crushes, hot-drops)
  plus a threat brief and the season-memory summary.
* :mod:`.memory` — process-local enemy-vision history.
* This module — assembles a PILOT_V3-specific prompt (universal STATE +
  candidates/threat/memory), invokes the inner Cortex Agent
  (``SOC_RED_REAPER_PILOT_V3``), and returns the audit envelope.

Self-contained: nothing in the orchestrator imports from here. The
orchestrator only knows this module's locator string.
"""

from __future__ import annotations

import json as _json
import re
import time
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from sea_of_colours.orchestrator_2.cortex_invoker import CortexAgentInvoker
from sea_of_colours.orchestrator_2.envelope import build_universal_envelope
from sea_of_colours.orchestrator_2.harnesses.pilot_v3.candidates import (
    compile_candidates,
)
from sea_of_colours.orchestrator_2.harnesses.pilot_v3.orbit import (
    compile_orbit_candidates,
)


# ── Two-call architecture (E5 recipe, 2025-07-14) ───────────────────
#
# PILOT_V3 makes TWO Cortex calls per turn:
#   1. STRATEGIST — picks a plan label + top candidates. 15s wallclock.
#      No tools registered. Terse 4-line output.
#   2. TACTICIAN — reads the strategist note + candidates. 45s wallclock.
#      Emits JSON choice only; the harness validates and submits.
#
# Validated on fixtures d3s9 + d7s26: 0 rambles median, 100% tool_called
# across N=10 total runs. Vs V3 single-call baseline (14 rambles median,
# 80% tool_called) that's a -100% rambling cut with +25% tool reliability.
INNER_CORTEX_AGENT = "SOC_RED_REAPER_PILOT_V3"  # legacy label (audit compat)
STRATEGIC_AGENT = "SOC_RED_REAPER_STRATEGIC"
TACTICAL_AGENT = "SOC_RED_REAPER_TACTICAL"
TACTICAL_LLM_ENABLED = False

_STRATEGIC_WALLCLOCK_S = 15
_TACTICAL_WALLCLOCK_S = 45
_STRATEGIC_RESPONSE_CAP = 3000
_TACTICAL_RESPONSE_CAP = 3000


_STRATEGIST_PREAMBLE = (
    "ROLE=STRATEGIST. You have NO tools. YOU HAVE 15 SECONDS.\n\n"
    "═══════════════════════════════════════════════════════════\n"
    "GAME PRIMARY GOAL: harvest RED, ship RED, deny enemy RED.\n"
    "The winner is whoever banks the most RED-value by end of day 7.\n"
    "Everything else — probes, EMPs, denial — is INFRASTRUCTURE that\n"
    "ONLY matters if it enables more RED harvest.\n\n"
    "AGGRESSION HEURISTICS (weigh into your PLAN choice):\n"
    "  • If ANY visible harvest chain scores > 30 AND you have a\n"
    "    harvester ready → pick harvest_pure or harvest_mixed.\n"
    "    Passivity loses. Only skip harvest when the harness says the\n"
    "    harvest[] menu is empty or every candidate scores ≤ 0.\n"
    "  • If harvesters_alive < 2 AND phase=orbit → pick fleet_rebuild.\n"
    "    You cannot harvest what you cannot deploy. A dead fleet is\n"
    "    the #1 losing pattern.\n"
    "  • If leading by > 200 AND < 3 nights left → still HARVEST.\n"
    "    Denial is a distant second when your own score can grow.\n"
    "═══════════════════════════════════════════════════════════\n\n"
    "You will be CUT OFF at 15 seconds — the network socket closes and "
    "whatever you've written is what the tactician sees. So be terse.\n\n"
    "Give your GUT call. Skim for score gap, posture, top 2-3 candidates. "
    "Then WRITE the 4 lines. Any analysis you add after eats into your "
    "own decision time.\n\n"
    "OUTPUT — start with these 4 lines. Any prose before them is wasted:\n\n"
    "  DIAGNOSIS: <one sentence — day X/7, my score vs rival, main tension>\n"
    "  PLAN: <exactly one of: harvest_pure, harvest_mixed, denial_dominant, "
    "emp_race, vault_flush_orbit, probe_seed, defensive_repair, "
    "fleet_rebuild, final_day_push>\n"
    "  TOP: <1-3 candidate IDs like H0, C0, P1, S1 — or coordinates>\n"
    "  RATIONALE: <one sentence — your gut>\n\n"
    "═══════════════════════════════════════════════════════════\n"
    "STATE (skim, don't dwell):\n\n"
)

_STRATEGIST_POSTAMBLE = (
    "\n═══════════════════════════════════════════════════════════\n"
    "END OF STATE. 15s clock ticking. FIRST TOKEN you emit must be "
    "'DIAGNOSIS:'. Any bold-headers or 'Let me parse' phrasing wastes "
    "your decision budget. Go:\n"
)

_TACTICIAN_PREAMBLE_TMPL = (
    "Return ONE JSON object only. No prose. No markdown. No tools.\n"
    "seat must be \"{seat}\". phase must be \"{phase}\".\n"
    "Allowed choices: recommended_policy, recommended_orbit_policy, or a "
    "candidate id shown below. If unsure choose the recommended choice.\n"
    "Strategist note:\n{strategist_note}\n"
)

_TACTICIAN_POSTAMBLE_TMPL = (
    "\n═══════════════════════════════════════════════════════════\n"
    "END STATE. Output ONE JSON object now. First byte MUST be '{{'. "
    "No analysis, no bullets, no markdown, no tools.\n"
    "Use exactly: {{\"seat\":\"{seat}\",\"phase\":\"{phase}\","
    "\"choice\":\"recommended_policy\",\"rationale\":\"short reason\"}}\n"
)

_PLANNING_VERBS = frozenset({"drop", "step", "pickup", "probe", "emp_launch"})
_ORBIT_VERBS = frozenset({
    "repair",
    "build_probe",
    "build_harvester",
    "build_emp",
    "build_chaff",
    "build_mine",
    "ship_catapult",
    "refine",
    "solar_jettison",
})


# Broad regex for extracting the plan label from the strategist's output.
# Tolerates common LLM variants: "PLAN: X", "PLAN LABEL: X", "**PLAN:** X",
# and "PLAN LABEL: This matches **X**".
_PLAN_RE = re.compile(
    r"\bPLAN(?:\s+LABEL)?\s*:?\s*\**\s*(?:This matches\s*)?\**\s*"
    r"(harvest_pure|harvest_mixed|denial_dominant|emp_race|"
    r"vault_flush_orbit|probe_seed|defensive_repair|"
    r"fleet_rebuild|final_day_push)",
    re.I,
)


def _parse_strategist_plan(text: str) -> str:
    """Extract the plan label from the strategist's output; '' if absent."""
    m = _PLAN_RE.search(text or "")
    return m.group(1).lower() if m else ""


def _compact_strategist_note(text: str) -> str:
    """Keep the tactician from inheriting strategist ramble/cutoff text."""
    plan = _parse_strategist_plan(text) or "harvest_mixed"
    top = "recommended_policy"
    for line in (text or "").splitlines():
        if re.match(r"^\s*\**\s*TOP", line, flags=re.I):
            top = line.split(":", 1)[-1].strip() or top
            break
    return (
        "DIAGNOSIS: strategist compressed by harness.\n"
        f"PLAN: {plan}\n"
        f"TOP: {top}\n"
        "RATIONALE: choose the best validated candidate for this plan."
    )


def _choice_from_strategist_note(text: str, *, is_orbit: bool) -> str:
    """Extract the agent's candidate choice; fallback stays validated."""
    if is_orbit:
        return "recommended_orbit_policy"
    top = ""
    for line in (text or "").splitlines():
        if re.match(r"^\s*\**\s*TOP", line, flags=re.I):
            top = line.split(":", 1)[-1]
            break
    haystack = top or text or ""
    if "recommended_policy" in haystack:
        return "recommended_policy"
    match = re.search(
        r"\b(HOTCB\d+|HOTSPEC\d+|HOT\d+|DB\d+|EMP\d+|"
        r"H\d+(?:_[A-Za-z0-9_]+)?|P\d+|S\d+|C\d+)\b",
        haystack,
    )
    return match.group(1) if match else "recommended_policy"


def _normalise_phase(phase: str) -> str:
    phase_l = (phase or "").strip().lower()
    return "planning" if phase_l in ("", "night", "planning") else phase_l


def _extract_decision_json(text: str) -> Tuple[Dict[str, Any], Optional[str]]:
    """Parse the tactician's JSON-only decision, tolerating fences."""
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
        if isinstance(parsed, dict) and {"seat", "phase", "choice"}.issubset(parsed):
            return parsed, None
        if not isinstance(parsed, dict):
            return {}, "json_not_object"
    return {}, "no_json_object"


def _candidate_lists(candidates_block: Mapping[str, Any]) -> Sequence[Sequence[Mapping[str, Any]]]:
    return (
        candidates_block.get("harvest") or [],
        candidates_block.get("probes") or [],
        candidates_block.get("probe_supersede") or [],
        candidates_block.get("harvester_crush") or [],
        candidates_block.get("hot_drop") or [],
        candidates_block.get("drop_block") or [],
        candidates_block.get("emp_launch") or [],
    )


def _find_candidate(candidates_block: Mapping[str, Any], choice: str) -> Optional[Mapping[str, Any]]:
    choice_norm = (choice or "").strip()
    if not choice_norm:
        return None
    for group in _candidate_lists(candidates_block):
        for cand in group:
            cid = str((cand or {}).get("id") or "")
            if cid == choice_norm or cid.startswith(choice_norm + "_"):
                return cand
    return None


def _validate_actions(items: Sequence[Mapping[str, Any]], allowed: frozenset[str]) -> Optional[str]:
    for idx, item in enumerate(items):
        if not isinstance(item, Mapping):
            return f"item_{idx}_not_object"
        verb = str(item.get("a") or "")
        if verb not in allowed:
            return f"illegal_verb:{verb or '<missing>'}"
    return None


def _materialize_planning_policy(
    *,
    decision: Mapping[str, Any],
    expected_seat: str,
    expected_phase: str,
    compiled: Mapping[str, Any],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    candidates_block = compiled.get("candidates") or {}
    recommended = candidates_block.get("recommended_policy") or {}
    fallback_moves = list(recommended.get("moves") or [])
    info: Dict[str, Any] = {
        "fallback_used": False,
        "fallback_reason": "",
        "choice": decision.get("choice"),
    }

    if str(decision.get("seat") or "") != expected_seat:
        info.update(fallback_used=True, fallback_reason="wrong_seat")
        return fallback_moves, info
    if _normalise_phase(str(decision.get("phase") or "")) != expected_phase:
        info.update(fallback_used=True, fallback_reason="wrong_phase")
        return fallback_moves, info

    choice = str(decision.get("choice") or "recommended_policy").strip()
    if not choice or choice == "recommended_policy":
        moves = fallback_moves
    else:
        cand = _find_candidate(candidates_block, choice)
        if cand is None:
            info.update(fallback_used=True, fallback_reason="unknown_choice")
            return fallback_moves, info
        moves = list(cand.get("moves") or [])
        info["materialized_candidate_id"] = cand.get("id")

    err = _validate_actions(moves, _PLANNING_VERBS)
    if err:
        info.update(fallback_used=True, fallback_reason=err)
        return fallback_moves, info
    return [dict(m) for m in moves], info


def _materialize_orbit_policy(
    *,
    decision: Mapping[str, Any],
    expected_seat: str,
    expected_phase: str,
    orbital: Mapping[str, Any],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    recommended = orbital.get("recommended_orbit_policy") or {}
    fallback_actions = list(recommended.get("actions") or [])
    info: Dict[str, Any] = {
        "fallback_used": False,
        "fallback_reason": "",
        "choice": decision.get("choice"),
    }
    if str(decision.get("seat") or "") != expected_seat:
        info.update(fallback_used=True, fallback_reason="wrong_seat")
        return fallback_actions, info
    if _normalise_phase(str(decision.get("phase") or "")) != expected_phase:
        info.update(fallback_used=True, fallback_reason="wrong_phase")
        return fallback_actions, info
    choice = str(decision.get("choice") or "recommended_orbit_policy").strip()
    if choice not in ("", "recommended_orbit_policy", "recommended_policy"):
        info.update(fallback_used=True, fallback_reason="unknown_orbit_choice")
        return fallback_actions, info
    err = _validate_actions(fallback_actions, _ORBIT_VERBS)
    if err:
        info.update(fallback_used=True, fallback_reason=err)
        return [], info
    return [dict(a) for a in fallback_actions], info


def _scrub_direct_submit_instruction(base: str, *, is_orbit: bool) -> str:
    replacement = (
        "Read STATE below, then return one JSON decision object. Do NOT call "
        "tools; the orchestrator validates your choice and submits it.\n"
    )
    base = base.replace(
        "Read STATE below, then CALL soc_submit_policy on your FIRST "
        'tool call with p_policy as a JSON STRING: {"moves":[...]}.\n',
        replacement,
    )
    if is_orbit:
        base = base.replace(
            "ORBIT PHASE — CALL soc_submit_orbit_actions on your FIRST "
            'tool call with p_actions as a JSON STRING: {"actions":[...]}.',
            "ORBIT PHASE — return choice='recommended_orbit_policy'. Do NOT call tools.",
        )
    return base


def _extract_state_from_prompt(prompt: str) -> Dict[str, Any]:
    marker = "STATE (JSON):\n```json\n"
    i = prompt.find(marker)
    if i < 0:
        return {}
    j = prompt.find("\n```", i + len(marker))
    if j < 0:
        return {}
    try:
        parsed = _json.loads(prompt[i + len(marker): j])
    except Exception:
        header = prompt[:i]
        seat_m = re.search(r"\bseat=([a-z0-9_]+)", header, flags=re.I)
        session_m = re.search(r"\bsession=([a-f0-9_\-]+)", header, flags=re.I)
        day_m = re.search(r"\bday=(\d+)", header, flags=re.I)
        phase_m = re.search(r'"phase"\s*:\s*"([^"]+)"', prompt)
        return {
            "meta": {
                "session_id": session_m.group(1) if session_m else None,
                "player": seat_m.group(1) if seat_m else None,
                "day": int(day_m.group(1)) if day_m else None,
                "phase": phase_m.group(1) if phase_m else "planning",
            }
        }
    return parsed if isinstance(parsed, dict) else {}


def _summarize_candidate(cand: Mapping[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "id": cand.get("id"),
        "kind": cand.get("kind") or cand.get("type"),
        "score": cand.get("score", cand.get("expected_score_after_vault_cascade")),
    }
    for key in ("unit", "at", "drop", "target", "rationale_hint"):
        if key in cand:
            out[key] = cand.get(key)
    return {k: v for k, v in out.items() if v not in (None, "")}


def _compact_decision_state(base_prompt: str, *, is_orbit: bool) -> str:
    state = _extract_state_from_prompt(base_prompt)
    meta = state.get("meta") or {}
    compact: Dict[str, Any] = {
        "meta": {
            "session_id": meta.get("session_id"),
            "player": meta.get("player"),
            "phase": "orbit" if is_orbit else "planning",
            "day": meta.get("day"),
        }
    }
    if is_orbit:
        orbital = state.get("orbital") or {}
        compact["orbital"] = {
            "recommended_orbit_policy": orbital.get("recommended_orbit_policy") or {},
            "play_enablers": orbital.get("play_enablers") or {},
            "trivial": orbital.get("trivial"),
        }
    else:
        candidates = state.get("candidates") or {}
        compact_candidates: Dict[str, Any] = {
            "recommended_policy": candidates.get("recommended_policy") or {},
        }
        for key in (
            "harvest", "probes", "probe_supersede", "harvester_crush",
            "hot_drop", "drop_block", "emp_launch",
        ):
            compact_candidates[key] = [
                _summarize_candidate(c) for c in (candidates.get(key) or [])[:6]
            ]
        compact["candidates"] = compact_candidates
        compact["threat"] = state.get("threat") or {}
    return "DECISION STATE (JSON):\n```json\n" + _json.dumps(
        compact, ensure_ascii=False, separators=(",", ":")
    ) + "\n```\n"


# Envelope addendum specific to PILOT_V3's doctrine. The orchestrator's
# universal envelope says "read STATE then call soc_submit_policy"; we
# extend it to say "the menu is pre-validated — pick from it."
_PILOT_V3_DEFAULT_PLAY = (
    "Default play: return choice='recommended_policy'. Override only by "
    "returning a candidate ID from candidates.* when that better realizes "
    "the strategist plan. Do NOT call tools or compose raw moves.\n"
)

# Orbit-phase default: distinct tool + doctrine block.
_PILOT_V3_ORBIT_DEFAULT_PLAY = (
    "ORBIT PHASE. Return choice='recommended_orbit_policy'. The harness "
    "will submit `orbital.recommended_orbit_policy.actions` after validation. "
    "Every slot is precomposed by doctrine: play-enablers (repair, "
    "probes, harvester expansion) fire first; baseline productive "
    "spends (ship vein+, refine trace→vein, dump green) fill the "
    "remaining slots. Override only if you see a stronger use of a "
    "slot — never leave slots empty. BLUE is spend currency, not "
    "hoard. Do NOT call tools.\n"
)


def _build_pilot_v3_prompt(
    session_id: str,
    view: Mapping[str, Any],
) -> str:
    """Build the per-turn prompt for PILOT_V3.

    Strategy: start from the orchestrator's universal envelope (so the
    seat / day / actions counters match every other agent's view), then
    inject candidates + threat + memory_summary INTO the embedded STATE
    JSON, plus append the PILOT_V3 default-play hint to the envelope.
    """
    base = _scrub_direct_submit_instruction(
        build_universal_envelope(session_id, view), is_orbit=False,
    )
    agent_view = view.get("agent_view") or {}

    # Best-effort enrichment. If the compiler explodes we still send the
    # universal STATE so PILOT_V3 can read raw grid + my_assets and play.
    try:
        extras = compile_candidates(agent_view)
    except Exception:
        extras = {}

    # Splice the extras into the JSON block of the base envelope so the
    # serialised STATE has candidates / threat / memory_summary keys at
    # the same level as world / navigation / my_assets.
    sentinel_open = "STATE (JSON):\n```json\n"
    sentinel_close = "\n```\n"
    i = base.find(sentinel_open)
    j = base.find(sentinel_close, i + len(sentinel_open)) if i >= 0 else -1
    if i < 0 or j < 0:
        # Defensive: emit the universal envelope with the default-play
        # hint and no extras. PILOT_V3 will still work (just slower).
        return base + "\n" + _PILOT_V3_DEFAULT_PLAY

    state_str = base[i + len(sentinel_open) : j]
    try:
        state = _json.loads(state_str)
    except Exception:
        return base + "\n" + _PILOT_V3_DEFAULT_PLAY

    # v0.9.27 — bug fix: include "combat" alongside candidates/threat/
    # memory_summary. Previously the combat block (weapon_stock,
    # blue_purity_available, credits_available, emp_mechanics) was being
    # silently dropped from the STATE JSON. The agent's spec says FOUR
    # extra blocks are injected but only 3 were making it through. This
    # is why EMP-menu presence never registered in real gameplay: the
    # agent never actually saw `combat.my_weapon_stock` or
    # `combat.emp_mechanics` in its brief.
    for key in ("candidates", "combat", "threat", "memory_summary"):
        if key in extras:
            state[key] = extras[key]
    new_state_str = _json.dumps(state, ensure_ascii=False, separators=(",", ":"))

    # Insert the default-play hint just before the STATE block.
    head = base[:i]
    tail = base[j + len(sentinel_close) :]
    rebuilt = (
        head
        + _PILOT_V3_DEFAULT_PLAY
        + sentinel_open
        + new_state_str
        + sentinel_close
        + tail
    )
    return rebuilt


def _build_pilot_v3_orbit_prompt(
    session_id: str,
    view: Mapping[str, Any],
) -> str:
    """Build the orbit-phase prompt for PILOT_V3.

    Same envelope shape as night, but only the ``orbital`` block is
    spliced in (no night-phase candidates/threat/memory) and the
    default-play hint points at ``soc_submit_orbit_actions``.
    """
    base = _scrub_direct_submit_instruction(
        build_universal_envelope(session_id, view), is_orbit=True,
    )
    agent_view = view.get("agent_view") or {}
    try:
        orbital = compile_orbit_candidates(agent_view)
    except Exception:
        orbital = {}
    sentinel_open = "STATE (JSON):\n```json\n"
    sentinel_close = "\n```\n"
    i = base.find(sentinel_open)
    j = base.find(sentinel_close, i + len(sentinel_open)) if i >= 0 else -1
    if i < 0 or j < 0:
        return base + "\n" + _PILOT_V3_ORBIT_DEFAULT_PLAY
    state_str = base[i + len(sentinel_open) : j]
    try:
        state = _json.loads(state_str)
    except Exception:
        return base + "\n" + _PILOT_V3_ORBIT_DEFAULT_PLAY
    state["orbital"] = orbital
    new_state_str = _json.dumps(state, ensure_ascii=False, separators=(",", ":"))
    head = base[:i]
    tail = base[j + len(sentinel_close) :]
    return (
        head
        + _PILOT_V3_ORBIT_DEFAULT_PLAY
        + sentinel_open
        + new_state_str
        + sentinel_close
        + tail
    )


def run(
    *,
    store,
    session_id: str,
    player: str,
    view: Mapping[str, Any],
) -> Dict[str, Any]:
    """Entry point — orchestrator hands us a turn, we drive it.

    Returns the audit envelope shape the orchestrator's dispatcher
    consumes:
        { "ok": bool, "elapsed_ms": int, "submitted_policy": bool,
          "tool_calls": [...], "response": str, "wallclock_capped": bool,
          "rationale": str, "extras": {...} }
    """
    started = time.time()
    phase = str(view.get("phase") or view.get("agent_view", {}).get("meta", {}).get("phase") or "").lower()
    is_orbit = phase == "orbit"
    if is_orbit:
        base_prompt = _build_pilot_v3_orbit_prompt(session_id, view)
    else:
        base_prompt = _build_pilot_v3_prompt(session_id, view)

    # ── Two-call architecture ──
    # 1) STRATEGIST — 15s, no tools, 4-line output
    strat_inv = CortexAgentInvoker(agent_name=STRATEGIC_AGENT)
    tact_inv = CortexAgentInvoker(agent_name=TACTICAL_AGENT)
    if not strat_inv.is_ready() or (TACTICAL_LLM_ENABLED and not tact_inv.is_ready()):
        return {
            "ok": False,
            "elapsed_ms": int((time.time() - started) * 1000),
            "submitted_policy": False,
            "error": (
                "Cortex invoker not ready for PILOT_V3 two-call "
                "(missing PAT/account or STRATEGIC/TACTICAL agents not deployed)"
            ),
            "extras": {"inner_agent": INNER_CORTEX_AGENT},
        }

    strategic_prompt = _STRATEGIST_PREAMBLE + base_prompt + _STRATEGIST_POSTAMBLE
    s_result = strat_inv.invoke(
        strategic_prompt,
        wallclock_cap_s=_STRATEGIC_WALLCLOCK_S,
        response_cap_bytes=_STRATEGIC_RESPONSE_CAP,
    )
    strategist_raw = str(s_result.get("response") or "")
    strategist_note = _compact_strategist_note(strategist_raw)
    plan_label = _parse_strategist_plan(strategist_note)

    # 2) Execution choice. Live gameplay uses strategist-only execution by
    # default: the harness materializes its validated recommendation. The
    # no-tool tactical LLM remains available behind TACTICAL_LLM_ENABLED for
    # fixture experiments, but it is not reliable enough to gate live turns.
    tactical_prompt = (
        _TACTICIAN_PREAMBLE_TMPL.format(
            seat=player,
            phase="orbit" if is_orbit else "planning",
            session_id=session_id,
            strategist_note=strategist_note
            or f"PLAN: harvest_mixed\nTOP: (strategist returned empty)"
        )
        + _compact_decision_state(base_prompt, is_orbit=is_orbit)
        + _TACTICIAN_POSTAMBLE_TMPL.format(
            seat=player,
            phase="orbit" if is_orbit else "planning",
        )
    )
    if TACTICAL_LLM_ENABLED:
        t_result = tact_inv.invoke(
            tactical_prompt,
            wallclock_cap_s=_TACTICAL_WALLCLOCK_S,
            response_cap_bytes=_TACTICAL_RESPONSE_CAP,
            tool_choice={"type": "auto"},
        )
    else:
        phase_label = "orbit" if is_orbit else "planning"
        choice = _choice_from_strategist_note(strategist_note, is_orbit=is_orbit)
        t_result = {
            "ok": True,
            "response": _json.dumps({
                "seat": player,
                "phase": phase_label,
                "choice": choice,
                "rationale": "Harness deterministic executor: validated recommended policy.",
            }, separators=(",", ":")),
            "elapsed_ms": 0,
            "tool_calls": [],
            "hallucinated_tools": [],
            "tool_errors": [],
        }

    decision, decision_error = _extract_decision_json(str(t_result.get("response") or ""))
    agent_view = view.get("agent_view") or {}
    try:
        from sea_of_colours.snowpark import engine as soc_engine

        if is_orbit:
            try:
                orbital = compile_orbit_candidates(agent_view)
            except Exception:
                orbital = {}
            materialized, validation = _materialize_orbit_policy(
                decision=decision,
                expected_seat=player,
                expected_phase="orbit",
                orbital=orbital,
            )
            if decision_error:
                validation.update(fallback_used=True, fallback_reason=decision_error)
                materialized = list(((orbital.get("recommended_orbit_policy") or {}).get("actions") or []))
            submit_result = soc_engine.submit_orbit_actions(
                store, session_id, player, materialized,
            )
            submit_tool_name = "soc_submit_orbit_actions"
        else:
            try:
                compiled = compile_candidates(agent_view)
            except Exception:
                compiled = {}
            materialized, validation = _materialize_planning_policy(
                decision=decision,
                expected_seat=player,
                expected_phase="planning",
                compiled=compiled,
            )
            if decision_error:
                validation.update(fallback_used=True, fallback_reason=decision_error)
                materialized = list((((compiled.get("candidates") or {}).get("recommended_policy") or {}).get("moves") or []))
            submit_result = soc_engine.submit_policy(
                store, session_id, player, materialized,
            )
            submit_tool_name = "soc_submit_policy"
        submit_ok = bool((submit_result or {}).get("ok", True))
        submit_errors = list((submit_result or {}).get("errors") or [])
    except Exception as exc:  # pragma: no cover - defensive
        materialized = []
        validation = {"fallback_used": True, "fallback_reason": f"submit_exception:{exc}"}
        submit_tool_name = "soc_submit_orbit_actions" if is_orbit else "soc_submit_policy"
        submit_ok = False
        submit_errors = [str(exc)]

    # Combined audit envelope. The tactician's tool call is the payload
    # that matters for gameplay; the strategist's note is preserved in
    # extras for post-hoc analysis.
    combined_ms = int(
        (s_result.get("elapsed_ms") or 0) + (t_result.get("elapsed_ms") or 0)
    )
    # Rationale = strategist note + tactician summary. Truncated to 2k by
    # the dispatcher's audit shim.
    rationale = (
        f"[STRATEGIST plan={plan_label or 'unparsed'}] {strategist_raw}\n\n"
        f"[TACTICIAN] {t_result.get('response') or ''}\n"
        f"[HARNESS submit={submit_tool_name} count={len(materialized)} "
        f"fallback={validation.get('fallback_used')}]"
    )
    return {
        "ok": bool(s_result.get("ok")) and bool(t_result.get("ok")) and submit_ok,
        "elapsed_ms": combined_ms or int((time.time() - started) * 1000),
        "submitted_policy": submit_ok,
        "tool_calls": [
            {
                "name": submit_tool_name,
                "args": {
                    "seat": player,
                    "count": len(materialized),
                    "source": "harness_validated_decision",
                },
            }
        ],
        "response": str(t_result.get("response") or ""),
        "wallclock_capped": bool(
            s_result.get("wallclock_capped") or t_result.get("wallclock_capped")
        ),
        "rationale": rationale[:2000],
        "error": t_result.get("error") or s_result.get("error"),
        "extras": {
            "inner_agent": INNER_CORTEX_AGENT,
            "strategic_agent": STRATEGIC_AGENT,
            "tactical_agent": TACTICAL_AGENT,
            "plan_label": plan_label,
            "strategist_ms": int(s_result.get("elapsed_ms") or 0),
            "tactician_ms": int(t_result.get("elapsed_ms") or 0),
            "strategist_note": strategist_raw[:1500],
            "strategist_note_compact": strategist_note,
            "prompt_chars": len(strategic_prompt) + len(tactical_prompt),
            # Persist the tactician's prompt for audit — that's the one
            # that produced the tool call.
            "prompt_excerpt": tactical_prompt,
            "hallucinated_tools": t_result.get("hallucinated_tools") or [],
            "tool_errors": t_result.get("tool_errors") or [],
            "decision": decision,
            "decision_error": decision_error,
            "decision_validation": validation,
            "materialized_count": len(materialized),
            "submit_errors": submit_errors,
            "model_tool_calls_ignored": list(t_result.get("tool_calls") or []),
        },
    }
