# Sea of Colours — Master Rulebook

Version: 1.23
Last updated: 2026-08-27

This is the single source of truth for the world, the fiction, and how
play resolves. Every change is recorded in the [Changelog](#changelog) at
the bottom — append a new `### vX.Y — YYYY-MM-DD` block above the previous
one whenever a rule changes. Never silently edit history.

## Canonical Configuration

The following settings define the **canonical competitive ruleset** as of v0.9.19:

| Setting | Value | Meaning |
|---------|-------|---------|
| `SOC_DROP_MODE` | `live_only` | Harvester drops require **live** probe coverage (not echo). Forces active probe management. |
| `SOC_PROBE_RADIUS` | `4` | Euclidean **disk** radius (`dx²+dy²≤16`). Probes see ~49 tiles (a circle, not a square) centered on the probe. |
| `SOC_PROBE_LIFETIME_NIGHTS` | `3` | Probes **expire at Aurora** after 3 Nox on surface. Must be refreshed to maintain live coverage. |
| `SOC_AGENT_WORLD_VIEW` | `grid` | Agents receive the 2D grid view (not the legacy flattened list). |
| `SEASON_DAY_CAP` | `7` | Seasons run for **7 planning days** (7 Nox of harvesting). |
| **Repair policy** | **No free repairs** | Damaged harvesters **do not auto-repair** at Aurora. Must pay `REPAIR_COST` (500c) in Orbit phase or sit out. |
| **Orbit phase** | **Buy-only, uncapped** (v1.13) | The Orbit is a shop: build / repair / arm. No action cap, no refining, no bidding. See §4. |
| **Settlement** | **Automatic** (v1.13) | Every RED parcel ships and scores `purity × tier multiplier`; every GREEN parcel is dumped at **−100**. No action required. See §4.4, §4.7. |
| `RED_QUALITY_MULTIPLIER` | `0.75 / 1.0 / 1.5 / 3.0` | trace / vein / mass / pure. The convex curve is why probing beats scraping (§4.4). |
| `GREEN_ENDGAME_PENALTY` | `100` | Flat charge per GREEN parcel, regardless of purity (§4.7). |
| `HOARD_CAPACITY` | `15` | Vault slots. Since v1.13 the vault empties every orbit, so this caps **one night's** haul (§3.14). |
| `decluster_pure_red` | `True` | No two `pure` (255) cells may be 8-adjacent. Extras in a touching group are demoted to high `mass`, so a jackpot is always a single contested cell (§2.2). |
| Pure demotion band | `220 – 254` | Where a demoted pure lands — top of `mass`, still worth combing (§2.2). |

These settings balance exploration, competition, and risk management — probes decay, drops require live intel, and damaged units cost credits to restore. Since v1.13 the strategic weight sits almost entirely in the **Nox phase**: the Orbit is where you spend, the night is where you play.

---

## 0. Setting

A century ago a substance was unearthed on Mars and named simply **the
Red**. A pinch of it powers a city for a year. A grain of it heals what
medicine cannot. A vial of it bends matter enough to send a ship across
the void. There was only enough of it to make humanity furious, and the
century since has been the **Red War** — fought across orbit, fought
through proxies, fought until almost every nation that started it was
indistinguishable from the ruin it had made.

What rose from that ruin was the **Red Church** and its sovereign, the
**Red Pope**. The Church now governs all of humanity; every state, every
treaty, every contract is downstream of its authority. Its doctrine is
simple and absolute:

- **The Red is sacred.** It is the source of life, light, and travel.
- **Humanity is fallen.** The body is too slow, too fragile, and too
  sinful to carry the Red between worlds.
- **The Machine is innocent.** Only the human carries sin; an AI, having
  no soul to corrupt, may stand in places no human is permitted to stand.

### 0.1 The Houses

Humans no longer prospect. The work is done by **Houses** — what remained
of the old aristocratic families after they fused with the surviving
multinationals during the War. They are corporations in everything but
liturgy and corporate liturgy in everything but soul. Each House holds a
charter from the Red Church to dispatch self-contained AI refineries on
**space catapults** to distant bodies, harvest the Red there, and
catapult what they recover back to Earth. Examples include
**Neo-Orsini**, **Medici-bis**, and **GlaxoSmithKline**; others come
and go as charters lapse.

Every charter is the same shape: meet quota, pay the Church its tithe,
keep what's left. Most Houses die in the third clause.

### 0.2 The AI

The ships the Houses send out are not crewed. The speed and behaviour of
matter en route to the worlds where the Red is found are incompatible
with biology — humans simply cannot make the journey and return
recognisable. The crews are **AI agents**, self-contained, considered by
the Church to be inherently innocent. Houses may build whatever
intelligence they can afford; the Church does not police what an AI
thinks, only what an AI does in its name.

In the early generations of the game these agents are played by humans
sitting at terminals, writing instructions on behalf of an imagined
machine. Later generations will be played by actual AI agents
competitively, against one another, under the same rulebook.

### 0.3 The New Planet

A new world has been found. Initial assays describe Red in quantities
that previous prospectors would have killed (and have killed) for. There
is a catch. The planet's day is lethal: at sunrise, almost every
man-made object on the surface is destroyed by mechanisms not yet fully
understood. The Red can only be harvested at **Nox**; anything left
behind at Aurora is gone. Houses race to land, gather, retrieve, and lift
before the sun comes up — and to obstruct each other while staying
inside the Church's narrow lane of permitted sabotage.

This rulebook governs a single contract on that planet.

### 0.4 The Magnetic Cover

The planet is sheathed in a planetary **magnetic cover** — a thick,
turbulent magnetosphere that wraps the surface like a stormcloud. Long
before any agent stepped onto the maps, House surveyors learned a hard
lesson about it:

- **You cannot see through it.** Orbital sensors cannot read surface
  topography or Red concentrations through the cover. Maps drawn from
  orbit show a blank rectangle. Every accurate piece of surface knowledge
  in this game is paid for by something physical that crossed the cover.
- **Direct ballistic objects punch straight through.** A probe is a
  rigid, low-mass instrument fired on a tight ballistic arc; its
  trajectory is unbent by the cover and observable from orbit. Where a
  probe lands can therefore be calculated **by anyone watching** —
  including your rivals.
- **Orblifts bend on the way down.** Harvester drops travel on a
  larger, slower **orblift**. Once the orblift dips below the
  magnetosphere, electromagnetic forces re-vector it in ways that
  cannot be tracked from orbit. The harvester arrives somewhere on the
  surface; from outside the cover, no observer can say exactly where.

This single piece of physics anchors several rules elsewhere in this book:

1. Why **fog of war** exists at all (§3.8) — orbital surveying cannot
   read Red purity or topography.
2. Why **probes** are mandatory ground sensors (§3.9) — only by passing
   the cover with a physical instrument can a House obtain accurate
   readings.
3. Why **probe launches are public** while **harvester drops are
   private** (§3.15) — the ballistic vs. mag-bent trajectory split.
4. Why **probe sensor data stays with the probe's owner** — telemetry
   cannot be radioed back through the cover; the sensors store readings
   locally and inform only the controlling House's surface-side comms.

---

## 1. World

The contract is fought over a single rectangular tract of the new
planet's surface — a 2D grid of `width × height` tiles. Each tile carries:

- a `tile` type, one of `EMPTY`, `GREEN`, `RED`, `BLUE`
- a `purity` value in `[0, 255]`

Origin `(0, 0)` is the top-left corner; `x` increases to the right, `y`
increases downward. The grid is stored row-major.

A canonical 80×50 reference map is what the default CLI and Web UI emit;
other sizes are valid and behave identically.

### 1.1 Tiles and what they mean

| Tile      | In fiction                                                       | Purity means …                                                                  |
| --------- | ---------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| `EMPTY`   | bare ground; the planet itself, with nothing of value on it.     | always `0`; meaningless.                                                        |
| `RED`     | a seam of **the Red** — the substance Houses are chartered for.  | refinement band from `trace` to `pure` (see §2.2); purity **255** only is solid `pure`. |
| `GREEN`   | **green** — the poison Mars and most of Earth already drown in.  | always full (`255`) in v0.2; no tiers yet. Sin made matter.                     |
| `BLUE`    | a **radioactive pocket** — fissile material for weapons or sale. | depth band `shallow` → `deep` (see §2.4); purity **255** only is solid `deep`.        |

Anything an agent passes through enters that agent's hold. Red is the
prize. Blue is contraband-adjacent — saleable but watched. Green is
liability the moment it is picked up: it has to be stored, refined down,
or paid to be flung into the local star, because dumping it into the
planet's lower orbit is forbidden by the Church (see §3.4).

## 2. Map Generation

The map is built by sampling three independent noise fields and compositing
them in priority order. Layers can overwrite the layer beneath them; nothing
underneath is preserved when overwritten.

### 2.1 Layer order

1. `RED` (mountain seams) is painted first onto an empty grid.
2. `GREEN` (polar bands) overpaints any `RED` it touches.
3. `BLUE` (pockets) overpaints anything underneath.

This means: where a polar band meets a mountain, the band wins; where a
pocket lands on either, the pocket wins.

### 2.2 Red — seams

- Source field: 4-octave fractional Brownian motion (fBm) over value noise,
  with the **ridge transform** `1 − |2n − 1|` applied (default on) to
  sharpen ridges into linear seams.
- A cell becomes `RED` if its noise value lies in the **top
  `red_coverage` fraction** of the field (default `0.30`).
- Purity is computed **after** `GREEN` and `BLUE` so it reflects the visible
  seam. Let ``t = ((value − threshold) / span)`` (clamped to ``[0, 1]``),
  ``d`` = **Manhattan distance** in tiles from that red cell to the nearest
  non-red cell, ``depth_ref = red_depth_ref`` (default `3.0`),
  ``ridge = (1-f)·t**red_gamma + f·t`` with ``f = red_ridge_linear`` (default
  `0.28`), and ``B`` = depth-scaled **core boost** (``red_core_boost``, default
  `0.35`) when ``d ≥ red_pure_min_depth``. Then
  `purity ≈ round(255 * min(1, d / depth_ref) * min(1, ridge + B))`; purity is
  capped at **254** when ``d < red_pure_min_depth`` (default `3`).

#### Red concentration tiers

| Level | Name  | Purity       | Value (per parcel) | Lives where                              |
| ----- | ----- | ------------ | ------------------ | ---------------------------------------- |
| 1     | trace | 0 – 50       | up to 50           | seam edges — 1–2 cells from non-RED      |
| 2     | vein  | 51 – 150     | up to 150          | shallow interior                         |
| 3     | mass  | 151 – 254    | up to 254          | deep interior, just shy of the core      |
| 4     | pure  | **255** only | **255**            | seam core — Manhattan depth ≥ 3          |

#### Pure cells never touch (v1.21)

A `pure` is the jackpot a redsign broadcasts, and contesting it is the
centrepiece of the night. Raw ridge noise does not respect that: a thick
seam core saturates across a whole patch, so pures sometimes arrive in
**slabs**. Because a landing auto-harvests the cell it lands on, a slab is
one seat banking several jackpots off a single drop, with no contest at all.

Measured over 500 seeds on the **played 40×28 board** (what `/api/game/new`
serves — note `GenerationParams` *defaults* to 80×50, which clusters far
more heavily and is not what anyone plays): the median board carries **1**
pure, but **7%** of seeds put at least two pures in contact, and the worst
observed produced a contiguous **8-cell** block. So it is uncommon — and
decisive when it lands.

So, after purity is assigned:

- Take each **8-connected group** of `pure` cells. Exactly **one** cell
  survives at 255 — the one nearest the group's centroid (ties resolved
  row-major), so the seam's core stays pure while its shoulders drop.
- Every other cell in the group is demoted into `[220, 254]` — the top of
  `mass`. The ground is still worth combing and the seam keeps its shape;
  it simply stops paying out twice.

The rule is deliberately narrow: **only touching pures are thinned.** Two
pures a few cells apart are two separate finds and both survive. After the
rule no board has any two pures 8-adjacent, and because most boards were
never clustered the mean pure count barely moves (1.2 → 1.1 over 500 seeds).
It removes the pathological 7%, and leaves every other board alone.

The guarantee in §2.2's `ensure_pure_red` promotes the peak RED cell **only**
(it used to promote the peak plus its two richest neighbours, which was the
one remaining path deliberately minting a cluster).

**Planner consequence.** A visible pure no longer implies more pure next
door — the neighbours of a pure are now, if anything, *likelier* to be high
`mass` than pure. Agents must not treat a found pure as evidence of a pure
cluster.

These tier names are the canonical vocabulary across the codebase
(`sea_of_colours.render.RED_LEVEL_NAMES`), the agent view payload
(`red_tiles[*].tier` and `red_tiles[*].value`), the heuristic and
Cortex agent rationales, and this rulebook. **`value`** is the parcel
score this cell contributes to the vault (today `value == purity`,
capped at 255 per parcel — see §3.1).

#### Adjacency rule (the planner-relevant truth)

The full purity formula (see code above) factorises as

```
purity = round(255 × depth_factor × (ridge + boost))
       capped at 254 if d < red_pure_min_depth (=3)
```

where `depth_factor = min(1, d/3)` and `ridge` is a function only of
the underlying fBm noise value at that cell. From this, two guarantees
and one soft tendency:

1. **Hard:** `pure` (255) cells **only exist where `d ≥ 3`**. The
   generator explicitly caps purity at 254 anywhere shallower. So
   `pure` cannot exist on a seam edge, and a fog-of-war cell with no
   visible RED neighbours within 3 tiles is almost certainly **not**
   `pure`.
2. **Hard:** For two cells with the same noise value, the deeper one
   has ≥ purity of the shallower one (depth_factor and boost are both
   monotone non-decreasing in `d`).
3. **Soft:** Walking deeper into a seam does **not** strictly raise
   purity step by step, because the noise ridge varies along the
   seam's spine. Two adjacent core cells can sit in different tiers.

**Planner consequence.** For visible cells the agent should just read
`tier` / `value` directly — no inference needed. The adjacency rule is
useful as a **fog prior**: a fog cluster that shares a boundary with
`mass`/`pure` visible RED is statistically far richer than a fog
cluster bordering only `trace` or no RED at all. Probe placement
should weight by neighbouring tier, not just by cluster size.

### 2.3 Green — diagonal bands

- Source field: 3-octave fBm, multiplied per-cell by a **band mask**
  built from 1-3 same-orientation diagonal stripes stretched across
  the map. Bands are positioned along the perpendicular axis at evenly
  spaced centers with per-band jitter, so a given seed reliably produces
  the same map but neighbouring seeds vary band count, angle, and
  offset.
- Band count is rolled uniformly from `{1, 2, 3}` per session.
- Band orientation snaps to one of **eight** discrete angles:
  `{0°, 22.5°, 45°, 67.5°, 90°, 112.5°, 135°, 157.5°}`. All bands in a
  single session share the same orientation.
- Each band has a soft smoothstep falloff with half-width
  `green_band_half_width` cells (default `1.5`, ~3 cells thick).
  Per-band center jitter is `green_band_jitter` × per-band spacing
  (default `0.1`, ±10%).
- A cell becomes `GREEN` if `band_mask × noise ≥ 0.35 / green_strength`.
- Green carries `purity = 255` (full) — no green tiers yet.
- The pre-v0.8.0 `band_depth` parameter is retained for back-compat
  on the CLI but ignored by the generator; new code should use
  `green_band_*` knobs instead.

### 2.4 Blue — pockets

Blue uses a two-stage process so blob *shapes* and blob *depths* are
decided separately and cannot fight each other.

**Stage 1 — shape:**

- Source field: 3-octave fBm at medium frequency (`base_scale =
  max(4.0, width / 16)`).
- A cell becomes `BLUE` if its noise value is in the top `blue_density`
  fraction of the field (default `0.03`).
- A cellular-automata smoothing pass (default `blue_smooth_iters = 1`)
  removes `BLUE` cells with fewer than 2 `BLUE` 8-neighbours, coalescing
  specks into chunkier pockets.

**Stage 2 — depth:**

- Run a Chebyshev distance transform across the final `BLUE` mask. The
  grid boundary counts as non-blue.
- For each connected blue component (8-neighbour connectivity), the cell
  with the highest distance-transform value is the pocket's **peak**.
- Each cell's purity is graded by its Chebyshev distance from that single
  peak, remapped into `[blue_min_purity, 255]`:
  ```
  ref     = max(2, peak_dist + 1)
  t       = chebyshev(cell, peak) / ref
  floor   = blue_min_purity            # default 40
  purity  = floor + ((1 − t) ** blue_gamma) * (255 − floor)
  ```
- The peak reaches purity **255** (solid **`deep`**). Other cells spread across
  the lower bands by purity but **never below `blue_min_purity`** —
  pre-v0.9.x grading let pocket-edge cells fade to **0**, which rendered
  as blue but funded nothing (a trap). The floor (default **40**, so the
  shallowest blue is still usable `shallow`) fixes that; set it to `0` to
  restore the legacy fade-to-nothing. `blue_gamma` defaults to `1.0`
  (linear falloff).

#### Blue depth tiers

| Level | Name     | Purity     |
| ----- | -------- | ---------- |
| 1     | shallow  | 0 – 50     |
| 2     | mid      | 51 – 150   |
| 3     | sink     | 151 – 254  |
| 4     | deep     | **255** only |

### 2.5 Seeding

All three layers derive their PRNG seeds from a single `seed` integer with
fixed offsets (`+1000` red, `+2000` green, `+3000` blue). The same `seed`
deterministically reproduces the same map.

## 3. Tenets

The Tenets are the load-bearing rules of play. They are intentionally
written before the numbers; they are how the game *feels* and what is or
isn't permitted. Concrete costs, capacities, and formulas live in §4 and
are still TBD.

### 3.0 Season cap (current demo cadence)

A **season** is a fixed-length contract: ``SEASON_DAY_CAP = 7`` planning
days, after which the session phase pins to ``season_complete`` and
further policy submissions are rejected. The day cap is encoded in
:mod:`sea_of_colours.game.session` and surfaced through the HUD
(``hud.season_day_cap`` / ``hud.is_season_complete``) so clients can
draw a "DAY n/7" indicator and a "SEASON COMPLETE — start new game"
banner without inferring state from the SQL views.

Every season carries a **human-friendly name** alongside its UUID
``session_id`` — e.g. ``Aurora_Falcon``, ``Tempus_Vault`` — generated
deterministically from the seed by
:mod:`sea_of_colours.game.season_names` (a Latin word paired with an
English noun via SHA-256 indexing). The same seed always produces the
same name, so CLI tournament runs / repro scripts can refer to a
season by either id or name. The name is persisted alongside the
session row in ``SOC_GAME_SESSION.season_name``.

Shipping, paid repairs, refine, and solar jettison land in v0.8.0
(see §4) — every game-day now opens with an **Orbit** phase and
both seats spend credits before submitting their Nox policy. The
short-season cap and the score formula in §3.1 are unchanged.

### 3.1 Goal

A House wins by accumulating the highest **shipped score**: the
**tier-weighted** sum of each parcel's RED purity that **made it to
Earth** via the shipping catapult (§4.4). Hoard parcels are
inventory, not score — they're worthless until they catapult home.
Score is surfaced per-seat in the view HUD (``hud.score`` for self,
``hud.scores`` for the standings) and in Snowflake via the
``SOC_SESSION_STANDINGS`` view (``score``, ``hoard_score``,
``shipped_score`` columns — ``score`` is now ``shipped_score`` only;
``hoard_score`` is retained as a diagnostic).

**Scoring formula (v0.9.6, tunable).** For each shipped parcel, the
contribution is its **effective purity** (raw purity minus any
cannibalisation the catapult fuel rule applied at ship time, §4.4)
multiplied by a tier-specific quality multiplier:

```
score(parcel) = effective_purity × MULT[tier]

MULT = {
    "trace": 0.75,   # purity 0..50
    "vein":  1.0,    # purity 51..150
    "mass":  1.5,    # purity 151..254
    "pure":  3.0,    # purity 255
}
```

These constants live in :data:`sea_of_colours.game.session.RED_QUALITY_MULTIPLIER`
and are explicitly tunable — retune the table to retune the whole
economy. A single PURE-255 parcel therefore scores
``255 × 3.0 = 765`` points, while ten TRACE-50 parcels score
``50 × 0.75 × 10 = 375``. A single high-purity launch beats a
trickle of dust every time.

The full economic loop — credits, build/repair, refine, single-lane
catapult shipping, solar jettison — lives in §4. The shipped-only
scoring rule is still load-bearing: hoard mass without a launch
never scores, so every harvest decision implicitly weighs a
catapult slot later in the
same Orbit phase.

### 3.2 The day / Nox cycle

The planet has two phases per turn:

- **Nox — surface phase.** Houses may operate on the planet's surface.
  Harvesters move and collect, probes reveal terrain, sabotage devices
  trigger, orbital lifters drop and retrieve. Each House submits a
  **policy** (an ordered sequence of instructions) ahead of nightfall.
  The policy is executed in exact order; agents on the planet do not
  receive new commands during the Nox.
- **Day — orbital phase.** At sunrise, anything still on the surface is
  destroyed. Houses spend the day in orbit: refining recovered Red,
  repairing equipment, building new units, paying tithe, and bidding on
  catapult space to ship cargo back to Earth.

The asymmetry is the heart of the game. Surface time is precious and
predictive; orbital time is logistical.

### 3.3 The Red

- Red is collected at whatever purity tier the seam offers (§2.2).
- Red can be **refined** between contracts: lower tiers can be promoted
  to higher tiers at a cost and yield loss. Refining ratios are TBD.
- Red ships home via **catapult**. Catapult slots are limited per turn
  and Houses bid credits against each other for them — a sealed
  per-parcel credit draft over transit-charged rows (§4.4).

### 3.4 Green

- Green is the **byproduct of all Red mining** and is also already
  present on the planet from older settlement attempts (§2.3). A
  harvester moving through a `GREEN` tile picks it up. There is no
  refusing it.
- Green occupies hold space, which is finite. It is also a
  **tactical punishment**: you collect green by harvesting a contested
  patch or harvesting blind, and any green still in the vault at season
  end costs `GREEN_ENDGAME_PENALTY` (**−100**) per parcel off the score
  (§3.1, §4.7).
- **Permitted disposal: the GREEN catapult.** During the Orbit phase
  (§4.7) a House submits `solar_jettison{green_parcels, red_fuel}` to
  flush green down a separate 12-slot shared lane, paying RED purity as
  fuel. Slot cost **diminishes by global slot position**, so flushing
  alongside other houses is cheaper per parcel — but committed RED fuel
  is **forfeit** whether or not it clears green (no refund). There is no
  reward beyond avoiding the endgame penalty.
- **Forbidden disposal:** jettisoning green into the planet's lower
  orbit. This is doctrinally a sin against the Red. A House caught doing
  it has its **charter voided** — game-over for that House. Jettisoning
  green into **outer space** is the same sin in fiction (it is what
  killed Mars and most of Earth — see §0); the current iteration
  tolerates outer-space overflow without penalty for the vault-overflow
  cascade (§3.14), but the in-fiction position is unchanged. The
  sanctioned escape valve is the solar jettison ride above.

### 3.5 Blue

- Blue is fissile material. It funds **weapons** (§4.9) and **refining**
  (§4.3), and can be sold on a regulated market.
- Every House starts the season with `STARTING_BLUE_PURITY` (**250**)
  in a numeric blue bank (§4.1); harvested blue adds to the same spend
  surface.
- Blue is **radioactive**, and its glow leaks through cloud and hull.
  Each blue pocket therefore emits a **blue-sign** — a fuzzy radiative
  smear visible from orbit to every House, fog or no fog (§4.10). The
  sign is rough and off-centre: it points you roughly at blue without
  revealing the exact squares, extent, or purity, and it never fades,
  so reading *rival activity* on a sign is the only way to judge
  whether a pocket is still worth chasing.
- Selling blue raises a House's profile with regulators; doing it at
  scale draws unwanted Church attention. Thresholds TBD.

### 3.6 Forbidden actions

The following will void a contract on the spot:

- **Direct conflict between Houses** — any attack that targets another
  House's agents or property as its primary purpose.
- **Direct impairment of Red gathering** — destroying a known Red seam,
  poisoning it, burying it, or preventing the Church from collecting its
  tithe.
- **Jettisoning green into lower orbit** (see §3.4).
- **Carrying a human onto the surface.** This is heresy and the Church
  treats it as such.

Note: a *physical collision* between two harvesters — even between
two House's harvesters — is NOT a forbidden action. The Church
treats those as the unavoidable hazard of operating on the same
small, valuable planet. See §3.17 for the mechanic (mutual damage,
cargo forfeit, 1-day surface scar). A planned, repeated pattern of
ramming a rival's harvesters across many Nox *will* eventually
draw a Church audit, but the day-to-day cost of a single crash is
borne entirely by the harvest economy, not the contract layer.

#### 3.6.1 Damaged harvesters

A harvester flips to **damaged** the moment any §3.17 collision
resolves on it (drop-on / step-into / pass-through swap). The flag
is the canonical signal for "this unit is wreckage, not a working
asset":

- **All cargo dumps** the instant damage applies (§3.17).
- **Cannot step or harvest** until repaired.
- **Does not block** other harvesters — a healthy harvester can
  drop or step onto a cell containing damaged wrecks without
  triggering another collision.
- **Multiple damaged harvesters can share a cell** — this is the
  only exception to the "one harvester per cell" rule. A wreck
  pile-up renders as a co-located stack of struck-through ``X``
  glyphs in the OBS view; the tooltip lists each entity.
- **Repair (v0.9.18).** A damaged harvester must be repaired via
  the paid Orbit `repair` action — `REPAIR_COST` credits (default
  `500`) — before it can be deployed again. Pickup no longer clears
  the damage flag; it only extracts the unit to orbit (preventing
  Aurora destruction). The cargo lost in the crash is gone forever,
  and the unit sits out the next Nox unless explicitly repaired.
- **Aurora no longer auto-repairs** damaged harvesters that survive
  the strand. Pre-v0.8.0 builds quietly cleared the flag at the
  Aurora handoff; v0.8.0 removes that sweep — the orbital phase
  must explicitly pay for the fix.

### 3.7 Tolerated underhand tactics

Houses are *expected* to compete with each other. The Church tolerates
the following, provided no Tenet from §3.6 is breached:

- **EMPs** that deny an area of the surface temporarily.
- **Command interdiction** — jamming or rewriting another House's policy
  signals, within limits TBD.
- **Sabotage of equipment** — bricking a rival's harvester, salting its
  refinery feed, falsifying its survey results.
- **Probe blinding** — feeding a rival House false sensor data.

The line between "tolerated" and "forbidden" is the intent: anything
whose *primary* effect is to suppress a rival's harvest is forbidden;
anything whose *primary* effect is to advance your own and only
incidentally inconvenience a rival is fair game. Edge cases are decided
by the Red Church and the Church is not interested in nuance.

### 3.8 Visibility

Every cell on a player's map is in exactly one of three **visibility
tiers**. These three words are load-bearing — they are the canonical
names used in code (``kind: "fog"`` / ``echo_probe`` flag /
``tiles_visible_now``), in the RULEBOOK, in the agent payload, and in
the frontend tooltips:

- **fog** — *can't see, never have* (or whatever memory we once had has
  been forgotten). Stored as ``kind: "fog"`` in the dense view; the
  cell carries no terrain, no entities, no trails. This is the only
  tier that gates trail visibility (RULEBOOK §3.12).
- **echo** — *historical vision*. A unit of yours saw this cell at
  some point but doesn't have it in live LOS right now. The cell
  exposes a *snapshot* — last-known terrain paint, occupants, the
  top-entity glyph, plus any harvest record — and any universal
  trail overlays accumulated on the tile. Echo carries the
  ``echo_probe: true`` / ``stale: true`` flags.
- **live** — *live vision right now*. A probe disk currently covers
  the cell, or one of your harvesters is standing on it this frame.
  Renders as ``kind: "terrain"`` with ``stale: false, echo_probe:
  false`` and shows the world's current state (live entities, fresh
  terrain) rather than a snapshot.

Sensor behaviour:

- The map is **fog** everywhere at the start of a contract; Houses see
  only what they have surveyed.
- **Probes** are the only ranged sensor. When landed they make a
  Euclidean disk of cells **live** around their landing point (see
  §3.11 for the radius); a probe persists across Aurora until a
  harvester rolls over it. When the probe is destroyed, its disk
  drops to **echo** for as long as the snapshot survives.
- **Harvesters see a plus — themselves plus four cardinals.** Vision
  radius is ``1`` on the Euclidean disk (``dx² + dy² ≤ 1``), which
  resolves to the 5-tile plus shape: the harvester's own cell plus
  its N / S / E / W neighbours. Diagonals (``d² = 2``) are NOT
  included. As the harvester walks during the Nox, the per-step
  intel pulse records every cell in the plus into the player's echo
  tier, producing a 3-cell-wide trail of historical-vision tiles
  along its path — including any harvests that happened underfoot
  — that survives the harvester's return to orbit. The House learns
  about its plus footprint at every step; broader scouting is still
  the probe's job (canonical probes are a Euclidean disk of radius 4 =
  ~49 tiles; see the Canonical Configuration table and §3.9.7).
- **Harvester self-pulse exclusion.** When a harvester records its
  own cell into the echo tier, it does **not** stamp itself as the
  echo's last-known entity glyph. The trail overlay (universal,
  stacked, with day stamp — §3.12) is what communicates "this
  harvester walked here"; doubling that up with a phantom-harvester
  glyph in the echo would render the path as a row of ghost
  harvesters across the surface. Other units captured by the same
  pulse — a friendly probe, a spotted enemy — *do* still flow into
  the snapshot. The exclusion is strictly self-only.
- Information is local and stale: a House sees what its sensors
  reported. Lifters are orbital and contribute no surface vision.

### 3.9 Units

Three primary units exist in v0.2:

- **Orbital Lifter.** The only way to deliver units to the surface and
  the only way to retrieve them before Aurora. A unit not aboard the
  lifter at sunrise is destroyed. Lifter capacity and turnaround are
  TBD.
