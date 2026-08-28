# Tutorial plan — landing menu, manual embeds, first-turn tooltips

Status: **PLAN ONLY — nothing here is implemented.** Written 2026-08-28.

Replaces the landing page's `Quick game` button with a `TUTORIAL` chooser
offering three entries. Every entry runs on the memory backend and lasts
three nights.

---

## 1. What already exists (and therefore costs nothing)

Worth stating up front, because it makes most of this feature cheap and
concentrates the real work in exactly two places.

- **Programmatic game spawn.** `newGame({players, agents, backend})` in
  `server/static/app.js` is already the entry point the landing page uses
  for `?new=quick`, and it already pins `backend: "memory"` (v1.14 — so a
  machine with Snowflake credentials doesn't make the "just let me play"
  button the slowest path in the app). Tutorial presets are more of the
  same call.
- **Board size and night count are first-class.** The New Game modal
  already exposes `ngm-width`, `ngm-height` and `ngm-cap`, and
  `GameSession.new` takes `width`, `height` and `season_day_cap`. "Smaller
  map, three nights" needs no engine change.
- **Manual deep links work, and so does re-pointing them.**
  `manual/manual.js` parses `#tab=<name>` and listens for `hashchange`, so
  a single iframe can be stepped through sections **without reloading** —
  set `iframe.contentWindow.location.hash` and the manual switches tab in
  place. This is what makes a stepper feel instant rather than flashing
  white between pages.
- **Available tabs:** `tiles`, `harvesters`, `probes`, `orders`, `vision`,
  `signs`, `emp`, `chaff`, `orbital`, `loop`, `season`, `maps`,
  `opponents`.

## 2. What does not exist

### 2.1 Turning weapons and signs off — the main body of work

There is **no flag anywhere** that disables weapons or signs.
`RED_HARVEST_LITE` is only a *bot* that declines to use weapons; it does
not stop a human buying an EMP, and nothing suppresses sign minting. Basic
mode needs both genuinely off.

Two constraints to hold to:

- **Per game, not per process.** Same rule as the storage backend
  (`AGENTS.md`, v1.14): the flags live on the session and are persisted, so
  a tutorial and a real season can coexist on one server. Nothing may ask
  "is this process in tutorial mode?".
- **Agents read the flags; they are not silently filtered.** If V12 keeps
  proposing EMPs and the sanitiser eats them, the agent burns its whole
  turn budget on illegal moves and looks broken. The flags belong in
  `_active_rules()` (`sea_of_colours/snowpark/view.py:65`) next to
  `drop_mode` / `probe_radius`, which is already the channel prompts are
  told to read dynamically.

This is a rules change, so it is a **fan-out edit** per `AGENTS.md`:
engine enforcement → `RULEBOOK.md` prose + Canonical Configuration +
changelog → V12 prompt (`orchestrator_2/harnesses/tabula_v12/`) →
`agent/heuristic_agent.py` → UI (`server/static/`) → `guide/` and
`manual/` → tests → `docs/OUTSTANDING_ISSUES.md`.

Note the UI half is *hide*, not *ignore*. A greyed EMP button in a mode
where weapons do not exist still teaches the player that weapons exist and
that they are broken.

### 2.2 A fixed tutorial board

`GameSession.new` only generates from a seed — it cannot be handed a
prebuilt grid. So "a thick seam down the middle with a pure" cannot be a
curated seed: no seed reliably produces that shape, and the v1.29 halo
grading would perturb it anyway.

**Recommended:** a named terrain preset in
`sea_of_colours/generator.py` (`terrain_preset="tutorial_seam"`) rather
than grid injection. The grid is packed and persisted *after* generation,
so a preset saves, loads and replays through every existing path with no
special-casing anywhere downstream.

## 3. The three entries

`server/static/landing.html:44` (`#btn-quick`) becomes `TUTORIAL`, opening
a chooser with three cards. `server/static/landing.js:330` currently sends
`?new=quick`; the chooser sends `?new=tut-basic`, `?new=tut-advanced` or
`?new=quick`, all handled in the same `app.js` block that reads the `new`
param today (~line 22185).

| Entry | Board | Nights | Weapons | Signs | Opponent |
|---|---|---|---|---|---|
| Basic | 24x16, `tutorial_seam` | 3 | off | off | `RED_HARVEST_LITE` |
| Advanced | 24x16, `tutorial_seam` (same board) | 3 | on | on | `RED_HARVEST_LITE` |
| Quick game | 40x28, normal generation | 3 | on | on | `RED_HARVEST_LITE` |

