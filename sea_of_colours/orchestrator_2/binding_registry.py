"""Binding registry — how orchestrator_2 decides where to send a turn.

An :class:`AgentBinding` names a delivery target for one ``(session,
player)`` pair. Four kinds today:

* ``cortex_agent``        — bare Snowflake Cortex Agent. Orchestrator
                            builds the universal envelope and POSTs to
                            ``agents/<locator>:run``. ``locator`` is the
                            agent's Snowflake object name.
* ``harness_in_process``  — Python module living in this repo. Locator
                            is ``"<module>:<callable>"``. The
                            dispatcher imports it and calls the entry
                            point with the universal envelope. The
                            harness handles its own prompt + tool calls.
* ``harness_proc``        — Snowflake stored procedure (future). Locator
                            is the proc identifier. Dispatcher invokes
                            ``CALL <proc>(p_session_id, p_player, p_state_json)``.
                            Stub today; raises NotImplementedError.
* ``harness_spcs``        — Snowpark Container Service (future). Locator
                            is the HTTPS URL. Dispatcher POSTs the
                            envelope. Stub today.
* ``heuristic``           — in-process RED_HARVEST. Locator is the
                            strategy name (``"RED_HARVEST"``).

Resolution order (most explicit first):

1. ``SOC_AGENT_BINDING`` Snowflake table — when backend == snowflake.
2. ``SOC_BINDING_<PLAYER>`` env var — e.g.
   ``SOC_BINDING_P1=harness_in_process:sea_of_colours.orchestrator_2.harnesses.pilot_v2.harness:run``.
3. ``SOC_CORTEX_AGENT`` env var + the :data:`KNOWN_AGENT_BINDINGS` map —
   lets existing eval configs keep setting that env var and have
   orchestrator_2 figure out the right binding (e.g. PILOT_V2 →
   harness_in_process; PILOT v1 → cortex_agent).
4. ``SOC_AGENT_RUNTIME=heuristic`` → kind=heuristic.
5. Default: heuristic.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


# ── Public dataclass ────────────────────────────────────────────────
@dataclass(frozen=True)
class AgentBinding:
    """One delivery target for a turn."""

    kind: str
    locator: str
    agent_label: Optional[str] = None  # display name (e.g. "PILOT_V2")


# ── Known-agent map (orchestrator_2's view of who's who) ───────────
#
# Maps a Cortex agent name (the historical ``SOC_CORTEX_AGENT`` env var
# value) to the binding orchestrator_2 should use for it. Keeps the
# existing eval CLI ergonomics: set ``SOC_CORTEX_AGENT=...`` and
# orchestrator_2 figures out whether that name needs a harness wrap.
#
# IMPORTANT: orchestrator_2 ONLY claims agents in this map. Anything
# else falls through to the heuristic. The original orchestrator
# continues to serve PILOT v1, GRID_FAST, etc. — they are NOT registered
# here on purpose.
KNOWN_AGENT_BINDINGS = {
    "SOC_RED_REAPER_PILOT_V2": AgentBinding(
        kind="harness_in_process",
        locator="sea_of_colours.orchestrator_2.harnesses.pilot_v2.harness:run",
        agent_label="PILOT_V2",
    ),
    "SOC_RED_REAPER_PILOT_V3": AgentBinding(
        kind="harness_in_process",
        locator="sea_of_colours.orchestrator_2.harnesses.pilot_v3.harness:run",
        agent_label="PILOT_V3",
    ),
    "SOC_RED_REAPER_PILOT_V4": AgentBinding(
        kind="harness_in_process",
        locator="sea_of_colours.orchestrator_2.harnesses.pilot_v4.harness:run",
        agent_label="PILOT_V4",
    ),
    # Tabula — harvest-only phase-1 pilot (formerly pilot_v6_arena). Single LLM
    # call per night (orbit stubs to empty), memory-driven predict/reflect loop,
    # candidates as hints (scores stripped) so the LLM computes EV itself.
    # Named "Tabula" (blank slate) because this is the new base agent — all
    # future extensions build on top of this clean single-LLM harness.
    "SOC_RED_REAPER_TABULA": AgentBinding(
        kind="harness_in_process",
        locator="sea_of_colours.orchestrator_2.harnesses.tabula.harness:run",
        agent_label="TABULA",
    ),
    # Tabula v2 — adds probe intelligence on top of v1. Extends the prompt
    # with FOG + ECHO exposure and PROBE PLACEMENT HINTS (area_gain +
    # edge_promise). v1 remains fully isolated and functional at the tabula
    # locator; v2 is a separate binding so both can be run/A-B tested.
    "SOC_RED_REAPER_TABULA_V2": AgentBinding(
        kind="harness_in_process",
        locator="sea_of_colours.orchestrator_2.harnesses.tabula_v2.harness:run",
        agent_label="TABULA_V2",
    ),
    # Tabula v3 — adds opponent awareness, hot drops, blue harvesting,
    # orbit→tactical wishlist hand-off, harvester crash rules, and a
    # rules/strategies split. v2 remains fully isolated and functional
    # at the tabula_v2 locator; v3 is a separate binding so both can be
    # run/A-B tested side by side.
    "SOC_RED_REAPER_TABULA_V3": AgentBinding(
        kind="harness_in_process",
        locator="sea_of_colours.orchestrator_2.harnesses.tabula_v3.harness:run",
        agent_label="TABULA_V3",
    ),
    # Tabula v4 — adds aggressive-probing structural mandate. The
    # harness prepends probes from the compiler's top hints when the
    # LLM's plan under-launches given available stock + open fog.
    # Motivation: v3 solo runs launched 7 probes/season vs the
    # heuristic's 18, and that gap capped LLM-agent performance.
    # v3 remains fully isolated at the tabula_v3 locator.
    "SOC_RED_REAPER_TABULA_V4": AgentBinding(
        kind="harness_in_process",
        locator="sea_of_colours.orchestrator_2.harnesses.tabula_v4.harness:run",
        agent_label="TABULA_V4",
    ),
    # Tabula v5 — lean core doctrine + conditional appendices. Replaces
    # v4's monolithic STRATEGIES_SUMMARY (10KB always-on) with a
    # STRATEGIES_CORE (~4.6KB) plus DOCTRINE_BLUE / DOCTRINE_REDSIGN /
    # DOCTRINE_BEWARE_EMP / DOCTRINE_BEWARE_CHAFF blocks that only ship
    # when their trigger condition fires. Also removes the deterministic
    # probe augmenter — probing is doctrine-driven only.
    "SOC_RED_REAPER_TABULA_V5": AgentBinding(
        kind="harness_in_process",
        locator="sea_of_colours.orchestrator_2.harnesses.tabula_v5.harness:run",
        agent_label="TABULA_V5",
    ),
    # Tabula v6 — faithful fork of v5 (the 4-0 baseline: seeds 42/7/99/2024
    # vs heuristic). v6 is where prior-night comprehension (reflection +
    # chaff), hot-drop combing (walk the whole revealed disk), and fog-beacon
    # redsign hot-drop combos get developed. v5 stays frozen as the champion
    # so we can A/B every v6 change against a known-good reference.
    "SOC_RED_REAPER_TABULA_V6": AgentBinding(
        kind="harness_in_process",
        locator="sea_of_colours.orchestrator_2.harnesses.tabula_v6.harness:run",
        agent_label="TABULA_V6",
    ),
    # Tabula v7 — faithful fork of v6, minted as the next dev baseline once
    # v6's moves-first + grounded-reflection + comb-path batch was proven.
    # v6 stays frozen as the reference; v7 is where the next batch of
    # improvements (see harnesses/tabula_v7/GOAL.md) is developed and A/B'd.
    "SOC_RED_REAPER_TABULA_V7": AgentBinding(
        kind="harness_in_process",
        locator="sea_of_colours.orchestrator_2.harnesses.tabula_v7.harness:run",
        agent_label="TABULA_V7",
    ),
    # Tabula v8 — the consolidation release. Currently a thin activation layer
    # over the v7 harness that forces the CONTAINED TWO-CALL SPLIT (reasoning-
    # first thinker + moves-first mover, both on the inference API). Lets v8 run
    # head-to-head vs the frozen v6/v7 champions in one arena; forks proper once
    # the §4 data hooks + §5 doctrine land (see tabula_v8/PLAN.md).
    "SOC_RED_REAPER_TABULA_V8": AgentBinding(
        kind="harness_in_process",
        locator="sea_of_colours.orchestrator_2.harnesses.tabula_v8.harness:run",
        agent_label="TABULA_V8",
    ),
    # Tabula v9 — the COMPREHENSION release (true fork of v8). Keeps v8's
    # contained two-call split + 3-pillar worldview and adds the attributed
    # event digest (why a probe/harvest/night was lost, with attacker +
    # consequence), a REFLECT block that forces a consequence acknowledgment,
    # EMP scars as a hazard, engine-truth redsign discoverer attribution, and
    # the rewritten two-case weapon-free redsign-poker doctrine. v6/v7/v8 stay
    # frozen. (v11 is the separate native-thinking-Sonnet bet.)
    "SOC_RED_REAPER_TABULA_V9": AgentBinding(
        kind="harness_in_process",
        locator="sea_of_colours.orchestrator_2.harnesses.tabula_v9.harness:run",
        agent_label="TABULA_V9",
    ),
    # Tabula v10 — the COMPILER-FAITHFULNESS release (true fork of v9, which
    # completed the comprehension agenda and won seed 69). v10 keeps v9's
    # thinker/doctrine but replaces the freelancing LLM executor with a
    # DETERMINISTIC packager (compiler pattern), and adds anti-crowd seat
    # differentiation + economy/final-night guards (see tabula_v10/
    # SEED69_FIXPLAN.md, R0–R6). v9 stays frozen. (v11 = native-thinking-Sonnet.)
    "SOC_RED_REAPER_TABULA_V10": AgentBinding(
        kind="harness_in_process",
        locator="sea_of_colours.orchestrator_2.harnesses.tabula_v10.harness:run",
        agent_label="TABULA_V10",
    ),
    # Tabula v11 — the ASSIGNMENT-COMPREHENSION release (true fork of v10). Keeps
    # v10's deterministic packager, walk-in reachability, and grounded reflection,
    # and adds the Pyramid × Posture harvester-assignment model + posture-tuned
    # plays + grounded memories (see tabula_v11_PLAN.md). Kills v10's probe-starved
    # dead turns, echo-pure literalism, and dual-redsign confusion. v10 stays
    # frozen as the fallback champion. (v12 = native-thinking-Sonnet bet.)
    "SOC_RED_REAPER_TABULA_V11": AgentBinding(
        kind="harness_in_process",
        locator="sea_of_colours.orchestrator_2.harnesses.tabula_v11.harness:run",
        agent_label="TABULA_V11",
    ),
}

# Heuristic fallback — used when no other binding resolves.
HEURISTIC_BINDING = AgentBinding(
    kind="heuristic",
    locator="RED_HARVEST",
    agent_label="RED_HARVEST",
)

# Hackathon "training wheels" opponent — same deterministic playbook,
# weapons (chaff/EMP) never built or fired. ``_dispatch_heuristic``
# branches on ``locator`` to pick this apart from the competitive
# ``HEURISTIC_BINDING`` above.
HEURISTIC_LITE_BINDING = AgentBinding(
    kind="heuristic",
    locator="RED_HARVEST_LITE",
    agent_label="RED_HARVEST_LITE",
)

# Game-config agent labels — the values stored in ``GameSession.agents``
# (chosen in the New Game / multiplayer menu) mapped to a binding. This
# lets the live server route a seat tagged e.g. ``"pilot_v2"`` straight
# to the harness with no env vars, so a human-vs-agent game works from
# the menu alone. Anything not listed here is treated as heuristic.
AGENT_LABEL_BINDINGS = {
    "pilot_v2": KNOWN_AGENT_BINDINGS["SOC_RED_REAPER_PILOT_V2"],
    "pilot_v3": KNOWN_AGENT_BINDINGS["SOC_RED_REAPER_PILOT_V3"],
    "pilot_v4": KNOWN_AGENT_BINDINGS["SOC_RED_REAPER_PILOT_V4"],
    "pilot_v6_arena": KNOWN_AGENT_BINDINGS["SOC_RED_REAPER_TABULA"],
    "tabula": KNOWN_AGENT_BINDINGS["SOC_RED_REAPER_TABULA"],
    "tabula_v2": KNOWN_AGENT_BINDINGS["SOC_RED_REAPER_TABULA_V2"],
    "tabula_v3": KNOWN_AGENT_BINDINGS["SOC_RED_REAPER_TABULA_V3"],
    "tabula_v4": KNOWN_AGENT_BINDINGS["SOC_RED_REAPER_TABULA_V4"],
    "tabula_v5": KNOWN_AGENT_BINDINGS["SOC_RED_REAPER_TABULA_V5"],
    "tabula_v6": KNOWN_AGENT_BINDINGS["SOC_RED_REAPER_TABULA_V6"],
    "tabula_v7": KNOWN_AGENT_BINDINGS["SOC_RED_REAPER_TABULA_V7"],
    "tabula_v8": KNOWN_AGENT_BINDINGS["SOC_RED_REAPER_TABULA_V8"],
    "tabula_v9": KNOWN_AGENT_BINDINGS["SOC_RED_REAPER_TABULA_V9"],
    "tabula_v10": KNOWN_AGENT_BINDINGS["SOC_RED_REAPER_TABULA_V10"],
    "tabula_v11": KNOWN_AGENT_BINDINGS["SOC_RED_REAPER_TABULA_V11"],
    "red_harvest_lite": HEURISTIC_LITE_BINDING,
}

# Labels that mean "just play the in-process heuristic".
_HEURISTIC_LABELS = {"human", "red_harvest", "heuristic"}


def _parse_env_binding(spec: str) -> AgentBinding:
    """Parse ``"<kind>:<locator>"`` (or ``"<kind>:<locator>:<label>"``)."""
    parts = spec.split(":", 2)
    if len(parts) < 2:
        raise ValueError(
            f"env binding {spec!r} must be 'kind:locator' or 'kind:locator:label'"
        )
    kind = parts[0].strip()
    locator = parts[1].strip()
    label = parts[2].strip() if len(parts) == 3 else None
    return AgentBinding(kind=kind, locator=locator, agent_label=label)


def resolve_binding(
    store,
    session_id: str,
    player: str,
    *,
    runtime_override: Optional[str] = None,
    agent_label: Optional[str] = None,
) -> AgentBinding:
    """Find the binding for ``(session_id, player)`` using the resolution order.

    ``runtime_override`` short-circuits everything:
    - ``"heuristic"`` → :data:`HEURISTIC_BINDING`
    - ``"cortex"``    → continue resolution (falls through to env vars + KNOWN_AGENT_BINDINGS)

    ``agent_label`` is the per-seat game-config label (from
    ``GameSession.agents`` / the New Game menu). When it names a known
    agent (:data:`AGENT_LABEL_BINDINGS`) it wins over env vars — this is
    how the live server routes a menu-selected ``"pilot_v2"`` seat to the
    harness without any env plumbing. A ``runtime_override="heuristic"``
    still forces the heuristic (used by the safety-net fallback).

    Order otherwise: seat label → env override → SOC_CORTEX_AGENT →
    SOC_AGENT_RUNTIME → heuristic. The Snowflake ``SOC_AGENT_BINDING``
    table is not consulted yet — that's a Phase 5 deliverable.
    """
    if runtime_override == "heuristic":
        return HEURISTIC_BINDING

    # 0. Explicit per-seat game-config label (New Game / multiplayer menu).
    if agent_label:
        lbl = agent_label.strip().lower()
        if lbl in AGENT_LABEL_BINDINGS:
            return AGENT_LABEL_BINDINGS[lbl]
        if lbl in _HEURISTIC_LABELS:
            return HEURISTIC_BINDING

    # 1. Per-player env var (most explicit).
    env_key = f"SOC_BINDING_{player.upper()}"
    spec = os.environ.get(env_key)
    if spec:
        return _parse_env_binding(spec)

    # 2. SOC_CORTEX_AGENT + known-agent map.
    agent_name = (os.environ.get("SOC_CORTEX_AGENT") or "").strip()
    if agent_name and agent_name in KNOWN_AGENT_BINDINGS:
        return KNOWN_AGENT_BINDINGS[agent_name]

    # 3. Bare Cortex agent — anyone setting SOC_CORTEX_AGENT to a name
    #    we don't know about wants to talk to it raw. We don't claim
    #    those (the v1 orchestrator does); fall through to heuristic so
    #    nothing accidentally double-dispatches.
    if runtime_override == "cortex":
        # Caller insisted on cortex but we don't recognise the agent.
        # Treat as a bare-Cortex binding; the dispatcher will POST the
        # universal envelope to that agent name.
        if agent_name:
            return AgentBinding(
                kind="cortex_agent",
                locator=agent_name,
                agent_label=agent_name,
            )

    # 4. SOC_AGENT_RUNTIME (legacy switch).
    mode = (os.environ.get("SOC_AGENT_RUNTIME") or "heuristic").strip().lower()
    if mode == "heuristic":
        return HEURISTIC_BINDING

    # 5. Default safety net.
    return HEURISTIC_BINDING