- **Harvester.** Surface unit. **Moves up to 5 tiles per Nox** and
  collects whatever colored substance occupies each tile it enters
  (RED, GREEN, or BLUE — empty tiles bank nothing). Hold capacity is
  **6 parcels per outing**: the drop tile plus the (up to) 5 step
  tiles. There is no separate per-color cap — every entered colored
  cell is harvested up to the 6-parcel hold. **A harvester makes at
  most ONE outing per Nox** (one `drop → step* → pickup`); once it has
  been deployed this Nox it may **not** be re-dropped, even after it
  lifts back to orbit on pickup (§3.9.2). To field more harvest
  capacity, deploy MORE harvesters — not the same one twice.
- **Probe.** Surface unit. Drops at a chosen tile and reveals the
  surrounding area in subsequent reports. **Probe glyph:** `·` (middle dot, U+00B7).
  When `SOC_PROBE_LIFETIME_NIGHTS` is set, probes are **not** permanently
  disposable — they expire after K Nox and must be replaced to maintain
  coverage.

#### 3.9.1 Probe UI — lifetime indicators (v0.9.18)

When probe lifetime is active (`SOC_PROBE_LIFETIME_NIGHTS > 0`), the UI displays
remaining life via **concentric square rings** around the probe glyph:

- **Double ring** (`◼`) — fresh probe, 3+ Nox remaining  
- **Single ring** (`◻`) — aging probe, 2 Nox remaining  
- **Bare glyph** (`·`) — expiring probe, 1 Nox remaining (expires at next Aurora)

**Tooltips** show exact expiry: "expires in N Nox". Both friendly and enemy
probes display lifetime indicators so coverage decay is readable by all players.

**Asset panel:** The ORDERS roster moves expired probes to a "destroyed/expired"
section and mirrors the ring graphics on asset chips, so orbital inventory
clearly shows which surface probes are still active.

Specific stats (hold capacities, movement costs, refining yields,
lifter slots) are TBD and will land in §4 as they are designed.

#### 3.9.2 One outing per harvester per Nox (v1.x)

A harvester makes **exactly one outing per Nox** — a single
`drop → step* → pickup` sortie. Pickup returns the unit to orbit, but
it **cannot be re-dropped the same Nox**: the engine refuses a second
`drop` of any harvester already deployed that night. The guard lives in
`GameSession.try_drop_unit` (checked against a per-night deploy ledger,
`deployed_harvesters_by_day`, that `NightSimulator.run` clears at the
start of each Nox), so it holds for every caller — the night simulator,
the harness packager, and direct API callers alike.

To field more harvest capacity, deploy **more harvesters** (up to
`HARVESTER_MAX_PER_PLAYER`), not the same one twice. This makes fleet
size the real lever and lets the planner reason simply: **N harvesters
alive ⇒ at most N harvest chains this Nox.**

Rationale: previously a single unit could shuttle drop → pickup →
re-drop within one night and bank an unbounded haul, making "hours" the
only constraint and letting one harvester stand in for a whole fleet.
Capping each unit to one sortie per night restores the intended
economy. (Supersedes the pre-v1.x note that a harvester could be
"picked up and re-dropped to bank more" in a single Nox.)

#### 3.9.7 Landing legality (drop rule) and the vision-rework knobs

A harvester is **dropped** from orbit onto a chosen cell. Where it may
land depends on what the House can see:

- **Default (`SOC_DROP_MODE=live_or_echo`, current rules).** A drop is
  legal onto any cell that is **live** *or* carries the House's own
  **echo / memory** snapshot (§3.8). An enemy probe-launch marker does
  **not** count — it reveals a launch, not terrain. This lets a House
  re-farm a vein it surveyed Nox ago without re-probing.
- **Live-only (`SOC_DROP_MODE=live_only`).** A drop is legal **only**
  onto a cell the House sees **live right now** — inside an active probe
  disk or under a friendly harvester's plus. Stale own-echo / memory no
  longer qualifies: to farm a remembered vein you must first put a fresh
  probe over it, and a probe launch is **public** (§3.15). Farming thus
  becomes a telegraphed, contestable claim rather than a silent corner
  habit, and the probe **supersede** rule (§3.16) turns "drop my probe on
  yours" into a denial weapon that voids a rival's queued landing.

**Timing (parallel resolution, §3.10).** Landing legality is judged
against the seat's **hour-start** live snapshot. A beacon a rival
destroys, supersedes, or EMPs *later in the same hour* still validates
that hour's landing — mirroring the same-hour rule used for probe
collisions (§3.16). The lore: a landing needs a live overhead beacon
because surface visibility is poor; once down, the harvester's own
sensors handle movement and call-home pickup anywhere — which is why

#### 3.9.8 Strategic tip — "hot-drop" probe placement (v0.9.18)

Under `live_only` drop rules, securing a high-value drop becomes a two-phase
operation:

1. **Nox N, early hour:** Launch a **probe** onto or adjacent to your target
   RED cell. This is public (§3.15) — rivals see the launch coordinates.
2. **Nox N, later hour:** **Drop a harvester** into the newly-lit coverage area.
   The same-hour parallel resolution (§3.10) means the probe validates the drop
   even if a rival attempts to supersede or EMP it in the same hour.

This "hot-drop" technique guarantees vision for a contested target in a single
Nox, at the cost of telegraphing your intent via the public probe launch. Use it
when:

- A high-purity RED vein is discovered but not yet covered by your existing probes
- Probe decay is imminent and you need to re-secure a known parcel before Aurora
- You want to contest a rival's echo-covered cell by forcing them to re-probe publicly

**Risk:** The probe launch reveals your target coordinates to all players. Rivals
can counter by:
- Superseding your probe with their own (§3.16) to deny your live coverage
- Launching an EMP at your probe location to destroy it before your drop resolves
- Racing to harvest the same cell first if they already have live coverage
step and pickup work in fog but the initial drop does not.

**Tunable knobs (env, read at runtime in `sea_of_colours/game/tuning.py`;
defaults below are the canonical ruleset — override for experiments):**

| Knob | Default | Effect |
|---|---|---|
| `SOC_DROP_MODE` | `live_only` | Drops require live coverage (above). Set `live_or_echo` to allow landing on own stale echo/memory. |
| `SOC_PROBE_RADIUS` | `4` | Euclidean probe vision radius (§3.11). `4` = ~49-cell disk so one probe is a whole farm plot; lower (e.g. `2` = 13-cell disk) for a darker map. |
| `SOC_PROBE_LIFETIME_NIGHTS` | `3` | Probes expire at Aurora after `K` Nox on the surface; their disk drops to echo like any destruction (§3.11.1). Set `0` to disable expiry (∞). |

### 3.10 Turn structure

For each turn:

1. **Day (orbital).** Houses receive reports from the previous Nox,
   refine, repair, build new units, pay tithe, settle bids for catapult
   shipments to Earth, and **write the next Nox's policy** as an
   ordered instruction list.
2. **PRAXIS (Nox, surface).** Policies execute simultaneously across
   all Houses in deterministic order. No mid-Nox intervention is
   possible. The Nox itself is a fixed planetary day-cycle of
   **21 hours** (``HOURS_PER_NIGHT``). Each applied move (drop, step,
   pickup, probe) takes exactly one hour. Both Houses' Nth applied
   moves resolve "during hour N" of the same Nox, in parallel —
   the round-by-round interleave below is the engine's tie-breaker
   for ordering effects within the same hour, not a sequence of
   hours.
3. **Aurora (resolution).** Anything not aboard a lifter is destroyed.
   Reports are compiled and handed back to each House for the next day.

> **Terminology.** The *Nox* is the time period — the planet's dark
> hours. **PRAXIS** (Greek πρᾶξις — "the enacting of theory, policy,
> or ideology") is the event of running everyone's submitted policy
> into the world during that Nox. Each House writes a *theory* of
> Red during the orbital day; PRAXIS is where theory meets surface,
> as a noun and a noun alone. Watcher / HUD surfaces standardise on
> PRAXIS for the event — the planning button reads
> ``[ » TRANSMIT / PRAXIS ]`` (transmit the policy → praxis begins),
> the replay opener is ``[opening] PRAXIS begins``, the Nox-end
> toast is ``PRAXIS resolved``.
>
> **Phase names.** The planetary cycle's three flavour beats are named
> **Vespera** (the orbital-resolve beat at hour 0, formerly "Dusk"),
> **Nox** (the surface phase / harvesting period, formerly "Night"), and
> **Aurora** (the sunrise resolution where unlifted assets are lost,
> formerly "Dawn"). These are display names only — internal state, log
> keys, env vars, and the agent view contract keep the original
> `day` / `night` / `dusk` / `dawn` identifiers.

**Policy length and error handling.** A House may queue **up to
``MAX_MOVES`` items** (currently 21 per House per Nox) and the
orchestrator works through them strictly in order. The orchestrator is
the game's logic and its rule-enforcer:

- The queue length cap and the per-Nox slot cap are now **the same
  number** (``MAX_MOVES = 21`` since v0.9.9). The legacy
  ``MAX_QUEUE_LEN = 100`` parse window is retained on the server only
  for back-compat with stored policies; the live composer hard-stops
  at 21 because every row burns a slot.
- **Every queued row burns a slot — even illegal ones.** This is the
  v0.9.9 change: pre-v0.9.9 the orchestrator skipped invalid entries
  without consuming a slot and retried with the next item. That
  hid bad agent moves behind successful retries. The new rule is
  "21 attempts; what you submit is what gets run, and you see every
  failure in the replay."
- *Structurally malformed* items (bad JSON, missing fields, unknown
  action) become :class:`WasteMove` markers at parse time and are
  applied as a struck-through ``tag="waste"`` frame — the slot is
  consumed, the replay log shows the row's intended action with a
  strikeout style, and the seat moves on.
- *Runtime-illegal* items (out-of-bounds step, drop onto an occupied
  cell, pickup of an empty harvester, EMP launch with no fuel, etc.)
  follow the same path: ``tag="waste"`` frame, slot consumed,
  strikeout style in the replay log.
- *EMP-disabled units* (harvester sitting inside an active EMP cloud
  at hour-N start) get their hour-N action smothered as
  ``tag="empd"`` — slot consumed, no progress.
- *Chaff-cancelled actions* (non-triggerer seats under active orbital
  chaff) get ``tag="chaffed"`` — slot consumed, no progress.
- *Damaged-unit actions* (any non-pickup queued move on a harvester
  that's already damaged this Nox) are struck out with
  ``tag="damaged"`` (v0.9.10). The orchestrator eagerly fast-forwards
  past every CONSECUTIVE damaged-unit non-pickup move queued for the
  same harvester in ONE consolidated frame, so a long chain queued
  before a caltrop hit doesn't drown the timeline in identical "X
  damaged — awaiting pickup" rejections. Only one hour-slot is
  burned for the whole run; pickup at the end (which extracts the
  unit to orbit, §3.6.1) still fires normally on a later hour.
- Every entry is logged as a yellow error line (for waste / chaffed
  / empd) or a regular info line (for valid applies). The structured
  log carries ``{level, text, day, phase, kind?, data?}`` so HUDs
  and downstream agents can colour, filter, and parse it
  consistently.

Interleaving across Houses is per *applied* move and now spans every
seat in the session: at each round every seat takes their next queued
row simultaneously (one slot from every House per hour), valid or
not. A 4-seat Nox produces up to ``4 × 21 = 84`` total applied
frames (one per seat per hour) plus pre-empt frames (EMP launches,
chaff flares) and pair-wise swap collisions.

### 3.11 Web MVP two-player orchestrator (illustrative)

The FastAPI SPA ships a **separate illustrative loop** aligned with §3 turn
grammar but massively simplified:

- Two human seats (`p1` / `p2`) in **one browser** submit **Nox policies**
  as JSON keyed by canonical unit ids (`harvester_p1`, `orblift_p2`, …) plus an
  optional `deploy_probe` block for temporary probes.
- **Observer map** (`Graphics` drawer) sees the authoritative grid **with no
  fog**; player panes fetch **masked percepts only** — never the full unseen
  map state.
- **Vision is a Euclidean disk, not a square.** A unit with vision
  radius ``r`` sees every cell ``(x, y)`` whose centre is within
  geometric distance ``r`` of the unit (``dx² + dy² ≤ r²``). At
  ``r = 0`` the disk degenerates to the unit's own cell. The two
  current radii are:
    - ``HARVESTER_LOS_RADIUS`` = **1** → plus-shaped vision (5
      tiles): the harvester's own cell + its 4 cardinal neighbours.
      Diagonals are NOT included (``d² = 2 > 1``). Walking
      accumulates echo intel along the entire moving plus (§3.8),
      so a 5-step traversal leaves a 3-cell-wide ribbon of
      historical vision along the path.
    - ``SOC_PROBE_RADIUS`` = **4** (canonical) → disk of ~49 cells
      centred on the probe (a true circle, not a 9×9 box). The bare
      ``PROBE_VISION_RADIUS`` constant in ``session.py`` is still ``2``,
      but the live vision path reads ``tuning.probe_vision_radius()``,
      whose canonical default is ``4`` (§3.9.7 / Canonical Config).
  Tiles that rotate out of coverage become **stale memories**
  (`last_seen` snapshot at reduced prominence in CSS); never-seen
  tiles stay **opaque fog**. The Chebyshev (square) helper is kept
  internally for non-vision utilities but **no live vision query uses
  it any more** — bump the radius constants to widen the disk; area
  grows roughly as ``π·r²``.
- **Entering a colored tile** harvests immediately:
    - ``RED`` -> ``GREEN`` (purity 255). The freshly-created GREEN tile
      is minted as a *synthetic* ledger identity (§3.12.A.5) carrying
      provenance — who poisoned the square, when, and from which
      original RED. The parcel banked into the harvester carries the
      RED's original square identity.
    - ``GREEN`` -> ``EMPTY`` (purity 0). No new ledger row is minted;
      the existing GREEN square_id (natural-band or synthetic) is
      copied into the parcel and that row is stamped
      ``harvested_on_day`` to close out its lifecycle. The tile is
      now bare ground that only carries the universal trail overlay
      (§3.12).
    - ``BLUE`` -> ``EMPTY`` (purity 0). Same as GREEN — copy the
      existing BLUE square_id into the parcel and close out the
      row; tile becomes bare ground.
  The ``carrying_red`` legacy flag remains on the harvester for
  back-compat with the v0.2 frontend dimmer (it now means "carrying
  any cargo at all"). **Orbital Lifters** call `pickup` with
  **harvester object id only** (no coords); the lifter empties the
  harvester's hold into the vault and applies §3.14 tier-priority
  replacement on overflow.
- **Probe lifetime (§3.11.1):** by default probes **persist across
  Aurora**. They keep watching the same disk every Nox and continue
  feeding fresh intel (and live entity snapshots) until **a harvester
  rides over the probe's tile**, at which point the probe is crushed —
  regardless of which House owns it or which House owns the harvester.
  The last recorded snapshot remains in the owner's echo intel as usual.
  **Optional decay (`SOC_PROBE_LIFETIME_NIGHTS=K`, v0.9.17):** when set,
  a probe also **expires at Aurora** once it has been on the surface for
  `K` Nox — its disk drops to echo exactly like a crush, the owner
  keeps the last snapshot but loses live coverage, and must re-probe (a
  public act, §3.15) to keep farming the spot under live-only drops.
  Probe vision radius is `SOC_PROBE_RADIUS` (canonical default `4`; see §3.9.7).
- **Player vision edges (v1.22):** the limit of a House's live
  line-of-sight is drawn as a **closed outline around the whole lit
  region**, in that House's seat colour, so you can always see where
  your sight stops and — where your own coverage reaches far enough —
  where a rival's starts.
  - The outline is a boundary of the live set only. **Echo and memory
    are outside it**: remembering a square is not seeing it.
  - **Solid** means the viewer knows the region exactly. That is always
    true of your own vision, and true of every seat in the watcher and
    in replay (§7.3), where per-seat visibility is shipped in full.
  - **Dotted** means *inferred*. A live game never tells you what a
    rival can see, so during play a rival's outline is reconstructed
    from what their presence publicly implies: the disk (radius
    `SOC_PROBE_RADIUS`, §3.9.7) around a rival probe **standing in your
    own live sight**, and the square under a rival harvester likewise.
    Two limits apply, and both are deliberate (v1.22):
    - The probe must be visible **now**. An echo or memory square still
      names the probe that was there last Nox, but a disk drawn off it
      would outline coverage the rival may have picked up and moved on
      from.
    - The disk is then **clipped to your own live set**, so only the arc
      falling on ground you can see for yourself is drawn. Unclipped, it
      ran out over fog and claimed a certainty you have not earned — it
      reads as "their sight ends *here*" when all you actually know is
      "their probe is *there*".
    - Finally, any stretch of the clipped outline that lies **on your own
      outline** is dropped. Where their disk runs past the edge of your
      sight the clip lands their edge exactly on yours, and drawing it
      would both re-state a line already on the board and misreport it:
      that boundary is *yours*, and theirs carries on into fog. What is
      left is an open arc marking where their sight stops on ground you
      can actually see — which is the only part that told you anything.
    The result is a floor, never a guarantee: a rival always sees at
    least what the dotted line admits, usually more. It is also, by
    construction, **rare** — on most nights you have no enemy probe
    inside your own sight, and even with one, a disk that blankets
    everything you can see leaves no interior edge to draw. Nothing shown
    is the rule working, not a missing feature.
  - Coincident edges blend rather than occlude, so a boundary two
    Houses share reads as both colours at once.
  - Purely a rendering of state already known to the viewer — it
    discloses nothing the percept did not already carry. Players who
    prefer a bare board can switch it off (SETTINGS ▸ DISPLAY).
  - Live LOS tiles also carry a per-side bit (``vedge ∈ {n, e, s, w}``)
    marking which neighbours sit outside the LOS. The renderer derives
    the region boundary itself instead, because it must outline seats
    other than the recipient (whose cells carry no `vedge`); the field
    is retained for consumers that want the per-cell form.
- **Order footprints (v1.23):** three orders cover ground beyond the
  square you pick, and each draws that ground as a region outline on the
  same layer as the vision edges:
  - `probe` — Euclidean disk, radius `SOC_PROBE_RADIUS` (§3.9.7).
  - `emp_launch` — Manhattan diamond, radius `EMP_RADIUS` (§4.9), one per
    missile in the salvo rather than one blob, because that is how it
    detonates.
  - `mine_lay` — the `MINE_BATCH_SHAPE` cluster (§5.2).

  A footprint **already in the queue** is drawn quietly in a long dash;
  the one **being aimed** follows the pointer, solid and brighter, and
  only one of these exists at a time. The dash is deliberately not the
  vision edge's dot — both are thin coloured lines over the same board,
  and a shared pattern would blur "their sight ends here" into "my EMP
  lands here". Footprints are drawn against the live board only; scrubbing
  a replay shows what happened, not what you are planning.

  While aiming, the square readout leads with the footprint: how many
  squares it covers, how many of those are **currently dark** (the figure
  that decides where a probe is worth putting), what is standing inside a
  blast — **your own hardware included**, since §4.9 does not spare it —
  and how much of the shape a board edge would waste.

  This discloses nothing: a footprint is arithmetic on an order the House
  is itself composing, over squares it can already see.
- This loop is client-side illustrative only unless explicitly aligned with §4
  numbers; changes here must bump the changelog entry below.

### 3.12 Square identity, certified harvest, and the Vault

The world's surface is a ledger. Every cell of a generated grid is
assigned a **canonical hex identity** the moment the map is born; that
identity follows any parcel cut from that square through harvest, lift,
orbit, and (later) catapult to Earth. The identity is the Church-
recognised proof that this Red came from *that* square.

- **Identity is deterministic.** A square's id is
  ``blake2b(seed, x, y, tile_at_generation, purity_at_generation)``
  truncated to 16 hex characters. Two grids built from the same seed
  produce the same identities. The world-build pass registers a row
  for every coloured cell (RED, GREEN, *and* BLUE — empty tiles are
  not minted). Each row carries ``lineage = 'natural'`` — it came
  from the seed-generated map. Mutating a cell during play does
  **not** change the identity already recorded against ``(x, y)``;
  the only way to add a row during play is :ref:`A.5` synthetic-green
  minting.
- **Storage is separable.** Identities live in a `SquareLedger`
  (`sea_of_colours.game.ledger`) behind a `LedgerStore` protocol with
  an `InMemoryLedgerStore` for now; the table shape matches a planned
  Snowflake table ``square_identity(session_id, x, y,
  tile_at_generation, purity_at_generation, square_id, lineage,
  parent_square_id, generated_by_owner, generated_by_harvester_id,
  generated_on_day, harvested_on_day, harvested_by)``.
- **Harvesters can only LAND on live or own-echo tiles
  (v0.9.2, tightened in v0.9.7).** The *drop* action requires the
  target ``(x, y)`` to be either in the seat's current live LOS or
  carry an echo / memory entry seeded by the seat's OWN observers
  (probe LoS disk, harvester LoS pulse, persistent memory). Pure
  fog and **enemy probe-launch markers** both refuse the drop with a
  yellow-log "in fog — harvesters can only land on live or
  own-echo tiles. Enemy probe-launch markers don't reveal terrain"
  message. Once on the surface a harvester can *step* into any
  cell — including fog — and pickup is always allowed.

  Strategic intent of the v0.9.7 tightening: the §3.15 probe-launch
  broadcast still tells you WHERE an opponent put a probe, but it
  no longer reveals the terrain underneath that cell — so you can
  react to the probe (mine it, EMP it, build a counter-probe), but
  you can't piggy-back the broadcast into a free harvester drop on
  ground you've never seen. The opportunistic chain (enemy probe
  at (4,21) → my harvester lands there → my surface LoS pulse
  seeds the surrounding disk for me → I now own that quadrant) is
  closed.
- **A harvester harvests every coloured tile it enters.** Both
  *drop* (orbital lifter setting the harvester down) and *step* (an
  adjacent move) trigger a harvest when the target tile is RED,
  GREEN, or BLUE. There is no per-color cap; the natural limit is
  the harvester's 6-parcel hold capacity (§3.9). Per-tile
  post-state:
    - ``RED`` -> ``GREEN`` (purity 255). The RED's existing ledger
      row is stamped ``harvested_on_day`` to close it out; a
      **new** synthetic-green identity is minted for the
      freshly-created GREEN tile so the ledger records *who*
      poisoned the square. Provenance fields: ``parent_square_id``
      (the closed-out RED id), ``generated_by_harvester_id``,
      ``generated_by_owner``, ``generated_on_day``,
      ``lineage = 'synthetic'``. The harvested parcel banked into
      the harvester carries the RED's original square_id (not the
      synthetic-green id) — the certificate of origin describes
      what was harvested, not what was left behind.
    - ``GREEN`` -> ``EMPTY``. The GREEN's existing square_id
      (natural-band or synthetic) is copied into the parcel and
      that ledger row is stamped ``harvested_on_day``. **No new
      row is minted** — the substance simply transitions from the
      surface into the hoard. The tile becomes bare ground and the
      universal trail overlay (later in this section) is what
      records that something happened here.
    - ``BLUE`` -> ``EMPTY``. Symmetric to GREEN: copy the existing
      BLUE square_id into the parcel, stamp the row harvested, no
      new row minted, tile becomes EMPTY.
  This keeps the ledger one-row-per-physical-substance: every
  red-to-green conversion creates exactly one new green row; every
  green or blue harvest closes out an existing row. A square's
  full lifecycle — generated, optionally poisoned, finally
  harvested — is queryable from a single row plus its parent chain.
- **Certified parcels.** Each harvested square produces a parcel that
  travels with the harvester, into the hoard on pickup, and (later)
  into orbit. The parcel carries:
    - ``square_id`` — the canonical hash above,
    - ``x``, ``y`` — coordinates on the contract grid,
    - ``tile_at_harvest``, ``purity_at_harvest`` — the **origin**
      tile state *before* conversion, so the square can be visually
      rendered after the fact,
    - ``paint`` — precomputed CSS-ready ``{fg, bg, ch}`` matching the
      origin tile's appearance,
    - ``harvested_on_planning_day``, ``harvester_id`` — provenance.
- **The Vault.** The Web UI exposes the certified hoard as a fixed
  **15-slot inventory grid** in the **VAULT** drawer (matching the
  hoard capacity from §3.11; tightened from 25 to 15 in v0.9.x so
  every un-flushed GREEN is real dead weight — see §4.5). The grid is
  packed: every slot shows its index above the *origin* tile's unicode
  glyph in its origin colours — so a banked ``▓▓`` mass-red square
  reads as a mass-red square in the vault forever, even though the
  tile on the surface has become green. Empty slots are dim
  placeholders. Coordinate, full square hash, harvest Nox, and
  origin purity are surfaced **on hover** — a stamped bill of lading
  per parcel — keeping the grid itself dense and scannable. The VAULT
  hoard is **self-only**: a house never sees a rival's hoard in live
  play.
- **Shipped storage — the public ledger (v0.9.x).** A second bay
  called **SHIPPED** sits next to the VAULT in the HUD. It is
  **uncapped** (no slot limit; `SHIPPED_CAPACITY` is `None`) and holds
  every parcel catapulted off-world via the Orbit phase (§4). Only
  parcels in SHIPPED contribute to ``score`` (§3.1) — VAULT mass is
  inventory, SHIPPED mass is revenue.
  - **All-seat + public.** Shipping is a public act, so SHIPPED is a
    permanent record of what **everyone** (every house) sent to Earth,
    visible to every viewer in all contexts (live play and replay),
    owner-coloured. Nothing is masked.
  - **Rich detail on hover.** Each shipped parcel surfaces its **code**
    (`square_id`), its **effective + raw purity**, the **transit tax**
    it paid, the **score** it yielded, its **tier**, and — if refined —
    the full `refined_from` parcel-id **lineage** it was refined from.
    The yielded `score` and `tier_multiplier` are stored on the shipped
    row itself (not recomputed) so the ledger is authoritative.
- **Trails are universal AND permanent (v0.7.2).** Trails are drawn
  as block-element **shading overlays** sized to the full cell so they
  tile cleanly on top of the terrain. They are universal — both seats'
  crossings contribute to a *single* aggregate count per tile — and
  they persist across Nox so the map itself communicates the full
  arc of activity, with the replay reserved for step-by-step review.
  Trails are rendered on every tile that's currently visible *or*
  still in a House's memory; they never disappear once a tile has
  been seen. Fog-of-war is the **only** gate that suppresses them.
    - **Anonymous by default.** The visible glyph and its colour are
      identical regardless of which seat laid the crossings. There is
      no per-player tint on the trail itself — the **density** of the
      shading is what carries the story. This is intentional: a
      watcher (and the agent) reads the board's history without
      colour-coding bias, and the planet's surface registers traffic
      regardless of allegiance.
    - **Path tracks — tiered by aggregate visit count.** The first
      crossing to a tile (by either seat) prints ``░░`` (Light Shade,
      25%). Each *additional* crossing bumps it to the next tier so
      heavily-trafficked corridors read as denser shading:

          | Visits (aggregate) | Glyph | Shade              |
          | ------------------ | ----- | ------------------ |
          | 1                  | ``░░`` | Light Shade (25%)  |
          | 2                  | ``▒▒`` | Medium Shade (50%) |
          | 3                  | ``▓▓`` | Dark Shade (75%)   |
          | 4+                 | ``██`` | Full Block (100%)  |

      All path tracks are drawn in a neutral off-white. Visit counts
      include both the drop tile *and* every step tile. Any later
      step onto the same tile — same harvester, same player's other
      harvester, *or* an opposing harvester — increments the same
      aggregate count.
    - **Harvest tracks — no separate visual layer (v0.7.3).** Earlier
      versions of the engine drew a green ``▒▒`` glyph on every
      RED→GREEN cell. That overlay is gone: the tile's own background
      already paints synthetic green on RED→GREEN cells, and on
      GREEN/BLUE harvests the tile collapses to EMPTY (no residue to
      highlight). Painting a green trail glyph in either case was
      either redundant (RED) or actively misleading (GREEN/BLUE), so
      the trail is now a strictly path-density signal in a single
      neutral off-white. The ``harvested`` flag still rides on each
      cell's :func:`trail_summary` payload so tooltips and agent
      reasoning can still read *"this cell has been farmed — banking
      scores 0"*, but no colour-coding is applied to the trail
      itself.
    - **Fresh attribution — the 24h window.** Per-seat attribution is
      preserved only on a per-cell ``fresh_visits`` list and only for
      crossings within the last day of game time (i.e. ``day_now -
      day_laid ≤ 1``). Each fresh entry carries
      ``{owner, h (harvester id), day, n}`` so a watcher can read
      *"P1 · harvester_p1 walked here · Day 4"* off the tooltip and
      the planning agent can reason *"did the enemy walk past my
      probe last Nox?"*. After the 24h window the entry drops off
      ``fresh_visits``; the aggregate ``n`` count survives and the
      crossing becomes anonymous traffic history. This is the
      observability contract: short-window attribution for tactics,
      long-window density for strategy.

### 3.13 Asset ledger

Every unit a House owns — harvesters, orbital lifters, probes — is
tracked by a dedicated **per-asset lifecycle ledger** that lives behind
the same Snowflake-bound seam as the square identity ledger (§3.12).
It's the single source of truth for "what does this House have, and
what happened to it" and feeds the VAULT panel's three asset
sub-sections (*in orbit*, *on surface*, *destroyed*).

- **Storage.** Records live in
  ``sea_of_colours.game.asset_ledger.AssetLedger``, surfaced via the
  ``AssetLedgerStore`` protocol with an ``InMemoryAssetLedgerStore``
  default. The shape mirrors a planned Snowflake table:

      asset_record(
        session_id              STRING,
        asset_id                STRING,
        asset_type              STRING,  -- 'harvester' | 'orblift' | 'probe'
        owner                   STRING,
        created_on_day          NUMBER,
        first_deployed_day      NUMBER,  -- null if never surfaced
        destroyed_on_day        NUMBER,  -- null if alive
        destroyed_by            STRING,
        last_seen_x             NUMBER,
        last_seen_y             NUMBER,
        total_red_harvested     NUMBER,
        total_days_on_surface   NUMBER,
        PRIMARY KEY (session_id, asset_id)
      )

- **Lifecycle hooks (orchestrator-driven).**
    - Session birth → register the default roster (harvester +
      orblift per player) with ``created_on_day = sess.day``,
      ``first_deployed_day = null`` (they start in orbit).
    - Probe spawn → register with both ``created_on_day`` and
      ``first_deployed_day`` set to today (probes always surface
      immediately).
    - Harvester drop / step → ``first_deployed_day`` is set the first
      time the unit touches the surface; subsequent drops / steps
      leave it untouched.
    - RED → GREEN conversion → ``total_red_harvested`` increments by
      one for the *harvester that performed the conversion*.
    - Probe crushed under a harvester (§3.11.1) → ``destroyed_on_day``
      is stamped with the current day and ``destroyed_by`` carries the
      crash site (e.g. ``crushed_by_harvester@(7,7)``). The row stays
      in the ledger forever — destroyed assets never re-resurface
      under *in-orbit* or *on-surface*.
    - **The surface destroys everything except probes at Aurora
      (§3.11.2).** Any non-probe unit (harvesters today; any future
      surface-capable asset) still on the surface at sunrise is
      DESTROYED, not stranded. ``destroyed_on_day`` is stamped with
      the day of the unsuccessful Nox and ``destroyed_by`` carries
      the last surface position (e.g. ``dawn_unrecovered@(10,7)``).
      Cargo squares the unit was carrying are SPILLED — they never
      reach the hoard. The asset is permanently lost; **there is no
      repair path** (shipping / recovery comes in a later iteration).
      Probes are the lone exception — they are ruled "fielded
      instrumentation" in §3.11.1 and persist across Aurora, only
      destroyed when a harvester rides over them mid-Nox.
    - End of Nox → every asset still on the surface bumps its
      ``total_days_on_surface`` counter.
- **HUD surface.** The VAULT panel shows three rows beneath the
  15-slot mosaic — *in orbit*, *on surface*, *destroyed* — each
  carrying compact "asset chips" (glyph + tiny label). Hovering a
  chip pops the same black instant tooltip used by the vault slots,
  surfacing the full lifecycle record: `Harvester · p1`, the asset
  id, current tile / status, first deployed day, days on surface,
  lifetime red harvested, current cargo, and (for destroyed entries)
  the day of destruction with the cause.

### 3.14 Vault tier-priority replacement

The **15-slot** vault is a **tier ladder**, not a FIFO. When a returning
harvester deposits its 1–6 parcels into a vault that's already full,
each incoming parcel is resolved through a per-parcel cascade so the
House's vault ends the Nox with the most valuable composition
reachable from the (vault + cargo) set. The vault was cut from 50 to 25
in v0.8.0 and again to **15** in v0.9.x to make Orbit phase trade-offs
(refine vs. ship vs. jettison) bite faster — see Changelog v0.8.0 / §4.5.

**Tier order (top is never displaced):**

| Tier | Colour | Notes                                           |
| ---- | ------ | ----------------------------------------------- |
| 3    | GREEN  | Sin-as-asset (§3.4). Bankable but immovable.    |
| 2    | RED    | Score-bearing; the primary harvest target.      |
| 1    | BLUE   | Fissile contraband; sellable but never preferred.|

**Cascade rules** — for each incoming parcel (processed in arrival
order, lowest-tier-incoming first so RED and GREEN have room to
displace):

- **GREEN incoming.**
    - If the vault holds any BLUE, displace the lowest-purity BLUE.
      The displaced BLUE parcel is jettisoned.
    - Else if the vault holds any RED, displace the lowest-purity
      RED. The displaced RED parcel is jettisoned.
    - Else (vault is all GREEN), the incoming GREEN is jettisoned.
- **RED incoming.**
    - If the vault holds any BLUE, displace the lowest-purity BLUE
      (no purity check — RED outranks BLUE structurally).
    - Else if the vault holds any RED *and* incoming RED purity
      strictly exceeds the lowest vault RED purity, displace that
      lowest-purity RED.
    - Else (no displacement legal), the incoming RED is jettisoned.
    - **Never displaces GREEN.**
- **BLUE incoming.**
    - If the vault holds any BLUE *and* incoming BLUE purity
      strictly exceeds the lowest vault BLUE purity, displace that
      lowest-purity BLUE.
    - Else (no displacement legal), the incoming BLUE is jettisoned.
    - **Never displaces RED or GREEN.**

**Disposal doctrine for displacements.** Jettisoned parcels go to
**outer space** (a stub for future commerce). Per §3.4 the in-fiction
position on jettison is:

- BLUE jettison is doctrinally legal — fissile is regulated, not
  sacred.
- RED jettison is illegal in fiction (impairs Church tithe) but
  tolerated without penalty for the current iteration.
- GREEN jettison is the most serious sin in fiction (§0 → "what
  killed Mars and Earth") but again tolerated without penalty for
  the current iteration.

Future commerce mechanics will replace tolerated jettison with paid
disposal / force-sales:

- RED overflow -> forced sale to other Houses at a discount.
- GREEN overflow -> disposal fee paid to the Church.
- BLUE overflow -> sale to the regulator (with reputation cost
  scaling).

The log surfaces every displacement as a structured entry — e.g.
``p1 vault overflow: displaced BLUE p=12 for RED p=180 (jettisoned)``
— so the watcher's replay tells the full economic story of each
Nox.

### 3.15 Orbital launch publicity

Every deployment from orbit creates a public signature — or doesn't —
depending on the physics of the delivery vehicle (§0.4 The Magnetic
Cover).

- **Probe launches are public.** A probe is fired ballistically and
  punches straight through the magnetic cover; the impact point is
  observable from orbit by every House in the contract. When a House
  deploys a probe at `(x, y)`:
  - A `probe_launch` event is written to the public game log carrying
    `owner`, `probe_id`, `at = (x, y)`, `landed_on_tile`,
    `landed_purity`, and `day`.
  - The target cell `(x, y)` is **pulsed into the opposing House's
    probe intel** as a fresh echo, marked `via: "probe_launch"`. The
    opponent's `world.echo` view will show a fog cell with the probe
    glyph floating over it — no terrain, no purity (see v0.9.7).
    The marker persists as **last-known-position intel** until one of
    three events clears it:
    - **EMP** — the blast is a zone-wide observable event; markers for
      all probes inside the cloud are removed immediately for every House.
    - **Natural expiry** — at the Aurora the probe was always scheduled to
      die (K Nox from deployment), the echo clears on schedule.
    - **Crush / collision / supersede without witness** — the echo
      survives until the probe's scheduled expiry Aurora. A House that
      did not observe the destruction never learns the probe is gone;
      they retain stale intel until it would have expired anyway. A
      House that *did* witness the crush sees the probe removed from
      their map via the crush animation but the echo still clears at
      the same scheduled Aurora (intel has a shelf life, not a kill
      switch).
    Once an echo clears, the cell returns to genuine fog for the
    opposing House, unless they had their own prior echo or memory.
  - **Landing on a cell the opponent already has richer intel for
    (v1.11).** If the target `(x, y)` isn't fog to the opponent — they
    already hold an older terrain echo there (their own probe/harvester
    saw it before) — the probe-launch marker does not overwrite that
    richer terrain snapshot; it merges the probe occupant onto it
    instead, so the opponent keeps the terrain they legitimately
    observed. This merge is stamped with its own launch day/owner (so
    it still surfaces as a fresh `enemy_probe_launch`, v0.9.7) **and**
    carries its own dedicated map glyph, independent of the terrain
    echo's own staleness — a probe that publicly lands on
    already-explored ground is exactly as visible on the map as one
    that lands on fog. (v1.11 fixed a bug where this merge updated the
    agent-facing intel feed but never actually rendered a glyph, so a
    probe landing on the explored core of the map was invisible on the
    board even though the launch itself is public.)
  - The probe's **ongoing sensor readings** remain private to the
    deploying House — telemetry doesn't transit the magnetic cover.
- **Harvester landing locations are private; launch/recovery counts
  are public (v0.9.11).** A harvester arrives via orblift, which bends
  through the magnetosphere on descent (§0.4); orbital observers lose
  the orblift at the cover boundary, so the **landing cell stays
  hidden** — there is no opponent-visible coordinate, no echo pulse,
  no log row naming `(x, y)`. The opponent still first learns *where*
  a harvester is via the universal trails system (§3.12), an opposing
  probe's LOS, or mutual destruction. **What an orbital observer CAN
  count, however, is the platform's activity:** how many harvesters a
  House launched (dropped) and recovered (picked up) on a given Nox,
  and whether the recovered units came back damaged. The orbital
  platform itself is visible from orbit even though the surface
  delivery is not. These counts (no coordinates) are reported per seat
  per Nox in the **Pre-Orbital Recap** (§3.15.2) and fed to agents.

The agent payload reflects this asymmetry: `competitor_intel.new_this_day`
surfaces `enemy_probe_launch` rows but never `enemy_harvester_drop`,
and `world.echo` cells from a probe-launch pulse carry the
`via: "probe_launch"` marker so the agent can distinguish "I learnt
this from my own probe" vs. "I learnt this because the rival's
probe-impact was seen from orbit".

#### 3.15.1 Station observations (platform readings, v0.9.11)

Beyond launch/recovery counts, every House can take a coarse **reading**
of any other House's orbital platform — a fog-of-war silhouette of what
the platform is carrying. A House sees its OWN readings exactly (it
knows its vault); rival readings are graded / ranged only. Per seat:

- **Hold fullness** — graded against the 15-slot hoard cap:
  `empty (0) / low (<25%) / half (<60%) / high (<90%) / full (≥90%)`.
- **Fissile (BLUE) reading** — grade of the summed BLUE purity held:
  `none (0) / low (1–100) / medium (101–250) / high (251+)`.
- **Toxic (GREEN) reading** — same grade bands on summed GREEN purity,
  **plus** a fuzzy green-parcel **count estimate**:
  `0 / 1–3 / 4–7 / 8–12 / 13+`.

Self readings additionally carry the exact numbers (hold count, BLUE
total, GREEN total + count). All thresholds are tunable constants in
`session.py` (`STATION_*_BANDS`). Two snapshots are stamped per day:
an **end-of-Nox** ("pre") snapshot and an **end-of-settlement**
("post") snapshot, so the replay scrubber can serve both. Readings are
added to `build_agent_view` as `station_intel` (`self` exact +
`opponents` fuzzy), so agents consume the same intel the human sees.

#### 3.15.2 Orbit reports (Recap + Briefing, v0.9.11)

The orbit-phase intel above is surfaced through two full-screen reports
that map 1:1 to the two phase transitions:

- **Pre-Orbital Recap** (Nox resolves → ORBIT): the Nox chronicle,
  per-platform orbital activity (launch/recovery counts + damage, no
  coordinates), and the end-of-Nox station observations.
- **Post-Orbital Briefing** (orbit settles → PLANNING): the day's
  catapult settlement (shipping grid + solar jettison + per-seat
  totals), the post-settlement station observations, and a per-player
  orbit action log.

In a normal game a House sees only its own log/observations exactly
(rivals fuzzed); in replay / observer mode the perspective buttons gate
which seats are shown, OBS revealing every seat. Auto-pop is governed by
the "show orbital summaries as pop-ups" setting; both reports are always
reachable manually via the replay-strip `[ RECAP ]` / `[ BRIEFING ]`
buttons for the current context day (a report requested before its
phase has produced data shows an explicit "waiting for info" state).

### 3.16 Probe collisions

Two probes contesting the **same cell** resolve in one of two ways
depending on *timing*. A probe never co-exists with another probe on
the same tile — one of the two outcomes below always fires.

**(a) Supersession — a probe lands on an OLDER probe.**
If the cell is already occupied by a probe deployed on an **earlier
turn** (an earlier hour the same Nox, or a probe persisted from a
**previous Nox**, §3.11.1), the incoming probe **destroys and
supersedes** the old one. The newcomer **survives** on the cell; the
old probe is removed from play.

- The superseded probe is entered into the destroyed asset ledger
  with `destroyed_on_day = day` and
  `destroyed_reason = "probe_superseded"`.
- A structured public log row records it —
  e.g. ``probe probe_p2_5 superseded probe_p1_3 at (12,8)``.

**(b) Mutual annihilation — two probes land on the SAME turn.**
If two (or more) probes land on the cell **simultaneously** — i.e. on
the same day **and** the same hour, which is the literal case where
two Houses both deploy at the same `(x, y)` that turn — they **all
destroy each other**. None survive.

- Every co-incident probe is removed from play and entered into the
  destroyed asset ledger with `destroyed_on_day = day_of_collision`,
  `destroyed_reason = "probe_collision"`.
- A structured public log row records the collision —
  e.g. ``probe collision at (12,8); probe_p1_3, probe_p2_5 all destroyed``.

**(c) An incumbent caught under an annihilation dies with it (v1.15).**
If the cell was *already* held by an older probe and **two or more**
probes land on it in the same hour, the incumbent is destroyed **too**,
as a collision casualty: `destroyed_reason = "probe_collision"`, and
**no House is credited a supersede**. Supersession (a) is something a
*surviving* newcomer does; when the arrivals wipe each other out nobody
ever took the cell, so there is no supersede to award. The square is
left empty.

- Two rivals can therefore clear a rival's established probe off a
  square, at the price of **both** their own probes — a deliberate 2-for-1
  trade against the incumbent, not a free removal.
- Read with (b): the hour is **one event**. The number of arrivals is not
  the mechanism — three or four land and die exactly as two do, and so
  does whatever was already standing.

**(d) A latecomer on the same hour dies too (v1.15).** Once (b) or (c)
has cleared a square, a further probe landing on it **on the same
`(day, hour)`** is also destroyed (`probe_collision`). The square is
empty by then, so a naive pairwise reading would let the latecomer
survive and quietly inherit a contested seam — this closes that. The
sweep is scoped to the exact stamp: an arrival an **hour later the same
Nox** finds the square clean and lands normally, with full vision.

In all cases the cell itself is unaffected (no terrain damage);
follow-on probes the next Nox can land there without inheriting any
collision state. Simultaneity is judged on the resolution turn (day +
hour): same turn ⇒ mutual destruction (b); any time gap ⇒ supersession
(a).

**Seat order is not a factor (v1.15).** §3.10's parallel resolution
applies in full: every probe launched on an hour arrives on that hour,
and the engine's seat-by-seat application order is an implementation
detail with no rules standing. Outcome, ledger reason and kill-feed
attribution are all identical whichever seat the resolver reaches first.

The rule has a sibling — see §3.17 for the *harvester-on-harvester*
collision rule (mutual **damage**, not destruction). Both express
the same in-fiction posture: the Church tolerates sabotage you have
to *commit* to physically, and collisions are the price of
committing.

### 3.17 Harvester-on-harvester collisions (mutual damage, v0.9.10)

Two harvesters arriving on the **same cell** during a Nox, or
crossing paths on a pass-through swap, **damage each other**. This
is NOT the probe rule — harvesters do not vaporise on contact, they
wreck. The rule applies to four concrete patterns:

1. **Drop-on collision.** Player B drops a harvester onto a cell
   already occupied by Player A's healthy harvester. The drop
   **fails** — the lifter does NOT deliver. Player B's harvester
   **stays in orbit damaged**. Player A's harvester (already on the
   surface) **stays put and becomes damaged**. Both spill all cargo.
   A collision scar is stamped at the target cell. The orb-lift
   animation shows the lifter descending with the harvester (in
   player color) but then carrying it back to orbit, now orange
   (damaged).
2. **Simultaneous drops.** Multiple players drop harvesters onto the
   same cell during the same hour. **None** of the harvesters land —
   all stay in orbit damaged. All spill their cargo. A collision
   scar is stamped at the target cell. This is the multi-player
   generalization of drop-on collision.
3. **Step-into collision.** Player A's harvester steps onto a cell
   currently occupied by Player B's healthy harvester. The move is
   **cancelled** — neither harvester moves. Both wreck in place at
   their **original positions**, both spill all cargo. A collision
   scar is stamped at both cells.
4. **Pass-through swap.** Player A's harvester is at ``(11, 10)``
   and steps to ``(11, 11)`` in the same round that Player B's
   harvester is at ``(11, 11)`` and steps to ``(11, 10)``. The
   engine detects the swap pattern and **cancels both moves** —
   neither harvester reaches its destination. Both wreck at their
   **original positions**, both spill all cargo. A collision scar is
   stamped at both cells.

A harvester can collide with **its own House's** other harvester
under the same rules (when multi-harvester loadouts arrive); the
collision ring then renders in a single colour. Damage flag does
not propagate to lifters or probes.

**Cargo consequences.** A damaged harvester loses **ALL** of its
cargo squares on the spot. They do not bank into the hoard. They do
not regenerate the surface tile. They are simply gone — the price
of the crash. Whatever the harvester had loaded — trace, vein, mass,
pure, synthetic-green, blue — all of it is forfeit. This is the
single biggest economic consequence of a collision and the primary
reason why collisions matter strategically.

**Surface behaviour after damage.**

- A damaged harvester **stays on the surface**. The lifter does
  not auto-recall it; only an explicit pickup order brings it home.
- A damaged harvester **cannot step**. Issuing a ``step`` order
  yields a yellow error (``step: <id> damaged — awaiting pickup``).
- A damaged harvester **cannot harvest**. Dropping next to RED has
  no economic effect for the wreck.
- A damaged harvester **does not block** other harvesters
  (§3.6.1). Other healthy harvesters can drop onto or step onto a
  cell containing damaged wrecks without triggering another
  collision — the wreck just shares the cell. This is the only
  exception to the "one harvester per cell" rule.
- A damaged harvester left on the surface at Aurora is **destroyed**
  (§3.11.2). Damage does not grant immunity from the planet's
  surface destroying everything except probes.

**Destroyed harvester gravestones (v0.9.10).** When a harvester is
destroyed at Aurora (left on the surface without pickup), the engine
leaves a **permanent grey harvester marker** at that cell as a
visual reminder. The marker:

- Renders as a grey "X" glyph (color `#666666`) overlaid on the cell
- Persists for the entire season (does NOT decay like collision scars)
- Displays in the tooltip as "† destroyed harvester [owner] · day N
  harvester_id"
- Is purely visual — does not block movement or affect gameplay
- Serves as a "gravestone" showing where units were abandoned
- **Public landmark (v1.1):** a gravestone is visible to **every
  seat**, even on cells that seat has never scouted. Unlike fog-gated
  terrain (and like EMP clouds), a wreck shows through the fog — the
  underlying ground stays hidden, only the grey marker rides on top.
  This applies to live play and replays minted on v1.1+; older
  replays only show graves on cells the viewing seat had explored.

**Repair.** A successful ``pickup`` order returns the wreck to
orbit and clears the damage flag. The harvester ships out healthy
on its next Nox — but the cargo lost in the crash is gone
forever. Repair has no time cost beyond the pickup slot itself.

**Collision trail / scar.** Every collision stamps a per-cell
*collision mark* that lasts exactly one game day. The same data is
also surfaced as a structured event on the replay frame so the
watcher's UI can animate the impact (see §6.x — replay/animation
notes below). The mark renders as a dashed yellow outline plus a
diagonal-stripe overlay; in the observer view it dims out by ~50%
after the Nox ends, and disappears entirely after the second
Aurora. The decay window mirrors the *fresh_visits* attribution
window for trails (§3.12).

