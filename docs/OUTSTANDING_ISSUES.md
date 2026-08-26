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

## Triage summary

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
