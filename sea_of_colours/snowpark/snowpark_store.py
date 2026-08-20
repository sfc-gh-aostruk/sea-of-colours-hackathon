"""SnowparkSocStore — :class:`SocStore` backed by a live Snowpark session.

The protocol surface in :mod:`sea_of_colours.snowpark.store` is intentionally
narrow; this module implements each method as a parameterised SQL call
against the SOC_* schema (declared in ``snowflake/soc_schema.sql``).

Two modes are supported:

* **Stored-procedure mode** (the normal case in Snowflake): a Snowpark
  ``session`` object is passed in (the same one the proc handler
  receives). We use ``session.sql(...).collect()`` to issue statements
  and ``session.create_dataframe(...)`` to bulk-insert rows.
* **Driver mode** (used by Phase 3's FastAPI proxy): a Python connector
  cursor wrapped in a minimal adapter — see :func:`from_cursor`. Same
  semantics; just a different way of issuing SQL.

Insert performance: we use a single ``MERGE INTO ... USING (SELECT ...
FROM VALUES(...))`` per batched upsert so a 25-frame night writes 25
rows of replay in one statement, and the per-day SOC_GAME_LOG insert
is also one statement.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence


def _json(value: Any) -> str:
    return json.dumps(value, default=str, separators=(",", ":"))


def _quote(value: Any) -> str:
    """SQL-literal-encode a Python value (NULL-safe).

    Snowflake interprets backslash escape sequences inside single-quoted
    string literals (``'foo\\n'`` → literal newline, ``'\\\\'`` →
    literal backslash, etc.), so we MUST double backslashes *before*
    we wrap in quotes. Otherwise any JSON we hand to ``PARSE_JSON`` is
    silently corrupted — e.g. ``json.dumps({"x": "a\\nb"})`` produces
    the two-character escape ``\\n``, which Snowflake then turns back
    into a literal newline inside the JSON string, and ``PARSE_JSON``
    explodes with ``"unterminated string, line 2, pos 0"``.

    Order matters: double the backslashes first, then the quotes — the
    other way round would also double-escape the backslashes inside the
    ``''`` we just inserted.
    """
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return repr(value)
    text = str(value).replace("\\", "\\\\").replace("'", "''")
    return f"'{text}'"


class SnowparkSocStore:
    """SocStore implementation against the live SEA_OF_COLOURS schema."""

    # Order: rows that reference nothing first. There are no declared FKs
    # in ``soc_schema.sql`` so technically any order works, but listing
    # the "child" tables before ``SOC_GAME_SESSION`` matches the natural
    # data dependency and keeps the wipe self-documenting.
    _SESSION_TABLES: tuple = (
        "SOC_AGENT_INVOCATION",
        "SOC_ORCHESTRATOR_LOG",
        "SOC_REPLAY_FRAME",
        "SOC_GAME_LOG",
        "SOC_POLICY_QUEUE",
        "SOC_SHIPPED_PARCEL",
        "SOC_HOARD_PARCEL",
        "SOC_ASSET_RECORD",
        "SOC_ENTITY_STATE",
        "SOC_GRID_CELL",
        "SOC_SQUARE_IDENTITY",
        "SOC_GAME_SESSION",
    )

    def __init__(self, session) -> None:
        self.session = session

    # ── SQL helpers ───────────────────────────────────────────────
    def _exec(self, sql: str) -> List[Any]:
        return list(self.session.sql(sql).collect())

    # ── season lifecycle ──────────────────────────────────────────
    def wipe_all_sessions(self) -> None:
        """Wipe every persisted season EXCEPT eval-tagged ones.

        Called by :func:`engine.init_session` so each NEW GAME starts
        a fresh season — the "every new season overwrites the
        previous" contract requested by the player UI. We use
        ``DELETE`` rather than ``TRUNCATE`` because ``DELETE`` only
        needs the ``DELETE`` privilege (already granted to
        ``SYSADMIN``); ``TRUNCATE`` needs ownership and would force
        every caller back into ``ACCOUNTADMIN``.

        Sessions whose ``season_name`` starts with ``eval:`` are
        preserved across wipes — those are evaluation fixtures
        owned by the ``/evals`` command center, not gameplay
        seasons, and a player clicking NEW GAME shouldn't nuke
        their A/B history. We delete child rows by parent-session
        membership so the SQL is consistent: any child row whose
        ``session_id`` points at a NON-eval session disappears
        along with that session.

        See :func:`server.app._is_eval_session` for the matching
        predicate on the API side.
        """
        # Step 1: child tables — drop any row whose parent is about
        # to be deleted. We compute "to-be-deleted parents" as the
        # complement of the eval-tagged set so a future tag scheme
        # that doesn't use season_name can override this.
        deletable_predicate = (
            "session_id IN ("
            "  SELECT session_id FROM SOC_GAME_SESSION "
            "  WHERE season_name IS NULL "
            "     OR NOT season_name LIKE 'eval:%'"
            ")"
        )
        for tbl in self._SESSION_TABLES:
            if tbl == "SOC_GAME_SESSION":
                continue
            try:
                self._exec(f"DELETE FROM {tbl} WHERE {deletable_predicate}")
            except Exception:
                # Table may not exist on a fresh deploy — treat as a
                # no-op so the first ever NEW GAME still succeeds.
                pass
        # Step 2: drop the parent rows themselves (any tagged eval
        # session stays).
        try:
            self._exec(
                "DELETE FROM SOC_GAME_SESSION "
                "WHERE season_name IS NULL OR NOT season_name LIKE 'eval:%'"
            )
        except Exception:
            pass

    def delete_session(self, session_id: str) -> None:
        """Delete one session id across every SOC_* table.

        Child tables first (by ``session_id`` membership), then the parent
        ``SOC_GAME_SESSION`` row. Missing tables are tolerated so a partial
        deploy still deletes what exists."""
        pred = f"session_id = {_quote(str(session_id))}"
        for tbl in self._SESSION_TABLES:
            if tbl == "SOC_GAME_SESSION":
                continue
            try:
                self._exec(f"DELETE FROM {tbl} WHERE {pred}")
            except Exception:
                pass
        try:
            self._exec(f"DELETE FROM SOC_GAME_SESSION WHERE {pred}")
        except Exception:
            pass

    # ── SOC_GAME_SESSION ──────────────────────────────────────────
    def save_session(self, row: Mapping[str, Any]) -> None:
        sql = (
            "MERGE INTO SOC_GAME_SESSION t "
            "USING (SELECT "
            f"{_quote(row['session_id'])} AS session_id, "
            f"{_quote(row.get('season_name'))} AS season_name, "
            f"{_quote(int(row['width']))}::INT AS width, "
            f"{_quote(int(row['height']))}::INT AS height, "
            f"{_quote(int(row['seed']))}::INT AS seed, "
            f"{_quote(int(row['day']))}::INT AS day, "
            f"{_quote(str(row['phase']))} AS phase, "
            f"PARSE_JSON({_quote(_json(row.get('json_state')))}) AS json_state"
            ") s ON t.session_id = s.session_id "
            "WHEN MATCHED THEN UPDATE SET "
            "  season_name = s.season_name, "
            "  width = s.width, height = s.height, seed = s.seed, "
            "  day = s.day, phase = s.phase, json_state = s.json_state, "
            "  last_touched_at = CURRENT_TIMESTAMP() "
            "WHEN NOT MATCHED THEN INSERT "
            "  (session_id, season_name, width, height, seed, day, phase, json_state) "
            "  VALUES (s.session_id, s.season_name, s.width, s.height, "
            "          s.seed, s.day, s.phase, s.json_state)"
        )
        self._exec(sql)

    def load_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        sql = (
            "SELECT session_id, season_name, width, height, seed, day, phase, json_state "
            "FROM SOC_GAME_SESSION WHERE session_id = "
            f"{_quote(session_id)}"
        )
        rows = self._exec(sql)
        if not rows:
            return None
        return _row_to_dict(rows[0])

    def list_sessions(self) -> List[Dict[str, Any]]:
        sql = (
            "SELECT session_id, season_name, width, height, seed, day, phase "
            "FROM SOC_GAME_SESSION ORDER BY last_touched_at DESC"
        )
        return [_row_to_dict(r) for r in self._exec(sql)]

    def latest_session(self) -> Optional[Dict[str, Any]]:
        rows = self.list_sessions()
        return rows[0] if rows else None

    def bulk_session_scores(self) -> Dict[str, Dict[str, int]]:
        """One-shot scores via :sql:`SOC_SESSION_STANDINGS`.

        Avoids the N-roundtrip cost of hydrating every session just to
        compute a leaderboard for the watcher's season picker. v0.8.0
        — the view now folds **shipped** purity only per (session,
        player) (RULEBOOK §3.1); the per-session score is the single
        ``score`` column.
        """
        sql = (
            "SELECT session_id, player, score "
            "FROM SOC_SESSION_STANDINGS"
        )
        out: Dict[str, Dict[str, int]] = {}
        for row in self._exec(sql):
            d = _row_to_dict(row)
            sid = d.get("session_id")
            player = d.get("player")
            if not sid or player not in {"p1", "p2"}:
                continue
            try:
                score = int(d.get("score", 0) or 0)
            except (TypeError, ValueError):
                score = 0
            bucket = out.setdefault(str(sid), {"p1": 0, "p2": 0})
            bucket[str(player)] = score
        return out

    # ── SOC_SQUARE_IDENTITY ───────────────────────────────────────
    def upsert_square_identity(
        self, session_id: str, entries: List[Mapping[str, Any]]
    ) -> None:
        if not entries:
            return
        values = ",".join(
            "(" + ",".join(
                [
                    _quote(session_id),
                    _quote(int(r["x"])),
                    _quote(int(r["y"])),
                    _quote(str(r["square_id"])),
                    _quote(int(r["tile_at_generation"])),
                    _quote(int(r["purity_at_generation"])),
                ]
            ) + ")"
            for r in entries
        )
        sql = (
            "MERGE INTO SOC_SQUARE_IDENTITY t USING ("
            f"SELECT * FROM (VALUES {values}) AS v("
            "  session_id, x, y, square_id, tile_at_generation, purity_at_generation"
            ")"
            ") s "
            "ON t.session_id = s.session_id AND t.x = s.x AND t.y = s.y "
            "WHEN MATCHED THEN UPDATE SET square_id = s.square_id, "
            "  tile_at_generation = s.tile_at_generation, "
            "  purity_at_generation = s.purity_at_generation "
            "WHEN NOT MATCHED THEN INSERT VALUES "
            "(s.session_id, s.x, s.y, s.square_id, "
            " s.tile_at_generation, s.purity_at_generation)"
        )
        self._exec(sql)

    # ── SOC_ASSET_RECORD ──────────────────────────────────────────
    def upsert_asset_records(
        self, session_id: str, records: List[Mapping[str, Any]]
    ) -> None:
        if not records:
            return
        values = ",".join(
            "(" + ",".join(
                [
                    _quote(session_id),
                    _quote(str(r["asset_id"])),
                    _quote(str(r["asset_type"])),
                    _quote(str(r["owner"])),
                    _quote(int(r["created_on_day"])),
                    _quote(r.get("first_deployed_day")),
                    _quote(r.get("destroyed_on_day")),
                    _quote(r.get("destroyed_by")),
                    _quote(r.get("last_seen_x")),
                    _quote(r.get("last_seen_y")),
                    _quote(int(r.get("total_red_harvested", 0))),
                    _quote(int(r.get("total_days_on_surface", 0))),
                ]
            ) + ")"
            for r in records
        )
        sql = (
            "MERGE INTO SOC_ASSET_RECORD t USING ("
            f"SELECT * FROM (VALUES {values}) AS v("
            "  session_id, asset_id, asset_type, owner, created_on_day, "
            "  first_deployed_day, destroyed_on_day, destroyed_by, "
            "  last_seen_x, last_seen_y, total_red_harvested, "
            "  total_days_on_surface"
            ")"
            ") s ON t.session_id = s.session_id AND t.asset_id = s.asset_id "
            "WHEN MATCHED THEN UPDATE SET "
            "  asset_type = s.asset_type, owner = s.owner, "
            "  created_on_day = s.created_on_day, "
            "  first_deployed_day = s.first_deployed_day, "
            "  destroyed_on_day = s.destroyed_on_day, "
            "  destroyed_by = s.destroyed_by, "
            "  last_seen_x = s.last_seen_x, last_seen_y = s.last_seen_y, "
            "  total_red_harvested = s.total_red_harvested, "
            "  total_days_on_surface = s.total_days_on_surface, "
            "  updated_at = CURRENT_TIMESTAMP() "
            "WHEN NOT MATCHED THEN INSERT VALUES "
            "(s.session_id, s.asset_id, s.asset_type, s.owner, "
            " s.created_on_day, s.first_deployed_day, s.destroyed_on_day, "
            " s.destroyed_by, s.last_seen_x, s.last_seen_y, "
            " s.total_red_harvested, s.total_days_on_surface, "
            " CURRENT_TIMESTAMP())"
        )
        self._exec(sql)

    # ── SOC_ENTITY_STATE ──────────────────────────────────────────
    def replace_entity_state(
        self, session_id: str, rows: List[Mapping[str, Any]]
    ) -> None:
        """Replace the session's entity rows with ``rows``.

        v0.9.5 — collapsed the per-entity INSERT loop into one
        multi-row ``INSERT … SELECT … FROM VALUES`` statement so a
        12-entity night (3 harvesters + 1 lifter + ~8 probes per
        seat) costs 2 Snowflake round-trips (DELETE + INSERT)
        instead of 1 + N. ``cargo_squares`` rides as a VARIANT via
        ``PARSE_JSON`` lifted into the SELECT.
        """
        self._exec(
            f"DELETE FROM SOC_ENTITY_STATE WHERE session_id = {_quote(session_id)}"
        )
        if not rows:
            return
        cols = (
            "session_id, entity_id, entity_type, owner, x, y, carrying_red, "
            "orbital_cargo_red, cargo_squares, lost_last_night"
        )
        alias_list = (
            "session_id, entity_id, entity_type, owner, x, y, carrying_red, "
            "orbital_cargo_red, cargo_squares_j, lost_last_night"
        )
        select_list = (
            "session_id, entity_id, entity_type, owner, x, y, carrying_red, "
            "orbital_cargo_red, PARSE_JSON(cargo_squares_j), lost_last_night"
        )
        # Entities per session are ≤ ~15, so a single 1-chunk batch
        # always fits comfortably under the SQL text cap.
        value_tuples: List[str] = []
        for r in rows:
            cargo_json = _json(list(r.get("cargo_squares") or []))
            parts = [
                _quote(session_id),
                _quote(str(r["entity_id"])),
                _quote(str(r["entity_type"])),
                _quote(str(r["owner"])),
                _quote(r.get("x")),
                _quote(r.get("y")),
                _quote(bool(r.get("carrying_red"))),
                _quote(bool(r.get("orbital_cargo_red"))),
                _quote(cargo_json),
                _quote(bool(r.get("lost_last_night"))),
            ]
            value_tuples.append("(" + ", ".join(parts) + ")")
        sql = (
            f"INSERT INTO SOC_ENTITY_STATE ({cols}) "
            f"SELECT {select_list} FROM (VALUES "
            + ", ".join(value_tuples)
            + f") AS v({alias_list})"
        )
        self._exec(sql)

    # ── SOC_GRID_CELL ─────────────────────────────────────────────
    def upsert_grid_cells(
        self, session_id: str, rows: List[Mapping[str, Any]]
    ) -> None:
        if not rows:
            return
        # 40×28 = 1120 cells. Each VALUES row is tiny (~6 small ints
        # plus the session_id string), so a single 1500-row chunk
        # comfortably fits Snowflake's 1MB SQL text cap and collapses
        # the entire grid into ONE round-trip instead of the previous
        # six chunks of 200. v0.9.6 — the grid write was the biggest
        # remaining offender in ``save_session_full`` (3-6s of wall
        # time); merging into one statement drops that to a single
        # Snowflake roundtrip (~500ms-1s).
        for chunk in _chunks(rows, 1500):
            values = ",".join(
                "(" + ",".join(
                    [
                        _quote(session_id),
                        _quote(int(r["x"])),
                        _quote(int(r["y"])),
                        _quote(int(r["tile"])),
                        _quote(int(r["purity"])),
                        _quote(r.get("last_mutated_day")),
                    ]
                ) + ")"
                for r in chunk
            )
            sql = (
                "MERGE INTO SOC_GRID_CELL t USING ("
                f"SELECT * FROM (VALUES {values}) AS v("
                "  session_id, x, y, tile, purity, last_mutated_day"
                ")"
                ") s ON t.session_id = s.session_id AND t.x = s.x AND t.y = s.y "
                "WHEN MATCHED THEN UPDATE SET tile = s.tile, "
                "  purity = s.purity, last_mutated_day = s.last_mutated_day "
                "WHEN NOT MATCHED THEN INSERT VALUES "
                "(s.session_id, s.x, s.y, s.tile, s.purity, s.last_mutated_day)"
            )
            self._exec(sql)

    # ── SOC_HOARD_PARCEL / SOC_SHIPPED_PARCEL ────────────────────
    def replace_hoard(
        self, session_id: str, owner: str, rows: List[Mapping[str, Any]]
    ) -> None:
        self._replace_parcels("SOC_HOARD_PARCEL", session_id, {owner: rows})

    def replace_shipped(
        self, session_id: str, owner: str, rows: List[Mapping[str, Any]]
    ) -> None:
        self._replace_parcels("SOC_SHIPPED_PARCEL", session_id, {owner: rows})

    def replace_hoard_bundle(
        self,
        session_id: str,
        by_owner: Mapping[str, List[Mapping[str, Any]]],
    ) -> None:
        """One-shot replacement of every player's hoard for a session.

        v0.9.6 — pre-v0.9.6 ``save_session_full`` called
        :meth:`replace_hoard` once per player, costing 4 Snowflake
        round-trips (2 DELETE + 2 INSERT) for hoard + the same for
        shipped. The bundled variant collapses both seats into ONE
        DELETE (session-scoped) + ONE multi-owner batched INSERT
        per parcel table, dropping the per-call cost from ~1.5s of
        wall time to a single Snowflake roundtrip.
        """
        self._replace_parcels("SOC_HOARD_PARCEL", session_id, by_owner)

    def replace_shipped_bundle(
        self,
        session_id: str,
        by_owner: Mapping[str, List[Mapping[str, Any]]],
    ) -> None:
        """Counterpart of :meth:`replace_hoard_bundle` for shipped parcels."""
        self._replace_parcels("SOC_SHIPPED_PARCEL", session_id, by_owner)

    def _replace_parcels(
        self, table: str, session_id: str,
        by_owner: Mapping[str, List[Mapping[str, Any]]],
    ) -> None:
        """Replace one or more players' parcel rows in ``table`` atomically.

        v0.9.6 — generalised the per-player API to take an owner→rows
        map so callers (like ``save_session_full``) can collapse the
        per-seat loop into a SINGLE DELETE + SINGLE batched INSERT.
        Pre-v0.9.5 a full hoard (25 parcels) cost 1 + 25 round-trips
        per player per save; v0.9.5 cut that to 2 round-trips per
        player; v0.9.6 cuts it to 2 round-trips TOTAL across both
        seats. The single-owner public methods stay thin wrappers
        around this for backward compatibility.
        """
        owners = sorted(by_owner.keys())
        if not owners:
            return
        # Session-scoped DELETE: when EVERY owner is being replaced
        # at once we don't need a per-owner WHERE filter. Callers
        # that only refresh ONE player still get correctness via
        # the owner filter (legacy single-owner code path).
        if len(owners) == 1:
            (only_owner,) = owners
            self._exec(
                f"DELETE FROM {table} WHERE session_id = {_quote(session_id)} "
                f"AND owner = {_quote(only_owner)}"
            )
        else:
            self._exec(
                f"DELETE FROM {table} WHERE session_id = {_quote(session_id)} "
                f"AND owner IN ({', '.join(_quote(o) for o in owners)})"
            )
        cols = (
            "session_id, owner, slot, square_id, origin_x, origin_y, "
            "origin_tile, origin_purity, harvested_day, site_uid, payload"
        )
        alias_list = (
            "session_id, owner, slot, square_id, origin_x, origin_y, "
            "origin_tile, origin_purity, harvested_day, site_uid, payload_j"
        )
        select_list = (
            "session_id, owner, slot, square_id, origin_x, origin_y, "
            "origin_tile, origin_purity, harvested_day, site_uid, "
            "PARSE_JSON(payload_j)"
        )
        value_tuples: List[str] = []
        for owner in owners:
            for r in (by_owner.get(owner) or []):
                payload_json = _json(r.get("payload") or dict(r))
                parts = [
                    _quote(session_id),
                    _quote(owner),
                    _quote(int(r["slot"])),
                    _quote(r.get("square_id")),
                    _quote(r.get("origin_x")),
                    _quote(r.get("origin_y")),
                    _quote(r.get("origin_tile")),
                    _quote(r.get("origin_purity")),
                    _quote(r.get("harvested_day")),
                    _quote(r.get("site_uid")),
                    _quote(payload_json),
                ]
                value_tuples.append("(" + ", ".join(parts) + ")")
        if not value_tuples:
            # All owners cleared to empty — DELETE already did the job.
            return
        sql = (
            f"INSERT INTO {table} ({cols}) "
            f"SELECT {select_list} FROM (VALUES "
            + ", ".join(value_tuples)
            + f") AS v({alias_list})"
        )
        self._exec(sql)

    def list_hoard(self, session_id: str, owner: str) -> List[Dict[str, Any]]:
        rows = self._exec(
            "SELECT * FROM SOC_HOARD_PARCEL "
            f"WHERE session_id = {_quote(session_id)} "
            f"AND owner = {_quote(owner)} ORDER BY slot"
        )
        return [_row_to_dict(r) for r in rows]

    def list_shipped(self, session_id: str, owner: str) -> List[Dict[str, Any]]:
        rows = self._exec(
            "SELECT * FROM SOC_SHIPPED_PARCEL "
            f"WHERE session_id = {_quote(session_id)} "
            f"AND owner = {_quote(owner)} ORDER BY slot"
        )
        return [_row_to_dict(r) for r in rows]

    # ── SOC_POLICY_QUEUE ──────────────────────────────────────────
    def upsert_policy(
        self, session_id: str, day: int, player: str, queue: List[Any],
    ) -> None:
        sql = (
            "MERGE INTO SOC_POLICY_QUEUE t USING (SELECT "
            f"{_quote(session_id)} AS session_id, "
            f"{_quote(int(day))} AS day, "
            f"{_quote(player)} AS player, "
            f"PARSE_JSON({_quote(_json(queue))}) AS queue, "
            f"{_quote(len(queue))} AS move_count) s "
            "ON t.session_id = s.session_id AND t.day = s.day "
            "AND t.player = s.player "
            "WHEN MATCHED THEN UPDATE SET queue = s.queue, "
            "  move_count = s.move_count, "
            "  submitted_at = CURRENT_TIMESTAMP() "
            "WHEN NOT MATCHED THEN INSERT (session_id, day, player, "
            "  queue, move_count) VALUES "
            "  (s.session_id, s.day, s.player, s.queue, s.move_count)"
        )
        self._exec(sql)

    def list_policies(
        self, session_id: str, day: int
    ) -> Dict[str, List[Any]]:
        rows = self._exec(
            "SELECT player, queue FROM SOC_POLICY_QUEUE "
            f"WHERE session_id = {_quote(session_id)} AND day = {_quote(int(day))}"
        )
        out: Dict[str, List[Any]] = {}
        for r in rows:
            d = _row_to_dict(r)
            queue = d.get("queue")
            if isinstance(queue, str):
                try:
                    queue = json.loads(queue)
                except json.JSONDecodeError:
                    queue = []
            out[d["player"]] = queue or []
        return out

    # ── SOC_GAME_LOG ──────────────────────────────────────────────
    def append_log(
        self, session_id: str, day: int,
        entries: List[Mapping[str, Any]],
    ) -> None:
        if not entries:
            return
        rows = self._exec(
            "SELECT COALESCE(MAX(seq), 0) AS s FROM SOC_GAME_LOG "
            f"WHERE session_id = {_quote(session_id)}"
        )
        next_seq = (rows[0][0] if rows else 0) + 1 if rows else 1
        values = ",".join(
            "(" + ",".join([
                _quote(session_id),
                _quote(int(day)),
                _quote(next_seq + offset),
                _quote(str(entry.get("level", "info"))),
                _quote(str(entry.get("text", ""))),
            ]) + ")"
            for offset, entry in enumerate(entries)
        )
        self._exec(
            "INSERT INTO SOC_GAME_LOG (session_id, day, seq, level, text) "
            f"SELECT * FROM (VALUES {values}) "
            "AS v(session_id, day, seq, level, text)"
        )

    def list_log(
        self, session_id: str,
        day_from: Optional[int] = None,
        day_to: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        where = [f"session_id = {_quote(session_id)}"]
        if day_from is not None:
            where.append(f"day >= {int(day_from)}")
        if day_to is not None:
            where.append(f"day <= {int(day_to)}")
        sql = (
            "SELECT session_id, day, seq, level, text, ts FROM SOC_GAME_LOG "
            f"WHERE {' AND '.join(where)} ORDER BY seq"
        )
        if limit is not None:
            sql = (
                f"SELECT * FROM ({sql}) ORDER BY seq DESC LIMIT {int(limit)}"
            )
        rows = [_row_to_dict(r) for r in self._exec(sql)]
        if limit is not None:
            rows.reverse()
        return rows

    # ── SOC_REPLAY_FRAME ──────────────────────────────────────────
    def append_replay_frames(
        self, session_id: str, day: int, frames: List[Mapping[str, Any]],
    ) -> None:
        """Bulk-insert all frames from one night.

        v0.9.5 — pre-v0.9.5 this fired one ``INSERT`` per frame, so a
        single PRAXIS that produced ~150 frames cost ~150 Snowflake
        round-trips and dominated the user-perceived latency.

        The batched path collapses N rows into a single
        ``INSERT … SELECT … FROM (VALUES (…), (…), …)`` statement,
        with ``PARSE_JSON`` lifted into the outer SELECT so each
        VARIANT column is hydrated from a string literal in the
        VALUES row. Snowflake's documented SQL text cap is 1MB; we
        chunk at 50 frames per statement so even a frame loaded with
        12 JSON blobs (cells, cells_player_*, entities, hoard, etc.)
        stays well under that limit.

        Behaviour is otherwise identical to the per-row writer:
        ``global_idx`` is monotonically assigned starting from
        ``MAX(global_idx) + 1`` so consumers see the same ordering
        contract.
        """
        if not frames:
            return
        # E1b — idempotent per (session, day). A night's frames are written in
        # ONE batch at resolution; if the same night is resolved again (e.g. a
        # stale-read re-dispatch), drop the prior copy first so the replay can
        # never contain a duplicated day (the "day 3 repeats three times" bug).
        self._exec(
            "DELETE FROM SOC_REPLAY_FRAME "
            f"WHERE session_id = {_quote(session_id)} AND day = {int(day)}"
        )
        rows = self._exec(
            "SELECT COALESCE(MAX(global_idx), -1) AS g FROM SOC_REPLAY_FRAME "
            f"WHERE session_id = {_quote(session_id)}"
        )
        next_global = (rows[0][0] if rows else -1) + 1

        # The VARIANT columns we round-trip via PARSE_JSON. Keep this
        # list in the SAME order as the VALUES tuple below — the
        # SELECT references them by positional alias.
        json_keys = (
            "cells",
            "cells_player_p1",
            "cells_player_p2",
            "entities",
            "hoard",
            "collisions",
            "crushed_probes",
            "scheduled_orders",
            # v0.9 interdiction-weapon FX payloads.
            "emp",
            "mine",
            "chaff",
            "emp_clouds",
            # v0.9.4 — persistent mine snapshot per frame.
            "mines_active",
            # v0.9.11 — p3/p4 percepts. Appended at the END so the
            # ``json_keys[:8]`` / ``json_keys[8:]`` split below (which
            # straddles the attempted/outcome/hour scalar columns) is
            # unaffected; these ride in the ``[8:]`` trailing group.
            "cells_player_p3",
            "cells_player_p4",
        )
        cols = (
            "session_id, day, frame_idx, global_idx, caption, tag, owner, "
            "cells, cells_player_p1, cells_player_p2, entities, hoard, "
            "collisions, crushed_probes, scheduled_orders, attempted, "
            "outcome, hour, emp, mine, chaff, emp_clouds, mines_active, "
            "cells_player_p3, cells_player_p4"
        )
        # Alias list mirrors ``cols`` so the SELECT can lift PARSE_JSON
        # against the right positional name in the VALUES table.
        alias_list = (
            "session_id, day, frame_idx, global_idx, caption, tag, owner, "
            "cells_j, cells_p1_j, cells_p2_j, entities_j, hoard_j, "
            "collisions_j, crushed_probes_j, scheduled_orders_j, attempted, "
            "outcome, hour, emp_j, mine_j, chaff_j, emp_clouds_j, "
            "mines_active_j, cells_p3_j, cells_p4_j"
        )
        select_list = (
            "session_id, day, frame_idx, global_idx, caption, tag, owner, "
            "PARSE_JSON(cells_j), PARSE_JSON(cells_p1_j), "
            "PARSE_JSON(cells_p2_j), PARSE_JSON(entities_j), "
            "PARSE_JSON(hoard_j), PARSE_JSON(collisions_j), "
            "PARSE_JSON(crushed_probes_j), PARSE_JSON(scheduled_orders_j), "
            "attempted, outcome, hour, PARSE_JSON(emp_j), PARSE_JSON(mine_j), "
            "PARSE_JSON(chaff_j), PARSE_JSON(emp_clouds_j), "
            "PARSE_JSON(mines_active_j), PARSE_JSON(cells_p3_j), "
            "PARSE_JSON(cells_p4_j)"
        )

        # Build rows lazily so the chunker can slice arbitrary windows
        # without re-walking the source. Each row carries (frame, the
        # global_idx assigned to it).
        indexed = list(enumerate(frames))

        # 50 rows/statement is a safe ceiling for ~12 JSON blobs/row
        # (the cells blob is the heaviest, ~5–20 KB serialised). With
        # 50 rows that's ~1 MB worst-case which fits Snowflake's SQL
        # text cap with headroom; smaller batches degrade gracefully
        # but a typical night still finishes in 2–3 statements.
        for chunk in _chunks(indexed, 50):
            value_tuples: List[str] = []
            for offset, frame in chunk:
                # ``hour`` falls back to NULL (not 0) when the frame
                # predates the planetary night clock — same contract
                # the per-row writer used to honour.
                hour_val = frame.get("hour")
                hour_sql = (
                    _quote(int(hour_val))
                    if isinstance(hour_val, int)
                    else "NULL"
                )
                parts = [
                    _quote(session_id),
                    _quote(int(day)),
                    _quote(int(frame.get("frame_idx", offset))),
                    _quote(next_global + offset),
                    _quote(frame.get("caption")),
                    _quote(frame.get("tag")),
                    _quote(frame.get("owner")),
                ]
                # JSON-bearing columns ride as string literals; the
                # outer SELECT lifts each via PARSE_JSON.
                parts.extend(
                    _quote(_json(frame.get(k))) for k in json_keys[:8]
                )
                parts.append(_quote(frame.get("attempted")))
                parts.append(_quote(frame.get("outcome")))
                parts.append(hour_sql)
                parts.extend(
                    _quote(_json(frame.get(k))) for k in json_keys[8:]
                )
                value_tuples.append("(" + ", ".join(parts) + ")")
            sql = (
                f"INSERT INTO SOC_REPLAY_FRAME ({cols}) "
                f"SELECT {select_list} FROM (VALUES "
                + ", ".join(value_tuples)
                + f") AS v({alias_list})"
            )
            self._exec(sql)

    def list_replay_frames(
        self, session_id: str,
        day_from: Optional[int] = None,
        day_to: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        where = [f"session_id = {_quote(session_id)}"]
        if day_from is not None:
            where.append(f"day >= {int(day_from)}")
        if day_to is not None:
            where.append(f"day <= {int(day_to)}")
        rows = self._exec(
            "SELECT * FROM SOC_REPLAY_FRAME "
            f"WHERE {' AND '.join(where)} ORDER BY global_idx"
        )
        out: List[Dict[str, Any]] = []
        for r in rows:
            d = _row_to_dict(r)
            # VARIANT columns come back as JSON strings from the driver;
            # parse them so callers (and the watcher viewer-toggle) can
            # consume them as Python structures directly.
            for col in (
                "cells",
                "cells_player_p1",
                "cells_player_p2",
                "entities",
                "hoard",
                "collisions",
                "crushed_probes",
                "scheduled_orders",
                # v0.9 — interdiction-weapon FX arrays. Same VARIANT
                # JSON-string treatment as the v0.7 FX columns above.
                "emp",
                "mine",
                "chaff",
                "emp_clouds",
                # v0.9.4 — per-frame mine snapshot.
                "mines_active",
                # v0.9.11 — p3/p4 percepts (N-seat OBS replay).
                "cells_player_p3",
                "cells_player_p4",
            ):
                v = d.get(col)
                if isinstance(v, str):
                    try:
                        d[col] = json.loads(v)
                    except json.JSONDecodeError:
                        pass
            # Back-compat alias: the playing UI (app.js) still reads
            # `frame.cells_player`. Surface p1's snapshot under that key
            # until the Phase-5 viewer toggle replaces it.
            if d.get("cells_player") is None and d.get("cells_player_p1") is not None:
                d["cells_player"] = d["cells_player_p1"]
            # v0.9.11 — rebuild ``cells_by_seat`` from the per-seat
            # columns so the OBS view (which reads cells_by_seat first)
            # works on Snowflake-persisted replays, not just the
            # in-memory store that keeps the full frame dict.
            cbs = {}
            for seat in ("p1", "p2", "p3", "p4"):
                seat_cells = d.get(f"cells_player_{seat}")
                if seat_cells is not None:
                    cbs[seat] = seat_cells
            if cbs and d.get("cells_by_seat") is None:
                d["cells_by_seat"] = cbs
            out.append(d)
        return out

    def day_index(self, session_id: str) -> List[Dict[str, Any]]:
        rows = self._exec(
            "SELECT day, frame_count, first_global_idx, last_global_idx, "
            "       started_at, ended_at, first_caption, last_caption "
            "FROM SOC_DAY_INDEX "
            f"WHERE session_id = {_quote(session_id)} ORDER BY day"
        )
        return [_row_to_dict(r) for r in rows]

    # ── SOC_AGENT_INVOCATION ──────────────────────────────────────
    def append_agent_invocation(self, row: Mapping[str, Any]) -> None:
        self.append_agent_invocations([row])

    def append_agent_invocations(
        self, rows: Sequence[Mapping[str, Any]],
    ) -> None:
        """Batched agent-invocation insert (v1.5, P3).

        One ``MAX(seq)`` lookup + one multi-row ``INSERT`` for the whole
        fan-out instead of a SELECT+INSERT per bot. A 4-seat game (3 bots)
        drops from ~6 Snowflake round-trips to 2 per TRANSMIT. ``PARSE_JSON``
        is applied in the outer SELECT so each row's ``tool_calls`` still lands
        as a VARIANT. Assumes all rows share one ``session_id`` (they do — the
        fan-out is per session).
        """
        rows = [r for r in rows if r]
        if not rows:
            return
        sid = str(rows[0]["session_id"])
        seq_rows = self._exec(
            "SELECT COALESCE(MAX(seq), 0) AS s FROM SOC_AGENT_INVOCATION "
            f"WHERE session_id = {_quote(sid)}"
        )
        base_seq = (seq_rows[0][0] if seq_rows else 0)
        values = ",".join(
            "(" + ",".join([
                _quote(str(r["session_id"])),
                _quote(int(r["day"])),
                _quote(base_seq + offset + 1),
                _quote(str(r["agent_id"])),
                _quote(str(r["player"])),
                _quote(r.get("prompt_excerpt")),
                _quote(_json(r.get("tool_calls") or [])),
                _quote(r.get("rationale")),
                _quote(r.get("response_text")),
                _quote(r.get("ms_elapsed")),
                _quote(r.get("status") or "ok"),
            ]) + ")"
            for offset, r in enumerate(rows)
        )
        self._exec(
            "INSERT INTO SOC_AGENT_INVOCATION (session_id, day, seq, agent_id, "
            " player, prompt_excerpt, tool_calls, rationale, response_text, "
            " ms_elapsed, status) SELECT session_id, day, seq, agent_id, "
            " player, prompt_excerpt, PARSE_JSON(tool_calls), rationale, "
            " response_text, ms_elapsed, status FROM (VALUES "
            f"{values}) AS v(session_id, day, seq, agent_id, player, "
            " prompt_excerpt, tool_calls, rationale, response_text, "
            " ms_elapsed, status)"
        )

    def list_agent_invocations(
        self, session_id: str, day: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        where = [f"session_id = {_quote(session_id)}"]
        if day is not None:
            where.append(f"day = {int(day)}")
        rows = self._exec(
            "SELECT * FROM SOC_AGENT_INVOCATION "
            f"WHERE {' AND '.join(where)} ORDER BY seq"
        )
        return [_row_to_dict(r) for r in rows]


def _row_to_dict(row: Any) -> Dict[str, Any]:
    """Best-effort row -> dict that works with Snowpark Row or tuples."""
    if hasattr(row, "as_dict"):
        return {k.lower(): v for k, v in row.as_dict().items()}
    if hasattr(row, "_asdict"):
        return {k.lower(): v for k, v in row._asdict().items()}
    if isinstance(row, Mapping):
        return {k.lower(): v for k, v in row.items()}
    return {f"col{i}": v for i, v in enumerate(row)}


def _chunks(items: List[Any], n: int) -> Iterable[List[Any]]:
    for i in range(0, len(items), n):
        yield items[i : i + n]
