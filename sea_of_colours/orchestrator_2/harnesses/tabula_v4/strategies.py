"""Advisory doctrine — the playbook the agent SHOULD follow.

Strategies are NOT enforced by the engine. This is your best-current-
understanding of how to play well. It's separated from rules.py so the
agent knows exactly which lines are physics (immutable) and which are
patterns (optional).

Adding to this file? Ask yourself: "would the engine accept a move that
violates this?" — if yes, it's a strategy. If no, it's a rule.
"""

STRATEGIES_SUMMARY = """\
STRATEGIES (playbook — advisory, not enforced by the engine)

PROBE STRATEGY (nomadic discovery — advance the frontier, don't camp):
  You are a nomad. Each probe is a step forward into UNEXPLORED fog.
  A probe costs 1 hour and reveals an 81-cell disk for 3 nights. Its
  purpose is to surface NEXT NIGHT'S harvest target — never to maintain
  vision over ground you've already worked.

  PROBING MANDATE:
    If probe_stock >= 2 AND fog_count > 300 → launch AT LEAST 2 probes.
    If probe_stock >= 1 AND fog_count > 150 → launch AT LEAST 1 probe.
    Different quadrants — layered disks reveal duplicate ground.

  THE NOMADIC CYCLE:
    1. Probe forward into fresh fog.
    2. Next night, harvest the best red the probe revealed.
    3. SAME night, launch a NEW probe further forward — into a different
       quadrant or deeper into the same seam if unexplored fog remains.
    4. Repeat. You are RANGING across the map.

  DEFAULT RULE — probes go into UNEXPLORED fog ONLY.
    A candidate is worth probing if its disk mostly covers cells you
    have NEVER surfaced. If the disk overlaps heavily with:
      * synthetic-green (cells you've already harvested — DEAD value),
      * red you've already chained through (also synthetic-green now),
      * territory a friendly probe recently expired over (already known),
    then it is a WASTED probe. Choose a different candidate.

  THE ONE LEGITIMATE EXCEPTION — RECOVERY RE-PROBE:
    You may re-probe an already-visited area ONLY when your initial
    probe was DESTROYED by opponent action (EMP, probe crush, chaff)
    BEFORE you got a harvester onto its revealed cells. This is the
    "the enemy stole my intel" case, not "I want vision insurance."

    Detection: read LAST NIGHT — my_assets_destroyed. If you see
    ``probe_p1_N reason=emp_pX`` AND you never landed a harvester in
    that probe's disk, that area is a legitimate recovery re-probe.
    Otherwise: NO re-probing. Move the frontier.

  SETUP NIGHT (day 1 with zero vision — you WILL be told explicitly when
  it happens): every cell is fog, no red is visible, no friendly probes
  or harvesters are on the surface. Drops are IMPOSSIBLE (there is no
  live-vision cell to land on) so the engine will reject any drop/step/
  pickup you submit. The ONLY productive move is probe. Launch 2-3 probes
  in DIFFERENT quadrants — spreading probes uncovers more territory than
  stacking them near each other. Do NOT pass the night with an empty
  moves list; a wasted setup night starves nights 2, 3, and 4 of vision.

  Prefer probes that:
    * Maximize AREA_GAIN — the disk lands mostly on FOG cells, not
      already-visible ones. 60 fresh cells is 4x the info of 15.
    * Extend from EDGES that already show high-purity red — RED tends
      to appear in seams, so a probe just past a pure/mass cluster's
      LOS edge is likely to reveal more red from the same seam
      (EDGE_PROMISE in the hints block).
    * Push into a different QUADRANT from tonight's chain — this is the
      nomadic principle: harvester is here now, probes prepare there.
    * Target public SIGNALS (bluesign, redsign) that point at rich
      territory you haven't yet reached.

  Skip probes when:
    * fog_count is 0 (you see everything — an hour is better spent
      stepping).
    * The best candidate has area_gain < ~15 (too much overlap with LOS,
      i.e. that disk is mostly already-known ground → you're camping).
    * You are on the FINAL night and the probe would only surface red
      the next-day-that-never-comes. (Hot drops on the final night
      still work because the reveal + drop resolve in the SAME night.)

  Layered probes: two probes with heavily overlapping disks reveal
  roughly the same territory. Prefer two probes in DIFFERENT regions
  over stacking them near each other. Nomad ranges the map; nomad
  does not double-cover.


HOT DROP (probe + harvest in the SAME night — signal-driven):
  Because live-vision refreshes each hour, you can:
    hour K:   probe(at=[x,y])   → the disk becomes live-vision
    hour K+1: drop(harvester, at=[x',y']) where (x',y') is inside the disk
  Then step 1-3 more to grab neighbors and pickup.

  Hot drop is DRIVEN BY PUBLIC SIGNALS. The engine broadcasts two:

  * REDSIGN — when ANY seat discovers a pure(255) RED cell, the engine
    publishes the coord to every player. That cell scores 765 pts × 3.0
    tier_mult = 2295 base pts. Whoever probes+drops+picks first wins it.
    ALWAYS take a redsign hot drop unless your existing chain scores
    equivalent-or-better. Race the opponent.

  * BLUE_SIGN — a public STATIC map of blue clusters visible from day 1.
    Each cluster contains 20-40 cells with per-cell intensity 0-1. Bright
    cells (>=0.6) are near-certain to have real BLUE nearby — but the
    exact purity is randomized. Somewhere in the cluster there IS a
    high-density blue vein; you just don't know which cell. Correct
    play: probe the brightest cell, drop-and-crawl 1-3 steps sampling
    neighbors, pickup. Some drops land on trace-purity blue (banks
    little). Others hit dense blue and bank a lot. Expected value is
    good.

  SETUP NIGHT special case: bluesign hot drop is a legitimate night-1
  move even with zero vision. The bluesign map is available from day 1
  and dropping into a bright cluster is often better than pure blind
  probing — you're gambling on known-blue territory rather than
  gambling on empty fog. On night 1 with only 1 harvester, consider:
  probe(bright bluesign) + drop-and-crawl on that same cluster. Two
  probes elsewhere is also fine; pick based on the wishlist.

  When NOT to hot drop:
    * You already have >=3 blue cells in LOS — a known-blue chain
      beats a bluesign gamble. The engine's HOT DROP HINTS block
      already suppresses bluesign entries in this case.
    * On the FINAL night, if the probe's payoff would only be visible
      the next-day-that-never-comes. (Hot drops still work on the
      final night for the SAME-night bank; they're only bad when the
      value is deferred.)


BLUE HARVEST (secondary priority — funds orbit):
  Blue banks to a separate BLUE vault that pays for weapons and orbital
  repairs. When your BLUE VAULT is empty and you have 2+ harvesters,
  the orbit turn will pass a ``grab_blue`` wishlist entry telling you to
  send one harvester to blue if there is no pressing RED chain.

  Rules of thumb:
    * "Spare harvester" = a harvester whose best available RED chain
      would score < ~400 pts. That harvester is a candidate for blue.
    * If a RED chain worth >600 pts is available, take it with that
      harvester. Blue can wait.
    * If your best RED chain is trace-only (score < 300), and blue is
      visible with purity > 100 OR a bright bluesign is in reach,
      prefer blue with that "spare" harvester.
    * Blue plays with the SAME drop→step→pickup grammar as red. Same
      crash rule applies.


OPPONENT AWARENESS (§3.15):
  You can see:
    * ``competitor_intel.new_this_day`` — enemy actions the engine
      revealed this hour (probe launches you were adjacent to, drops
      inside your LOS, EMPs targeting you).
    * ``station_intel.opponents`` — public opponent totals (blue/green
      banked, harvesters recovered, weapons fired).
    * NOT visible: opponent's probe positions in fog, opponent's exact
      queue.

  Use it to:
    * Anticipate collisions. If enemy dropped near your cluster last
      night, they may be back tonight.
    * Prioritize red the opponent hasn't seen. Purity data is public
      the moment a cell is in ANY player's LOS.
    * Skip contested cells when the ROI is marginal.


CRASH PREVENTION (never lose a harvester):
  Every drop is a commitment to a pickup THIS NIGHT. If you write a
  chain of 6 steps and only submit 5 hours' worth, the harvester
  crashes at dawn. Rebuilding takes credits and a whole orbit turn.

  Before submitting a chain, count:
    hours_used = 1 (drop) + len(step_moves) + 1 (pickup)
  If hours_used > (21 minus other actions), the chain is too long. Trim.

  When last_night.my_assets_destroyed is non-empty, READ the reasons
  and update your plan. If a harvester died to EMP last night, the
  opponent knows your positions — vary your drops.

  OPPONENT-CONTESTED AREAS — the SHORT-CHAIN pattern:
    Every hour a harvester spends ON THE SURFACE is exposure time.
    Enemy EMPs can destroy it. Enemy chaff can jam its pickup. Enemy
    harvesters can crush your probes and race you off pickups. Time
    on surface = risk.

    When ``competitor_intel.new_this_day`` shows enemy probe launches or
    drops near an area you want to harvest, you have three options:

    (a) SKIP the area. If the chain was going to score < 400 pts and
        risk crash, the safer expected value is to harvest elsewhere
        or use the hour on a probe for tomorrow.

    (b) SHORT-CHAIN — go in, grab 1-2 juicy cells, pickup, exit.
        A 3-hour or 4-hour chain (drop + 1-2 steps + pickup) banks
        the highest-value cell(s) and minimizes time on surface. Yes,
        you leave points on the board. Better to bank 400 pts safely
        than gamble 900 pts and crash. No shame in short-chaining.

    (c) GO EARLY — drop at hour 1 with a well-planned short chain
        and pickup at hour 3 or 4, BEFORE enemy chaff/EMP can catch
        you. Beats an hour-8 drop that runs into an hour-12 EMP salvo.

    The doctrine: MINIMIZE time on surface when contested. 6-cell
    chains are for uncontested territory. 2-3 cell chains are the
    default when the opponent's fingerprint is nearby.
"""


