"""tabula_v9 — night entry point (true fork of v8).

v9 is the COMPREHENSION release on the current stack (haiku, inference API).
It owns its turn loop and FEEDING layer (the digest-aware prompt in
:mod:`.prompt`, the rewritten doctrine in :mod:`.doctrine`), while reusing
v7's proven COMPUTATION layer (hint compilers, sanitizer, wishlist, memory,
weapon inference, recorder) by import.

What v9 changes vs v8:
  * The prompt now renders a two-way WHAT HAPPENED digest (attacks TO you and
    denials BY you, with attribution + consequence), surfaces EMP scars as a
    board hazard, and FORCES a consequence acknowledgment in REFLECT.
  * The doctrine carries the two-case WEAPON-FREE redsign poker, branching on
    the engine-truth ``redsign.mine`` flag.

The CONTAINED TWO-CALL SPLIT (reasoning-first thinker -> moves-first mover,
both on the inference API) is native and on by default; ``TABULA_V9_SINGLE=1``
runs mover-only for an A/B.

Flow per turn mirrors v8: close prior-day memory, snapshot, read memory, build
the v9 prompt, (thinker ->) mover, parse/sanitize, submit, persist, return the
dispatcher envelope (with per-sub-agent audit rows).
"""

from __future__ import annotations

import hashlib
import os
import random
import time
from typing import Any, Dict, List, Mapping

from sea_of_colours.orchestrator_2.cortex_invoker import CortexAgentInvoker
from sea_of_colours.orchestrator_2.cortex_chat import CortexChatInvoker
from sea_of_colours.orchestrator_2.harnesses.tabula_v7 import (
    chat_schema,
    directive as directive_mod,
    harness as v7h,
    heuristic_chains,
    memory,
    move_sanitizer,
    opponent_weapons,
    orbit_stub,
    probe_hints as probe_hints_mod,
    recorder,
)
from sea_of_colours.orchestrator_2.harnesses.tabula_v7 import (
    orbit_wishlist as wishlist_mod,
)
from sea_of_colours.orchestrator_2.harnesses.tabula_v9 import prompt as prompt_mod
from sea_of_colours.orchestrator_2.harnesses.tabula_v9 import (
    agency as agency_mod,
    chain_filter,
    chat_schema as v9_chat_schema,
    hint_dispersion as hint_dispersion_mod,
    seam_control as seam_control_mod,
)

# ── Agent identity ─────────────────────────────────────────────────────
INNER_AGENT_LABEL = "TABULA_V9"
THINKER_AGENT_LABEL = "TABULA_V9_THINKER"
# The rare JSON-finisher fallback reuses v7's dedicated finisher spec.
FINISHER_AGENT_NAME = v7h.FINISHER_AGENT_NAME

# Budgets carried over from v7/v8's contained-split config (measured on seed 42).
_THINKER_CHAT_MODEL = v7h._THINKER_CHAT_MODEL
_THINKER_CHAT_MAX_TOKENS = v7h._THINKER_CHAT_MAX_TOKENS
_THINKER_CHAT_WALLCLOCK_S = v7h._THINKER_CHAT_WALLCLOCK_S
# CONTAINED TWO-STAGE thinker budgets (measured on the seed-69 day-2 replay):
#   THINK — bounded prose reasoning, own hard budget (~1.5k chars observed, well
#           under this cap; the cap is the leash so it can never run away).
#   PLAN  — decision-only JSON, tiny dedicated budget so it ALWAYS lands.
_THINK_CHAT_MAX_TOKENS = 1400
_THINK_CHAT_WALLCLOCK_S = 40
_PLAN_CHAT_MAX_TOKENS = 800
_PLAN_CHAT_WALLCLOCK_S = 30
_MOVER_CHAT_MODEL = v7h._MOVER_CHAT_MODEL
# A4 (mover latency). v9's mover is MOVES-ONLY (chat_schema._V9_MOVES_SCHEMA) —
# the thinker already reflected/planned/reasoned, so the mover no longer writes
# any prose. A full night is ~20 short move objects (~600-900 tokens of JSON),
# so we halve the v7 budget and tighten the wall clock. This is the fix for the
# 25-99s mover turns (it was spending the budget on reflection/rationale prose).
_MOVER_CHAT_MAX_TOKENS = 1_100
_WALLCLOCK_S = 40
_CONTINUATION_WALLCLOCK_S = v7h._CONTINUATION_WALLCLOCK_S
_CONTINUATION_RESPONSE_CAP = v7h._CONTINUATION_RESPONSE_CAP
_MIN_FINISHER_RED_VALUE = v7h._MIN_FINISHER_RED_VALUE
_MAX_MOVES = v7h._MAX_MOVES


