# Tabula v10 — Compiler-Faithfulness Plan (the living tracker)

> **v10 mission:** v9 completed its objectives (comprehension + redsign poker,
> WON seed 69 three ways). v10 forks v9 and fixes the failure class v9's audit
> exposed — the LLM executor drops the thinker's concrete cells and freelances.
> v10 makes execution a **deterministic packager** (compiler pattern) and adds
> anti-crowd seat differentiation + economy/final-night guards. It still runs on
> **Haiku, 7 nights, seed 69** — no bigger model (that is v11).
>
> **Definition of done:** `tabula_v10` must WIN seed 69 in a clean 3-way mirror
> AND vs heuristic, AND — the bar v9 did not clear — the mirror's CASE-2 rivals
> must actually BANK their redsign contests (no 14× self-collision spread), with
> executor-vs-thinker cell alignment ≥ 90% and 0 self-collisions.

Seed 69 is the stress seed: it spawns **multiple pure-RED seams in separate
regions** plus a pure-blue, so it exercises multiprobe spread, redsign
ownership (CASE 1 / CASE 2), and denial poker all in one game.

### ✅ V10 FINISH — reflection grounding landed + validated (0730)

Two last v10 fixes closed the seed-69 failure class before handing off to v11:

1. **Walk-in reachability** (already landed): echo/edge pure now yields
   `WALKIN_GRAB`/`WALKIN_SECURE` instead of a probe-starved dead turn.
2. **PLAN vs CORRECTOR vs EXECUTED digest** (this finish): the harness stamps
   `plan_ids` / `planned_cells` / `corrector_notes` / `moves_executed` onto the
   memory entry; `digest.format_self_execution_block` renders them at the TOP of
   SECTION 3 so the reflection reconciles to engine truth. Kills the day-4
   confabulation (0-move night narrated as a 6-parcel harvest) and surfaces the
   corrector (no longer a silent black hole).

**Validation** — `V10_vs_HEUR_s69_d7_reflect-digest_0730` (session
`d4738f68d2c8415182e67c122b3d813a`): **v10 3193 vs heuristic 1590**, clean, every
night resolved once. Day 4 executed `WALKIN_GRAB` (banked the pure at (31,18) via
a live-frontier drop at (29,18) — no probe). Day 5 reflection correctly quoted the
executed cells AND named the corrector's friendly-collision truncation ("keep
harvesters ≥2 cells apart"). Remaining gap = EMP-reactive planning (day-5 EMP
disabled a harvester mid-chain) — that is **v11 posture-matrix** work, not a v10
regression.

**Handoff:** the harvester-assignment redesign (Pyramid × Posture + grounded
memories) is now planned as **v11** (`tabula_v11_PLAN.md`). The Sonnet
native-thinking track moved to **v12** (`tabula_v12_PLAN.md`).

## Inherited baseline — v9's seed-69 seasons (frozen reference)

These are **v9's** runs (v10 has not run yet). Full history lives in the frozen
`tabula_v9/SEED69_FIXPLAN.md`; kept here as the target v10 must beat.

| session | label | note |
|---|---|---|
| `83e6588090264b4fa3836fd3429f3f30` | `v9_anchor_blindgrab_3way_s69` | 3-way, exposed E1/E2/A1–A4 |
| `178c9dff65034a248012a77f9e86a34e` | `V9_vs_HEUR_s69_d7_multiprobe-spread` | 1v1, exposed the day-5 issues |
| `ae0e132455094291977f86f09feacfe7` | `V9_vs_V9_vs_V9_s69_d7_mirror-bigpush` | mirror: p1 **2801**, p2 380, p3 198 (14× spread = self-collision) |
| `29f64184f0904cde877a27a407e46367` | `V9_vs_HEUR_s69_d7_bigpush` | v9 **2207** vs heuristic −673 |
| `23b396c1ce694c0cafc0864a2f623291` | `V9_vs_V8_vs_V7_s69_d7_bigpush` | v9 **2635**, v7 1708, v8 627 |

**v9 verdict (0728):** v9 won all three but the wins were inflated by opponents
self-colliding, and v9's OWN mirror showed a 14× spread (identical code, three
seats dogpiling the same beacon). That is exactly what v10's R1 (deterministic
executor) + R3 (anti-crowd) target. Below, the v9-era diagnosis and landed fixes
are the INHERITED baseline; the **RECONCILED PLAN (R0–R6)** is v10's active work.

---

## ENGINE ISSUES

### E1 — Day-1 night resolved TWICE  ✅ FIX LANDED (needs season re-validation)
**Evidence (`83e658…`, day 1):** two `[praxis] day 1 — Nox begins` blocks.
Round 1 = three heuristic **fallback** policies (2 moves each) → premature
resolution. Round 2 = the real v10 cortex policies (p1 8mv, p3 7mv) → the SAME
day 1 resolved again, with reset probe counters, a phantom redsign near
`(~17,6)`, and p1+p3 colliding at `(33,19)`/`(35,21)`. This is the
"teleporting replay".

**Root cause:** a **cold-start miss** on the first Inference-API call of the
season returned `submitted_policy=False` in ~3s *without running the pipeline*.
`runtime.run_agent_turn` dropped straight to the heuristic fallback, which
**submitted a placeholder policy**; once all seats had placeholders the night
resolved. The retried cortex turns (picked up again off a stale session read)
then submitted the REAL policies and resolved day 1 a second time.

