"""Prompt assembly for tabula_v9 — the COMPREHENSION restructure.

v9 keeps v8's three labelled worldview pillars and adds the comprehension
layer proven missing by the v8 audit:

  === SECTION 1 - THE GAME (how it works) ===
    RULES + DOCTRINE (core + state-triggered appendices, now including the
    COMPREHENSION note and the rewritten two-case redsign-poker book) + the
    STRATEGIST DIRECTIVE handoff (mover only, split mode).

  === SECTION 2 - THE BOARD NOW (what you see) ===
    YOUR STATE, VISIBLE RED, DROP-LEGAL, FOG+ECHO, ENEMY PROBES, EMP SCARS
    (new hazard), OPPONENT INTEL, OPPONENT WEAPONS + WEAPON GEOMETRY, wishlist,
    and the precomputed HINT menu.

  === SECTION 3 - WHAT HAPPENED LAST NIGHT (learn) ===
    The two-way WHAT HAPPENED digest (attacks TO you + denials BY you, with
    attribution + consequence — the keystone comprehension fix), the
    collision-aware LAST NIGHT block, the grounded REFLECT block (now forcing a
    consequence acknowledgment for probe/EMP/chaff loss, not just collisions),
    and MEMORY.

Battle-tested block formatters are imported verbatim from ``tabula_v7.prompt``
(pure functions over the agent view); v9 owns the digest-aware blocks and the
sectioned assembler. This is a true fork of the *feeding* layer that reuses
the *computation* layer.
"""

from __future__ import annotations

from typing import Any, List, Mapping, Sequence

from sea_of_colours.orchestrator_2.harnesses.tabula_v9 import (
    digest, doctrine, rules,
)
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
    _THINKER_SCHEMA,
)

_SECTION_1 = "=== SECTION 1 - THE GAME (how it works) ==="
_SECTION_2 = "=== SECTION 2 - THE BOARD NOW (what you can see right now) ==="
_SECTION_3 = "=== SECTION 3 - WHAT HAPPENED LAST NIGHT (learn from it) ==="

# v9 agency addendum to the (shared) v7 thinker schema: two extra, OPTIONAL
# fields the mover-side resolver consumes. Kept here (not in the frozen v7
# schema text) so v7/v8 thinkers are unchanged.
_V9_THINK_TASK = """\
=== YOUR TASK (THINK — reasoning only, this is the THINK pass) ===
You are the STRATEGIST for tonight. THINK the night through, then STOP:
  * Reflect on last night — what missed and WHY (name the real cause; do not
    over-generalise a collision on a DECOY cell into "always drop offset").
  * Read the REDSIGN: is it YOURS (CASE 1, mine=true) or a rival's (CASE 2)?
    Where is the pure(255), what is the seam worth, who is racing it?
  * Choose which OPTION MENU IDs you will select and in what execution order,
    plus any targets to prioritise / cells to avoid. When a pure(255) is
    reachable AND it is YOUR redsign, plan to DROP ON the pure (the landing cell
    is auto-harvested — that is free parcel #1) and bank it on a SHORT chain;
    only drop OFFSET when the cell is genuinely CONTESTED by rivals THIS night.
Output ONLY your analysis as CONCISE prose — no JSON, no move list, no headings.
Keep it under ~200 words. Reason, then stop; the next pass turns this into moves.
"""


_V9_PLAN_TASK = """\
=== YOUR TASK (COMMIT — decision only, this is the PLAN pass) ===
Turn the analysis above into a decision. Do NOT re-reason at length — you already
thought it through. Emit ONLY the decision fields, faithful to your analysis.
"""


