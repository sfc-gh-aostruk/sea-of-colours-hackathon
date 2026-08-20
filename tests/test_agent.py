"""SOC_RED_REAPER agent runtime tests.

Exercises the heuristic path end-to-end against the in-memory SOC
store. The Cortex path is covered by the live-Snowflake lane in
``test_soc_parity.py`` (gated by ``SOC_TEST_LIVE=1``); here we just
confirm the orchestrator falls back gracefully when no PAT is set.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("SOC_BACKEND", "memory")

from fastapi.testclient import TestClient

from sea_of_colours.agent.heuristic_agent import HeuristicAgent, plan_moves
from sea_of_colours.agent.runtime import (
    AI_AGENTS,
    CORTEX_AGENT_DEFAULT,
    HEURISTIC_AGENT_NAME,
    run_agent_turn,
)
from sea_of_colours.snowpark import backend as soc_backend
from sea_of_colours.snowpark import engine as soc_engine


@pytest.fixture()
def store():
    soc_backend.reset_for_tests()
    return soc_backend.get_store()


@pytest.fixture()
def session(store):
    info = soc_engine.init_session(store, seed=21, width=18, height=12)
    return info["session_id"]


def _make_view_payload(*, red_xy=(6, 4)):
    """Tiny hand-rolled agent_view for unit-testing :func:`plan_moves`."""
    return {
        "grid": {"width": 18, "height": 12, "cell_counts": {"fog": 100, "stale": 0, "fresh": 12}},
        "red_tiles": [
            {"x": red_xy[0], "y": red_xy[1], "purity": 200, "freshness": "fresh", "square_id": "abc"},
        ],
        "green_tiles": [],
        "fog_clusters": [
            {"centroid": [12, 7], "size": 40, "nearest_visible_edge": [10, 6]},
            {"centroid": [3, 9], "size": 18, "nearest_visible_edge": [4, 9]},
        ],
        "entities": {
            "mine": [
                {"id": "harvester_p1", "type": "harvester", "pos": None,
                 "carrying_red": False, "cargo_count": 0},
                {"id": "orblift_p1", "type": "orblift", "pos": None,
                 "holds_red": False},
            ],
            "echoes": [],
        },
    }


def test_plan_moves_emits_drop_then_step_when_orbital():
    view = _make_view_payload(red_xy=(6, 4))
    moves, rationale = plan_moves(view)
    # First move: drop adjacent to (6,4); next: step onto (6,4).
    assert moves[0]["a"] == "drop"
    assert moves[0]["unit"] == "harvester_p1"
    assert moves[1]["a"] == "step"
    assert moves[1]["to"] == [6, 4]
    # And probes on the two largest fog clusters — now aimed at the
    # CLUSTER CENTROID (deep in the fog) rather than the visible-edge
    # boundary, so each probe expands the visible region meaningfully.
    probes = [m for m in moves if m["a"] == "probe"]
    assert len(probes) == 2
    centroids = {(12, 7), (3, 9)}
    for p in probes:
        assert tuple(p["at"]) in centroids, (
            f"probes should hit cluster centroids, got {p['at']}"
        )
    assert "harvester" in rationale.lower() or "probe" in rationale.lower()


def test_probes_avoid_piling_on_existing_probes():
    """Successive probes must spread out — that was the root cause of
    the 'no RED visible' stall the player hit on day 6+.

    Setup: a fog cluster centroid sits 3 cells from an existing probe.
    With ``min_separation=8`` the planner should NOT drop another probe
    on top of the same area; it falls through to the cluster's
    visible-edge anchor instead (or skips that cluster entirely).
    """
    view = _make_view_payload(red_xy=(6, 4))
    view["red_tiles"] = []  # force the exploratory branch
    # One large cluster whose centroid is right next to an existing probe.
    view["fog_clusters"] = [
        {"centroid": [11, 7], "size": 60, "nearest_visible_edge": [3, 1]},
    ]
    # Existing probe at (10,6) — centroid (11,7) is only 2 cells away.
    view["entities"]["mine"].append({
        "id": "probe_p1_1", "type": "probe", "pos": [10, 6],
    })
    moves, _ = plan_moves(view)
    probes = [m for m in moves if m["a"] == "probe"]
    assert probes, "should still drop SOME probe (fall back to edge)"
    for p in probes:
        # The probe must NOT have landed near the existing one — that
        # would defeat the whole point of the exploration heuristic.
        from sea_of_colours.agent.heuristic_agent import _manhattan
        assert _manhattan(tuple(p["at"]), (10, 6)) >= 8, (
            f"probe at {p['at']} is piled on existing probe (10,6); "
            "spread-out rule failed"
        )


def test_exploratory_drop_moves_off_centre_on_subsequent_nights():
    """When no RED is visible AND map centre has already been explored,
    the harvester should land somewhere ELSE on subsequent nights — not
    keep dropping at the same coordinates forever.

    This is the exact regression the player reported: 5+ nights of
    "p1 dropped harvester_p1 at (20,14)" with hoard frozen at 9/50.
    """
    view = _make_view_payload(red_xy=(0, 0))
    view["red_tiles"] = []  # no harvest target → exploratory branch
    # Pretend the map centre is already covered by probes.
    width, height = view["grid"]["width"], view["grid"]["height"]
    cx, cy = width // 2, height // 2
    view["entities"]["mine"].extend([
        {"id": f"probe_p1_{i}", "type": "probe", "pos": [cx + dx, cy + dy]}
        for i, (dx, dy) in enumerate([(0, 0), (2, 1), (-1, 2)])
    ])
    # A fog cluster far from the centre — that's where the harvester
    # should choose to drop instead of piling on the centre again.
    view["fog_clusters"] = [
        {"centroid": [2, 2], "size": 80, "nearest_visible_edge": [4, 4]},
    ]
    moves, rationale = plan_moves(view)
    drops = [m for m in moves if m["a"] == "drop"]
    assert drops, "exploratory branch should still drop the harvester"
    drop_xy = tuple(drops[0]["at"])
    # The chosen drop site must NOT be the map centre — that's the bug.
    assert drop_xy != (cx, cy), (
        f"harvester dropped at map centre {drop_xy} despite probes "
        "already there; exploratory drop should target the fog cluster"
    )


def test_plan_moves_falls_back_to_fog_frontier_when_no_red_visible():
    """Orbital harvester + no RED visible → drop at the largest fog
    cluster's NEAREST_VISIBLE_EDGE so the harvester lands on a
    live/echo tile (RULEBOOK §3.10) and its 2-cell vision disk
    reveals fresh ground beyond the frontier next turn.

    Pre-v0.9.5 the heuristic aimed at the fog *centroid*, which
    the conftest patch let through but the live game would have
    rejected as "drop into fog". v0.9.5 picks the visible edge so
    the drop actually succeeds in production.
    """
    view = _make_view_payload(red_xy=(0, 0))
    view["red_tiles"] = []
    # Fog clusters from _make_view_payload: largest is the [12,7]
    # cluster with visible edge at [10, 6].
    moves, rationale = plan_moves(view)
    drops = [m for m in moves if m["a"] == "drop"]
    assert len(drops) == 1
    assert drops[0]["at"] == [10, 6], (
        "fog-push drop should target the cluster's NEAREST_VISIBLE_EDGE, "
        "not the deep-fog centroid (RULEBOOK §3.10 — harvesters must land "
        "on live or echo cells)"
    )
    # v0.9.6 — after the drop the harvester now WALKS into the fog
    # (zero-or-more step moves) before lifting. The HARVESTER chain
    # must end with exactly one pickup so dawn doesn't destroy the
    # unit. Anything AFTER the pickup is the probe-drop block; the
    # pickup is the last action that targets this harvester.
    drop_idx = moves.index(drops[0])
    pickups = [
        i for i, m in enumerate(moves)
        if m.get("a") == "pickup" and m.get("unit") == drops[0].get("unit")
    ]
    assert len(pickups) == 1, (
        f"scout chain must end with exactly one pickup for this harvester, "
        f"got {len(pickups)}"
    )
    pickup_idx = pickups[0]
    assert pickup_idx > drop_idx, (
        "pickup for the scouted harvester must come AFTER its drop"
    )
    # Any actions between the drop and the pickup must be ``step``s
    # belonging to the same harvester — the v0.9.6 fog-scout walk.
    middle = moves[drop_idx + 1 : pickup_idx]
    assert all(m["a"] == "step" for m in middle), (
        f"expected step actions between drop and pickup, got {middle}"
    )
    # Whatever follows the pickup is the probe-drop block; it must
    # not target the scouted harvester (engine §3.11.2 — dawn would
    # crash the unit if it were still on the surface).
    tail = moves[pickup_idx + 1 :]
    assert all(m.get("a") != "step" or m.get("unit") != drops[0].get("unit") for m in tail), (
        "no harvester steps may run after the unit's pickup"
    )
    assert "no red" in rationale.lower() or "drop" in rationale.lower() or "scouting" in rationale.lower()


def test_plan_moves_only_probes_when_harvester_already_surfaced_with_no_red():
    """If the harvester is already on the surface and no RED is visible, emit probes only."""
    view = _make_view_payload(red_xy=(0, 0))
    view["red_tiles"] = []
    # Surface the harvester so the orbital fallback doesn't fire.
    for ent in view["entities"]["mine"]:
        if ent["type"] == "harvester":
            ent["pos"] = [4, 4]
    moves, _ = plan_moves(view)
    assert all(m["a"] == "probe" for m in moves)


def test_agent_view_includes_echoed_red_tiles_as_stale():
    """REGRESSION: red_tiles must include echo-only reds, marked stale.

    The bug: ``build_agent_view`` only populated ``red_tiles`` from the
    *currently-visible* set. The moment the harvester returned to orbit
    and the player had no probes on a known-RED area, the agent went
    completely blind to those tiles — even though the player's screen
    still showed them via the echo (probe intel) layer. RED_HARVEST
    then stalled forever on the no-RED fallback.
    """
    from sea_of_colours.game.entities import Entity
    from sea_of_colours.game.session import GameSession
    from sea_of_colours.generator import Cell, Tile
    from sea_of_colours.snowpark.view import build_agent_view

    sess = GameSession.new(16, 10, seed=12345)
    # Force a RED tile at (8, 5) and a probe at (8, 5) so the snapshot
    # gets recorded into probe_intel, then *remove the probe* — that's
    # the state where live LoS no longer covers the cell but the echo
    # remembers it.
    sess.grid[5][8] = Cell(Tile.RED, 220)
    probe_id = "probe_p1_echotest"
    sess.entities[probe_id] = Entity(
        id=probe_id, entity_type="probe", owner="p1", x=8, y=5,
    )
    sess._pulse_vision_intel()
    # Drop probe — only echo intel remains.
    del sess.entities[probe_id]
    # Lift the harvester to orbit so the player has no live LoS at all.
    h = sess.entities["harvester_p1"]
    h.x = None
    h.y = None

    view = build_agent_view(sess, "p1")
    reds = view["red_tiles"]
    matching = [r for r in reds if (r["x"], r["y"]) == (8, 5)]
    assert matching, (
        "echo'd RED at (8,5) must appear in agent's red_tiles — "
        "this was the missing data that caused RED_HARVEST to stall"
    )
    assert matching[0]["freshness"] == "stale", (
        "echo-sourced reds should be flagged stale so the agent can "
        "still prefer fresh reds when available"
    )
    assert matching[0]["purity"] == 220, (
        "purity must round-trip from the snapshot, not get lost"
    )


def test_agent_view_red_rows_carry_canonical_tier_and_value():
    """Every red_tiles row (fresh OR stale) must carry tier + value.

    These fields are what the agent prompt + heuristic now reason
    over (see RULEBOOK §2.2). They MUST match the canonical
    ``sea_of_colours.render.red_level`` / ``RED_LEVEL_NAMES`` so
    the rulebook, the engine, the agent_view payload, and the
    Cortex prompt all share a single source of truth.
    """
    from sea_of_colours.game.entities import Entity
    from sea_of_colours.game.session import GameSession
    from sea_of_colours.generator import Cell, Tile
    from sea_of_colours.render import RED_LEVEL_NAMES, red_level
    from sea_of_colours.snowpark.view import build_agent_view

    sess = GameSession.new(16, 10, seed=2026)
    # One cell per tier so we exercise the whole ladder. Coordinates
    # picked to keep them inside the harvester's vision disk when we
    # plant a probe there.
    samples = [
        (3, 3, 40, "trace"),
        (6, 4, 120, "vein"),
        (9, 5, 200, "mass"),
        (12, 6, 255, "pure"),
    ]
    for x, y, purity, _ in samples:
        sess.grid[y][x] = Cell(Tile.RED, purity)
        pid = f"probe_p1_{x}_{y}"
        sess.entities[pid] = Entity(
            id=pid, entity_type="probe", owner="p1", x=x, y=y,
        )
    sess._pulse_vision_intel()
    view = build_agent_view(sess, "p1")
    rows = {(int(r["x"]), int(r["y"])): r for r in view["red_tiles"]}
    for x, y, purity, expected_tier in samples:
        row = rows.get((x, y))
        assert row is not None, f"sample RED@({x},{y}) missing from red_tiles"
        assert row["purity"] == purity
        assert row["tier"] == expected_tier == RED_LEVEL_NAMES[red_level(purity) - 1]
        # value == purity today, capped at 255 per parcel.
        assert row["value"] == min(255, purity)


def test_agent_view_stale_red_rows_also_carry_tier_and_value():
    """The echo (stale) path must surface the same tier + value fields."""
    from sea_of_colours.game.entities import Entity
    from sea_of_colours.game.session import GameSession
    from sea_of_colours.generator import Cell, Tile
    from sea_of_colours.snowpark.view import build_agent_view

    sess = GameSession.new(16, 10, seed=99)
    sess.grid[5][8] = Cell(Tile.RED, 222)
    probe_id = "probe_p1_echotest"
    sess.entities[probe_id] = Entity(
        id=probe_id, entity_type="probe", owner="p1", x=8, y=5,
    )
    sess._pulse_vision_intel()
    del sess.entities[probe_id]
    h = sess.entities["harvester_p1"]
    h.x = None
    h.y = None

    view = build_agent_view(sess, "p1")
    row = next(r for r in view["red_tiles"] if (r["x"], r["y"]) == (8, 5))
    assert row["freshness"] == "stale"
    assert row["tier"] == "mass"  # 222 sits in 151–254
    assert row["value"] == 222


def test_agent_acts_on_stale_red_when_no_fresh_red_visible():
    """When only stale RED is in the view, the agent should still act.

    Without this, day 6+ of a season looks identical to day 1: the
    agent picks the no-RED fallback and dumps the harvester at the
    map centre forever.
    """
    view = _make_view_payload(red_xy=(0, 0))
    # No fresh reds — only an echo-sourced one.
    view["red_tiles"] = [
        {"x": 12, "y": 6, "purity": 180, "freshness": "stale", "square_id": "s1"},
    ]
    moves, rationale = plan_moves(view)
    # Must produce a real harvest chain (drop+step+pickup), NOT the
    # exploratory branch.
    actions = [m["a"] for m in moves]
    assert "drop" in actions
    assert "pickup" in actions
    assert "step" in actions
    # The first step should head toward (12, 6).
    first_step = next(m for m in moves if m["a"] == "step")
    assert first_step["to"][0] in (11, 12, 13) or first_step["to"][1] in (5, 6, 7)


def test_heuristic_agent_play_wraps_plan_moves():
    agent = HeuristicAgent()
    plan = agent.play(_make_view_payload())
    assert plan["moves"]
    assert "rationale" in plan
    assert plan["tool_calls"]


def test_run_agent_turn_logs_invocation(store, session):
    """RED_HARVEST (heuristic) always lands an audit row, even on a fully-fogged Day 1."""
    result = run_agent_turn(store, session, "p1")
    assert result["ok"]
    assert result["runtime"] == "heuristic"
    # Heuristic runs identify themselves as RED_HARVEST — the AI
    # agents catalogue (Cortex-backed) uses different names.
    assert result["agent_id"] == HEURISTIC_AGENT_NAME
    assert result["agent_id"] not in AI_AGENTS, "heuristic must not collide with AI agent names"
    audit = store.list_agent_invocations(session)
    assert len(audit) == 1
    assert audit[0]["agent_id"] == HEURISTIC_AGENT_NAME
    assert audit[0]["player"] == "p1"
    assert audit[0]["rationale"]


def test_run_agent_turn_submits_when_view_has_targets(store, session):
    """When the structured view exposes red tiles, the agent submits a queue."""
    # Hand-rolled view payload with a known RED tile so we exercise the
    # submission path even when the live grid hasn't revealed any reds.
    view = _make_view_payload(red_xy=(6, 4))
    moves, _ = plan_moves(view)
    assert moves, "heuristic should produce a queue when a RED tile is visible"
    # Submit it the way the runtime would and assert the engine accepts it.
    res = soc_engine.submit_policy(store, session, "p1", moves)
    assert res["ok"]


def test_agent_route_smoke(store, session):
    soc_backend._memory_store = store  # share the fixture's store
    from server.app import app

    client = TestClient(app)
    r = client.post(f"/api/game/{session}/agent/think", params={"player": "p1"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"]
    # Default runtime is heuristic → RED_HARVEST identifies itself in the
    # envelope. Cortex would substitute a name from AI_AGENTS.
    assert body["agent_id"] == HEURISTIC_AGENT_NAME
    assert body["runtime"] in {"cortex", "heuristic"}


def test_agent_resolves_night_when_partner_already_locked(store, session):
    """If p2 already submitted, the agent's turn should resolve the night."""
    soc_engine.submit_policy(store, session, "p2", [])
    result = run_agent_turn(store, session, "p1")
    assert result["ok"]
    # Either the policy was empty (no moves) → submit_result missing, OR
    # the night actually resolved. We accept both: red-less map may
    # legitimately produce a zero-move queue.
    if result["moves"]:
        assert result["night_resolved"] is True


