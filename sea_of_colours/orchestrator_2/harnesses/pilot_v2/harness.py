"""SOC_RED_REAPER_PILOT_V2's standalone harness.

This module is the **only public surface** the orchestrator sees. The
orchestrator looks up the binding for PILOT_V2 (via the binding
registry), gets the locator
``"sea_of_colours.orchestrator_2.harnesses.pilot_v2.harness:run"``, and
calls :func:`run` with the universal STATE envelope.

Everything PILOT_V2 needs lives inside this package:

* :mod:`.candidates` — pre-compiled menu of legal scored moves
  (harvest chains, probes, supersedes, harvester crushes, hot-drops)
  plus a threat brief and the season-memory summary.
* :mod:`.memory` — process-local enemy-vision history.
* This module — assembles a PILOT_V2-specific prompt (universal STATE +
  candidates/threat/memory), invokes the inner Cortex Agent
  (``SOC_RED_REAPER_PILOT_V2``), and returns the audit envelope.

Self-contained: nothing in the orchestrator imports from here. The
orchestrator only knows this module's locator string.
"""

from __future__ import annotations

import json as _json
import time
from typing import Any, Dict, Mapping

from sea_of_colours.orchestrator_2.cortex_invoker import CortexAgentInvoker
from sea_of_colours.orchestrator_2.envelope import build_universal_envelope
from sea_of_colours.orchestrator_2.harnesses.pilot_v2.candidates import (
    compile_candidates,
)
from sea_of_colours.orchestrator_2.harnesses.pilot_v2.orbit import (
    compile_orbit_candidates,
)


# Cortex agent this harness wraps. Pinned to PILOT_V2's deployed spec
# (claude-haiku-4-5, 30s/12k budget, single soc_submit_policy tool).
INNER_CORTEX_AGENT = "SOC_RED_REAPER_PILOT_V2"

# Envelope addendum specific to PILOT_V2's doctrine. The orchestrator's
# universal envelope says "read STATE then call soc_submit_policy"; we
# extend it to say "the menu is pre-validated — pick from it."
_PILOT_V2_DEFAULT_PLAY = (
    "Default play: copy `candidates.recommended_policy.moves` into "
    "p_policy as a JSON STRING. Override only when `threat` says so "
    "(see your spec). World state is below — peek `world.grid` for "
    "tactical detail when composing custom moves.\n"
)

# Orbit-phase default: distinct tool + doctrine block.
_PILOT_V2_ORBIT_DEFAULT_PLAY = (
    "ORBIT PHASE. Call `soc_submit_orbit_actions` (NOT "
    "`soc_submit_policy`) with the action list from "
    "`orbital.recommended_orbit_policy.actions` as a JSON STRING. "
    "Every slot is precomposed by doctrine: play-enablers (repair, "
    "probes, harvester expansion) fire first; baseline productive "
    "spends (ship vein+, refine trace→vein, dump green) fill the "
    "remaining slots. Override only if you see a stronger use of a "
    "slot — never leave slots empty. BLUE is spend currency, not "
    "hoard.\n"
)


def _build_pilot_v2_prompt(
    session_id: str,
    view: Mapping[str, Any],
) -> str:
    """Build the per-turn prompt for PILOT_V2.

    Strategy: start from the orchestrator's universal envelope (so the
    seat / day / actions counters match every other agent's view), then
    inject candidates + threat + memory_summary INTO the embedded STATE
    JSON, plus append the PILOT_V2 default-play hint to the envelope.
    """
    base = build_universal_envelope(session_id, view)
    agent_view = view.get("agent_view") or {}

    # Best-effort enrichment. If the compiler explodes we still send the
    # universal STATE so PILOT_V2 can read raw grid + my_assets and play.
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
        # hint and no extras. PILOT_V2 will still work (just slower).
        return base + "\n" + _PILOT_V2_DEFAULT_PLAY

    state_str = base[i + len(sentinel_open) : j]
    try:
        state = _json.loads(state_str)
    except Exception:
        return base + "\n" + _PILOT_V2_DEFAULT_PLAY

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
        + _PILOT_V2_DEFAULT_PLAY
        + sentinel_open
        + new_state_str
        + sentinel_close
        + tail
    )
    return rebuilt


def _build_pilot_v2_orbit_prompt(
    session_id: str,
    view: Mapping[str, Any],
) -> str:
    """Build the orbit-phase prompt for PILOT_V2.

    Same envelope shape as night, but only the ``orbital`` block is
    spliced in (no night-phase candidates/threat/memory) and the
    default-play hint points at ``soc_submit_orbit_actions``.
    """
    base = build_universal_envelope(session_id, view)
    # The universal envelope hard-codes a "CALL soc_submit_policy" line.
    # Rewrite it to name the orbit tool so the agent doesn't get mixed
    # signals: system-level instruction says soc_submit_policy, our
    # doctrine says soc_submit_orbit_actions. That contradiction caused
    # PILOT_V2 to call soc_submit_policy during orbit and never submit.
    base = base.replace(
        "CALL soc_submit_policy on your FIRST "
        'tool call with p_policy as a JSON STRING: {"moves":[...]}.',
        "ORBIT PHASE — CALL soc_submit_orbit_actions on your FIRST "
        'tool call with p_actions as a JSON STRING: {"actions":[...]}.',
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
        return base + "\n" + _PILOT_V2_ORBIT_DEFAULT_PLAY
    state_str = base[i + len(sentinel_open) : j]
    try:
        state = _json.loads(state_str)
    except Exception:
        return base + "\n" + _PILOT_V2_ORBIT_DEFAULT_PLAY
    state["orbital"] = orbital
    new_state_str = _json.dumps(state, ensure_ascii=False, separators=(",", ":"))
    head = base[:i]
    tail = base[j + len(sentinel_close) :]
    return (
        head
        + _PILOT_V2_ORBIT_DEFAULT_PLAY
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
        prompt = _build_pilot_v2_orbit_prompt(session_id, view)
    else:
        prompt = _build_pilot_v2_prompt(session_id, view)
    inv = CortexAgentInvoker(agent_name=INNER_CORTEX_AGENT)
    if not inv.is_ready():
        return {
            "ok": False,
            "elapsed_ms": int((time.time() - started) * 1000),
            "submitted_policy": False,
            "error": "Cortex invoker not ready for PILOT_V2 (missing PAT/account)",
            "extras": {"inner_agent": INNER_CORTEX_AGENT},
        }

    raw = inv.invoke(prompt)

    return {
        "ok": bool(raw.get("ok")),
        "elapsed_ms": int(raw.get("elapsed_ms") or int((time.time() - started) * 1000)),
        "submitted_policy": bool(raw.get("submitted_policy")),
        "tool_calls": list(raw.get("tool_calls") or []),
        "response": str(raw.get("response") or ""),
        "wallclock_capped": bool(raw.get("wallclock_capped")),
        "rationale": str(raw.get("response") or "")[:2000],
        "error": raw.get("error"),
        "extras": {
            "inner_agent": INNER_CORTEX_AGENT,
            "prompt_chars": len(prompt),
            # v0.9.27 — surface the built prompt for audit.py to
            # persist. Truncated to 8KB by audit's PROMPT_EXCERPT_CHAR_CAP.
            "prompt_excerpt": prompt,
            "hallucinated_tools": raw.get("hallucinated_tools") or [],
            "tool_errors": raw.get("tool_errors") or [],
        },
    }
