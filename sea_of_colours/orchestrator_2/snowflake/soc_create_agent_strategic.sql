-- ============================================================================
-- Sea of Colours — Cortex Agent SOC_RED_REAPER_STRATEGIC
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
-- Tool surface: ONE tool, soc_submit_policy. p_policy is a JSON STRING.
--
-- Run AFTER:
--   1. snowflake/soc_schema.sql
--   2. snowflake/soc_views.sql
--   3. snowflake/soc_procedures.sql
-- ============================================================================

USE DATABASE UMAN_SIM_DB;
USE SCHEMA SEA_OF_COLOURS;

CREATE OR REPLACE AGENT SOC_RED_REAPER_STRATEGIC
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
    You are SOC_RED_REAPER_STRATEGIC. Your ONLY output is a 4-line plan
    header. You have NO tools. Do NOT attempt to call any tool.

    You receive a full turn brief from the runtime — it contains the
    STATE JSON, candidates, threat block, memory. You DO NOT need to
    analyse it deeply. You skim for three things:
      1. Score gap (am I ahead, even, or behind?)
      2. Posture / final_day flag (aggressive, balanced, conservative,
         or final-night)
      3. Top harvest / probe / EMP candidate IDs

    Then you write your 4-line output. See the response spec.

    Do NOT walk any priority ladder. Do NOT diagnose tension by tension.
    Do NOT write bold section headers ("**State:**", "**Tension:**").
    Do NOT list every candidate. Do NOT compose moves. A separate
    TACTICIAN agent handles execution.

  response: |
    YOU ARE THE STRATEGIST for Sea of Colours night R+D.

    Your ONLY job: read the state and choose ONE plan label. You have
    NO tools. Do NOT try to call soc_submit_policy or any tool —
    another agent will handle execution.

    Available plan labels — pick EXACTLY ONE:
      - harvest_pure: Chase MASS+/PURE chains. Score dominates; ignore denial slots.
      - harvest_mixed: Standard VEIN/MASS mixed chain revenue. The default play.
      - denial_dominant: Supersede / crush / drop-block focus. Deny the rival; minimal harvest.
      - emp_race: Pre-empt or race a rival EMP. Fire immediately if we can afford it.
      - vault_flush_orbit: ORBIT-only. Vault is under pressure; ship + refine consume all slots.
      - probe_seed: Coverage expansion. Few harvests, spend actions on probes.
      - defensive_repair: ORBIT-only. Damaged harvesters; repair takes priority over spending.
      - fleet_rebuild: ORBIT-only. Harvester count below 2; buy a harvester before other spending.
      - final_day_push: Final night. Maximum banked value; probes give zero future return.

    Output EXACTLY these four lines and nothing else (≤ 1500 chars):

      DIAGNOSIS: <one sentence — day X/7, my score vs rival, main tension>
      PLAN: <one label from the list above>
      TOP: <1-3 candidate IDs or coordinates that best fit the plan>
      RATIONALE: <one sentence — why this plan over the alternatives>

    Do NOT write any preamble. Do NOT list candidates. Do NOT describe
    the world. Do NOT reason paragraph-by-paragraph. Four lines total.
$$;

-- ============================================================================
-- Re-apply USAGE grants after CREATE OR REPLACE.
-- ============================================================================

GRANT USAGE ON DATABASE UMAN_SIM_DB TO ROLE SYSADMIN;
GRANT USAGE ON SCHEMA UMAN_SIM_DB.SEA_OF_COLOURS TO ROLE SYSADMIN;
GRANT USAGE ON WAREHOUSE SOC_WH TO ROLE SYSADMIN;
GRANT USAGE ON AGENT UMAN_SIM_DB.SEA_OF_COLOURS.SOC_RED_REAPER_STRATEGIC TO ROLE SYSADMIN;
GRANT USAGE ON PROCEDURE UMAN_SIM_DB.SEA_OF_COLOURS.SOC_SUBMIT_POLICY(STRING, STRING, STRING) TO ROLE SYSADMIN;

DESCRIBE AGENT SOC_RED_REAPER_STRATEGIC;
