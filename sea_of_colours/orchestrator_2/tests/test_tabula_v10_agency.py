"""v10 Phase 2 — the agency layer (option registry / menu / resolver) and the
directive round-trip of the new ``plan`` + ``situational`` fields.
"""

from __future__ import annotations

from sea_of_colours.orchestrator_2.harnesses.tabula_v7 import (
    directive as directive_mod,
    probe_hints,
    heuristic_chains,
)
from sea_of_colours.orchestrator_2.harnesses.tabula_v10 import (
    agency,
    seam_control as sc,
)


def _view(*, mine=False, enemy_at=None):
    av = {
        "world": {"width": 30, "height": 30, "live": [], "fog_count": 800},
        "orbit": {"probe_stock": 3},
        "my_assets": [
            {"id": "harvester_p1_1", "kind": "harvester", "state": "orbit"},
        ],
        "redsign": [{"center": [10, 10], "cells": [[10, 10, 1.0]], "hour": 3,
                     "mine": mine}],
        "blue_tiles": [], "red_tiles": [], "last_night": {},
    }
    if enemy_at is not None:
        av["competitor_intel"] = {"new_this_day": [
            {"kind": "enemy_probe_launch", "at": list(enemy_at), "day_seen": 2},
        ]}
    return av


def _registry(av):
    hd = probe_hints.top_hot_drop_hints(av, max_hints=2)
    for h in hd:
        h["mine"] = bool(av["redsign"][0].get("mine"))
    pr = probe_hints.top_probe_hints(av, max_hints=3)
    ch = heuristic_chains.top_chain_hints(av, max_chains=3)
    ss = probe_hints.top_supersede_hints(av, max_hints=2)
    seam = sc.build_seam_menu(av, hd)
    return agency.build_registry(
        agent_view=av, seam_patterns=seam, hot_drop_hints=hd,
        probe_hints=pr, chain_hints=ch, supersede_hints=ss,
    )


# ── registry + menu ──────────────────────────────────────────────────────
def test_registry_assigns_stable_ids():
    reg = _registry(_view(mine=False, enemy_at=[10, 10]))
    ids = list(reg.keys())
    assert "BLIND_GRAB" in ids and "UNBEATEN_FLANK" in ids and "WALK_IN" in ids
    # redsign hot-drops are folded into the seam patterns, NOT re-listed as raw
    # HDn (those cells miss the pure — the day-2 trap).
    assert "HD1" not in ids
    assert "PR1" in ids
    assert "SS1" in ids  # enemy probe present -> a supersede option
    # seam patterns lead the registry order (the redsign centrepiece).
    assert ids[0] in ("BLIND_GRAB", "UNBEATEN_FLANK", "WALK_IN")


def test_bluesign_hotdrop_offers_three_comb_shapes():
    # A bluesign hot drop (no redsign) is expanded into STRETCH/SWEEP/SAMPLE
    # variants the thinker chooses between — same drop, different walk.
    av = {
        "world": {"width": 30, "height": 30, "live": [], "fog_count": 800},
        "orbit": {"probe_stock": 3},
        "my_assets": [{"id": "harvester_p1_1", "kind": "harvester",
                       "state": "orbit"}],
        "blue_sign": [{"center": [12, 12],
                       "cells": [[12, 12, 0.9], [13, 12, 0.8]]}],
        "blue_tiles": [], "red_tiles": [], "last_night": {},
    }
    hd = [{"probe_at": [12, 12], "drop_at": [12, 12], "signal_type": "blue_sign",
           "comb_path": [[13, 12]], "mine": False}]
    reg = agency.build_registry(agent_view=av, hot_drop_hints=hd)
    ids = list(reg.keys())
    # HD1 fanned into up to three suffixed shape variants, all sharing group HD1.
    variants = [i for i in ids if i.startswith("HD1")]
    assert len(variants) >= 2
    assert all(reg[i].payload.get("group") == "HD1" for i in variants)
    shapes = {reg[i].payload.get("shape") for i in variants}
    assert shapes <= {"STRETCH", "SWEEP", "SAMPLE"} and len(shapes) >= 2


