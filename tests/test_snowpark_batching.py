"""SnowparkSocStore batching regression tests (v0.9.5).

Background: pre-v0.9.5 the snowpark store's hottest write paths fired
one ``INSERT`` per row, which dominated the user-perceived PRAXIS
latency on Snowflake — a 150-frame night cost ~150 round-trips per
``append_replay_frames`` call.

These tests pin the new batched behaviour:

* ``append_replay_frames`` issues at most ``ceil(N / 50) + 1``
  statements for N frames (the ``+1`` is the leading
  ``SELECT MAX(global_idx)`` round-trip).
* ``replace_entity_state`` issues exactly 2 statements (DELETE +
  one batched INSERT) regardless of how many entities are in the
  payload.
* ``_replace_parcels`` (via ``replace_hoard``) issues exactly 2
  statements for a non-empty hoard.

v0.9.6 follow-ups:

* ``upsert_grid_cells`` chunks at 1500 rows, so a full 40×28 grid
  (1120 cells) lands in ONE statement instead of six.
* ``replace_hoard_bundle`` / ``replace_shipped_bundle`` collapse
  both players into ONE DELETE + ONE INSERT each (instead of 4
  round-trips for the per-player loop).
* ``save_session_full`` fans every independent phase out across
  a thread pool, so each table is still written exactly once.

We drive the store with a fake Snowpark session that captures every
SQL string instead of executing it, so the tests pass without any
live Snowflake connectivity.
"""

from __future__ import annotations

from typing import Any, List

from sea_of_colours.snowpark.snowpark_store import SnowparkSocStore


class _FakeDF:
    """Snowpark ``DataFrame`` stand-in returned by ``session.sql``.

    The store only needs ``.collect()`` to return an iterable of
    row-like objects. We return an empty list for INSERT/MERGE/DELETE
    statements and pretend the leading ``SELECT MAX(global_idx)`` of
    a fresh table yields ``[-1]`` (so the first batch starts at
    ``global_idx = 0``).
    """

    def __init__(self, rows: List[Any]) -> None:
        self._rows = rows

    def collect(self) -> List[Any]:
        return list(self._rows)


class _FakeSession:
    """Captures every SQL string the store hands to ``session.sql``."""

    def __init__(self) -> None:
        self.statements: List[str] = []

    def sql(self, query: str) -> _FakeDF:
        self.statements.append(query)
        # First SELECT against a fresh SOC_REPLAY_FRAME table returns
        # MAX(global_idx) = -1 → next_global starts at 0.
        if "MAX(global_idx)" in query:
            return _FakeDF([(-1,)])
        return _FakeDF([])


def _make_frame(idx: int) -> dict:
    """Build a frame dict with every JSON-bearing column populated.

    Mirrors the shape ``GameSession.replay_push_scene`` emits so the
    batched code path exercises ``PARSE_JSON`` for every VARIANT
    column. Values are intentionally tiny so the test doesn't trip
    Snowflake's 1MB SQL text limit even if the chunker is broken.
    """
    return {
        "frame_idx": idx,
        "caption": f"frame {idx}",
        "tag": "tick",
        "owner": "p1",
        "cells": [{"x": 0, "y": 0, "ch": "  "}],
        "cells_player_p1": [{"x": 0, "y": 0, "ch": "  "}],
        "cells_player_p2": [{"x": 0, "y": 0, "ch": "  "}],
        "entities": [{"id": "harvester_p1", "x": 1, "y": 2}],
        "hoard": [{"slot": 0}],
        "collisions": [],
        "crushed_probes": [],
        "scheduled_orders": [],
        "attempted": "step",
        "outcome": "applied",
        "hour": 3,
        "emp": None,
        "mine": None,
        "chaff": None,
        "emp_clouds": [],
        "mines_active": [],
    }