def _split_on() -> bool:
    """v9 runs the contained split by default; ``TABULA_V9_SINGLE=1`` disables."""
    return os.environ.get("TABULA_V9_SINGLE", "0").strip().lower() not in (
        "1", "true", "yes",
    )


def _thinker_plan_summary(directive: Any) -> str:
    """One-line plan_this_turn sourced from the thinker directive (A4).

    The moves-only mover no longer authors ``plan_this_turn``; the thinker's
    posture + selected option IDs already describe the night, so summarise them
    for the memory replay. Empty when there is no directive.
    """
    if directive is None:
        return ""
    posture = str(getattr(directive, "posture", "") or "")
    plan = [str(p) for p in (getattr(directive, "plan", None) or [])]
    if plan:
        return f"{posture}: {', '.join(plan[:6])}".strip(": ").strip()
    return posture


def _turn_rng(session_id: str, player: str, day: int) -> "random.Random":
    """A reproducible per-(session, seat, night) RNG.

    Uses a STABLE hash (sha256, not Python's per-process ``hash``) so the same
    inputs always yield the same stream — the whole point is that a season is
    replayable and auditable, not that it is unpredictable. Because the seat id
    is part of the seed, p1/p2/p3 get DIFFERENT streams on the same board, which
    is what breaks the symmetric-determinism pile-ups (Phase 1).
    """
    digest = hashlib.sha256(
        f"{session_id}|{player}|{int(day)}".encode("utf-8")
    ).hexdigest()
    return random.Random(int(digest[:16], 16))


def clear_snapshots() -> None:
    """Test helper — v9 shares v7's process-local snapshot cache."""
    v7h.clear_snapshots()


