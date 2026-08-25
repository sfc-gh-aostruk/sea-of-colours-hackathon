"""FastAPI app — thin proxy over the SOC_* engine layer.

Every game route delegates to :mod:`sea_of_colours.snowpark.engine`. The
storage backend is **auto-detected** unless ``SOC_BACKEND`` names one:
``snowflake`` when the Snowpark deps and key-pair config are both
present, otherwise the zero-setup in-process ``memory`` store. The
resolved choice and the reason for it are printed at boot and served
from ``/api/meta/backend`` — see :mod:`sea_of_colours.snowpark.backend`.

Routes::

  GET  /                          SPA shell (player view)
  GET  /watch.html                SPA shell (watcher mode — alias of /)
  GET  /api/generate              Stateless map paint (spectator tooling)
  POST /api/game/new              SOC_INIT_SESSION
  GET  /api/game/latest           SOC_LIST_SESSIONS (most recent)
  GET  /api/sessions              Every persisted season (watcher picker)
  GET  /api/game/{id}/status      SOC_GET_SESSION_STATUS
  GET  /api/game/{id}/view        SOC_GET_VIEW (player percept + agent payload)
  GET  /api/game/{id}/observer    SOC_GET_OBSERVER
  GET  /api/game/{id}/replay      SOC_GET_REPLAY (multi-day)
  GET  /api/game/{id}/day-index   day-by-day frame counts (for scrub bar)
  POST /api/game/{id}/policy      SOC_SUBMIT_POLICY (resolves night when both ready)
  GET  /evals                     Eval command center SPA shell
  GET  /api/evals/scenarios       Every scenario in the harness + pass conditions
  GET  /api/evals/sessions        Past eval runs (filterable by scenario)
"""

from __future__ import annotations

import json
import random
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from sea_of_colours.agent.runtime import run_agent_turn
from sea_of_colours.evals.assertions import AssertionContext
from sea_of_colours.evals.scenarios import SCENARIOS
from sea_of_colours.generator import GenerationParams, generate_grid
from sea_of_colours.render import cell_visual
from sea_of_colours.snowpark import backend as soc_backend
from sea_of_colours.snowpark.backend import get_store
from sea_of_colours.snowpark import engine as soc_engine
from sea_of_colours.game.session import MAX_SEATS


# v0.9.6 — N-seat games (1..MAX_SEATS) use canonical slugs ``p1`` … ``pN``.
# Pre-N-seat code-paths hard-coded the 2-seat split, which now rejects p3/p4
# at the API surface even though the engine accepts them. This helper is the
# single gate: callers pass in any user-supplied seat slug and we accept it
# iff it parses as ``p<int>`` within the session-cap range. Centralising the
# rule here avoids drift between the three API endpoints that need it.
_VALID_SEAT_SLUGS: frozenset[str] = frozenset(f"p{i}" for i in range(1, MAX_SEATS + 1))


def _is_valid_seat_slug(player: str | None) -> bool:
    return isinstance(player, str) and player in _VALID_SEAT_SLUGS


# v0.9.12 — cross-browser multiplayer. Two humans on different machines can
# submit for the same game within milliseconds of each other. Each submit is a
# hydrate -> mutate -> save_session_full round-trip; without serialisation a
# concurrent pair can read the same pre-mutation snapshot and the second save
# clobbers the first seat's stash (lost-update). These endpoints are sync
# ``def`` handlers, so FastAPI runs them in a worker threadpool — an
# ``asyncio.Lock`` would not apply. We guard each game_id with a process-wide
# ``threading.Lock`` so the read-modify-write for a given session is atomic.
# (For multi-process / multi-host deploys this would need a store-level lock;
# a single ``uvicorn`` worker — the documented hosting path — is covered.)
_GAME_LOCKS: dict[str, threading.Lock] = {}
_GAME_LOCKS_GUARD = threading.Lock()


def _game_lock(game_id: str) -> threading.Lock:
    with _GAME_LOCKS_GUARD:
        lock = _GAME_LOCKS.get(game_id)
        if lock is None:
            lock = threading.Lock()
            _GAME_LOCKS[game_id] = lock
        return lock


# ── Background agent turns ("the agent thinks on your time") ─────────────
# A Cortex/harness seat's turn costs ~30-80s. If we only ran it when the
# human hits TRANSMIT, they'd wait that long every round. Instead a
# per-game daemon worker pre-fires pending bot seats the moment a phase
# opens (kicked on game create, every status poll, and after each human
# submit), so by the time the human submits the agent has usually already
# played. Each bot turn holds ``_game_lock`` — the Cortex submit and a
# human submit are a cross-process read/modify/write on the same
# ``json_state`` blob, so they MUST be serialised — but status polls are
# lock-free, so the "who's being waited on" timer keeps ticking live.
_BOT_WORKERS: dict[str, threading.Thread] = {}
_BOT_WORKERS_GUARD = threading.Lock()
# game_id -> {"seat", "agent", "started"} while a bot turn is in flight.
_BOT_TURN_STATE: dict[str, dict[str, Any]] = {}
_BOT_TURN_GUARD = threading.Lock()


def _set_bot_turn(game_id: str, seat: str, agent: str) -> None:
    with _BOT_TURN_GUARD:
        _BOT_TURN_STATE[game_id] = {
            "seat": seat, "agent": agent, "started": time.time(),
        }


def _clear_bot_turn(game_id: str) -> None:
    with _BOT_TURN_GUARD:
        _BOT_TURN_STATE.pop(game_id, None)


def _get_bot_turn(game_id: str) -> Optional[dict[str, Any]]:
    with _BOT_TURN_GUARD:
        st = _BOT_TURN_STATE.get(game_id)
        return dict(st) if st else None


# Once a seat lands a policy the store's ``pending`` flag makes the turn
# permanently idempotent (it's skipped on every subsequent kick). This
# ledger only guards the OTHER case: a turn that returned WITHOUT landing
# a policy (an exception before the heuristic fallback, or a mid-turn
# server reload). Without it a persistently failing agent would be
# re-fired back-to-back on every status poll. We record the last attempt
# per ``(seat, phase, day)`` and back off for a cooldown before retrying.
_BOT_ATTEMPT_TS: dict[str, dict[tuple, float]] = {}
_BOT_ATTEMPT_GUARD = threading.Lock()
_BOT_RETRY_COOLDOWN_S = 25.0


def _bot_attempt_recent(game_id: str, key: tuple) -> bool:
    with _BOT_ATTEMPT_GUARD:
        ts = (_BOT_ATTEMPT_TS.get(game_id) or {}).get(key)
    return ts is not None and (time.time() - ts) < _BOT_RETRY_COOLDOWN_S


def _bot_attempt_mark(game_id: str, key: tuple) -> None:
    with _BOT_ATTEMPT_GUARD:
        _BOT_ATTEMPT_TS.setdefault(game_id, {})[key] = time.time()


# How long a human submit will wait for the game lock before giving up and
# returning ``agent_busy`` (the agent is mid-turn holding it). Short so the
# HTTP request never hangs — the browser keeps its wait frame up and retries.
_AGENT_SUBMIT_LOCK_WAIT_S = 3.0
# Display hint for the UI countdown — the hard per-turn ceiling enforced by
# ``orchestrator_2/cortex_invoker.py`` (SOC_RED_REAPER_PILOT_V2 → 80s).
_AGENT_TURN_CAP_MS = 80_000


def _try_lock(game_id: str, timeout: float) -> Optional[threading.Lock]:
    """Acquire the per-game lock, or return ``None`` if it can't within
    ``timeout`` (the background agent turn is holding it)."""
    lk = _game_lock(game_id)
    return lk if lk.acquire(timeout=timeout) else None