Basic pairs naturally with `RED_HARVEST_LITE`, which already never fires
anything — so the weapons-off rule and the bot's behaviour agree instead of
the bot being visibly hobbled.

Advanced deliberately reuses the *same* board as Basic. The second run is
about what signs and weapons add to terrain you have already read, so
re-rolling the map would throw away the only thing the player knows.

**Build the presets as overrides on the New Game modal's default config,
not as independent literals.** Otherwise any field added to that modal
later silently fails to reach the three tutorial paths — a drift bug that
would surface months later as "the tutorial ignores X".

## 4. Teaching surface: mini-films first, manual second

Eight sections of prose before a first move is a wall. The primary
teaching surface should be **short silent films of real turns**, with the
manual embed demoted to "read more" behind them.

### 4.1 How the films get made — generated, never hand-recorded

**Hard rule: no hand-recorded video.** The ORDERS and ORBIT panels are
mid-redesign and mines are being removed; a screen capture taken today is
wrong within a week, and nobody re-records by hand. Films must be
reproducible by running a script.

The machinery is close to already built. `scripts/_fx_*.py` — sixteen
harnesses today — already boot a memory-backend server, seed a season,
drive the real UI and take screenshots. Playwright is installed and its
`new_context(record_video_dir=...)` is available, so the same harness
pattern records `webm` instead of stills.

**Proposed:** `scripts/make_tutorial_films.py`, one function per film,
sharing the `_fx_*` seeding helpers. Output committed to
`server/static/films/*.webm`. Re-run after any UI change that a film
shows.

Two known gaps:

- **No cursor in the recording.** Playwright doesn't paint a pointer into
  video. Inject a small fake cursor element that the script moves to each
  click target before clicking — without it the UI appears to operate
  itself, which teaches nothing about *where to click*.
- **Pacing.** Real automation clicks faster than a human can follow.
  Films need deliberate dwell before and after each click.

### 4.2 Why not the alternatives

- **Replaying a canned session through the existing cinematic**
  (`paintReplayFrameOntoMain` / `runReplayAnimationsTick`, fed by a
  pre-seeded session on the memory backend) is attractive — zero video
  files, and it can never look stale because it renders through the live
  renderer. But it only shows *the night resolving*, never *how to give
  the order*, which is precisely the thing a first-timer is stuck on. Good
  candidate for the "what happens at night" beat specifically.
- **A hand-built self-contained animation** in the style of
  `docs/scatter_fx.html` gives total control and drifts fastest. Not worth
  it for turn mechanics.

### 4.3 The films

Silent, looping, autoplay-muted, roughly 8–15s each — one idea per film.

**Basic**

1. **You start blind** — the whole board is fog; hover a cell, the tooltip
   says `terrain unseen`.
2. **Launch a probe** — the vision border opens up and terrain appears.
3. **Read a cell** — hover inside the lit area: colour, tier, value, score.
4. **Drop a harvester** — `DROP`, pick a cell *you can see*, the queued
   annotation appears on the row.
5. **Walk, harvest, and lift** — queue steps and a `LIFT`, `TRANSMIT`, the
   night resolves, cargo fills, the vault and score move.

**Probe before drop is not a stylistic choice.** `drop_mode` is
`live_only` (`game/tuning.py`), so on night one there is nowhere legal to
land — the board is 100% fog until a probe goes up. A film that opens by
dropping a harvester is teaching an order the engine will refuse. The
opening lesson *is* the blindness.

Likewise **the lift belongs in the same film as the walk**, not a later
one: a harvester left on the surface at the end of your queue is destroyed
at Aurora (§3.11.2), so a film that drops and walks without lifting has
quietly taught the player to lose the unit.

**Advanced**

6. **Signs** — what a rival's sign gives away.
7. **EMP and chaff** — the area goes down; a harvester dies.

That covers the ground the eight prose sections were covering, in the
order a turn actually happens.

### 4.4 The manual embed (secondary)

Still worth building, now as "read more" rather than the front door. A
modal iframe over `/manual/#tab=<name>`, stepped with Next / Back by
writing the hash.

**Embed mode.** Add `#embed` (or `?embed=1`) handling to `manual/` that
hides the manual's own sidebar and tab bar, so the modal shows one section
of content rather than a whole nested application. Only the sections listed
below need to be embed-safe; the rest of the manual is unaffected.

**Always link out.** Every embedded section carries an "open the full
manual" link to `/manual/#tab=<current>` in a new tab, dropping embed mode.
Nothing in the embed is a dead end.

**Section order.**

