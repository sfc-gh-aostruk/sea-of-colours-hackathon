# The agentic improvement loop — plan

**Status:** partly built (2026-08-31). Written 2026-08-30.
**Scope:** what an attendee does between "I forked V12" and "my agent is
better than it was", and what we should build so that round trip is
minutes rather than an afternoon.

This is the design document for Phase 7.5 + Phase 8 in
`docs/HACKATHON_BUILD_PLAN.md`. It supersedes the sketch there; that
table should point here.

---

## What is built, as of 2026-08-31

The attendee-facing guide is **`docs/HACKATHON_AGENTS.md`** — mint,
improve, score, publish, league. Read that first; this document is the
reasoning behind it.

| Piece | Where | State |
|---|---|---|
| One front door | `scripts/soc.py` | built — `new`, `list`, `suite`, `why`, `doctor`, `push`, `league` |
| Fork registration without conflicts | `orchestrator_2/agent_manifest.py` | built — directory discovery over `agent.json` |
| The scenario suite | `evals/battles/` | built — 9 boards x 5 rungs x 4 loadouts, offline |
| Verdict after an edit | `soc suite` | built — 45 turns in ~1s against the heuristic |
| "Why did it do that" | `soc why <board> [agent]` | built — question, canonical, V12's baseline, then every move against every check |
| Per-run cards | `soc suite --cards DIR` | built |
| Submission | `soc push` | built — enforces agent-only diffs |
| League | `soc league` | built — entrants are discovered, fallback runs flagged |

**Time-to-verdict, measured:** ~1s for the whole suite against the
heuristic, so the target in §1 is met for the offline case. An LLM agent
is bounded by its own latency, which is why `--board` and `--up-to`
exist — the common inner-loop command is one board at one rung.

### Three things the build changed about the plan

1. **Registration had to move before anything else.** The plan assumed
   forks register in `binding_registry.py`. With forty teams that makes
   every push conflict with every other push and turns collation into
   forty merges. Discovery over `agent.json` came first because `soc
   push` and the league both depend on an agent being exactly one
   directory.
2. **The boards are constructed, not restored.** The nine documented
   redsign battles live in Snowflake snapshots that are not in git, so
   they cannot be restored offline — and a frozen blob has exactly one
   difficulty anyway. They are rebuilt from their documented geometry
   via `WorldBuilder`, which is what makes the difficulty ladder
   possible at all. The trade: documented shape, not byte-exact state.
3. **Scoring a fallback as a score is a real hazard.** A V12 fork with
   no credentials scored 86% on its internal safety net and outranked
   the heuristic. Runs now record whether the model was reached, and
   both the report and the league say so loudly.

### Still open

- **`two_seams_choose_one` is red** (`tests/test_eval_scenarios.py`), a
  pre-existing heuristic regression unrelated to this work. It should be
  green before attendees are told to trust scenario results.
- **No LLM verification.** Everything above was exercised against the
  offline heuristic. The V12 path needs one real run with a PAT before
  the day.
- **The prompt-diff idea in §5 is not built.** `soc why` covers the
  "what did it see" half; comparing two runs' cards is still manual.

---

## 1. The thing we are actually designing for

An attendee's day, honestly described:

| Time | What they do | What they need |
|------|--------------|----------------|
| 0:00 | Install, run the server, play the tutorial | Already built |
| 0:30 | Watch V12 play a night | Already built (AGENT panel, replay) |
| 0:45 | `new_agent.py --team x --name y` | Already built |
| 0:50 | **"Why did it do that?"** | Cards exist — but you have to know to set an env var |
| 1:00 | Change a doctrine string / a gate / add a weapon option | The two gaps are documented |
| 1:05 | **"Is it better?"** | ← **this is where the day is won or lost** |
| … | Repeat 1:00–1:05 as many times as possible | |
| 6:00 | Submit, compete | Nothing exists |

Everything hinges on the cost of the 1:00 → 1:05 round trip. If it is
five minutes, an attendee gets maybe forty iterations in a day and
learns something. If it is fifteen, they get a dozen, most of which they
will not bother to run, and they will spend the day reading code and
guessing.

**So the design goal is one number: time-to-verdict after an edit.**
Target: under 30 seconds for the common case.

## 2. What already exists (and is good)

I inventoried the repo before proposing anything. There is more here
than a first read suggests:

- **Minting works.** `scripts/new_agent.py --team redwatch --name reaper`
  copies the harness, rewrites `tabula_v12` → `redwatch_reaper` through
  imports/identity/env-var namespaces, and inserts two entries into
  `binding_registry.py`. It rolls back on failure. The fork appears in
  the New Game modal on the next server start with no frontend edit,
  because the modal reads `/api/meta/agents` off `selectable_agents()`.
