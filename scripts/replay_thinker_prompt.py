#!/usr/bin/env python3
"""Fire a prompt at the LIVE tabula_v9 thinker with its exact production config.

Feeds a prompt (a captured file, or a stored audit ``prompt_excerpt``) to the
Cortex chat invoker using the SAME model, token ceiling, response schema and
wallclock cap the v9 harness uses for its thinker — then reports, per run:
elapsed_ms, whether it hit the wallclock cap, the response length, whether the
reasoning/JSON looks truncated, and the parsed directive. ``--repeat`` runs it N
times so a flaky timeout (e.g. the day-6 night) can be characterised.

Usage::

    PYTHONPATH=. python scripts/replay_thinker_prompt.py \\
        --file reports/prompts/v9_1v1_s42/day6_thinker.txt --repeat 3

    PYTHONPATH=. python scripts/replay_thinker_prompt.py \\
        --session 91cf... --day 5 --repeat 2      # replay a STORED prompt
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import List, Optional

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="replay_thinker_prompt")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--file", default=None, help="Path to a prompt text file.")
    src.add_argument("--session", default=None,
                     help="Audited session_id (with --day) to pull a stored "
                          "prompt_excerpt (may be truncated at 32KB).")
    p.add_argument("--day", type=int, default=None, help="Day for --session.")
    p.add_argument("--player", default="p1")
    p.add_argument("--repeat", type=int, default=1)
    p.add_argument("--out", default=None, help="Optional markdown dump of runs.")
    return p


def _load_prompt(args) -> str:
    if args.file:
        return Path(args.file).read_text(encoding="utf-8")
    if not args.day:
        raise SystemExit("--session requires --day")
    os.environ.setdefault("SOC_BACKEND", "snowflake")
    from sea_of_colours.snowpark import backend as soc_backend
    store = soc_backend.get_store()
    rows = store.list_agent_invocations(args.session)
    for r in rows:
        if (str(r.get("player")) == args.player
                and int(r.get("day") or 0) == args.day
                and "THINKER" in str(r.get("agent_id") or "").upper()):
            pe = str(r.get("prompt_excerpt") or "")
            if len(pe) >= 32000:
                print("WARNING: stored prompt is 32000 chars = TRUNCATED; not "
                      "the exact prompt. Use reconstruct_prompt.py for exact.",
                      file=sys.stderr)
            return pe
    raise SystemExit(f"no thinker prompt for {args.player} day {args.day}")


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    os.environ.setdefault("SOC_BACKEND", "snowflake")

    from sea_of_colours.orchestrator_2.cortex_chat import CortexChatInvoker
    from sea_of_colours.orchestrator_2.harnesses.tabula_v7 import chat_schema
    from sea_of_colours.orchestrator_2.harnesses.tabula_v9 import harness as v9h
    from sea_of_colours.orchestrator_2.harnesses.tabula_v7 import directive as dmod

    if not CortexChatInvoker().is_ready():
        print("preflight: no Snowflake PAT/account found.", file=sys.stderr)
        return 2

    prompt = _load_prompt(args)
    print(f"prompt: {len(prompt)} chars   model={v9h._THINKER_CHAT_MODEL}   "
          f"max_completion_tokens={v9h._THINKER_CHAT_MAX_TOKENS}   "
          f"wallclock_cap={v9h._THINKER_CHAT_WALLCLOCK_S}s   repeat={args.repeat}")
    print("=" * 70)

    lines: List[str] = [f"# Thinker replay ({len(prompt)} char prompt)\n"]
    for i in range(1, args.repeat + 1):
        invoker = CortexChatInvoker(
            model=v9h._THINKER_CHAT_MODEL,
            response_format=chat_schema.DECISION_RESPONSE_FORMAT,
            max_completion_tokens=v9h._THINKER_CHAT_MAX_TOKENS,
        )
        t0 = time.time()
        res = invoker.invoke(prompt, wallclock_cap_s=v9h._THINKER_CHAT_WALLCLOCK_S)
        dt = int((time.time() - t0) * 1000)
        resp = str(res.get("response") or "")
        thinking = str(res.get("thinking") or "")
        capped_wall = bool(res.get("wallclock_capped"))
        ok = bool(res.get("ok"))
        directive, reasoning = dmod.parse_directive_json(resp)
        posture = getattr(directive, "posture", None)
        plan = getattr(directive, "plan", None)
        # A crude truncation signal: response present but no closing brace / no
        # parseable posture despite non-trivial length.
        looks_trunc = bool(resp) and resp.rstrip()[-1:] not in "}\"" and len(resp) > 200
        verdict = (
            "TIMEOUT/EMPTY" if not resp else
            "WALLCLOCK_CAP" if capped_wall else
            "TRUNCATED?" if looks_trunc else "OK"
        )
        print(f"run {i}: {dt:6d}ms  ok={ok}  wall_capped={capped_wall}  "
              f"resp={len(resp):5d}c  think={len(thinking):5d}c  "
              f"posture={posture}  plan={plan}  -> {verdict}")
        if res.get("error"):
            print(f"        error: {str(res.get('error'))[:200]}")
        lines.append(
            f"\n## run {i} — {dt}ms — {verdict}\n"
            f"- ok={ok} wall_capped={capped_wall} resp_len={len(resp)} "
            f"think_len={len(thinking)} posture={posture} plan={plan}\n\n"
            f"```\n{resp[:4000]}\n```\n"
        )

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
