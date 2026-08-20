"""Attributed event digest — turn the raw event channels into causal prose.

Workstream A of the v9 comprehension uplift. ``view._last_night_recap`` now
emits three attributed channels on ``agent_view.last_night``:

  * ``incoming_attacks`` — probe kills / EMP / chaff done TO this seat, each
    with the attacker seat (``by``) and the ``consequence``.
  * ``my_denials``       — supersedes this seat inflicted ON opponents.
  * ``emp_scars``        — active EMP scars (cells + hours) as a board hazard.

Plus the pre-existing ``my_collisions`` (harvester simultaneous-drop pile-ups).

This module is pure string formatting over that structured data — no engine
access, no I/O. It exists so the prompt (SECTION 3) can show a two-way
"WHAT HAPPENED — to you & by you" narrative that draws the causal line for
the agent ("p2 superseded your probe -> you lost that disk -> the hot-drop
had no sensor -> 0 banked") instead of leaving it to confabulate a cause.
"""

from __future__ import annotations

from typing import Any, List, Mapping, Sequence


def _fmt_cell(at: Any) -> str:
    """Render an ``[x, y]`` cell, tolerating missing / malformed input."""
    if isinstance(at, (list, tuple)) and len(at) == 2 and at[0] is not None:
        try:
            return f"({int(at[0])},{int(at[1])})"
        except (TypeError, ValueError):
            return "a shared cell"
    return "a shared cell"


def _fmt_hours(hours: Sequence[Any]) -> str:
    """Compress a sorted hour list into contiguous ranges, e.g. ``9-11, 14``."""
    vals: List[int] = []
    for h in hours or []:
        try:
            vals.append(int(h))
        except (TypeError, ValueError):
            continue
    if not vals:
        return "?"
    vals = sorted(set(vals))
    spans: List[str] = []
    start = prev = vals[0]
    for v in vals[1:]:
        if v == prev + 1:
            prev = v
            continue
        spans.append(f"{start}-{prev}" if start != prev else f"{start}")
        start = prev = v
    spans.append(f"{start}-{prev}" if start != prev else f"{start}")
    return ", ".join(spans)


def _fmt_seats(seats: Sequence[Any]) -> str:
    """Join a seat list for prose (``p2``, ``p2 & p3``, ``p2, p3 & p4``)."""
    names = [str(s) for s in (seats or []) if str(s)]
    if not names:
        return "a rival"
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " & " + names[-1]


def narrate_incoming(agent_view: Mapping[str, Any]) -> List[str]:
    """Causal lines for everything done TO this seat last night."""
    ln = agent_view.get("last_night") or {}
    lines: List[str] = []

    for a in ln.get("incoming_attacks") or []:
        if not isinstance(a, Mapping):
            continue
        atype = str(a.get("type", ""))
        by = _fmt_seats(a.get("by"))
        cons = str(a.get("consequence") or "").strip()
        if atype == "emp_hit":
            unit = str(a.get("unit") or "a harvester")
            hrs = _fmt_hours(a.get("hours"))
            lines.append(
                f"{by} EMP-smothered {unit} at hour(s) {hrs} -> {cons}"
            )
        elif atype == "chaff_jam":
            hrs = _fmt_hours(a.get("hours"))
            units = a.get("units") or []
            u = f" ({_fmt_seats(units)})" if units else ""
            lines.append(
                f"{by} chaff-jammed your actions{u} at hour(s) {hrs} -> {cons}"
            )
        elif atype == "probe_superseded":
            cell = _fmt_cell(a.get("at"))
            lost = ", ".join(str(x) for x in (a.get("lost_ids") or [])) or "a probe"
            lines.append(
                f"{by} dropped a probe onto your {lost} at {cell}, "
                f"destroying it -> {cons}"
            )
        elif atype == "probe_collision":
            cell = _fmt_cell(a.get("at"))
            lines.append(
                f"your probe mutually annihilated with {by}'s probe at {cell} "
                f"-> {cons}"
            )

    # Harvester simultaneous-drop pile-ups (the pre-existing keystone channel).
    for c in ln.get("my_collisions") or []:
        if not isinstance(c, Mapping):
            continue
        cell = _fmt_cell(c.get("at"))
        others = c.get("others") or []
        who = f" with {_fmt_seats(others)}" if others else ""
        lines.append(
            f"your harvester COLLIDED at {cell}{who} -> banked ZERO; the cargo "
            f"was LOST, not held in hoard (the advertised cell was a "
            f"mutual-kill zone)"
        )
    return lines


def narrate_denials(agent_view: Mapping[str, Any]) -> List[str]:
    """Causal lines for everything this seat did TO opponents last night."""
    ln = agent_view.get("last_night") or {}
    lines: List[str] = []
    for d in ln.get("my_denials") or []:
        if not isinstance(d, Mapping):
            continue
        dtype = str(d.get("type", ""))
        cell = _fmt_cell(d.get("at"))
        cons = str(d.get("consequence") or "").strip()
        against = _fmt_seats(d.get("against"))
        if dtype == "probe_superseded":
            lines.append(
                f"you superseded {against}'s probe at {cell} -> {cons}"
            )
    return lines


def narrate_scars(agent_view: Mapping[str, Any]) -> List[str]:
    """Board-hazard lines for EMP scars still live this coming night."""
    ln = agent_view.get("last_night") or {}
    lines: List[str] = []
    for s in ln.get("emp_scars") or []:
        if not isinstance(s, Mapping):
            continue
        cell = _fmt_cell(s.get("at"))
        hrs = _fmt_hours(s.get("hours"))
        lines.append(f"{cell} scarred at hour(s) {hrs}")
    return lines


def format_event_digest_block(agent_view: Mapping[str, Any]) -> str:
    """SECTION 3 two-way digest: what happened TO you and BY you last night.

    Returns "" when nothing attributable happened, so the prompt can skip the
    block entirely on a quiet night.
    """
    incoming = narrate_incoming(agent_view)
    denials = narrate_denials(agent_view)
    if not incoming and not denials:
        return ""
    out: List[str] = ["WHAT HAPPENED LAST NIGHT (cause -> effect):"]
    if incoming:
        out.append("  TO YOU (attacks + losses — learn the lesson):")
        for line in incoming[:6]:
            out.append(f"    - {line}")
    if denials:
        out.append("  BY YOU (denial you inflicted — press the advantage):")
        for line in denials[:6]:
            out.append(f"    - {line}")
    return "\n".join(out) + "\n"


def format_emp_scars_block(agent_view: Mapping[str, Any]) -> str:
    """SECTION 2 hazard block: EMP scars to route drops/steps around."""
    scars = narrate_scars(agent_view)
    if not scars:
        return ""
    out = [
        "EMP SCARS (still live — route drops/steps AROUND these; a unit "
        "caught inside is disabled and risks a dawn crash):"
    ]
    for line in scars[:8]:
        out.append(f"  {line}")
    return "\n".join(out) + "\n"
