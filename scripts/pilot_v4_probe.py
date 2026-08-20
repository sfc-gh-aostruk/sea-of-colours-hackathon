#!/usr/bin/env python3
"""PILOT_V4 staged single-turn diagnostic — verify the agent ACTUALLY works.

The point of this tool: before trusting the full agent, prove each
*elementary* stage works and localise any break. It drives the REAL
``harnesses.pilot_v4.harness.run`` (both Cortex calls, real submit) on one
eval fixture and prints a PASS / WARN / FAIL verdict per stage:

    S0 credentials  strategist + tactician invokers ready (PAT + account)
    S1 compile      candidate menu / orbit options compiled (non-empty?)
    S2 strategist   HTTP ok · under cap · plan ∈ taxonomy · not rambling
    S3 tactician    HTTP ok · under cap · valid JSON · picked real ids
    S4 materialize  legal verbs · ≤21 slots · every harvester has a pickup
    S5 submit       queue landed (submitted, no submit errors)
    S6 budget       total wallclock inside the 60–90s interactive window

Exit code = the number of the FIRST failing stage (0 = all pass), so CI /
a human sees instantly which brick is missing.

Requires SOC_BACKEND=snowflake (the submit tool runs warehouse-side and
must find the mirrored session).

Usage::

    SOC_BACKEND=snowflake PYTHONPATH=. python scripts/pilot_v4_probe.py \
        --scenario tier_choice --seat p1

    # orbit phase:
    SOC_BACKEND=snowflake PYTHONPATH=. python scripts/pilot_v4_probe.py \
        --scenario solo_drop_orbit

    # batch metrics over N runs (ramble rate, plan mix, fallback rate, p50/p95):
    SOC_BACKEND=snowflake PYTHONPATH=. python scripts/pilot_v4_probe.py \
        --scenario tier_choice --repeat 10
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from typing import Any, Dict, List, Mapping, Optional, Tuple


# ── verdict helpers ─────────────────────────────────────────────────
PASS, WARN, FAIL = "PASS", "WARN", "FAIL"
_GLYPH = {PASS: "✅", WARN: "⚠️ ", FAIL: "❌"}


class Stage:
    def __init__(self, num: int, name: str):
        self.num = num
        self.name = name
        self.verdict = PASS
        self.notes: List[str] = []

    def fail(self, msg: str) -> None:
        self.verdict = FAIL
        self.notes.append(msg)

    def warn(self, msg: str) -> None:
        if self.verdict != FAIL:
            self.verdict = WARN
        self.notes.append(msg)

    def ok(self, msg: str) -> None:
        self.notes.append(msg)

    def render(self) -> str:
        head = f"  {_GLYPH[self.verdict]} S{self.num} {self.name:<12} {self.verdict}"
        body = "".join(f"\n        · {n}" for n in self.notes)
        return head + body


# ── config ──────────────────────────────────────────────────────────
_TAXONOMY_HINT = None  # filled from plans at runtime
_STRAT_CAP_MS = 25_000
_TACT_CAP_MS = 45_000
_TOTAL_LOW_MS = 60_000   # below this = fast (fine, but flag: strategist may be rushing)
_TOTAL_HIGH_MS = 90_000  # above this = over the interactive ceiling
_RAMBLE_CHARS = 1_800    # strategist longer than this = worth eyeballing for loop/doubt


def _menu_summary(compiled: Mapping[str, Any], is_orbit: bool) -> Tuple[int, str]:
    """Return (n_actionable, human_summary) for the compiled menu."""
    if is_orbit:
        orbital = compiled.get("orbital") or compiled
        rec = (orbital.get("recommended_orbit_policy") or {}).get("actions") or []
        return len(rec), f"recommended_orbit actions={len(rec)} trivial={orbital.get('trivial')}"
    cands = compiled.get("candidates") or {}
    counts = {k: len(cands.get(k) or []) for k in
              ("harvest", "probes", "probe_supersede", "harvester_crush",
               "hot_drop", "drop_block", "emp_launch")}
    rec = len((cands.get("recommended_policy") or {}).get("moves") or [])
    total = sum(counts.values())
    return total + rec, f"recommended_moves={rec} " + " ".join(f"{k}={v}" for k, v in counts.items() if v)


def _deployed_harvesters(agent_view: Mapping[str, Any]) -> List[str]:
    out = []
    for a in (agent_view.get("my_assets") or []):
        if isinstance(a, Mapping) and str(a.get("kind") or "").lower() == "harvester" \
                and str(a.get("state") or "").lower() in ("deployed", "surface"):
            out.append(str(a.get("id") or ""))
    return out


def _read_planning_queue(store, session_id: str, day: int, seat: str) -> List[Dict[str, Any]]:
    try:
        policies = store.list_policies(session_id, day) or {}
        queue = policies.get(seat) or []
        return [m if isinstance(m, dict) else getattr(m, "to_dict", lambda: m)() for m in queue]
    except Exception:
        return []


# ── one staged run ──────────────────────────────────────────────────
def probe_once(*, scenario_name: str, seat_arg: Optional[str], show_prompts: bool,
               verbose: bool, force_orbit: bool = False) -> Tuple[List[Stage], Dict[str, Any]]:
    from sea_of_colours.orchestrator_2.harnesses.pilot_v4 import harness as hv4
    from sea_of_colours.orchestrator_2.harnesses.pilot_v4.candidates import compile_candidates
    from sea_of_colours.orchestrator_2.harnesses.pilot_v4.orbit import compile_orbit_candidates
    from sea_of_colours.orchestrator_2.harnesses.pilot_v4.plans import PLAN_LABELS
    from sea_of_colours.orchestrator_2.cortex_invoker import CortexAgentInvoker
    from sea_of_colours.evals.runner import _mirror_fixture_to_backend
    from sea_of_colours.evals.scenarios import get_scenario
    from sea_of_colours.snowpark import engine as soc_engine

    stages: List[Stage] = []
    metrics: Dict[str, Any] = {}

    # Build + mirror fixture.
    scenario = get_scenario(scenario_name)
    store, session_id = scenario.build()
    seat = seat_arg or scenario.player
    if os.environ.get("SOC_BACKEND") == "snowflake":
        store = _mirror_fixture_to_backend(store, session_id)
    # Force orbit phase if requested (no eval scenario ships an orbit turn).
    if force_orbit:
        from sea_of_colours.game.session import Phase
        sess = soc_engine._hydrate_session(store, session_id)
        sess.phase = Phase.ORBIT
        # Seed credits so the orbit menu is non-empty (repairs/builds/probes
        # are credit-gated; a raw planning fixture has 0 credits).
        try:
            sess.award_orbit_credits()
        except Exception:
            for p in getattr(sess, "players", []) or []:
                sess.credits[p] = int(sess.credits.get(p, 0)) + 300
        soc_engine.save_session_full(store, sess)
    sess = soc_engine._hydrate_session(store, session_id)
    day = int(sess.day)
    view = soc_engine.get_view(store, session_id, seat)
    agent_view = view.get("agent_view") or {}
    phase = str(view.get("phase") or agent_view.get("meta", {}).get("phase") or "planning").lower()
    is_orbit = phase == "orbit"
    metrics.update(scenario=scenario_name, seat=seat, day=day, phase=phase)

    # ── S0 credentials ──
    s0 = Stage(0, "credentials")
    strat_inv = CortexAgentInvoker(agent_name=hv4.STRATEGIC_AGENT)
    tact_inv = CortexAgentInvoker(agent_name=hv4.TACTICAL_AGENT)
    if not strat_inv.is_ready():
        s0.fail(f"{hv4.STRATEGIC_AGENT} invoker not ready (PAT/account)")
    else:
        s0.ok(f"{hv4.STRATEGIC_AGENT} ready · cap {strat_inv._wallclock_cap_s}s")
    if not tact_inv.is_ready():
        s0.fail(f"{hv4.TACTICAL_AGENT} invoker not ready (PAT/account)")
    else:
        s0.ok(f"{hv4.TACTICAL_AGENT} ready · cap {tact_inv._wallclock_cap_s}s")
    if os.environ.get("SOC_BACKEND") != "snowflake":
        s0.warn("SOC_BACKEND != snowflake — submit tool cannot reach the session")
    stages.append(s0)
    if s0.verdict == FAIL:
        return stages, metrics

    # ── S1 compile ──
    s1 = Stage(1, "compile")
    try:
        compiled = compile_orbit_candidates(agent_view) if is_orbit else compile_candidates(agent_view)
        compiled_wrap = {"orbital": compiled} if is_orbit else compiled
        n, summary = _menu_summary(compiled_wrap, is_orbit)
        metrics["_menu_n"] = n
        s1.ok(f"phase={phase} · {summary}")
        if n == 0:
            s1.warn("menu is empty (blind/early turn?) — agent will lean on fallback")
    except Exception as exc:
        s1.fail(f"compiler raised: {type(exc).__name__}: {exc}")
        stages.append(s1)
        return stages, metrics
    stages.append(s1)

    # ── drive the REAL harness ──
    t0 = time.time()
    result = hv4.run(store=store, session_id=session_id, player=seat, view=view)
    total_ms = int((time.time() - t0) * 1000)
    extras = result.get("extras") or {}
    metrics.update(
        total_ms=total_ms,
        strategist_ms=int(extras.get("strategist_ms") or 0),
        tactician_ms=int(extras.get("tactician_ms") or 0),
        plan_label=extras.get("plan_label") or "",
        fallback=(extras.get("decision_validation") or {}).get("fallback_used"),
        fallback_reason=(extras.get("decision_validation") or {}).get("fallback_reason"),
        decision_error=extras.get("decision_error"),
        materialized=extras.get("materialized_count"),
        submitted=result.get("submitted_policy"),
        wallclock_capped=result.get("wallclock_capped"),
    )

    if show_prompts:
        print("\n----- STRATEGIST NOTE -----\n" + str(extras.get("strategist_note") or "")[:6000])
        print("\n----- TACTICIAN RESPONSE -----\n" + str(result.get("response") or "")[:1000])

    # ── S2 strategist ──
    s2 = Stage(2, "strategist")
    strat_ms = int(extras.get("strategist_ms") or 0)
    strat_note = str(extras.get("strategist_note") or "")
    plan = str(extras.get("plan_label") or "")
    if result.get("wallclock_capped") and strat_ms >= _STRAT_CAP_MS - 500:
        s2.warn(f"strategist near/at wallclock cap ({strat_ms}ms)")
    if not extras.get("strategist_ok", True):
        s2.fail(f"strategist HTTP/orchestration error: {extras.get('strategist_error')}")
    tool_errors = extras.get("tool_errors") or []
    if tool_errors:
        s2.warn(f"tool_errors during turn: {tool_errors}")
    if not strat_note.strip():
        s2.fail(f"strategist returned empty text (error={extras.get('strategist_error')})")
    plan_explicit = bool(extras.get("plan_explicit"))
    if plan and plan in PLAN_LABELS and plan_explicit:
        s2.ok(f"plan='{plan}' ∈ taxonomy (explicit PLAN: line) · {strat_ms}ms")
    elif plan and plan in PLAN_LABELS and not plan_explicit:
        s2.warn(f"plan defaulted to '{plan}' — no explicit PLAN: line parsed "
                "(footer likely truncated/omitted) · {}ms".format(strat_ms))
    else:
        s2.fail(f"plan not parsed from strategist output (got '{plan}')")
    if len(strat_note) > _RAMBLE_CHARS:
        s2.warn(f"strategist long ({len(strat_note)} chars > {_RAMBLE_CHARS}) — "
                "OK if it's grounded reasoning, watch for looping/doubt")
    else:
        s2.ok(f"concise ({len(strat_note)} chars)")
    stages.append(s2)

    # ── S3 tactician ──
    s3 = Stage(3, "tactician")
    tact_ms = int(extras.get("tactician_ms") or 0)
    dec_err = extras.get("decision_error")
    decision = extras.get("decision") or {}
    validation = extras.get("decision_validation") or {}
    if dec_err:
        s3.fail(f"tactician JSON not parsed: {dec_err} (raw: {str(result.get('response'))[:120]!r})")
    else:
        sels = decision.get("selections") or []
        s3.ok(f"valid JSON · {len(sels)} selection(s) · {tact_ms}ms")
        selected_ids = validation.get("selected_ids") or []
        if selected_ids:
            s3.ok(f"resolved ids={selected_ids}")
        if validation.get("fallback_used"):
            s3.warn(f"harness fell back ({validation.get('fallback_reason')}) — picks not honoured")
    if tact_ms > _TACT_CAP_MS:
        s3.warn(f"tactician over cap ({tact_ms}ms > {_TACT_CAP_MS}ms)")
    stages.append(s3)

    # ── S4 materialize ──
    s4 = Stage(4, "materialize")
    mat_count = int(extras.get("materialized_count") or 0)
    menu_n = metrics.get("_menu_n", 1)
    if mat_count == 0:
        if is_orbit and menu_n == 0:
            s4.warn("0 actions — orbit menu was empty (legal no-op turn)")
        else:
            s4.fail("no moves/actions materialized")
    elif mat_count > hv4.MAX_MOVES and not is_orbit:
        s4.fail(f"materialized {mat_count} > MAX_MOVES {hv4.MAX_MOVES}")
    else:
        s4.ok(f"{mat_count} {'action' if is_orbit else 'move'}(s)")
    if not is_orbit:
        queue = _read_planning_queue(store, session_id, day, seat)
        if queue:
            verbs = [str(m.get("a")) for m in queue]
            illegal = [v for v in verbs if v not in hv4._PLANNING_VERBS]
            if illegal:
                s4.fail(f"illegal verbs in landed queue: {illegal}")
            # no harvester may be dropped more than once in a Nox
            dropped = [str(m.get("unit")) for m in queue if str(m.get("a")) == "drop" and m.get("unit")]
            dupes = {u for u in dropped if dropped.count(u) > 1}
            if dupes:
                s4.fail(f"harvester(s) dropped more than once (illegal): {sorted(dupes)}")
            # pickup coverage on the LANDED queue (the real survival check).
            on_surface = set(_deployed_harvesters(agent_view))
            picked = set()
            for m in queue:
                if str(m.get("a")) == "drop" and m.get("unit"):
                    on_surface.add(str(m.get("unit")))
                if str(m.get("a")) == "pickup" and m.get("unit"):
                    picked.add(str(m.get("unit")))
            stranded = on_surface - picked
            if stranded:
                s4.fail(f"harvesters left on surface (no pickup): {sorted(stranded)}")
            else:
                s4.ok(f"pickup coverage OK ({len(on_surface)} harvester(s))")
            if validation.get("pickup_repaired"):
                s4.warn(f"harness auto-repaired pickups for {validation['pickup_repaired']}")
        else:
            s4.warn("could not read landed queue from store to verify pickups")
    stages.append(s4)

    # ── S5 submit ──
    s5 = Stage(5, "submit")
    if result.get("submitted_policy"):
        s5.ok("submitted_policy=True")
    else:
        s5.fail("submitted_policy=False — nothing landed")
    submit_errors = extras.get("submit_errors") or []
    if submit_errors:
        s5.fail(f"submit errors: {submit_errors}")
    tool_errors = extras.get("tool_errors") or []
    if tool_errors:
        s5.warn(f"tool_errors surfaced: {tool_errors}")
    stages.append(s5)

    # ── S6 budget ──
    s6 = Stage(6, "budget")
    if total_ms > _TOTAL_HIGH_MS:
        s6.fail(f"total {total_ms}ms over {_TOTAL_HIGH_MS}ms interactive ceiling")
    elif total_ms < _TOTAL_LOW_MS:
        s6.ok(f"total {total_ms}ms (fast; under {_TOTAL_LOW_MS//1000}s)")
    else:
        s6.ok(f"total {total_ms}ms (inside 60–90s window)")
    s6.ok(f"strategist {strat_ms}ms + tactician {tact_ms}ms")
    stages.append(s6)

    return stages, metrics


# ── batch mode ──────────────────────────────────────────────────────
def run_batch(args) -> int:
    plan_mix: Dict[str, int] = {}
    fallbacks = 0
    json_ok = 0
    rambles = 0
    totals: List[int] = []
    strat_ms: List[int] = []
    tact_ms: List[int] = []
    fails = 0

    for i in range(args.repeat):
        stages, m = probe_once(scenario_name=args.scenario, seat_arg=args.seat,
                               show_prompts=False, verbose=False,
                               force_orbit=getattr(args, "orbit", False))
        worst = max((s.num for s in stages if s.verdict == FAIL), default=-1)
        status = "FAIL@S%d" % worst if worst >= 0 else "ok"
        if worst >= 0:
            fails += 1
        plan_mix[m.get("plan_label") or "?"] = plan_mix.get(m.get("plan_label") or "?", 0) + 1
        if m.get("fallback"):
            fallbacks += 1
        if not m.get("decision_error"):
            json_ok += 1
        if m.get("total_ms"):
            totals.append(m["total_ms"])
        if m.get("strategist_ms"):
            strat_ms.append(m["strategist_ms"])
        if m.get("tactician_ms"):
            tact_ms.append(m["tactician_ms"])
        print(f"  run {i+1:2d}/{args.repeat}  {status:8s}  plan={m.get('plan_label'):<16} "
              f"total={m.get('total_ms')}ms  fallback={m.get('fallback')}")

    def pct(xs, p):
        if not xs:
            return 0
        xs = sorted(xs)
        return xs[min(len(xs) - 1, int(len(xs) * p / 100))]

    n = args.repeat
    print("\n=== BATCH SUMMARY ===")
    print(f"  scenario           : {args.scenario} (phase reported per run)")
    print(f"  runs               : {n}")
    print(f"  clean (no stage FAIL): {n - fails}/{n}")
    print(f"  tactician JSON ok  : {json_ok}/{n} ({100*json_ok//max(1,n)}%)")
    print(f"  harness fallbacks  : {fallbacks}/{n}")
    print(f"  plan distribution  : {plan_mix}")
    print(f"  total  p50/p95     : {pct(totals,50)}ms / {pct(totals,95)}ms")
    print(f"  strat  p50/p95     : {pct(strat_ms,50)}ms / {pct(strat_ms,95)}ms")
    print(f"  tact   p50/p95     : {pct(tact_ms,50)}ms / {pct(tact_ms,95)}ms")
    return 1 if fails else 0


# ── main ────────────────────────────────────────────────────────────
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenario", default="tier_choice",
                    help="Eval scenario name (default: tier_choice; use "
                         "solo_drop_orbit for an orbit-phase turn).")
    ap.add_argument("--seat", default=None, help="Seat to probe (default: scenario player).")
    ap.add_argument("--repeat", type=int, default=1,
                    help="Batch mode: run N times and print aggregate metrics.")
    ap.add_argument("--orbit", action="store_true",
                    help="Force the fixture into ORBIT phase to exercise the "
                         "orbit path (no eval scenario ships an orbit turn).")
    ap.add_argument("--show-prompts", action="store_true",
                    help="Print the strategist note + tactician response.")
    args = ap.parse_args(argv)

    os.environ.setdefault("SOC_AGENT_WORLD_VIEW", "grid")

    if args.repeat > 1:
        return run_batch(args)

    print("=" * 68)
    print(f"  PILOT_V4 PROBE — scenario={args.scenario} seat={args.seat or '(default)'}"
          f"{' [FORCED ORBIT]' if args.orbit else ''}")
    print(f"  backend={os.environ.get('SOC_BACKEND', 'memory')}")
    print("=" * 68)
    stages, metrics = probe_once(scenario_name=args.scenario, seat_arg=args.seat,
                                 show_prompts=args.show_prompts, verbose=True,
                                 force_orbit=args.orbit)
    print(f"\n  phase={metrics.get('phase')} day={metrics.get('day')} "
          f"plan={metrics.get('plan_label')} total={metrics.get('total_ms')}ms\n")
    for s in stages:
        print(s.render())

    first_fail = min((s.num for s in stages if s.verdict == FAIL), default=-1)
    print("\n" + "-" * 68)
    if first_fail < 0:
        warns = [s.num for s in stages if s.verdict == WARN]
        print(f"  RESULT: all stages PASS" + (f" (warnings at S{warns})" if warns else ""))
        return 0
    print(f"  RESULT: first failure at STAGE {first_fail} — fix that before trusting the agent")
    return first_fail if first_fail > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
