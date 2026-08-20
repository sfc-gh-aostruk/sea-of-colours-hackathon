"""Unit tests for the tabula_v10 comprehension uplift.

Covers the fork's new levers:
  * the ATTRIBUTED EVENT channels added to ``view._last_night_recap``
    (incoming_attacks / my_denials / emp_scars), additive + fog-safe;
  * the digest narration (attacker + consequence, both directions);
  * the prompt render — two-way WHAT HAPPENED in SECTION 3, EMP scars in
    SECTION 2, and a REFLECT block that FORCES a consequence acknowledgment
    for probe/EMP/chaff loss (not just collisions);
  * the two-case redsign-poker doctrine + the engine-truth ``mine`` ownership
    pointer (CASE 1 vs CASE 2).
"""

from __future__ import annotations

from types import SimpleNamespace

from sea_of_colours.orchestrator_2.harnesses.tabula_v10 import (
    digest,
    doctrine,
    prompt as prompt_mod,
)
from sea_of_colours.snowpark import view as view_mod


def _view(width=20, height=20, **extra):
    base = {
        "world": {"width": width, "height": height, "live": []},
        "entities": {"mine": []},
        "my_assets": [],
        "red_tiles": [],
    }
    base.update(extra)
    return base


def _kwargs(**over):
    base = dict(
        agent_view=_view(),
        day=3, day_cap=7, vault_score=100,
        memory_replay="(none)\n",
        chain_hints=[],
    )
    base.update(over)
    return base


def test_reflect_anchor_fires_on_banked_parcels():
    """A harvested cell shows GREEN today; the audit caught the seat reading that
    current state and inverting a SUCCESS into a 'green crash'. The anchor pins
    the reflection to my_parcels_banked so it stops confabulating a crash."""
    av = _view(last_night={
        "day_ended": 2,
        "my_parcels_banked": [
            {"from": [15, 4], "tile": "RED", "purity": 41, "tier": "trace"},
        ],
    })
    text = prompt_mod.build_prompt(mode="thinker", **_kwargs(agent_view=av))
    assert "ANCHOR TO THE RECORD" in text
    assert "(15,4)" in text
    assert "green crash" in text.lower() or "green crash" in text


def test_reflect_anchor_absent_without_banked_parcels():
    av = _view(last_night={"day_ended": 2, "my_parcels_banked": []})
    text = prompt_mod.build_prompt(mode="thinker", **_kwargs(agent_view=av))
    assert "ANCHOR TO THE RECORD" not in text


# ── A7: exact alive-harvester count as a hard fact ────────────────────────
def _fleet_probe_view(*, harvesters=2, probe_stock=3, **extra):
    av = _view(**extra)
    av["entities"] = {"mine": [
        {"id": f"harvester_p1_{i}", "type": "harvester", "pos": [1 + i, 1]}
        for i in range(harvesters)
    ]}
    av["orbit"] = {"probe_stock": probe_stock}
    return av


def test_fleet_fact_states_exact_alive_count():
    av = _fleet_probe_view(harvesters=2)
    text = prompt_mod.build_prompt(mode="thinker", **_kwargs(agent_view=av))
    assert "you have 2 harvester(s) ALIVE" in text
    assert "no phantom extra unit" in text


# ── A6: FINAL NIGHT doctrine gated to the actual final night ──────────────
def test_probe_stock_priming_non_final_night_disclaims_finality():
    av = _fleet_probe_view(probe_stock=3)
    text = prompt_mod.build_prompt(
        mode="thinker", **_kwargs(agent_view=av, day=3, day_cap=7),
    )
    assert "NOT the final night" in text
    # the final-night-only supersede weaponisation must NOT be offered early.
    assert "it is the final night" not in text


def test_probe_stock_priming_final_night_offers_supersede():
    av = _fleet_probe_view(probe_stock=3)
    text = prompt_mod.build_prompt(
        mode="thinker", **_kwargs(agent_view=av, day=7, day_cap=7),
    )
    assert "it is the final night" in text
    assert "NOT the final night" not in text


