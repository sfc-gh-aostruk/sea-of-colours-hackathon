"""Orbital candidate compiler + composer for PILOT_V3.

Mirrors the shape of :mod:`.combat` but for the orbit phase (RULEBOOK §4).

Contract:

* Public entry :func:`compile_orbit_candidates(agent_view) -> Dict` emits a
  single ``orbital`` block with candidate menus + a ``recommended_orbit_policy``
  that fills all ``MAX_ORBIT_ACTIONS`` slots the engine allows.
* Priority ladder (doctrine — user-defined):

    1. Vault at cap / imminent overflow  → ship or refine (jumps queue)
    2. Damaged harvester                  → repair
    3. Probe stock < target               → build probes (batched into 1 slot)
    4. Harvester expansion                → good RED visible + affordable
                                             OR flush with cash
    5. BLUE ≥ 200 + valid weapon target   → build EMP / chaff / mine
    6. Baseline: ship vein+ parcel
    7. Baseline: refine trace → vein (or vein → mass)
    8. Baseline: trace-fuelled green catapult (dump junk)

  Slots are ALWAYS fully spent — nothing is gated off. If Tier 1 isn't
  active, remaining slots fall through to Tier 6/7/8 baseline spends.

The block the agent reads is a MENU. It may reason within doctrine to
swap a slot (e.g. drop the baseline refine for a second harvester build
under aggressive posture), but the composed default is always 3 actions.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence


# ── Constants (mirrored from engine so we don't depend on session at
# candidate-compile time). ─────────────────────────────────────────
HARVESTER_BUILD_COST: int = 1500
PROBE_BUILD_COST: int = 250
REPAIR_COST: int = 500

EMP_COST_BLUE: int = 200
EMP_COST_CREDITS: int = 250
CHAFF_COST_BLUE: int = 255
CHAFF_COST_CREDITS: int = 0
MINE_COST_BLUE: int = 100
MINE_COST_CREDITS: int = 100

REFINE_BLUE_TRACE: int = 10  # per input parcel
REFINE_BLUE_VEIN: int = 20   # per input parcel

MAX_ORBIT_ACTIONS: int = 3

# Doctrine knobs — kept as module-level so they can be tuned without
# recompiling doctrine into the agent spec.
PROBE_TARGET_STOCK: int = 4
VAULT_PRESSURE_THRESHOLD: float = 0.80  # ≥ 12/15 → escalate ship/refine
GOOD_RED_SCORE_MIN: int = 500  # visible RED score to justify harvester buy
FLUSH_CREDITS_THRESHOLD: int = 3000  # buy harvester even without red
VEIN_MIN_PURITY: int = 51
MASS_MIN_PURITY: int = 151
BLUE_WEAPON_MIN: int = 200  # min BLUE to consider offensive spend
SHIP_BID_PER_PARCEL: int = 25  # credit bid per parcel on catapult


# ── State extraction helpers ─────────────────────────────────────
def _get_orbit_block(agent_view: Mapping[str, Any]) -> Mapping[str, Any]:
    ob = agent_view.get("orbit")
    return ob if isinstance(ob, Mapping) else {}


def _get_my_harvesters(agent_view: Mapping[str, Any]) -> List[Dict[str, Any]]:
    entities = (agent_view.get("entities") or {}).get("mine") or []
    return [e for e in entities if e.get("type") == "harvester"]


def _visible_red_score(agent_view: Mapping[str, Any]) -> int:
    """Sum of visible RED purity, weighted lightly by tier.

    Cheap proxy for "is there somewhere worthwhile to deploy?". Pure
    counts most; mass moderate; trace ignored. Used to decide whether
    building a new harvester is worthwhile.
    """
    nav = agent_view.get("navigation") or {}
    reds = nav.get("best_red_visible") or agent_view.get("red_tiles") or []
    total = 0
    for r in reds:
        try:
            purity = int(r.get("value") or r.get("purity") or 0)
        except (TypeError, ValueError):
            continue
        if purity >= 255:
            total += purity * 3
        elif purity >= MASS_MIN_PURITY:
            total += purity * 2
        elif purity >= VEIN_MIN_PURITY:
            total += purity
        # trace ignored
    return total


def _enemy_probes_visible(agent_view: Mapping[str, Any]) -> int:
    ci = agent_view.get("competitor_intel") or {}
    n_new = len(ci.get("new_this_day") or [])
    n_echo = len(ci.get("persistent_echoes") or [])
    return int(n_new + n_echo)


# ── Individual candidate blocks ──────────────────────────────────
def _repair_candidates(agent_view: Mapping[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for h in _get_my_harvesters(agent_view):
        if not bool(h.get("damaged")):
            continue
        uid = str(h.get("id") or "")
        out.append({
            "unit_id": uid,
            "cost": REPAIR_COST,
            "action": {"a": "repair", "unit": uid},
            "reason": (
                f"{uid} is damaged — blocking night-phase harvest. "
                f"Repair now to restore play capability."
            ),
        })
    return out


def _probe_purchase(agent_view: Mapping[str, Any]) -> Dict[str, Any]:
    ob = _get_orbit_block(agent_view)
    stock = int(ob.get("probe_stock", 0) or 0)
    credits = int(ob.get("credits", 0) or 0)
    want = max(0, PROBE_TARGET_STOCK - stock)
    affordable = credits // PROBE_BUILD_COST if PROBE_BUILD_COST > 0 else 0
    buy_count = int(min(want, affordable))
    if buy_count >= 1:
        action = {"a": "build_probe", "count": buy_count} if buy_count > 1 \
            else {"a": "build_probe"}
        verdict = "buy"
    elif want <= 0:
        action = None
        verdict = "already_at_target"
    else:
        action = None
        verdict = "unaffordable"
    return {
        "stock": stock,
        "target": PROBE_TARGET_STOCK,
        "cost_per": PROBE_BUILD_COST,
        "buy_count": buy_count,
        "total_cost": buy_count * PROBE_BUILD_COST,
        "action": action,
        "verdict": verdict,
    }


def _harvester_purchase(agent_view: Mapping[str, Any]) -> Dict[str, Any]:
    ob = _get_orbit_block(agent_view)
    credits = int(ob.get("credits", 0) or 0)
    cap_used = int(ob.get("harvester_cap_used", 0) or 0)
    cap_max = int(ob.get("harvester_cap_max", 999) or 999)
    visible_red = _visible_red_score(agent_view)
    at_cap = cap_used >= cap_max
    affordable = credits >= HARVESTER_BUILD_COST
    good_red = visible_red >= GOOD_RED_SCORE_MIN
    flush = credits >= FLUSH_CREDITS_THRESHOLD
    # v3 aggression patch (2025-07-14): when fleet dips below 2
    # harvesters the game is effectively lost — no drops, no RED
    # banked. Rebuild is the #1 priority regardless of visible RED or
    # credit flush. The strategist doctrine calls this `fleet_rebuild`
    # and expects it to fire automatically.
    fleet_thin = cap_used < 2
    if at_cap:
        verdict = "at_fleet_cap"
        action = None
    elif not affordable:
        verdict = "unaffordable"
        action = None
    elif fleet_thin:
        verdict = "buy"  # fleet under 2 — always rebuild if we can
        action = {"a": "build_harvester"}
    elif good_red:
        verdict = "buy"  # good red visible AND affordable
        action = {"a": "build_harvester"}
    elif flush:
        verdict = "buy"  # flush cash even without red — expand for future turns
        action = {"a": "build_harvester"}
    else:
        verdict = "hold"  # affordable but no deploy target and not flush
        action = None
    return {
        "cost": HARVESTER_BUILD_COST,
        "credits_available": credits,
        "credit_headroom": credits - HARVESTER_BUILD_COST,
        "fleet": f"{cap_used}/{cap_max}",
        "fleet_thin": fleet_thin,
        "visible_red_score": visible_red,
        "good_red_threshold": GOOD_RED_SCORE_MIN,
        "flush_threshold": FLUSH_CREDITS_THRESHOLD,
        "action": action,
        "verdict": verdict,
    }


def _weapon_purchase(
    agent_view: Mapping[str, Any],
    weapon: str,
    blue_cost: int,
    credit_cost: int,
) -> Dict[str, Any]:
    ob = _get_orbit_block(agent_view)
    blue = int(ob.get("blue_purity_total", 0) or 0)
    credits = int(ob.get("credits", 0) or 0)
    stock_key = weapon  # emp | chaff | mine
    stock = int((ob.get("weapon_stock") or {}).get(stock_key, 0) or 0)
    enemy_visible = _enemy_probes_visible(agent_view)
    affordable = blue >= blue_cost and credits >= credit_cost
    has_target = enemy_visible >= 1
    if not affordable:
        verdict = "unaffordable"
        action = None
    elif not has_target and weapon == "emp":
        # EMP needs a target to be worth building; chaff/mine can be
        # built proactively even without immediate target.
        verdict = "no_target"
        action = None
    else:
        verdict = "buy"
        action = {"a": f"build_{weapon}"}
    return {
        "weapon": weapon,
        "blue_cost": blue_cost,
        "credit_cost": credit_cost,
        "blue_available": blue,
        "credits_available": credits,
        "stock": stock,
        "enemy_visible": enemy_visible,
        "action": action,
        "verdict": verdict,
    }


def _ship_candidates(agent_view: Mapping[str, Any]) -> Dict[str, Any]:
    ob = _get_orbit_block(agent_view)
    parcels = list(ob.get("hoard_parcels") or [])
    credits = int(ob.get("credits", 0) or 0)
    vein_plus: List[Dict[str, Any]] = []
    for p in parcels:
        colour = str(p.get("colour", "")).upper()
        if colour != "RED":
            continue
        try:
            purity = int(p.get("purity", 0) or 0)
        except (TypeError, ValueError):
            purity = 0
        if purity >= VEIN_MIN_PURITY:
            vein_plus.append(p)
    ranked = sorted(vein_plus, key=lambda p: -int(p.get("purity", 0) or 0))
    ship_n = min(len(ranked), 5)  # 1 catapult row = 5 slots
    if ship_n == 0:
        return {"candidates": [], "action": None, "verdict": "no_vein_plus"}
    bid_each = int(min(SHIP_BID_PER_PARCEL, credits // max(1, ship_n)))
    if bid_each <= 0:
        return {"candidates": ranked, "action": None, "verdict": "no_credits"}
    ids = [str(p.get("square_id")) for p in ranked[:ship_n]
           if p.get("square_id")]
    if not ids:
        return {"candidates": ranked, "action": None, "verdict": "no_ids"}
    action = {
        "a": "ship_catapult",
        "bids": [{"id": i, "credits": bid_each} for i in ids],
    }
    total_score = sum(int(p.get("score", 0) or 0) for p in ranked[:ship_n])
    return {
        "candidates": [
            {"square_id": p.get("square_id"), "tier": p.get("tier"),
             "purity": p.get("purity"), "score": p.get("score")}
            for p in ranked[:ship_n]
        ],
        "ship_count": ship_n,
        "bid_each": bid_each,
        "total_cost": bid_each * ship_n,
        "expected_score_added": total_score,
        "action": action,
        "verdict": "ship",
    }


def _refine_candidates(agent_view: Mapping[str, Any]) -> Dict[str, Any]:
    ob = _get_orbit_block(agent_view)
    parcels = list(ob.get("hoard_parcels") or [])
    blue = int(ob.get("blue_purity_total", 0) or 0)
    trace = [p for p in parcels if str(p.get("colour", "")).upper() == "RED"
             and int(p.get("purity", 0) or 0) < VEIN_MIN_PURITY]
    vein = [p for p in parcels if str(p.get("colour", "")).upper() == "RED"
            and VEIN_MIN_PURITY <= int(p.get("purity", 0) or 0) < MASS_MIN_PURITY]
    trace_blue_needed = len(trace) * REFINE_BLUE_TRACE
    vein_blue_needed = len(vein) * REFINE_BLUE_VEIN
    options: List[Dict[str, Any]] = []
    if trace and blue >= REFINE_BLUE_TRACE:
        options.append({
            "source_tier": "trace",
            "count": len(trace),
            "blue_cost": trace_blue_needed,
            "blue_available": blue,
            "upgraded_to": "vein",
            "action": {"a": "refine", "source_tier": "trace"},
        })
    if vein and blue >= REFINE_BLUE_VEIN:
        options.append({
            "source_tier": "vein",
            "count": len(vein),
            "blue_cost": vein_blue_needed,
            "blue_available": blue,
            "upgraded_to": "mass",
            "action": {"a": "refine", "source_tier": "vein"},
        })
    verdict = "refine" if options else "none_available"
    return {"options": options, "verdict": verdict}


def _trace_to_green(agent_view: Mapping[str, Any]) -> Dict[str, Any]:
    """Trace-fuelled green catapult — burn junk RED for green score."""
    ob = _get_orbit_block(agent_view)
    green_count = int(ob.get("green_owned_count", 0) or 0)
    green_cfg = ob.get("green_catapult") or {}
    cost_base = int(green_cfg.get("cost_base", 50) or 50)
    cost_step = int(green_cfg.get("cost_step", 5) or 5)
    if green_count <= 0:
        return {"verdict": "no_green", "action": None}
    # Right-sized RED fuel bid: one term per held green parcel.
    floor = 0
    for s in range(green_count):
        floor += max(0, cost_base - cost_step * s)
    action = {
        "a": "solar_jettison",
        "green_parcels": green_count,
        "red_fuel": max(0, floor + cost_step),
    }
    return {
        "green_count": green_count,
        "red_fuel_bid": action["red_fuel"],
        "action": action,
        "verdict": "flush",
    }


def _vault_pressure(agent_view: Mapping[str, Any]) -> Dict[str, Any]:
    """Vault-pressure signal — does ship/refine jump the queue?"""
    hud = agent_view.get("hud") or {}
    hoard = hud.get("hoard") or {}
    used = int(hoard.get("used", 0) or 0)
    max_ = int(hoard.get("max", 15) or 15)
    ratio = (used / max_) if max_ > 0 else 0.0
    return {
        "hoard_used": used,
        "hoard_max": max_,
        "pressure_ratio": round(ratio, 3),
        "threshold": VAULT_PRESSURE_THRESHOLD,
        "escalate": ratio >= VAULT_PRESSURE_THRESHOLD,
    }


# ── Composer ────────────────────────────────────────────────────
def _compose_recommendation(
    *,
    repair: List[Dict[str, Any]],
    probe: Dict[str, Any],
    harvester: Dict[str, Any],
    emp: Dict[str, Any],
    chaff: Dict[str, Any],
    mine: Dict[str, Any],
    ship: Dict[str, Any],
    refine: Dict[str, Any],
    green_flush: Dict[str, Any],
    vault: Dict[str, Any],
) -> Dict[str, Any]:
    """Walk the priority ladder and fill up to ``MAX_ORBIT_ACTIONS`` slots.

    v3 — sequential budget: each committed slot deducts its BLUE / credit
    cost from a running balance. Later slots that would drive the balance
    negative are dropped, not emitted, so the recommendation is always
    affordable when submitted in order.
    """
    actions: List[Dict[str, Any]] = []
    reasons: List[str] = []
    dropped: List[Dict[str, Any]] = []
    used_kinds: set[str] = set()

    # Running balance seeded from the orbit block. Every candidate's own
    # ``credits_available`` / ``blue_available`` field is the pre-turn
    # snapshot, so we can use any block as the seed. Probe block has both
    # credits_available implicitly (buy_count derived from credits) and
    # explicit_ish state — pull from EMP block which carries both.
    running_credits: int = int(
        emp.get("credits_available", ship.get("credits_available", 0)) or 0
    )
    running_blue: int = int(emp.get("blue_available", 0) or 0)

    def _try_append(
        action: Optional[Mapping[str, Any]],
        reason: str,
        kind: str,
        *,
        credit_cost: int = 0,
        blue_cost: int = 0,
    ) -> bool:
        nonlocal running_credits, running_blue
        if action is None:
            return False
        if kind in used_kinds:
            # A given kind (e.g. "ship_catapult") should only appear once.
            return False
        if len(actions) >= MAX_ORBIT_ACTIONS:
            return False
        if credit_cost > running_credits or blue_cost > running_blue:
            dropped.append({
                "kind": kind,
                "reason": reason,
                "credit_cost": credit_cost,
                "blue_cost": blue_cost,
                "running_credits": running_credits,
                "running_blue": running_blue,
                "verdict": "unaffordable_after_prior_slots",
            })
            return False
        actions.append(dict(action))
        reasons.append(reason)
        used_kinds.add(kind)
        running_credits -= credit_cost
        running_blue -= blue_cost
        return True

    # Priority 1 — vault escalation. If vault ≥ 80%, ship jumps queue.
    if vault.get("escalate") and ship.get("action") is not None:
        _try_append(
            ship["action"],
            f"[vault {vault['hoard_used']}/{vault['hoard_max']}] ship {ship.get('ship_count', 0)} vein+ parcels",
            "ship_catapult",
            credit_cost=int(ship.get("total_cost", 0) or 0),
        )
        if refine.get("options") and len(actions) < MAX_ORBIT_ACTIONS:
            top = refine["options"][0]
            _try_append(
                top["action"],
                f"[vault escalation] refine {top['count']} {top['source_tier']}→{top['upgraded_to']}",
                "refine",
                blue_cost=int(top.get("blue_cost", 0) or 0),
            )

    # Priority 2 — repair any damaged harvester (may need multiple slots).
    for rc in repair:
        _try_append(
            rc["action"],
            f"repair {rc['unit_id']} ({rc['cost']}c)",
            f"repair:{rc['unit_id']}",
            credit_cost=int(rc.get("cost", 0) or 0),
        )

    # Priority 2.5 — v3 aggression patch: if fleet is thin (< 2 alive
    # harvesters), build one BEFORE spending on probes. A dead fleet
    # cannot harvest. This is the `fleet_rebuild` plan the strategist
    # is briefed on.
    if harvester.get("fleet_thin") and harvester.get("action") is not None:
        _try_append(
            harvester["action"],
            f"[fleet_rebuild] build_harvester ({harvester['cost']}c) — fleet {harvester['fleet']} < 2",
            "build_harvester",
            credit_cost=int(harvester.get("cost", 0) or 0),
        )

    # Priority 3 — probe stock top-up (single batched slot).
    if probe.get("action") is not None:
        _try_append(
            probe["action"],
            f"build_probe ×{probe['buy_count']} — stock {probe['stock']}→{probe['stock'] + probe['buy_count']} ({probe['total_cost']}c)",
            "build_probe",
            credit_cost=int(probe.get("total_cost", 0) or 0),
        )

    # Priority 4 — harvester expansion (normal case: fleet already ≥ 2).
    if harvester.get("action") is not None and not harvester.get("fleet_thin"):
        v = harvester["verdict"]
        why = "good RED visible" if v == "buy" and harvester["visible_red_score"] >= GOOD_RED_SCORE_MIN else "flush cash reserve"
        _try_append(
            harvester["action"],
            f"build_harvester ({harvester['cost']}c) — {why}, fleet {harvester['fleet']}",
            "build_harvester",
            credit_cost=int(harvester.get("cost", 0) or 0),
        )

    # Priority 5 — offensive BLUE (EMP first, then chaff, then mine).
    for weap_block, tag in ((emp, "emp"), (chaff, "chaff"), (mine, "mine")):
        if weap_block.get("action") is not None:
            _try_append(
                weap_block["action"],
                f"build_{tag} ({weap_block['blue_cost']} BLUE + {weap_block['credit_cost']}c) — {weap_block['enemy_visible']} enemy visible",
                f"build_{tag}",
                credit_cost=int(weap_block.get("credit_cost", 0) or 0),
                blue_cost=int(weap_block.get("blue_cost", 0) or 0),
            )

    # Priority 6 — baseline ship (if not already queued via vault escalation).
    if ship.get("action") is not None:
        _try_append(
            ship["action"],
            f"ship {ship.get('ship_count', 0)} vein+ parcels ({ship.get('total_cost', 0)}c bid, ~{ship.get('expected_score_added', 0)} score)",
            "ship_catapult",
            credit_cost=int(ship.get("total_cost", 0) or 0),
        )

    # Priority 7 — baseline refine (trace→vein preferred over vein→mass).
    if refine.get("options"):
        top = refine["options"][0]
        _try_append(
            top["action"],
            f"refine {top['count']} {top['source_tier']}→{top['upgraded_to']} ({top['blue_cost']} BLUE)",
            "refine",
            blue_cost=int(top.get("blue_cost", 0) or 0),
        )

    # Priority 8 — trace-fuelled green catapult (dump junk for score).
    if green_flush.get("action") is not None:
        _try_append(
            green_flush["action"],
            f"green flush — {green_flush['green_count']} GREEN parcel(s), {green_flush['red_fuel_bid']} RED fuel",
            "solar_jettison",
        )

    return {
        "actions": actions,
        "total_actions": len(actions),
        "slot_reasons": reasons,
        "rationale_hint": "; ".join(reasons),
        "dropped_slots": dropped,
        "running_credits_after": running_credits,
        "running_blue_after": running_blue,
    }


# ── Public entry ─────────────────────────────────────────────────
def compile_orbit_candidates(agent_view: Mapping[str, Any]) -> Dict[str, Any]:
    """Emit the ``orbital`` block for the pilot_v4 harness output.

    Every field is JSON-serialisable. Pure — same inputs give same
    outputs. Does not touch the store or the engine.
    """
    repair = _repair_candidates(agent_view)
    probe = _probe_purchase(agent_view)
    harvester = _harvester_purchase(agent_view)
    emp = _weapon_purchase(agent_view, "emp", EMP_COST_BLUE, EMP_COST_CREDITS)
    chaff = _weapon_purchase(agent_view, "chaff", CHAFF_COST_BLUE, CHAFF_COST_CREDITS)
    mine = _weapon_purchase(agent_view, "mine", MINE_COST_BLUE, MINE_COST_CREDITS)
    ship = _ship_candidates(agent_view)
    refine = _refine_candidates(agent_view)
    green_flush = _trace_to_green(agent_view)
    vault = _vault_pressure(agent_view)

    recommended = _compose_recommendation(
        repair=repair, probe=probe, harvester=harvester,
        emp=emp, chaff=chaff, mine=mine,
        ship=ship, refine=refine, green_flush=green_flush, vault=vault,
    )

    # v3 — "trivial" fast-path signal for the LLM. When set, the agent's
    # doctrine tells it to submit `recommended_orbit_policy.actions`
    # verbatim without walking the ladder, saving ~30-40s of wallclock
    # per orbit turn. The situation is trivial when:
    #   * no vault escalation pressure (< 80 % full)
    #   * no repairs pending
    #   * no offensive weapons available (can't afford or no enemy)
    #   * the recommended action list fits within budget (already
    #     guaranteed by _compose_recommendation's sequential-budget
    #     accounting — no unaffordable slots got dropped)
    trivial = bool(
        not vault.get("escalate")
        and not repair
        and emp.get("action") is None
        and chaff.get("action") is None
        and mine.get("action") is None
        and not recommended.get("dropped_slots")
    )

    return {
        "play_enablers": {
            "repair_candidates": repair,
            "probe_purchase": probe,
            "harvester_purchase": harvester,
        },
        "vault_pressure": {
            **vault,
            "ship": ship,
            "refine": refine,
            "trace_to_green": green_flush,
        },
        "offensive_blue": {
            "emp_purchase": emp,
            "chaff_purchase": chaff,
            "mine_purchase": mine,
        },
        "recommended_orbit_policy": recommended,
        "max_actions": MAX_ORBIT_ACTIONS,
        "trivial": trivial,
    }
