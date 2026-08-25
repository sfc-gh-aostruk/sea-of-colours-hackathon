# AGENTS.md — Sea of Colours

Turn-based, fog-of-war strategy game ("Sea of Colours") with a pure-Python
engine, a Snowflake-backed persistence/agent layer, and a vanilla-JS web UI.
This file is always-on context for AI agents; keep it lean and current.

## Source-of-truth docs (read before non-trivial work)

- `RULEBOOK.md` — **canonical** game rules + changelog. Section refs like `§3.14`
  are used throughout the code/comments. If behaviour and RULEBOOK disagree, the
  RULEBOOK wins (or the RULEBOOK needs updating — flag it).
- `docs/OUTSTANDING_ISSUES.md` — the running bug/triage log. Update the relevant
  entry (and the triage table) when you fix something; mark it `✅ (DONE, vX.Y)`
  with root cause + fix.
- `README.md` — CLI map generator + web/Snowflake setup and flags.
- `guide/index.html` — the attendee-facing install guide + tutorial
 (self-contained HTML, sibling to `manual/`, deep-links into it via
 `#tab=<name>`). It quotes concrete commands, expected output and the
 pytest baseline, so **it's a fan-out surface**: if you change install
 steps, env vars, agent names or the new-game modal, reconcile it.
- `manual/agent.html` — the agent & harness guide: one real V12 turn
 taken apart (percept → prompt → reply → sanitiser → engine). Its data
 is **generated**, not hand-written — regenerate via
 `scripts/export_agent_guide_data.py` rather than editing
 `manual/agent-data.js`. It cites harness module paths, so a rename in
 `harnesses/tabula_v12/` fans out here.
- `docs/SNOWFLAKE_SETUP.md` — BYO-Snowflake-trial-account walkthrough
  (PAT for the V12 agent; optional schema deploy for persistent
  sessions). Playing/testing against `RED_HARVEST` / `RED_HARVEST_LITE`
  needs none of this — `SOC_BACKEND=memory` is fully offline.
- `docs/HACKATHON_BUILD_PLAN.md` — **read this first if you're picking
  up work on this repo.** This repo is mid-port from a larger dev repo
  into a hackathon-ready distribution; this doc tracks phase status,
  what's already decided, and a concrete inventory for the next
  pending phase. Update its status table as phases complete.

## Run & test

```bash
pip install -r requirements.txt
python run_web.py        # FastAPI UI on http://127.0.0.1:8000 (reload on)
pytest                   # tests/ (pythonpath=. via pytest.ini)
```

- **Backend selection:** unset = **auto-detect**
  (`sea_of_colours/snowpark/backend.py`) — `snowflake` only when the
  Snowpark extras *and* key-pair `sf_config` are both present, else
  `memory`. `SOC_BACKEND` overrides, and an explicit value is strict
  (the server exits rather than falling back). **Auto never resolves to
  a live backend under pytest** — detection keys off a config file most
  dev machines have, and `init_session` wipes the target schema, so
  that guard is what stops a test run writing to your account. Tests
  that need a specific store set `SOC_BACKEND` themselves.
- A dev server is usually already running (see the terminals folder). Check
  before starting another.

## Architecture

```
sea_of_colours/
  game/          Pure-Python engine — session.py (state/ledgers), simulator.py (night sim)
  snowpark/      Storage-agnostic engine wrappers (engine.py) + backend.py + stores
  agent/         RED_HARVEST heuristic + Cortex AI agent runtime/invoker
  evals/         Scenario/eval harness
  orchestrator_2/  Newer agent orchestration (pilot_v2 harness) — migration in progress
    harnesses/tabula_v12/  current Red-Reaper agent — see its README.md, and
                           ENGINE_INTERFACE.md for the engine boundary it must obey
server/
  app.py         FastAPI thin proxy (/, /api/game/*); static mounted no-cache
  static/        Web UI — app.js, styles.css, station.js, index.html
scripts/         deploy_soc_schema.py, run_season*.py, run_evals.py, run_battery.py
snowflake/       SOC_* schema, views, procedures, agent SQL
```

Server flow: `server/app.py` → `sea_of_colours/snowpark/engine.py` → `game/*`.
The same `engine.py` backs the Snowpark stored procedures.

## Frontend conventions (`server/static/`)

- **No build step.** `index.html` loads `app.js` / `station.js` via `<script>`.
- Static is served `Cache-Control: no-cache` **from disk** (`_NoCacheStatic` in
  `server/app.py`), so JS/CSS edits need **only a browser hard-refresh
  (Cmd-Shift-R) — no server restart.**
