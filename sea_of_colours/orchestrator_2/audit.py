"""Audit writer for orchestrator_2.

Stamps one row into ``SOC_AGENT_INVOCATION`` per dispatched turn. The
column shape matches what the legacy orchestrator writes so the existing
UI / replay / postmortem queries keep working.

Source: :func:`sea_of_colours.snowpark.engine.save_agent_rationale`.
We delegate to it for backend consistency rather than rolling our own
INSERT — that way row deduplication, day-resolution race handling, and
column-truncation semantics stay in one place.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from sea_of_colours.orchestrator_2.binding_registry import AgentBinding
from sea_of_colours.orchestrator_2.dispatcher import DispatchResult
from sea_of_colours.snowpark import engine as soc_engine


# Soft cap on rationale length — the audit row's column is variant-y
# but the UI gets unhappy past a few KB. Matches the legacy
# orchestrator's ``RATIONALE_CHAR_CAP``.
RATIONALE_CHAR_CAP = 2_000

# Soft cap on the prompt-excerpt column so a 40KB STATE JSON doesn't
# blow up the audit row. 32KB captures ~80% of a typical PILOT_V2
# prompt — enough to include world.grid PLUS the extras blocks
# (candidates / combat / threat / memory_summary) that live at the
# end of the STATE JSON. 8KB was too aggressive: it truncated inside
# the fog-null world.grid before reaching the interesting content.
PROMPT_EXCERPT_CHAR_CAP = 32_000


def _truncate(s: str, cap: int) -> str:
    if len(s) <= cap:
        return s
    return s[: cap - 1] + "…"


def write_invocation(
    *,
    store,
    session_id: str,
    player: str,
    day: int,
    binding: AgentBinding,
    result: DispatchResult,
) -> None:
    """Persist one audit row for the dispatched turn."""
    rationale = _truncate(result.rationale or result.response, RATIONALE_CHAR_CAP)
    agent_id = binding.agent_label or binding.locator

    timings = {
        "elapsed_ms": result.elapsed_ms,
        "wallclock_capped": result.wallclock_capped,
    }
    timings.update(result.extras or {})

    # v0.9.27 — persist the prompt excerpt too. Harnesses that expose
    # the built prompt via ``extras["prompt_excerpt"]`` (PILOT_V2 does)
    # get their prompt captured in the audit row so we can debug what
    # the agent actually saw. Cap length so a 40KB brief doesn't blow
    # the row up.
    prompt_excerpt: Optional[str] = None
    extras = result.extras or {}
    if isinstance(extras, Mapping):
        raw = extras.get("prompt_excerpt")
        if isinstance(raw, str) and raw:
            prompt_excerpt = _truncate(raw, PROMPT_EXCERPT_CHAR_CAP)

    # Multi-agent observability: a harness that fires more than one Cortex call
    # per turn (e.g. the v7 split's THINKER + MOVER) can expose each extra call
    # via ``extras["sub_invocations"]``. We persist each as its OWN
    # SOC_AGENT_INVOCATION row (distinct agent_id) BEFORE the primary row, so
    # the reasoning of every sub-agent is visible in the UI / scannable in the
    # audit trail — not just the final move-enforcer. Best-effort: a bad
    # sub-row must never block the primary audit row.
    sub_invocations = []
    if isinstance(extras, Mapping):
        raw_subs = extras.get("sub_invocations")
        if isinstance(raw_subs, (list, tuple)):
            sub_invocations = list(raw_subs)
    for sub in sub_invocations:
        if not isinstance(sub, Mapping):
            continue
        try:
            sub_label = str(sub.get("label") or "SUB_AGENT")
            sub_prompt = sub.get("prompt_excerpt")
            soc_engine.save_agent_rationale(
                store,
                session_id,
                int(day),
                sub_label,
                player,
                _truncate(str(sub.get("rationale") or ""), RATIONALE_CHAR_CAP),
                runtime=str(sub.get("kind") or "sub"),
                prompt_excerpt=(
                    _truncate(sub_prompt, PROMPT_EXCERPT_CHAR_CAP)
                    if isinstance(sub_prompt, str) and sub_prompt else None
                ),
                tool_calls=[],
                response_text=str(sub.get("response_text") or ""),
                ms_elapsed=int(sub.get("ms_elapsed") or 0),
            )
        except Exception:  # pragma: no cover - a sub-row must not kill the turn
            pass

    try:
        soc_engine.save_agent_rationale(
            store,
            session_id,
            int(day),
            str(agent_id),
            player,
            rationale,
            runtime=binding.kind,
            prompt_excerpt=prompt_excerpt,
            tool_calls=list(result.tool_calls or []),
            response_text=result.response,
            ms_elapsed=int(result.elapsed_ms),
        )
    except Exception:  # pragma: no cover - audit failure must not kill a turn
        pass