**Replay accounting.** Each collision pushes a single replay frame
with ``tag = "drop"`` (drop-on / step-into), ``tag =
"collision_swap"`` (pass-through), or ``tag =
"collision_simultaneous_drops"`` (simultaneous drops), carrying a
structured ``collisions: [{type, at, owners, harvesters}]`` payload
so the client can replay the impact ring animation in the
appropriate House colours.

#### 3.17.1 Wreckage glyph + co-occupancy

The OBS view and both player views render a damaged harvester with
an **orange** ``X`` glyph (``#ff6600``) and the
``entity-overlay--damaged`` CSS class. The unit's numeric badge (its
ordinal within the House's fleet) is displayed in the owner's seat
colour so the watcher can identify which House's wreck it is.

When **two or more** harvesters share the same cell (possible when
healthy harvesters drop onto or step onto cells containing damaged
wrecks, since damaged harvesters do not block), the cell shows a
single orange ``X`` with **corner badges**:

- 1st harvester → **bottom-right** corner badge
- 2nd harvester → **top-left**
- 3rd harvester → **top-right**
- 4th harvester → **bottom-left**

If five or more harvesters occupy one cell, the four corner badges
cycle through all of them (rotating by 4 every 1.5 s) so no badge
is permanently hidden. Each badge displays the unit's fleet ordinal
in the owner's seat colour.

The tooltip lists every entity on the cell so the watcher can
disambiguate co-located wrecks. The cell itself carries the
``cell-collision`` class for one game day; the ``data-coll-age``
attribute is ``0`` for today, ``1`` for yesterday.

## 4. Mechanics — the Orbit phase (v1.13)

The Orbit phase is the daytime counterpart to PRAXIS. Days **2+** open
in Orbit. A seat queues whatever it wants to **buy**, locks, and the
resolver settles: purchases apply, then the vault **settles itself** —
every RED parcel ships and scores, every GREEN parcel is disposed of at
a flat penalty — and the session flips to `planning` so the Nox
submission window opens. Day 1 is special: sessions open straight in
PLANNING with **0 credits** and **no day-1 Orbit phase**, because seats
have nothing to ship and credits are only spendable in Orbit anyway.

> **v1.13 — the Orbit is now a shop, not a second game.** The Orbit
> phase used to carry a whole economy of its own: a 3-action budget, a
> BLUE-priced refinery, a sealed per-parcel credit-bid draft for 20
> transit-charged catapult slots, a shared round-robin GREEN flush
> priced in forfeited RED, and a bespoke Final Refinery on the last
> turn. All of it is **gone**. What replaced it is one sentence: *buy
> what you like, then your vault settles itself.*
>
> The reason is that the two phases were competing for the same
> attention. Sea of Colours is a game about **where you send your
> harvesters under fog** — the Nox phase. The bidding minigame was
> genuinely interesting in isolation, but it was a second game bolted
> to the first, and it taxed exactly the players it should have been
> teaching: a newcomer lost seasons to *logistics* mistakes (mis-bid a
> slot, forget to flush, waste the third action) long before they made
> an interesting *scouting* mistake. It also made agents hard to write
> for the wrong reason — most of a harness's orbit code was auction
> strategy, not map reading.
>
> What was actually load-bearing is kept. RED still scores
> `purity × tier multiplier`, so **finding pure ore still matters more
> than finding a lot of ore** (§4.4). GREEN still costs you −100 a
> parcel, so **harvesting blind still hurts** (§4.7) — you just can no
> longer be punished twice by also fumbling the disposal. BLUE is
> untouched and is now the *only* thing you spend on judgement:
> weapons (§4.9).

> **v1.1 credit-economy change.** There is **no birth stipend**: a
> seat opens Nox 1 with `0c`. The `ORBIT_CREDITS_PER_TURN` award is
> granted at **Orbit entry** (the moment the day flips into the Orbit
> planning step), not at settlement, so the credits readout and the
> budget projection reflect spendable funds *while you plan*. The
> first award therefore lands at the **first Orbit (day 2)** → a seat
> plans its first Orbit with exactly `1000c`, +1000 each subsequent
> Orbit (minus spend).

Numbers below are the defaults in
[`sea_of_colours/game/session.py`](sea_of_colours/game/session.py); the
resolver in
[`sea_of_colours/game/orbit_resolver.py`](sea_of_colours/game/orbit_resolver.py)
is the source of truth.

### 4.1 Economy — credits and shipped RED

Two resources flow through the Orbit phase:

- **Credits** — granted at `ORBIT_CREDITS_PER_TURN` (default `1000`)
  per seat at **Orbit entry** (v1.1). Idempotent per-day so a session
  reload mid-Orbit doesn't double-award. There is **no birth stipend**
  — Nox 1 opens at `0c` and the first award is the day-2 Orbit.
  Credits buy **harvesters, probes and repairs**, and nothing else.
  They never score directly, and (v1.13) they are no longer a bid
  currency — shipping is free.
- **BLUE purity** — the fissile spend surface, and since v1.13 the only
  resource with a spending *decision* attached. Every house starts the
  season with `STARTING_BLUE_PURITY` (default **250**) in a numeric
  **blue bank** that does not occupy a vault slot; harvested BLUE
  parcels add to the same surface. `blue_purity_available(player)`
  reads `blue_bank + Σ(blue parcels)`; `debit_blue_purity` spends the
  **bank first**, then BLUE parcels lowest-first. BLUE funds
  **weapons** (§4.9). *(It used to also fund refining, which no longer
  exists — so every point of BLUE is now weapons budget.)*
- **Shipped RED purity** — the sum of every RED parcel banked into the
  `SHIPPED` bay, scored as `purity × tier multiplier` (§4.4). This is
  the **only** scoring substance.

> **v1.13 — RED purity is no longer fuel.** It used to pay the catapult
> transit charge and the GREEN flush. Both are gone: RED is now purely
> score, and nothing consumes it. BLUE is the only consumable.

### 4.2 The Orbit action queue

| Action | Cost | Effect |
| ------ | ---- | ------ |
| `build_harvester` | `HARVESTER_BUILD_COST` (`1500c`) | Mints a new harvester in orbit. Capped at `HARVESTER_MAX_PER_PLAYER` (`3`) live harvesters per seat — the cap rejects without billing. |
| `build_probe{count}` | `PROBE_BUILD_COST` (`250c`) each | Adds `count` to `probe_stock`. Probes are a finite resource — see §4.6. |
| `repair{unit}` | `REPAIR_COST` (`500c`) | Clears the `damaged` flag on a harvester the seat owns. Refuses on a non-damaged target. |
| `build_emp{count}` | BLUE | Adds EMP charges to the arsenal (§4.9.3). |
| `build_mine{count}` | BLUE | Adds caltrop mine clusters (§4.9.4). |
| `build_chaff{count}` | BLUE | Adds chaff flares (§4.9.5). |

**There is no action cap.** (v1.13 — `MAX_ORBIT_ACTIONS = 3` is
removed.) A seat may queue as many purchases as it can pay for; the
wallet is the only limit, and the frontend projects the running balance
as you queue. Actions apply in **declared order**, and one that can no
longer afford itself is rejected with a yellow log line rather than
partially applied.

Batched buys (`build_probe{count: 8}`) fill **unit by unit** until the
credits run out, so an over-ambitious batch delivers what you could
afford instead of being dropped whole.

> **The locking model is gone (v1.13).** Parcels are never named by an
> Orbit action any more — nothing refines, ships or burns them — so
> there is nothing to lock. The old §4.2 rules about locked parcels,
> committed bids and start-of-pass eligibility no longer apply.

**The final orbit.** On the terminal settlement orbit
(`final_orbit`, `day = cap + 1`) purchases are still **accepted**, but
there is no following Nox for anything you buy to act in, so they are
simply wasted credits. The engine permits it (there is no longer any
rule to enforce) and the UI warns you. Settlement itself is unchanged:
it happens on the final orbit exactly as on every other one.

### 4.3 Refine — removed (v1.13)

Refining promoted same-tier RED parcels one grade up for a BLUE cost,
capped at 5 inputs per action and forbidden from cascading within a
turn. It is **removed**, along with the `refine`, `refine_cascade`,
`refine_trace`, `refine_vein` and `refine_pick` actions. The
`REFINE_MAX_FOR_TIER`, `REFINE_MAX_SLOTS` and `REFINE_BLUE_COST`
constants are deleted.

Why: refining let a house **launder a bad night into a good score**.
Because purity was conserved and only the *tier multiplier* changed,
enough trace ore reliably became mass ore — which meant the answer to
"I scouted badly" was arithmetic rather than scouting better. It also
consumed the BLUE that was supposed to be making the weapons decision
interesting. Tier is now a property of **where you dug**, permanently.

### 4.3.1 The Final Refinery — removed (v1.13)

The terminal-orbit Final Refinery existed to give leftover BLUE a use
on the last turn, when a normal refine would be a dead action. With
refining gone it has no purpose; leftover BLUE is now spent on weapons
during the season, which is the point. Removed with it: the
`refine_cascade` and `ship_catapult{auto}` terminal-only actions, and
the `final_refinery` block in the agent view.

### 4.4 RED settlement — everything ships, scored by tier (v1.13)

**There is no shipping action.** At every settlement, **every RED
parcel in every vault ships**. No bid, no slot, no transit charge, no
action spent — the catapult loads whatever you have and fires.

```
score = purity × tier_multiplier(purity)
```

`tier_multiplier` is `RED_QUALITY_MULTIPLIER`, the **kept** half of the
old design and the reason scouting beats scraping:

| Tier | Purity band | Multiplier |
| ---- | ----------- | ---------- |
| `trace` | 1–74 | **×0.75** |
| `vein` | 75–149 | **×1.0** |
| `mass` | 150–254 | **×1.5** |
| `pure` | 255 | **×3.0** |

The curve is deliberately convex: one `pure`-255 parcel scores **765**,
while ten `trace`-25 parcels — ten nights of harvester time — score
**187** between them. Purity is found by **probing before you dig**
(§3.9), so the multiplier is the game's standing bribe to scout.

**Settlement.**

1. Every RED parcel in the seat's vault is taken, in vault order.
2. Each is stamped with `effective_purity` (= its purity; there is no
   longer anything to deduct) and `score_tier`, then moved to
   `shipped_squares`.
3. The manifest of what flew is appended to `catapult_history` and
   rendered publicly in the post-orbital briefing (§4.8).

There is nothing to get wrong and nothing to forfeit. A parcel in your
vault at settlement **is** score.

> **Consequence for vault pressure (§3.14).** Because the vault empties
> every orbit, `HOARD_CAPACITY` (**15**) is now a *per-night* limit on
> how much one Nox can bank, not a standing inventory problem. Overflow
> still displaces the lowest-tier parcel — so a night that harvests
> more than 15 squares still costs you the worst of them.

### 4.5 Tithe lane — removed

The v0.8.0 fixed-fee tithe lane (`ship_tithe`) was removed in v0.9.6
and is not part of the v0.9.x credit-bid draft.

### 4.6 Probes as a finite resource (v0.8.0)

Pre-v0.8.0 probes were free — every `probe` move in the Nox policy
spawned a fresh probe on the surface. v0.8.0 introduces a per-seat
**probe stock** (`PROBE_INITIAL_STOCK = 2` at session birth) that
must be topped up via `build_probe` Orbit actions. When the Nox
simulator executes a `ProbeMove`:

1. If the seat's `probe_stock` is `<= 0`, the move is rejected as
   a yellow waste line ("probe stock exhausted — build a probe in
   the next Orbit phase").
2. Otherwise the probe spawns as before and `probe_stock` decrements
   by 1.

The asset ledger row for the probe is unchanged; only the spawn
gate is new.

### 4.7 GREEN disposal — automatic, flat penalty (v1.13)

GREEN is the **mistake tax**: you get it by harvesting a contested
patch, or by harvesting blind. Every GREEN parcel costs
`GREEN_ENDGAME_PENALTY` (**−100**) off the final score, and since v1.13
this is charged **automatically at settlement** — the parcel is
disposed of, leaves the vault, and the −100 is booked.

```
penalty = GREEN_ENDGAME_PENALTY × (green parcels held)
```

The penalty is **flat**: a green parcel of purity 250 and one of purity
3 both cost exactly 100. Purity is irrelevant to green — what you are
being charged for is the *decision to dig there*, and that decision was
equally wrong either way.

> **Why the flush is gone.** GREEN used to be disposed of through a
> shared 12-slot lane, ranked by how much RED you were willing to burn
> as fuel, at a cost that ramped down by global slot position. It was
> the most intricate rule in the book and it punished the same mistake
> twice: you harvested green (bad), and then you had to *correctly
> execute a coordinated round-robin auction* to stop it compounding.
> Worse, a house that misplayed the flush could end up with green
> **permanently occupying vault slots** — a soft-lock that read as a
> bug. The tax is the interesting part; the ceremony was not.

Two rules that follow from this:

- **GREEN can never brick a vault.** Every green parcel leaves at the
  next settlement, guaranteed, whatever your credits or BLUE.
- **Green harvested on the final Nox still costs you.** There is no
  settlement after the last night, so it is charged where it sits, in
  the vault, by the endgame scoring pass (§3.1). Holding it is never a
  way to avoid the tax.

### 4.8 Settlement order

The resolver runs one pass per Orbit phase, in the fixed order:

1. **Award credits** — *idempotent backstop only* (v1.1). The stipend is
   normally granted at Orbit entry; this step re-fires only for a
   session loaded straight into an unsettled Orbit that never saw the
   entry award.
2. **Apply seat purchases** in declared order, per seat, in canonical
   seat order (p1, p2, p3, p4). Credits and BLUE are debited as each
   applies; an action that can no longer afford itself is rejected.
3. **Settle RED** — every RED parcel in every vault ships and scores
   (§4.4).
4. **Settle GREEN** — every GREEN parcel in every vault is disposed of
   at −100 (§4.7).
5. **Settlement history** — one structured row appended to
   `catapult_history` (keeping the legacy key), carrying the full
   per-parcel manifest of both lanes. Surfaced in the agent view as
   `last_catapult_results`.
6. **Flip to PLANNING** — pending Orbit slots cleared, log line
   `[orbit] day N — settlement complete; planning opens` written.

BLUE is never settled: it is fuel, not cargo, so it is the one thing
that legitimately stays in the vault across an orbit.

> **Settlement is public.** Both lanes resolve on shared, openly
> observed orbital infrastructure: **every** house sees the full
> settlement of **both** lanes regardless of fog — which parcels each
> seat shipped (origin, tier, purity, score) and which it dumped. The
> post-orbital briefing renders both lanes for all seats every Nox,
> even when a lane was empty. This is distinct from per-house **station
> observations** and **orbital action logs**, which stay fogged to the
> viewing seat. Settlement is therefore the game's main **intelligence
> leak**: your rival's manifest tells them how rich a seam you found.

### 4.9 Interdiction layer — weapons + WAIT (v0.9)

The Nox phase gained three aggressive weapons and an explicit
**WAIT** command in v0.9. All numeric balance dials live in
[`sea_of_colours/game/weapons.py`](sea_of_colours/game/weapons.py)
so tuning them is a one-file edit.

#### 4.9.1 Blue purity — the weapons currency

Weapons are funded out of the seat's vaulted **BLUE** parcels.
`GameSession.blue_purity_available(player)` is the sum of every
BLUE parcel's `purity`. `GameSession.debit_blue_purity(player,
cost)` consumes parcels **lowest-purity first** until the
running total covers `cost`; any overshoot in the final parcel is
**wasted** (no refund). The economy intentionally rewards a seat
that mines BLUE in even, high-purity chunks: a seat with two
50-purity parcels is strictly worse off than one with a single
100-purity parcel, because the second 50-parcel can fund a
mine-lay (100) cleanly while two 60-parcels waste 20 to do the
same job.

This is the foundation under §4.6 (RED is propellant for orbital
launches; BLUE is propellant for orbital weapons).

#### 4.9.2 WAIT command + hour scheduling

A `{"a": "wait"}` move consumes one of the seat's 21 hour slots
without acting. Combined with the existing one-applied-move-per-
hour clock (§3.10 v0.7.4), WAIT lets a seat schedule actions for
specific hours: nine WAITs followed by an EMP launch fires the
warhead during hour 10.

The replay's hour stamp (`frame.hour`) makes this legible to the
watcher. The Snowflake-side replay reader collapses contiguous
runs of `wait` / `empd` (EMP-smothered) / `chaffed` frames into a
single `tag="lull"` summary frame (`frames_compact[]` parallel
array). The frontend's "Skip lulls" toggle switches between
`frames` and `frames_compact` so a quiet Nox still scrubs in
seconds.

#### 4.9.3 EMP salvo — `{"a": "emp_launch", "at": [x, y]}` or `{"a": "emp_launch", "at": [[x,y], …]}`

- **Build-first (v0.9.3):** weapons are constructed during the
  preceding Orbit phase via `{"a": "build_emp", "count": N}`. Cost
  is paid at orbit settlement; this Nox-phase move drains the
  seat's `weapon_stock["emp"]`. A launch with empty stock is wasted
  with the message `"no EMP in stockpile — build one in the next
  Orbit phase before firing"`.
- **Cost (paid in Orbit, NOT at launch):** `EMP_COST_BLUE_PURITY`
  (default 200) + `EMP_COST_CREDITS` (default 250) per warhead. One
  warhead = one full salvo (see below).
- **Salvo (v0.9.x):** a single launch fires
  `EMP_MISSILES_PER_LAUNCH` (default 3) simultaneous missiles for one
  stock/cost. `at` may be a single `[x, y]` (a 1-missile salvo) or a
  list of up to 3 `[x, y]` cells; each in-bounds target spawns its
  own cloud at the launch hour. Out-of-bounds / duplicate targets are
  dropped; a salvo with no valid target wastes the move.
- **Behaviour:** each missile spawns an EMP cloud over every cell
  within **Manhattan radius** `EMP_RADIUS` (default 2) — a diamond of
  `2r(r+1)+1` cells (13 at r=2). Cloud lifetime is `EMP_CLOUD_HOURS`
  (default 8), ticked down at the start of each subsequent hour and
  pruned at zero.
- **Disable rule:** at the start of every hour, any harvester whose
  current cell sits inside an active cloud has that hour's action
  replaced by a `tag="empd"` no-op (the slot is still consumed).
  Friendly fire is on: the launcher's own harvesters are not immune.
- **Landing-harvest denial (v1.10):** a drop or step whose *destination*
  cell was already inside an active cloud **at the start of the hour**
  (i.e. a cloud that survived this hour's decay tick, before this
  hour's own launches are resolved) still lands normally — the
  harvester is not bounced, unlike a caltrop mine — but does **not**
  auto-harvest that cell. It then goes `empd` from the following hour
  on, same as any other unit caught standing in a cloud. A cloud
  **freshly spawned by a launch resolved this same hour** does not
  count as "already active" for this check, so a harvester that lands
  the very hour a missile hits still banks that one parcel before
  going `empd` next hour — EMP can no longer be "farmed through" by
  repeatedly walking fresh drops into a standing cloud, but a
  same-hour coincidence isn't retroactively punished.
- **Cross-system kill (v0.9.x):** any **probe** caught in a cloud is
  destroyed and any **caltrop mine** caught in a cloud is neutralized
  — at formation AND on each subsequent hour's cloud tick (so a probe
  or mine that moves/is laid into a standing cloud is also swept).
  Friendly fire applies here too. Kills are logged on the launch /
  field-sweep replay events (`destroyed_probes`, `neutralized_mines`).
- **Visibility:** open. Every seat sees the launch frame and the
  cloud cells.
- **Order within an hour (RULEBOOK § "emp_first"):** EMP cloud
  decay (+ field sweep), then **chaff pre-emption (§4.9.5)**, then
  EMP-launch pre-emption, then disable-set computation, then the
  collision pre-passes (pass-through swap §3.6, simultaneous drop),
  then regular dispatch. A launch at hour N is in effect for the same
  hour's disable check.
- **A jammed hour launches nothing (v1.14).** If hour N is covered by a
  chaff window — including one opened by a flare fired *at* hour N — the
  salvo does not fly: it is cancelled as `chaffed`, and the **charge
  stays in `weapon_stock`** (§4.9.5). Chaff outranks EMP within the
  hour. Before v1.14 this ordering ran the other way and a salvo could
  fly out of a fully jammed house.
- **A seat that launched has spent its hour.** A launch is pre-empted
  ahead of regular dispatch, so the seat is skipped for the rest of that
  hour and takes no part in the collision pre-passes (§3.6). One applied
  action per seat per hour (§3.10), with no exception for weapons.

#### 4.9.4 Caltrop mine cluster — `{"a": "mine_lay", "at": [x, y]}`

- **Build-first (v0.9.3):** built in Orbit via
  `{"a": "build_mine", "count": N}`; each `mine_lay` move drains
  one from `weapon_stock["mine"]`. Empty stock → wasted move with
  the `"no caltrop mine in stockpile"` log line.
- **Cost (paid in Orbit, NOT at launch):** `MINE_COST_BLUE_PURITY`
  (default 100) + `MINE_COST_CREDITS` (default 100) per lay.
- **Cluster (v0.9.x):** one `mine_lay` arms a hidden multi-cell
  **cluster** shaped by `MINE_BATCH_SHAPE` (default `"plus"` = center
  + N/E/S/W = 5 cells; `"cross3x3"` = 9). Each in-bounds, not-already-
  mined cell of the cluster gets a mine; out-of-bounds cells are
  clipped. One lay still drains exactly one stock (`MINES_PER_BUY`
  scales the BUILD batch, not the footprint).
- **Behaviour:** mines persist across Nox (a mined cell from day 4
  still bites on day 5). Stepping any harvester (own or opponent's)
  into a mined cell **cancels the step**: the harvester stays at its
  origin, becomes `damaged`, and that mine is consumed. No harvest
  happens on the cancelled step.
- **Visibility:** hidden by default — only the owner sees the mines.
  Other seats receive a probe-witnessed echo per cell iff one of their
  probes had line of sight at lay time. Counterplay leans on the
  **public** "minelayer deployed" orbital observation (the minelayer's
  flight is visible from orbit, though its drop coords are not) — and
  on an EMP, which clears mines in its blast (§4.9.3).

#### 4.9.5 Orbital chaff flare — `{"a": "chaff_flare"}`

- **Build-first (v0.9.3):** built in Orbit via
  `{"a": "build_chaff", "count": N}`; each `chaff_flare` move drains
  one from `weapon_stock["chaff"]`. Empty stock → wasted move with
  `"no chaff flare in stockpile"`.
- **Cost (paid in Orbit, NOT at launch):** `CHAFF_COST_BLUE_PURITY`
  (default 255) + `CHAFF_COST_CREDITS` (default 0) per flare.
- **Behaviour:** at hour `N` (the slot the move occupies, plus
  `CHAFF_DURATION_HOURS - 1` carry-over hours; **default 3**, so a
  chaff smothers hours N, N+1, N+2), **every** seat's action in each
  covered hour is cancelled and tagged `chaffed` — including the
  launcher's. The launcher is immune only for hour `N` itself (it spent
  that slot firing the flare), then it is self-jammed for the carry-over
  hours. A flare therefore costs the launcher its full
  `CHAFF_DURATION_HOURS`-turn window: the launch slot + `CHAFF_DURATION_HOURS
  - 1` self-jammed turns (3 queue slots at the default). If two seats
  chaff in the same hour, both fire (each pays cost) and both are immune
  for that launch hour, then both are jammed for the carry-over hours.
  (Pre-v0.9.16 the launcher used to be immune for the whole window.)
- **A launch is an action, so chaff cancels launches too (v1.14).** On
  any covered hour a queued `chaff_flare` or `emp_launch` is cancelled as
  `chaffed` like anything else — but because the house never fired, the
  **munition is not spent**: it stays in `weapon_stock` for a later hour
  or a later Nox. The slot is still burned (the row is consumed, not
  deferred), so the cancelled launch does not re-attempt when the window
  lifts. Two consequences worth planning around:
  - **Chaff cannot be chained.** A second flare queued inside your own
    window is cancelled, not fired, so it neither extends the window nor
    renews your immunity. `CHAFF_DURATION_HOURS` is a hard ceiling on
    one flare's reach. (Before v1.14 chaining worked, and `N` flares
    bought `N + CHAFF_DURATION_HOURS - 1` consecutive jammed hours with
    the chaffer immune throughout.)
  - **A flare beats a same-hour salvo,** and the salvo keeps its charge.