# v9 MOVER output contract — MOVES ONLY. The thinker already reflected, planned,
# and reasoned (that prose is captured separately), so the mover must NOT rewrite
# any of it. Emitting only ``moves`` is what keeps the mover fast (the A4 fix:
# the shared v7 schema forced a wall of reflection/plan/rationale prose that cost
# 25-99s). Keep this in lock-step with tabula_v9/chat_schema._V9_MOVES_SCHEMA.
_V9_ACTION_SCHEMA = """\
OUTPUT CONTRACT — output ONE JSON object, MOVES ONLY. Start with the open-brace
character; NO prose before or after the JSON. Do NOT write any reflection, plan,
rationale, predicted-outcome, or memory fields — the reasoning is already done;
your ONLY job is to package it into moves. Fields:

  moves: list of wire-format actions, in execution order. Each is one of:
    {"a":"drop",   "unit":"harvester_p1", "at":[x,y]}
    {"a":"step",   "unit":"harvester_p1", "to":[x,y]}
    {"a":"pickup", "unit":"harvester_p1"}
    {"a":"probe",  "at":[x,y]}
  Chain grammar: drop -> step* -> pickup PER harvester. Probes anywhere.
  step "to" MUST be Manhattan-1 from the harvester's CURRENT cell: exactly ONE
  of (x+1,y),(x-1,y),(x,y+1),(x,y-1). NO diagonals, NO multi-cell jumps — list
  each intermediate cell as its own step. An illegal step is silently canceled
  and cascades into a crashed harvester at dawn.

  note: OPTIONAL one line — leave it out unless you had to CUT a low-priority
  plan item to fit the night; if so, name what you cut. Nothing else.
"""


_V9_THINKER_ADDENDUM = """\
=== v9 AGENCY FIELDS (put these RIGHT AFTER "posture", before "reasoning") ===
  "plan": ["ID", ...] — the OPTION MENU IDs you SELECT, in EXECUTION ORDER
      (e.g. ["SMASH_GRAB"] for CASE 1, or ["BLIND_GRAB","UNBEATEN_FLANK",
      "WALK_IN"] for CASE 2; add HDn/PRn/CHn/SSn for spare units). The geometry
      is pre-filled — you are choosing and ordering, not inventing coordinates.
      This is the MOST IMPORTANT field: it is what the mover executes. Emit it
      EARLY (right after posture) so it is never lost — an empty "plan" on a
      redsign night means the mover has nothing to execute and will misfire.
  "situational": {"mine": bool, "players": int, "chaff": bool, "emp": bool}
      — your read of the SITUATIONAL FACTS that justifies the plan. Fill it
      whenever a redsign is live.
  Leave "plan" empty (and omit "situational") only when NOTHING on the menu
  fits (rare); the mover then works from posture/targets as before.
"""


# ── Board blocks carried from v8 ───────────────────────────────────────
def format_enemy_probes_block(
    agent_view: Mapping[str, Any], *, day: int,
) -> str:
    """First-class ENEMY PROBES block (from v8 §4c).

    An enemy probe launch is PUBLIC (§3.15). Promotes these to a standing
    block on EVERY night so the agent can route around them, stage behind
    them, or supersede them, and so it understands a rival can hot-drop into
    these disks (the collision risk on a shared cell).
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
    """WEAPON GEOMETRY constants (from v8 §4d).

    Only rendered when some opponent is estimated to hold EMP or chaff, so the
    agent reasons about EMP as a targeted orbital strike with a KNOWN blast
    radius on a known beacon — not a distance-from-a-cluster gamble.
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


def format_orbit_directives_block(wishlist: "Wishlist | None") -> str:
    """v9 ORBIT DIRECTIVES block — crisp imperatives from the orbit turn.

    Renders ``Wishlist.directives`` (need_blue / vault-nearly-full / conserve),
    the explicit orbit->night channel. Empty when the orbit turn had no
    directive for tonight.
    """
    directives = list(getattr(wishlist, "directives", None) or [])
    if not directives:
        return ""
    lines = ["ORBIT DIRECTIVES (act on these tonight):"]
    for d in directives[:5]:
        lines.append(f"  - {d}")
    return "\n".join(lines) + "\n"