# ── view recap: attributed channels ────────────────────────────────────
def _recap_session(*, day, log=None, combat=None, emp_marks=None):
    """Minimal duck-typed GameSession for _last_night_recap."""
    return SimpleNamespace(
        day=day,
        asset_records={},
        harvest_log={},
        collision_marks={},
        combat_events_by_day={str(day - 1): list(combat or [])},
        log=list(log or []),
        emp_marks=dict(emp_marks or {}),
    )


def test_recap_incoming_probe_supersede_attributed_to_me():
    sess = _recap_session(day=4, log=[{
        "day": 3, "kind": "probe_superseded",
        "data": {
            "at": [4, 7], "new_owner": "p2",
            "destroyed_ids": ["probe_p1_8"],
            "owners": {"probe_p1_8": "p1"},
        },
    }])
    recap = view_mod._last_night_recap(sess, "p1", [])
    inc = recap["incoming_attacks"]
    assert len(inc) == 1
    assert inc[0]["type"] == "probe_superseded"
    assert inc[0]["by"] == ["p2"]
    assert inc[0]["lost_ids"] == ["probe_p1_8"]
    assert "vision" in inc[0]["consequence"]
    assert recap["my_denials"] == []


def test_recap_supersede_by_me_is_a_denial_not_an_attack():
    sess = _recap_session(day=4, log=[{
        "day": 3, "kind": "probe_superseded",
        "data": {
            "at": [4, 7], "new_owner": "p1",
            "destroyed_ids": ["probe_p2_3"],
            "owners": {"probe_p2_3": "p2"},
        },
    }])
    recap = view_mod._last_night_recap(sess, "p1", [])
    assert recap["incoming_attacks"] == []
    den = recap["my_denials"]
    assert len(den) == 1 and den[0]["against"] == ["p2"] and den[0]["at"] == [4, 7]


def test_recap_incoming_emp_and_chaff_from_combat_feed():
    sess = _recap_session(day=4, combat=[
        {"type": "emp_hit", "victim": "p1", "unit": "harvester_p1_2",
         "by": ["p3"], "hours": [9, 10]},
        {"type": "chaff_jam", "victim": "p1", "by": ["p2"], "units": ["h1"],
         "hours": [6]},
        {"type": "emp_hit", "victim": "p2", "by": ["p1"], "hours": [3]},  # not mine
    ])
    recap = view_mod._last_night_recap(sess, "p1", [])
    types = {a["type"] for a in recap["incoming_attacks"]}
    assert types == {"emp_hit", "chaff_jam"}  # p2's emp_hit is filtered out


def test_recap_emp_scars_channel():
    sess = _recap_session(day=4, emp_marks={
        "12:12": {"owners": ["p2"], "hours": [9, 10, 11], "day": 3},
    })
    recap = view_mod._last_night_recap(sess, "p1", [])
    scars = recap["emp_scars"]
    assert len(scars) == 1 and scars[0]["at"] == [12, 12]
    assert scars[0]["hours"] == [9, 10, 11]


def test_recap_channels_are_additive_and_present_when_empty():
    sess = _recap_session(day=4)
    recap = view_mod._last_night_recap(sess, "p1", [])
    for key in ("incoming_attacks", "my_denials", "emp_scars"):
        assert recap[key] == []


# ── digest narration ───────────────────────────────────────────────────
def test_digest_narrates_incoming_with_attacker_and_consequence():
    av = _view(last_night={
        "incoming_attacks": [{
            "type": "probe_superseded", "by": ["p2"], "at": [4, 7],
            "lost_ids": ["probe_p1_8"],
            "consequence": "you LOST that disk's vision from the next hour on",
        }],
    })
    lines = digest.narrate_incoming(av)
    assert len(lines) == 1
    assert "p2" in lines[0] and "probe_p1_8" in lines[0]
    assert "LOST that disk" in lines[0]


def test_digest_hours_compress_to_ranges():
    av = _view(last_night={
        "incoming_attacks": [{
            "type": "emp_hit", "by": ["p3"], "unit": "harvester_p1_2",
            "hours": [9, 10, 11, 14], "consequence": "harvester DISABLED",
        }],
    })
    line = digest.narrate_incoming(av)[0]
    assert "9-11, 14" in line