- **The card is excellent.** `SOC_CARD_DUMP_DIR=/tmp/cards` writes one
  file per turn containing the full prompt, the option menu, the THINK
  prose, the PLAN JSON, the packager trace, the sanitiser trace and the
  final moves. This is a complete autopsy of a decision. Everything else
  in this document orbits it.
- **Evaluation exists at three scales**: ~56 scenarios in
  `sea_of_colours/evals/` (24 wired into the orchestrator_2 CLI, 7 pinned
  as a must-pass heuristic set in CI); `scripts/turn_suite.py` for pinned
  turns; `scripts/run_matchup_v12.py` for full head-to-head seasons.
- **The harness contract is clean.** One function,
  `run(*, store, session_id, player, view) -> dict`, and
  `submit=False` gives you the whole pipeline with no engine write —
  which is what the in-game advisor already uses.
- **The gaps are real and well chosen.** Gap 1 (buys weapons, never
  fires) needs edits in four independent places, which is a genuine
  systems exercise rather than a prompt tweak. Gap 2 (BLUE is an
  afterthought) has five levers where loosening one alone does nothing.

## 3. Where the loop actually breaks

Six problems, roughly in order of how much they cost:

1. **There is no answer to "is it better?" that runs in under a minute.**
   A matchup season is 5–15 minutes of LLM calls. The scenario suite is
   faster but still tens of seconds per scenario with a real model, and
   it reports pass/fail against fixed assertions rather than
   *better/worse than what I had*.
2. **Six scripts, no front door.** `new_agent.py`, `run_evals.py`,
   `run_battery.py`, `run_matchup_v12.py`, `turn_suite.py`,
   `advise_v12.py`, `dump_suite_cards.py`, `replay_turn.py`. Each has
   its own flags. An attendee has to learn the toolchain before they can
   use it, and the toolchain is not the point of the day.
3. **Cards are opt-in and undiscoverable.** They are the best artifact we
   have and they are behind an environment variable that is documented
   in a harness README.
4. **Nothing compares two cards.** The single most useful question —
   "I changed my doctrine, what did that actually do to the decision?" —
   has no tool. You diff two 30KB text files by eye.
5. **The advisor is hardcoded to V12.** An attendee cannot ask *their own
   agent* for advice in-game, which is the most enjoyable way to
   understand what it thinks.
6. **There is no end to the day.** No submission format, no scoring, no
   leaderboard, no reason for the room to compete rather than forty
   people quietly tuning in parallel.

There is also one small correctness snag worth fixing early: the
orchestrator_2 eval CLI refuses to run Cortex configs unless
`SOC_BACKEND=snowflake` (`orchestrator_2/evals/cli.py:138-141`), while
`run_matchup_v12.py` runs the same agent fine on `memory`. That
inconsistency will cost somebody an hour.

## 4. The proposal: three loops at three speeds, behind one command

The insight is that "is it better?" has three different answers with
three different costs, and attendees should reach for the cheap one
almost always.

```
   soc turn      seconds     one pinned board, one decision, one card
   soc eval      minutes     the scenario suite, scored against your last run
   soc match     ~15 min     full seasons vs RED_HARVEST and vs stock V12
```

The fast loop is **pinned turns**, not seasons. A pinned turn is a frozen
board state (we already have these — `reports/turn_suite/suite.json`,
and `export_agent_guide_data.py` uses a frozen snapshot). Running your
agent on one is a single LLM call: 5–15 seconds. Running it on eight is
a minute, parallelised.

That is the round trip. Everything else is confirmation.

### 4.1 `soc` — one front door

A single entry point that wraps what exists. Not a rewrite: a façade over
the current scripts, so the scripts stay usable and nothing is
reimplemented.

```bash
soc new                      # interactive mint: team, name, colour, blurb
soc play                     # start the server and open a game vs your agent

soc turn                     # run your agent on the default pinned board
soc turn --board own_seam_d4 --repeat 3
soc diff                     # your last card vs your previous card
soc diff --against stock     # your last card vs stock V12 on the same board

soc eval                     # the scenario suite for your agent
soc eval --scenario tier_choice --card    # one scenario, dump the card

soc match                    # seasons vs RED_HARVEST, LITE and stock V12
soc submit                   # package + score + push to the leaderboard

soc card                     # pretty-print the most recent card
soc why                      # the last decision in one screen (see 4.3)
```