def format_hint_tactics_block(
    hot_drop_hints: Sequence[Mapping[str, Any]],
    probe_hints: Sequence[Mapping[str, Any]],
) -> str:
    """v9 TACTICAL OPTIONS block — surface the ranked/contested hint metadata.

    The shared compilers now tag each hint ``contested`` and attach ranked
    seam OFFSETS (``alt_drops``) + a ``supersede`` option. This block turns
    that into a short menu so the agent makes contested placement a deliberate
    choice (offset onto the seam / blind the finder) instead of blindly diving
    the single advertised cell. Empty when nothing is contested.
    """
    def _xy(v: Any) -> "str | None":
        if isinstance(v, (list, tuple)) and len(v) == 2:
            return f"({int(v[0])},{int(v[1])})"
        return None

    lines: List[str] = []
    for h in hot_drop_hints or []:
        if not isinstance(h, Mapping) or not h.get("contested"):
            continue
        sig = str(h.get("signal_type") or "signal")

        # CASE 1 — this redsign is OURS: we know the pure cell, move first.
        if h.get("mine") is True:
            drop_s = _xy(h.get("drop_at")) or "the pure"
            lines.append(
                f"  YOUR {sig} (CASE 1) — you discovered this seam, so you know "
                f"where the pure is. SMASH-AND-GRAB: drop on/adjacent {drop_s} "
                f"wave 1 before rivals arrive."
            )
            continue

        # CASE 2 — a rival's / unclaimed contested beacon. Each seat is assigned
        # a DIFFERENT seam offset so we fan out instead of stacking.
        assigned = _xy(h.get("seat_offset"))
        if assigned:
            parts = [
                f"  CONTESTED {sig} (CASE 2) — everyone races the advertised "
                f"cell and COLLIDES (0 banked). YOUR ASSIGNED approach is "
                f"{assigned} (rivals get different seam cells) — drop THERE, "
                f"not on the beacon."
            ]
        else:
            drop_s = _xy(h.get("drop_at")) or "?"
            parts = [
                f"  CONTESTED {sig} (CASE 2) at {drop_s} — everyone races this "
                f"cell; a shared drop COLLIDES (0 banked)."
            ]
        alts = [a for a in (h.get("alt_drops") or [])
                if isinstance(a, (list, tuple)) and len(a) == 2]
        # Show the fallback seam cells AFTER the assigned lead (already rotated).
        fallback = ", ".join(f"({int(a[0])},{int(a[1])})" for a in alts[1:]) \
            if assigned else ", ".join(f"({int(a[0])},{int(a[1])})" for a in alts)
        if fallback:
            parts.append(f"    -> other seam cells if blocked: {fallback}")
        sup = h.get("supersede")
        if isinstance(sup, (list, tuple)) and len(sup) == 2:
            parts.append(
                f"    -> or SUPERSEDE the finder's probe at "
                f"({int(sup[0])},{int(sup[1])}) to blind them first"
            )
        lines.extend(parts)

    contested_probes = [
        h for h in (probe_hints or [])
        if isinstance(h, Mapping) and h.get("contested")
    ]
    for h in contested_probes:
        at = h.get("at")
        at_s = (
            f"({int(at[0])},{int(at[1])})"
            if isinstance(at, (list, tuple)) and len(at) == 2 else "?"
        )
        lines.append(
            f"  CONTESTED probe placement {at_s} — near a public beacon or an "
            f"enemy probe; expect company, plan redundancy."
        )

    if not lines:
        return ""
    return "TACTICAL OPTIONS (contested cells — choose deliberately):\n" + \
        "\n".join(lines) + "\n"


def format_situational_facts_block(
    agent_view: Mapping[str, Any],
    player_count: int,
    opponent_weapon_estimates: "Mapping[str, Any] | None",
) -> str:
    """v9 SITUATIONAL FACTS — the ground truth the thinker must reason over.

    Surfaces exactly the four dials the thinker echoes back in ``situational``
    (mine? / players / chaff / emp) so its structured read is GROUNDED, not
    guessed. ``mine`` is engine truth; chaff/emp fuse "seen last night" (recap)
    with "estimated in stock" (opponent inference). Rendered only in the thinker
    pass. Always non-empty (it anchors the decision even off-seam).
    """
    any_mine, any_not = _redsign_ownership(agent_view)
    if any_mine and any_not:
        mine_s = "mixed (you own at least one beacon, a rival owns another)"
    elif any_mine:
        mine_s = "true (a live REDSIGN is YOURS -> CASE 1)"
    elif any_not:
        mine_s = "false (the live REDSIGN is a rival's -> CASE 2)"
    else:
        mine_s = "n/a (no live redsign)"

    ln = agent_view.get("last_night") or {}
    chaff_seen = any(
        "chaff" in str(a.get("type") or "").lower()
        for a in (ln.get("incoming_attacks") or [])
        if isinstance(a, Mapping)
    )
    emp_seen = bool(ln.get("emp_scars"))
    est_emp = est_chaff = False
    for e in (opponent_weapon_estimates or {}).values():
        if getattr(e, "emps_max", 0) > 0:
            est_emp = True
        if getattr(e, "chaff_max", 0) > 0:
            est_chaff = True

    def _w(seen: bool, est: bool) -> str:
        if seen:
            return "YES (hit you last night)"
        if est:
            return "possible (a rival is estimated to hold stock)"
        return "none observed"

    players_s = str(player_count) if player_count else "unknown"
    return (
        "SITUATIONAL FACTS (reason over these; echo them back in "
        "\"situational\"):\n"
        f"  mine: {mine_s}\n"
        f"  players: {players_s}\n"
        f"  chaff: {_w(chaff_seen, est_chaff)}\n"
        f"  emp: {_w(emp_seen, est_emp)}\n"
    )