# ─────────────────────────────────────────────────────────────────────────
# CONDITIONAL DOCTRINE — appended to the prompt only when the relevant
# opponent-weapon estimate flags a non-zero max. Kept as separate module
# constants so ``prompt.build_prompt`` can gate each snippet independently
# based on the WeaponEstimate the opponent_weapons tracker produces.
#
# The static ``STRATEGIES_SUMMARY`` above stays weapon-agnostic — no need
# to burn prompt tokens on EMP mitigations when no opponent has EMP stock.
# ─────────────────────────────────────────────────────────────────────────


DOCTRINE_BEWARE_EMP = """\
OPPONENT WEAPONS — beware_emp (P1: vision + landing denial):
  What EMP actually does:
    * EMP is used for VISION DENIAL and LANDING DENIAL. It is RARELY
      aimed at a moving harvester — random hits are unlikely.
    * Manhattan-r2 blast (13 cells per missile × 3 missiles per launch).
      Inside the blast: probes and mines are DESTROYED; harvesters are
      DISABLED for 8 hours (or the rest of the night).
    * CRITICAL RULE: an EMP'd harvester RETAINS its haul and can still
      be picked up. Being EMP'd is NOT death — only a dawn crash kills
      the harvester and its cargo. If you banked cells before the EMP,
      those parcels come home when the harvester is picked up.
    * Opponent's most likely target: YOUR LATEST launched probe — a
      blind-fire stall to deny your next-night landing.
    * Second most likely target: an area of dense red the opponent
      wants to harvest themselves — EMP shields it from you for 8h,
      then they land in the cleared window.

  Two mitigation flavors based on what's on the board:

  FLAVOR A — REDSIGN fired (pure red is public, everyone is coming):
    Assume EMP will be aimed at the pure area around hour 3-8.
    * HOUR-1 DROP: race to bank pure before EMP fires. Drop at hour 1,
      chain to grab just the pure + 1-2 adjacent juicy cells, pickup
      by hour 4. Short chain = short exposure.
    * OR HOUR-9+ DROP: probe fresh at hour 8, drop at hour 9 — the
      8-hour EMP window from an hour-1 fire has closed. Second-wave.
    * OR TWO HARVESTERS in tandem:
        - One at hour 1 to snatch the pure before EMP resolves.
        - One at hour 10+ as backup wave.
      SUPPORT BOTH with a SECOND probe positioned OUTSIDE the primary
      probe's Manhattan-r2 blast area (offset above/below). If the
      primary probe is EMP'd, the backup keeps the target cell in
      live-vision so you can still drop legally.

  FLAVOR B — no pure on the board (opponent will blind-fire at probes):
    Opponent's EMP is most likely aimed at your LATEST probe to stall
    you a turn.
    * SUPPORT every harvest with a second probe outside the primary
      probe's Manhattan-r2 blast area. If primary is EMP'd, backup
      keeps you legal.
    * If chaining, AVOID the primary probe's exact cell — that's their
      most likely aim point.
    * BUT if the primary probe's disk contains the best red on the
      board, DROP DIRECTLY on it at hour 1 — no time for opponent to
      react. Speed beats stealth.

  Universal: SHORTEN CHAINS when beware_emp fires. Grab only the
  exact high-scoring parcels, not full 6-cell chains. Faster in,
  faster out, less time on surface.
"""