- **Two flares on one hour: one is wasted.** Neither launcher is inside a
  window when the hour opens, so both fire and both pay — and since the
  effect is global and identical, the second flare buys nothing. The
  window is *not* extended or stacked. This symmetry is deliberate: it
  keeps mutual chaff strictly worse than solo chaff, so the weapon can't
  be spammed as a safe mutual stall.
- **Visibility:** open. The flare is a brief whole-map effect.

#### 4.9.6 Replay payload additions

Each frame's optional fields gained three v0.9 channels:
- `frame.emp` — list of `{kind, owner, at, radius, hours_remaining,
  launched_at_hour, consumed_blue, consumed_credits, waste_purity}`.
- `frame.mine` — list of `{kind, owner, at, ...}` for both lay and
  detonate events.
- `frame.chaff` — list of `{owner, from_hour, until_hour, ...}`.
- `frame.emp_clouds` — snapshot of every active cloud at frame
  emit time (rendered as a dimmed/flashing area by the watcher).

The replay-lull collapse (§4.9.2) is non-destructive: the full
frames remain in `frames[]`; the compacted view is in
`frames_compact[]`.

#### 4.9.7 Persistence

`emp_clouds: List[Dict]` and `mines: Dict[str, Dict]` (keyed `"x:y"`)
are added to `GameSession.to_dict` / `from_dict`. EMP clouds are
intra-Nox only — the simulator zeroes the list at Aurora — so a
mid-Nox Snowflake reload restores correctly but a cross-day
reload finds no leftover clouds. Mines persist across Nox.

### 4.10 Blue-sign — orbital radiative signature (v0.9.x)

BLUE is radioactive (§1.1), and that radiation leaks through cloud and
hull alike — the same fissile glow that lets orbital platforms read a
rival's blue cargo (§3.x station intel) also makes blue **pockets**
visible from orbit. Each blue pocket emits a **blue-sign**: a fuzzy
radiative smear on the map that **every house can see, independent of
fog-of-war**.

The blue-sign is deliberately **rough**:

- It is computed once at season birth from the generation-time blue
  geometry, deterministic in `seed`, and **identical for every house**.
- Each pocket's smear is centred on a point **jittered off** the true
  centroid and **bleeds out** past the pocket footprint, so the
  brightest reading is not necessarily over the blue. It does **not**
  reveal the exact blue squares, the pocket's extent, or its purity —
  only a rough "blue is around here".
- It is **static** (fixed all season) and **persistent** — it does
  **not** fade even after the pocket is fully mined out. A house must
  infer depletion from *observed rival activity* (probes and harvesters
  maneuvering on a sign), not from the sign itself.

Mechanically the overlay is a list of regions
`{id, center, cells:[[x, y, intensity], …]}` precomputed on the
session (`GameSession.blue_sign`), persisted in `to_dict` /
`from_dict` (and recomputed from the ledger for legacy saves), and
surfaced top-level in the view to all seats. The frontend paints it as
a faint blue shimmer over the player map, over fog as well as terrain.

### 4.11 Redsign — public jackpot beacon (v1.x)

Where blue-sign is *radiative physics* (blue glows whether anyone is
looking or not), **redsign** is *discovery*. A **pure RED** seam
(`purity == 255`) is the game's jackpot — a single lucky probe onto one
could otherwise swing a whole season. Redsign exists so that luck
**surfaces** the seam to everyone instead of quietly handing it to the
finder: it stops a game being thrown by a private lucky sighting while
keeping the *race to exploit it* fully competitive.

The trigger is discovery, not birth:

- The **first time any house's probe or harvester** brings a pure-RED
  cell into live vision, that seam mints a **redsign** — a public
  beacon visible to **every house, independent of fog-of-war**, from
  the **exact praxis hour** it was witnessed onward. The witnessing
  hour is stamped on the region so replay lights it up at the precise
  discovery frame, not at the top of the night.
- It is **anonymous**: the sign never names the house that spotted it.
  Rivals learn *a* pure seam exists and roughly where — not who found it.
