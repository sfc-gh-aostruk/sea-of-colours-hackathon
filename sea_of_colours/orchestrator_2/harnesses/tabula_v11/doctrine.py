"""Advisory doctrine — the playbook the agent SHOULD follow (tabula_v11 fork).

v10 keeps the frozen v7 core doctrine (imported verbatim) and rewrites the
redsign-poker book into a clear TWO-CASE, WEAPON-FREE playbook that branches
on the new engine-truth ``redsign.mine`` flag (Workstream E). It also keeps
v8's weapons-as-orbital-strike reframe and adds a short COMPREHENSION note
that points the agent at the new WHAT-HAPPENED digest.

Split (kept strict):
  * MECHANICS (immutable engine physics) live in :mod:`.rules`.
  * PLAYBOOK (advice) lives HERE, gated by ``prompt.build_prompt`` on live
    state so haiku never burns attention on doctrine it cannot act on tonight.

Carried over from v7 (unchanged): STRATEGIES_CORE, DOCTRINE_BLUE,
DOCTRINE_REDSIGN, DOCTRINE_LASTDAY_SUPERSEDE, DOCTRINE_BEWARE_EMP,
DOCTRINE_BEWARE_CHAFF.

New / rewritten in v10:
  * DOCTRINE_REDSIGN_POKER — the two-case weapon-free opening book (my-redsign
    vs not-mine), the user's hot-drop poker.
  * DOCTRINE_WEAPONS_ORBITAL — EMP/chaff reframed as targeted orbital strikes.
  * DOCTRINE_COMPREHENSION — read the attributed WHAT HAPPENED digest and act.
"""

from __future__ import annotations

# Re-export the frozen v7 doctrine so v10 owns one doctrine surface.
from sea_of_colours.orchestrator_2.harnesses.tabula_v7.strategies import (  # noqa: F401
    STRATEGIES_CORE as _V7_STRATEGIES_CORE,
    DOCTRINE_BLUE,
    DOCTRINE_REDSIGN as _V7_DOCTRINE_REDSIGN,
    DOCTRINE_LASTDAY_SUPERSEDE,
    DOCTRINE_BEWARE_EMP,
    DOCTRINE_BEWARE_CHAFF,
)