**Fix (landed):** `orchestrator_2/runtime.py` — on a planning-phase cortex
miss, **re-dispatch the real binding ONCE in place** before firing the
heuristic fallback. The transient cold-start self-heals within the seat's own
turn, so no premature placeholder is ever submitted and the night resolves
exactly once. (Reaching the retry means the re-poll already saw no pending
row, so a retry cannot double-submit.)

**Follow-ups:**
- E1a — warm the Cortex Inference client once before the season loop so the
  first day-1 call is never cold. *(not yet done)*
- E1b — stale-read re-resolution → duplicated replay days.  ✅ **FIX LANDED (0729)**

### E1b — "day N repeats three times" in the replay  ✅ FIX LANDED (0729)
**Evidence (`V10_vs_HEUR_s69_d7_variation_0729`, day 3 & 4):** the
`[praxis] day 3 — Nox begins` block appears **three times, byte-identical**, and
day-4's `[orbit] +1000 credits` / `dawnComplete` appear 3×. p2 ran its policy
turn twice (`waiting_on=p2` then `night_resolved`). The replay viewer therefore
plays day 3 three times. **Final score is still correct** — each re-resolution
starts from the same pre-night state and is deterministic, last-save-wins — so
this is a feed/replay-integrity bug, not a score-corruption bug.

**Root cause:** `engine.save_session_full` wrote **all 7 SOC_* tables on a
`ThreadPoolExecutor` sharing the ONE Snowpark `Session`** — including
`store.save_session(session_row)`, the authoritative `SOC_GAME_SESSION.json_state`
row that `_hydrate_session` reads *exclusively*. Concurrent statements on one
shared connection intermittently let the very next `_hydrate_session` observe a
**pre-resolution** snapshot. The season runner then re-picked the
already-submitted seat (its `pending` map looked un-submitted) and/or force-called
`run_night`, re-simulating the SAME night and **appending its replay frames + log
lines again**. Nondeterministic thread-race → "weird, never happened before"
(the redsign-lifecycle changes nudged log/replay volume + timing enough to start
tripping it).

**Fix (landed):**
1. `engine.save_session_full` — the authoritative `save_session` row now runs
   **synchronously on the main thread** (after the 6 derived-table writes fan
   out in parallel), so the control-flow row `_hydrate_session` reads is never
   subject to the shared-`Session` race → read-your-writes holds for the runner.
2. `append_replay_frames` is now **idempotent per `(session_id, day)`** in every
   store (`snowpark_store` DELETE-before-INSERT, `file_store` rewrite-on-replace,
   in-memory `store` drop-stale) — a re-resolved night can never stack a second
   copy of its frames onto the replay. Pinned by
   `tests/test_replay_payload.py::test_replay_frames_idempotent_per_day`.

*(The `append_log` feed is left additive — it is written incrementally within a
day, so a per-day replace would drop legitimate orbit/planning lines; fix #1
already prevents duplicate log appends by eliminating the re-resolution.)*

### E2 — Discoverer's probe near a rival redsign went INVISIBLE to the rival  ✅ ENGINE FIX LANDED
**Evidence (`83e658…`, day 6→7):** p2 launched `probe_p2_16` at **(18,21)**;
that discovery minted a redsign whose PUBLIC beacon smear is centred
**(~14,22)** — but the true pure was at **(15,22)** (where p2 harvested it on
day 7). p1's day-7 THINK never mentioned (18,21) and blind-guessed the smear.

**Root cause (verified against the live session blob — §3.15 was violated by
two compounding bugs, NOT a lost entity):**
- The probe entity `probe_p2_16` is **alive** and p1's `probe_intel` **does**
  hold (18,21) — but as a merged occupant on a **stale day-5 terrain echo**
  (`day_seen=5`, no `via=probe_launch`), because p1 had legitimately probed
  that cell on day 5 and its old echo was richer.
- **M1 (engine merge):** `session._pulse_probe_launch` merged the day-6 launch
  onto that older echo but **never stamped the launch day** — so the freshest,
  most decision-critical enemy probe looked 2 days old and carried no launch
  marker.
- **M2 (view window):** `view._competitor_intel` built `new_this_day`
  enemy-probe-launches from only the **last-20 recent-log rows**. The
  redsign-minting launch happened mid-way through a BUSY night and scrolled out
  of that window before day-7 planning read it — so it never appeared as "new",
  even though §3.15 launches are public and retained until scheduled expiry.

**Fix (landed):**
- `session.py::_pulse_probe_launch` — on the merge branch, stamp
  `probe_launch_day = self.day` + `launched_by` (terrain snapshot untouched, so
  fog terrain is not falsely aged fresh).
- `view.py::_competitor_intel` — source `new_this_day` enemy-probe-launches
  from the authoritative `sess.probe_intel` markers (window-independent),
  additive + deduped with the existing log path. Covers both a clean
  `via=probe_launch` marker and a merged-onto-echo marker.
- Regression tests: `tests/test_v0_7_0.py::`
  `test_competitor_intel_surfaces_launch_without_recent_log_window` and
  `test_launch_onto_opponent_echo_still_surfaces_as_new_launch`.

**Still open (agent, M3):** even when the finder's probe position is available,
the redsign CASE-2 patterns anchor BLIND_GRAB to the **jittered beacon**, not to
the discoverer's probe cell. Anchor CASE-2 geometry (supersede target + drop
sweep) to the freshest enemy probe INSIDE the redsign smear so v10 triangulates
the pure instead of guessing. (Ties into A1/A3.)