def format_last_night_block(agent_view: Mapping[str, Any]) -> str:
    """v9 LAST NIGHT block — v7's engine record PLUS the collision channel.

    The collision lines are the keystone fix: a simultaneous-drop pile-up
    banks ZERO and shows up in no other channel. Sourced from the fog-safe
    ``last_night.my_collisions``. (The richer two-way attack narrative lives
    in the WHAT HAPPENED digest block above this.)
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
    """v9 grounded REFLECT — v7's block PLUS forced consequence acknowledgment.

    v7's reflect frames a 0 shipped-change with a healthy harvest as "held, not
    lost". On a night with a COLLISION or an incoming ATTACK (probe kill / EMP /
    chaff) that framing is wrong — cargo/vision was genuinely LOST. So when such
    an event is on record we append a hard "this was a LOSS, name the cause"
    line the model must acknowledge, defeating the confabulation seen in the v8
    audit ("thin seam" / "held not lost").
    """
    base = _v7_reflect_block(agent_view, prior_day_entry, day)
    ln = agent_view.get("last_night") or {}
    collisions = ln.get("my_collisions") or []
    incoming = ln.get("incoming_attacks") or []
    banked = ln.get("my_parcels_banked") or []
    if not collisions and not incoming and not banked:
        return base

    prior_day = int(day) - 1
    lines: List[str] = []
    if not base.strip():
        lines.append(
            f"REFLECT ON LAST NIGHT (day {prior_day}) — engine ground truth:"
        )
    else:
        lines.append(base.rstrip("\n"))

    # ANCHOR (anti-confabulation): a cell you HARVESTED last night is now SPENT,
    # so it shows GREEN / '! AVOID' in TODAY's drop-legal zones. The audit caught
    # the seat reading that current-green state and RETROJECTING it onto last
    # night's drop ("(15,4) hit synthetic-green, crashed the chain") when the
    # record plainly says it dropped there and auto-harvested RED. Anchor the
    # reflection to my_parcels_banked so it stops inverting a success into a crash.
    if banked:
        cells = ", ".join(
            f"({b.get('from', [None, None])[0]},{b.get('from', [None, None])[1]})"
            for b in banked[:6] if isinstance(b, Mapping)
        )
        lines.append(
            "  ANCHOR TO THE RECORD: my_parcels_banked lists cells you HARVESTED "
            f"last night ({cells}). You banked those — you did NOT crash or hit "
            "green there. A cell you harvest becomes SPENT and shows GREEN / "
            "'! AVOID' in TODAY's drop-legal zones: that is the SUCCESS signature "
            "of a completed harvest, NOT evidence of a green crash. Never infer a "
            "past crash from a cell being green today — trust the LAST NIGHT "
            "engine record over the current map state."
        )

    for c in collisions[:3]:
        if not isinstance(c, Mapping):
            continue
        at = c.get("at") or [None, None]
        others = c.get("others") or []
        at_s = f"[{at[0]},{at[1]}]" if at and at[0] is not None else "the beacon"
        who = f" with {others}" if others else " with rivals"
        lines.append(
            f"  COLLISION LOSS: a harvester collided at {at_s}{who} and banked "
            f"ZERO — this cargo is LOST, not held. Set gap_reason to the "
            f"collision (NOT 'held in hoard'). The trap was diving a CONTESTED "
            f"advertised cell blind at the same hour as rivals — the fix is to "
            f"fan out / stagger your wave timing, NOT to abandon the pure. On "
            f"YOUR redsign still SECURE the pure (that is what SMASH_GRAB does — "
            f"drop on the seam core); only offset OFF a cell rivals are "
            f"contesting THIS night."
        )
    for a in incoming[:3]:
        if not isinstance(a, Mapping):
            continue
        atype = str(a.get("type", "")).replace("_", " ")
        by = ", ".join(str(b) for b in (a.get("by") or [])) or "a rival"
        cons = str(a.get("consequence") or "").strip()
        lines.append(
            f"  LOSS TO ACKNOWLEDGE ({atype} by {by}): {cons} Set gap_reason "
            f"to THIS cause — do not confabulate a 'thin seam' or call lost "
            f"cargo 'held'."
        )
    return "\n".join(lines) + "\n"


# ── Doctrine assembly (v7 gating + v9 additions) ───────────────────────
def _alive_harvester_count(agent_view: Mapping[str, Any]) -> int:
    """Count the reading seat's alive harvesters (orbit + surface)."""
    entities = (agent_view.get("entities") or {}).get("mine") or []
    return sum(
        1 for e in entities
        if isinstance(e, Mapping) and str(e.get("type") or "") == "harvester"
    )