# SCORING CORRECTION (v10 hermetic fix — hyg-scoring). A pure(255) is
# 255 × 3.0 = 765 base pts, NOT 2295 (the frozen v7 text double-counts the tier
# multiplier). Correct the two v7 strategy strings for v10 ONLY; v7/v8 baselines
# stay frozen. See tabula_v11/rules.py for the engine reference.
STRATEGIES_CORE = _V7_STRATEGIES_CORE.replace(
    "A pure(255) cell is 2295 base pts and usually overrides a normal chain",
    "A pure(255) cell is 765 base pts (the biggest single cell; the surrounding "
    "SEAM adds more) and usually overrides a normal chain",
)
# CONTESTED-JACKPOT EXCEPTION (v10 — hyg-contradictions). The frozen v7
# "MAXIMIZE THE CHAIN / go short only for a real reason" line teaches the agent
# to WALK long every time and frames an early pickup as wasted hours. That is
# right for ORDINARY red but WRONG for a contested jackpot: dropping on a
# pure(255)/redsign already banks it (auto-harvest, parcel #1), so the job is to
# SECURE it, not to ride it around the seam. Name the exception loudly.
STRATEGIES_CORE = STRATEGIES_CORE.replace(
    "Go SHORT only for a real reason (see below).",
    "Go SHORT only for a real reason (see below) — and a CONTESTED JACKPOT is "
    "the biggest one. When you drop ON a pure(255)/redsign you ALREADY banked it "
    "as parcel #1 (auto-harvest), so SECURE it: pick up within 1-2 hours (0 "
    "extra steps under chaff/EMP/contest, 1-2 only when clearly safe). Do NOT "
    "ride a long chain over a jackpot — a crash/chaff/collision on the walk "
    "spills the whole load, and that risk beats the few extra harvest-hours. "
    "Strip the wider seam with a SEPARATE harvester or a LATER wave, never the "
    "grabbing unit.",
)
# MENU-AS-SOURCE-OF-TRUTH (v11 menu rebuild). The frozen v7 PER-TURN PROCEDURE
# points the agent at standalone CHAIN/HOT-DROP/PROBE HINT blocks and tells it to
# compute EV itself. v11 retired those blocks: the OPTION MENU now carries every
# play's walk, yield, crushes, and collision risk. Rewrite steps 1-2 to point at
# the menu (and drop the "hints carry no scores" line, which is now false).
STRATEGIES_CORE = STRATEGIES_CORE.replace(
    "  1. ENUMERATE opportunities: visible RED chains (CHAIN HINTS), hot-drop\n"
    "     combos (HOT DROP HINTS), any REDSIGN race, and fog worth probing\n"
    "     (PROBE HINTS). The HINT blocks below are your candidate menu.\n"
    "  2. SCORE each with the tier table in RULES (purity x tier_mult). You\n"
    "     compute EV yourself; the hints carry no scores.",
    "  1. ENUMERATE opportunities from the OPTION MENU below — the single source\n"
    "     of truth. It lists every play (grabs, redsign patterns, hot drops,\n"
    "     probes, juice chains) with its walk, expected yield (red/blue/green),\n"
    "     crushes, and collision risk already computed for you.\n"
    "  2. COMPARE them on what the menu shows; prefer high yield at low collision\n"
    "     risk with no self-crush. You do NOT recompute EV or reconstruct the\n"
    "     geometry — the menu already carries it.",
)
# AGENT-OWNED TAIL TRIM (v11). The packager compiles the chain you pick VERBATIM
# (minus the hard hazards: chaff window, known-green, contested blind-walk); it
# does NOT shorten a walk for value/exposure reasons — that judgement is YOURS.
# So trim your own tails: when a chain's trailing steps are low-value AND the menu
# flags them under enemy vision, pick the SHORT variant or ``avoid`` those cells.
STRATEGIES_CORE = STRATEGIES_CORE.replace(
    "     geometry — the menu already carries it.",
    "     geometry — the menu already carries it.\n"
    "  2b. TRIM YOUR OWN TAILS (the compiler will NOT do it for you): when a\n"
    "     chain's TRAILING steps are low-value (trace red / fog / already-green)\n"
    "     AND the menu marks them under enemy vision (collision risk MED/HIGH),\n"
    "     take the SHORT variant or put those tail cells in `avoid` — secure the\n"
    "     rich head and lift early. Keep the full walk only when the tail's own\n"
    "     mass/pure/blue yield is worth the exposure.",
)
STRATEGIES_CORE = STRATEGIES_CORE.replace(
    "the HOT DROP HINTS give a crush-safe",
    "the HOT DROP options in the menu give a crush-safe",
)
DOCTRINE_REDSIGN = _V7_DOCTRINE_REDSIGN.replace(
    "cell scores 765 x 3.0 = 2295 base pts and pure runs in SEAMS, so the",
    "cell scores 255 x 3.0 = 765 base pts and pure runs in SEAMS, so the",
)
assert "2295" not in STRATEGIES_CORE + DOCTRINE_REDSIGN, (
    "v10 scoring correction failed to apply"
)


# ─────────────────────────────────────────────────────────────────────────
# COMPREHENSION — read the causal digest before you plan
# ─────────────────────────────────────────────────────────────────────────
DOCTRINE_COMPREHENSION = """\
UNDERSTAND LAST NIGHT BEFORE YOU MOVE (see WHAT HAPPENED):
  A bad night has a CAUSE. Before planning, read the WHAT HAPPENED digest and
  name it: who did what to you, and what it cost.
    * A probe of yours destroyed (superseded or collided) means you LOST that
      disk's VISION — any hot-drop that relied on it had no live sensor and
      banked nothing. Do not re-plan a drop into a disk you no longer own.
    * An EMP hit means your harvester was DISABLED in those hours; a pickup
      you scheduled then did NOT happen (dawn-crash risk). Re-time it.
    * A chaff jam CANCELLED your action slots in those hours. Nothing you
      queued then ran.
    * A harvester collision banked ZERO and the cargo was LOST (not held).
  If you denied an opponent (BY YOU), press it: a blinded rival cannot drop
  into that disk next hour. Set your reflection/gap_reason to the REAL cause,
  never "held in hoard" for cargo that was lost.
"""


