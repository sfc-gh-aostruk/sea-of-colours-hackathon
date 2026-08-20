"""Eval runner for orchestrator_2.

Thin adapter over :mod:`sea_of_colours.evals.runner` that swaps the
agent-turn callable to point at
:func:`sea_of_colours.orchestrator_2.runtime.run_agent_turn`. Scenarios,
assertions, fixture builders, and the markdown report renderer come
from the v1 evals package unchanged.

This module also registers a ``pilot_v2`` :class:`EvalConfig` so the
existing eval CLI ergonomics (``--config pilot_v2``) continue to work
through the new orchestrator path.
"""

from __future__ import annotations

from typing import Optional

from sea_of_colours.evals.configs import CONFIGS as _LEGACY_CONFIGS
from sea_of_colours.evals.configs import EvalConfig
from sea_of_colours.evals.runner import (  # re-exported convenience
    ScenarioResult,
    _agent_context_extras,
    _build_watch_url,
    _extract_policy_from_store,
    _mirror_fixture_to_backend,
    _patched_env,
    _resolve_night_for_replay,
)
from sea_of_colours.evals.assertions import AssertionContext
from sea_of_colours.snowpark import engine as soc_engine

# Use orchestrator_2's run_agent_turn — this is the ONLY behavioural
# divergence from the v1 runner.
from sea_of_colours.orchestrator_2.runtime import run_agent_turn


# orchestrator_2-specific eval configs. The v1 runner has its own
# CONFIGS dict that we don't pollute — pilot_v2 lives here exclusively.
CONFIGS = {
    **{k: v for k, v in _LEGACY_CONFIGS.items()},  # inherit all v1 configs
    "pilot_v2": EvalConfig(
        label="pilot_v2",
        world_view="grid",
        cortex_agent="SOC_RED_REAPER_PILOT_V2",
        description=(
            "Master-harvester pilot reading a pre-compiled candidate menu. "
            "Runs through orchestrator_2's binding-driven dispatcher: "
            "the SOC_CORTEX_AGENT env var resolves to the in-process "
            "harness `harnesses/pilot_v2/harness:run`, which augments the "
            "universal STATE envelope with candidates/threat/memory_summary "
            "and invokes claude-haiku-4-5 with a 35s wall-clock cap. "
            "Drop-in challenger to the v1 `pilot` config."
        ),
    ),
    "pilot_v4": EvalConfig(
        label="pilot_v4",
        world_view="grid",
        cortex_agent="SOC_RED_REAPER_PILOT_V4",
        description=(
            "Two-phase agentic pilot (strategist + tactician), haiku-4.5. "
            "Routes through orchestrator_2 binding `pilot_v4/harness:run` "
            "which stages the strategist brief, compiles a candidate "
            "menu, runs the tactician selection, and materialises the "
            "policy queue. Populates `plan_label`, `selections`, and "
            "`materialized_count` on the agent envelope so the "
            "coherence assertions (Rationale*, PlanLabelIn, "
            "PlanMatchesMaterialisedVerb, NoSilentSelectionDrops) can "
            "verify the agent's reasoning grounds the moves."
        ),
    ),
}


def get_config(label: str) -> EvalConfig:
    """Same contract as the v1 ``get_config`` — KeyError on miss."""
    if label in CONFIGS:
        return CONFIGS[label]
    known = ", ".join(sorted(CONFIGS.keys()))
    raise KeyError(f"unknown eval config {label!r}. Known: {known}")


def run_scenario(
    scenario,
    *,
    runtime_override: Optional[str] = None,
    sample_index: int = 0,
    config: Optional[EvalConfig] = None,
    record_replay: bool = False,
) -> ScenarioResult:
    """Execute one scenario through orchestrator_2.

    Identical contract to :func:`sea_of_colours.evals.runner.run_scenario`,
    just routed through orchestrator_2's runtime. We don't subclass /
    monkey-patch the v1 runner because it imports the v1 ``run_agent_turn``
    at module level — duplicating the small dispatch loop here is
    cleaner than a runtime patch.
    """
    overrides = config.env_overrides() if config is not None else {}
    with _patched_env(overrides):
        store, session_id = scenario.build()
        if runtime_override == "cortex":
            store = _mirror_fixture_to_backend(store, session_id)
        sess = soc_engine._hydrate_session(store, session_id)
        if record_replay:
            cfg_label = config.label if config is not None else "default"
            sess.season_name = f"eval:{scenario.name}:{cfg_label}"
            soc_engine.save_session_full(store, sess)
        day_at_run = int(sess.day)
        player = scenario.player

        env = run_agent_turn(
            store, session_id, player, runtime_override=runtime_override,
        )

        policy = _extract_policy_from_store(
            store, session_id, day_at_run, player,
        )

        sess_after = soc_engine._hydrate_session(store, session_id)
        ctx_extras = _agent_context_extras(env)
        context = AssertionContext(
            session=sess_after, player=player, day_at_run=day_at_run,
            rationale=ctx_extras["rationale"],
            plan_label=ctx_extras["plan_label"],
            selection_count=ctx_extras["selection_count"],
            materialized_count=ctx_extras["materialized_count"],
        )

        results = [
            a.evaluate(policy, context=context)
            for a in scenario.assertions
        ]

        watch_url: Optional[str] = None
        if record_replay:
            try:
                _resolve_night_for_replay(store, session_id, player)
                watch_url = _build_watch_url(session_id)
            except Exception:
                watch_url = None

    return ScenarioResult(
        scenario_name=scenario.name,
        summary=scenario.summary,
        policy=policy,
        rationale=str(env.get("rationale") or ""),
        agent_id=str(env.get("agent_id") or ""),
        runtime=str(env.get("runtime") or runtime_override or ""),
        results=results,
        sample_index=sample_index,
        config_label=config.label if config is not None else None,
        session_id=session_id,
        watch_url=watch_url,
    )
