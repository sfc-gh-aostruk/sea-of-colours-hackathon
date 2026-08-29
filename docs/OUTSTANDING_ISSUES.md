# Outstanding issues / bug log

Running log of known bugs and misbehaviours to triage and fix. **Documentation
only — no fixes applied yet.** Logged 2026-07-01.

Severity legend: 🔴 critical (breaks play / multi-client) · 🟠 high · 🟡 medium · ⚪ low.

---

## 1. ✅ (DONE, v1.8) Phantom harvester trails in echo-only areas

**Status (v1.8):** Fixed. Trails are now a **fog-gated observation** rather than
a live overlay.

**Root cause:** `player_dense_view` / `agent_dense_view` re-derived the trail from
the **live** ledger (`_trail_summary` / `_trail_markup`) and stamped it onto
*every* visible cell — including `echo` (stale) and `memory` cells. Because the
ledger updates every night, an echo tile showed traffic that grew in real time
without the seat having current LOS (a genuine fog leak — it affected the AI
world view too, not just the human map).

**Fix:**
- Echo snapshots (`_probe_tile_snapshot`) and memory tiles (`_blend_memory`) now
  **freeze** `trail` + `trail_markup` at sighting time.
- The view builders serve the **live** ledger only on cells with current LOS;
  echo/memory cells serve the **frozen** copy. Fog cells still carry nothing;
  the omniscient observer view is unchanged.
- Edge case: when a harvester crushes a probe by landing on it, `consume_probes_at`
  now freezes a final echo (with the just-laid trail) into the owner's intel — the
  probe "witnesses its killer" — since the dying probe can't re-pulse.

**Tests:** existing `test_player_view_trails_survive_into_stale_memory` now passes
on correct semantics (it previously relied on the phantom leak).

---

## 2. ✅ (DONE, v1.7) Vault reflects 15-square capacity + capacity warning

**Status (v1.7):** Fixed. The VAULT denominator is now uniformly the canonical
**15-slot** capacity (RULEBOOK §3.12), and the VAULT tab pill surfaces a
persistent, at-a-glance capacity warning.

**Root cause (display):** The backend was already correct — `HOARD_CAPACITY = 15`
is enforced in `deposit_haul_to_hoard` (tier-priority displacement, §3.14) and
`inventory_pack` ships `hoard_capacity: 15` (confirmed live: `6/15`). But the
client had **stale capacity fallbacks** scattered across the render paths — `|| 50`
(`fmtInventory`, `_emptyInventory`, INTEL meta), `|| 25` (`renderVault`, INTEL
meta), `|| 0` (`fullVaultPickupWarning`) — so any path that arrived without an
explicit `hoard_capacity` (empty inventory, replay reconstruction, INTEL tab)
rendered a wrong 25/50 denominator.

**Fix (`server/static/app.js`, `styles.css`):**
- Added one shared `HOARD_CAP_FALLBACK = 15` constant and routed every fallback
  through it, so the vault never shows a stale 25/50.
- Added a **persistent capacity warning** on the VAULT tab meta pill in
  `renderVault`: amber `cc-tab-meta--warn` at ≥ 90 % (14/15) and a pulsing red
  `cc-tab-meta--full` at 15/15, each with a hover tooltip explaining that an
  incoming square displaces the lowest-tier parcel (§3.14) and to ship/refine to
  free slots. This complements the existing TRANSMIT-time overflow guard
  (`fullVaultPickupWarning`), which only fires when a pickup is queued into an
  already-full vault.

**Symptom (original):** The vault didn't clearly reflect the 15-square capacity
and issued no standing warning as it approached/exceeded the limit.

**Repro (original):** Fill a vault toward/over 15 squares and watch the count +
warning behaviour.

---

## 3. ✅ (DONE, v1.7) Multiplayer: praxis submission bounced back to the action menu

**Status (v1.7):** Fixed. A multi-human submit whose night did **not** resolve
on our click (other humans still plotting) now holds the player in a committed
"LOCKED IN — waiting for pN" frame instead of tearing the resolving overlay
down and re-enabling the composer.

**Root cause:** `submitSoloNight` (`server/static/app.js`) always ran
`pullAllMaps({playFx:true})` then `endResolvingFrame()` + re-enabled the
TRANSMIT button in its `finally`. In a 2-human game the first submitter's
`POST /policy` returns `night_resolved:false` (the engine only resolves once
`both_ready()`), so there was no cinematic — the overlay just dropped and the
composer came back, reading as "nothing happened" even though the seat was
locked (tick + waiting strip were correct).

