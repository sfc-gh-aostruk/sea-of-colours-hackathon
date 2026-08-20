"""Engine MECHANICS the agent must obey.

This module holds only IMMUTABLE facts about the game — what the engine
enforces regardless of strategy. It never contains advisory doctrine
("prefer X over Y"); that lives in :mod:`.strategies`.

Splitting rules from strategies makes it obvious to the agent that:
  * RULES = physics (violate them and the engine rejects the move).
  * STRATEGIES = playbook (helpful patterns, not enforced).

If you find yourself adding "prefer" or "consider" language here, it
belongs in strategies.py instead.
"""

RULES_SUMMARY = """\
SEA OF COLOURS — ENGINE RULES

GOAL: bank as many POINTS as possible into your vault over the season.
      RED = your primary source. BLUE = a secondary source that funds
      weapons and orbital repairs (see BLUE below).

BOARD:
- 40x28 grid. Persistent across nights: harvested cells become synthetic-green (worthless).
- Fog of war: you only see cells covered by an active probe or by a harvester currently on the surface.

TIME:
- Each night has 21 HOURS.
- Each action (drop / step / pickup / probe) takes exactly ONE HOUR.
- You submit a queue of up to 21 actions; the engine resolves them in the order you list.
- You do NOT need to use all 21 hours. Unused hours are fine.
- Actions across multiple units interleave — drop harvester_p1 at hour 1,
  drop harvester_p1_2 at hour 2, then step both alternately.

SIMULTANEOUS RESOLUTION (§3.10):
- Your moves and the opponent's moves resolve TOGETHER at each hour.
- Live-vision is recomputed at the start of every hour, so a probe you
  launch at hour K makes its 4-radius disk visible for your moves at
  hour K+1 (this enables HOT DROP — see strategies).
- If you and the opponent target the SAME cell in the same hour, the
  engine resolves the collision (typically one wins, or both fail).
  Do not assume unopposed access to any cell.

TILES:
- RED: score = purity(0..255) × tier_mult
    trace (purity 0-50)    = 0.75
    vein  (purity 51-150)  = 1.0
    mass  (purity 151-254) = 1.5
    pure  (purity 255)     = 3.0   (ONLY 255 exactly is pure — 250 or 254 are still mass!)
    Do NOT relabel tiers yourself. Use the `tier` field the engine gives you
    in the RED cell rows verbatim. One pure(255) = 765 pts. One trace(30) = 22 pts.
- BLUE: harvestable. Same drop→step→pickup chain grammar as RED. Purity
    scoring differs (blue is banked to a separate blue vault that funds
    weapons + repairs). BLUE cells can be stepped on and picked up like RED.
- GREEN: harvestable but score-negative. Stepping onto GREEN banks a
    green parcel (cell becomes EMPTY). GREEN does NOT destroy the
    harvester — it's a legal step. HOWEVER every green parcel left in
    your hoard at season end costs -100 pts (GREEN_ENDGAME_PENALTY).
    The disposal path is the orbit-phase green catapult (§4.5). If you
    can't catapult (some harness configs stub orbit), AVOID stepping
    on natural GREEN — the parcel will sit in your hoard and cost you.
- synthetic_green (sg): a cell you harvested previously. Scores 0. Do not step
    (wastes an hour without banking anything).

SIGNALS (public information every seat sees — orthogonal to LOS):
- blue_sign: a STATIC map of blue clusters, available from day 1. Each
    cluster has 20-40 cells with per-cell intensity 0.0-1.0. High intensity
    (>=0.6) is near-certain to overlap with a real BLUE cell — but the
    exact purity is RANDOMIZED. You know blue is "somewhere in this
    cluster with dense readings"; you don't know which specific cell has
    purity 30 (trace-blue) vs 200 (rich-blue). Probing or walking onto
    a bright bluesign cell reveals the actual purity.
- redsign: a PUBLIC BROADCAST triggered when ANY seat discovers a
    pure(255) RED cell. Empty on day 1; populates when the season heats
    up. Each broadcast reveals ``(x, y, hour, discoverer)``. Every player
    sees the same broadcast. Racing to a redsign is a legitimate move —
    the cell scores 765 × 3.0 tier_mult = 2295 base pts and whoever
    lands, chains, and picks up first wins it.

UNITS you control:
- harvester: drops from orbit onto a LIVE-VISION cell, walks a chain of
    MANHATTAN-1 steps (N/S/E/W ONLY — NO diagonals), then MUST end with PICKUP. If the chain does not end in
    pickup, the harvester CRASHES at sunrise (see CRASH RULE) — cargo lost,
    stock lost.
- probe: launches from orbit onto ANY cell (including fog), sits there
    revealing a 4-radius disk for the next 3 nights, then expires.

ACTIONS per unit (planning phase):
  drop(unit, at=[x,y])   Deploy harvester from orbit. Cell MUST be in your
                         live vision AT THE HOUR the move applies (inside a
                         probe disk that has already landed, or on a friendly
                         surface unit). Drops into fog are REJECTED.
  step(unit, to=[x,y])   Move harvester one MANHATTAN-1 tile (N/S/E/W only —
                         NO diagonals; the engine's ``_adj`` check requires
                         ``abs(dx) + abs(dy) == 1``). Harvests the
                         destination tile as part of the step.

  WHAT COUNTS AS A LEGAL STEP (concrete):
    From (x,y), the ONLY legal step destinations are the FOUR cells:
        (x+1, y)   — East
        (x-1, y)   — West
        (x,   y+1) — South
        (x,   y-1) — North
    Diagonals like (x+1, y+1) or (x-1, y-1) are ILLEGAL.
    Multi-cell jumps like (x+3, y+2) are ILLEGAL — ``step`` is not
    ``goto``; each step moves one Manhattan-1 tile.

  CONSEQUENCE OF AN ILLEGAL MOVE:
    The engine silently CANCELS the illegal move at that hour and moves
    to the next hour with the harvester's position unchanged. The rest
    of your queue continues to execute. But because a canceled step
    means the harvester is NOT where your subsequent step assumed, the
    NEXT step will also fail (its ``from`` cell is wrong). One bad
    diagonal / teleport step typically cascades into 3-5 canceled hours
    and a crashed harvester at dawn — cargo lost, stock lost.
    ALWAYS emit adjacent-only steps. If you want to travel from (19,12)
    to (16,10), that is FIVE steps, not one: (19,12)→(18,12)→(17,12)
    →(16,12)→(16,11)→(16,10).
  pickup(unit)           Bank the harvester's cargo. MANDATORY at chain end.
  probe(at=[x,y])        Launch a probe from orbit onto any cell (fog OK).

CHAIN GRAMMAR: drop → step* → pickup. Every step harvests one tile.
Chain length up to 6 (drop + 5 steps + pickup = 7 hours per harvester).
With 2 harvesters chaining 7 hours each + 2 probes at 1 hour each, you use
16 of your 21 hours — budget is generous.

CRUSH RULE (tactical choice, NOT a bug):
  Dropping a harvester onto a cell where YOUR OWN probe sits DESTROYS the probe.
  The harvester survives and harvests the tile. You lose the probe's vision of
  that area until you launch another probe. Memory records every crush.

CRASH RULE (harvester lost + stock lost):
  A harvester on the surface at DAWN with no completed pickup CRASHES.
  Consequences:
    * All cargo in that harvester is lost (banks zero).
    * The harvester itself is destroyed — you lose ONE from your fleet.
    * Rebuilding a harvester costs credits during a future orbit phase.
  Other destruction causes (all engine-recorded in ``last_night.my_assets_destroyed``
  with a ``reason`` field — READ it):
    * EMP hit while on the surface, cargo not yet in vault.
    * Chaff-jammed off the pickup hour, then caught at dawn.
    * Enemy harvester collision on the same cell.
  (Stepping onto natural GREEN does NOT destroy the harvester — GREEN is
  a legal harvestable tile. The risk with GREEN is the -100 endgame
  penalty per green parcel left in the hoard, not destruction.)

  Every chain you commit to MUST end with pickup within the same night.
  Never issue a drop you can't finish. Better to drop nothing than to
  drop-then-crash.
"""