def test_digest_block_two_way_and_skips_when_quiet():
    assert digest.format_event_digest_block(_view(last_night={})) == ""
    av = _view(last_night={
        "incoming_attacks": [{"type": "chaff_jam", "by": ["p2"], "hours": [6],
                              "consequence": "slots CANCELLED"}],
        "my_denials": [{"type": "probe_superseded", "against": ["p3"],
                        "at": [5, 5], "consequence": "you BLINDED them"}],
    })
    block = digest.format_event_digest_block(av)
    assert "TO YOU" in block and "BY YOU" in block


def test_digest_scars_block():
    av = _view(last_night={"emp_scars": [{"at": [12, 12], "hours": [9, 10]}]})
    block = digest.format_emp_scars_block(av)
    assert "EMP SCARS" in block and "(12,12)" in block


# ── prompt render ──────────────────────────────────────────────────────
def test_event_digest_rendered_in_section3():
    av = _view(last_night={
        "incoming_attacks": [{"type": "probe_superseded", "by": ["p2"],
                              "at": [4, 7], "lost_ids": ["probe_p1_8"],
                              "consequence": "you LOST that disk's vision"}],
    })
    text = prompt_mod.build_prompt(mode="mover", **_kwargs(agent_view=av))
    i3 = text.find("SECTION 3 - WHAT HAPPENED")
    iwh = text.find("WHAT HAPPENED LAST NIGHT (cause -> effect)")
    assert i3 != -1 and iwh > i3


def test_emp_scars_rendered_in_section2():
    av = _view(last_night={"emp_scars": [{"at": [12, 12], "hours": [9, 10]}]})
    text = prompt_mod.build_prompt(mode="mover", **_kwargs(agent_view=av))
    i2 = text.find("SECTION 2 - THE BOARD NOW")
    i3 = text.find("SECTION 3 - WHAT HAPPENED")
    iscar = text.find("EMP SCARS")
    assert i2 < iscar < i3


def test_reflect_forces_consequence_for_incoming_attack():
    av = _view(last_night={
        "incoming_attacks": [{"type": "emp_hit", "by": ["p3"], "hours": [9],
                              "consequence": "harvester DISABLED in those hours"}],
    })
    block = prompt_mod.format_reflect_block(av, None, day=4)
    assert "LOSS TO ACKNOWLEDGE" in block
    assert "do not confabulate" in block


def test_comprehension_doctrine_rides_with_events():
    av = _view(last_night={
        "my_denials": [{"type": "probe_superseded", "against": ["p2"],
                        "at": [3, 3], "consequence": "blinded"}],
    })
    text = prompt_mod.build_prompt(mode="thinker", **_kwargs(agent_view=av))
    assert "UNDERSTAND LAST NIGHT BEFORE YOU MOVE" in text


def test_no_comprehension_doctrine_on_quiet_night():
    text = prompt_mod.build_prompt(mode="thinker", **_kwargs())
    assert "UNDERSTAND LAST NIGHT BEFORE YOU MOVE" not in text


# ── two-case redsign poker + ownership pointer ─────────────────────────
def test_redsign_poker_two_cases_present():
    av = _view(redsign=[{"center": [2, 13], "cells": [[2, 13, 1.0]], "mine": True}])
    text = prompt_mod.build_prompt(mode="thinker", **_kwargs(agent_view=av))
    assert "REDSIGN POKER" in text
    assert "CASE 1 — IT IS YOUR REDSIGN" in text
    assert "CASE 2 — IT IS NOT YOUR REDSIGN" in text


def test_ownership_pointer_case1_when_mine():
    av = _view(redsign=[{"center": [2, 13], "cells": [[2, 13, 1.0]], "mine": True}])
    text = prompt_mod.build_prompt(mode="thinker", **_kwargs(agent_view=av))
    assert "a live REDSIGN is YOURS -> play CASE 1" in text


def test_ownership_pointer_case2_when_not_mine():
    av = _view(redsign=[{"center": [2, 13], "cells": [[2, 13, 1.0]], "mine": False}])
    text = prompt_mod.build_prompt(mode="thinker", **_kwargs(agent_view=av))
    assert "NOT yours -> play CASE 2" in text