**Fix:** When `_multiHumanGame && !body.night_resolved`, `submitSoloNight`
(and `submitSoloOrbit`) now call `enterHumanWaitFrame(...)`: it freezes the
transmit feed on a persistent "you locked in · waiting for other players" line,
repaints the overlay headline to `LOCKED IN — waiting for pN`, ensures the
live-sync poller is running, and returns early. The `finally` keeps the frame up
and the button disabled. The standing `pollLiveSync` clears the frame + drives
the reveal/cinematic when the night resolves (see #4).

**Symptom (original):** In human multiplayer, submitting praxis dimmed the menu,
showed the progress list, then **cleared and returned the player to the action
menu** while a tick appeared next to their name and the UI showed "waiting for
players" — the submission was registered but the flow implied it hadn't happened.

---

## 4. ✅ (DONE, v1.7) Multiplayer: praxis animation broke for every player except the last

**Status (v1.7):** Fixed. All connected clients now play the same clean
resolution cinematic when the night resolves, regardless of submit order.

**Root cause:** The **last** submitter's client resolves the night inside its own
`submitSoloNight`, and its `pullAllMaps({playFx:true})` cinematic runs while
`inFlightSubmit === true`, which suppresses the standing `pollLiveSync` poller —
so it played uninterrupted. **Earlier** submitters had already torn down (bug #3)
and relied on `pollLiveSync` to drive the cinematic; but that poller (a) fired a
full `pullAllMaps({playFx:true})` on *every* status-signature change (including a
bare opponent-lock / pending flip), and (b) had no `_liveFxPlaying` guard, so a
2.5s poll tick landing mid-cinematic re-pulled and half-painted / cancelled the
in-flight animation → "breaks for everyone but the last".

**Fix (`pollLiveSync`, `server/static/app.js`):**
- Skip entirely while `_liveFxPlaying` (never re-pull over a playing cinematic).
- Distinguish a real **resolution** (new replay window, day roll, or phase flip)
  from a mere **opponent-lock** (pending flip, same day/phase): only a real
  resolution drives `pullAllMaps({playFx:true})`; a lock just refreshes the
  waiting strip + phase line via a light `refreshStatus()`.
- On resolution, clear the committed-wait frame (#3) and let the shared cinematic
  path play + drop the overlay (`pullAllMaps` still frame-gates via
  `newDayLanded`, so the resolver never double-plays).
- The resolver re-seeds the poller baseline (`liveSyncSig = ""`) on teardown so
  its own next tick doesn't replay the night as a redundant reveal.

**Symptom (original):** The full praxis animation began for all players (menu
dims, orbital commands appear) but the sequence broke for everyone except the
last to submit; only the last player got the intact animation → orbital flow.

---

## 5. ✅ (DONE) "LAUNCH DELAY" debug button leaks into the replay toolbar

**Status (v1.4):** Removed. The debug button is gone; the orbit→surface
sequencing it hinted at is now a proper **Settings** toggle (`toggle-orbit-seq`,
"sequence orbit launch → surface", default ON), persisted to localStorage. Drops
and probes lead their board effect behind the orbital launch animation.

**Symptom:** A `LAUNCH DELAY: ON/OFF` button appears in the replay toolbar. It
is an undocumented debug control — the user doesn't know what it does.

**What it does:** Injected by `_osInjectSetting()` in
`server/static/station.js` (only when the optional station UI is active). It
toggles `window._osLaunchDelay` between 0 and 220ms, which staggers the map's
orbital arc animation ~220ms behind the station-panel canvas animation (see the
launch-delay branches in `server/static/app.js` around the `drop` / `probe`
delta handlers).

**Expected:** It should not live in the replay strip. Move it into the Settings
panel alongside the other orbit-report toggles (auto-pop reports, last-turn FX,
cinematic title cards), persisted to localStorage so the choice survives
reloads, and gated to when the station UI is active.

**Repro:** Open `/watch.html?station=1&...`, load a replay — the button appears
in `.cc-replay-toolbar`.

---

## 6. ✅ (DONE, v1.7) Board state pops before its animation lands (drop / probe / harvest / trail)

**Status (v1.7):** Fixed across all four action effects — the board now holds its
pre-action look until the corresponding sprite actually lands, in the live
"PRAXIS BEGINS" cinematic, replay autoplay, and forward-step, in any perspective
(OBS or a single seat's fog view).

**Root cause:** `paintReplayFrameOntoMain` paints the fully-resolved end-state
frame first, then flies the delta animations over the top. Only a narrow
`step`-destination recolor (3 hard-coded colours, read from the *observer* cells)
was deferred; everything else painted instantly:
- **Harvester drop landing square** recolored to harvested (green/red → dark) the
  moment the frame painted — the drop branch deferred only the *revealed vision*,
  never the landing cell's own recolor (confirmed on a live session: landing
  `(12,11)` `rgb(63,185,80)` → `rgb(14,11,22)`).
- **Probe vision** popped its whole disk instantly: the reveal mask
  (`collectNewlyRevealedCells`) used a Euclidean **radius-2** gate, but a probe
  opens a **Chebyshev-4** square (~49 cells) — the entire outer ring was never
  masked.
- **Harvester walk** recolor + the freshly-laid **trail** glyph popped before the
  sprite arrived.

**Fix (`server/static/app.js`):**
- Added a general `_layTerrainStandin(cell, beforeCell)` that overlays a tile with
  its pre-action look (bg / fg / trail / terrain char) read from the **viewing
  seat's own** dense cells (`_frameSeatCells`), removed at the landing beat.
- `step`: stand-in on both the destination (recolor) and the departed cell (new
  trail), lifted on the 160ms step land.
- `drop`: stand-in on the landing tile, lifted at the lifter's deposit beat
  (`_onDeposit`, arc midpoint t=0.5), alongside the existing vision reveal.
- `collectNewlyRevealedCells`: dropped the radius gate — every fog→visible cell on
  the frame is masked (each frame is one unit's action), so the full probe disk
  (and drop reveal) stays dark until the streak/lifter lands.

**Symptom (original):** For a split second harvesters rendered in their landed
positions, resources showed as harvested, and probe vision opened before the
animations played — the board "moved" a beat before the sprites.

**Repro (original):** Watch a replay/live night with drops + probes and step/play
forward onto those frames.

---

## 7. ✅ (DONE) End-game report combat detail with per-player colour tallies

**Status (v1.6):** Full **attacker→victim kill-feed** shipped — the earlier v1.4
victim-side-only limitation is resolved. The engine now accumulates a per-season
`combat_attrib[stat][attacker][victim]` matrix at each event source during the
night sim (persisted in `json_state`; tiny) and `get_endgame_summary` exposes a
per-player `killfeed` (aligned to a fixed `combat_seats` order) plus a `personal`
ops block. The results screen renders the kill-feed **under each agent card**:
one row per stat with N slash-separated counts, each number in the **victim's**
seat colour (FPS-style; a player's own column is included since you can crush
your own probe). Stats: probes crushed, probes superseded, EMP'd probes, EMP'd
harvesters (distinct), chaff jams, harvesters damaged, harvesters lost (only
when your chaff cancelled the egress). Personal: probes launched, harvesters
dropped/recovered, red/green/blue harvested, EMPs/chaff/mines fired, and the new
**moves cancelled** (queued moves that resolved invalid/cancelled at execution).
Covered by `tests/test_v16_killfeed.py`. Attribution only populates for games
run after v1.6.

**Status (v1.4, superseded):** Implemented as a per-seat "// combat log" (see
#8). Each attrition category showed every seat's season total in that seat's
colour (the mine/enemy split). Limitation (now fixed): attacker attribution
(whose unit killed whose) wasn't recorded, so the coloured counts were
victim-side / own actions rather than a true attacker/victim breakdown.

**Symptom:** The end-game report is too thin. It doesn't break down what actually
happened in combat/attrition over the season: harvesters crashed, EMPed, and
destroyed (and the same for probes).

**Expected:** Add richer end-game stats. For each attrition category
(harvesters crashed, probes crashed, EMPed, destroyed, …) show **coloured
numbers per player** describing who did it to whom.

- Format like `1/1` where the split is by owner colour: the **first** number in
  *my* colour, the **second** in the **enemy** colour.
  - Example: if I crashed my harvester against the red player once, it reads
    `1/1` — the first `1` in my colour (my harvester lost), the second `1` in
    the enemy's (red) colour (their involvement / kill).
- Apply the same coloured-tally treatment across the categories: harvesters
  crashed, probes crushed, EMPed, (units) destroyed.

**Notes / to investigate:**
- Where end-game stats are aggregated (session/season summary) and what
  attrition events are already recorded per seat (crash / EMP / destroy).
- Decide the exact semantics of the `mine/enemy` split for each category so the
  two coloured numbers are unambiguous (attacker vs. victim vs. mutual).
- The end-game report renderer (client) needs per-seat colour styling for each
  number.

**Repro:** Finish a season with combat (crashes / EMPs / destroys) and open the
end-game report — the attrition breakdown + coloured per-player tallies are
missing.

---

## 8. ✅ (DONE, replay) Final game-resolve simulation step (last catapult launch + vault cleaning)

**Status (v1.4):** Implemented for the **replay** path + winner celebration.
- Backend already resolves the final settlement orbit on `day = cap + 1`
  (`catapult_by_day[cap+1]`, `station_obs_by_day[cap+1].post`, `SEASON_COMPLETE`).
- `buildReplayTicks` now appends a terminal **`resolve`** tick when the season is
  complete and `catapultByDay[cap+1]` has activity.
- `paintReplayFrameOntoMain` handles the `resolve` slot (sunset film + "SEASON
  RESOLVES" card), and `station.js` `osOnReplayTick` runs the DUSK stage then
  FIRES inline (no night frame follows): catapults launch, `+X` folds into the
  score, blue consumes, vaults settle to `post[cap+1]`.
- A full-bleed **winner celebration** overlay (`#cc-victor`, winner-colour sweep +
  "SEASON VICTOR") plays after the resolve beat, then the results modal opens.
  Results auto-pop is deferred until the finale completes (`triggerSeasonFinale`).
- **#7 combat detail** shipped alongside and was later upgraded in **v1.6** to a
  full attacker→victim kill-feed rendered under each agent card (see #7 above).
  The v1.4 "// combat log" (victim-side season totals in seat colour) is
  superseded by the per-card kill-feed + personal ops block.

**Follow-ups (v1.5 update):**
- ✅ **Live path DONE.** `osOnLiveResolve` (station.js) now plays the inline
  final-settlement animation (last launch + `+X` fold + blue burn + vault
  settle) on season-complete, and the winner celebration is deferred until it
  finishes (`handleLiveSeasonState`). The confetti-before-resolve ordering bug
  (both replay and live) is fixed — the celebration lands after the final scores
  are on the board.
- ✅ **Refine-preview UX DONE (part b).** Queuing a refine now optimistically
  removes consumed inputs and mints a white-bordered **"pending"** parcel across
  the vault tab, both composers, and the orbital vault; pending outputs are
  locked out of ship / re-refine. See RULEBOOK v1.5.
- ✅ **Final-orbit dead-refine RESOLVED (part a) — via the Final Refinery, v1.7.**
  The tier-weighted fire-sale plan was **rejected** (shipping is the game; the
  fire-sale stays `0.5 × purity`, no tier weight). Instead the **terminal orbit**
  now runs an uncapped **Final Refinery** (RULEBOOK §4.3.1): the 3-action and
  5-parcel refine caps are lifted, same-turn trace→vein→mass cascade is allowed,
  and refined parcels can ship the SAME turn via a new auto bid
  (`ship_catapult{auto:true}`) plus a one-click `refine_cascade{target_tier}`.
  So leftover BLUE finally has an aggressive use and the last-orbit refine is no
  longer dead. Engine + parser + resolver + UI + agent-view + heuristic/pilot_v2
  doctrine + `tests/test_final_refinery.py`. See `docs/RULES_PENDING_REVISION.md`
  #1 (marked shipped).

<details><summary>Original report</summary>

**Symptom:** At the very end of the game there's no dedicated resolve/cinematic
step, so the **final** orbital resolve isn't shown: the last catapult launch and
the vault cleaning (final depletion) aren't played out.

**Expected:** Add a final "game resolve" simulation step as the last beat of the
season that plays the closing orbital resolve — fire the **last catapult** and
run the **vault cleaning** (empty the vaults) — so the season ends on a complete,
visible resolution rather than cutting off before the final launch.

**Notes / to investigate:**
- The replay/cinematic pipeline (`buildReplayTicks` / `_playNightCinematic` in
  `server/static/app.js`, plus the station DUSK/praxis beats in
  `server/static/station.js`) — add a terminal resolve tick after the last night.
- Ensure it composes with the DUSK→praxis catapult ghost model (final launch
  fires, then vaults clean to empty).

**Repro:** Play/replay a full season to the end — the last catapult + vault
cleaning are never shown.

</details>

---

## 9. ✅ (DONE) H0/DUSK step + live-return bugs (v1.5)

**Fixed:**
- **LIVE after orbit landed on the previous dawn ("H25"), stuck.** LIVE now
  re-stages the DUSK/RESOLVE beat (loaded catapults, `+X` lines, blue lift) when
  the committed orbit's night is unplayed (`planning`) or the season closed,
  instead of snapping to the stale dawn tick and clearing the staging.
- **`+X` score sometimes never folded into the total.** `_praxisPending` is now
  armed on every DUSK staging path (forward, scrub-onto-DUSK, and live
  `osOnLiveDusk`), so the pending gain always folds at the next praxis frame.
- **Enemy blue bar always read "full."** Rescaled to ~300/pip fractional (see
  RULEBOOK v1.5) so 139 / 279 / 941 / 1358 blue read as distinct levels rather
  than all pinning to 5 pips. (Root cause: it counts the invisible blue bank; a
  4P game genuinely had seats holding 900–1350 banked blue.)

## 12. ✅ (DONE, v1.6) Probe trails missing in the live "PRAXIS BEGINS" cinematic

**Symptom:** Probe flight streaks didn't render during the live night cinematic
("praxis begins"), but scrubbing/replaying the same night showed them fine. EMP
streaks were unaffected.

**Root cause:** Probe launches are held back by the orbit→surface sequencing lead
(`_osOrbitLeadMs("probe")` = 1600ms, Option B default ON), so the streak is
scheduled via `setTimeout(_probeGo, 1600)`. The live cinematic loops held each
tick only ~620ms before painting the next tick (which repaints the board), so the
deferred streak fired against a stale/detached cell → nothing drew. EMP streaks
spawn immediately (no lead), so they were fine. The replay ticker already waited
`window._osPendingDwellMs` (`_maxLead + 1300`), which is why scrub/replay worked.

**Fix:** `_playNightCinematic` and `_playLiveTurnAnimations` (`server/static/app.js`)
now reset `window._osPendingDwellMs` before each tick paint and hold
`max(620ms, pendingDwell)` after — mirroring the replay ticker — so the deferred
probe streak completes before the next repaint.

## 10. ✅ (DONE, v1.9) Vault ↔ Orbital Vault ↔ actual content can still disagree

**Symptom (user, v1.4):** The VAULT tab, the orbital-station vault, and the true
game content disagreed at times, especially around the H0/DUSK transition.

**Root cause:** All three surfaces reconcile to the same authoritative hoard **at
rest** (tab + station both read the live inventory in play, or the per-tick frame
hoard reconstruction in replay) — *except* across a DUSK shed. The DUSK **forward**
beat renders the pre-orbital vault and then animates it down by popping only the
**red/green catapult parcels** (`_scheduleDepart`). Its settle callback re-synced
**only the rival bars** to the post-orbital snapshot; the observed vault was left
at whatever the shed produced. Anything the shed doesn't model — **burned BLUE
fissile, a tier-priority overflow eviction, or a refine's byproducts** — left the
station diamond over-counting versus the VAULT tab (which reconstructs
authoritative POST on the next tick). Live DUSK (`osOnLiveDusk`) had the identical
gap and no reconcile at all.

**Fix (`server/static/station.js`):**
- New `_osReconcileObservedVaults(preferLive)` snaps every **observed** vault back
  to the authoritative post-orbital hoard (rivals still get the bar estimate).
- Replay DUSK settle now calls it (was rival-bars only), and live DUSK schedules
  it once the shed dwell has played (`preferLive` reads the server's true
  post-orbital `lastLiveInventory`, since no night frame exists yet to
  reconstruct from). Both reconciles ride `_vaultSettleTimers`, so a scrub/resolve
  clears them cleanly.

**Audit tool:** `window._socVaultAudit()` (in `app.js`) prints, per active seat,
`tab / station / authoritative` counts and warns on any drift — a one-call repro
capture (`[vault-audit] replay day 3 (tick 42): diamond disagrees …`) for any
residual desync.

## 11. ⏳ (INVESTIGATED) 4-player Snowflake praxis is slow

**Finding:** The praxis/night simulation itself is fully **in-memory** — there
are **no per-hour / per-seat Snowflake writes** in the sim loop, and the
`auto_fire_bot_seats` per-seat full-save regression was already fixed (v0.9.8,
one batched save per TRANSMIT). The 4P slowdown is **persistence payload
amplification**, not un-batched per-step sim writes. Prioritised culprits:
- **P1:** ✅ **DONE (v1.5).** `last_night_replay` was serialized **twice** every
  night — inside the `json_state` MERGE (`session.to_dict()`) *and* into
  `SOC_REPLAY_FRAME`. Fattest on 4P. `_save_session_row` now pops
  `last_night_replay` from the persisted blob (frame table stays authoritative;
  `to_dict()` and its in-memory round-trip test are unchanged). Verified nothing
  reads it back after a reload — `get_replay` and evals both read the frame
  table.
- **P2:** Replay frames carry **four** dense per-seat cell grids
  (`cells_player_p1..p4`) → ~2× SQL text / PARSE_JSON vs 2P. Fix: store one
  shared grid + per-seat fog deltas. *(Deferred — schema/format change, not
  batching; the HTTP wire already strips these aliases.)*
- **P3:** ✅ **DONE (v1.5).** `append_agent_invocation` was **unbatched** (SELECT
  MAX(seq) + INSERT per bot → ~6 round-trips for 3 bots). Added
  `append_agent_invocations([...])` to every store (Snowpark = one MAX + one
  multi-row INSERT with `PARSE_JSON` in the outer SELECT; file store batches the
  disk write; composite groups by session). `_persist_bot_fanout` now calls it
  once → 4-seat fan-out drops from ~6 round-trips to 2.
- **P4:** `json_state` grows with players × days (`station_obs_by_day`,
  `orbital_activity_by_day`, memory/probe maps) and is re-MERGED wholesale.
  *(Deferred — blob restructure, larger change.)*
- **P5:** extra `get_session_status` hydrate after every submit. *(Deferred —
  changes the server response contract.)*

P1 + P3 (the highest value / lowest risk batching wins) are shipped. P2/P4/P5
remain — they're structural (schema, blob layout, HTTP contract) rather than
batching, so they're tracked separately.

## 13. ✅ (DONE, v1.17) Multiplayer: the night cinematic depended on which seat you were, and on your tab

The v1.7 work (#3, #4) made the *waiting* seat resolve at all. These are the
three ways it still ended up watching a different turn from the seat that
happened to resolve the phase.

**Symptom (reported):** "when players submit orbital orders … the moves
cycle, and they are allowed to submit moves, but the night begins message
and the heat dissipating animation never trigger, so the image is still
shimmering and the view of the map hasn't advanced to the night stage."
Separately: "in some multiplayer games the end state of the turn is shown
before the simulation animation."

**Root cause A — the orbit night-opening was inline in the submit
handler.** `NOX n BEGINS` + the sunset sweep lived inside the orbit-submit
success path, *after* the `!body.orbit_resolved` early return that parks a
non-resolving seat in the committed-wait frame. So only the seat whose
submit resolved the phase ever ran them. The waiting seat's poller went
straight to `pullAllMaps({playFx, stageOrbitBeat})`, and an orbit resolve
emits no night frames, so there was no cinematic either — it just snapped
to the resolved board. Worse, the no-cinematic branch re-applies heat with
`_heatApplyInstant(host, 0.52)` whenever `_heatPhase === "hold"`, and only
the sunset sweep clears that phase — hence "still shimmering" on a board
that had supposedly moved to night. This was **always**, not just when
backgrounded; the player's "or maybe always" was right.

**Root cause B — the cinematic trigger was a frame diff, so any refresh
could eat it.** `refreshNightReplay` computed `newDayLanded` by comparing
incoming frames against the ones the client already held, which makes the
animation a side effect of *fetch order*. `closeReport()` fires a plain
`pullAllMaps()` on close specifically to pick up "state that landed while
it was up" — including the opponent's just-resolved night. Once it had,
the real cinematic pull saw nothing new and fell into the hard-cut branch.
Two seats closing the orbit report in a different order therefore saw
different turns, which is the "end state before the animation" report.

**Root cause C — a backgrounded tab lost the night outright.**
`pollLiveSync` returns early while `document.hidden` (correctly — rAF is
throttled, so a cinematic started there would stall half-played), and it
treats its first sample as a baseline it never acts on. A player who
submitted and switched away had *no* baseline, because every poll since
had returned before seeding. The first poll after they came back sampled
the already-resolved state, recorded that as the baseline, and returned.
The transition was consumed without ever being played.

**Fix (`server/static/app.js`):**

- `playOrbitNightOpening(day)` — extracted, and called by **both** the
  resolving seat and the live-sync poller, in the same order (card, sweep,
  then the pull). The poller runs it only on an orbit resolve
  (`prevPhase === "orbit"`), since a night resolve is carried by the
  cinematic proper.
- The cinematic gate is now `_lastCinematicDay`: day N animates exactly
  once per seat, whoever refreshed in between. Loads that must *not*
  animate (new game, joining a seat, opening a saved season) pass
  `claimCinematic: true`; the incidental `closeReport()` refresh
  deliberately does not, so it can no longer steal a pending night.
- The start tick comes from `findFirstCinematicTickOfDay(day)` rather than
  a held tick count, which was only correct if nothing else had fetched
  first. It also matches the synthetic DUSK tick (day lives on the tick,
  not a frame) so the orbital-resolve beat isn't silently skipped.
- `seedLiveSyncBaseline()` records the pre-resolve state when the wait
  starts, ignoring `document.hidden` because it only records and never
  paints. A hidden tab now *defers* the night instead of losing it, and a
  `visibilitychange` listener polls on refocus so it plays immediately.

**Tests:** `tests/test_live_cinematic.py` (18) pins each mechanism — there
is no JS runner, so these scan `app.js` the way `tests/test_seat_links.py`
does.

## 14. ✅ (DONE, v1.19) A crushed probe left TWO ghosts of the harvester that killed it

**Symptom (reported):** "if a harvester runs over your probe you are left
with two ghost images of the harvester, not one, as the probe loses life."

Reproduced exactly: the victim's echo showed `harvester_p1` at both `10:8`
(where it stood) and `9:8` (where it had stepped from). Both render as
echo cells, both carry a harvester glyph, and nothing distinguishes the
real one — so the probe's owner is handed a board that lies about where
the enemy is, in the one moment they paid a probe to find out.

**Root cause (`sea_of_colours/game/session.py`).** A live probe refreshes
its **whole vision disk** on every hourly pulse (`_pulse_vision_intel`),
which is what normally retires a sighting: the harvester moves on, the
next pulse re-snapshots the vacated cell as empty, and the old glyph is
gone. The death path (v1.8, "the probe witnesses its own killer") only
refreshed the **single cell the probe died on**. So the echo was stitched
from two different instants — the death cell as of the crush, every other
cell as of the last pulse before it — and because the observer is now
dead, no later pulse could ever reconcile them. The stale glyph became
permanent for the rest of the night.

Worth noting the bug needed *both* halves to appear: the sighting on the
approach (correct at the time) and the fresh sighting at the grave. That
is why it only shows up when a harvester walks in from inside the probe's
own disk — i.e. exactly the crossing the probe existed to watch.

**Fix.** `_freeze_final_probe_echo(probe)` takes the probe's last look
across its entire vision disk, which is precisely the work the hourly
pulse would have done had it survived the hour. One coherent instant, one
harvester. The final echoes are also frozen *after* every probe crushed in
that step is off the board, so two probes dying together can no longer
record each other as still standing.

**Tests:** `tests/test_probe_death_echo.py` (5). They pin the invariant
("the killer appears exactly once"), not the mechanism, plus a guard that
the setup really does sight the harvester on approach — otherwise the main
test would pass vacuously. Verified against the old behaviour in place:
two ghosts before, one after.

## 15. ✅ (DONE, v1.19) A weapon launch did not cost the launcher its hour

**Found by audit,** not by report: the question was "what happens when two
chaffs execute in the same hour?" (§4.9.5). The rule and the engine agree on
the chaff *window* — but the audit found a hole underneath it that needs no
chaff at all.

**Symptom.** A seat could fire a weapon **and** act again in the same hour,
and the extra action damaged harvesters. Minimal case: p1 queues
`emp_launch` then `step`, p2 queues the crossing `step`. Hour 1 emitted
*both* an `emp_launch` frame and a `collision_swap` — and **both**
harvesters came out `damaged`. So it wasn't cosmetic: fire an EMP and still
cripple the harvester walking past you, for one slot.

**Root cause (`sea_of_colours/game/simulator.py`).** EMP and chaff resolve
in the pre-hour phase, which consumes the launcher's slot and records the
seat in `_preempted_seats_this_hour` so the main dispatch skips it. The two
collision pre-passes — pass-through swap (§3.6) and simultaneous drop
(v0.9.10) — run between those two points and peek every seat's *next*
queued move, guarded only by `applied[p] >= MAX_MOVES`. For a pre-empted
seat that next move belongs to the **following** hour, so the pre-pass both
granted a second action and staged a collision between two moves that were
never simultaneous.

**The chaff case is the worse one.** When *every* seat flares in the same
hour they are all launch-hour immune, which is the sole condition that opens
the pre-pass gate (`all_chaff_immune`) while chaff is active. The swap that
leaked through then consumed the very moves the carry-over hours existed to
jam, so hours N+1/N+2 emitted **no `chaffed` frames at all** and the
launchers dodged the self-jam §4.9.5 makes them pay:

> If two seats chaff in the same hour, both fire (each pays cost) and both
> are immune for that launch hour, then both are jammed for the carry-over
> hours.

In other words a mutual flare was strictly *cheaper* than a solo one — the
opposite of the intended trade, and exactly the kind of thing an agent
harness will find and exploit.

**Fix.** Both pre-passes take `skip_seats` and ignore seats already
pre-empted this hour. The invariant is the one §3.10 already states — one
applied action per seat per hour — it just wasn't enforced on this path. The
gate itself is left alone: with the skip in place `all_chaff_immune` can no
longer resolve anything (triggerers are always a subset of the pre-empted),
so no collision semantics change for seats that acted normally.

**Tests:** `tests/test_preempt_slot_integrity.py` (5), including a guard
that a plain weaponless swap still collides — without it the others would
pass by simply disabling the mechanic. Verified against the old behaviour by
stubbing the skip back out: 4 fail, the guard passes.

## 16. ✅ (DONE, v1.19 / RULEBOOK v1.14) Chaff could not stop a weapon, and could be chained into a lock

Same audit as #15, and the same underlying shape: the pre-hour phase
resolved launches before the chaff gate was ever consulted. Here it was not
just a slot-accounting slip — it changed who wins a weapon exchange.

**The RULEBOOK contradicted itself,** which is why this survived so long.
§4.9.5: on a covered hour "**every** seat's action ... is cancelled". A
launch is an action. But §4.9.3's within-hour ordering list put *EMP-launch
pre-emption before chaff pre-emption*, which grants a salvo priority over a
same-hour flare. The engine implemented the ordering list. Ruled in favour
of §4.9.5 (see RULEBOOK v1.14).

**Symptom A — a salvo flew out of a fully jammed house.** Both launch types
were pre-empted in one seat-ordered pass, so whichever seat the loop reached
first simply fired. Measured: p1 flares at H1 (window 1..3), p2's EMP
queued at H2 launches anyway and spends its charge. "Answer their chaff with
an EMP" was a reliable counter that no rule granted.

**Symptom B — chaff chained into a lock.** A flare fired *inside its own
window* fired anyway: it re-armed the window (1..3, then 2..4, then 3..5)
**and** re-entered `chaff_triggerers_by_hour`, which re-granted the launcher
launch-hour immunity. So `N` flares jammed the opponent for
`N + CHAFF_DURATION_HOURS - 1` consecutive hours while the chaffer was never
jammed once. With enough blue that is a whole night of denial, and it is the
kind of edge an agent harness finds by search long before a human does.

**Fix.** `_pre_hour_phase` resolves flares first, then salvos, and skips
both on an hour already covered by a window opened earlier. A cancelled
launch falls through to the main dispatch: slot burned, `tag="chaffed"`, and
crucially **the munition is not spent** — a house that never fired has not
spent the round, so the flare or charge stays in `weapon_stock`.

**What deliberately did NOT change.** Two flares on the *same* hour still
both fire and both pay, so one is wasted: neither seat is inside a window
when the hour opens, and the effect is global and identical. That symmetry
is what keeps mutual chaff strictly worse than solo chaff, so the weapon
can't be spammed as a safe mutual stall. Now stated explicitly in §4.9.5
rather than left as an emergent accident.

**Fan-out:** RULEBOOK §4.9.3 (ordering) + §4.9.5 (prose) + v1.14 changelog
and header bump; `manual/manual.js` and `manual/index.html` chaff panes. V12
was left alone on purpose — its doctrine only reads chaff *defensively* ("a
jam cancelled your slots, re-time it"), which is still true, and
`tabula_v12` is the baseline forks are measured against. The offensive
reading is the hackathon's own exercise, and this rule is now the thing
attendees' weapon logic has to respect.

**Tests:** `tests/test_chaff_precedence.py` (8). Verified against the
original simulator with a restore trap: 9 of the 13 new tests across both
files fail there, and the guards (unopposed salvo still flies, two flares
still both fly) pass — so the suite is not just asserting "weapons are
broken".

## 17. ✅ (DONE, v1.19) Probe-launch markers could outlive their probe forever

Raised as "markers should be removed after three nights no matter what", and
the useful part of the answer is that **the rule already existed** — v1.2
specifies exactly that, so no rulebook change was needed. What was missing
was the sweep actually running:

> **Aurora sweep added to `decay_probes`.** At **every Aurora**, after
> expiring live probes by lifetime, the engine also sweeps `probe_intel` for
> any `via="probe_launch"` marker whose probe is no longer alive but has
> reached its natural expiry date. (RULEBOOK v1.2)

Design intent recap: a probe killed by crush / collision / supersede stays
in the non-witnesses' intel deliberately (they saw it land, not die), and the
probe's scheduled expiry — `SOC_PROBE_LIFETIME_NIGHTS`, default **3** — is
the *only* bound on that. So if the sweep misfires there is no other backstop
and the marker is simply permanent.

**Hole A — the sweep was behind an early return.** `decay_probes` bailed with
`if not expired: return []` *before* the sweep, so markers only cleared on an
Aurora where some **unrelated** live probe also hit its lifetime. Measured
with a single secretly-killed probe and nothing else on the board: marker
still present on day 6 and every day after. Add one decoy probe that expires
on day 3 and the same marker cleared correctly on day 3 — the cleanup worked,
it just fired on someone else's schedule.

**Hole B — merged markers were skipped.** The sweep matched
`via == "probe_launch"`. A launch onto a cell the viewer had *already*
scouted is merged onto that richer terrain echo (v1.11) and leaves only a
`probe_launch_glyph` overlay with `via` untouched, so the sweep walked past
it. That is precisely the case the v1.11 comment predicted would "linger
forever as a permanent ghost": it was fixed for the death path
(`_clear_probe_launch_markers`) and never for the scheduled path. Measured:
glyph still rendering on day 5 even though the sweep had run on day 3.

**Fix.** The sweep is now `_expire_stale_launch_markers(k)`, called
unconditionally at every Aurora, and it recognises both marker shapes: a bare
`via="probe_launch"` entry is deleted, while a merged entry has only the
overlay stripped (glyph, launch day, the dead probe's occupant row) so the
viewer keeps the terrain snapshot they earned. Marker dating prefers the
`asset_records` deploy day and falls back to the marker's own
`probe_launch_day` / `day_seen` for hydrated state, instead of the old
"no ledger row → treat as stale" shortcut.

**Tests:** `tests/test_launch_marker_expiry.py` (8), including the v1.2
guards that must NOT regress — the marker survives every night *before* its
scheduled dawn, a live probe's marker is never retired, and with decay
switched off markers stand forever because there is no schedule to clear
against. Verified against the committed engine: 4 fail there, the 4 guards
pass.

## 18. ✅ (DONE, v1.19 / RULEBOOK v1.15) A probe could die with no graphic at all, and an incumbent died with the wrong name on it

Two problems on one square, found from "there is currently no graphic for
superseding a probe".

**The graphics.** `crushed_probes` is the replay payload that drives the
pixel-splash — eight squares flying out of the cell in the dead probe's seat
colour. It was only ever filled by `consume_probes_at`, the harvester crush
it was built for. All three §3.16 paths in `spawn_probe` wrote a log line and
nothing else, so:

- a **superseded** probe blinked out with no cue that the arriving probe had
  killed it; and
- a **mutual annihilation** rendered *nothing whatsoever* — not even the
  incoming streak. The animator derives a landing by diffing frame entity
  snapshots, and a probe destroyed on arrival is created and destroyed inside
  one move, so it never appears in one. Two seats could burn a probe each on
  the same square and the board would not flicker.

Fixed by filing a record on every path (`_queue_probe_death_fx`, carrying a
`reason`), and by synthesising the landing delta from that record when no
surviving probe can be diffed out. No new visuals — the existing streak,
splash and ripple, with the streak's existing per-probe random stagger doing
the "series of landings" look. A doomed probe skips the ripple only, because
the ripple is the vision pop and an annihilated probe grants no vision.

**Then the splash timing, which was wrong for every crush, not just the new
ones.** The tick-level FX pass fires the instant a tick paints, while the
unit that did the crushing is still visibly in flight — so the burst popped
in isolation with nothing arriving to explain it. The first pass at this
moved only the probe-on-probe case into the streak's landing callback and
left harvester crushes where they were, on the false grounds that "the
crushing unit's own animation already puts it on the beat". It does not:
`runReplayAnimationsTick` only *schedules* the ghosts, so the FX loop right
after it still runs at t=0 — ahead of a step slide, a lifter's deposit, and
(with orbit sequencing on) a ~2.6s launch lead.

**And two faults in the pre-landing mask itself**, both of which broke the
one rule the mask exists to enforce — the board must not move before the
sprite arrives.

- *The mask leaked the tile under it.* Matching it to `--fog-bg` fixed the
  black hole but that colour is **96% alpha** — fine on a fog cell, which
  has nothing beneath it but the board, and wrong as an overlay on a cell
  the frame has already painted revealed. The remaining 4% let a RED seam
  glow faintly through before the probe had found it: the sign bleeding a
  beat early, which is exactly the intel the mask withholds. Now stacked as
  the fog tint over `--bg`, which composites to the same colour a fog cell
  shows with no transparency left.
- *One probe's landing opened another probe's vision.* The probe branch
  revealed the shared `probeMaskedCells` set rather than its own cells, so
  the first streak down lifted every in-flight probe's mask. `spawnProbeTrail`
  jitters each start by up to 200ms precisely so simultaneous probes land
  staggered, so the second probe's ground opened while it was still in the
  air — most visibly with two seats onto one square (§3.16). It now calls
  `revealMaskedCells(pendingMasks)`, the local-array helper the harvester
  drop already used; the shared set stays as the cancellation ledger.

**The reveal mask also un-saw ground the viewer already held.**
`collectNewlyRevealedCells` asked "was this cell *fresh* before?", which puts
a remembered tile in the same bucket as pitch fog — so every stale tile and
probe echo inside an incoming probe's disc got the fog block dropped on it
and blinked out, as though the probe were un-seeing the ground on its way in.
Only a genuine fog → visible flip is fog-masked now. A stale tile is instead
*held at its remembered look* (dimmed to `--opa-stale`, since the dimming
normally comes from `.cell--stale` on a cell that is fresh in this frame and
would otherwise show the memory at full live brightness), and promoted to
live on the landing beat with everything else.

**The victim also had to still be standing when its killer arrived.** The
replay paints the resolved end-state frame and animates deltas over it, so a
doomed probe was already erased the instant the tick painted — it blinked out
while the harvester was still sliding toward it, and the splash then went off
over a square that had been empty for a second. Fixing *when* the splash
fires did nothing for this on its own. `_layDoomedProbeStandins` now holds
each victim on its cell from the moment the delta is scheduled, and the same
landing hook that fires the splash removes it, so the probe is gone in the
beat it bursts rather than long before. It only stands in for a probe that
was on the board in the previous frame — a probe born and destroyed inside
one move (the arriving side of a §3.16 annihilation) was never visible, and
its arrival is already the incoming streak. Verified against the reel: 7 of
its 8 probe deaths take a stand-in, and the one that doesn't is exactly that
case.

A third, separate hole: **a seat could not see its own probe die.** A probe
killed on arrival grants no vision, so the cell paints as fog for the seat
that launched it, and `playProbeCrushFx`'s fog gate then swallowed the only
feedback that seat had — streak in, nothing. The gate now yields when the
viewer owns the dead probe. Nothing leaks: that seat picked the target and
knows the probe is gone. Another House's probe dying on a cell you cannot
see stays hidden, because that *would* tell you they had a probe there.

Every branch now fires its own splash from its own landing hook — `step` on
the ghost's `transitionend`, `drop` at `_onDeposit`, `probe` at the streak's
touchdown — scoped to the cell it landed on, since two units can crush two
different probes in the same hour and an unscoped call from whichever landed
first detonated the other's victim early. Hooks stake their cell in
`crushClaimedCells` as they are scheduled, and the tick-level pass now fires
only what nobody claimed: a scrub (no animations run) or a delta skipped
outright, e.g. an enemy action the viewing seat cannot see. Those have no
beat to be in time with. `_onDeposit` is also installed unconditionally now
— it used to be skipped when a drop revealed nothing and recoloured nothing,
which is exactly the case where a crush was the only thing left to sequence.

**The rule.** §3.16 was explicit that two or more probes landing on a square
in one hour all die, and **silent** on an older probe already standing there.
The engine answered by accident: resolving seat by seat, the first arrival
superseded the incumbent, then the second annihilated with the first. Body
count right, attribution wrong — the incumbent was ledgered
`probe_superseded` and the `probes_superseded` kill-feed credit went to
whichever seat the resolver reached first, a seat that lost its own probe in
the same instant.

Ruled (RULEBOOK v1.15, new §3.16(c)): the incumbent dies as a **collision
casualty** and **nobody** is credited a supersede — supersession is an act by
a surviving newcomer, and when the arrivals wipe each other out nobody took
the cell. Two rivals clearing an established probe therefore pay both their
own probes for it. `_finalise_probe_contest` re-files the provisional
supersede once a second same-stamp arrival proves the cell was never held, so
ledger and kill-feed no longer depend on seat order. Also written down at
last: the same-hour latecomer sweep (new §3.16(d)) shipped in v0.9.17 citing
a "§3.16 E4" that had never existed in the RULEBOOK.

**Tests:** `tests/test_probe_death_fx.py` — 14 cases covering all three
paths, the incumbent ruling (2-, 3- and 4-way piles), the guard that a lone
newcomer *does* still earn its supersede, and the guard that an unopposed
launch splashes nothing.

## 19. ✅ (DONE, v1.19) A dead probe kept marking a square you could see was empty

**Symptom:** a probe glyph sat on a cell that the owner had clear sight of
and that plainly held nothing. It never aged out on its own; only a later
event on the same cell cleared it.

**Root cause:** two rules that are each correct on their own, colliding.
§3.15 stamps a **launch marker** on the target cell so a seat can see where
its own probe went, and that marker is deliberately sticky (it survives
losing sight of the cell — that's the point of it, and it has its own
3-night expiry). §3.16 kills probes on collision and supersession. Nothing
connected the two: when a seat **witnessed** its own probe die, the death
was drawn, but the launch marker underneath it was left in
`probe_intel`. The seat was therefore looking at a marker for a probe it
had just watched be destroyed.

The earlier crush path didn't show this because `_freeze_final_probe_echo`
already rewrites the victim's echo on that route. Widening that helper to
cover the §3.16 deaths was the first attempt and was wrong — it re-froze
the whole vision disk, handing the dead probe's owner a free snapshot of
everything the probe *could* have seen, which is unearned vision.

**Fix (`game/session.py`):** new `_forget_probe_marks_at`, which takes a
cell and a set of just-died probe ids and removes **only** those probes'
traces (occupant entries, `probe_launch_glyph`, `via`, and the glyph
fields when nothing else claims them) from every player's `probe_intel`.
It grants no vision — it only retracts a claim the engine now knows to be
false. Called from `spawn_probe` on both the collision and the supersede
paths. `_freeze_final_probe_echo` stays where it was, on harvester crush.

**Tests:** `tests/test_probe_death_fx.py` — a superseded probe stops being
painted on its square; a multi-way pile-up leaves no mark anywhere; a
probe that *survives* keeps its launch mark (the guard against
over-retracting); a death elsewhere doesn't touch an unrelated square.

---

## 20. ✅ (DONE, v1.19) The day-2 harvester collision exploded three seconds before impact

**Symptom:** on a simultaneous drop, one harvester detonated and lifted off
while the other was still visibly falling — the explosion, damage numbers
and lift-off all played before the two craft met.

**Root cause — two faults, not one.** Both are sequencing, not logic; the
engine ordering was right throughout.

1. *The explosion.* Orbital arrivals animate with a long run-in
   (`_OS_LEAD_MS` — 2600ms for a drop) so the craft has somewhere to fall
   from, but `playCollisionFx` fired from the tick loop at frame-paint
   time. Detonation and contact ran ~3s apart.
2. *The departure.* `pickup` had **no lead at all**, so a recovery began
   at tick paint while the inbound drop was still held by its 2600ms
   lead: the damaged harvester lifted off and was clear of the board two
   seconds before the impact that damaged it was drawn.

Fixing (1) alone left the reported symptom untouched, because the thing
being complained about was (2). Worse, the check that would have caught
it looked in the wrong place: a replay **tick bundles several frames**
(here hour 3's collision and hour 4's recovery), and they all animate
concurrently, each on its own lead. A pickup asking its own
`curFrame.collisions` sees nothing, because the collision belongs to a
different frame of the same tick.

**Fix (`server/static/app.js`):**
- The collision ring is **claimed** by the arrival animation rather than
  raced by the tick loop — `runOrbitalArcAnimation` installs
  `_fireCollision` on `delta._onDeposit` so it goes off at the bounce
  midpoint, with `collisionClaimedCells` preventing a double fire.
- `runReplayAnimationsTick` now censuses collisions across **every frame
  in the tick** into `tickCollisionCells`. A pickup off a tile in that set
  is held until `_osCollisionContactMs()` (inbound lead + the 550ms arc
  midpoint), so the impact is drawn before the recovery starts.
- The held unit is stood back onto its tile from paint time
  (`_layPickupStandin`, handed to the deferred arc via `_preStandin`).
  Without it the harvester blinked out at paint and the collision landed
  on an empty square — the first attempt at this fix did exactly that.

**Verification:** `scripts/_fx_census.py`, which supersedes the two
narrower harnesses that missed this. Tick 10 of the reel now reads:
inbound ghost +2652ms, impact +3183ms, unit lifted +3766ms — cause before
effect, with no blink-out.

**Note on the earlier harnesses.** `_fx_collision.py` timed only the
explosion and never asked when the harvester sprite left; `_fx_probe.py`
sampled a hardcoded cell list, so anything happening elsewhere was
invisible. Both reported "fixed"/"not reproducible" on faults that were
live. `_fx_census.py` diffs every sprite on the board, by glyph **and
colour** (a probe superseded by a rival is `·` before and after, so a
glyph-only diff calls a change of owner "no change").

---

## 21. ✅ (DONE, v1.19) The doomed probe vanished the instant the hour opened

**Symptom:** a harvester dropping onto an occupied square crushed the probe
on the right beat — the burst was correctly timed by #20's fix — but the
probe *itself* left the square the moment the hour started, so the crush
detonated on ground that had already been empty for three seconds.

**Why the census said it was fine.** `_layDoomedProbeStandins` was doing
its job: the stand-in node was in the DOM, attached to the right cell, and
`getComputedStyle` reported it visible for the full hold. Every DOM-level
check passed. `.harvest-terrain-standin` — the layer that holds the tile's
*terrain* still while a drop is in the air — is `position:absolute;
inset:0; z-index:4` with an opaque background, and `.entity-overlay`
carries no `z-index` at all. The terrain hold was painted straight over
the probe. Present, visible, and behind an opaque rectangle.

This is the third time in this bug family that a harness reported "not
reproducible" on a live fault (see the note under #20). The lesson is
narrower than "the harness was too narrow": **presence in the DOM is not
presence on screen.** Anything asserting a sprite was seen has to end in
pixels.

**Fix (`server/static/app.js`, `server/static/styles.css`):**
- `.entity-overlay--doomed` at `z-index: 5`, so a unit deliberately held on
  its tile sits above the terrain hold rather than under it.
- The stand-in is now built from the probe the board **was actually
  painting** a beat ago — `entityOverlayHtml(before.entity)` off the
  previous frame's cells — instead of a hand-rolled `·`. The old dot had no
  lifetime rings and no profile colour, so even unoccluded it read as some
  other, fainter thing appearing rather than the probe staying put.

The supersede path (`§3.16(a)`) lays no terrain stand-in, so it was never
occluded; it picks up the markup half of the fix only.

**Verification:** `scripts/_fx_pixels.py` — screenshots one cell every
250ms through a tick and contact-sheets the result, deliberately ignoring
the DOM. Before: the cell is bare from +0ms. After: the probe is on screen
at +0ms in its real markup, holds to +2000ms, and is replaced by the
harvester and its crush burst at +3000ms.

---

## 22. ✅ (DONE, v1.19) V12 played every Snowflake season with no cross-night memory

**Status (v1.19):** Fixed. `SOC_AGENT_MEMORY` and `SOC_AGENT_BINDING` are now
part of the standard deploy and part of the session wipe.

**Symptom:** V12 played visibly worse in the browser than in the headless
matchup runner it was tuned against — repeating plans it had already seen fail,
re-picking cells it had just been denied, and losing the thread between nights.
Its own THINK text would name a cause one night and ignore it the next.

**Root cause:** two independent gaps that hid each other.

- When orchestrator_2 landed, `SOC_AGENT_MEMORY` was **relocated** out of
  `snowflake/soc_schema.sql` into
  `sea_of_colours/orchestrator_2/snowflake/orchestrator_v2_schema.sql`. That
  file's header says to deploy it via `scripts/deploy_soc_schema.py` — but the
  deployer only ever shipped three files, all from `snowflake/`. Nothing
  created the table, on any account. `SOC_AGENT_BINDING` was missing for the
  same reason. Confirmed against the live account: 12 `SOC_*` tables, neither
  of these among them.
- All three of V12's memory modules — the strategy journal
  (`tabula_v12/_v7/memory.py`), `hazard_memory.py` and `frontier.py` — keep a
  **process-local dict** and mirror it to that table **best-effort inside bare
  `except` blocks**, with the rehydrate-on-empty read equally forgiving. A
  missing table therefore produced no error, no log line, and no visible
  degradation in any test.

**Why only live play suffered:** `scripts/run_matchup_v12.py` does
`os.environ.setdefault("SOC_BACKEND", "memory")` and plays a whole season
inside one process, so the process-local dict carries the full journal and the
mirror is irrelevant — which is exactly the configuration V12 was validated in.
A live season runs for hours on Snowflake, where that dict is the *only* copy;
the moment the server process is replaced the memory is gone for good, because
rehydration hits a table that does not exist and swallows the failure.

**Fix:**
- `scripts/deploy_soc_schema.py` now deploys `orchestrator_v2_schema.sql`
  between the schema and the views (it is `CREATE TABLE IF NOT EXISTS`, so it
  is non-destructive and safe to re-run).
- `SnowparkSocStore._SESSION_TABLES` gains both tables, as the SQL file's own
  comment had been asking for. Both key on `session_id`, so the existing wipe
  predicates work unchanged; without this a reused session id would inherit a
  dead game's journal.

**Verification:** `scripts/_check_agent_memory.py` writes a journal entry
through V12's own `memory.save_entry`, clears the in-process store to force the
restarted-server path, and reads it back through `read_recent` — 0 rows before
the fix, round-trip PASS after. Full suite 1051 passed / 1 failed, the failure
being the pre-existing `two_seams_choose_one` eval debt.

**Verified in play (session `46615fbd`, V12 vs RED_HARVEST):** the server was
killed at day 6 with the journal held only in-process, restarted empty, and the
season resumed and completed. Days 1–6 hydrated back out of Snowflake and day 7
plus `hazard_cells` / `spent_blue` / `enemy_probe_disk_history` were written by
the new process. Before this fix that restart erased the season's history
silently. `read_recent` was also confirmed against the real season data from a
fresh process with an empty cache.

**Not established:** whether this is what collapsed the day-3 plan on session
`e75dbdc` (`sanitized=9 … moves=1`). That night has not been isolated. Note
also that a season played on one uninterrupted process was never affected —
the process-local cache covered it — so this fix changes behaviour only across
a restart.

---

## 23. ✅ (DONE, v1.20) The Snowflake season picker crowned the loser

**Status (v1.20):** Fixed. `SnowparkSocStore.bulk_session_scores` folds the
persisted parcels through `compute_player_score` like every other store; nothing
user-facing scores off the SQL view any more.

**Symptom:** the season picker and the end-of-season card disagreed about the
score, and on at least one finished season they disagreed about **who won**.
Serpens_Lattice (`46615fbd`, V12 vs RED_HARVEST) read p1 1436 / p2 1853 in the
picker against a true p1 1527 / p2 1418 on the results screen — opposite
winners.

**Root cause:** the scoring rules existed in two places. `compute_player_score`
(`game/session.py`) is the canonical one, and its docstring promises "the
standings, the HUD's shipped-score line, and the end-of-game results screen can
never disagree". The Snowflake store did not call it: `bulk_session_scores`
selected a precomputed `score` column out of the `SOC_SESSION_STANDINGS` view,
which reimplements scoring in SQL as

```sql
SUM(LEAST(255, GREATEST(0, COALESCE(origin_purity, 0))))
```

That is a raw purity sum, and it diverges twice:

- **No RED tier multiplier.** The real score is tier-weighted, which is why
  engine scores carry fractions (`1526.75`) and the view's never did.
- **GREEN is credited instead of charged.** Since v1.13 green is auto-disposed
  each orbit and the disposed parcels are appended to `SOC_SHIPPED_PARCEL`
  carrying their GREEN origin tile — deliberately, so the bulk scoreboard can
  charge them with no extra column (§4.7). Green is always purity 255, so the
  view paid **+255** for each one where the scorer charges
  **−100**: a 355-point error per parcel. RED_HARVEST had jettisoned four, so
  55% of its phantom 1853 was green it should have been penalised for.

**Why it went unnoticed:** only the Snowflake store had the duplicate. The
memory and file stores both call `compute_player_score`, so every offline
season, every headless matchup and the entire test suite agreed with the results
screen. The invariant only broke on a live Snowflake game, where the two
surfaces are rarely read side by side.

**Fix:** `bulk_session_scores` now issues three grouped reads (phases, shipped,
hoard) and scores them in Python through `compute_player_score`, unwrapping each
row's VARIANT `payload` so the scorer sees the same parcel dict the live session
holds — including the catapult-stamped `effective_purity` / `score_tier`. Still
no per-session hydration. Seats come from the parcel `owner` column, so it stays
N-seat aware. The view is left in the schema for ad-hoc SQL.

**Verification:** `tests/test_snowflake_standings_parity.py` pins the parity
offline against a fake session, asserts a disposed GREEN costs
`GREEN_ENDGAME_PENALTY` rather than paying its purity, and fails if anything
reads `SOC_SESSION_STANDINGS` on the score path again. Against the live account
the picker now matches `score_for` exactly on Serpens_Lattice and on four other
sessions including a single-seat one. Full suite 1056 passed / 1 failed, the
failure being the pre-existing `two_seams_choose_one` eval debt.

---

## 24. ✅ (DONE, v1.28) A same-hour EMP voided a rival's landing

**Status (v1.28):** Fixed. The hour-start visibility snapshot is taken inside
`NightSimulator._pre_hour_phase`, beside the established-cloud snapshot and
immediately after the decay sweep, instead of in the hour loop after that
function has already fired the hour's salvos.

**Symptom:** reported from a live season (Terra_Kestrel, day 6, hour 1). p1
fired an EMP salvo onto (2,14); it destroyed p2's probe; p2's harvester drop
on (2,14), queued for that **same hour**, was refused with `drop: (2,14) has
no live sensor beacon`. The landing should have succeeded *and* auto-harvested.

**Root cause:** the engine had the right mechanism and consulted it a beat too
late. `try_drop_unit` correctly honours a `live_override` snapshot, but the
simulator computed that snapshot *after* `_pre_hour_phase` returned — and
`_pre_hour_phase` is where this hour's EMP launches are pre-empted and
resolved. So "what this seat could see at hour start" was recorded with the
rival's beacon already destroyed by an event that had not happened yet at hour
start.

The tell is that **supersede obeyed the rule and EMP did not**, despite
§3.9.7 listing them as equivalent. That is purely an artefact of where each
resolves: a supersede is a normal dispatch action and lands *after* the
snapshot, a weapon launch is pre-empted and lands *before* it.

**Why it survived so long:** the rule is stated in four places and the engine
was the only dissenter — RULEBOOK §3.9.7 ("a beacon a rival destroys,
supersedes, or EMPs *later in the same hour* still validates that hour's
landing"), §3.9.8 restating it, §4.9.3 (a cloud spawned this same hour is not
"established", so the landing keeps its auto-harvest), and `manual/manual.js`,
which scripts this exact scenario for attendees. Meanwhile §3.9.8's own risk
list recommended "launching an EMP at your probe location to destroy it before
your drop resolves" as a counter to the hot-drop — four lines below the
sentence saying that cannot work. The bug had been written up as a feature.

Test coverage existed and could not have caught it:
`test_vision_rework.test_live_only_honours_hour_start_override` passes
`try_drop_unit` an override by hand, so it pins the plumbing, not the *timing*.

**Regression:** `tests/test_emp_beacon_timing.py`, four tests, all driving the
real `NightSimulator`. Two reproduce the report (the landing, and the harvest)
and fail without the fix with the reported error string verbatim. Two are
counterweights that pass either way, so the fix cannot be over-applied: a cloud
established on an *earlier* hour must still forfeit the landing's auto-harvest
(§4.9.3), and the one-hour reprieve must not persist — a beacon destroyed on
hour 1 must not validate a drop on hour 2, which is exactly what a "cache the
first snapshot" implementation would have done.

**Note for the next reader:** the snapshot instant is deliberate. It sits after
the decay sweep, not at the very top of the hour, because a probe swept by a
cloud that has been standing since an earlier hour is killed by a weapon
already on the board — not by something happening "later in the same hour".

---

## 25. ✅ (DONE, v1.29) A jackpot sat in poor ground, so "warmer" was not a readable signal

**Symptom (design, not a crash).** A `pure` cell — the jackpot the whole
redsign mechanic is built around — was usually an isolated 255 in trace. The
median board carried **2** `mass` squares out of 1120, and **79% of jackpots
had no `mass` at all within 4.5 cells**.

**Root cause.** `_spread_pure_red`'s top-up promotes the richest RED cell that
clears the 12-cell separation, and separated `mass` barely exists, so it
routinely lifted a cell of purity 80–150 straight to 255. Nothing had ever
decided what should surround a pure; the count and spacing rules only decided
*where* they go.

**Why it mattered.** It broke the read prospecting should give a player —
*thickening ground means you are getting warmer*. A pure surrounded by trace
can only be found by landing on it, making the search a lottery rather than a
deduction.

**Fix.** New `_grade_pure_red` pass (RULEBOOK §2.2) lays a deposit around every
pure: `mass` chunks clinging to it plus a scatter further out, through a `vein`
shoulder. Bounded by three rules — only ever raises purity, never touches GREEN
or BLUE, never writes 255 (so it cannot mint a pure beside the one it is
decorating). Runs last on its own RNG stream. Median `mass` per board 2 → 15,
jackpots with no mass 79% → 1.4%.

**⚠ THIS MOVES SCORES, AND THE FOLLOW-UPS MATTER MORE THAN THE FIX:**

1. **Total RED on a board roughly doubled** (median map value 8,844 → 15,394 at
   two seats). Seasons score higher, the `EXTRACTED %` denominator moves, and
   **a score from before v1.29 is not comparable to one after it** — including
   agent benchmarks and the RED_HARVEST floor.
2. **V12's `_ASSUMED_HALO_PURITY = 55` — investigated and largely a false
   alarm.** It prices the blind comb of an unseen redsign halo, which is the
   ground grading enriched, so it looked like a serious knock-on. Measured with
   `scripts/_v12_halo_trace.py` over 28 offline seasons (14 graded, 14 not, same
   seeds), sampling every real smear a seat could see:

   * **The constant is reached on 1.0% of priced seams** (2.1% ungraded).
     `blind_estimate` measures each visible seam and pools across seams first,
     and that path reads the new terrain by itself. The terrain change did not
     quietly break redsign pricing.
   * **55 was never right.** Real smears measure a median non-pure purity of
     **30** ungraded and **107** graded (n=1095 / 1525). The original 53/54/63
     came from three hand-picked snapshots richer than a typical board, so the
     constant ran ~1.8× *high* before v1.29 and ~1.9× *low* now.
   * **The `mass` cliff at 151 is not in play.** That step (×1.0 → ×1.5) is what
     made an early 180 guess beat every option on the card — a 6-cell comb
     prices 281 at purity 55, 602 at 107, 1377 at 180. Across 1525 graded
     samples the measured mean never exceeded **146**; real halos stay in
     `vein`, so a value near 107 is safe in a way 180 was not.

   **Applied (v1.29):** `_ASSUMED_HALO_PURITY` 55 → **105** (graded median 107,
   rounded down) and `_ASSUMED_RED_DENSITY` 0.85 → **0.95** (measured 0.98).
   Both nudged slightly conservative, because the failure this constant has
   historically produced is over-valuing a blind attack, never under-valuing
   one. Safe to apply alongside the terrain change precisely because of the 1%
   reach — it cannot meaningfully confound a score comparison. Re-run the
   tracer before moving them again.
3. **Revert is a server restart, not a code change.** `SOC_MAP_HALO=off`
   restores byte-identical v1.28 terrain (pinned by
   `test_soc_map_halo_off_restores_the_v128_board_exactly`); a fraction thins
   the `mass` without moving jackpots. Safe mid-season — sessions persist their
   grid, not just their seed.

**Reproduce:** `python scripts/_mapgen_pure_census.py 200 40 28 2` prints both
sides over the same seeds.

**Loose end — `manual/agent-data.js` still carries the v1.28 prompt wording**
("the halo is thin"). It could not be regenerated here:
`scripts/export_agent_guide_data.py` needs `SOC_BACKEND=snowflake` to read
snapshot `SNAP_408ddd46_d4_p1`, and its other input,
`reports/turn_suite/cards/post_phaseD/own_seam_d4.txt`, is not in the repo.
Worth a thought before regenerating: that file is an **autopsy of one real
historical turn**, so the prompt it shows is the prompt genuinely sent that
night. Rewriting it to today's wording would falsify the record — the choice is
between re-capturing a fresh turn on a graded board (better teaching material)
and leaving the old turn intact and dating it. Not a product bug either way.

---

## 26. ✅ (DONE, v1.31) A stale `mine_lay` burned a slot and said nothing

**Status (v1.31):** Resolved by retiring the weapon. The caltrop mine is gone
(RULEBOOK §4.9.4) and both of its tags are now **refused by name** instead of
falling through: `mine_lay` via the new `_RETIRED_MOVE_TAGS` in
`game/policy.py`, `build_mine` via the existing `_RETIRED_ORBIT_TAGS`.

**Symptom:** an agent that asked for a mine it could not use lost an hour and
was told nothing it could learn from. The row resolved as a generic waste, so
the next night's prompt carried no reason and the model asked again.

**Root cause:** two gaps lined up. V12's `_v7/move_sanitizer.py` never filtered
`mine_lay`, so a stale model reply reached engine policy intact; and policy's
fall-through for an unrecognised tag is the bare "unknown action" waste, which
consumes a slot (§3.10, every queued row burns one) without naming what went
wrong. The same shape as the v1.13 `ship_catapult` problem, and it is fixed the
same way: a dead tag maps to a *reason*, not to silence.

**Fix:** `_RETIRED_MOVE_TAGS` as the night-move mirror of the orbit dict, both
tags answering with "the caltrop mine was retired in v1.31" and what to use
instead. The slot is still consumed — that part is the rule, not the bug — but
the seat now sees why on the card.

**Deliberately not fixed, because it is not broken:** replay frames, the
Snowflake replay columns, the minelayer flight animation and the `mine_lay`
entry in the orbital activity tally all stay. The tally classifies *stored
frames*, so dropping the tag would have blanked the orbital silhouette of every
archived season that used caltrops.

**Migration:** a pre-v1.31 save has its armed caltrops cleared on load (a
retired weapon must not keep damaging harvesters mid-season) and its unspent
stock refunded as blue purity at the price paid, 100 each; credits are not
refunded. A `[mineRetired]` log line reports both counts.

**Tests:** `tests/test_v09_weapons.py` —
`test_retired_mine_lay_says_why_rather_than_shrugging`,
`test_retired_build_mine_says_why_rather_than_shrugging`, and
`test_stale_mine_stock_refunds_as_blue_on_load`.
`docs/ADDING_A_WEAPON.md` maps every hole the vacated slot leaves.

---

## 27. 🔴 (OPEN) The heuristic stopped choosing a seam in `two_seams_choose_one`

**Symptom:** `pytest` is one red at HEAD —
`tests/test_eval_scenarios.py::test_heuristic_passes_known_scenarios[two_seams_choose_one]`,
failing `HarvesterChainHits: hit 0/1 of 3 target cells`. The agent still
plans a sane-looking night: it walks `harvester_p1` from `[12,13]` out to
`RED[15,15]` and drops both probes on fog clusters. It simply walks the
*other* seam from the one the scenario is asserting on.

**Not from the tutorial work (v1.32/v1.33).** Confirmed by running the file
in a clean worktree at HEAD: it fails there too, with none of the film or
preset changes present. Everything else is green — 1209 passed.

**Where to start:** the three most recent heuristic commits are the
suspects, and all three moved exactly the number this scenario measures —
`9f555e5` (grade the ground around a jackpot, scale jackpots with the
table), `d33b710` (price a blind seam from what seams actually measure),
`92c0534` (last-night settlement). The question to answer first is whether
the scenario's expected cells are still the *better* seam under the new
pricing. If they are not, the fixture is stale and should be re-pinned
with a note; if they are, the seam scorer is the bug. Do not "fix" it by
loosening the assertion until that is settled — this scenario exists to
catch the heuristic wandering.

---

## 28. ✅ (DONE, v1.33) The tutorial stopped teaching after you had played it once

**Symptom:** start Basic a second time and no film modal ever appears. Nothing
errors, the `[ TUTORIAL ]` button is still there, and the reels still resolve —
the modal simply never opens itself. A first-timer on a borrowed laptop that
had already been demoed would get a teaching mode with no teaching in it.

**Root cause:** the auto-open is suppressed once a reel has been shown, so the
modal does not reappear on every four-second poll. That memory
(`soc.tutorial.seen.v1` in `localStorage`) was keyed on the **reel name
alone** — and reel names are `basic:planning:1`, `basic:orbit:2` and so on,
identical in every Basic game. One tutorial filled the set; every later
tutorial read as already seen. The original comment ("keyed by reel, not by
turn number, so replaying the tutorial does not re-nag") had it exactly
backwards: **starting a fresh teaching game is a request to be taught.**

A second, quieter half: `onState` decided "is this a new turn?" by comparing
bare reel keys too, so a new game reached without a page reload looked like
the same turn as before.

**Fix:** `app.js` puts the session id on the `soc:tutorial-state` event, and
`tutorial.js` scopes both the seen-set and the changed-check to
`"<game>|<reel>"`. Mute (`soc.tutorial.muted.v1`) is untouched and is still
the real "stop showing me these" control — it silences the auto-open without
removing the button. Old un-scoped entries are ignored rather than migrated;
worst case someone mid-game sees one reel a second time. The list is capped
so a browser that plays many tutorials does not grow it forever.

**Why no test caught it:** `scripts/_fx_tutorial.py` gets a clean browser
profile on every run, and this bug only exists on the *second* game in one
profile. It now plays a second tutorial in the same context and asserts the
modal opens again, plus a third with mute set to assert mute still wins. Both
were confirmed to fail against the old code before the fix went in.

| # | Area | Severity | Blocking multiplayer? |
|---|------|----------|-----------------------|
| 1 | Vision / trails (echo coverage — now fog-frozen) | ✅ done (v1.8) | no |
| 2 | Vault capacity (15) + capacity warning | ✅ done | no |
| 3 | Multiplayer praxis submit UX (committed waiting frame) | ✅ done | no |
| 4 | Multiplayer praxis animation (non-last clients) | ✅ done | no |
| 5 | Station UI: LAUNCH DELAY button placement | ✅ done | no |
| 6 | Board state pops before animation (drop/probe/harvest/trail) | ✅ done | no |
| 7 | End-game report: attacker→victim kill-feed + personal ops (v1.6) | ✅ done | no |
| 8 | Final game-resolve step (last catapult + vault cleaning) | ✅ done | no |
| 9 | H0/DUSK step + LIVE-return bugs (dawn lock, `+X` fold, blue bar) | ✅ done | no |
| 10 | Vault ↔ Orbital Vault ↔ actual disagreement (DUSK shed reconcile) | ✅ done (v1.9) | no |
| 11 | 4-player Snowflake praxis slowness (persistence payload) | 🟠 high (P1+P3 batched; P2/P4/P5 open) | no |
| 12 | Probe trails missing in live PRAXIS cinematic | ✅ done | no |
| 13 | Night cinematic differed per seat / lost by a background tab | ✅ done (v1.17) | no |
| 14 | Crushed probe echoed its killer twice (stale disk, dead observer) | ✅ done (v1.19) | no |
| 15 | Weapon launch + a second action in the same hour (collision pre-passes ignored pre-empted seats) | ✅ done (v1.19) | no |
| 16 | Chaff couldn't stop a launch; chaff chained into a lock (RULEBOOK §4.9.3 ⇄ §4.9.5 contradiction) | ✅ done (v1.19 / RULEBOOK v1.14) | no |
| 17 | Probe-launch markers never expired (sweep behind an early return; merged glyphs skipped) | ✅ done (v1.19) | no |
| 18 | Supersede/annihilation had no graphic at all; incumbent mis-ledgered by seat order (§3.16 silent on it) | ✅ done (v1.19 / RULEBOOK v1.15) | no |
| 19 | §3.15 launch marker outlived a death its owner watched happen | ✅ done (v1.19) | no |
| 20 | Collision: ring fired ~3s early, and the damaged harvester lifted off before the impact (cross-frame sequencing within a tick) | ✅ done (v1.19) | no |
| 21 | Doomed probe held in the DOM but painted under the opaque terrain stand-in, so it vanished at hour open | ✅ done (v1.19) | no |
| 22 | V12 had no cross-night memory on Snowflake: `SOC_AGENT_MEMORY` was never deployed and every write/read swallowed the failure | ✅ done (v1.19) | no |
| 23 | Snowflake picker scored off a SQL view that credited disposed GREEN at +255 instead of charging −100 and applied no tier multiplier, inverting a finished season's winner | ✅ done (v1.20) | no |
| 24 | A same-hour EMP voided a rival's queued landing: the hour-start vision snapshot was taken after the pre-hour phase had already fired the salvo and destroyed the beacon (§3.9.7 ⇄ engine) | ✅ done (v1.28) | no |
| 25 | A jackpot sat in trace (79% had no mass within 4.5), so "richer ground means warmer" was not a readable signal — new graded-deposit pass (§2.2). **Doubles map RED: pre-v1.29 scores are not comparable.** V12's `_ASSUMED_HALO_PURITY` fallback measured (reached on only 1% of seams, so never the knock-on it looked like) and retuned 55 → 105 | ✅ done (v1.29) | no |
| 26 | A stale `mine_lay` reached the engine unfiltered (the v7 sanitiser never rejected it) and wasted a slot as a nameless "unknown action" — resolved by retiring the caltrop and refusing both tags by name (§4.9.4); old saves clear armed caltrops and refund unspent stock as blue | ✅ done (v1.31) | no |
| 27 | `two_seams_choose_one` red at HEAD: the heuristic walks the other seam, so `HarvesterChainHits` sees 0/1. Predates the tutorial work; suspects are the three recent seam/jackpot pricing commits | 🔴 open | no |
| 28 | The tutorial modal never auto-opened again after one play: the shown-already set was keyed on reel names that repeat in every Basic game, so a returning player got a teaching mode that taught nothing. Now scoped per game id | ✅ done (v1.33) | no |
