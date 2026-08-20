"""Tabula grounding + probe-decision audit.

Two independent regression harnesses in one script:

1. **Coordinate/tier grounding audit** — for each move & every coord
   reference in plan/rationale text, cross-check against the actual
   ``agent_view``. Flags any coord that does not match a real RED cell
   (or a legal drop-adjacent LOS cell). This is the audit that proved
   Tabula v1 wasn't hallucinating.

2. **Probe decision audit** — for each ``probe(at=...)`` action, verify
   the placement actually reveals fog cells and doesn't just re-cover
   existing LOS. Reports the ratio of ``area_gain(chosen)`` to
   ``area_gain(best_candidate)`` — a good agent should be >= 0.6.

Runs against either Tabula v1 (``SOC_RED_REAPER_TABULA``) or v2
(``SOC_RED_REAPER_TABULA_V2``) — pass the agent name as ``--agent`` on
the CLI, or set ``TABULA_AUDIT_AGENT`` in the environment.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from typing import Any, Dict, List, Mapping, Sequence, Set, Tuple

os.environ.setdefault("SOC_BACKEND", "memory")

# Repo-root import: allow running this script directly from ``scripts/``.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sea_of_colours.evals import get_scenario  # noqa: E402
from sea_of_colours.snowpark import engine as engine_mod  # noqa: E402
from sea_of_colours.orchestrator_2.cortex_invoker import CortexAgentInvoker  # noqa: E402


# ─── helpers: ground-truth extraction ──────────────────────────────────


def _red_cells(agent_view: Mapping[str, Any]) -> Dict[Tuple[int, int], Dict[str, Any]]:
    out: Dict[Tuple[int, int], Dict[str, Any]] = {}
    for row in (agent_view.get("red_tiles") or []):
        if not isinstance(row, Mapping):
            continue
        try:
            x, y = int(row["x"]), int(row["y"])
        except (TypeError, KeyError, ValueError):
            continue
        out[(x, y)] = {"tier": row.get("tier"), "purity": row.get("purity")}
    return out


def _friendly_probes(agent_view: Mapping[str, Any]) -> Dict[Tuple[int, int], str]:
    out: Dict[Tuple[int, int], str] = {}
    for uid, e in (agent_view.get("entity_detail") or {}).items():
        if not isinstance(e, Mapping) or not uid.startswith("probe_"):
            continue
        at = e.get("at") or e.get("pos")
        if isinstance(at, (list, tuple)) and len(at) == 2:
            out[tuple(at)] = uid
    return out


def _live_cells(agent_view: Mapping[str, Any]) -> Set[Tuple[int, int]]:
    out: Set[Tuple[int, int]] = set()
    for row in ((agent_view.get("world") or {}).get("live") or []):
        if isinstance(row, Mapping):
            try:
                out.add((int(row["x"]), int(row["y"])))
            except (TypeError, KeyError, ValueError):
                continue
    return out


def _disk_cells(cx: int, cy: int, width: int, height: int, r: int = 4) -> List[Tuple[int, int]]:
    return [
        (x, y)
        for x in range(max(0, cx - r), min(width, cx + r + 1))
        for y in range(max(0, cy - r), min(height, cy + r + 1))
    ]


# ─── audit 1: coordinate grounding ─────────────────────────────────────


def audit_moves(decision: Mapping[str, Any], red: Mapping, probes: Mapping, los: Set) -> List[Tuple[str, str]]:
    findings: List[Tuple[str, str]] = []
    for i, m in enumerate(decision.get("moves") or []):
        if not isinstance(m, Mapping):
            continue
        act = m.get("a")
        if act == "drop":
            xy = tuple(m.get("at") or [])
            if xy in red:
                info = red[xy]
                findings.append(("GROUNDED", f"move[{i}] drop {xy} — REAL RED tier={info['tier']} p={info['purity']}"))
            elif xy in probes:
                findings.append(("GROUNDED", f"move[{i}] drop {xy} — crushes {probes[xy]}"))
            elif xy in los:
                findings.append(("OK-EMPTY", f"move[{i}] drop {xy} — LOS cell (legal, non-red)"))
            else:
                findings.append(("HALLUCINATION", f"move[{i}] drop {xy} — NOT RED, NOT probe, NOT in LOS"))
        elif act == "step":
            xy = tuple(m.get("to") or [])
            if xy in red:
                findings.append(("GROUNDED", f"move[{i}] step {xy} — REAL RED tier={red[xy]['tier']}"))
            else:
                findings.append(("OK-EMPTY", f"move[{i}] step {xy} — empty cell"))
        elif act == "pickup":
            findings.append(("GROUNDED", f"move[{i}] pickup {m.get('unit')}"))
        elif act == "probe":
            xy = tuple(m.get("at") or [])
            findings.append(("GROUNDED", f"move[{i}] probe {xy}"))
    return findings


def audit_text(text: str, red: Mapping) -> List[Tuple[str, str]]:
    findings: List[Tuple[str, str]] = []
    for m in re.finditer(r"\((\d{1,2})\s*,\s*(\d{1,2})\)", text or ""):
        xy = (int(m.group(1)), int(m.group(2)))
        if xy in red:
            info = red[xy]
            findings.append(("GROUNDED", f"text {xy} -> real RED tier={info['tier']} p={info['purity']}"))
        else:
            findings.append(("HALLUCINATION", f"text {xy} -> NOT a visible RED cell"))
    actual = {v["tier"] for v in red.values()}
    for name in ("pure", "mass", "vein", "trace"):
        if name in (text or "").lower() and name not in actual:
            findings.append(("TIER-MISMATCH", f"text mentions '{name}' but visible tiers are {actual}"))
    return findings


# ─── audit 2: probe decision quality ───────────────────────────────────


def _best_probe_candidate(agent_view: Mapping[str, Any]) -> Tuple[Tuple[int, int], int]:
    """Sweep a coarse grid to find the placement with the max area_gain.
    Returns (best_at, best_area_gain).
    """
    world = agent_view.get("world") or {}
    W, H = int(world.get("width") or 40), int(world.get("height") or 28)
    los = _live_cells(agent_view)
    best_at, best_gain = (0, 0), 0
    # Every 2nd cell — sufficient resolution for a 4-radius disk.
    for cx in range(0, W, 2):
        for cy in range(0, H, 2):
            disk = _disk_cells(cx, cy, W, H)
            gain = sum(1 for c in disk if c not in los)
            if gain > best_gain:
                best_gain = gain
                best_at = (cx, cy)
    return best_at, best_gain


def audit_probes(decision: Mapping[str, Any], agent_view: Mapping[str, Any]) -> List[Tuple[str, str]]:
    findings: List[Tuple[str, str]] = []
    world = agent_view.get("world") or {}
    W, H = int(world.get("width") or 40), int(world.get("height") or 28)
    los = _live_cells(agent_view)
    fog_count = int(world.get("fog_count") or 0)
    probes_planned = [m for m in (decision.get("moves") or []) if isinstance(m, Mapping) and m.get("a") == "probe"]

    if fog_count == 0 and probes_planned:
        for i, m in enumerate(probes_planned):
            findings.append(("WASTEFUL", f"probe[{i}] {tuple(m.get('at') or [])} launched but fog_count=0"))
        return findings
    if not probes_planned:
        return findings

    best_at, best_gain = _best_probe_candidate(agent_view)

    for i, m in enumerate(probes_planned):
        at = tuple(m.get("at") or [])
        if len(at) != 2:
            findings.append(("MALFORMED", f"probe[{i}] at={at!r}"))
            continue
        cx, cy = at
        if not (0 <= cx < W and 0 <= cy < H):
            findings.append(("OUT-OF-BOUNDS", f"probe[{i}] {at}"))
            continue
        disk = _disk_cells(cx, cy, W, H)
        gain = sum(1 for c in disk if c not in los)
        if gain == 0:
            findings.append(("USELESS", f"probe[{i}] {at} — disk fully inside LOS (area_gain=0)"))
        else:
            ratio = gain / max(1, best_gain)
            tag = "GOOD" if ratio >= 0.6 else ("MEDIOCRE" if ratio >= 0.3 else "POOR")
            findings.append((tag, f"probe[{i}] {at} area_gain={gain} vs best={best_gain} (@{best_at}) ratio={ratio:.2f}"))
    return findings


# ─── runner ─────────────────────────────────────────────────────────────


def _extract_json(raw: str) -> Dict[str, Any]:
    if "```" in raw:
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                pass
    dec = json.JSONDecoder()
    for m in re.finditer(r"\{", raw):
        try:
            obj, _ = dec.raw_decode(raw[m.start():])
        except Exception:
            continue
        if isinstance(obj, dict) and "moves" in obj:
            return obj
    return {}


def _completion_predicate(accum: str) -> bool:
    if '"moves"' not in accum:
        return False
    if accum.count("{") < 1 or accum.count("}") < accum.count("{"):
        return False
    dec = json.JSONDecoder()
    for m in re.finditer(r"\{", accum):
        try:
            obj, _ = dec.raw_decode(accum[m.start():])
        except Exception:
            continue
        if isinstance(obj, dict) and "moves" in obj:
            return True
    return False


def _import_harness(agent_name: str):
    """Return the (prompt, memory, chain_hints, [probe_hints]) modules for
    the given agent name. Picks the right harness so v1 and v2 can be
    audited with the same script."""
    if agent_name.endswith("_V2"):
        from sea_of_colours.orchestrator_2.harnesses.tabula_v2 import (
            heuristic_chains, memory as memory_mod, probe_hints, prompt as prompt_mod,
        )
        return prompt_mod, memory_mod, heuristic_chains, probe_hints
    else:
        from sea_of_colours.orchestrator_2.harnesses.tabula import (
            heuristic_chains, memory as memory_mod, prompt as prompt_mod,
        )
        return prompt_mod, memory_mod, heuristic_chains, None


def run_scenario(agent_name: str, scenario_name: str, day: int, trial: int) -> Dict[str, Any]:
    scenario = get_scenario(scenario_name)
    store, sid = scenario.build()
    av = engine_mod.get_view(store, sid, "p1").get("agent_view")

    prompt_mod, memory_mod, chain_mod, probe_mod = _import_harness(agent_name)

    kwargs = dict(
        agent_view=av, day=day, day_cap=3, vault_score=0,
        memory_replay=memory_mod.format_replay([]),
        chain_hints=chain_mod.top_chain_hints(av, max_chains=3),
    )
    if probe_mod is not None:
        kwargs["probe_hints"] = probe_mod.top_probe_hints(av, max_hints=3)
    prompt_text = prompt_mod.build_prompt(**kwargs)

    invoker = CortexAgentInvoker(agent_name=agent_name, text_completion_predicate=_completion_predicate)
    t0 = time.time()
    result = invoker.invoke(prompt_text, wallclock_cap_s=30, response_cap_bytes=3000)
    wall = time.time() - t0
    raw = str(result.get("response") or "")
    decision = _extract_json(raw)

    red = _red_cells(av)
    probes = _friendly_probes(av)
    los = _live_cells(av)

    move_findings = audit_moves(decision, red, probes, los)
    plan_findings = audit_text(decision.get("plan_this_turn") or "", red)
    rat_findings = audit_text(decision.get("rationale") or "", red)
    probe_findings = audit_probes(decision, av)

    return {
        "scenario": scenario_name, "trial": trial, "day": day,
        "wallclock_s": round(wall, 1),
        "response_chars": len(raw),
        "err": result.get("error"),
        "decision": decision,
        "move_findings": move_findings,
        "plan_findings": plan_findings,
        "rat_findings": rat_findings,
        "probe_findings": probe_findings,
    }


def _print_report(res: Dict[str, Any]) -> None:
    def tag(v: str) -> str:
        return {
            "GROUNDED": "OK", "OK-EMPTY": "..", "HALLUCINATION": "!!",
            "TIER-MISMATCH": "~~", "GOOD": "OK", "MEDIOCRE": "~~",
            "POOR": "!!", "USELESS": "!!", "WASTEFUL": "!!",
            "OUT-OF-BOUNDS": "!!", "MALFORMED": "!!",
        }.get(v, "??")

    print(f"\n=== {res['scenario']} trial {res['trial']}  wall={res['wallclock_s']}s  bytes={res['response_chars']} ===")
    if res.get("err"):
        print(f"  ERROR: {res['err'][:120]}")
        return
    d = res["decision"]
    print(f"  plan     : {(d.get('plan_this_turn') or '')[:160]}")
    print(f"  predicted: {(d.get('predicted_outcome') or {}).get('banked_pts_estimate')}")
    print(f"  --- moves ({len(res['move_findings'])}) ---")
    for v, m in res["move_findings"]:
        print(f"    [{tag(v)}] {m}")
    if res["plan_findings"]:
        print(f"  --- plan text ({len(res['plan_findings'])}) ---")
        for v, m in res["plan_findings"]:
            print(f"    [{tag(v)}] {m}")
    if res["rat_findings"]:
        print(f"  --- rationale text ({len(res['rat_findings'])}) ---")
        for v, m in res["rat_findings"]:
            print(f"    [{tag(v)}] {m}")
    if res["probe_findings"]:
        print(f"  --- probe decision ({len(res['probe_findings'])}) ---")
        for v, m in res["probe_findings"]:
            print(f"    [{tag(v)}] {m}")


def _summarize(all_res: Sequence[Dict[str, Any]]) -> None:
    totals: Dict[str, int] = {}
    for r in all_res:
        for section in ("move_findings", "plan_findings", "rat_findings", "probe_findings"):
            for v, _ in r.get(section) or []:
                totals[v] = totals.get(v, 0) + 1
    print("\n" + "=" * 60)
    print("GRAND TOTALS")
    print("=" * 60)
    print(f"  GROUNDED               : {totals.get('GROUNDED', 0)}")
    print(f"  OK-EMPTY moves         : {totals.get('OK-EMPTY', 0)}")
    print(f"  TIER-MISMATCH          : {totals.get('TIER-MISMATCH', 0)}")
    print(f"  HALLUCINATION          : {totals.get('HALLUCINATION', 0)}  <-- must be 0")
    print(f"  probe GOOD             : {totals.get('GOOD', 0)}")
    print(f"  probe MEDIOCRE         : {totals.get('MEDIOCRE', 0)}")
    print(f"  probe POOR             : {totals.get('POOR', 0)}  <-- ideally 0")
    print(f"  probe USELESS/WASTEFUL : {totals.get('USELESS', 0) + totals.get('WASTEFUL', 0)}  <-- must be 0")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", default=os.environ.get("TABULA_AUDIT_AGENT", "SOC_RED_REAPER_TABULA_V2"))
    parser.add_argument("--trials", type=int, default=1, help="trials per scenario")
    parser.add_argument("--scenarios", nargs="+", default=["arena_day1", "arena_day2", "arena_day3", "arena_day1_fog"])
    args = parser.parse_args()

    day_map = {"arena_day1": 1, "arena_day2": 2, "arena_day3": 3, "arena_day1_fog": 1}
    all_res: List[Dict[str, Any]] = []
    print(f"Auditing agent: {args.agent}  scenarios: {args.scenarios}  trials: {args.trials}")
    for name in args.scenarios:
        for t in range(1, args.trials + 1):
            res = run_scenario(args.agent, name, day_map.get(name, 1), t)
            _print_report(res)
            all_res.append(res)
    _summarize(all_res)


if __name__ == "__main__":
    main()
