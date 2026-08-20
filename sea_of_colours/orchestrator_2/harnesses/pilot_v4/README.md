# PILOT_V4 harness — two-phase *agentic* pilot (haiku-4.5)

Self-contained brain for `SOC_RED_REAPER_PILOT_V4`. The orchestrator only
knows this package's locator
(`sea_of_colours.orchestrator_2.harnesses.pilot_v4.harness:run`); nothing in
the orchestrator imports from here.

## Why v4

- **v2** ran one big call that did all the analysis *and* composed the move
  queue — it rambled and looped.
- **v3** over-corrected: it disabled the tactical LLM (`TACTICAL_LLM_ENABLED
  = False`) and crushed the strategist to a rubber-stamp, so the "agent" was
  really a heuristic.
- **v4** keeps two phases but makes *both* genuine, bounded LLM calls, and
  moves the safety net into the harness so a miss still submits a legal move.

## The turn

1. **STRATEGIST** (`SOC_RED_REAPER_STRATEGIST_V4`, ~18–25s) reads a *tiny
   decision brief* (score gap, fleet, top candidate scores, redsign / blue
   presence) — not the full grid, which is what made haiku ramble. It picks
   ONE plan label (phase-filtered — planning turns never see orbit-only
   plans) + a short INTENT + PRIORITIES. The doctrine baked into its prompt:
   - **RED PURE is the jackpot**: score = purity × tier mult; PURE-255 × 3.0
     = 765 pts/parcel, so one pure launch beats a trickle of dust.
   - **REDSIGN** is the *public* pure-seam beacon — if lit, assume the rival
     races the same seam. Winning the core is a *fight*: it may take denial
     (EMP the racing harvester, `harvester_crush`, `drop_block`, chaff) to
     get there first. Denial is normally secondary **except** when contesting
     a pure seam, where it is the highest-value play.
   - **INTERDICTION TOOLKIT** (surfaced in the brief's `interdiction` / `emp`
     summary): `emp_launch` (freezes a cloud incl. our own units — watch
     `self_freeze`), `harvester_crush`, `drop_block`, `probe_supersede`,
     `hot_drop`, and orbit `build_chaff` / `build_mine` / `build_emp`.
   - **BLUE** is spend currency; with ≥2 harvesters and no rich RED, send a
     spare harvester to blind-drop toward a blue-sign rather than idle it.
2. **TACTICIAN** (`SOC_RED_REAPER_TACTICIAN_V4`, ~3–15s) reads the plan + the
   full pre-validated candidate MENU (night — incl. the denial candidates and
   a `combat` block with EMP cost/radius/cloud-hours) or ORBIT OPTIONS, and
   emits JSON: an ordered list of candidate IDs, each optionally trimmed
   (`trim_to`). Genuine pick + order + light-edit agency, including sequencing
   denial / EMP picks first for `emp_race` / `denial_dominant`.
3. **HARNESS** materialises the selection into a legal queue, enforces
   invariants, and submits:
   - ≤ 21 planning slots / orbit `max_actions`.
   - **one commitment per harvester**: `H0`/`H1`/`H2` are usually *alternative*
     chains for the same unit; the harness keeps the first and skips the rest
     (`skipped_conflicts`) so a harvester is never dropped at two cells in one
     Nox.
   - **pickup invariant**: every deployed *and* newly-dropped harvester gets
     a `pickup`, or it dies at Aurora — the harness auto-repairs a missing
     one.
   - illegal verb / unknown id / empty selection / bad JSON → fall back to
     the always-legal doctrine `recommended_policy` /
     `recommended_orbit_policy`.

Both agents tend to write a short analysis before their committed output;
the harness gives generous *capture* room (strategist 10k, tactician 8k
bytes) so the trailing `PLAN:` footer / JSON always lands and parses. The
wallclock caps (strategist 28s, tactician 45s; 90s PILOT_V4 ceiling) bound
the tail. Observed: total p50 ~29s, p95 ~40s.

## Module layout

| File | Purpose |
|---|---|
| `harness.py` | Two-phase driver: strategist brief → tactician menu → materialize + validate + submit. |
| `plans.py` | Phase-tagged plan taxonomy + `prompt_line_for_strategist(phase)` / `labels_for_phase`. |
| `candidates.py` / `orbit.py` / `combat.py` / `threat_assess.py` | The pre-compiled scored option menus (spatial math). |
| `memory.py` | Process-local enemy-vision history. |

## Cortex specs

`orchestrator_2/snowflake/soc_create_agent_strategist_v4.sql` and
`..._tactician_v4.sql` (both `claude-haiku-4-5`, no tools). Deployed in
`UMAN_SIM_DB.SEA_OF_COLOURS`. **The REST/PAT call runs as the token's role
(SYSADMIN here), so after any `CREATE OR REPLACE` re-grant USAGE to that
role** (or create it as SYSADMIN, which now holds `CREATE AGENT` on the
schema).

## Verifying the agent — the staged probe

`scripts/pilot_v4_probe.py` drives ONE real turn and prints a PASS/WARN/FAIL
verdict per elementary stage, exiting at the first failure so a break is
localised instantly:

```
S0 credentials · S1 compile · S2 strategist · S3 tactician
S4 materialize (legal · ≤21 · every harvester has a pickup) · S5 submit · S6 budget
```

```bash
# planning turn:
SOC_BACKEND=snowflake PYTHONPATH=. python scripts/pilot_v4_probe.py \
    --scenario tier_choice --seat p1 --show-prompts

# orbit turn (no eval scenario ships one, so force it + seed credits):
SOC_BACKEND=snowflake PYTHONPATH=. python scripts/pilot_v4_probe.py \
    --scenario vault_pressure --orbit --show-prompts

# batch metrics (JSON reliability, fallback rate, plan mix, p50/p95 latency):
SOC_BACKEND=snowflake PYTHONPATH=. python scripts/pilot_v4_probe.py \
    --scenario tier_choice --repeat 10
```

Offline structural tests (no network, fast) live in
`orchestrator_2/tests/test_pilot_v4_harness.py` — they exercise parsing,
trim, the pickup invariant, materialization, fallbacks, and `run()` for both
phases with a mock invoker.

## Head-to-head eval (optional)

```bash
SOC_BACKEND=snowflake PYTHONPATH=. \
  SOC_BINDING_P1=harness_in_process:sea_of_colours.orchestrator_2.harnesses.pilot_v4.harness:run:PILOT_V4 \
  SOC_BINDING_P2=harness_in_process:sea_of_colours.orchestrator_2.harnesses.pilot_v3.harness:run:PILOT_V3 \
  python scripts/run_season_v2.py --p1 cortex --p2 cortex --days 7 --season-name V4_VS_V3
```
