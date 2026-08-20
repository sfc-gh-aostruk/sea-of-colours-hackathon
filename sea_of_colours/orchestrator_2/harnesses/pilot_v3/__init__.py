"""PILOT_V3's standalone harness.

Reads the universal STATE envelope, runs its own candidate compiler +
threat brief + season memory, calls the inner Cortex Agent
(SOC_RED_REAPER_PILOT_V3), and writes a policy via the agent's
``soc_submit_policy`` tool call.

Nothing in the orchestrator imports from this package. The orchestrator
only knows the locator string ``sea_of_colours.orchestrator_2.harnesses.pilot_v3.harness:run``.
"""

from sea_of_colours.orchestrator_2.harnesses.pilot_v3.harness import run

__all__ = ["run"]
