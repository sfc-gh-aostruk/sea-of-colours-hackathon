# orchestrator_2 — where agents plug in

This package decides *who* takes a turn and *how* they are called. It
delivers the same world view to every agent and lets each one bring
whatever brain it likes: a Python harness in this repo, a heuristic, or
(in principle) a remote service.

For the hackathon, everything you need is here and in
[`harnesses/tabula_v12/README.md`](harnesses/tabula_v12/README.md).

## Mint your own agent

```bash
python scripts/new_agent.py --team redwatch --name reaper
python run_web.py          # restart; REDWATCH_REAPER is now in NEW GAME
```

That forks V12 — the shipped LLM agent — into
`harnesses/redwatch_reaper/`, renames its identity so its turns are
attributed to you, and registers it. Then open
`harnesses/redwatch_reaper/README.md`: it explains the pipeline and
points at the two deliberate gaps that are the exercise.

Naming is `<team>_<agent>`. A room full of forks all called `reaper`
helps nobody, and the label ends up in the audit trail and on the
scoreboard.

**Fork; don't edit V12 in place.** V12 is the control in your
experiment. Change it directly and you can no longer tell whether your
agent is better than the baseline, because there is no baseline left.

## Registering by hand

The scaffold just automates two edits to `binding_registry.py`. If you
wrote a harness from scratch, do them yourself:

```python
# 1. KNOWN_AGENT_BINDINGS — the binding itself
"SOC_REDWATCH_REAPER": AgentBinding(
    kind="harness_in_process",
    locator="sea_of_colours.orchestrator_2.harnesses.redwatch_reaper.harness:run",
    agent_label="REDWATCH_REAPER",
    menu_label="REDWATCH_REAPER — redwatch's agent",
    needs_llm=True,     # fail loudly at game creation if no PAT
),

# 2. AGENT_LABEL_BINDINGS — makes it selectable
"redwatch_reaper": KNOWN_AGENT_BINDINGS["SOC_REDWATCH_REAPER"],
```

That is the whole registration. The New Game dropdown is built from
`selectable_agents()` and served at `/api/meta/agents`, so your agent
appears without touching the frontend, and the eval CLI accepts your
label as a `--config` without an eval config.

Omit `menu_label` to keep an agent routable but unlisted — useful for a
half-finished fork you don't want opponents picking yet.

## The harness contract

One function. It is called once per turn, for one seat:

```python
def run(*, store, session_id: str, player: str,
        view: Mapping[str, Any]) -> Dict[str, Any]:
    ...
```

| Argument | What it is |
| --- | --- |
| `store` | Storage backend handle; pass it to engine calls |
| `session_id` | The game |
| `player` | Your seat — `"p1"`, `"p2"`, … |
| `view` | The turn brief. `view["agent_view"]` is the fog-limited board |

**You must call `soc_engine.submit_policy(store, session_id, player,
moves)` yourself.** Returning moves is not enough; the orchestrator
checks that a policy landed and substitutes a heuristic fallback if one
didn't.

Return an audit envelope. Everything is optional except that the shape
is a dict:

```python
{
  "ok": True,
  "agent_id": "REDWATCH_REAPER",
  "rationale": "one-line summary shown in the game log",
  "submitted_policy": True,
  "moves": [...],
  "ms_elapsed": 8321,
  "extras": {"prompt_excerpt": "..."},   # captured into the audit trail
}
```

Both phases come through the same function — check `view["phase"]` and
branch, as V12 does in `harness.py`.

### What you get in `view`

`view["agent_view"]` is the fog-limited board: `meta` (rules and caps),
`hud` (scores, vault), `world` (the grid, `null` where fogged),
`my_assets`, `navigation`, `last_night`, `competitor_intel`.

Read caps and radii from `meta.rules` rather than hardcoding them —
retunes happen, and an agent with a stale constant plays a game nobody
else is playing.

`envelope.py` can render this as a text brief
(`build_universal_envelope`) if you want a prompt-shaped version. It is
deliberately agent-agnostic and takes no agent name: every agent sees
the same board.

## Debugging a turn

| Want | Where |
| --- | --- |
| What the model saw and did | Set `SOC_CARD_DUMP_DIR=/tmp/cards`, read `/tmp/cards/dNN_pN.txt` |
| Per-turn audit rows | `SOC_AGENT_INVOCATION` (rationale, prompt excerpt, timings) |
| One-line summary per turn | The in-game log panel |
| Scenario regressions | The eval CLI, below |

## Evals

```bash
# Heuristic baseline — no credentials:
PYTHONPATH=. python -m sea_of_colours.orchestrator_2.evals.cli \
    --config grid_v1 --runtime heuristic --backend memory

# V12, the agent to beat:
PYTHONPATH=. python -m sea_of_colours.orchestrator_2.evals.cli \
    --config tabula_v12 --runtime cortex --backend memory

# Your fork, by its registered label:
PYTHONPATH=. python -m sea_of_colours.orchestrator_2.evals.cli \
    --config redwatch_reaper --runtime cortex --backend memory
```

## File map

```
orchestrator_2/
├── runtime.py            public run_agent_turn + heuristic safety net
├── dispatcher.py         switch over binding.kind; imports harnesses
├── binding_registry.py   labels → AgentBinding. Register here.
├── envelope.py           universal STATE brief (agent-agnostic)
├── cortex_chat.py        Cortex inference over REST with a PAT
├── cortex_invoker.py     shared SSE/PAT transport + per-agent caps
├── audit.py              writes SOC_AGENT_INVOCATION
├── harnesses/
│   └── tabula_v12/       V12 — the agent you fork. Read its README.
├── snowflake/            SOC_AGENT_BINDING + SOC_AGENT_MEMORY schema
├── evals/                scenario suite wrapper
└── tests/
```

## Binding kinds

| Kind | Locator | Status |
| --- | --- | --- |
| `harness_in_process` | `module.path:callable` | The one you want |
| `heuristic` | `RED_HARVEST` / `RED_HARVEST_LITE` | Built-in bots |
| `human` | `HUMAN` | Not a dispatch target; in the roster so the menu is one list |
| `cortex_agent` | Snowflake agent object name | Legacy; no agent objects ship any more |
| `harness_proc` / `harness_spcs` | proc id / HTTPS URL | Stubs, raise `NotImplementedError` |

## Resolution order

1. Seat label from the New Game menu (`AGENT_LABEL_BINDINGS`) — the
   normal path.
2. `SOC_BINDING_<PLAYER>` env var, e.g.
   `SOC_BINDING_P2=harness_in_process:my.harness:run#MYAGENT`. The label
   suffix uses `#` because harness locators already contain a colon.
3. `SOC_CORTEX_AGENT` + `KNOWN_AGENT_BINDINGS`.
4. `SOC_AGENT_RUNTIME=heuristic`.
5. Default: heuristic.

Anything unrecognised resolves to the heuristic rather than erroring, so
a typo'd label produces a bot that plays rather than a crash — check the
game log if your agent seems to have been replaced by RED_HARVEST.

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for why it is built this way.