def test_doctrine_exports_two_case_book():
    assert "CASE 1" in doctrine.DOCTRINE_REDSIGN_POKER
    assert "CASE 2" in doctrine.DOCTRINE_REDSIGN_POKER
    assert "no weapons" in doctrine.DOCTRINE_REDSIGN_POKER.lower()


# ── mover remit: recipe suppresses re-targeting bait ───────────────────
def _fleet_view():
    """A view with 2 alive harvesters (so full-utilization would fire)."""
    av = _view()
    av["entities"] = {"mine": [
        {"type": "harvester", "id": "harvester_p1_1", "state": "orbit"},
        {"type": "harvester", "id": "harvester_p1_2", "state": "orbit"},
    ]}
    return av


_CHAIN_HINTS = [{"unit": "harvester_p1_1", "cells": [[5, 5], [5, 6]],
                 "tiers": ["vein", "vein"], "purities": [80, 70],
                 "length": 2, "drop_at": [5, 5]}]
_PROBE_HINTS = [{"at": [11, 13], "area_gain": 40, "edge_promise": 243,
                 "extends_from": "fog"}]


def test_mover_with_recipe_hides_target_menus_and_swaps_full_utilization():
    """The PACKAGER mover must lose the re-targeting bait (chain/probe/fog-echo
    menus) and the 'deploy every unit' doctrine when it holds the thinker's
    committed recipe — otherwise it re-plans (the Day-4 override)."""
    av = _fleet_view()
    recipe = ("EXECUTE THIS PLAN — priority order.\n"
              " 1. CH1: drop (5,5) then walk (5,6)  (unit a harvester)\n")
    common = dict(agent_view=av, chain_hints=_CHAIN_HINTS,
                  probe_hints=_PROBE_HINTS)
    with_recipe = prompt_mod.build_prompt(
        mode="mover", strategist_directive_block=recipe, **_kwargs(**common))
    no_recipe = prompt_mod.build_prompt(
        mode="mover", strategist_directive_block="", **_kwargs(**common))

    # Re-targeting menus present WITHOUT a recipe, hidden WITH one.
    for marker in ("HEURISTIC SUGGESTIONS", "PROBE PLACEMENT HINTS",
                   "FOG + ECHO"):
        assert marker in no_recipe, marker
        assert marker not in with_recipe, marker

    # Full-utilization doctrine swapped for the "package, don't add" note.
    assert "DEPLOY THE WHOLE FLEET" in no_recipe
    assert "DEPLOY THE WHOLE FLEET" not in with_recipe
    assert "FLEET ALREADY SIZED" in with_recipe
    # The committed recipe rides along as top-priority guidance.
    assert "EXECUTE THIS PLAN" in with_recipe


def test_thinker_keeps_target_menus_and_full_utilization():
    """The THINKER is the planner — it must still see the menus + fleet doctrine
    (only the mover-with-recipe is stripped)."""
    av = _fleet_view()
    text = prompt_mod.build_prompt(
        mode="thinker",
        **_kwargs(agent_view=av, chain_hints=_CHAIN_HINTS,
                  probe_hints=_PROBE_HINTS))
    assert "HEURISTIC SUGGESTIONS" in text
    assert "PROBE PLACEMENT HINTS" in text
    assert "DEPLOY THE WHOLE FLEET" in text
    assert "FLEET ALREADY SIZED" not in text


def test_thinker_gets_multiprobe_when_stock_high():
    """With spare probe stock the thinker is told to launch AND spread the spare
    probes (the fix for dogpiling every probe on one seam / leaving stock idle)."""
    av = _fleet_view()
    av["orbit"] = {"probe_stock": 4}
    text = prompt_mod.build_prompt(
        mode="thinker",
        **_kwargs(agent_view=av, chain_hints=_CHAIN_HINTS,
                  probe_hints=_PROBE_HINTS))
    assert "PROBE STOCK TONIGHT: 4" in text
    assert "SPREAD" in text and "DEPLOY EVERY SPARE PROBE" in text


