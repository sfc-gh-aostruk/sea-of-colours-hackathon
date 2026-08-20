"""Advisory doctrine — the playbook the agent SHOULD follow (tabula_v8 fork).

v8 keeps the frozen v7 doctrine (imported verbatim) and adds the pieces the
v7 audit proved missing — the "redsign poker" opening book and a weapons
reframe — as new state-triggered appendices. Like v7, these are gated by
``prompt.build_prompt`` on live state + the new §4 data so haiku never burns
attention on doctrine it cannot act on tonight.

Carried over from v7 (unchanged): STRATEGIES_CORE, DOCTRINE_BLUE,
DOCTRINE_REDSIGN, DOCTRINE_LASTDAY_SUPERSEDE, DOCTRINE_BEWARE_EMP,
DOCTRINE_BEWARE_CHAFF.

New in v8:
  * DOCTRINE_REDSIGN_POKER — the honeypot-beacon opening book (fixes L1/L3/L4).
  * DOCTRINE_WEAPONS_ORBITAL — reframes EMP/chaff as targeted orbital strikes
    with known geometry, killing the "they're clustered far east, low risk"
    misread (L1).
"""

from __future__ import annotations

# Re-export the frozen v7 doctrine so v8 owns one doctrine surface.
from sea_of_colours.orchestrator_2.harnesses.tabula_v7.strategies import (  # noqa: F401
    STRATEGIES_CORE,
    DOCTRINE_BLUE,
    DOCTRINE_REDSIGN,
    DOCTRINE_LASTDAY_SUPERSEDE,
    DOCTRINE_BEWARE_EMP,
    DOCTRINE_BEWARE_CHAFF,
)


# ─────────────────────────────────────────────────────────────────────────
# NEW v8 APPENDICES
# ─────────────────────────────────────────────────────────────────────────

DOCTRINE_REDSIGN_POKER = """\
REDSIGN POKER — the beacon is a HONEYPOT (read this before you race):
  A public REDSIGN broadcasts ONE cell everyone can see. That is exactly
  why the broadcast cell is a trap: every seat dives the SAME advertised
  cell, and two harvesters dropping on the same cell in the same hour
  COLLIDE — both take damage and bank ZERO (see LAST NIGHT for any collision
  you were just in). The pure runs in a SEAM, so the points are in the cells
  AROUND the beacon, not only on it.

  THE WINNING READ — drop OFFSET onto the seam, not on the advertised cell:
    * Land on a pure/mass cell ADJACENT to the broadcast cell (your own
      probe disk usually makes several seam cells drop-legal), and comb the
      seam away from the beacon. You bank the 255/245/210 neighbours while
      rivals crush each other on the single advertised point.
    * Only land ON the beacon cell itself if it is the ONLY drop-legal pure
      cell AND no rival probe is watching it (rare).

  CONTESTED (a `! WATCHED` cell, or an enemy probe near the seam) — commit
  redundancy, expect some loss:
    * Commit TWO harvesters on DISJOINT offset chains (keep their paths >=2
      cells apart so they never share a cell — a friendly collision is the
      same zero-bank pile-up). If one collides with a rival, the other still
      banks.
    * If the watching seat is WEAPON-CAPABLE (see OPPONENT WEAPONS), stagger
      the second harvester behind a FRESH probe (~hour 9) and exfil by ~hour
      13, and drop a BACKUP probe offset from the beacon so a mass-nuke still
      leaves you night-2 vision.

  DENY VIA SUPERSEDE — blind the discoverer:
    * Landing a probe ON an enemy's discovering probe destroys + supersedes
      it (your probe survives), denying their drop from hour K+1. Honest
      timing: a drop they committed in hour K STILL lands (vision snapshots
      at hour-start); supersede denies K+1 onward.

  SCALES WITH SEATS: more opponents -> higher collision odds on the beacon
  -> offset drops, backup probes, and a second harvester are worth MORE, not
  less. When 3 seats can see the beacon, assume the advertised cell is a
  mutual-kill zone and take the seam.
"""


DOCTRINE_WEAPONS_ORBITAL = """\
KNOW WHO HAS WHAT — weapons are ORBITAL strikes, not ground units:
  Opponents are in ORBIT. EMP and chaff are launched FROM orbit and can hit
  ANYWHERE on the map regardless of where an opponent's harvesters or probes
  sit. "They're clustered on the far side, so low risk" is a MISREAD — range
  is not the variable. The real question is: does THIS seat have stock, and
  do you present an obvious aim point?
    * A public REDSIGN + your probe drop on the beacon is a BULLSEYE: it
      tells a weapon-capable seat EXACTLY where to aim an EMP.
    * Read OPPONENT WEAPONS per-seat: a FIRED launch is a FACT (that stock
      existed and was spent); an un-fired [min..max] build estimate is an
      ESTIMATE, not certainty. Treat fired = known threat, estimate = hedge.
    * Match the reaction to the seat that actually has the weapon, not to a
      global "someone might" — if only p3 has chaff and p3 is not contesting
      your seam tonight, do not shorten every chain.
  See WEAPON GEOMETRY for the exact blast radius / durations to reason with.
"""


__all__ = [
    "STRATEGIES_CORE",
    "DOCTRINE_BLUE",
    "DOCTRINE_REDSIGN",
    "DOCTRINE_LASTDAY_SUPERSEDE",
    "DOCTRINE_BEWARE_EMP",
    "DOCTRINE_BEWARE_CHAFF",
    "DOCTRINE_REDSIGN_POKER",
    "DOCTRINE_WEAPONS_ORBITAL",
]
