"""Runtime-tunable rule knobs for the vision rework (Phase 2).

These are read from the environment **at call time** (not import time) so
the offline balance sweep can flip them per-config in-process, and a live
server can be launched with a variant without code edits.

v0.9.17 — canonical ruleset committed:
  SOC_DROP_MODE=live_only  (probe coverage required to land)
  SOC_PROBE_RADIUS=4       (~49-cell Euclidean disk per probe)
  SOC_PROBE_LIFETIME_NIGHTS=3  (probes expire after 3 nights)

Env vars still override code defaults for local experiments and CI sweeps.

Knobs:

* ``SOC_DROP_MODE`` — ``"live_only"`` (canonical) or ``"live_or_echo"``.
  In live-only, a harvester may only be dropped onto a cell the seat sees
  *right now* (probe disk or a friendly harvester's plus); stale own-echo /
  memory no longer qualifies. Landing becomes a public, contested act
  (probe launches are broadcast, §3.15).
* ``SOC_PROBE_RADIUS`` — Euclidean probe vision radius (default 4 = a
  ~49-cell disk). Overridable for balance experiments.
* ``SOC_PROBE_LIFETIME_NIGHTS`` — nights a probe survives before dawn
  expiry. Default 3. Set to 0 to disable expiry.
"""

from __future__ import annotations

import os
from typing import Optional

DROP_MODE_LIVE_ONLY = "live_only"
DROP_MODE_LIVE_OR_ECHO = "live_or_echo"


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(str(raw).strip())
    except ValueError:
        return default


def drop_mode() -> str:
    """Return the active drop-legality mode (canonical: live_only)."""
    raw = (os.environ.get("SOC_DROP_MODE") or "").strip().lower()
    if raw in (DROP_MODE_LIVE_OR_ECHO, "liveorecho", "live-or-echo", "echo"):
        return DROP_MODE_LIVE_OR_ECHO
    return DROP_MODE_LIVE_ONLY


def live_only_drops() -> bool:
    return drop_mode() == DROP_MODE_LIVE_ONLY


def probe_vision_radius(default: int = 4) -> int:
    """Euclidean probe vision radius (canonical default: 4 = ~49-cell disk)."""
    return max(1, _int_env("SOC_PROBE_RADIUS", int(default)))


def probe_lifetime_nights() -> Optional[int]:
    """Nights a probe survives before dawn expiry (canonical: 3)."""
    k = _int_env("SOC_PROBE_LIFETIME_NIGHTS", 3)
    return k if k > 0 else None