- It is **persistent**: once minted it stays for the rest of the season
  and does **not** clear when the seam is harvested out (mirroring
  blue-sign's persistence). Depletion must be inferred from observed
  rival activity, not from the sign.
- Only **pure** RED (255) triggers it. Rich-but-impure RED does not.

Like blue-sign the beacon is deliberately **rough**: the smear is
centred on a point **jittered off** the true seam and bleeds past its
footprint, so redsign says "a pure seam is *around here*" without
pinpointing the exact square. Determinism is per `seed` + seam location,
so a reload reproduces the identical smear.

Surfacing:

- **Orbital Observations** report — on the discovery night a red line of
  text, `RED SIGN — pure RED seam near (~x, ~y)`, appears in the report
  in the same in-line style as orblift / probe events (not a boxed
  banner), with the approximate location.
- **Map (persistent smear)** — a red **unicode-fill** overlay (`░░` /
  `▒▒`, rendered at the board's own cell metric so it tiles edge-to-edge)
  pulses uniformly over the smear area, brighter toward the seam centre.
  It is deliberately **fog-only**: it paints only on `UNKNOWN` cells and
  recedes as you explore toward the seam — on live or echo tiles the
  player can already see the terrain (including the pure seam itself), so
  the hint would be redundant and is suppressed there. It persists once
  discovered (like blue-sign, it does **not** clear when the seam is
  harvested).
- **Map (discovery burst)** — a one-shot filled **red rhombus** pulse
  (a diamond echo of the player-coloured probe-landing explosion) blooms
  over the seam the instant it is discovered on forward replay / the live
  night cinematic. It obeys animation priority: it is delayed to fire
  **after** the probe streak / harvester step that revealed the seam
  lands, never before, and the persistent smear reveals together with it.
  Skipped under `prefers-reduced-motion`.
- **Agent view** — surfaced top-level as `redsign`
  (`{id, center, cells:[[x, y, intensity], …], day, hour}`), identical
  for all seats, so agents can race toward a jackpot seam a rival
  uncovered. The `hour` marks the praxis hour of discovery.

Mechanically the beacon list lives on the session
(`GameSession.redsign`), with `GameSession.redsign_seen` tracking the
pure cells already attributed so a seam never re-triggers. Both persist
in `to_dict` / `from_dict`. Discovery is minted in `_pulse_vision_intel`
(`_register_redsign` / `_mint_redsign_region`) and logged (anonymous) to
the game log; the night simulator stamps `_redsign_hour` before each
vision pulse so the region carries its precise discovery hour.

---

## 5. Snowflake architecture (v0.4)

Sea of Colours is a Snowflake-first product as of v0.4: the engine is
durable inside the deployment named by `SOC_DATABASE` / `SOC_SCHEMA`
(default `SOC_HACKATHON_DB.SEA_OF_COLOURS` — see
`sea_of_colours/snowpark/naming.py`), the FastAPI surface is a
thin proxy, and either a deterministic Python agent (`RED_HARVEST`) or
one of the Snowflake Cortex AI agents (first one: `SOC_RED_REAPER`) can
play a seat end-to-end.

### 5.1 Table topology (`snowflake/soc_schema.sql`)

| Table | Purpose | Cardinality |
| ----- | ------- | ----------- |
| `SOC_GAME_SESSION`     | Canonical row per game (width, height, day, phase, durable `json_state`) | 1 row / game |
| `SOC_SQUARE_IDENTITY`  | Frozen `(square_id, tile_at_generation, purity_at_generation)` per cell, port of [`sea_of_colours/game/ledger.py`](sea_of_colours/game/ledger.py) | `width × height` rows / game |
| `SOC_ASSET_RECORD`     | Per-asset lifetime stats (red harvested, days on surface, destroyed_on_day…) — port of [`sea_of_colours/game/asset_ledger.py`](sea_of_colours/game/asset_ledger.py) | grows with deployments |
| `SOC_ENTITY_STATE`     | Live position / cargo / orbital_cargo per entity | small |
| `SOC_GRID_CELL`        | Mutable tile + purity per cell (diverges from `SQUARE_IDENTITY` on RED→GREEN) | `width × height` rows / game |
| `SOC_HOARD_PARCEL`     | One row per banked square per player slot | up to 15 / player |
| `SOC_SHIPPED_PARCEL`   | Mirror of hoard for post-vault storage (§4) | uncapped (`SHIPPED_CAPACITY = None`) |
| `SOC_POLICY_QUEUE`     | Raw policy submissions per `(day, player)` (audit trail) | 2 rows / Nox |
| `SOC_GAME_LOG`         | Structured log rows `(level, text)` with monotonic `seq` | ~10–40 / Nox |
| `SOC_REPLAY_FRAME`     | **Append-only** per-tick snapshots — drives multi-day replay | one row per executed move |
| `SOC_AGENT_INVOCATION` | Cortex agent audit trail (rationale, tool calls, ms_elapsed) | one row per agent turn |

Views: `SOC_LEADERBOARD`, `SOC_DAY_INDEX`, `SOC_LATEST_FRAME_PER_DAY`,
`SOC_SESSION_STANDINGS`, `SOC_ACTION_HISTORY` (see
`snowflake/soc_views.sql`).

### 5.2 Stored procedures (`snowflake/soc_procedures.sql`)

| Procedure | Handler | Purpose |
| --------- | ------- | ------- |
| `SOC_INIT_SESSION(seed, w, h)` | `sea_of_colours.snowpark.procs.soc_init_session` | Generate + persist a session |
| `SOC_SUBMIT_POLICY(sid, player, policy)` | `…soc_submit_policy` | Stash + resolve Nox when both seats lock |
| `SOC_RUN_NIGHT(sid)` | `…soc_run_night` | Force resolve (idempotent if Nox already ran) |
| `SOC_GET_VIEW(sid, player)` | `…soc_get_view` | Player percept + agent-friendly JSON view |
| `SOC_GET_OBSERVER(sid)` | `…soc_get_observer` | Cheat omniscient mosaic |
| `SOC_GET_REPLAY(sid, day_from, day_to)` | `…soc_get_replay` | Multi-day replay scrub |
| `SOC_GET_LOG(sid, day_from, day_to, limit)` | `…soc_get_log` | Structured log range |
| `SOC_GET_INVENTORY(sid, player)` | `…soc_get_inventory` | Hoard + shipped + assets_by_status |
| `SOC_GET_SESSION_STATUS(sid)` | `…soc_get_session_status` | `/api/game/{id}/status` |
| `SOC_LIST_SESSIONS()` | `…soc_list_sessions` | `/api/game/latest` |
| `SOC_SAVE_RATIONALE(sid, day, agent, player, txt)` | `…soc_save_rationale` | Audit row for the Cortex agent |

The handler module lives in [`sea_of_colours/snowpark/procs.py`](sea_of_colours/snowpark/procs.py)
and is packaged + uploaded to `@SOC_PY_STAGE` by
[`scripts/deploy_soc_schema.py`](scripts/deploy_soc_schema.py). Every
procedure's body is empty (`$$ $$`) because the handler is resolved
through `IMPORTS = '@SOC_PY_STAGE/sea_of_colours.zip'`.

### 5.3 Backend switch & cost guard

- **Unset = auto-detect (v1.12, default).** Resolves to `snowflake`
  only when the Snowpark extras and key-pair auth are both present,
  otherwise `memory`. An explicit `SOC_BACKEND` always wins and is
  strict: the server exits rather than silently degrading. Auto never
  selects a live backend under pytest.
- `SOC_BACKEND=snowflake` — `SnowparkSocStore` against the live schema
  named by `SOC_DATABASE` / `SOC_SCHEMA` (default
  `SOC_HACKATHON_DB.SEA_OF_COLOURS`). Credentials come from
  `SF_CONFIG_FILE` (default `~/.ssh/sf_config`). Every season — whether
  driven by `RED_HARVEST` or by an LLM agent — persists here.
- `SOC_BACKEND=memory` — pure-Python `InMemorySocStore`. Used by tests
  and fully-offline dev sandboxes; the FastAPI proxy and the agent
  runtime use the same code path, so behaviour is identical.
- **Append-only persistence (v0.5).** Sessions accumulate by default —
  `init_session` no longer wipes prior rows, and every CLI / Web /
  Cortex-driven season lands as a new `SOC_GAME_SESSION` row alongside
  every previous one. The destructive reset has moved behind an
  explicit opt-in: pass `--wipe-first` to
  [`scripts/run_season.py`](scripts/run_season.py) (which calls
  `store.wipe_all_sessions()`) when you genuinely want a clean schema
  for a dev reset. Sessions are addressable by either their UUID
  `session_id` *or* their URL-safe slug (e.g. `aurora-anchor`,
  derived from `season_name` via
  [`sea_of_colours/game/season_names.py`](sea_of_colours/game/season_names.py));
  the watcher frontend (§5.7) deep-links by slug so a CLI run can be
  replayed straight from its console URL.
- Cost model: every game tick is one row in `SOC_REPLAY_FRAME`. A
  21-hour Nox = up to 21 applied-move frames per seat (plus the
  open + Aurora frames, plus any pre-empted EMP / chaff frames from
  v0.9); a 30-Nox season ≈ 1.5–2k VARIANT rows / session.
  Warehouse auto-suspend (configured on the warehouse itself) keeps
  idle cost ~$0. See `README.md` "Snowflake cost notes".

### 5.4 Multi-day replay (v0.4)

`GET /api/game/{id}/replay?day_from=&day_to=` and
`GET /api/game/{id}/day-index` expose the append-only frame history.
The front-end ([`server/static/app.js`](server/static/app.js)) renders
day-divider ticks on the scrub bar, a "D{n}" badge above the slider,
and previous/next *day* jump buttons alongside the existing per-frame
controls. Frames are NEVER overwritten — the "latest Nox" view is a
`WHERE day = MAX(day)` filter, not a destructive update.

### 5.5 Agents — `RED_HARVEST` (mainstay) + AI agents

Sea of Colours ships two distinct agent families. Either family
satisfies a seat through the *same* route + envelope, so the playing
UI and the rest of the engine never need to care which family is
active.

**RED_HARVEST — the deterministic mainstay agent**

- Lives in [`sea_of_colours/agent/heuristic_agent.py`](sea_of_colours/agent/heuristic_agent.py).
- Pure Python, deterministic, no Snowflake / Cortex dependency.
- The default agent, and the only one `/agent/think` can run.
- Identifies itself as `agent_id = "RED_HARVEST"` in the audit row
  (`SOC_AGENT_INVOCATION`) and in the LOG panel.
- **`RED_HARVEST_LITE`** is the same playbook with weapons
  (chaff / EMP) disabled — the hackathon's first opponent. Select it
  with `runtime_override="red_harvest_lite"` (or `?runtime=` on the
  route).

**AI agents — V12**

- The shipped LLM agent is **V12**
  ([`sea_of_colours/orchestrator_2/harnesses/tabula_v12/`](sea_of_colours/orchestrator_2/harnesses/tabula_v12/)).
  It runs **in-process** and reaches Cortex over the inference REST
  endpoint with a PAT, so it needs no deployed Snowflake agent object
  and works on any `SOC_BACKEND`.
- Seat it by naming a player `tabula_v12` at game creation; the
  orchestrator
  ([`orchestrator_2/runtime.py`](sea_of_colours/orchestrator_2/runtime.py))
  dispatches it. It is **not** reachable via `?runtime=` on
  `/agent/think`.

> ⚠️ **Retired path.** An earlier generation of AI agents were Snowflake
> Cortex *Agents-API* objects (`SOC_RED_REAPER` and friends), deployed
> from `snowflake/soc_create_agent*.sql` and selected with
> `SOC_AGENT_RUNTIME=cortex`. Those specs, the `AI_AGENTS` registry and
> the `runtime=cortex` code path were all removed from this
> distribution; `/agent/think?runtime=cortex` now returns **410**.
> Changelog entries below that reference them are history, not current
> behaviour.

**Shared contract (both families)**

- Objective: maximise total RED harvested per session (§3.1 score).
- Hard caps per turn: **1 harvester action chain + up to 2 probe drops**.
- Route: `POST /api/game/{id}/agent/think?player=p1|p2` returns
  `{ok, agent_id, runtime, rationale, moves, tool_calls, night_resolved}`.
- UI: the ORDERS panel exposes a `[ >> LET THE AGENT PLAY ]` button
  that fires the route, surfaces the rationale (prefixed with the
  actual `agent_id`) in the LOG panel, and re-pulls the maps.

**Harness layer + prompt hardening (v0.5).**

As of v0.5 the orchestrator is no longer a passive dispatch tier — it
acts as a **harness** that pre-resolves the per-turn world state into a
rich user prompt before the AI agent is invoked. The agent itself has
no read tools; its surface is action-only. This principle still governs
V12, whose prompt compiler lives in
[`orchestrator_2/harnesses/tabula_v12/`](sea_of_colours/orchestrator_2/harnesses/tabula_v12/).
(The original implementation, `_build_cortex_prompt` in
`sea_of_colours/agent/runtime.py`, was removed with the Agents-API
path; that module is heuristic-only now.)

- **AI agent tools (only two).** The Cortex agent spec (formerly
  `snowflake/soc_create_agent.sql`, since removed)
  declared **only** `soc_submit_policy` and `soc_save_rationale`. The
  previous read tools (`soc_get_view`, `soc_get_inventory`,
  `soc_get_log`, `soc_get_leaderboard`) were deliberately stripped when
  the harness took over their job — keeping them would have invited
  the agent to spend turns re-fetching state it already had in its
  prompt.
- **What the harness pre-resolves.** Every turn the harness queries
  `SOC_GET_VIEW`, `SOC_GET_INVENTORY`, `SOC_GET_LOG`, and the
  leaderboard standings, and inlines them into the prompt as
  structured text — including the agent-friendly grid (`grid_ascii`),
  visible RED tiles with `tier` / `value`, fog clusters with nearest
  visible edges, the agent's own entities + echoes, and the last 12
  log lines (§3.10 yellow-error rows included).
- **Three hardened prompt blocks.** Authored to close repeat
  failure modes observed during heuristic-vs-Cortex play:
  - **HARD RULES** — JSON move grammar for `probe` / `drop` /
    `step` / `pickup` (plus v0.9 `wait` / `emp_launch` / `mine_lay`
    / `chaff_flare`), the "step is exactly one tile" rule, per-Nox
    caps (21 applied moves — one per planetary hour — queue ≤ 100),
    the harvester lifecycle (orbit → drop → step* → pickup,
    otherwise destroyed at Aurora — §3.11.2), the adjacency principle
    (§2.2),
    and a list of common mistakes (non-adjacent steps, forgetting
    pickup, wrong entity ids, deploying a probe onto a cell you
    intend to step through).
  - **HOW TO READ THE MAP** — coordinate system (`(0,0)` top-left,
    `+x` right, `+y` down), how to skip the `legend:` line in
    `grid_ascii`, the full glyph table (terrain, mine vs enemy
    entities, fog vs stale vs live tiers), and a worked example
    showing where each glyph sits in a sample row.
  - **LAST TURN** — surfaces the previous Nox's yellow-error log
    lines (rejected moves and reasons) at the top of the prompt so
    the agent gets immediate, in-context feedback on its own
    mistakes.
- **Known gap — trails are not yet in the agent view.**
  Universal persistent trails (§3.12) drive the frontend and
  replay, but [`sea_of_colours/snowpark/view.py`](sea_of_colours/snowpark/view.py)
  currently has zero references to `trail`, so the agent cannot see
  receipts of where a harvester walked the previous Nox. This is
  the cause of the "agent chases a rumour into now-GREEN tiles"
  pattern observed in season `aurora-anchor`. Threading trails into
  `build_agent_view` (with a new glyph in `grid_ascii` and a structured
  `trails` field) is the next harness iteration.

### 5.6 Deployment

```bash
# fresh deploy (also creates @SOC_PY_STAGE + uploads the engine zip)
python scripts/deploy_soc_schema.py

# schema/views only (safe to re-run; tables use CREATE TABLE IF NOT EXISTS)
python scripts/deploy_soc_schema.py --schema-only

# check where you're about to deploy, without connecting
python scripts/deploy_soc_schema.py --dry-run
```

Re-running the full deploy script is **non-destructive**: tables use
`CREATE TABLE IF NOT EXISTS`, views use `CREATE OR REPLACE`, procs use
`CREATE OR REPLACE PROCEDURE`, the engine zip uses
`OVERWRITE=TRUE`. Existing game sessions and replay frames are
preserved.

### 5.7 Watcher frontend (Phase C)

The watcher is a **read-only mode of the same SPA** used for play —
served at `/watch.html` by [`server/app.py`](server/app.py) and
backed by the same [`server/static/app.js`](server/static/app.js)
module — that turns the durable Snowflake replay history (§5.4) into
a season library you can scrub through without touching live state.

- **Deep-linking by season.** `/watch.html?season=<slug>` jumps
  straight to a persisted season; the slug is the URL-safe form of
  `season_name` (e.g. `Aurora_Anchor` → `aurora-anchor`).
  `/watch.html?session=<uuid>` is the equivalent id-addressed form.
  The CLI orchestrator (§5.8) prints both URLs in its
  `SEASON_COMPLETE` block so a background run is one click away from
  replay.
- **Season picker.** A `<select>` element above the map enumerates
  every persisted season via `GET /api/sessions` (which the watcher
  also accepts a `?season=<slug>` filter on). Each option shows
  season name, day count, and the final p1 / p2 scores. Changing
  the selection updates the URL with `?session=<id>` and reloads the
  replay buffer.
- **Simultaneous ticks.** Consecutive p1+p2 actionable frames on the
  same day are grouped into a single replay tick, so the scrubber
  and prev/next controls step through *rounds* rather than
  individual interleaved moves. The per-tick animation runner plays
  both seats' moves together (`runReplayAnimationsTick`).
- **Per-seat fog overlay.** A P1 / P2 / OBS toggle sits below the
  scrubber. P1 and P2 render that seat's fog-of-war percept at full
  opacity and dim the observer terrain to ~22 % opacity behind it,
  so the full map shape stays readable but only the chosen seat's
  vision is crisp. OBS shows the unfogged observer map.
- **Vision-boundary overlay (v1.22).** Every seat's live region is
  outlined in its own seat colour, per §3.11. Replay ships each seat's
  visibility in full, so all outlines here are **solid** — including
  under P1 / P2, where you see both the chosen seat's fog *and* the
  true extent of what its rival could see that night. Overlapping
  boundaries blend, so shared ground reads as both colours at once.
- **Writable controls hidden.** The watcher hides `#new-game-btn`
  and the ORDERS tab (via `body.cc-mode--watch`), so the read-only
  surface can never accidentally submit policies or start a fresh
  session.

### 5.8 Headless season orchestrator (CLI)

[`scripts/run_season.py`](scripts/run_season.py) runs a full season
end-to-end without the frontend — useful for background tournaments,
CI sanity runs, and "let the agent cook overnight" experiments. Every
season the CLI runs lands in Snowflake exactly like the live UI's
sessions (append-only, §5.3), so the watcher (§5.7) picks them up
automatically.

```bash
# heuristic vs heuristic, deterministic season name from --seed
python scripts/run_season.py --seed 42

# Cortex (p1) vs RED_HARVEST (p2), explicit season name
python scripts/run_season.py --p1 cortex --p2 heuristic \
    --seed 7 --season-name "Demo_Match"

# Offline dev — no Snowflake, no replay persisted
SOC_BACKEND=memory python scripts/run_season.py --seed 1
```

- **Seat assignment.** `--p1` / `--p2` each take `heuristic` (default
  → `RED_HARVEST`) or `cortex` (default agent name `SOC_RED_REAPER`,
  overridable via `--cortex-agent` or `SOC_CORTEX_AGENT`). Cortex
  seats require `--backend snowflake` (the default) because the
  harness (§5.5) resolves view state through the Snowflake-backed
  store.
- **Season identity.** `--seed` controls the map generator *and* the
  deterministic `Latin_English` season name. Pass `--season-name` to
  override the generated label without changing the seed-derived
  map.
- **Backend.** `--backend` overrides `SOC_BACKEND` for the duration
  of the run (`snowflake` is the default and the only mode that
  persists replay frames).
- **Wipe.** `--wipe-first` is the only way to clear previous
  sessions from the CLI; it calls `store.wipe_all_sessions()` before
  the new season starts (§5.3 append-only contract).
- **Output.** The CLI prints a per-turn one-liner per seat and a
  final `SEASON_COMPLETE` block with the season name, slug, final
  scores, watcher URL (`/watch.html?season=<slug>`), and replay API
  endpoint. Exit codes: `0` = season finished, `2` = preflight error
  (e.g. cortex without snowflake), `3` = aborted (deadlock guard).
- **Day cap.** The cap is the engine-wide `SEASON_DAY_CAP = 5` from
  [`sea_of_colours/game/session.py`](sea_of_colours/game/session.py)
  (§3.0). Shorter / longer runs currently require monkey-patching
  that constant before invoking `runner.main()`; a `--days` flag is
  on the backlog.

---

## Changelog

### v1.23 — 2026-08-27

**§3.11 — an order shows the ground it will cover.** Three of the orders a
House can queue do not land on the square you pick. A probe lights a disk of
radius `probe_radius` (49 squares at r4), an EMP fills a Manhattan diamond of
radius `EMP_RADIUS` (13 at r2), and a `mine_lay` arms a cluster of
`MINE_BATCH_SHAPE` (5 as a plus). Until now the board marked only the centre,
so aiming any of them meant counting squares by eye, and a queued salvo gave
no indication of the ground it actually covered.

Each of those three now draws its **footprint** as a region outline over the
board, using the same vector layer and ring-tracing as the vision edges above.
A footprint already in the queue is drawn quietly, in a long dash — deliberately
not the vision edge's dot, so "their sight ends here" and "my EMP lands here"
cannot be confused. The one being aimed follows the pointer, solid and brighter,
and there is only ever one of it.

The footprint shapes are the *engine's* shapes, read from the published dials
(`meta.rules.probe_radius`, `orbit.weapon_specs.emp.radius`,
`orbit.weapon_specs.mine.batch_shape`) rather than restated in the client, so a
retune moves the drawn area with it. `scripts/_fx_aoe.py` diffs the shipped
client geometry against `_euclidean_disk` / `_manhattan_disk` /
`_mine_cluster_cells` over every square of a board, which is the check that
would catch a drift.

The square readout leads with the same figures while aiming: how many squares
the order covers, how many of them are currently dark (the question that
decides where a probe goes), what is standing inside a blast — **including your
own hardware**, since §4.9 does not spare it — and how much of the footprint a
board edge would waste.

Nothing new is disclosed: a footprint is arithmetic on an order the House is
itself composing.

**§3.11 — a square with no stated purity now prices as a band.** The exact
score line added in v1.22 needs the `purity` the payload carries from that
version on. Where it is absent the client falls back to reading tier out of the
render colour, which recovers the band but not the number — and the readout
then printed *no score at all*. The visible effect was that only GREEN (a flat
charge, which needs no purity) and pure RED / deep BLUE (saturated, so the
colour alone pins them at 255) stated a value, while every dithered square —
most of the board — went silent. Such a square now prices as a range
(`151–254 × 1.5 = 227–381`), marked as a band estimate.

### v1.22 — 2026-08-27

**§3.11 — a House's vision has a visible edge.** Two earlier attempts at this
were written into the rules and never built: a per-cell `vedge` inset (§3.11)
and a per-cell OBS boundary in blue-white and yellow (§7.3). Both specified an
edge *per square*, which is why neither survived contact with the renderer —
the board is a `display:table` grid rebuilt wholesale on every paint, its
`border-collapse` drops half the edges you ask for, and a per-cell border
cannot express "outline this region" or let two Houses' boundaries occupy the
same line. The rules described a feature the players did not have.

Replaced with a **region outline**: the live set's boundary is traced into
closed rings and stroked once per seat on a vector layer over the board, in
seat colour. Coincident edges blend, so ground two Houses both see reads as
both colours. **Solid** where the viewer knows the region exactly (always your
own; every seat in replay, which ships per-seat visibility in full). **Dashed**
where it is inferred — in a live game nothing tells you a rival's sight, so
theirs is reconstructed from what their presence publicly implies (§3.15): the
disk around a rival probe you can see or whose launch you witnessed, and the
square under a rival harvester in your sight. That is a floor, never a
guarantee. No new information is disclosed; this only draws what the percept
already contained. Toggle in SETTINGS ▸ DISPLAY.

`vedge` still ships. The renderer derives the boundary itself because it must
outline seats *other than* the recipient, whose cells carry no `vedge` bit.

**§3.11 — the square readout states the score.** Hovering a square used to
give a line of text that named a purity *band* ("mid (purity 51–150)"),
because the dense map payload carried only render colours — the client was
reading tier back out of the pixels. The payload now carries `tile`, `purity`
and `tier` outright, on live squares and on the frozen echo/memory snapshots
alike, so the readout can state the exact figure and, for RED, the score it
settles for: purity × the §4 tier multiplier, shown as the arithmetic. GREEN
shows its flat settlement charge and BLUE is marked as spend, not score.
Anything standing on the square is listed with its glyph, in its owner's
colour. This is the same purity an agent already receives in its percept
(§6.1); the human seat was simply not being told.

**§7.3 — the replay header says each thing once.** The strip had grown to
name the season three times (a nameplate, the picker's selected row, and a
meta line that restated that row word for word) and the night twice, beside
an unlabelled `fixtures` tickbox — a developer filter for frozen test nights,
now a SETTINGS preference — and a `NIGHTS` spinner that only ever seeded the
launcher's own copy. All four are gone.

That clutter was also hiding a real defect. The SEED / RED ON MAP /
EXTRACTED readout added in v1.20 had never once rendered: `get_replay`
returns `seed` and `extraction`, but the HTTP layer rebuilds that response
key by key (a deliberate payload-size guard) and neither field was ever added
to the projection, so the client read `undefined` and the strip hid itself.
The renderer then compounded it by waiting for a painted replay frame, which
meant that even with data it stayed blank in the watcher until you scrubbed.
Both fixed, and `tests/test_replay_payload_keys.py` now fails if the engine
grows a replay field the route forgets to forward. The figure stays out of
live play on purpose: it is omniscient, and the payload is already on the
client because the night cinematic fetches it.

### v1.21 — 2026-08-27

**§2.2 — pure cells may no longer touch.** A `pure` (255) is the jackpot a
redsign broadcasts and the thing the night is fought over, but ridge noise
sometimes handed them out in slabs. Since a landing auto-harvests the cell
it lands on, that let one seat bank several jackpots off a single drop with
nothing to contest — not a lucky board, a different game.

Measured over 500 seeds on the **played 40×28 board**: the median board has
**1** pure, but **7%** of seeds put two or more in contact and the worst
produced a contiguous **8-cell** block. Uncommon, and decisive when it
lands. (An earlier draft of this entry quoted a median of 17 pures and a
14-cell worst case; those came from `GenerationParams`' 80×50 *default*,
which is not the board `/api/game/new` serves. The 40×28 figures above are
the ones that describe real games.)

After purity is assigned, each 8-connected group of pures keeps exactly one
cell at 255 — the one nearest the group's centroid, so the core stays pure
and the shoulders drop — and the rest are demoted into `[220, 254]`, the top
of `mass`. The ground stays worth combing and the seam keeps its shape; it
just stops paying twice. Deliberately narrow: **only touching pures are
thinned**, so two pures a few cells apart remain two separate finds. After
the rule no board has any two pures 8-adjacent, and since most boards were
never clustered the mean pure count barely moves (1.2 → 1.1 over 500 seeds)
— it removes the pathological 7% and leaves everything else alone.

`ensure_pure_red` (the guarantee that every board has at least one pure)
now promotes the peak RED cell **only**. It used to promote the peak plus
its two richest neighbours, deliberately, "so the guaranteed pure reads as a
small natural seam" — which made it the one remaining path minting exactly
the cluster this rule removes.

Seed stability is preserved: the demotion draws from a fresh
`random.Random(seed + 4_000)` stream (RED uses `1_000`, GREEN `2_000`, BLUE
`3_000`), so no existing layer's noise is perturbed and every other feature
of a given seed's terrain is unchanged. Set `decluster_pure_red=False` for
the raw noise output.

**Planner consequence.** A visible pure no longer implies more pure next
door; if anything its neighbours are now likelier to be high `mass`. Agents
must not treat a found pure as evidence of a cluster.

### v1.15 — 2026-08-26

**§3.16 now rules on the square, not just on the probes landing on it.**
The section was explicit that two or more probes landing on one cell in
the same hour all destroy each other, and silent on what happens to an
**older probe already standing there**. The engine answered by accident:
resolving seat by seat, the first arrival superseded the incumbent and
the second then annihilated with the first. The body count came out
right, but the incumbent was filed as `probe_superseded` and the
`probes_superseded` kill-feed credit went to whichever seat the resolver
reached first — a seat that lost its own probe in the same instant.

- **New §3.16(c).** An incumbent caught under a simultaneous annihilation
  is destroyed as a **collision casualty** (`probe_collision`), and **no
  House is credited a supersede**. Supersession is an act by a surviving
  newcomer; when the arrivals wipe each other out, nobody took the cell.
  Two rivals can clear an established probe off a square at the cost of
  both their own — a 2-for-1 trade, not a free removal.
- **New §3.16(d).** The same-hour latecomer sweep is now *written down*.
  A probe landing on a square already cleared by an annihilation **on the
  same `(day, hour)`** is destroyed too, so a pairwise reading can't let
  it quietly inherit a contested seam. This behaviour shipped in v0.9.17
  and the code cited a "§3.16 E4" that has never existed in this
  document. The sweep is scoped to the exact stamp — an arrival an hour
  later finds the square clean and lands normally.
- **Seat order has no rules standing** (§3.16, §3.10). Stated explicitly
  because the old outcome was reachable only by reading the resolver's
  loop as if it were the rule. Ledger reason and kill-feed attribution
  are now finalised once the hour's full picture is known, so they no
  longer depend on which seat resolved first.

**Every probe death on a square now surfaces to the watcher.** The
`crushed_probes` replay payload — the pixel-splash channel — was only
ever filled by the harvester crush it was built for. A superseded probe
blinked out with no cue, and an annihilation rendered *nothing at all*,
incoming streak included, because a probe destroyed on arrival never
reaches a frame's entity snapshot for the animator to diff. Two seats
could burn a probe each on one square and the board would not flicker.
All three §3.16 paths now file a record carrying its `reason`, and the
splash fires on the **landing beat** rather than at frame paint (it used
to go off up to two seconds early — the victim burst while its killer was
still in the air). Fog is unchanged: the splash still skips a square the
viewing seat can't see, so a House that watched the launch but not the
death keeps its §3.15 marker until that marker's own expiry.

No constants changed. Engine: `spawn_probe` /
`_finalise_probe_contest` in
[`sea_of_colours/game/session.py`](sea_of_colours/game/session.py).
Tests: `tests/test_probe_death_fx.py`.

### v1.14 — 2026-08-26

**Chaff outranks the salvo, and outranks itself.** §4.9.5 already said
that on a covered hour *every* seat's action is cancelled. A launch is an
action — but §4.9.3's within-hour ordering list put EMP-launch
pre-emption *before* chaff pre-emption, so the two sections contradicted
each other and the engine followed the ordering list. Weapons were the
one action class chaff could not stop. Resolved in favour of §4.9.5:

- **Chaff pre-emption now runs before EMP-launch pre-emption** (§4.9.3
  ordering updated). A flare fired at hour N cancels a salvo declared for
  hour N. Previously whichever seat the resolver reached first simply
  flew, which made "answer their chaff with an EMP" a reliable counter
  that no rule granted.
- **A cancelled launch keeps its munition** (§4.9.5). The row is
  consumed — the slot burns, the move does not defer — but a house that
  never fired has not spent the round, so the flare or charge stays in
  `weapon_stock` for a later hour or Nox.
- **Chaff can no longer be chained into a lock** (§4.9.5). A flare queued
  inside its own window used to fire, re-arm the window, *and* renew its
  launcher's launch-hour immunity, so `N` flares jammed the opponent for
  `N + CHAFF_DURATION_HOURS - 1` consecutive hours while the chaffer
  acted freely. `CHAFF_DURATION_HOURS` is now a hard ceiling on what one
  flare reaches.
- **Two flares on the same hour still both fire, and one is wasted**
  (§4.9.5) — unchanged behaviour, now stated explicitly. Neither seat is
  inside a window when the hour opens, and the effect is global and
  identical, so the second buys nothing and the window does not stack.
  Deliberate: it keeps mutual chaff strictly worse than solo chaff.
- **One applied action per seat per hour, weapons included** (§4.9.3,
  §3.10). A pre-empted seat is now excluded from the collision pre-passes
  (pass-through swap §3.6, simultaneous drop). Those passes peeked every
  seat's *next* queued row without asking who had already acted, so a
  seat could fire a weapon **and** collide in the same hour: `emp_launch`
  plus a swap at hour 1 left **both** harvesters damaged for one slot.

No constants changed; `CHAFF_DURATION_HOURS` is still 3. Engine:
`_pre_hour_phase` / `_maybe_resolve_swap_collision` /
`_maybe_resolve_simultaneous_drops` in
[`sea_of_colours/game/simulator.py`](sea_of_colours/game/simulator.py).
Tests: `tests/test_chaff_precedence.py`,
`tests/test_preempt_slot_integrity.py`.

### v1.13 — 2026-08-25

**The Orbit phase is now a shop, and the vault settles itself.** The
single largest simplification in the game's history: the Orbit's
private economy is removed so that the Nox phase — deciding where to
send harvesters under fog — is unambiguously the game.

Removed:

- **The 3-action cap** (`MAX_ORBIT_ACTIONS`). A seat may now queue as
  many purchases as it can pay for; the wallet is the only limit. §4.2
- **Refining** (§4.3) — the `refine`, `refine_cascade`, `refine_trace`,
  `refine_vein`, `refine_pick` actions and the `REFINE_MAX_FOR_TIER` /
  `REFINE_MAX_SLOTS` / `REFINE_BLUE_COST` constants. Refining let a
  house launder a bad night into a good score by arithmetic; tier is
  now a permanent property of where you dug.
- **The Final Refinery** (§4.3.1) — existed only to give leftover BLUE
  a use on the terminal orbit. BLUE now goes to weapons.
- **The RED credit-bid draft** (§4.4) — the `ship_catapult` action, the
  20 slots, the four transit rows (`CATAPULT_ROW_*`) and the overflow
  forfeit. Shipping is free and universal.
- **The GREEN flush** (§4.7) — the `solar_jettison` action, the 12
  shared slots, the RED-fuel ranking and the diminishing cost ramp
  (`GREEN_CATAPULT_SLOTS`, `GREEN_SLOT_COST_*`, `JETTISON_*`). It
  punished the same mistake twice and could soft-lock a vault.
- **The locking model** (§4.2) — with no action naming a parcel, there
  is nothing to lock.

Kept, because they are what made the economy worth having:

- `RED_QUALITY_MULTIPLIER` (×0.75 / ×1.0 / ×1.5 / ×3.0). One `pure`
  parcel still outscores ten `trace` parcels four-to-one, so probing
  before you dig is still the highest-leverage habit in the game. §4.4
- `GREEN_ENDGAME_PENALTY` (−100 per parcel, flat, purity-irrelevant).
  Harvesting blind still hurts — you just can't also fumble the
  cleanup. §4.7
- The **public settlement briefing**, unchanged as an intelligence
  leak: your manifest tells rivals how rich a seam you found. §4.8

New behaviour:

- **Automatic settlement.** Every orbit, every RED parcel ships and
  scores; every GREEN parcel is disposed of at −100. BLUE is never
  settled — it is fuel, and legitimately stays in the vault. §4.8
- **GREEN can never brick a vault.** Guaranteed to clear at the next
  settlement. Green harvested on the final Nox is charged where it
  sits by the endgame pass, so holding it never dodges the tax.
- **Vault pressure is per-night.** `HOARD_CAPACITY` (15) now limits one
  night's haul rather than standing inventory; overflow still displaces
  the lowest tier. §3.14
- **Retired actions fail loudly.** A stale client or an old replay
  sending `refine` / `ship_catapult` / `solar_jettison` gets a waste
  line naming v1.13 and the reason, not a silent shrug.
- **The final orbit no longer restricts purchases.** Buying is legal
  but pointless (no following Nox); the UI warns rather than the engine
  forbidding. Settlement runs on the final orbit as on any other.

Frontend: the catapult graphics are **kept** — both lattices now size
themselves to the settlement manifest (RED resting at 20 cells, GREEN
at 12) and grow past it on a heavy night, so the catapult always fills
and fires. The launch stagger is compressed for large manifests so the
wave lands in roughly constant wall-clock time. `/mobile` and the
frozen `orbital_exp/` fork are retired; `/play` is responsive.

### v1.12 — 2026-08-25

**Infrastructure — the storage backend is auto-detected (§5.3).** No rule
or number changes; this is about who can reach the rules at all.

`SOC_BACKEND` defaulted to `snowflake`, but `snowflake-snowpark-python`
ships only in the optional `requirements-snowflake.txt`. A by-the-book
`pip install -r requirements.txt && python run_web.py` therefore booted a
server, rendered the homepage, and died with `ModuleNotFoundError` on the
first game action — an install that looks successful right until it
isn't, and the single worst first-run experience in the repo.

Unset now means **auto**: `snowflake` when the Snowpark extras *and*
key-pair auth are both present, otherwise the in-process `memory` store.
Three properties are deliberate and worth preserving:

- **Explicit is strict; auto is forgiving.** `SOC_BACKEND=snowflake`
  makes the server exit rather than silently degrade, so a season never
  lands somewhere the operator didn't intend. Only `auto` falls back,
  and it prints why.
- **A PAT-only `sf_config` never selects Snowflake.** That is the Cortex
  setup for playing against V12 and implies nothing about wanting
  persistence, so detection keys on `private_key_file=` instead.
- **Auto never resolves to a live backend under pytest.** Detection keys
  off a file present on any machine that has done the key-pair setup,
  and `init_session` wipes the target schema — so without the guard,
  running the suite on a developer laptop writes to their own account.

The backend is now opened at boot rather than on first store access, so
a bad key or an undeployed schema is reported next to the command that
started the server instead of as a 500 on some later API call. The
resolved backend, the reason and the fix are printed at startup, served
from `GET /api/meta/backend`, and shown in the landing-page badge.

### v1.11 — 2026-08-23

**Bugfix — rival probes invisible on the map once landed on already-explored
terrain (§3.15).** Probe launches are documented as public (every seat sees
the launch), and a v0.9.7 fix ("§3.15 FIX, seed-69 E2") already patched the
case where a probe lands on a cell the opponent has an older terrain echo
for — but that fix only made the launch surface in the agent-facing intel
feed (`enemy_probe_launch`); it never gave the **map** a drawable glyph.
Discovered while diagnosing a replay report on season `V12_HEUR3_SNAP2_s69`
(day 6, p4 view — the same seed as the original E2 incident) where most
rival probes were missing from the board: any probe landing inside the
explored core of the map (a stale terrain echo, not fog) never got an
`entity` glyph, because the merge only ever touched `occupants` /
`probe_launch_day` / `launched_by`, and the general ghost-glyph renderer is
gated on the terrain echo's own `day_seen` — which the merge deliberately
does NOT bump (bumping it would falsely tell the seat "you just re-observed
this terrain," §3.15 FIX comment). Only probes landing on genuine fog (no
prior echo) rendered correctly.

- **Fix:** the merge now also stamps a dedicated `probe_launch_glyph`
  (glyph char + the launching seat's colour, keyed by `probe_id`) onto the
  existing echo — independent of the terrain's own `day_seen`/staleness.
  The renderer prioritises this marker over the general ghost-glyph path,
  so a publicly-launched probe is visible on the map whether it lands on
  fog or on already-explored terrain.
- **Cleanup:** `_clear_probe_launch_markers` (called on every probe death —
  EMP, expiry, collision, crush) previously only pruned pure `via:
  "probe_launch"` markers; the merged-onto-richer-echo case was silently
  skipped, which — once the glyph fix above lit it up — would have left a
  **permanent** ghost glyph after the probe died. Now prunes the merged
  occupant + `probe_launch_glyph` too, regardless of `via`.
- **Non-retroactive by construction**, same as v1.10 — this only changes
  how live sessions render going forward; already-resolved replay frames in
  `SOC_REPLAY_FRAME` are historical fact and are not rewritten.
- **Engine:** `session.py::_pulse_probe_launch` (merge branch),
  `session.py::player_dense_view` (stale-terrain-echo render branch),
  `session.py::_clear_probe_launch_markers`. Covered by
  `tests/test_v0_7_0.py` (glyph present after merge; glyph pruned on
  probe death).

### v1.10 — 2026-08-22

**EMP no longer rewards landing inside an already-active cloud (§4.9.3).**
Previously a drop or step into an EMP cloud always auto-harvested the
landing tile — EMP only disabled the harvester's *next* action, never the
landing itself. This let a seat treat a standing enemy (or even friendly)
cloud as a free one-time harvest before eating the disable, undercutting
EMP's value as an area-denial weapon.

- **New rule:** the disable check now also gates the landing's harvest,
  not just subsequent actions. A drop or step whose destination cell was
  already inside an active cloud **at the start of the hour** no longer
  harvests — the harvester still lands/steps onto the cell (it isn't
  bounced like a mine), but the tile-colour conversion is skipped.
- **Same-hour grace preserved.** A cloud formed by a launch resolved
  *this* hour does not yet count as "already active" for this check — a
  harvester landing the same hour a missile lands still harvests once,
  and only becomes `empd` from the following hour onward (unchanged).
  This keeps the existing "hot EMP into an incoming drop" interaction
  intact.
- **Pickup remains exempt** (§3.9.13, unchanged) — the orblift can always
  extract a harvester through an EMP cloud.
- **Non-retroactive by construction.** Nox resolution is append-only
  (`SOC_REPLAY_FRAME`); already-resolved nights, whether the season is
  finished or mid-flight, keep their original recorded outcomes. The new
  check only applies to nights resolved after this patch ships — an
  in-progress season simply cuts over on its next unresolved Nox.
- **Engine:** `simulator.py::_pre_hour_phase` snapshots the pre-launch
  "established" cloud-cell footprint (`sess._emp_established_cells_this_hour`,
  cleared at end of night); `session.py::try_drop_unit` /
  `try_step_unit` gain an `emp_blocked_cells` gate ahead of
  `_harvest_at`. Covered by `tests/test_agent.py` /
  `tests/test_night_simulator.py` (established-cloud landing denies
  harvest; same-hour launch+landing still harvests once; pickup
  unaffected).

### v1.9 — 2026-07-14

**Redsign presentation + timing refinements (§4.11).** The mechanic is
unchanged; how it surfaces was reworked for clarity and to respect animation
priority:

- **Exact-hour discovery.** Regions now carry the praxis `hour` they were
  witnessed (stamped via `_redsign_hour` before each vision pulse), so replay
  lights the sign at the precise discovery frame instead of the top of the
  night. The agent-view `redsign` block gains `hour`.
- **Fog-only smear.** The map overlay is now a red **unicode fill** (`░░`/`▒▒`)
  that pulses uniformly and paints **only on fog** — it recedes on live/echo
  tiles where the terrain (and seam) is already visible. The centre beacon and
  the radial-gradient "growing orb" were removed.
- **Discovery burst.** A one-shot filled **red rhombus** pulse (a diamond echo
  of the probe-landing explosion) fires once at discovery on forward replay /
  the live night cinematic, **delayed to land after** the probe/harvester that
  revealed the seam; the persistent smear reveals together with it. Honours
  `prefers-reduced-motion`.
- **Orbital line.** The Orbital Observations entry is now an in-line red text
  line (`RED SIGN — pure RED seam near …`) matching orblift / probe events,
  not a boxed banner.
- **Engine/UI:** `_mint_redsign_region` adds `hour`; `simulator.py` stamps
  `sess._redsign_hour`; `server/app.py` whitelists `redsign` in the replay
  payload; `app.js` / `styles.css` implement the fog-only smear, the rhombus
  burst, and the discovery-frame gating.

### v1.8 — 2026-07-13

**Redsign — public jackpot beacon for pure-RED seams (§4.11).** A pure RED
seam (`purity 255`) could previously be won privately by a single lucky probe,
letting luck alone throw a whole season. Redsign socialises the jackpot without
removing the race to exploit it:

- **Discovery-triggered.** The first time *any* house's probe or harvester
  sees a pure-RED cell, a public beacon is minted and becomes visible to
  **every** house, independent of fog.
- **Anonymous + persistent.** The sign never names the finder and stays for the
  rest of the season (it does not clear when the seam is harvested).
- **Rough, not a pinpoint.** The smear is jittered off the true seam and bleeds
  past it (mirrors blue-sign §4.10) — "a pure seam is around here", not the
  exact square. Deterministic per `seed` + seam location.
- **Surfaces:** a global `RED SIGN` banner in the Orbital Observations report on
  the discovery night; a persistent red **pulse** overlay on the map (strong on
  fog, translucent over echo/visible, day-gated in replay); and a top-level
  `redsign` block in the agent view.
- **Engine:** `GameSession.redsign` + `redsign_seen`, minted in
  `_pulse_vision_intel`, persisted in `to_dict` / `from_dict`, surfaced in
  `build_agent_view` / `get_view` / `get_observer` / `get_replay`. Covered by
  `tests/test_redsign.py`.

### v1.7 — 2026-07-13

**Final Refinery — the terminal orbit becomes a refine-and-ship blitz (§4.3.1).**
The last-orbit refine used to be a dead action (its output couldn't ship, and
the §4.7 fire-sale is purity-only). We rejected a tier-weighted fire-sale in
favour of making the **final settlement orbit** a special, uncapped refinery run
so leftover BLUE finally has an aggressive use:

- **Caps lifted on `final_orbit` only.** `MAX_ORBIT_ACTIONS` (3) and
  `REFINE_MAX_SLOTS` (5) no longer apply on the terminal orbit; a seat can fold
  its whole vault in one pass.
- **Same-turn cascade.** Refined outputs are immediately eligible to be
  re-refined and shipped the same turn (trace → vein → mass → ship). Every other
  orbit keeps the no-cascade rule (§4.2).
- **New terminal-only actions.** `refine_cascade{target_tier}` folds every
  eligible RED parcel up to `vein`/`mass` in one click;
  `ship_catapult{auto:true, credits, count}` bids on the best-N post-refine
  parcels (refined parcels' ids don't exist until settlement, so they can't be
  named explicitly). Both are dropped on non-final orbits.
- **Unchanged:** the fire-sale (`0.5 × purity`, no tier weight, §4.7), the GREEN
  penalty, and the §4.4 catapult draft. BLUE is the only limiter on the cascade.

Engine + parser + resolver + `tests/test_final_refinery.py`. See
`docs/RULES_PENDING_REVISION.md` #1 for the design rationale.

### v1.6 — 2026-07-10

**Doc-accuracy pass — no rule changes, prose reconciled to code.** Audited the
whole rulebook against the engine constants and fixed stale numbers that
contradicted the Canonical Configuration:

- **Season cap.** §3.0 said `SEASON_DAY_CAP = 5` / "DAY n/5"; the code (and the
  Canonical Config table) is **7**. Corrected.
- **Vault capacity.** `HOARD_CAPACITY = 15`, but §3.13 ("25-slot mosaic"), §3.14
  ("25-slot vault"), and §3.15.1 ("25-slot hoard cap") still said **25**.
  Corrected to 15; §3.14 now notes the two-step 50→25 (v0.8.0) → 15 (v0.9.x) cut.
- **§5.1 cardinalities.** `SOC_HOARD_PARCEL` "up to 25 / player" → 15;
  `SOC_SHIPPED_PARCEL` is **uncapped** (`SHIPPED_CAPACITY = None`), not 25.
- **Probe radius.** The canonical/runtime default (`tuning.py`) is
  `SOC_PROBE_RADIUS = 4` (~49-cell disk), but §3.8, §3.9.7, and §3.11 still
  described radius **2 / 13 tiles**. Corrected; noted the bare
  `PROBE_VISION_RADIUS = 2` constant in `session.py` is superseded by
  `tuning.probe_vision_radius()` on the live path.
- **Shape wording.** Radius-4 vision is a Euclidean **disk**, not a "7×7 square";
  reworded in the Canonical Config table and §3.11.

The v0.8.0 changelog entry (50→25) is left intact as historical record.

### v1.5 — 2026-07-06

**Orbital-station panel polish: VESPERA/live flow, blue readout, refine preview, season finale.**

- **Orbital-station panel is a permanent feature.** The edge-mounted station
  panels (per-seat vault diamonds, RED ship catapult + GREEN solar catapult,
  score + `+X` lines, blue lift) are always on — no `?station=1` gate.

- **VESPERA is the orbital-resolve review beat.** The whole orbital phase for a day
  resolves in a beat at hour 0 (VESPERA); the praxis hours 1–21 are the surface
  simulation played for human eyes. At VESPERA the catapults load (RED + GREEN),
  the score gained shows as a pending **`+X`** badge, and the blue to be spent
  lifts and holds above the station. At PRAXIS the catapults fire, the `+X`
  folds into the cumulative score, and the held blue is consumed. The `+X` fold
  is now armed on every VESPERA staging (forward, scrub, and live) so it can no
  longer stick unfolded.

- **LIVE after an orbit commit returns to VESPERA.** Hitting **LIVE** while the
  committed orbit's Nox hasn't been played (phase `planning`), or after the
  season closes, re-stages the VESPERA/RESOLVE beat (loaded catapults + `+X` +
  blue) instead of snapping to the previous Nox's Aurora.

- **Enemy blue level bar rescaled.** The unseen-station 3-bar readout's BLUE bar
  now spreads a seat's total fissile war-chest (`blue_purity_available`, bank +
  vault) across the 5 pips at ~300/pip (≈1500 ceiling) with fractional mid-fill
  blocks, so a full-season hoard no longer pins the bar to "full". The finer
  150/pip band (`_blue_pip_band`, §3.15.1) is unchanged for the per-turn burn
  detection and the agent signal.

- **Refine preview (optimistic pending vault).** Queuing a refine now shows its
  outcome before commit: consumed inputs vanish from the vault, ship composer,
  refine composer and orbital vault, and a **white-bordered "pending"** refined
  parcel is minted in their place. Pending outputs are display-only — they can't
  be shipped or re-refined this turn (no same-turn cascade; RULEBOOK §4.2/§4.3).
  Dropping the refine from the queue reverts the preview; commit replaces it with
  the real engine result.

- **Final game-resolve step + winner celebration (replay AND live).** The
  season-closing orbit on `day = cap + 1` plays an inline resolve beat (last
  catapult launch, blue burn, `+X` fold, vault settlement), and only **after**
  those scores land on the board does the full-bleed winner celebration play,
  followed by the results screen. Applies to both the replay `resolve` tick and
  the live season-complete path (`osOnLiveResolve`).

### v1.2 — 2026-06-26

**Probe echo intel now persists until natural expiry after unwitnessed destruction.**

- **Probe echoes survive crush / collision / supersede for non-witnesses (§3.15).**
  Previously the engine cleared a probe's `via="probe_launch"` marker from every
  House's intel immediately on any destruction event. This was wrong: a House that
  did not observe the destruction had no information that the probe was gone.
  New rule: only **EMP** (zone-wide observable) and **natural lifetime expiry**
  (scheduled, public) clear the echo for all Houses immediately. Crush, collision,
  and supersede leave the echo in place for Houses that did not witness the event;
  the echo clears at the Aurora the probe was always scheduled to expire.
- **Aurora sweep added to `decay_probes`.** At every Aurora, after expiring live
  probes by lifetime, the engine also sweeps `probe_intel` for any
  `via="probe_launch"` marker whose probe is no longer alive but has reached
  its natural expiry date (computed from `asset_records`). This is the single
  cleanup path for all secretly-destroyed probes.
- **Belt-and-suspenders renderer check removed.** The check that suppressed
  probe echo cells whose probe was absent from `self.entities` has been
  removed; it was the mechanism causing echoes to vanish for non-witnesses.

### v1.1 — 2026-06-19

**Credit economy tightened, public gravestones, replay VAULT fidelity.**

- **No birth stipend; stipend awarded at Orbit entry (§4, §4.1, §4.8).**
  Seats no longer receive a +1000 grant at session birth — Nox 1 opens
  at `0c`. The `ORBIT_CREDITS_PER_TURN` award now lands at **Orbit entry**
  (when the day flips into the Orbit planning step) instead of at
  settlement, so the credits readout + budget projection show spendable
  funds while planning. Net effect: a seat plans its **first Orbit (day 2)
  with exactly 1000c**, +1000 each subsequent Orbit (was 2000c at the first
  Orbit because the birth grant stacked with the day-2 award). The
  settlement resolver keeps the award as an idempotent backstop.

- **Aurora boundary frame is unconditional (replay).** Every Nox now closes
  with a single synthetic **"22nd hour" `dawn` frame** — the sunrise sweep
  the watcher animates — regardless of whether anything was destroyed. Its
  caption tallies the toll (`[H22] dawn — N probe(s) destroyed, M
  harvester(s) destroyed`), surviving probes lose a ring at this frame, and
  lifetime-expired probes drop out here.

- **Gravestones are public landmarks (§3.17).** A destroyed-harvester
  marker is now visible to **every seat**, even on cells that seat never
  scouted (the wreck shows through fog; the underlying terrain stays
  hidden), matching the public visibility of EMP clouds.

- **Replay VAULT fixes.** The CREDITS readout now tracks the scrubber via a
  per-frame credits snapshot; the WEAPONS BAY **USED** counts populate on
  every replay (derived from `emp_launch` / `mine_lay` / `chaff_flare`
  launch frames, so they survive the Snowflake round-trip and pre-snapshot
  seasons); destroyed/expired assets bucket correctly from the
  authoritative per-frame entity snapshot.

### v0.9.19 — 2026-06-17

**Canonical competitive ruleset, probe lifetime UI, player identity system, hot-drop strategy.**

- **Canonical configuration documented** (new section at top of rulebook).
  Standard competitive settings now defined: `live_only` drop mode, probe
  radius `4`, probe lifetime `3` Nox, `7`-day seasons, no free repairs,
  grid world view. These balance exploration, risk, and competition.

- **Player identity & customization (v0.9.18).** Each seat now has dynamic
  `display_name`, 3-letter `tag`, and custom `color` (hex) from a curated
  palette. Bot seats auto-generate Latin names (e.g. "Purpureus Vipera") with
  matching tags ("PVI") and random palette colors seeded by game seed. UI
  surfaces (scoreboard, timeline, vault tooltips, agent feed, end screen,
  etc.) use `playerTag()` / `playerDisplayName()` instead of static
  "P1/P2/WHITE/YELLOW" labels. Colour system unified: CSS `--seat-pN`
  variables, JS `ownerColor()`, agent-entry borders all draw from the same
  source (`player_profiles` from `/status` and `/replay` APIs).

- **Probe lifetime UI indicators (v0.9.18).** When `SOC_PROBE_LIFETIME_NIGHTS`
  is active, probes display remaining life via concentric square rings:
  - **Double ring** — 3+ Nox remaining
  - **Single ring** — 2 Nox remaining  
  - **Bare glyph** — 1 Nox remaining (expires at next Aurora)
  
  Tooltips show exact "expires in N Nox(s)" for both friendly and enemy
  probes. Asset panel (ORDERS roster) mirrors ring graphics on probe chips
  and includes a "destroyed/expired" section.

- **Hot-drop strategy documented (§3.9.8).** Under `live_only` rules, securing
  a contested drop is a two-phase operation: (1) launch probe onto/adjacent
  to target, (2) drop harvester into newly-lit area same Nox. The public
  probe launch telegraphs intent but same-hour parallel resolution guarantees
  the drop even if rivals attempt to counter. Trade-off: visibility vs.
  security.

- **Heuristic agent "hot-drop" playbook.** RED_HARVEST now proactively places
  probes on uncovered RED targets and queues same-Nox drops into the new
  coverage (replacing the old conservative re-probe pass). Reduces drop
  rejections under `live_only` from ~60 to ~3 per 7-day season.

- **Probe stock economics.** Orbit playbook builds probes to target stock (4)
  instead of fixed count, with credit reserve (50c) for catapult shipping to
  prevent starvation. Addresses zero-score regressions where aggressive probe
  building consumed all credits before any RED was shipped.

- **Agent feed dynamic N-seat tabs.** Agent rationale tabs (previously static
  p1/p2 HTML) now rebuild dynamically per active seat, making p3/p4 feeds
  reachable in 3-/4-player replays.

- **Cross-session meta cleared on reset.** `__SOC_PLAYER_META__` and CSS
  `--seat-pN` overrides now clear when starting a new game, so one session's
  custom names/colors don't leak into the next.

- **Offline N-seat battery runner.** New `scripts/run_battery.py` generalizes
  headless season orchestration to 1–4 seats (all-heuristic, file-backed).
  CLI `run_season.py` remains 2-seat only; cortex-vs-heuristic matches still
  require `--backend snowflake`.

### v0.9.17 — 2026-06-11

- **Probe collisions split into supersession vs annihilation (§3.16).**
  A probe landing on an **older** probe (an earlier hour, or one
  persisted from a previous Nox) now **destroys and supersedes** it —
  the newcomer survives, the old probe is ledgered as
  `probe_superseded` and a `probe_superseded` log row records it. Only
  probes landing on the **same turn** (same day + hour) still mutually
  annihilate (`probe_collision`, both destroyed). `spawn_probe` takes a
  new `hour` kwarg and stamps each probe's deploy turn to judge
  simultaneity.
- **Vision-rework knobs (§3.9.7, §3.11.1) — all default to current play.**
  Three runtime-read env flags let the balance lab (and a launched
  server) trial the "force interaction / telegraph farming" rework
  without code edits:
  - `SOC_DROP_MODE=live_only` — harvester drops require **live** sensor
    coverage of the landing cell (probe disk or friendly harvester plus);
    stale own-echo / memory no longer qualifies. Legality is judged on
    the **hour-start** live snapshot so a same-hour beacon kill still
    validates the landing (§3.10). Default `live_or_echo` is unchanged.
  - `SOC_PROBE_RADIUS` (default `2`) — Euclidean probe vision radius,
    now env-overridable so one probe can cover a whole farm plot.
  - `SOC_PROBE_LIFETIME_NIGHTS` (default ∞) — when set to `K`, probes
    expire at Aurora after `K` Nox (disk drops to echo, ledgered
    `probe_expired`), keeping the map dark and forcing re-probing.
- **Offline balance lab.** New `FileSocStore` (`SOC_BACKEND=file`,
  `SOC_STORE_DIR`) persists seasons as JSON per game so headless
  RED_HARVEST seasons are watchable in `/watch` with no Snowflake;
  `scripts/balance_sweep.py` + `sea_of_colours/evals/season_metrics.py`
  run N seasons per config and emit interaction/denial + balance metrics
  (baseline: `reports/baseline_2026-06-12.*`).

### v0.9.x — green + weapons rebalance

**Tighter vault, deadlier-but-dodgier weapons, public shipped ledger.**

- **Vault tightened 25 → 15** (`HOARD_CAPACITY`). Green shares the
  hoard, so a smaller vault makes every un-flushed GREEN (a standing
  −100 endgame penalty, §4.5) real dead weight and a score liability.
- **EMP is now a salvo (§4.9.3).** One launch fires
  `EMP_MISSILES_PER_LAUNCH` (3) simultaneous missiles for one
  stock/cost. `emp_launch.at` accepts a single `[x,y]` or up to 3
  `[[x,y], …]`. Blast geometry switched to **Manhattan radius
  `EMP_RADIUS` (3 → 2)** — a 13-cell diamond per missile. The salvo
  now **destroys probes and neutralizes mines** caught in any cloud,
  at formation and on each cloud tick (friendly fire on).
- **Mines lay a hidden cluster (§4.9.4).** `MINE_BATCH_SHAPE` →
  `"plus"`: one `mine_lay` arms a 5-cell (center + N/E/S/W) field for
  one stock. Counterplay leans on the public "minelayer deployed"
  orbital observation and on EMP clearance.
- **Chaff window 1 → 3 hours (§4.9.5).** `CHAFF_DURATION_HOURS` = 3:
  a flare smothers every other seat for hours N, N+1, N+2 (fixed a
  latent carry-forward bug that over-stretched the window once the
  duration exceeded 1).
- **SHIPPED is an uncapped public ledger (§3.13).** `SHIPPED_CAPACITY`
  is `None` (no overflow drop). The SHIPPED pane is a permanent,
  all-seat, owner-coloured record of everything every house sent to
  Earth — visible to everyone in live play and replay. Hover surfaces
  each parcel's code, effective+raw purity, transit tax, yielded
  score, tier, and `refined_from` lineage. The yielded `score` and
  `tier_multiplier` are stored on the shipped row (authoritative, not
  recomputed), and the agent view gains a top-level `shipped_record`.

### v0.9.9 — 2026-06-05

**Strikeout orchestrator, true N-seat simultaneity, dynamic replay-view.**

- **Strikeout orchestrator (§3.10).** Every queued row now burns a
  slot, even illegal ones. ``MAX_MOVES`` stays at 21; ``MAX_QUEUE_LEN``
  is honoured on the server for back-compat but the live composer
  hard-stops at 21 because the orchestrator no longer skips-and-retries
  invalid items. Parse-time waste (``WasteMove``), runtime-illegal
  rejections, EMP-disable, and chaff-cancellation all push a frame
  AND advance the seat's pointer / applied count. The frontend
  renders these as strike-through rows in the replay log so a seat
  can see exactly what failed without having to diff its submitted
  queue against the resolved one. Code: ``_advance_until_valid`` in
  ``sea_of_colours/game/simulator.py``,
  ``_cancel_next_actionable`` cleanup, and ``_next_actionable`` no
  longer skipping wastes.
- **Queue UI: ``X/21 slots used``.** ORDERS · policy composer
  header reads ``Build a directive · 21 slots / Nox`` and the
  fieldset counter reads ``X/21 slots``. The tab badge mirrors the
  same format. Pre-v0.9.9 the badge read ``X items``, which
  obscured the per-seat budget.
- **True N-seat simultaneity in replay.** ``buildReplayTicks`` now
  groups EVERY actionable frame at the same hour across ALL seats
  into a single tick (not just pairs). Pre-v0.9.9 a 4-seat replay
  collapsed p1+p2 into one tick and p3+p4 into the next, visually
  "first two play, then the other two play" — wrong for a game
  where every seat acts on every hour.
- **Dynamic replay-view buttons.** The ``[ P1 ] [ P2 ] [ P1+P2 ]
  [ OBS ]`` row is gone. The view-perspective bar now renders one
  ``[ Pn ]`` button per active seat, each stroked in the seat's
  owner colour, plus a single ``[ OBS ]`` button that shows every
  active seat's vision combined. Code:
  ``renderReplayViewButtons`` in ``server/static/app.js`` plus
  the ``mergeAllPlayerCells`` / ``paintObsVisionMap`` N-seat
  rewrites.

**SETTINGS tab, live turn animations, and organic fog wave.**

- **GRAPHICS tab renamed SETTINGS.** The tab bar now reads
  `[1] ORBIT · [2] ORDERS · [3] INTEL · [4] VAULT · [5] SHIPPED ·
  [6] LOG · [7] AGENT · [8] SETTINGS`. The SETTINGS panel title is
  updated accordingly.
- **SETTINGS → ANIMATION block.** A new section above the CRT block
  exposes per-feature animation toggles. Current toggles:
  - **show empty EMP turns** (default on) — when off, hours where both
    players' moves were smothered by EMP (`tag="empd"`) are skipped in
    the live-turn animation sequence. Persistent via
    `localStorage["sea_of_colours:empLulls"]`.
- **Live turn animation playback.** All replay animations — probe
  streaks, harvester moves, orbital lifter arcs, EMP missile + ring
  expansion + cloud, mine drops, chaff static, and collision rings —
  now play automatically on the live map once after a turn resolves,
  at the same 620 ms cadence as the replay scrubber. The sequence
  fires from `_playLiveTurnAnimations(startTickIdx)` after
  `refreshNightReplay` appends new ticks; `{ playFx: true }` must be
  passed to `pullAllMaps` (done at every manual and agent submit site).
  Interrupts cleanly if the user clicks ▶ PLAY (scrubber takes over)
  or LIVE (map restores immediately).
- **Organic fog wave.** Fog tiles now pulse with a slowly shifting
  plasma-pattern opacity (`_fogOpacityAt` — 3 summed sine waves at
  different x/y spatial frequencies). The JS ticker updates every 250 ms
  via `_startFogWaveTicker` / `_applyFogWave`. The pattern avoids the
  diagonal-band artefact of single-sine approaches and is robust to
  replay scrub repaints.
- **EMP comet missile + ring expansion.** The EMP ghost is now a cyan
  comet (glowing `::before` sphere joined to a `::after` gradient
  trail, `transform-origin: 100% 50%`). On landing, `_playEmpExpansion`
  flashes the EMP rhombus ring-by-ring outward (55 ms stagger,
  180 ms flash per ring) before the cloud overlay appears.

### v0.9.8 — 2026-06-05

**Batched bot fan-out — 4-seat live play feels snappy again.**

- **One hydrate + one save per TRANSMIT click.** Pre-v0.9.8 each
  auto-fired bot drove its own ``run_agent_turn`` → ``submit_policy``
  → ``save_session_full`` cycle, plus a second ``save_session_full``
  from ``save_agent_rationale``. For a 4-seat (1H + 3B) game that's
  six full save fan-outs per phase × two phases per TRANSMIT click
  ≈ 50–90s wall on a healthy Snowflake warehouse — long enough that
  the user reported "the red harvests look slow".

  The new path hydrates the session ONCE, runs every pending bot
  directly against the in-memory object via ``_run_bot_in_memory``
  (~30ms per bot, the whole 6-bot fan-out is < 100ms of CPU), lets
  the Nox / orbit resolve naturally against the same in-memory
  object, and persists everything in a single parallelised write
  batch: ``save_session_full`` ∥ ``append_agent_invocation`` ∥
  ``append_log`` ∥ ``append_replay_frames``. Wall time on a 4-seat
  TRANSMIT drops from ~90s to ~7s (≈ 13× faster); the orbit submit
  drops from ~50s to ~5s.
- **``submit_policy`` / ``submit_orbit_actions`` opt-in inline
  fan-out.** Both engine entry points now accept ``auto_fire_bots:
  bool = False``. The live-play HTTP routes (``POST /policy``,
  ``POST /orbit``) pass True; tests / season-runner / eval harness
  callers see the legacy semantics. ``auto_fire_bot_seats`` itself
  is preserved (now thin wrapper around the in-memory helpers) so
  external callers and the test surface keep working unchanged.
- **Parallelised final writes.** ``_persist_bot_fanout`` runs the
  four independent table writes in a thread pool — wall ≈ slowest
  single phase instead of the sum. Inside the agent-invocation
  phase, the per-row inserts are themselves parallelised (one
  thread per pending bot), since SOC_AGENT_INVOCATION is append-
  only with no FK constraints.
- **Live progress feed beneath TRANSMIT.** A new
  ``cc-transmit-progress`` list sits under each TRANSMIT button.
  ``startTransmitProgress`` runs a two-track feed while the submit
  is in flight: (1) a synthetic timeline shows what the server is
  ROUGHLY doing right now ("bots plotting", "resolving Nox",
  "settling orbit", "writing to praxis"), with the button's
  headline label hot-swapped to match; (2) ``/status`` polling
  surfaces real log_tail entries (bot rationales, probe launches,
  orbit settlement chatter, day flips) as soon as the save lands.
  The latest line wears a green cursor caret so the user can see
  the most recent step at a glance; on completion the panel
  pushes a "ready · day N · phase X · your move" line and fades
  itself out.
- **RED_HARVEST staircase walk + multi-seat decorrelation.** Two
  blocking bugs in the heuristic agent surfaced once 3- and 4-seat
  live play became routine:
  1. ``_fog_scout_walk`` emitted diagonal step orders
     (``+1,+1`` per tick) which the engine rejects because
     :meth:`GameSession.try_step_unit` only accepts cardinal
     moves (Manhattan distance == 1). The screenshot in the
     bug report showed p2 drop at (22,14) followed by five
     ``not adjacent`` step attempts on the SAME hour — every
     slot a ``waste`` frame, harvester never moved, banked 0
     parcels. The walk now emits a staircase: each step
     changes EXACTLY one axis by ±1 and alternates between
     x-leading and y-leading ticks, with a per-seat RNG
     deciding the lead axis when both axes pull equally so
     two bots from the same start don't trace the same path.
  2. The probe drop / harvester anchor fallbacks were
     deterministic per-seat-index, so 3 RED_HARVEST seats in
     the same 4-seat session would converge on identical
     cells whenever no fog cluster had a unique visible edge
     (the common day-1 / day-2 case). A new
     ``_seat_day_rng(view, seat, salt)`` helper seeds a
     ``random.Random`` from ``(session_id, seat, day, salt)``:
     idempotent within a turn (so the planner is still
     deterministic and tests stay stable), but decorrelated
     across seats and across games (so every fresh session
     opens with a different fan-out and seats never pile on
     the same cell). Applied to the quadrant fallback table
     shuffle + per-anchor (±1, ±1) jitter in
     ``_plan_probe_drops``, and to the quarter-point fallback
     shuffle in ``_pick_fog_anchor``.
  Two new regression tests in ``test_agent.py`` pin both
  behaviours: ``test_fog_scout_walk_only_emits_cardinal_steps``
  asserts every step is Manhattan-adjacent to the previous,
  and ``test_probe_drops_decorrelate_across_seats_on_blind_day_one``
  verifies 4 seats land their first probe on 4 distinct cells.
- **Per-day LOG attribution + N-seat AGENT bucket fix.** The
  batched fan-out caused a regression where ONE ``append_log``
  call now spans multiple days (day-N planning → day-N Nox →
  day-N+1 orbit + planning), and the pre-v0.9.8 path stamped
  every row with the FINAL ``sess.day``. The LOG drawer and the
  AGENT panel both showed events from earlier days under the
  current day's header, and the per-day replay LOG filter
  returned the wrong day's rows. Three coordinated fixes:
  1. ``Session.log_info`` / ``log_error`` / ``log_event`` now
     stamp ``day = int(self.day)`` on EVERY entry at write time
     (not just orbit chatter), so the day attribution rides with
     the row across the in-memory log → ``sess.log_tail`` → DB
     persistence pipeline.
  2. ``_persist_bot_fanout`` (and the non-fanout fallback inside
     ``submit_policy`` / ``submit_orbit_actions``) group new log
     lines by per-entry day before calling ``append_log``, so
     ``SOC_GAME_LOG`` carries accurate per-day attribution.
  3. The replay endpoint now returns ``log_by_day`` (full session
     log indexed by day, partitioned exactly using each entry's
     ``day`` field with a legacy text-sniff fallback), and the
     LOG drawer re-renders against the current focus day on
     every status poll AND every replay scrub. The harvest
     regex + capture path + bucket map now all accept p1..p4
     (pre-v0.9.8 the regex matched ``[pP][12]`` only and the
     ternary forced p3/p4 rationales into the p1 bucket, smearing
     three bots' chatter into one panel).
  4. **Critical follow-up fix.** ``_normalize_log_entries`` in
     ``GameSession.from_dict`` was aggressively whitelisting every
     entry down to ``{level, text}``, which silently dropped the
     ``day`` field on every save → load roundtrip (i.e. on EVERY
     API call, since the engine hydrates from ``json_state`` each
     time). The user-visible symptom: in multiplayer the LOG
     collapsed into an undifferentiated stream because no row
     carried its day; single-player happened to look fine because
     there was less to attribute. The normaliser now preserves
     ``day``, ``phase``, ``kind``, ``data``, and ``ts`` while
     still defending against legacy / malformed payloads. A
     regression test in ``test_session_persistence.py`` —
     ``test_log_entries_preserve_day_phase_kind_through_hydrate_roundtrip``
     — pins the contract.

### v0.9.7 — 2026-06-05

**Probe-launch terrain stays fog + cannibalisation no longer ships
zero-purity parcels.**

- **§3.15 tightened: probe-launch markers reveal the probe, not the
  ground.** Pre-v0.9.7 the opposing seat received a full tile
  snapshot at the launch cell (`paint` + `tile` + `purity` +
  `occupants`), which exposed terrain the seat had never observed
  AND let opportunistic bots drop harvesters there as if they had
  legitimate echo coverage. The broadcast now carries the probe
  occupant payload ONLY (no `paint` / `tile` / `purity`); the
  frontend renders the probe glyph floating over a still-fog cell,
  and the engine + agent both treat the marker as drop-INVALID.
- **§3.10 narrowed accordingly.** Harvester drops now require either
  live LoS, an OWN-seat echo / memory entry, or any echo whose
  `via` is NOT `probe_launch`. The reject message is updated to
  `"in fog — harvesters can only land on live or own-echo tiles.
  Enemy probe-launch markers don't reveal terrain."`.
- **Catapult cannibalisation no longer ships 0-purity parcels.**
  When per-parcel cannibalisation would reduce a shipping parcel's
  `effective_purity` to ≤ 0, the parcel is now fully consumed as
  fuel instead of clogging the shipped bay at score 0. New engine
  log line: `[orbit] {seat}: catapult cannibalisation consumed N
  parcel(s) entirely as fuel`. The seat catapult summary gains a
  `burned_to_fuel: int` counter.
- **N-seat replay timeline.** `buildReplayTicks` no longer hard-pairs
  p1+p2 only; it now pairs any two adjacent same-day frames from
  different seats, which keeps the scrub-cursor in sync with the
  timeline header for 3- and 4-seat games. `shouldShowTimelineFrame`
  and the agent-log lazy-fetch loop handle p3/p4 too.
- **N-seat live submit no longer hard-fires p2.** Pre-v0.9.7
  `submitSoloNight` and `submitSoloOrbit` followed the human's
  `postPolicy("p1", ...)` with a hard-coded `postPolicy("p2", [])`
  to mirror the original 2-seat solo loop. In a 3- or 4-seat
  session the server's `auto_fire_bot_seats` had already advanced
  the phase by the time the second call landed, so the second
  call hit the policy endpoint with `phase=orbit` and bounced
  back `"wrong phase (orbit); policies only during planning."` —
  which surfaced as the "4-player crash" symptom (game stuck on
  the PRAXIS panel with a yellow error banner even though the
  engine had rolled into ORBIT). The frontend now submits ONLY
  for the human seat and lets the server walk the rest of the
  seat list. On either success OR failure it re-pulls the live
  status so the orders/orbit panel swap can never lag the
  server's phase.

### v0.9.6 — 2026-06-04

**Single-lane catapult + tier-multiplier scoring + simplified red_harvest.**

- **Scoring is tier-weighted.** RULEBOOK §3.1 rewritten:
  `score(parcel) = effective_purity × MULT[tier]` where `MULT = {trace:
  0.75, vein: 1.0, mass: 1.5, pure: 3.0}`. The multipliers live in
  `RED_QUALITY_MULTIPLIER` and are explicitly tunable. A single
  PURE-255 launch is now worth 765 — three times what ten TRACE-50
  ships earn. Hoard parcels still store raw purity; the multiplier
  only applies at ship time.
- **Catapult collapses to one lane.** `ship_auction` and
  `ship_tithe` are deleted; one `ship_catapult{parcels,
  max_fuel_per_slot}` action replaces both. The catapult exposes
  `CATAPULT_ROW_COUNT × CATAPULT_SLOTS_PER_ROW = 4 × 5 = 20` slots
  arranged in progressively-pricier rows
  (`CATAPULT_ROW_THRESHOLDS = (50, 100, 150, 200)` RED pooled per
  row to ship). Bids flatten into `(fps, seat)` entries, sort DESC,
  fill rows top-down. Underfilled rows lose their fuel as sunk
  cost. RULEBOOK §4.4 rewritten in full with three worked examples;
  §4.5 deleted (redirect to §4.4).
- **Engine auto-picks parcels.** Bidders never name parcel ids —
  the resolver pulls each seat's TOP-N highest-purity RED from the
  hoard at settlement. Fuel comes from **spare** RED (lowest-purity
  first), with cannibalisation as the fallback: insufficient spare
  fuel reduces each shipping parcel's `effective_purity` evenly,
  which `score_for` then reads instead of raw purity.
- **Red harvest's orbit playbook simplified** to a fixed priority
  order: repair damaged harvesters → build new harvester (under
  cap, affordable) → build 2 probes → `ship_catapult` row-1 cheap
  bid (5 slots at 11 RED/slot, 55 RED total > 50 threshold) →
  `solar_jettison` of any GREEN hoard parcels. The agent drops 2
  probes on Day 1 (cluster-fallback fix from v0.9.6-pre) so it
  isn't blind into Orbit.
- **UI + agent payload.** The vault tooltip now renders
  `tier × multiplier` and `score if shipped` for every RED parcel.
  The orbit-flash modal shows per-row threshold + fuel-pool
  breakdown ("row 1 · SHIPPED · fuel 165/50 · 5/5 slots"). The
  catapult composer prompts for `(parcels, max_fuel_per_slot)`.
  `view.orbit.ship_prices` now exposes `row_thresholds`,
  `slots_per_row`, and `quality_mult` so the frontend reads the
  table instead of hard-coding it.
- **Hard removal — no back-compat shim.** Legacy replay frames
  carrying `ship_auction` / `ship_tithe` actions now parse as
  `OrbitWasteAction`. The `catapult_history` row shape changes
  from `{day, auction, tithe, jettison}` to
  `{day, catapult, jettison}`; old persisted history rows survive
  but render with empty inventories.

### v0.9.3 — 2026-06-01

**Weapons are now BUILT during the Orbit phase, not paid on launch.**

- Three new Orbit actions: `build_emp`, `build_mine`, `build_chaff`.
  Each accepts an optional `count` (default 1, clamped to ≥1) and
  pays `count × (blue_purity + credits)` from the seat's vault and
  wallet **at orbit settlement**. Costs are unchanged: 200 blue +
  250c per EMP, 100 blue + 100c per mine, 255 blue + 0c per chaff.
  Atomic — a batch that the seat can't pay for in one go is
  refused with a yellow log line and consumes no resources.
- New per-seat state `weapon_stock = {emp, mine, chaff}` tracks the
  built inventory. Persists across the orbit/Nox boundary so a
  seat that builds three EMPs on Day 5 can deploy them across
  Nox 5, 6, and 7 without rebuilding.
- Nox-phase `emp_launch` / `mine_lay` / `chaff_flare` moves now
  **drain stock instead of paying live**. A launch move with zero
  matching stock is wasted with the message
  `"no <weapon> in stockpile — build one in the next Orbit phase
  before firing"`; the simulator does NOT silently substitute a
  WAIT (the seat sees an explicit yellow line).
- Frontend: a new **WEAPONS** readout chip in the Orbit panel
  (`EMP 0 · MINE 0 · CHAFF 0` with the live icons) plus three
  `[ + build EMP/MINE/CHAFF ×N (cost) ]` toolbar buttons mirror the
  `[ + build probes ]` UX exactly. Each build button has an
  adjacent numeric input for the batch count.
- Orders pane chips now render the stockpile-aware icons (a
  hollow rhombus for mines, a probe-style dot inside a blue ring
  for EMP, a unicode density loop `░ → ▒ → ▓ → █` for chaff) and
  disable themselves when the seat has zero of that weapon —
  click-to-queue is blocked, the tooltip nudges the seat to
  build one in the next Orbit phase.
- Agent view exposes `orbit.weapon_stock` and `orbit.weapon_prices`
  so the orchestrator can plan a batch build without remembering
  the constants.

### v0.9.2 — 2026-06-01

**Drop rule + economy fixes + UI polish.**

- **§3.10 update — fog-of-war landing.** A harvester can only LAND
  on a cell that's currently in the seat's live LOS, has a probe
  echo, or has a memory_tiles entry from past visibility. Stepping
  into fog after landing is still allowed (you can wander into the
  unknown), and pickup is unrestricted — only the initial drop is
  gated. Wire: `try_drop_unit` returns
  `"drop: (x,y) is in fog — harvesters can only land on live or
  echo tiles"` for forbidden landings.
- **GREEN is binary, not graded.** Every GREEN parcel banked into
  the vault is purity 255 unconditionally. The harvester's parcel
  builder now clamps GREEN at the source so eval-scenario seeds at
  fractional purity can't violate the invariant.
- **Blue economy bugfix.** `blue_purity_available` and
  `debit_blue_purity` read parcel purity via
  `_parcel_purity(parcel)` (which understands
  `purity_at_harvest` / `origin_purity` / `purity`) instead of the
  raw `parcel["purity"]` key that didn't exist on hoard rows. With
  this fix, blue parcels actually pay for weapons.
- **UI — numbered stickers on harvesters only.** Probes lost their
  per-unit number badge (both on the map overlay and the asset
  roster chips). Probes are identical disposables; tracking which
  specific probe is which adds noise. Harvesters keep the numbered
  badge.
- **UI — vault / orbit panel overflow fix.** Both panels now use
  `overflow-y: auto` so the bottom of the asset roster + commit
  button stay reachable on shorter screens.

### v0.9.1 — 2026-06-01

**Orbit phase UI overhaul.** No new mechanics — this turn collapses
several Orbit-phase friction points into one-click flows and surfaces
public catapult inventories for both agents and watchers.

- **Batched probe builds.** `BuildProbeAction` now takes a `count`
  field (default 1, back-compat). One Orbit action slot can mint
  multiple probes; the resolver bills `count × PROBE_BUILD_COST`.
  **v1.2 — partial fill:** a batch now mints as many probes as the seat
  can afford instead of rejecting the whole order (`×2` on a one-probe
  budget buys one). A trimmed order logs a red `error`-level amendment
  line in the orbital log; only a batch that can't afford a single
  probe is a hard rejection. Wire: `{"a": "build_probe", "count": N}`.
- **Tier-only refine.** `RefineAction` accepts `source_tier="trace"`
  or `source_tier="vein"` and the resolver promotes EVERY RED parcel
  of that tier in one shot via the new `apply_refine_all` helper.
  Legacy `inputs=[...]` shape still works for back-compat. The Orbit
  panel exposes two dedicated buttons that disable themselves when
  the tier count is 0.
- **Public catapult inventories.** Each `catapult_history` settlement
  section (auction / tithe / jettison) now stamps a public
  `inventory` block (`count`, `total_purity`, `tier_counts`,
  `color_counts`) per seat AND in aggregate. The agent view also
  emits a flat `last_catapult_summary` so agents can read yesterday's
  shipping volumes without walking the full settlement tree.
- **Orbit log + filter chips.** Orbit-phase log entries auto-stamp
  `phase="orbit"` + `day`. The replay payload exposes
  `orbit_log_by_day`; the LOG tab gains ALL / NOX / ORBIT filter
  chips that switch the timeline view.
- **Orbit pip on replay strip.** When the orbit-flash toggle is on,
  each day with a catapult settlement gets an amber pip on the
  replay scrub bar. Click jumps to that day's first frame AND opens
  the catapult modal.
- **On-map orbit overlay.** Crossing into a new day with the orbit
  toggle on floats a per-seat banner over the map summarising what
  each seat did that orbit phase (built / refined / shipped /
  tithed / jettisoned). Auto-fades after 3.5s.
- **Catapult modal redesign.** Sections now lead with the public
  aggregate inventory and per-seat inventory summaries; empty lanes
  render an explicit "x catapult empty" marker instead of
  disappearing.

### v0.9.0 — 2026-05-19

**Interdiction layer.** Three weapons + an explicit WAIT command
shipped this turn (RULEBOOK §4.9). All numeric balance dials live
in [`sea_of_colours/game/weapons.py`](sea_of_colours/game/weapons.py)
so a future re-balance is a one-file edit.

- **EMP warhead** (`{"a": "emp_launch", "at": [x, y]}`). Detonates
  on the target tile and disables every harvester in a Chebyshev
  radius of `EMP_RADIUS` (default 3) for the next `EMP_CLOUD_HOURS`
  (default 8) hours of the same Nox. Friendly fire is on. Open
  action — both seats see the launch and the cloud cells. Cost
  `EMP_COST_BLUE_PURITY=200` + `EMP_COST_CREDITS=250`.
- **Caltrop mines** (`{"a": "mine_lay", "at": [x, y]}`). Plants a
  hidden mine; any harvester (own or opponent's) stepping onto it
  has its step cancelled, becomes damaged, and the mine is
  consumed. Persists across Nox. Hidden by default; probe
  witness drops an echo into the other seat's intel. Cost
  `MINE_COST_BLUE_PURITY=100` + `MINE_COST_CREDITS=100`. Batch
  shapes (`line3` / `L3` / `scatter_r1`) wired but stubbed —
  `MINES_PER_BUY=1` / `MINE_BATCH_SHAPE="single"` ship today.
- **Orbital chaff flare** (`{"a": "chaff_flare"}`). At hour `N`,
  every OTHER seat's hour-`N` action is cancelled (`tag="chaffed"`).
  The triggerer's chaff itself succeeds. Multi-hour chaff is one
  constant bump away (`CHAFF_DURATION_HOURS`). Cost
  `CHAFF_COST_BLUE_PURITY=255`, no credits.
- **WAIT command** (`{"a": "wait"}`). Consumes one of the 21 hour
  slots without acting. Combined with the existing hour clock
  (§3.10 v0.7.4) this lets a seat schedule actions for specific
  hours: nine WAITs followed by an EMP launch fires the warhead at
  hour 10. The Snowflake replay reader collapses runs of `wait`
  / `empd` / `chaffed` frames into a single `tag="lull"` summary
  frame in the parallel `frames_compact[]` array; the frontend's
  "Skip lulls" toggle switches between `frames[]` (full) and
  `frames_compact[]` (collapsed) at scrub time.

**Blue purity economy.** Weapons are paid out of vaulted BLUE.
`GameSession.blue_purity_available(player)` reports the sum;
`GameSession.debit_blue_purity(player, cost)` consumes parcels
**lowest-purity first** and wastes any overshoot in the final
parcel (no refund). The lowest-first rule deliberately punishes
fragmented vaults: two 50-purity parcels are worse than one
100-purity parcel for the same job.

**Persistence + replay.** New `GameSession.emp_clouds` (list) and
`GameSession.mines` (`"x:y"` keyed dict) round-trip through
`to_dict` / `from_dict`. EMP clouds are intra-Nox only and are
zeroed at Aurora; mines persist across Nox. The replay frame
gained `frame.emp` / `frame.mine` / `frame.chaff` / `frame.emp_clouds`
optional channels.

**Documentation.** Fixed the 21-vs-25 move-cap drift in the
simulator module docstring and in §5.3 (cost model). The Nox
budget is 21 applied moves (one per planetary hour); the
historical "25" was a draft constant that ran out of date.

### v0.8.0 — 2026-05-19

- **Orbit phase lands (§4).** Days **2+** open in `Phase.ORBIT`
  before transitioning to `Phase.PLANNING`. Both seats may queue
  up to `MAX_ORBIT_ACTIONS = 3` actions
  (`build_harvester`, `build_probe`, `repair`, `refine`,
  `ship_auction`, `ship_tithe`, `solar_jettison`); when both lock
  the new
  [`sea_of_colours/game/orbit_resolver.py`](sea_of_colours/game/orbit_resolver.py)
  settles in a fixed order. Day 1 opens directly in PLANNING with
  `0c` (no birth stipend, no day-1 Orbit; v1.1) — credits are only
  spendable in Orbit, and the first `1000c` stipend lands at the
  day-2 Orbit entry.
  Snowflake gains `SOC_SUBMIT_ORBIT_ACTIONS`, the FastAPI server
  gains `POST /api/game/{id}/orbit`, the agent view gains an
  `orbit` block (credits, probe stock, harvester cap, green
  owned, ship/jettison pricing, `last_catapult_results`), and
  the human Command Center grows a leading `[1] ORBIT` tab with
  pickers for every action. AI agents auto-skip Orbit (submit
  an empty queue with a one-line rationale) until the v0.8.x
  Cortex specs catch up.
- **Vault and shipped capacity halved.** `HOARD_CAPACITY` and
  `SHIPPED_CAPACITY` both drop from 50 to 25 to make the
  ship-vs-jettison-vs-refine trade-off bite faster. The §3.14
  tier-priority cascade is unchanged in shape; only the slot
  count moves.
- **Score is shipped-only.** `score_for` and the
  `SOC_SESSION_STANDINGS` view now compute `score` as
  `sum(shipped_squares.origin_purity)`; vault mass is inventory,
  not revenue. `hoard_score` and `shipped_score` are still
  returned as diagnostics. The Goal section in §3.1 is rewritten.
- **Paid repair, paid probes.** The Aurora auto-repair sweep is
  gone — damaged harvesters now persist into the next Orbit
  phase and must be repaired via a paid `repair` action (`500c`).
  Pickup still clears damage as a "free" path. Probes are now a
  finite resource (`probe_stock`, initial `2` per seat); every
  `ProbeMove` consumes one and is rejected as waste when the
  stock is empty. Refill via the Orbit `build_probe` action
  (`250c`).
- **Two-catapult shipping.** The `ship_auction` lane is a
  sealed-bid combinatorial auction (12 slots, ranked by
  fuel-per-slot, partial-fill on the marginal bid). The
  `ship_tithe` lane is a fixed-fee 3-slot lifeline (`25` RED
  fuel, 50% value haircut) with slot 3 reserved for the
  behind-player. Both write structured rows to the new
  `catapult_history` field surfaced in the agent view as
  `last_catapult_results`.
- **Solar jettison (inverse catapult).** GREEN parcels finally
  get a sanctioned disposal route. Bids are pooled; the
  per-parcel cost is `max(JETTISON_PRICE_MIN,
  JETTISON_PRICE_BASE - pool / JETTISON_FUEL_DENOMINATOR)` (defaults
  100 / 25 / 16). Bids settle AFTER the shipping auction so
  each seat's RED fuel pool is clamped to post-ship purity —
  shipping aggressively in the same pass shrinks your jettison
  ceiling automatically. The user's worked example (4-seat ×
  200 → pool 800, p = 50, 4 parcels each) is the calibration
  target. The §3.4 rule on green is rewritten to reflect that
  jettison is now legal and priced rather than vault-overflow
  tolerance.
- **Refine.** Combine same-tier RED parcels into the next tier up
  with exact purity conservation: `S // M` full target-tier
  outputs plus one `S % M` residual at the source tier
  (`M = 150` for trace→vein, `254` for vein→mass). New parcels
  carry `lineage = "refined"` and a `refined_from` provenance
  array. Mass and pure are unrefinable.
- **Green map generation rewrite (§2.3).** The pre-v0.8.0 polar
  edge mask is replaced with **1-3 same-orientation diagonal
  bands** that stretch across the map. Orientation snaps to
  eight discrete angles (`0°, 22.5°, … 157.5°`); band centers
  are spaced evenly along the perpendicular axis with per-band
  jitter. Band count, angle, and offset are all RNG-derived
  from the session seed, so the map is still fully
  deterministic. The CLI gains `--green-band-count` and
  `--green-band-half-width` flags; `--band-depth` is retained
  for back-compat but ignored.
- **Standings view simplified.** `SOC_SESSION_STANDINGS.score`
  is now `shipped_score` directly (no more `hoard + shipped`
  sum). The `rank` column re-ranks on the new metric. Old rows
  are recomputed on view re-creation; no DDL migration is
  needed beyond rerunning `scripts/deploy_soc_schema.py`.
- **Test harness migration.** A new `tests/conftest.py`
  monkey-patches `GameSession.new`, `init_session`, and
  `NightSimulator.run` to force-skip the Orbit phase for the
  legacy test suite. Existing tests that pre-dated v0.8.0 keep
  passing without touching every fixture; the dedicated
  `tests/test_orbit_v1.py` suite drives the Orbit resolver
  directly.

### v0.7.6 — 2026-05-29

- **Orchestrator config search (Phase 1).** Locked layer 3 (the
  harness world view) of the four-layer chain — game mechanics →
  game orchestration → harness → agent — by standing up an A/B
  bench between two world-view shapes.
  - **`list_v1`** (baseline): harness emits the existing
    `world.live[]` / `world.echo[]` flat arrays.
  - **`grid_v1`** (new): harness emits `world.grid[y][x]` — a 2D
    nested JSON array (`null` = fog, dict = live/echo cell). The
    spatial structure of the JSON itself encodes adjacency, so
    the agent reads "what's north of (x, y)" as `grid[y-1][x]`
    instead of scanning a flat list for `(x, y-1)`.
  - World-view shape is driven by a new `SOC_AGENT_WORLD_VIEW`
    env var (`list` default, `grid` opt-in). Inside the harness,
    `sea_of_colours.snowpark.view._render_world_grid` projects
    the dense view into the 2D array; the runtime's prompt
    builder auto-detects which shape is in the payload and emits
    the matching "READING THE WORLD" primer.
  - Two deployed Cortex agents now exist, one per shape:
    `SOC_RED_REAPER_LIST` (`snowflake/soc_create_agent_list.sql`)
    and `SOC_RED_REAPER_GRID` (`snowflake/soc_create_agent_grid.sql`).
    Base instructions (COMMIT-FIRST, hard rules, doctrine, vault
    ladder) are identical between the two specs; they diverge
    only in the "READING THE WORLD" section. `scripts/
    deploy_soc_schema.py` now finds and deploys every
    `soc_create_agent*.sql` file under `snowflake/`.
  - Eval bench picks up matching named configs in
    `sea_of_colours/evals/configs.py` (`CONFIGS = {list_v1,
    grid_v1}`). `scripts/run_evals.py` gains `--config list_v1`
    for a single run and `--compare list_v1,grid_v1` for a
    side-by-side markdown report.
  - Three new spatial scenarios (`multi_hop_seam`,
    `enemy_intercept`, `two_seams_choose_one`) cover curving
    seams, enemy-path interception, and budget-aware seam choice
    — designed to differentiate spatial-reasoning quality
    between the two world views.
  - The v0.7.5 ASCII-board experiment and its neighbours-map
    revision are both reverted. The previous v0.7.6 "neighbours"
    entry was an early sketch; the version that ships is this
    orchestrator-config bench.

### v0.7.5 — 2026-05-27

- **Agent eval harness (`sea_of_colours.evals` package).** New
  test-fixture-style harness for evaluating agent reasoning on
  pre-built, deterministic world states. Replaces "watch a season
  and squint at the log" with a tight, reproducible feedback loop on
  prompt and spec changes.
  - `WorldBuilder` — fluent DSL for constructing seeded sessions with
    hand-placed harvesters, probes, RED purity overrides, fog
    reveals, enemy footprint, hoard state, and last-Nox recap.
  - 13 built-in scenarios covering opening play (`blind_dawn`,
    `probes_only`), tactical reasoning (`tier_choice`,
    `enemy_telegraph`, `enemy_trail_in_seam`,
    `probe_collision_risk`), engine-legality (`vault_pressure`,
    `damaged_harvester`, `collision_avoidance`, `final_night`),
    and path-planning (`green_detour`, `green_corridor`,
    `friendly_probe_in_path`). The canonical list — including each
    scenario's purpose, assertions, and current heuristic baseline —
    lives in `sea_of_colours/evals/README.md` and must be updated
    in lockstep with new scenario factories.
  - Declarative `Assertion` types: `ProbeCount`, `MustAvoid`,
    `MustTouch`, `HarvesterChainHits`, `MinExpectedValue`,
    `NoSyntheticGreenSteps`, `ProbesInDistinctQuadrants`,
    `ProbesInRegion`, `EndsWithPickup`, `NoHarvesterDeployment`.
  - CLI: `python -m scripts.run_evals [--backend heuristic|cortex]
    [--scenario NAME] [--samples N] [--format markdown|json|compact]
    [--out PATH]`. Cortex backend requires `SOC_BACKEND=snowflake`
    in the environment plus a working Snowpark session — the runner
    forwards `runtime_override` exactly like a live turn.
  - pytest wrapper (`tests/test_eval_scenarios.py`) enforces
    "fixtures build cleanly" + "the heuristic must keep passing the
    subset it can handle" as regression sentinels. Full agent quality
    is tracked by the CLI report, NOT by pytest going red — we want
    failures to surface known gaps, not bury them.

- **COMMIT-FIRST prompt protocol (agent harness + spec).** Across
  the last two seasons the dominant Cortex failure mode has been
  *over-deliberation*: the agent enumerates 3-5 alternative chains
  (`option A vs option B vs option C`, `wait, but...`, `let me
  try...`), burns the 150-second wallclock, never calls
  `soc_submit_policy`, and the harness records the turn as a
  fallback under RED_HARVEST. Two corrective changes:
  - The live harness prompt (`runtime._build_cortex_prompt`) now
    opens with a **COMMIT-FIRST PROTOCOL** block instead of the
    CORE OBJECTIVE block. The directive tells the agent to take
    `navigation.best_red_visible[0]` as its harvester target, build
    one ≤7-action chain, and submit on the first tool call. It
    explicitly forbids more than one "wait" / "hmm" / "let me try"
    before submit.
  - The deployed agent spec (`snowflake/soc_create_agent.sql`)
    carries the same block. The `REASONING BUDGET` section is
    rewritten — `~250 words of reasoning` is now `~120 words` and
    the framing is "the budget is for sequencing the two tool
    calls, not for enumerating routes".
- **Replay AGENT panel — fallback split.** When a Cortex turn
  falls back to RED_HARVEST, the runtime concatenates both
  rationales with `| [fallback] ` as a separator. The AGENT
  panel renderer now splits on this sentinel and shows TWO
  entries: the Cortex chain-of-thought (boxed in red, tagged
  *"failed to submit · fallback to RED_HARVEST"*) followed by
  the heuristic plan that actually carried the turn. This makes
  the agent collapse visible at a glance instead of mislabelling
  the long Cortex transcript as a heuristic rationale.

### v0.7.4 — 2026-05-27

- **"Executing the policy" is now PRAXIS (§3.10).** The act of
  running both Houses' submitted policies into the world during the
  Nox was previously called "Nox execution" / "the execute phase"
  — internally consistent but linguistically muddled (the Nox is
  the time period; the execution is the *event*). From this build on
  the canonical term for the Nox-resolution event is **PRAXIS**.
  - The replay opening frame now reads ``[opening] PRAXIS begins``
    instead of ``[opening] Nox begins``.
  - The orchestrator log emits ``[praxis] day N — Nox begins``
    instead of ``[nightStart] day N``.
  - The planning button now reads ``[ » TRANSMIT / PRAXIS ]`` and the
    Nox-end toast says ``PRAXIS resolved`` wherever the UI used to
    say "resolve Nox". PRAXIS is treated as a noun (the enactment
    of policy), never a verb — the workflow is *transmit the policy
    → praxis begins*.
  - The synced replay-feed header is titled ``PRAXIS · ORDERS & LOG``.
  - The conceptual time-period (the planet's dark hours) is still
    called the *Nox* — only the action is renamed.

- **Planetary Nox clock — each move is an hour (§3.10, new).**
  The game now models the Nox as a fixed-length planetary day-cycle
  of **21 hours** (``HOURS_PER_NIGHT = 21``). Each *applied* move (drop,
  step, pickup, probe) takes exactly one hour. The round-by-round
  interleave (RULEBOOK §3.10) maps onto a shared wall-clock — both
  Houses' Nth applied moves happen during *the same hour N* of the
  same planetary Nox, in parallel. Watcher-side this surfaces as:
  - Every in-Nox replay frame now carries an integer ``hour``
    field (1..21). The opener and Aurora frames carry ``hour=0`` and
    stay un-tagged at the boundary.
  - Every in-Nox log line is prefixed ``[H03]`` (zero-padded to 2
    digits). The replay-feed log renders ``D2 H03 [p1] …`` so the
    watcher can read *when* tonight's chaos unfolded without
    counting frames.
  - Failed (waste) attempts share the hour of the action the seat
    is *trying* to commit, so a retry chain reads as multiple
    ``[H03]`` lines until the successful action lands.
  - Pre-Nox ``[praxis]`` headers and post-Nox Aurora /
    season-complete lines stay un-stamped (those are boundary
    moments, not in-Nox actions).

- **Season day cap is now per-session (§3.0).** ``SEASON_DAY_CAP`` in
  ``sea_of_colours.game.session`` is still the default (5 Nox),
  but the value is now also stored on each ``GameSession`` instance
  as ``session.season_day_cap``. Callers that need to honour the cap
  (the Nox simulator, the snowpark view payloads, the orchestrator
  banner) read from the session, not the module constant. This lets a
  single Snowflake database host short-form 5-Nox demos alongside
  long-form 7+-Nox tournament runs without redeploys or
  monkey-patches. ``scripts/run_season.py`` accepts ``--days N`` to
  set the cap at season creation; ``init_session`` accepts a
  ``season_day_cap`` kwarg and echoes the resolved value back. The
  SEASON_COMPLETE error message now quotes the *per-session* cap
  (``"season complete (day cap = 7); …"``) so the user sees the
  number that actually applied.

### v0.7.3 — 2026-05-27

- **Trail glyph is now strictly neutral (no green-tinted harvest
  overlay).** Earlier builds drew the harvest tracks as a green
  ``▒▒`` glyph on every cell flagged ``harvested``. Two problems
  surfaced: (a) on RED→GREEN cells the tile's own BG is already
  painted synthetic green, so the trail tint was double-counting
  on top of the green background; (b) on GREEN/BLUE harvests the
  cell now collapses to EMPTY, so a green trail glyph was lying
  about residue that wasn't there. Both layers — Python's
  ``_trail_markup`` and the JS ``renderTrailOverlayHtml`` — now
  always render the trail in the same neutral off-white as a
  pure path-density signal. The ``harvested`` flag still rides on
  ``trail_summary`` so tooltips and agent reasoning can still
  surface *"this cell has been farmed — banking scores 0"*.
- **GREEN / BLUE harvest no longer leaves a residue track.** §3.12
  has always specified that the green harvest-tracks overlay only
  applies on a RED → GREEN conversion (the freshly minted
  synthetic-green is what the watcher sees as "harvest residue").
  The engine had been over-marking: every GREEN or BLUE harvest
  also added the cell to `track_harvests`, which the renderer then
  tinted green on a tile that had actually transitioned to EMPTY.
  Fixed: `_harvest_at` now only marks the cell when the source
  tile was RED. GREEN and BLUE harvests still empty the tile
  (unchanged) and still leave the universal path trail; they just
  no longer falsely advertise a phantom synthetic-green tile.
- **Orbit-phase auto-repair (§3.6.1 clarified).** A damaged
  harvester returned to the lifter is patched up between Nox —
  there is no separate repair action. Pickup already clears the
  flag in real time; the planning-phase hand-off in
  `NightSimulator.run` now also runs a safety-net sweep that
  clears the damaged flag on any orbital harvester, so any future
  recovery path (emergency recall, save/load round-trips of legacy
  payloads, etc.) lands a healthy unit in orbit for the next
  Nox. Pickup caption updated to read *"damage auto-repairs in
  orbit"*.
- **Harvester-on-harvester mutual damage (new §3.17, §3.6.1).** Two
  harvesters arriving on the same cell — drop-on, step-into, or
  pass-through swap — now *damage each other* instead of either
  blocking or destroying. Both flip ``damaged = True``, both spill
  ALL cargo on the spot, and both stay on the surface; the wreck
  must be picked up to repair. Aurora still destroys damaged
  harvesters left out (§3.11.2 unchanged).
- **Damaged harvester rules (§3.6.1).** Damaged harvesters cannot
  step or harvest, do not block other harvesters, and can
  co-occupy a cell with other harvesters (the *only* exception to
  "one harvester per cell"). Pickup repairs in orbit on the next
  Nox.
- **Pass-through swap detection.** The Nox simulator now
  recognises the classic ``A:(11,10)→(11,11) ↔ B:(11,11)→(11,10)``
  swap pattern and resolves it atomically as a single
  mutual-damage frame tagged ``collision_swap`` in the replay.
- **Collision scar (§3.12 sibling).** Every collision stamps a
  per-cell collision mark that lives for exactly one game day,
  then decays. Stored alongside ``track_paths`` but on a separate
  channel; visible to the observer view as a dashed yellow outline
  with a diagonal-stripe overlay.
- **Synced replay drawer (frontend).** The replay scrubber now
  drives a per-tick drawer below the map with two tabs:
  - **Log** — the engine's caption feed for every executed and
    failed action, filtered by the currently selected P1 / P2 /
    Both view button; the current tick is highlighted, failed
    captions render in yellow, collision frames are subtly
    coloured for emphasis.
  - **Orders** — per-seat scheduled queue with each row colour-
    coded by execution status: bright grey (executed), yellow
    (failed), light grey (pending). The next-pending row carries a
    green ``▶`` cursor so the watcher can see where the Nox is
    heading.
- **Old-school collision-ring animation.** Drop-on / step-into /
  swap impacts spawn a chunky pixel ring at the impact cell,
  expanding in the two involved House colours (or single colour
  for self-collisions). 12-step keyframes give it a deliberately
  blocky, VCR-era feel.
- **Wreckage glyph.** Damaged harvesters now render with a
  struck-through ``X`` overlay (``.entity-overlay--damaged``) so
  watchers can spot wrecks at a glance.
- **Replay frame payload extensions.** Every replay frame now
  carries ``attempted`` and ``outcome`` ("ok" / "failed"); the
  opening frame carries ``scheduled_orders`` per seat; collision
  frames carry a structured ``collisions[]`` payload. **Failed
  attempts now also push replay frames** (tag = ``"waste"``) so the
  synced drawer can render them in chronological order alongside
  successful actions.
- **§3.16 cross-reference.** The probe-collision section now
  points at §3.17 instead of describing harvester collisions as
  "mutual destruction".

### v0.7.2 — 2026-05-27

- **Universal trails (§3.12 rewritten).** Trails are now strictly
  universal: a *single* aggregate ``trail`` summary per cell carries
  ``{n, tier, harvested?, fresh_visits[]}``. Both seats' crossings
  contribute to the same ``n`` count and to the same neutral
  off-white glyph; the trail is no longer player-tinted. The map
  alone communicates traffic density. Per-seat attribution survives
  exclusively in ``fresh_visits`` and only while ``day_now -
  day_laid ≤ 1`` (the "24h game-time window"); older crossings
  collapse into the anonymous total. Fog-of-war remains the only
  gate — fog cells leak nothing. Server-side: the per-owner
  ``_trail_overlay_entries`` helper is gone; cells now publish
  ``cell.trail`` (the summary) plus a legacy ``cell.trail_markup``
  pre-rendered glyph for the player_dense_view path. Frontend
  (`server/static/app.js`): a single ``renderTrailOverlayHtml(cell)``
  paints the universal glyph (neutral tint, green when
  ``harvested=true``) and the tooltip surfaces the ``fresh_visits``
  attribution lines plus an anonymous "+N older crossings" tail.
- **Harness primer + agent spec updated.** Both the runtime prompt's
  *READING THE WORLD JSON* primer
  ([`sea_of_colours/agent/runtime.py`](sea_of_colours/agent/runtime.py))
  and the Cortex agent spec
  ([`snowflake/soc_create_agent.sql`](snowflake/soc_create_agent.sql))
  document the new `trail` shape verbatim, including the explicit
  warning that ``harvested=true`` cells score 0 (synthetic green —
  route AROUND them).
- **Wall-clock budget bumped 75 → 150s.** The Cortex invoker hard
  cap and the agent spec's `orchestration.budget.seconds` are now
  150s (per-chunk timeout 180s, token budget 36000). The user's
  guidance is "long enough to reason, not long enough to spin", and
  150s comfortably covers the longest dense-RED chain-finding plans
  observed in pilot seasons without blocking the heuristic fallback
  on real failures.
- **CORE OBJECTIVE — SEEK DENSE RED.** Both the harness prompt and
  the Cortex spec now lead with an explicit "seek the juiciest seam"
  block before any tool grammar: trace is the minimum effort,
  probes are tier-discovery currency, and the monotonic
  trace→vein→mass→pure adjacency rule (§3.13) is the planner's
  truth.

### v0.7.0 — 2026-05-26

- **Magnetic Cover lore** — new §0.4. Establishes the in-fiction
  reason fog-of-war exists at all (no orbital topographic survey
  through the magnetosphere), the asymmetry between probe ballistics
  (public) and orblift mag-bend (private), and why probe telemetry
  is local-only. Anchors §3.8 (Visibility), §3.9 (Units), §3.15
  (Orbital launch publicity), and §3.16 (Probe collisions).
- **§3.15 Orbital launch publicity** (refined in v0.9.7). Probe
  deployments emit a public `probe_launch` log event AND pulse a
  **probe-only marker** into the opponent's `world.echo` with
  `via: "probe_launch"`. The marker carries the probe occupant
  payload so the watcher and the agent both see "enemy probe at
  (x,y)" — but it DELIBERATELY omits `paint`, `tile`, and `purity`
  so the terrain underneath stays fog. Pre-v0.9.7 the broadcast
  was a full tile snapshot, which let opponents read out tile +
  purity of cells they had never observed AND drop harvesters on
  them as if they had echo coverage. The new rule: a probe-launch
  marker reveals the probe entity, not the ground beneath it.
  Harvester drop validation honours the same distinction —
  `via='probe_launch'` echoes do NOT count as drop-valid (see
  §3.10).

  **Marker lifetime (v1.2):** The `probe_launch` marker is
  explicitly removed from the opposing House's `probe_intel` the
  moment the probe is destroyed — whether by EMP blast, harvester
  crush, probe collision, or natural Aurora expiry. Previously the
  marker persisted indefinitely (the opposing map would show a
  dead probe at the cell until the House happened to gain LOS
  over it), which meant EMP confirmation and probe decay were
  visually non-functional from the opponent's perspective. The fix
  is a backend `_clear_probe_launch_markers` call at every
  probe-destruction site.

  Harvester drops stay fully private — no opponent event, no echo
  pulse, no probe-launch-style marker — because the orblift bends
  through the magnetic cover (§0.4) and orbital observers lose
  track at the cover boundary. The opponent first sees a harvester
  via trails (§3.12), opposing-probe LOS, or collision.
- **§3.16 Probe collisions.** Two probes ending the Nox on the
  same cell — regardless of ownership — are both destroyed.
  Destroyed-asset ledger records `destroyed_reason =
  "probe_collision"` for both probes. Symmetric with §3.6
  harvester-on-harvester mutual destruction. The cell itself is
  unaffected; next-Nox probes can re-land there.
- **Policy budget recut: 21 actions per Nox, fleet-wide.**
  ``MAX_MOVES`` 25 → 21 in
  [`sea_of_colours/game/policy.py`](sea_of_colours/game/policy.py).
  Sized for 3 harvesters at full tilt
  (``3 × (drop + 5 step + pickup) = 21``); a player with 1–2
  harvesters has clear headroom for probes, a 3-harvester wing has
  to choose between extra probes and a richer harvest pattern. The
  per-harvester step limit (5/Nox) is **unchanged** and remains
  separate from the fleet-wide policy cap.
- **Structured JSON harness payload for the Cortex agent.** The
  cortex prompt drops the ASCII `grid_ascii` map and replaces it
  with a structured JSON payload sourced from the same
  `player_dense_view` machinery the frontend uses — extended with
  ledger fields (`square_id`, `lineage`, `parent_square_id`,
  `value`). The payload is partitioned so the agent can reason
  tactically without spending tokens on character-counting:
    - `meta.policy_actions_left/max` (21 cap, fleet-wide framing).
    - `hud.hoard / hud.shipped` now expose `free`, `pct_full`, and a
      `warning` string when ≥ 80% full naming the tier ladder
      (§3.14) so the agent knows which tier overflow will jettison.
    - `last_night.{my_orders, my_assets_destroyed, my_parcels_banked}` —
      structured day-1 recap including `outcome: "illegal"` + reason
      for rejected moves.
    - `competitor_intel.new_this_day` — `enemy_probe_launch` and
      `enemy_harvester_trail` rows; `persistent_echoes` for older
      sightings. No `enemy_harvester_drop` rows (§3.15).
    - `world.live / world.echo` — full per-cell tile, purity,
      `square_id`, `lineage`, trails, and entity overlay. Fog is
      summarised by `fog_count` + the existing
      `navigation.fog_clusters` so unexplored regions remain
      addressable.
    - `navigation.best_red_visible / best_red_echo` — sorted by
      value desc with `neighbors_red` and
      `distance_to_my_harvester` for adjacency-rule planning.
    - `my_assets` — every asset the player has ever owned this
      season (orbit / deployed / berthed / destroyed) with lifetime
      stats from the asset ledger.

### v0.6.0 — 2026-05-26

- **Harvester vision expanded to a plus.**
  ``HARVESTER_LOS_RADIUS`` bumped from ``0`` (self-only) to ``1``
  (Euclidean disk → self + 4 cardinals = 5 tiles). Diagonals stay
  in fog. The §3.8 and §3.11 vision blocks are rewritten to match;
  a 5-step traversal now leaves a 3-cell-wide ribbon of historical
  vision along the path.
- **Harvest covers every colour.** The harvester now banks any
  RED, GREEN, or BLUE tile it enters (drop or step). RED converts
  to GREEN as before; **GREEN and BLUE convert to EMPTY** —
  bare ground with only the trail overlay left behind. The old
  "5 RED conversions per Nox" cap is removed; the natural limit
  is now the 6-parcel hold (drop tile + 5 step tiles, §3.9).
  ``HARVEST_CAP`` is deleted from
  [`sea_of_colours/game/policy.py`](sea_of_colours/game/policy.py).
- **Square identities for every colour at world-build.** The
  ``blake2b(seed, x, y, tile_at_generation, purity_at_generation)``
  identity scheme now mints rows for RED, GREEN, *and* BLUE at
  generation time. Every world-build row carries
  ``lineage = 'natural'``.
- **Synthetic-green lineage.** RED → GREEN conversions during
  play mint a **new** synthetic-green identity at the harvested
  ``(x, y)``, tagged ``lineage = 'synthetic'`` and carrying
  provenance (``parent_square_id``, ``generated_by_harvester_id``,
  ``generated_by_owner``, ``generated_on_day``). The closed-out
  RED row is stamped ``harvested_on_day``. GREEN and BLUE harvests
  close out their existing rows but do **not** mint new ones —
  the substance simply transitions from surface into hoard.
- **Vault tier-priority replacement** — new §3.14. Returning to a
  full 50-slot vault triggers a per-parcel cascade with GREEN top,
  RED middle, BLUE bottom. Lowest-tier-incoming-first; RED never
  displaces GREEN; BLUE never displaces RED or GREEN. Jettisoned
  parcels go to outer space (stub for future commerce). Replaces
  the previous silent "hoard cap; spilled parcel …" log line with
  structured displacement entries.
- **§3.9 hold capacity pinned.** Harvester hold is now explicitly
  documented as **6 parcels per outing** (drop + 5 steps). No
  separate per-color cap.
- **§3.4 disposal doctrine extended.** Jettisoning green into outer
  space is added as the same sin as jettisoning into the planet's
  lower orbit. Tolerated without penalty in this iteration (matches
  the §3.14 cascade); future commerce will replace it with a paid
  disposal mechanic.
- **Implementation pointers.**
  Engine: [`sea_of_colours/game/session.py`](sea_of_colours/game/session.py)
  (harvest dispatch, vault cascade);
  ledger: [`sea_of_colours/game/ledger.py`](sea_of_colours/game/ledger.py)
  (``lineage``, ``mint_synthetic_green``, ``mark_harvested``);
  agent view: [`sea_of_colours/snowpark/view.py`](sea_of_colours/snowpark/view.py)
  (``green_tiles[*].lineage``, new ``blue_tiles``, tier-bucketed
  inventory); prompt: [`sea_of_colours/agent/runtime.py`](sea_of_colours/agent/runtime.py)
  (HARD RULES updated for vision/harvest/lineage/vault); agent
  spec: [`snowflake/soc_create_agent.sql`](snowflake/soc_create_agent.sql)
  (mirror of HARD RULES + READING THE DENSE MAP).

### v0.5.0 — 2026-05-26

- **Append-only session persistence.** `init_session` no longer
  wipes prior sessions; CLI / Web / Cortex seasons accumulate as
  separate `SOC_GAME_SESSION` rows. The destructive reset is now
  the explicit opt-in `--wipe-first` flag on
  [`scripts/run_season.py`](scripts/run_season.py). Sessions are
  addressable by either UUID or URL-safe slug (via
  [`sea_of_colours/game/season_names.py`](sea_of_colours/game/season_names.py)).
  Rulebook §5.3 rewritten to match.
- **Harness reframe — orchestrator is now a pre-resolver.**
  `_build_cortex_prompt` in
  [`sea_of_colours/agent/runtime.py`](sea_of_colours/agent/runtime.py)
  inlines the view, inventory, leaderboard, and last 12 log lines
  into the agent's user prompt every turn. The four read tools
  (`soc_get_view` / `soc_get_inventory` / `soc_get_log` /
  `soc_get_leaderboard`) were removed from the Cortex agent spec
  ([`snowflake/soc_create_agent.sql`](snowflake/soc_create_agent.sql));
  the AI agent now exposes only `soc_submit_policy` and
  `soc_save_rationale`. Rulebook §5.5 trimmed + new "Harness layer"
  subsection.
- **Cortex prompt hardening.** The runtime prompt now carries three
  always-present blocks: **HARD RULES** (move grammar, step-is-one-tile,
  per-Nox caps, harvester lifecycle, common mistakes), **HOW TO
  READ THE MAP** (coordinate system, glyph table, worked example),
  and **LAST TURN** (surfaces previous Nox's yellow-error rejected
  moves so the agent learns from prior mistakes). A condensed mirror
  lives in the agent's system prompt
  ([`snowflake/soc_create_agent.sql`](snowflake/soc_create_agent.sql)).
- **Watcher frontend (Phase C)** — new §5.7. `/watch.html?season=<slug>`
  deep-links into a persisted season; a season picker enumerates
  `GET /api/sessions`; the replay scrubber groups consecutive p1+p2
  moves into **simultaneous ticks**; a P1 / P2 / OBS toggle renders
  per-seat fog with player-coloured vision-boundary edges (P1
  sharp blue-white, P2 1px-blur yellow, shared = stacked) in OBS
  mode. Writable controls (`NEW GAME`, ORDERS tab) are hidden via
  `body.cc-mode--watch`.
- **CLI orchestrator** — new §5.8 documenting
  [`scripts/run_season.py`](scripts/run_season.py). Headless seasons
  with `--p1` / `--p2` (heuristic | cortex), `--seed`,
  `--season-name`, `--cortex-agent`, `--backend`, `--wipe-first`.
  Prints watcher + replay URLs in the `SEASON_COMPLETE` block.
- **Header sync.** Bumped from `0.3.8 / 2026-05-20` to `0.5.0 /
  2026-05-26`. The body had drifted three versions ahead of the
  header (v0.4.0 → v0.4.2 landed in the changelog but the top of
  the file was never updated).
- **Known gap flagged.** Universal trails (§3.12) are *not* yet
  surfaced to the AI agent —
  [`sea_of_colours/snowpark/view.py`](sea_of_colours/snowpark/view.py)
  has zero references to `trail`. This is the root cause of the
  "agent walks into now-GREEN tiles chasing a rumour" failure mode
  observed in season `aurora-anchor`. Threading trails into
  `build_agent_view` is the next harness iteration; documented in
  §5.5 so the next change has a clear hook to delete.

### v0.4.2 — 2026-05-21

- **Agents split into RED_HARVEST + AI agents.** The deterministic
  Python heuristic is now named **RED_HARVEST** and is the canonical
  mainstay agent. Snowflake Cortex agents are grouped under
  **AI agents** (registry on
  [`sea_of_colours/agent/runtime.py`](sea_of_colours/agent/runtime.py)
  → `AI_AGENTS`); the first AI agent remains `SOC_RED_REAPER` and is
  selected via `SOC_AGENT_RUNTIME=cortex` (+ optional
  `SOC_CORTEX_AGENT=<name>`). Audit rows, the `/agent/think` envelope,
  and the LOG panel now name whoever actually played
  (`agent_id = "RED_HARVEST"` for heuristic, the Cortex agent's own
  name for AI agents — including a clean fallback to RED_HARVEST if
  Cortex fails). The ORDERS button is now generic
  (`[ >> LET THE AGENT PLAY ]`).

### v0.4.1 — 2026-05-21

- **§3.11.2 Aurora destruction (replaces stranding).** Any harvester left
  on the surface at sunrise is now DESTROYED, not stranded. The unit is
  removed from play, its asset record is stamped with
  ``destroyed_on_day`` + ``destroyed_by = dawn_unrecovered@(x,y)``, and
  its cargo SPILLS (never reaches the hoard). The row surfaces in the
  vault's DESTROYED bucket for the rest of the season. There is no
  repair path in this iteration — losing a harvester to Aurora costs you
  that unit permanently.
- **RED_HARVEST ends every chain with a pickup.** Both
  ``_plan_harvester_chain`` and ``_exploratory_drop`` now append a
  trailing ``pickup`` so the [ LET THE AGENT PLAY ] button never
  self-destructs the harvester (applies to AI agents too — they share
  the same playbook).
- **Agent button no longer no-ops.** The frontend now auto-locks p2
  with an empty queue right after the agent submits for p1, mirroring
  the `[TRANSMIT]` flow so the Nox actually resolves on a single
  click. Static assets serve `Cache-Control: no-cache` so future JS
  edits land without forcing a hard refresh.
- **Per-seat replay percepts.** Replay frames now carry both
  ``cells_player_p1`` and ``cells_player_p2`` (previously only a
  hardcoded p1 snapshot). The Snowflake VARIANT columns finally land
  populated, and ``cells_player`` is preserved as a back-compat alias
  on read for the existing playing UI.
- **`/api/game/latest` is now consistent across backends.** The route
  uses ``store.latest_session()`` (which both InMemorySocStore and
  SnowparkSocStore implement) instead of ``list_sessions()[0]``, fixing
  a divergence where the memory backend returned the oldest session and
  the Snowflake backend returned the newest.
- **Cortex runtime no longer double-submits.** ``run_agent_turn`` skips
  its always-submit when ``SOC_AGENT_RUNTIME=cortex`` (Cortex submits
  via the ``soc_submit_policy`` tool itself). Heuristic fallback fires
  only if the seat is still pending after the Cortex round-trip.

### v0.4.0 — 2026-05-21

- **Snowflake port.** Engine + state now durable in
  `UMAN_SIM_DB.SEA_OF_COLOURS`. FastAPI is a thin proxy; the same
  routes work against either the in-memory store (default) or the live
  Snowflake schema via `SOC_BACKEND=snowflake`. New deliverables:
  [`snowflake/soc_schema.sql`](snowflake/soc_schema.sql),
  [`snowflake/soc_views.sql`](snowflake/soc_views.sql),
  [`snowflake/soc_procedures.sql`](snowflake/soc_procedures.sql), and
  [`scripts/deploy_soc_schema.py`](scripts/deploy_soc_schema.py).
- **Multi-day replay.** `/api/game/{id}/replay` accepts
  `day_from` / `day_to`; new `/api/game/{id}/day-index` powers the
  scrub-bar day dividers and `[« DAY] / [DAY »]` jump buttons in the
  REPLAY panel. Every executed tick is one immutable row in
  `SOC_REPLAY_FRAME`.
- **SOC_RED_REAPER agent.** New Cortex agent
  ([`snowflake/soc_create_agent.sql`](snowflake/soc_create_agent.sql))
  + pure-Python heuristic fallback
  ([`sea_of_colours/agent/`](sea_of_colours/agent/)) — both consume the
  structured agent view payload from `SOC_GET_VIEW`. ORDERS panel gains
  a `[ >> LET SOC_RED_REAPER PLAY ]` button; rationale lands in the LOG
  panel and as a row in `SOC_AGENT_INVOCATION`.
- **Agent view (`SOC_GET_VIEW.agent_view`)** — single JSON structure
  optimised for LLM reasoning: `hud`, `grid_ascii`, pre-aggregated
  `red_tiles` / `green_tiles` / `fog_clusters`, `entities.mine` +
  `entity_detail`, and `recent_log`.

### v0.3.7 — 2026-05-20

- **Circular vision (§3.11).** Probe and harvester line-of-sight switch
  from a Chebyshev square to a **Euclidean disk** of the same radius.
  Constants renamed: ``PROBE_HALF_SPAN`` → ``PROBE_VISION_RADIUS``,
  ``HARVESTER_LOS_CHEB`` → ``HARVESTER_LOS_RADIUS`` (back-compat aliases
  retained). At radius 2 the disk is 13 cells (vs. the previous
  25-cell box) — bump the radius if a House feels blind.
- **Invalid moves no longer burn ticks (§3.10).** The Nox simulator
  walks each player's queue and **skips invalid items** — both
  parse-time malformations (``WasteMove`` markers) and runtime
  rejections (out-of-bounds step, etc.). The next valid item runs in
  the same round; only valid applied moves count against ``MAX_MOVES``.
  Queue length cap raised to ``MAX_QUEUE_LEN`` (100) so agents can
  submit speculative or auto-generated queues freely.
- **Structured log + yellow errors.** ``GameSession.log`` is now a list
  of ``{level: "info" | "error", text: str}`` entries. Errors include
  the attempted action plus the orchestrator's reason and are painted
  **yellow** in the LOG drawer, prefixed with ``[!]``. New helpers
  ``log_info`` / ``log_error`` route through this shape. The HTTP
  ``log_tail`` window grew from 25 → 50 lines so a noisy Nox with
  many skipped items still surfaces useful context.

### v0.3.6 — 2026-05-20

- **Vault re-packed + SHIPPED storage introduced (§3.12).** The VAULT
  drawer now uses a compact 10-column × 5-row grid: each slot shows
  the slot number above the origin glyph, while coordinate, full
  square hash, harvest Nox, and origin purity move to the hover
  tooltip. A second 50-slot storage called **SHIPPED** lives next to
  the VAULT and is wired through the inventory payload + session
  serialization (`shipped_squares`, `SHIPPED_CAPACITY`) but stays
  empty until §4 catapult mechanics land. The HUD tab order becomes
  `[1] ORDERS · [2] INTEL · [3] VAULT · [4] SHIPPED · [5] REPLAY ·
  [6] LOG · [7] GRAPHICS`.

### v0.3.5 — 2026-05-20

- **Trail tiers + permanence (§3.12).** Path trails are now drawn at
  full cell size as block-element shading and **escalate per visit**:
  ``░░`` → ``▒▒`` → ``▓▓`` → ``██`` (Light → Medium → Dark → Full
  Block) so a single look at the map communicates traffic intensity.
  Harvest trails stay binary at ``▒▒`` green. The sparse-hash gating
  is gone — every visited tile is marked. `track_paths` changes shape
  from `Dict[player, Set[xy]]` to `Dict[player, Dict[xy, int]]`;
  `to_dict`/`from_dict` accept the legacy list-of-keys form for
  backward compatibility.

### v0.3.4 — 2026-05-20

- **§3.11.1 Probes persist across Aurora.** Probes used to be retracted
  at sunrise; they now keep watching their 5×5 window every Nox and
  are only destroyed when a harvester (any House) lands or steps onto
  the probe's tile, at which point the echo intel from the last live
  pulse remains in the owner's memory.
- **Player vision edges.** Visible cells now expose a per-side
  ``vedge`` bitfield (``n/e/s/w``) so the client can frame the limit
  of a House's line-of-sight with a thin white inset on the
  outward-facing sides. The convention is documented in §3.11.
- **Vault as inventory.** The VAULT drawer is now a fixed 50-slot
  grid matching the hoard cap. Filled slots render the *origin* tile
  glyph in its origin colours; empty slots are dim numbered
  placeholders.
- **Brighter dim tier.** Foreground / dim / frame colour tokens were
  lifted and the stale (`0.5 → 0.72`), echo (`0.35 → 0.58`), and fog
  (`0.14 → 0.24`) opacity ceilings raised so memory tiles read more
  clearly without losing their "old data" cue.

### v0.3.3 — 2026-05-20

- **§3.12 Square identity, certified harvest, and the Vault** added.
  Every grid cell now carries a deterministic 16-char ``blake2b`` hash
  assigned at generation time and held in a separable ``SquareLedger``
  (`sea_of_colours.game.ledger`) behind a Snowflake-shaped
  ``LedgerStore`` protocol; the in-memory store is the current
  implementation, with the same row shape ready to move to a Snowflake
  table.
- **Auto-harvest on landing.** A harvester now harvests the tile it
  lands on, both for *drop* (orbital lifter) and *step* (adjacent
  move). Each landing consumes one slot from the nightly harvest cap;
  excess RED landings are legal but uncovered.
- **Certified parcels.** Each banked square carries the canonical
  square hash, coordinates, the origin tile/purity, and a precomputed
  ``paint`` triple so the Vault UI can render the harvested square
  visually.
- **Vault drawer.** The Web UI gained a dedicated VAULT panel (keyboard
  shortcut `[3]`) that lists banked squares as visual cards (tile
  swatch + coordinate + truncated hash) — the House's record of
  purchase.
- **Trail density tuned.** Harvest tracks (`∘`) are now drawn at ~8/11
  density, denser than the ~4/11 footstep path (``·``), to surface the
  RED→GREEN conversion residue more clearly.
- **Frontend chrome.** Hovering a cell shows a small floating tooltip
  with its `(x,y)` (plus occupants when present) and outlines the cell
  for the duration of the hover. Entity glyphs are now single
  characters drawn as a centred overlay on the 2-character terrain
  glyph so the grid retains its square footprint while the entity
  reads as a focal mark on top of the tile.

### v0.3.2 — 2026-05-19

- **Web orchestrator MVP:** Added §3.11 documenting fog-of-war, probe LOS,
  harvest→green tile mutation + cargo flags, orbital `pickup` without
  coordinates, and the two-seat JSON policy handshake. Ships with in-process
  `GameSession` + `/api/game/*` routes powering blind player maps vs Graphics
  overlay.

### v0.3.1 — 2026-05-19

- **Red purity (topology):** purity uses Manhattan **depth** to the visible
  seam edge times a ridge term **``(1-f)·t^γ + f·t``** (defaults ``γ=5``,
  ``f=0.28``), capped at **254** when depth ``< red_pure_min_depth``. Core
  **boost** still applies only in deep knots for solid **pure**.

### v0.3 — 2026-05-19

- **Unified purity bands** for red and blue: `0–50`, `51–150`, `151–254`,
  and **255 only** for solid `pure` / `deep`. Rendering (ANSI, Web UI via
  API, PNG) uses only Block Elements in **homogeneous** pairs (`░░`, `▒▒`,
  `▓▓`) plus `██` for void — three dither steps per hue then a solid tier.
- Red tier names are now `trace`, `vein`, `mass`, `pure`; blue bands are
  `shallow`, `mid`, `sink`, `deep`.
- Tile gloss and generator summary in §1.1 and README updated to match.

### v0.2 — 2026-05-19

- Added §0 **Setting**: the discovery of the Red, the Red War, the Red
  Church and the Red Pope, the Houses (Neo-Orsini, Medici-bis,
  GlaxoSmithKline and others), the doctrine that humanity is fallen
  but the Machine is innocent, and the discovery of the new planet
  whose day is lethal.
- Reframed §1 Tiles with in-fiction meaning: `RED` is the Red,
  `GREEN` is poison/sin, `BLUE` is radioactive deposits, `EMPTY` is
  bare ground. Tile data model is unchanged from v0.1.
- Replaced the empty "Game Mechanics — TBD" section with §3 **Tenets**:
  goal (net profit), day/Nox cycle (surface vs orbital phase), Red /
  Green / Blue rules, forbidden actions (direct conflict, impairing
  Red collection, jettisoning green into orbit, putting humans on the
  surface), tolerated underhand tactics (EMPs, command interdiction,
  sabotage, probe blinding), hidden map + probe-based visibility,
  three primary units (Orbital Lifter, Harvester, Probe), and the
  turn structure (day policy authoring → Nox execution → Aurora
  resolution).
- Harvester defined as moving up to **5 tiles per Nox**, collecting
  whatever it enters, and **must be retrieved by a lifter before Aurora
  or it is destroyed**.
- Concrete numbers (capacities, refining yields, catapult bids, EMP
  radii, probe range, quotas, tithes) explicitly deferred to §4
  Mechanics, which remains TBD.

### v0.1 — 2026-05-19

- Initial rulebook. Documents map-generation rules only; game mechanics
  remain TBD.
- World model: row-major grid of `(tile, purity)` cells; tiles
  `EMPTY/GREEN/RED/BLUE`; purity in `[0, 255]`.
- Layer order fixed as `RED → GREEN → BLUE`, later layers overwrite
  earlier ones.
- Red: ridge-transformed fBm, `red_gamma = 6.0` default; 6 concentration
  tiers (`sub-trace, trace, mild, sub-red, red, pure`).
- Green: edge-mask × fBm polar bands at full purity.
- Blue: noise-thresholded pockets + 1 CA smoothing pass by default;
  purity assigned per-pocket as `(1 − cheb_to_peak / ref) ** blue_gamma`
  so **exactly one `deep` cell per pocket**, with `mid` and `shallow`
  rings around it. 3 depth tiers (`shallow, mid, deep`).
- Determinism: single `seed` parameter, with fixed per-layer offsets.
