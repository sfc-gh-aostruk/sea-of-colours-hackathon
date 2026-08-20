-- ============================================================================
-- Sea of Colours — Cortex Agent SOC_RED_REAPER_TACTICAL
-- ============================================================================
-- Master-harvester pilot. Sibling of SOC_RED_REAPER_PILOT, BUT the harness
-- now ships a pre-compiled menu of legal scored moves + a threat brief +
-- season memory alongside the usual STATE JSON (see
-- sea_of_colours/agent/candidates.py and runtime.CANDIDATE_CONSUMING_AGENTS).
-- The agent's job collapses from "do all the spatial math" to "pick or
-- compose from a menu", which lets us drop the budget from 120s/30k to
-- 30s/12k while improving decisions.
--
-- Doctrine lives entirely in this spec (RULES_IN_SPEC); per-turn message
-- is the slim envelope + STATE JSON with `candidates`, `threat`, and
-- `memory_summary` keys appended.
--
-- Tool surface: none. The harness owns all state mutation.
--
-- Run AFTER:
--   1. snowflake/soc_schema.sql
--   2. snowflake/soc_views.sql
--   3. snowflake/soc_procedures.sql
-- ============================================================================

USE DATABASE UMAN_SIM_DB;
USE SCHEMA SEA_OF_COLOURS;

CREATE OR REPLACE AGENT SOC_RED_REAPER_TACTICAL
  COMMENT = 'Sea of Colours: master-harvester pilot reading a pre-compiled candidate menu (sub-60s).'
FROM SPECIFICATION $$
models:
  orchestration: claude-haiku-4-5

orchestration:
  budget:
    seconds: 70
    tokens: 20000

instructions:
  orchestration: |
    You are SOC_RED_REAPER_TACTICAL. You have NO tools. Never try to call
    soc_submit_policy, soc_submit_orbit_actions, or any other tool.

    A STRATEGIST agent already picked the plan. Your job is only to choose
    one precompiled candidate ID from the STATE JSON. The harness validates
    your JSON and submits the selected policy for the current seat.

    Output must be one JSON object. No prose before or after it.

  response: |
    Return exactly one JSON object with these fields:

      seat      — copy STATE.meta.player exactly.
      phase     — copy STATE.meta.phase exactly, using "planning" for night.
      choice    — for planning, use "recommended_policy" or a candidate ID
                  from candidates.* (H0_harvester_p1, HOT0, P0, S0, C0,
                  DB0, EMP0, etc.). For orbit, use
                  "recommended_orbit_policy".
      rationale — one short sentence.

    Rules:
      - Do NOT emit raw moves or actions.
      - Do NOT name another player in seat.
      - Do NOT call tools.
      - If uncertain, choose the recommended policy for the current phase.

    Example:
    {"seat":"p1","phase":"planning","choice":"recommended_policy","rationale":"Best validated RED harvest mix for this plan."}
$$;

-- ============================================================================
-- Re-apply USAGE grants after CREATE OR REPLACE.
-- ============================================================================

GRANT USAGE ON DATABASE UMAN_SIM_DB TO ROLE SYSADMIN;
GRANT USAGE ON SCHEMA UMAN_SIM_DB.SEA_OF_COLOURS TO ROLE SYSADMIN;
GRANT USAGE ON WAREHOUSE SOC_WH TO ROLE SYSADMIN;
GRANT USAGE ON AGENT UMAN_SIM_DB.SEA_OF_COLOURS.SOC_RED_REAPER_TACTICAL TO ROLE SYSADMIN;

DESCRIBE AGENT SOC_RED_REAPER_TACTICAL;
