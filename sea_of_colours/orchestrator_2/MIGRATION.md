# MIGRATION — porting an agent from the legacy orchestrator

The legacy orchestrator (`sea_of_colours/agent/runtime.py`) and
orchestrator_2 are designed to coexist. You can run agents on either,
and you can port one agent at a time.

This doc walks through the three port patterns by example.

## Pattern A — Bare Cortex Agent (no preprocessing)

You have a Cortex Agent that just reads the universal STATE JSON and
calls `soc_submit_policy`. Nothing fancy.

**Port steps:**

1. Confirm the agent's spec uses the same envelope contract as the
   legacy orchestrator's slim builder (it does, for any agent
   currently in `RULES_IN_SPEC_AGENTS`).
2. Decide how callers select your agent. Two options:
   * **Env-var path (zero code changes):** callers set
     `SOC_CORTEX_AGENT=<your_agent>` and pass
     `runtime_override="cortex"` to `run_agent_turn`. The dispatcher
     resolves a `cortex_agent` binding automatically.
   * **Known-map path:** add an entry to
     `binding_registry.KNOWN_AGENT_BINDINGS` so the dispatcher can
     resolve your agent even without `runtime_override="cortex"`.
3. (Optional) Add per-agent wallclock cap to
   `cortex_invoker.WALLCLOCK_CAP_OVERRIDES`.
4. Done. The dispatcher's `cortex_agent` arm handles everything.

## Pattern B — Harnessed agent (Python preprocessing in-repo)

Your agent benefits from Python-side preprocessing (candidate
compilation, threat analysis, multi-agent ensemble, deterministic
guardrails, etc.). PILOT_V2 is the reference implementation.

**Port steps:**

1. Create `orchestrator_2/harnesses/<your_agent>/`:
   ```
   harnesses/<your_agent>/
   ├── __init__.py    (re-export `run`)
   ├── harness.py     (the entry point)
   └── <internals>/   (your preprocessing modules)
   ```
2. Implement `harness.run(*, store, session_id, player, view) -> Dict`:
   ```python
   def run(*, store, session_id, player, view):
       # 1. Preprocess `view` however you like.
       # 2. Build your prompt (or skip the LLM entirely).
       # 3. Call your inner Cortex Agent via:
       from sea_of_colours.orchestrator_2.cortex_invoker import CortexAgentInvoker
       inv = CortexAgentInvoker(agent_name="YOUR_INNER_AGENT")
       result = inv.invoke(prompt)
       # 4. The agent's tool call wrote SOC_POLICY_QUEUE warehouse-side.
       # 5. Return audit envelope (see DispatchResult fields).
       return {
           "ok": result["ok"],
           "elapsed_ms": result["elapsed_ms"],
           "submitted_policy": result["submitted_policy"],
           "tool_calls": result["tool_calls"],
           "response": result["response"],
           "wallclock_capped": result.get("wallclock_capped", False),
           "rationale": result["response"][:2000],
           "extras": {...},
       }
   ```
3. Register the binding in
   `binding_registry.KNOWN_AGENT_BINDINGS`:
   ```python
   "YOUR_INNER_AGENT": AgentBinding(
       kind="harness_in_process",
       locator="sea_of_colours.orchestrator_2.harnesses.your_agent.harness:run",
       agent_label="YOUR_AGENT_LABEL",
   ),
   ```
4. (Optional) Add per-agent caps to
   `cortex_invoker.WALLCLOCK_CAP_OVERRIDES` and
   `RESPONSE_CAP_OVERRIDES`.
5. Write tests in `orchestrator_2/tests/test_<your_agent>_harness.py`.

## Pattern C — Snowflake-hosted harness (deferred)

For competitive deployments where contributors should NOT need local
code, hosting the harness as a Snowflake stored procedure (or SPCS
container) is the long-term path. The dispatcher reserves the
`harness_proc` and `harness_spcs` kinds for this.

This is **not yet implemented**. When it lands, the port steps will be:

1. Write a Python stored procedure that accepts `(p_session_id,
   p_player, p_state_json)`, preprocesses, invokes the inner Cortex
   Agent (via external access integration), and writes
   `SOC_POLICY_QUEUE` directly.
2. Deploy it to Snowflake.
3. Register a binding:
   ```sql
   INSERT INTO SOC_AGENT_BINDING (session_id, player, kind, locator, agent_label, notes)
   VALUES ('*', 'p1', 'harness_proc',
           'SOC_HACKATHON_DB.SEA_OF_COLOURS.SOC_FOO_HARNESS_RUN',
           'FOO', 'comp registration');
   ```
4. Run the orchestrator. The dispatcher will route by procedure call.

See `ARCHITECTURE.md` for the dispatcher's stub of these kinds.

## Worked example: PILOT_V2

PILOT_V2 follows Pattern B. The full port is:

* `harnesses/pilot_v2/candidates.py` — preprocessing (top-K menu).
* `harnesses/pilot_v2/memory.py` — season-scoped enemy vision history.
* `harnesses/pilot_v2/harness.py` — wraps the inner Cortex Agent
  `SOC_RED_REAPER_PILOT_V2`, injects candidates/threat/memory_summary
  into the universal envelope's STATE block, and appends the
  PILOT_V2-specific "default-play" hint.
* `binding_registry.KNOWN_AGENT_BINDINGS["SOC_RED_REAPER_PILOT_V2"]`
  registers the binding.
* `cortex_invoker.WALLCLOCK_CAP_OVERRIDES["SOC_RED_REAPER_PILOT_V2"] = 35`
  for the sub-60s wall-clock cap.

Total new code: ~150 lines of harness logic + 1620 lines of
preprocessing (candidates+memory, mostly inherited from the original
PILOT_V2 implementation).
