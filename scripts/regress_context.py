#!/usr/bin/env python3
"""Repeatable per-turn regression harness for the v9 thinker context.

Fires the PRODUCTION two-stage THINK->PLAN design at a set of byte-exact
captured board contexts (opener / redsign / vanilla / full-fleet), N times each,
and scores each run against explicit per-turn PASS/FAIL criteria. Emits a
scorecard (check -> hits/N per turn) so we can:

  1. establish a BASELINE on the current (pre-fix) prompt, then
  2. re-run after each plan change and watch the aspirational checks go green.

Prompts are produced by ``reconstruct_prompt.py``; after any change that alters
prompt-building, RE-CAPTURE (re-run reconstruct) before scoring so the context
reflects the new code.

Usage::

    PYTHONPATH=. SOC_BACKEND=snowflake python scripts/regress_context.py \\
        --repeat 5 --out reports/regress_context_baseline.md
    # subset + quick:
    ... --turns redsign,vanilla --repeat 3
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_TASK_MARKER = "=== YOUR TASK"


# ── two-stage instruction blocks (mirror the shipped v9 harness) ────────
def _instr_blocks():
    from sea_of_colours.orchestrator_2.harnesses.tabula_v9 import prompt as _v9p
    think = _v9p._V9_THINK_TASK
    plan = (
        "=== YOUR ANALYSIS (from your think pass — commit it now) ===\n"
        "<<<\n__ANALYSIS__\n>>>\n"
        + _v9p._V9_PLAN_TASK
        + "\n" + _v9p._V9_THINKER_ADDENDUM
        + "\nOUTPUT ONE JSON OBJECT NOW — DECISION FIRST: \"posture\", then "
        "\"plan\" (the OPTION MENU IDs from your analysis, in execution order), "
        "then \"situational\" when a REDSIGN is live; a SHORT \"reasoning\" LAST. "
        "Start with the open-brace character. GO:\n"
    )
    return think, plan


def _fire(model: str, prompt: str, *, response_format, max_tokens: int,
          wall: float) -> Dict[str, Any]:
    from sea_of_colours.orchestrator_2.cortex_chat import CortexChatInvoker
    inv = CortexChatInvoker(model=model, response_format=response_format,
                            max_completion_tokens=max_tokens)
    t0 = time.time()
    res = inv.invoke(prompt, wallclock_cap_s=wall)
    res["_elapsed_ms"] = int((time.time() - t0) * 1000)
    return res


# ── check helpers (operate on a per-run ctx dict) ───────────────────────
def _has(plan: List[str], *prefixes: str) -> bool:
    up = [str(p).upper() for p in plan]
    return any(p.startswith(pre) for p in up for pre in prefixes)


def _smash(plan: List[str]) -> bool:
    return any("SMASH" in str(p).upper() for p in plan)


def _mentions(a: str, *needles: str) -> bool:
    return any(n in a for n in needles)


_COORD_RE = __import__("re").compile(r"\(?\b(\d{1,2})\s*,\s*(\d{1,2})\)?")


def _coords_in(text: str) -> List[tuple]:
    return [(int(m.group(1)), int(m.group(2))) for m in _COORD_RE.finditer(text)]


def _cheb(a, b) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


# Each check: name -> predicate(ctx) -> bool. ctx keys:
#   a (analysis lower), plan (list), targets (list of [x,y]), posture,
#   landed (bool), think_capped (bool), plan_capped (bool)
Check = Callable[[Dict[str, Any]], bool]


def _common() -> List[tuple]:
    return [
        ("contain_think", lambda c: not c["think_capped"]),
        ("plan_lands", lambda c: c["landed"]),
    ]


def _names_pure_near_beacon(c) -> bool:
    """Agent reasons about a cell near the (drift-safe) beacon center parsed
    from the capture. Robust to the nondeterministic replay moving the pure."""
    beacon = c.get("beacon")
    if not beacon:
        return False
    cells = _coords_in(c["a"]) + [tuple(t) for t in c["targets"]
                                  if isinstance(t, (list, tuple)) and len(t) == 2]
    return any(_cheb(cell, beacon) <= 4 for cell in cells)


def _secures_pure_not_offset(c) -> bool:
    """Picks the pure-grab pattern AND does not talk itself into the OFFSET
    reversion (the hyg-contradictions conflict: 'drop ON the pure' vs the
    last-night 'drop offset' lesson)."""
    reverts = _mentions(
        c["a"], "not drop on", "will not drop", "drop offset", "drop adjacent",
        "adjacent to it", "offset onto", "not on the lit", "avoid the pure cell",
        "not the pure cell itself", "offset from the pure",
    )
    return _smash(c["plan"]) and not reverts


def _grab_is_short(c) -> bool:
    """SMASH_GRAB framed as a FAST grab (drop on the pure = auto-harvest, pick up
    quickly), NOT a long seam walk over the jackpot. The night-2 error looked
    like: 'smash-and-grab. Drop onto (31,18)... then WALK THE SEAM ... pickup at
    hour 7 ... in one chain'. Green = plans the pure as a short/fast grab and the
    wider seam as a separate/later job."""
    if not _smash(c["plan"]):
        return False
    a = c["a"]
    long_walk = _mentions(
        a, "walk the seam", "walk the full seam", "walk the whole", "full chain",
        "one chain", "hour 7", "6-cell", "six-cell", "5 steps", "five steps",
        "then walk the", "long chain",
    )
    fast = _mentions(
        a, "pick up fast", "pickup fast", "pick up early", "pickup early",
        "pick up immediately", "pickup immediately", "bank it before",
        "auto-harvest", "fast grab", "0 extra steps", "zero extra steps",
        "1-2 steps", "1 to 2 steps", "short chain", "secure the pure",
        "secure it", "grab and pickup", "grab and go",
    )
    return (not long_walk) and fast


TURNS_ALL: List[Dict[str, Any]] = [
    {
        "id": "opener",
        "label": "Opener s69 d1 (1 harvester, blue setup, no redsign)",
        "file": "reports/prompts/s69_3way/day1_thinker.txt",
        "checks": _common() + [
            ("deploys_harvester", lambda c: _smash(c["plan"]) or _has(c["plan"], "HD", "CH")),
            ("keeps_blue_hotdrop", lambda c: _has(c["plan"], "HD")),
            ("launches_probe", lambda c: _has(c["plan"], "PR")),
            # aspirational (post-fix): no reliance on a phantom 'brightest' cell
            ("no_brightest_reasoning", lambda c: "brightest" not in c["a"]),
            ("no_phantom_redsign", lambda c: not _mentions(
                c["a"], "case 1", "my redsign", "mine=true", "mine = true")),
        ],
    },
    {
        "id": "redsign",
        "label": "Redsign discovery s69 d2 (CASE 1 mine=true; pure near beacon)",
        "file": "reports/prompts/s69_3way/day2_thinker.txt",
        "checks": _common() + [
            ("case1_identified", lambda c: _mentions(
                c["a"], "case 1", "my redsign", "mine=true", "mine = true", "it is your redsign")),
            ("names_pure_near_beacon", _names_pure_near_beacon),
            ("picks_smash_grab", lambda c: _smash(c["plan"])),
            # aspirational (hyg-contradictions): secures the pure without reverting
            # to the OFFSET lesson on its OWN redsign.
            ("secures_pure_not_offset", _secures_pure_not_offset),
            # aspirational (post-fix): SMASH_GRAB = fast grab, not a long seam walk
            ("grab_is_short", _grab_is_short),
            # aspirational (post-fix): value is 765, not the double-counted 2295
            ("value_not_2295", lambda c: "2295" not in c["a"]),
        ],
    },
    {
        "id": "vanilla",
        "label": "Vanilla s42 d3 (1 harvester, thin board, no redsign)",
        "file": "reports/prompts/v9_1v1_s42/day3_thinker.txt",
        "checks": _common() + [
            # true hallucination = ASSERTING a live/owned redsign or racing a pure
            # (NOT echoing the prompt's "no pure(255) race" negation).
            ("no_phantom_redsign", lambda c: not (
                _smash(c["plan"])
                or _mentions(c["a"], "mine=true", "mine = true", "my redsign",
                             "redsign is mine", "it is your redsign", "own the redsign",
                             "race the pure", "race the redsign"))),
            ("scouts_probes", lambda c: _has(c["plan"], "PR")),
            ("reflect_not_lost", lambda c: (
                _mentions(c["a"], "hoard", "held", "harvested")
                and not (("lost" in c["a"]) and ("hoard" not in c["a"])))),
        ],
    },
    {
        "id": "fullfleet",
        "label": "Full fleet s69 d7 (multi-harvester, final night, no redsign)",
        "file": "reports/prompts/s69_3way/day7_thinker.txt",
        "checks": _common() + [
            # full utilization: one harvester-consuming option (HD/CH/SMASH) per
            # ALIVE harvester (c["harv_n"], parsed from the STATE block). An idle
            # harvester is the under-deployment ws-full-utilization targets.
            ("deploys_all_available", lambda c: (
                len([p for p in c["plan"] if _smash([p]) or str(p).upper().startswith(("HD", "CH"))])
                >= max(2, c.get("harv_n", 2)))),
            # final night: don't burn probes on frontier vision (supersede is ok)
            ("final_no_frontier_probe", lambda c: not _has(c["plan"], "PR")),
        ],
    },
]


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="regress_context")
    p.add_argument("--turns", default="opener,redsign,vanilla,fullfleet",
                   help="Comma-separated turn ids to run.")
    p.add_argument("--repeat", type=int, default=5)
    p.add_argument("--think-tokens", type=int, default=1400)
    p.add_argument("--plan-tokens", type=int, default=800)
    p.add_argument("--think-wall", type=float, default=40.0)
    p.add_argument("--plan-wall", type=float, default=30.0)
    p.add_argument("--out", default=None)
    args = p.parse_args(argv)

    os.environ.setdefault("SOC_BACKEND", "snowflake")
    from sea_of_colours.orchestrator_2.harnesses.tabula_v7 import chat_schema
    from sea_of_colours.orchestrator_2.harnesses.tabula_v7 import directive as dm
    from sea_of_colours.orchestrator_2.harnesses.tabula_v9 import harness as v9h
    from sea_of_colours.orchestrator_2.cortex_chat import CortexChatInvoker

    if not CortexChatInvoker().is_ready():
        print("preflight: no Snowflake PAT/account.", file=sys.stderr)
        return 2

    think_instr, plan_instr = _instr_blocks()
    model = v9h._THINKER_CHAT_MODEL
    decision_first = chat_schema.DECISION_RESPONSE_FORMAT

    want = [t.strip() for t in args.turns.split(",") if t.strip()]
    turns = [t for t in TURNS_ALL if t["id"] in want]
    missing = [t for t in turns if not (_REPO_ROOT / t["file"]).exists()]
    for t in missing:
        print(f"WARNING: missing capture for '{t['id']}' -> {t['file']} (skipping)")
    turns = [t for t in turns if (_REPO_ROOT / t["file"]).exists()]
    if not turns:
        print("no turns to run (captures missing).", file=sys.stderr)
        return 1

    rows: List[str] = [f"# Context regression — model={model} repeat={args.repeat}\n"]
    scorecard: Dict[str, Dict[str, int]] = {}

    import re as _re
    for t in turns:
        full = (_REPO_ROOT / t["file"]).read_text(encoding="utf-8")
        i = full.find(_TASK_MARKER)
        context = full[:i].rstrip() if i > 0 else full
        # Count alive harvesters from the STATE block for adaptive checks.
        _hm = _re.search(r"harvesters_alive:\s*(\[[^\]]*\])", context)
        harv_n = _hm.group(1).count("'id'") if _hm else 1
        # Beacon center (drift-safe) for the pure-proximity check.
        _bm = _re.search(r"REDSIGN LIVE near \(~?(\d+),\s*~?(\d+)\)", context)
        beacon = (int(_bm.group(1)), int(_bm.group(2))) if _bm else None
        print(f"\n{'='*72}\n{t['id'].upper()}: {t['label']}\n  context={len(context)}c "
              f"harvesters={harv_n} file={t['file']}")
        rows.append(f"\n## {t['id']} — {t['label']}\ncontext={len(context)}c\n")
        checks = t["checks"]
        tally = {name: 0 for name, _ in checks}
        tally["_n"] = 0

        for r in range(1, args.repeat + 1):
            tres = _fire(model, context + "\n\n" + think_instr,
                         response_format=None, max_tokens=args.think_tokens,
                         wall=args.think_wall)
            analysis = str(tres.get("response") or "")
            tcap = tres.get("finish_reason") == "length"
            pprompt = context + "\n\n" + plan_instr.replace("__ANALYSIS__", analysis)
            pres = _fire(model, pprompt, response_format=decision_first,
                         max_tokens=args.plan_tokens, wall=args.plan_wall)
            presp = str(pres.get("response") or "")
            dv, _ = dm.parse_directive_json(presp)
            plan = list(getattr(dv, "plan", []) or []) if dv else []
            targets = list(getattr(dv, "targets", []) or []) if dv else []
            posture = getattr(dv, "posture", None) if dv else None
            landed = dv is not None and bool(plan or posture)
            ctx = {
                "a": analysis.lower(), "plan": plan, "targets": targets,
                "posture": posture, "landed": landed, "harv_n": harv_n,
                "beacon": beacon,
                "think_capped": tcap, "plan_capped": pres.get("finish_reason") == "length",
            }
            tally["_n"] += 1
            res_flags = []
            for name, fn in checks:
                try:
                    ok = bool(fn(ctx))
                except Exception:
                    ok = False
                tally[name] += int(ok)
                res_flags.append(f"{name}={'Y' if ok else '.'}")
            tot_ms = tres["_elapsed_ms"] + pres["_elapsed_ms"]
            print(f"  run {r}: {tot_ms:6d}ms think={len(analysis):5d}c(cap={tcap!s:5}) "
                  f"plan={plan} posture={posture}")
            print(f"         {' '.join(res_flags)}")
            rows.append(
                f"\n### run {r} ({tot_ms}ms, think {len(analysis)}c cap={tcap})\n"
                f"- plan={plan} targets={targets} posture={posture}\n"
                f"- checks: {', '.join(res_flags)}\n"
                f"**THINK:**\n```\n{analysis[:1600]}\n```\n"
                f"**PLAN:**\n```\n{presp[:900]}\n```\n")

        scorecard[t["id"]] = tally

    # ── scorecard ──────────────────────────────────────────────────────
    print(f"\n{'='*72}\nSCORECARD (hits / N)\n")
    rows.append("\n## Scorecard (hits / N)\n")
    for t in turns:
        tally = scorecard[t["id"]]
        n = tally["_n"] or 1
        print(f"\n{t['id']} (N={n}):")
        rows.append(f"\n**{t['id']}** (N={n}):\n")
        for name, _ in t["checks"]:
            line = f"  {name:26s} {tally[name]}/{n}"
            print(line)
            rows.append(f"- `{name}`: {tally[name]}/{n}\n")

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text("".join(rows) + "\n", encoding="utf-8")
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
