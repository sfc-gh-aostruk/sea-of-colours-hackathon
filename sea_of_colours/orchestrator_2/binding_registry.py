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
    # v12 — the WORLD-VIEW release, and the only LLM agent this
    # distribution ships. Deterministic packager, redsign seam-control,
    # continuous journal, plus two persistent "beyond tonight" prompt
    # components: an agent-authored WORLD VIEW (cross-day rivals+map
    # model) and a static OUT-OF-GRID KNOWLEDGE reference (the fixed
    # scoring/weapon/redsign physics).
    #
    # Every earlier harness (pilot_v2..v4, tabula, tabula_v2..v11) was
    # deleted for the hackathon distribution — they were R&D lineage,
    # and leaving a dozen near-identical agents in the tree is the
    # fastest way to confuse someone asking "which one do I fork?".
    # The answer is: this one.
    "SOC_RED_REAPER_TABULA_V12": AgentBinding(
        kind="harness_in_process",
        locator="sea_of_colours.orchestrator_2.harnesses.tabula_v12.harness:run",
        agent_label="TABULA_V12",
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
    "tabula_v12": KNOWN_AGENT_BINDINGS["SOC_RED_REAPER_TABULA_V12"],
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