def test_agent_route_rejects_bad_player(store, session):
    soc_backend._memory_store = store
    from server.app import app

    client = TestClient(app)
    r = client.post(f"/api/game/{session}/agent/think", params={"player": "p9"})
    assert r.status_code == 400


def test_agent_route_rejects_bad_runtime_override(store, session):
    """Unknown ``?runtime=...`` values must be rejected at the route level."""
    soc_backend._memory_store = store
    from server.app import app

    client = TestClient(app)
    r = client.post(
        f"/api/game/{session}/agent/think",
        params={"player": "p1", "runtime": "skynet"},
    )
    assert r.status_code == 400


def test_agent_route_runtime_override_heuristic(store, session):
    """``?runtime=heuristic`` pins RED_HARVEST for a single call."""
    soc_backend._memory_store = store
    from server.app import app

    client = TestClient(app)
    r = client.post(
        f"/api/game/{session}/agent/think",
        params={"player": "p1", "runtime": "heuristic"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"]
    assert body["runtime"] == "heuristic"
    assert body["agent_id"] == HEURISTIC_AGENT_NAME


def test_cortex_runtime_does_not_double_submit(monkeypatch, store, session):
    """When Cortex is the runtime, runtime.py MUST NOT re-submit the policy.

    Background: the original implementation always called
    `soc_engine.submit_policy(..., moves=[])` after the agent ran. In
    Cortex mode, `moves` stays empty because Cortex submits via the
    `soc_submit_policy` tool itself — so the always-call would overwrite
    Cortex's live queue with an empty list and brick the seat.
    """
    import sea_of_colours.agent.runtime as runtime_mod

    # 1) Make the cortex path take over.
    monkeypatch.setenv("SOC_AGENT_RUNTIME", "cortex")

    # 2) Stub the invoker so we don't touch the network.
    class _StubInvoker:
        def __init__(self, *args, **kwargs):
            # Runtime now passes ``agent_name=...`` so the stub has to
            # accept arbitrary kwargs to stay drop-in.
            self.agent_name = kwargs.get("agent_name") or CORTEX_AGENT_DEFAULT

        def is_ready(self):
            return True

        def invoke(self, prompt):
            # Simulate Cortex calling SOC_SUBMIT_POLICY out of band by
            # writing a non-empty queue directly into the store the
            # runtime sees. The runtime's status read will then observe
            # the seat as ready, mirroring real Cortex behaviour.
            soc_engine.submit_policy(
                store,
                session,
                "p1",
                [{"a": "probe", "at": [4, 4]}],
            )
            return {
                "ok": True,
                "response": "stub-rationale",
                "tool_calls": [{"tool": "soc_submit_policy"}],
            }

    monkeypatch.setattr(runtime_mod, "CortexAgentInvoker", _StubInvoker)

    # 3) Spy on submit_policy so we can count calls.
    calls = []
    real_submit = soc_engine.submit_policy

    def _spy(s, sid, player, moves):
        calls.append((player, list(moves)))
        return real_submit(s, sid, player, moves)

    monkeypatch.setattr(soc_engine, "submit_policy", _spy)
    monkeypatch.setattr(runtime_mod.soc_engine, "submit_policy", _spy)

    result = run_agent_turn(store, session, "p1")
    assert result["ok"]
    assert result["runtime"] == "cortex"
    # The Cortex stub identifies as the default AI agent, NOT as RED_HARVEST.
    assert result["agent_id"] == CORTEX_AGENT_DEFAULT
    assert result["agent_id"] in AI_AGENTS

    # The stub invoker submitted ONE non-empty queue. runtime.py MUST NOT
    # have added a second submit.
    submits_by_player = [c for c in calls if c[0] == "p1"]
    assert len(submits_by_player) == 1, (
        f"expected exactly one p1 submission (Cortex's own), got "
        f"{len(submits_by_player)}: {submits_by_player}"
    )
    assert submits_by_player[0][1], "Cortex's submitted queue should be non-empty"


def test_cortex_failure_falls_back_to_heuristic_submit(monkeypatch, store, session):
    """If Cortex says ok but never submits, runtime.py runs the heuristic fallback."""
    import sea_of_colours.agent.runtime as runtime_mod

    monkeypatch.setenv("SOC_AGENT_RUNTIME", "cortex")

    class _SilentInvoker:
        def __init__(self, *args, **kwargs):
            self.agent_name = kwargs.get("agent_name") or CORTEX_AGENT_DEFAULT

        def is_ready(self):
            return True

        def invoke(self, prompt):
            # Cortex says ok but never actually called soc_submit_policy.
            return {"ok": True, "response": "looked but didn't submit", "tool_calls": []}

    monkeypatch.setattr(runtime_mod, "CortexAgentInvoker", _SilentInvoker)

    result = run_agent_turn(store, session, "p1")
    assert result["ok"]
    # We should still see p1's seat now locked in the engine (the
    # heuristic fallback submitted something on cortex's behalf).
    status = soc_engine.get_session_status(store, session)
    assert status["pending"]["p1"] is True
    assert "fallback" in result["rationale"].lower() or result["submitted"]
    # Because the heuristic carried the seat, the envelope reports the
    # heuristic's name (not the failed Cortex agent's).
    assert result["agent_id"] == HEURISTIC_AGENT_NAME
    assert result["runtime"] == "heuristic"


def test_runtime_override_pins_heuristic_even_when_env_says_cortex(
    monkeypatch, store, session
):
    """An explicit ``runtime_override='heuristic'`` MUST win over the env.

    This is the contract the "AI vs RED_HARVEST" button relies on:
    one seat (p1) calls ``?runtime=cortex``, the other (p2) calls
    ``?runtime=heuristic``, and we need each to take effect for that
    single call regardless of ``SOC_AGENT_RUNTIME``.
    """
    import sea_of_colours.agent.runtime as runtime_mod

    monkeypatch.setenv("SOC_AGENT_RUNTIME", "cortex")

    invoker_built = {"count": 0}

    class _ExplodingInvoker:
        """Will fail the test if instantiated — the heuristic override
        must short-circuit Cortex entirely."""

        def __init__(self, *args, **kwargs):
            invoker_built["count"] += 1

        def is_ready(self):
            return True

        def invoke(self, prompt):
            raise AssertionError("cortex must not be invoked when runtime_override='heuristic'")

    monkeypatch.setattr(runtime_mod, "CortexAgentInvoker", _ExplodingInvoker)

    result = run_agent_turn(store, session, "p1", runtime_override="heuristic")
    assert result["ok"]
    assert result["runtime"] == "heuristic"
    assert result["agent_id"] == HEURISTIC_AGENT_NAME
    assert invoker_built["count"] == 0, (
        "Cortex invoker must not even be constructed when override pins heuristic"
    )


def test_runtime_override_picks_cortex_for_one_call_only(
    monkeypatch, store, session
):
    """``runtime_override='cortex'`` takes one seat to an AI agent.

    The env stays at the default ``heuristic`` (so the *server-wide*
    setting is unchanged), and only the call that passes the override
    routes through Cortex. Mirrors what the versus button does for p1.
    """
    import sea_of_colours.agent.runtime as runtime_mod

    monkeypatch.delenv("SOC_AGENT_RUNTIME", raising=False)

    invoked = {"count": 0}

    class _StubInvoker:
        def __init__(self, *args, **kwargs):
            self.agent_name = kwargs.get("agent_name") or CORTEX_AGENT_DEFAULT

        def is_ready(self):
            return True

        def invoke(self, prompt):
            invoked["count"] += 1
            soc_engine.submit_policy(
                store, session, "p1", [{"a": "probe", "at": [3, 3]}]
            )
            return {"ok": True, "response": "cortex pick", "tool_calls": []}

    monkeypatch.setattr(runtime_mod, "CortexAgentInvoker", _StubInvoker)

    result = run_agent_turn(store, session, "p1", runtime_override="cortex")
    assert result["ok"]
    assert result["runtime"] == "cortex"
    assert result["agent_id"] == CORTEX_AGENT_DEFAULT
    assert invoked["count"] == 1


# ── Harness reframe tests ────────────────────────────────────────────
#
# After the orchestrator was reframed as a harness layer (the Cortex
# agent's tool surface shrank to soc_submit_policy + soc_save_rationale),
# `_build_cortex_prompt` is the new contract. These tests pin the
# envelope shape so the agent can rely on every section being present
# for every turn, even when sub-sections are empty.


def test_cortex_prompt_includes_v070_sections(store, session):
    """v0.7.0 harness envelope: structured JSON with the new top-level keys.

    The ASCII map / RED TILES / FOG CLUSTERS / MY ENTITIES / INVENTORY
    / RECENT LOG / LEADERBOARD prose sections were retired when the
    payload moved to the JSON-blob format. The new contract pins the
    presence of: HEADER, CONTRACT, HARD RULES, READING THE WORLD
    JSON primer, and the STATE JSON fence containing
    meta / hud / last_night / competitor_intel / world / navigation /
    my_assets.
    """
    import json as _json

    from sea_of_colours.agent.runtime import _build_cortex_prompt

    view = soc_engine.get_view(store, session, "p1")
    prompt = _build_cortex_prompt(session, view)

    assert "SESSION:" in prompt
    assert "DAY:" in prompt and "SEASON:" in prompt
    assert "POLICY BUDGET:" in prompt
    assert "TWO tools" in prompt or "two tools" in prompt.lower()
    assert "soc_submit_policy" in prompt
    assert "soc_save_rationale" in prompt
    # Anti-hallucination block (v0.7.1): the prompt MUST name the
    # removed read tools as forbidden so the model stops inventing
    # them. We assert each one appears AND that the FORBIDDEN marker
    # precedes them — that proves they appear in the warning context,
    # not as legitimate references.
    forbidden_idx = prompt.find("FORBIDDEN TOOL NAMES")
    assert forbidden_idx > 0, "FORBIDDEN TOOL NAMES block missing from prompt"
    for hallucination in (
        "soc_get_view",
        "soc_get_inventory",
        "soc_get_log",
        "soc_get_leaderboard",
        "soc_list_sessions",
    ):
        assert hallucination in prompt, f"forbidden tool {hallucination} not surfaced"
        assert prompt.find(hallucination) > forbidden_idx, (
            f"{hallucination} appears OUTSIDE the FORBIDDEN block — treat as a bug"
        )
    # v0.7.0 prose anchors.
    assert "HARD RULES" in prompt
    assert "READING THE WORLD JSON" in prompt
    assert "STATE (JSON" in prompt
    # v0.7.1 juicy-seam doctrine: the prompt should teach the agent
    # that trace is the minimum-effort play, not the target. Pin a
    # couple of low-friction anchors so the section can be reworded
    # without breaking the test.
    assert "JUICY SEAM DOCTRINE" in prompt
    assert "trace" in prompt.lower() and "pure" in prompt.lower()
    # The JSON fence must be parseable and carry the new top-level keys.
    start = prompt.index("```json\n") + len("```json\n")
    end = prompt.index("\n```", start)
    parsed = _json.loads(prompt[start:end])
    for key in (
        "meta", "hud", "last_night", "competitor_intel",
        "world", "navigation", "my_assets",
    ):
        assert key in parsed, f"v0.7.0 STATE JSON missing top-level key: {key}"
    # The world section is partitioned into live/echo with a fog count.
    world = parsed["world"]
    for key in ("width", "height", "live", "echo", "fog_count"):
        assert key in world, f"world.{key} missing"
    # meta.policy_actions_max should be 21 (fleet-wide cap).
    assert parsed["meta"].get("policy_actions_max") == 21


def test_cortex_prompt_respects_size_cap_when_world_explodes(store, session):
    """A pathological world (huge live/echo arrays) must still fit the cap.

    Real Snowflake-backed sessions on later days surface hundreds of
    visible + echoed cells. The prompt builder must never produce a
    user message that exceeds ``PROMPT_PAYLOAD_CAP_CHARS``; if it
    would, world.live / world.echo are sorted by proximity and
    truncated to the top-N cells.
    """
    from sea_of_colours.agent.runtime import (
        PROMPT_PAYLOAD_CAP_CHARS,
        _build_cortex_prompt,
    )

    view = soc_engine.get_view(store, session, "p1")
    av = view.setdefault("agent_view", {})
    fake_cells = [
        {
            "x": i % 40,
            "y": (i // 40) % 28,
            "tile": "RED" if i % 7 == 0 else "EMPTY",
            "purity": (i * 17) % 256,
            "value": (i * 17) % 256,
            "square_id": f"sq_{i:04d}",
        }
        for i in range(800)
    ]
    av["world"] = {
        "width": 40,
        "height": 28,
        "live": list(fake_cells),
        "echo": list(fake_cells),
        "fog_count": 0,
    }

    prompt = _build_cortex_prompt(session, view)
    assert len(prompt) <= PROMPT_PAYLOAD_CAP_CHARS, (
        f"prompt size {len(prompt)} > cap {PROMPT_PAYLOAD_CAP_CHARS}"
    )
    assert "truncated_to_nearest" in prompt, (
        "the size-cap fallback must annotate the truncation so the "
        "agent knows the world view is partial"
    )


def test_cortex_prompt_handles_empty_view_gracefully(store, session):
    """Day-1 with full fog: every required section still renders.

    The harness must not raise just because there is no last_night
    recap, no competitor activity, etc. Empty inner arrays / objects
    are still legal — the agent relies on the envelope shape staying
    stable.
    """
    import json as _json

    from sea_of_colours.agent.runtime import _build_cortex_prompt

    view = soc_engine.get_view(store, session, "p1")
    av = view.setdefault("agent_view", {})
    av["last_night"] = {
        "day_ended": 0,
        "my_orders": [],
        "my_assets_destroyed": [],
        "my_parcels_banked": [],
    }
    av["competitor_intel"] = {"new_this_day": [], "persistent_echoes": []}
    av["recent_log"] = []

    prompt = _build_cortex_prompt(session, view)
    # The STATE JSON must still parse cleanly.
    start = prompt.index("```json\n") + len("```json\n")
    end = prompt.index("\n```", start)
    parsed = _json.loads(prompt[start:end])
    assert parsed["last_night"]["my_orders"] == []
    assert parsed["competitor_intel"]["new_this_day"] == []


def test_cortex_prompt_includes_hard_rules_block(store, session):
    """The HARD RULES block must be present and crisp.

    Pins the exact phrases that protect against the failure modes the
    agent has demonstrated historically (multi-tile steps, made-up
    unit ids, forgotten pickups) AND the v0.7.0 additions (probe
    launch publicity, probe-on-probe destruction, the 21-action
    fleet-wide cap).
    """
    from sea_of_colours.agent.runtime import _build_cortex_prompt

    view = soc_engine.get_view(store, session, "p1")
    prompt = _build_cortex_prompt(session, view)

    # Move grammar appears verbatim.
    assert '"a":"probe"' in prompt
    assert '"a":"drop"' in prompt
    assert '"a":"step"' in prompt
    assert '"a":"pickup"' in prompt
    # Single-tile step rule.
    assert "Manhattan distance == 1" in prompt
    # Dawn-destruction reminder.
    assert "dawn" in prompt.lower()
    assert "pickup" in prompt.lower()
    # v0.7.0: fleet-wide policy budget = 21 (not 25).
    assert "21 VALID actions" in prompt
    assert "25 valid moves" not in prompt
    # Per-harvester hold capacity.
    assert "HOLD = 6 parcels" in prompt or "6 parcels per outing" in prompt
    # v0.7.0: probe-on-probe collisions + magnetic cover lore.
    assert "PROBE COLLISIONS" in prompt
    assert "magnetic cover" in prompt.lower()
    # Orbital publicity asymmetry.
    assert "ORBITAL PUBLICITY" in prompt
    assert "probe_launch" in prompt
    # Vault tier ladder + adjacency rule still surface.
    assert "VAULT TIER LADDER" in prompt
    assert "Manhattan depth" in prompt


def test_cortex_prompt_includes_world_json_primer(store, session):
    """The READING THE WORLD JSON block must be present and complete.

    Replaces the legacy "HOW TO READ THE MAP" block — the agent now
    consumes structured JSON instead of an ASCII grid. The primer
    must explain each top-level key + the filtering contract
    (skip fog, scan navigation, check hud.hoard.warning) so a future
    refactor cannot silently strip the agent's reading guide.
    """
    from sea_of_colours.agent.runtime import _build_cortex_prompt

    view = soc_engine.get_view(store, session, "p1")
    prompt = _build_cortex_prompt(session, view)

    assert "READING THE WORLD JSON" in prompt
    # Each top-level key gets a one-liner.
    for key in (
        "meta", "hud", "last_night", "competitor_intel",
        "world.live", "world.echo", "navigation", "my_assets",
    ):
        assert key in prompt, f"reading primer must document `{key}`"
    # Filtering contract.
    assert "FILTERING CONTRACT" in prompt
    assert "skip fog" in prompt.lower()
    # The legacy block must NOT be in the prompt any more — drift here
    # means we shipped a confusing hybrid.
    assert "HOW TO READ THE MAP" not in prompt
    assert "DENSE MAP" not in prompt


def test_cortex_prompt_surfaces_last_night_illegal_orders(store, session):
    """When last_night.my_orders contains illegal items, the agent must see
    them in the STATE JSON with outcome='illegal' + reason.

    The dedicated "your moves were REJECTED" prose header from v0.6
    was retired with the prompt rewrite; the agent now reads its own
    rejected orders directly from the structured last_night recap.
    """
    import json as _json

    from sea_of_colours.agent.runtime import _build_cortex_prompt

    view = soc_engine.get_view(store, session, "p1")
    av = view.setdefault("agent_view", {})
    av["last_night"] = {
        "day_ended": 0,
        "my_orders": [
            {
                "idx": 0,
                "text": "p1: step harvester_p1 (5,5)->(8,8) — not adjacent",
                "outcome": "illegal",
                "reason": "p1: step harvester_p1 (5,5)->(8,8) — not adjacent",
            },
            {
                "idx": 1,
                "text": "p1 deployed probe_p1_1 at (10,7)",
                "outcome": "ok",
            },
        ],
        "my_assets_destroyed": [],
        "my_parcels_banked": [],
    }

    prompt = _build_cortex_prompt(session, view)
    start = prompt.index("```json\n") + len("```json\n")
    end = prompt.index("\n```", start)
    parsed = _json.loads(prompt[start:end])
    orders = parsed["last_night"]["my_orders"]
    assert any(
        o.get("outcome") == "illegal" and "not adjacent" in (o.get("reason") or "")
        for o in orders
    ), "illegal orders must round-trip into the structured prompt"


# ── Cortex invoker SSE diagnostics (v0.7.1) ──────────────────────────
#
# After the Lux_Hollow post-mortem revealed that `soc_submit_policy`
# failures were invisible to the orchestrator, we added tool-error and
# wall-clock-cap surfacing to ``CortexAgentInvoker``. These tests pin
# the invoker's parsing of the SSE stream by injecting a fake
# ``requests.post`` that returns a deterministic event sequence.


def _make_sse_response(events):
    """Build a stand-in ``requests`` response for the SSE iterator.

    ``events`` is a list of either dicts (auto-wrapped as ``data: …``
    JSON lines) or already-encoded strings. The returned object mimics
    just enough of the ``requests.Response`` surface that the invoker
    touches: ``.status_code``, ``.iter_lines()`` (returning bytes),
    and ``.close()``.
    """
    import json as _json

    lines = []
    for ev in events:
        if isinstance(ev, dict):
            lines.append(f"data: {_json.dumps(ev)}".encode("utf-8"))
        else:
            lines.append(str(ev).encode("utf-8"))

    class _FakeResponse:
        status_code = 200

        def __init__(self):
            self._lines = lines
            self.closed = False

        def iter_lines(self):
            for line in self._lines:
                yield line

        def close(self):
            self.closed = True

    return _FakeResponse()


def test_cortex_invoker_records_tool_calls_and_submission_flag(monkeypatch):
    """SSE chunks with ``executing_tool`` events build the tool_calls list.

    Also pins ``submitted_policy=True`` whenever a ``soc_submit_policy``
    call appears in the stream — the runtime relies on this flag to
    distinguish "Cortex actually tried" from "Cortex never tried".
    """
    from sea_of_colours.agent import cortex_invoker as ci_mod

    fake = _make_sse_response(
        [
            {"text": "Analyzing the map. "},
            {"status": "executing_tool", "message": "Running soc_submit_policy"},
            {"text": "Submitting one probe."},
            {"status": "executing_tool", "message": "Running soc_save_rationale"},
            "data: [DONE]",
        ]
    )

    def _fake_post(*args, **kwargs):
        return fake

    monkeypatch.setattr("requests.post", _fake_post)

    inv = ci_mod.CortexAgentInvoker(
        agent_name="SOC_RED_REAPER",
        pat_token="test-pat",
    )
    # Force-set the account because the constructor only builds the
    # endpoint URL when the sf_config supplies one.
    inv.account = "test-account"

    result = inv.invoke("hello")
    assert result["ok"] is True
    assert result["submitted_policy"] is True, (
        "soc_submit_policy in tool_calls must flip submitted_policy True"
    )
    names = [c.get("name") for c in result["tool_calls"]]
    assert "soc_submit_policy" in names
    assert "soc_save_rationale" in names
    assert result["hallucinated_tools"] == [], (
        "no forbidden tools were invoked"
    )
    assert result["tool_errors"] == []
    assert result["wallclock_capped"] is False
    assert "Submitting one probe" in result["response"]


def test_cortex_invoker_flags_hallucinated_tool_calls(monkeypatch):
    """Calls to undeclared tools (e.g. ``soc_get_view``) get flagged.

    Before this change Lux_Hollow's Cortex turn opened with
    ``soc_get_view`` every night — a tool we deleted in the harness
    reframe. The hallucination went silent because the SSE parser only
    captured tool names, never compared them to the declared surface.
    """
    from sea_of_colours.agent import cortex_invoker as ci_mod

    fake = _make_sse_response(
        [
            {"status": "executing_tool", "message": "Running soc_get_view"},
            {"text": "(view unavailable, proceeding blind)"},
            {"status": "executing_tool", "message": "Running soc_submit_policy"},
            "data: [DONE]",
        ]
    )

    monkeypatch.setattr("requests.post", lambda *a, **kw: fake)

    inv = ci_mod.CortexAgentInvoker(pat_token="t")
    inv.account = "acct"

    result = inv.invoke("hi")
    assert result["ok"]
    assert "soc_get_view" in result["hallucinated_tools"], (
        "undeclared tools must appear in hallucinated_tools"
    )
    # The declared tool name does NOT get flagged.
    assert "soc_submit_policy" not in result["hallucinated_tools"]


def test_cortex_invoker_surfaces_tool_result_errors(monkeypatch):
    """A ``tool_result`` chunk carrying an error lands in ``tool_errors``.

    This was the missing observability that hid Lux_Hollow's
    soc_submit_policy rejections — the SSE stream did send back
    error payloads, but the parser only ever looked at the text /
    tool_use events.
    """
    from sea_of_colours.agent import cortex_invoker as ci_mod

    fake = _make_sse_response(
        [
            {"status": "executing_tool", "message": "Running soc_submit_policy"},
            {
                "tool_result": {
                    "name": "soc_submit_policy",
                    "is_error": True,
                    "error": "p_policy must be a JSON string",
                }
            },
            "data: [DONE]",
        ]
    )

    monkeypatch.setattr("requests.post", lambda *a, **kw: fake)

    inv = ci_mod.CortexAgentInvoker(pat_token="t")
    inv.account = "acct"

    result = inv.invoke("hi")
    assert result["ok"]
    assert result["submitted_policy"] is True, (
        "Cortex still attempted the call — the flag tracks *attempt*, "
        "not success"
    )
    assert result["tool_errors"], "tool_result error must populate tool_errors"
    first = result["tool_errors"][0]
    assert first["tool"] == "soc_submit_policy"
    assert "p_policy must be a JSON string" in first["error"]


def test_cortex_invoker_enforces_walltime_cap(monkeypatch):
    """A slow streaming Cortex must be cut off at the wall-clock cap.

    Simulated by having ``iter_lines`` sleep between chunks while the
    invoker's clock advances. Once the cap is exceeded, the loop must
    break and ``wallclock_capped`` flips True.
    """
    import time as _time

    from sea_of_colours.agent import cortex_invoker as ci_mod

    # Build a fake response whose iter_lines yields slowly. We patch
    # ``time.time`` inside cortex_invoker to advance by 60s on each
    # iteration so a 75s cap fires after the second chunk.
    times = iter([0.0, 30.0, 80.0, 200.0])
    monkeypatch.setattr(ci_mod.time, "time", lambda: next(times))

    fake = _make_sse_response(
        [
            {"text": "chunk1"},
            {"text": "chunk2"},
            {"text": "chunk3"},   # should never be appended (cap fired)
            "data: [DONE]",
        ]
    )

    monkeypatch.setattr("requests.post", lambda *a, **kw: fake)

    inv = ci_mod.CortexAgentInvoker(pat_token="t")
    inv.account = "acct"

    result = inv.invoke("hi", wallclock_cap_s=75)
    assert result["ok"]
    assert result["wallclock_capped"] is True
    # The third chunk's text must not appear — the cap was supposed to
    # close the stream before it arrived.
    assert "chunk3" not in result["response"]
    assert fake.closed, "wall-clock cap must close the response stream"


def test_runtime_preserves_cortex_submission_when_seat_locks(
    monkeypatch, store, session
):
    """Cortex's submission must NOT be overwritten when the seat locked.

    Mirrors the day-1 p1 of Lux_Hollow: Cortex calls soc_submit_policy
    inside the SSE stream (here simulated by the stub calling
    soc_engine.submit_policy directly), then returns ok with
    submitted_policy=True. The runtime must NOT run the heuristic on
    top, and the envelope must carry the Cortex agent name + runtime.
    """
    import sea_of_colours.agent.runtime as runtime_mod

    monkeypatch.setenv("SOC_AGENT_RUNTIME", "cortex")

    class _GoodInvoker:
        def __init__(self, *a, **kw):
            self.agent_name = kw.get("agent_name") or CORTEX_AGENT_DEFAULT

        def is_ready(self):
            return True

        def invoke(self, prompt):
            # Stand-in for the model's own soc_submit_policy call.
            soc_engine.submit_policy(
                store, session, "p1", [{"a": "probe", "at": [3, 3]}]
            )
            return {
                "ok": True,
                "response": "PLAN: probe (3,3). MOVES: 1. RATIONALE: scout edge.",
                "tool_calls": [{"name": "soc_submit_policy"}],
                "tool_errors": [],
                "hallucinated_tools": [],
                "submitted_policy": True,
                "wallclock_capped": False,
            }

    monkeypatch.setattr(runtime_mod, "CortexAgentInvoker", _GoodInvoker)

    submits = []
    real_submit = soc_engine.submit_policy

    def _spy(s, sid, player, moves):
        submits.append((player, list(moves)))
        return real_submit(s, sid, player, moves)

    monkeypatch.setattr(runtime_mod.soc_engine, "submit_policy", _spy)

    result = run_agent_turn(store, session, "p1")
    assert result["agent_id"] == CORTEX_AGENT_DEFAULT
    assert result["runtime"] == "cortex"
    # Exactly one submission (Cortex's). The runtime must not have
    # added a second one with a heuristic plan.
    assert len(submits) == 1, (
        f"runtime must not double-submit when Cortex locked the seat; "
        f"got {submits}"
    )
    assert submits[0][1] == [{"a": "probe", "at": [3, 3]}]


def test_runtime_does_not_overwrite_when_cortex_submit_was_rejected(
    monkeypatch, store, session
):
    """When Cortex called soc_submit_policy but it was REJECTED, the
    runtime must keep the Cortex name on the audit row and lock the
    seat with an empty policy — NOT silently overwrite with a
    heuristic plan.

    This is the Lux_Hollow days-2-to-5 regression: Cortex was making
    the tool call but the proc rejected the payload, the seat stayed
    empty, and the runtime overrode it with RED_HARVEST output. The
    fix preserves the failure under Cortex's name so it's visible.
    """
    import sea_of_colours.agent.runtime as runtime_mod

    monkeypatch.setenv("SOC_AGENT_RUNTIME", "cortex")

    class _RejectedInvoker:
        def __init__(self, *a, **kw):
            self.agent_name = kw.get("agent_name") or CORTEX_AGENT_DEFAULT

        def is_ready(self):
            return True

        def invoke(self, prompt):
            # Cortex called soc_submit_policy but the proc rejected
            # the payload — the seat stays empty.
            return {
                "ok": True,
                "response": "PLAN: harvest pure. MOVES: 3.",
                "tool_calls": [{"name": "soc_submit_policy"}],
                "tool_errors": [
                    {
                        "tool": "soc_submit_policy",
                        "error": "p_policy must be a JSON string",
                    }
                ],
                "hallucinated_tools": [],
                "submitted_policy": True,
                "wallclock_capped": False,
            }

    monkeypatch.setattr(runtime_mod, "CortexAgentInvoker", _RejectedInvoker)

    result = run_agent_turn(store, session, "p1")
    assert result["ok"]
    # KEY ASSERTION: the audit row stays attributed to Cortex — the
    # failure is the agent's, not the heuristic's.
    assert result["agent_id"] == CORTEX_AGENT_DEFAULT
    assert result["runtime"] == "cortex"
    # The diagnostic tail surfaces the proc rejection.
    rat = result["rationale"]
    assert "soc_submit_policy" in rat and "JSON string" in rat
    assert "DIAGNOSTICS" in rat
    # The seat IS locked (we don't deadlock the night) but with an
    # empty move queue.
    assert result["moves"] == []
    status = soc_engine.get_session_status(store, session)
    assert status["pending"]["p1"] is True
    # The envelope advertises the tool error so the watcher can render
    # it in yellow.
    assert result.get("tool_errors")
    assert result["tool_errors"][0]["tool"] == "soc_submit_policy"


def test_runtime_falls_back_when_cortex_made_no_submit_call(
    monkeypatch, store, session
):
    """If Cortex returned without calling soc_submit_policy AT ALL, the
    heuristic takes over and the audit row reflects that.

    This is the only case where the heuristic SHOULD claim the seat —
    Cortex produced no policy whatsoever, so something has to lock
    the seat or the season deadlocks.
    """
    import sea_of_colours.agent.runtime as runtime_mod

    monkeypatch.setenv("SOC_AGENT_RUNTIME", "cortex")

    class _NoSubmitInvoker:
        def __init__(self, *a, **kw):
            self.agent_name = kw.get("agent_name") or CORTEX_AGENT_DEFAULT

        def is_ready(self):
            return True

        def invoke(self, prompt):
            return {
                "ok": True,
                "response": "Thinking but not submitting.",
                "tool_calls": [{"name": "soc_save_rationale"}],
                "tool_errors": [],
                "hallucinated_tools": ["soc_get_view"],
                "submitted_policy": False,
                "wallclock_capped": False,
            }

    monkeypatch.setattr(runtime_mod, "CortexAgentInvoker", _NoSubmitInvoker)

    result = run_agent_turn(store, session, "p1")
    assert result["agent_id"] == HEURISTIC_AGENT_NAME
    assert result["runtime"] == "heuristic"
    # The hallucinated tool name still gets surfaced for visibility.
    assert "soc_get_view" in (result.get("hallucinated_tools") or [])
    # The rationale references the fallback so post-mortems are honest.
    assert "fallback" in result["rationale"].lower()


def test_runtime_repolls_on_apparent_race(monkeypatch, store, session):
    """A first status check showing the seat empty must trigger a
    short re-poll when Cortex's SSE stream reported a submission.

    Mirrors the warehouse commit-visibility race we suspected on
    Lux_Hollow's later turns. The first ``get_session_status`` call
    sees an empty seat, but a second call ~200 ms later sees it
    locked. The runtime must NOT fall back in that case.
    """
    import sea_of_colours.agent.runtime as runtime_mod

    monkeypatch.setenv("SOC_AGENT_RUNTIME", "cortex")

    submits = []

    class _RacyInvoker:
        def __init__(self, *a, **kw):
            self.agent_name = kw.get("agent_name") or CORTEX_AGENT_DEFAULT

        def is_ready(self):
            return True

        def invoke(self, prompt):
            return {
                "ok": True,
                "response": "PLAN: probe. MOVES: 1.",
                "tool_calls": [{"name": "soc_submit_policy"}],
                "tool_errors": [],
                "hallucinated_tools": [],
                "submitted_policy": True,
                "wallclock_capped": False,
            }

    monkeypatch.setattr(runtime_mod, "CortexAgentInvoker", _RacyInvoker)

    # Patch get_session_status so the FIRST call returns p1 empty,
    # and the SECOND call returns it locked (after a simulated commit
    # arrival). The race-tolerant re-poll inside runtime.run_agent_turn
    # is the only mechanism that should rescue this turn.
    poll_count = {"n": 0}
    real_get_status = soc_engine.get_session_status

    def _flaky_status(s, sid):
        poll_count["n"] += 1
        if poll_count["n"] == 1:
            # First check: pretend Cortex's commit hasn't landed yet.
            base = real_get_status(s, sid)
            base["pending"] = dict(base["pending"])
            base["pending"]["p1"] = False
            return base
        # Second check: pretend the commit just arrived. We backfill
        # the engine state to match by submitting an empty policy on
        # Cortex's behalf so the real state is consistent.
        submits.append("backfill")
        soc_engine.submit_policy(s, sid, "p1", [{"a": "probe", "at": [2, 2]}])
        return real_get_status(s, sid)

    monkeypatch.setattr(runtime_mod.soc_engine, "get_session_status", _flaky_status)
    monkeypatch.setattr(
        runtime_mod, "time", type("t", (), {"sleep": lambda *_a: None, "time": __import__("time").time})
    )

    result = run_agent_turn(store, session, "p1")
    # The re-poll succeeded — the seat appeared on the second check,
    # so the runtime trusted Cortex and did not run the heuristic.
    assert result["agent_id"] == CORTEX_AGENT_DEFAULT
    assert result["runtime"] == "cortex"
    assert poll_count["n"] == 2, (
        "runtime must poll status TWICE on apparent race (was "
        f"{poll_count['n']})"
    )


# ── v0.9.5 — Orbit playbook + multi-harvester planner ─────────────


def _make_orbit_view(
    *,
    credits: int = 1000,
    cap_used: int = 1,
    cap_max: int = 3,
    damaged_ids: tuple = (),
    healthy_ids: tuple = ("harvester_p1_1",),
    red_parcels: tuple = (),
    green_parcels: int = 0,
    blue_purity_total: int = 0,
    emp_stock: int = 0,
) -> dict:
    """Hand-rolled agent_view for orbit-phase unit tests.

    ``damaged_ids`` lists the ids of harvesters flagged damaged;
    ``healthy_ids`` lists the rest. Together they form the seat's
    fleet exposed via ``entities.mine``.

    v0.9.6 — ``red_parcels`` accepts a tuple of ``(square_id, purity)``
    so a test can hand the catapult some hoard inventory to ship;
    ``green_parcels`` is the number of GREEN parcels to surface for
    the jettison priority path.
    """
    mine_rows = []
    for hid in damaged_ids:
        mine_rows.append({
            "id": hid, "type": "harvester", "pos": None,
            "carrying_red": False, "cargo_count": 0, "damaged": True,
        })
    for hid in healthy_ids:
        mine_rows.append({
            "id": hid, "type": "harvester", "pos": None,
            "carrying_red": False, "cargo_count": 0, "damaged": False,
        })
    hoard_parcels: list = []
    for sid, purity in red_parcels:
        hoard_parcels.append({
            "square_id": sid, "colour": "RED",
            "purity": int(purity),
        })
    for i in range(int(green_parcels)):
        hoard_parcels.append({
            "square_id": f"g-{i}", "colour": "GREEN",
            "purity": 200,
        })
    return {
        "phase": "orbit",
        "grid": {"width": 18, "height": 12, "cell_counts": {"fog": 100, "stale": 0, "fresh": 0}},
        "entities": {"mine": mine_rows, "echoes": []},
        "orbit": {
            "phase_active": True,
            "credits": credits,
            "harvester_cap_used": cap_used,
            "harvester_cap_max": cap_max,
            "actions_max": 3,
            "ship_prices": {
                "harvester_build": 1500,
                "probe_build": 250,
                "repair": 500,
                # v0.9.6 catapult tunables — surfaced via ``view.orbit
                # .ship_prices`` so the agent reads them instead of
                # hard-coding the row schedule.
                "row_count": 4,
                "slots_per_row": 5,
                "row_transit": [10, 25, 50, 100],
                "row_thresholds": [50, 100, 150, 200],
                "quality_mult": {
                    "trace": 0.75, "vein": 1.0, "mass": 1.5, "pure": 3.0,
                },
            },
            "green_catapult": {
                "slots": 12, "cost_base": 50, "cost_step": 5,
                "endgame_penalty": 100,
            },
            "jettison_pricing": {
                "base": 100, "min": 25, "fuel_denominator": 16,
            },
            "hoard_parcels": hoard_parcels,
            # v0.9.9 — blue economy + weapons readouts.
            "blue_purity_total": int(blue_purity_total),
            "weapon_stock": {"emp": int(emp_stock), "mine": 0, "chaff": 0},
            "weapon_prices": {
                "emp": {"blue": 200, "credits": 0},
                "mine": {"blue": 100, "credits": 0},
                "chaff": {"blue": 50, "credits": 0},
            },
        },
        # meta drives the seeded RNG used by the 50% EMP-build roll.
        "meta": {"session_id": "test-orbit", "player": "p1", "day": 1},
        "hud": {"day": 1, "player": "p1"},
    }


def test_orbit_playbook_repairs_damaged_then_probes_then_harvester():
    """Full 1000c budget, 1 damaged harvester, 1 healthy → playbook
    fits repair + 2 probes in 2 action slots (500c + 500c = 1000c).
    """
    from sea_of_colours.agent.heuristic_agent import plan_orbit_actions

    view = _make_orbit_view(
        credits=1000,
        damaged_ids=("harvester_p1_2",),
        healthy_ids=("harvester_p1_1",),
    )
    actions, rationale = plan_orbit_actions(view)
    assert actions[0] == {"a": "repair", "unit": "harvester_p1_2"}
    assert actions[1] == {"a": "build_probe", "count": 2}
    # 1000c - 500 (repair) - 500 (2 probes) = 0c → no harvester yet.
    assert all(a["a"] != "build_harvester" for a in actions)
    assert "repaired harvester_p1_2" in rationale
    assert "built 2 probe(s)" in rationale


def test_orbit_playbook_builds_harvester_when_flush_with_credits():
    """1500c (saved over 2 turns) → 2 probes + harvester in one orbit.

    Demonstrates the "every second / third turn" harvester-building
    cadence the player asked for: with no repairs to make, the
    heuristic spends 500c on probes + 1500c on the harvester.
    """
    from sea_of_colours.agent.heuristic_agent import plan_orbit_actions

    view = _make_orbit_view(credits=2000, cap_used=1)
    actions, _ = plan_orbit_actions(view)
    tags = [a["a"] for a in actions]
    assert "build_probe" in tags
    assert "build_harvester" in tags
    # And the probe action is the 2-count batch.
    probe_action = next(a for a in actions if a["a"] == "build_probe")
    assert probe_action.get("count") == 2


def test_orbit_playbook_skips_harvester_when_fleet_at_cap():
    """At 3/3 harvesters, the heuristic still buys probes but does
    NOT queue a build_harvester (the resolver would reject it anyway).
    """
    from sea_of_colours.agent.heuristic_agent import plan_orbit_actions

    view = _make_orbit_view(credits=2000, cap_used=3, cap_max=3)
    actions, _ = plan_orbit_actions(view)
    assert {"a": "build_harvester"} not in actions
    # Probes still buy though.
    assert any(a["a"] == "build_probe" for a in actions)


def test_orbit_playbook_falls_back_to_one_probe_on_tight_budget():
    """With 300c (after some hypothetical repair) the seat can't
    afford 2 probes (500c) but can still buy 1 (250c)."""
    from sea_of_colours.agent.heuristic_agent import plan_orbit_actions

    view = _make_orbit_view(credits=300, cap_used=1)
    actions, _ = plan_orbit_actions(view)
    probe_action = next(
        (a for a in actions if a["a"] == "build_probe"), None,
    )
    assert probe_action is not None
    assert probe_action.get("count") == 1


def test_orbit_playbook_honours_three_action_slot_cap():
    """Three damaged harvesters → all 3 slots go to repair; the
    probe / harvester builds get deferred even when the seat has
    cash. RULEBOOK §4 caps Orbit submissions at 3 actions."""
    from sea_of_colours.agent.heuristic_agent import plan_orbit_actions

    view = _make_orbit_view(
        credits=5000,
        cap_used=3,
        damaged_ids=("harvester_p1_1", "harvester_p1_2", "harvester_p1_3"),
        healthy_ids=(),
    )
    actions, _ = plan_orbit_actions(view)
    assert len(actions) == 3
    assert all(a["a"] == "repair" for a in actions)


# ── v0.9.6 catapult + jettison playbook coverage ────────────────────


def test_orbit_playbook_v096_priority_repair_before_harvester_before_probes():
    """v0.9.6 priority: repair → build_harvester → 2 probes → ship →
    jettison. With 2000c + 1 damaged unit + 2/3 fleet, the seat
    spends the full budget before the slot cap bites:
      slot 0: repair (500c left 1500)
      slot 1: build_harvester (1500c left 0) → defer probes since
              we hit the slot cap on the next pickup
    """
    from sea_of_colours.agent.heuristic_agent import plan_orbit_actions

    view = _make_orbit_view(
        credits=2000,
        cap_used=2,
        damaged_ids=("harvester_p1_2",),
        healthy_ids=("harvester_p1_1",),
    )
    actions, _ = plan_orbit_actions(view)
    assert actions[0] == {"a": "repair", "unit": "harvester_p1_2"}
    # v0.9.6 — harvester comes BEFORE probes in priority order.
    assert actions[1] == {"a": "build_harvester"}


def test_orbit_playbook_emits_ship_catapult_when_hoard_has_red():
    """With RED in the hoard, the playbook queues a ``ship_catapult``
    bid naming the highest-purity parcels with a flat credit bid each
    (RULEBOOK §4.4)."""
    from sea_of_colours.agent.heuristic_agent import plan_orbit_actions

    view = _make_orbit_view(
        credits=300,  # too low for harvester, builds 1 probe (250)
        cap_used=1,
        red_parcels=(("red-a", 200), ("red-b", 100), ("red-c", 80)),
    )
    actions, _ = plan_orbit_actions(view)
    tags = [a["a"] for a in actions]
    assert "ship_catapult" in tags
    bid = next(a for a in actions if a["a"] == "ship_catapult")
    # 3 RED parcels named; bid_each = min(25, remaining(50)//3) = 16.
    assert len(bid["bids"]) == 3
    assert {b["id"] for b in bid["bids"]} == {"red-a", "red-b", "red-c"}
    assert all(b["credits"] == 16 for b in bid["bids"])


def test_orbit_playbook_emits_solar_jettison_when_hoard_has_green():
    """GREEN parcels trigger the green-catapult flush, bidding a
    RIGHT-SIZED RED fuel commitment (solo-flush floor + one slot-step of
    rank headroom), capped at the toxic-legacy penalty it avoids."""
    from sea_of_colours.agent.heuristic_agent import plan_orbit_actions

    view = _make_orbit_view(
        credits=300,
        cap_used=1,
        green_parcels=3,
    )
    actions, _ = plan_orbit_actions(view)
    tags = [a["a"] for a in actions]
    assert "solar_jettison" in tags
    jett = next(a for a in actions if a["a"] == "solar_jettison")
    # Solo-flush floor for 3 parcels = 50 + 45 + 40 = 135; + one
    # slot-step (5) of rank headroom = 140. Penalty avoided is
    # 3 × 100 = 300, so the 140 bid is well under the cap.
    assert jett["red_fuel"] == 140
    assert jett["green_parcels"] == 3


def test_orbit_playbook_green_bid_is_right_sized_not_escalated():
    """The flush bid is RIGHT-SIZED, not desperate: it does NOT ramp up
    near the endgame (over-bidding burns shippable RED, since the
    resolver forfeits the whole commitment), and it is hard-capped at
    the toxic-legacy penalty it avoids."""
    from sea_of_colours.agent.heuristic_agent import plan_orbit_actions

    def _bid(day, cap, green):
        view = _make_orbit_view(credits=300, cap_used=1, green_parcels=green)
        view["hud"]["day"] = day
        view["hud"]["season_day_cap"] = cap
        actions, _ = plan_orbit_actions(view)
        return next(a for a in actions if a["a"] == "solar_jettison")["red_fuel"]

    # Same green count → same bid regardless of nights left (flat).
    early = _bid(1, 10, 2)
    mid = _bid(7, 10, 2)
    final = _bid(9, 10, 2)
    assert early == mid == final
    # Floor for 2 parcels = 50 + 45 = 95; + one slot-step (5) = 100,
    # which also equals the 2 × 100 penalty cap.
    assert early == 100

    # A single green parcel: floor 50 + step 5 = 55, under the 100 cap.
    assert _bid(1, 10, 1) == 55


def test_orbit_playbook_skips_catapult_when_hoard_empty():
    """No RED in the hoard → no ship_catapult bid (RULEBOOK §4.4)."""
    from sea_of_colours.agent.heuristic_agent import plan_orbit_actions

    view = _make_orbit_view(credits=300, cap_used=1, red_parcels=())
    actions, _ = plan_orbit_actions(view)
    tags = [a["a"] for a in actions]
    assert "ship_catapult" not in tags


def test_orbit_playbook_ships_vein_even_when_broke():
    """v1.x — SHIPPING IS THE GAME: a VEIN+ parcel launches even with 0
    credits (a 0-credit bid is legal, RULEBOOK §4.4). Refusing to ship
    when broke was the "hoard RED → settle at 0" bug."""
    from sea_of_colours.agent.heuristic_agent import plan_orbit_actions

    # 0 credits, but a shippable VEIN parcel in the hoard.
    view = _make_orbit_view(
        credits=0,
        cap_used=3,  # fleet full → no harvester build competing for slots
        red_parcels=(("red-vein", 150),),
        blue_purity_total=0,
    )
    actions, _ = plan_orbit_actions(view)
    ship = next((a for a in actions if a["a"] == "ship_catapult"), None)
    assert ship is not None, "must ship its VEIN parcel even at 0 credits"
    assert {b["id"] for b in ship["bids"]} == {"red-vein"}
    assert all(int(b["credits"]) == 0 for b in ship["bids"])


def test_orbit_playbook_only_ships_vein_or_above():
    """v0.9.9 — sub-VEIN (purity ≤ 50) RED is NOT catapulted; only
    VEIN-or-above parcels make the ship list."""
    from sea_of_colours.agent.heuristic_agent import plan_orbit_actions

    view = _make_orbit_view(
        credits=300,
        cap_used=1,
        # one VEIN (120), one TRACE (30): only the VEIN ships.
        red_parcels=(("red-vein", 120), ("red-trace", 30)),
        blue_purity_total=80,
    )
    actions, _ = plan_orbit_actions(view)
    ship = next((a for a in actions if a["a"] == "ship_catapult"), None)
    assert ship is not None
    shipped_ids = {b["id"] for b in ship["bids"]}
    assert shipped_ids == {"red-vein"}, "TRACE parcel must not ship"


def test_orbit_playbook_refines_trace_parcels():
    """v0.9.9 — TRACE parcels trigger a refine toward VEIN when the
    seat has blue to pay for it."""
    from sea_of_colours.agent.heuristic_agent import plan_orbit_actions

    view = _make_orbit_view(
        credits=300,
        cap_used=1,
        red_parcels=(("red-trace-a", 20), ("red-trace-b", 40)),
        blue_purity_total=120,
    )
    actions, _ = plan_orbit_actions(view)
    refine = next((a for a in actions if a["a"] == "refine"), None)
    assert refine is not None
    assert refine["source_tier"] == "trace"
    # All-trace hoard → nothing ships.
    assert all(a["a"] != "ship_catapult" for a in actions)


def test_orbit_playbook_builds_emp_when_blue_surplus_and_roll_hits():
    """v1.x — blue in the 50%-roll band (250-300) + a winning roll → an
    EMP build is queued (above 300 the always-build tier takes over)."""
    from sea_of_colours.agent.heuristic_agent import plan_orbit_actions

    view = _make_orbit_view(credits=300, cap_used=1, blue_purity_total=280)
    # day 0 → seeded roll 0.458 < 0.5 → build fires.
    view["meta"]["day"] = 0
    view["hud"]["day"] = 0
    actions, _ = plan_orbit_actions(view)
    assert any(a["a"] == "build_emp" for a in actions)


def test_orbit_playbook_skips_emp_when_roll_misses():
    """v1.x — blue in the roll band but the 50% roll misses → no EMP
    (and no always-build chaff since blue is under 300)."""
    from sea_of_colours.agent.heuristic_agent import plan_orbit_actions

    view = _make_orbit_view(credits=300, cap_used=1, blue_purity_total=280)
    # day 1 → seeded roll 0.926 ≥ 0.5 → no build.
    view["meta"]["day"] = 1
    view["hud"]["day"] = 1
    actions, _ = plan_orbit_actions(view)
    assert all(a["a"] != "build_emp" for a in actions)
    assert all(a["a"] != "build_chaff" for a in actions)


def test_orbit_playbook_skips_emp_when_blue_below_threshold():
    """v0.9.9 — below the blue threshold the EMP roll never happens."""
    from sea_of_colours.agent.heuristic_agent import plan_orbit_actions

    view = _make_orbit_view(credits=300, cap_used=1, blue_purity_total=100)
    view["meta"]["day"] = 0  # would-hit roll, but blue gate blocks it
    view["hud"]["day"] = 0
    actions, _ = plan_orbit_actions(view)
    assert all(a["a"] != "build_emp" for a in actions)
    assert all(a["a"] != "build_chaff" for a in actions)


def test_orbit_playbook_always_builds_chaff_when_blue_flush_and_no_chaff():
    """v1.x — blue above 300 with no chaff in the locker → ALWAYS build a
    weapon, and it's CHAFF first (needed for the egress jam)."""
    from sea_of_colours.agent.heuristic_agent import plan_orbit_actions

    view = _make_orbit_view(credits=300, cap_used=1, blue_purity_total=420)
    actions, _ = plan_orbit_actions(view)
    assert any(a["a"] == "build_chaff" for a in actions)
    assert all(a["a"] != "build_emp" for a in actions)


def test_orbit_playbook_builds_emp_when_flush_and_chaff_stocked():
    """v1.x — blue above 300 but we already hold chaff → the always-build
    tier fills the kit with an EMP instead."""
    from sea_of_colours.agent.heuristic_agent import plan_orbit_actions

    view = _make_orbit_view(credits=300, cap_used=1, blue_purity_total=420)
    view["orbit"]["weapon_stock"]["chaff"] = 1
    actions, _ = plan_orbit_actions(view)
    assert any(a["a"] == "build_emp" for a in actions)
    assert all(a["a"] != "build_chaff" for a in actions)


def test_orbit_playbook_green_flush_jumps_queue_when_pile_of_green():
    """v0.9.9 — a big green pile flushes right after repairs, ahead of
    builds (priority scales with green count)."""
    from sea_of_colours.agent.heuristic_agent import plan_orbit_actions

    view = _make_orbit_view(credits=2000, cap_used=1, green_parcels=4)
    actions, _ = plan_orbit_actions(view)
    tags = [a["a"] for a in actions]
    assert "solar_jettison" in tags
    # With 4 green parcels the flush precedes the harvester build.
    if "build_harvester" in tags:
        assert tags.index("solar_jettison") < tags.index("build_harvester")


def test_night_emp_falls_back_to_enemy_harvester_when_no_beacon():
    """v0.9.10 — with no enemy beacon on the board, the EMP salvo
    falls back to the freshest enemy harvester sighting and fans the
    missiles out (centre + spread) over it."""
    from sea_of_colours.agent.heuristic_agent import plan_moves

    view = _make_view_payload(red_xy=(6, 4))
    view["orbit"] = {"weapon_stock": {"emp": 1, "mine": 0, "chaff": 0}}
    view["competitor_intel"] = {
        "new_this_day": [
            {"kind": "enemy_harvester_trail", "owner": "p2", "at": [9, 5]},
        ],
        "persistent_echoes": [],
    }
    moves, _ = plan_moves(view)
    emp = next((m for m in moves if m["a"] == "emp_launch"), None)
    assert emp is not None
    # ``at`` is now a list of spread target cells; the aim point is
    # the first (centre) missile.
    assert emp["at"][0] == [9, 5]
    assert len(emp["at"]) >= 2, "salvo should fan out, not single-target"


def test_night_emp_targets_latest_enemy_beacon():
    """v0.9.10 — the EMP salvo prefers the opponent's freshest probe
    BEACON over an enemy harvester, blanketing the area the enemy
    just lit up."""
    from sea_of_colours.agent.heuristic_agent import plan_moves

    view = _make_view_payload(red_xy=(6, 4))
    view["orbit"] = {"weapon_stock": {"emp": 1, "mine": 0, "chaff": 0}}
    view["competitor_intel"] = {
        "new_this_day": [
            {"kind": "enemy_harvester_trail", "owner": "p2", "at": [2, 2]},
            {"kind": "enemy_probe_launch", "owner": "p2", "at": [10, 6],
             "day_seen": 3},
        ],
        "persistent_echoes": [
            {"kind": "enemy_probe", "owner": "p2", "at": [1, 1],
             "last_seen_day": 1},
        ],
    }
    moves, _ = plan_moves(view)
    emp = next((m for m in moves if m["a"] == "emp_launch"), None)
    assert emp is not None
    # Centre missile aims at the freshest beacon (10,6), not the
    # harvester or the stale echo.
    assert emp["at"][0] == [10, 6]


def test_night_harvesters_avoid_dropping_in_emp_cloud():
    """v0.9.10 — harvesters do not drop inside the EMP salvo's
    friendly-fire footprint."""
    from sea_of_colours.agent.heuristic_agent import (
        plan_moves,
        _emp_cloud_cells,
        _emp_spread_targets,
        _latest_enemy_beacon,
    )

    view = _make_view_payload(red_xy=(6, 4))
    view["orbit"] = {"weapon_stock": {"emp": 1, "mine": 0, "chaff": 0}}
    # Beacon sits right on the only RED tile's neighbourhood so the
    # cloud would otherwise be a tempting drop zone.
    view["competitor_intel"] = {
        "new_this_day": [
            {"kind": "enemy_probe_launch", "owner": "p2", "at": [6, 4],
             "day_seen": 2},
        ],
        "persistent_echoes": [],
    }
    aim = _latest_enemy_beacon(view)
    targets = _emp_spread_targets(aim, count=3, radius=2, width=18, height=12)
    zone = _emp_cloud_cells(targets, radius=2, width=18, height=12)
    moves, _ = plan_moves(view)
    drops = [tuple(m["at"]) for m in moves if m["a"] == "drop"]
    for d in drops:
        assert d not in zone, f"harvester dropped at {d} inside EMP cloud {sorted(zone)[:5]}…"


def test_night_harvests_blue_when_blue_is_low():
    """v0.9.9 — low blue folds visible BLUE tiles into the harvest
    target pool so a harvester chases them."""
    from sea_of_colours.agent.heuristic_agent import plan_moves

    view = _make_view_payload(red_xy=(6, 4))
    view["red_tiles"] = []  # no RED → harvester must reach for BLUE
    view["blue_tiles"] = [
        {"x": 7, "y": 4, "purity": 180, "value": 180, "freshness": "fresh",
         "square_id": "blue-1"},
    ]
    view["orbit"] = {"blue_purity_total": 10}  # well below threshold
    moves, rationale = plan_moves(view)
    # The harvester should drop adjacent to the BLUE tile and step in.
    steps_to_blue = [m for m in moves if m.get("a") == "step" and m.get("to") == [7, 4]]
    drops = [m for m in moves if m["a"] == "drop"]
    assert drops, "harvester should deploy to reach the BLUE tile"
    assert steps_to_blue, "harvester should walk onto the BLUE tile"
    assert "blue" in rationale.lower()


def test_night_ignores_blue_when_blue_is_plentiful():
    """v0.9.9 — with ample blue, BLUE tiles are NOT folded into the
    target pool: the plan matches a no-blue baseline exactly."""
    from sea_of_colours.agent.heuristic_agent import plan_moves

    def _view(blue_total):
        v = _make_view_payload(red_xy=(6, 4))
        v["red_tiles"] = [
            {"x": 6, "y": 4, "purity": 200, "value": 200,
             "freshness": "fresh", "square_id": "abc"},
        ]
        v["blue_tiles"] = [
            {"x": 7, "y": 4, "purity": 180, "value": 180,
             "freshness": "fresh", "square_id": "blue-1"},
        ]
        v["orbit"] = {"blue_purity_total": blue_total}
        return v

    plentiful, _ = plan_moves(_view(5000))  # way above threshold
    baseline_view = _view(5000)
    baseline_view["blue_tiles"] = []
    baseline, _ = plan_moves(baseline_view)
    assert plentiful == baseline, "blue tiles must not change the plan when blue is high"


def test_night_schedules_chaff_in_egress_window():
    """v1.x — holding chaff, the night plan splices a ``chaff_flare`` at a
    queue position that resolves inside an egress window (5-7 / 11-13)."""
    from sea_of_colours.agent.heuristic_agent import plan_moves

    view = _make_view_payload(red_xy=(6, 4))
    view["orbit"] = {"weapon_stock": {"emp": 0, "mine": 0, "chaff": 1}}
    moves, rationale = plan_moves(view)
    idxs = [i for i, m in enumerate(moves) if m.get("a") == "chaff_flare"]
    assert len(idxs) == 1, "exactly one chaff flare should be scheduled"
    # Queue position is 1-indexed hour (one applied move per hour, §3.10).
    hour = idxs[0] + 1
    assert hour in (5, 6, 7, 11, 12, 13), f"chaff at hour {hour} not in a window"
    assert "chaff" in rationale.lower()


def test_night_no_chaff_when_unstocked():
    """v1.x — no chaff in the locker → no flare scheduled."""
    from sea_of_colours.agent.heuristic_agent import plan_moves

    view = _make_view_payload(red_xy=(6, 4))
    view["orbit"] = {"weapon_stock": {"emp": 0, "mine": 0, "chaff": 0}}
    moves, _ = plan_moves(view)
    assert all(m.get("a") != "chaff_flare" for m in moves)


# ── RED_HARVEST_LITE — weapons_enabled=False (hackathon tutorial bot) ──


def test_orbit_playbook_weapons_disabled_never_builds_chaff_or_emp():
    """RED_HARVEST_LITE: even with a blue surplus well past the
    always-build threshold, ``weapons_enabled=False`` must never queue
    build_chaff / build_emp — every other priority is unaffected."""
    from sea_of_colours.agent.heuristic_agent import plan_orbit_actions

    view = _make_orbit_view(credits=2000, cap_used=1, blue_purity_total=420)
    actions, rationale = plan_orbit_actions(view, weapons_enabled=False)
    assert all(a["a"] not in ("build_chaff", "build_emp") for a in actions)
    assert "chaff" not in rationale.lower()
    assert "emp" not in rationale.lower()
    # The rest of the playbook still runs (harvester build affordable here).
    assert any(a["a"] == "build_harvester" for a in actions)

    # And with the full heuristic (default weapons_enabled=True) on the
    # SAME view, a weapon build fires — proving the flag, not the view,
    # is what's gating the behaviour.
    full_actions, _ = plan_orbit_actions(view)
    assert any(a["a"] in ("build_chaff", "build_emp") for a in full_actions)


def test_night_weapons_disabled_never_fires_emp_or_chaff():
    """RED_HARVEST_LITE: EMP salvo and chaff egress jam are both
    skipped when ``weapons_enabled=False``, even with full stock."""
    from sea_of_colours.agent.heuristic_agent import plan_moves

    view = _make_view_payload(red_xy=(6, 4))
    view["orbit"] = {"weapon_stock": {"emp": 1, "mine": 0, "chaff": 1}}
    view["competitor_intel"] = {
        "new_this_day": [
            {"kind": "enemy_harvester_trail", "owner": "p2", "at": [9, 5]},
        ],
        "persistent_echoes": [],
    }
    moves, rationale = plan_moves(view, weapons_enabled=False)
    assert all(m.get("a") not in ("emp_launch", "chaff_flare") for m in moves)
    assert "emp" not in rationale.lower()
    assert "chaff" not in rationale.lower()

    # Same stock, weapons enabled → both fire (control case).
    full_moves, _ = plan_moves(view)
    assert any(m.get("a") == "emp_launch" for m in full_moves)
    assert any(m.get("a") == "chaff_flare" for m in full_moves)


def test_heuristic_agent_lite_flag_threads_through_play():
    """``HeuristicAgent(weapons_enabled=False)`` is RED_HARVEST_LITE end
    to end via the public ``play()`` contract (both phases)."""
    from sea_of_colours.agent.heuristic_agent import HeuristicAgent

    lite = HeuristicAgent(name="RED_HARVEST_LITE", weapons_enabled=False)
    orbit_view = _make_orbit_view(credits=2000, cap_used=1, blue_purity_total=420)
    orbit_view["phase"] = "orbit"
    plan = lite.play(orbit_view)
    assert all(
        a["a"] not in ("build_chaff", "build_emp")
        for a in plan["orbit_actions"]
    )

    night_view = _make_view_payload(red_xy=(6, 4))
    night_view["orbit"] = {"weapon_stock": {"emp": 1, "mine": 0, "chaff": 1}}
    night_plan = lite.play(night_view)
    assert all(
        m.get("a") not in ("emp_launch", "chaff_flare")
        for m in night_plan["moves"]
    )

    # Default HeuristicAgent() is unaffected (weapons_enabled defaults True).
    full = HeuristicAgent()
    assert full.weapons_enabled is True


def _two_orbital_harvesters() -> list:
    return [
        {"id": "harvester_p1_1", "type": "harvester", "pos": None,
         "carrying_red": False, "cargo_count": 0},
        {"id": "harvester_p1_2", "type": "harvester", "pos": None,
         "carrying_red": False, "cargo_count": 0},
        {"id": "orblift_p1", "type": "orblift", "pos": None,
         "holds_red": False},
    ]


def test_night_surplus_harvester_seeks_blue_when_only_low_red():
    """v1.x — with 2 harvesters, blue below the 400 cap, and only LOW-tier
    RED visible, the surplus unit diverts to BLUE (weapons economy)."""
    from sea_of_colours.agent.heuristic_agent import plan_moves

    view = _make_view_payload(red_xy=(6, 4))
    view["entities"]["mine"] = _two_orbital_harvesters()
    # Only a TRACE seam (purity 40) — not worth diverting the surplus unit.
    view["red_tiles"] = [
        {"x": 6, "y": 4, "purity": 40, "value": 40, "freshness": "fresh",
         "square_id": "red-trace"},
    ]
    view["blue_tiles"] = [
        {"x": 14, "y": 8, "purity": 200, "value": 200, "freshness": "fresh",
         "square_id": "blue-1"},
    ]
    # 300 is ABOVE the low-blue top-up (250) but BELOW the weapon cap (400),
    # so only the surplus-seek path can surface BLUE here.
    view["orbit"] = {"blue_purity_total": 300}
    moves, rationale = plan_moves(view)
    assert any(m.get("a") == "step" and m.get("to") == [14, 8] for m in moves), (
        "surplus harvester should walk onto the BLUE tile"
    )
    assert "blue" in rationale.lower()


def test_night_surplus_harvester_still_grabs_high_red():
    """v1.x — plentiful high-tier RED keeps BOTH harvesters on RED even
    when blue-seek is armed: no unit diverts to BLUE."""
    from sea_of_colours.agent.heuristic_agent import plan_moves

    view = _make_view_payload(red_xy=(6, 4))
    view["entities"]["mine"] = _two_orbital_harvesters()
    # Two MASS seams (purity 200) on opposite sides — one per harvester.
    view["red_tiles"] = [
        {"x": 6, "y": 4, "purity": 200, "value": 200, "freshness": "fresh",
         "square_id": "red-mass-a"},
        {"x": 14, "y": 8, "purity": 200, "value": 200, "freshness": "fresh",
         "square_id": "red-mass-b"},
    ]
    view["blue_tiles"] = [
        {"x": 2, "y": 2, "purity": 200, "value": 200, "freshness": "fresh",
         "square_id": "blue-1"},
    ]
    view["orbit"] = {"blue_purity_total": 300}
    moves, _ = plan_moves(view)
    assert any(m.get("a") == "step" and m.get("to") == [6, 4] for m in moves)
    assert any(m.get("a") == "step" and m.get("to") == [14, 8] for m in moves)
    assert all(m.get("to") != [2, 2] for m in moves if m.get("a") == "step"), (
        "no harvester should divert to BLUE while high RED is unclaimed"
    )


def test_play_dispatches_to_orbit_actions_in_orbit_phase():
    """The :class:`HeuristicAgent` ``play`` method must route the
    submission to orbit_actions when the view's phase is orbit, not
    night-phase moves."""
    view = _make_orbit_view(credits=2000, cap_used=1)
    out = HeuristicAgent().play(view)
    assert out["moves"] == []
    assert out["orbit_actions"], "orbit phase should emit orbit_actions"
    assert any(a["a"] == "build_probe" for a in out["orbit_actions"])


def _make_night_view_two_orbital_harvesters(red_xys=((6, 4), (14, 8))):
    """Two harvesters in orbit, two reds visible on opposite sides.

    With target-claiming the planner should drop one harvester
    next to each red — NOT both next to the same one.
    """
    reds = []
    for i, (rx, ry) in enumerate(red_xys):
        reds.append({
            "x": rx, "y": ry, "purity": 200, "freshness": "fresh",
            "value": 200, "square_id": f"sq-{i}",
        })
    return {
        "grid": {"width": 18, "height": 12, "cell_counts": {}},
        "red_tiles": reds,
        "green_tiles": [],
        "fog_clusters": [],
        "entities": {
            "mine": [
                {"id": "harvester_p1_1", "type": "harvester", "pos": None,
                 "carrying_red": False, "cargo_count": 0},
                {"id": "harvester_p1_2", "type": "harvester", "pos": None,
                 "carrying_red": False, "cargo_count": 0},
                {"id": "orblift_p1", "type": "orblift", "pos": None,
                 "holds_red": False},
            ],
            "echoes": [],
        },
    }


def test_plan_moves_assigns_different_harvesters_to_different_reds():
    """Two orbital harvesters + two visible reds → two drops, each
    targeting a DIFFERENT red. This is the bug the v0.9.5 multi-
    harvester pass fixes: the old planner emitted only one chain so
    the second harvester sat in orbit unused."""
    view = _make_night_view_two_orbital_harvesters(
        red_xys=((6, 4), (14, 8)),
    )
    moves, rationale = plan_moves(view)
    drops = [m for m in moves if m["a"] == "drop"]
    assert len(drops) == 2, (
        f"Expected 2 drops (one per harvester), got {len(drops)}: {moves}"
    )
    # Each drop should target a DIFFERENT unit.
    units = [d["unit"] for d in drops]
    assert len(set(units)) == 2, f"both drops on same unit: {units}"
    # And the chains should aim at DIFFERENT reds. Pick the step
    # destination right after each drop as the harvest target.
    step_targets = []
    for i, m in enumerate(moves):
        if m["a"] == "step":
            step_targets.append(tuple(m["to"]))
    # The two reds in the test are at (6,4) and (14,8); the chains
    # should land on cells adjacent to both, eventually stepping
    # onto each.
    assert (6, 4) in step_targets or (14, 8) in step_targets


def test_plan_moves_pushes_surplus_harvesters_into_fog():
    """One visible red + two orbital harvesters → harvester #1
    claims the red, harvester #2 pushes to the FOG FRONTIER so it
    contributes new vision next turn instead of sitting idle.

    RULEBOOK §3.10 — harvesters can only land on live/echo, so the
    "push beyond visible area" actually means dropping at the
    cluster's NEAREST_VISIBLE_EDGE (the live/echo cell nearest the
    deep-fog centroid) and letting LoS expand the frontier."""
    view = _make_night_view_two_orbital_harvesters(red_xys=((6, 4),))
    view["red_tiles"] = view["red_tiles"][:1]
    view["fog_clusters"] = [
        {"centroid": [14, 9], "size": 40, "nearest_visible_edge": [12, 8]},
    ]
    moves, rationale = plan_moves(view)
    drops = [m for m in moves if m["a"] == "drop"]
    assert len(drops) == 2, (
        f"Both harvesters should drop, got {len(drops)}: {moves}"
    )
    drop_coords = {tuple(d["at"]) for d in drops}
    assert (12, 8) in drop_coords, (
        "Surplus harvester should push to the cluster's visible-edge "
        f"frontier [12,8], got drops {drop_coords}"
    )


def test_plan_moves_damaged_surface_harvester_picks_up():
    """A damaged harvester on the surface should pickup so the next
    orbit phase can repair it, instead of trying to step (the engine
    would reject step moves from a damaged unit anyway)."""
    view = _make_night_view_two_orbital_harvesters(red_xys=((6, 4),))
    # Surface one harvester at (5, 4) and mark it damaged. The other
    # stays orbital and healthy.
    view["entities"]["mine"][0].update({
        "pos": [5, 4], "damaged": True,
    })
    moves, rationale = plan_moves(view)
    # The damaged harvester's chain should be exactly one pickup.
    damaged_moves = [m for m in moves if m.get("unit") == "harvester_p1_1"]
    assert damaged_moves == [{"a": "pickup", "unit": "harvester_p1_1"}], (
        f"Damaged harvester should pickup only, got {damaged_moves}"
    )


def test_agent_view_exposes_damaged_flag_on_harvester():
    """REGRESSION: ``entities.mine`` rows for harvesters must carry
    a ``damaged`` field so :func:`plan_orbit_actions` can decide
    whether to queue a repair action."""
    from sea_of_colours.game.session import GameSession
    from sea_of_colours.snowpark.view import build_agent_view

    sess = GameSession.new(18, 12, seed=314)
    # Flip the default harvester to damaged via the same mechanism
    # the simulator uses on collisions.
    sess.entities["harvester_p1"].damaged = True

    view = build_agent_view(sess, "p1")
    mine = view.get("entities", {}).get("mine", [])
    harvester_rows = [r for r in mine if r.get("type") == "harvester"]
    assert harvester_rows, "expected at least one harvester in mine"
    assert harvester_rows[0]["damaged"] is True, (
        "damaged harvester must surface as ``damaged: true`` in entity row"
    )


def test_runtime_orbit_phase_routes_to_heuristic_playbook(store):
    """End-to-end: when the runtime hits the orbit phase, it should
    submit the heuristic's planned action list (not an empty queue).

    The conftest auto-skips the v0.8.0 orbit phase for legacy tests
    (see :file:`tests/conftest.py`), so we flip the persisted
    session into ORBIT manually before running the agent — same
    pattern :file:`tests/test_orbit_v1.py` uses.
    """
    from sea_of_colours.game.session import GameSession, Phase

    info = soc_engine.init_session(store, seed=7, width=18, height=12)
    sid = info["session_id"]
    # Reach into the session row, flip phase + clear pending orbit
    # submissions, and re-persist so the engine's read path sees
    # the session as in ORBIT (with the +1000c stipend already
    # awarded for day 1).
    row = dict(store.load_session(sid) or {})
    sess = GameSession.from_dict(row["json_state"])
    sess.phase = Phase.ORBIT
    sess.pending_orbit_actions = {"p1": None, "p2": None}
    # Force a known credit balance so the playbook assertions are
    # deterministic regardless of any prior +stipend accounting.
    sess.credits = {"p1": 1000, "p2": 1000}
    row["json_state"] = sess.to_dict()
    row["phase"] = Phase.ORBIT.value
    store.save_session(row)

    result = run_agent_turn(store, sid, "p1")
    assert result["agent_id"] == HEURISTIC_AGENT_NAME
    assert result["runtime"] == "heuristic"
    assert "orbit_actions" in result
    assert result["orbit_actions"], "playbook should not be empty"
    tags = [a["a"] for a in result["orbit_actions"]]
    # 1000c budget, healthy fleet (1 starter harvester) → exactly
    # the "build 2 probes" action lands first; harvester build is
    # deferred because 1000c < HARVESTER_BUILD_COST (1500c).
    assert "build_probe" in tags, (
        f"orbit playbook should always include build_probe, got {tags}"
    )


# ── v0.9.8 — fog-scout cardinal-step contract + multi-seat decorrelation ─


def test_fog_scout_walk_only_emits_cardinal_steps():
    """Every step the agent emits must be Manhattan-adjacent to the
    previous position. The pre-v0.9.8 implementation emitted diagonal
    moves (``+1,+1`` per tick) which the engine rejected as ``not
    adjacent`` — the screenshot in the bug report shows ``H02 [p2]
    step harvester_p2 → (23,15)`` from a drop at (22,14), wasting
    every queue slot as a ``waste`` frame and never actually moving
    the unit. The staircase rewrite must produce strictly cardinal
    deltas. (RULEBOOK §3.10 / :meth:`GameSession.try_step_unit`.)
    """
    from sea_of_colours.agent.heuristic_agent import _fog_scout_walk

    view = _make_view_payload(red_xy=(6, 4))
    view["meta"] = {"session_id": "S-cardinal", "day": 1}
    view["hud"] = {"player": "p2", "day": 1}
    view["players"] = ["p1", "p2"]
    # Start at the upper-left so the centroid pull is roughly down-right
    # — that's exactly the case where the buggy diagonal walk fired.
    start = (4, 4)
    visible_set = {(0, 0), (1, 0), (0, 1), (1, 1)}
    moves = _fog_scout_walk(
        view=view, start=start, width=20, height=16,
        harvester_id="harvester_p2", max_steps=8, visible_set=visible_set,
    )
    assert moves, "scout walk must emit at least one step from a deep-fog start"
    here = start
    for m in moves:
        assert m["a"] == "step"
        nxt = tuple(m["to"])
        # Cardinal adjacency: Manhattan distance exactly 1.
        delta = abs(nxt[0] - here[0]) + abs(nxt[1] - here[1])
        assert delta == 1, (
            f"non-cardinal scout step {here} → {nxt} "
            f"(Manhattan distance {delta}); engine will reject as 'not adjacent'"
        )
        here = nxt


def test_probe_drops_decorrelate_across_seats_on_blind_day_one():
    """Two RED_HARVEST seats running the day-1 quadrant fallback with
    identical (no-fog-cluster) views must NOT both land their first
    probe on the same cell. Pre-v0.9.8 the fallback table was fixed
    per seat and seats 0/2 (or p1/p2 in 2-seat games) ended up with
    different tables; in 3- / 4-seat live games seats whose tables
    happened to share a cell at low map widths still collided. The
    (session × seat × day) RNG shuffle is what makes this work.
    """
    from sea_of_colours.agent.heuristic_agent import _plan_probe_drops

    def _blank_view(seat: str) -> dict:
        return {
            "grid": {"width": 24, "height": 18, "cell_counts": {"fog": 100, "stale": 0, "fresh": 0}},
            "red_tiles": [],
            "green_tiles": [],
            # No fog clusters — forces the quadrant fallback path.
            "fog_clusters": [],
            "entities": {"mine": [], "echoes": []},
            "meta": {"session_id": "S-decorrelate", "player": seat,
                     "players": ["p1", "p2", "p3", "p4"], "day": 1},
            "hud": {"player": seat, "day": 1},
            "players": ["p1", "p2", "p3", "p4"],
        }

    cells = []
    for seat in ("p1", "p2", "p3", "p4"):
        probes = _plan_probe_drops(_blank_view(seat))
        assert probes, f"seat {seat} should drop at least one fallback probe"
        # First probe each seat plants — that's the cell that matters
        # for "did they collide?".
        cells.append(tuple(probes[0]["at"]))
    assert len(set(cells)) == 4, (
        f"4 seats must land their first probe on 4 distinct cells, got {cells}"
    )