def _agent_status_meta(game_id: str, status: dict[str, Any]) -> dict[str, Any]:
    """Build the ``waiting_on`` + ``bot_turn`` block shared by /status and
    the submit responses so the browser can drive the wait-frame timer."""
    meta: dict[str, Any] = {}
    agents = status.get("agents") or {}
    pending = status.get("pending") or {}
    players = status.get("players") or list(agents.keys())
    phase = str(status.get("phase") or "")
    if phase and phase != "season_complete":
        waiting = []
        for s in players:
            if pending.get(s, False):
                continue
            is_human = str(agents.get(s, "human")).strip().lower() == "human"
            waiting.append({
                "seat": s,
                "agent": str(agents.get(s, "human")),
                "is_human": is_human,
            })
        meta["waiting_on"] = waiting
    turn = _get_bot_turn(game_id)
    if turn:
        meta["bot_turn"] = {
            "seat": turn["seat"],
            "agent": turn["agent"],
            "elapsed_ms": int(max(0.0, time.time() - turn["started"]) * 1000),
            "cap_ms": _AGENT_TURN_CAP_MS,
        }
    return meta


def _run_bot_turn(store, game_id: str, seat: str, agent_label: str) -> None:
    """Run one bot seat's turn through orchestrator_2, publishing live
    turn state for the UI timer for its whole duration."""
    from sea_of_colours.orchestrator_2.runtime import (
        run_agent_turn as _v2_run_agent_turn,
    )
    _set_bot_turn(game_id, seat, agent_label)
    try:
        _v2_run_agent_turn(store, game_id, seat, agent_label=agent_label)
    finally:
        _clear_bot_turn(game_id)


def _drive_bots(game_id: str, *, max_turns: int = 64) -> None:
    """Fire pending BOT seats (Cortex/harness) until a human is needed or
    the season completes. Store-based, night resolved with the local
    engine (populates the combat kill feed) — mirrors the season runner.

    Each iteration takes ``_game_lock`` so a bot turn never races a human
    submit on the shared ``json_state`` blob. Humans are never fired — the
    loop returns and hands control back to the browser. Runs in the
    background worker (``_kick_bots``); human submits are non-blocking and
    the browser polls /status for the resolution this produces.
    """
    store = _store()
    for _ in range(max_turns):
        with _game_lock(game_id):
            status = soc_engine.get_session_status(store, game_id)
            if str(status.get("phase") or "") == "season_complete":
                return
            agents = status.get("agents") or {}
            pending = status.get("pending") or {}
            players = status.get("players") or list(agents.keys())
            phase, day = status.get("phase"), status.get("day")

            bot_seat = None
            human_pending = False
            deferred_bot = False  # a bot we're backing off from (recent miss)
            for s in players:
                if pending.get(s, False):
                    continue  # already landed a policy — permanently skipped
                if str(agents.get(s, "human")).strip().lower() == "human":
                    human_pending = True
                    continue
                # A bot that hasn't landed a policy. If we tried it very
                # recently and it still hasn't stashed, back off (avoids a
                # tight retry loop on a failing/interrupted agent).
                if _bot_attempt_recent(game_id, (s, phase, day)):
                    deferred_bot = True
                    continue
                bot_seat = s
                break

            if bot_seat is None:
                # Don't force a resolve while a bot is merely in cooldown —
                # it hasn't submitted, so run_night would be premature.
                if human_pending or deferred_bot:
                    return  # waiting on a human / cooling-down bot
                # Everyone submitted but the phase hasn't advanced — resolve
                # the night locally (orbit auto-resolves on submit).
                before = cur
                try:
                    soc_engine.run_night(store, game_id)
                except Exception as exc:  # pragma: no cover — defensive
                    print(f"[soc] _drive_bots run_night crashed: {exc}",
                          file=sys.stderr, flush=True)
                    return
                after = soc_engine.get_session_status(store, game_id)
                if (after.get("phase"), after.get("day")) == before:
                    return  # no progress — avoid spin
                continue

            # Fire this bot seat (holds the lock for the whole ~80s turn).
            # Mark the attempt first: a successful turn lands a policy and is
            # skipped via ``pending`` next loop; a failed one is skipped via
            # the cooldown so we don't hammer it.
            _bot_attempt_mark(game_id, (bot_seat, phase, day))
            try:
                _run_bot_turn(
                    store, game_id, bot_seat,
                    str(agents.get(bot_seat) or ""),
                )
            except Exception as exc:  # pragma: no cover — defensive
                print(f"[soc] _drive_bots seat={bot_seat} crashed: {exc}",
                      file=sys.stderr, flush=True)
                return


def _kick_bots(game_id: str) -> None:
    """Ensure a background worker is draining this game's pending bot seats.

    Idempotent: a no-op if a worker is already running for the game. Cheap
    to call on every status poll — the thread exits immediately when
    there's nothing for a bot to do (only humans pending / season over).
    """
    with _BOT_WORKERS_GUARD:
        existing = _BOT_WORKERS.get(game_id)
        if existing is not None and existing.is_alive():
            return

        def _worker() -> None:
            try:
                _drive_bots(game_id)
            except Exception as exc:  # pragma: no cover — defensive
                print(f"[soc] bot worker for {game_id} crashed: {exc}",
                      file=sys.stderr, flush=True)
            finally:
                with _BOT_WORKERS_GUARD:
                    if _BOT_WORKERS.get(game_id) is t:
                        _BOT_WORKERS.pop(game_id, None)

        t = threading.Thread(target=_worker, name=f"bots-{game_id[:8]}",
                             daemon=True)
        _BOT_WORKERS[game_id] = t
        t.start()


# Runtime labels the /agent/think route accepts. Mirrors
# ``agent.runtime._SUPPORTED_RUNTIMES`` — the engine raises on anything
# else, but rejecting at the API boundary gives a 400 instead of a 500.
_HEURISTIC_RUNTIMES = ("heuristic", "red_harvest_lite")

_STATIC_DIR = Path(__file__).resolve().parent / "static"
_REPO_ROOT = Path(__file__).resolve().parent.parent
_MANUAL_DIR = _REPO_ROOT / "manual"
_GUIDE_DIR = _REPO_ROOT / "guide"
_DOCS_DIR = _REPO_ROOT / "docs"
_INDEX_HTML = _STATIC_DIR / "index.html"
_EVALS_HTML = _STATIC_DIR / "evals.html"
_MOBILE_HTML = _STATIC_DIR / "mobile.html"
_LANDING_HTML = _STATIC_DIR / "landing.html"

# ── Boot banner ────────────────────────────────────────────────────────
# Resolve and OPEN the store here, before serving. Building the Snowpark
# session lazily meant a bad key or an undeployed schema surfaced as a
# 500 on whichever API call happened to come first — nowhere near the
# command the operator had just run.
def _boot_banner() -> None:
    print("[soc] FastAPI starting", file=sys.stderr, flush=True)
    try:
        res = soc_backend.probe_store()
    except soc_backend.BackendUnavailable as exc:
        print(f"[soc] {exc}", file=sys.stderr, flush=True)
        if exc.fix:
            print(f"[soc]   fix: {exc.fix}", file=sys.stderr, flush=True)
        # Explicit request, explicit failure: don't limp along on a
        # backend they didn't ask for and silently lose their seasons.
        sys.exit(2)

    print(f"[soc] {res.summary()}", file=sys.stderr, flush=True)
    print(f"[soc]   {res.reason}", file=sys.stderr, flush=True)
    if res.fix:
        # Only call it a fix when something the operator asked for
        # failed. Landing on memory because no Snowflake setup exists is
        # the normal, supported outcome, and labelling that "fix" tells a
        # first-timer their working install is broken.
        label = "fix" if res.requested != "auto" else "for persistence"
        print(f"[soc]   {label}: {res.fix}", file=sys.stderr, flush=True)
    if not res.persists:
        # Be precise about what memory does and doesn't cost you. It is
        # the supported zero-setup path: human seats, both heuristics,
        # and the in-process V12 harness (which reaches Cortex over REST
        # with a PAT) all work fine. The only thing you lose is
        # durability across a restart.
        print(
            "[soc]   human seats, RED_HARVEST/_LITE and V12 all work on "
            "memory; you only lose seasons across a restart.",
            file=sys.stderr,
            flush=True,
        )