def test_append_replay_frames_batches_to_few_statements() -> None:
    """150 frames must collapse to MAX_BATCH(50) inserts, not 150.

    Pre-v0.9.5 this was 1 SELECT + 150 INSERTs (~30s+ on live
    Snowflake). Post-v0.9.5 it's 1 SELECT + ceil(150/50)=3 INSERTs.
    """
    sess = _FakeSession()
    store = SnowparkSocStore(sess)
    frames = [_make_frame(i) for i in range(150)]

    store.append_replay_frames("sess-batch", day=1, frames=frames)

    inserts = [s for s in sess.statements if s.startswith("INSERT INTO SOC_REPLAY_FRAME")]
    selects = [s for s in sess.statements if "MAX(global_idx)" in s]
    assert len(selects) == 1, (
        f"expected 1 leading MAX(global_idx) select, got {len(selects)}"
    )
    assert len(inserts) == 3, (
        f"expected 3 batched INSERTs for 150 frames (50/batch), "
        f"got {len(inserts)}"
    )


def test_append_replay_frames_empty_is_a_noop() -> None:
    """Zero frames must not issue any SQL.

    The leading SELECT was also skipped pre-v0.9.5 for the empty
    list — that contract still holds.
    """
    sess = _FakeSession()
    store = SnowparkSocStore(sess)
    store.append_replay_frames("sess-empty", day=1, frames=[])
    assert sess.statements == []


def test_append_replay_frames_small_batch_is_single_insert() -> None:
    """A typical night (~30 frames) fits in one batched INSERT.

    This is the common case — most PRAXIS submissions resolve in a
    single round-trip after the leading MAX(global_idx) query.
    """
    sess = _FakeSession()
    store = SnowparkSocStore(sess)
    frames = [_make_frame(i) for i in range(30)]

    store.append_replay_frames("sess-small", day=1, frames=frames)

    inserts = [s for s in sess.statements if s.startswith("INSERT INTO SOC_REPLAY_FRAME")]
    assert len(inserts) == 1
    # Sanity-check: the single statement carries 30 row tuples
    # rather than 30 separate INSERTs. We can't easily count tuples
    # without parsing the SQL, so as a proxy assert the statement
    # carries every PARSE_JSON column header exactly once.
    body = inserts[0]
    for header in (
        "PARSE_JSON(cells_j)",
        "PARSE_JSON(entities_j)",
        "PARSE_JSON(mines_active_j)",
    ):
        assert body.count(header) == 1, (
            f"batched SELECT must reference {header} once, "
            f"got {body.count(header)}"
        )


def test_replace_entity_state_uses_one_delete_plus_one_insert() -> None:
    """``replace_entity_state`` is now 2 statements regardless of size.

    Pre-v0.9.5 it was 1 DELETE + N per-entity INSERTs; the new path
    is 1 DELETE + 1 batched INSERT.
    """
    sess = _FakeSession()
    store = SnowparkSocStore(sess)

    rows = [
        {
            "entity_id": f"e{i}",
            "entity_type": "harvester",
            "owner": "p1",
            "x": i,
            "y": i,
            "carrying_red": False,
            "orbital_cargo_red": False,
            "cargo_squares": [],
            "lost_last_night": False,
        }
        for i in range(8)
    ]
    store.replace_entity_state("sess-ent", rows)

    deletes = [s for s in sess.statements if s.startswith("DELETE FROM SOC_ENTITY_STATE")]
    inserts = [s for s in sess.statements if s.startswith("INSERT INTO SOC_ENTITY_STATE")]
    assert len(deletes) == 1
    assert len(inserts) == 1, (
        f"expected 1 batched INSERT for 8 entities, got {len(inserts)}"
    )