def test_redsign_hotdrops_folded_into_patterns_not_raw_hd():
    """A CASE-1 (mine) redsign must expose SMASH_GRAB and NOT a competing raw
    redsign HDn that lands short of the pure."""
    reg = _registry(_view(mine=True))
    ids = list(reg.keys())
    assert "SMASH_GRAB" in ids
    assert not any(i.startswith("HD") for i in ids)


def test_menu_block_lists_ids_grouped():
    reg = _registry(_view(mine=True))
    block = agency.format_menu_block(reg)
    assert "OPTION MENU" in block
    assert "REDSIGN PATTERNS" in block
    assert "[SMASH_GRAB]" in block


def test_menu_empty_when_registry_empty():
    assert agency.format_menu_block({}) == ""


# ── resolver ─────────────────────────────────────────────────────────────
def test_resolve_plan_case_insensitive_and_preserves_order():
    reg = _registry(_view(mine=False, enemy_at=[10, 10]))
    sel = agency.resolve_plan(
        ["unbeaten_flank", "BLIND_GRAB"], reg,
    )
    assert [o.option_id for o in sel] == ["UNBEATEN_FLANK", "BLIND_GRAB"]


def test_resolve_plan_tolerates_decorated_probe_ids():
    """The thinker sometimes bolts coordinates onto a bare id (``PR1_at_22_18``);
    the resolver strips the tail so the probe still fires (night-6 wart)."""
    reg = _registry(_view(mine=True))
    pr = next(i for i in reg if i.startswith("PR"))
    for decorated in (f"{pr}_at_22_18", f"{pr}@(22,18)", f"{pr} at 22,18"):
        sel = agency.resolve_plan([decorated], reg)
        assert [o.option_id for o in sel] == [pr], decorated


def test_normalize_option_id_leaves_bare_and_underscore_ids_intact():
    assert agency._normalize_option_id("SMASH_GRAB") == "SMASH_GRAB"
    assert agency._normalize_option_id("BLIND_GRAB#2") == "BLIND_GRAB#2"
    assert agency._normalize_option_id("PR1_at_22_18") == "PR1"
    assert agency._normalize_option_id("ss3") == "SS3"


def test_resolve_plan_drops_unknown_and_dupes():
    reg = _registry(_view(mine=False, enemy_at=[10, 10]))
    sel = agency.resolve_plan(
        ["BLIND_GRAB", "NOPE", "BLIND_GRAB", "SS1"], reg,
    )
    assert [o.option_id for o in sel] == ["BLIND_GRAB", "SS1"]


def test_resolve_plan_empty_inputs():
    reg = _registry(_view(mine=True))
    assert agency.resolve_plan([], reg) == []
    assert agency.resolve_plan(["SMASH_GRAB"], {}) == []


def test_execute_block_renders_selected_in_order():
    reg = _registry(_view(mine=False, enemy_at=[10, 10]))
    sel = agency.resolve_plan(["BLIND_GRAB", "SS1"], reg)
    block = agency.format_execute_block(sel)
    assert "EXECUTE THIS PLAN" in block
    assert block.index("BLIND_GRAB") < block.index("SS1")


def test_execute_block_empty_when_nothing_selected():
    assert agency.format_execute_block([]) == ""


# ── frontier hot-drop (gated last resort) ────────────────────────────────
_FRONTIER_WORLD = {"world": {"width": 40, "height": 28}}
_ECHO_PROBE = [{"at": [11, 13], "area_gain": 40, "edge_promise": 243,
                "extends_from": "echo"}]


def _reg_frontier(*, red_purity=None, probes=None, hot_drop=None, chain=None):
    av = dict(_FRONTIER_WORLD)
    av["red_tiles"] = ([{"x": 5, "y": 5, "purity": red_purity}]
                       if red_purity is not None else [])
    return agency.build_registry(
        agent_view=av, seam_patterns=[], hot_drop_hints=hot_drop or [],
        probe_hints=probes if probes is not None else _ECHO_PROBE,
        chain_hints=chain or [],
    )


