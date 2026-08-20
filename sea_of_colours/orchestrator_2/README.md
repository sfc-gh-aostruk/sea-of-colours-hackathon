# orchestrator_2

A parallel orchestrator for Sea of Colours that delivers a **universal
world view** to every agent and lets each agent bring whatever harness
it wants. PILOT_V2 lives here as the proof-of-concept.

**The production orchestrator** still lives at
`sea_of_colours/agent/runtime.py` and serves PILOT (v1), GRID_FAST,
SOC_RED_REAPER, LIST_V2, and the heuristic. Nothing in this folder
touches that path; you opt in to orchestrator_2 by importing
`sea_of_colours.orchestrator_2.runtime.run_agent_turn` instead of the
legacy one.

## Quickstart

Run PILOT_V2 against a single eval scenario:

```bash
PYTHONPATH=. SOC_BACKEND=snowflake \
  SOC_AGENT_RUNTIME=cortex \
  SOC_AGENT_WORLD_VIEW=grid \
  SOC_CORTEX_AGENT=SOC_RED_REAPER_PILOT_V2 \
  python -m sea_of_colours.orchestrator_2.evals.run --scenario solo_drop_orbit
```

Run a full season with PILOT_V2 vs heuristic:

```bash
PYTHONPATH=. SOC_BACKEND=snowflake \
  SOC_CORTEX_AGENT=SOC_RED_REAPER_PILOT_V2 \
  python -m sea_of_colours.orchestrator_2.evals.run_season --p1 cortex --p2 heuristic
```

See `ARCHITECTURE.md` for the design, `MIGRATION.md` for how to port
an agent over, and `harnesses/pilot_v2/README.md` for PILOT_V2-specific
debug notes.

## File map

```
orchestrator_2/
├── runtime.py            ← public run_agent_turn (thin)
├── dispatcher.py         ← 4-way switch over binding.kind
├── binding_registry.py   ← session+player → AgentBinding
├── envelope.py           ← universal STATE envelope builder (agent-agnostic)
├── cortex_invoker.py     ← thin subclass of the legacy invoker; PILOT_V2 caps
├── audit.py              ← writes SOC_AGENT_INVOCATION
├── harnesses/
│   └── pilot_v2/         ← PILOT_V2's standalone brain (self-contained)
│       ├── harness.py
│       ├── candidates.py
│       └── memory.py
├── snowflake/
│   ├── orchestrator_v2_schema.sql     ← SOC_AGENT_BINDING + SOC_AGENT_MEMORY
│   └── soc_create_agent_pilot_v2.sql  ← Cortex agent spec
├── evals/                ← thin wrapper around the v1 evals package
└── tests/
```

## Status

| Phase | Status |
|---|---|
| Revert v1 orchestrator | done |
| Scaffold orchestrator_2 | done |
| Build dispatcher / registry / runtime | done |
| Port PILOT_V2 (in-process) | done |
| Snowflake schema authored (NOT deployed) | done |
| Tests | in progress |
| Evals port | in progress |
| Snowflake-hosted PILOT_V2 (stored procedure) | deferred |
| SPCS-hosted harness | deferred |
| Port PILOT v1 / GRID_FAST / etc. | deferred (stay in v1) |