def _probe_stock(agent_view: Mapping[str, Any]) -> int:
    """Probes available to LAUNCH from orbit this night (0 if none)."""
    try:
        return int((agent_view.get("orbit") or {}).get("probe_stock") or 0)
    except (TypeError, ValueError):
        return 0


def _redsign_ownership(agent_view: Mapping[str, Any]) -> "tuple[bool, bool]":
    """Return (any_mine, any_not_mine) over the live redsign regions."""
    any_mine = any_not = False
    for r in agent_view.get("redsign") or []:
        if not isinstance(r, Mapping):
            continue
        if r.get("mine"):
            any_mine = True
        else:
            any_not = True
    return any_mine, any_not


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
    mover_has_recipe: bool = False,
) -> str:
    """Assemble core doctrine + state-triggered appendices (v7 gating + v9).

    When ``mover_has_recipe`` the reading pass is the MOVER holding the thinker's
    committed EXECUTE-THIS-PLAN recipe: the planning doctrines that tempt it to
    ADD units (full-utilization) are replaced by a short "package, don't add"
    note so it stops re-planning the fleet.
    """
    text = doctrine.STRATEGIES_CORE

    # COMPREHENSION — fires whenever something attributable happened to/by us.
    ln = agent_view.get("last_night") or {}
    if (ln.get("incoming_attacks") or ln.get("my_denials")
            or ln.get("my_collisions")):
        text += "\n\n" + doctrine.DOCTRINE_COMPREHENSION

    # REDSIGN + the v9 two-case POKER book — a public pure-RED beacon is live.
    redsign_present = bool(agent_view.get("redsign")) or any(
        isinstance(h, Mapping) and h.get("signal_type") == "redsign"
        for h in (hot_drop_hints or ())
    )
    if redsign_present:
        # ONE redsign doctrine surface (hyg-dedup/hyg-contradictions): a compact
        # locator, then v9's authoritative REDSIGN POKER + DROP-ON-VALUE below.
        # The legacy v7 DOCTRINE_REDSIGN is intentionally NOT included — it
        # conflicted ("long chain, not a 1-cell snatch" / "land ADJACENT") with
        # v9's drop-on-value + agent-owns-length doctrine.
        centers = _redsign_centers(agent_view)
        if centers:
            coord_str = ", ".join(f"(~{cx},~{cy})" for cx, cy in centers[:4])
            text += (
                f"\n\nREDSIGN LIVE near {coord_str} — a pure(255) RED seam is "
                f"PUBLIC (every seat sees it). The broadcast coord is a JITTERED "
                f"smear, not the exact pure. Check VISIBLE RED / ECHO for unfogged "
                f"pure/mass near there FIRST; else use the redsign HOT DROP / "
                f"SMASH_GRAB geometry from the menu. Play it by the two cases below:"
            )
        else:
            text += (
                "\n\nREDSIGN LIVE — a pure(255) RED seam is PUBLIC. Play it by "
                "the two cases below:"
            )
        # v9: point the agent at the right CASE using engine-truth ownership.
        any_mine, any_not = _redsign_ownership(agent_view)
        if any_mine and not any_not:
            text += (
                "\n\nOWNERSHIP: a live REDSIGN is YOURS -> play CASE 1 (you "
                "know the pure cell; smash-and-grab wave 1)."
            )
        elif any_not and not any_mine:
            text += (
                "\n\nOWNERSHIP: the live REDSIGN is NOT yours -> play CASE 2 "
                "(blind the finder's probe first, then fight for the seam)."
            )
        elif any_mine and any_not:
            text += (
                "\n\nOWNERSHIP: mixed — at least one REDSIGN is yours (CASE 1) "
                "and one is a rival's (CASE 2); pick per beacon."
            )
        text += "\n\n" + doctrine.DOCTRINE_REDSIGN_POKER

    # DROP-ON-VALUE (I13/F7) — teach the auto-harvest of the landing cell +
    # secure-the-pure-short whenever there is real value to grab (a redsign in
    # play, or hot-drop hints pointing at a value cluster). Off-seam quiet nights
    # skip it to keep the mover's attention budget lean.
    high_value_drop = redsign_present or bool(hot_drop_hints)
    if high_value_drop:
        text += "\n\n" + doctrine.DOCTRINE_DROP_ON_VALUE

    # FULL UTILIZATION — fires on a multi-harvester night (the "deploy every
    # harvester" modus operandi). Single-harvester nights skip it (nothing to
    # spread) to keep the doctrine lean. The MOVER holding a committed recipe gets
    # a "package, don't add" note INSTEAD — the thinker already sized the fleet,
    # and leaving full-utilization in tempts the mover to bolt on off-menu units.
    alive_harvesters = _alive_harvester_count(agent_view)
    if alive_harvesters >= 2:
        # A7: state the EXACT alive count as a hard fact. The agent kept
        # hallucinating a phantom "three harvesters available" when only two
        # were alive (a crashed/idle unit does not exist tonight), then planned
        # a third chain that dissolved. Anchor the plan to the real roster.
        fleet_fact = (
            f"\n\nFLEET TONIGHT: you have {alive_harvesters} harvester(s) ALIVE "
            "and usable this night (the fleet maximum is 3, but only the alive "
            f"units count — plan for {alive_harvesters}, no phantom extra unit)."
        )
        if mover_has_recipe:
            text += fleet_fact + (
                " FLEET ALREADY SIZED: your reasoning pass already decided how "
                "many units to deploy and to what (see EXECUTE THIS PLAN). PACKAGE "
                "that plan — do NOT add an extra harvester drop or probe to 'use "
                "every unit'. An unused unit the plan left in orbit is deliberate."
            )
        else:
            text += fleet_fact + "\n\n" + doctrine.DOCTRINE_FULL_UTILIZATION

    # MULTIPROBE — spend AND spread spare probe stock for next-night vision.
    # Fires in the THINKER path (the plan is what sizes the probes); the mover
    # holding a recipe is told separately not to add units, so it is skipped
    # there. Keyed to actual stock so a lean 0-1 probe night stays quiet. This is
    # the fix for the "dogpile every probe on the current seam / leave stock
    # idle" pattern — the thinker was selecting one PR while 3-4 sat in orbit.
    probe_stock = _probe_stock(agent_view)
    is_final_night = int(day) >= int(day_cap)
    if not mover_has_recipe and probe_stock >= 2:
        # A6: only offer the "SS instead of PR" weaponisation on the ACTUAL final
        # night. On every earlier night a spare probe buys tomorrow's vision, so
        # naming the final-night option here primed the day-5 "final night"
        # hallucination (it superseded instead of scouting with days still left).
        if is_final_night:
            spend_hint = (
                "put a PR (or an SS to blind a rival — it is the final night) id "
                "in \"plan\" for the spare ones"
            )
        else:
            nights_left = int(day_cap) - int(day)
            spend_hint = (
                f"put a PR id in \"plan\" for the spare ones — this is night "
                f"{int(day)} of {int(day_cap)} ({nights_left} night(s) LEFT, NOT "
                "the final night), so a scouting probe still buys tomorrow's "
                "vision; do NOT waste stock on final-night-only supersedes"
            )
        text += (
            f"\n\nPROBE STOCK TONIGHT: {probe_stock} probe(s) ready to launch "
            f"from orbit — {spend_hint}, spread across NEW ground.\n"
            + doctrine.DOCTRINE_MULTIPROBE
        )

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
    # v9: whenever any weapon is in play, reframe it as an orbital strike.
    if opp_has_emp or opp_has_chaff or was_empd or was_chaffed:
        text += "\n\n" + doctrine.DOCTRINE_WEAPONS_ORBITAL
    if opp_has_emp or was_empd:
        text += "\n\n" + doctrine.DOCTRINE_BEWARE_EMP
    if opp_has_chaff or was_chaffed:
        text += "\n\n" + doctrine.DOCTRINE_BEWARE_CHAFF

    # FINAL NIGHT — supersede enemy probes. Gated to the ACTUAL final night
    # (A6): earlier nights must not see this or the agent starts declaring
    # "final night" and burning probes on denial while scouting still pays.
    if is_final_night and supersede_hints:
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
    option_menu_block: str = "",
    player_count: int = 0,
    think_analysis: str = "",
) -> str:
    """Assemble the tabula_v9 prompt as three labelled worldview sections.

    ``mode`` selects the closing contract ("mover" -> moves-first ACTION
    schema; "thinker" -> reasoning-first DECISION schema). The board-fact
    sections are shared between both passes.
    """
    wl = wishlist if wishlist is not None else Wishlist()
    setup_advisory = format_setup_night_advisory(agent_view, day, day_cap)
    is_setup_night = bool(setup_advisory.strip())

    # The MOVER holding the thinker's committed recipe is a PACKAGER: it keeps the
    # board facts it needs for LEGALITY (visible red, drop-legal) but loses the
    # blocks that tempt it to RE-TARGET (raw hot-drops, tactics, chain/probe/blue
    # hints, and the fog/echo frontier menu) and the full-utilization doctrine.
    mover_has_recipe = mode == "mover" and bool(strategist_directive_block)

    doctrine_text = _assemble_doctrine(
        agent_view=agent_view,
        day=day,
        day_cap=day_cap,
        hot_drop_hints=hot_drop_hints,
        wishlist=wl,
        opponent_weapon_estimates=opponent_weapon_estimates,
        supersede_hints=supersede_hints,
        is_setup_night=is_setup_night,
        mover_has_recipe=mover_has_recipe,
    )

    directive_part = (
        ("\nSTRATEGIST DIRECTIVE (top-priority guidance from your reasoning "
         "pass — execute it):\n" + strategist_directive_block + "\n")
        if (mode == "mover" and strategist_directive_block)
        else ""
    )

    is_last_day = int(day) >= int(day_cap)
    event_digest_block = digest.format_event_digest_block(agent_view)
    emp_scars_block = digest.format_emp_scars_block(agent_view)
    last_night_block = format_last_night_block(agent_view)
    reflect_block = format_reflect_block(agent_view, prior_day_entry, day)
    opponent_block = format_opponent_block(agent_view)
    enemy_probes_block = format_enemy_probes_block(agent_view, day=day)
    weapons_block = format_opponent_weapons_block(opponent_weapon_estimates)
    geometry_block = format_weapon_geometry_block(opponent_weapon_estimates)
    wishlist_block = format_wishlist_block(wl)
    directives_block = format_orbit_directives_block(wl)
    hot_drop_block = format_hot_drop_hints_block(hot_drop_hints)
    tactics_block = format_hint_tactics_block(hot_drop_hints, probe_hints)
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
    ]
    # FOG & ECHO is a frontier TARGET menu (edge_promise, echo clusters). The
    # mover holding a recipe must not re-target, so hide it — this is the exact
    # block it mined for the off-menu frontier hot-drop. Keep it for the thinker
    # and for recipe-less mover nights.
    if not mover_has_recipe:
        parts += [format_fog_and_echo_block(agent_view), "\n"]
    if enemy_probes_block:
        parts += [enemy_probes_block, "\n"]
    if emp_scars_block:
        parts += [emp_scars_block, "\n"]
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
    if directives_block:
        parts += [directives_block, "\n"]
    # Chain / probe hints are TARGET menus too — the mover repurposed a probe hint
    # into an off-menu drop. Hide them when it holds a recipe; the thinker keeps
    # them for planning.
    if not mover_has_recipe:
        parts += [
            format_chain_hints_block(chain_hints), "\n",
            format_probe_hints_block(probe_hints), "\n",
        ]
    # When the MOVER has already been handed an EXECUTE-THIS-PLAN recipe from the
    # thinker, hide the raw hot-drop combos (each carries a "READY COMB" the
    # mover is tempted to copy verbatim), the tactics block, and the blue-hint
    # target menu. The recipe already encodes the chosen drops + combs; these are
    # re-targeting bait. (mover_has_recipe is computed once, above.)
    if hot_drop_block and not mover_has_recipe:
        parts += [hot_drop_block, "\n"]
    if tactics_block and not mover_has_recipe:
        parts += [tactics_block, "\n"]
    if blue_block and not mover_has_recipe:
        parts += [blue_block, "\n"]
    if is_last_day and supersede_hints:
        parts += [format_supersede_hints_block(supersede_hints), "\n"]

    # ── SECTION 3 — WHAT HAPPENED LAST NIGHT ──────────────────────────
    parts += ["\n", _SECTION_3, "\n\n"]
    if event_digest_block:
        parts += [event_digest_block, "\n"]
    if last_night_block:
        parts += [last_night_block, "\n"]
    if reflect_block:
        parts += [reflect_block, "\n"]
    parts += [f"YOUR MEMORY (agent-authored, oldest first):\n{memory_replay}\n"]

    # ── Closing contract ──────────────────────────────────────────────
    # The CONTAINED TWO-STAGE thinker (mode="think" then mode="plan") replaces
    # the single reasoning-first "thinker" call: stage 1 THINKS on its own hard
    # token budget (bounded prose, no decision to starve), stage 2 turns that
    # bounded analysis into the compact decision JSON on its own budget (so the
    # plan ALWAYS lands, conditioned on real reasoning). "thinker" is kept for
    # the legacy single-call path / tests.
    if mode in ("thinker", "think", "plan"):
        # Agency layer: the grounded situational facts + the ID'd option menu
        # the thinker SELECTS from (echoed into "plan"). Rendered right before
        # the closing so they are the last thing it reads before it reasons.
        situational_block = format_situational_facts_block(
            agent_view, player_count, opponent_weapon_estimates,
        )
        parts += ["\n", situational_block]
        if option_menu_block:
            parts += ["\n", option_menu_block]
        if mode == "think":
            parts += ["\n", _V9_THINK_TASK]
        elif mode == "plan":
            parts += [
                "\n=== YOUR ANALYSIS (from your think pass — commit it now) ===\n",
                "<<<\n", (think_analysis or "").strip(), "\n>>>\n",
                _V9_PLAN_TASK,
                "\n", _V9_THINKER_ADDENDUM,
                "\nOUTPUT ONE JSON OBJECT NOW — DECISION FIRST: \"posture\", then "
                "\"plan\" (the OPTION MENU IDs from your analysis, in execution "
                "order), then \"situational\" when a REDSIGN is live; a SHORT "
                "\"reasoning\" LAST. Start with the open-brace character. GO:\n",
            ]
        else:  # legacy single-call "thinker"
            parts += [
                "\n", _THINKER_SCHEMA,
                "\n", _V9_THINKER_ADDENDUM,
                "\nOUTPUT ONE JSON OBJECT NOW — DECISION FIRST: \"posture\", then "
                "\"plan\" (the OPTION MENU IDs in execution order), then "
                "\"situational\" when a REDSIGN is live; a SHORT \"reasoning\" "
                "goes LAST. Start with the open-brace character. GO:\n",
            ]
    else:
        parts += [
            "\n", _V9_ACTION_SCHEMA,
            "\nOUTPUT THE JSON OBJECT NOW. Start with the open-brace "
            "character. GO:\n",
        ]
    return "".join(parts)
