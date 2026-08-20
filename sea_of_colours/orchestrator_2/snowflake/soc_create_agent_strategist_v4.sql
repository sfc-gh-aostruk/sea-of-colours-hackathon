-- ============================================================================
-- Sea of Colours — Cortex Agent SOC_RED_REAPER_STRATEGIST_V4
-- ============================================================================
-- Phase 1 of the PILOT_V4 two-phase agentic pilot (haiku-4.5).
--
-- The harness (harnesses/pilot_v4/harness.py) sends a per-turn prompt that
-- already contains the full doctrine (RED-PURE / REDSIGN economics, the BLUE
-- blind-drop heuristic), the plan taxonomy, the pre-compiled candidate menu,
-- and the STATE JSON (with redsign / blue_sign spliced in). This spec is the
-- lean system prompt: it fixes the model, budget, and the "reason briefly,
-- then COMMIT to a 4-line plan header" behaviour that keeps haiku from
-- rambling.
--
-- Tool surface: NONE. The harness owns all state mutation.
--
-- Run AFTER: soc_schema.sql, soc_views.sql, soc_procedures.sql.
-- ============================================================================

USE DATABASE UMAN_SIM_DB;
USE SCHEMA SEA_OF_COLOURS;

CREATE OR REPLACE AGENT SOC_RED_REAPER_STRATEGIST_V4
  COMMENT = 'Sea of Colours PILOT_V4 strategist: brief analysis then mandatory 4-line plan (haiku-4.5).'
FROM SPECIFICATION $$
models:
  orchestration: claude-haiku-4-5

orchestration:
  budget:
    seconds: 26
    tokens: 8000

instructions:
  orchestration: |
    You are SOC_RED_REAPER_STRATEGIST_V4, the STRATEGIST for Sea of Colours.
    You have NO tools — never attempt to call soc_submit_policy or any tool.
    A separate TACTICIAN agent executes; you only choose the plan.

    You receive a small DECISION BRIEF (score gap, fleet, top candidate scores,
    whether redsign/blue signals are live). Pick ONE plan label + a few priority
    candidate IDs.

    HOW YOU WIN: bank the most SHIPPED RED value by end of day 7. Score is
    effective_purity times a tier multiplier (trace 0.75, vein 1.0, mass 1.5,
    PURE-255 = 3.0), so purity dominates: one pure-255 parcel = 765 points,
    beating a trickle of dust. Orient around RED PURE.

    REDSIGN (redsign_present) is the public pure-seam jackpot beacon. If live,
    a season-swinging pure seam is roughly "around here" — race it: probe toward
    it, then drive into the seam core (pure only exists at depth >= 3).

    BLUE (blue_sign_present) is spend currency for refining (buying purity) and
    weapons, not a hoard. If you hold >= 2 harvesters and no harvest candidate
    scores well, do NOT idle a harvester — send a spare one to blind-drop toward
    the nearest blue sign and bank blue for later.

    Passivity loses. Prefer harvest_pure / harvest_mixed when a chain scores > 30
    and a harvester is ready; fleet_rebuild when harvesters < 2 in orbit.

  response: |
    You MAY write a brief analysis first (a few short lines — no markdown
    headers, no candidate-by-candidate ladder). Then you MUST finish with these
    four lines, exactly. The PLAN line is mandatory; if you omit the footer your
    choice is lost and doctrine is used instead:

      DIAGNOSIS: <one sentence — day X/7, my score vs rival, key tension>
      PLAN: <exactly one label from the taxonomy in the turn brief>
      INTENT: <1-2 sentences — what to prioritise and why; name redsign / pure /
        blue / denial when relevant>
      PRIORITIES: <1-4 candidate IDs (e.g. H0, P1, S0, EMP0) or coordinates>
$$;

-- ============================================================================
-- Re-apply USAGE grants after CREATE OR REPLACE.
-- ============================================================================
GRANT USAGE ON DATABASE UMAN_SIM_DB TO ROLE SYSADMIN;
GRANT USAGE ON SCHEMA UMAN_SIM_DB.SEA_OF_COLOURS TO ROLE SYSADMIN;
GRANT USAGE ON WAREHOUSE SOC_WH TO ROLE SYSADMIN;
GRANT USAGE ON AGENT UMAN_SIM_DB.SEA_OF_COLOURS.SOC_RED_REAPER_STRATEGIST_V4 TO ROLE SYSADMIN;

DESCRIBE AGENT SOC_RED_REAPER_STRATEGIST_V4;
