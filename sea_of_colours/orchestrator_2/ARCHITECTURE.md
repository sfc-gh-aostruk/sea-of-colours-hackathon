# orchestrator_2 — Architecture

## Why a parallel orchestrator?

The legacy orchestrator (`sea_of_colours/agent/runtime.py`) couples
agent-specific preprocessing (candidate compilation, threat brief,
season memory) into the prompt builder. That coupling has worked but
makes it hard to:

1. Guarantee every agent receives the SAME world view (fairness in a
   competitive tournament).
2. Treat agents as independent submissions — i.e. let anyone deploy a
   harness without touching the orchestrator.
3. Host harnesses outside the orchestrator process (Snowflake stored
   procedure, SPCS container, etc.).

orchestrator_2 splits the responsibilities cleanly:

* The **orchestrator** owns world-state loading, the universal STATE
  envelope, dispatch routing, policy-queue reconciliation, audit, and
  the heuristic fallback.
* Each **agent harness** owns its own preprocessing, its own prompt
  shape, its own Cortex Agent invocation, and its own quirks.

## The dispatch contract

```
┌─────────────────────────────────────────────────────────────────┐
│  ORCHESTRATOR (orchestrator_2.runtime.run_agent_turn)            │
│                                                                  │
│  1. view = soc_engine.get_view(store, session_id, player)       │
│  2. binding = binding_registry.resolve_binding(...)             │
│  3. result = dispatcher.dispatch_turn(binding, view, ...)       │
│  4. reconcile against SOC_POLICY_QUEUE                          │
│  5. if not submitted → heuristic fallback                       │
│  6. audit.write_invocation(...)                                 │
│  7. return envelope dict                                        │
└────────────────────────────┬────────────────────────────────────┘
                             │
                  ┌──────────┴──────────┐
                  │  Resolved binding   │
                  └──────────┬──────────┘
        ┌────────────────────┼─────────────────────────┐
        ▼                    ▼                         ▼
  kind=cortex_agent    kind=harness_in_process    kind=heuristic
  POST agents/X:run    import X:Y; call X:Y(view) plan_moves(view)
                                                  submit_policy()
                  ┌──────────┐
                  │ FUTURE   │
                  │ kinds    │
                  └──────────┘
        kind=harness_proc   kind=harness_spcs
        CALL <proc>(...)    POST <spcs_url>
        (NotImplemented)    (NotImplemented)
```

## Binding kinds

| Kind | Locator format | Use case |
|---|---|---|
| `cortex_agent` | Snowflake agent name (`SOC_FOO`) | Bare Cortex Agent that reads the universal envelope and calls `soc_submit_policy` |
| `harness_in_process` | `<module_path>:<callable>` | Python harness in this repo with custom preprocessing |
| `harness_proc` | Snowflake procedure identifier | (deferred) Stored-procedure-hosted harness |
| `harness_spcs` | HTTPS URL | (deferred) SPCS container-hosted harness |
| `heuristic` | `RED_HARVEST` | In-process RED_HARVEST policy |

## Binding resolution order

The registry checks, in order:

1. **`SOC_BINDING_<PLAYER>` env var** — explicit override, format
   `kind:locator[:label]`. Used by eval CLIs.
2. **`SOC_CORTEX_AGENT` env var + `KNOWN_AGENT_BINDINGS` map** — lets
   legacy callers keep setting `SOC_CORTEX_AGENT` and the registry
   maps the name to the right binding kind. Today maps PILOT_V2.
3. **`runtime_override="cortex"` + unknown agent name** — falls back to
   `kind=cortex_agent` so callers can talk to any deployed Cortex
   agent without registering it.
4. **`SOC_AGENT_RUNTIME=heuristic` (or unset)** — `kind=heuristic`.
5. **Default** — `kind=heuristic`.

The `SOC_AGENT_BINDING` Snowflake table (Phase 5 schema) is a future
deliverable; today the env-var path covers all use cases.

## What's "universal" vs what's per-agent

| Concern | Universal (orchestrator) | Per-agent (harness) |
|---|---|---|
| World-state loading | yes | no |
| STATE envelope (meta/hud/world/navigation/my_assets/last_night/competitor_intel) | yes | no |
| Move grammar | yes | no |
| Policy-queue reconciliation | yes | no |
| Heuristic fallback on miss | yes | no |
| Audit row write | yes | no |
| Candidate compilation | NO | yes (PILOT_V2 only) |
| Threat brief | NO | yes (PILOT_V2 only) |
| Season memory | NO | yes (PILOT_V2 only) |
| Custom prompt format | NO | yes |
| Inner Cortex Agent invocation | NO | yes |
| Wall-clock cap | mechanism yes, value per-agent | value yes |

## Fairness contract

The orchestrator MUST NOT inject agent-specific keys into the universal
envelope. Two automated tests pin this:

* `tests/test_envelope.py` asserts the envelope shape is identical for
  any caller (no `agent_name` parameter).
* `tests/test_dispatcher.py::test_universal_envelope_identical_across_bindings`
  builds envelopes for `cortex_agent` and `heuristic` and asserts they
  are byte-equal.

If you find yourself wanting to add an `agent_name` argument to
`envelope.build_universal_envelope`, you almost certainly want to move
that logic into the agent's harness module instead.

## Compatibility with the legacy orchestrator

* `sea_of_colours.agent.runtime.run_agent_turn` is unchanged and serves
  PILOT v1, GRID_FAST, SOC_RED_REAPER, LIST_V2, heuristic. Switching a
  caller to orchestrator_2 is one import change.
* `sea_of_colours.evals.*` continue to use the v1 runtime. The
  `orchestrator_2/evals/` wrapper re-uses scenarios/builders/assertions
  but swaps the agent-turn callable.
* The audit table `SOC_AGENT_INVOCATION` is shared; orchestrator_2
  writes the same column shape (`runtime` column carries the binding
  `kind` for orchestrator_2 turns so postmortems can tell the two
  apart).