def test_frontier_appears_when_trace_only_and_no_better_target():
    reg = _reg_frontier(red_purity=30)  # trace (< vein floor)
    assert "FR1" in reg
    opt = reg["FR1"]
    assert opt.kind == "frontier"
    line = "\n".join(opt.execute_lines)
    assert "probe (11,13)" in line and "drop (11,13)" in line
    assert "LAST RESORT" in opt.detail
    # renders under its own menu group
    assert "FRONTIER HOT-DROP" in agency.format_menu_block(reg)


def test_frontier_suppressed_when_real_red_is_known():
    # a vein-or-better chain means there IS something worth a real drop.
    chain = [{"unit": "h", "cells": [[5, 5]], "purities": [120], "length": 1}]
    reg = _reg_frontier(red_purity=120, chain=chain)
    assert "FR1" not in reg


def test_frontier_suppressed_when_a_hotdrop_is_available():
    hd = [{"signal_type": "bluesign", "probe_at": [8, 8], "drop_at": [9, 9],
           "comb_path": []}]
    reg = _reg_frontier(red_purity=30, hot_drop=hd)
    assert "FR1" not in reg


def test_frontier_needs_a_promising_fog_target():
    reg = _reg_frontier(red_purity=30, probes=[{"at": [11, 13], "edge_promise": 0}])
    assert "FR1" not in reg


def test_execute_block_supersede_is_mandatory_wording():
    """A hot drop that carries a supersede must render it as a required FIRST
    move (O8: the mover used to quietly drop the decisive supersede)."""
    from collections import OrderedDict

    hd = {"probe_at": [8, 8], "drop_at": [10, 10], "signal_type": "redsign",
          "supersede": [4, 16], "unit": "harvester_p1_1"}
    reg = OrderedDict()
    opt = agency._hotdrop_option(1, hd)
    reg[opt.option_id] = opt
    block = agency.format_execute_block(agency.resolve_plan(["HD1"], reg))
    assert "SUPERSEDE" in block
    assert "(4,16)" in block
    assert "optional" not in block.lower()
    # every listed line (incl. the supersede) must be emitted as a real move.
    assert "Emit EVERY probe / supersede / drop / walk line" in block
    assert "do NOT skip this" in block


# ── plan recovery from prose (I3/F4/O8) ──────────────────────────────────
def _prose_registry():
    """Minimal registry with the ID shapes prose recovery must handle."""
    from collections import OrderedDict

    reg = OrderedDict()
    for oid, kind in [
        ("BLIND_GRAB", "seam"), ("UNBEATEN_FLANK", "seam"),
        ("WALK_IN", "seam"), ("SMASH_GRAB#2", "seam"),
        ("HD1", "hotdrop"), ("SS1", "supersede"),
    ]:
        reg[oid] = agency.Option(option_id=oid, kind=kind, title=oid, detail="")
    return reg


def test_recover_plan_from_prose_orders_by_first_appearance():
    reg = _prose_registry()
    prose = (
        "This is a rival beacon. I will SUPERSEDE via SS1 first, then run "
        "BLIND_GRAB, and keep UNBEATEN_FLANK as my secured backup."
    )
    assert agency.recover_plan_from_prose(prose, reg) == [
        "SS1", "BLIND_GRAB", "UNBEATEN_FLANK",
    ]


def test_recover_plan_from_prose_dedupes():
    reg = _prose_registry()
    prose = "BLIND_GRAB now, and again BLIND_GRAB if it survives."
    assert agency.recover_plan_from_prose(prose, reg) == ["BLIND_GRAB"]


def test_recover_plan_from_prose_respects_token_boundaries():
    reg = _prose_registry()
    # 'walk in' (with a space) is NOT the WALK_IN id; and SMASH_GRAB#2 must not
    # also register a bare SMASH_GRAB (it isn't in the registry here).
    prose = "I will walk in slowly and pick SMASH_GRAB#2."
    got = agency.recover_plan_from_prose(prose, reg)
    assert got == ["SMASH_GRAB#2"]
    assert "WALK_IN" not in got