DOCTRINE_BEWARE_CHAFF = """\
OPPONENT WEAPONS — beware_chaff (P2: pickup-killer, avoid predictable windows):
  What chaff actually does:
    * Chaff cancels all OTHER seats' actions for 3 CONSECUTIVE hours
      (CHAFF_DURATION_HOURS = 3). The triggerer's own actions still
      resolve; only opponents lose the window.
    * If your PICKUP falls in a chaffed hour, the pickup is cancelled.
      Harvester stays on the surface, and if the chaff window straddles
      your last legal pickup hour of the night → dawn crash + haul lost.

  Mitigation — avoid PREDICTABLE pickup windows:
    Chaff is BLIND-fired at hours where opponents most naturally pickup.
    Two natural windows to AVOID:
      * HOUR 6-9   — the "drop at 1, walk 5, pickup at 7" pattern.
      * HOUR 12-16 — the "mid-night drop, mid-night pickup" pattern.
    Both are prime chaff targets. Move OUT of these windows:
      * Pickup at hour <= 4 (very early — before enemy has read field)
      * Pickup at hour >= 19 (very late — enemy has less incentive to
        burn chaff on a near-empty night)
      * Short chain (drop -> 1-2 steps -> pickup at hour 3 or 4) is
        the strongest chaff-hedge — you're gone before the natural
        chaff window opens.

  CRITICAL RULE — SPACE MULTI-HARVESTER PICKUPS >= 3 HOURS APART:
    Chaff kills a 3-hour window. If you schedule two harvesters to
    pickup within 3 hours of each other, ONE chaff can cancel BOTH
    -> double dawn crash -> catastrophic loss. Space your pickups so
    no two land within a 3-hour span:
      * harvester_p1 pickup at hour 4, harvester_p1_2 pickup at hour 8
        -> 4-hour gap, chaff can only catch one.
      * NEVER: harvester_p1 pickup at hour 4, harvester_p1_2 pickup
        at hour 5 -> one chaff at hour 4 kills both.

  Universal: SHORTEN CHAINS when beware_chaff fires. Shorter chains
  = earlier pickup = smaller window for chaff to catch you.
"""
