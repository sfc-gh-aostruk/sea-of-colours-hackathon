# Tabula v11 — PLAN: Pyramid × Posture harvester assignment + grounded memories

> Status: **plan — mint as a fork of v10** once v10's finish (walk-in reachability
> + the PLAN‑vs‑CORRECTOR‑vs‑EXECUTED reflection digest) validates on seed 69.
> Stack unchanged: **haiku + Agents API + the deterministic packager**. This is a
> *comprehension/heuristics* release, NOT a model bet — the model bet is v12
> (native bounded thinking on the inference API, formerly the v11 doc).
>
> Versioning: v7 (cheap split) → v8 (data+doctrine) → v9 (comprehension, won
> seed 69) → v10 (deterministic compiler-faithful execution) → **v11 (this doc:
> unify harvester assignment)** → v12 (heavyweight model bet).

---

## Why v11 exists

v10 made *execution* faithful: the LLM thinker picks plan IDs + forks, and a
deterministic Python packager compiles them to legal wire moves. That fixed the
freelancing mover. But the seed‑69 diagnostics exposed a deeper problem that is
**not** an execution bug — it is an **assignment** bug. The agent does not have a
single, coherent mental model for "given everything I can see, what should each
of my ≤3 harvesters do tonight?" Instead it has a pile of special‑case pattern
families (SMASH/SECURE/LATE, WALKIN_*, HD_ECHO, chain, blind‑grab, rival flanks)
bolted on one at a time, plus a menu that only fires under narrow preconditions.
Symptoms observed on seed 69 (session `8fab7741…`):

1. **Probe starvation → dead turns.** Orbit built a harvester, left `probe_stock=0`,
   and every probe‑gated redsign pattern silently vanished → 0 moves on day 3.
2. **Echo‑pure literalism.** A harvester‑discovered pure sat in ECHO (no live
   probe). The redsign menu required live vision to drop, so it offered nothing —
   even though the pure was one cell from live and trivially *walk‑in*‑able.
3. **Dual‑redsign confusion.** Mine + rival redsign live simultaneously; the menu
   couldn't express "smash my pure with H1, contest the rival's with H2."
4. **Confabulated reflections.** With no execution feedback, a 0‑move night got
   narrated as "harvested 6 RED parcels." (v10 finish fixes the *feedback*; v11
   also needs the assignment to stop producing dead turns in the first place.)

The through‑line: **value provenance (LIVE / ECHO / EXPECTED) and posture (who
else can see it, weapons, tempo) are computed implicitly and inconsistently
across five modules.** v11 makes them the *first‑class inputs* to one assignment
pass.

## The six logic gates (where assignment happens today)

| Gate | Module | What it decides | Current failure |
|------|--------|-----------------|-----------------|
| G1 Economy | `orbit.py` | build/repair probes & harvesters | starves probes without knowing tonight's targets need them |
| G2 Value surfacing | `probe_hints`, `seam_control`, blue hints | which cells are "worth it" | provenance (live/echo/expected) not tagged; live pure not force‑surfaced |
| G3 Menu assembly | `seam_control`, `agency.py` | build the option menu | patterns gated on narrow preconditions; drop silently when unmet |
| G4 Thinker | `cortex_chat` think→plan | pick plays + forks | picks IDs that may not be executable; no posture read |
| G5 Packager | `harness`, packager | compile IDs → moves | faithful (v10) — keep |
| G6 Corrector | `move_sanitizer` | legalise moves | was silent (v10 finish surfaces it); still reroutes blindly sometimes |