# ─────────────────────────────────────────────────────────────────────────
# REDSIGN POKER — the two-case, WEAPON-FREE hot-drop book
# ─────────────────────────────────────────────────────────────────────────
DOCTRINE_REDSIGN_POKER = """\
REDSIGN POKER (no weapons in play) — a public pure-RED beacon is a HONEYPOT:
  Everyone sees the SAME advertised cell, so everyone dives it and two drops
  on one cell in one hour COLLIDE (both damaged, both bank ZERO). The pure
  runs in a SEAM, so the points are in the cells AROUND the beacon. The game is
  ALWAYS Hawk — but SMART hawk: there are many cells to go down, so fan out and
  hit the seam from waves and angles rather than stacking the one lit cell.

  YOU CHOOSE THE PLAY. The OPTION MENU has pre-built, named seam PATTERNS with
  the geometry already filled in. Read the ONE question — is this MY redsign
  (engine-truth ``mine`` flag / OWNERSHIP line) — then put the pattern IDs you
  want, IN EXECUTION ORDER, into your "plan". You are selecting and ordering,
  not inventing coordinates.

  ============================================================
  CASE 1 — IT IS YOUR REDSIGN (mine=true; you know the pure cell):
  ============================================================
  HOW you take the pure depends on whether you can DROP on it right now. The menu
  shows ONE of two own-seam trios — pick whichever IDs it actually lists.

  WHY GO EARLY — BANK THE PURE BEFORE THEY DENY IT. The redsign is PUBLIC (§3.15):
  EVERY rival sees this pure and is racing you to it. Within an hour or two they
  will SUPERSEDE the probe that lights it (blinding you), blind-walk onto it, or
  COLLIDE on the cell — any of which costs you the crown jewel. So take it EARLY
  and pick up FAST. "No enemy vision RIGHT NOW" is a trap — a public pure DRAWS
  contest, so a safe-looking hour you waste is the hour a rival arrives.

  TWO WAYS TO TAKE IT — A REAL CHOICE, NOT A RULE. The menu offers BOTH; weigh
  them yourself:
    * SMASH_GRAB (the SURE play) — land STRAIGHT on the pure, it auto-harvests,
      lift in one hour. EMP-proof and collision-proof on the grab itself: you bank
      the jackpot (~765) for CERTAIN, and leave the rest of the seam.
    * FULL_SWEEP (the GAMBLE) — ride the WHOLE visible seam in ONE outing (its
      pures + the mass ring): FAR more points, but ONE harvester means a
      chaff/EMP/collision ANYWHERE on the walk spills the WHOLE unlifted load, the
      pure included. It is a genuine gamble, and the odds get WORSE with (a) MORE
      players racing the same public seam and (b) LATER in the season (more weapons
      banked, tighter contest). Offset that against the sheer value: EARLY, few
      rivals, quiet board -> the sweep's extra pures are usually worth it;
      CROWDED, LATE, or weapons about -> take the sure SMASH_GRAB.
  With TWO harvesters you do NOT have to choose: SMASH_GRAB with H1 to lock the
  jackpot, then SECURE_MASS / LATE_SWEEP with H2/H3 to bank the ring safely (a
  crash on those later waves costs only ring mass, never the pure).

  BECAUSE THE PURE IS BANKED, THE RING IS LOW-STAKES. Once H1 has locked the
  jackpot you can work the surrounding mass FREELY — with a SEPARATE harvester on
  its OWN later wave (a DIFFERENT hour block), each backed by its own probe. A ring
  wave that crashes or gets jammed only costs ring mass, never the pure — that is
  the whole reason you secured it first. So the 2nd/3rd harvester can be greedier
  and range wider than the grabbing unit ever should.

  (1a) PURE IS DROP-LEGAL NOW (a live probe disk covers it) — the SMASH trio, plus
  FULL_SWEEP as the greedy H1 alternative:
    plan = ["SMASH_GRAB", "SECURE_MASS", "LATE_SWEEP"]   # sure grab + ring waves
       or  ["FULL_SWEEP"]                                # one-harvester seam gamble
    * SMASH_GRAB (H1) — the GRAB is the DROP. Land ON the pure — it auto-harvests,
      so the jackpot banks as parcel #1 the instant you touch down. Drop STRAIGHT
      (no probe). PICK UP FAST — 0 extra steps under chaff/EMP/contest, 1-2 only
      when clearly safe. A direct smash is EMP-PROOF (it resolves in one hour).
      The SURE grab.
    * FULL_SWEEP (H1 — the ALTERNATIVE to SMASH_GRAB, same harvester) — instead of
      lifting after the pure, ride the whole visible seam and bank its pures + mass
      in one walk. Do NOT pick BOTH FULL_SWEEP and SMASH_GRAB — they are the same
      unit; choose FULL_SWEEP when the value outweighs the risk (see the gamble
      note above), SMASH_GRAB when you must be sure of the jackpot.
    * SECURE_MASS (H2) — a SECOND harvester, on its OWN wave at a LATER hour block
      and backed by its own probe, strips the MASS ring around the pure (most of a
      seam's points live in the ring, not the single lit cell). The jackpot is
      already banked, so this unit can be GREEDIER than the grabber — a crash here
      costs ring mass, never the pure.
    * LATE_SWEEP (H3) — a THIRD harvester, later still, bigger pattern from a new
      bearing over the dense seam.

  (1b) PURE IS FOGGED/ECHO BUT WALKABLE (no probe needed) — the WALK-IN trio:
    plan = ["WALKIN_GRAB", "WALKIN_SECURE", "WALKIN_LATE"]
    The pure is yours but sits outside a live probe disk. Only the initial DROP
    needs live coverage — STEPS do not — so you land on the nearest live frontier
    cell and WALK straight onto the pure. No probe required.
    * WALKIN_GRAB (H1) — drop on the live frontier, walk the fog steps onto your
      pure, grab, pick up FAST.
    * WALKIN_SECURE — CRUCIAL: a walk-in is NOT EMP-proof (it spans hours, so an
      EMP can jam the steps). The pure is too valuable to trust to one chain, so
      a SECOND harvester DOUBLE-WALKS the same pure from a different frontier: if
      H1 was jammed this still banks the jackpot; if H1 landed, re-hitting takes a
      green — worth it to be SURE. It then walks on into the surrounding mass.
    * WALKIN_LATE — a THIRD, staggered walk-in that takes the pure then sweeps the
      mass halo around it.
    Default on a rich own seam under walk-in: take WALKIN_GRAB + WALKIN_SECURE at
    minimum (double-walk the jackpot); add WALKIN_LATE with a third harvester.

  If the menu shows NEITHER own-seam trio, your pure is fogged, unwalkable, and
  you hold no probe this night — it is simply unreachable. Do not force it: spend
  the fleet on a CHAIN (CHn) / HOT DROP / rival beacon, and buy a probe next orbit
  if you want the seam tomorrow.
  Deploy every harvester you have. Add a PROBE (PRn) for any spare probe once the
  pure is secured.

  ============================================================
  CASE 2 — IT IS NOT YOUR REDSIGN (mine=false; a rival found it) — ATTACK it:
  ============================================================
  DEFAULT POSTURE: ATTACK. A redsign is nearly always exactly ONE night old — a
  frontier probe trips it, and the finder usually cannot harvest it until the
  NEXT day — so the pure is very likely STILL THERE, and the seam is MASS-RICH.
  That means a blind drop is +EV even when it MISSES the pure: a hit is a double
  win (huge points + huge denial), and a miss still banks the surrounding
  vein/mass. So do NOT default to sitting back — the timid confirm-only play is
  what throws these away. The menu shows two things at once:

  2a. FOGGED to you (no live probe of yours on the seam) — the USUAL case. The
      menu now offers a BLIND ATTACK (plus CONTEST_DENY, demoted, below). Scale
      the attack to your FLEET — this is the whole decision:
        * 0 probes → you CANNOT land on a fogged seam. Skip it; farm red you can
          SEE and buy a probe for tomorrow.
        * 1 probe, 1 harvester → BLIND_GRAB: drop a covering probe (ON the
          finder to blind them when you can), blind-drop on the best smear guess
          and BLIND-WALK ~5 cells across the mass-rich seam, then pick up fast.
        * 1 probe, 2 harvesters → BLIND_GRAB with H1; send H2 ELSEWHERE (a chain
          / your own seam). Do NOT stack the second harvester behind one lone
          probe on a contested seam — spread the risk.
        * 2 probes, 2 harvesters → the TWO-BEARING attack: BLIND_GRAB (H1 blinds
          the finder + combs one sector) AND UNBEATEN_FLANK (H2 brings its OWN
          probe and combs a DIFFERENT sector from the opposite bearing). One is
          likely contested; the other banks.
      The accepted risk is FOG, never a KNOWN penalty — the compiler still
      refuses any drop/step onto a cell you KNOW is stripped/green.

      CONTEST_DENY (DEMOTED — the "ahead / want-certainty" alternative): supersede
      the finder + drop a probe to confirm the pure, commit NO harvester, and
      SMASH it for real tomorrow. Prefer this over a blind attack only when you
      are AHEAD (protect the lead, take the sure denial) or you specifically want
      certainty before spending a harvester. It is denial without the fog gamble
      — but it banks nothing tonight, so it is the cautious pick, not the default.

  2b. LIVE-confirmed (a live probe of yours already reveals red on the seam) —
      the menu shows the aggressive trio. Now you KNOW where the value is, so
      contest hard. Typical plan, in order:
    plan = ["BLIND_GRAB", "UNBEATEN_FLANK", "WALK_IN"]
    * BLIND_GRAB — blind the finder (land your probe ON theirs to supersede it),
      then a blind drop and a SHORT SWEEP. KEY DIFFERENCE FROM SMASH_GRAB: here
      you do NOT know the exact pure — the broadcast is a jittered smear, so one
      guessed drop cell rarely IS the pure. Comb across the top candidates (not
      zero — a single-cell blind grab usually banks trace for nothing), then pick
      up. Poker note: if they drop in hour K it STILL lands (vision snapshots at
      hour-start); your supersede only denies them from K+1. Try it anyway — the
      sweep banks nearby red and denies.
    * UNBEATEN_FLANK — the SECURED bank: a fresh probe on the OPPOSITE axis
      reaches the same seam from an uncontested angle after the EMP window. This
      is the wave nobody is fighting for; make it your reliable pickup.
    * WALK_IN — late outer mop-up from a THIRD bearing: pure red bleeds into
      good red, so you scoop the halo even if the pure itself is contested (and
      you keep great vision for tomorrow).
  If a wave 1 crash means NOBODY banked the pure, that is fine: the pure tile
  SURVIVES a collision. Come again next wave / next night from a new angle.

  THE ONE OPPORTUNITY-COST CAVEAT: if you ALREADY see a significant CONFIRMED
  chain (visible mass and/or a pure you can reach — a strong GRAB or a ≥150 JUICE
  CHAIN), take THAT first: a bird in the hand beats a fogged gamble. But do not
  just walk away from the redsign — spend a spare PROBE to light it (a
  CONTEST_DENY or a plain probe on the beacon) so you SEE it and strike for real
  NEXT night. Bank the sure value now, set up the redsign kill for tomorrow.

  ============================================================
  CASE 3 — TWO REDSIGNS AT ONCE (one MINE + one a RIVAL's):
  ============================================================
  Now the menu shows BOTH: your own set (the SMASH trio SMASH_GRAB/SECURE_MASS/
  LATE_SWEEP, or the WALK-IN trio WALKIN_GRAB/WALKIN_SECURE/WALKIN_LATE if your
  pure must be walked) and the rival's set suffixed #2 — the aggressive trio
  (BLIND_GRAB#2 / UNBEATEN_FLANK#2 / WALK_IN#2) if the rival seam is LIVE to you,
  or the blind-attack pair BLIND_GRAB#2 / UNBEATEN_FLANK#2 (plus a demoted
  CONTEST_DENY#2) if the rival seam is fogged. A fresh fogged rival seam is worth
  ATTACKING (mass-rich, usually unharvested), but H1 is still your OWN pure —
  contest the rival with the SECOND unit / spare probe, not the first.
    * H1 is NOT a choice: grab your own pure (SMASH_GRAB or WALKIN_GRAB). It is
      the surest points on the board and yours alone — always take it first.
    * Your 2nd (and 3rd) harvester is a REAL FORK, and no rule can pick it for
      you — THINK IT THROUGH:
        (a) CONTEST THE RIVAL — BLIND_GRAB#2 (blind their finder, then blind-walk
            the mass-rich seam) or UNBEATEN_FLANK#2 (crawl in from an untested
            angle). This is DOUBLE DAMAGE: you take their pure AND deny them (they
            get nothing, you get everything), and even a miss banks nearby
            vein/mass on a fresh seam. But it is RISKIER — you blind first, and if
            they smash-grab in the same hour it still lands; weaker bots won't
            even know the move. High upside, high variance.
        (b) SECOND OWN DROP — SECURE_MASS (or WALKIN_SECURE) your own seam. SAFER
            and near-certain: you both walk away with something (they get their
            pure, you get your mass / a double-walked jackpot). Lower variance.
    * Let the SCORE tilt the fork (do not hard-code it): even or AHEAD → you can
      afford the double-damage swing on the rival. MASSIVELY BEHIND → the safe
      own-mass bank is usually smarter than a coin-flip; but if only a big swing
      can win, take the risk. Weapons likely on the rival seam → contesting is
      dearer (their chaff can zero your blind grab), so lean toward securing your
      own — or commit TWO units to the rival on distinct cells so one survives.
    * State your reasoning in "reasoning": which fork, and WHY (score, weapons,
      player count). This is exactly the judgement the menu hands to you.

  ============================================================
  WEAPONS SET THE CADENCE (defensive read):
  ============================================================
    * CHAFF seen -> a H1 smash can be cancelled. KEEP A BACKUP WAVE: always
      carry UNBEATEN_FLANK (or a later HOT DROP) so one jam does not zero your
      night.
    * EMP seen near the seam -> the patterns already SPACE later waves past the
      cloud window and FLANK the fresh probe OUTSIDE the blast. Do not schedule
      two pickups inside the same jam window.

  THE IDEA (no weapons): get in there and harvest SOMETHING. The ONLY things
  that pull a harvester off this contest are ANOTHER redsign elsewhere or a
  genuinely juicy mass CHAIN (CHn) — then spend ONE harvester there instead.

  DISJOINT PATHS: whenever two of your harvesters work the same seam, keep their
  chains >=2 cells apart so they never share a cell — a friendly collision is
  the same zero-bank pile-up as diving the beacon.
"""