def test_replace_hoard_uses_one_delete_plus_one_insert() -> None:
    """A 25-parcel hoard must batch into a single INSERT.

    Pre-v0.9.5 a full hoard cost 1 + 25 round-trips PER PLAYER PER
    SAVE — 50 round-trips total just for hoards. The batched path
    keeps it at 4 (2 per player).
    """
    sess = _FakeSession()
    store = SnowparkSocStore(sess)
    rows = [
        {
            "slot": i,
            "square_id": f"sq-{i}",
            "origin_x": i,
            "origin_y": 0,
            "origin_tile": 2,
            "origin_purity": 80,
            "harvested_day": 1,
            "site_uid": f"uid-{i}",
            "payload": {"slot": i, "purity": 80},
        }
        for i in range(25)
    ]
    store.replace_hoard("sess-hoard", "p1", rows)
    deletes = [s for s in sess.statements if s.startswith("DELETE FROM SOC_HOARD_PARCEL")]
    inserts = [s for s in sess.statements if s.startswith("INSERT INTO SOC_HOARD_PARCEL")]
    assert len(deletes) == 1
    assert len(inserts) == 1, (
        f"expected 1 batched INSERT for 25 hoard parcels, got {len(inserts)}"
    )


def test_upsert_grid_cells_full_board_is_a_single_statement() -> None:
    """40×28 = 1120 cells must collapse to ONE MERGE statement.

    Pre-v0.9.6 the chunker capped each statement at 200 rows so a
    full grid cost 6 round-trips. v0.9.6 bumped the cap to 1500
    rows, which fits the entire board in one VALUES list under
    Snowflake's SQL text limit.
    """
    sess = _FakeSession()
    store = SnowparkSocStore(sess)
    rows = [
        {"x": x, "y": y, "tile": (x + y) % 5, "purity": (x * 7 + y * 3) % 256}
        for y in range(28) for x in range(40)
    ]
    assert len(rows) == 1120
    store.upsert_grid_cells("sess-grid", rows)
    merges = [s for s in sess.statements if s.startswith("MERGE INTO SOC_GRID_CELL")]
    assert len(merges) == 1, (
        f"expected 1 batched MERGE for {len(rows)} cells, got {len(merges)}"
    )


def test_replace_hoard_bundle_collapses_both_seats_into_two_statements() -> None:
    """``replace_hoard_bundle`` for {p1,p2} must issue exactly 1 DELETE + 1 INSERT.

    Pre-v0.9.6 ``save_session_full`` looped over both players and
    called the single-owner :meth:`replace_hoard` twice — 4 round-
    trips. The bundle variant covers both seats in 2 round-trips
    (one session-scoped DELETE, one batched INSERT carrying both
    owners interleaved).
    """
    sess = _FakeSession()
    store = SnowparkSocStore(sess)

    def _rows(prefix: str):
        return [
            {
                "slot": i,
                "square_id": f"{prefix}-sq-{i}",
                "origin_x": i,
                "origin_y": 0,
                "origin_tile": 1,
                "origin_purity": 50 + i,
                "harvested_day": 2,
                "site_uid": f"{prefix}-uid-{i}",
                "payload": {"slot": i},
            }
            for i in range(5)
        ]

    store.replace_hoard_bundle(
        "sess-bundle", {"p1": _rows("p1"), "p2": _rows("p2")},
    )

    deletes = [s for s in sess.statements if s.startswith("DELETE FROM SOC_HOARD_PARCEL")]
    inserts = [s for s in sess.statements if s.startswith("INSERT INTO SOC_HOARD_PARCEL")]
    assert len(deletes) == 1, (
        f"expected 1 session-scoped DELETE, got {len(deletes)}"
    )
    # The single DELETE must filter on BOTH owners so we don't blow
    # away a third seat's rows (future-proofing). Check the owner
    # list is present in the WHERE clause.
    assert "owner IN" in deletes[0], deletes[0]
    assert "'p1'" in deletes[0] and "'p2'" in deletes[0]
    assert len(inserts) == 1, (
        f"expected 1 batched INSERT covering both seats, got {len(inserts)}"
    )
    # And the INSERT must carry rows from both seats (look for
    # owner labels in the VALUES literal).
    assert "'p1'" in inserts[0] and "'p2'" in inserts[0]


