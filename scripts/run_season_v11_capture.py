"""Headless v11-vs-heuristic season runner WITH full per-turn capture.

Reuses the proven ``scripts.run_season`` loop (game creation, phase
advancement, night/orbit resolution, scoring) but taps every agent turn's
``extras`` so we can review the FULL text the model saw and produced —
verbatim THINK prompt (worldview + LAST NIGHT + STRATEGY JOURNAL + option
menu), PLAN prompt, THINK reasoning, PLAN JSON, agent-authored intent /
reflection, the compiled moves, and the whole raw ``extras`` blob.

It works exactly like ``run_season_v2.py``: it monkeypatches the symbol
``sea_of_colours.agent.runtime.run_agent_turn`` (which ``run_season.main``
imports lazily) with a wrapper that (1) routes the turn through the
orchestrator_2 runtime, (2) adapts the response to the legacy shape the
season loop expects, and (3) writes a readable per-turn card + a raw JSON
dump to the capture directory.

Usage::

    SOC_BACKEND=snowflake python scripts/run_season_v11_capture.py \\
        --p1 cortex --p2 heuristic \\
        --cortex-agent SOC_RED_REAPER_TABULA_V11 \\
        --seed 7 --days 7 --season-name V11_CAPTURE_s7

Capture lands in ``reports/v11_capture/<season>/`` (override with
``SOC_CAPTURE_DIR``): one ``turn_NN_dayD_seat_phase.md`` per cortex/harness
turn plus a matching ``.json`` and a rolling ``_manifest.md`` index.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Patch the runtime import BEFORE run_season is imported (same trick as
# run_season_v2) so the lazy ``from sea_of_colours.agent.runtime import
# run_agent_turn`` inside run_season.main resolves to our capturing wrapper.
import sea_of_colours.agent.runtime as _legacy_runtime  # noqa: E402
from sea_of_colours.orchestrator_2.runtime import (  # noqa: E402
    run_agent_turn as _v2_run_agent_turn,
)
from sea_of_colours.snowpark import engine as _soc_engine  # noqa: E402


def _capture_dir(session_id: str, season_name: str) -> Path:
    base = os.environ.get("SOC_CAPTURE_DIR")
    root = Path(base) if base else (_REPO_ROOT / "reports" / "v11_capture")
    slug = (season_name or session_id or "season").replace("/", "_")
    d = root / slug
    d.mkdir(parents=True, exist_ok=True)
    return d


_STATE: Dict[str, Any] = {"turn": 0, "dir": None, "session_id": None}


def _board_summary(agent_view: Dict[str, Any]) -> str:
    red = agent_view.get("red_tiles") or []
    live = sum(1 for t in red if str(t.get("freshness") or "") == "fresh")
    echo = len(red) - live
    # Live redsigns live under the singular ``redsign`` key; enemy probes are
    # surfaced via competitor_intel (public launches + persistent echoes), not a
    # top-level key. Count them the same way the prompt blocks do so the captured
    # board line matches what the model actually saw (was always 0/0 before).
    signs = (
        agent_view.get("redsign")
        or agent_view.get("redsigns")
        or agent_view.get("red_signs")
        or []
    )
    _ci = agent_view.get("competitor_intel") or {}
    _probe_cells = {
        (int(r["at"][0]), int(r["at"][1]))
        for src in ("new_this_day", "persistent_echoes")
        for r in (_ci.get(src) or [])
        if isinstance(r, dict)
        and str(r.get("kind") or "").startswith("enemy_probe")
        and isinstance(r.get("at"), (list, tuple))
        and len(r["at"]) >= 2
    }
    enemy_probes = list(_probe_cells)
    probe_stock = (
        agent_view.get("probe_stock")
        or (agent_view.get("orbit") or {}).get("probe_stock")
        or 0
    )
    return (
        f"red_tiles={len(red)} (live={live} echo={echo})  "
        f"redsigns={len(signs)}  enemy_probes={len(enemy_probes)}  "
        f"probe_stock={probe_stock}"
    )


def _sub(extras: Dict[str, Any], kind: str) -> Dict[str, Any]:
    for s in extras.get("sub_invocations") or []:
        if str(s.get("kind") or "") == kind:
            return s
    return {}


def _write_turn(
    *,
    session_id: str,
    season_name: str,
    seat: str,
    day: int,
    phase: str,
    result: Dict[str, Any],
    agent_view: Dict[str, Any],
) -> None:
    extras = result.get("extras") or {}
    # Heuristic turns carry no extras/prompt — skip the detailed card but
    # still note them in the manifest so the timeline is complete.
    has_detail = bool(extras.get("thinker_prompt") or extras.get("plan_prompt"))

    d = _STATE["dir"]
    n = _STATE["turn"]
    _STATE["turn"] += 1

    agent_id = result.get("agent_id", "?")
    runtime = result.get("runtime", "?")
    submitted = bool(result.get("submitted"))
    nr = bool(result.get("night_resolved"))
    ms = int(result.get("ms_elapsed", 0))
    # Prefer the real compiled queue from extras; fall back to the stub list.
    moves = extras.get("final_moves")
    if not isinstance(moves, list):
        moves = result.get("moves") or []
    stem = f"turn_{n:02d}_day{day}_{seat}_{phase}"

    # Manifest line (always).
    manifest = d / "_manifest.md"
    with manifest.open("a", encoding="utf-8") as mf:
        mf.write(
            f"- turn {n:02d} | day {day} | {seat} | {phase} | {agent_id} "
            f"({runtime}) | moves={len(moves)} submit={'Y' if submitted else 'N'} "
            f"night_resolved={'Y' if nr else 'N'} | {ms}ms"
            f"{'' if has_detail else '  (heuristic — no prompt)'}\n"
        )

    if not has_detail:
        return

    directive = extras.get("thinker_directive") or {}
    intent = extras.get("agent_intent") or ""
    reflection = extras.get("agent_reflection") or ""
    think = extras.get("thinker_reasoning") or ""
    plan_raw = _sub(extras, "plan").get("response_text") or ""
    think_prompt = extras.get("thinker_prompt") or ""
    plan_prompt = extras.get("plan_prompt") or ""
    menu_block = extras.get("option_menu_block") or ""
    selected = extras.get("selected_option_ids") or []
    sanitizer = extras.get("sanitizer_changes") or []

    md: list[str] = []
    md.append(f"# Turn {n:02d} — day {day} · {seat} · {phase}")
    md.append("")
    md.append(f"- agent: **{agent_id}** (runtime={runtime})")
    md.append(
        f"- submitted={submitted}  night_resolved={nr}  ms={ms}  "
        f"exec={'packager' if extras.get('packager_used') else 'mover'}"
        f"{'; FALLBACK' if extras.get('fallback_used') else ''}"
    )
    md.append(f"- board v11 saw: {_board_summary(agent_view)}")
    md.append(
        f"- thinker: api={extras.get('thinker_api') or '-'} "
        f"ms={extras.get('thinker_ms') or 0} retried={extras.get('thinker_retried')}"
    )
    if selected:
        md.append(f"- selected options: {', '.join(str(o) for o in selected)}")
    md.append(f"- compiled moves: {len(moves)}")
    md.append("")
    if intent:
        md.append(f"**INTENT (this turn):** {intent}")
        md.append("")
    if reflection:
        md.append(f"**REFLECTION (on last night):** {reflection}")
        md.append("")

    md.append("## THINK reasoning")
    md.append("")
    md.append(think or "(none)")
    md.append("")

    md.append("## PLAN — raw JSON")
    md.append("")
    md.append("```json")
    md.append(plan_raw or "(none)")
    md.append("```")
    md.append("")
    if directive:
        md.append("### resolved directive")
        md.append("```json")
        md.append(json.dumps(directive, indent=2, default=str))
        md.append("```")
        md.append("")

    md.append("## COMPILED MOVES")
    md.append("```json")
    md.append(json.dumps(moves, indent=2, default=str))
    md.append("```")
    if sanitizer:
        md.append("")
        md.append("### sanitizer changes")
        for s in sanitizer[:20]:
            md.append(f"- {s}")
    md.append("")

    if menu_block:
        md.append("## OPTION MENU (surfaced to the thinker)")
        md.append("```")
        md.append(str(menu_block))
        md.append("```")
        md.append("")

    md.append("## THINK PROMPT (verbatim — the full model input)")
    md.append("```")
    md.append(str(think_prompt))
    md.append("```")
    md.append("")
    if plan_prompt:
        md.append("## PLAN PROMPT (verbatim)")
        md.append("```")
        md.append(str(plan_prompt))
        md.append("```")
        md.append("")

    (d / f"{stem}.md").write_text("\n".join(md), encoding="utf-8")

    # Raw everything for completeness.
    blob = {
        "turn": n, "day": day, "seat": seat, "phase": phase,
        "agent_id": agent_id, "runtime": runtime, "submitted": submitted,
        "night_resolved": nr, "ms_elapsed": ms,
        "moves": moves, "extras": extras,
    }
    (d / f"{stem}.json").write_text(
        json.dumps(blob, indent=2, default=str), encoding="utf-8"
    )


def _capturing_run_agent_turn(
    store, session_id, player, runtime_override=None,
):
    """Legacy-shape wrapper around orchestrator_2's runtime + per-turn capture."""
    if _STATE["dir"] is None:
        status0 = _soc_engine.get_session_status(store, session_id) or {}
        season = str(status0.get("season_name") or "")
        _STATE["dir"] = _capture_dir(session_id, season)
        _STATE["session_id"] = session_id
        print(f"[capture] writing per-turn cards to {_STATE['dir']}", flush=True)

    pre = _soc_engine.get_session_status(store, session_id) or {}
    pre_day = int(pre.get("day", 0))
    pre_phase = str(pre.get("phase") or "")

    # Grab the view the harness will see (for the board summary) — cheap and
    # matches what the harness reads internally.
    try:
        view = _soc_engine.get_view(store, session_id, player)
        agent_view = view.get("agent_view") or {}
    except Exception:
        agent_view = {}

    result = _v2_run_agent_turn(store, session_id, player,
                                runtime_override=runtime_override)

    post = _soc_engine.get_session_status(store, session_id) or {}
    post_day = int(post.get("day", pre_day))
    night_resolved = post_day > pre_day

    submitted = bool(result.get("submitted_policy")) or bool(result.get("ok"))
    moves_count = 0
    extras = result.get("extras") or {}
    if isinstance(extras, dict):
        moves_count = int(
            extras.get("materialized_count")
            or extras.get("moves_count")
            or len(extras.get("final_moves") or [])
            or 0
        )
    result["moves"] = [None] * moves_count
    result["submitted"] = submitted
    result["night_resolved"] = night_resolved

    try:
        _write_turn(
            session_id=session_id,
            season_name=str(pre.get("season_name") or ""),
            seat=player,
            day=pre_day,
            phase=pre_phase,
            result=result,
            agent_view=agent_view,
        )
    except Exception as ex:  # never crash the season on a capture bug
        print(f"[capture] WARN failed to write turn: {ex}", flush=True)

    return result


_legacy_runtime.run_agent_turn = _capturing_run_agent_turn


def main() -> int:
    from scripts.run_season import main as _legacy_main
    return _legacy_main()


if __name__ == "__main__":
    sys.exit(main())
