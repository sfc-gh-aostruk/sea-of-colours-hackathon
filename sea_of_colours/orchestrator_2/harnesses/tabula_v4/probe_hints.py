"""Probe placement hint compiler for Tabula v2.

Answers: given the current fog of war, where should we drop a probe?

Design goal
-----------
Probes are cheap information. A probe launched onto ``(x, y)`` reveals a
Chebyshev-4 disk (81 cells) for the next 3 nights. Two scoring signals
tell us whether a candidate is worth the hour:

1. **AREA_GAIN**
   How many currently-fog cells the disk would reveal. Bigger = more
   information gained. Overlapping with existing LOS is wasted budget.

2. **EDGE_PROMISE**
   Extra value when the disk extends outward from LOS edges that
   already show high-purity RED (seams tend to continue past visible
   boundaries), or when the disk covers cells the engine has flagged
   in ``navigation.best_red_echo``.

The LLM sees ``area_gain`` and ``edge_promise`` as separate ints — no
combined score field, mirroring the "candidates as hints" rule. It's
free to rank, alter, or ignore.

Self-contained
--------------
Reads ``agent_view`` directly. No reach into pilot_v4 / other harnesses.
Keeps Tabula v2 on the same clean-base architecture v1 established.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

# Probe disk radius (Chebyshev). Must match the engine's probe FOV rule.
_PROBE_RADIUS = 4

# Extra weight per unit of edge promise, used ONLY for our internal
# ranking of candidates (the LLM never sees this). Set high enough that
# a 200-purity mass neighbour tips a candidate over one that only wins
# on raw area. Purely a candidate-ordering knob.
_EDGE_WEIGHT = 0.05

_TIER_MULT = {"trace": 0.75, "vein": 1.0, "mass": 1.5, "pure": 3.0}


def _tier_name(purity: int) -> str:
    p = int(purity or 0)
    if p >= 255:
        return "pure"
    if p >= 151:
        return "mass"
    if p >= 51:
        return "vein"
    return "trace"


def _grid_dims(agent_view: Mapping[str, Any]) -> Tuple[int, int]:
    world = agent_view.get("world") or {}
    try:
        return int(world.get("width") or 40), int(world.get("height") or 28)
    except (TypeError, ValueError):
        return 40, 28


def _los_cells(agent_view: Mapping[str, Any]) -> Set[Tuple[int, int]]:
    """Cells currently in live vision (a probe disk or a friendly unit).

    Reads ``world.live[]`` which each cell inside LOS is enumerated in.
    """
    out: Set[Tuple[int, int]] = set()
    for row in ((agent_view.get("world") or {}).get("live") or []):
        if not isinstance(row, Mapping):
            continue
        try:
            out.add((int(row["x"]), int(row["y"])))
        except (TypeError, KeyError, ValueError):
            continue
    return out


def _fog_clusters(agent_view: Mapping[str, Any]) -> List[Dict[str, Any]]:
    return [c for c in (agent_view.get("fog_clusters") or []) if isinstance(c, Mapping)]


def _echo_cells(agent_view: Mapping[str, Any]) -> Dict[Tuple[int, int], int]:
    """Best-red echo readings (cells hinted at beyond LOS). Keyed by
    (x, y) to purity estimate."""
    out: Dict[Tuple[int, int], int] = {}
    for row in (((agent_view.get("navigation") or {}).get("best_red_echo")) or []):
        if not isinstance(row, Mapping):
            continue
        try:
            out[(int(row["x"]), int(row["y"]))] = int(row.get("purity") or row.get("value") or 0)
        except (TypeError, KeyError, ValueError):
            continue
    return out


# Bright cells inside a bluesign are near-certain to contain real blue.
# Intensity threshold picked so a "well-lit" cluster interior qualifies
# but faint outer cells don't. Tune here if the scoring feels off.
_BLUESIGN_BRIGHT_THRESHOLD = 0.6


def _blue_sign_bright_cells(agent_view: Mapping[str, Any]) -> Dict[Tuple[int, int], float]:
    """Cells inside blue_sign clusters with intensity >= threshold.

    Blue sign is a PUBLIC static map (every seat sees the same data).
    Cluster ``cells`` are ``[[x, y, intensity], ...]`` where intensity
    is 0.0-1.0. High intensity → higher confidence real blue lives at
    (or very near) that cell. Purity is unknown until probed / walked.
    """
    out: Dict[Tuple[int, int], float] = {}
    for cluster in (agent_view.get("blue_sign") or []):
        if not isinstance(cluster, Mapping):
            continue
        for cell in (cluster.get("cells") or []):
            if not isinstance(cell, (list, tuple)) or len(cell) < 3:
                continue
            try:
                x, y, intensity = int(cell[0]), int(cell[1]), float(cell[2])
            except (TypeError, ValueError):
                continue
            if intensity >= _BLUESIGN_BRIGHT_THRESHOLD:
                # Keep the strongest intensity if a cell shows up in
                # multiple clusters (rare but possible on cluster edges).
                out[(x, y)] = max(out.get((x, y), 0.0), intensity)
    return out


def _redsign_cells(agent_view: Mapping[str, Any]) -> Dict[Tuple[int, int], int]:
    """Redsign broadcast cells — public "someone found pure(255) HERE"
    announcements. Empty at start; populates as pure red is discovered.

    Each broadcast row has ``[x, y, hour]`` (or similar); we key by
    (x, y) and store the hour as a freshness signal (lower = more recent
    is arbitrary — presence is what matters).
    """
    out: Dict[Tuple[int, int], int] = {}
    for row in (agent_view.get("redsign") or []):
        if isinstance(row, Mapping):
            try:
                out[(int(row["x"]), int(row["y"]))] = int(row.get("hour") or 0)
            except (TypeError, KeyError, ValueError):
                continue
        elif isinstance(row, (list, tuple)) and len(row) >= 2:
            try:
                out[(int(row[0]), int(row[1]))] = int(row[2]) if len(row) >= 3 else 0
            except (TypeError, ValueError):
                continue
    return out


def _visible_red(agent_view: Mapping[str, Any]) -> Dict[Tuple[int, int], int]:
    """Every RED cell currently in LOS with its purity."""
    out: Dict[Tuple[int, int], int] = {}
    for row in (agent_view.get("red_tiles") or []):
        if not isinstance(row, Mapping):
            continue
        try:
            x, y = int(row["x"]), int(row["y"])
            p = int(row.get("purity") or 0)
        except (TypeError, KeyError, ValueError):
            continue
        if p > 0:
            out[(x, y)] = p
    return out


def _disk(cx: int, cy: int, width: int, height: int) -> List[Tuple[int, int]]:
    r = _PROBE_RADIUS
    return [
        (x, y)
        for x in range(max(0, cx - r), min(width, cx + r + 1))
        for y in range(max(0, cy - r), min(height, cy + r + 1))
    ]


def _seed_candidates(
    agent_view: Mapping[str, Any],
    width: int,
    height: int,
    los: Set[Tuple[int, int]],
) -> Dict[Tuple[int, int], str]:
    """Return ``{(x, y) -> label}`` of candidate probe placements.

    Labels indicate the SOURCE of the seed (rendered as ``extends_from``
    in the hint payload) so the agent can weigh the signal quality:
      * ``"redsign"``      — public "pure(255) here" broadcast (strongest)
      * ``"blue_sign"``    — public bright bluesign cell (strong)
      * ``"echo"``         — this seat's own red echo (weak, often empty)
      * ``"fog_centroid"`` — center of largest fog cluster (neutral)
      * ``"los_edge"``     — nearest_visible_edge to a fog cluster (neutral)
      * ``"seam_extension"`` — one step past a high-purity visible red cell

    Cells fully inside LOS are dropped except when they're echoes (echoes
    live in fog by definition and can still be worth revisiting).
    """
    seeds: Dict[Tuple[int, int], str] = {}

    def _in_bounds(xy: Tuple[int, int]) -> bool:
        return 0 <= xy[0] < width and 0 <= xy[1] < height

    # Strongest signals first — bluesign and redsign are PUBLIC data.
    # (Bounds-checked because external signal data has been observed
    # to reference cells outside the current grid — real bug in v3.)
    for xy in _redsign_cells(agent_view):
        if _in_bounds(xy):
            seeds[xy] = "redsign"
    for xy in _blue_sign_bright_cells(agent_view):
        if _in_bounds(xy):
            seeds.setdefault(xy, "blue_sign")

    # Fog structure — where to un-cover territory blindly.
    for cluster in _fog_clusters(agent_view):
        centroid = cluster.get("centroid")
        if isinstance(centroid, (list, tuple)) and len(centroid) == 2:
            try:
                cxy = (int(centroid[0]), int(centroid[1]))
            except (TypeError, ValueError):
                cxy = None
            if cxy is not None and _in_bounds(cxy):
                seeds.setdefault(cxy, "fog_centroid")
        nve = cluster.get("nearest_visible_edge")
        if isinstance(nve, (list, tuple)) and len(nve) == 2:
            try:
                nxy = (int(nve[0]), int(nve[1]))
            except (TypeError, ValueError):
                nxy = None
            if nxy is not None and _in_bounds(nxy):
                seeds.setdefault(nxy, "los_edge")

    for xy in _echo_cells(agent_view):
        if _in_bounds(xy):
            seeds.setdefault(xy, "echo")

    # Seam extension — one step out from every high-purity visible red.
    red = _visible_red(agent_view)
    ranked_reds = sorted(red.items(), key=lambda kv: kv[1], reverse=True)[:6]
    for (rx, ry), _ in ranked_reds:
        for dx in (-4, -3, 0, 3, 4):
            for dy in (-4, -3, 0, 3, 4):
                if dx == 0 and dy == 0:
                    continue
                cx, cy = rx + dx, ry + dy
                if 0 <= cx < width and 0 <= cy < height:
                    seeds.setdefault((cx, cy), "seam_extension")

    # Filter obviously silly seeds (fully in LOS), except signal cells
    # which we ALWAYS keep even if lit — signals point to real value
    # you want to walk onto, not just un-fog.
    echoes = set(_echo_cells(agent_view).keys())
    signal_cells = set(_redsign_cells(agent_view)) | set(_blue_sign_bright_cells(agent_view))
    return {
        xy: label for xy, label in seeds.items()
        if xy in echoes or xy in signal_cells or xy not in los
    }


def _score_candidate(
    at: Tuple[int, int],
    width: int,
    height: int,
    los: Set[Tuple[int, int]],
    red: Mapping[Tuple[int, int], int],
    echoes: Mapping[Tuple[int, int], int],
) -> Tuple[int, int, List[Tuple[int, int]]]:
    """Return (area_gain, edge_promise, disk_cells) for a candidate."""
    disk_cells = _disk(at[0], at[1], width, height)
    area_gain = sum(1 for c in disk_cells if c not in los)

    # Edge promise: (a) visible red immediately outside the disk (seam
    # extension), plus (b) echo cells inside the disk that would resolve
    # to real red once probed. Both weighted by tier_mult × purity so
    # a pure hint dominates a trace hint.
    edge = 0.0
    disk_set = set(disk_cells)
    # (a) Visible red just outside the disk boundary (Chebyshev-adjacent
    # to any disk cell but not inside the disk itself).
    for (rx, ry), purity in red.items():
        if (rx, ry) in disk_set:
            continue
        # Chebyshev-1 to any disk cell? Cheap check: dist to (at[0],at[1])
        # in (_PROBE_RADIUS, _PROBE_RADIUS+1].
        d = max(abs(rx - at[0]), abs(ry - at[1]))
        if d == _PROBE_RADIUS + 1:
            edge += purity * _TIER_MULT.get(_tier_name(purity), 1.0)
    # (b) Echo cells inside the disk.
    for (ex, ey), purity in echoes.items():
        if (ex, ey) in disk_set:
            edge += purity * _TIER_MULT.get(_tier_name(purity), 1.0)

    return area_gain, int(round(edge)), disk_cells


def top_probe_hints(
    agent_view: Mapping[str, Any],
    *,
    max_hints: int = 3,
    historical_probe_positions: Optional[Sequence[Tuple[int, int]]] = None,
) -> List[Dict[str, Any]]:
    """Return up to ``max_hints`` probe-placement candidates.

    Each hint carries:
      * ``at`` — [x, y] of the probe drop
      * ``area_gain`` — # fog cells the disk would reveal
      * ``edge_promise`` — purity-weighted seam-extension value
      * ``extends_from`` — short label describing why this cell was seeded
        ("fog_centroid", "los_edge", "echo", "seam_extension")

    NO combined score. LLM ranks by re-reading area_gain + edge_promise
    against its own doctrine (RULES probe strategy section).

    ``historical_probe_positions`` — every (x,y) this player has probed
    earlier in the season, including probes that have already expired.
    Without this, the anti-clustering filter is myopic: it only sees
    ACTIVE probes and happily re-suggests the exact same seed once the
    original probe ages out (observed at day 3 of arena_solo_normal
    where probe A came back to (7,4) — same cell as night 1). The
    caller (harness) collects these from ``_SNAPSHOTS.moves_by_day``.

    Empty return means the board has no useful probes right now (either
    no fog at all, or every candidate has area_gain == 0). The LLM is
    trusted to spend its probe elsewhere or skip.
    """
    width, height = _grid_dims(agent_view)
    los = _los_cells(agent_view)
    # NOTE: empty LOS is a legitimate state (day 1 no probes yet). We
    # used to bail here — that was wrong; every cell has max area_gain
    # in that case, and public signals (bluesign, redsign) can still
    # point at useful probes even without any pre-existing LOS.

    fog_count = int(((agent_view.get("world") or {}).get("fog_count")) or 0)
    if fog_count == 0:
        return []

    red = _visible_red(agent_view)
    echoes = _echo_cells(agent_view)

    seeds = _seed_candidates(agent_view, width, height, los)
    if not seeds:
        return []

    # Filter out seeds too close to a currently-active friendly probe OR
    # to any cell where a probe was launched EARLIER this season (even
    # if it has since expired). Active-only filtering was myopic: once a
    # night-1 probe aged out, the compiler happily re-suggested the same
    # cell on night 3, and the LLM followed. History-aware filtering
    # enforces the nomadic doctrine STRUCTURALLY across the whole
    # season, not just within the currently-visible board.
    #
    # We measure "too close" by disk-center Chebyshev distance:
    #   4 = perfect overlap, 8 = no overlap.
    # Threshold=4 kills exact-duplicate coords; threshold=6 kills
    # significant overlap. We use 5 as a middle ground.
    active_probes = _friendly_probe_positions(agent_view)
    prior_probes = list(historical_probe_positions or [])
    all_probes = list({*active_probes, *prior_probes})
    _MIN_PROBE_SEPARATION = 5
    if all_probes:
        filtered_seeds: Dict[Tuple[int, int], str] = {}
        for xy, label in seeds.items():
            too_close = any(
                max(abs(xy[0] - px), abs(xy[1] - py)) < _MIN_PROBE_SEPARATION
                for (px, py) in all_probes
            )
            if not too_close:
                filtered_seeds[xy] = label
        seeds = filtered_seeds
        if not seeds:
            return []

    scored: List[Tuple[float, int, int, Tuple[int, int], str]] = []
    for at, label in seeds.items():
        area_gain, edge_promise, _ = _score_candidate(at, width, height, los, red, echoes)
        # Probes MUST reveal new fog to earn a slot. Removed the previous
        # "signal cells always earn a slot" carve-out — signals are for
        # WALKING (via chain hints / hot drop hints), not for re-probing
        # cells already in LOS. If a bluesign cell is in a friendly
        # probe's disk, we already see it; a new probe there wastes an
        # hour and a probe slot.
        if area_gain <= 0 and edge_promise <= 0:
            continue
        internal_rank = area_gain + _EDGE_WEIGHT * edge_promise
        # Modest bonuses for signal-associated seeds still apply — they
        # bias the compiler toward probes that BOTH reveal new fog AND
        # extend toward a signal cluster. But signals alone (area_gain=0)
        # no longer surface here.
        if label == "redsign":
            internal_rank += 500
        elif label == "blue_sign":
            internal_rank += 100
        scored.append((internal_rank, area_gain, edge_promise, at, label))

    scored.sort(key=lambda t: t[0], reverse=True)

    # De-duplicate near-identical placements (candidates whose disks
    # overlap >75%) so the LLM sees genuinely distinct options.
    hints: List[Dict[str, Any]] = []
    taken_disks: List[Set[Tuple[int, int]]] = []
    for _rank, area_gain, edge_promise, at, label in scored:
        disk_set = set(_disk(at[0], at[1], width, height))
        if any(len(disk_set & taken) / max(1, len(disk_set)) > 0.75 for taken in taken_disks):
            continue
        hints.append({
            "at": [int(at[0]), int(at[1])],
            "area_gain": int(area_gain),
            "edge_promise": int(edge_promise),
            "extends_from": label,
        })
        taken_disks.append(disk_set)
        if len(hints) >= max_hints:
            break

    return hints


# ═══════════════════════════════════════════════════════════════════════
# HOT DROP HINTS — probe at hour K, drop at hour K+1 onto probe's disk
# ═══════════════════════════════════════════════════════════════════════
#
# The engine refreshes live-vision each hour (game/simulator.py:245), so
# a probe applied at hour K becomes live-vision for a drop at hour K+1.
# This lets a single harvester reach a mystery cell in ONE night rather
# than waiting until the next dawn.
#
# A hot drop is only worth suggesting when we have STRONG public reason
# to believe the disk contains harvestable value. The strongest signals:
#   * ``redsign``   — public "pure(255) here" broadcast. Fires when any
#                     seat discovers a pure cell. Whoever probes+drops
#                     first wins ~765 pts × tier_mult. Race the opponent.
#   * ``blue_sign`` — public static map of blue clusters. Bright cells
#                     (>=0.6 intensity) have real blue nearby; the probe
#                     confirms exactly WHERE and the drop crawls onto it.
#                     Purity is unknown until landed, but bluesign
#                     guarantees dense blue is SOMEWHERE in the cluster.
#
# Suppression: bluesign hot drops are dropped when the visible board
# already has >= 3 blue cells in LOS. The agent should prefer KNOWN
# blue over a bluesign gamble when a better option exists.


def top_hot_drop_hints(
    agent_view: Mapping[str, Any],
    *,
    max_hints: int = 3,
) -> List[Dict[str, Any]]:
    """Return up to ``max_hints`` probe-then-drop pairings for this night.

    Each hint carries:
      * ``signal_type``       — "redsign" or "blue_sign"
      * ``signal_intensity``  — float for bluesign (0.6-1.0), 1.0 for redsign
      * ``probe_at``          — [x, y] to launch the probe at hour 1
      * ``drop_at``           — [x, y] the harvester should land on
      * ``area_gain``         — # fog cells the probe reveals (context)
      * ``unit``              — harvester id the drop is scoped to

    Returns [] when:
      * No probes in stock, OR
      * No harvesters in orbit, OR
      * No bluesign bright cells AND no redsign broadcasts
    """
    stock = int((agent_view.get("orbit") or {}).get("probe_stock") or 0)
    if stock <= 0:
        return []

    harvesters = _orbit_harvester_ids(agent_view)
    if not harvesters:
        return []

    width, height = _grid_dims(agent_view)
    los = _los_cells(agent_view)

    # Signal collection. Redsign always ranks first (pure red is worth
    # more per cell than any blue). Blue only surfaces if the visible
    # board isn't already blue-rich — 3+ known blue cells in LOS means
    # bluesign is a suboptimal use of the harvester's night.
    redsign = _redsign_cells(agent_view)
    visible_blue_count = sum(
        1 for row in (agent_view.get("blue_tiles") or [])
        if isinstance(row, Mapping)
    )
    if visible_blue_count >= 3:
        bluesign_bright: Dict[Tuple[int, int], float] = {}
    else:
        bluesign_bright = _blue_sign_bright_cells(agent_view)

    # Build (score, target_cell, signal_type, intensity) triples.
    # redsign gets a fixed high score; bluesign scales by intensity so
    # a 0.9 cell wins over a 0.6 cell.
    targets: List[Tuple[float, Tuple[int, int], str, float]] = []
    for xy, _hour in redsign.items():
        targets.append((10.0, xy, "redsign", 1.0))
    for xy, intensity in bluesign_bright.items():
        targets.append((float(intensity), xy, "blue_sign", float(intensity)))
    if not targets:
        return []
    targets.sort(key=lambda t: t[0], reverse=True)

    hints: List[Dict[str, Any]] = []
    used_probe_positions: Set[Tuple[int, int]] = set()
    used_drop_positions: Set[Tuple[int, int]] = set()

    for _score, (tx, ty), signal_type, intensity in targets:
        if (tx, ty) in used_drop_positions:
            continue
        # Find the probe placement that covers this target AND maximises
        # area_gain. We center on the target and try a small ring of
        # offsets — a slight offset can catch more fog while still
        # covering the target within the Chebyshev-4 disk.
        candidate_probes = [(tx, ty)] + [
            (tx + dx, ty + dy) for dx in (-3, -2, 0, 2, 3) for dy in (-3, -2, 0, 2, 3)
            if not (dx == 0 and dy == 0)
        ]
        chosen_probe = None
        best_gain = -1
        for cx, cy in candidate_probes:
            if not (0 <= cx < width and 0 <= cy < height):
                continue
            if (cx, cy) in used_probe_positions:
                continue
            disk = _disk(cx, cy, width, height)
            if (tx, ty) not in disk:
                continue
            gain = sum(1 for c in disk if c not in los)
            if gain > best_gain:
                best_gain = gain
                chosen_probe = (cx, cy)
        if chosen_probe is None:
            continue

        unit = harvesters[len(hints) % len(harvesters)]
        hints.append({
            "signal_type": signal_type,
            "signal_intensity": round(intensity, 2),
            "probe_at": [int(chosen_probe[0]), int(chosen_probe[1])],
            "drop_at": [int(tx), int(ty)],
            "area_gain": int(best_gain),
            "unit": unit,
        })
        used_probe_positions.add(chosen_probe)
        used_drop_positions.add((tx, ty))
        if len(hints) >= max_hints:
            break

    return hints


def _orbit_harvester_ids(agent_view: Mapping[str, Any]) -> List[str]:
    out: List[str] = []
    for a in (agent_view.get("my_assets") or []):
        if isinstance(a, Mapping) and a.get("kind") == "harvester" and a.get("state") == "orbit":
            uid = a.get("id")
            if isinstance(uid, str):
                out.append(uid)
    return out


def _friendly_probe_positions(agent_view: Mapping[str, Any]) -> List[Tuple[int, int]]:
    """Return the (x, y) center of every currently-active friendly probe.

    Reads from ``agent_view.entities.mine`` (probes are entities of type
    ``probe`` at their launch coord). Excludes probes whose position is
    None (defensive — shouldn't happen for deployed probes) or whose
    remaining nights is 0 (expired but not yet cleared from the view).

    Used by :func:`top_probe_hints` to enforce the nomadic doctrine
    structurally — seeds within :data:`_MIN_PROBE_SEPARATION` of any
    active probe are dropped, so the compiler never suggests a probe
    that duplicates existing vision.
    """
    positions: List[Tuple[int, int]] = []
    for e in ((agent_view.get("entities") or {}).get("mine") or []):
        if not isinstance(e, Mapping):
            continue
        if e.get("type") != "probe":
            continue
        pos = e.get("pos") or e.get("at")
        nr = e.get("nights_remaining")
        if isinstance(nr, (int, float)) and int(nr) <= 0:
            continue
        if isinstance(pos, (list, tuple)) and len(pos) == 2:
            try:
                positions.append((int(pos[0]), int(pos[1])))
            except (TypeError, ValueError):
                continue
    return positions

