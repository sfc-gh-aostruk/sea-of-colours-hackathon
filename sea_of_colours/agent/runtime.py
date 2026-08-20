"""Orchestrator-side glue: agent → SOC engine → audit row.

Exposed as :func:`run_agent_turn`, the single function FastAPI's
``/api/game/{id}/agent/think`` route calls. The contract:

1. Fetch the structured view via :func:`engine.get_view`.
2. Invoke the configured agent runtime (Cortex if available, else the
   in-process :class:`HeuristicAgent`).
3. If the agent returned a non-empty move queue, submit it via
   :func:`engine.submit_policy` (the engine will resolve the night if
   both seats are ready — same path as a human player).
4. Persist a row in SOC_AGENT_INVOCATION via
   :func:`engine.save_agent_rationale`.
5. Return an envelope describing what happened (rationale, tool calls,
   night_resolved flag, elapsed milliseconds, runtime label) for the UI
   to render in the LOG panel.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Mapping, Optional, Tuple

from sea_of_colours.agent.cortex_invoker import CortexAgentInvoker
from sea_of_colours.agent.heuristic_agent import HeuristicAgent
from sea_of_colours.snowpark import engine as soc_engine
from sea_of_colours.snowpark.store import SocStore


# ── Agent identity catalogue ─────────────────────────────────────────
#
# RED_HARVEST is the deterministic Python heuristic — our "mainstay"
# agent. It runs by default, requires no Snowflake / Cortex access,
# and is what powers the [LET RED_HARVEST PLAY] button out of the box.
#
# SOC_RED_REAPER is the first of our AI agents (Snowflake Cortex
# agent declared in `snowflake/soc_create_agent.sql`). Additional
# Cortex agents can be added by registering more entries on the
# ``AI_AGENTS`` map and pointing ``SOC_AGENT_RUNTIME`` /
# ``SOC_CORTEX_AGENT`` at the desired name.
HEURISTIC_AGENT_NAME = "RED_HARVEST"
HEURISTIC_AGENT_TAG = "RHV"  # v0.9.18 — 3-letter tag for UI display

# Hackathon "training wheels" opponent (RULEBOOK-adjacent, see docs/) —
# the same deterministic HeuristicAgent playbook with weapons
# (build_chaff / build_emp / chaff_flare / emp_launch) disabled.
# Selected via ``runtime_override="red_harvest_lite"``.
HEURISTIC_LITE_AGENT_NAME = "RED_HARVEST_LITE"
HEURISTIC_LITE_RUNTIME_KEY = "red_harvest_lite"
CORTEX_AGENT_DEFAULT = "SOC_RED_REAPER"
AI_AGENTS = {
    "SOC_RED_REAPER": {
        "summary": (
            "Red-harvest maximiser; Cortex-driven policy engine. The "
            "harness pre-resolves all world state into the prompt, so "
            "the agent's tool surface is action-only "
            "(soc_submit_policy + soc_save_rationale)."
        ),
        "tag": "SRR",  # v0.9.18 — 3-letter tag for UI display
    },
    "SOC_RED_REAPER_GRID_FAST": {
        "summary": (
            "Sub-60s sibling of GRID_V2; pins claude-3-5-haiku with a "
            "50s/12k-token orchestration budget. Compact TURN COMPILER "
            "prompt distilled from the RED_HARVEST heuristic playbook "
            "(cluster scoring, RED-bracket probes, GREEN avoidance, "
            "mandatory pickup). Paired with a 55s wall-clock cap in "
            "cortex_invoker.WALLCLOCK_CAP_OVERRIDES so a slow model "
            "lands the heuristic fallback well before the next turn."
        ),
        "tag": "GRF",  # v0.9.18 — 3-letter tag for UI display
    },
    "SOC_RED_REAPER_PILOT": {
        "summary": (
            "Rules-in-spec map-reading pilot. ALL doctrine (move grammar, "
            "rules, world.grid reading guide, one-harvester turn procedure) "
            "lives in the agent spec, so the per-turn prompt is a SLIM "
            "envelope + live STATE JSON with the FULL grid intact (see "
            "runtime.RULES_IN_SPEC_AGENTS). claude-3-5-haiku, 120s/30k "
            "budget, single soc_submit_policy tool. Mission: read the whole "
            "board and logic out one good harvester drop + harvest chain."
        ),
        "tag": "PLT",  # 3-letter tag for UI display
    },
}

# Back-compat alias for callers that imported the old name. New code
# should use HEURISTIC_AGENT_NAME or CORTEX_AGENT_DEFAULT explicitly.
AGENT_NAME = HEURISTIC_AGENT_NAME

# Agents whose game rules + world-reading guide live in their *spec*
# (the Snowflake ``instructions.orchestration`` YAML), not in the
# per-turn user message. For these we send a SLIM prompt — a tiny
# envelope + the live STATE JSON (full grid included) — so we stop
# re-transmitting ~16KB of doctrine every turn and never clip the
# board. See :func:`_build_cortex_prompt_slim`.
RULES_IN_SPEC_AGENTS = frozenset({"SOC_RED_REAPER_PILOT"})


def _runtime_mode() -> str:
    return os.environ.get("SOC_AGENT_RUNTIME", "heuristic").strip().lower()


def _cortex_agent_name() -> str:
    return os.environ.get("SOC_CORTEX_AGENT", CORTEX_AGENT_DEFAULT).strip()


# Soft ceiling on stored rationale. The on-screen log + audit table both
# read this column, and a 60KB chain-of-thought makes the log unreadable.
# 2KB is enough for ~6 lines of reasoning + the structured tail; if the
# response has a "**PLAN:**" / "PLAN:" marker we always keep that part
# verbatim so the post-mortem stays intact.
RATIONALE_CAP_CHARS = 2_000


def _smart_truncate_rationale(text: str, cap: int = RATIONALE_CAP_CHARS) -> str:
    """Cap reasoning while preserving the structured PLAN/MOVES/RATIONALE tail.

    Strategy:
    1. If ``text`` fits under the cap, return it unchanged.
    2. Otherwise look for the LAST occurrence of a ``PLAN:`` marker
       (``**PLAN:**`` is the markdown form from the agent spec; bare
       ``PLAN:`` also matches). Everything from that marker onward is
       the "structured summary" — the rest of the budget is split
       between a head excerpt of the reasoning and that tail.
    3. If no marker is present, just hard-cut at ``cap`` and add an
       ellipsis suffix so the truncation is visible in the log.

    The cap is intentionally generous (~2KB ≈ a paragraph or two of
    reasoning + the 3-line PLAN/MOVES/RATIONALE block) — the goal is
    "cap, don't kill", per the player's request.
    """
    if not text or len(text) <= cap:
        return text or ""
    # Find the last PLAN: marker (case-insensitive). Markdown bold form
    # wins over bare form because the agent spec asks for it.
    lower = text.lower()
    plan_idx = lower.rfind("**plan:**")
    if plan_idx < 0:
        plan_idx = lower.rfind("plan:")
    if plan_idx < 0:
        return text[: cap - 16].rstrip() + " …[truncated]"
    tail = text[plan_idx:]
    if len(tail) >= cap:
        # The structured block alone exceeds the cap (rare); take it whole
        # so the player at least sees the final committed plan.
        return tail
    # Budget the head: cap − (tail length + separator)
    sep = "\n…[reasoning truncated]…\n"
    head_budget = cap - len(tail) - len(sep)
    if head_budget < 80:
        # Not enough room for a meaningful preamble — just return tail.
        return tail
    head = text[:head_budget].rstrip()
    return f"{head}{sep}{tail}"


# Hard ceiling on the user-message payload we send to Cortex. The
# warehouse model is happy with ~100KB of context, but the proxy caps
# *responses* at 12KB and our turn budget is 75s — flooding the input
# with a 60KB JSON dump correlates strongly with analysis-paralysis and
# wasted tokens. 20KB fits the densest 40×28 map + 30 red tiles + 12
# log entries + inventory comfortably while leaving headroom for the
# system prompt itself.
#: Hard cap on the cortex user prompt size. Scaled to the
#: ``orchestration.budget.tokens`` in
#: :file:`snowflake/soc_create_agent.sql` — at 36000 tokens (v0.7.2)
#: and ~3 chars/token, the input can comfortably absorb ~28k chars of
#: structured payload before the world.live/echo proximity trimmer
#: starts cropping.
PROMPT_PAYLOAD_CAP_CHARS = 28_000

# Slim-prompt cap for RULES_IN_SPEC agents. Their per-turn message is
# just the envelope + STATE JSON (no doctrine), so the budget can be
# sized to the model's real context instead of the legacy 28k ceiling.
# A dense 40x28 board serialises to ~12-40k chars; 120k leaves ample
# headroom while still catching a pathological runaway. When exceeded
# we WINDOW the grid to the active region (around harvesters + best
# RED) rather than dropping it — the agent must always see the map.
SLIM_PROMPT_CAP_CHARS = 120_000


def _format_red_tile(row: Dict[str, Any]) -> str:
    """One-line render of a red_tiles row for the agent prompt."""
    return (
        f"  - ({row.get('x')}, {row.get('y')}) tier={row.get('tier', '?')} "
        f"value={row.get('value', row.get('purity', 0))} "
        f"freshness={row.get('freshness', '?')} "
        f"dist_to_h={row.get('distance_to_harvester', '?')}"
    )


def _format_fog_cluster(c: Dict[str, Any]) -> str:
    cen = c.get("centroid")
    edge = c.get("nearest_visible_edge")
    return (
        f"  - centroid={cen} size={c.get('size', '?')} "
        f"nearest_visible_edge={edge}"
    )


def _format_log_row(row: Dict[str, Any]) -> str:
    level = row.get("level") or row.get("kind") or "info"
    text = row.get("text") or row.get("message") or json.dumps(row)
    day = row.get("day")
    if day is not None:
        return f"  [day {day}|{level}] {text}"
    return f"  [{level}] {text}"


# ── World-view-aware prompt sections (Phase 1 orchestrator-config A/B) ──
#
# The "READING THE WORLD" primer that the agent sees is the *only*
# part of the prompt that needs to differ between ``list`` and
# ``grid`` orchestrator configs. Everything else (COMMIT-FIRST, hard
# rules, doctrine, navigation, my_assets, filtering contract) is
# shape-agnostic and lives in :func:`_build_cortex_prompt` directly.
#
# We detect the active shape from the agent view's ``world`` block:
# presence of ``grid`` → grid mode; presence of ``live``/``echo`` →
# list mode. This keeps the runtime stateless — the same code path
# serves both the live Cortex agent (per env var) and the eval
# framework (per config).
_WORLD_PRIMER_COMMON_HEAD = (
    "\nREADING THE WORLD JSON (next section is the live payload):\n"
    "\n"
    "Top-level keys you must care about:\n"
    "  - meta           — day, phase, policy_actions_left/max, season.\n"
    "  - hud            — score, hoard {used, max, free, pct_full, by_tier, warning},\n"
    "                     shipped (same shape). If a warning string is present, read it —\n"
    "                     it names which tier the next overflow will jettison.\n"
    "  - last_night     — yesterday's recap. my_orders has outcome='ok'|'illegal' with a\n"
    "                     reason for illegal entries. my_assets_destroyed lists what you lost.\n"
    "                     my_parcels_banked is what you actually got.\n"
    "  - competitor_intel — what the opponent did, that you can lawfully see. new_this_day\n"
    "                     contains enemy_probe_launch (always visible per §3.15) and\n"
    "                     enemy_harvester_trail (only cells you witnessed). NO\n"
    "                     enemy_harvester_drop rows because of the magnetic cover.\n"
    "                     persistent_echoes are older sightings still on your memory.\n"
)

_WORLD_PRIMER_LIST = (
    "  - world          — addressable cells partitioned by visibility tier:\n"
    "      world.live[]    cells you can currently see (full provenance: tile, purity, value,\n"
    "                      square_id, lineage, parent_square_id, trail, entity).\n"
    "      world.echo[]    cells you have seen at some point. Carries last_seen_day and\n"
    "                      via ('probe_launch' = came from §3.15 publicity). Tile/purity\n"
    "                      may be STALE — the cell could have changed since.\n"
    "      world.fog_count number of cells you have NEVER seen. They are not enumerated;\n"
    "                      any (x,y) within (width, height) NOT in live or echo is fog.\n"
    "\n"
    "      TRAIL SHAPE (v0.7.2 — universal, not player-specific):\n"
    "        Each visible cell may carry a `trail` object:\n"
    "          {\n"
    "            \"n\":            aggregate crossings across BOTH seats,\n"
    "            \"tier\":         1..4 density tier derived from n,\n"
    "            \"harvested\":    true if any seat has harvested this cell (optional),\n"
    "            \"fresh_visits\": [ {owner, h, day, n}, ... ]  // last 24h only\n"
    "          }\n"
    "        Use `n` / `tier` for traffic density (anonymous). Use\n"
    "        `fresh_visits` to identify whose harvester walked through in\n"
    "        the past day — that is the ONLY attribution channel. After\n"
    "        24h game time, crossings collapse into the anonymous total\n"
    "        and `fresh_visits` empties. `harvested=true` means the cell\n"
    "        is now synthetic green (banking it scores ZERO — avoid).\n"
)

_WORLD_PRIMER_GRID = (
    "  - world          — 2D nested-array board with spatial structure baked in:\n"
    "      world.width / world.height — board dimensions.\n"
    "      world.grid[y][x] — the cell at (x, y). Read it like a map:\n"
    "                         row y is `world.grid[y]`, column x is index `[x]`,\n"
    "                         east neighbour is `world.grid[y][x+1]`, south neighbour\n"
    "                         is `world.grid[y+1][x]`, etc. No counting characters,\n"
    "                         no scanning a flat list for (x±1, y).\n"
    "      world.fog_count number of cells you have NEVER seen (a count, not a list).\n"
    "\n"
    "      CELL SHAPES inside `world.grid[y][x]`:\n"
    "        null                — fog (never seen). NOT legal to step into blindly\n"
    "                              from orbit (drop will land on whatever's underneath);\n"
    "                              prefer probing instead.\n"
    "        {tile:'EMPTY'}      — visible empty ground (no parcel here).\n"
    "        {tile:'RED',  purity:N, value:N}\n"
    "                            — visible RED. `value` is what gets banked if you\n"
    "                              harvest it (0..255). Sort by `value` to find the\n"
    "                              juiciest cell.\n"
    "        {tile:'GREEN', synthetic?:true}\n"
    "                            — visible green. `synthetic=true` means a previously-\n"
    "                              harvested RED — banking it scores ZERO and wastes\n"
    "                              a hold slot. Route AROUND these cells.\n"
    "        {tile:'BLUE'}       — visible BLUE (lowest vault tier, see §3.14).\n"
    "        {..., entity:{kind, owner, carrying?}}\n"
    "                            — cell is occupied. owner=='p1' or 'p2'. NEVER step\n"
    "                              onto an enemy harvester (§3.17 mutual damage) or\n"
    "                              your own probe (you'd crush it).\n"
    "        {..., echo:true, last_seen_day?:N}\n"
    "                            — stale memory; tile/purity may have changed since\n"
    "                              `last_seen_day`. Treat as 'this is what I knew was\n"
    "                              there', not as ground truth.\n"
    "        {..., collision:true}\n"
    "                            — active collision scar from §3.17 (1-day persistence).\n"
    "\n"
    "      DECISION TEMPLATE for a step move from (cx, cy):\n"
    "        next_cell = world.grid[cy + dy][cx + dx]    # for (dx, dy) ∈ N/E/S/W\n"
    "        if next_cell is null       → FOG (step blind; prefer probe)\n"
    "        if next_cell.tile == 'GREEN' and next_cell.synthetic → AVOID (zero score)\n"
    "        if next_cell.entity and next_cell.entity.kind == 'harvester'\n"
    "                                    and next_cell.entity.owner != you  → AVOID (§3.17)\n"
    "        if next_cell.entity and next_cell.entity.kind == 'probe'\n"
    "                                    and next_cell.entity.owner == you  → AVOID\n"
    "        else                       → legal step. RED cells auto-harvest at `value`.\n"
)

_WORLD_PRIMER_COMMON_TAIL_LIST = (
    "  - navigation     — pre-sorted convenience views over world:\n"
    "      best_red_visible — RED tiles in current LOS, sorted by value DESC.\n"
    "      best_red_echo    — RED tiles in echo only (stale but actionable).\n"
    "      best_green / best_blue — same shape for other colours.\n"
    "      fog_clusters     — connected fog regions ranked by size, with a\n"
    "                         nearest_visible_edge anchor — drop probes here.\n"
    "  - my_assets      — every asset you have owned this season. state ∈ {orbit, deployed,\n"
    "                     destroyed, missing}. Destroyed assets carry destroyed_on_day +\n"
    "                     destroyed_reason in their lifetime block.\n"
    "\nFILTERING CONTRACT:\n"
    "  - Plan tactically: iterate world.live (and world.echo as fallback) — skip fog.\n"
    "  - Find your best target: scan navigation.best_red_visible (head of list).\n"
    "  - Avoid §3.14 cascade: check hud.hoard.by_tier + warning BEFORE pickup.\n"
    "  - Anticipate opponent: read competitor_intel.new_this_day for their probe drops.\n"
)

_WORLD_PRIMER_COMMON_TAIL_GRID = (
    "  - navigation     — pre-sorted convenience views (still present in grid mode):\n"
    "      best_red_visible — RED tiles in current LOS, sorted by value DESC.\n"
    "      best_red_echo    — RED tiles in echo only (stale but actionable).\n"
    "      best_green / best_blue — same shape for other colours.\n"
    "      fog_clusters     — connected fog regions ranked by size, with a\n"
    "                         nearest_visible_edge anchor — drop probes here.\n"
    "      Each entry carries (x, y) so you can cross-reference world.grid[y][x] for\n"
    "      full context (neighbours, entity, collision flag, etc).\n"
    "  - my_assets      — every asset you have owned this season. state ∈ {orbit, deployed,\n"
    "                     destroyed, missing}. Destroyed assets carry destroyed_on_day +\n"
    "                     destroyed_reason in their lifetime block.\n"
    "\nFILTERING CONTRACT:\n"
    "  - Plan tactically: pick a target from navigation.best_red_visible (head of list).\n"
    "    Then walk world.grid[y][x] cell-by-cell to plan the path — null = fog (skip),\n"
    "    everything else is actionable terrain.\n"
    "  - Adjacency: world.grid[y][x±1] / world.grid[y±1][x] gives you the four cardinal\n"
    "    neighbours directly. No need to scan a flat list.\n"
    "  - Avoid §3.14 cascade: check hud.hoard.by_tier + warning BEFORE pickup.\n"
    "  - Anticipate opponent: read competitor_intel.new_this_day for their probe drops.\n"
)


def _build_reading_block(agent_view: Mapping[str, Any]) -> str:
    """Assemble the 'READING THE WORLD JSON' primer for the active world shape.

    Detection is by presence: if ``world.grid`` is in the payload we
    use the grid primer, otherwise we fall back to the list primer.
    This means a single deployed Cortex agent could in principle
    handle both shapes if the runtime prompted accordingly — though
    in practice we deploy one Cortex agent per shape (with matching
    base instructions) for clarity.
    """
    world = agent_view.get("world") or {}
    if "grid" in world:
        world_block = _WORLD_PRIMER_GRID
        tail = _WORLD_PRIMER_COMMON_TAIL_GRID
    else:
        world_block = _WORLD_PRIMER_LIST
        tail = _WORLD_PRIMER_COMMON_TAIL_LIST
    return _WORLD_PRIMER_COMMON_HEAD + world_block + tail


def _build_cortex_prompt_slim(
    session_id: str,
    view: Dict[str, Any],
    agent_name: Optional[str] = None,
) -> str:
    """Per-turn message for RULES_IN_SPEC agents — state only, no doctrine.

    The agent's spec (``instructions.orchestration``) already carries
    the move grammar, hard rules, and the ``world.grid[y][x]`` reading
    guide, so we never re-send them. The per-turn payload is a tiny
    envelope (whose turn, which seat, action budget) plus the live
    STATE JSON — meta / hud / last_night / competitor_intel / world /
    navigation / my_assets — with the FULL grid intact.

    Capped at :data:`SLIM_PROMPT_CAP_CHARS`. On the rare dense board
    that overflows, we WINDOW ``world.grid`` to the active region
    (bounding box around harvesters + ``navigation.best_red_visible``,
    padded) instead of dropping it, so the agent always sees the map.
    """
    import json as _json

    agent_view = view.get("agent_view") or {}
    meta = agent_view.get("meta") or {}
    hud = agent_view.get("hud") or {}
    day = meta.get("day") or hud.get("day", view.get("day"))
    player = meta.get("player") or hud.get("player", "p1")
    season_cap = hud.get("season_day_cap") or 7
    policy_max = meta.get("policy_actions_max", 21)
    policy_left = meta.get("policy_actions_left", policy_max)

    structured_payload: Dict[str, Any] = {
        "meta": agent_view.get("meta") or {},
        "hud": agent_view.get("hud") or {},
        "last_night": agent_view.get("last_night") or {},
        "competitor_intel": agent_view.get("competitor_intel") or {},
        "world": dict(agent_view.get("world") or {}),
        "navigation": agent_view.get("navigation") or {},
        "my_assets": agent_view.get("my_assets") or [],
    }

    def _serialise(payload: Dict[str, Any]) -> str:
        return _json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    envelope = (
        "SEA OF COLOURS — turn brief. The rules, move grammar, and how to "
        "read world.grid are in your system instructions; do not expect "
        "them here.\n"
        f"session={session_id} day={day}/{season_cap} seat={player} "
        f"actions_left={policy_left}/{policy_max}\n"
        "Read STATE below, then CALL soc_submit_policy on your FIRST "
        'tool call with p_policy as a JSON STRING: {"moves":[...]}.\n'
    )

    state_block = "\nSTATE (JSON):\n```json\n" + _serialise(structured_payload) + "\n```\n"
    body = envelope + state_block
    if len(body) <= SLIM_PROMPT_CAP_CHARS:
        return body

    # Over cap — window the grid to the active region. Keep grid
    # dimensions (so world.grid[y][x] indexing stays valid) but null
    # out non-anchor cells outside the bounding box.
    world = dict(structured_payload["world"] or {})
    grid = world.get("grid")
    if isinstance(grid, list) and grid:
        anchors: List[Tuple[int, int]] = []
        for a in structured_payload["my_assets"] or []:
            at = a.get("at") if isinstance(a, dict) else None
            if isinstance(at, list) and len(at) == 2:
                anchors.append((int(at[0]), int(at[1])))
        nav = structured_payload["navigation"] or {}
        for r in (nav.get("best_red_visible") or []):
            if isinstance(r, dict) and isinstance(r.get("x"), int) and isinstance(r.get("y"), int):
                anchors.append((int(r["x"]), int(r["y"])))
        if anchors:
            margin = 8
            xs = [a[0] for a in anchors]
            ys = [a[1] for a in anchors]
            x0, x1 = min(xs) - margin, max(xs) + margin
            y0, y1 = min(ys) - margin, max(ys) + margin
            windowed = [
                [
                    cell if (cell is not None and x0 <= x <= x1 and y0 <= y <= y1) else None
                    for x, cell in enumerate(row)
                ]
                for y, row in enumerate(grid)
            ]
            world["grid"] = windowed
            world["windowed_bbox"] = [max(0, x0), max(0, y0), x1, y1]
            structured_payload["world"] = world
            body2 = (
                envelope
                + "\nSTATE (JSON, world.grid windowed to the active region "
                "[x0,y0,x1,y1]):\n```json\n"
                + _serialise(structured_payload)
                + "\n```\n"
            )
            if len(body2) <= SLIM_PROMPT_CAP_CHARS:
                return body2

    return body[: SLIM_PROMPT_CAP_CHARS - 32].rstrip() + "\n…[prompt truncated]\n"


def _build_cortex_prompt(
    session_id: str, view: Dict[str, Any], agent_name: Optional[str] = None,
) -> str:
    """Harness envelope — v0.7.0 structured-JSON briefing.

    The Cortex agent's tool surface is exactly two entries:
    ``soc_submit_policy`` and ``soc_save_rationale``. There is no
    mid-turn re-decision in the engine — agents see, decide, submit.
    So this builder packs everything the agent could otherwise fetch
    into a single structured user message.

    Sections (in order):

    1. ``HEADER`` — session, day, season, seat, scores, policy budget.
    2. ``CONTRACT`` — the two tools and the no-mid-turn-refetch rule.
    3. ``HARD RULES`` — move grammar, 21-action fleet cap, Magnetic
       Cover (§0.4), §3.15 orbital publicity, §3.16 probe collisions,
       harvest doctrine, vault tier ladder, harvester lifecycle,
       adjacency rule.
    4. ``READING THE WORLD JSON`` — primer for the payload that
       follows, including the fog-of-war filtering contract.
    5. ``STATE`` — a single ```json``` fence containing the live
       agent payload (meta / hud / last_night / competitor_intel /
       world / navigation / my_assets).

    Hard-capped at :data:`PROMPT_PAYLOAD_CAP_CHARS`. If the cap is
    exceeded we shrink ``world.live`` / ``world.echo`` by sorting
    cells by Manhattan distance to the nearest deployed harvester
    and keeping only the top-N.

    Agents listed in :data:`RULES_IN_SPEC_AGENTS` carry their doctrine
    in the Snowflake spec, so they get the slim state-only message via
    :func:`_build_cortex_prompt_slim` instead of this verbose envelope.
    """
    if agent_name and agent_name in RULES_IN_SPEC_AGENTS:
        return _build_cortex_prompt_slim(session_id, view, agent_name=agent_name)

    import json as _json

    agent_view = view.get("agent_view") or {}
    meta = agent_view.get("meta") or {}
    hud = agent_view.get("hud") or {}
    day = meta.get("day") or hud.get("day", view.get("day"))
    player = meta.get("player") or hud.get("player", "p1")
    season = (
        meta.get("season")
        or hud.get("season_name")
        or view.get("season_name")
        or "(unnamed)"
    )
    season_cap = hud.get("season_day_cap") or 7
    policy_max = meta.get("policy_actions_max", 21)
    policy_left = meta.get("policy_actions_left", policy_max)

    header = (
        "COMMIT-FIRST PROTOCOL — READ BEFORE ANYTHING ELSE.\n"
        "Your single dominant failure mode is *over-deliberation*. You\n"
        "enumerate 'option A vs option B vs option C', argue yourself in\n"
        "circles, run out of wallclock, and the heuristic takes the seat.\n"
        "An UNSUBMITTED 'perfect' plan scores ZERO. A SUBMITTED 'good'\n"
        "plan scores its actual value. Therefore:\n"
        "  1. Pick the highest-purity RED tile in navigation.best_red_visible\n"
        "     (index 0). That is your target. Do not second-guess this.\n"
        "  2. Build ONE chain: drop on or adjacent to it, step toward it /\n"
        "     its highest-purity RED neighbours, pickup. ≤5 steps total.\n"
        "  3. CALL soc_submit_policy NOW with that chain. THEN reason\n"
        "     post-hoc in soc_save_rationale if you must. NEVER let\n"
        "     'let me reconsider...' precede the submit tool call.\n"
        "  4. If the prompt below contains 'best_red_visible: []' and\n"
        "     'best_red_echo: []' — submit ONLY probes on the largest\n"
        "     navigation.fog_clusters. Do not blind-drop harvesters.\n"
        "RULE: at MOST one 'wait,' / 'hmm,' / 'reconsider' / 'actually'\n"
        "in your entire reasoning trace. If you catch yourself writing a\n"
        "second one — STOP, submit the current best plan, MOVE ON.\n"
        "\n"
        "CORE OBJECTIVE — SEEK OUT DENSE RED.\n"
        "Your score is the sum of purity across every RED parcel you bank.\n"
        "Purity is 0-255: trace ≤ 50, vein 51-150, mass 151-254, pure 255.\n"
        "ONE pure parcel beats FIVE trace parcels. A 6-step detour to a vein\n"
        "or mass cell almost always beats a 1-step grab of trace. Mining\n"
        "trace because it's nearby is the minimum-effort play and almost\n"
        "always wrong. Probes are TIER-DISCOVERY currency, not generic\n"
        "vision — spend them on fog INWARD from your trace cells to surface\n"
        "the seam's vein/mass/pure core.\n"
        "\n"
        f"SESSION: {session_id}\n"
        f"DAY: {day} / {season_cap}  ·  SEASON: {season}  ·  SEAT: {player}\n"
        f"PHASE: {hud.get('phase', '?')}\n"
        f"POLICY BUDGET: {policy_left}/{policy_max} fleet-wide actions remain this night\n"
        f"MY SCORE: {hud.get('score', 0)}  ·  HOARD: "
        f"{(hud.get('hoard') or {}).get('used', 0)}/"
        f"{(hud.get('hoard') or {}).get('max', '?')}  ·  SHIPPED: "
        f"{(hud.get('shipped') or {}).get('used', 0)}/"
        f"{(hud.get('shipped') or {}).get('max', '?')}\n"
    )

    contract = (
        "\nAll game context for this turn is pre-loaded below. You "
        "have exactly TWO tools:\n"
        "  1. soc_submit_policy(p_session_id, p_player, p_policy)  "
        "— submit your move queue as a JSON STRING.\n"
        "  2. soc_save_rationale(p_session_id, p_day, p_agent_id, "
        "p_player, p_rationale)  — write your post-mortem.\n"
        "Call them in that order. There is no mid-turn re-fetch — "
        "the engine runs PRAXIS (executes both seats' policies "
        "simultaneously across the 21-hour night) only after BOTH seats "
        "lock policy. Each applied move is one hour of the planetary "
        "night. Skip the reads, decide on the data below, and act.\n"
        "\n"
        "FORBIDDEN TOOL NAMES (these do NOT exist on this agent — calling "
        "them wastes the turn and returns 'unknown tool' errors that we "
        "log against your name):\n"
        "  - soc_get_view          (we already include world JSON below)\n"
        "  - soc_get_inventory     (see hud + my_assets below)\n"
        "  - soc_get_log           (see last_night below)\n"
        "  - soc_get_leaderboard   (see hud.score + competitor_intel)\n"
        "  - soc_list_sessions     (irrelevant to a turn)\n"
        "If you 'feel' you need a view tool, scroll up — the data is "
        "already in this message. Do NOT invent or attempt them.\n"
        "\n"
        "WIRE FORMAT FOR soc_submit_policy (the #1 reason policies get "
        "rejected): `p_policy` MUST be a JSON STRING, not a structured "
        "object. The warehouse runtime cannot pass OBJECT params through "
        "tool calls, so wrap the envelope as a string:\n"
        "  p_policy = \"{\\\"moves\\\":[{\\\"a\\\":\\\"probe\\\",\\\"at\\\":[8,5]}]}\"\n"
        "If the proc rejects your call, the seat will lock empty under "
        "your name and the round will count as a wasted turn.\n"
    )

    # v0.9.17 — drop legality reflects the ACTIVE ruleset (env knobs read
    # at runtime, §3.9.7). Default mode keeps the live-or-echo wording.
    from sea_of_colours.game import tuning as _tuning
    _probe_radius = _tuning.probe_vision_radius()
    _probe_life = _tuning.probe_lifetime_nights()
    _life_line = (
        f"  - Probes EXPIRE after {_probe_life} night(s) on the surface "
        f"(disk drops to echo) — re-probe to keep a claim live.\n"
        if _probe_life else ""
    )
    if _tuning.live_only_drops():
        drop_rules_block = (
            "DROP LEGALITY (§3.9.7) — LIVE-ONLY MODE ACTIVE:\n"
            "  - You may ONLY drop a harvester onto a cell you see LIVE right now: inside an\n"
            "    active probe disk, or under a friendly harvester's plus. Stale own-echo /\n"
            "    memory does NOT qualify. To farm a remembered vein, drop a PROBE on it FIRST\n"
            "    this night, then land there next night.\n"
            "  - Probe launches are PUBLIC (§3.15): a probe broadcasts exactly which vein you\n"
            "    intend to farm. Expect the cell to be contested — and consider SUPERSEDING a\n"
            "    rival's probe (below) to void their queued landing on a vein you both want.\n"
            f"  - Probe vision radius = {_probe_radius} (Euclidean disk).\n"
            + _life_line
            + "\n"
        )
    else:
        drop_rules_block = (
            "DROP LEGALITY (§3.9.7):\n"
            "  - Drop a harvester onto any cell that is LIVE now OR carries your OWN echo/memory\n"
            "    snapshot. Enemy probe-launch markers do NOT reveal terrain — never blind-drop\n"
            "    onto a cell you've only seen as an enemy launch.\n"
            f"  - Probe vision radius = {_probe_radius} (Euclidean disk).\n"
            + _life_line
            + "\n"
        )

    rules_block = (
        "\nHARD RULES (v0.7.0 — read before you decide):\n"
        "\n"
        "MOVE GRAMMAR — your queue is a JSON array; exactly four shapes are legal:\n"
        '  {"a":"probe",  "at":[x,y]}                          → deploy a probe at (x,y)\n'
        '  {"a":"drop",   "unit":"<harvester_id>", "at":[x,y]} → drop a harvester from orbit onto (x,y)\n'
        '  {"a":"step",   "unit":"<harvester_id>", "to":[x,y]} → walk a harvester ONE tile (Manhattan distance == 1)\n'
        '  {"a":"pickup", "unit":"<harvester_id>"}             → lift a harvester back to orbit with whatever it carries\n'
        "Anything else (missing fields, wrong key names, made-up unit IDs, [x,y] not a 2-length list of ints) "
        "is rejected and surfaces in last_night.my_orders with outcome='illegal' + a reason. Illegal items "
        "do NOT consume your action slot, but they DO tell us you didn't read the rules.\n"
        "\n"
        "POLICY BUDGET (fleet-wide, NOT per-harvester):\n"
        f"  - Up to {policy_max} VALID actions applied per player per night across your whole fleet.\n"
        f"    Sized for 3 harvesters at full tilt: 3 x (drop + 5 step + pickup) = {policy_max}.\n"
        "  - Each drop / step / pickup / probe is one action.\n"
        "  - Per-HARVESTER step limit is 5 per night (separate from this fleet-wide cap).\n"
        "  - Harvester HOLD = 6 parcels per outing (drop tile + 5 step tiles). No per-colour cap.\n"
        "  - Queue length ceiling 100 entries (extras dropped at parse time).\n"
        "\n"
        "THE MAGNETIC COVER (§0.4 — why the visibility rules below exist):\n"
        "  The planet is sheathed in a magnetic cover; the surface cannot be read from orbit.\n"
        "  - You CANNOT see RED purity or topography from orbit. Probes + harvester LOS are your\n"
        "    only sensors. This is the root cause of fog-of-war.\n"
        "  - Probe trajectories punch the cover unbent → probe LAUNCHES are publicly observable.\n"
        "  - Orblifts bend through the magnetosphere on descent → harvester DROPS are private.\n"
        "  - Probe telemetry does NOT transit the cover; your probes' sensor data stays with you.\n"
        "\n"
        "ORBITAL PUBLICITY (§3.15) — direct consequence of the cover:\n"
        "  - Every PROBE you deploy: the opponent sees the landing cell in their world.echo for\n"
        "    that night with via='probe_launch' and a fresh last_seen_day. They learn the tile\n"
        "    and purity you punched. Probe placement TELEGRAPHS your interest.\n"
        "  - Every HARVESTER you drop: the opponent learns NOTHING about the drop itself. They\n"
        "    only discover the harvester via its trail after it moves, or via their probes' LOS.\n"
        "  - Conversely: read competitor_intel.new_this_day for enemy_probe_launch rows — the\n"
        "    opponent has just told you what cells they care about.\n"
        "\n"
        + drop_rules_block +
        "PROBE COLLISIONS (§3.16):\n"
        "  - Land on an OLDER probe (earlier hour, or one persisted from a prior night) and your\n"
        "    new probe DESTROYS + SUPERSEDES it — your probe survives, theirs is removed (logged\n"
        "    `probe_superseded`). Use this to evict a rival's recon probe from a cell you want.\n"
        "  - Two probes landing on the SAME turn (same hour) at one cell — any ownership — BOTH\n"
        "    destroyed (`probe_collision`). Avoid stacking on obvious centroids the opponent is\n"
        "    likely to also probe THIS turn.\n"
        "\n"
        "HARVESTER COLLISIONS — MUTUAL DAMAGE (§3.17, v0.7.3):\n"
        "  - Two harvesters arriving on the SAME cell DAMAGE each other (NOT destroy). Same rule\n"
        "    for: (1) drop-on a healthy harvester, (2) step-into a healthy harvester, (3) pass-\n"
        "    through swap (A:(10,5)→(11,5) crossing B:(11,5)→(10,5) in the same round).\n"
        "  - Both harvesters end the action `damaged=True`, both spill ALL cargo on the spot,\n"
        "    both stay on the surface (no orbital recall).\n"
        "  - A `damaged` harvester cannot step or harvest — only `pickup` will repair it in orbit\n"
        "    next night. Dawn still destroys damaged harvesters left out (§3.11.2).\n"
        "  - Damaged harvesters DO NOT block movement; healthy harvesters can drop/step onto a\n"
        "    wreck-cell without triggering another collision. Multiple wrecks can share a tile.\n"
        "  - Cells with active collision scars are marked in `world.live[*].collision = {age, owners}`\n"
        "    for one game day. `age=0` is tonight's, `age=1` is yesterday's.\n"
        "  - STRATEGIC IMPLICATION: never drop or step onto a cell where the enemy harvester is\n"
        "    currently sitting (check `world.live[*].entity` and `competitor_intel`). The harvest\n"
        "    is worth far less than the cargo you'd forfeit. Pick a sibling cell with similar\n"
        "    RED density — adjacent tiles in a seam are usually within one purity tier (§2.2).\n"
        "\n"
        "VISION (v0.6.0):\n"
        "  - Harvester vision is a PLUS: self + 4 cardinal neighbours (N/S/E/W). Diagonals are fog.\n"
        "  - Probe vision is a Euclidean disk of radius 4 (~49 cells).\n"
        "  - Walking lays a 3-cell-wide ribbon of echo intel along the path.\n"
        "\n"
        "HARVEST DOCTRINE — what entering a coloured tile does:\n"
        "  - RED   → GREEN(255). The RED's parcel is banked at its original purity (0-255). A new\n"
        "    synthetic-green identity is minted at (x,y).\n"
        "  - GREEN → EMPTY.       The GREEN's parcel is banked; tile becomes bare ground.\n"
        "  - BLUE  → EMPTY.       The BLUE's parcel is banked; tile becomes bare ground.\n"
        "  Only RED parcels contribute to score (purity 0..255 each). GREEN/BLUE fill the hoard\n"
        "  without scoring. Synthetic green is a receipt of a prior RED harvest — re-harvesting it\n"
        "  is wasted hold space.\n"
        "\n"
        "VAULT TIER LADDER (§3.14) — what happens at pickup when the 15-slot vault is FULL:\n"
        "  Tier 3 (top, never displaced):    GREEN\n"
        "  Tier 2 (middle):                  RED\n"
        "  Tier 1 (bottom, always preempted): BLUE\n"
        "  - GREEN incoming displaces lowest BLUE → else lowest RED → else jettisoned.\n"
        "  - RED   incoming displaces lowest BLUE → else lowest RED IF strictly higher purity → else jettisoned.\n"
        "  - BLUE  incoming displaces lowest BLUE IF strictly higher purity → else jettisoned.\n"
        "  Read hud.hoard.warning — when not null, it names the tier the next overflow will jettison.\n"
        "\n"
        "HARVESTER LIFECYCLE — the #1 way agents lose value:\n"
        "  1. Harvesters begin the day IN ORBIT (state='orbit', at=null). Use `drop` first.\n"
        "  2. After `drop` the harvester is ON SURFACE. It auto-harvests any coloured tile underfoot.\n"
        "     Each `step` moves it to one of 4 cardinal neighbours (NOT diagonal, NOT multi-tile).\n"
        "  3. Before night end you MUST `pickup` that harvester. Dawn destroys anything left on\n"
        "     the surface (harvester + all cargo). Your last move for every deployed harvester\n"
        "     should be a pickup.\n"
        "  4. A harvester whose unit-id isn't in my_assets is not yours — referencing it is wasted.\n"
        "\n"
        "ADJACENCY / VALUE — what to actually aim for:\n"
        "  - Purity grows monotonically with Manhattan depth from the nearest non-RED tile.\n"
        "    Edges of a seam are 'trace' (~1-60); centre of a thick seam is 'pure' (~200-255).\n"
        "  - Your score is the sum of origin_purity across every RED parcel you bank.\n"
        "    One pure RED parcel (~250) is worth FIVE trace RED parcels (~50).\n"
        "  - From a visible RED edge, step INWARD (toward the RED neighbour with the most RED of\n"
        "    its own) to climb toward 'pure'. Don't waste steps along a trace boundary.\n"
        "\n"
        "JUICY SEAM DOCTRINE — read this before every harvest decision:\n"
        "  - Mining TRACE is the MINIMUM-EFFORT play. A trace parcel scores ~10-50; a pure parcel\n"
        "    scores 255. Five trace tiles = one pure tile. Trace tiles are the consolation prize\n"
        "    when nothing better is visible, NOT the target.\n"
        "  - Your job each night is to find the JUICIEST cell available and route a harvester to\n"
        "    it. The hierarchy from worst to best is:\n"
        "      trace (0-50)  →  vein (51-150)  →  mass (151-254)  →  pure (255)\n"
        "  - WHEN ALL YOU CAN SEE IS TRACE: that means the live LOS only touches seam edges.\n"
        "    Don't settle. Spend probes on fog clusters that BORDER your trace tiles — the seam\n"
        "    deepens INWARD, and one cell of depth typically jumps a tier. Use\n"
        "    navigation.fog_clusters where nearest_visible_edge is a trace cell to find these.\n"
        "  - Probes are your TIER-DISCOVERY budget, not just generic vision. A probe sitting on\n"
        "    fog adjacent to mass/pure RED is worth far more next turn than one in the corner.\n"
        "  - On the FINAL night of the season (meta.day == hud.season_day_cap) probes return\n"
        "    nothing — only banked parcels score, so on day N spend all your actions on harvest.\n"
    )

    reading_block = _build_reading_block(agent_view)

    structured_payload = {
        "meta": agent_view.get("meta") or {},
        "hud": agent_view.get("hud") or {},
        "last_night": agent_view.get("last_night") or {},
        "competitor_intel": agent_view.get("competitor_intel") or {},
        "world": dict(agent_view.get("world") or {}),
        "navigation": agent_view.get("navigation") or {},
        "my_assets": agent_view.get("my_assets") or [],
    }

    def _serialise(payload: Dict[str, Any]) -> str:
        return _json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    closing = (
        "\nSUBMIT NOW. Pull navigation.best_red_visible[0] as your target, "
        "build a ≤7-action chain (drop + ≤5 steps toward that cell or its "
        "RED neighbours + pickup), and CALL soc_submit_policy on the FIRST "
        "tool call. Do not write a second 'alternative route' before the "
        "submit lands. Every paragraph you write past the first chain is "
        "wallclock the heuristic gets to steal your turn.\n"
        "Pickup is mandatory — dawn destroys anything left on the surface.\n"
        "If best_red_visible is empty, submit probes on the largest fog "
        "clusters and an empty harvester queue; do NOT blind-drop.\n"
    )

    state_block = (
        "\nSTATE (JSON):\n```json\n" + _serialise(structured_payload) + "\n```\n"
    )
    prose = header + contract + rules_block + reading_block + state_block + closing
    if len(prose) <= PROMPT_PAYLOAD_CAP_CHARS:
        return prose

    # Cap exceeded — shrink the world payload. Trim strategy depends
    # on the active world-view shape:
    #   list mode → sort world.live / world.echo by proximity to the
    #     nearest deployed harvester, keep the top-N.
    #   grid mode → the 2D nested array is dense by construction
    #     (mostly ``null`` fog), so cap-exceeded is rare. If it does
    #     hit, replace the grid with an empty array and a load-bearing
    #     ``truncated_to_nearest: 0`` flag so the agent sees the
    #     truncation explicitly rather than getting a corrupt JSON.
    world = dict(structured_payload["world"] or {})
    is_grid_mode = "grid" in world

    def _cell_distance(cell: Dict[str, Any], anchor: Optional[Tuple[int, int]]) -> int:
        if anchor is None:
            return 0
        cx = cell.get("x")
        cy = cell.get("y")
        if not isinstance(cx, int) or not isinstance(cy, int):
            return 10_000
        return abs(cx - anchor[0]) + abs(cy - anchor[1])

    deployed: List[Tuple[int, int]] = []
    for a in structured_payload["my_assets"] or []:
        at = a.get("at")
        if isinstance(at, list) and len(at) == 2 and a.get("state") == "deployed":
            deployed.append((int(at[0]), int(at[1])))
    anchor: Optional[Tuple[int, int]] = deployed[0] if deployed else None

    if not is_grid_mode:
        for cap in (200, 120, 80, 40):
            trimmed_world = dict(world)
            live_cells = sorted(world.get("live") or [], key=lambda c: _cell_distance(c, anchor))
            echo_cells = sorted(world.get("echo") or [], key=lambda c: _cell_distance(c, anchor))
            trimmed_world["live"] = live_cells[:cap]
            trimmed_world["echo"] = echo_cells[:cap]
            trimmed_world["truncated_to_nearest"] = cap
            payload2 = dict(structured_payload)
            payload2["world"] = trimmed_world
            state2 = (
                "\nSTATE (JSON, world truncated to nearest "
                + str(cap) + " cells per tier):\n```json\n"
                + _serialise(payload2) + "\n```\n"
            )
            prose2 = header + contract + rules_block + reading_block + state2 + closing
            if len(prose2) <= PROMPT_PAYLOAD_CAP_CHARS:
                return prose2

    # Static prose has grown past the cap with the world payload at its
    # smallest. Strip world.live/echo (or world.grid) entirely so the
    # agent at least gets a clearly-flagged "world view dropped" payload
    # instead of a mid-array hard truncation. ``truncated_to_nearest: 0``
    # is load-bearing: it signals "no per-cell world data" to the agent
    # and to the size-cap regression test.
    trimmed_world = dict(world)
    if is_grid_mode:
        trimmed_world["grid"] = []
    else:
        trimmed_world["live"] = []
        trimmed_world["echo"] = []
    trimmed_world["truncated_to_nearest"] = 0
    payload3 = dict(structured_payload)
    payload3["world"] = trimmed_world
    state3 = (
        "\nSTATE (JSON, world payload dropped — prompt over cap):\n"
        "```json\n"
        + _serialise(payload3) + "\n```\n"
    )
    prose3 = header + contract + rules_block + reading_block + state3 + closing
    if len(prose3) <= PROMPT_PAYLOAD_CAP_CHARS:
        return prose3
    return prose3[: PROMPT_PAYLOAD_CAP_CHARS - 32].rstrip() + "\n…[prompt truncated]\n"


def _annotate_cortex_diagnostics(
    rationale: str,
    *,
    tool_errors: List[Dict[str, Any]],
    hallucinated_tools: List[str],
    wallclock_capped: bool,
    proc_rejection: bool = False,
) -> str:
    """Append a structured diagnostic tail to a Cortex rationale.

    Before this helper existed, Cortex's `soc_submit_policy` failures
    were invisible to operators — the SSE stream's tool-error events
    were dropped and the runtime silently fell back to the heuristic.
    Surfacing the diagnostics here gives the audit row + on-screen log
    a one-line trail of what actually went wrong (proc rejection,
    hallucinated tool, wall-clock cap) so post-mortems aren't
    archaeology.

    Returns ``rationale`` unchanged if there is nothing to report.
    """
    parts: List[str] = []
    if proc_rejection:
        parts.append(
            "[soc_submit_policy was called but the seat is still empty "
            "— the proc rejected the payload]"
        )
    if tool_errors:
        # Cap the surfaced errors so a chatty tool-result stream cannot
        # blow the rationale budget.
        rendered = []
        for entry in tool_errors[:3]:
            tool = str(entry.get("tool", "?"))
            err = str(entry.get("error", ""))[:200]
            rendered.append(f"{tool}: {err}")
        parts.append("[tool errors] " + " | ".join(rendered))
    if hallucinated_tools:
        names = ", ".join(hallucinated_tools[:6])
        parts.append(f"[hallucinated tools] {names}")
    if wallclock_capped:
        parts.append(
            "[wall-clock cap hit — Cortex stream closed before [DONE]]"
        )
    if not parts:
        return rationale
    sep = "\n\n— DIAGNOSTICS —\n"
    return (rationale or "").rstrip() + sep + "\n".join(parts)


def run_agent_turn(
    store: SocStore,
    session_id: str,
    player: str,
    runtime_override: Optional[str] = None,
) -> Dict[str, Any]:
    """Run one agent turn end-to-end.

    The active agent is normally chosen by ``SOC_AGENT_RUNTIME``:

    * ``heuristic`` (default) → :data:`HEURISTIC_AGENT_NAME` (``RED_HARVEST``).
    * ``cortex``              → one of the :data:`AI_AGENTS` entries
      (defaults to ``SOC_RED_REAPER``; override with
      ``SOC_CORTEX_AGENT``).
    * ``red_harvest_lite``    → :data:`HEURISTIC_LITE_AGENT_NAME`
      (``RED_HARVEST_LITE``) — same deterministic playbook with
      chaff/EMP disabled; the hackathon's easy first opponent.

    Callers can also pass an explicit ``runtime_override`` to pick the
    agent per call — used by the "agent vs RED_HARVEST" UI flow where
    one seat is forced to ``"heuristic"`` and the other to ``"cortex"``
    in the same night, regardless of what the env var says.

    Returns the envelope FastAPI surfaces to the front-end, including
    ``agent_id`` so the UI / audit log can render the actual name of
    whoever played this turn.
    """
    started = time.time()
    view = soc_engine.get_view(store, session_id, player)
    agent_view = view.get("agent_view") or {}
    # Snapshot day before the agent run so we can detect night-resolution
    # by Cortex's own `soc_submit_policy` call without re-submitting.
    day_before = int(view.get("day", 0))

    # RED_HARVEST_LITE (hackathon "no weapons" tutorial opponent) is
    # selected the same way "heuristic" is — via runtime_override — and
    # never builds/fires chaff or EMP, in orbit or at night.
    is_lite = (
        (runtime_override or "").strip().lower() == HEURISTIC_LITE_RUNTIME_KEY
    )
    weapons_enabled = not is_lite
    heuristic_agent_name = HEURISTIC_LITE_AGENT_NAME if is_lite else HEURISTIC_AGENT_NAME

    # v0.9.5 — Orbit phase is now driven by RED_HARVEST's deterministic
    # playbook (repair → 2 probes → harvester, gated on the 3-slot
    # action cap and the seat's credit balance). Cortex agents still
    # don't reason about the orbit submission directly, so we ALWAYS
    # use the heuristic here regardless of ``runtime_override`` /
    # ``SOC_AGENT_RUNTIME`` — the audit trail records this as
    # ``RED_HARVEST`` (or ``RED_HARVEST_LITE``) so the watcher can tell
    # a heuristic-driven orbit from a Cortex-driven night for the same
    # seat.
    if str(view.get("phase") or "") == "orbit":
        from sea_of_colours.agent.heuristic_agent import plan_orbit_actions

        orbit_actions, rationale = plan_orbit_actions(
            agent_view, weapons_enabled=weapons_enabled,
        )
        submit_result = soc_engine.submit_orbit_actions(
            store, session_id, player, orbit_actions,
        )
        orbit_resolved = bool(submit_result.get("orbit_resolved"))
        ms_elapsed = int((time.time() - started) * 1000)
        tool_calls_log = [
            {"name": "soc_get_view", "args": {"echo": "in-process"}},
            {
                "name": "soc_submit_orbit_actions",
                "args": {"action_count": len(orbit_actions)},
            },
        ]
        soc_engine.save_agent_rationale(
            store,
            session_id,
            view.get("day", agent_view.get("hud", {}).get("day", 0)),
            heuristic_agent_name,
            player,
            rationale,
            runtime="heuristic",
            prompt_excerpt=None,
            tool_calls=tool_calls_log,
            response_text=None,
            ms_elapsed=ms_elapsed,
        )
        return {
            "ok": True,
            "agent_id": heuristic_agent_name,
            "player": player,
            "runtime": "heuristic",
            "rationale": rationale,
            "moves": [],
            "orbit_actions": orbit_actions,
            "tool_calls": tool_calls_log,
            "submitted": True,
            "night_resolved": False,
            "orbit_resolved": orbit_resolved,
            "submit_result": submit_result,
            "ms_elapsed": ms_elapsed,
        }

    # Explicit per-call override wins; otherwise fall back to the env.
    if runtime_override:
        runtime = runtime_override.strip().lower()
    else:
        runtime = _runtime_mode()
    cortex_used = False
    cortex_response = ""
    tool_calls: list = []
    tool_errors: list = []
    hallucinated_tools: list = []
    cortex_submitted_policy = False
    cortex_wallclock_capped = False
    moves = []
    rationale = ""
    # Default identity is the heuristic — we flip this if Cortex
    # successfully takes the turn below.
    chosen_agent_name = heuristic_agent_name
    # We persist the full Cortex prompt to ``SOC_AGENT_INVOCATION``
    # so the eval command center (and any post-mortem tooling) can
    # see exactly what we sent to the model. Held at None when the
    # heuristic carries the turn — there's no LLM prompt for
    # deterministic Python. When Cortex is attempted but the
    # heuristic falls back, we still save the prompt because it's
    # part of the audit trail; ``agent_id`` will be RED_HARVEST,
    # which signals to readers that the Cortex attempt didn't
    # commit.
    cortex_prompt: Optional[str] = None

    if runtime == "cortex":
        cortex_name = _cortex_agent_name()
        invoker = CortexAgentInvoker(agent_name=cortex_name)
        if invoker.is_ready():
            cortex_used = True
            chosen_agent_name = cortex_name
            cortex_prompt = _build_cortex_prompt(
                session_id, view, agent_name=cortex_name,
            )
            cortex_result = invoker.invoke(cortex_prompt)
            if cortex_result.get("ok"):
                cortex_response = str(cortex_result.get("response") or "")
                tool_calls = list(cortex_result.get("tool_calls") or [])
                tool_errors = list(cortex_result.get("tool_errors") or [])
                hallucinated_tools = list(
                    cortex_result.get("hallucinated_tools") or []
                )
                cortex_submitted_policy = bool(
                    cortex_result.get("submitted_policy")
                )
                cortex_wallclock_capped = bool(
                    cortex_result.get("wallclock_capped")
                )
                # The Cortex agent submits its own policy via
                # soc_submit_policy → SOC_SUBMIT_POLICY proc, so we do
                # NOT double-submit here. The heuristic fallback below
                # ONLY fires when cortex_used is False.
                rationale = cortex_response
            else:
                rationale = (
                    f"{cortex_name} (cortex) invocation failed: "
                    f"{cortex_result.get('error', 'unknown error')}; "
                    f"falling back to {HEURISTIC_AGENT_NAME}."
                )
                cortex_used = False
                chosen_agent_name = HEURISTIC_AGENT_NAME

    if not cortex_used:
        agent = HeuristicAgent(
            name=heuristic_agent_name, weapons_enabled=weapons_enabled,
        )
        plan = agent.play(agent_view)
        moves = plan["moves"]
        rationale = rationale + (" | " if rationale else "") + plan["rationale"]
        tool_calls = list(plan["tool_calls"])

    night_resolved = False
    submit_result: Dict[str, Any] = {}
    if cortex_used:
        # Cortex submits its own policy via the `soc_submit_policy` tool
        # (declared in the agent spec). Re-submitting here would overwrite
        # that queue with our empty `moves` list and brick the seat.
        # Instead, ask the engine for current status so we still surface
        # `night_resolved` to the front-end consistently. `pending` is
        # `{p1: bool, p2: bool}` where True means "policy stashed".
        status = soc_engine.get_session_status(store, session_id)
        pending = status.get("pending") or {}
        seat_ready = bool(pending.get(player))

        # Race-tolerant re-poll: if Cortex attempted a submission but the
        # status check still shows the seat empty, give the proc commit
        # a beat to land before we conclude it failed. Real failures
        # remain unaffected (the seat stays empty), but warehouse
        # commit-visibility hiccups stop misattributing turns to the
        # heuristic.
        #
        # Two trigger conditions, with different patience budgets:
        #
        # 1. ``submitted_policy=True`` from the SSE stream — we saw the
        #    `executing_tool: soc_submit_policy` event, so the proc is
        #    definitely running. 200ms is enough for a healthy commit.
        # 2. ``wallclock_capped=True`` — the SSE stream was cut off
        #    before we could see whether soc_submit_policy fired, but
        #    the proc may still be executing in the warehouse. Give it
        #    a longer leash (3s) before falling back, because in the
        #    Vetus_Beacon demo the in-flight proc landed 1-2 seconds
        #    after the cap fired and the heuristic overwrote it.
        #
        # In both cases we only retry once; the goal is to absorb the
        # warehouse-commit-visibility race, not to wait indefinitely
        # on a genuinely failed call.
        if not seat_ready and not tool_errors:
            if cortex_submitted_policy:
                time.sleep(0.2)
            elif cortex_wallclock_capped:
                time.sleep(3.0)
            else:
                # Neither signal — no point waiting.
                pass
            if cortex_submitted_policy or cortex_wallclock_capped:
                status = soc_engine.get_session_status(store, session_id)
                pending = status.get("pending") or {}
                seat_ready = bool(pending.get(player))
                # If the wall-clock cap fired AND a delayed commit
                # arrived, treat this as a successful Cortex turn
                # (mark the submission flag so the elif branch below
                # cannot misroute us into proc-rejection territory).
                if seat_ready and cortex_wallclock_capped:
                    cortex_submitted_policy = True

        if seat_ready:
            # Cortex landed a submission. Trust it. The night ticks
            # forward via `maybe_resolve_if_ready` whenever it was the
            # second seat in.
            night_resolved = int(status.get("day", day_before)) > day_before
            submit_result = {"ok": True, "via": "cortex"}
            if tool_errors or hallucinated_tools or cortex_wallclock_capped:
                rationale = _annotate_cortex_diagnostics(
                    rationale,
                    tool_errors=tool_errors,
                    hallucinated_tools=hallucinated_tools,
                    wallclock_capped=cortex_wallclock_capped,
                )
        elif cortex_submitted_policy:
            # Cortex called `soc_submit_policy` but the seat is still
            # empty after the re-poll. That means the proc rejected the
            # payload (most likely a malformed `p_policy`, but errors
            # from the warehouse should appear in ``tool_errors``).
            #
            # We deliberately do NOT silently overwrite with a heuristic
            # plan here — Cortex's failure is the policy's failure, and
            # masking it under the RED_HARVEST label is exactly the bug
            # that hid the Lux_Hollow regression. Instead we lock the
            # seat with an EMPTY queue (keeping the night flowing) and
            # leave the rationale tagged as Cortex with the proc error
            # surfaced so the season replay shows what really happened.
            moves = []
            submit_result = soc_engine.submit_policy(
                store, session_id, player, moves,
            )
            night_resolved = bool(submit_result.get("night_resolved"))
            rationale = _annotate_cortex_diagnostics(
                rationale,
                tool_errors=tool_errors,
                hallucinated_tools=hallucinated_tools,
                wallclock_capped=cortex_wallclock_capped,
                proc_rejection=True,
            )
            # Keep `chosen_agent_name = cortex_name` so the audit row
            # correctly blames the AI. `cortex_used` stays True — the
            # envelope reports ``runtime="cortex"`` because Cortex
            # *was* the policy author for this seat.
        else:
            # Cortex never even called soc_submit_policy. This is the
            # one case where falling back to the heuristic is the right
            # call: the model produced no policy, so something has to
            # lock the seat or the season deadlocks. We label the
            # invocation as the heuristic because that's what carried
            # the turn.
            agent = HeuristicAgent()
            plan = agent.play(agent_view)
            moves = plan["moves"]
            tool_calls = list(plan["tool_calls"]) + tool_calls
            rationale = (
                rationale
                + f" | [fallback] {chosen_agent_name} did not call "
                + f"soc_submit_policy; {HEURISTIC_AGENT_NAME} took over: "
                + plan["rationale"]
            )
            if tool_errors or hallucinated_tools or cortex_wallclock_capped:
                rationale = _annotate_cortex_diagnostics(
                    rationale,
                    tool_errors=tool_errors,
                    hallucinated_tools=hallucinated_tools,
                    wallclock_capped=cortex_wallclock_capped,
                )
            submit_result = soc_engine.submit_policy(
                store, session_id, player, moves,
            )
            night_resolved = bool(submit_result.get("night_resolved"))
            chosen_agent_name = HEURISTIC_AGENT_NAME
            cortex_used = False
    else:
        # Heuristic always submits — an empty queue is the agent's way of
        # saying "I have nothing to do this night, lock my seat". The night
        # can't resolve until both seats submit, so skipping this would
        # deadlock a 2-AI / 1-AI+1-human game whenever the heuristic comes
        # back blank.
        submit_result = soc_engine.submit_policy(
            store, session_id, player, moves,
        )
        night_resolved = bool(submit_result.get("night_resolved"))

    ms_elapsed = int((time.time() - started) * 1000)

    # "Cap rather than kill" — the audit row and the on-screen log both
    # take the truncated form so a 60KB chain-of-thought can't drown the
    # UI. The full untruncated Cortex output still lands in
    # ``response_text`` for forensic replay (it's column-bounded inside
    # Snowflake but not surfaced to the log/UI by default).
    capped_rationale = _smart_truncate_rationale(rationale)

    soc_engine.save_agent_rationale(
        store,
        session_id,
        view.get("day", agent_view.get("hud", {}).get("day", 0)),
        chosen_agent_name,
        player,
        capped_rationale,
        runtime="cortex" if cortex_used else "heuristic",
        prompt_excerpt=cortex_prompt,
        tool_calls=tool_calls,
        response_text=cortex_response or None,
        ms_elapsed=ms_elapsed,
    )

    submitted = bool(submit_result.get("ok") or submit_result.get("via") == "cortex")
    envelope = {
        "ok": True,
        "agent_id": chosen_agent_name,
        "player": player,
        "runtime": "cortex" if cortex_used else "heuristic",
        "rationale": capped_rationale,
        "moves": moves,
        "tool_calls": tool_calls,
        "submitted": submitted,
        "night_resolved": night_resolved,
        "submit_result": submit_result,
        "ms_elapsed": ms_elapsed,
    }
    # Diagnostic surfacing for the watcher/CLI. These keys are only
    # populated when Cortex was the chosen runtime AND something the
    # operator cares about happened (proc rejection, hallucinated tool,
    # wall-clock cap). They are absent on a clean heuristic-only turn,
    # so existing callers don't need to handle them.
    if tool_errors:
        envelope["tool_errors"] = tool_errors
    if hallucinated_tools:
        envelope["hallucinated_tools"] = hallucinated_tools
    if cortex_wallclock_capped:
        envelope["wallclock_capped"] = True
    return envelope