v11 rewrites **G2 + G3** around one taxonomy and feeds **G4** a posture
annotation. **G1 (orbit) is LEFT AS-IS** — per the scope correction, the agent
must cope with whatever probe stock orbit hands it; orbit ↔ tactics *reservation*
is a later improvement. **G5 is untouched** (v10's contract) and **G6 keeps** the
v10‑finish surfacing.

---

## The model: Pyramid of Value × Posture Matrix

Every turn produces ONE ranked list of **complete plays** (drop + walk + pickup,
optionally a probe), plus a short **leftover‑probe** section for spare probes.
Each play is derived from two orthogonal axes.

### Axis 1 — Value × Provenance (the pyramid → default action)

Provenance tiers, richest first, each tagged `LIVE` (under a live probe now),
`ECHO` (own memory / prior sighting, no live probe), or `EXPECTED` (redsign fog —
a pure is *implied* but its exact cell is unknown).

| Value | Provenance | Default action | Probe? |
|-------|-----------|----------------|--------|
| **PURE** | LIVE & drop‑legal | `SMASH` — drop on it, auto‑harvest, shortest walk, early pickup | no |
| **PURE** | LIVE but on the edge (not drop‑legal) or ECHO, **walkable from live** | `WALK_IN` — drop on nearest live cell, walk onto the pure, walk out | no |
| **PURE** | ECHO/EXPECTED, **not walkable**, probe in stock | `PROBE_GRAB` — probe H1, hot‑drop H2 | yes (1) |
| **PURE** | fogged, no probe | *nothing* — surface a redirect, never a blind harvester |
| **MASS/VEIN** | LIVE (nothing purer competes) | `CHAIN` — length set by posture (long when safe) | no |
| **MASS/VEIN** | ECHO, walkable | `WALK_IN` (mass tail) | no |
| **BLUE (rich)** | LIVE, no red competes | `GRAB_BLUE` — blue is loot (v10 sanitizer already honours it) | no |
| **FRONTIER** | EXPECTED (high edge_promise / echo cluster) | `PROBE` for vision — never a blind harvester unless echo‑backed | yes |

The key doctrine the diagnostics demanded, encoded as the *top* of the pyramid:
**"IF YOU SEE A PURE IN LIVE — grab it. If a pure is in ECHO and close to live —
walk in and grab it."** This must fire *regardless of redsign ownership* — a pure
is a pure whether or not a beacon is lit.

### Axis 2 — Posture modifiers (tune the play)

Each candidate play is annotated with a posture read that modulates length,
timing, and defensive riders — it does **not** change *which* value you go for,
only *how*:

| Signal | Read | Modulation |
|--------|------|-----------|
| Enemy vision on the cell | can a rival legally drop here, and at which hour? | if a rival can drop **H1** and it's contested → shorten, or blind first |
| Enemy weapons (chaff/EMP likely) | from stock + prior‑night losses | shorter chains, earlier pickups, **double‑walk the pure** for EMP redundancy on walk‑ins |
| Enemy probe presence | rival probe on/near the seam | `SUPERSEDE` to blind the finder (tempo‑sensitive: a supersede at H‑21 is near‑useless) |
| Own score (ahead/behind) | vault delta | ahead → tempo/denial (blind + take); behind → don't take unnecessary risk |
| Tempo (day / hour) | early season vs final night | final night weaponises spare probes; early season values vision extension |
| Probes remaining | after harvesters committed | drives the leftover‑probe section |

### Complete plays + leftover‑probe plans

The menu is two sections:

1. **HARVESTER PLAYS** — one complete play per assignable harvester, drawn from
   the pyramid, already posture‑annotated. The thinker assigns harvesters to
   plays (and *forks* where the trade‑off is genuine — see below).
2. **LEFTOVER PROBES** — what to do with probes not consumed by a play: extend
   frontier vision (bias to fog + historically enemy‑free areas — the variation
   memory from v10's speculative pass), blind a finder, or (final night only)
   weaponise. Explicitly low‑value late in the day.

### The one genuine fork the agent must own

A **pure on the edge of LIVE** is reachable two equally‑good ways, and the
choice is *not* heuristically decidable — it depends on what else the agent
wants its probes for:

- `PROBE_GRAB` — spend a probe to hot‑drop; **extends vision** to the surrounding
  mass for tomorrow.
- `WALK_IN` — save the probe (for frontier/blind elsewhere); get the pure in the
  same 3 moves, but **no bonus vision**.

v11 surfaces BOTH for the same pure, labelled with their cost, and lets the
thinker fork. This is the "complete plays with probes AND leftover‑probe plans"
the user asked for.

---

## What v11 builds ON (already shipped in v10)

- **Walk‑in reachability** (`seam_control._walkin_from_live`, `_walk_path_to`,
  `_mass_tail`) — the geometry for `WALK_IN` exists; v11 generalises it from
  "redsign only" to "any reachable pure/mass."
- **Region‑driven menu** — `build_seam_menu` already enumerates live + fogged
  regions; v11 folds this into the pyramid surfacer.
- **PLAN‑vs‑CORRECTOR‑vs‑EXECUTED digest** (`digest.format_self_execution_block`)
  — grounded reflection; v11 extends it into a cross‑day **strategies memory**
  (what worked / what got interdicted) for on‑the‑job learning.
- **Value‑aware drops + blue‑as‑loot + comb value_cells** — the v10 targeting
  fixes carry straight in.
- **Deterministic packager (G5)** — unchanged; the pyramid only changes what the
  thinker is offered, not how it compiles.

---

## Phased implementation

### Phase 1 — Provenance + default grabs (the biggest single lever)
- New `value_pyramid.py`: build the ranked, provenance‑tagged candidate list
  (LIVE / ECHO / EXPECTED × PURE / MASS / BLUE / FRONTIER).
- Force‑surface: **any LIVE pure → a `SMASH` play; any ECHO pure walkable from
  live → a `WALK_IN` play; best LIVE mass chain → a `CHAIN` play** — regardless
  of redsign. This alone kills failure modes #1/#2 (dead turns, echo literalism).
- Doctrine: "pure in LIVE = grab; pure in ECHO near live = walk in" at the top.

> **✅ LANDED (0730).** `value_pyramid.py` (`build_candidates` +
> `force_surface_grabs`): provenance from `red_tiles[].freshness` (LIVE/ECHO),
> tiers from purity bands, rich LIVE blue folded in. Emits SMASH / WALK_IN /
> GRAB_MASS / GRAB_BLUE, all chain‑shaped so the existing packager compiles them
> unchanged; not‑walkable pures (need a probe) deferred to Phase 2. Wired into
> `agency.build_registry` as a new top‑of‑menu `grab` kind ("PRIORITY GRABS"),
> deduped against cells the seam/hot‑drop/chain menu already targets;
> `grab → _pack_chain` registered in the packager + added to `_DEPLOY_KINDS`.
> `DOCTRINE_DROP_ON_VALUE` extended to point at the grabs menu + legitimise the
> walk‑in drop. Tests: `test_tabula_v11_value_pyramid.py` (9); full v11 suite
> green (177).

### Phase 2 — Probe-budget awareness (menu-side; ORBIT UNTOUCHED)
> **Scope correction (user):** do NOT touch the orbital heuristic. The agent must
> deal with whatever probe stock orbit hands it as-is; orbit ↔ tactics *reservation*
> (orbit peeking at the pyramid to hold back a probe) is a LATER improvement, not
> part of v11. Phase 2 is purely menu/agent-side.
- The menu copes with the GIVEN stock: probe-gated plays (`PROBE_GRAB`, seam
  probe-flanked patterns) only appear when stock covers them; when probe-starved,
  the zero-probe `WALK_IN` twin survives (the v10 budget guard already does this —
  generalise it to the Phase-1 grabs).
- Menu LABELS every play's probe cost explicitly ("costs 1 probe" / "no probe")
  so the thinker can reason about the budget instead of picking an unexecutable
  play. No orbit changes — the pyramid simply reads `probe_stock` and adapts.

> **✅ LANDED (0730).** Menu-side only, orbit untouched. `agency._option_probe_cost`
> mirrors the packager's spend sites exactly (probe/supersede/frontier = 1;
> hot-drop = probe + supersede; seam = per-wave; grabs/chains = 0).
> `format_menu_block(reg, probe_stock=N)` prints a PROBE BUDGET header + tags each
> option ("· needs N probe(s)" / "· no probe"); the harness passes the given
> stock. The existing v10 budget guard already drops unaffordable probe-gated
> seam patterns and keeps their zero-probe walk-in twins, and Phase-1 grabs are
> zero-probe by construction — so a probe-starved night always has executable
> plays. Tests: +2 in `test_tabula_v11_value_pyramid.py`; full v11 suite green (179).

### Phase 3 — Precaution guards + tightened enemy‑redsign aggression

> **Revised (0730) after the 9‑season deep audit (`audit_html/v11_deep_analysis.md`).**
> The audit reframed the root cause: the THINK pass already reasons correctly
> about green hazards, chaff windows, collisions and redsign cases, but the
> THINKER→packager handoff **strips the spatial/temporal constraints**, so the
> packager compiles blind. The measured bleeds are (a) −900 on s56 from
> blind‑dropping onto rival‑stripped GREEN, (b) Aurora destructions from pickups
> inside chaff windows, (c) mirror collisions. One HARD engine constraint shapes
> the design: **the packager emits ALL of a night's moves up front — it cannot
> "probe at H1, read the result, then decide the H2 drop."** So confirmation of a
> fogged cell is a *cross‑night / live‑vision* gate, never a mid‑night one.

**Part A — Precaution guards (packager‑side, deterministic, low‑risk).**
- **A1 — persistent stripped/green guard.** Green is monotonic (harvested = green
  forever). Accumulate every synthetic/hazard green cell the seat has *ever* seen
  into a per‑(session, seat) set that **survives fog**, and forbid any drop/step
  onto it in the packager (+ feed it to the sanitizer's `bad` set as a backstop).
  Kills the s56 self‑harm where a prior‑night stripped cell, now fogged, still ate
  −100/parcel.
- **A2 — no harvester step onto a FOGGED cell in a contested seam.** A contest
  chain may only step onto cells that are live‑red for the seat at plan time.
- **A3 — chaff‑window pickup.** When chaff is likely, keep the contest chain short
  and schedule the pickup outside the known jam window.

**Part B — Tighten aggression on the enemy redsign (CASE 2 = rival's beacon).**
Replace "blind‑dive the beacon" with a **vision‑gated, tempo‑honest** contest:
- **Seam LIVE‑RED for me** (my probe already covers it): aggressive — smash the
  *confirmed* pure/mass, but **offset from the beacon core** and **stagger waves**
  (smart‑hawk pincer); never stack the advertised cell.
- **Seam FOGGED to me** (the s56 failure): do **NOT** send a harvester. Instead
  **probe it** (confirm + vision for a real drop tomorrow), **supersede the
  finder** (blind the discoverer, deny their next‑night harvest), and keep my
  harvesters on my own confirmed value. This is more aggressive in the right
  currency (denial + tempo) and stops the green/collision self‑harm.
- **Behind + late**: don't speculatively contest a fogged rival pure — bank own
  value. Mechanically a **menu gate**: on a CASE‑2 seam, `BLIND_GRAB`/blind
  hot‑drops appear only when I have live red on the seam; when fogged the menu
  offers PROBE‑seam + SUPERSEDE‑finder instead. Menu‑side, **orbit untouched**.

**Part C — Carry the intent to the packager (the audit's #1 lever).**
- Enrich the THINKER JSON with `constraints_by_token` per plan item: `avoid_cells`
  (green/stripped), `offset_from` (beacon core), `stagger_from` + `min_hours`,
  `pickup_hour`. The packager **consumes** these — the compiler pattern is kept
  (a richer *grounded* recipe, not free re‑targeting). Phase‑3 posture becomes the
  *producer* of these constraints.
- Fold the dual‑redsign CASE‑3 fork in here (mine‑first, then contest/second‑drop).

**Sequencing:** A1 (kills the biggest bleed) → A2/A3 → B (menu gate) → C (schema).
**Pass/fail:** zero green auto‑harvests on contested seams; v11 no longer last on
seed 56; mirror spread narrows; vs‑heuristic denial on seed 69 recovers toward v10.

> **✅ A1 LANDED (0730).** New `hazard_memory.py`: a per‑(session, seat)
> monotonic union of every synthetic/hazard GREEN cell ever seen, persisted
> best‑effort to `SOC_AGENT_MEMORY` (`kind='arena:hazard_cells'`) + a process
> cache. The harness accumulates it each turn and threads it as
> `forbidden_cells` into `packager.pack_recipe` (refuses any drop, and truncates
> a walk before any step, onto a forbidden cell) and as `extra_bad_cells` into
> `move_sanitizer.sanitize_moves` (fog‑surviving backstop that catches a probe‑
> re‑lit stripped cell the view‑only green helpers miss). Tests:
> `test_tabula_v11_hazard_memory.py` (5) + 4 packager guard tests.

> **✅ B LANDED (0730).** `seam_control._live_core` gates CASE‑2 on the engine's
> own LIVE signal (`red_tiles[].freshness=='fresh'`, matching `value_pyramid`).
> Fogged rival seam → `_rival_deny_pattern` returns a single `CONTEST_DENY` whose
> lone wave is `deny_only=True`: it supersedes the finder + drops a covering
> confirm‑probe and commits NO harvester (the packager's `_pack_seam` skips the
> chain for a `deny_only` wave). LIVE‑confirmed seam → the aggressive
> BLIND_GRAB/UNBEATEN_FLANK/WALK_IN trio as before. Dual‑redsign shows
> `CONTEST_DENY#2` for a fogged rival. `ensure_final_night_deploy` no longer
> counts a deny‑only seam as a deploy. Doctrine CASE‑2/CASE‑3 rewritten to teach
> the confirm‑gate. Full orchestrator_2 suite green (855).

> **✅ A2 LANDED (0730).** `SeamWave.contested` (set on a rival BLIND_GRAB whose
> core is still fogged); the packager threads the seat's LIVE‑red set
> (`seam_control._live_red`) and, on a contested wave, truncates the sweep before
> the first step that is not live‑red — never blind‑walk a fogged neighbour that
> may already be stripped green. NOTE: after Part B (fogged rival → CONTEST_DENY,
> live rival → land on confirmed value with a 0‑step contested grab) the blind
> sweep is largely unreachable, so A2 is a *defensive backstop* + reusable
> mechanism, tested at the packager level (3 tests).

> **✅ A3 LANDED (0730).** `seam_control._CHAFF_CHAIN_STEPS`: under weapons (a
> chaff jam last night or an EMP scar near the seam) the later "secured" waves
> (UNBEATEN_FLANK / WALK_IN / CASE‑1 LATE_SWEEP) cap their comb to 2 steps and
> set `pickup_after`, so they bank and lift inside the safe window instead of
> riding a full serpentine into the jam. Quiet boards ride the full chain
> unchanged. Tests: 3 (no‑chaff long chain vs chaff‑capped early lift, mine + rival).

> **✅ C LANDED (0730) — reframed to the compiler pattern.** The audit's #1 lever
> ("carry the thinker's spatial/temporal constraints THROUGH the handoff to the
> packager") is delivered by *consuming the constraints the thinker already
> emits* rather than adding an LLM coordinate channel (which would reintroduce the
> confabulation v11's compiler pattern removed). The decision schema already
> carries `avoid` (cells) + `chaff_react` (bool), but they only reached the
> advisory LLM‑mover block; now the deterministic packager consumes both:
> `avoid` unions into `forbidden_cells` (drops/steps there refused, same
> mechanism as A1); `chaff_react` caps EVERY chain to `_CHAFF_STEP_CAP=2` (early
> lift). Both are restriction‑only — they can never re‑target or extend a play,
> so the compiler pattern is intact. The thinker addendum now tells the model
> these fields are honoured. The other proposed keys (`offset_from`,
> `stagger_from`, `min_hours`, `pickup_hour`) are ALREADY produced
> deterministically — offset/stagger by `_seat_offset_geom` + `_value_drop`,
> min_hours by the wave cadence (H1/H9/H12), pickup timing by A3 — so no LLM
> coordinate channel was added for them. Tests: 2 (chaff cap on / off).

> **STILL OPEN (this phase):** the validation sweep (mirror / vs‑heur / vs‑v8‑v7
> on seeds 69/2/56) to confirm the s56 green collapse is gone and mirror spread
> narrows. Solo 1‑player smoke (seeds 69/2/56) already passed clean: 4476 / 3105
> / 3193, ZERO green auto‑harvests, no dawn destructions, exit 0.

### Phase 4 — Grounded memories (on‑the‑job learning)
- Keep v10's self‑execution digest; add a compact cross‑day **strategies memory**:
  per play family, a running "tried N, banked M, interdicted K (cause)" line so
  the agent sees which plays pay off on THIS board.
- Persist enemy‑landing memory to `SOC_AGENT_MEMORY` (`kind='enemy_probe_disk_history'`
  pattern already exists) so the frontier‑variation bias survives process restarts.

---

## Determinism vs agency (design invariant)

- **Geometry stays deterministic** in the packager (v10). The pyramid does not
  hand the LLM raw coordinates to retype — it hands **plays with IDs**; the
  packager resolves the real cells. This *reduces confabulation, not agency.*
- **Agency lives in decisions**: which plays to assign to which harvester, and the
  genuine forks (probe‑grab vs walk‑in; take‑the‑rival‑pure vs secure‑my‑mass;
  tempo when ahead vs risk‑off when behind).
- Chaff‑aware chain length is a *packager* safety floor honouring the thinker's
  chosen shape (STRETCH/SWEEP/SAMPLE), not a coordinate the LLM invents.

## Definition of done

- **v11 wins seed 69 in all three matchups**: `v11 vs v11 vs v11` (self‑collision
  + symmetric determinism), `v11 vs heuristic` (performance floor), and
  `v11 vs v8 vs v7` (competitive benchmark).
- **No probe‑starvation dead turns** — every turn with a reachable pure produces
  a harvester play (smash or walk‑in).
- **Honest reflections** — every reflection reconciles to the EXECUTED line; no
  phantom harvests.
- Then run the broader seed set (2, 56) to confirm no regression.

## Mint recipe (fork v10 → v11)

1. `cp -r harnesses/tabula_v10 harnesses/tabula_v11`; rename `TABULA_V10_*`
   labels → `TABULA_V11_*`; update `__init__.py` module docstring/version.
2. Register the v11 binding in `binding_registry.py` (mirror the v10 entry) and
   add the `soc_create_agent` SQL if a server‑side spec is used.
3. Duplicate the v10 test suite → `test_tabula_v11_*`; keep both green.
4. Land Phases 1→4 in `tabula_v11` only (hermetic — v7/v8/v9/v10 untouched).
5. Keep v10 as the fallback champion until the Definition of done passes.

## Open questions

- Does the pyramid *replace* `seam_control`'s pattern families, or wrap them?
  (Lean: wrap in Phase 1 — reuse the geometry — then retire the redundant
  precondition gates in Phase 3 once the taxonomy proves out.)
- Cross‑day strategies memory: per‑session only, or aggregate across seeds?
  (Lean: per‑session first; cross‑seed is a later research bet.)