- **Basic (8):** `tiles` → `harvesters` → `probes` → `vision` → `orders` →
  `loop` → `maps` → `opponents`. Board, then what you own, then how you
  see, then how you give orders, then how a night resolves, then the wider
  map and rivals.
- **Advanced (3):** `signs` → `emp` → `chaff`.

**Nothing here gates play.** With films carrying the front door, these
eight are opt-in reading reachable from the film stepper and from the
in-game manual link — not a wall to climb before the first move. Keep the
`START PLAYING` button live throughout regardless.

## 5. First-turn tooltips

Reconciling two things said at different times: no scripted overlay, and
tooltip overlays for first-turn play. The line between them:

**Build:** contextual, anchored, dismissible tooltips pointing at real
controls, driven by a small declarative list
(`{anchor: <selector>, text, showWhen: <predicate>}`), that never block
input and never advance the game. First turn only. Dismissed on
interaction with the thing they point at, plus a "don't show again"
persisted in `localStorage`.

**Do not build:** a wizard that greys the board, takes the wheel, and
marches through numbered steps.

**Scope:** tutorial games only (Basic and Advanced), not Quick game.

The declarative list matters more than it looks — it is what stops these
becoming thirty hardcoded `if` branches scattered through `app.js`, and it
is what lets a stale tooltip be found when a control is renamed.

## 6. Suggested order

1. **Mines removal first** (already queued). It shrinks the weapons surface
   *before* a toggle is added across it — otherwise that work is done twice.
2. **Per-game `weapons_enabled` / `signs_enabled`**, with the full fan-out
   sweep. This is the big one.
3. **`tutorial_seam` terrain preset.**
4. **Landing chooser + the three presets** — mostly existing machinery.
5. **First-turn tooltips.**
6. **Films last, deliberately.** Every film shows the UI as it is on the
   day it is shot, so shooting before the mines removal and the
   ORDERS/ORBIT redesign have settled means shooting twice. The films are
   also the cheapest step once `make_tutorial_films.py` exists, so there is
   no schedule reason to pull them forward.
7. **Manual embed mode + iframe modal stepper** — optional, "read more".

## 7. Risks

- **The rot risk on the flags.** An engine that honours `weapons_enabled`
  while the V12 prompt does not know about it produces an agent that spends
  every turn proposing illegal moves. Prompt and heuristic must land in the
  same change as the engine, not after it.
- **Preset drift** — mitigated by building presets as overrides on modal
  defaults (§3).
- **Embed-mode scope creep.** Only the eleven listed sections need to be
  embed-safe. Making the whole manual embeddable is a much larger job with
  no payoff here.
- **Film staleness is the whole ball game.** A film is a screenshot of a
  moving target. The mitigation is not discipline, it is that
  `make_tutorial_films.py` regenerates all of them in one run — so the
  script is the deliverable and the `.webm` files are build output. If
  films ever become hand-recorded, they will be wrong and stay wrong.
- **Film review has no test — and this is not hypothetical.** The spike
  (`scripts/_film_drop.py`, run 2026-08-28) exited `PASS`, produced a clean
  11.6s film, and was pedagogically wrong twice over: it dropped onto fog
  (illegal under `live_only`, so the order dies at resolution) and left the
  harvester with a `STRANDED` sticker. Every automated check it had was
  green. A film can only be signed off by watching it.

## 8. Spike result (2026-08-28)

`scripts/_film_drop.py` proved the pipeline end to end. Output:
11.6s, 1.4 MB `webm`, `reports/films/drop_a_harvester.webm`.

What it establishes:

- **The generation approach works.** Real session, real selectors, real
  clicks, real animations, ~16s to shoot. Re-running after a UI change is
  free.
- **The injected cursor reads correctly.** A lime ring that glides on
  `requestAnimationFrame` with an `easeInOutQuad` and pulses on press.
  Critically, the script moves the *real* pointer to the same place, or
  nothing hovers and half the UI never lights up.
- **A caption bar is worth having** and costs nothing — plain DOM, picked
  up by the recording for free.

What it exposed, all now folded into §4.3 above:

- Night one is **100% fog** (384/384 cells), so "pick an unfogged cell"
  finds nothing and the shoot stalls. Fixed by selecting the centre cell
  by coordinate.
- The ORDERS panel is an **annotator, not a gate** (v1.24) — clicking fog
  queues the order happily. Convenient for filming, and exactly why the
  film could teach an illegal move without anything complaining.
- The picker is **sticky** — a landing chains into steps, so the blinking
  banner is still up when the film ends unless `Escape` is pressed.
