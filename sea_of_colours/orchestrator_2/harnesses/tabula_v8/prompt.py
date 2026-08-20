"""Prompt assembly for tabula_v8 — the WORLDVIEW restructure.

v7's ``build_prompt`` concatenated 16 blocks in a flat order. v8 groups them
into THREE explicitly-labelled worldview pillars so the agent (and the
contained thinker especially) has a clean scaffold to reason against:

  === SECTION 1 - THE GAME (how it works) ===
    RULES (engine physics) + DOCTRINE (core + state-triggered appendices,
    including the new v8 redsign-poker book and weapons-orbital reframe) +
    the STRATEGIST DIRECTIVE handoff (mover only, split mode).

  === SECTION 2 - THE BOARD NOW (what you see) ===
    YOUR STATE, VISIBLE RED, DROP-LEGAL, FOG+ECHO, ENEMY PROBES (new),
    OPPONENT INTEL, OPPONENT WEAPONS + WEAPON GEOMETRY (new), wishlist, and
    the precomputed HINT menu.

  === SECTION 3 - WHAT HAPPENED LAST NIGHT (learn) ===
    LAST NIGHT (now including COLLISIONS - the keystone fix), the grounded
    REFLECT block (collision losses named as LOST, not held), and MEMORY.

Battle-tested block formatters are imported verbatim from ``tabula_v7.prompt``
(pure functions over the agent view); v8 only writes the new blocks
(enemy probes, weapon geometry, collision-aware last-night/reflect) and the
sectioned assembler. This is a true fork of the *feeding* layer that reuses
the *computation* layer.
"""

from __future__ import annotations

from typing import Any, List, Mapping, Sequence

from sea_of_colours.orchestrator_2.harnesses.tabula_v8 import doctrine, rules
from sea_of_colours.orchestrator_2.harnesses.tabula_v7.orbit_wishlist import (
    Wishlist,
)
from sea_of_colours.orchestrator_2.harnesses.tabula_v7.probe_hints import (
    _redsign_centers,
    _enemy_probe_cells,
)
# Reuse v7's proven, pure block formatters + schemas verbatim.
from sea_of_colours.orchestrator_2.harnesses.tabula_v7.prompt import (
    format_state_block,
    format_visible_red_block,
    format_drop_legal_block,
    format_fog_and_echo_block,
    format_opponent_block,
    format_opponent_weapons_block,
    format_wishlist_block,
    format_chain_hints_block,
    format_probe_hints_block,
    format_hot_drop_hints_block,
    format_blue_hints_block,
    format_supersede_hints_block,
    format_setup_night_advisory,
    format_reflect_block as _v7_reflect_block,
    format_last_night_block as _v7_last_night_block,
    _my_jam_events,
    _ACTION_SCHEMA,
    _THINKER_SCHEMA,
)

_SECTION_1 = "=== SECTION 1 - THE GAME (how it works) ==="
_SECTION_2 = "=== SECTION 2 - THE BOARD NOW (what you can see right now) ==="
_SECTION_3 = "=== SECTION 3 - WHAT HAPPENED LAST NIGHT (learn from it) ==="


# ── NEW v8 board blocks ────────────────────────────────────────────────
def format_enemy_probes_block(
    agent_view: Mapping[str, Any], *, day: int,
) -> str:
    """First-class ENEMY PROBES block (v8 §4c).

    An enemy probe launch is PUBLIC (§3.15). v7 only surfaced these as
    ``! WATCHED`` annotations on drop-legal cells and as final-night
    supersede hints; v8 promotes them to a standing block on EVERY night so
    the agent can plan to route around them, stage behind them, or supersede
    them mid-season, and so it understands a rival can hot-drop into these
    disks (the collision risk on a shared cell).
    """
    enemy = _enemy_probe_cells(agent_view)
    if not enemy:
        return ""
    lines = [
        "ENEMY PROBES (public launches — a rival SEES and can DROP into each "
        "disk; a shared drop cell risks a mutual-kill collision):"
    ]
    for row in enemy[:6]:
        at = row.get("at")
        if not (isinstance(at, (list, tuple)) and len(at) == 2):
            continue
        ds = row.get("day_seen")
        src = str(row.get("source") or "seen")
        age_txt = ""
        try:
            if ds is not None and int(ds) > 0:
                age = max(0, int(day) - int(ds))
                age_txt = f" (day {int(ds)}, ~{age}n old)"
        except (TypeError, ValueError):
            age_txt = ""
        lines.append(f"  ({int(at[0])},{int(at[1])}){age_txt} via {src}")
    lines.append(
        "  -> Route your drops/steps around these disks. Staging a harvester "
        "behind a FRESH probe of your own keeps you off their watched cells. "
        "Landing YOUR probe on one of these cells SUPERSEDES it (destroys "
        "their vision; yours survives) — cheap denial, best on the final night."
    )
    return "\n".join(lines) + "\n"


