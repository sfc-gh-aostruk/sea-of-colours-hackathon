# PILOT_V2 harness

Self-contained "brain" for the `SOC_RED_REAPER_PILOT_V2` Cortex Agent.

The orchestrator delivers a universal STATE envelope to this harness;
the harness preprocesses, augments the prompt, calls the inner agent,
and returns an audit envelope. The orchestrator never imports anything
from this folder.

## Module layout

| File | Purpose |
|---|---|
| `harness.py` | Entry point. Builds the PILOT_V2 prompt and calls `SOC_RED_REAPER_PILOT_V2`. |
| `candidates.py` | Compiles the top-K candidate menu (harvest chains, probes, supersedes, harvester crushes, hot-drop pairs) + the threat brief + the memory summary. |
| `memory.py` | Process-local season memory — tracks every cell ever lit by a known enemy probe disk so the candidate compiler can flag chains that have been telegraphed. |

## Prompt shape

PILOT_V2 receives the orchestrator's universal envelope **plus**:

1. A "Default play" line in the envelope head:
   > Default play: copy `candidates.recommended_policy.moves` into
   > p_policy as a JSON STRING. Override only when `threat` says so.
2. Three extra keys spliced into the STATE JSON block:
   * `candidates` — pre-validated menu of legal scored moves.
   * `threat` — proximity, hoard pressure, publicity risk, my-fleet
     status, enemy-fleet estimate, final-day flag.
   * `memory_summary` — what the enemy has historically seen.

The agent's spec teaches it to read those keys and either copy
`recommended_policy.moves` verbatim or pick a different candidate ID.

## Cortex agent spec

Source-of-truth SQL: `orchestrator_2/snowflake/soc_create_agent_pilot_v2.sql`.

Key parameters:

* Model: `claude-haiku-4-5`
* Budget: 30s spec budget / 12k tokens
* Wall-clock cap: 35s (set in `orchestrator_2/cortex_invoker.py`)
* Tool surface: single tool, `soc_submit_policy`

## Expected timings

Based on prior session-2 measurements (legacy orchestrator, identical
agent + identical candidate compiler):

| Phase | Time |
|---|---|
| `compile_candidates` | <50ms (process-local, no I/O) |
| Prompt assembly | <5ms |
| Cortex Agent invocation (SSE round-trip) | 25–32s typical |
| Total per turn | 28–35s |

If a turn approaches 35s, `wallclock_capped=True` in the result and
the orchestrator's heuristic fallback fires. The 30s spec budget +
5s commit buffer is the safety margin.

## Debug pointers

* **Empty candidates menu** (`candidates.recommended_policy.moves == []`):
  the compiler ran but found nothing legal. Usually means full-fog
  Day 1 with no harvesters to position. The agent should fall through
  to its spec's "no menu" branch and either probe blindly or no-op.

* **`tool_errors` non-empty**: the inner agent called
  `soc_submit_policy` but the procedure rejected the queue (illegal
  moves, malformed JSON). Inspect the procedure's response.

* **Doubt markers in `response` text** (`"wait"`, `"actually"`,
  `"let me parse this turn brief carefully"`): the agent isn't
  trusting the compiler. Two fixes that helped historically:
  (a) tighten the spec's "do not re-verify recommended_policy" clause;
  (b) ensure `threat.my_fleet.probes_deployed` is reconciled with
  `entities.mine` (probes can exist in the grid but not in the
  `my_assets` asset records, which trips a confusion spiral).

* **Wall-clock cap triggered**: spec budget too tight, or claude-haiku-4-5
  decided to deliberate. Either bump `seconds` in the spec OR drop the
  candidate menu size (top-K → top-3).
