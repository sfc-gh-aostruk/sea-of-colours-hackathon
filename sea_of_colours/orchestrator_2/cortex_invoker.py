"""Cortex Agent invoker for orchestrator_2.

Thin subclass of :class:`sea_of_colours.agent.cortex_invoker.CortexAgentInvoker`
that adds orchestrator_2-specific per-agent caps. The SSE parser, tool-call
detection, and hallucination tracking come from the parent class
unchanged — that way fixes flow to both orchestrators.

What's overridden:

* :data:`WALLCLOCK_CAP_OVERRIDES` adds ``SOC_RED_REAPER_PILOT_V2: 80``
  (hard 80s-per-turn ceiling; a turn that hasn't submitted by then is
  cut off and the orchestrator falls back to the doctrine policy).
* :data:`RESPONSE_CAP_OVERRIDES` adds a generous 40KB ceiling for
  PILOT_V2 so its rationale lands intact in audit.
"""

from __future__ import annotations

from typing import Dict

from sea_of_colours.agent.cortex_invoker import (
    CortexAgentInvoker as _LegacyInvoker,
)


class CortexAgentInvoker(_LegacyInvoker):
    """orchestrator_2 invoker with PILOT_V2-aware caps."""

    WALLCLOCK_CAP_OVERRIDES: Dict[str, int] = {
        **_LegacyInvoker.WALLCLOCK_CAP_OVERRIDES,
        # PILOT_V2 — hard 80s per-turn ceiling. This is a *real* abort:
        # once 80s of SSE stream elapses the invoker closes the socket
        # (agent/cortex_invoker.py) and reports ``wallclock_capped``; if
        # the agent hadn't called soc_submit_policy by then the
        # orchestrator lands its doctrine ``recommended_policy`` instead,
        # so a live human never waits more than ~80s on a single agent
        # turn. Observed audit p95 ~61s, so 80s preserves reasoning
        # quality while bounding the tail for interactive play.
        "SOC_RED_REAPER_PILOT_V2": 80,
        # PILOT_V3 — same 80s ceiling. The v3 orbit fast-path should
        # reduce mean orbit-turn wallclock by ~30-40s (trivial flag →
        # verbatim submit), but the CAP is unchanged so night-turn
        # reasoning still has full 80s runway when needed.
        "SOC_RED_REAPER_PILOT_V3": 80,
        # PILOT_V3 two-call split (2025-07-14). The strategist gets a
        # tight 15s budget — enough for a 4-line plan header, not enough
        # to write a V3-style analytical wall. The harness passes an
        # explicit override too but this default protects against
        # accidental invocations without a per-call cap.
        "SOC_RED_REAPER_STRATEGIC": 15,
        # The tactician gets 45s to read the strategist note, lift
        # candidate moves, and fire the tool call. Combined 60s worst
        # case is under the 80s ceiling of V3 baseline.
        "SOC_RED_REAPER_TACTICAL": 45,
        # PILOT_V4 two-phase agentic split (2026-07). Both phases are real
        # (bounded) haiku-4.5 calls. Strategist reasons briefly then commits
        # (25s); tactician picks + orders + trims from the menu (45s).
        # Combined worst case 70s < the 90s PILOT_V4 interactive ceiling.
        "SOC_RED_REAPER_PILOT_V4": 90,
        "SOC_RED_REAPER_STRATEGIST_V4": 28,
        "SOC_RED_REAPER_TACTICIAN_V4": 45,
        # TABULA — single LLM call per night, no strategist/tactician
        # split. 30s wall-clock is more than the model needs for the
        # phase-1 prompt (~2KB in, ~1KB out) and leaves headroom for
        # occasional network glitches.
        "SOC_RED_REAPER_TABULA": 30,
        # TABULA_V2 — same budget as v1 (single LLM call, ~2KB in, ~1KB
        # out). Prompt is slightly larger (adds FOG + PROBE HINTS blocks)
        # but well within budget.
        "SOC_RED_REAPER_TABULA_V2": 30,
        # TABULA_V3 — larger prompt (adds opponent + last-night + wishlist +
        # hot-drop + blue + opponent-weapons + gated doctrine blocks). At
        # ~25KB the model needs real reasoning time — 60s is the current
        # working ceiling. Matches the harness's ``_WALLCLOCK_S``.
        "SOC_RED_REAPER_TABULA_V3": 60,
        # TABULA_V3 continuation finisher — JSON-only completer that
        # takes the primary's partial output and closes it. Tight 20s
        # cap because it's not planning, just completing; the primary
        # has already burned reasoning time.
        "SOC_RED_REAPER_TABULA_V3_FINISHER": 20,
        # TABULA_V4 — same LLM budget as v3. The v4 improvement is
        # structural (harness auto-augments probes) not doctrinal, so
        # the primary agent's spec is largely the same as v3 with an
        # added PROBING MANDATE section describing what the harness
        # will do.
        "SOC_RED_REAPER_TABULA_V4": 60,
        "SOC_RED_REAPER_TABULA_V4_FINISHER": 20,
        # TABULA_V5 — doctrine rewrite (state-triggered strategies); same
        # LLM budget as v3/v4. The lean CORE + gated appendices keep the
        # prompt no larger than v4 on any given night, often smaller.
        "SOC_RED_REAPER_TABULA_V5": 60,
        "SOC_RED_REAPER_TABULA_V5_FINISHER": 20,
        # TABULA_V6 — fork of v5; same wallclock budget until a change
        # proves it needs more.
        "SOC_RED_REAPER_TABULA_V6": 60,
        "SOC_RED_REAPER_TABULA_V6_FINISHER": 20,
        # TABULA_V7 — fork of v6; inherits the same wallclock budget until a
        # change proves it needs more.
        "SOC_RED_REAPER_TABULA_V7": 60,
        "SOC_RED_REAPER_TABULA_V7_FINISHER": 20,
        # TABULA_V7 THINKER — call 1 of the two-call split. haiku auto-does
        # ~30s of extended thinking on the Agents API before emitting the
        # answer/DECISION, so it needs ~50s (an 18s cap truncated it mid-think
        # every turn). Split mode is a headless A/B setting; this cap plus the
        # mover exceeds the 55s live wall by design.
        "SOC_RED_REAPER_TABULA_V7_THINKER": 50,
    }

    RESPONSE_CAP_OVERRIDES: Dict[str, int] = {
        **_LegacyInvoker.RESPONSE_CAP_OVERRIDES,
        "SOC_RED_REAPER_PILOT_V2": 40_000,
        "SOC_RED_REAPER_PILOT_V3": 40_000,
        # Two-call split — 3k bytes each. Combined ~6k is half of the
        # 12k baseline so the model produces less filler by construction.
        "SOC_RED_REAPER_STRATEGIC": 3_000,
        "SOC_RED_REAPER_TACTICAL": 3_000,
        # PILOT_V4 — tight response ceilings keep haiku terse by
        # construction (strategist reasons then commits; tactician JSON).
        # Strategist is roomy enough that rich reasoning never truncates
        # the mandatory PLAN footer; the wallclock cap bounds ramble.
        "SOC_RED_REAPER_STRATEGIST_V4": 10_000,
        "SOC_RED_REAPER_TACTICIAN_V4": 8_000,
        # TABULA — 3KB is enough for the compact JSON schema
        # (plan + rationale + predicted + moves + memory_note), which
        # typically comes in under 1KB. Small cap forces terseness and
        # kills rambling before it starts.
        "SOC_RED_REAPER_TABULA": 3_000,
        # TABULA_V2 — same tight ceiling; the prompt grew slightly but
        # the output schema (moves + rationale + memory_note) is the same
        # compact JSON, so keep the belt-and-braces cap.
        "SOC_RED_REAPER_TABULA_V2": 3_000,
        # TABULA_V3 — same tight ceiling. The prompt is bigger but the
        # OUTPUT JSON is still the same compact shape.
        "SOC_RED_REAPER_TABULA_V3": 3_000,
        # TABULA_V4 — same response cap as v3.
        "SOC_RED_REAPER_TABULA_V4": 3_000,
        # TABULA_V5 — roomier ceiling. A full 21-move plan + prose fields
        # overflowed the old 3KB cap, corrupting the JSON with a
        # "[…response capped]" marker and forcing heuristic fallback (the
        # rerun score collapse). The harness passes an explicit cap too;
        # this default keeps parity if a caller omits it. No wallclock cost
        # — the completion predicate closes the socket as soon as valid
        # JSON streams.
        "SOC_RED_REAPER_TABULA_V5": 8_000,
        "SOC_RED_REAPER_TABULA_V5_FINISHER": 4_000,
        # TABULA_V6 — inherits v5's roomier ceilings.
        "SOC_RED_REAPER_TABULA_V6": 8_000,
        "SOC_RED_REAPER_TABULA_V6_FINISHER": 4_000,
        # TABULA_V7 — inherits v6's roomier ceilings.
        "SOC_RED_REAPER_TABULA_V7": 8_000,
        "SOC_RED_REAPER_TABULA_V7_FINISHER": 4_000,
        # TABULA_V7 THINKER — roomy: reasoning prose lives here and never
        # reaches the mover or the mover's cap; only the DECISION line is used.
        "SOC_RED_REAPER_TABULA_V7_THINKER": 6_000,
    }
