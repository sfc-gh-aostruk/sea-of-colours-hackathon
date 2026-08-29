"""v0.9 — Weapons + WAIT tuning constants.

Every numeric balance dial for the interdiction layer (EMP warheads,
orbital chaff flares, the WAIT command) lives here. Engine, UI, and
tests all import from this module so balance work is a one-file edit.

The plan deliberately keeps the *mechanics* generalised even when the
current launch values look like "three missiles a salvo" or "1-hour
chaff" — bumping ``EMP_MISSILES_PER_LAUNCH`` or ``CHAFF_DURATION_HOURS``
should never require an engine change.

v1.31 — the caltrop mine's dials were the third block here and are
gone; ``docs/ADDING_A_WEAPON.md`` uses them as the worked example of
what a replacement weapon has to define.

See RULEBOOK §5 (v0.9) for the canonical prose; the values below
are the SHIPPED defaults at v0.9.0.
"""

from __future__ import annotations


# ── EMP warhead blast ────────────────────────────────────────────
# Launch-cost: 200 blue-purity + 250 credits. A single launch fires
# THREE simultaneous missiles (EMP_MISSILES_PER_LAUNCH); each forms
# its own Manhattan radius-2 cloud at its target cell at the launch
# hour. Every harvester sitting in any cloud is disabled for the
# next 8 hours of the same night, and any PROBE caught in a cloud is
# destroyed. Friendly fire IS in scope — the launcher's own
# units are not immune. Open action: all seats see the launch frame
# + cloud cells.
EMP_COST_BLUE_PURITY: int = 200
EMP_COST_CREDITS: int = 250
EMP_RADIUS: int = 2
"""Manhattan radius; each cloud covers ``2*r*(r+1)+1`` cells (13 at r=2)."""
EMP_MISSILES_PER_LAUNCH: int = 3
"""Missiles fired per launch / stock consumed. One launch = up to this
many simultaneous target cells, each spawning its own EMP cloud."""
EMP_CLOUD_HOURS: int = 8
"""Cloud lifetime in PRAXIS hours. Clamped to remaining night."""
EMP_VISIBILITY: str = "open"
"""``"open"`` | ``"hidden_until_probed"`` — only ``"open"`` is wired
in v0.9.0; the field is here so a future stealth EMP is a flip."""


# ── Caltrop mines — RETIRED v1.31 ────────────────────────────────
# The third weapon slot is deliberately empty. Mines were retired to
# free it for a replacement, not because the slot was a mistake, so
# the machinery around it (schema columns, replay frames, the FX
# path) was left standing on purpose — archived seasons still play
# back, and a new weapon plugs into the same holes.
#
# Everything a third weapon has to touch is mapped in
# docs/ADDING_A_WEAPON.md, with the caltrop as the worked example.
# Its dials lived here: cost in blue purity and credits, how many
# tiles one order armed, the batch shape, and visibility.


# ── Orbital chaff flare ──────────────────────────────────────────
# Launch-cost: 255 blue-purity, 0 credits. At the hour the chaff
# resolves, every OTHER seat's action that hour is cancelled
# (probes, drops, steps, pickups, weapon launches, other chaffs).
# The triggerer's chaff itself succeeds. Multi-hour chaff is a
# constant bump away: the simulator tracks ``chaff_until_hour``
# (computed as ``hour + CHAFF_DURATION_HOURS - 1``) so raising
# the duration is one line.
CHAFF_COST_BLUE_PURITY: int = 255
CHAFF_COST_CREDITS: int = 0
CHAFF_DURATION_HOURS: int = 3
"""Number of consecutive hours the chaff smothers other moves,
starting at the hour the chaff resolves."""


# ── WAIT command ─────────────────────────────────────────────────
# Currently no tunables. Kept here for symmetry; future caps on
# consecutive waits or forced-action rules would land here.
# (A wait consumes one of the 21 hour slots but does nothing.)


__all__ = [
    "EMP_COST_BLUE_PURITY",
    "EMP_COST_CREDITS",
    "EMP_RADIUS",
    "EMP_MISSILES_PER_LAUNCH",
    "EMP_CLOUD_HOURS",
    "EMP_VISIBILITY",
    "CHAFF_COST_BLUE_PURITY",
    "CHAFF_COST_CREDITS",
    "CHAFF_DURATION_HOURS",
]