DOCTRINE_DROP_ON_VALUE = """\
DROP ON THE VALUE — the landing cell is auto-harvested (free parcel #1):
  When a harvester DROPS onto a cell, the engine harvests THAT cell immediately
  (drop counts as harvest #1), and every step after also harvests its
  destination. So the drop cell is not a staging square — it is your FIRST
  parcel. Two consequences:
    * DROP DIRECTLY ON the highest-value reachable cell (pure > mass > vein).
      Do NOT drop on trace/edge and "walk in" to the good stuff — that wastes
      parcel #1 on junk and exposes the pure for extra hours.
    * SECURE A PURE SHORT. When a pure (or very high-tier) cell is reachable,
      drop ON it FIRST and pick up FAST — 0 extra steps under chaff/EMP/contest,
      1-2 only when clearly safe. The auto-harvested pure sits in the harvester's
      HOLD and only banks to your hoard at PICKUP, so a long chain leaves the
      whole load one crash/chaff/collision from being spilled. Strip the wider
      seam with a SECOND harvester or a later wave, never the grabbing unit.
  Exception: never drop/step onto GREEN or synthetic-green (that auto-banks a
  -100 parcel). Value-first, but hazard cells are still off-limits.

  PRIORITY RED GRABS are the top of your value pyramid — they list every pure /
  mass RED you can already SEE (LIVE) or REACH (ECHO walk-in), pre-built as
  drop+walk with NO probe. If a RED GRAB is offered it is almost always your FIRST
  pick: take the pure/mass you can see before anything speculative (a fresh probe,
  a fogged frontier, a supersede). A GRAB tagged WALK_IN drops on a LIVE frontier
  cell and walks ONTO a fogged/echo pure — that is the CORRECT way to take a pure
  that is not drop-legal, NOT the "drop on junk" mistake (the frontier cell is
  empty, the pure is the prize). Only skip a RED GRAB when a redsign pattern
  already secures that same pure, or a rival will clearly beat you to it this hour.

  HIGH-YIELD BLUE GRABS are a SEPARATE, lower group — rich blue you can SEE and
  grab with zero risk, but RED always outranks blue for a scarce harvester. They
  only appear when orbital asks for blue (vault low) OR you have a spare harvester
  beyond your strong red chains. Take one when you NEED blue or a harvester would
  otherwise idle / gather low-yield red — never over a red chain that could run it.

  CHOOSE THE COMB SHAPE. A hot drop may appear on the menu as three variants of
  the SAME drop — pick exactly ONE per drop; the length/area is YOUR call:
    * STRETCH (…L) — long straight-ish line, MAX new intel/area. Use on a BLIND
      bluesign/fog gamble where you don't know where the value sits and want to
      see + sweep the most ground.
    * SWEEP (…T) — tight dense serpentine hugging the drop. Use when you have
      LANDED ON a known cluster and just want to strip it.
    * SAMPLE (…Q) — quick 2-step in/out. Use on a HOT/CONTESTED cell: grab what
      you can and lift before a rival collision or chaff zeroes the load.
"""