def test_recover_plan_from_prose_empty_inputs():
    reg = _prose_registry()
    assert agency.recover_plan_from_prose("", reg) == []
    assert agency.recover_plan_from_prose("no ids here", reg) == []
    assert agency.recover_plan_from_prose("BLIND_GRAB", {}) == []


def test_resolver_id_maps_to_concrete_geometry():
    """The centrepiece guarantee: an ID expands to its pre-built geometry."""
    av = _view(mine=True)
    reg = _registry(av)
    sel = agency.resolve_plan(["SMASH_GRAB"], reg)
    assert sel
    payload = sel[0].payload
    assert payload["beacon"] == [10, 10]
    assert payload["waves"], "resolved seam option carries concrete waves"
    assert payload["waves"][0]["drop_at"]


# ── directive round-trip of plan + situational ───────────────────────────
def test_parse_directive_json_recovers_plan_and_situational():
    raw = (
        '{"reasoning":"beacon is a rival find, fan out",'
        '"posture":"redsign_race",'
        '"plan":["blind_grab","UNBEATEN_FLANK","ch1"],'
        '"situational":{"mine":false,"players":3,"chaff":true,"emp":false}}'
    )
    d, reasoning = directive_mod.parse_directive_json(raw)
    assert reasoning.startswith("beacon is a rival")
    # IDs are uppercased + order-preserved.
    assert d.plan == ["BLIND_GRAB", "UNBEATEN_FLANK", "CH1"]
    assert d.situational == {"mine": False, "players": 3, "chaff": True, "emp": False}


def test_coerce_ids_filters_bad_tokens_and_caps():
    from sea_of_colours.orchestrator_2.harnesses.tabula_v7.directive import (
        _coerce_ids, _MAX_PLAN_IDS,
    )
    got = _coerce_ids(["HD1", "bad token!", "", 42, "PR2", "PR2"])
    assert got == ["HD1", "PR2"]  # bad/empty/non-str dropped, dupe removed
    long = _coerce_ids([f"HD{i}" for i in range(20)])
    assert len(long) == _MAX_PLAN_IDS


def test_coerce_situational_whitelists_keys():
    from sea_of_colours.orchestrator_2.harnesses.tabula_v7.directive import (
        _coerce_situational,
    )
    got = _coerce_situational(
        {"mine": "yes", "players": "3", "chaff": 0, "emp": True, "junk": 9},
    )
    assert got == {"mine": True, "players": 3, "chaff": False, "emp": True}
    assert "junk" not in got


def test_sanitize_directive_preserves_plan_and_situational():
    d = directive_mod.Directive(
        posture="redsign_race",
        plan=["SMASH_GRAB", "HD1"],
        situational={"mine": True, "players": 2, "chaff": False, "emp": False},
    )
    out = directive_mod.sanitize_directive(d, {"world": {"width": 30, "height": 30}})
    assert out.plan == ["SMASH_GRAB", "HD1"]
    assert out.situational["mine"] is True


def test_v7_thinker_output_without_plan_stays_empty():
    """Frozen-safety: a v7-style decision (no plan/situational) parses clean."""
    raw = '{"reasoning":"harvest best red","posture":"aggressive"}'
    d, _ = directive_mod.parse_directive_json(raw)
    assert d.plan == []
    assert d.situational == {}


# ── end-to-end harness glue (menu -> thinker -> resolve -> mover) ────────
def _stage_of(response_format) -> str:
    """think (no schema) | plan (decision schema) | mover (moves schema)."""
    name = ((response_format or {}).get("json_schema") or {}).get("name", "")
    if name == "soc_strategist_decision":
        return "plan"
    # ``soc_tabula_plan`` is the shared v7 mover schema; v10's moves-only mover
    # (A4) uses its own trimmed ``soc_tabula_v10_moves`` schema.
    if name in ("soc_tabula_plan", "soc_tabula_v10_moves"):
        return "mover"
    return "think"


