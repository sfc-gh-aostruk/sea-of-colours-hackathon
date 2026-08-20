"""Engine MECHANICS the agent must obey (tabula_v8 fork).

Physics does not change between v7 and v8 — the rules are the engine's,
not the agent's. v8 re-exports the frozen v7 ``RULES_SUMMARY`` verbatim so
the fork owns its own ``rules`` module (per the v8 restructure) without
duplicating immutable text that must stay byte-identical to the engine.

If a genuinely new mechanic ships, add it HERE (and only here) so v7 stays
frozen; advisory guidance belongs in :mod:`.doctrine`.
"""

from __future__ import annotations

from sea_of_colours.orchestrator_2.harnesses.tabula_v7.rules import (
    RULES_SUMMARY,
)

__all__ = ["RULES_SUMMARY"]
