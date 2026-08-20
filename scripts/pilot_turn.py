#!/usr/bin/env python3
"""Raw single-turn capture for a Cortex agent on an eval fixture.

Unlike ``scripts/run_evals.py`` (which only surfaces the parsed policy +
rationale), this prints the RAW Cortex envelope for ONE turn: the exact
slim prompt we sent, the tool calls the agent made, whether it called
soc_submit_policy, the response text, and the move queue that actually
landed in the store. Use it to SEE the agent reason over a full-size grid.

Requires SOC_BACKEND=snowflake (the agent's soc_submit_policy tool runs
warehouse-side and must find the mirrored session).

Usage::

    SOC_BACKEND=snowflake SOC_AGENT_WORLD_VIEW=grid \
    SOC_CORTEX_AGENT=SOC_RED_REAPER_PILOT \
    python scripts/pilot_turn.py --scenario solo_drop_orbit
"""

from __future__ import annotations

import argparse
import json
import os
import sys


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scenario", default="solo_drop_orbit",
                    help="Eval scenario name (default: solo_drop_orbit).")
    ap.add_argument("--agent", default=None,
                    help="Cortex agent name (default: SOC_CORTEX_AGENT env "
                         "or SOC_RED_REAPER_PILOT).")
    ap.add_argument("--show-prompt", action="store_true",
                    help="Print the full slim prompt that was sent.")
    args = ap.parse_args(argv)

    agent_name = (
        args.agent
        or os.environ.get("SOC_CORTEX_AGENT")
        or "SOC_RED_REAPER_PILOT"
    )
    os.environ["SOC_CORTEX_AGENT"] = agent_name
    os.environ.setdefault("SOC_AGENT_WORLD_VIEW", "grid")

    from sea_of_colours.agent.cortex_invoker import CortexAgentInvoker
    from sea_of_colours.agent.runtime import _build_cortex_prompt
    from sea_of_colours.evals.runner import _mirror_fixture_to_backend
    from sea_of_colours.evals.scenarios import get_scenario
    from sea_of_colours.snowpark import engine as soc_engine

    backend = os.environ.get("SOC_BACKEND", "memory")
    scenario = get_scenario(args.scenario)
    store, session_id = scenario.build()
    player = scenario.player
    if backend == "snowflake":
        store = _mirror_fixture_to_backend(store, session_id)

    sess = soc_engine._hydrate_session(store, session_id)
    day_at_run = int(sess.day)

    view = soc_engine.get_view(store, session_id, player)
    prompt = _build_cortex_prompt(session_id, view, agent_name=agent_name)

    print("=" * 70)
    print(f"  PILOT TURN — scenario={args.scenario}  agent={agent_name}")
    print(f"  session={session_id}  seat={player}  day={day_at_run}  backend={backend}")
    print("=" * 70)
    print(f"  slim prompt chars : {len(prompt)}")
    print(f"  prompt has rules? : {'HARD RULES' in prompt or 'READING THE WORLD' in prompt}")
    # Confirm the grid the agent received.
    try:
        i = prompt.rfind("```json"); j = prompt.index("```", i + 7)
        state = json.loads(prompt[i + 7:j].strip())
        w = state.get("world", {})
        g = w.get("grid")
        nn = sum(1 for row in g for c in row if c is not None) if isinstance(g, list) else "n/a"
        nav = state.get("navigation", {})
        print(f"  grid dims         : {len(g)}x{len(g[0]) if g else 0}  non-null cells: {nn}")
        print(f"  best_red_visible  : {(nav.get('best_red_visible') or [])[:3]}")
    except Exception as exc:  # pragma: no cover
        print(f"  (could not parse STATE: {exc})")
    if args.show_prompt:
        print("-" * 70)
        print(prompt)
        print("-" * 70)

    inv = CortexAgentInvoker(agent_name=agent_name)
    print(f"  invoker ready?    : {inv.is_ready()}  endpoint={inv.agent_endpoint[:60]}...")
    if not inv.is_ready():
        print("  ABORT — invoker not ready (PAT/account).")
        return 2
    if backend != "snowflake":
        print("  WARNING — SOC_BACKEND != snowflake; soc_submit_policy will not "
              "find the session. Run with SOC_BACKEND=snowflake.")

    result = inv.invoke(prompt)
    print("\n--- RAW CORTEX ENVELOPE ---")
    print(f"  ok                : {result.get('ok')}")
    print(f"  elapsed_ms        : {result.get('elapsed_ms')}")
    print(f"  submitted_policy  : {result.get('submitted_policy')}")
    print(f"  wallclock_capped  : {result.get('wallclock_capped')}")
    print(f"  tool_calls        : {result.get('tool_calls')}")
    print(f"  tool_errors       : {result.get('tool_errors')}")
    print(f"  hallucinated_tools: {result.get('hallucinated_tools')}")
    if not result.get("ok"):
        print(f"  error             : {result.get('error')}")
    resp = (result.get("response") or "").strip()
    print(f"\n--- RESPONSE TEXT ---\n{resp[:1200]}")

    # What actually landed in the store?
    try:
        policies = store.list_policies(session_id, day_at_run) or {}
        queue = policies.get(player) or []
        norm = [m if isinstance(m, dict) else getattr(m, "to_dict", lambda: m)() for m in queue]
        print(f"\n--- STORED MOVE QUEUE (day {day_at_run}, {player}) ---")
        print(f"  {len(norm)} move(s):")
        for m in norm:
            print(f"    {m}")
    except Exception as exc:  # pragma: no cover
        print(f"  (could not read stored policy: {exc})")

    return 0 if result.get("submitted_policy") else 1


if __name__ == "__main__":
    sys.exit(main())