**Watch:** the replay per-seat frame renders (18,21) from the stale echo, which
is why the glyph flickered/vanished in the agent view; confirm the frame picks
up the refreshed marker now (ties into U1).

### E3 — Redsign discoverer seat id at mint  ✅ ALREADY LANDED
`session._register_redsign` computes the seeding seat and
`_mint_redsign_region` stamps `discoverer` + `co_discoverers`;
`view._redsign_for_seat` derives an exact per-seat `mine` boolean from them
(legacy un-stamped regions fall back to `mine=False`). Ownership (CASE 1 vs
CASE 2) is therefore always exact. Verified present; no further work.

### E4 — Simultaneous probe-collision resolves pairwise  ✅ FIX LANDED
A 3-way simultaneous probe collision left the **third** probe alive because the
first pair annihilated and **cleared the cell** before the latecomer landed, so
the pairwise check saw an empty crater. Seen on day 1 of `83e658…`.
**Fix (`session.spawn_probe`):** record every simultaneous-collision cell keyed
by its turn stamp (`_probe_collision_cells`) and destroy any **same-stamp**
arrival that lands in the crater. A later-hour probe (different stamp) still
resolves normally. Regression tests:
`test_three_probes_same_turn_all_destroyed_no_crater_survivor` +
`test_later_hour_probe_on_collision_crater_still_supersedes_normally`.

---

## AGENT ISSUES (v10 harness)

### A1 — Thinker HALLUCINATES option geometry
**Evidence (`83e658…`, day 7):** the THINK pass narrated "Combo A probes
(14,22)→drops (15,24); Combo B probes (15,19)→drops (16,21)". **None of those
coordinates exist in the menu** — the option menu gives IDs + doctrine only,
not per-option coordinates. The thinker invented plausible-looking coords, and
the mover (which gets the REAL resolved geometry) executed something entirely
different. **Fix:** put the RESOLVED per-option geometry (wave-1 drop cell,
enabler-probe cell, sweep cells) INTO the menu the thinker sees, so its prose
references real cells and the THINK↔MOVE picture matches. Forbid the thinker
from emitting coordinates that aren't in the menu.

### A2 — UNBEATEN_FLANK resolves to an unrelated far-away probe
**Evidence (day 7):** UNBEATEN_FLANK resolved to a drop at **(28,24)** off the
pre-existing `probe_p1_13@(28,23)` — the OPPOSITE side of the map from the
redsign at (15,22). It banked purity-6 trace junk. The "opposite axis / secured
bank" selector grabbed any secured probe disk instead of one anchored to the
contested seam. **Fix:** UNBEATEN_FLANK geometry must be anchored to the
CONTESTED redsign (a fresh probe on the opposite bearing INTO the seam), never
an arbitrary existing disk elsewhere; if no such angle exists, the option must
not be offered.

### A3 — BLIND_GRAB enabler probe not launched → uncovered drop → idle harvester
**Evidence (day 7):** BLIND_GRAB needs a fresh probe onto/near the finder's
probe to (a) supersede it and (b) make the drop cell drop-legal. Instead the
mover spent p1's probe on the **SS1** supersede at (14,10), then dropped
`harvester_p1` at **(15,24)** — which no probe covered (dist² from (14,10) =
197 ≫ 16) — so the sanitizer stripped it and `harvester_p1` sat **idle** all
night. **Fix:** bundle BLIND_GRAB's enabler probe as a mandatory, first-class
part of the recipe (probe cell + guaranteed drop-legal drop cell), resolved by
the agency and never separable from its drop; SS supersedes must draw from a
SEPARATE probe budget, not cannibalise the grab's enabler.

### A4 — Mover latency 99s (and generally 25–45s)  ✅ FIX LANDED
**Evidence (day 7):** p1 mover `ms_elapsed = 99021`. The mover shared the v7
schema, which forces `plan_this_turn / rationale / predicted_outcome /
reflection / memory_note` prose AFTER `moves` — it "thinks in its head" for
tens of seconds. **Fix:** v10 now has its own **moves-only** mover schema
(`tabula_v10/chat_schema._V10_MOVES_SCHEMA`, `additionalProperties: False`, only
`moves` + optional `note`) and a matching lean output contract
(`prompt._V10_ACTION_SCHEMA`). `_MOVER_CHAT_MAX_TOKENS` 2000→1100, `_WALLCLOCK_S`
60→40. The turn narrative for memory/audit is sourced from the **thinker**
(posture + plan IDs + plan-pass reasoning) instead of the mover. Tests:
`test_v9_mover_schema_is_moves_only`, `_name_is_distinct_from_v7`.

### A5 — Mover freelances vs the priority plan (carried over, still live)
The mover invents off-menu drops / converts probes to hot-drops / drops planned
races. Remit = strict packager of the thinker's ordered plan (unit assignment,
hour budget, legality trims from the bottom of the list only). The execute-block
contract already forbids off-menu moves; the moves-only schema (A4) reduces the
surface, but this needs a real season to confirm. **Still open.**