_boot_banner()

app = FastAPI(
    title="Sea of Colours",
    description="Orchestrator surface for the Sea of Colours world.",
    version="0.4.0",
)

# Replay payloads are large, highly-repetitive JSON (per-frame fog grids).
# Gzip compresses them ~10-30x on the wire so the multi-MB replay download
# stays small even though the parsed shape is still substantial.
app.add_middleware(GZipMiddleware, minimum_size=2048)

class _NoCacheStatic(StaticFiles):
    """Serve static assets with ``Cache-Control: no-cache`` headers.

    Browsers aggressively cache `/static/app.js` and `/static/styles.css`,
    so iterating on the UI without a hard-reload would silently keep
    serving stale code. For a dev-only orchestrator like this one we
    prefer freshness over the trivial bandwidth savings. The browser
    still gets ETag validation under the hood — `no-cache` just forces
    a re-check on every request.
    """

    async def get_response(self, path: str, scope):  # type: ignore[override]
        response = await super().get_response(path, scope)
        response.headers.setdefault(
            "Cache-Control", "no-cache, no-store, must-revalidate"
        )
        response.headers.setdefault("Pragma", "no-cache")
        response.headers.setdefault("Expires", "0")
        return response


class _DocsStatic(_NoCacheStatic):
    """Static files, but Markdown is served as text the browser will show.

    Starlette types ``.md`` as ``text/markdown``, which browsers download
    rather than render — so a doc link would silently produce a file in
    ~/Downloads instead of a page. Markdown is designed to read fine as
    plain text, so overriding the type is enough; rendering it properly
    would mean adding a Markdown dependency for a handful of links.
    """

    async def get_response(self, path: str, scope):  # type: ignore[override]
        response = await super().get_response(path, scope)
        if path.lower().endswith(".md"):
            response.headers["Content-Type"] = "text/plain; charset=utf-8"
        return response


app.mount("/static", _NoCacheStatic(directory=_STATIC_DIR), name="static")

# v1.12 — serve the two reader-facing document trees over HTTP as well.
# They were built as self-contained file:// pages and still work that
# way, but that meant the only way to share them was "clone the repo and
# open a folder". Mounting them lets a host hand out a URL — including
# over the multiplayer tunnel — and costs nothing, since both are plain
# static assets. `html=True` makes /guide/ and /manual/ serve index.html.
if _MANUAL_DIR.is_dir():
    app.mount(
        "/manual", _NoCacheStatic(directory=_MANUAL_DIR, html=True), name="manual",
    )
if _GUIDE_DIR.is_dir():
    app.mount(
        "/guide", _NoCacheStatic(directory=_GUIDE_DIR, html=True), name="guide",
    )
if _DOCS_DIR.is_dir():
    app.mount("/docs", _DocsStatic(directory=_DOCS_DIR), name="docs")