def test_replace_shipped_bundle_empty_owner_keeps_the_delete() -> None:
    """A seat with no shipped parcels still gets its old rows cleared.

    The bundle path can't skip the DELETE just because one seat is
    empty — otherwise stale shipped rows survive across saves and
    corrupt the score. We accept either ``[]`` or omitted-owner
    payloads.
    """
    sess = _FakeSession()
    store = SnowparkSocStore(sess)
    store.replace_shipped_bundle(
        "sess-shipped-empty", {"p1": [], "p2": []},
    )
    deletes = [s for s in sess.statements if s.startswith("DELETE FROM SOC_SHIPPED_PARCEL")]
    inserts = [s for s in sess.statements if s.startswith("INSERT INTO SOC_SHIPPED_PARCEL")]
    assert len(deletes) == 1, "DELETE must still fire so stale rows are evicted"
    assert len(inserts) == 0, "no INSERT when every owner is empty"


def test_save_session_full_parallel_writes_each_table_once() -> None:
    """:func:`save_session_full` fans out across a thread pool but still
    issues exactly one bundle/batched statement per SOC_* table.

    Pin the contract: enabling parallelism must not duplicate any
    write (e.g. two threads racing on the same table). The fake
    session is thread-safe because Python's GIL serialises list
    appends; that's the same safety property the real Snowpark
    session relies on for concurrent ``session.sql`` calls.
    """
    import os as _os
    from sea_of_colours.snowpark import engine as _engine
    from sea_of_colours.snowpark.store import InMemorySocStore
    from sea_of_colours.game.session import GameSession

    # Build a small session so the test stays fast.
    sess = GameSession.new(8, 6, seed=42)
    # The default backend already saves once on ``GameSession.new`` -
    # bypass that by routing through a fresh InMemorySocStore and
    # capturing how many times each method is invoked.

    call_log: list[str] = []

    class _CountingStore(InMemorySocStore):
        def save_session(self, row):  # type: ignore[override]
            call_log.append("save_session")
            super().save_session(row)

        def upsert_square_identity(self, sid, rows):  # type: ignore[override]
            call_log.append("upsert_square_identity")
            super().upsert_square_identity(sid, rows)

        def upsert_asset_records(self, sid, rows):  # type: ignore[override]
            call_log.append("upsert_asset_records")
            super().upsert_asset_records(sid, rows)

        def replace_entity_state(self, sid, rows):  # type: ignore[override]
            call_log.append("replace_entity_state")
            super().replace_entity_state(sid, rows)

        def upsert_grid_cells(self, sid, rows):  # type: ignore[override]
            call_log.append("upsert_grid_cells")
            super().upsert_grid_cells(sid, rows)

        def replace_hoard_bundle(self, sid, by_owner):  # type: ignore[override]
            call_log.append("replace_hoard_bundle")
            super().replace_hoard_bundle(sid, by_owner)

        def replace_shipped_bundle(self, sid, by_owner):  # type: ignore[override]
            call_log.append("replace_shipped_bundle")
            super().replace_shipped_bundle(sid, by_owner)

    store = _CountingStore()
    # Force parallel mode on regardless of caller environment.
    prev = _engine._PARALLEL_SAVE
    _engine._PARALLEL_SAVE = True
    try:
        _engine.save_session_full(store, sess)
    finally:
        _engine._PARALLEL_SAVE = prev

    # Each of the 7 phases must be invoked EXACTLY once.
    expected = {
        "save_session",
        "upsert_square_identity",
        "upsert_asset_records",
        "replace_entity_state",
        "upsert_grid_cells",
        "replace_hoard_bundle",
        "replace_shipped_bundle",
    }
    assert set(call_log) == expected
    assert len(call_log) == 7, (
        f"each phase must run once, got {sorted(call_log)}"
    )
