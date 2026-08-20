# Building a new PILOT version (v3, v4, …) without breaking live play

**Audience:** whoever is iterating on the PILOT agent line.
**Goal:** ship a new version (e.g. `pilot_v3`) that you can eval headless and
eventually offer in the live menu, **without touching the `pilot_v2` that
humans are currently playing against.**

The short version: a PILOT version is **additive**. New harness package +
new binding label + (usually) a new Snowflake agent. You never edit the v2
package or redeploy the v2 Cortex agent. Existing v2 sessions/replays are
immutable — the agent label is baked into each session's `json_state`.

---

## 1. What "pilot_v2" actually is (two independent layers)

1. **Local harness package** —
   `sea_of_colours/orchestrator_2/harnesses/pilot_v2/`
   (`harness.py`, `candidates.py`, `orbit.py`, `combat.py`, `threat_assess.py`,
   `memory.py`). Self-contained: *nothing in the orchestrator imports from
   here* — the orchestrator only knows the harness's **locator string**. This
   is where ~all of your day-to-day iteration happens (candidate scoring,
   threat model, memory, prompt assembly).

2. **Deployed Cortex agent** — `SOC_RED_REAPER_PILOT_V2` in Snowflake, created
   by `sea_of_colours/orchestrator_2/snowflake/soc_create_agent_pilot_v2.sql`.
   This is the LLM spec: system prompt, model (claude-haiku-4-5), tool
   (`soc_submit_policy` / `soc_submit_orbit_actions`), budgets. The harness
   names it via `INNER_CORTEX_AGENT` in `harness.py`.

Per turn: the orchestrator resolves the seat's **binding** → imports the
harness locator → calls `harness.run(...)` → the harness builds a
PILOT-specific prompt and invokes the inner Cortex agent → the agent calls a
submit tool → the orchestrator reconciles the stashed policy.

---

## 2. Every place the name "pilot_v2" / "SOC_RED_REAPER_PILOT_V2" appears

Only five, and only three of them matter for a new version:

| File | Reference | Touch for v3? |
|------|-----------|---------------|
| `orchestrator_2/binding_registry.py` | `KNOWN_AGENT_BINDINGS["SOC_RED_REAPER_PILOT_V2"]` + `AGENT_LABEL_BINDINGS["pilot_v2"]` | **Add v3 entries** (don't edit v2's) |
| `orchestrator_2/harnesses/pilot_v2/harness.py` | `INNER_CORTEX_AGENT = "SOC_RED_REAPER_PILOT_V2"` | Copied into your v3 package |
| `orchestrator_2/cortex_invoker.py` | `WALLCLOCK_CAP_OVERRIDES` / `RESPONSE_CAP_OVERRIDES` keyed by the agent name | **Add a v3 key** |
| `orchestrator_2/snowflake/soc_create_agent_pilot_v2.sql` | the deployed agent | **Copy to a new `_v3.sql`** if the LLM spec changes |
| `server/static/app.js` | new-game menu dropdown lists `"pilot_v2"` | **Add `"pilot_v3"`** when ready to play it live |

---

## 3. Step-by-step: create `pilot_v3`

### 3a. Copy the harness package
```bash
cp -r sea_of_colours/orchestrator_2/harnesses/pilot_v2 \
      sea_of_colours/orchestrator_2/harnesses/pilot_v3
```
Edit freely inside `pilot_v3/`. In `pilot_v3/harness.py`:
- Update the module docstring.
- Set `INNER_CORTEX_AGENT = "SOC_RED_REAPER_PILOT_V3"` **iff** you deploy a new
  Cortex agent (see 3c). If v3 is a *harness-only* change (same LLM spec), you
  may leave it pointing at `SOC_RED_REAPER_PILOT_V2` — but a separate agent is
  cleaner and safer.

### 3b. Register the binding (do NOT edit v2's entries)
In `orchestrator_2/binding_registry.py`:
```python
KNOWN_AGENT_BINDINGS = {
    "SOC_RED_REAPER_PILOT_V2": AgentBinding(...),          # leave as-is
    "SOC_RED_REAPER_PILOT_V3": AgentBinding(
        kind="harness_in_process",
        locator="sea_of_colours.orchestrator_2.harnesses.pilot_v3.harness:run",
        agent_label="PILOT_V3",
    ),
}

AGENT_LABEL_BINDINGS = {
    "pilot_v2": KNOWN_AGENT_BINDINGS["SOC_RED_REAPER_PILOT_V2"],  # leave as-is
    "pilot_v3": KNOWN_AGENT_BINDINGS["SOC_RED_REAPER_PILOT_V3"],
}
```

