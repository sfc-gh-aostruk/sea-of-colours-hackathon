#!/usr/bin/env python3
"""A/B a captured thinker prompt: single-call reasoning-first vs two-stage
THINK->PLAN "contained thinking".

Feeds the SAME byte-exact board context (a prompt captured by
``reconstruct_prompt.py``) to two strategist designs, live, N times each:

  BASELINE  — reasoning-FIRST, one call, big token budget (the design that
              rambled ~9k chars past the cap on dense redsign nights and lost
              the whole decision).
  TWOSTAGE  — (1) a THINK call with its OWN small token budget that emits ONLY
              bounded prose analysis, then (2) a PLAN call that takes that
              analysis and emits ONLY the compact decision JSON. Each stage owns
              its budget so neither starves the other: the think is leashed and
              the plan ALWAYS lands, conditioned on the real reasoning.

Per run we report whether a usable directive landed, its posture/plan/targets,
whether it selected the CASE-1 pure-grab pattern (SMASH_GRAB) and named the pure
cell, plus elapsed + truncation. The point is a pure-capture / plan-lands RATE,
not a single sample.

Usage::

    PYTHONPATH=. SOC_BACKEND=snowflake python scripts/exp_contained_think.py \\
        --file reports/prompts/s69_3way/day2_thinker.txt \\
        --pure 31,18 --repeat 5 --out reports/exp_contained_think_s69_d2.md
"""

from __future__ import annotations

import argparse
import copy
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_TASK_MARKER = "=== YOUR TASK"

# NB: these MIRROR the shipped harness (tabula_v9/prompt.py). Keep in sync so
# the A/B reflects what actually runs in production.
from sea_of_colours.orchestrator_2.harnesses.tabula_v9 import prompt as _v9p  # noqa: E402

_THINK_INSTR = _v9p._V9_THINK_TASK

_PLAN_INSTR = (
    "=== YOUR ANALYSIS (from your think pass — commit it now) ===\n"
    "<<<\n__ANALYSIS__\n>>>\n"
    + _v9p._V9_PLAN_TASK
    + "\n" + _v9p._V9_THINKER_ADDENDUM
    + "\nOUTPUT ONE JSON OBJECT NOW — DECISION FIRST: \"posture\", then "
    "\"plan\" (the OPTION MENU IDs from your analysis, in execution order), "
    "then \"situational\" when a REDSIGN is live; a SHORT \"reasoning\" LAST. "
    "Start with the open-brace character. GO:\n"
)

_BASELINE_INSTR = """\
=== YOUR TASK (STRATEGIST) ===
You are the STRATEGIST for tonight. Return ONE JSON object. Fill "reasoning"
FIRST and actually think there (reflect on last night; read the REDSIGN — yours
or a rival's; which OPTION MENU IDs to select and in what order; targets/avoid),
then the decision fields: "posture", "plan" (OPTION MENU IDs in execution
order), "situational", "targets", "avoid", "note". OUTPUT ONE JSON OBJECT NOW
with "reasoning" FIRST. Start with the open-brace character. GO:
"""


def _reasoning_first_schema() -> Dict[str, Any]:
    """The OLD reasoning-first DECISION schema (reasoning property first,
    required)."""
    from sea_of_colours.orchestrator_2.harnesses.tabula_v7 import chat_schema
    schema = copy.deepcopy(
        chat_schema.DECISION_RESPONSE_FORMAT["json_schema"]["schema"]
    )
    props = schema["properties"]
    reordered = {"reasoning": props["reasoning"]}
    for k, v in props.items():
        if k != "reasoning":
            reordered[k] = v
    schema["properties"] = reordered
    schema["required"] = ["reasoning", "posture"]
    return {"type": "json_schema",
            "json_schema": {"name": "soc_strategist_decision", "schema": schema}}


def _fire(model: str, prompt: str, *, response_format=None,
          max_tokens: int, wall: float) -> Dict[str, Any]:
    from sea_of_colours.orchestrator_2.cortex_chat import CortexChatInvoker
    inv = CortexChatInvoker(
        model=model, response_format=response_format,
        max_completion_tokens=max_tokens,
    )
    t0 = time.time()
    res = inv.invoke(prompt, wallclock_cap_s=wall)
    res["_elapsed_ms"] = int((time.time() - t0) * 1000)
    return res


