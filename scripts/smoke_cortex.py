"""Cortex AI-agent smoke test (RED_HARVEST baseline → SOC_RED_REAPER live).

Run me after pasting your Agent Arena PAT into ``~/.ssh/sf_config`` (or
into the ``SNOWFLAKE_PAT`` env var). The script performs three phases,
each gated so a failure surfaces a useful message rather than a stack
trace:

  Phase 0 — Credential check
    * ``CortexAgentInvoker.is_ready()`` — confirms PAT + account.
    * Prints the assembled agent endpoint so you can sanity-check it.

  Phase 1 — Heuristic baseline (RED_HARVEST)
    * Always runs against the in-memory store so we know the engine
      itself is healthy and the agent / submit / resolve cycle works.

  Phase 2 — Cortex live turn (SOC_RED_REAPER)
    * Requires ``SOC_BACKEND=snowflake`` so the game state is reachable
      from the Cortex agent's ``soc_get_view`` / ``soc_submit_policy``
      tool calls.
    * If ``SOC_BACKEND`` isn't ``snowflake``, Phase 2 is skipped with a
      loud notice (Cortex can't see an in-memory game).

Usage:
    SNOWFLAKE_PAT=... SOC_BACKEND=snowflake python scripts/smoke_cortex.py
    # or, with pat= in ~/.ssh/sf_config:
    SOC_BACKEND=snowflake python scripts/smoke_cortex.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any, Dict

from sea_of_colours.agent.cortex_invoker import CortexAgentInvoker
from sea_of_colours.agent.runtime import (
    CORTEX_AGENT_DEFAULT,
    HEURISTIC_AGENT_NAME,
    run_agent_turn,
)
from sea_of_colours.snowpark import backend as soc_backend
from sea_of_colours.snowpark import engine as soc_engine


def banner(title: str) -> None:
    line = "=" * (len(title) + 4)
    print(f"\n{line}\n  {title}\n{line}")


def mask(token: str) -> str:
    if not token:
        return "(empty)"
    if len(token) <= 8:
        return "***"
    return f"{token[:4]}…{token[-4:]} ({len(token)} chars)"


def phase_0_credentials() -> tuple[bool, CortexAgentInvoker]:
    banner("Phase 0 — credential check")
    inv = CortexAgentInvoker()
    print(f"  account         : {inv.account or '(missing)'}")
    print(f"  config_file     : {inv.config_file}")
    print(f"  pat_token       : {mask(inv.pat_token)}")
    print(f"  agent_name      : {inv.agent_name}")
    print(f"  agent_endpoint  : {inv.agent_endpoint or '(no account → no endpoint)'}")
    ready = inv.is_ready()
    if not ready:
        print(
            "  status          : NOT READY — Cortex calls will fall back to "
            f"{HEURISTIC_AGENT_NAME}."
        )
    else:
        print("  status          : READY")
    return ready, inv


def phase_1_heuristic() -> bool:
    banner(f"Phase 1 — heuristic baseline ({HEURISTIC_AGENT_NAME}, memory store)")
    # Force the in-memory store so this phase always runs even if Snowflake
    # is misconfigured. Restored at the end of the script.
    prior_backend = os.environ.get("SOC_BACKEND")
    os.environ["SOC_BACKEND"] = "memory"
    try:
        soc_backend.reset_for_tests()
        store = soc_backend.get_store()
        sid = soc_engine.init_session(store, seed=4242, width=24, height=16)[
            "session_id"
        ]
        t0 = time.time()
        result = run_agent_turn(store, sid, "p1", runtime_override="heuristic")
        dt = time.time() - t0
        print(f"  duration        : {dt:.2f}s")
        print(f"  runtime         : {result.get('runtime')}")
        print(f"  agent_id        : {result.get('agent_id')}")
        print(f"  moves           : {len(result.get('moves') or [])}")
        print(f"  night_resolved  : {result.get('night_resolved')}")
        print(f"  rationale       : {(result.get('rationale') or '')[:140]}")
        ok = (
            bool(result.get("ok"))
            and result.get("agent_id") == HEURISTIC_AGENT_NAME
            and result.get("runtime") == "heuristic"
        )
        print(f"  PASS            : {ok}")
        return ok
    finally:
        if prior_backend is not None:
            os.environ["SOC_BACKEND"] = prior_backend
        else:
            os.environ.pop("SOC_BACKEND", None)
        soc_backend.reset_for_tests()


def phase_2_cortex_live() -> bool:
    banner(f"Phase 2 — Cortex live turn ({CORTEX_AGENT_DEFAULT})")
    backend = os.environ.get("SOC_BACKEND", "memory")
    if backend != "snowflake":
        print(
            "  SKIP — SOC_BACKEND is "
            f"'{backend}'. Cortex needs a Snowflake-backed session to "
            "reach SOC_GET_VIEW / SOC_SUBMIT_POLICY. Re-run with:\n"
            "    SOC_BACKEND=snowflake python scripts/smoke_cortex.py"
        )
        return False

    try:
        soc_backend.reset_for_tests()
        store = soc_backend.get_store()
        info = soc_engine.init_session(store, seed=4242, width=24, height=16)
        sid = info["session_id"]
        print(f"  session_id      : {sid}")
        t0 = time.time()
        result = run_agent_turn(store, sid, "p1", runtime_override="cortex")
        dt = time.time() - t0
        print(f"  duration        : {dt:.2f}s")
        print(f"  runtime         : {result.get('runtime')}")
        print(f"  agent_id        : {result.get('agent_id')}")
        print(f"  submitted       : {result.get('submitted')}")
        print(f"  moves (echo)    : {len(result.get('moves') or [])}")
        print(f"  tool_calls      : {result.get('tool_calls')}")
        print(f"  night_resolved  : {result.get('night_resolved')}")
        print(f"  rationale       : {(result.get('rationale') or '')[:280]}")
        # Cortex success = the runtime label says ``cortex`` AND the
        # agent identity is the Cortex one. We do NOT require the
        # heuristic ``moves`` echo to be non-empty: Cortex submits its
        # own policy server-side via the ``soc_submit_policy`` tool, so
        # the local ``moves`` list is whatever the runtime happened to
        # carry through (often empty when Cortex drove it directly).
        # A graceful fallback to RED_HARVEST is NOT a pass.
        ok = (
            bool(result.get("ok"))
            and result.get("runtime") == "cortex"
            and result.get("agent_id") == CORTEX_AGENT_DEFAULT
        )
        print(f"  PASS            : {ok}")
        if not ok:
            print(
                "  → If agent_id flipped back to RED_HARVEST, the rationale "
                "above explains why (HTTP code, transport, missing tool, etc.)."
            )
        return ok
    except Exception as exc:  # pragma: no cover - surface live errors
        print(f"  EXCEPTION       : {type(exc).__name__}: {exc}")
        return False


def main() -> int:
    ready, _inv = phase_0_credentials()
    p1_ok = phase_1_heuristic()
    snowflake_backend = os.environ.get("SOC_BACKEND") == "snowflake"
    p2_attempted = ready and snowflake_backend
    p2_ok = phase_2_cortex_live() if ready else False

    banner("Summary")
    print(f"  Phase 0 credentials      : {'OK' if ready else 'NOT READY'}")
    print(f"  Phase 1 RED_HARVEST      : {'PASS' if p1_ok else 'FAIL'}")
    if not p2_attempted:
        p2_label = "SKIPPED" if not ready else "SKIPPED (need SOC_BACKEND=snowflake)"
    else:
        p2_label = "PASS" if p2_ok else "FAIL"
    print(f"  Phase 2 SOC_RED_REAPER   : {p2_label}")
    # Phase 0 + Phase 1 are required; Phase 2 only counts as a failure
    # when we actually tried it (credentials + Snowflake backend present).
    if not p1_ok:
        return 2
    if p2_attempted and not p2_ok:
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