class _FakeInvoker:
    """Three-stage routing: THINK -> prose, PLAN -> decision JSON, MOVER ->
    moves JSON (the contained two-stage thinker + mover)."""

    prompts: dict = {}

    def __init__(self, *, model=None, response_format=None, max_completion_tokens=None):
        self._stage = _stage_of(response_format)

    def invoke(self, prompt, *, wallclock_cap_s=None, **kw):
        # keep the legacy "thinker" key pointing at the PLAN prompt (tests assert
        # the option menu reaches it), and add a "think" key for the think pass.
        key = {"plan": "thinker", "mover": "mover", "think": "think"}[self._stage]
        _FakeInvoker.prompts[key] = prompt
        if self._stage == "think":
            return {"response": "Rival beacon; fan out, do not stack. "
                                "Use BLIND_GRAB then UNBEATEN_FLANK."}
        if self._stage == "plan":
            return {"response": (
                '{"posture":"redsign_race",'
                '"plan":["BLIND_GRAB","UNBEATEN_FLANK"],'
                '"situational":{"mine":false,"players":3,"chaff":false,"emp":false},'
                '"reasoning":"rival beacon; fan out, do not stack"}'
            )}
        return {"response": '{"moves":[{"a":"probe","at":[8,8]}],'
                            '"plan_this_turn":"contest the seam"}'}


def _live_view():
    grid_w, grid_h = 30, 30
    return {
        "agent_view": {
            "meta": {"day": 3},
            "hud": {"day": 3, "season_day_cap": 7,
                    "scores": {"p1": 0, "p2": 0, "p3": 0}},
            "world": {"width": grid_w, "height": grid_h, "live": [],
                      "fog_count": 700},
            "orbit": {"probe_stock": 3},
            "my_assets": [
                {"id": "harvester_p1_1", "kind": "harvester", "state": "orbit"},
            ],
            "redsign": [{"center": [10, 10], "cells": [[10, 10, 1.0]],
                         "hour": 3, "mine": False}],
            "red_tiles": [], "blue_tiles": [],
            "competitor_intel": {"new_this_day": [
                {"kind": "enemy_probe_launch", "at": [10, 10], "day_seen": 2},
            ]},
            "last_night": {},
        },
    }


def test_harness_run_wires_menu_to_thinker_and_execute_to_mover(monkeypatch):
    from sea_of_colours.snowpark.store import InMemorySocStore
    from sea_of_colours.orchestrator_2.harnesses.tabula_v10 import harness as h
    from sea_of_colours.snowpark import engine as soc_engine

    _FakeInvoker.prompts = {}
    monkeypatch.setattr(h, "CortexChatInvoker", _FakeInvoker)
    monkeypatch.setattr(
        soc_engine, "submit_policy",
        lambda *a, **k: {"ok": True, "accepted": True},
    )
    h.clear_snapshots()

    store = InMemorySocStore()
    out = h.run(store=store, session_id="AG1", player="p1", view=_live_view())

    assert out["ok"] is True
    extras = out["extras"]
    # The curated menu was built and offered to the thinker...
    assert "BLIND_GRAB" in extras["option_menu_ids"]
    assert "OPTION MENU" in _FakeInvoker.prompts["thinker"]
    # ...the thinker's plan resolved to concrete options...
    assert extras["selected_option_ids"] == ["BLIND_GRAB", "UNBEATEN_FLANK"]
    # ...and R1 COMPILED the recipe deterministically — the LLM mover was NOT
    # called (no mover prompt captured), and the moves come from the packager,
    # not the fake mover's probe(8,8).
    assert extras["packager_used"] is True
    assert "mover" not in _FakeInvoker.prompts
    assert any(m.get("a") == "drop" for m in out["moves"])
    assert {"a": "probe", "at": [8, 8]} not in out["moves"]


