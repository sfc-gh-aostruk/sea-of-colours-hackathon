"""PILOT_V4's standalone harness.

Two-phase agentic pilot (haiku-4.5):

* STRATEGIST (``SOC_RED_REAPER_STRATEGIST_V4``) reads the STATE + the
  compiled candidate menu + threat/combat/redsign/blue_sign and commits
  to ONE plan label plus a short intent. It reasons — briefly — about the
  strategic situation (score gap, jackpot seams, blue economy, fleet).
* TACTICIAN (``SOC_RED_REAPER_TACTICIAN_V4``) reads the strategist's plan
  and the menu, then picks + orders + lightly edits the candidate moves
  that best serve the plan, emitting a JSON selection.
* The harness materialises the selection into a legal move queue,
  enforces invariants (slot cap, every deployed harvester gets a pickup),
  and submits. Any parse/validation miss falls back to the always-legal
  doctrine ``recommended_policy``.

Nothing in the orchestrator imports from this package. The orchestrator
only knows the locator string
``sea_of_colours.orchestrator_2.harnesses.pilot_v4.harness:run``.
"""

from sea_of_colours.orchestrator_2.harnesses.pilot_v4.harness import run

__all__ = ["run"]