def _summarize(directive, *, pure: Tuple[int, int]) -> Dict[str, Any]:
    from sea_of_colours.orchestrator_2.harnesses.tabula_v7 import directive as dm  # noqa
    posture = getattr(directive, "posture", None)
    plan = list(getattr(directive, "plan", []) or [])
    targets = list(getattr(directive, "targets", []) or [])
    landed = directive is not None and bool(plan or posture)
    picked_smash = any("SMASH" in p.upper() for p in plan)
    named_pure = pure in [tuple(t) for t in targets]
    return {
        "landed": landed, "posture": posture, "plan": plan,
        "targets": targets, "picked_smash_grab": picked_smash,
        "named_pure": named_pure,
    }


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="exp_contained_think")
    p.add_argument("--file", required=True, help="Captured thinker prompt.")
    p.add_argument("--pure", default="31,18", help="Pure cell x,y for scoring.")
    p.add_argument("--repeat", type=int, default=5)
    p.add_argument("--think-tokens", type=int, default=1200)
    p.add_argument("--plan-tokens", type=int, default=700)
    p.add_argument("--baseline-tokens", type=int, default=3600)
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

    px, py = (int(v) for v in args.pure.split(","))
    pure = (px, py)
    model = v9h._THINKER_CHAT_MODEL
    full = Path(args.file).read_text(encoding="utf-8")
    i = full.find(_TASK_MARKER)
    context = full[:i].rstrip() if i > 0 else full
    print(f"context: {len(context)} chars   model={model}   pure={pure}   "
          f"repeat={args.repeat}")
    print("=" * 72)

    rf_schema = _reasoning_first_schema()
    decision_first = chat_schema.DECISION_RESPONSE_FORMAT

    rows: List[str] = [f"# Contained-thinking A/B ({Path(args.file).name})\n",
                       f"context={len(context)}c model={model} pure={pure} "
                       f"repeat={args.repeat}\n"]

    tallies: Dict[str, Dict[str, int]] = {}

    def _tally(kind: str, s: Dict[str, Any], capped: bool) -> None:
        t = tallies.setdefault(
            kind, {"landed": 0, "smash": 0, "pure": 0, "capped": 0, "n": 0})
        t["n"] += 1
        t["landed"] += int(s["landed"])
        t["smash"] += int(s["picked_smash_grab"])
        t["pure"] += int(s["named_pure"])
        t["capped"] += int(capped)

    for r in range(1, args.repeat + 1):
        # ── BASELINE: reasoning-first, one call ──────────────────────────
        bprompt = context + "\n\n" + _BASELINE_INSTR
        res = _fire(model, bprompt, response_format=rf_schema,
                    max_tokens=args.baseline_tokens, wall=args.think_wall)
        resp = str(res.get("response") or "")
        dv, _ = dm.parse_directive_json(resp)
        s = _summarize(dv, pure=pure)
        capped = res.get("finish_reason") == "length"
        _tally("baseline", s, capped)
        print(f"run {r} BASELINE  {res['_elapsed_ms']:6d}ms resp={len(resp):5d}c "
              f"capped={capped!s:5} landed={s['landed']!s:5} "
              f"smash={s['picked_smash_grab']!s:5} pure={s['named_pure']!s:5} "
              f"plan={s['plan']}")
        rows.append(f"\n## run {r} BASELINE — {res['_elapsed_ms']}ms capped={capped}\n"
                    f"- landed={s['landed']} plan={s['plan']} targets={s['targets']}\n"
                    f"```\n{resp[:1500]}\n```\n")

        # ── TWOSTAGE: THINK (bounded) -> PLAN (decision only) ────────────
        tprompt = context + "\n\n" + _THINK_INSTR
        tres = _fire(model, tprompt, response_format=None,
                     max_tokens=args.think_tokens, wall=args.think_wall)
        analysis = str(tres.get("response") or "")
        tcapped = tres.get("finish_reason") == "length"
        pprompt = (context + "\n\n"
                   + _PLAN_INSTR.replace("__ANALYSIS__", analysis))
        pres = _fire(model, pprompt, response_format=decision_first,
                     max_tokens=args.plan_tokens, wall=args.plan_wall)
        presp = str(pres.get("response") or "")
        dv2, _ = dm.parse_directive_json(presp)
        s2 = _summarize(dv2, pure=pure)
        pcapped = pres.get("finish_reason") == "length"
        _tally("twostage", s2, pcapped)
        tot_ms = tres["_elapsed_ms"] + pres["_elapsed_ms"]
        print(f"run {r} TWOSTAGE  {tot_ms:6d}ms think={len(analysis):5d}c"
              f"(cap={tcapped!s:5}) plan_resp={len(presp):4d}c "
              f"landed={s2['landed']!s:5} smash={s2['picked_smash_grab']!s:5} "
              f"pure={s2['named_pure']!s:5} plan={s2['plan']}")
        rows.append(
            f"\n## run {r} TWOSTAGE — think {tres['_elapsed_ms']}ms "
            f"(cap={tcapped}) + plan {pres['_elapsed_ms']}ms (cap={pcapped})\n"
            f"- landed={s2['landed']} plan={s2['plan']} targets={s2['targets']}\n"
            f"**THINK analysis:**\n```\n{analysis[:1800]}\n```\n"
            f"**PLAN decision:**\n```\n{presp[:1200]}\n```\n")
        print("-" * 72)

    print("\n=== SUMMARY (rate over %d runs) ===" % args.repeat)
    for kind in ("baseline", "twostage"):
        t = tallies.get(kind)
        if not t:
            continue
        n = t["n"] or 1
        print(f"{kind:9s}: landed {t['landed']}/{n}  smash_grab {t['smash']}/{n}"
              f"  named_pure {t['pure']}/{n}  output_capped {t['capped']}/{n}")
        rows.append(f"\n- **{kind}**: landed {t['landed']}/{n}, smash_grab "
                    f"{t['smash']}/{n}, named_pure {t['pure']}/{n}, "
                    f"output_capped {t['capped']}/{n}")

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text("\n".join(rows) + "\n", encoding="utf-8")
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