# ── Public entry point ─────────────────────────────────────────────────
def run(
    *, store: Any, session_id: str, player: str, view: Mapping[str, Any],
) -> Dict[str, Any]:
    """Drive one v9 arena turn. Returns the dispatcher audit envelope."""
    started = time.time()
    phase = str(
        view.get("phase")
        or (view.get("agent_view", {}).get("meta", {}) or {}).get("phase")
        or ""
    ).lower()
    if phase == "orbit":
        return orbit_stub.submit_orbit(store, session_id, player, view)

    agent_view = view.get("agent_view") or {}
    meta = agent_view.get("meta") or {}
    hud = agent_view.get("hud") or {}
    day = int(meta.get("day") or hud.get("day") or 0)
    day_cap = int(hud.get("season_day_cap") or 7)
    scores = hud.get("scores") or {}
    vault_score = int(scores.get(player) or 0)
    season_name = str(hud.get("season_name") or "")

    # 1. Close prior day's memory with the engine-resolved outcome.
    snap = v7h._SNAPSHOTS.get(v7h._snap_key(session_id, player), {})
    recorder.close_prior_day_if_needed(
        session_id, player,
        current_day=day,
        turn_start_score_by_day=snap.get("score_by_day", {}),
        turn_start_probes_by_day=snap.get("probes_by_day", {}),
        moves_submitted_by_day=snap.get("moves_by_day", {}),
        store=store,
        season_name=season_name,
    )

    # 2. Snapshot this turn's start state for next turn's reflection.
    v7h._capture_snapshot(session_id, player, day, agent_view)

    # 3. Read memory + the prior-day entry that grounds the REFLECT block.
    prior_entries = memory.read_recent(session_id, player, limit=3, store=store)
    memory_replay = memory.format_replay(prior_entries)
    prior_day_entry = next(
        (e for e in reversed(prior_entries) if int(e.get("day") or 0) == day - 1),
        None,
    )

    # 4. Precompute the hint menu (v7 compilers, now with v9 seeded variability:
    #    a per-(session, seat, night) rng breaks near-tie symmetry so seats fan
    #    out instead of stacking the single deterministic best).
    turn_rng = _turn_rng(session_id, player, day)
    # A8: over-generate then dedupe by BODY overlap + a vein-value floor so two
    # harvesters are never handed near-identical chains on one small cluster
    # (the day-5 double-dig) and trace-only junk chains are dropped.
    chain_hints = chain_filter.dedupe_and_floor(
        heuristic_chains.top_chain_hints(agent_view, max_chains=5),
    )[:3]
    probe_hints = probe_hints_mod.top_probe_hints(
        agent_view,
        max_hints=3,
        historical_probe_positions=v7h._historical_probe_targets(
            session_id, player, store=store,
        ),
        rng=turn_rng,
    )
    hot_drop_hints = probe_hints_mod.top_hot_drop_hints(
        agent_view, max_hints=2, rng=turn_rng,
    )
    # Ownership tagging + fallback dispersion (Fix A). Seat-asymmetry is now
    # primarily provided by WS1 (the seeded near-tie shuffle above) and the seam
    # PATTERNS below; hint_dispersion is retained only to stamp the engine-truth
    # ``mine`` flag on each hot drop (which seam_control + the tactics block
    # read) and as the non-agency fallback offset.
    hot_drop_hints = hint_dispersion_mod.personalize_hot_drops(
        hot_drop_hints, agent_view, player,
    )
    supersede_hints = (
        probe_hints_mod.top_supersede_hints(agent_view, max_hints=4)
        if int(day) >= int(day_cap) else []
    )

    # v9 agency: compile the redsign seam PATTERN menu + the ID'd option
    # registry the thinker selects from (curate -> select -> package).
    seam_patterns = seam_control_mod.build_seam_menu(agent_view, hot_drop_hints)
    option_registry = agency_mod.build_registry(
        agent_view=agent_view,
        seam_patterns=seam_patterns,
        hot_drop_hints=hot_drop_hints,
        probe_hints=probe_hints,
        chain_hints=chain_hints,
        supersede_hints=supersede_hints,
    )
    option_menu_block = agency_mod.format_menu_block(option_registry)
    player_count = len(scores) if isinstance(scores, dict) and scores else 0
    weapon_estimates = opponent_weapons.update_estimates(
        session_id, player, agent_view,
    )
    wishlist = wishlist_mod.compute_wishlist(
        agent_view, day=day, opponent_weapon_estimates=weapon_estimates,
    )
    want_blue = any(e.tag == "grab_blue" for e in wishlist.entries)
    blue_hints = (
        heuristic_chains.top_blue_chain_hints(agent_view, max_chains=2)
        if want_blue else []
    )

    prompt_kwargs: Dict[str, Any] = dict(
        agent_view=agent_view,
        day=day, day_cap=day_cap, vault_score=vault_score,
        memory_replay=memory_replay,
        chain_hints=chain_hints,
        probe_hints=probe_hints,
        hot_drop_hints=hot_drop_hints,
        blue_hints=blue_hints,
        supersede_hints=supersede_hints,
        wishlist=wishlist,
        opponent_weapon_estimates=weapon_estimates,
        prior_day_entry=prior_day_entry,
    )

    # 4b. CONTAINED THINKER (reasoning-first, inference API, hard cap).
    directive_block = ""
    thinker_used = False
    thinker_directive = None
    thinker_reasoning = ""
    thinker_plan_reasoning = ""
    thinker_response_chars = 0
    thinker_ms = 0
    thinker_prompt = ""
    thinker_retried = False
    selected_options: List[Any] = []
    plan_prompt = ""
    if _split_on():
        thinker_used = True
        # ── STAGE 1 — THINK (bounded prose, its OWN hard budget) ───────────
        # The think call is ALLOWED to spend its whole budget reasoning; there
        # is no decision crammed into it, so nothing to starve. Capped tokens =
        # the leash that stops the ~9k-char ramble that used to eat the budget
        # and drop the decision entirely.
        thinker_prompt = prompt_mod.build_prompt(
            mode="think",
            option_menu_block=option_menu_block,
            player_count=player_count,
            **prompt_kwargs,
        )
        thinker_started = time.time()
        think_invoker = CortexChatInvoker(
            model=_THINKER_CHAT_MODEL,
            response_format=None,
            max_completion_tokens=_THINK_CHAT_MAX_TOKENS,
        )
        think_result = think_invoker.invoke(
            thinker_prompt, wallclock_cap_s=_THINK_CHAT_WALLCLOCK_S,
        )
        thinker_reasoning = str(think_result.get("response") or "").strip()
        think_ms = int((time.time() - thinker_started) * 1000)

        # ── STAGE 2 — PLAN (decision-only JSON, own budget, conditioned on the
        # bounded think) — this ALWAYS lands: the payload is tiny and the model
        # already reasoned, so it just commits. I1 retry guards a transient
        # empty body.
        plan_prompt = prompt_mod.build_prompt(
            mode="plan",
            option_menu_block=option_menu_block,
            player_count=player_count,
            think_analysis=thinker_reasoning,
            **prompt_kwargs,
        )
        plan_invoker = CortexChatInvoker(
            model=_THINKER_CHAT_MODEL,
            response_format=chat_schema.DECISION_RESPONSE_FORMAT,
            max_completion_tokens=_PLAN_CHAT_MAX_TOKENS,
        )
        plan_started = time.time()
        raw_directive = None
        plan_text = ""
        thinker_plan_reasoning = ""
        for _attempt in range(2):
            plan_result = plan_invoker.invoke(
                plan_prompt, wallclock_cap_s=_PLAN_CHAT_WALLCLOCK_S,
            )
            plan_text = str(plan_result.get("response") or "")
            raw_directive, _plan_reasoning = directive_mod.parse_directive_json(
                plan_text,
            )
            if _plan_reasoning:
                thinker_plan_reasoning = str(_plan_reasoning)
            if raw_directive is not None:
                break
            if _attempt == 0:
                thinker_retried = True
        plan_ms = int((time.time() - plan_started) * 1000)
        thinker_ms = think_ms + plan_ms
        # The bounded THINK prose is the audited/recoverable reasoning (it names
        # the patterns); ``thinker_response_chars`` tracks the PLAN payload.
        thinker_response_chars = len(plan_text)
        thinker_directive = directive_mod.sanitize_directive(
            raw_directive, agent_view,
        )
        # PLAN-HANDOFF HARDENING (I3/F4/O8): the thinker often NAMES the pattern
        # in prose (``BLIND_GRAB``, ``SS1``) but leaves the structured ``plan``
        # empty, so the decisive geometry (incl. the finder-probe supersede)
        # never reaches the mover. When the JSON plan is empty, recover the
        # ordered IDs from the chain-of-thought. Additive only — a populated
        # plan is left untouched.
        #
        # Extended: also fire when parsing produced NO directive at all (a
        # clipped/rambled thinker). Rather than let the mover freelance with no
        # recipe, build a MINIMAL directive from the prose-recovered plan so the
        # agency layer still resolves an EXECUTE-THESE block. This is the gap
        # that let a redsign night ship the wrong hot-drop: the thinker had
        # priced the pure in prose but the empty structured plan handed the
        # mover nothing, so it copied a stale offset combo.
        if thinker_directive is None and thinker_reasoning:
            recovered = agency_mod.recover_plan_from_prose(
                thinker_reasoning, option_registry,
            )
            if recovered:
                thinker_directive = directive_mod.sanitize_directive(
                    directive_mod.Directive(
                        posture=directive_mod._DEFAULT_POSTURE,
                        plan=recovered,
                    ),
                    agent_view,
                )
        if (
            thinker_directive is not None
            and not thinker_directive.plan
            and thinker_reasoning
        ):
            recovered = agency_mod.recover_plan_from_prose(
                thinker_reasoning, option_registry,
            )
            if recovered:
                thinker_directive.plan = recovered
        # AGENCY RESOLVE: expand the thinker's selected option/pattern IDs to
        # their pre-built geometry and hand the mover an EXECUTE-THESE recipe.
        # Falls back to the classic strategist-directive block when the thinker
        # selected nothing valid (off-seam nights / v7-style guidance).
        selected_options = (
            agency_mod.resolve_plan(thinker_directive.plan, option_registry)
            if thinker_directive else []
        )
        execute_block = agency_mod.format_execute_block(selected_options)
        directive_block = (
            execute_block
            or directive_mod.format_directive_block(thinker_directive)
        )

    prompt_text = prompt_mod.build_prompt(
        mode="mover", strategist_directive_block=directive_block, **prompt_kwargs,
    )

    # 5. CONTAINED MOVER (moves-first, inference API, schema-guaranteed).
    invoker = CortexChatInvoker(
        model=_MOVER_CHAT_MODEL,
        response_format=v9_chat_schema.MOVES_RESPONSE_FORMAT,
        max_completion_tokens=_MOVER_CHAT_MAX_TOKENS,
    )
    result = invoker.invoke(prompt_text, wallclock_cap_s=_WALLCLOCK_S)
    response_text = str(result.get("response") or "")

    # 6. Parse JSON; on failure, finisher retry then heuristic net.
    decision, decision_error = v7h._extract_decision_json(response_text)
    fallback_used = False
    fallback_reason = ""
    continuation_used = False
    response_text_continuation = ""
    if decision_error or not decision.get("moves"):
        if response_text.strip():
            continuation_used = True
            cont_prompt = v7h._continuation_prompt(
                response_text,
                day=day, day_cap=day_cap,
                orbit_harvesters=probe_hints_mod._orbit_harvester_ids(agent_view),
                chain_hints=chain_hints,
                supersede_hints=supersede_hints,
            )
            finisher_invoker = CortexAgentInvoker(agent_name=FINISHER_AGENT_NAME)
            cont_result = finisher_invoker.invoke(
                cont_prompt,
                wallclock_cap_s=_CONTINUATION_WALLCLOCK_S,
                response_cap_bytes=_CONTINUATION_RESPONSE_CAP,
            )
            cont_text = str(cont_result.get("response") or "")
            response_text_continuation = cont_text
            cont_decision, cont_err = v7h._extract_decision_json(cont_text)
            if not cont_err and cont_decision.get("moves"):
                decision = cont_decision
            else:
                fallback_used = True
                fallback_reason = f"finisher_failed: {cont_err or 'missing moves'}"
                decision = v7h._heuristic_fallback_decision(chain_hints, day)
        else:
            fallback_used = True
            fallback_reason = (
                f"parse: {decision_error}" if decision_error
                else "parse: missing 'moves' key"
            )
            decision = v7h._heuristic_fallback_decision(chain_hints, day)

    proposed = list(decision.get("moves") or [])

    # 7. Mechanical move sanitizer (skip the already-legal heuristic plan).
    sanitizer_log: List[str] = []
    if not fallback_used and proposed:
        is_final_night = int(day) >= int(day_cap)
        enemy_probe_cells = {
            (int(h["probe_at"][0]), int(h["probe_at"][1]))
            for h in supersede_hints
            if isinstance(h.get("probe_at"), (list, tuple))
            and len(h["probe_at"]) == 2
        }
        proposed, sanitizer_log = move_sanitizer.sanitize_moves(
            proposed,
            agent_view,
            chain_hints=chain_hints,
            is_final_night=is_final_night,
            enemy_probe_cells=enemy_probe_cells,
        )
        if continuation_used and chain_hints:
            if v7h._plan_red_value(proposed, agent_view) <= _MIN_FINISHER_RED_VALUE:
                fallback_used = True
                fallback_reason = "finisher_low_value: swapped to heuristic chain"
                decision = v7h._heuristic_fallback_decision(chain_hints, day)
                proposed = list(decision.get("moves") or [])
                sanitizer_log.append(
                    "swapped finisher plan -> heuristic (finisher banked ~no "
                    "reachable RED while chains were available)"
                )

    # 8. Cap + submit.
    final_moves = proposed[:_MAX_MOVES]
    v7h._record_moves(session_id, player, day, final_moves)

    from sea_of_colours.snowpark import engine as soc_engine
    submit_result = soc_engine.submit_policy(store, session_id, player, final_moves)

    # 9. Persist this turn's memory entry.
    #
    # A4: the v9 mover is MOVES-ONLY now, so it emits no plan/rationale/memory
    # prose. Source the turn narrative from the THINKER (which already reflected
    # and reasoned) instead, falling back to whatever the mover happened to emit
    # (belt-and-braces for the non-split legacy path). This keeps the memory
    # replay + audit rich WITHOUT paying the mover's prose-generation latency.
    plan_this_turn = str(decision.get("plan_this_turn") or "")
    rationale = str(decision.get("rationale") or "")
    predicted_outcome = decision.get("predicted_outcome") or {}
    memory_note = str(decision.get("memory_note") or decision.get("note") or "")
    if thinker_used:
        plan_this_turn = plan_this_turn or _thinker_plan_summary(thinker_directive)
        rationale = rationale or thinker_plan_reasoning[:400]
        memory_note = memory_note or thinker_reasoning[:200]
    entry = memory.new_entry(
        day,
        plan_this_turn=plan_this_turn,
        rationale=rationale,
        predicted_outcome=predicted_outcome,
        moves_summary=v7h._summarise_moves(final_moves),
        memory_note=memory_note,
    )
    memory.save_entry(session_id, player, entry, store=store, season_name=season_name)

    ms_elapsed = int((time.time() - started) * 1000)
    return {
        "ok": True,
        "agent_id": INNER_AGENT_LABEL,
        "runtime": "harness_in_process",
        "rationale": (
            f"[plan={plan_this_turn[:80]}] "
            f"[predicted={v7h._pred_label(decision)}] "
            f"[fallback={fallback_used}"
            + (f":{fallback_reason[:120]}" if fallback_used else "")
            + "]"
            + (" [continuation=recovered]"
               if (continuation_used and not fallback_used) else "")
            + (f" [sanitized={len(sanitizer_log)}]" if sanitizer_log else "")
            + (f" [thinker={thinker_directive.posture}"
               + (";chaff" if thinker_directive.chaff_react else "") + "]"
               if thinker_directive
               else (" [thinker=none]" if thinker_used else ""))
            + f" moves={len(final_moves)}"
        ),
        "moves": final_moves,
        "submitted_policy": True,
        "wallclock_capped": bool(result.get("wallclock_capped")),
        "ms_elapsed": ms_elapsed,
        "response": response_text,
        "extras": {
            "inner_agent": INNER_AGENT_LABEL,
            "plan_label": plan_this_turn[:80],
            "predicted_outcome": predicted_outcome or None,
            "reflection_on_last_night": decision.get("reflection_on_last_night"),
            "materialized_count": len(final_moves),
            "fallback_used": fallback_used,
            "fallback_reason": fallback_reason,
            "sanitizer_changes": sanitizer_log,
            "continuation_used": continuation_used,
            "continuation_response_chars": len(response_text_continuation),
            "thinker_used": thinker_used,
            "thinker_directive": (
                {
                    "posture": thinker_directive.posture,
                    "targets": thinker_directive.targets,
                    "chaff_react": thinker_directive.chaff_react,
                    "avoid": thinker_directive.avoid,
                    "note": thinker_directive.note,
                    "plan": thinker_directive.plan,
                    "situational": thinker_directive.situational,
                }
                if thinker_directive else None
            ),
            "option_menu_ids": list(option_registry.keys()),
            "selected_option_ids": [o.option_id for o in selected_options],
            "seam_pattern_ids": [p.pattern_id for p in seam_patterns],
            "thinker_response_chars": thinker_response_chars,
            "thinker_api": "chat" if thinker_used else "",
            "thinker_reasoning": thinker_reasoning,
            "thinker_ms": thinker_ms,
            "thinker_retried": thinker_retried,
            "sub_invocations": (
                [
                    {
                        "label": "TABULA_V9_THINK",
                        "kind": "think",
                        "api": "chat",
                        "response_text": thinker_reasoning,
                        "rationale": "[think pass — bounded reasoning]",
                        "ms_elapsed": think_ms,
                        "prompt_excerpt": thinker_prompt[:32_000],
                    },
                    {
                        "label": THINKER_AGENT_LABEL,
                        "kind": "plan",
                        "api": "chat",
                        "response_text": plan_text,
                        "rationale": (
                            f"[posture={thinker_directive.posture}"
                            + (";chaff" if thinker_directive.chaff_react else "")
                            + f"] plan={[o.option_id for o in selected_options]}"
                            + f" targets={thinker_directive.targets}"
                            if thinker_directive else "[plan=no directive]"
                        ),
                        "ms_elapsed": plan_ms,
                        "prompt_excerpt": plan_prompt[:32_000],
                    },
                ]
                if thinker_used else []
            ),
            "mover_api": "chat",
            "mover_capped": bool(result.get("capped")),
            "prompt_chars": len(prompt_text),
            "response_chars": len(response_text),
            "submit_result": submit_result,
            "prompt_excerpt": prompt_text[:32_000],
        },
    }