def format_weapon_geometry_block(
    estimates: "Mapping[str, Any] | None",
) -> str:
    """WEAPON GEOMETRY constants (v8 §4d).

    Only rendered when some opponent is estimated to hold EMP or chaff, so
    the agent reasons about EMP as a targeted orbital strike with a KNOWN
    blast radius on a known beacon — not a distance-from-a-cluster gamble.
    """
    if not estimates:
        return ""
    armed = any(
        getattr(e, "emps_max", 0) > 0 or getattr(e, "chaff_max", 0) > 0
        for e in estimates.values()
    )
    if not armed:
        return ""
    try:
        from sea_of_colours.game.weapons import (
            EMP_RADIUS,
            EMP_MISSILES_PER_LAUNCH,
            EMP_CLOUD_HOURS,
            CHAFF_DURATION_HOURS,
        )
    except Exception:  # pragma: no cover - defensive
        EMP_RADIUS, EMP_MISSILES_PER_LAUNCH = 2, 3
        EMP_CLOUD_HOURS, CHAFF_DURATION_HOURS = 8, 3
    return (
        "WEAPON GEOMETRY (reason with the exact numbers, not vibes):\n"
        f"  EMP: an orbital salvo of {EMP_MISSILES_PER_LAUNCH} missiles; each "
        f"forms a Manhattan-radius-{EMP_RADIUS} cloud (~13 cells) that lasts "
        f"{EMP_CLOUD_HOURS}h. Inside it: probes/mines DESTROYED, harvesters "
        f"DISABLED (they keep their haul — only a dawn crash kills them). It "
        f"is aimed at a CELL (usually your latest probe or a pure beacon), "
        f"reachable anywhere on the map.\n"
        f"  CHAFF: cancels every OTHER seat's actions for {CHAFF_DURATION_HOURS} "
        f"consecutive hours. A pickup inside that window is lost -> dawn-crash "
        f"risk. It has no location — it is a seat-wide jam.\n"
    )


def format_last_night_block(agent_view: Mapping[str, Any]) -> str:
    """v8 LAST NIGHT block — v7's engine record PLUS the collision channel.

    The collision lines are the keystone fix: a simultaneous-drop pile-up
    banks ZERO and shows up in no other channel, so without this the agent
    saw "banked 0" and confabulated a cause. Sourced from the fog-safe
    ``last_night.my_collisions`` (public collision rings, self-party only).
    """
    base = _v7_last_night_block(agent_view)
    ln = agent_view.get("last_night") or {}
    collisions = ln.get("my_collisions") or []
    if not collisions:
        return base

    lines: List[str] = []
    if not base.strip():
        lines.append(
            f"LAST NIGHT (day {ln.get('day_ended', '?')} — engine record):"
        )
    else:
        lines.append(base.rstrip("\n"))
    lines.append(f"  my_collisions ({len(collisions)}) — YOU banked ZERO here:")
    for c in collisions[:4]:
        if not isinstance(c, Mapping):
            continue
        at = c.get("at") or [None, None]
        others = c.get("others") or []
        who = f" with {others}" if others else ""
        at_s = (
            f"[{at[0]},{at[1]}]" if at and at[0] is not None else "a shared cell"
        )
        lines.append(
            f"    - harvester COLLIDED at {at_s}{who} — returned orbital "
            f"damaged, 0 cargo (cargo LOST, NOT held in hoard). The advertised "
            f"cell was a mutual-kill zone."
        )
    return "\n".join(lines) + "\n"


def format_reflect_block(
    agent_view: Mapping[str, Any],
    prior_day_entry: "Mapping[str, Any] | None",
    day: int,
) -> str:
    """v8 grounded REFLECT — v7's block PLUS explicit collision-LOSS framing.

    v7's reflect tells the agent a 0 shipped-change with a healthy harvest is
    "held, not lost". On a COLLISION night that framing is dangerously wrong —
    the cargo was genuinely LOST, nothing entered the hoard. So when a
    collision is on record we prepend a hard "this was a LOSS" line the model
    must acknowledge, defeating the "thin seam"/"held not lost" confabulation.
    """
    base = _v7_reflect_block(agent_view, prior_day_entry, day)
    ln = agent_view.get("last_night") or {}
    collisions = ln.get("my_collisions") or []
    if not collisions:
        return base

    prior_day = int(day) - 1
    lines: List[str] = []
    if not base.strip():
        lines.append(
            f"REFLECT ON LAST NIGHT (day {prior_day}) — engine ground truth:"
        )
    else:
        lines.append(base.rstrip("\n"))
    for c in collisions[:4]:
        if not isinstance(c, Mapping):
            continue
        at = c.get("at") or [None, None]
        others = c.get("others") or []
        at_s = f"[{at[0]},{at[1]}]" if at and at[0] is not None else "the beacon"
        who = f" with {others}" if others else " with rivals"
        lines.append(
            f"  COLLISION LOSS: a harvester of yours collided at {at_s}{who} "
            f"and banked ZERO — this cargo is LOST, not held. Set gap_reason "
            f"to the collision (do NOT call it 'held in hoard'), and next time "
            f"drop OFFSET onto the seam instead of the advertised cell."
        )
    return "\n".join(lines) + "\n"