def test_multiprobe_absent_when_stock_low():
    """A lean 1-probe night stays quiet — no multiprobe nag."""
    av = _fleet_view()
    av["orbit"] = {"probe_stock": 1}
    text = prompt_mod.build_prompt(
        mode="thinker",
        **_kwargs(agent_view=av, chain_hints=_CHAIN_HINTS,
                  probe_hints=_PROBE_HINTS))
    assert "PROBE STOCK TONIGHT" not in text
    assert "DEPLOY EVERY SPARE PROBE" not in text


def test_mover_with_recipe_gets_no_multiprobe_nag():
    """The PACKAGER mover must NOT be told to add probes (it re-plans then)."""
    av = _fleet_view()
    av["orbit"] = {"probe_stock": 4}
    recipe = "EXECUTE THIS PLAN — priority order.\n 1. CH1: drop (5,5)\n"
    text = prompt_mod.build_prompt(
        mode="mover", strategist_directive_block=recipe,
        **_kwargs(agent_view=av, chain_hints=_CHAIN_HINTS,
                  probe_hints=_PROBE_HINTS))
    assert "DEPLOY EVERY SPARE PROBE" not in text


# ── self-execution digest (PLAN vs CORRECTOR vs EXECUTED) ─────────────────
def test_self_exec_zero_night_names_nothing_executed():
    """The confabulation fix: a night where the corrector stripped an undroppable
    plan must be reported as EXECUTED NOTHING so the agent cannot narrate a phantom
    harvest (the day-4 '6 RED parcels' that never happened)."""
    prior = {
        "day": 3,
        "plan_ids": ["SMASH_GRAB", "SECURE_MASS"],
        "planned_cells": ["SMASH_GRAB->(31,18)", "SECURE_MASS->(31,17)"],
        "corrector_notes": [
            "dropped SMASH_GRAB: no live vision on (31,18) — removed",
            "dropped SECURE_MASS: no live vision on (31,17) — removed",
        ],
        "moves_executed": 0,
        "actual_banked": 0,
    }
    block = digest.format_self_execution_block(prior, _view(last_night={}))
    assert "PLAN vs CORRECTOR vs EXECUTED" in block
    assert "EXECUTED: NOTHING" in block
    assert "SMASH_GRAB->(31,18)" in block
    assert "THE CORRECTOR REWROTE YOUR PLAN" in block
    assert "reconcile" in block.lower()


def test_self_exec_banked_night_quotes_engine_cells():
    """A real harvest reports the engine's banked cells (quote THESE, not
    remembered ones) — grounds the agent's coordinate narration."""
    prior = {
        "day": 4, "plan_ids": ["SMASH_GRAB"],
        "planned_cells": ["SMASH_GRAB->(30,18)"],
        "corrector_notes": [], "moves_executed": 6, "actual_banked": 765,
    }
    av = _view(last_night={
        "my_parcels_banked": [
            {"from": [30, 18], "tile": "RED", "purity": 255},
            {"from": [31, 18], "tile": "RED", "purity": 200},
        ],
    })
    block = digest.format_self_execution_block(prior, av)
    assert "EXECUTED & BANKED" in block
    assert "(30,18)" in block and "(31,18)" in block
    assert "NET TO VAULT: 765" in block


def test_self_exec_absent_without_prior_entry():
    assert digest.format_self_execution_block(None, _view()) == ""
    # old-shape entry with none of the stamped fields is also skipped
    assert digest.format_self_execution_block({"day": 2}, _view()) == ""


def test_self_exec_wired_into_thinker_prompt():
    prior = {
        "day": 3, "plan_ids": ["SMASH_GRAB"],
        "planned_cells": ["SMASH_GRAB->(31,18)"],
        "corrector_notes": ["no live vision on (31,18) — removed"],
        "moves_executed": 0, "actual_banked": 0,
    }
    text = prompt_mod.build_prompt(
        mode="thinker",
        **_kwargs(agent_view=_view(last_night={}), prior_day_entry=prior),
    )
    assert "PLAN vs CORRECTOR vs EXECUTED" in text
    assert "EXECUTED: NOTHING" in text