class _FakeInvokerEmptyPlan:
    """Think pass NAMES the patterns in prose but the PLAN pass leaves the JSON
    ``plan`` empty (the F4/O8 failure). The harness must recover the plan from
    the think prose so the EXECUTE geometry still reaches the mover."""

    prompts: dict = {}

    def __init__(self, *, model=None, response_format=None, max_completion_tokens=None):
        self._stage = _stage_of(response_format)

    def invoke(self, prompt, *, wallclock_cap_s=None, **kw):
        key = {"plan": "thinker", "mover": "mover", "think": "think"}[self._stage]
        _FakeInvokerEmptyPlan.prompts[key] = prompt
        if self._stage == "think":
            return {"response": "Rival beacon. Supersede the finder then "
                                "BLIND_GRAB; hold UNBEATEN_FLANK as backup."}
        if self._stage == "plan":
            return {"response": '{"posture":"redsign_race","plan":[]}'}
        return {"response": '{"moves":[{"a":"probe","at":[8,8]}],'
                            '"plan_this_turn":"contest"}'}


def test_harness_recovers_empty_plan_from_prose(monkeypatch):
    from sea_of_colours.snowpark.store import InMemorySocStore
    from sea_of_colours.orchestrator_2.harnesses.tabula_v10 import harness as h
    from sea_of_colours.snowpark import engine as soc_engine

    _FakeInvokerEmptyPlan.prompts = {}
    monkeypatch.setattr(h, "CortexChatInvoker", _FakeInvokerEmptyPlan)
    monkeypatch.setattr(
        soc_engine, "submit_policy",
        lambda *a, **k: {"ok": True, "accepted": True},
    )
    h.clear_snapshots()

    store = InMemorySocStore()
    out = h.run(store=store, session_id="AG2", player="p1", view=_live_view())

    assert out["ok"] is True
    # The JSON plan was empty, but prose named the patterns → recovered + resolved
    # → R1 packager compiled the recipe (LLM mover not called).
    assert out["extras"]["selected_option_ids"] == ["BLIND_GRAB", "UNBEATEN_FLANK"]
    assert out["extras"]["packager_used"] is True
    assert "mover" not in _FakeInvokerEmptyPlan.prompts


class _FakeInvokerFlakyThinker:
    """The PLAN pass returns an EMPTY body on the first call (transient flake)
    then a valid decision on the retry. Think + mover behave normally."""

    thinker_calls = 0

    def __init__(self, *, model=None, response_format=None, max_completion_tokens=None):
        self._stage = _stage_of(response_format)

    def invoke(self, prompt, *, wallclock_cap_s=None, **kw):
        if self._stage == "think":
            return {"response": "rival beacon; fan out, BLIND_GRAB"}
        if self._stage == "plan":
            _FakeInvokerFlakyThinker.thinker_calls += 1
            if _FakeInvokerFlakyThinker.thinker_calls == 1:
                return {"response": ""}  # flake: empty body, no directive
            return {"response": (
                '{"posture":"redsign_race","plan":["BLIND_GRAB"],'
                '"reasoning":"rival beacon; fan out"}'
            )}
        return {"response": '{"moves":[{"a":"probe","at":[8,8]}],'
                            '"plan_this_turn":"contest"}'}


def test_harness_retries_thinker_once_on_empty(monkeypatch):
    from sea_of_colours.snowpark.store import InMemorySocStore
    from sea_of_colours.orchestrator_2.harnesses.tabula_v10 import harness as h
    from sea_of_colours.snowpark import engine as soc_engine

    _FakeInvokerFlakyThinker.thinker_calls = 0
    monkeypatch.setattr(h, "CortexChatInvoker", _FakeInvokerFlakyThinker)
    monkeypatch.setattr(
        soc_engine, "submit_policy",
        lambda *a, **k: {"ok": True, "accepted": True},
    )
    h.clear_snapshots()

    store = InMemorySocStore()
    out = h.run(store=store, session_id="AG3", player="p1", view=_live_view())

    assert out["ok"] is True
    # Retried exactly once, then recovered the directive on the 2nd call.
    assert _FakeInvokerFlakyThinker.thinker_calls == 2
    assert out["extras"]["thinker_retried"] is True
    assert out["extras"]["selected_option_ids"] == ["BLIND_GRAB"]


