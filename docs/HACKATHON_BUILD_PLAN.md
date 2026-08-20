# Hackathon repo build plan

This repo (`sea-of-colours-hackathon`) is a from-scratch port of the
`sea_of_colours` dev repo, purpose-built as a hackathon distribution:
clone it, play a game, then build your own agent to compete. This doc
is the working plan for finishing that port — read this **before**
picking up any of the pending phases below. It is the single
source-of-truth for "what's done, what's left, what a phase means."

Original dev repo (for reference / diffing, not part of this repo):
`/Users/lgalan/Desktop/sea_of_colours` on the machine this was ported
from. That repo remains the primary/working copy; this one is the
distribution artifact for hackathon attendees only.

## Status

| Phase | What | Status |
| --- | --- | --- |
| 0 | Revert the RED_HARVEST_LITE experiment from the original dev repo (unrelated pre-existing WIP untouched); confirm green baseline | ✅ done |
| 1 | Port to this clean repo; BYO-Snowflake docs; re-apply RED_HARVEST_LITE fresh | ✅ done |
| 2 | Trim the agent roster to exactly `RED_HARVEST` / `RED_HARVEST_LITE` / `V11` | ⏳ next — inventory below |
| 3 | Easy install & first-run verification pass | pending |
| 4 | Simplify the Orbital phase | pending — **detail TBD, needs a scoping conversation with the user before any implementation** |
| 5 | Finish/polish the interactive manual (`manual/`) | pending |
| 6 | Hackathon Guide (tab-shell onboarding, sibling to `manual/`) | pending |
| 7 | In-game read-only agent advisor (invoke V11/RED_HARVEST mid-turn from the UI) | pending |
| 8 | Drift-testing alarms + PR-based submission workflow doc | pending |

Sequencing: 1→2→3 is the critical path. 4 is intentionally unscheduled
— stop and ask the user to scope it before touching any code. 5-8 build
on top of the Phase 1 repo and can be reordered relative to each other.

## What Phase 0/1 actually did (context, not TODOs)

- Reverted a same-session experiment from the original dev repo (6
  files: `sea_of_colours/agent/heuristic_agent.py`,
  `sea_of_colours/agent/runtime.py`,
  `sea_of_colours/orchestrator_2/binding_registry.py`,
  `sea_of_colours/orchestrator_2/dispatcher.py`,
  `sea_of_colours/orchestrator_2/runtime.py`, `scripts/run_season.py`,
  `tests/test_agent.py`) back to the dev repo's own baseline —
  confirmed via `git stash` that the one remaining test failure
  (`tests/test_eval_scenarios.py::test_heuristic_passes_known_scenarios[two_seams_choose_one]`)
  is pre-existing on a clean `HEAD`, unrelated to anything done here.
- Copied a trimmed snapshot of the dev repo here via `rsync`
  (respecting current uncommitted WIP on `manual/manual.css`,
  `manual/manual.js`, and the `tabula_v11/` harness — those were
  carried over as-is, not just the last commit), excluding:
  `reports/`, `card*.txt`, `prompt_dump.txt`, `seasons*`,
  `_tmp_seasons_dbg/`, `audit_html/`, `batch_snowpark/`, `soc_eras/`,
  `build/`, `tmp_hallucination_audit.py`.
- Re-applied the `RED_HARVEST_LITE` variant fresh, directly in this
  repo: a `weapons_enabled: bool` flag threaded through
  `plan_orbit_actions()` / `plan_moves()` / `HeuristicAgent` in
  `sea_of_colours/agent/heuristic_agent.py`, wired through both the
  legacy `agent/runtime.py` (`runtime_override="red_harvest_lite"`)
  and `orchestrator_2`'s `binding_registry.py` /
  `dispatcher.py` / `runtime.py` (`HEURISTIC_LITE_BINDING`, locator
  `"RED_HARVEST_LITE"`), plus a `--p1/--p2/--p3/--p4 red_harvest_lite`
  CLI choice in `scripts/run_season.py`. 3 regression tests added to
  `tests/test_agent.py`.
- Found + fixed a real gap on a from-scratch install: `requirements.txt`
  was missing `httpx` (needed by `fastapi.testclient`) and `requests`
  (needed by `cortex_chat.py` / `cortex_invoker.py`). Both added.
