"""Backend factory for the snowpark engine layer.

Selects the :class:`SocStore` implementation that the FastAPI proxy and
the agent invoker share. The default is the **Snowflake-backed** store
so every season — whether driven by ``RED_HARVEST`` or by a Cortex AI
agent — persists into the deployment named by
:mod:`sea_of_colours.snowpark.naming` (``SOC_DATABASE`` / ``SOC_SCHEMA``,
defaulting to ``SOC_HACKATHON_DB.SEA_OF_COLOURS``). Set
``SOC_BACKEND=memory`` for fully-offline runs (unit tests, schema-less
dev sandboxes) where the in-memory ``InMemorySocStore`` keeps the
session state in process.

The Snowpark session is created on first use and reused — Snowflake will
auto-suspend the warehouse after the idle interval declared on the
warehouse itself, so we don't need to keepalive / suspend manually
(matches AA4's pattern in
``agent_arena_v4/orchestrator/snowflake_client.py``).
"""

from __future__ import annotations

import os
import threading
from typing import Optional

from sea_of_colours.snowpark.store import InMemorySocStore, SocStore


# Backend label resolved at import; lower-cased for forgiving matching.
# Default is "snowflake" — the running app persists every season. Tests
# explicitly opt back into "memory" via ``os.environ.setdefault`` before
# this module imports. ``file`` selects the local, cross-process,
# Snowflake-free :class:`FileSocStore` (one JSON file per season under
# ``SOC_STORE_DIR``) so a headless bot season and a watcher server can
# share the same on-disk seasons offline.
SOC_BACKEND = os.environ.get("SOC_BACKEND", "snowflake").strip().lower()

_lock = threading.Lock()
_memory_store: Optional[InMemorySocStore] = None
_file_store: Optional[SocStore] = None
_snowflake_store: Optional[SocStore] = None
_multi_store: Optional[SocStore] = None
_snowpark_session = None


def _get_memory_store() -> InMemorySocStore:
    global _memory_store
    with _lock:
        if _memory_store is None:
            _memory_store = InMemorySocStore()
        return _memory_store


def _get_file_store() -> SocStore:
    global _file_store
    with _lock:
        if _file_store is None:
            from sea_of_colours.snowpark.file_store import FileSocStore

            _file_store = FileSocStore()
        return _file_store


def _build_snowpark_session():
    """Create a Snowpark session from ``SF_CONFIG_FILE`` / ``~/.ssh/sf_config``."""
    config = os.environ.get(
        "SF_CONFIG_FILE", os.path.expanduser("~/.ssh/sf_config"),
    )
    # Lazy import so importing this module doesn't require snowpark when
    # SOC_BACKEND=memory (the default).
    from scripts.deploy_soc_schema import create_snowpark_session

    return create_snowpark_session(config)


def _get_snowflake_store() -> SocStore:
    global _snowflake_store, _snowpark_session
    with _lock:
        if _snowflake_store is None:
            from sea_of_colours.snowpark.snowpark_store import SnowparkSocStore

            if _snowpark_session is None:
                _snowpark_session = _build_snowpark_session()
            _snowflake_store = SnowparkSocStore(_snowpark_session)
        return _snowflake_store


def _get_multi_store() -> SocStore:
    """Composite store: Snowflake primary + local file secondary, merged.

    Lets one server surface both your durable Snowflake history *and* the
    offline file-backed bot seasons at once (each tagged with its source).
    The Snowflake session is built lazily through the factory, so a missing
    / unreachable warehouse degrades to local-only instead of failing the
    whole server.
    """
    global _multi_store
    # Build the secondary BEFORE taking ``_lock``: ``_get_file_store()``
    # acquires the same non-reentrant lock, so constructing it while we
    # already hold ``_lock`` would deadlock. The primary is passed as a
    # factory (not called here), so it adds no lock contention.
    secondary = _get_file_store()
    with _lock:
        if _multi_store is None:
            from sea_of_colours.snowpark.multi_store import CompositeSocStore

            _multi_store = CompositeSocStore(
                primary_factory=_get_snowflake_store,
                secondary=secondary,
            )
        return _multi_store


def get_store() -> SocStore:
    """Return the configured :class:`SocStore` for the current backend."""
    if SOC_BACKEND == "snowflake":
        return _get_snowflake_store()
    if SOC_BACKEND == "file":
        return _get_file_store()
    if SOC_BACKEND == "multi":
        return _get_multi_store()
    return _get_memory_store()


def reset_for_tests() -> None:
    """Reset module-level singletons. Tests only — never call from app code."""
    global _memory_store, _file_store, _snowflake_store, _multi_store
    global _snowpark_session
    with _lock:
        _memory_store = None
        _file_store = None
        _snowflake_store = None
        _multi_store = None
        _snowpark_session = None