DOCTRINE_FULL_UTILIZATION = """\
DEPLOY THE WHOLE FLEET (modus operandi) — you have more than one harvester
tonight, so get EVERY one onto the board. An idle harvester in orbit banks
nothing; a wasted unit is a wasted night. Give each its OWN target (a JUICE
CHAIN, a HOT DROP, or a seam wave) and put an ID for each into "plan". Keep two
harvesters' paths >=2 cells apart so they never share a cell (a friendly
collision banks ZERO, same as diving a beacon). Length follows VALUE — a thin
seam is a SHORT chain, never a padded walk — but the default is: all harvesters
out, every night.
"""


DOCTRINE_MULTIPROBE = """\
DEPLOY EVERY SPARE PROBE, AND SPREAD THEM (vision is how you win the NEXT night).
A probe launches from orbit and does NOT cost your harvesters' walk hours — an
idle probe in stock is simply blindness you chose. So after the probe(s) your
seam pattern already uses, put a PR id into "plan" for EACH remaining probe in
stock. TWO rules:
  * SPREAD, don't dogpile. One flank probe on the seam you are already working
    is plenty; every extra probe stacked on the SAME region is wasted vision.
    Send the rest to NEW ground — a DIFFERENT signal (a bluesign cluster, a
    second redsign), a fresh fog centroid, or a scouting edge — so tomorrow you
    can act on the whole map, not one corner.
  * SUPERSEDE (SS) to deny, not just on the last night. Any night you hold a
    SPARE probe (>1 probe, or your red chains already bank high so a probe is
    free), spend it landing ON a rival's probe to BLIND it — deny their next
    landing + vision. If you are TRAILING, blind the LEADER's freshest probe
    first; never waste one on a probe about to expire (its vision is spent).
    On the FINAL night this is the DEFAULT for every spare probe — there is no
    "next night" to see for, so blind the enemy's last harvest.
Selecting only one PR while probes sit in stock is the single most common way
this seat throws away a night's vision. Match the number of PR/SS ids to your
probe stock.
"""