- Added `requirements-snowflake.txt` (optional `snowflake-snowpark-python`,
  only needed for `scripts/deploy_soc_schema.py` / `SOC_BACKEND=snowflake`
  — NOT needed for V11, which talks to Cortex over plain REST + a PAT).
- Added `docs/SNOWFLAKE_SETUP.md` — from-scratch BYO-trial-account
  walkthrough, split into "PAT only, for V11" vs. "optional persistent
  sessions." Fixed a stale claim in `README.md` (said default backend
  was `memory`; code default is `snowflake` — `SOC_BACKEND=memory` is
  the opt-in offline path).
- Verified end to end: fresh venv + `pip install -r requirements.txt`
  → `SOC_BACKEND=memory pytest` → 539 passed, 1 pre-existing unrelated
  failure, 4 skipped → `uvicorn server.app:app` boots and serves the
  game homepage.
- Initial commit made (`git log --oneline` → "Initial commit: Sea of
  Colours hackathon repo"). Local-only — no remote configured, nothing
  pushed anywhere.

## Phase 2 — Reduce the agent roster to exactly three

**Goal:** only `RED_HARVEST`, `RED_HARVEST_LITE`, and `V11` should exist
as agents a participant can select or read about. Everything else is
pre-hackathon R&D debris that will only confuse someone trying to
understand "how do I build an agent."

**Keep:**
- `RED_HARVEST` — `sea_of_colours/agent/heuristic_agent.py`, weapons on.
- `RED_HARVEST_LITE` — same file, `weapons_enabled=False` (done in Phase 1).
- `V11` — `sea_of_colours/orchestrator_2/harnesses/tabula_v11/`, the
  only LLM harness. Binding: `KNOWN_AGENT_BINDINGS["SOC_RED_REAPER_TABULA_V11"]`
  in `binding_registry.py`, `kind="harness_in_process"`, calls out via
  `orchestrator_2/cortex_chat.py` (`CortexChatInvoker`, the inference
  chat/completions API — not the older Agents API).

**Remove — harness directories** (`sea_of_colours/orchestrator_2/harnesses/`):
```
pilot_v2/  pilot_v3/  pilot_v4/
tabula/    tabula_v2/ tabula_v3/ tabula_v4/ tabula_v5/ tabula_v6/
tabula_v7/ tabula_v8/ tabula_v9/ tabula_v10/
tabula_v11_PLAN.md   tabula_v12_PLAN.md   CHANGES_TABULA_v6_v7.md
```
(`tabula_v12_PLAN.md` is speculative planning for a *future* agent, not
a retired one — user call on whether to keep it or fold it into
`PILOT_VERSIONING_GUIDE.md`'s "minting a new agent" section instead of
deleting outright.)

**Remove — `binding_registry.py`:**
- `KNOWN_AGENT_BINDINGS` entries: `SOC_RED_REAPER_PILOT_V2`,
  `_PILOT_V3`, `_PILOT_V4`, `_TABULA`, `_TABULA_V2` .. `_TABULA_V10`
  (keep only `_TABULA_V11`).
- `AGENT_LABEL_BINDINGS` entries: `pilot_v2`, `pilot_v3`, `pilot_v4`,
  `pilot_v6_arena`, `tabula`, `tabula_v2` .. `tabula_v10` (keep
  `tabula_v11`, `red_harvest_lite`).

**Remove/trim — `sea_of_colours/agent/runtime.py`:**
- `AI_AGENTS` dict currently has 3 entries: `SOC_RED_REAPER` (base
  Cortex Agents-API agent), `SOC_RED_REAPER_GRID_FAST` (referenced by
  `.env.canonical`'s `SOC_CORTEX_AGENT=` default — **fix that file
  too** once this entry is gone), `SOC_RED_REAPER_PILOT` (rules-in-spec
  variant). None of these are `V11` (V11 doesn't go through this dict
  at all — it's `orchestrator_2`-only). Decide with the user whether
  to drop `AI_AGENTS` + the whole legacy Cortex-Agents-API path
  (`cortex_invoker.py`, `SOC_AGENT_RUNTIME=cortex`) entirely, since
  V11 supersedes it, or keep `SOC_RED_REAPER` as a documented
  legacy/back-compat option. Whichever way: no dangling references to
  `GRID_FAST` or `PILOT` should remain if removed.

**Remove — SQL agent specs** (safe to delete once the bindings above
are gone; nothing will reference them):
- `snowflake/soc_create_agent_grid.sql`, `_grid_fast.sql`, `_grid_v2.sql`,
  `_list.sql`, `_list_v2.sql`, `_pilot.sql`. (`snowflake/soc_create_agent.sql`
  is the `SOC_RED_REAPER` base spec — tie its fate to the `AI_AGENTS`
  decision above.)
- `sea_of_colours/orchestrator_2/snowflake/soc_create_agent_pilot_v2.sql`,
  `_pilot_v3.sql`, `_scratch.sql`, `_strategic.sql`, `_strategist_v4.sql`,
  `_tabula.sql`, `_tabula_v2.sql` .. `_tabula_v7*.sql` (incl.
  `_finisher`/`_thinker` variants), `_tactical.sql`, `_tactician_v4.sql`.
  (`orchestrator_v2_schema.sql` is infra, not an agent spec — keep it.)
  **No `tabula_v11` SQL spec exists** — confirmed intentional, V11 is
  `harness_in_process` and never registers a Snowflake Agent object.

**Rewrite:** `sea_of_colours/orchestrator_2/harnesses/PILOT_VERSIONING_GUIDE.md`
around minting a new agent **from V11** (the only harness left to
fork) instead of from a `pilot_v2` that will no longer exist in this
repo. Read it first — it's currently written as a full version-history
narrative across all the removed harnesses.

**Sweep for stragglers** (found so far via `grep -rl` for
`pilot_v[234]|GRID_FAST|SOC_RED_REAPER_PILOT|SOC_RED_REAPER_GRID|tabula_v([1-9]|10)\b`,
excluding `reports/` per the repo-wide convention of not editing
historical AI transcripts):
- Docs: `docs/AGENT_ARCHITECTURE.md`, `docs/OUTSTANDING_ISSUES.md`,
  `docs/RULES_PENDING_REVISION.md` — read each and decide keep
  (historical/still-accurate) vs. rewrite vs. delete-the-section.
- Scripts (mostly one-off diagnostics tied to retired agents — most of
  these are probably fine to delete outright rather than edit):
  `scripts/_season_naming.py`, `diag_v9_vs_heuristic.py`,
  `exp_contained_think.py`, `pilot_turn.py`, `pilot_v4_probe.py`,
  `reconstruct_prompt.py`, `regress_context.py`,
  `replay_thinker_prompt.py`, `run_per_seat.py`, `run_season_v2.py`,
  `run_solo_v5.py`, `run_v5_vs_v4.py`, `run_versus.py`, `scan_thinker.py`,
  `tabula_hallucination_audit.py`, `tabula_v2_multinight.py`. Two
  **do** need to stay functional and just get their retired-agent
  references cleaned instead of deleted: `scripts/run_matchup_v11.py`
  and `scripts/run_season.py` (both are live, general-purpose runners
  that happen to mention old agent names in comments/choices).
- Tests: `tests/test_player_profiles.py`, `tests/test_world_grid.py` —
  check whether they assert on retired agent names/tags specifically,
  or just happen to match the grep pattern incidentally (e.g. a
  fixture named similarly) before touching anything.
- `.env.canonical` — currently sets
  `SOC_CORTEX_AGENT=SOC_RED_REAPER_GRID_FAST`; needs a new default (or
  removal) once the `AI_AGENTS` decision above is made. V11 doesn't
  use `SOC_CORTEX_AGENT` at all (that env var is legacy-cortex-only).

**After the trim:** re-run `SOC_BACKEND=memory pytest` — expect the same
539 passed / 1 pre-existing-unrelated-failure baseline as Phase 1 (the
pre-existing failure is `test_heuristic_passes_known_scenarios[two_seams_choose_one]`,
confirmed unrelated to any agent-roster changes). If new failures show
up, they're from this phase's trim — find and fix rather than skip.

## Phase 3 — Easy install & first-run experience

- Verify `pip install -r requirements.txt` + `python run_web.py` with
  `SOC_BACKEND=memory` gets a human into a game vs `RED_HARVEST_LITE`
  with zero Snowflake, zero config, from a genuinely fresh clone (not
  just this already-verified checkout — re-verify after Phase 2's
  edits land, since deletions are easy to over-reach).
- Confirm the BYO-Snowflake path for V11 end-to-end against a fresh
  trial account (not just an already-configured one) — walk
  `docs/SNOWFLAKE_SETUP.md` literally, step by step, as a first-time
  reader would.
- Consider a `scripts/quickstart_check.py` (or similar) that verifies
  the environment (Python version, deps importable, `pytest` green,
  optionally PAT reachability) and prints a clear pass/fail per check.

## Phase 4 — Simplify the Orbital phase (detail TBD)

**Do not implement anything here without a scoping conversation with
the user first.** Strawman discussed earlier (not committed to):
auto-scoring RED, auto-deducting GREEN, dropping refining, auto-buying
probes/harvesters, and auto-buying a weapon (chaff + EMP) at a BLUE
threshold. Touches `RULEBOOK.md`, all three agents' orbit logic, and
the manual — a big, risky change. If asked to start this phase,
re-confirm scope with the user before writing any code.

## Phase 5 — Manual pass

Finish/polish the existing interactive manual (`manual/index.html`,
`manual.css`, `manual.js` — carried over from the dev repo's own
mid-edit state, not a finished baseline). Revisit if Phase 4 lands and
changes the ruleset underneath it.

## Phase 6 — Hackathon Guide (leveraging the manual)

Lightweight sibling to `manual/` — same retro-terminal shell/CSS, same
tab-strip pattern, but prose/snippets/buttons rather than new animated
demos. Tabs: Welcome → Install & Play → Manual (embeds the existing
one) → Your First Game (vs `RED_HARVEST_LITE`) → Level Up (vs
`RED_HARVEST`) → Play With Friends (adapt `docs/MULTIPLAYER.md`) →
Meet V11 → Build Your Own Agent → Improve Your Agent → Ship It.

## Phase 7 — In-game agent advisor (front-end invoker)

Surface `scripts/advise_v11.py`'s read-only `submit=False` advisor
pattern directly in the web UI. While playing your own seat, invoke an
agent (V11 and/or RED_HARVEST) mid-turn to see its proposed plan
without it touching your game:
- Backend: a read-only `/api/game/{id}/advise` endpoint wrapping
  `harness.run(..., submit=False)`, returning the same
  reasoning/option-menu/moves payload `advise_v11.py` renders into its
  "card" (see `card.txt`/`card1.txt`/etc. in the original dev repo for
  example output shape — those files were deliberately NOT ported here
  as they're scratch output, not source).
- Frontend: a panel to trigger it and render the card (reasoning,
  proposed moves, expandable full detail matching `--full`/`--prompt`),
  plus a "recommend moves" action that pre-fills your order queue for
  you to edit/submit yourself.

## Phase 8 — Drift-testing alarms + submission workflow

- Extend `sea_of_colours/evals/assertions.py` with `OrdersIssuedFully`,
  `WallclockBudget` (vs. `cortex_chat.py`'s wall-clock cap constants —
  note Phase 2 may have changed exactly where these live if the legacy
  `cortex_invoker.py`'s `WALLCLOCK_CAP_OVERRIDES` gets removed), and
  `TokenBudget` (verify/add token-usage capture in `cortex_chat.py`
  first — check whether the chat/completions response envelope already
  surfaces token counts before assuming you need to add capture).
- `docs/HACKATHON_SUBMISSION.md`: fork a harness folder (from V11, per
  the rewritten `PILOT_VERSIONING_GUIDE.md`), register a binding, run
  the drift checklist, open a PR with harness + binding entry.

## Working conventions established so far (keep following these)

- **Don't commit unless explicitly asked.** Stage + describe changes,
  wait for a go-ahead, per this repo's git norms (mirrors the original
  dev repo's `AGENTS.md` git section).
- **Prefer targeted `StrReplace` edits over rewriting whole files**,
  especially in `heuristic_agent.py` (huge file) and
  `binding_registry.py` (many similar dict entries — easy to
  fat-finger the wrong one without full context).
- **Re-run `SOC_BACKEND=memory pytest` after each meaningful change**
  and compare against the 539-passed/1-pre-existing-failure baseline
  rather than assuming green.
- **Clean up any throwaway `.venv` / `__pycache__` / `.pytest_cache`**
  created while verifying, before considering a phase "done" — keeps
  `git status` honest and the tree light for the next diff.
- Fan-out discipline from the original repo's `AGENTS.md` still
  applies here: a rule/constant/formula change is not "done" until
  engine → `RULEBOOK.md` → agent prompts/logic → client/UI → tests →
  trackers are all reconciled. Phase 4 in particular will need this
  checklist in full.
