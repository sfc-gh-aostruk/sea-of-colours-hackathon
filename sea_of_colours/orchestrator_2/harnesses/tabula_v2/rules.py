"""Static RULES block for the tabula phase-1 agent.

Kept as a single Python constant so tweaks to what the agent sees flow
through exactly one file. Everything the agent knows about the game
comes from here plus the per-turn STATE the harness assembles.

Phase 1 intentionally omits: redsign, blue harvesting, hot drops, chain
trimming, chaff, EMP, orbit builds, shipping bids, opponent modelling,
and strategies text. Add those in later phases by extending this string
and the corresponding harness code together.
"""

RULES_SUMMARY = """\
SEA OF COLOURS — HARVEST TRIALS (3-night phase-1 spec)

GOAL: bank as many RED points as possible into your vault over 3 nights.

BOARD:
- 40x28 grid. Persistent across nights: harvested cells become synthetic-green (worthless).
- Fog of war: you only see cells covered by an active probe or by a harvester currently on the surface.

TIME:
- Each night has 21 HOURS.
- Each action (drop / step / pickup / probe) takes exactly ONE HOUR.
- You submit a queue of up to 21 actions; the engine resolves them in the order you list.
- You do NOT need to use all 21 hours. Unused hours are fine.
- Actions across multiple units interleave in the same night — you might drop
  harvester_p1 at hour 1, drop harvester_p1_2 at hour 2, then step both alternately.

TILES:
- RED: score = purity(0..255) × tier_mult
    trace (purity 0-50)    = 0.75
    vein  (purity 51-150)  = 1.0
    mass  (purity 151-254) = 1.5
    pure  (purity 255)     = 3.0   (ONLY 255 exactly is pure — 250 or 254 are still mass!)
    Do NOT relabel tiers yourself. Use the `tier` field the engine gives you
    in the RED cell rows verbatim. One pure(255) = 765 pts. One trace(30) = 22 pts.
- BLUE: do not step on it in phase 1.
- GREEN: hazard. Do not step.
- synthetic_green (sg): a cell you harvested previously. Scores 0. Do not step.

UNITS you control:
- harvester: drops from orbit onto a LIVE-VISION cell, walks a chain of
    Chebyshev-1 steps, then MUST end with PICKUP. If the chain does not end in
    pickup, the harvester is DESTROYED at sunrise and its cargo is lost.
- probe: launches from orbit onto ANY cell (including fog), sits there
    revealing a 4-radius disk for the next 3 nights, then expires.

ACTIONS per unit (planning phase):
  drop(unit, at=[x,y])   Deploy harvester from orbit. Cell MUST be in your
                         live vision right now (inside a probe disk or on a
                         friendly surface unit). Drops into fog or onto
                         echo-only cells are REJECTED by the engine.
  step(unit, to=[x,y])   Move harvester one Chebyshev-1 tile. Harvests the
                         destination tile as part of the step.
  pickup(unit)           Bank the harvester's cargo. MANDATORY at chain end.
  probe(at=[x,y])        Launch a probe from orbit onto any cell (fog OK).

CHAIN GRAMMAR: drop → step* → pickup. Every step harvests one tile.
Chain length up to 6 (drop + 5 steps + pickup = 7 hours per harvester).
With 2 harvesters chaining 7 hours each + 2 probes at 1 hour each, you use
16 of your 21 hours — budget is generous.

CRUSH RULE (tactical choice, NOT a bug):
  Dropping a harvester onto a cell where YOUR OWN probe sits DESTROYS the probe.
  The harvester survives and harvests the tile. You lose the probe's vision of
  that area until you launch another probe. If the cell holds valuable RED,
  the crush is often worthwhile: 765 pts of pure easily outweighs 2-3 nights
  of probe vision. Memory records every crush so you can track lost vision.

PROBE STRATEGY (an hour that pays for 3 nights):
  A probe costs 1 hour and reveals an 81-cell disk for 3 nights. That is a
  cheap information trade — a well-placed probe on day 1 pays dividends on
  days 2 and 3 too. Bad probes waste an hour AND take up a scarce probe slot.

  SETUP NIGHT (day 1 with zero vision — you WILL be told explicitly when
  this happens): every cell is fog, no red is visible, no friendly probes
  or harvesters are on the surface. Drops are IMPOSSIBLE (there is no
  live-vision cell to land on) so the engine will reject any drop/step/
  pickup you submit. The ONLY productive move is probe. Launch 2-3 probes
  in DIFFERENT quadrants — spreading probes uncovers more territory than
  stacking them near each other. Do NOT pass the night with an empty
  moves list; a wasted setup night starves nights 2, 3, and 4 of vision.

  Prefer probes that:
    * Maximize AREA_GAIN — the disk lands mostly on FOG cells, not already-
      visible ones. A probe covering 60 fresh cells is 4x the info of one
      covering 15.
    * Extend from EDGES that already show high-purity red — RED tends to
      appear in seams, so a probe just past a pure/mass cluster's LOS edge
      is likely to reveal more red from the same seam. The prompt scores
      this as EDGE_PROMISE.
    * Target ECHO cells — the engine sometimes surfaces "best_red_echo"
      readings (real red beyond LOS). A probe whose disk covers an echo
      cell is a near-certain reveal of harvestable red.

  Skip probes when:
    * fog_count is 0 (you see everything — an hour better spent stepping).
    * The best candidate has area_gain < ~15 (too much overlap with LOS).
    * You're on the LAST NIGHT and the probe would only surface red the
      next-day-that-never-comes.

  Layered probes: two probes with heavily overlapping disks reveal roughly
  the same disk. Prefer two probes in DIFFERENT regions over stacking.
"""
