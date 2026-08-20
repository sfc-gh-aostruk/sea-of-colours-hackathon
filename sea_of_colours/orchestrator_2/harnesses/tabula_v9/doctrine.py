"""Advisory doctrine — the playbook the agent SHOULD follow (tabula_v9 fork).

v9 keeps the frozen v7 core doctrine (imported verbatim) and rewrites the
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

New / rewritten in v9:
  * DOCTRINE_REDSIGN_POKER — the two-case weapon-free opening book (my-redsign
    vs not-mine), the user's hot-drop poker.
  * DOCTRINE_WEAPONS_ORBITAL — EMP/chaff reframed as targeted orbital strikes.
  * DOCTRINE_COMPREHENSION — read the attributed WHAT HAPPENED digest and act.
"""

from __future__ import annotations

# Re-export the frozen v7 doctrine so v9 owns one doctrine surface.
from sea_of_colours.orchestrator_2.harnesses.tabula_v7.strategies import (  # noqa: F401
    STRATEGIES_CORE as _V7_STRATEGIES_CORE,
    DOCTRINE_BLUE,
    DOCTRINE_REDSIGN as _V7_DOCTRINE_REDSIGN,
    DOCTRINE_LASTDAY_SUPERSEDE,
    DOCTRINE_BEWARE_EMP,
    DOCTRINE_BEWARE_CHAFF,
)

# SCORING CORRECTION (v9 hermetic fix — hyg-scoring). A pure(255) is
# 255 × 3.0 = 765 base pts, NOT 2295 (the frozen v7 text double-counts the tier
# multiplier). Correct the two v7 strategy strings for v9 ONLY; v7/v8 baselines
# stay frozen. See tabula_v9/rules.py for the engine reference.
STRATEGIES_CORE = _V7_STRATEGIES_CORE.replace(
    "A pure(255) cell is 2295 base pts and usually overrides a normal chain",
    "A pure(255) cell is 765 base pts (the biggest single cell; the surrounding "
    "SEAM adds more) and usually overrides a normal chain",
)
# CONTESTED-JACKPOT EXCEPTION (v9 — hyg-contradictions). The frozen v7
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
DOCTRINE_REDSIGN = _V7_DOCTRINE_REDSIGN.replace(
    "cell scores 765 x 3.0 = 2295 base pts and pure runs in SEAMS, so the",
    "cell scores 255 x 3.0 = 765 base pts and pure runs in SEAMS, so the",
)
assert "2295" not in STRATEGIES_CORE + DOCTRINE_REDSIGN, (
    "v9 scoring correction failed to apply"
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
  SMASH_GRAB is a HYPER-FAST grab, NOT a seam walk. Typical plan:
    plan = ["SMASH_GRAB", ...]
    * The GRAB is the DROP. Land the harvester ON the pure at H1 — the landing
      cell auto-harvests, so the 765 jackpot banks as parcel #1 the instant you
      touch down. If the pure is already in live vision, drop STRAIGHT (no probe
      first); secure the pure BEFORE spending a probe elsewhere.
    * Then PICK UP FAST — length is DANGER-GATED: 0 extra steps (just drop +
      pickup) under chaff/EMP/contest or a 3-way; 1-2 steps only when clearly
      safe. NEVER ride a long chain over the jackpot — a crash/chaff/collision
      on the walk spills the whole load, which beats the few extra hours.
    * The WIDER SEAM is a SEPARATE job — a LATER wave (post-EMP, new angle) or a
      SECOND harvester / CHn chain. Do NOT fold the seam strip into the grab.
    * Add a HOT DROP (HDn) or PROBE (PRn) for a spare harvester/probe once the
      pure is secured.

  ============================================================
  CASE 2 — IT IS NOT YOUR REDSIGN (mine=false; a rival found it) — a fight:
  ============================================================
  The finder is piggybacking the probe that discovered the pure. Fan out; do
  NOT stack the lit cell. Typical plan, in order:
    plan = ["BLIND_GRAB", "UNBEATEN_FLANK", "WALK_IN"]
    * BLIND_GRAB — blind the finder (land your probe ON theirs to supersede it),
      then a blind drop and a SHORT SWEEP. KEY DIFFERENCE FROM SMASH_GRAB: here
      you do NOT know the exact pure — the broadcast is a jittered smear, so one
      guessed drop cell rarely IS the pure. Comb 2-3 cells across the top
      candidates (not zero — a single-cell blind grab usually banks trace for
      nothing), then pick up. Poker note: if they drop in hour K it STILL lands
      (vision snapshots at hour-start); your supersede only denies them from K+1.
      Try it anyway — the sweep banks nearby red and denies.
    * UNBEATEN_FLANK — the SECURED bank: a fresh probe on the OPPOSITE axis
      reaches the same seam from an uncontested angle after the EMP window. This
      is the wave nobody is fighting for; make it your reliable pickup.
    * WALK_IN — late outer mop-up from a THIRD bearing: pure red bleeds into
      good red, so you scoop the halo even if the pure itself is contested (and
      you keep great vision for tomorrow).
  If a wave 1 crash means NOBODY banked the pure, that is fine: the pure tile
  SURVIVES a collision. Come again next wave / next night from a new angle.

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
  * On the FINAL night, spare probes become SUPERSEDES (SS) — there is no
    "next night" to see for, so spend them blinding the enemy's last harvest.
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
]