`soc` reads a `.soc-agent` file written by `soc new` so that every other
command already knows which fork you mean. No `--config my_team_my_name`
on every invocation — that repetition is small but it is paid forty
times an hour.

**Build cost:** small. This is argument plumbing over existing entry
points, plus the config file. A day.

### 4.2 The card diff — the highest-leverage single thing

Cards are ~30KB of text. Diffing them raw is useless: the board state,
timestamps and the whole rules block move around. What an attendee wants
is a *semantic* diff of the decision:

```
$ soc diff

board own_seam_d4 · seat p1 · day 4
  redwatch_reaper @ HEAD          vs   redwatch_reaper @ 3 edits ago

  MENU        41 options            42 options       +EMP_SALVO_1
  THINK       "hold the seam"       "contest the pure"
  PLAN        picked CH2, PR1       picked SMASH_GRAB, EMP_SALVO_1
  PACKAGER    5 moves, 0 repairs    7 moves, 1 repair (green avoid @ 12,9)
  MOVES       drop step×3 pickup    drop step×4 pickup + emp×3
  VALUE       est 210               est 604
```

Four sections, each one line unless it changed. This turns "I changed a
doctrine string" into a verdict in the time it takes to read six lines.

The pieces already exist: `card.py` renders the card, and the harness
already returns the option menu, the reasoning, the plan and the moves as
structured `extras`. What is missing is (a) persisting cards under a
content-addressed name so "previous" is well defined, and (b) the
comparator.

**This is the thing I would build first if I could only build one.**
`docs/HACKATHON_BUILD_PLAN.md` already reaches the same conclusion in
its Phase 7.5 note; this is agreement, not a new idea.

**Build cost:** two days, most of it deciding what counts as a
meaningful difference.

### 4.3 `soc why` — the decision on one screen

