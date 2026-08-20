"""Sea of Colours agent runtimes.

Sea of Colours ships two distinct agent families:

* **RED_HARVEST** — the deterministic Python heuristic
  (:class:`HeuristicAgent`). This is our mainstay agent: it is the
  default behind the ``[ LET RED_HARVEST PLAY ]`` button, runs without
  any Snowflake / Cortex dependency, and is fully tested. Pick it when
  you just want a reasonable opponent / partner with no setup.
* **AI agents** — Snowflake Cortex agents declared in
  ``snowflake/soc_create_agent.sql`` and driven through
  :class:`CortexAgentInvoker`. The first such agent is
  ``SOC_RED_REAPER``; additional Cortex agents register against
  :data:`sea_of_colours.agent.runtime.AI_AGENTS`. Select an AI agent by
  exporting ``SOC_AGENT_RUNTIME=cortex`` (optionally with
  ``SOC_CORTEX_AGENT=<name>``).

Both families return the same envelope::

    {
        "ok": bool,
        "agent_id": str,            # e.g. "RED_HARVEST" / "SOC_RED_REAPER"
        "runtime": "heuristic" | "cortex",
        "rationale": str,
        "moves": [<wire-format move>...],
        "tool_calls": list[dict],
        "ms_elapsed": int,
    }
"""

from sea_of_colours.agent.heuristic_agent import HeuristicAgent, plan_moves
from sea_of_colours.agent.runtime import (
    AI_AGENTS,
    CORTEX_AGENT_DEFAULT,
    HEURISTIC_AGENT_NAME,
    run_agent_turn,
)

__all__ = [
    "AI_AGENTS",
    "CORTEX_AGENT_DEFAULT",
    "HEURISTIC_AGENT_NAME",
    "HeuristicAgent",
    "plan_moves",
    "run_agent_turn",
]