- After editing `app.js`, run `node --check server/static/app.js` and clear
  lints (`ReadLints`). It's one large IIFE — prefer `StrReplace` with ample
  context.
- `station.js` loads **after** `app.js` and wires `window.osOn*` hooks; keep that
  order.
- Replay/live cinematic renders the **resolved end-state frame first**, then
  animates deltas over it (`paintReplayFrameOntoMain` → `runReplayAnimationsTick`
  → `runSingleDeltaAnimation`). To avoid the board "moving" before a sprite
  lands, defer effects with terrain stand-ins / reveal masks lifted at the
  landing beat (see the `step`/`drop`/`probe` branches and `_layTerrainStandin`).

## Keeping rules ⇄ engine ⇄ agents ⇄ UI in sync (READ THIS)

The same rule/number lives in many surfaces. When you change a mechanic, a
constant, or a formula, treat it as a **fan-out edit** — updating only the engine
silently leaves agents and players reading stale rules (this has bitten us:
vault `25→15` and probe radius `2→4` drifted for months in prompts + UI while the
engine was already correct). **A change is not "done" until every surface below
is reconciled.**

**Order of truth:** engine constant → `RULEBOOK.md` → everything that describes
or mirrors it.

Checklist for any rule/constant/formula change:

1. **Engine (source of truth).** Change the single canonical definition — a
   constant at the top of `game/session.py` (capacities, costs, multipliers),
   `game/weapons.py` (EMP/mine/chaff dials), `game/tuning.py` (env-tunable vision
   knobs), or `game/policy.py` (slot caps). Never duplicate a literal you could
   import.
2. **RULEBOOK.md.** Update the prose **and** the `Canonical Configuration` table,
   then add a `### vX.Y — YYYY-MM-DD` **changelog** entry at the top and bump the
   header version. **Never edit past changelog entries** (they're history) — add a
   new one. Keep `§` section refs stable; code/comments cite them.
3. **Agent prompts** (agents act on what they're told). All live prompt text
   is now **in Python**, under
   `sea_of_colours/orchestrator_2/harnesses/tabula_v12/` — that's the shipped
   LLM agent, and it builds its prompt in-process each turn.
   - ⚠️ There are no longer any deployed Cortex *agent objects*. The
     `soc_create_agent*.sql` specs and the `runtime=cortex` code path were
     deleted; V12 talks to Cortex **inference** over REST with a PAT, so a
     prompt edit takes effect on the next turn with no redeploy step.
   - `sea_of_colours/agent/runtime.py` is heuristic-only and has no prompt.
   - **Prefer dynamic values:** read `meta.rules` (`drop_mode`, `probe_radius`,
     `probe_lifetime_nights`) and `hud.season_day_cap` from the view instead of
     hardcoding, so future retunes don't require prompt edits.
4. **Agent logic/heuristics that model the mechanic.** `agent/heuristic_agent.py`
   and the `orchestrator_2/harnesses/pilot_v*` compilers must derive coverage /
   caps / costs from the constant or `tuning.py` — never a hardcoded copy
   (e.g. `_fog_yield` reads `probe_vision_radius()`).
4b. **Onboarding surfaces.** `guide/index.html` and `manual/` restate
 rules and numbers in prose an attendee reads *before* touching code —
 the place a stale value does the most damage. Grep both.
5. **Client/UI.** Mirror, don't hard-code, in `server/static/` (`app.js`,
   `index.html`, `styles.css`, `mobile.html`, and the `orbital_exp/` copies):
   check rendered denominators, `title=`/`aria-label=`/placeholder text, and
   scoreboard defaults.
6. **Tests.** Update expectations and add a regression test pinning the new
   value/behaviour (`tests/`).
7. **Trackers.** Update `docs/OUTSTANDING_ISSUES.md` (bug) or
   `docs/RULES_PENDING_REVISION.md` (deliberate rule change) and mark status.
8. **Sweep for stragglers.** After the change, grep the repo for the **old**
   literal (and its prose forms) to catch stale copies — e.g.
   `rg -n "25-slot|0/25|radius 2|13-cell"`. Exclude `reports/` (historical AI
   transcripts) and already-shipped changelog entries.

## House style

- Comments explain **why / trade-offs**, not what. Tag notable changes with the
  version, e.g. `// v1.7 — ...`, matching RULEBOOK bumps.
- Python: `from __future__ import annotations`, type hints, dataclasses for game
  state; capacity/tuning constants live at the top of `game/session.py`
  (e.g. `HOARD_CAPACITY = 15`).
- Keep game constants single-sourced; mirror them (don't hard-code) on the
  client.

## Git

- **Do not commit unless explicitly asked.** When asked, follow the repo's
  concise commit style and never touch git config.