# ── Doctrine assembly (v7 gating + v8 additions) ───────────────────────
def _assemble_doctrine(
    *,
    agent_view: Mapping[str, Any],
    day: int,
    day_cap: int,
    hot_drop_hints: Sequence[Mapping[str, Any]],
    wishlist: Wishlist,
    opponent_weapon_estimates: "Mapping[str, Any] | None",
    supersede_hints: Sequence[Mapping[str, Any]],
    is_setup_night: bool,
) -> str:
    """Assemble core doctrine + state-triggered appendices (v7 rules + v8 book)."""
    text = doctrine.STRATEGIES_CORE

    # REDSIGN + the new v8 POKER book — a public pure-RED beacon is live.
    redsign_present = bool(agent_view.get("redsign")) or any(
        isinstance(h, Mapping) and h.get("signal_type") == "redsign"
        for h in (hot_drop_hints or ())
    )
    if redsign_present:
        centers = _redsign_centers(agent_view)
        if centers:
            coord_str = ", ".join(f"(~{cx},~{cy})" for cx, cy in centers[:4])
            text += (
                f"\n\nREDSIGN LIVE near {coord_str} — a pure(255) RED seam is "
                f"PUBLIC (every seat sees it). Check VISIBLE RED for unfogged "
                f"pure/mass near there FIRST; else use the redsign HOT DROP "
                f"hints. Then apply:\n" + doctrine.DOCTRINE_REDSIGN
            )
        else:
            text += "\n\n" + doctrine.DOCTRINE_REDSIGN
        # v8: the honeypot opening book always rides with the redsign doctrine.
        text += "\n\n" + doctrine.DOCTRINE_REDSIGN_POKER

    # BLUE — setup night OR the orbit wishlist asked for blue.
    want_blue = any(
        getattr(e, "tag", "") == "grab_blue" for e in (wishlist.entries or [])
    )
    if is_setup_night or want_blue:
        text += "\n\n" + doctrine.DOCTRINE_BLUE

    # Weapons — jam that hit us last night forces reaction even if tracker cold.
    jam_events = _my_jam_events(agent_view)
    was_chaffed = any(str(e.get("type")) == "chaff_jam" for e in jam_events)
    was_empd = any(str(e.get("type")) == "emp_hit" for e in jam_events)
    if jam_events:
        from sea_of_colours.orchestrator_2.harnesses.tabula_v7.prompt import (
            _format_combat_event,
        )
        jam_lines = "; ".join(_format_combat_event(e) for e in jam_events[:3])
        text += (
            "\n\nTHREAT LAST NIGHT (react NOW): " + jam_lines +
            " Do NOT schedule a pickup in the jammed hours again — the opponent "
            "blind-fires the same predictable window. Pick up EARLY (hour <=4) "
            "or shift the window."
        )

    opp_has_emp = opp_has_chaff = False
    if opponent_weapon_estimates:
        opp_has_emp = any(
            getattr(e, "emps_max", 0) > 0
            for e in opponent_weapon_estimates.values()
        )
        opp_has_chaff = any(
            getattr(e, "chaff_max", 0) > 0
            for e in opponent_weapon_estimates.values()
        )
    # v8: whenever any weapon is in play, reframe it as an orbital strike.
    if opp_has_emp or opp_has_chaff or was_empd or was_chaffed:
        text += "\n\n" + doctrine.DOCTRINE_WEAPONS_ORBITAL
    if opp_has_emp or was_empd:
        text += "\n\n" + doctrine.DOCTRINE_BEWARE_EMP
    if opp_has_chaff or was_chaffed:
        text += "\n\n" + doctrine.DOCTRINE_BEWARE_CHAFF

    # FINAL NIGHT — supersede enemy probes.
    if int(day) >= int(day_cap) and supersede_hints:
        text += "\n\n" + doctrine.DOCTRINE_LASTDAY_SUPERSEDE

    return text