> ⚠️ **This registration is mandatory before wiring the menu.** A menu seat
> tagged `"pilot_v3"` that is NOT in `AGENT_LABEL_BINDINGS` falls through
> `resolve_binding` and **silently plays the RED_HARVEST heuristic** (label not
> recognised → not a heuristic label → env lookups miss → default heuristic).
> No error is raised. Always eval headless first to confirm the real agent runs.

### 3c. Deploy the Cortex agent (only if the LLM spec changes)
If v3 changes the **system prompt / model / tools**, deploy a NEW object:
```bash
cp sea_of_colours/orchestrator_2/snowflake/soc_create_agent_pilot_v2.sql \
   sea_of_colours/orchestrator_2/snowflake/soc_create_agent_pilot_v3.sql
# edit: rename the agent to SOC_RED_REAPER_PILOT_V3, change the prompt, then run it in Snowflake
```
**Never edit `soc_create_agent_pilot_v2.sql` and redeploy `SOC_RED_REAPER_PILOT_V2`** —
live v2 games call that object every turn.
If v3 only changes harness Python, you can skip this and reuse the v2 agent.

### 3d. Add the per-turn cap
In `orchestrator_2/cortex_invoker.py`:
```python
WALLCLOCK_CAP_OVERRIDES = {
    **_LegacyInvoker.WALLCLOCK_CAP_OVERRIDES,
    "SOC_RED_REAPER_PILOT_V2": 80,
    "SOC_RED_REAPER_PILOT_V3": 80,   # hard per-turn ceiling (seconds)
}
RESPONSE_CAP_OVERRIDES = {
    **_LegacyInvoker.RESPONSE_CAP_OVERRIDES,
    "SOC_RED_REAPER_PILOT_V2": 40_000,
    "SOC_RED_REAPER_PILOT_V3": 40_000,
}
```

### 3e. (When ready) wire the live menu
In `server/static/app.js`, the new-game agent dropdown:
```javascript
for (const [val, label] of [
  ["human", "HUMAN — pilot from this browser"],
  ["red_harvest", "RED_HARVEST — heuristic bot"],
  ["pilot_v2", "PILOT_V2 — Cortex agent (slow · ~1 min/turn)"],
  ["pilot_v3", "PILOT_V3 — Cortex agent (slow · ~1 min/turn)"],
]) {
```
No other frontend change is needed: `app.js` treats **any** label that isn't
`human`/`red_harvest`/`heuristic` as a "slow" agent automatically (same set as
the server's `_HEURISTIC_AGENT_LABELS`), so v3 gets the background pre-fire,
the non-blocking submit, and the "waiting on PILOT_V3 · Ns / ~80s" wait frame
for free.

---

## 4. How the live human-vs-agent runtime drives your agent

The web server (`server/app.py`) treats a game as "slow" when any seat's label
isn't a heuristic (`_game_has_slow_bot`). For those games:

- **Background pre-fire:** a per-game worker (`_kick_bots` → `_drive_bots`)
  starts your agent's turn the moment a phase opens — on game create, on every
  `/status` poll, and after each human submit. So the agent thinks *while the
  human deliberates*.
- **Non-blocking submit:** the human's `POST /policy|/orbit` never hangs on the
  agent. If the agent is mid-turn holding the game lock, the endpoint returns
  `agent_busy` within `_AGENT_SUBMIT_LOCK_WAIT_S` (3s) and the browser retries.
- **The 80s contract:** the invoker aborts a turn at the wallclock cap and the
  orchestrator lands the harness's `candidates.recommended_policy` (the
  doctrine fallback) so a human never waits more than ~cap on one turn.
- **UI timer:** `/status` exposes `bot_turn` (`seat`, `agent`, `elapsed_ms`,
  `cap_ms`) and `waiting_on`. The browser shows a live countdown and an
  "over budget · auto-playing…" state past the cap.

**What this means for you as an agent author:**
- Your `harness.run(...)` should return promptly after the inner agent submits;
  don't add long post-processing — it counts against the human's wait.
- Make `candidates.recommended_policy` **always legal and decent** — it *is*
  your agent's move whenever the LLM misses/timeouts.