class _FakeInvokerRambleNoDirective:
    """Worst case: the PLAN pass is clipped before any ``posture`` lands (both
    attempts), so parsing yields NO directive. The THINK prose still NAMES the
    patterns, so the harness must build a minimal directive from the recovered
    plan rather than hand the mover nothing (the gap that let it freelance the
    wrong hot-drop)."""

    prompts: dict = {}

    def __init__(self, *, model=None, response_format=None, max_completion_tokens=None):
        self._stage = _stage_of(response_format)

    def invoke(self, prompt, *, wallclock_cap_s=None, **kw):
        key = {"plan": "thinker", "mover": "mover", "think": "think"}[self._stage]
        _FakeInvokerRambleNoDirective.prompts[key] = prompt
        if self._stage == "think":
            return {"response": "Rival beacon at (10,10). I should BLIND_GRAB "
                                "the core, then UNBEATEN_FLANK from a fresh "
                                "angle after the EMP window."}
        if self._stage == "plan":
            # clipped before ``posture`` lands — unparseable, no directive.
            return {"response": '{"situational":{"mine":false,"players":3,'}
        return {"response": '{"moves":[{"a":"probe","at":[8,8]}],'
                            '"plan_this_turn":"contest"}'}


# ── R5 final-night deploy guarantee ─────────────────────────────────────
def _opt(oid, kind):
    return agency.Option(option_id=oid, kind=kind, title="t", detail="d")


def _reg(*opts):
    from collections import OrderedDict
    return OrderedDict((o.option_id, o) for o in opts)


def test_r5_injects_deploy_when_final_night_all_probes():
    reg = _reg(_opt("BLIND_GRAB", "seam"), _opt("PR1", "probe"),
               _opt("SS1", "supersede"))
    selected = [reg["SS1"], reg["PR1"]]  # no harvester deploy
    out, injected = agency.ensure_final_night_deploy(
        selected, reg, alive_harvesters=1, is_final_night=True,
    )
    assert injected is True
    assert out[0].option_id == "BLIND_GRAB"       # best deploy prepended
    assert [o.option_id for o in out[1:]] == ["SS1", "PR1"]


def test_r5_noop_when_plan_already_deploys():
    reg = _reg(_opt("CH1", "chain"), _opt("PR1", "probe"))
    selected = [reg["CH1"], reg["PR1"]]
    out, injected = agency.ensure_final_night_deploy(
        selected, reg, alive_harvesters=2, is_final_night=True,
    )
    assert injected is False and out == selected


def test_r5_noop_off_final_night():
    reg = _reg(_opt("BLIND_GRAB", "seam"), _opt("PR1", "probe"))
    selected = [reg["PR1"]]
    out, injected = agency.ensure_final_night_deploy(
        selected, reg, alive_harvesters=1, is_final_night=False,
    )
    assert injected is False and out == selected


def test_r5_noop_when_no_harvester_alive():
    reg = _reg(_opt("BLIND_GRAB", "seam"), _opt("PR1", "probe"))
    out, injected = agency.ensure_final_night_deploy(
        [reg["PR1"]], reg, alive_harvesters=0, is_final_night=True,
    )
    assert injected is False


def test_harness_builds_directive_from_prose_when_parse_yields_none(monkeypatch):
    from sea_of_colours.snowpark.store import InMemorySocStore
    from sea_of_colours.orchestrator_2.harnesses.tabula_v10 import harness as h
    from sea_of_colours.snowpark import engine as soc_engine

    _FakeInvokerRambleNoDirective.prompts = {}
    monkeypatch.setattr(h, "CortexChatInvoker", _FakeInvokerRambleNoDirective)
    monkeypatch.setattr(
        soc_engine, "submit_policy",
        lambda *a, **k: {"ok": True, "accepted": True},
    )
    h.clear_snapshots()

    store = InMemorySocStore()
    out = h.run(store=store, session_id="AG4", player="p1", view=_live_view())

    assert out["ok"] is True
    # No parseable directive at all, but prose named the patterns → recovered,
    # resolved, and R1 packager compiled the recipe (LLM mover not called).
    assert out["extras"]["selected_option_ids"] == ["BLIND_GRAB", "UNBEATEN_FLANK"]
    assert out["extras"]["packager_used"] is True
    assert "mover" not in _FakeInvokerRambleNoDirective.prompts