def build_prompt(
    *,
    agent_view: Mapping[str, Any],
    day: int,
    day_cap: int,
    vault_score: int,
    memory_replay: str,
    chain_hints: Sequence[Mapping[str, Any]],
    probe_hints: Sequence[Mapping[str, Any]] = (),
    hot_drop_hints: Sequence[Mapping[str, Any]] = (),
    blue_hints: Sequence[Mapping[str, Any]] = (),
    supersede_hints: Sequence[Mapping[str, Any]] = (),
    wishlist: "Wishlist | None" = None,
    opponent_weapon_estimates: "Mapping[str, Any] | None" = None,
    prior_day_entry: "Mapping[str, Any] | None" = None,
    mode: str = "mover",
    strategist_directive_block: str = "",
) -> str:
    """Assemble the tabula_v8 prompt as three labelled worldview sections.

    ``mode`` selects the closing contract ("mover" -> moves-first ACTION
    schema; "thinker" -> reasoning-first DECISION schema). The board-fact
    sections are shared between both passes.
    """
    wl = wishlist if wishlist is not None else Wishlist()
    setup_advisory = format_setup_night_advisory(agent_view, day, day_cap)
    is_setup_night = bool(setup_advisory.strip())

    doctrine_text = _assemble_doctrine(
        agent_view=agent_view,
        day=day,
        day_cap=day_cap,
        hot_drop_hints=hot_drop_hints,
        wishlist=wl,
        opponent_weapon_estimates=opponent_weapon_estimates,
        supersede_hints=supersede_hints,
        is_setup_night=is_setup_night,
    )

    directive_part = (
        ("\nSTRATEGIST DIRECTIVE (top-priority guidance from your reasoning "
         "pass — execute it):\n" + strategist_directive_block + "\n")
        if (mode == "mover" and strategist_directive_block)
        else ""
    )

    is_last_day = int(day) >= int(day_cap)
    last_night_block = format_last_night_block(agent_view)
    reflect_block = format_reflect_block(agent_view, prior_day_entry, day)
    opponent_block = format_opponent_block(agent_view)
    enemy_probes_block = format_enemy_probes_block(agent_view, day=day)
    weapons_block = format_opponent_weapons_block(opponent_weapon_estimates)
    geometry_block = format_weapon_geometry_block(opponent_weapon_estimates)
    wishlist_block = format_wishlist_block(wl)
    hot_drop_block = format_hot_drop_hints_block(hot_drop_hints)
    blue_block = format_blue_hints_block(blue_hints)

    parts: List[str] = []

    # Banner: setup-night alert rides above everything when it fires.
    if setup_advisory:
        parts += [setup_advisory, "\n"]

    # ── SECTION 1 — THE GAME ──────────────────────────────────────────
    parts += [
        _SECTION_1, "\n\n",
        rules.RULES_SUMMARY, "\n",
        doctrine_text, "\n",
        directive_part,
    ]

    # ── SECTION 2 — THE BOARD NOW ─────────────────────────────────────
    parts += [
        "\n", _SECTION_2, "\n\n",
        format_state_block(
            agent_view, day=day, day_cap=day_cap, vault_score=vault_score,
        ), "\n",
        format_visible_red_block(agent_view), "\n",
        format_drop_legal_block(agent_view), "\n",
        format_fog_and_echo_block(agent_view), "\n",
    ]
    if enemy_probes_block:
        parts += [enemy_probes_block, "\n"]
    if opponent_block:
        parts += [opponent_block, "\n"]
    if weapons_block:
        parts += [weapons_block]
    if geometry_block:
        parts += [geometry_block, "\n"]
    elif weapons_block:
        parts += ["\n"]
    if wishlist_block:
        parts += [wishlist_block, "\n"]
    parts += [
        format_chain_hints_block(chain_hints), "\n",
        format_probe_hints_block(probe_hints), "\n",
    ]
    if hot_drop_block:
        parts += [hot_drop_block, "\n"]
    if blue_block:
        parts += [blue_block, "\n"]
    if is_last_day and supersede_hints:
        parts += [format_supersede_hints_block(supersede_hints), "\n"]

    # ── SECTION 3 — WHAT HAPPENED LAST NIGHT ──────────────────────────
    parts += ["\n", _SECTION_3, "\n\n"]
    if last_night_block:
        parts += [last_night_block, "\n"]
    if reflect_block:
        parts += [reflect_block, "\n"]
    parts += [f"YOUR MEMORY (agent-authored, oldest first):\n{memory_replay}\n"]

    # ── Closing contract ──────────────────────────────────────────────
    if mode == "thinker":
        parts += [
            "\n", _THINKER_SCHEMA,
            "\nOUTPUT ONE JSON OBJECT NOW with \"reasoning\" FIRST (think "
            "there), then the decision fields. Start with the open-brace "
            "character. GO:\n",
        ]
    else:
        parts += [
            "\n", _ACTION_SCHEMA,
            "\nOUTPUT THE JSON OBJECT NOW. Start with the open-brace "
            "character. GO:\n",
        ]
    return "".join(parts)