### A-carryover (from the multiprobe season)
- **A6** ✅ Gate the `FINAL NIGHT` doctrine to the ACTUAL final night. The
  probe-stock priming now disclaims finality on non-final nights ("night N of
  M, NOT the final night") and only offers the SS-weaponisation on the real
  final night; `DOCTRINE_LASTDAY_SUPERSEDE` gated to `day >= day_cap`.
- **A7** ✅ Surface the EXACT alive count as a hard fact ("you have N
  harvester(s) ALIVE … no phantom extra unit") — kills the phantom-3rd.
- **A8** ✅ v10 `chain_filter.dedupe_and_floor` — over-generate 5, drop chains
  whose peak purity is below the vein floor, dedupe by **body overlap** (>50%
  shared cells), trim to 3. Never strips to empty (safety net).
- **A9** Promote **echo-red** to first-class `HD_ECHO` options (sighted hot-drop:
  bundled enabler probe + known echo target) — "hot drop but NOT blind". **Open.**
- **A10** Promote **pure/strong BLUE** to compete for a spare harvester when RED
  is below a value floor ("if nothing else, get the pure blue"). **Open.**
- **A11** ⚠️ Partial: sanitizer collision reroute now prefers a NON-probe cell
  first (`avoid_probes=True` then fall back), so it never crushes a live probe
  just to dodge a clash. The zero-RED-value deploy guard is **deferred** — it
  risks killing legitimate blind redsign grabs whose value is fogged.
- **A12** Reflection anchor (landed) — keep; ensure reflection never reports a
  zero-bank + probe-crush as "correct play".

### M3 — CASE-2 geometry anchored to the FINDER's probe  ✅ FIX LANDED
The rival-redsign patterns anchored BLIND_GRAB to the jittered beacon, not the
discoverer's probe. **Fix (`seam_control`):** `_freshest_enemy_probe_in_smear`
finds the finder's probe inside the smear (now visible after E2); BLIND_GRAB
supersedes THAT cell (fallback when the hint carries no supersede) and
`_triangulated_blind_geometry` drops on the in-disk candidate NEAREST the
finder (the pure is by their probe), approaching from their bearing. Tests:
`test_case2_supersede_anchors_to_finder_probe_off_beacon`,
`test_case2_blind_drop_triangulates_toward_finder`.

---

## POST-BIG-PUSH DIAGNOSIS (0728, three seed-69 seasons)

Reports: `reports/diag_s69_mirror.md`, `diag_s69_heur.md`, `diag_s69_v9v8v7.md`.

**What is CONFIRMED working live:**
- **E4 crater** — mirror + v9v8v7 day 1: `probe_p3_1 landed on a
  simultaneous-collision crater at (33,19); destroyed`. The 3rd probe now dies.
- **E1** — exactly one Nox/day across all seasons.
- **A6** — v10 only went `final_convert` on day 7; d1–d6 aggressive/redsign_race.
- **A4** — mover 99s → ~19–32s (better; still above the <15s target on Haiku).
- **CASE-1 owner poker** — whoever discovers a seam plays it well: day-2
  `SMASH_GRAB mine=True` on the (32,17) seam, `CH1` juice chains, and on the
  heuristic game day-6 a **full-fleet staggered `BLIND_GRAB` + `UNBEATEN_FLANK#2`**
  (harvesters to disjoint (13,11)/(17,9)). v10 wins clean when not fighting itself.

**DOMINANT BUG — D1: primary-target CONVERGENCE (all seats pick the SAME cell).**
Mirror + v9v8v7 day 1: EVERY seat (incl. v8 & v7!) hot-drops `(35,21)` and probes
`(33,19)` off the (~32,17) redsign → guaranteed **3-way harvester collision at
(35,21)** (0 cargo) + probe collision at (33,19). Day 1 is a universal write-off.
Root cause: `_turn_rng` seat differentiation only breaks NEAR-TIES; the single
best hot-drop/probe is DETERMINISTIC and identical for every seat on a shared
board, and seam geometry (`build_seam_menu`) takes no rng at all. This is the
pending "Day-1 convergence" item and it is the main reason the mirror's p2/p3
crater (380/198 vs 2801).

**SECONDARY BUG — D2: two CASE-2 rivals both pick `BLIND_GRAB` → collide on the
pure.** Mirror day 2 (both drop (33,19)) and day 6 (p3 drops (16,6) onto p1's
SMASH_GRAB cell → `SIMULTANEOUS DROP COLLISION (p1+p3)`). With 2+ rivals they
should SPLIT (one BLIND_GRAB deny, one UNBEATEN_FLANK offset), but each thinker
independently picks the single "best" contest and they stack.

**Both reduce to ONE root: seat-differentiated target geometry.** Fix plan:
- **D1a** Make each seat pick a DIFFERENT cell from the top-K hot-drop / probe
  candidates via its seat-seeded `_turn_rng` (rotate/offset by seat, not just
  shuffle exact ties), so mirror seats fan out on the opener.
- **D1b** Thread the seat rng into `build_seam_menu` / seam drop geometry so the
  wave-1 drop + flank angles differ per seat around the same beacon.
- **D2** When 2+ CASE-2 rivals are plausible, bias the menu so a seat's own
  differentiated pick lands on a DIFFERENT smear cell / opposite bearing (or
  offset the BLIND_GRAB drop 1 cell off the exact bullseye so two "on-pure"
  grabs don't hit the identical cell).

These are the next implementation targets; they also subsume the earlier A1/A2
concerns (the geometry the thinker references becomes seat-specific and real).

## RECONCILED PLAN (my diag + external audit `audit_html/v9_audit_and_recommendations.md`)

**Score correction first** — the external audit's score table is wrong in 3
places; ground truth from HUD (`get_view`):

| Season | audit | ACTUAL |
|---|---|---|
| vs Heuristic (HEUR) | 27 | **−673** |
| Mirror p2 | 480 | **380** |
| vs V8/V7 | V8 727 / V7 1908.5 | **V8 627 / V7 1708** |

Note: in vs-V8/V7 the true runner-up is **V7 (1708)** — V8 (627) *underperforms*
the older V7. Qualitative findings unaffected; 14× mirror spread is real.

The audit independently confirms the two dominant bugs (executor freelancing +
self-collision) and adds economy / final-night / dead-field findings. Unified,
impact-ranked worklist (supersedes the scattered A/D items above):

> **STATUS (0728) — R0–R6 all LANDED (code + unit tests, full orchestrator_2
> suite green at 634).** Not yet validated with a seed-69 season run.
> - **R0 ✅ subsumed by R1.** v10 already resolves plan IDs to concrete geometry
>   server-side (`agency.resolve_plan` → `Option.payload`), so the recipe the
>   packager compiles IS the full per-token target set — the thinker never needs
>   to hand-type `targets`. (`predicted_outcome` half of R0 is R6.)
> - **R1 ✅** `tabula_v10/packager.py` — deterministic compiler: recipe → wire
>   moves with one-drop-per-unit + contiguous steps by construction, probe/unit
>   budgeting, and a completion/utilization pass. The LLM mover is now the
>   NO-RECIPE fallback only. Harness surfaces `[exec=packager]` + `packager_log`.
> - **R3 ✅** `hint_dispersion` fans out on ANY known not-mine redsign (day-1
>   fresh beacons included, not just `contested`), lead seat keeps the pure and
>   shifts the enabler probe with the drop; `seam_control.build_seam_menu` takes
>   `seat_index` and seat-offsets the CASE-2 blind grab so mirror seats diverge.
> - **R4 ✅** `tabula_v10/orbit.py` economy gate: in the fleet-short window
>   (day ≤4 on one harvester, or one died last night) trims speculative probe
>   builds to a floor of 2 and injects/conserves toward a recovery harvester.
> - **R5 ✅** `agency.ensure_final_night_deploy` — final night + a live harvester
>   but an all-probes plan → prepend the best deploy option. `[final_deploy_…]`.
> - **R6 ✅** `harness._synth_predicted_outcome` fills `predicted_outcome` when
>   the packager/moves-only mover emits none, so the reflect loop has a target.

- **R0 — Thinker emits full `targets` (PREREQUISITE for R1).** Audit: `targets=[]`
  on 20/21 turns — the thinker emits plan TOKENS but not the cells behind them, so
  the executor has nothing concrete to compile and freelances. Thinker must emit a
  per-token geometry map, e.g.
  `{"SMASH_GRAB": {"drop":[16,6], "chain":[[15,6],[17,7]], "pickup_hour":7},
    "PR1":{"at":[19,12]}, "SS1":{"at":[17,1]}}`. This is also HALF of R6. Source
  the cells from the agency registry (already resolved) rather than the LLM.
- **R1 — DECISION MADE: deterministic Python packager (compiler pattern).** Every
  audit hallucination is in the executor STAGE (wrong drop cell (13,6)→(16,6);
  21-move multi-drop on one unit; zero-walk final-night drop; invented "pure at
  (18,8)"). The executor does NOT do creative work — it compiles a precise token
  vocabulary into wire moves, a translation task with fully-defined semantics that
  Python does better. It also runs on the SAME snapshot as the thinker (no new
  info), so any latitude only subtracts value. Wins: multi-drop becomes
  IMPOSSIBLE; coordinate faithfulness GUARANTEED; −21 LLM calls/season; fully
  reproducible (only the thinker to debug); consolidates the sanitizer (already
  "Python fixing LLM output") upstream and makes it authoritative. Keep the LLM
  mover ONLY as the no-recipe fallback (v7/v8 untouched). Subsumes A1/A2/A5.
  Caveat (named, accepted): we forgo the theoretical LLM mid-execution adaptation
  — moot here because thinker+executor share one game state ms apart, and the
  reflect-on-last-night loop catches misses next turn. NOTE: R1 is more agentic,
  not less — it forces the thinker to COMMIT to concrete cells (accountable
  reasoning) instead of hand-waving "SMASH_GRAB the redsign" and leaving details
  to a freelancing compiler.
- **R2 — Off-plan multi-drop guard (SUBSUMED BY R1).** mirror d6 p1: SMASH_GRAB(1
  wave)+3 probes → executor invented 3 drop waves on one harvester (14 stripped).
  A deterministic packager cannot emit a 2nd drop for a unit without an intervening
  pickup — this becomes structurally impossible under R1. Only relevant to the
  LLM-fallback path (where the sanitizer guard remains).
- **R3 — Anti-crowd seat differentiation (mirror floor).** Day-1 every seat (incl.
  v8/v7) hot-drops (35,21)+probe (33,19) → 3-way collision; d6 two rivals both
  BLIND_GRAB the pure. Seat-seeded `_turn_rng` must pick a DIFFERENT cell from the
  top-K (not just break ties) and thread into `build_seam_menu` so drop/flank
  angle differs per seat. Subsumes D1/D2.
- **R4 — Harvester economy gate.** v10 built only 1–2 harvesters across 7 nights
  (mirror: 1). Rule: if a harvester died last night and credits ≥1000c, build one
  regardless of the 1500c target; on day ≤4 with 1 harvester alive, prefer a 2nd
  harvester over probes 3–4.
- **R5 — Final-night collapse is a THINKER posture bug (NOT executor).** After a
  d6 chain loss v10's thinker chose all-probes-no-harvester; the executor faithfully
  compiled it. Determinism does NOT fix this. Rule at the thinker: if a harvester
  is alive on the final night, plan MUST include ≥1 of
  SMASH_GRAB/BLIND_GRAB/CH1/UNBEATEN_FLANK.
- **R6 — Fill dead schema fields.** `predicted_outcome` never emitted →
  `[predicted=?]` every turn (weakens the reflect loop). `targets` is R0. Cheap
  prompt fix.

### What deterministic execution (R1) does NOT fix
Determinism kills 4 of the audit's issues (wrong cells, multi-drop, zero-walk,
invented cell-contents) but 3 are UPSTREAM and need their own fixes:
- **R3 anti-crowd / self-collision** — a perfect packager still drops three v10
  seats on (16,6) if all three thinkers pick it. Needs seat differentiation.
- **R5 chain-loss recovery** — thinker-level posture choice (above).
- **R4 one-harvester economy** — orbit heuristic, not the planning pipeline.

### Order of operations (compiler cutover)
1. **R0 first — thinker emits full `targets`.** Then test whether the CURRENT LLM
   executor now uses them verbatim. If YES → cheap win, no refactor needed. If NO
   (expected) → proceed to the Python packager.
2. **Write the Python packager** (~200 lines over the token vocabulary; reuse the
   sanitizer's geometry helpers). Recipe → wire moves is a pure function.
3. **Add the deterministic completion/utilization pass** — guarantees all alive
   harvesters deployed + all probe stock spent, drawing ONLY from offered hints
   (this is the "all probes used, all harvesters dropped" guarantee).
4. **A/B validate** — one mirror at seed 69 with LLM executor on p1 vs Python
   packager on p2; compare per-turn executor-vs-thinker cell alignment. Cut over
   when Python matches/beats on faithfulness AND score.

Open engine follow-ups (E1a/E1b) still apply. Recommended build order:
**R0 → R1 (packager+completion) → R3 (anti-crowd) → R4/R5/R6.** R3/R4/R5/R6 are
independent of the compiler cutover and can land in parallel. All scoped
**v10-only (hermetic fork)** unless stated.

## VALIDATION PROTOCOL (repeat until DONE)

1. Re-run `v10 vs v10 vs v10` on seed 69, 7 nights → assert **exactly one** Nox
   per day (E1), no day-1 self-collision.
2. Assert p1 SEES the discoverer's probe on any rival redsign night (E2).
3. Assert on the day-6/7 rival redsign, v10 lands a covered BLIND_GRAB on/adjacent
   the pure and banks it (A1–A3).
4. Score: v10 must finish **1st**. Then repeat `v10 vs heuristic`.
5. Mover p95 latency < 15s (A4).

## UI

- **U1** ✅ Replay now defaults `replayViewSeat = "obs"` for bot/season
  (`WATCH_MODE`) replays (`server/static/app.js`), so the whole board is stable
  by default; live play still opens on the player's own seat.

---

## BIG-PUSH STATUS (this pass)

Landed + unit-tested: **E4, A4, A6, A7, A8, A11 (reroute half), M3, U1**;
**E3** confirmed already present. Deferred/open (need a real seed-69 season to
tune or too risky to land blind): **A1, A2, A3, A5, A9, A10, A11 (value
guard), E1a/E1b defensive follow-ups**, and the M3 replay-frame watch (U1
per-seat frame). Next step is a fresh `v10 vs v10 vs v10` + `v10 vs heuristic`
season on seed 69 to re-run the VALIDATION PROTOCOL and see which agent-side
items (A1/A2/A3/A5) still bite with the new geometry + faster mover.

> Note: the `two_seams_choose_one` heuristic **eval** scenario is currently red,
> but it is a PRE-EXISTING regression from earlier heuristic/randomization work
> (the eval + heuristic paths don't touch anything in this push; confirmed by
> reverting the sanitizer change and by `chain_filter` being v10-only).

## VARIATION PASS (0729) — speculative picks stop the night-1 pile-up ✅ LANDED

The R3 pincer stops mirror seats mutually-crashing, but the deeper cause of the
night-1 convergence is that the shared compiler gives ONE deterministic answer:
on an all-fog board `_seed_candidates` yields essentially the fog centroid (=map
centre), and `top_hot_drop_hints` takes the raw-intensity ARGMAX bright cell — so
every seat (and v1–v9) opens on the same square. Fix = genuine VARIATION on
SPECULATIVE picks only; assured red (live LOS / echo) stays greedy.

New hermetic v10 modules (all unit-tested; full `orchestrator_2` suite green, 656):

- **`frontier.py`** — exploration-probe placement. Generates a rich candidate
  grid inset one probe-radius from every wall (edge/quadrant disks stay full), so
  "grab the sides" costs no coverage. Scores **coverage-BAND** (≥70% of best is
  coverage-equivalent) − **enemy-proximity** − **own-history** + a light
  **per-seat sector** pull, then **weighted-samples** (not argmax) with a
  min-separation between a seat's own picks. Enemy probe launches are PUBLIC and
  accumulated **season-long** (`record_enemy_landings` / `enemy_landings`) so the
  scorer steers away from ground rivals have worked. Wired into the harness:
  anchored probes (redsign/echo/seam) stay deterministic from the shared
  compiler; the frontier fog probes come from here.
- **`speculative.py`** — bluesign hot-drop picker. Groups bright cells BY cluster
  (keeps seam identity), **samples which cluster** (weighted by peak brightness)
  and **which drop cell** within it (weighted by intensity), per-seat rng. Tags
  hints `varied=True` so the pincer safety-net leaves them alone. Falls back to
  the shared bluesign picks when there is no cluster to sample.
- **`comb_shapes.py`** — three harvest walks offered per hot drop, the thinker
  chooses length/area: **STRETCH** (long line, max intel; may leave the disk),
  **SWEEP** (tight dense harvest), **SAMPLE** (quick 2-step in/out for
  hot/contested). Agency expands each hot drop into `HDnL/HDnT/HDnQ` sharing a
  `group`; the packager refuses a second drop on an already-claimed cell so two
  shape variants of one drop can never double-deploy (self-collision).

Doctrine: `DOCTRINE_DROP_ON_VALUE` now tells the thinker to pick exactly one
shape per drop and when to use each. Smoke test (day-1, 3 seats) confirms:
frontier probes fan to distinct edge/quadrant cells (no centre), bluesign drops
differ per seat, menu shows the shape variants.

**Still PENDING:** the seed-69 validation seasons (`v10³ mirror` → `v10 vs
heuristic` → `v10 vs v8 vs v7`) to confirm the night-1 pile-up is gone in a live
fight and re-run the VALIDATION PROTOCOL.

## E1b + VALUE-TARGETING PASS (0729b) — the dual-redsign day fixes

### E1b — stale-read double-resolution ✅ FIX LANDED
The "day 3 repeats three times" replay bug. `save_session_full` wrote the
authoritative `SOC_GAME_SESSION` row **inside** the parallel save pool alongside
the derived-table writes, so a subsequent `_hydrate_session` on the same
connection could read a **pre-resolution** snapshot — the runner then re-picked
an already-submitted seat and re-resolved the night, stacking duplicate replay
frames. Fixes: (1) `engine.save_session_full` writes the session row LAST, on the
main thread, after all derived writes land (read-your-writes for the critical
row); (2) `append_replay_frames` is idempotent per `(session, day)` in all three
stores (snowpark DELETE-before-INSERT, file rewrite-on-replace, in-mem drop-stale).

**Impact (measured):** re-run `V10_vs_HEUR_s69_d7_e1b_0729`
(`60302bb18f194d5abcd4656e726768e1`) flipped a **−748 loss → +2633 win**
(3686 vs 1052), the best V10-family score on record. Dead steps 5→0, green
steps 2→0, chaff exposure 12→2.

> **CORRECTED ATTRIBUTION (important).** The external `v10_e1b_report.md` credits
> the swing to *new* packager features ("green avoidance DONE", "chaff-window
> awareness DONE", "chain-loss recovery DONE"). That causation is wrong: **no
> packager code changed in e1b** — only the two infra fixes above. Those
> behaviours were **already in the packager**; the prior run's days 5–7 "collapse"
> was the `RED_HARVEST` **heuristic fallback** firing because the stale-read
> re-dispatched the night, discarding the real plan. E1b simply stopped the
> spurious fallback, so the packager's pre-existing behaviour became visible for
> the first time. Likewise "targets populated on 1/7 turns" is **not** a schema
> fix we shipped — the thinker already emits `targets` sometimes; the other turns
> were the fallback (no thinker output). Do not chase "we added green avoidance";
> the real open lever is still **targets on every turn** (see B / R-targets).

### V1 — sanitizer blue-blind (`has_loot` red-only) ✅ FIX LANDED
Day 3: the agent wanted a pure-blue cell in vision but "walked around it". Cause:
`move_sanitizer` spared a friendly probe only when `has_loot = red>0`, so a drop/
step onto a **pure-blue** cell under a 2+-night probe was rerouted off the value.
Fix: `_visible_blue` + opt-in `blue_is_loot` (default OFF, so v7/v8 byte-identical;
v10 harness passes True). Rich blue (`purity ≥ 192`) now counts as loot → the
crush is justified, the blue is banked. Both `has_loot` sites (drop-crush T2 and
step-crush T5) updated.

### V2 — flank/walk-in drops ignored live value ✅ FIX LANDED
Day 4: `UNBEATEN_FLANK` on the OWN redsign did a "blind walk of its own live" —
waves 2/3 dropped one geometric step off the jittered beacon (`_drop_toward`),
ignoring the purity their own probe reveals. Fix: `_value_drop` picks the richest
drop-legal cell in the wave-probe's disk via `enumerate_value_ring` (skips the
probe centre so the enabler isn't self-crushed; falls back to `_drop_toward` when
no value is visible). Applied to `_mine_patterns` waves 2/3 and `_rival_patterns`
UNBEATEN_FLANK + WALK_IN.

### V3 — comb shapes swept blind ✅ FIX LANDED
`agency._hotdrop_shape_options` called `comb_variants` with **no** `value_cells`,
so SWEEP/SAMPLE combs walked blind and could route AROUND the cluster the drop
landed on. Fix: `_hotdrop_value_cells` feeds visible red (purity-ranked) + blue in
the probe disk so the combs bias toward the actual value.

### A-dualred — dual-redsign menu + per-harvester CASE-1 fork ✅ FIX LANDED (0729c)
`build_seam_menu` was driven by `hot_drop_hints`, so a rival redsign **in fog**
(Day 4's second beacon) produced NO pattern — the thinker's `UNBEATEN_FLANK#2`
had nothing to resolve and both harvesters converged on the own redsign. Rebuilt
the menu around the user's fork model:

- **Region-driven menu.** `build_seam_menu` now enumerates the authoritative live
  regions (`agent_view['redsign']`), pairs each with its nearest redsign hint for
  geometry (fogged regions get a synthesised centre hint), then folds in any
  hint-only beacon a region didn't cover (nothing the old path produced is lost).
  Ordering is **MINE first** (smash-grab is THE priority); the second source's IDs
  are suffixed `#2`. So a dual day shows `SMASH_GRAB / SECURE_MASS / LATE_SWEEP`
  (own) **and** `BLIND_GRAB#2 / UNBEATEN_FLANK#2 / WALK_IN#2` (rival).
- **CASE-1 split into per-harvester options.** `_mine_patterns` now returns three
  single-wave patterns (one harvester each) instead of one 3-wave campaign that
  ate the whole fleet: `SMASH_GRAB` (H1 belly-flop the pure), `SECURE_MASS` (H2
  SHORT strip of the visible mass ring, value-first via `_value_drop`; doctrine
  offers a weapons-time pure re-hit), `LATE_SWEEP` (H3 late, bigger pattern). This
  is what lets the DUAL case fork — H1 grabs own, later harvesters are free to
  contest the rival OR bank own mass.
- **Doctrine CASE 3.** `DOCTRINE_REDSIGN_POKER` now teaches the dual fork: H1
  SMASH_GRAB own (non-negotiable); 2nd/3rd harvester = agent's judged fork between
  **double-damage** (contest rival, high upside/variance) and **safe own mass**
  (both get something), tilted by SCORE (ahead → swing; far behind → usually
  secure) and weapons — explicitly non-deterministic, stated in `reasoning`.

Tests: region-driven fog-rival + dual-beacon cases added; full `orchestrator_2`
suite green (659).

### WALK-IN-FROM-LIVE — the "echo pure, 0 probes → 0 moves" strand ✅ FIX LANDED

**Root cause (day-3 of `V10_vs_HEUR_s69_...`).** The agent's own harvester
discovered a pure at (31,18) on day 2 (echo, not live). On day 3 orbit built a
2nd harvester → `probe_stock=0`. `_known_core` found the echo pure, but
`_wave1_grab_geometry` only knew two modes: drop STRAIGHT on the pure (needs live
coverage on the pure — absent) or launch a fresh probe (stock 0). It chose probe;
packager dropped the probe; sanitizer stripped the bare drop → **0 moves**, then
the day-4 reflection hallucinated a harvest that never ran.

**The insight (user).** Only the initial DROP is vision-gated; STEPS are not. An
echo pure outside live coverage is still reachable ON FOOT: drop on the nearest
live-legal, non-green frontier cell and WALK in through fog. No probe needed.
Verified for this exact turn: `(33,17)/(29,20)/(33,20)` were live+non-green two
cells from the pure; a 3-step walk banks it.

**Fix (all in `seam_control.py`, hermetic to v10).**
- New geometry: `_live_cells`, `_walk_path_to` (BFS, steps avoid green, ≤ hold
  cap), `_walkin_from_live` (nearest live frontier that can walk to the pure;
  `avoid_drops` lets a 2nd wave pick a disjoint frontier), `_mass_tail` (extend
  past the pure into the visible mass, else blind-walk the halo).
- **Reachability fork in `_mine_patterns`** (threads `probe_stock`): pure
  drop-legal now → classic EMP-proof SMASH trio; pure fogged/echo but WALKABLE →
  **WALK-IN trio** (`WALKIN_GRAB` H1 + `WALKIN_SECURE` double-walk + `WALKIN_LATE`),
  no probes; fogged + unwalkable + a probe in stock → existing probe-flanked
  trio; fogged + unwalkable + no probe → **`[]` (starvation; spend fleet
  elsewhere)** rather than undroppable geometry.
- **EMP double-walk doctrine.** A direct smash is EMP-proof (resolves in 1 hour);
  a walk-in spans hours so EMP can jam it. `WALKIN_SECURE` re-walks the SAME pure
  from a disjoint frontier — the pure is too valuable to trust to one
  interdictable chain (knowingly takes a green if H1 already banked it).
- **PROBE BUDGET guard.** `build_seam_menu` drops probe-gated patterns once the
  night's `probe_stock` is spent (walk-ins cost 0, always survive); rival CASE-2
  patterns are omitted entirely when stock=0 (can't contest a fogged seam with no
  probe). Harness reads probe_stock top-level or `orbit.probe_stock`.

**On D1 (orbit probe budgeting): NOT pursued.** Per the user, starvation is fine —
the walk-in makes the pure reachable without forcing a probe build. Tests: walk-in,
double-walk, starvation, and probe-budget cases added; full `orchestrator_2` suite
green (663).

### STILL OPEN (added to plan, not yet built)
- **B / R-targets — `targets_by_token` on every turn.** The single biggest lever
  per both diagnostics. Thinker emits concrete cells; packager compiles the
  thinker's coordinates instead of re-deriving from hints. Currently populated on
  only some turns.
- **Same-cell crash-hedge carve-out.** The weapons-time "re-hit the pure" play is
  doctrine-only for now — the packager/sanitizer dedupes a second drop on an
  already-claimed cell, so an intentional same-cell repeat-wave can't execute yet.
- **Packager decision trace (`[packager_trace]`).** Per-token compile status so
  we can see which plan items compiled vs were dropped. Not built.

All four landed fixes: full `orchestrator_2` suite green (657); v7/v8 unchanged
(blue-loot is opt-in). Next: the seed-69 validation seasons.
