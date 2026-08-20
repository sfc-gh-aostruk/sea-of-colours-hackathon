"""Rival arsenal tracker — turn coarse station_intel + public weapon events
into structured "rival probably has a chaff in stock and fired one last Nox"
signals the strategist can reason over.

The engine explicitly makes weapon spend legible via ``station_intel``:
each rival's ``blue.band`` moves in 150-purity pips so a ~200-blue weapon
build shows up as a 1-2 band drop (see game/session.py:6564). Combined
with the PUBLIC ``last_night.combat_events`` feed (EMP salvos and chaff
flares are zone-wide observable), we can:

* watch each rival's ``blue.band`` across turn snapshots and infer when
  they spent (chaff=255, emp=200, mine=100 blue);
* attribute observed firings (EMP salvos, chaff flares) against inferred
  builds to keep a running estimated stock;
* expose ``chaff_capable_now`` / ``emp_capable_now`` / ``likely_weapon``
  flags so the strategist can pre-empt (e.g. chain lengths and pickup
  timing under a chaff-capable rival).

Process-local per-session state (mirrors ``memory.py``). No I/O, no
Snowflake writes. ``reset_for_tests()`` clears state for pytest.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional


# ── Cost table (RULEBOOK §4.9) ──────────────────────────────────────
EMP_COST_BLUE = 200
EMP_COST_CREDITS = 250
CHAFF_COST_BLUE = 255
CHAFF_COST_CREDITS = 0
MINE_COST_BLUE = 100
MINE_COST_CREDITS = 100

# Band mid-point in blue purity — session.py grades in 150-purity pips.
_BAND_PIP = 150

# Refine costs ~10 blue per parcel; ignore for our threshold reasoning
# (a single-band drop is dominated by weapon builds, not refine noise).


# ── Per-session state ───────────────────────────────────────────────
_STATE: Dict[str, Dict[str, Any]] = {}


def reset_for_tests() -> None:
    """Drop all per-session state (call from pytest fixtures)."""
    _STATE.clear()


def _session_state(session_id: str) -> Dict[str, Any]:
    st = _STATE.get(session_id)
    if st is None:
        st = {"opponents": {}, "last_ingested_day": -1}
        _STATE[session_id] = st
    return st


def _rival_state(session_state: Dict[str, Any], seat: str) -> Dict[str, Any]:
    opps = session_state["opponents"]
    st = opps.get(seat)
    if st is None:
        st = {
            "band_history": [],       # [(day, band, blue_total_est_or_none)]
            "weapon_events": [],      # [{day, hour, kind, owner}]
            "built_emp_seen": 0,
            "built_chaff_seen": 0,
            "fired_emp_seen": 0,
            "fired_chaff_seen": 0,
        }
        opps[seat] = st
    return st


# ── Public API ──────────────────────────────────────────────────────
def update_and_summarize(
    session_id: str,
    agent_view: Mapping[str, Any],
) -> Dict[str, Any]:
    """Ingest this turn's station_intel + last_night combat events, return
    a compact summary the strategist / tactician can splice into their
    context.

    Idempotent per (session, day): calling it twice on the same day just
    re-reads the same snapshot.
    """
    session_state = _session_state(session_id)
    meta = agent_view.get("meta") or {}
    day = int(meta.get("day") or 0)
    station = agent_view.get("station_intel") or {}
    last_night = agent_view.get("last_night") or {}

    # 1) Update band history from station_intel.opponents[*].blue.band.
    opponents_now = station.get("opponents") or []
    for op in opponents_now:
        if not isinstance(op, Mapping):
            continue
        seat = str(op.get("seat") or "")
        if not seat:
            continue
        blue = op.get("blue") or {}
        try:
            band = int(blue.get("band") or 0)
        except (TypeError, ValueError):
            band = 0
        rs = _rival_state(session_state, seat)
        hist = rs["band_history"]
        # Idempotent: overwrite last entry if same day already stamped.
        if hist and hist[-1][0] == day:
            hist[-1] = (day, band, None)
        else:
            hist.append((day, band, None))

    # 2) Ingest last-night combat events (public — every seat sees them).
    combat_events = last_night.get("combat_events") or []
    seen_this_call: set = set()
    for ev in combat_events:
        if not isinstance(ev, Mapping):
            continue
        etype = str(ev.get("type") or "")
        if etype not in ("emp", "chaff"):
            continue
        owner = str(ev.get("owner") or "")
        if not owner:
            continue
        # Only rival events go into the arsenal tracker (self is known).
        me = str(meta.get("player") or "")
        if owner == me:
            continue
        try:
            hour = int(ev.get("hour") or 0)
        except (TypeError, ValueError):
            hour = 0
        # Dedup across turn re-invocations for the same (seat, day, hour, type).
        key = (owner, day - 1, hour, etype)
        if key in seen_this_call:
            continue
        seen_this_call.add(key)
        rs = _rival_state(session_state, owner)
        # Don't double-count across days: use a per-event flag by key.
        already = any(
            (e.get("day") == day - 1 and e.get("hour") == hour
             and e.get("kind") == etype)
            for e in rs["weapon_events"]
        )
        if already:
            continue
        rs["weapon_events"].append(
            {"day": day - 1, "hour": hour, "kind": etype, "owner": owner}
        )
        if etype == "emp":
            rs["fired_emp_seen"] += 1
        elif etype == "chaff":
            rs["fired_chaff_seen"] += 1

    session_state["last_ingested_day"] = day
    return _summary(session_state, agent_view)


def _classify_likely_weapon(band_drop_pips: int, hoard_grade: str) -> Optional[str]:
    """Best guess for a single-orbit spend.

    band_drop_pips is (prev_band - curr_band); each pip ~= 150 blue.
    Cost table: chaff 255, emp 200, mine 100.
    """
    if band_drop_pips <= 0:
        return None
    # Two-pip drop (~300+ blue) is chaff (255) — EMP alone is only ~200.
    if band_drop_pips >= 2:
        return "chaff"
    # One-pip drop (~150+ blue) fits either EMP or chaff-with-carryover.
    # Chaff (255) crossing a band boundary is one pip; EMP (200) is one
    # pip. Cannot disambiguate from band alone; default to EMP (cheaper,
    # more common) and defer to observed firings.
    return "emp"


def _summary(session_state: Dict[str, Any], agent_view: Mapping[str, Any]) -> Dict[str, Any]:
    station = agent_view.get("station_intel") or {}
    opponents_now = {}
    for op in (station.get("opponents") or []):
        if isinstance(op, Mapping) and op.get("seat"):
            opponents_now[str(op["seat"])] = op

    out_opponents: List[Dict[str, Any]] = []
    for seat, rs in session_state["opponents"].items():
        cur = opponents_now.get(seat, {})
        blue = cur.get("blue") or {}
        try:
            band_now = int(blue.get("band") or 0)
        except (TypeError, ValueError):
            band_now = 0
        band_grade = str(blue.get("grade") or "unknown")
        hoard_grade = str((cur.get("fullness") or {}).get("grade") or "unknown")
        activity = cur.get("activity") or {}
        hist = rs["band_history"]
        band_prev = int(hist[-2][1]) if len(hist) >= 2 else band_now
        band_delta = band_now - band_prev  # negative = spent since last snapshot

        # Capability flags. A rival can chaff this Nox only if they hold
        # ≥255 blue (band ≥ 2 = ≥300, guaranteed; band = 1 = 150-300 may
        # or may not have 255 — treat as maybe). Same for EMP at 200.
        chaff_capable_now = band_now >= 2
        emp_capable_now = band_now >= 2 or (band_now == 1 and band_grade in ("medium",))

        built_this_orbit = band_delta <= -1
        drop_pips = -band_delta if band_delta < 0 else 0
        likely_weapon = _classify_likely_weapon(drop_pips, hoard_grade) if built_this_orbit else None

        # Estimated stock: builds_seen - firings_seen (best-effort).
        # We infer builds from band drops; firings we've observed directly.
        # NOTE: this is an inference floor — rival may have started with
        # weapons we never saw built. Confidence is low early season.
        emp_built = max(0, rs["built_emp_seen"])
        chaff_built = max(0, rs["built_chaff_seen"])
        # For now, credit a build to the inferred weapon each orbit.
        if built_this_orbit:
            if likely_weapon == "chaff":
                chaff_built += 1
                rs["built_chaff_seen"] = chaff_built
            elif likely_weapon == "emp":
                emp_built += 1
                rs["built_emp_seen"] = emp_built
        emp_stock = max(0, emp_built - rs["fired_emp_seen"])
        chaff_stock = max(0, chaff_built - rs["fired_chaff_seen"])

        fired_last_nox = [
            {"kind": e["kind"], "hour": e["hour"]}
            for e in rs["weapon_events"]
            if e.get("day") == (int((agent_view.get("meta") or {}).get("day") or 0) - 1)
        ]

        out_opponents.append({
            "seat": seat,
            "blue_band_now": band_now,
            "blue_grade": band_grade,
            "blue_band_delta": band_delta,
            "hoard_grade": hoard_grade,
            "harvesters_dropped_last_nox": int(activity.get("dropped") or 0),
            "harvesters_recovered_last_nox": int(activity.get("picked_up") or 0),
            "chaff_capable_now": bool(chaff_capable_now),
            "emp_capable_now": bool(emp_capable_now),
            "built_weapon_last_orbit": bool(built_this_orbit),
            "likely_weapon_built": likely_weapon,
            "weapons_fired_last_nox": fired_last_nox,
            "estimated_stock": {"emp": int(emp_stock), "chaff": int(chaff_stock)},
        })

    return {
        "day": int((agent_view.get("meta") or {}).get("day") or 0),
        "opponents": out_opponents,
    }


# ── Per-candidate risk scoring ──────────────────────────────────────
# Given the arsenal summary + threat context + redsign presence, estimate
# how likely a rival will EMP or chaff a specific harvest chain. Returns
# risk scores in [0.0, 1.0] plus concrete tactical hedges the tactician
# should apply.
#
# Signals we can lawfully use (all from the agent view):
#   • arsenal.opponents[*].{emp_capable_now, chaff_capable_now,
#     estimated_stock, weapons_fired_last_nox, built_weapon_last_orbit}
#   • candidate.threat_cost — sum of enemy vision heat on cells traversed
#   • candidate.chain_survival_prob — model-derived survival estimate
#   • redsign_present — public jackpot beacon flag
#
# We DON'T get "is this candidate on the redsign" as a boolean, but the
# threat_cost + shared_vision proxy is a strong indicator that a chain
# is telegraphed and worth denying.


def score_candidate_risk(
    candidate: Mapping[str, Any],
    arsenal_summary: Optional[Mapping[str, Any]],
    *,
    redsign_present: bool = False,
    redsign_cells: Optional[List[List[int]]] = None,
) -> Dict[str, Any]:
    """Return {emp_risk, chaff_risk, hedges: [...]} for one harvest chain.

    The scores are heuristic-ish (weighted-sum, no ML) but grounded in
    the observable capability flags and threat cost. Hedges are the
    concrete tactical moves the tactician should consider when a risk
    exceeds ~0.5.
    """
    threat_cost = 0.0
    if isinstance(candidate, Mapping):
        try:
            threat_cost = float(candidate.get("threat_cost") or 0.0)
        except (TypeError, ValueError):
            threat_cost = 0.0

    # Normalise threat cost to a [0,1] "telegraph" fraction. Empirically
    # threat_cost of 4.0+ is a heavily-scouted chain; 0.5- is dark.
    telegraph = min(1.0, threat_cost / 4.0)

    # Chain is on/near redsign? A rough proxy: if redsign_cells provided,
    # count how many chain cells fall inside the smear. Absent that data,
    # treat "redsign_present + telegraph > 0.5" as contested-pure.
    on_redsign = False
    if redsign_cells and isinstance(candidate, Mapping):
        cells = candidate.get("cells_traversed") or []
        rs_set = {tuple(c[:2]) for c in redsign_cells
                  if isinstance(c, (list, tuple)) and len(c) >= 2}
        on_redsign = any(tuple(c[:2]) in rs_set for c in cells
                         if isinstance(c, (list, tuple)) and len(c) >= 2)
    contested_pure = redsign_present and (on_redsign or telegraph > 0.5)

    # Pick the "worst" rival — highest weapon capability — since a single
    # rival firing is enough to kill the chain.
    worst_emp = 0.0
    worst_chaff = 0.0
    for op in ((arsenal_summary or {}).get("opponents") or []):
        if not isinstance(op, Mapping):
            continue
        emp_cap = 0.3 if op.get("emp_capable_now") else 0.0
        chaff_cap = 0.3 if op.get("chaff_capable_now") else 0.0
        stock = op.get("estimated_stock") or {}
        emp_stock_bonus = 0.2 if int(stock.get("emp") or 0) > 0 else 0.0
        chaff_stock_bonus = 0.2 if int(stock.get("chaff") or 0) > 0 else 0.0
        built_last = op.get("likely_weapon_built") if op.get("built_weapon_last_orbit") else None
        emp_recent_bonus = 0.2 if built_last == "emp" else 0.0
        chaff_recent_bonus = 0.2 if built_last == "chaff" else 0.0
        emp_risk = (
            emp_cap + emp_stock_bonus + emp_recent_bonus
            + 0.3 * telegraph
            + (0.3 if contested_pure else 0.0)
        )
        chaff_risk = (
            chaff_cap + chaff_stock_bonus + chaff_recent_bonus
            + 0.2 * telegraph
            + (0.2 if contested_pure else 0.0)
        )
        worst_emp = max(worst_emp, emp_risk)
        worst_chaff = max(worst_chaff, chaff_risk)
    worst_emp = min(1.0, worst_emp)
    worst_chaff = min(1.0, worst_chaff)

    # Concrete hedges the tactician should apply.
    hedges: List[str] = []
    if worst_chaff >= 0.5:
        hedges.append("short_chain_trim_to_4")
        hedges.append("split_across_multiple_harvesters")
    if worst_emp >= 0.5:
        hedges.append("late_deploy_after_cloud")
        hedges.append("hot_drop_probe_outside_cloud")
        hedges.append("prefire_emp_to_deny_rival_first")
    if contested_pure and (worst_emp >= 0.4 or worst_chaff >= 0.4):
        hedges.append("consider_own_chaff_to_deny_rival_pickup")
    return {
        "emp_risk": round(worst_emp, 2),
        "chaff_risk": round(worst_chaff, 2),
        "contested_pure": bool(contested_pure),
        "telegraph": round(telegraph, 2),
        "hedges": hedges,
    }


# ── Self telemetry: harvester utilisation last Nox ──────────────────
def harvester_utilization(agent_view: Mapping[str, Any]) -> Dict[str, Any]:
    """Was every alive harvester used last Nox? Idle harvesters bank zero.

    Reads ``my_assets`` + ``last_night.my_orders`` (public log for our
    own seat) to detect which harvester units received a ``drop`` last
    Nox. Returns a per-unit `used_last_nox` flag + a `wasted_units`
    count the strategist can weight as "score bleed".
    """
    my_assets = agent_view.get("my_assets") or []
    alive = [str(a.get("id") or "") for a in my_assets
             if isinstance(a, Mapping)
             and str(a.get("kind") or "").lower() == "harvester"
             and str(a.get("id") or "")]

    last_night = agent_view.get("last_night") or {}
    orders = last_night.get("my_orders") or []
    dropped_units: set = set()
    for row in orders:
        if not isinstance(row, Mapping):
            continue
        text = str(row.get("text") or "")
        # Log rows include "p1 dropped harvester_p1 at (...)" or the
        # move payload. Cheap grep for "dropped harvester_" tokens.
        if "dropped harvester_" in text:
            # Extract the unit id after "dropped ".
            i = text.find("dropped ")
            if i >= 0:
                tail = text[i + len("dropped "):]
                unit = tail.split()[0].rstrip(",;.:")
                dropped_units.add(unit)

    per_unit = [{"unit": u, "used_last_nox": u in dropped_units} for u in alive]
    wasted = sum(1 for row in per_unit if not row["used_last_nox"])
    return {
        "harvesters_alive": len(alive),
        "wasted_units_last_nox": wasted,
        "per_unit": per_unit,
    }