- The concurrency model requires the agent turn to hold the game lock; keep the
  turn single-shot (one invoke). Don't spawn background work that writes
  `json_state` outside the turn.
- The UI countdown cap is currently a hardcoded hint (`_AGENT_TURN_CAP_MS =
  80_000` in `app.py`) plus the `cap_ms` the server sends. If v3 uses a
  different real cap, update that constant too so the countdown matches.

---

## 5. Isolation guarantees (what's safe)

- Editing anything under `harnesses/pilot_v3/` cannot affect v2.
- Adding `KNOWN_AGENT_BINDINGS` / `AGENT_LABEL_BINDINGS` / cap entries for v3
  leaves v2's resolution untouched.
- Deploying `SOC_RED_REAPER_PILOT_V3` is a new Snowflake object; v2's agent is
  unchanged.
- Existing sessions/replays store their agent label in `json_state`; v3's
  existence changes nothing about them.

## 6. Shared code — handle with care

These are used by **all** agents; changing them affects v2 too:

- `orchestrator_2/runtime.py`, `dispatcher.py`, `envelope.py`, base
  `agent/cortex_invoker.py` — the turn machinery.
- `snowpark/view.py` + engine — the **view** every agent sees (`world`,
  `last_night`, `combat_events`, `station_intel`, …). Changing the schema
  changes v2's inputs as well (often intended — keep it shared unless you have
  a reason not to).
- **`_heuristic_fallback` in `runtime.py` hardcodes
  `harnesses.pilot_v2.candidates`** for the safety-net move. If you want v3's
  missed-turn fallback to use *v3's* candidate compiler, generalize that
  function (e.g. pick the compiler from the binding) — otherwise a missed v3
  turn falls back on v2 doctrine. Low stakes, but know it.

---

## 7. Dev workflow — eval headless, never on the live server

Iterate with the season runner (Snowflake backend so Cortex is reachable):

```bash
# If v3 is registered in KNOWN_AGENT_BINDINGS:
SOC_BACKEND=snowflake PYTHONPATH=. python scripts/run_season_v2.py \
  --p1 cortex --p2 cortex --cortex-agent SOC_RED_REAPER_PILOT_V3 \
  --days 7 --season-name PILOT_V3_DUEL

# v3 vs v2 head-to-head (per-seat env binding, no menu needed):
SOC_BACKEND=snowflake PYTHONPATH=. \
  SOC_BINDING_P1=harness_in_process:sea_of_colours.orchestrator_2.harnesses.pilot_v3.harness:run:PILOT_V3 \
  SOC_BINDING_P2=harness_in_process:sea_of_colours.orchestrator_2.harnesses.pilot_v2.harness:run:PILOT_V2 \
  python scripts/run_season_v2.py --p1 cortex --p2 cortex --days 7 --season-name V3_VS_V2
```

Review the replay in the watcher (`/watch.html?season=<slug>`), the kill feed
on the season-complete screen, and the per-turn audit
(`SOC_AGENT_INVOCATION` / rationale) to see prompts, tool calls, timings, and
whether it fell back.

> **Don't hand-edit v3 files while a human is playing a live v2 game on the same
> server.** The dev server runs the WatchFiles reloader (watches
> `sea_of_colours/`), so a save bounces the process and drops any in-flight
> agent turn (the retry/cooldown recovers it, but it's disruptive). Do v3 work
> headless, or run it on a **separate port/instance**:
> `SOC_BACKEND=snowflake uvicorn server.app:app --port 8010`.

---

## 8. Ship checklist

- [ ] `harnesses/pilot_v3/` copied; `harness.py` docstring + `INNER_CORTEX_AGENT` updated.
- [ ] `SOC_RED_REAPER_PILOT_V3` deployed in Snowflake (if the LLM spec changed).
- [ ] `KNOWN_AGENT_BINDINGS` + `AGENT_LABEL_BINDINGS["pilot_v3"]` added (v2 untouched).
- [ ] Cap entries added in `cortex_invoker.py`.
- [ ] Headless season runs green; audit shows real submits (not silent heuristic fallback).
- [ ] (Only when ready) `"pilot_v3"` added to the `app.js` menu; UI cap hint updated if cap differs.
- [ ] Smoke test a live human-vs-`pilot_v3` game: agent pre-fires during
      deliberation, submit is non-blocking, night resolves, replay + kill feed populate.
