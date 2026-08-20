"""Engine MECHANICS the agent must obey (tabula_v10 fork).

Physics does not change between v7/v8 and v10 — the rules are the engine's,
not the agent's. v10 re-exports the frozen ``RULES_SUMMARY`` verbatim so the
fork owns its own ``rules`` module (per the fork convention) without
duplicating immutable text that must stay byte-identical to the engine.

If a genuinely new mechanic ships, add it HERE (and only here); advisory
guidance belongs in :mod:`.doctrine`.
"""

from __future__ import annotations

from sea_of_colours.orchestrator_2.harnesses.tabula_v7.rules import (
    RULES_SUMMARY as _V7_RULES_SUMMARY,
)

# SCORING CORRECTION (v10 hermetic fix — hyg-scoring). The engine scores a
# parcel as ``eff_purity × RED_QUALITY_MULTIPLIER[tier]`` (snowpark/engine.py
# ``_parcel_score_value``); a pure(255) is 255 × 3.0 = 765 base pts. The frozen
# v7 text DOUBLE-COUNTS the tier multiplier ("765 × 3.0 = 2295"), which taught
# the thinker a pure was worth 2295 (confirmed in the s69-d2 replay). Correct it
# for v10 ONLY, so v7/v8 baselines stay byte-frozen for the comparison.
RULES_SUMMARY = _V7_RULES_SUMMARY.replace(
    "the cell scores 765 × 3.0 tier_mult = 2295 base pts and whoever",
    "the cell scores 255 × 3.0 tier_mult = 765 base pts (the biggest single-cell "
    "score; the SEAM around it adds more) and whoever",
)
assert "2295" not in RULES_SUMMARY, "v10 scoring correction failed to apply"

# FULL-UTILIZATION CORRECTION (v10 hermetic fix — ws-full-utilization / audit A6).
# The frozen v7 CHAIN GRAMMAR assumes a 2-harvester fleet ("budget is generous"),
# which invites an idle harvester. The engine fields 3 (HARVESTER_MAX_PER_PLAYER)
# and 3 × 7h = 21h = the whole night, so a FULL fleet FILLS the night and
# probes/weapons trade against harvest hours. Correct it for v10 only.
RULES_SUMMARY = RULES_SUMMARY.replace(
    "With 2 harvesters chaining 7 hours each + 2 probes at 1 hour each, you use\n"
    "16 of your 21 hours — budget is generous.",
    "DEPLOY EVERY HARVESTER: you can field 3 (HARVESTER_MAX_PER_PLAYER) and\n"
    "3 × 7 hours = 21 = the whole night — the night is DESIGNED for a full triple\n"
    "drop. An idle harvester in orbit is wasted value, so get ALL of them onto the\n"
    "board. A full fleet FILLS the night: probes (1h each) and own-weapon plays\n"
    "then trade AGAINST harvest hours — not free slack. Run each chain only as\n"
    "long as the VALUE warrants (short on a thin seam); never pad with dead steps.",
)
assert "budget is generous" not in RULES_SUMMARY, (
    "v10 full-utilization correction failed to apply"
)

__all__ = ["RULES_SUMMARY"]