A card is complete, which makes it long. For the 0:50 moment ("why did it
do that?") the attendee wants one screen:

```
DAY 4 · SEAT p1 · redwatch_reaper

IT SAW      pure @ (12,9) [redsign, not yet contested]
            rival probe @ (14,8), 2 nights old
            vault 11/15 · 1750c · 50b

IT WAS OFFERED   CH1 seam@(4,3) est 180   CH2 seam@(11,9) est 240
                 SMASH_GRAB @(12,9) est 604   PR1..PR4   [no weapon options]

IT CHOSE    CH2 — "the pure is probably defended and I cannot
            afford to lose the hull this late"

IT DID      drop(11,9) step(11,10) step(12,10) pickup      est 240

⚠ 2 EMP in stock, 0 fired.  This is Gap 1 — see harness README §Gap 1.
```

That last line matters more than it looks. Pointing at the gap *at the
moment the attendee is looking at its consequence* is worth more than any
amount of README. The same treatment applies to Gap 2: flag unspent blue
against a vault that had room.

**Build cost:** a day on top of the card work — it is a different render
of the same structured data.

### 4.4 Make the advisor fork-aware

`GET/POST /api/game/{id}/advisor` already runs `harness.run(submit=False)`
and paints the suggestion on the board. It is hardcoded to V12. Making it
resolve through `binding_registry` like everything else means an attendee
can sit in a live game, press ASK, and watch *their own* agent's
reasoning appear over the board they are looking at.

This is the single most *enjoyable* item on the list, and enjoyment is
not a soft concern at a hackathon — it is what makes people iterate
forty times instead of twelve.

**Build cost:** small, if the advisor's V12 import is the only coupling.
Worth checking for hardcoded `tabula_v12` strings on the server side
before promising it.

### 4.5 A leaderboard, and therefore an end to the day

Without this the room is forty people tuning in parallel with no reason
to finish. With it, the day has a shape.

- `soc submit` runs a **fixed** battery: N seeds × seats, against
  RED_HARVEST, RED_HARVEST_LITE and stock V12, on pinned seeds so every
  entry faces the same boards.
- It writes a result row: agent label, team, score deltas, green-line
  count, weapons fired, wall-clock, token spend.
- A served page ranks them. `server/static/evals.html` already exists as
  an eval replay viewer and is the natural place to hang it.
- Every row links to a **replay** of one of its seasons. The leaderboard
  should be watchable, not just a table — this game is legible in replay
  and that is a large part of its charm.

Two design notes:
- **Rank on margin against a fixed opponent, not head-to-head Elo.**
  Elo needs many games; we will have a handful per team and a day.
  Margin-vs-baseline on pinned seeds is fairer and computable from one
  battery run.
- **Report token spend and wall-clock next to score.** Otherwise the
  winning strategy is "call the model nine times a turn", which teaches
  the wrong lesson and empties somebody's Snowflake credits.

**Build cost:** two to three days including the page. This is the largest
item and the most cuttable — the loop works without it, the *day* does
not.

### 4.6 A recipe book, not more reference docs

The harness README documents the two gaps well. What it does not have is
a worked example of a *small* change end to end. I would add three, each
one page, each following the same shape — change, command, verdict:

1. **Loosen a blue gate** (one number in `value_pyramid.py`) → `soc diff`
   → see the menu gain a blue option → `soc eval` → see two scenarios
   flip. The "you can do this in ninety seconds" example.
2. **Add an EMP option to the menu** (`agency.build_registry` +
   `packager` + move schema) → the real Gap 1 exercise, with the four
   gates named and the reference implementation in `heuristic_agent.py`
   ~2250–2410 cited.
3. **Rewrite a doctrine block** → `soc diff` showing the THINK prose
   change and the plan *not* changing, which is the most useful negative
   result in the whole exercise and the one nobody expects.

## 5. Build order

Ordered by (value to the attendee) ÷ (cost), with the constraint that
each step is useful on its own if we run out of time:

| # | Item | Cost | Why here |
|---|------|------|----------|
| 1 | Cards on by default + content-addressed storage | 0.5d | Prerequisite for everything; also fixes discoverability on its own |
| 2 | `soc` façade with `new` / `turn` / `card` | 1d | The front door; makes cards reachable |
| 3 | `soc diff` | 2d | The verdict. The single highest-value item |
| 4 | `soc why` | 1d | Turns the card into understanding; carries the gap nudges |
| 5 | Fix the eval-CLI backend inconsistency | 0.5d | Small, and it will otherwise eat somebody's morning |
| 6 | `soc eval` + `soc match` wrappers | 1d | Confirmation loops |
| 7 | Fork-aware advisor | 1d | Enjoyment, and the best explanation surface we have |
| 8 | Recipe book (3 worked changes) | 1d | Turns the tooling into a taught skill |
| 9 | `soc submit` + leaderboard page | 3d | Gives the day an ending |

Items 1–4 are the loop. If only those ship, the hackathon works.
Items 5–8 make it pleasant. Item 9 makes it a competition.

## 6. What I would deliberately not build

- **A GUI agent editor.** Attendees are here to write Python. A visual
  editor would take a week and produce worse agents.
- **Elo / a full tournament bracket.** Too few games, too much
  machinery. See 4.5.
- **A new eval framework.** There are ~56 scenarios and a working runner.
  The problem is not the scenarios, it is that nothing tells you whether
  *your* run beat *your last* run.
- **Auto-tuning / a meta-agent that edits the agent.** Tempting, and
  exactly the sort of thing that eats the whole day and teaches nobody
  anything.
- **Anything that requires a Snowflake account to iterate.** The fast
  loop must work against `memory` with one PAT. Cards, diffs and pinned
  turns all can.

## 7. Risks

- **Token cost.** Forty attendees × forty iterations × 3 LLM calls is a
  lot of inference. The pinned-turn loop is the mitigation (1 call, not a
  season), and `soc` should print a running token count so the cost is
  visible rather than discovered.
- **The card format is not stable.** `soc diff` couples to it. Either
  freeze the structured `extras` contract or have the diff work off the
  harness return value rather than the rendered text — the latter is
  better and is what I would do.
- **Fork drift.** `new_agent.py` copies V12 wholesale, so a bug fixed in
  V12 after minting never reaches the forks. Acceptable for one day; the
  README should say so plainly rather than let people discover it.
- **`soc` becoming a second toolchain.** If it wraps the scripts it is a
  façade; if it starts owning logic it is a rewrite. Keep the scripts
  working and callable directly.

## 8. Open questions

1. Is the advisor's V12 coupling only the import, or does the server hold
   other `tabula_v12` strings? (Determines whether 4.4 is one day or
   three.)
2. Which boards go in the pinned set for `soc turn`? It wants ~8 turns
   covering: an uncontested seam, a contested pure, a blue decision, a
   final night, a damaged hull, an EMP opportunity. Some exist in
   `reports/turn_suite/suite.json`; the set should be chosen so that a
   good change moves at least one and a bad change moves the wrong one.
3. Do we score the leaderboard on one battery or best-of-N submissions?
   Best-of-N rewards resubmitting; one battery rewards being ready.
4. `two_seams_choose_one` currently fails in CI (a known regression, see
   `docs/OUTSTANDING_ISSUES.md` #27). The must-pass heuristic set should
   be green before we ask attendees to trust scenario results as a
   verdict.
