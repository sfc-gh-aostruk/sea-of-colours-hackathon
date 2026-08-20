"""Threat assessment heatmap for SOC_RED_REAPER_PILOT_V2.

Builds a per-cell heatmap that composes four layers into a single scalar
that downstream consumers (chain scoring, supersede ranking, hot-drop
emission, drop-block emission) all read:

    heatmap[y][x] = w_e · enemy_knowledge[y][x]
                  + w_r · red_magnet[y][x]
                  + w_a · enemy_asset_proximity[y][x]
                  + w_o · enemy_orbit_inverse_distance[y][x]

The enemy_knowledge layer is a single MERGED current+historical scalar
per cell (linear decay over the season horizon). This collapses the
"who has seen this cell" question to one number — high = enemy
recently/currently has eyes here; low = stale; zero = dark zone.

Doctrines this module powers:
    1. engage-ratio filter — abandon contested+low-value chains
    2. supersede preempt — boost supersede when contested+juicy+budget
    3. heat-adaptive chain length + survival-probability scoring
    4a. speculative hot-drop into fog
    4b. counter-blind hot-drop after our probe was superseded
    5. collision-vs-value scored cost (no hard avoid for enemy harvesters)

All math is grounded in the rulebook:
- §3.10: 21 hours/night, action position = hour, parallel resolution
- §3.16: same-cell same-hour probes = mutual annihilation
- §3.17: harvester collision = TOTAL cargo loss
- §3.15: probe launches public → telegraph cost
- §3.9.7/3.9.8: drop legality at hour-start snapshot → hot-drop works
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple


# ── tunable weights & thresholds ─────────────────────────────────────
# All in one block so reviewers and weight-tuning passes can find them
# without grep diving.

WEIGHT_ENEMY_KNOWLEDGE = 0.45
WEIGHT_RED_MAGNET = 0.30
WEIGHT_ASSET_PROX = 0.15
WEIGHT_ORBIT_INV = 0.10

# Linear decay horizon for enemy_knowledge: a cell seen exactly
# KNOWLEDGE_DECAY_HORIZON_DAYS ago contributes zero. Cells seen within
# the horizon decay linearly from 1.0 → 0.0.
KNOWLEDGE_DECAY_HORIZON_DAYS = 7

# Probe disk radius (§3.9.7) and harvester plus radius (§3.8).
PROBE_DISK_RADIUS = 4
HARVESTER_PLUS_RADIUS = 1

# Doctrine 1 — engage-ratio filter.
ABANDON_THRESHOLD = 0.3
ABANDON_PENALTY = 1000  # subtracted from chain score when abandoned

# Doctrine 2 — supersede boost.
HIGH_VALUE_THRESHOLD = 400  # red density inside zone (radius-3) needed for "juicy"
JUICY_CONTEST_BOOST = 1.5  # multiplier on supersede score

# Doctrine 3 — heat-as-SIGNAL (v0.9.24 redesign).
#
# DESIGN RULE: Threat heat marks where the rival is likely to STRIKE,
# not where we should run away from. High heat at a valuable target
# means "harvest fast or hit them harder" — NOT "skip the target".
#
# Concretely:
# * The walker does NOT truncate chains based on heat. Heat no longer
#   shortens the chain's step count.
# * Chains that touch high-value (pure or mass) cells in a SHORT
#   action window (≤ 5) get a ``RACE_BONUS`` proportional to local
#   heat — "get in and out before they swing".
# * Offensive candidates (drop_block, hot_drop_counter_blind,
#   crush_probe) get an ``OFFENSIVE_RESPONSE_BONUS`` so they outrank
#   passive harvest when local heat is medium+.
HOT_HEAT_THRESHOLD = 0.70
MEDIUM_HEAT_THRESHOLD = 0.40
MAX_STEP_BUDGET = 5  # mirrors heuristic_agent.MAX_HARVESTER_STEPS
INVENTORY_LOSS_COST = 150  # scalar penalty for a full inventory-loss collision (§3.17)
CELL_COLLISION_BASE_RATE = 0.10  # base P(enemy interferes) per unit heatmap

# v0.9.24 — race-and-respond bonuses (replaces avoidance penalty).
RACE_BONUS = 60          # × mean_heat_along_chain, applied to short pure/mass chains
RACE_BONUS_MAX_ACTIONS = 5     # chains ≤ this length are "race-eligible"
RACE_BONUS_MIN_VALUE = 400     # cascaded value floor for race eligibility
OFFENSIVE_RESPONSE_BONUS = 120  # × local_heat, added to drop-block / hot-drop / crush

# Doctrine 4a — speculative hot-drop.
FOG_GAMBLE_THRESHOLD = 0.55  # red_magnet prior strength to gamble on
SPECULATIVE_HOT_DROP_DAY_GUARD = 2  # don't emit before this day

# Doctrine 4b — counter-blind hot-drop.
COUNTER_BLIND_LOOKBACK_DAYS = 2

# Drop-block (NEW from rulebook).
DROP_BLOCK_HEAT_FLOOR = 0.6
DROP_BLOCK_HARVESTER_DAMAGE_BONUS = 200

# Dark-zone detection.
DARK_ZONE_HEAT_CEILING = 0.15
DARK_ZONE_MIN_SIZE = 6


# ── EMP threat detection (v0.9.22) ───────────────────────────────────
#
# Per RULEBOOK §4.9.3, an EMP launch costs 200 BLUE + 250c built in the
# preceding Orbit phase. Station intel (§3.15.1) surfaces every rival's
# BLUE purity two ways: a coarse grade (none / low / medium / high, cutoffs
# 0 / 1-100 / 101-250 / 251+) AND a finer PIP band (``blue.band``, 0..5 at
# 150 purity/pip). The pip band is the primary consumption signal — a
# ~200-BLUE EMP spend reliably shows as a ≥1-pip drop turn-over-turn, which
# the coarse grade can miss when the spend stays inside one band. We fall
# back to the grade drop only when pip data is unavailable. Cross-reference
# with confirmed EMP launches (station_intel.activity.emps) for certainty.

BLUE_GRADE_ORDER = ["none", "low", "medium", "high"]


def _blue_grade_rank(grade: Optional[str]) -> int:
    """Return 0..3 for the BLUE-purity grade bands."""
    if not grade:
        return -1
    try:
        return BLUE_GRADE_ORDER.index(str(grade).lower())
    except ValueError:
        return -1


def compute_emp_threat_signal(
    agent_view: Mapping[str, Any],
    memory: Mapping[str, Any],
) -> Dict[str, Any]:
    """Estimate the rival's EMP threat from BLUE-grade deltas + launch history.

    Returns a dict with:
    * ``rival_built_weapon`` (bool) — best-guess that the rival spent
      BLUE on an offensive weapon in the most recent settlement.
    * ``confidence`` (float in [0, 1]) — strength of the signal.
    * ``reason`` (str) — human-readable rationale for the agent's prompt.
    * ``signal_source`` (str) — "blue_drop_band" / "confirmed_launch" /
      "blue_drop_band+confirmed_launch" / "none".
    * ``rival_blue_grade_now`` / ``rival_blue_grade_prev``.
    * ``rival_emp_launches_last_night`` (int) — confirmed launches.
    """
    meta = agent_view.get("meta") or {}
    me = str(meta.get("player") or "")
    current_day = int(meta.get("day") or 0)

    # Current grade + pip band from this turn's station_intel.
    station_intel = agent_view.get("station_intel") or {}
    rival_grade_now: Optional[str] = None
    rival_pip_now: Optional[int] = None
    rival_emp_now = 0
    for opp in (station_intel.get("opponents") or []):
        if not isinstance(opp, Mapping):
            continue
        seat = str(opp.get("seat") or "")
        if not seat or seat == me:
            continue
        blue_obs = opp.get("blue") or {}
        grade = (blue_obs.get("grade") or "")
        if grade:
            rival_grade_now = str(grade).lower()
        if blue_obs.get("band") is not None:
            try:
                rival_pip_now = int(blue_obs.get("band"))
            except (TypeError, ValueError):
                rival_pip_now = None
        try:
            rival_emp_now = int(((opp.get("activity") or {}).get("emps") or 0))
        except (TypeError, ValueError):
            rival_emp_now = 0
        break  # one rival per seat in v1

    # Previous grade from memory.
    history = (memory or {}).get("rival_blue_grade_history") or {}
    rival_grade_prev: Optional[str] = None
    for d in range(current_day - 1, 0, -1):
        if str(d) in history:
            rival_grade_prev = str(history[str(d)]).lower()
            break

    # Previous pip band from memory (finer signal).
    pip_history = (memory or {}).get("rival_blue_band_history") or {}
    rival_pip_prev: Optional[int] = None
    for d in range(current_day - 1, 0, -1):
        if str(d) in pip_history:
            try:
                rival_pip_prev = int(pip_history[str(d)])
            except (TypeError, ValueError):
                rival_pip_prev = None
            break

    # Confirmed launches from memory's history (cumulative).
    launches_history = (memory or {}).get("rival_emp_launches_history") or {}
    total_launches_seen = 0
    for v in launches_history.values():
        try:
            total_launches_seen += int(v or 0)
        except (TypeError, ValueError):
            continue

    # Classify. Prefer the finer PIP drop (150/pip); fall back to grade band.
    grade_drop = 0
    if rival_grade_now is not None and rival_grade_prev is not None:
        grade_drop = max(0, _blue_grade_rank(rival_grade_prev) - _blue_grade_rank(rival_grade_now))

    pip_drop = 0
    if rival_pip_now is not None and rival_pip_prev is not None:
        pip_drop = max(0, rival_pip_prev - rival_pip_now)

    use_pips = rival_pip_now is not None and rival_pip_prev is not None
    # ``band_drop`` = the effective drop the signal is built on (pips when
    # available, else the coarse grade). Kept as the primary output key.
    band_drop = pip_drop if use_pips else grade_drop

    rival_built_weapon = False
    confidence = 0.0
    sources: List[str] = []
    reason_bits: List[str] = []

    if band_drop >= 1:
        rival_built_weapon = True
        if use_pips:
            # ~150 BLUE/pip; an EMP (200) ≈ 1.3 pips. 1 pip ~0.5, 2 ~0.8, 3+ ~0.9.
            confidence = max(confidence, min(0.9, 0.35 + 0.25 * band_drop))
            sources.append("blue_drop_pip")
            reason_bits.append(
                f"rival BLUE dropped {rival_pip_prev}→{rival_pip_now} pips "
                f"(~{band_drop * 150} BLUE) — weapon build likely"
            )
        else:
            # 1 grade drop = ~0.55 confidence; 2 grades = 0.85.
            confidence = max(confidence, 0.55 + 0.30 * min(2, band_drop - 1))
            sources.append("blue_drop_band")
            reason_bits.append(
                f"rival BLUE dropped {rival_grade_prev}→{rival_grade_now} "
                f"({band_drop} band(s)) — weapon build likely"
            )

    if rival_emp_now > 0:
        rival_built_weapon = True
        confidence = max(confidence, 0.95)
        sources.append("confirmed_launch")
        reason_bits.append(
            f"rival fired {rival_emp_now} EMP(s) last night — high-confidence"
        )
    elif total_launches_seen > 0:
        # Rival has fired EMPs in past nights — they know how. Lower-bound
        # the confidence so we don't completely drop our guard.
        confidence = max(confidence, 0.35)
        sources.append("prior_launch_history")
        reason_bits.append(
            f"rival has fired EMPs earlier this season "
            f"({total_launches_seen} total) — stay alert"
        )

    if not sources:
        sources.append("none")
        reason_bits.append("no EMP signal — rival BLUE flat or unknown")

    return {
        "rival_built_weapon": bool(rival_built_weapon),
        "confidence": round(float(confidence), 2),
        "reason": "; ".join(reason_bits),
        "signal_source": "+".join(s for s in sources if s != "none") or "none",
        "rival_blue_grade_now": rival_grade_now,
        "rival_blue_grade_prev": rival_grade_prev,
        "rival_blue_band_drop": int(band_drop),
        "rival_blue_pip_now": rival_pip_now,
        "rival_blue_pip_prev": rival_pip_prev,
        "rival_blue_pip_drop": int(pip_drop),
        "signal_basis": "pip" if use_pips else "grade",
        "rival_emp_launches_last_night": int(rival_emp_now),
        "rival_emp_launches_season_total": int(total_launches_seen),
    }


# Doctrine D-EMP-1 (front-load) constants.
EMP_FRONTLOAD_HOURS = 6   # chains finishing by hour 6 are EMP-resilient
EMP_FRONTLOAD_BONUS = 80  # score bonus added to fast chains under EMP threat
EMP_LONGCHAIN_PENALTY = 40  # score penalty applied to slow chains under EMP threat

# PURE-cell prioritization (v0.9.23, retuned v0.9.25).
#
# Per RULEBOOK §2.2 + heuristic_agent._RED_TIER_MULT:
#   shipping multiplier: trace 0.75, vein 1.0, mass 1.5, pure 3.0
# A pure parcel ships for ~765 (255 × 3.0). A mass parcel ships for
# ~300 (200 × 1.5). The chain score formula sums raw purity, NOT
# shipping value — which dramatically undervalues high-tier cells.
# These bonuses bridge the gap so the compiler picks chains that
# maximise SHIPPED-value, not raw purity.
#
# Pure: +600 per cell ≈ marginal ship-value lift over vein.
# Mass: +150 per cell ≈ marginal ship-value lift over vein.
# Chain priority bonus: +200 once per chain containing any pure cell.
PURE_PURITY_THRESHOLD = 255      # the bar
MASS_PURITY_THRESHOLD = 151      # mass starts here (vein ceiling at 150)
PURE_CELL_BONUS = 600            # ≈ marginal ship-value lift over vein per pure cell
MASS_CELL_BONUS = 150            # ≈ marginal ship-value lift over vein per mass cell
PURE_CHAIN_PRIORITY_BONUS = 200  # one-shot bonus when chain contains any pure cell


# ── posture (score-gap-aware playstyle) ──────────────────────────────
#
# When PILOT_V2 is BEHIND and hasn't found enough visible red, it
# should expand aggressively (more probes, lower hot-drop thresholds,
# earlier speculative gambles). When AHEAD late, it should lock in
# (fewer probes, conservative chain picks). Posture is a discrete
# label the candidate emitters read to swing their thresholds.

# Aggressive triggers.
AGGRESSIVE_SCORE_GAP_THRESHOLD = -50          # behind by this much → aggressive
AGGRESSIVE_LOW_VISIBLE_RED = 200              # visible red below this → aggressive
AGGRESSIVE_MIN_DAYS_REMAINING = 2             # only push if 2+ days left
AGGRESSIVE_EXPLORE_MIN_DAYS_REMAINING = 3     # explore-mode needs 3+ days

# Conservative triggers.
CONSERVATIVE_LEAD_GAP = 100                   # ahead by this much → conservative
CONSERVATIVE_MAX_DAYS_REMAINING = 2           # lock it in when ≤ 2 days left

# Per-posture knobs (used by candidates.py emitters).
HOT_DROP_VALUE_FLOOR = {
    "aggressive": 50,
    "balanced": 100,
    "conservative": 150,
}
SPECULATIVE_DAY_GUARD = {
    "aggressive": 1,
    "balanced": SPECULATIVE_HOT_DROP_DAY_GUARD,  # 2
    "conservative": 3,
}
RECOMMENDED_PROBE_CAP = {
    "aggressive": 3,
    "balanced": 2,
    "conservative": 1,
}
SUPERSEDE_ACTIVATION_THRESHOLD = {
    "aggressive": 40,
    "balanced": 80,
    "conservative": 120,
}


def compute_posture(
    agent_view: Mapping[str, Any],
    memory: Mapping[str, Any],
) -> Dict[str, Any]:
    """Classify this turn's playstyle from score gap + visible value + tempo.

    Returns a dict with ``label`` (``aggressive`` / ``balanced`` /
    ``conservative``) plus the raw signals for transparency in the
    threat envelope.
    """
    meta = agent_view.get("meta") or {}
    hud = agent_view.get("hud") or {}
    me = str(meta.get("player") or "")
    day = int(meta.get("day") or 0)
    season_cap = int(hud.get("season_day_cap") or 7)
    days_remaining = max(0, season_cap - day + 1)

    # Score gap.
    scores = hud.get("scores") or {}
    my_score = int(scores.get(me, hud.get("score") or 0) or 0)
    rival_score = 0
    for seat, s in scores.items():
        if seat != me:
            try:
                rival_score = max(rival_score, int(s or 0))
            except (TypeError, ValueError):
                continue
    score_gap = my_score - rival_score

    # Visible RED value — sum of purities across navigation.best_red_visible.
    nav = agent_view.get("navigation") or {}
    visible_red_value = 0
    for r in (nav.get("best_red_visible") or []):
        try:
            visible_red_value += int(r.get("value") or r.get("purity") or 0)
        except (TypeError, ValueError):
            continue

    # Classify. Order matters — last-day Hail Mary / lock-in fire first.
    label = "balanced"
    reason = "default"
    if days_remaining == 1 and score_gap < 0:
        label = "aggressive"
        reason = "last-day Hail Mary (trailing on final night)"
    elif days_remaining == 1 and score_gap > 50:
        label = "conservative"
        reason = "last-day lead protection"
    elif (
        score_gap < AGGRESSIVE_SCORE_GAP_THRESHOLD
        and days_remaining >= AGGRESSIVE_MIN_DAYS_REMAINING
    ):
        label = "aggressive"
        reason = f"trailing by {-score_gap} with {days_remaining}d left"
    elif (
        visible_red_value < AGGRESSIVE_LOW_VISIBLE_RED
        and days_remaining >= AGGRESSIVE_EXPLORE_MIN_DAYS_REMAINING
    ):
        label = "aggressive"
        reason = (
            f"visible red sum {visible_red_value} is below "
            f"{AGGRESSIVE_LOW_VISIBLE_RED} — explore harder"
        )
    elif (
        score_gap > CONSERVATIVE_LEAD_GAP
        and days_remaining <= CONSERVATIVE_MAX_DAYS_REMAINING
    ):
        label = "conservative"
        reason = f"leading by {score_gap} with only {days_remaining}d left"

    return {
        "label": label,
        "reason": reason,
        "score_gap": int(score_gap),
        "my_score": int(my_score),
        "rival_score": int(rival_score),
        "visible_red_value": int(visible_red_value),
        "days_remaining": int(days_remaining),
        # Knobs the emitters read.
        "hot_drop_value_floor": HOT_DROP_VALUE_FLOOR[label],
        "speculative_day_guard": SPECULATIVE_DAY_GUARD[label],
        "recommended_probe_cap": RECOMMENDED_PROBE_CAP[label],
        "supersede_activation_threshold": SUPERSEDE_ACTIVATION_THRESHOLD[label],
    }


# ── heatmap container ────────────────────────────────────────────────


@dataclass
class Heatmap:
    """A 2D heatmap with convenience accessors.

    Stored row-major as ``values[y][x]``. Every cell is in ``[0, 1]``
    after layer composition (weights sum to 1.0).
    """

    width: int
    height: int
    values: List[List[float]]
    # Cached per-layer arrays for debugging / decomposition surfaces.
    layer_enemy_knowledge: List[List[float]]
    layer_red_magnet: List[List[float]]
    layer_asset_proximity: List[List[float]]
    layer_orbit_inv: List[List[float]]

    def value(self, x: int, y: int) -> float:
        if 0 <= x < self.width and 0 <= y < self.height:
            return float(self.values[y][x])
        return 0.0

    def value_xy(self, xy: Tuple[int, int]) -> float:
        return self.value(int(xy[0]), int(xy[1]))

    def mean_along(self, cells: Iterable[Tuple[int, int]]) -> float:
        vs: List[float] = []
        for xy in cells:
            vs.append(self.value(int(xy[0]), int(xy[1])))
        if not vs:
            return 0.0
        return sum(vs) / len(vs)

    def top_cells(self, k: int) -> List[Dict[str, Any]]:
        """Top-K hottest cells with decomposition for the prompt envelope."""
        all_cells: List[Tuple[float, int, int]] = []
        for y in range(self.height):
            for x in range(self.width):
                v = self.values[y][x]
                if v > 0.0:
                    all_cells.append((v, x, y))
        all_cells.sort(key=lambda t: -t[0])
        out: List[Dict[str, Any]] = []
        for v, x, y in all_cells[: max(0, int(k))]:
            out.append({
                "at": [x, y],
                "heat": round(v, 3),
                "decomposition": {
                    "enemy_knowledge": round(self.layer_enemy_knowledge[y][x], 3),
                    "red_magnet": round(self.layer_red_magnet[y][x], 3),
                    "asset_proximity": round(self.layer_asset_proximity[y][x], 3),
                    "orbit_inv": round(self.layer_orbit_inv[y][x], 3),
                },
            })
        return out

    def dark_zones(self) -> List[Dict[str, Any]]:
        """Connected low-heat regions (heat ≤ DARK_ZONE_HEAT_CEILING).

        Returns a list of zones with the top-left anchor and size.
        Useful for the agent envelope so it can frame "stealth pockets".
        """
        seen: List[List[bool]] = [[False] * self.width for _ in range(self.height)]
        zones: List[Dict[str, Any]] = []
        for y in range(self.height):
            for x in range(self.width):
                if seen[y][x]:
                    continue
                if self.values[y][x] > DARK_ZONE_HEAT_CEILING:
                    seen[y][x] = True
                    continue
                # BFS flood fill within heat ≤ ceiling.
                queue: List[Tuple[int, int]] = [(x, y)]
                cells: List[Tuple[int, int]] = []
                min_x, min_y = x, y
                while queue:
                    cx, cy = queue.pop()
                    if cx < 0 or cy < 0 or cx >= self.width or cy >= self.height:
                        continue
                    if seen[cy][cx]:
                        continue
                    if self.values[cy][cx] > DARK_ZONE_HEAT_CEILING:
                        continue
                    seen[cy][cx] = True
                    cells.append((cx, cy))
                    if cx < min_x:
                        min_x = cx
                    if cy < min_y:
                        min_y = cy
                    queue.append((cx + 1, cy))
                    queue.append((cx - 1, cy))
                    queue.append((cx, cy + 1))
                    queue.append((cx, cy - 1))
                if len(cells) >= DARK_ZONE_MIN_SIZE:
                    zones.append({
                        "top_left": [min_x, min_y],
                        "size": len(cells),
                    })
        zones.sort(key=lambda z: -int(z["size"]))
        return zones[:8]


# ── layer builders ───────────────────────────────────────────────────


def _world_dims(agent_view: Mapping[str, Any]) -> Tuple[int, int]:
    world = agent_view.get("world") or {}
    try:
        w = int(world.get("width") or 0)
        h = int(world.get("height") or 0)
    except (TypeError, ValueError):
        return (0, 0)
    return (w, h)


def _zero_grid(width: int, height: int) -> List[List[float]]:
    return [[0.0 for _ in range(width)] for _ in range(height)]


def _disk_cells(centre: Tuple[int, int], radius: int, width: int, height: int) -> Iterable[Tuple[int, int]]:
    cx, cy = int(centre[0]), int(centre[1])
    r2 = int(radius) * int(radius)
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dx * dx + dy * dy > r2:
                continue
            x, y = cx + dx, cy + dy
            if 0 <= x < width and 0 <= y < height:
                yield (x, y)


def _decay(days_ago: int) -> float:
    """Linear decay over the season horizon."""
    if days_ago <= 0:
        return 1.0
    if days_ago >= KNOWLEDGE_DECAY_HORIZON_DAYS:
        return 0.0
    return 1.0 - (float(days_ago) / float(KNOWLEDGE_DECAY_HORIZON_DAYS))


def compute_enemy_knowledge(
    agent_view: Mapping[str, Any],
    memory: Mapping[str, Any],
    width: int,
    height: int,
) -> List[List[float]]:
    """Merged current+historical "what does the enemy see / has seen" layer."""
    if width <= 0 or height <= 0:
        return _zero_grid(width, height)
    grid = _zero_grid(width, height)
    current_day = int((agent_view.get("meta") or {}).get("day") or 0)

    # 1) Current vision: every known enemy probe lights its disk to 1.0.
    intel = agent_view.get("competitor_intel") or {}
    probe_rows: List[Tuple[Tuple[int, int], int]] = []
    for r in (intel.get("persistent_echoes") or []):
        if not isinstance(r, Mapping):
            continue
        if "probe" not in str(r.get("kind") or "").lower():
            continue
        at = r.get("at")
        if not (isinstance(at, (list, tuple)) and len(at) == 2):
            continue
        try:
            x, y = int(at[0]), int(at[1])
        except (TypeError, ValueError):
            continue
        last_day = int(r.get("last_seen_day") or current_day)
        probe_rows.append(((x, y), last_day))
    for r in (intel.get("new_this_day") or []):
        if not isinstance(r, Mapping):
            continue
        if "probe" not in str(r.get("kind") or "").lower():
            continue
        at = r.get("at")
        if not (isinstance(at, (list, tuple)) and len(at) == 2):
            continue
        try:
            x, y = int(at[0]), int(at[1])
        except (TypeError, ValueError):
            continue
        probe_rows.append(((x, y), current_day))

    # Probes within their 3-night lifetime contribute current vision (1.0).
    # Older probe sightings contribute as historical (decayed).
    PROBE_LIFETIME = 3
    for (xy, last_day) in probe_rows:
        days_ago = max(0, current_day - last_day)
        if days_ago <= PROBE_LIFETIME:
            heat = 1.0
        else:
            heat = _decay(days_ago - PROBE_LIFETIME)
        for c in _disk_cells(xy, PROBE_DISK_RADIUS, width, height):
            if heat > grid[c[1]][c[0]]:
                grid[c[1]][c[0]] = heat

    # 2) Enemy harvester plus shapes (current sightings get full 1.0).
    for row in (intel.get("harvesters") or []):
        if not isinstance(row, Mapping):
            continue
        at = row.get("at") or row.get("pos")
        if not (isinstance(at, (list, tuple)) and len(at) == 2):
            continue
        try:
            x, y = int(at[0]), int(at[1])
        except (TypeError, ValueError):
            continue
        for c in _disk_cells((x, y), HARVESTER_PLUS_RADIUS, width, height):
            if 1.0 > grid[c[1]][c[0]]:
                grid[c[1]][c[0]] = 1.0

    # 3) Historical enemy harvester positions from memory (decayed).
    eh_history = (memory or {}).get("enemy_harvester_positions") or {}
    for day_key, cells in eh_history.items():
        try:
            d = int(day_key)
        except (TypeError, ValueError):
            continue
        days_ago = max(0, current_day - d)
        h = _decay(days_ago)
        if h <= 0.0:
            continue
        for xy in cells or []:
            if not (isinstance(xy, (list, tuple)) and len(xy) == 2):
                continue
            try:
                x, y = int(xy[0]), int(xy[1])
            except (TypeError, ValueError):
                continue
            for c in _disk_cells((x, y), HARVESTER_PLUS_RADIUS, width, height):
                if h > grid[c[1]][c[0]]:
                    grid[c[1]][c[0]] = h

    return grid


def compute_red_magnet(agent_view: Mapping[str, Any], width: int, height: int) -> List[List[float]]:
    """Normalized red purity per cell (high = drop magnet for the enemy)."""
    grid = _zero_grid(width, height)
    if width <= 0 or height <= 0:
        return grid

    # Best signal: navigation.best_red_visible / best_red_echo carries explicit
    # value per RED cell. Fall back to red_tiles for synthetic test fixtures.
    nav = agent_view.get("navigation") or {}
    pools: List[List[Mapping[str, Any]]] = [
        nav.get("best_red_visible") or [],
        nav.get("best_red_echo") or [],
        list(agent_view.get("red_tiles") or []),
    ]
    for pool in pools:
        for r in pool:
            if not isinstance(r, Mapping):
                continue
            try:
                x, y = int(r.get("x")), int(r.get("y"))
                v = float(r.get("value") or r.get("purity") or 0)
            except (TypeError, ValueError):
                continue
            if 0 <= x < width and 0 <= y < height:
                v_norm = max(0.0, min(1.0, v / 255.0))
                if v_norm > grid[y][x]:
                    grid[y][x] = v_norm
    return grid


def compute_asset_proximity(
    agent_view: Mapping[str, Any],
    memory: Mapping[str, Any],
    width: int,
    height: int,
) -> List[List[float]]:
    """Inverse Manhattan distance to nearest known enemy probe/harvester."""
    grid = _zero_grid(width, height)
    if width <= 0 or height <= 0:
        return grid

    # Collect anchor positions.
    anchors: List[Tuple[int, int]] = []
    intel = agent_view.get("competitor_intel") or {}
    for r in (intel.get("persistent_echoes") or []) + (intel.get("new_this_day") or []):
        if not isinstance(r, Mapping):
            continue
        if "probe" not in str(r.get("kind") or "").lower() and "harvester" not in str(r.get("kind") or "").lower():
            continue
        at = r.get("at")
        if not (isinstance(at, (list, tuple)) and len(at) == 2):
            continue
        try:
            anchors.append((int(at[0]), int(at[1])))
        except (TypeError, ValueError):
            continue
    for r in (intel.get("harvesters") or []):
        if not isinstance(r, Mapping):
            continue
        at = r.get("at") or r.get("pos")
        if not (isinstance(at, (list, tuple)) and len(at) == 2):
            continue
        try:
            anchors.append((int(at[0]), int(at[1])))
        except (TypeError, ValueError):
            continue
    # Historical harvesters within decay horizon.
    eh = (memory or {}).get("enemy_harvester_positions") or {}
    current_day = int((agent_view.get("meta") or {}).get("day") or 0)
    for day_key, cells in eh.items():
        try:
            d = int(day_key)
        except (TypeError, ValueError):
            continue
        if current_day - d > 2:
            continue
        for xy in cells or []:
            if isinstance(xy, (list, tuple)) and len(xy) == 2:
                try:
                    anchors.append((int(xy[0]), int(xy[1])))
                except (TypeError, ValueError):
                    continue

    if not anchors:
        return grid

    # Inverse Manhattan with saturation at distance 8.
    MAX_D = 8
    for y in range(height):
        for x in range(width):
            d_min = MAX_D + 1
            for ax, ay in anchors:
                d = abs(x - ax) + abs(y - ay)
                if d < d_min:
                    d_min = d
                if d_min == 0:
                    break
            if d_min <= MAX_D:
                grid[y][x] = max(0.0, 1.0 - (d_min / float(MAX_D)))
    return grid


def compute_orbit_inv_distance(
    agent_view: Mapping[str, Any],
    width: int,
    height: int,
) -> List[List[float]]:
    """Inverse distance to enemy orbital column (if known via §3.15 publicity)."""
    grid = _zero_grid(width, height)
    if width <= 0 or height <= 0:
        return grid

    # Try to find an enemy orbit column from intel.
    intel = agent_view.get("competitor_intel") or {}
    col: Optional[int] = None
    for key in ("enemy_orbit_column", "orbit_column", "drop_column"):
        v = intel.get(key)
        if v is None:
            continue
        try:
            col = int(v)
            break
        except (TypeError, ValueError):
            continue
    if col is None:
        # Fall back: infer from observed probe launches (modal column).
        cols: Dict[int, int] = {}
        for r in (intel.get("new_this_day") or []) + (intel.get("persistent_echoes") or []):
            if not isinstance(r, Mapping):
                continue
            at = r.get("at")
            if not (isinstance(at, (list, tuple)) and len(at) == 2):
                continue
            try:
                cx = int(at[0])
            except (TypeError, ValueError):
                continue
            cols[cx] = cols.get(cx, 0) + 1
        if cols:
            col = max(cols.items(), key=lambda kv: kv[1])[0]

    if col is None:
        return grid

    MAX_D = max(8, width // 2)
    for y in range(height):
        for x in range(width):
            d = abs(x - col)
            if d <= MAX_D:
                grid[y][x] = max(0.0, 1.0 - (d / float(MAX_D)))
    return grid


# ── heatmap composer ─────────────────────────────────────────────────


def compute_heatmap(
    agent_view: Mapping[str, Any],
    memory: Mapping[str, Any],
) -> Heatmap:
    """Compose the four layers into a single per-cell heatmap.

    Returns a :class:`Heatmap` even on empty input — callers can treat
    a degenerate (0×0) heatmap as a no-op.
    """
    width, height = _world_dims(agent_view)
    if width <= 0 or height <= 0:
        return Heatmap(
            width=0,
            height=0,
            values=[],
            layer_enemy_knowledge=[],
            layer_red_magnet=[],
            layer_asset_proximity=[],
            layer_orbit_inv=[],
        )
    ek = compute_enemy_knowledge(agent_view, memory or {}, width, height)
    rm = compute_red_magnet(agent_view, width, height)
    ap = compute_asset_proximity(agent_view, memory or {}, width, height)
    oi = compute_orbit_inv_distance(agent_view, width, height)
    out = _zero_grid(width, height)
    for y in range(height):
        for x in range(width):
            v = (
                WEIGHT_ENEMY_KNOWLEDGE * ek[y][x]
                + WEIGHT_RED_MAGNET * rm[y][x]
                + WEIGHT_ASSET_PROX * ap[y][x]
                + WEIGHT_ORBIT_INV * oi[y][x]
            )
            # Clamp for safety.
            if v < 0.0:
                v = 0.0
            elif v > 1.0:
                v = 1.0
            out[y][x] = v
    return Heatmap(
        width=width,
        height=height,
        values=out,
        layer_enemy_knowledge=ek,
        layer_red_magnet=rm,
        layer_asset_proximity=ap,
        layer_orbit_inv=oi,
    )


# ── scoring primitives for consumers ─────────────────────────────────


def engage_ratio(chain_red_value: float, chain_threat_cost: float) -> float:
    """Higher = more worth pursuing.

    Defined as ``value / (threat + ε)`` so a 0-threat chain is finite.
    Compare against :data:`ABANDON_THRESHOLD` to decide demotion.
    """
    epsilon = 0.01
    if chain_red_value <= 0:
        return 0.0
    return float(chain_red_value) / (float(chain_threat_cost) + epsilon)


def effective_step_budget(heat_along_path: float, base: int = MAX_STEP_BUDGET) -> int:
    """DEPRECATED in v0.9.24. Heat no longer caps walker length.

    Retained for back-compat with any external callers / tests that
    still import the symbol. Now always returns ``base`` — heat is a
    SIGNAL, not a chain-shortener. The race-bonus does the
    "short-chain-under-heat" shaping in chain scoring instead.
    """
    return int(base)


def preferred_chain_length(heat_along_path: float) -> int:
    """Soft preference for shorter chains under heat (not a hard cap).

    Returns the *target* action count — used only as a scoring shaper
    by the race-bonus. The walker still walks the full ``MAX_STEP_BUDGET``;
    chains that happen to be shorter just get the bonus.
    """
    if heat_along_path >= HOT_HEAT_THRESHOLD:
        return 3
    if heat_along_path >= MEDIUM_HEAT_THRESHOLD:
        return 4
    return MAX_STEP_BUDGET


def chain_survival_prob(
    heatmap: Heatmap,
    cells: Sequence[Tuple[int, int]],
) -> float:
    """P(harvester completes chain without losing cargo to collision).

    Per §3.17: collision = TOTAL cargo loss. Each step in a hot cell
    multiplies survival by ``(1 - heat × base_rate)``.
    """
    if not cells:
        return 1.0
    p = 1.0
    for xy in cells:
        h = heatmap.value_xy(xy)
        p *= max(0.0, 1.0 - (h * CELL_COLLISION_BASE_RATE))
    return max(0.0, min(1.0, p))


def expected_chain_value(
    chain_red_value: float,
    survival_prob: float,
) -> float:
    """Survival-weighted expected harvest value.

    ``E[value] = red × P(survive) - INVENTORY_LOSS_COST × (1 - P(survive))``
    """
    survive = max(0.0, min(1.0, float(survival_prob)))
    return float(chain_red_value) * survive - INVENTORY_LOSS_COST * (1.0 - survive)


# ── predicted enemy drops ────────────────────────────────────────────


def predicted_enemy_drops(
    heatmap: Heatmap,
    agent_view: Mapping[str, Any],
    memory: Mapping[str, Any],
    *,
    k: int = 3,
) -> List[Dict[str, Any]]:
    """Top-K cells the enemy is most likely to drop on next turn.

    Score = enemy_knowledge × red_magnet (they need both to drop on
    juicy RED, per §3.9.7 live-only rule). The orbit_inv layer modestly
    boosts cells near their drop column.
    """
    if heatmap.width <= 0:
        return []
    cells: List[Tuple[float, int, int]] = []
    for y in range(heatmap.height):
        for x in range(heatmap.width):
            ek = heatmap.layer_enemy_knowledge[y][x]
            rm = heatmap.layer_red_magnet[y][x]
            oi = heatmap.layer_orbit_inv[y][x]
            if rm <= 0 or ek <= 0:
                continue
            score = ek * rm + 0.15 * oi * rm
            cells.append((score, x, y))
    cells.sort(key=lambda t: -t[0])
    out: List[Dict[str, Any]] = []
    for score, x, y in cells[: max(0, int(k))]:
        out.append({
            "at": [x, y],
            "score": round(score, 3),
            "heat": round(heatmap.values[y][x], 3),
            "reason": _drop_prediction_reason(heatmap, x, y),
        })
    return out


def _drop_prediction_reason(heatmap: Heatmap, x: int, y: int) -> str:
    ek = heatmap.layer_enemy_knowledge[y][x]
    rm = heatmap.layer_red_magnet[y][x]
    bits: List[str] = []
    if ek >= 0.7:
        bits.append("enemy has live vision")
    elif ek >= 0.3:
        bits.append("enemy saw recently")
    if rm >= 0.7:
        bits.append("very high red purity")
    elif rm >= 0.3:
        bits.append("moderate red")
    if not bits:
        bits.append("trace signal")
    return "; ".join(bits)


# ── exports ──────────────────────────────────────────────────────────

__all__ = [
    # Constants
    "WEIGHT_ENEMY_KNOWLEDGE",
    "WEIGHT_RED_MAGNET",
    "WEIGHT_ASSET_PROX",
    "WEIGHT_ORBIT_INV",
    "KNOWLEDGE_DECAY_HORIZON_DAYS",
    "PROBE_DISK_RADIUS",
    "HARVESTER_PLUS_RADIUS",
    "ABANDON_THRESHOLD",
    "ABANDON_PENALTY",
    "HIGH_VALUE_THRESHOLD",
    "JUICY_CONTEST_BOOST",
    "HOT_HEAT_THRESHOLD",
    "MEDIUM_HEAT_THRESHOLD",
    "MAX_STEP_BUDGET",
    "INVENTORY_LOSS_COST",
    "CELL_COLLISION_BASE_RATE",
    "RACE_BONUS",
    "RACE_BONUS_MAX_ACTIONS",
    "RACE_BONUS_MIN_VALUE",
    "OFFENSIVE_RESPONSE_BONUS",
    "FOG_GAMBLE_THRESHOLD",
    "SPECULATIVE_HOT_DROP_DAY_GUARD",
    "COUNTER_BLIND_LOOKBACK_DAYS",
    "DROP_BLOCK_HEAT_FLOOR",
    "DROP_BLOCK_HARVESTER_DAMAGE_BONUS",
    "DARK_ZONE_HEAT_CEILING",
    "DARK_ZONE_MIN_SIZE",
    # Types
    "Heatmap",
    # Layer builders
    "compute_enemy_knowledge",
    "compute_red_magnet",
    "compute_asset_proximity",
    "compute_orbit_inv_distance",
    # Composer
    "compute_heatmap",
    # Scoring
    "engage_ratio",
    "effective_step_budget",
    "preferred_chain_length",
    "chain_survival_prob",
    "expected_chain_value",
    # Predictions
    "predicted_enemy_drops",
]
