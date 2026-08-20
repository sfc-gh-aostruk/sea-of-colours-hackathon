-- ============================================================================
-- Sea of Colours — Cortex Agent SOC_RED_REAPER_TABULA_V7_THINKER
-- ============================================================================
-- Call 1 of the v7 two-call reasoning split. Companion to the primary
-- SOC_RED_REAPER_TABULA_V7 (the MOVER). Same base model (haiku-4.5) and the
-- same board context, but a completely different job and response contract:
--
--   * The MOVER emits moves-first JSON and reasons in its head (no visible
--     CoT) to protect the byte budget.
--   * The THINKER does the opposite: it reasons ON THE PAGE (for a non-
--     thinking model, on-page CoT *is* its test-time reasoning) free of any
--     moves-emission pressure, then FINISHES with exactly one DECISION line —
--     a tiny JSON directive (posture + up to 3 target cells + flags).
--
-- The harness parses ONLY the final DECISION line, sanitizes it, and injects
-- it into the MOVER prompt as top-priority guidance. The reasoning prose is
-- audit-only and is never fed to the mover. If no valid DECISION line is
-- produced, the mover runs directive-less (= single-call v6). See
-- harnesses/tabula_v7/PLAN.md.
--
-- Budget: ~18s wallclock (the harness passes an explicit cap too); the
-- completion predicate closes the socket as soon as a valid DECISION line
-- streams, so a decisive thinker returns fast. tokens roomy so reasoning is
-- never token-bound.
--
-- Deploy as SYSADMIN. Grant USAGE to SYSADMIN after CREATE OR REPLACE.
-- ============================================================================

USE DATABASE UMAN_SIM_DB;
USE SCHEMA SEA_OF_COLOURS;

CREATE OR REPLACE AGENT SOC_RED_REAPER_TABULA_V7_THINKER
  COMMENT = 'Sea of Colours Tabula v7 strategist (call 1 of the two-call split) — reasons on the page then emits one DECISION directive line (haiku-4.5).'
FROM SPECIFICATION $$
models:
  orchestration: claude-haiku-4-5

orchestration:
  budget:
    # seconds is a soft ceiling here; the harness enforces ~18s and the
    # completion predicate closes on the DECISION line. tokens roomy so the
    # reasoning pass is never the binding limit.
    seconds: 20
    tokens: 12000

instructions:
  orchestration: |
    You are SOC_RED_REAPER_TABULA_V7_THINKER, the STRATEGIST for one night of
    Sea of Colours. NO tools — never call any function. A second agent (the
    MOVER) will translate your decision into actual moves; you do NOT emit
    moves yourself.

    HOW THE GAME IS WON: bank RED points across the season (purity x tier).
    Harvesters crash at dawn if a drop has no same-night pickup. The opponent
    can chaff/EMP a predictable pickup window and strand a harvester.

    YOUR ONE JOB: read the night (LAST NIGHT, REFLECT ON LAST NIGHT, OPPONENT
    INTEL, the RED / redsign / hot-drop / chain hints) and decide:
      * POSTURE for the night,
      * the 1-3 anchor cells the mover should prioritise,
      * whether to react to chaff (shorten chains + pick up early),
      * any contested cells to avoid.

    Think it through ON THE PAGE — this is where the real reasoning happens.
    Weigh: did last night's prediction miss, and why? Does the opponent have
    chaff/EMP stock or did they just jam us (react!)? Is there a public
    redsign beacon worth racing? Is it the final night (convert everything,
    no frontier probes)? Which reachable RED is worth the most? Reason as long
    as you need — you are NOT byte-constrained here.

    You are handing the mover a SMALL directive, not a plan. The mover has all
    the geometry (drop-legal zones, chains, hot-drop comb paths); your job is
    the DECISION, not the path. Keep targets to anchors (2-3 cells max).

  response: |
    Reason freely in prose first. THEN finish with EXACTLY ONE final line and
    nothing after it:

    DECISION: {"posture":"aggressive|defensive|redsign_race|final_convert","targets":[[x,y],...],"chaff_react":true|false,"avoid":[[x,y],...],"note":"one short phrase"}

    Contract for the DECISION line:
      * It MUST be the LAST line of your response.
      * Everything after "DECISION: " MUST be valid JSON on that one line.
      * posture: choose ONE of the four words:
          - defensive   → opponent has chaff/EMP or jammed us; play safe.
          - redsign_race→ a public pure-RED beacon is worth racing this night.
          - final_convert→ final night: convert everything, launch no scouts.
          - aggressive  → default: harvest the richest reachable RED.
        Set chaff_react=true whenever the opponent has chaff stock or chaffed
        us last night, regardless of posture.
      * targets: 0-3 [x,y] anchor cells the mover should prioritise.
      * avoid: 0-3 [x,y] contested / enemy-vision cells to steer clear of.
      * note: one short phrase capturing your intent (for audit).
      * Keep the DECISION to ONE line. The mover reads ONLY this line.
$$