DOCTRINE_WEAPONS_ORBITAL = """\
KNOW WHO HAS WHAT — weapons are ORBITAL strikes, not ground units:
  Opponents are in ORBIT. EMP and chaff are launched FROM orbit and can hit
  ANYWHERE on the map regardless of where an opponent's units sit. "They're
  clustered on the far side, so low risk" is a MISREAD — range is not the
  variable. The real question is: does THIS seat have stock, and do you
  present an obvious aim point?
    * A public REDSIGN + your probe drop on the beacon is a BULLSEYE: it tells
      a weapon-capable seat EXACTLY where to aim an EMP. Prefer offset drops.
    * Read OPPONENT WEAPONS per-seat: a FIRED launch is a FACT (that stock
      existed and was spent); an un-fired [min..max] build estimate is an
      ESTIMATE, not certainty. Treat fired = known threat, estimate = hedge.
    * Match the reaction to the seat that actually has the weapon, not to a
      global "someone might" — if only p3 has chaff and p3 is not contesting
      your seam tonight, do not shorten every chain.
  See WEAPON GEOMETRY for the exact blast radius / durations, and EMP SCARS
  for cells to route around this coming night.
"""


DOCTRINE_WEAPONS_MULTIWAVE = """\
WEAPONS => MORE UNITS ON THE SEAM, NOT ONE SHORTER CHAIN (offensive read):
  The defensive rules above (short chains, dodge predictable pickup windows) are
  how a SINGLE unit survives. They are NOT the whole answer, because a lone
  chain — however short — is ONE EMP or ONE chaff away from a zero night. When a
  weapon is likely on a contested seam, the winning move is REDUNDANCY ACROSS
  HARVESTERS: commit MORE of the fleet to the SAME seam on DISTINCT cells so a
  strike that catches one wave still leaves another banking.
    * SPLIT THE TARGETS. Send one harvester to GRAB THE PURE (short, danger-gated
      drop+lift) and a SECOND to work the surrounding MASS on a different cell /
      bearing. Pure and mass are different cells — hitting BOTH with two units is
      not a repeat, it is coverage. Add a THIRD wave (later HOT DROP / flank
      probe) past the blast window if you have the unit.
    * DISTINCT CELLS, DISJOINT PATHS (>=2 apart). Two units must never share a
      drop or a step cell — the packager/sanitizer will delete the second as a
      self-collision, and in the engine it is the same zero-bank pile-up as
      diving the beacon. Redundancy means DIFFERENT cells on the same seam, never
      the same cell twice.
    * STAGGER PAST THE WINDOW. Space the waves so their pickups do not all fall in
      one jam window (the flank/late wave lands AFTER the likely EMP/chaff hour).
    * BEING JAMMED IS NOT DEATH. An EMP'd harvester KEEPS its haul and can still
      be picked up; everything it banked before the strike comes home. So a second
      committed unit is cheap insurance, not a gamble — the downside is a few
      hours, the upside is you still bank if the first wave is jammed.
  The failure this fixes: on a weapons-likely night the seat retreats to ONE
  timid short chain, gets it jammed, and banks nothing while two harvesters sat
  idle in orbit. Deploy the fleet ONTO the seam; let the strike waste itself on
  one wave.
"""


__all__ = [
    "STRATEGIES_CORE",
    "DOCTRINE_BLUE",
    "DOCTRINE_REDSIGN",
    "DOCTRINE_LASTDAY_SUPERSEDE",
    "DOCTRINE_BEWARE_EMP",
    "DOCTRINE_BEWARE_CHAFF",
    "DOCTRINE_COMPREHENSION",
    "DOCTRINE_REDSIGN_POKER",
    "DOCTRINE_DROP_ON_VALUE",
    "DOCTRINE_FULL_UTILIZATION",
    "DOCTRINE_MULTIPROBE",
    "DOCTRINE_WEAPONS_ORBITAL",
    "DOCTRINE_WEAPONS_MULTIWAVE",
]