@app.get("/{name:path}.md", include_in_schema=False)
def api_root_markdown(name: str) -> Response:
    """Serve the root-level Markdown the guide links to (README, RULEBOOK).

    Restricted to a fixed set rather than resolving arbitrary paths: this
    route sits at the URL root, so anything looser would be a directory
    traversal waiting to happen.
    """
    allowed = {"README", "RULEBOOK", "AGENTS"}
    if name not in allowed:
        raise HTTPException(status_code=404, detail="not found")
    path = _REPO_ROOT / f"{name}.md"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="not found")
    return Response(
        content=path.read_text(encoding="utf-8"),
        media_type="text/plain; charset=utf-8",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


def _rgb(triple: tuple[int, int, int]) -> str:
    return f"rgb({triple[0]},{triple[1]},{triple[2]})"


def _store():
    """Return the configured SOC_* storage backend."""
    return get_store()


# ── Slow-agent (Cortex / harness) live bot fan-out ──────────────────────
# Seats tagged with a non-heuristic agent (e.g. ``"pilot_v2"``) can't run
# through the fast in-memory heuristic fan-out (``_fire_bots_in_memory``):
# that path is hardcoded to RED_HARVEST and silently downgrades the agent.
# For any game containing such a seat we instead drive every pending bot
# seat through orchestrator_2 (store-based submit + local night
# resolution), mirroring the headless season runner. This is slower
# (~30-70s per Cortex turn) but is the only correct path for a real agent.
_HEURISTIC_AGENT_LABELS = {"human", "red_harvest", "heuristic"}


def _game_has_slow_bot(agents: dict[str, Any]) -> bool:
    """True when any seat runs a non-heuristic agent (Cortex / harness)."""
    return any(
        str(v).strip().lower() not in _HEURISTIC_AGENT_LABELS
        for v in (agents or {}).values()
    )


def _llm_seats(agents: dict[str, Any]) -> list[str]:
    """Seats bound to an in-process LLM harness (V12 and friends)."""
    from sea_of_colours.orchestrator_2.binding_registry import (
        AGENT_LABEL_BINDINGS,
    )

    out = []
    for seat, label in (agents or {}).items():
        binding = AGENT_LABEL_BINDINGS.get(str(label).strip().lower())
        if binding is not None and binding.kind == "harness_in_process":
            out.append(str(seat))
    return sorted(out)


def _preflight_llm_credentials(agents: dict[str, Any]) -> None:
    """Refuse to start a game whose LLM seat could never think.

    Without a PAT the harness doesn't error — it falls back and passes
    every night with zero moves, so the player watches "V12" sit still
    and concludes the agent is broken. Catch it at creation, where we
    can name the fix, rather than letting it look like a game bug.
    """
    seats = _llm_seats(agents)
    if not seats:
        return
    from sea_of_colours.orchestrator_2.cortex_chat import credentials_status

    ready, reason = credentials_status()
    if ready:
        return
    raise HTTPException(
        status_code=400,
        detail=(
            f"Seat(s) {', '.join(seats)} are set to an LLM agent, but "
            f"Snowflake credentials are missing: needs {reason}. "
            f"See docs/SNOWFLAKE_SETUP.md. To play right now with no "
            f"setup, pick RED_HARVEST_LITE or RED_HARVEST instead."
        ),
    )


_NO_CACHE_HEADERS = {
    "Cache-Control": "no-cache, no-store, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0",
}


@app.get("/")
def index() -> FileResponse:
    """Landing / title screen — Play / Multiplayer / Replay over a looping
    hero background. The command centre SPA lives at ``/play``; deep links
    (``?session=``/``?player=``/``?season=``) are path-agnostic so they keep
    working against ``/play`` and ``/watch.html``."""
    return FileResponse(_LANDING_HTML, headers=_NO_CACHE_HEADERS)


@app.get("/play")
def play_shell() -> FileResponse:
    """Command-centre SPA (formerly served at ``/``)."""
    return FileResponse(_INDEX_HTML, headers=_NO_CACHE_HEADERS)


@app.get("/evals")
def evals_shell() -> FileResponse:
    """Eval command center SPA shell.

    Standalone single-page app that lists every scenario in
    :data:`sea_of_colours.evals.scenarios.SCENARIOS`, surfaces each
    one's assertions as a "pass conditions" headline, and embeds the
    watcher for any past eval session via the
    :func:`api_evals_sessions` endpoint. Lives next to ``/`` rather
    than under ``/watch.html`` because the read-only watcher and the
    eval browser have very different chrome.
    """
    return FileResponse(_EVALS_HTML, headers=_NO_CACHE_HEADERS)


@app.get("/mobile")
def mobile_shell() -> FileResponse:
    return FileResponse(_MOBILE_HTML, headers=_NO_CACHE_HEADERS)


@app.get("/watch.html")
def watch_shell() -> FileResponse:
    """Watcher entry point — Phase C.

    Serves the same SPA shell as ``/`` but is the canonical URL the CLI
    season runner prints in its post-run summary (``/watch.html?season=
    <slug>``). The frontend reads ``?session=<id>`` / ``?season=<slug>``
    / ``?watch=1`` from the URL on boot and switches into a read-only
    watcher mode that hides the policy / NEW GAME controls and loads
    the requested season's replay end-to-end.
    """
    return FileResponse(_INDEX_HTML, headers=_NO_CACHE_HEADERS)


@app.get("/api/generate")
def api_generate(
    seed: Optional[int] = Query(None, description="Deterministic seed; random when omitted."),
    width: int = Query(80, ge=4, le=400),
    height: int = Query(50, ge=4, le=400),
) -> dict:
    """Stateless map paint (spectator tooling — not session-bound)."""
    if seed is None:
        seed = random.randrange(2**31)
    params = GenerationParams(width=width, height=height, seed=seed)
    grid = generate_grid(params)
    cells: list[dict[str, Any]] = []
    for row in grid:
        for cell in row:
            fg, bg, ch = cell_visual(cell)
            entry: dict[str, Any] = {"ch": ch, "bg": _rgb(bg)}
            if fg is not None:
                entry["fg"] = _rgb(fg)
            cells.append(entry)
    return {"seed": seed, "width": width, "height": height, "cells": cells}


@app.get("/api/game/palette")
def api_game_palette() -> dict[str, Any]:
    """Return the curated seat color palette for player customization.
    
    v0.9.18 — exposes SEAT_COLOR_PALETTE from session.py so the new-game
    modal can render swatches and validate user picks without duplicating
    the palette definition.
    """
    from sea_of_colours.game.session import SEAT_COLOR_PALETTE, SEAT_DEFAULT_COLORS
    return {
        "palette": [
            {"hex": hex_color, "rgb": list(rgb)}
            for hex_color, rgb in SEAT_COLOR_PALETTE.items()
        ],
        "defaults": dict(SEAT_DEFAULT_COLORS),
    }


@app.post("/api/game/new")
def api_game_new(
    payload: Optional[dict[str, Any]] = None,
    seed: Optional[int] = Query(None),
    width: int = Query(40, ge=8, le=200),
    height: int = Query(28, ge=8, le=200),
    season_day_cap: Optional[int] = Query(
        None,
        ge=1,
        le=60,
        description=(
            "Number of nights in the season. Defaults to "
            "SEASON_DAY_CAP (v0.9.18: 7). Clamped to 1..60."
        ),
    ),
) -> dict[str, Any]:
    """Start a new game. v0.9.6 — accepts the N-seat launcher payload.

    Query params (``seed`` / ``width`` / ``height`` / ``season_day_cap``)
    survive for the legacy "open watcher" path. The optional JSON
    body lets the new-game modal override those AND specify:

    * ``players``: list of seat ids in canonical order (1-4 entries,
      defaults to ``["p1", "p2"]``).
    * ``agents``: per-seat agent assignment, e.g.
      ``{"p1": "human", "p2": "red_harvest"}``. Defaults every seat
      to ``"human"``.
    * ``visibility_mode``: ``"hidden"`` (default, fog-of-war) or
      ``"open"`` (omniscient, OBS-style).
    """
    body = payload or {}

    def _maybe_int(value: Any) -> Optional[int]:
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    body_seed = _maybe_int(body.get("seed"))
    if body_seed is not None:
        seed = body_seed
    body_width = _maybe_int(body.get("width"))
    if body_width is not None:
        width = max(8, min(200, body_width))
    body_height = _maybe_int(body.get("height"))
    if body_height is not None:
        height = max(8, min(200, body_height))
    body_cap = _maybe_int(body.get("season_day_cap"))
    if body_cap is not None:
        season_day_cap = max(1, min(60, body_cap))

    raw_players = body.get("players")
    players: Optional[list[str]] = None
    if isinstance(raw_players, list) and raw_players:
        players = [str(p) for p in raw_players][:4]
    raw_agents = body.get("agents") or {}
    agents: dict[str, str] = {}
    if isinstance(raw_agents, dict):
        for k, v in raw_agents.items():
            agents[str(k)] = str(v).strip().lower() or "human"
    _preflight_llm_credentials(agents)
    visibility_mode = str(body.get("visibility_mode") or "hidden").strip().lower()
    if visibility_mode not in ("hidden", "open"):
        visibility_mode = "hidden"
    
    # v0.9.18 — extract player_profiles from body (custom names/tags/colors)
    raw_profiles = body.get("player_profiles")
    player_profiles: Optional[dict[str, dict[str, str]]] = None
    if isinstance(raw_profiles, dict):
        player_profiles = {}
        for seat, prof in raw_profiles.items():
            if isinstance(prof, dict):
                player_profiles[str(seat)] = {
                    "display_name": str(prof.get("display_name", "")),
                    "tag": str(prof.get("tag", ""))[:3].upper(),
                    "color": str(prof.get("color", "")).upper(),
                }

    if seed is None:
        seed = random.randrange(2**31)
    created = soc_engine.init_session(
        _store(),
        seed=seed,
        width=width,
        height=height,
        season_day_cap=season_day_cap,
        players=players,
        agents=agents or None,
        visibility_mode=visibility_mode,
        player_profiles=player_profiles,
    )
    # v1.11 — kick the background bot worker so any Cortex/harness seat
    # starts thinking the moment the game exists, in parallel with the
    # human opening the board (agent plays on the human's time).
    if _game_has_slow_bot(agents) and isinstance(created, dict):
        gid = created.get("session_id")
        if isinstance(gid, str) and gid:
            _kick_bots(gid)
    return created


def _is_eval_session(row: dict[str, Any]) -> bool:
    """True when a session row carries the eval command-center tag.

    Eval-recorded sessions (see
    :func:`sea_of_colours.evals.runner.run_scenario`) set
    ``season_name`` to ``eval:<scenario>:<config>`` so the watcher
    UI's season picker can filter them out — evals aren't gameplay
    seasons and shouldn't clutter the main "open a saved game"
    dropdown. The same predicate gates the NEW-GAME wipe so eval
    sessions survive across season changes.
    """
    return str(row.get("season_name") or "").startswith("eval:")


@app.get("/api/game/latest")
def api_game_latest() -> dict[str, Any]:
    # Walk in last-touched order until we find a non-eval session — the
    # watcher's "open the most recent game" affordance shouldn't pop
    # straight into an eval replay (those have their own UI at /evals).
    for row in _store().list_sessions():
        if _is_eval_session(row):
            continue
        return {
            "session_id": row["session_id"],
            "day": row.get("day"),
            "phase": row.get("phase"),
            "width": row.get("width"),
            "height": row.get("height"),
        }
    raise HTTPException(status_code=404, detail="no sessions yet")


@app.get("/api/sessions")
def api_sessions(
    season: Optional[str] = Query(
        None,
        description=(
            "Filter to a single season by URL slug (e.g. 'glacies-helix'). "
            "When provided, returns at most one row — used by the watcher's "
            "?season=<slug> deep-link path."
        ),
    ),
) -> dict[str, Any]:
    """List every persisted season for the watcher frontend.

    See :func:`sea_of_colours.snowpark.engine.list_sessions` for the
    enriched per-row shape. Sessions are returned in ``last_touched_at
    DESC`` order so the most recent CLI / UI run is first.

    Pass ``?season=<slug>`` to resolve a slug-only deep-link (used by
    the CLI runner's printed watch URL); the response then contains
    zero or one entry depending on whether the slug matches.
    """
    store = _store()
    if season:
        row = soc_engine.find_session_by_slug(store, season)
        if row and _is_eval_session(row):
            # Slug-resolution still works for eval sessions (handy
            # for sharing deep links) but we hide them from the
            # picker dropdown — the eval UI at /evals is the
            # canonical surface for them.
            return {"sessions": []}
        return {"sessions": [row] if row else []}
    payload = soc_engine.list_sessions(store)
    payload["sessions"] = [
        s for s in payload.get("sessions") or [] if not _is_eval_session(s)
    ]
    return payload


@app.delete("/api/game/{game_id}")
def api_game_delete(game_id: str) -> dict[str, Any]:
    """Permanently delete one replay/session (the watcher's bin control).

    Refuses eval-tagged sessions (those belong to the /evals surface).
    Routes to whichever backend owns the id under the composite store, so
    a local file season and a Snowflake season are both deletable from the
    same picker. Deleting a missing id is a no-op (still returns ok)."""
    store = _store()
    row = store.load_session(game_id)
    if row is not None and _is_eval_session(row):
        raise HTTPException(
            status_code=403,
            detail="eval sessions can't be deleted from the watcher",
        )
    store.delete_session(game_id)
    return {"ok": True, "session_id": game_id}


# ---------------------------------------------------------------------
# Eval command center API
# ---------------------------------------------------------------------
@app.get("/api/evals/scenarios")
def api_evals_scenarios() -> dict[str, Any]:
    """List every scenario in the harness with its pass conditions.

    The frontend renders one sidebar entry per scenario and a
    headline-table of ``describe()`` strings — see
    :meth:`sea_of_colours.evals.assertions.Assertion.describe`. We
    return ``tags`` so the sidebar can group/colour items (e.g. the
    spatial-reasoning trio used by the Phase 1 A/B).
    """
    out: list[dict[str, Any]] = []
    for s in SCENARIOS:
        out.append(
            {
                "name": s.name,
                "summary": s.summary,
                "player": s.player,
                "tags": list(s.tags),
                "assertions": [
                    {"name": a.name, "describe": a.describe()}
                    for a in s.assertions
                ],
            }
        )
    return {"scenarios": out}


def _parse_eval_season(season_name: Optional[str]) -> Optional[tuple[str, str]]:
    """Parse ``eval:<scenario>:<config>`` season labels.

    Returns ``None`` for non-eval seasons (so the UI can ignore them)
    and ``(scenario_name, config_label)`` for tagged eval rows.
    All eval-recorded sessions get this tag at write time in
    :func:`sea_of_colours.evals.runner.run_scenario`; the 12
    pre-tagger legacy rows were backfilled with
    ``eval:<scenario>:legacy`` tags so every eval session
    classifies through this one function — no fingerprint
    fallback required.
    """
    if not season_name or not season_name.startswith("eval:"):
        return None
    parts = season_name.split(":", 2)
    if len(parts) != 3:
        return None
    return parts[1], parts[2]


@app.get("/api/evals/sessions")
def api_evals_sessions(
    scenario: Optional[str] = Query(
        None, description="Filter to a single scenario name."
    ),
) -> dict[str, Any]:
    """Past eval sessions, optionally filtered to one scenario.

    Resolves each session's scenario + config from its
    ``eval:<scenario>:<config>`` season-name tag — newly-recorded
    eval runs set this in :func:`run_scenario` and legacy sessions
    were backfilled with ``eval:<scenario>:legacy`` tags by the
    one-shot in
    ``scripts/`` (see chat history). Untagged sessions are
    treated as gameplay and ignored here. Every returned entry
    carries everything the command-center UI needs to render a row
    without follow-up calls: ``passed`` (re-evaluated against the
    stored policy + post-night session state), ``per_assertion``
    for the verdict breakdown, ``policy`` to surface drop / chain
    coords, and a ``watch_url`` for the embedded iframe.

    Returned newest-first — the underlying
    :func:`SocStore.list_sessions` already orders by
    ``last_touched_at DESC``.
    """
    store = _store()
    scenarios_by_name = {s.name: s for s in SCENARIOS}
    rows = store.list_sessions()

    out: list[dict[str, Any]] = []
    for row in rows:
        sid = row["session_id"]
        tag = _parse_eval_season(row.get("season_name"))
        if tag is None:
            # Untagged = gameplay session. The watcher owns those,
            # not the eval command center.
            continue
        scen_name, config_label = tag
        is_tagged = True

        # Optional scenario filter — applied before policy lookup so
        # we skip expensive store calls for sessions the caller
        # isn't asking about.
        if scenario and scen_name != scenario:
            continue

        # Fetch the submitted policy. After a night resolves,
        # ``row.day`` has already advanced by one, so we look up
        # against day-1 first — that's where the harvester run we
        # want to inspect lives. For unresolved fixtures the
        # original day still works, so we fall back to that.
        day = int(row.get("day") or 0)
        p1_pol: list[dict[str, Any]] = []
        policy_day: Optional[int] = None
        for try_day in (day - 1, day):
            if try_day < 0:
                continue
            policies = store.list_policies(sid, try_day) or {}
            cand = policies.get("p1") or []
            if cand:
                p1_pol = list(cand)
                policy_day = try_day
                break
        night_resolved = policy_day is not None and policy_day < day

        # Evaluate the scenario's assertions against the stored
        # policy. Structural checks (HarvesterChainHits, MustAvoid,
        # EndsWithPickup, …) are pure functions of the move queue and
        # always reliable. Context-sensitive checks (MinExpectedValue
        # reads ``cell_purity``; NoSyntheticGreenSteps reads
        # ``is_synthetic_green``) inspect the live cell state — which
        # has been MUTATED by the resolved night for replay-enabled
        # sessions (the RED the agent harvested is gone, so
        # MinExpectedValue scores 0). For those rows we surface a
        # "n/a" verdict instead of a misleading FAIL — the pass
        # condition is still listed in the headline so the user
        # knows what was being tested; we just can't reconstruct
        # the answer from post-night state.
        _CONTEXT_SENSITIVE = ("MinExpectedValue", "NoSyntheticGreenSteps")
        per_assertion: list[dict[str, Any]] = []
        all_passed = True
        scen_def = scenarios_by_name.get(scen_name)
        if scen_def is not None and p1_pol:
            try:
                sess = soc_engine._hydrate_session(store, sid)
                ctx = AssertionContext(
                    session=sess,
                    player=scen_def.player,
                    day_at_run=(policy_day if policy_day is not None else day),
                )
                for a in scen_def.assertions:
                    if night_resolved and a.name in _CONTEXT_SENSITIVE:
                        per_assertion.append(
                            {
                                "name": a.name,
                                "passed": None,
                                "detail": "n/a (post-night state)",
                            }
                        )
                        continue
                    res = a.evaluate(p1_pol, context=ctx)
                    per_assertion.append(
                        {
                            "name": res.name,
                            "passed": res.passed,
                            "detail": res.detail,
                        }
                    )
                    if not res.passed:
                        all_passed = False
            except Exception:
                # Best-effort — surface the session without verdicts
                # if we can't hydrate (corrupt blob, missing schema).
                per_assertion = []
                all_passed = False

        drop_coord = next(
            (mv.get("at") for mv in p1_pol if mv.get("a") == "drop"), None,
        )
        n_steps = sum(1 for mv in p1_pol if mv.get("a") == "step")
        n_probes = sum(1 for mv in p1_pol if mv.get("a") == "probe")

        # Surface the Cortex agent identity (e.g. SOC_RED_REAPER_LIST
        # vs SOC_RED_REAPER_GRID) by reaching into SOC_AGENT_INVOCATION.
        # We take the LAST invocation on ``policy_day`` for the seat
        # under test — that's the row whose ``agent_id`` matches the
        # ``soc_submit_policy`` call (earlier rows on the same day are
        # ``soc_save_rationale`` followups or aborted Cortex attempts).
        # ``has_prompt`` lets the transcript tab tell the user up-front
        # whether the model's input was recorded (post-Phase-1 runs) or
        # is lost to history (legacy + heuristic-only runs).
        agent_id: Optional[str] = None
        has_prompt = False
        if (
            scen_def is not None
            and policy_day is not None
            and hasattr(store, "list_agent_invocations")
        ):
            try:
                invocations = store.list_agent_invocations(sid, day=policy_day)
            except Exception:
                invocations = []
            seat = scen_def.player
            seat_rows = [
                r for r in invocations
                if str(r.get("player") or "").lower() == seat
            ]
            if seat_rows:
                # ``list_agent_invocations`` orders by ``seq`` ASC, so
                # the last entry is the most recent turn for this seat.
                latest = seat_rows[-1]
                agent_id = latest.get("agent_id")
                has_prompt = bool(latest.get("prompt_excerpt"))

        out.append(
            {
                "session_id": sid,
                "scenario": scen_name,
                "config": config_label,
                "tagged": is_tagged,
                "agent_id": agent_id,
                "has_prompt": has_prompt,
                "passed": bool(per_assertion) and all_passed,
                "per_assertion": per_assertion,
                "drop": drop_coord,
                "n_steps": n_steps,
                "n_probes": n_probes,
                "n_moves": len(p1_pol),
                "day": row.get("day"),
                "policy_day": policy_day,
                "player": scen_def.player if scen_def else "p1",
                "watch_url": f"/?session={sid}",
            }
        )

    return {"sessions": out}


@app.get("/api/game/{game_id}/status")
def api_game_status(game_id: str) -> dict[str, Any]:
    try:
        status = soc_engine.get_session_status(_store(), game_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    # v1.11 — if the game has a slow (Cortex/harness) seat, make sure the
    # background worker is draining it so the agent thinks while the human
    # deliberates. Idempotent + cheap (no-op when nothing's pending).
    if _game_has_slow_bot(status.get("agents") or {}):
        _kick_bots(game_id)
    # Surface who's being waited on + the in-flight bot turn for the UI timer.
    status.update(_agent_status_meta(game_id, status))
    return status


@app.post("/api/game/{game_id}/orbit")
def api_game_orbit(game_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Submit a seat's Orbit phase action queue (v0.8.0).

    Mirrors :func:`api_game_policy` for the daytime ORBIT phase.
    Payload shape: ``{"player": "<seat_id>", "actions": [...]}`` where
    each action follows the discriminator schema declared in
    :mod:`sea_of_colours.game.policy`. v0.9.6 — accepts any seat
    in :attr:`GameSession.players` (1-4 seats).
    """
    player = payload.get("player")
    if not isinstance(player, str) or not player:
        raise HTTPException(status_code=400, detail="player is required")
    actions_field: Any = payload.get("actions", payload.get("commands"))
    if actions_field is None:
        actions_field = []
    pre_status = soc_engine.get_session_status(_store(), game_id)
    slow = _game_has_slow_bot(pre_status.get("agents") or {})

    # ── Fast path: no slow agent — unchanged legacy behaviour. ──────────
    if not slow:
        with _game_lock(game_id):
            try:
                result = soc_engine.submit_orbit_actions(
                    _store(), game_id, player, actions_field, auto_fire_bots=True,
                )
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
        status = soc_engine.get_session_status(_store(), game_id)
        return {
            "ok": result["ok"],
            "errors": result.get("errors") or [],
            "pending_orbit": status.get("pending") or {},
            "phase": status.get("phase") or result.get("phase"),
            "day": status.get("day") or result.get("day"),
            "orbit_resolved": result.get("orbit_resolved", False),
            "credits": result.get("credits") or {},
            "probe_stock": result.get("probe_stock") or {},
            "log_tail": status.get("log_tail", []),
            "max_orbit_actions": result.get("max_orbit_actions"),
        }

    # ── Slow path: NON-BLOCKING (mirrors api_game_policy). ──────────────
    lk = _try_lock(game_id, _AGENT_SUBMIT_LOCK_WAIT_S)
    if lk is None:
        status = soc_engine.get_session_status(_store(), game_id)
        return {
            "ok": True,
            "agent_busy": True,
            "errors": [],
            "pending_orbit": status.get("pending") or {},
            "phase": status.get("phase"),
            "day": status.get("day"),
            "orbit_resolved": False,
            "credits": {},
            "probe_stock": {},
            "log_tail": status.get("log_tail", []),
            "max_orbit_actions": None,
            **_agent_status_meta(game_id, status),
        }
    try:
        try:
            result = soc_engine.submit_orbit_actions(
                _store(), game_id, player, actions_field, auto_fire_bots=False,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        lk.release()
    if result.get("ok"):
        _kick_bots(game_id)
    status = soc_engine.get_session_status(_store(), game_id)
    orbit_resolved = (
        str(pre_status.get("phase")) == "orbit"
        and str(status.get("phase") or "") != "orbit"
    )
    return {
        "ok": result["ok"],
        "errors": result.get("errors") or [],
        "pending_orbit": status.get("pending") or {},
        "phase": status.get("phase") or result.get("phase"),
        "day": status.get("day") or result.get("day"),
        "orbit_resolved": orbit_resolved,
        "credits": result.get("credits") or {},
        "probe_stock": result.get("probe_stock") or {},
        "log_tail": status.get("log_tail", []),
        "max_orbit_actions": result.get("max_orbit_actions"),
        **_agent_status_meta(game_id, status),
    }


@app.post("/api/game/{game_id}/policy")
def api_game_policy(game_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    player = payload.get("player")
    if not isinstance(player, str) or not player:
        raise HTTPException(status_code=400, detail="player is required")
    moves_field: Any = payload.get("moves", payload.get("commands"))
    if moves_field is None:
        moves_field = []
    pre_status = soc_engine.get_session_status(_store(), game_id)
    slow = _game_has_slow_bot(pre_status.get("agents") or {})

    # ── Fast path: no slow agent — unchanged legacy behaviour. ──────────
    # v0.9.12 — serialise the hydrate->mutate->save for this game so two
    # humans submitting near-simultaneously can't lost-update each other.
    if not slow:
        with _game_lock(game_id):
            try:
                result = soc_engine.submit_policy(
                    _store(), game_id, player, moves_field, auto_fire_bots=True,
                )
            except KeyError as exc:
                # v0.9.5 — surface the full traceback so we can pin down the
                # bare ``["x"]`` lookup; keep raising so the FE is unchanged.
                print("\n[soc] submit_policy KeyError traceback ↓↓↓",
                      file=sys.stderr, flush=True)
                traceback.print_exc(file=sys.stderr)
                print("[soc] submit_policy KeyError traceback ↑↑↑\n",
                      file=sys.stderr, flush=True)
                raise HTTPException(status_code=404, detail=str(exc)) from exc
        status = soc_engine.get_session_status(_store(), game_id)
        return {
            "ok": result["ok"],
            "errors": result.get("errors") or [],
            "pending": status.get("pending") or {},
            "phase": status.get("phase") or result.get("phase"),
            "day": status.get("day") or result.get("day"),
            "night_resolved": result.get("night_resolved", False),
            "log_tail": status.get("log_tail", []),
            "moves_stashed": result.get("moves_stashed", 0),
        }

    # ── Slow path: game has a Cortex/harness seat — NON-BLOCKING. ───────
    # v1.11 — we no longer synchronously drive the agent (which could hang
    # the request for up to the agent's ~80s turn). Instead: stash the human
    # WITHOUT firing bots (auto_fire_bots=False resolves inline only if the
    # agent already submitted during deliberation), then kick the background
    # worker and return immediately. The browser holds a "waiting on <agent>"
    # frame and polls /status for the resolution. If the agent is mid-turn
    # and holding the lock, we can't stash safely — return ``agent_busy`` so
    # the browser keeps its frame and retries once the agent lands.
    lk = _try_lock(game_id, _AGENT_SUBMIT_LOCK_WAIT_S)
    if lk is None:
        status = soc_engine.get_session_status(_store(), game_id)
        return {
            "ok": True,
            "agent_busy": True,
            "errors": [],
            "pending": status.get("pending") or {},
            "phase": status.get("phase"),
            "day": status.get("day"),
            "night_resolved": False,
            "log_tail": status.get("log_tail", []),
            "moves_stashed": 0,
            **_agent_status_meta(game_id, status),
        }
    try:
        try:
            result = soc_engine.submit_policy(
                _store(), game_id, player, moves_field, auto_fire_bots=False,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        lk.release()
    if result.get("ok"):
        _kick_bots(game_id)  # background: fire agent + resolve
    status = soc_engine.get_session_status(_store(), game_id)
    # Resolved inline only if the agent had already submitted (both_ready).
    night_resolved = (
        str(pre_status.get("phase")) == "planning"
        and str(status.get("phase") or "") != "planning"
    ) or (int(status.get("day") or 0) > int(pre_status.get("day") or 0))
    return {
        "ok": result["ok"],
        "errors": result.get("errors") or [],
        "pending": status.get("pending") or {},
        "phase": status.get("phase") or result.get("phase"),
        "day": status.get("day") or result.get("day"),
        "night_resolved": night_resolved,
        "log_tail": status.get("log_tail", []),
        "moves_stashed": result.get("moves_stashed", 0),
        **_agent_status_meta(game_id, status),
    }


@app.get("/api/game/{game_id}/replay")
def api_game_replay(
    game_id: str,
    day_from: Optional[int] = Query(None, alias="day_from"),
    day_to: Optional[int] = Query(None, alias="day_to"),
) -> dict[str, Any]:
    try:
        reply = soc_engine.get_replay(
            _store(), game_id, day_from=day_from, day_to=day_to,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    # The legacy shape was {mode, phase, width, height, frames}. Keep
    # `frames` populated (flattened across all days) for back-compat,
    # but also expose the new `days` / `day_index` payload Phase 4 uses.
    #
    # Payload-size guard: a 4-seat, multi-night replay can balloon past
    # half a gigabyte and OOM-crash the browser tab on parse. Two big
    # offenders, both pure duplication:
    #   1. ``days[].frames`` / ``days[].frames_compact`` repeat every
    #      frame the flat ``frames`` list already carries. The watcher
    #      frontend reads ``frames`` + ``day_index`` only, so we ship
    #      ``days`` as lightweight ``{day}`` markers (tests assert the
    #      day numbers, nothing reads the nested frames over HTTP).
    #   2. Each frame's ``cells_player_p1..pN`` are exact copies of
    #      ``cells_by_seat[pN]`` (the frontend's primary read). We strip
    #      the aliases from the wire frames; ``cells_by_seat`` and the
    #      single ``cells_player`` (still used by the reveal animation)
    #      remain. The engine reply / stored frames are untouched.
    frames: list[dict[str, Any]] = []
    for day_bucket in reply.get("days") or []:
        for f in day_bucket.get("frames") or []:
            frames.append(
                {k: v for k, v in f.items() if not k.startswith("cells_player_")}
            )
    slim_days = [{"day": b.get("day")} for b in (reply.get("days") or [])]
    return {
        "mode": "replay",
        "phase": reply.get("phase"),
        "width": reply.get("width"),
        "height": reply.get("height"),
        "frames": frames,
        "days": slim_days,
        "day_index": reply.get("day_index") or [],
        "total_frames": reply.get("total_frames", len(frames)),
        "catapult_by_day": reply.get("catapult_by_day") or {},
        # v0.9.10 — forward the N-seat fields from the engine reply so
        # the frontend can populate __SOC_PLAYERS__ from replay mode.
        "players": reply.get("players") or [],
        "cumulative_shipped_score": reply.get("cumulative_shipped_score") or {},
        # v1.x — per-seat final settlement breakdown (shipped / green penalty
        # / vault-red fire-sale / final) for the animated +/- settlement lines.
        "settlement": reply.get("settlement") or {},
        # v1.x — authoritative post-settlement hoard snapshot per seat so the
        # replay vault reconstructor shows the SETTLED vault (not stale RED)
        # on the terminal RESOLVE tick.
        "final_hoard": reply.get("final_hoard") or {},
        "orbit_log_by_day": reply.get("orbit_log_by_day") or {},
        "log_by_day": reply.get("log_by_day") or {},
        # v0.9.11 — per-day station-observation snapshots ({pre,post})
        # + observable orbital-activity tallies for the Pre-Orbital
        # Recap / Post-Orbital Briefing reports.
        "station_obs_by_day": reply.get("station_obs_by_day") or {},
        "orbital_activity_by_day": reply.get("orbital_activity_by_day") or {},
        # Ordered per-day orbital event lists (probe/orblift/EMP launches,
        # recoveries, collisions). The engine produces these but the HTTP
        # layer previously dropped them; the inline station UI's hover-card
        # event log reads this. Kept lightweight (event tallies, not frames).
        "orbital_events_by_day": reply.get("orbital_events_by_day") or {},
        # v1.x — discovery-triggered REDSIGN beacons (RULEBOOK §4.11).
        # Full final list with per-region ``day``; the client day-gates and
        # paints the persistent pulse overlay in replay.
        "redsign": reply.get("redsign") or [],
        # v1.0 — end-of-game support for the replay end screen.
        "player_names": reply.get("player_names") or {},
        # v0.9.18 — forward custom identity profiles (tags + colors) so the
        # replay/watch UI renders named, coloured seats instead of P1/P2.
        "player_profiles": reply.get("player_profiles") or {},
        "is_season_complete": bool(reply.get("is_season_complete", False)),
        "season_day_cap": reply.get("season_day_cap") or 0,
    }


@app.get("/api/game/{game_id}/summary")
def api_game_summary(game_id: str) -> dict[str, Any]:
    """End-of-game results payload (rankings, tallies, manifest, chart)."""
    try:
        return soc_engine.get_endgame_summary(_store(), game_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/game/{game_id}/day-index")
def api_game_day_index(game_id: str) -> dict[str, Any]:
    """Compact per-day metadata for the Phase-4 scrub bar header."""
    try:
        reply = soc_engine.get_replay(_store(), game_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "session_id": game_id,
        "day_index": reply.get("day_index") or [],
    }


@app.get("/api/game/{game_id}/view")
def api_game_view(
    game_id: str,
    player: str = Query("p1"),
) -> dict[str, Any]:
    """Player-only percept. Use ``/observer`` for the cheat full-map view."""
    if not _is_valid_seat_slug(player):
        raise HTTPException(status_code=400, detail="unknown player slug")
    try:
        return soc_engine.get_view(_store(), game_id, player)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/game/{game_id}/observer")
def api_game_observer(game_id: str) -> dict[str, Any]:
    """Omniscient observer mosaic — for the GRAPHICS drawer only."""
    try:
        return soc_engine.get_observer(_store(), game_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/game/{game_id}/agent-log")
def api_game_agent_log(
    game_id: str,
    day: int | None = Query(
        None,
        description="Optional day filter (1-indexed). Omit for all days.",
    ),
    player: str | None = Query(
        None,
        description="Optional seat filter ('p1' or 'p2'). Omit for all seats.",
    ),
) -> dict[str, Any]:
    """Replay-mode access to ``SOC_AGENT_INVOCATION`` rows so the
    front-end AGENT tab can fill in rationale for a persisted season.

    The live AGENT panel captures rationales inline from the
    ``/agent/think`` response; this endpoint is the equivalent
    surface for sessions loaded into watcher mode.
    """
    if player is not None and not _is_valid_seat_slug(player):
        raise HTTPException(status_code=400, detail="unknown player slug")
    store = _store()
    if not hasattr(store, "list_agent_invocations"):
        # In-memory store has no agent-log persistence; return empty
        # so the frontend's lazy-fetch path silently no-ops.
        return {"session_id": game_id, "day": day, "player": player, "invocations": []}
    try:
        rows = store.list_agent_invocations(game_id, day=day)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if player is not None:
        rows = [r for r in rows if str(r.get("player") or "").lower() == player]
    # Trim to the fields the frontend actually renders so the
    # response stays compact. ``prompt_excerpt`` stores the full
    # Cortex prompt (typed STRING in Snowflake, ~28KB ceiling per
    # ``PROMPT_PAYLOAD_CAP_CHARS``) — surfacing it here is what
    # powers the /evals TRANSCRIPT tab. Legacy rows with
    # ``prompt_excerpt=NULL`` predate this column being populated;
    # the UI renders them as "(prompt not recorded)".
    out = []
    for r in rows:
        tool_calls = r.get("tool_calls")
        # Snowpark hands us the column either as a parsed JSON list
        # or as the raw string we PARSE_JSON'd on insert; normalise.
        if isinstance(tool_calls, str):
            try:
                tool_calls = json.loads(tool_calls)
            except (json.JSONDecodeError, TypeError):
                tool_calls = []
        elif tool_calls is None:
            tool_calls = []
        out.append(
            {
                "day": r.get("day"),
                "seq": r.get("seq"),
                "agent_id": r.get("agent_id"),
                "player": r.get("player"),
                "runtime": r.get("runtime") or _infer_runtime(r.get("agent_id")),
                "prompt": r.get("prompt_excerpt"),
                "rationale": r.get("rationale"),
                "response_text": r.get("response_text"),
                "tool_calls": tool_calls,
                "ms_elapsed": r.get("ms_elapsed"),
                "status": r.get("status"),
            }
        )
    return {
        "session_id": game_id,
        "day": day,
        "player": player,
        "invocations": out,
    }


def _infer_runtime(agent_id: str | None) -> str:
    """Best-effort runtime inference for legacy rows that pre-date the
    ``runtime`` column. ``RED_HARVEST`` is the heuristic; anything
    else (Cortex agents like ``SOC_RED_REAPER``) is treated as
    cortex."""
    if not agent_id:
        return ""
    return "heuristic" if str(agent_id).upper() == "RED_HARVEST" else "cortex"


@app.post("/api/game/{game_id}/agent/think")
def api_agent_think(
    game_id: str,
    player: str = Query("p1"),
    runtime: str | None = Query(
        None,
        description=(
            "Optional per-call runtime override: 'heuristic' (RED_HARVEST) "
            "or 'red_harvest_lite' (RED_HARVEST_LITE, weapons disabled). "
            "Defaults to 'heuristic'."
        ),
    ),
) -> dict[str, Any]:
    """Run one deterministic agent turn for ``player`` end-to-end.

    Fetches the player view, runs the in-process heuristic, submits the
    resulting policy through the SOC engine, and writes an audit row to
    ``SOC_AGENT_INVOCATION``. The envelope includes ``agent_id`` so the
    caller knows who played.

    This route is heuristic-only. **LLM seats do not come through here**
    — seat the player as ``tabula_v12`` at game creation and the
    orchestrator dispatches V12 automatically, on any storage backend.
    """
    if not _is_valid_seat_slug(player):
        raise HTTPException(status_code=400, detail="unknown player slug")
    if runtime == "cortex":
        # Explicit, actionable 410 rather than a generic 400: the old
        # Agents-API runtime was a documented part of this route, so
        # callers still asking for it deserve to be told where it went.
        raise HTTPException(
            status_code=410,
            detail=(
                "The 'cortex' runtime was removed along with the Cortex "
                "Agents-API specs. The LLM agent is now V12: seat a "
                "player as 'tabula_v12' when creating the game and the "
                "orchestrator dispatches it (works on any SOC_BACKEND; "
                "needs SNOWFLAKE_PAT). Use 'heuristic' for RED_HARVEST."
            ),
        )
    if runtime is not None and runtime not in _HEURISTIC_RUNTIMES:
        raise HTTPException(
            status_code=400,
            detail=f"runtime must be one of {sorted(_HEURISTIC_RUNTIMES)}",
        )
    try:
        return run_agent_turn(_store(), game_id, player, runtime_override=runtime)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/meta/backend")
def api_meta_backend() -> dict[str, Any]:
    """Diagnostic — which storage backend is the proxy talking to, and why.

    ``reason`` matters as much as ``backend``: with auto-detection the
    answer to "where did my game go?" is usually a sentence about a
    missing dependency or config, not the backend name.
    """
    res = soc_backend.resolution()
    return {
        "backend": res.name,
        "requested": res.requested,
        "reason": res.reason,
        "fix": res.fix,
        "persists": res.persists,
        "summary": res.summary(),
    }


@app.get("/api/meta/status")
def api_meta_status() -> dict[str, Any]:
    """Health for the landing-page status badge.

    Reports the backend mode, per-store health (the composite store knows
    whether Snowflake is reachable vs local-only), and whether a public
    tunnel is currently up. The badge maps this to local / snowflake / off.
    """
    from server import tunnel as soc_tunnel

    res = soc_backend.resolution()
    backend = res.name
    stores: dict[str, str] = {}
    store = _store()
    health = getattr(store, "health", None)
    if callable(health):
        try:
            stores = health()
        except Exception:
            stores = {}
    else:
        # Single-backend server: the active store is simply "ok".
        stores = {backend: "ok"}
    return {
        "backend": backend,
        "persists": res.persists,
        "reason": res.reason,
        "stores": stores,
        "tunnel": soc_tunnel.status(),
    }


@app.post("/api/tunnel/start")
def api_tunnel_start(request: Request) -> dict[str, Any]:
    """Start (or reuse) a cloudflared quick tunnel to this server.

    Targets the port the caller connected on (so a dev server on :8000
    just works), falling back to 8000. Returns the public
    ``trycloudflare.com`` URL once cloudflared publishes it."""
    from server import tunnel as soc_tunnel

    port = request.url.port or 8000
    return soc_tunnel.start(int(port))


@app.get("/api/tunnel/status")
def api_tunnel_status() -> dict[str, Any]:
    from server import tunnel as soc_tunnel

    return soc_tunnel.status()


@app.post("/api/tunnel/stop")
def api_tunnel_stop() -> dict[str, Any]:
    from server import tunnel as soc_tunnel

    return soc_tunnel.stop()


def _lan_ip() -> Optional[str]:
    """Best-effort primary LAN IPv4 of the host running this server.

    Opens a UDP socket toward a public address and reads back the local
    endpoint the OS picked — this resolves the address other devices on
    the same network would use to reach us, without sending any packets
    or requiring internet access. Returns ``None`` (and the caller falls
    back to the request origin) if the host is fully offline.
    """
    import socket

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except OSError:
        try:
            ip = socket.gethostbyname(socket.gethostname())
        except OSError:
            return None
    finally:
        s.close()
    if not ip or ip.startswith("127."):
        return None
    return ip


@app.get("/api/meta/lan")
def api_meta_lan() -> dict[str, Any]:
    """Report the host's LAN IP so the invite modal can build a phone-
    reachable URL (and QR) instead of ``localhost`` — which on a phone
    points at the phone itself. ``lan_ip`` is ``None`` when offline."""
    import socket as _socket

    return {"lan_ip": _lan_ip(), "hostname": _socket.gethostname()}
