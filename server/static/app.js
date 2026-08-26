// sea_of_colours web UI — solo player + queue-based night form (+ observer drawer).

(() => {
  "use strict";

  // v0.9.8 — banner so we can tell from the browser console which
  // build is actually loaded. If the LOG isn't updating during
  // playback and this banner doesn't appear OR shows an older
  // version, the issue is browser cache (force-reload with Cmd+Shift+R).
  // eslint-disable-next-line no-console
  console.log("[soc] app.js build: v0.9.8-log-fix-r3");

  // ── Watcher mode (Phase C) ──────────────────────────────────────────
  // Detect whether this page-load is the read-only watcher rather than
  // the play surface. Three URL signals are accepted, in order of
  // specificity:
  //
  //   ?session=<id>     pin a specific session_id
  //   ?season=<slug>    resolve a season slug → session_id via /api/sessions
  //   ?watch=1          generic "open the watcher" (no pre-selection)
  //
  // The detection runs once at module load so the IIFE can branch
  // before the NEW-GAME click handler is wired up.
  const _watchParams = new URLSearchParams(window.location.search);
  // v0.9.12 — cross-browser multiplayer seat binding.
  //
  //   ?session=<id>&player=pN   JOIN an existing session as a PLAYABLE seat
  //                             (a friend's shareable link). NOT the watcher.
  //   ?session=<id>             read-only watcher (omniscient replay)
  //   ?season=<slug> / ?watch=1 watcher
  //   (no params)               solo play — local seat stays p1, identical to
  //                             the single-browser flow that always shipped.
  //
  // ``?watch=1`` always wins, so you can spectate even a seat-bound link.
  const _rawPlayerParam = String(_watchParams.get("player") || "")
    .trim()
    .toLowerCase();
  const _validSeatParam = /^p[1-4]$/.test(_rawPlayerParam) ? _rawPlayerParam : "";
  const JOIN_MODE =
    _watchParams.has("session") &&
    !!_validSeatParam &&
    _watchParams.get("watch") !== "1";
  const WATCH_MODE =
    !JOIN_MODE &&
    (_watchParams.has("session") ||
      _watchParams.has("season") ||
      _watchParams.get("watch") === "1");
  const WATCH_SESSION_ID = _watchParams.get("session") || "";
  const WATCH_SEASON_SLUG = _watchParams.get("season") || "";
  // The local "this is me" seat. Solo play (no ?player=) keeps p1 so every
  // hardcoded-p1 call site below behaves exactly as it did pre-multiplayer.
  // A joiner binds to the seat from their link; the seat picker (join with no
  // ?player=) can reassign it before the first map load.
  let MY_SEAT = _validSeatParam || "p1";
  if (WATCH_MODE) {
    document.body.classList.add("cc-mode--watch");
  }
  if (JOIN_MODE) {
    document.body.classList.add("cc-mode--join");
  }

  const MAX_MOVES = 21; // policy-slot cap per player per night (v0.9.9: each queued row burns a slot whether the engine accepts it or strikes it out)
  let maxQueueLen = 21; // queue submission cap = MAX_MOVES; refreshed from /api/game/new + status
  // v0.9.16 — chaff jams its OWN launcher too (engine: CHAFF_DURATION_HOURS=3,
  // launcher immune only for the launch hour). The flare therefore costs the
  // launcher the launch slot + this many self-jammed turns, so the composer
  // reserves CHAFF_SELF_JAM_SLOTS locked rows right after every chaff.
  const CHAFF_SELF_JAM_SLOTS = 2;

  const GRID_LINES_KEY = "sea_of_colours:gridLines";
  const CRT_ON_KEY = "sea_of_colours:crtOn";
  const CRT_INTENSITY_KEY = "sea_of_colours:crtIntensity";
  const CRT_CURVE_KEY = "sea_of_colours:crtCurve";
  const CRT_GLITCH_KEY = "sea_of_colours:crtGlitch";
  const EMP_LULLS_KEY = "sea_of_colours:empLulls";
  // v0.9.11 — orbit-report settings keys.
  const LAST_TURN_FX_KEY = "soc.replay.lastTurnFx";
  const AUTOPOP_REPORTS_KEY = "soc.orbit.autoPopReports";

  // v1.1 — gate the cinematic title cards (NIGHT n / PRAXIS BEGINS).
  const TITLE_CARDS_KEY = "soc.cinematic.titleCards";
  // Orbit→surface launch sequencing (station launch plays before the
  // on-board landing). Default ON. Drives window._osOrbitSeq.
  const ORBIT_SEQ_KEY = "soc.orbit.launchSequencing";
  // Replay playback tail behaviour.
  //   soc.replay.loop      — when ON, autoplay/next wraps back to day 1 at the
  //                          end of the timeline. Default OFF (stop at the last
  //                          available window).
  //   soc.replay.endAnim   — when ON (and loop is OFF), reaching the end plays
  //                          the final settlement + victory celebration + score
  //                          card. Default ON.
  const REPLAY_LOOP_KEY = "soc.replay.loop";
  const REPLAY_END_ANIM_KEY = "soc.replay.endAnimation";
  const MAP_ZOOM_KEY = "sea_of_colours:mapZoomPx";
  const MAP_ZOOM_MIN = 10;
  const MAP_ZOOM_MAX = 28;
  // ``let`` (not ``const``) so the optional station UI can reset the
  // fit-to-width baseline via window._osSetMapZoomDefault. Default is
  // identical to before when the station UI is off.
  let MAP_ZOOM_DEFAULT = 14;

  const mapPlayer = document.getElementById("map-player");
  const mapObserver = document.getElementById("map-observer");
  const fullMapBlock = document.getElementById("cc-fullmap-block");
  const replayBar = document.getElementById("replay-bar");
  const replayLiveBtn = document.getElementById("replay-live");
  const replayPrev = document.getElementById("replay-prev");
  const replayNext = document.getElementById("replay-next");
  const replayPlay = document.getElementById("replay-play");
  const replayCaptionEl = document.getElementById("replay-caption");
  const replaySlotEl = document.getElementById("replay-slot");
  const replayScrub = document.getElementById("replay-scrub");
  const replayDayBadge = document.getElementById("replay-day-badge");
  const replayDayPrev = document.getElementById("replay-day-prev");
  const replayDayNext = document.getElementById("replay-day-next");
  const replayDayTicks = document.getElementById("replay-day-ticks");
  // v0.9.9 — the replay-view row is populated dynamically by
  // renderReplayViewButtons() based on the active seat list. The pre-v0.9.9
  // static P1/P2/P1+P2/OBS buttons are gone; only the OBS button is
  // declared upfront in the HTML and the per-seat buttons are injected
  // before it on each render. ``replayViewObsBtn`` is kept as a stable
  // handle because the OBS click handler is wired once on page-load.
  const replayViewRowEl = document.getElementById("cc-replay-view-row");
  const replayViewObsBtn = document.getElementById("replay-view-obs");
  const phaseLine = document.getElementById("phase-line");
  const orchLogEl = document.getElementById("orch-log");
  // v0.7.3 — synced replay feed. Lives INSIDE the REPLAY side-panel,
  // directly below the replay bar. Orders and log are stacked and
  // always shown together — no tabs — so the watcher reads
  // "what was scheduled" alongside "what actually happened" as the
  // scrubber walks the night. Both sections filter on the active
  // P1 / P2 / Both view button above. The whole feed hides in LIVE
  // mode.
  const replayFeedEl = document.getElementById("replay-feed");
  const replayFeedTimelineEl = document.getElementById("replay-feed-timeline");
  const replayFeedDayEl = document.getElementById("replay-feed-day");
  // v0.7.5 — universal replay strip pinned below the map. Contains
  // the controls + a single-line "now playing" ticker (D{n} H{nn} +
  // last caption). Always visible regardless of which side panel is
  // active.
  const replayStripEl = document.getElementById("replay-strip");
  const replayNowClockEl = document.getElementById("replay-now-clock");
  const replayNowCaptionEl = document.getElementById("replay-now-caption");
  // v0.7.5 — scoreboard inside the LOG panel (was REPLAY).
  const replayScoreboardEl = document.getElementById("replay-scoreboard");
  // v0.7.5 — AGENT panel (was LOG). Per-seat sub-tabs + filtered
  // rationale feed. The legacy #orch-log is now a hidden in-DOM
  // buffer for the status-poll path (renderOrchLog) so we don't
  // break it; the visible AGENT body is #agent-feed.
  const agentFeedEl = document.getElementById("agent-feed");
  // v0.9.18 — agent seat sub-tabs are rebuilt dynamically into this
  // container by renderAgentSeatTabs() (the static p1/p2 buttons in the
  // HTML are placeholders that get replaced on first render).
  const agentSeatTabsEl = document.getElementById("agent-seat-tabs");
  // v0.7.5 / v0.9.11 — VAULT panel seat sub-tabs. The buttons are now
  // built dynamically (one per active seat) by ``renderVaultSeatTabs``;
  // in live play only the player's own seat shows. Hoard contents are
  // reconstructed per scrub tick so the vault fills as the night plays.
  const vaultSeatTabsEl = document.getElementById("vault-seat-tabs");
  const collisionFxLayer = document.getElementById("collision-fx-layer");
  // v1.1 — daylight wash (single yellow film for the DAY phase).
  const daylightWashEl = document.getElementById("cc-daylight-wash");
  // v1.1 — dawn cinematic chrome (submission framing + title cards).
  const resolvingOverlayEl = document.getElementById("cc-resolving-overlay");
  const resolvingProgressEl = document.getElementById("cc-resolving-progress");
  const resolvingRecapEl = document.getElementById("cc-resolving-recap");
  const mapTitleCardEl = document.getElementById("cc-map-titlecard");
  const mapTitleCardMainEl = document.getElementById("cc-titlecard-main");
  const mapTitleCardSubEl = document.getElementById("cc-titlecard-sub");
  const newGameBtn = document.getElementById("new-game-btn");
  // Watcher-mode UI (Phase C). These nodes exist in the DOM but stay
  // hidden until ``WATCH_MODE`` flips on; see the bottom-of-file
  // bootstrap for the load flow.
  const watchPickerWrap = document.getElementById("watch-picker-wrap");
  const watchPickerEl =
    /** @type {HTMLSelectElement | null} */ (document.getElementById("watch-season-picker"));
  const watchPickerMetaEl = document.getElementById("watch-picker-meta");
  const watchDeleteBtn = document.getElementById("watch-delete-btn");
  const watchFixturesEl =
    /** @type {HTMLInputElement | null} */ (document.getElementById("watch-show-fixtures"));
  /** @type {NodeListOf<HTMLButtonElement>} */
  const ccTabs = document.querySelectorAll(".cc-tab[data-cc-tab]");
  /** @type {NodeListOf<HTMLElement>} */
  const ccPanels = document.querySelectorAll(".cc-panel[data-cc-panel]");
  const ccTabOrdersMeta = document.getElementById("cc-tab-orders-meta");
  const ccTabIntelMeta = document.getElementById("cc-tab-intel-meta");
  const ccTabVaultMeta = document.getElementById("cc-tab-vault-meta");
  const ccTabShippedMeta = document.getElementById("cc-tab-shipped-meta");
  const ccTabReplayMeta = document.getElementById("cc-tab-replay-meta");
  const vaultGridEl = document.getElementById("vault-grid");
  const shippedGridEl = document.getElementById("shipped-grid");
  const vaultAssetsOrbitEl = document.getElementById("vault-assets-in-orbit");
  const vaultAssetsSurfaceEl = document.getElementById("vault-assets-on-surface");
  const vaultAssetsDestroyedEl = document.getElementById("vault-assets-destroyed");
  // Canonical certified-hoard slot count (RULEBOOK §3.12 — the VAULT is a
  // fixed 15-slot grid, self-only). Used as the fallback denominator anywhere
  // an inventory payload arrives without an explicit ``hoard_capacity`` so the
  // vault never renders a stale 25/50 capacity.
  const HOARD_CAP_FALLBACK = 15;

  const gridlinesEl = document.getElementById("toggle-gridlines");
  const gridlinesBox = document.querySelector(
    'label[for="toggle-gridlines"] .cli-check-box',
  );

  const empLullsEl = /** @type {HTMLInputElement|null} */ (
    document.getElementById("toggle-emp-lulls")
  );
  const empLullsBox = document.querySelector(
    'label[for="toggle-emp-lulls"] .cli-check-box',
  );

  // v0.9.11 — orbit-report settings checkboxes.
  const lastTurnFxEl = /** @type {HTMLInputElement|null} */ (
    document.getElementById("toggle-last-turn-fx")
  );
  const lastTurnFxBox = document.querySelector(
    'label[for="toggle-last-turn-fx"] .cli-check-box',
  );
  const autoPopReportsEl = /** @type {HTMLInputElement|null} */ (
    document.getElementById("toggle-autopop-reports")
  );
  const autoPopReportsBox = document.querySelector(
    'label[for="toggle-autopop-reports"] .cli-check-box',
  );
  // v1.1 — cinematic title-card toggle.
  const titleCardsEl = /** @type {HTMLInputElement|null} */ (
    document.getElementById("toggle-title-cards")
  );
  const titleCardsBox = document.querySelector(
    'label[for="toggle-title-cards"] .cli-check-box',
  );
  // Orbit→surface sequencing toggle.
  const orbitSeqEl = /** @type {HTMLInputElement|null} */ (
    document.getElementById("toggle-orbit-seq")
  );
  const orbitSeqBox = document.querySelector(
    'label[for="toggle-orbit-seq"] .cli-check-box',
  );
  // Replay tail toggles.
  const replayLoopEl = /** @type {HTMLInputElement|null} */ (
    document.getElementById("toggle-replay-loop")
  );
  const replayLoopBox = document.querySelector(
    'label[for="toggle-replay-loop"] .cli-check-box',
  );
  const replayEndAnimEl = /** @type {HTMLInputElement|null} */ (
    document.getElementById("toggle-replay-end-anim")
  );
  const replayEndAnimBox = document.querySelector(
    'label[for="toggle-replay-end-anim"] .cli-check-box',
  );

  const crtEl = document.getElementById("toggle-crt");
  const crtBox = document.querySelector('label[for="toggle-crt"] .cli-check-box');
  const crtViewport = document.getElementById("crt-viewport");
  const crtIntensityEl = document.getElementById("crt-intensity");
  const crtCurveEl = document.getElementById("crt-curve");
  const glitchEl = document.getElementById("toggle-glitch");
  const glitchBox = document.querySelector('label[for="toggle-glitch"] .cli-check-box');
  const crtCursorFollower = document.getElementById("crt-cursor-follower");

  const mapZoomSliderEl = /** @type {HTMLInputElement|null} */ (
    document.getElementById("cc-map-zoom-slider")
  );
  const mapZoomReadoutEl = document.getElementById("cc-map-zoom-readout");
  const mapZoomInBtn = document.getElementById("cc-map-zoom-in");
  const mapZoomOutBtn = document.getElementById("cc-map-zoom-out");
  const mapHostMainEl = document.getElementById("map-player");

  const soloForm = document.getElementById("solo-night-form");
  const soloStandardFieldset = document.getElementById("solo-standard-fieldset");
  const soloQueueHost = document.getElementById("solo-move-queue");
  const soloQueueCount = document.getElementById("solo-queue-count");
  const soloQueueClearBtn = document.getElementById("solo-queue-clear");
  // v0.9.5 — "show all 21 slots" toggle. When pressed, the queue
  // renderer pads up to ``MAX_MOVES`` rows so the user can see the
  // full night timeline with idle slots rendered as (wait)
  // placeholders. Drag-and-drop reorder works against both real and
  // placeholder rows.
  const soloQueueShowAllBtn = document.getElementById("solo-queue-show-all");
  let soloQueueShowAll = false;
  // v0.8.0 ORBIT panel DOM refs.
  const orbitQueueHost = document.getElementById("solo-orbit-queue");
  const orbitQueueCount = document.getElementById("solo-orbit-queue-count");
  const orbitQueueClearBtn = document.getElementById("solo-orbit-queue-clear");
  const orbitTabMeta = document.getElementById("cc-tab-orbit-meta");
  const orbitCommitBtn = document.getElementById("solo-commit-orbit");
  const orbitErr = document.getElementById("err-solo-orbit");
  const orbitCreditsEl = document.getElementById("cc-orbit-credits");
  const orbitProbeStockEl = document.getElementById("cc-orbit-probe-stock");
  const orbitHarvestersEl = document.getElementById("cc-orbit-harvesters");
  const orbitGreenEl = document.getElementById("cc-orbit-green");
  const soloExpert = document.getElementById("solo-expert");
  const soloExpertJson = document.getElementById("solo-expert-json");
  const soloCommitBtn = document.getElementById("solo-commit-night");
  // v0.9.13 — sticky mobile orders bar (only visible on the stacked layout).
  const mobileOrdersBar = document.getElementById("cc-mobile-orders");
  const mobileOrdersOpenBtn = document.getElementById("cc-mobile-orders-open");
  const mobileOrdersTxBtn = document.getElementById("cc-mobile-orders-tx");
  const mobileOrdersCountEl = document.getElementById("cc-mobile-orders-count");
  const soloAgentBtn = document.getElementById("solo-agent-think");
  const soloAgentAutoplayBtn = document.getElementById("solo-agent-autoplay");
  const soloAgentVersusBtn = document.getElementById("solo-agent-versus");
  /** @type {HTMLSelectElement | null} */
  const soloAgentRuntime = document.getElementById("solo-agent-runtime");
  /** @type {HTMLSelectElement | null} */
  const soloVersusP1 = document.getElementById("solo-versus-p1");
  /** @type {HTMLSelectElement | null} */
  const soloVersusP2 = document.getElementById("solo-versus-p2");
  const errSoloEl = document.getElementById("err-solo");

  // The `/agent/think` route is heuristic-only: RED_HARVEST or
  // RED_HARVEST_LITE. The retired "cortex" runtime now returns 410, so
  // nothing below may ever produce it. LLM seats are not driven from
  // here at all — seat a player as `tabula_v12` at game creation and the
  // orchestrator dispatches V12 on the server side.
  const HEURISTIC_RUNTIMES = ["heuristic", "red_harvest_lite"];

  /** Read the runtime the user picked from the AGENT: dropdown, falling
   *  back to RED_HARVEST when the dropdown isn't present. */
  function selectedAgentRuntime() {
    const v = soloAgentRuntime?.value;
    return HEURISTIC_RUNTIMES.includes(v) ? v : "heuristic";
  }

  /** Short label for a runtime — used in the versus button label. */
  function runtimeShortLabel(runtime) {
    return runtime === "red_harvest_lite" ? "RED_HARVEST_LITE" : "RED_HARVEST";
  }

  /** Read the two VERSUS: dropdowns and return the matchup as
   *  ``{ p1, p2 }``. Defaults to RED_HARVEST vs RED_HARVEST_LITE when a
   *  select is missing — the weapons-on bot against the weapons-off one. */
  function selectedVersusMatchup() {
    const pick = (sel, fallback) =>
      HEURISTIC_RUNTIMES.includes(sel?.value) ? sel.value : fallback;
    return {
      p1: pick(soloVersusP1, "heuristic"),
      p2: pick(soloVersusP2, "red_harvest_lite"),
    };
  }

  /** Refresh the VERSUS button label so the user can see exactly which
   *  matchup is about to start. Called on page load and whenever either
   *  dropdown changes. Not called while the loop is running — that
   *  state is owned by setVersusLabel which shows STOP · turn/total. */
  function refreshVersusButtonLabel() {
    if (!soloAgentVersusBtn) return;
    if (versusRunning) return; // loop owns the label while active
    const { p1, p2 } = selectedVersusMatchup();
    const turns = parseInt(
      soloAgentVersusBtn.dataset.maxTurns ?? "10",
      10,
    ) || 10;
    soloAgentVersusBtn.textContent =
      `[ >> ${runtimeShortLabel(p1)} vs ${runtimeShortLabel(p2)} · ${turns} Nox ]`;
  }

  // versusRunning is declared further down — we reference it inside the
  // refreshVersusButtonLabel closure above, so JS hoists the `let`
  // binding to the IIFE's top. Safe because the function is only called
  // *after* the listeners below are wired, by which point the `let` is
  // initialised to false.

  if (soloVersusP1) soloVersusP1.addEventListener("change", refreshVersusButtonLabel);
  if (soloVersusP2) soloVersusP2.addEventListener("change", refreshVersusButtonLabel);

  // ── Live agent status banner ────────────────────────────────────
  //
  // Surfaces the actual phase the agent is in so 10-90s Cortex turns
  // don't feel like the UI is frozen. Read by all three entry points
  // (single-turn, autoplay loop, versus loop). The banner has three
  // visual states:
  //   working — pill border glows, dot pulses (default while working)
  //   done    — steady glow, dot static (between turns or at finish)
  //   error   — red glow, dot red (a turn threw / timed out)
  //
  // The elapsed-seconds counter is driven by a single shared interval
  // managed here, so callers never have to worry about leaking timers.
  const agentStatusEl = document.getElementById("agent-status");
  const agentStatusRuntimeEl = document.getElementById("agent-status-runtime");
  const agentStatusTurnEl = document.getElementById("agent-status-turn");
  const agentStatusElapsedEl = document.getElementById("agent-status-elapsed");
  const agentStatusPhaseEl = document.getElementById("agent-status-phase");
  const agentStatusDetailEl = document.getElementById("agent-status-detail");

  let agentStatusInterval = null;
  let agentStatusStartedAt = 0;

  function clearAgentStatusInterval() {
    if (agentStatusInterval != null) {
      clearInterval(agentStatusInterval);
      agentStatusInterval = null;
    }
  }

  function setAgentStatus({
    state = "working",
    runtime = null,
    turn = null,
    total = null,
    phase = null,
    detail = null,
    resetElapsed = false,
  } = {}) {
    if (!agentStatusEl) return;
    agentStatusEl.hidden = false;
    agentStatusEl.dataset.state = state;
    if (runtime != null && agentStatusRuntimeEl) {
      agentStatusRuntimeEl.textContent =
        runtime === "cortex" ? "AI AGENT" :
        runtime === "heuristic" ? "RED_HARVEST" :
        String(runtime);
    }
    if (turn != null && total != null && agentStatusTurnEl) {
      agentStatusTurnEl.textContent = `· turn ${turn}/${total}`;
    } else if (turn === "" && agentStatusTurnEl) {
      agentStatusTurnEl.textContent = "";
    }
    if (phase != null && agentStatusPhaseEl) {
      agentStatusPhaseEl.textContent = phase;
    }
    if (agentStatusDetailEl) {
      if (detail) {
        agentStatusDetailEl.textContent = detail;
        agentStatusDetailEl.hidden = false;
      } else {
        agentStatusDetailEl.textContent = "";
        agentStatusDetailEl.hidden = true;
      }
    }
    if (resetElapsed) {
      agentStatusStartedAt = Date.now();
      if (agentStatusElapsedEl) agentStatusElapsedEl.textContent = "0s";
    }
    if (state === "working") {
      if (agentStatusInterval == null) {
        agentStatusInterval = setInterval(() => {
          if (!agentStatusElapsedEl) return;
          const elapsed = Math.round(
            (Date.now() - agentStatusStartedAt) / 1000,
          );
          agentStatusElapsedEl.textContent = `${elapsed}s`;
        }, 250);
      }
    } else {
      clearAgentStatusInterval();
    }
  }

  function hideAgentStatus() {
    clearAgentStatusInterval();
    if (agentStatusEl) {
      agentStatusEl.hidden = true;
      agentStatusEl.dataset.state = "";
    }
  }
  /** @type {HTMLElement | null} */
  const soloExpertFake =
    soloExpert?.closest(".cli-check")?.querySelector(".cli-check-box") ?? null;

  const reduceMotionMq = window.matchMedia("(prefers-reduced-motion: reduce)");

  let glitchTimerId = null;

  let sessionId = null;
  let replayWindowCount = 0;
  /** @type {any[]} */
  let nightReplayFrames = [];
  // Phase-4 multi-day metadata. Mirrors /api/game/{id}/day-index — one entry
  // per night with frame_count + global indices so we can render dividers
  // and jump whole days at a time.
  let replayDayIndex = [];
  /** @type {{ frames: any[], firstFrameIdx: number, lastFrameIdx: number }[]} */
  let replayTicks = [];
  /** Per-day catapult settlement payloads keyed by day number. Sourced
   *  from ``/api/game/{id}/replay`` and rendered by the ORBIT flash
   *  overlay when the user scrubs across a day boundary. */
  /** @type {Record<string, any>} */
  let catapultByDay = {};
  /** v1.x — per-seat final settlement breakdown ({shipped, green_penalty,
   *  vault_red_loss, final}) from the replay payload. Drives the animated
   *  +red-fire-sale / -green-penalty delta lines in the closing RESOLVE beat.
   *  @type {Record<string, {shipped:number,green_penalty:number,vault_red_loss:number,final:number}>} */
  let settlementBySeat = {};
  /** v1.x — authoritative POST-settlement hoard snapshot per seat
   *  ({seat: {count, sites:[...]}}). Used by ``reconstructVaultAtTick`` at
   *  the terminal RESOLVE tick so the vault reflects the settled state
   *  instead of the stale pre-ship night snapshot (still full of RED).
   *  @type {Record<string, {count:number, sites:any[]}>} */
  let finalHoardSnapshot = {};
  /** v1.4 — season length (last night day). The final SETTLEMENT orbit
   *  resolves on ``day = cap + 1`` (no night frames), which the terminal
   *  RESOLVE replay tick animates. Sourced from the replay payload. */
  let replaySeasonDayCap = 0;
  /** v0.9.1 — per-day orbit chatter (info + error lines), used by
   *  the LOG tab's ORBIT filter chip and the per-day orbit pip
   *  visibility check on the replay scrub strip. */
  let orbitLogByDay = {};
  /** v0.9.8 — full session log indexed by day, returned by the
   *  ``/replay`` endpoint so the LOG drawer can render historical
   *  days even after the in-memory ``log_tail`` rolls past them. */
  let logByDay = {};
  /** v0.9.1 — log feed filter: 'all' | 'night' | 'orbit'. */
  let replayFeedFilter = "all";
  /** v0.9.8 — most recent ``st.log_tail`` from the status poll. The
   *  LOG drawer re-renders this against the current focus day, so
   *  replay scrubbing across days repaints the LOG panel without
   *  hitting the server. */
  let lastLogTail = [];
  /** v0.9.8 — most recent live ``sess.day`` so the LOG focus filter
   *  can default to "live = current day" while leaving the cached
   *  tail available to a replay-mode override. */
  let lastLiveDay = null;
  /** Whether the ORBIT replay toggle is armed. When ON, scrubbing
   *  across a day boundary auto-opens the flash overlay; when OFF,
   *  the modal can still be opened manually via the toggle button. */
  // v0.9.11 — when ON, the orbit reports auto-pop (live + replay) and
  // the replay timeline grows synthetic recap/briefing ticks. Mirrors
  // the "show orbital summaries as pop-ups" setting; loaded from
  // localStorage on boot.
  let orbitFlashEnabled = false;
  // v0.9.11 — when ON, a freshly-resolved night auto-plays its
  // last-turn animation on the live map. Mirrors the "replay last turn
  // animation" setting.
  let replayLastTurnFx = true;
  // v1.1 — when ON, the cinematic title cards (NIGHT n BEGINS / PRAXIS
  // BEGINS) flash over the map. Independent of the FX/sweep so a player
  // can keep the dawn sweep but skip the text. Mirrors "show title cards".
  let titleCardsEnabled = true;
  // Replay tail: cycle back to day 1 at the end (default OFF), and play the
  // closing settlement + victory + score card when the timeline ends without
  // looping (default ON). See REPLAY_LOOP_KEY / REPLAY_END_ANIM_KEY.
  let replayLoopEnabled = false;
  let replayEndAnimEnabled = true;
  /** v0.9.11 — current orbit report context. ``reportKind`` is
   *  "recap" | "briefing"; ``reportDay`` is the day the report is
   *  showing. */
  let reportKind = "recap";
  let reportDay = 0;
  /** v0.9.11 — last day each report was auto-popped for (live), so the
   *  status poller doesn't re-pop on every interval. */
  let lastShownRecapDay = 0;
  /** v0.9.11 — per-day station-observation snapshots + observable
   *  orbital-activity tallies, cached from /replay (all days) and
   *  /status (latest). Keyed by string day. */
  let stationObsByDay = {};
  let orbitalActivityByDay = {};
  /** v0.9.13 — per-day ORDERED orbital event log (chronological,
   *  no coords), cached from /replay (all days) + /status (latest).
   *  Keyed by string day → seat → [{tag, carrying?, damaged?}, ...].
   *  Lives in the session blob server-side so it's as resilient as the
   *  station-obs / activity caches (independent of the replay-frame
   *  table loading). Keyed by string day. */
  let orbitalEventsByDay = {};
  /** Last day the overlay was auto-opened for. Prevents the modal
   *  re-popping on every scrub tick within the same day. */
  let orbitFlashLastDay = 0;
  /** v0.9.9 — last day the LIVE-mode orbit summary modal was popped.
   *  ``refreshStatus`` watches ``latest_catapult.day`` and pops the
   *  modal once per fresh settlement; this guard prevents repeated
   *  pops on the polling interval. Reset to 0 on session change. */
  let lastShownOrbitDay = 0;
  /** v0.9.9 — orbit summary flash duration in seconds. Read from
   *  localStorage on boot, written by the slider; consumed by the
   *  replay auto-play handler to pause on each synthetic
   *  ``orbit_summary`` tick. Clamp to [0.5, 5.0]. */
  let orbitFlashSeconds = 2.0;
  let replayTickIdx = 0;
  // U1 — bot/season replays (WATCH_MODE) open on the OBSERVER view so the whole
  // board is visible by default; a per-seat fog view hid the parts of the map
  // the picked seat couldn't see (the "muddled, different map parts" report).
  // Live play still defaults to the player's own seat.
  let replayViewSeat = WATCH_MODE ? "obs" : MY_SEAT;
  /** @type {number | null} */
  let replayTicker = null;
  let _liveFxPlaying = false;
  /** v0.9.13 — when true, ``refreshSoloPlayerMap`` caches the live map
   *  WITHOUT painting it and ``refreshStatus`` holds back the orbit
   *  report auto-pop. Set during a fresh night turn so the night-replay
   *  cinematic (animate → reveal live → pop recap) controls the reveal
   *  order instead of flashing the end-state + recap before the replay. */
  let _suppressLiveReveal = false;
  const replayDims = { width: 40, height: 28 };

  /** @type {any} */
  let lastHints = null;
  /** @type {{ harvester: string | null; lifter: string | null }} */
  let soloIds = { harvester: null, lifter: null };
  /** Reset when switching day/phase to pre-fill queue placeholders once. */
  let prefetchPlanKey = "";
  /** @type {Array<{ a: string; x?: number; y?: number }>} ordered queue of moves */
  let soloQueue = [];
  /** v0.9.15 — set true once the human has been warned (this submit
   *  attempt) that a queued harvester will be stranded + destroyed at
   *  dawn. The first TRANSMIT click warns and bails; the second submits
   *  anyway. Reset whenever the queue changes so a fresh strand re-warns. */
  let strandWarnAcked = false;
  /** v0.9.13 — set true once the human has been warned (this submit
   *  attempt) that a queued pickup will return cargo into a FULL vault,
   *  so the §3.14 cascade keeps only the best parcels and jettisons the
   *  rest. First TRANSMIT warns + bails; second submits anyway. Reset
   *  whenever the queue changes so a fresh overflow re-warns. */
  let vaultFullWarnAcked = false;
  /** v0.8.0 ORBIT phase action queue. Items are raw orbit-action dicts
   *  matching :mod:`sea_of_colours.game.policy`. */
  /** @type {Array<{ a: string; [key: string]: any }>} */
  let orbitQueue = [];
  /** Latest snapshot of the agent_view.orbit block, populated on every
   *  status refresh while ``phase === "orbit"``. */
  /** @type {any} */
  let lastOrbitView = null;
  /** v0.9.x — latest static blue-sign overlay (list of fuzzy radiative
   *  regions), refreshed on every live /view poll. Orbit-wide and
   *  fog-independent: identical for every seat, painted over the
   *  player map (including fog cells). */
  /** @type {Array<any>} */
  let lastBlueSign = [];
  // Lookup built from lastBlueSign: "x,y" → intensity [0,1]
  /** @type {Map<string,number>} */
  let _blueSignMap = new Map();
  function _buildBlueSignMap(regions) {
    _blueSignMap.clear();
    for (const region of (Array.isArray(regions) ? regions : [])) {
      for (const c of (Array.isArray(region?.cells) ? region.cells : [])) {
        const inten = Math.max(0, Math.min(1, Number(c[2]) || 0));
        if (inten > 0) _blueSignMap.set(`${c[0]},${c[1]}`, inten);
      }
    }
  }
  function _blueSignStyles(intensity) {
    // Cell background: blend fog dark (15,12,24) → blue-dark (8,22,70).
    // Tinting the opaque background is what makes blue register at low glyph opacity.
    const br = Math.round(15 - 7  * intensity);
    const bg = Math.round(12 + 10 * intensity);
    const bb = Math.round(24 + 46 * intensity);
    // Glyph foreground: blend fog grey (168,177,189) → vivid blue (100,160,255).
    const fr = Math.round(168 - 68 * intensity);
    const fg = Math.round(177 - 17 * intensity);
    const fb = Math.round(189 + 66 * intensity);
    return {
      cell:  `background:rgba(${br},${bg},${bb},0.96)`,
      glyph: `color:rgb(${fr},${fg},${fb})`,
    };
  }
  /** v1.x — REDSIGN: discovery-triggered public beacons over pure-RED
   *  seams (RULEBOOK §4.11). Unlike blue-sign this is NOT baked into cell
   *  glyphs — it's an absolutely-positioned PULSE overlay on
   *  ``collisionFxLayer`` so the animation survives repaints and can glow
   *  over ANY cell kind (strong on fog, translucent over echo/visible).
   *  Each region carries a ``day`` so replay only lights it once the
   *  discovery night is reached. */
  /** @type {Array<any>} */
  let lastRedSign = [];
  /** Day+hour cutoff for the redsign overlay. In replay these track the
   *  current scrub position so a beacon pops at the exact discovery FRAME
   *  (the praxis hour a unit witnessed the seam), not the top of the night.
   *  Live/observer leaves both at Infinity so every discovered beacon
   *  paints. Regions carry {day, hour}; hour defaults to 0 for legacy
   *  regions (which then show from the start of their discovery night). */
  let _redsignDayCutoff = Infinity;
  let _redsignHourCutoff = Infinity;
  /** v1.x — region ids whose one-shot DISCOVERY BURST (red rhombus pulse) has
   *  already fired this playthrough, so it plays exactly once at the discovery
   *  frame. Cleared on scrub/jump so a re-play re-fires it. */
  let _redsignBurstFired = new Set();
  /** v1.x — region ids whose fog smear is held back on forward play until the
   *  probe streak / harvester step that revealed the seam actually lands. The
   *  discovery-burst timer clears the id and repaints, so the smear appears
   *  WITH the burst, not a beat before the probe. Cleared on scrub/jump. */
  let _redsignPendingReveal = new Set();
  function _redsignVisibleRegions() {
    const cd = _redsignDayCutoff;
    const ch = _redsignHourCutoff;
    return (Array.isArray(lastRedSign) ? lastRedSign : []).filter((r) => {
      if (r && r.id && _redsignPendingReveal.has(r.id)) return false; // held for burst
      const d = Number(r?.day);
      if (!Number.isFinite(d)) return true;   // no day (live) → always paint
      if (d < cd) return true;                // discovered on an earlier night
      if (d > cd) return false;               // not discovered yet
      const h = Number(r?.hour) || 0;         // same night → gate by hour
      return ch >= h;
    });
  }
  // v0.9.5 — current game day, refreshed every status poll. Used by
  // the shared asset tooltip to compute "alive · N days" / "deployed
  // · N days ago" without piping the day through every render. Null
  // until the first status response lands.
  /** @type {number | null} */
  let __currentGameDay = null;
  /** When non-null, next map click fills coords for this action. */
  let pickMode = /** @type {string|null} */ (null);
  /** v0.9.13 — set true by the touch gesture layer after a pan/pinch so
   *  the trailing synthetic ``click`` on ``#map-player`` doesn't fire a
   *  stray deploy. Consumed (reset) by the map click handler. */
  let _suppressNextMapClick = false;
  /** "live" | "replay": whether ``#map-player`` shows dawn API snapshot or rewound replay. */
  let mainMapSource = "live";
  /** Cached last percept for returning from replay without refetching. */
  /** @type {{ width: number; height: number; cells: any[] } | null} */
  let lastLiveMapPayload = null;

  // ── v0.7.5 universal-strip / per-seat tabs state ────────────────
  /** Most recently observed session phase ("planning", "policy_open",
   *  "night_resolving", "season_complete", etc.). Drives the LIVE
   *  button pulse: pulsing while the engine is mid-game, steady
   *  while finished / replay-only. */
  let livePhase = null;
  /** Last inventory payload we saw in live mode. Cached so the
   *  scoreboard + vault renderers can stay synced even between
   *  status pings. */
  /** @type {any} */
  let lastLiveInventory = null;
  /** v0.9.x — uncapped PUBLIC all-seat SHIPPED ledger from the latest
   *  /view. Every house's shipments, owner-tagged, full detail. Painted
   *  into the SHIPPED pane even in live play (shipping is public). */
  /** @type {any[]} */
  let lastLiveShippedRecord = [];
  // Expose the viewer's TRUE current live vault to the orbital-station panel so
  // its LIVE view shows the real post-orbital hoard (not a stale replay-frame
  // reconstruction). Only MY_SEAT is known in live play (fog hides rivals).
  // v1.13 — a straight passthrough now. This used to overlay the queued
  // refine's optimistic outcome, because refining was the one orbit
  // action that rewrote the vault before commit. Nothing left in the
  // queue touches the hoard, so the live reading is always the truth.
  window._socLiveInventory = (seat) => {
    if (seat !== MY_SEAT || !lastLiveInventory) return null;
    return lastLiveInventory;
  };
  // v1.9 (bug #10) — one-shot consistency audit for the vault surfaces. Compares,
  // per active seat, the VAULT-tab reading, the ORBITAL-station diamond's working
  // cell count, and the AUTHORITATIVE hoard (live inventory in play, per-tick
  // frame reconstruction in replay). Any row with mismatched numbers is the
  // exact "tab X / station Y / actual Z" repro the triage note asks for. Call
  // ``_socVaultAudit()`` from the console (returns the rows and warns on drift).
  window._socVaultAudit = function () {
    const rows = [];
    const replay = mainMapSource === "replay" && replayTicks.length > 0;
    const tick = replay
      ? Math.max(0, Math.min(replayTickIdx, replayTicks.length - 1))
      : null;
    for (const seat of activeSeats()) {
      let authoritative = null;
      if (replay) {
        const inv = reconstructVaultAtTick(tick, seat);
        authoritative = Array.isArray(inv && inv.hoard) ? inv.hoard.length : null;
      } else if (seat === MY_SEAT && lastLiveInventory) {
        const linv = window._socLiveInventory(seat);
        authoritative = Array.isArray(linv && linv.hoard) ? linv.hoard.length : null;
      }
      const tab = authoritative; // the tab renders from the same authoritative source
      const station =
        typeof window._osVaultCount === "function"
          ? window._osVaultCount(seat)
          : null;
      const drift = station != null && authoritative != null && station !== authoritative;
      rows.push({ seat, tab, station, authoritative, drift });
    }
    const bad = rows.filter((r) => r.drift);
    if (bad.length) {
      const where = replay
        ? `replay day ${String(currentReplayDay())} (tick ${String(tick)})`
        : "live play";
      console.warn(`[vault-audit] ${where}: diamond disagrees with hoard`, bad);
    } else {
      console.info("[vault-audit] all vault surfaces agree", rows);
    }
    return rows;
  };
  /** Active seat for the AGENT panel sub-tabs (rationale view). */
  let agentSeat = MY_SEAT;
  /** Active seat for the VAULT panel sub-tabs. */
  let vaultSeat = MY_SEAT;
  /** v0.9.12 — true while a TRANSMIT round-trip is in flight, so the
   *  standing live-sync poller doesn't fight the submit's own refresh. */
  let inFlightSubmit = false;
  /** v0.9.12 — set once a multi-human game is spawned/joined so the seat
   *  identity badge + waiting strip render. */
  let _multiHumanGame = false;
  /** v1.7 — true after WE lock in a multi-human turn whose night/orbit did
   *  NOT resolve on our submit (other humans still pending). Keeps the
   *  committed "waiting for players" overlay up instead of bouncing back to
   *  the composer (bug #3); the live-sync poller drives the resolution
   *  cinematic + tears the frame down once the last human submits (bug #4). */
  let _awaitingHumanResolution = false;
  /** Which composer we locked from — "praxis" or "orbit" — so the resolution
   *  finaliser re-enables the right button. */
  let _awaitingHumanMode = "praxis";
  /** Handle to the frozen transmit-progress feed for the committed wait. */
  let _humanWaitProgress = /** @type {any} */ (null);
  /** v1.11 — set in refreshStatus when any seat runs a slow (Cortex/harness)
   *  agent. Drives the non-blocking submit + "waiting on <agent>" wait frame
   *  in the solo human-vs-agent flow. */
  let _slowBotGame = false;
  /** v1.11 — what the committed wait frame is waiting on, so the ticker can
   *  paint a live "waiting on V12 · Ns / ~80s" headline. */
  let _waitTicker = null;
  let _waitAgent = /** @type {any} */ (null); // {agent, seat, baseMs, capMs}
  let _waitHumans = /** @type {string[]} */ ([]);
  const _AGENT_CAP_MS_FALLBACK = 80_000;
  /** v0.9.13 — cached LAN origin (e.g. "http://192.168.1.42:8000") from
   *  /api/meta/lan, so invite links / QR codes are phone-reachable rather
   *  than ``localhost``. ``null`` = not fetched yet, ``""`` = unavailable. */
  let _lanOrigin = /** @type {string|null} */ (null);
  /** Rationale capture, bucketed by (seat -> day -> [entries]). Each
   *  entry: { ts, day, seat, agent_id, runtime, text }. Populated
   *  both from the live "agent think" handler AND from a lazy fetch
   *  of /api/game/{id}/agent-log when replay/watch loads a persisted
   *  season. */
  /** @type {{p1: Map<number, any[]>, p2: Map<number, any[]>}} */
  // v0.9.8 — N-seat agent log buckets. Pre-v0.9.8 only ``p1`` /
  // ``p2`` had a Map; in 3- and 4-seat games p3/p4 rationales were
  // either silently dropped (by the harvest regex) OR coerced into
  // the p1 bucket (the ``"p2" ? "p2" : "p1"`` ternary in
  // ``captureAgentRationale``), which made the AGENT panel show
  // p1+p3+p4 events smeared together. Buckets are now created on
  // demand for any seat slug, with a helper that auto-provisions.
  const agentLogByDay = { p1: new Map(), p2: new Map(), p3: new Map(), p4: new Map() };
  function _agentBucketFor(seat) {
    if (!seat) return null;
    if (!agentLogByDay[seat]) agentLogByDay[seat] = new Map();
    return agentLogByDay[seat];
  }
  /** Set of (sessionId|day|seat) we have already pulled from the
   *  agent-log endpoint, to avoid re-fetching as the user scrubs. */
  const agentLogFetched = new Set();

  /** Matches an agent-rationale LOG line:
   *  ``[SOC_RED_REAPER] [cortex] (p2) day 3 plan: …`` — captures
   *  (agent_id, runtime, seat, body). These lines are a seat's PRIVATE
   *  planning reasoning; they must never bleed into another seat's
   *  shared LOG / night chronicle (fog-of-war). The per-seat AGENT tab
   *  is the one place they're shown, gated by perspective. */
  const AGENT_RATIONALE_RE =
    /^\[([A-Z0-9_]+)\]\s*(?:\[([a-z]+)\]\s*)?\(([pP][1-4])\)\s*(.+)$/;

  /** Seat slug owning an agent-rationale line, or ``null`` if the entry
   *  isn't one. Accepts a raw string or a ``{text}`` log entry. */
  function rationaleSeatOf(entry) {
    const text = typeof entry === "string" ? entry : String(entry?.text || "");
    const m = text.match(AGENT_RATIONALE_RE);
    return m ? m[3].toLowerCase() : null;
  }

  /** Fog-of-war gate for shared LOG surfaces. A non-rationale line is
   *  always allowed; an agent-rationale line is allowed only when the
   *  viewer "is" that seat — live play exposes p1, single-seat replay
   *  exposes that seat, and OBS / omniscient replay exposes everyone
   *  (all driven by ``reportExactSeats``). This keeps opponents' private
   *  planning reasoning (and the exact probe coordinates it cites) out
   *  of your night chronicle and live log. */
  function viewerMaySeeLogEntry(entry) {
    const seat = rationaleSeatOf(entry);
    if (!seat) return true;
    return reportExactSeats().has(seat);
  }

  /** @param {string} s */
  /** v0.8.1 — animate the TRANSMIT/PRAXIS button while we're
   *  round-tripping with Snowflake. Cycles through the Unicode
   *  density shade glyphs (░ ▒ ▓ █) as a "signal flowing" cue so
   *  the human knows the click registered even when the Cortex
   *  agent takes 60–90s to respond.
   *
   *  Usage:
   *    const stop = startTransmittingAnim(btn, "[ %s TRANSMITTING %s ]");
   *    try { await ... } finally { stop(); }
   *
   *  The %s placeholders get replaced with the current density
   *  glyph each tick. The button's original textContent is
   *  restored when ``stop()`` is called. */
  function startTransmittingAnim(btn, template) {
    if (!btn) return () => {};
    const glyphs = ["░", "▒", "▓", "█", "▓", "▒"];
    const original = btn.textContent;
    const wasDisabled = btn.disabled;
    btn.disabled = true;
    btn.classList.add("cli-btn--transmitting");
    let i = 0;
    let label = (template || "[ %s TRANSMITTING %s ]");
    const tick = () => {
      const g = glyphs[i % glyphs.length];
      btn.textContent = label.replaceAll("%s", g);
      i += 1;
    };
    tick();
    const handle = window.setInterval(tick, 140);
    const ctl = () => {
      window.clearInterval(handle);
      btn.textContent = original;
      btn.classList.remove("cli-btn--transmitting");
      btn.disabled = wasDisabled;
    };
    /** Hot-swap the button label template mid-flight so the headline
     *  tracks the server's current phase (e.g. "RESOLVING NOX" →
     *  "BOTS PLOTTING" → "DAY 2 OPENING"). The next density-shade tick
     *  picks up the new template; we also paint the new label
     *  immediately so the swap feels instant. */
    ctl.setLabel = (next) => {
      if (!next) return;
      label = next;
      tick();
    };
    return ctl;
  }

  /**
   * v0.9.8 — live progress feed shown beneath a TRANSMIT button while
   * the submit is in flight. Polls ``/api/game/{id}/status`` every
   * 700ms and diff-renders human-readable lines as the server walks
   * the phase graph (human submit landed → bot p2 plotted → bot p3
   * plotted → night resolves → orbit settles → next day opens). Stops
   * itself when ``stop()`` is called (or the page is hidden). The
   * status endpoint is cheap (single hydrate, no save) so polling at
   * this cadence costs ~1 read per second on a healthy warehouse.
   *
   * Usage:
   *   const feed = startTransmitProgress({
   *     listEl: document.getElementById("solo-commit-progress"),
   *     btnAnim: stopAnim,            // returned by startTransmittingAnim
   *     phaseSnapshot,                 // optional { phase, day } seed
   *     mode: "praxis" | "orbit",     // shapes the headline label
   *   });
   *   try { await ... } finally { feed.stop(); }
   *
   * @param {{
   *   listEl: HTMLElement | null,
   *   btnAnim: ((sel?: string) => void) & { setLabel?: (s: string) => void } | null,
   *   phaseSnapshot?: { phase?: string, day?: number } | null,
   *   mode?: "praxis" | "orbit",
   * }} opts
   */
  function startTransmitProgress(opts) {
    const {
      listEl,
      btnAnim,
      phaseSnapshot,
      mode = "praxis",
    } = opts || {};
    const stopFns = [];
    const seenSigs = new Set();

    const setBtnLabel = (next) => {
      if (btnAnim && typeof btnAnim.setLabel === "function") {
        btnAnim.setLabel(next);
      }
    };

    /** Append a line; dedupe by signature so multiple poll rounds
     *  don't repeat the same event. Marks the latest line with the
     *  ``--latest`` class for the cursor blink + pulse. */
    const pushLine = (sig, msg, /** @type {"info"|"ok"|"warn"} */ kind = "info", tag = "") => {
      if (!listEl) return;
      if (seenSigs.has(sig)) return;
      seenSigs.add(sig);
      if (listEl.hidden) listEl.hidden = false;
      // Demote the previous "latest" so the new one is the only one
      // wearing the cursor.
      const prev = listEl.querySelector(".cc-transmit-line--latest");
      if (prev) prev.classList.remove("cc-transmit-line--latest");
      const li = document.createElement("li");
      li.className =
        "cc-transmit-line--latest" +
        (kind === "ok" ? " cc-transmit-line--ok" :
         kind === "warn" ? " cc-transmit-line--warn" : "");
      if (tag) {
        const t = document.createElement("span");
        t.className = "cc-transmit-tag";
        t.textContent = tag;
        li.appendChild(t);
      }
      const m = document.createElement("span");
      m.className = "cc-transmit-msg";
      m.textContent = msg;
      li.appendChild(m);
      listEl.appendChild(li);
      // Cap the list so a long-lived session doesn't accumulate
      // forever; the CSS already overflow-hides anything past ~9
      // lines but DOM bloat is its own problem.
      while (listEl.childElementCount > 12) {
        listEl.removeChild(/** @type {Node} */ (listEl.firstChild));
      }
      // Scroll to the bottom inside the overflow box so the latest
      // line is always visible.
      listEl.scrollTop = listEl.scrollHeight;
    };

    /** Translate a single log_tail entry into a friendly progress line
     *  + a headline label hint. Returns null if we don't want to
     *  surface this entry (e.g. low-signal noise from the resolver). */
    const interpretLog = (text) => {
      if (!text) return null;
      // Bot rationale lines: "[RED_HARVEST] [heuristic] (pN) ..."
      let m = text.match(
        /^\[RED_HARVEST\]\s*(?:\[[^\]]+\]\s*)?\(([^)]+)\)\s*(.*)$/,
      );
      if (m) {
        const seat = m[1];
        const rest = m[2] || "";
        const trim = rest.length > 64 ? rest.slice(0, 61) + "…" : rest;
        return {
          tag: seat,
          msg: `bot plotted · ${trim}`,
          kind: "info",
          headline: `[ %s BOTS PLOTTING %s ]`,
        };
      }
      // Per-seat policy / orbit lock lines: "day N: pN locked policy (K move(s))."
      m = text.match(
        /^day\s+(\d+):\s+(p\d+)\s+locked\s+(policy|orbit)\s+\((\d+)\s+(?:action|move)/,
      );
      if (m) {
        const seat = m[2];
        const kind = m[3];
        const n = m[4];
        return {
          tag: seat,
          msg: `${kind} lock · ${n} ${kind === "policy" ? "move" : "action"}(s)`,
          kind: "info",
          headline:
            kind === "policy"
              ? "[ %s BOTS PLOTTING %s ]"
              : "[ %s BOTS ON ORBIT %s ]",
        };
      }
      // Night narration boundary.
      m = text.match(/^\[praxis\]\s+day\s+(\d+).*night\s+begins/);
      if (m) {
        return {
          tag: `D${m[1]}`,
          msg: "Nox resolving · praxis fires",
          kind: "info",
          headline: "[ %s RESOLVING NOX %s ]",
        };
      }
      // Dawn / orbit-open marker.
      m = text.match(/dawnComplete|day\s+(\d+)\s+opens\s+in\s+orbit/i);
      if (m) {
        return {
          tag: m[1] ? `D${m[1]}` : "",
          msg: "Aurora complete · orbit opens",
          kind: "ok",
          headline: "[ %s BOTS ON ORBIT %s ]",
        };
      }
      // Orbit settlement (catapult / refinery chatter).
      m = text.match(/^\[orbit\]\s+(?:day\s+\d+\s+)?(.*)$/);
      if (m) {
        const detail = m[1] || "";
        const trim = detail.length > 56 ? detail.slice(0, 53) + "…" : detail;
        return {
          tag: "",
          msg: `orbit · ${trim}`,
          kind: "info",
          headline: "[ %s SETTLING ORBIT %s ]",
        };
      }
      // Probe launches during night narration.
      m = text.match(
        /^(p\d+)\s+launched\s+(probe_[^\s]+)\s+at\s+\(([^)]+)\)/,
      );
      if (m) {
        return {
          tag: m[1],
          msg: `probe ${m[2].split("_").pop()} → (${m[3]})`,
          kind: "info",
          headline: "[ %s RESOLVING NOX %s ]",
        };
      }
      return null;
    };

    let lastSeenDay = phaseSnapshot?.day ?? null;
    let lastSeenPhase = phaseSnapshot?.phase ?? null;
    let pollInflight = false;

    const poll = async () => {
      if (!sessionId || pollInflight) return;
      pollInflight = true;
      try {
        const res = await fetch(
          `/api/game/${sessionId}/status`,
          { cache: "no-store" },
        );
        if (!res.ok) return;
        const st = await res.json();
        const tail = Array.isArray(st.log_tail) ? st.log_tail : [];
        // Walk the tail oldest → newest so the dedupe set keeps
        // chronological ordering when we surface lines.
        for (let i = 0; i < tail.length; i++) {
          const entry = tail[i];
          const text = String(entry?.text || "");
          if (!text) continue;
          const sig = `log:${text}`;
          if (seenSigs.has(sig)) continue;
          const parsed = interpretLog(text);
          if (!parsed) {
            // Still mark as seen so the next poll doesn't re-evaluate.
            seenSigs.add(sig);
            continue;
          }
          pushLine(sig, parsed.msg, parsed.kind, parsed.tag);
          if (parsed.headline) setBtnLabel(parsed.headline);
        }
        // Day-flip detection. Drives the "DAY N+1 OPENS" line + label.
        const curDay = Number(st.day || 0);
        const curPhase = String(st.phase || "");
        if (
          lastSeenDay !== null
          && curDay > Number(lastSeenDay)
        ) {
          const sig = `day-open:${curDay}-${curPhase}`;
          pushLine(
            sig,
            `day ${curDay} opens · ${curPhase}`,
            "ok",
            `D${curDay}`,
          );
          setBtnLabel("[ %s DAY OPENING %s ]");
        } else if (
          lastSeenPhase !== null
          && curPhase !== lastSeenPhase
        ) {
          const sig = `phase-flip:${lastSeenPhase}->${curPhase}-${curDay}`;
          pushLine(
            sig,
            `phase · ${lastSeenPhase} → ${curPhase}`,
            "ok",
            `D${curDay}`,
          );
        }
        lastSeenDay = curDay;
        lastSeenPhase = curPhase;
      } catch {
        // Polling is best-effort; a transient network blip should
        // never break the actual submit's promise.
      } finally {
        pollInflight = false;
      }
    };

    // Surface an immediate "transmitting…" line so the panel pops the
    // moment the user clicks — confirms the click registered even
    // before the first /status poll lands.
    if (listEl) {
      listEl.innerHTML = "";
      listEl.hidden = false;
      pushLine(
        "start",
        mode === "orbit"
          ? "transmitting orbit actions → praxis"
          : "transmitting policy → praxis",
        "info",
        "you",
      );
    }
    // Stagger the first poll — the server's submit_policy call holds
    // the connection open while it batches every write into ONE
    // ``save_session_full`` (v0.9.8) so ``/status`` polls during the
    // call return STALE state (the row in SOC_GAME_SESSION won't
    // reflect the in-flight changes until the save lands). The
    // polling still catches the final post-save state as soon as the
    // submit returns, which is the main signal we want.
    const startTimer = window.setTimeout(() => {
      void poll();
    }, 800);
    const handle = window.setInterval(poll, 900);
    stopFns.push(() => window.clearInterval(handle));
    stopFns.push(() => window.clearTimeout(startTimer));

    // Synthetic timeline. The user is going to stare at the button
    // for ~5–8s of Snowflake writes (POST /policy total ≈ 5–8s
    // post-v0.9.8 for a 4-seat game). Polling /status can't surface
    // intermediate state because save_session_full is the durability
    // boundary — so we fire a sequence of "this is roughly what the
    // server is doing right now" lines on a fixed clock. Real
    // log_tail entries from /status supersede the synthetic ones via
    // the dedupe set as soon as they arrive.
    const t0 = performance.now();
    // Server reality (per SOC_PERF logs, post-v0.9.8 4-seat game):
    //   ~700ms  hydrate_session  (Snowflake read)
    //   ~100ms  fire_bots_in_memory (3-6 bots in ~30ms each)
    //    ~5ms   night/orbit resolve (in-memory)
    //   3-4s    save_session_full + append_log + append_replay_frames
    //           + append_agent_invocations (parallel write fan-out)
    // The timeline below mirrors that — fast burst of in-engine
    // activity in the first ~1.2s, then "writing to praxis" for the
    // remainder. Real /status data takes over after the writes land.
    /** @type {Array<{at:number,sig:string,msg:string,kind:"info"|"ok"|"warn",tag:string,headline?:string}>} */
    const timeline =
      mode === "orbit"
        ? [
            { at:  300, sig: "syn:hydrate", tag: "soc",   msg: "hydrating session blob",        kind: "info" },
            { at:  800, sig: "syn:bots",    tag: "bots",  msg: "bots plotting orbit playbook",  kind: "info", headline: "[ %s BOTS ON ORBIT %s ]" },
            { at: 1300, sig: "syn:res",     tag: "rdv",   msg: "settling vault \u2014 shipping + disposal",  kind: "info", headline: "[ %s SETTLING ORBIT %s ]" },
            { at: 1800, sig: "syn:save",    tag: "io",    msg: "writing to praxis ledgers",     kind: "info", headline: "[ %s WRITING / PRAXIS %s ]" },
            { at: 3500, sig: "syn:wait",    tag: "io",    msg: "syncing entity + grid state",   kind: "info" },
            { at: 6000, sig: "syn:longer",  tag: "io",    msg: "warehouse cold start? hold on…", kind: "warn" },
          ]
        : [
            { at:  300, sig: "syn:hydrate", tag: "soc",   msg: "hydrating session blob",        kind: "info" },
            { at:  800, sig: "syn:bots",    tag: "bots",  msg: "bots plotting Nox moves",       kind: "info", headline: "[ %s BOTS PLOTTING %s ]" },
            { at: 1300, sig: "syn:night",   tag: "praxis", msg: "praxis resolving Nox",         kind: "info", headline: "[ %s RESOLVING NOX %s ]" },
            { at: 1800, sig: "syn:dawn",    tag: "dawn",  msg: "Aurora breaks · orbit opens",   kind: "info", headline: "[ %s OPENING DAY %s ]" },
            { at: 2300, sig: "syn:obots",   tag: "bots",  msg: "bots playing orbit phase",      kind: "info", headline: "[ %s BOTS ON ORBIT %s ]" },
            { at: 2800, sig: "syn:save",    tag: "io",    msg: "writing to praxis ledgers",     kind: "info", headline: "[ %s WRITING / PRAXIS %s ]" },
            { at: 5000, sig: "syn:wait",    tag: "io",    msg: "syncing entity + grid state",   kind: "info" },
            { at: 8000, sig: "syn:longer",  tag: "io",    msg: "warehouse cold start? hold on…", kind: "warn" },
          ];
    /** Cursor into the timeline so each entry fires at most once. */
    let syntheticIdx = 0;
    const synthTick = () => {
      const dt = performance.now() - t0;
      while (
        syntheticIdx < timeline.length
        && dt >= timeline[syntheticIdx].at
      ) {
        const step = timeline[syntheticIdx];
        pushLine(step.sig, step.msg, step.kind, step.tag);
        if (step.headline) setBtnLabel(step.headline);
        syntheticIdx += 1;
      }
    };
    const synthHandle = window.setInterval(synthTick, 200);
    stopFns.push(() => window.clearInterval(synthHandle));

    return {
      stop({ keepLines = false } = {}) {
        for (const f of stopFns) {
          try { f(); } catch { /* noop */ }
        }
        if (!keepLines && listEl) {
          // Fade then clear so the user gets visual confirmation that
          // the operation completed and the panel is settling.
          window.setTimeout(() => {
            listEl.innerHTML = "";
            listEl.hidden = true;
          }, 600);
        }
      },
      // Surface a one-off line from caller code (e.g. "ready · your move").
      pushLine,
    };
  }

  function esc(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  /** Escape for HTML double-quoted attributes (tooltips). */
  function escAttr(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  // Trail-tier glyphs mirror Python's PATH_TIER_GLYPHS so the JS renderer
  // can paint observer trails without needing a tier hint from the
  // server. 1 visit → ░░ (light), 2 → ▒▒, 3 → ▓▓, 4+ → ██ (saturated).
  const PATH_TIER_GLYPHS = ["\u2591\u2591", "\u2592\u2592", "\u2593\u2593", "\u2588\u2588"];
  function trailTierGlyph(n) {
    if (!Number.isFinite(n) || n <= 0) return null;
    const idx = Math.min(Math.max(1, Math.floor(n)), PATH_TIER_GLYPHS.length) - 1;
    return PATH_TIER_GLYPHS[idx];
  }
  // Neutral trail tint — v0.7.2 made trails universal (RULEBOOK §3.12),
  // so we no longer tint per seat. The map alone communicates traffic
  // density; the OWNER who laid a fresh crossing surfaces only via the
  // tooltip / fresh_visits list.
  //
  // v0.7.3 — harvested cells no longer recolour the trail. The tile's
  // own background already carries the harvest signal: RED→GREEN cells
  // paint their BG synthetic-green, and GREEN/BLUE harvests collapse to
  // EMPTY (no green left at all). Tinting the trail glyph green on top
  // of those cells was double-counting on RED-harvests and outright
  // lying on GREEN/BLUE-harvests, so the trail now reads neutral white
  // everywhere. The ``harvested`` flag survives on the trail summary
  // for tooltips and agent reasoning — only its visual side-effect is
  // gone.
  const TRAIL_COLOR_NEUTRAL = "#dcdee6";

  /**
   * Render the universal trail overlay for one cell.
   * v0.7.2: ``cell.trail`` is now a single summary object
   * ``{n, tier, harvested?, fresh_visits: [...]}``. Both seats'
   * crossings are baked into ``n``; per-player attribution is
   * surfaced via the tooltip (see :func:`trailTooltipParts`), not
   * via colour. ``cell.trail_markup`` (Python-rendered glyph + fg) is
   * accepted as a legacy fallback for player_dense_view cells.
   * @param {object} cell
   */
  function renderTrailOverlayHtml(cell) {
    const t = cell && cell.trail;
    if (t && typeof t === "object" && typeof t.n === "number") {
      const glyph = trailTierGlyph(t.n);
      if (!glyph) return "";
      // Fresh crossings get full opacity so the eye picks out
      // last-night activity at a glance without colour-coding by seat.
      const op =
        Array.isArray(t.fresh_visits) && t.fresh_visits.length
          ? "0.95"
          : "0.7";
      return `<span class="trail-overlay" style="color:${esc(TRAIL_COLOR_NEUTRAL)};opacity:${op}">${esc(glyph)}</span>`;
    }
    // Legacy fallback: server still emits ``trail_markup`` for some
    // player-dense paths during the v0.7.2 transition. Render the
    // pre-computed glyph but force the neutral trail tint so the
    // harvested-cell green tint from older payloads doesn't leak
    // through (v0.7.3 — trails are colour-agnostic to harvest state;
    // the cell's own BG carries the harvest signal).
    const m = cell && cell.trail_markup;
    if (m && m.ch != null) {
      return `<span class="trail-overlay" style="color:${esc(TRAIL_COLOR_NEUTRAL)}">${esc(String(m.ch))}</span>`;
    }
    return "";
  }

  /**
   * Human-readable trail entries for the cell hover tooltip. The new
   * universal trail (v0.7.2) carries an aggregate ``n`` and an
   * optional ``fresh_visits`` list. Fresh visits (≤ 1 day of game
   * time) print a verbose line — *"P1 · harvester_p1 walked here ·
   * Day 4"* — so a watcher can read the recent action without
   * scrubbing replay frames. Older crossings are anonymous: just the
   * total tier + density.
   * @param {object} cell
   */
  function trailTooltipParts(cell) {
    const t = cell && cell.trail;
    if (!t || typeof t !== "object" || typeof t.n !== "number") return [];
    const out = [];
    const fresh = Array.isArray(t.fresh_visits) ? t.fresh_visits : [];
    if (fresh.length) {
      for (const v of fresh) {
        if (!v || !v.owner) continue;
        const who = playerTag(v.owner);
        const harv = v.h ? ` · ${v.h}` : "";
        const day = (typeof v.day === "number") ? ` · Day ${v.day}` : "";
        const verb = (v.n || 0) > 1 ? `crossed (×${v.n})` : "walked here";
        out.push(`${who}${harv} ${verb}${day} (fresh)`);
      }
      // If the aggregate exceeds the fresh-visit sum, surface the
      // anonymous remainder so the density tier still has a story.
      const freshSum = fresh.reduce((a, v) => a + (v.n || 0), 0);
      if (t.n > freshSum) {
        const older = t.n - freshSum;
        out.push(`+${older} older crossing${older === 1 ? "" : "s"}`);
      }
    } else if (t.n > 0) {
      out.push(`trail · ×${t.n} crossing${t.n === 1 ? "" : "s"} (older)`);
    }
    if (t.harvested) {
      out.push("harvested (synthetic green — banking scores 0)");
    }
    return out;
  }

  /** @param {object} cell */
  function occupantsTitle(cell) {
    const occ =
      cell && Array.isArray(cell.occupants) ? cell.occupants : [];
    const labels = occ.map((o) => o.label || o.id || "").filter(Boolean);
    const trailParts = trailTooltipParts(cell);
    const merged = labels.concat(trailParts);
    return merged.join(" · ");
  }

  /** Lazily-built floating coord/occupant tooltip; one for the whole page. */
  const cellTooltip = (() => {
    const el = document.createElement("div");
    el.className = "cell-tooltip";
    el.hidden = true;
    el.setAttribute("aria-hidden", "true");
    document.body.appendChild(el);
    return el;
  })();

  /**
   * Format full cell data for the hover tooltip.
   * @param {any} c  raw cell object from __cellStore
   * @param {number} xi
   * @param {number} yi
   * @param {{mines?: any[], empClouds?: any[]}} [meta]
   *   Frame-level fallbacks for mine + EMP cloud surfaces. Replay
   *   frames recorded before v0.9.5 don't stamp ``mine`` /
   *   ``emp_cloud`` onto each cell, so we cross-reference the
   *   authoritative ``mines_active`` / ``emp_clouds`` arrays that
   *   :func:`paintMinesOverlay` and :func:`paintEmpCloudOverlay`
   *   already consume.
   */
  function formatCellTip(c, xi, yi, meta) {
    if (!c) return `(${xi},${yi})\n(no data)`;
    const lines = [`(${xi},${yi})`];
    if (c.kind === "fog") {
      // v0.9.7 — probe-launch markers carry the enemy probe occupant
      // even though the terrain underneath stays fog. Surface the
      // occupant label(s) so the watcher tooltip explains the glyph
      // they're seeing hover over a fogged tile.
      const occ = Array.isArray(c.occupants) ? c.occupants : [];
      if (occ.length) {
        lines.push("fog (terrain unseen)");
        for (const o of occ) {
          const lbl = (o && (o.label || o.id)) || "";
          if (lbl) lines.push(lbl);
        }
        return lines.join("\n");
      }
      lines.push("fog");
      return lines.join("\n");
    }

    // Visibility tier
    lines.push(c.stale || c.echo_probe ? "echo (historical)" : "live");

    // Tile type + purity tier — inferred from the deterministic render colors.
    // RED lower tiers:  fg="rgb(255,0,0)", bg=void dark, ch = ░░/▒▒/▓▓
    // RED pure (255):   bg="rgb(255,0,0)", ch = "  "
    // GREEN:            bg="rgb(63,185,80)", ch = "  "
    // BLUE lower tiers: fg="rgb(59,143,224)", bg=void dark, ch = ░░/▒▒/▓▓
    // BLUE deep (255):  bg="rgb(59,143,224)", ch = "  "
    // EMPTY:            bg=void dark, fg=void dark, ch = ██
    const fg = c.fg || "";
    const bg = c.bg || "";
    const ch = c.ch || "";
    if (fg === "rgb(255,0,0)") {
      const tierName = ch === "░░" ? "trace" : ch === "▒▒" ? "vein" : "mass";
      const range    = ch === "░░" ? "0–50" : ch === "▒▒" ? "51–150" : "151–254";
      lines.push(`RED · ${tierName}  (purity ${range})`);
    } else if (bg === "rgb(255,0,0)") {
      lines.push("RED · pure  (purity 255)");
    } else if (bg === "rgb(63,185,80)") {
      lines.push("GREEN");
    } else if (fg === "rgb(59,143,224)") {
      const tierName = ch === "░░" ? "shallow" : ch === "▒▒" ? "mid" : "sink";
      const range    = ch === "░░" ? "0–50" : ch === "▒▒" ? "51–150" : "151–254";
      lines.push(`BLUE · ${tierName}  (purity ${range})`);
    } else if (bg === "rgb(59,143,224)") {
      lines.push("BLUE · deep  (purity 255)");
    } else {
      lines.push("EMPTY");
    }

    // v0.9.5 — track which occupant id was already represented as
    // the "entity" line so we don't print it a second time in the
    // generic occupants loop below. Cells with multiple stacked
    // entities (rare — harvester + probe, two probes mid-collision)
    // still surface every extra occupant; only the duplicate of the
    // primary glyph is suppressed.
    const consumedOccIds = new Set();
    if (c.entity && c.entity.ch != null) {
      const eCh = c.entity.ch;
      const occ = Array.isArray(c.occupants) ? c.occupants.find(
        (/** @type {any} */ o) => o.type === "harvester" || o.type === "orblift" || o.type === "probe"
      ) : null;
      if (occ && occ.id) consumedOccIds.add(occ.id);
      const ownerId = occ && occ.owner ? ` [${playerTag(occ.owner)}]` : "";
      const entId   = occ ? ` ${occ.id}` : "";
      if (eCh === "X" || eCh === "x") {
        const cargo = c.entity.carrying ? "carrying Red" : "empty hold";
        lines.push(`X  harvester · ${cargo}${ownerId}${entId}`);
      } else if (eCh === "·") {
        // v0.9.18 — surface the probe's remaining coverage life on hover
        // (the on-map ring count is the at-a-glance cue; this is the
        // exact figure). Same datum the agent reads as nights_remaining.
        const nr =
          (c.entity && c.entity.nights_remaining != null)
            ? c.entity.nights_remaining
            : (occ && occ.nights_remaining != null)
              ? occ.nights_remaining
              : null;
        const life =
          nr != null
            ? ` · expires in ${nr} Nox`
            : "";
        lines.push(`·  probe${ownerId}${entId}${life}`);
      } else if (eCh === "▲") {
        lines.push(`▲  orbital lifter${ownerId}${entId}`);
      } else {
        lines.push(`entity: ${eCh}${ownerId}`);
      }
    }
    // v0.9.5 — caltrop mine surfaced as a first-class object on the
    // cell. Visibility is enforced server-side (player_dense_view's
    // mine_visible_to gate honours RULEBOOK §5.2: owner always; other
    // seat only after witnessing the lay or a later fly-over).
    // Replays recorded before v0.9.5 didn't stamp ``mine`` per cell,
    // so we fall back to the frame-level ``mines_active`` list that
    // :func:`paintMinesOverlay` already paints from. Same fallback
    // applies in obs-mode replays for older frames.
    let mineForCell = (c.mine && typeof c.mine === "object")
      ? c.mine
      : null;
    if (!mineForCell && meta && Array.isArray(meta.mines)) {
      for (const m of meta.mines) {
        if (Number(m.x) === xi && Number(m.y) === yi) {
          mineForCell = m;
          break;
        }
      }
    }
    if (mineForCell) {
      const m = /** @type {any} */ (mineForCell);
      const owner = m.owner ? `owner=${playerTag(m.owner)}` : "";
      const laidDay = m.laid_at_day != null ? `laid day ${m.laid_at_day}` : "";
      const laidHour = m.laid_at_hour != null ? `${m.laid_at_hour}:00` : "";
      const metaStr = [owner, [laidDay, laidHour].filter(Boolean).join(" ")]
        .filter(Boolean).join(" · ");
      lines.push(`◆  caltrop mine${metaStr ? "  " + metaStr : ""}`);
    }
    // v0.9.5 — EMP cloud overlay. Public (RULEBOOK §5.1 — clouds
    // aren't gated by fog), surfaced on the cell payload by both
    // observer + player_dense_view so the tooltip can read it
    // without cross-referencing the frame's emp_clouds list. The
    // same back-compat fallback applies to pre-v0.9.5 replays via
    // the frame-level ``emp_clouds`` array.
    let empForCell = (c.emp_cloud && typeof c.emp_cloud === "object")
      ? c.emp_cloud
      : null;
    if (!empForCell && meta && Array.isArray(meta.empClouds)) {
      for (const e of meta.empClouds) {
        const cx = Number(e.cx);
        const cy = Number(e.cy);
        const r = Number(e.radius);
        if (Number.isFinite(cx) && Number.isFinite(cy) && Number.isFinite(r)
            && Math.abs(xi - cx) + Math.abs(yi - cy) <= r) {
          empForCell = e;
          break;
        }
      }
    }
    if (empForCell) {
      const e = /** @type {any} */ (empForCell);
      const owner = e.owner ? `owner=${playerTag(e.owner)}` : "";
      const hours = e.hours_remaining != null
        ? `${e.hours_remaining}h left`
        : "";
      const center = (e.cx != null && e.cy != null)
        ? `center (${e.cx},${e.cy})`
        : "";
      const metaStr = [owner, hours, center].filter(Boolean).join(" · ");
      lines.push(`◌  EMP cloud${metaStr ? "  " + metaStr : ""}`);
    }
    // v0.9.10 — destroyed harvester gravestone marker (permanent).
    if (c.destroyed_harvester && typeof c.destroyed_harvester === "object") {
      const d = c.destroyed_harvester;
      const owner = d.owner ? `[${playerTag(d.owner)}]` : "";
      const harvId = d.harvester_id || "?";
      const day = d.day != null ? `day ${d.day}` : "";
      const metaStr = [owner, day].filter(Boolean).join(" · ");
      lines.push(`†  destroyed harvester${metaStr ? "  " + metaStr : ""}  ${harvId}`);
    }
    // v0.7.2: trails are universal — a single ``cell.trail`` summary
    // with aggregate ``n`` + optional ``fresh_visits`` (≤ 1 day old).
    // The legacy ``cell.trail_markup`` shape (glyph + fg) survives as a
    // server-side fallback for player_dense_view cells.
    const trailLines = trailTooltipParts(c);
    if (trailLines.length) {
      for (const line of trailLines) lines.push(line);
    } else if (c.trail_markup && c.trail_markup.ch != null) {
      lines.push(`trail: ${c.trail_markup.ch}`);
    }
    if (Array.isArray(c.occupants) && c.occupants.length) {
      for (const o of c.occupants) {
        if (o && o.id && consumedOccIds.has(o.id)) continue;
        lines.push(`  · ${o.label || o.id || "?"}`);
      }
    }
    return lines.join("\n");
  }

  /**
   * Bind a single pointer listener to a map host so any descendant `.cell`
   * shows a rich cell-data tooltip on hover.
   * Re-binding is a cheap no-op (idempotent flag on the element).
   * @param {HTMLElement | null} host
   */
  function bindCellHoverTip(host) {
    if (!host) return;
    if (/** @type {any} */ (host).__cellTipBound) return;
    /** @type {any} */ (host).__cellTipBound = true;

    host.addEventListener("pointermove", (ev) => {
      const target = /** @type {Element | null} */ (ev.target);
      const cell = target ? target.closest(".cell") : null;
      if (!cell || !host.contains(cell)) {
        cellTooltip.hidden = true;
        return;
      }
      const xAttr = cell.getAttribute("data-x");
      const yAttr = cell.getAttribute("data-y");
      if (xAttr == null || yAttr == null) {
        cellTooltip.hidden = true;
        return;
      }

      const store = /** @type {any} */ (host).__cellStore;
      let tipText;
      if (store) {
        const xi = parseInt(xAttr, 10), yi = parseInt(yAttr, 10);
        let c = store.cells && store.cells[yi * store.width + xi];
        if (c && c.kind === "fog" && store.obsCells) {
          c = store.obsCells[yi * store.width + xi] ?? c;
        }
        // v0.9.5 — pass the frame-level mine/EMP arrays so older
        // replays (whose cells lack per-cell ``mine`` /
        // ``emp_cloud`` stamps) still surface those objects in the
        // tooltip. Live game views leave these undefined and rely
        // on the per-cell payload from player_dense_view.
        const meta = (store.mines || store.empClouds)
          ? { mines: store.mines || [], empClouds: store.empClouds || [] }
          : undefined;
        tipText = formatCellTip(c, xi, yi, meta);
      } else {
        const occ = cell.getAttribute("data-occ") || "";
        tipText = occ ? `(${xAttr},${yAttr}) · ${occ}` : `(${xAttr},${yAttr})`;
      }
      cellTooltip.textContent = tipText;
      const pad = 14;
      cellTooltip.style.left = `${Math.max(2, ev.clientX + pad)}px`;
      cellTooltip.style.top  = `${Math.max(2, ev.clientY + pad)}px`;
      cellTooltip.hidden = false;
    });

    host.addEventListener("pointerleave", () => {
      cellTooltip.hidden = true;
    });
  }

  /** @param {HTMLElement} el @param {string} text */
  function paintPlaceholder(el, text) {
    el.textContent = "";
    el.classList.remove("map-grid", "map-grid--lines");
    el.style.removeProperty("--map-cols");
    const span = document.createElement("span");
    span.className = "dim";
    span.textContent = text;
    el.appendChild(span);
  }

  function allMapGrids() {
    return Array.from(document.querySelectorAll(".map-host .map-grid"));
  }

  function syncGridlinesClass() {
    const on = Boolean(gridlinesEl?.checked);
    if (gridlinesBox) {
      gridlinesBox.textContent = on ? "[x]" : "[ ]";
    }
    try {
      localStorage.setItem(GRID_LINES_KEY, on ? "1" : "0");
    } catch (_) {
      /* ignore */
    }
    for (const g of allMapGrids()) {
      g.classList.toggle("map-grid--lines", on);
    }
  }

  /**
   * Paint dense observer map (classic generate shape).
   * @param {HTMLElement} host
   * @param {{width:number,height:number,cells:any[]}} data
   */
  function paintObserverMap(host, data) {
    const { width, height, cells } = data;
    const lines = Boolean(gridlinesEl?.checked);
    const cls = lines ? "map-grid map-grid--lines" : "map-grid";
    const parts = [];
    let idx = 0;
    for (let y = 0; y < height; y++) {
      parts.push('<div class="row">');
      for (let x = 0; x < width; x++) {
        const c = cells[idx++];
        const fg = c.fg ? `;color:${esc(c.fg)}` : "";
        const tt = occupantsTitle(c);
        const occAttr = tt ? ` data-occ="${escAttr(tt)}"` : "";
        const ent = c.entity;
        const entHtml =
          ent && typeof ent.ch === "string" ?
            `<span class="entity-overlay" style="color:${esc(ent.fg || "#fff")}">${esc(ent.ch === "x" ? "X" : ent.ch)}</span>`
          : "";
        // Trail overlay (v0.7.2): single universal glyph; attribution
        // for fresh visits is surfaced through the tooltip, not colour.
        const trailHtml = renderTrailOverlayHtml(c);
        parts.push(
          `<div class="cell" data-x="${x}" data-y="${y}"${occAttr}><span class="glyph" style="background:${esc(c.bg)}${fg}">${trailHtml}${esc(c.ch)}${entHtml}</span></div>`,
        );
      }
      parts.push("</div>");
    }
    host.textContent = "";
    host.innerHTML =
      `<div class="${cls}" style="--map-cols:${String(width)}">${parts.join("")}</div>`;
    host.style.setProperty("--map-cols", String(width));
    /** @type {any} */ (host).__cellStore = { cells, width, height };
    bindCellHoverTip(host);
  }

  /**
   * @param {HTMLElement} host
   * @param {{width:number,height:number,cells:any[]}} data
   * @param {string} [_viewerSeat] Reserved for future per-seat accent
   *   styling on the viewer's OWN trail. Currently unused — trails
   *   are universal (RULEBOOK §3.12); each overlay is coloured by its
   *   own owner, not by who's viewing the map.
   */
  /** Compose the per-cell CSS class for the collision scar (§3.6
   *  v0.7.3) and inline the ``data-coll-age`` attribute so the
   *  yesterday/today distinction can be styled differently. */
  function collisionAttrs(c) {
    const cm = c?.collision;
    if (!cm) return { cls: "", attr: "" };
    const age = Number.isFinite(cm.age) ? Math.max(0, Math.min(1, cm.age)) : 0;
    return {
      cls: " cell-collision",
      attr: ` data-coll-age="${age}"`,
    };
  }

  // v0.9.14 — a damaged harvester now wears the same neutral-grey
  // "wreck" glyph as a destroyed-harvester gravestone (the player
  // disliked the old orange), but KEEPS its seat-coloured number badge
  // so you can still tell whose unit it is at a glance. Shared by the
  // static map overlay, the multi-harvester collision overlay, and the
  // orbital-lift animation cargo so the damaged look is identical
  // everywhere.
  const DAMAGED_GLYPH_CSS = "color:#d6d6de;text-shadow:0 0 3px rgba(0,0,0,0.95)";

  /** Pick a glyph for the entity overlay, honouring the v0.7.3
   *  damaged flag — a wrecked harvester renders as a struck-through
   *  ``X`` so the watcher can tell at a glance which units are
   *  awaiting pickup vs. still operational. */
  // v0.9.18 — derive the owning seat from an entity blob so we can
  // recolour its glyph from the LIVE player profile at paint time
  // rather than trusting the colour baked into the frame. Entity ids
  // are ``harvester_p1`` / ``probe_p2_3`` / ``orblift_p4`` etc.
  function ownerFromEntity(ent) {
    if (!ent) return null;
    if (typeof ent.owner === "string" && ent.owner) return ent.owner;
    const id = typeof ent.id === "string" ? ent.id : "";
    const m = id.match(/p[1-4]/i);
    return m ? m[0].toLowerCase() : null;
  }

  function entityOverlayHtml(ent) {
    if (!ent || typeof ent.ch !== "string") return "";
    const damaged = Boolean(ent.damaged);
    const ch = ent.ch === "x" ? "X" : ent.ch;
    const cls = damaged ? "entity-overlay entity-overlay--damaged" : "entity-overlay";
    // v0.8.1 — multi-asset turns are hard to read without an
    // identifier. The backend stamps each harvester and probe glyph
    // with a 1-based ``idx`` ordinal; render it as a small bordered
    // subscript tag pinned to the bottom-right of the cell (Option
    // C — chemistry-style subscript). The tag inherits the entity's
    // foreground colour so it reads as "part of this unit".
    // v0.9.2 — only harvesters keep the numbered subscript badge.
    // Probes are identical disposables so the per-probe number adds
    // noise without value (the watcher reads density / placement,
    // not which specific probe). Harvesters cap at 3 per seat and
    // are individually meaningful, so they keep the badge.
    // v0.9.18 — probe lifetime is shown as concentric square strokes
    // hugging the probe rather than a numeric badge: two rings (double
    // border) when it has the most life, one ring next, then a bare
    // probe on its final night. The precise count rides the hover
    // tooltip and the agent's map data (``nights_remaining``).
    const idx = ent.idx != null ? Number(ent.idx) : null;
    const isNumbered =
      Number.isFinite(idx) && ent.id?.startsWith("harvester");
    const nr = ent.nights_remaining;
    const isProbe = Boolean(ent.id?.startsWith("probe"));
    const badge = isNumbered
      ? `<span class="entity-overlay-sub" aria-hidden="true">${esc(String(idx))}</span>`
      : "";
    let probeRingCls = "";
    if (isProbe && nr != null && Number.isFinite(Number(nr))) {
      // rings = nights_remaining - 1, clamped to [0, 2] so coverage with
      // a long lifetime still tops out at a tidy double border.
      const rings = Math.max(0, Math.min(2, Number(nr) - 1));
      probeRingCls = ` entity-overlay--probe entity-overlay--probe-life-${rings}`;
    }
    const chHtml = damaged ? `<span style="${DAMAGED_GLYPH_CSS}">${esc(ch)}</span>` : esc(ch);
    // v0.9.18 — prefer the live profile colour (custom/random seat
    // colours) over the frame-baked ``fg`` so static board pieces match
    // the animation overlay (which uses ownerColor) and old replays
    // recolour correctly. Order: profile meta → baked fg → seat default,
    // so we never regress to a hardcoded colour while real data exists.
    const owner = ownerFromEntity(ent);
    const meta = owner && __SOC_PLAYER_META__ ? __SOC_PLAYER_META__[owner] : null;
    const col = (meta && meta.color) || ent.fg || (owner ? ownerColor(owner) : null) || "#fff";
    return `<span class="${cls}${probeRingCls}" style="color:${esc(col)}">${chHtml}${badge}</span>`;
  }

  // Corner badge class suffixes in assignment order (first harvester → br,
  // second → tl, third → tr, fourth → bl).
  const _BADGE_CORNERS = ["br", "tl", "tr", "bl"];
  let _multiHarvCycleTimer = null;

  function _tickMultiHarvCycle() {
    const els = document.querySelectorAll("[data-cycle-harv]");
    if (!els.length) {
      clearInterval(_multiHarvCycleTimer);
      _multiHarvCycleTimer = null;
      return;
    }
    for (const el of els) {
      try {
        const all = JSON.parse(el.dataset.cycleHarv);
        if (all.length < 5) continue;
        const offset = ((el._cycleOffset || 0) + 4) % all.length;
        el._cycleOffset = offset;
        const badges = el.querySelectorAll(".entity-overlay-sub");
        for (let i = 0; i < badges.length && i < 4; i++) {
          const h = all[(offset + i) % all.length];
          badges[i].textContent = h.idx != null ? String(h.idx) : "";
          badges[i].style.color = ownerColor(h.owner);
        }
      } catch (_) { /* malformed data-cycle-harv — skip */ }
    }
  }

  /** Render entity overlay HTML for a cell, handling stacked harvesters.
   *  For 2+ harvesters co-located (drop-on collision) each harvester
   *  gets its own corner badge in its seat colour; the glyph uses the
   *  grey wreck look (matching damaged units + gravestones). */
  function entityOverlaysHtml(cell) {
    // v0.9.10 — if this cell has a destroyed harvester marker, render a
    // grey "gravestone" harvester icon instead of the normal entity
    // overlay. Bright neutral grey (#d6d6de) so the wreck reads clearly
    // against the dark void cells. It stays distinct from a live unit
    // (seat colours: p1 near-white, p2 yellow, p3 magenta, p4 cyan). A
    // damaged-but-recoverable unit shares this grey wreck glyph but keeps
    // its seat-coloured number badge; a permanent gravestone has no badge.
    // A subtle dark halo keeps it legible even on lighter terrain tiles.
    if (cell.destroyed_harvester && typeof cell.destroyed_harvester === "object") {
      return '<span class="entity-overlay" style="color:#d6d6de;text-shadow:0 0 3px rgba(0,0,0,0.95)" aria-label="destroyed harvester">X</span>';
    }
    const harvesters = Array.isArray(cell.occupants)
      ? cell.occupants.filter((o) => o.type === "harvester" && o.idx != null)
      : [];
    if (harvesters.length < 2) return entityOverlayHtml(cell.entity);

    // 2–4 harvesters: fixed corner badges.
    // 5+: 4 corner badges + data-cycle-harv triggers JS rotation.
    const show = harvesters.slice(0, 4);
    let badgesHtml = "";
    for (let i = 0; i < show.length; i++) {
      const h = show[i];
      const fg = ownerColor(h.owner);
      const corner = _BADGE_CORNERS[i];
      const cls = corner === "br"
        ? "entity-overlay-sub"
        : `entity-overlay-sub entity-overlay-sub--${corner}`;
      badgesHtml += `<span class="${cls}" aria-hidden="true" style="color:${esc(fg)}">${esc(String(h.idx))}</span>`;
    }
    const cycleData = harvesters.length > 4
      ? ` data-cycle-harv="${escAttr(JSON.stringify(harvesters.map((h) => ({ idx: h.idx, owner: h.owner }))))}"` : "";
    if (harvesters.length > 4 && !_multiHarvCycleTimer) {
      _multiHarvCycleTimer = setInterval(_tickMultiHarvCycle, 1500);
    }
    return `<span class="entity-overlay entity-overlay--damaged"${cycleData} style="${DAMAGED_GLYPH_CSS}"><span style="${DAMAGED_GLYPH_CSS}">X</span>${badgesHtml}</span>`;
  }

  function paintPlayerMap(host, data, _viewerSeat) {
    const { width, height, cells } = data;    const lines = Boolean(gridlinesEl?.checked);
    const cls = lines ? "map-grid map-grid--lines" : "map-grid";
    const parts = [];
    let idx = 0;
    for (let y = 0; y < height; y++) {
      parts.push('<div class="row">');
      for (let x = 0; x < width; x++) {
        const c = cells[idx++];
        if (c.kind === "fog") {
          // v0.9.7 — RULEBOOK §3.15: probe-launch markers surface
          // as fog cells that CARRY the enemy probe occupant. The
          // terrain stays fogged but we render the probe glyph on
          // top so the watcher sees "there's a probe over there".
          // v1.1 — harvester gravestones are public landmarks: a wreck
          // marker rides on a fog cell (server surfaces it for every seat
          // regardless of exploration), so render the grey "X" over the
          // fog block just like an enemy probe-launch marker.
          const fogGrave =
            c.destroyed_harvester && typeof c.destroyed_harvester === "object";
          if (
            c.entity ||
            (Array.isArray(c.occupants) && c.occupants.length) ||
            fogGrave
          ) {
            let tt = occupantsTitle(c);
            if (!tt && fogGrave) {
              const d = c.destroyed_harvester;
              const owner = d.owner ? `[${playerTag(d.owner)}]` : "";
              const day = d.day != null ? `day ${d.day}` : "";
              const meta = [owner, day].filter(Boolean).join(" · ");
              tt = `† destroyed harvester${meta ? "  " + meta : ""}  ${d.harvester_id || "?"}`;
            }
            const occAttr = tt ? ` data-occ="${escAttr(tt)}"` : "";
            const entHtml = entityOverlaysHtml(c);
            parts.push(
              `<div class="cell cell--fog cell--fog-probe" data-x="${x}" data-y="${y}"${occAttr}><span class="glyph dim">░░${entHtml}</span></div>`,
            );
            continue;
          }
          const bsInten = _blueSignMap.get(`${x},${y}`);
          const bsSt = bsInten ? _blueSignStyles(bsInten) : null;
          const bsCellSt = bsSt ? ` style="${bsSt.cell}"` : "";
          const bsGlyphSt = bsSt ? ` style="${bsSt.glyph}"` : "";
          parts.push(
            `<div class="cell cell--fog"${bsCellSt} data-x="${x}" data-y="${y}"><span class="glyph dim"${bsGlyphSt}>░░</span></div>`,
          );
          continue;
        }
        const collInfo = collisionAttrs(c);
        const stClasses = `${c.stale ? " cell--stale" : ""}${c.echo_probe ? " cell--probe-echo" : ""}${collInfo.cls}`;
        const fg = c.fg ? `;color:${esc(c.fg)}` : "";
        const tt = occupantsTitle(c);
        const occAttr = tt ? ` data-occ="${escAttr(tt)}"` : "";
        // Trails are universal (RULEBOOK §3.12 v0.7.2): a single
        // anonymous tier glyph per cell, harvest tracks tinted green.
        // Fresh attribution surfaces through the tooltip, not colour.
        // Fog-of-war is the only gate, and it's already enforced
        // server-side (fog cells skip this branch entirely).
        const trailHtml = renderTrailOverlayHtml(c);
        const entHtml = entityOverlaysHtml(c);
        parts.push(
          `<div class="cell${stClasses}" data-x="${x}" data-y="${y}"${occAttr}${collInfo.attr}><span class="glyph glyph--terrain" style="background:${esc(c.bg)}${fg}">${trailHtml}${esc(c.ch)}${entHtml}</span></div>`,
        );
      }
      parts.push("</div>");
    }
    host.textContent = "";
    host.innerHTML =
      `<div class="${cls}" style="--map-cols:${String(width)}">${parts.join("")}</div>`;
    host.style.setProperty("--map-cols", String(width));
    /** @type {any} */ (host).__cellStore = { cells, width, height };
    bindCellHoverTip(host);
    _startFogWaveTicker();
    _applyFogWave();
  }

  /**
   * @param {HTMLElement} host
   * @param {{width:number,height:number}} dims
   * @param {any[]} playerCells
   * @param {any[]} observerCells
   */
  function paintFogOverlayMap(host, dims, playerCells, observerCells, _seat) {
    const { width, height } = dims;
    const lines = Boolean(gridlinesEl?.checked);
    const cls = lines ? "map-grid map-grid--lines" : "map-grid";
    const parts = [];
    let idx = 0;
    for (let y = 0; y < height; y++) {
      parts.push('<div class="row">');
      for (let x = 0; x < width; x++) {
        const c = playerCells[idx];
        const o = observerCells[idx];
        idx++;
        if (!c || c.kind === "fog") {
          const bg = o ? esc(o.bg) : "#1a1322";
          const fg = o && o.fg ? `;color:${esc(o.fg)}` : "";
          const ch = o ? esc(o.ch) : "░░";
          // v0.9.7 — probe-launch markers (RULEBOOK §3.15) render as
          // fog with an enemy probe glyph on top. The observer layer
          // (live truth) wins for the background paint but we still
          // show the probe-launch occupant overlay on the player's
          // dim layer so the tooltip explains the glyph.
          if (c && (c.entity || (Array.isArray(c.occupants) && c.occupants.length))) {
            const tt = occupantsTitle(c);
            const occAttr = tt ? ` data-occ="${escAttr(tt)}"` : "";
            const entHtml = entityOverlaysHtml(c);
            parts.push(
              `<div class="cell cell--fog cell--fog-dim cell--fog-probe" data-x="${x}" data-y="${y}"${occAttr}><span class="glyph" style="background:${bg}${fg}">${ch}${entHtml}</span></div>`,
            );
            continue;
          }
          const bsInten2 = _blueSignMap.get(`${x},${y}`);
          const bsSt2 = bsInten2 ? _blueSignStyles(bsInten2) : null;
          const bsFg2 = bsSt2 ? `;${bsSt2.glyph}` : "";
          parts.push(
            `<div class="cell cell--fog cell--fog-dim" data-x="${x}" data-y="${y}"><span class="glyph" style="background:${bg}${fg}${bsFg2}">${ch}</span></div>`,
          );
          continue;
        }
        const collInfo = collisionAttrs(c);
        const stClasses = `${c.stale ? " cell--stale" : ""}${c.echo_probe ? " cell--probe-echo" : ""}${collInfo.cls}`;
        const fg = c.fg ? `;color:${esc(c.fg)}` : "";
        const tt = occupantsTitle(c);
        const occAttr = tt ? ` data-occ="${escAttr(tt)}"` : "";
        const trailHtml = renderTrailOverlayHtml(c);
        const entHtml = entityOverlaysHtml(c);
        parts.push(
          `<div class="cell${stClasses}" data-x="${x}" data-y="${y}"${occAttr}${collInfo.attr}><span class="glyph glyph--terrain" style="background:${esc(c.bg)}${fg}">${trailHtml}${esc(c.ch)}${entHtml}</span></div>`,
        );
      }
      parts.push("</div>");
    }
    host.textContent = "";
    host.innerHTML =
      `<div class="${cls}" style="--map-cols:${String(width)}">${parts.join("")}</div>`;
    host.style.setProperty("--map-cols", String(width));
    /** @type {any} */ (host).__cellStore = { cells: playerCells, obsCells: observerCells, width, height };
    bindCellHoverTip(host);
  }

  /** Observer map — full cells with both seats' trail overlays. */
  function paintObsVisionMap(host, dims, obsCells, ...seatCellArrays) {
    const { width, height } = dims;
    const lines = Boolean(gridlinesEl?.checked);
    const cls = lines ? "map-grid map-grid--lines" : "map-grid";
    const parts = [];

    // v0.9.9 — N-seat fog dim. A cell is considered "seen" by the
    // collective observer iff at least ONE of the active seats has
    // it as non-fog in this frame. The pre-v0.9.9 signature only
    // accepted (p1Cells, p2Cells) so 3/4-seat games dimmed cells
    // that p3 or p4 could actually see.
    const seatLists = seatCellArrays.filter(
      (lst) => Array.isArray(lst) && lst.length,
    );

    let idx = 0;
    for (let y = 0; y < height; y++) {
      parts.push('<div class="row">');
      for (let x = 0; x < width; x++) {
        const c = obsCells[idx];
        let seen = false;
        for (const lst of seatLists) {
          const pc = lst[idx];
          if (pc && pc.kind !== "fog") { seen = true; break; }
        }
        idx++;
        const dimAttr = seen ? "" : ' data-obs-dim="1"';
        const collInfo = collisionAttrs(c);
        const fg = c.fg ? `;color:${esc(c.fg)}` : "";
        let tt = occupantsTitle(c);
        // v1.9 — graves were invisible in OBS: this path drew only the live
        // ``c.entity`` (entityOverlayHtml) and never checked
        // ``c.destroyed_harvester``, unlike the per-seat/live renderer
        // (paintPlayerMap → entityOverlaysHtml). Use the same overlay builder
        // so permanent harvester wrecks (and stacked-harvester badges) show
        // for the omniscient watcher too. Server already stamps the marker on
        // every obs cell, so no data change is needed.
        if (!tt && c.destroyed_harvester && typeof c.destroyed_harvester === "object") {
          const d = c.destroyed_harvester;
          const owner = d.owner ? `[${playerTag(d.owner)}]` : "";
          const day = d.day != null ? `day ${d.day}` : "";
          const meta = [owner, day].filter(Boolean).join(" · ");
          tt = `† destroyed harvester${meta ? "  " + meta : ""}  ${d.harvester_id || "?"}`;
        }
        const occAttr = tt ? ` data-occ="${escAttr(tt)}"` : "";
        const entHtml = entityOverlaysHtml(c);
        const trailHtml = renderTrailOverlayHtml(c);
        parts.push(
          `<div class="cell${collInfo.cls}" data-x="${x}" data-y="${y}"${occAttr}${dimAttr}${collInfo.attr}><span class="glyph" style="background:${esc(c.bg)}${fg}">${trailHtml}${esc(c.ch)}${entHtml}</span></div>`,
        );
      }
      parts.push("</div>");
    }
    host.textContent = "";
    host.innerHTML =
      `<div class="${cls}" style="--map-cols:${String(width)}">${parts.join("")}</div>`;
    host.style.setProperty("--map-cols", String(width));
    /** @type {any} */ (host).__cellStore = { cells: obsCells, width, height };
    bindCellHoverTip(host);
  }

  function fmtUnits(rows) {
    return rows
      .map((r) => {
        if (r.label) return r.label.replace(/\s+/g, " ").trim();
        return `${r.id}${r.orbit ? " orbit" : ` @${JSON.stringify(r.pos)}`}${r.carrying_red ? " cargo:R" : ""}`;
      })
      .join("\n");
  }

  /** @param {any} inv */
  function fmtInventory(inv) {
    if (!inv || typeof inv !== "object") return "";
    /** @type {string[]} */
    const lines = [];
    const cap = Number(inv.hoard_capacity) || HOARD_CAP_FALLBACK;
    const hoard = Array.isArray(inv.hoard) ? inv.hoard : [];
    lines.push(`# hoard (orbital vault) · ${String(hoard.length)}/${String(cap)}`);

    hoard.slice(-32).forEach((row, i) => {
      const sid = row.site_id ?? "?";
      const cx = row.x;
      const cy = row.y;
      const tail = hoard.length <= 32 ? i + 1 : hoard.length - 32 + i + 1;
      lines.push(`${tail}. ${String(sid)} @(${String(cx)},${String(cy)})`);
    });
    if (!hoard.length) lines.push("(empty — pickups bank squares here)");

    lines.push("", "# asset roster");
    const assets = Array.isArray(inv.assets) ? inv.assets : [];
    if (!assets.length) lines.push("(none)");
    else {
      for (const a of assets) {
        lines.push(a.label || a.id || "?");
      }
    }

    lines.push("", "# surface harvest journal");
    const fieldLog = Array.isArray(inv.field_harvest_journal)
      ? inv.field_harvest_journal
      : [];
    if (!fieldLog.length) {
      lines.push("(no red converted this session yet)");
      return lines.join("\n");
    }
    fieldLog.slice(-24).forEach((row, i) => {
      const hid = row.harvester_id || "?";
      const sid = row.site_id ?? "—";
      lines.push(`${i + 1}. (${String(row.x)},${String(row.y)}) · ${String(sid)} · ${hid}`);
    });

    lines.push("", "# orbital lifter cue (compat)");
    lines.push(`orbital_cargo_legacy_flag: ${inv.orbital_holds_red ? "yes" : "no"}`);
    return lines.join("\n");
  }

  /**
   * Render a fixed-size storage grid into ``host`` (the VAULT or
   * SHIPPED panel). The grid is **packed** — zero gap, every slot is
   * just the canonical tile glyph filling its square, with the slot
   * number rendered as a small label *on top of* the glyph. All
   * metadata (coord, full hash, harvest night, purity) lives on
   * ``data-*`` attributes and is surfaced through a custom tooltip on
   * hover (see :func:`bindStorageTooltip`).
   *
   * @param {HTMLElement | null} host
   * @param {any[]} parcels
   * @param {number} cap
   */
  /**
   * v0.9.6 — Derive a paint dict (bg / fg / ch) from a parcel's
   * ``tile_at_harvest`` + ``purity_at_harvest`` when the server-side
   * ``paint`` field is missing or stale.
   *
   * Background: refined parcels minted before v0.9.6 did not stamp
   * a fresh paint on the new tier, so the VAULT slot fell back to
   * the trace-tier ░░ default even when the parcel was a vein or
   * mass output. The engine has been fixed to stamp paint on every
   * new refined parcel (see :py:meth:`apply_refine`); this helper
   * lets the frontend recover the correct visual for parcels still
   * persisted under the old shape, so a user doesn't have to
   * re-refine just to see the right glyph.
   *
   * Mirrors :py:func:`sea_of_colours.render.cell_visual`:
   *   - trace (1-50)   → ░░ (light shade)
   *   - vein  (51-150) → ▒▒ (medium shade)
   *   - mass  (151-254)→ ▓▓ (heavy shade)
   *   - pure  (255)    → ██ (solid, painted in tile fg colour)
   *
   * @param {number} tile  Tile enum value (0 empty, 1 green, 2 red, 3 blue)
   * @param {number} purity 0..255 purity
   * @returns {{bg: string, fg: string, ch: string} | null}
   */
  function computeParcelPaintFallback(tile, purity) {
    const t = Number.isFinite(tile) ? Number(tile) : -1;
    const p = Math.max(0, Math.min(255, Number.isFinite(purity) ? Number(purity) : 0));
    if (t !== 1 && t !== 2 && t !== 3) return null;
    const VOID = "rgb(14,11,22)";
    if (t === 1) {
      // GREEN — binary (always 255 by invariant). Solid green block.
      return { bg: VOID, fg: "rgb(63,185,80)", ch: "\u2588\u2588" };
    }
    // RED + BLUE share the same tier ramp; only the fg/bg colour differs.
    const fg = t === 2 ? "rgb(255,0,0)" : "rgb(59,143,224)";
    // Tier mapping mirrors RED_LEVEL_CUTOFFS = (0, 51, 151, 255).
    if (p >= 255) {
      return { bg: VOID, fg, ch: "\u2588\u2588" };
    }
    if (p >= 151) {
      return { bg: VOID, fg, ch: "\u2593\u2593" };
    }
    if (p >= 51) {
      return { bg: VOID, fg, ch: "\u2592\u2592" };
    }
    if (p >= 1) {
      return { bg: VOID, fg, ch: "\u2591\u2591" };
    }
    return null;
  }

  /** v0.9.14 — the canonical purity-tier glyph used by the VAULT / hoard
   *  parcels (double-width block whose density reads the tier at a
   *  glance): ██ pure, ▓▓ mass, ▒▒ vein, ░░ trace. Tier cutoffs mirror
   *  ``computeParcelPaintFallback`` (RED_LEVEL_CUTOFFS). Catapult slots
   *  (submit preview + orbital briefing) reuse this so a shipped parcel
   *  shows the SAME glyph as it did in the hoard, alongside its purity. */
  function catTierGlyph(purity) {
    const p = Math.max(0, Math.min(255, Number(purity) || 0));
    if (p >= 255) return "\u2588\u2588"; // ██ pure
    if (p >= 151) return "\u2593\u2593"; // ▓▓ mass
    if (p >= 51) return "\u2592\u2592";  // ▒▒ vein
    if (p >= 1) return "\u2591\u2591";   // ░░ trace
    return "\u2591\u2591";               // ░░ purity 0 reads as lowest (was ██)
  }

  function renderStorageGrid(host, parcels, cap, opts) {
    if (!host) return;
    // v0.9.11 — ``ownerBorders`` draws a seat-coloured frame around each
    // filled slot and stamps ``data-owner`` (used by the SHIPPED pane in
    // replay, which aggregates every player's bay into one grid). The
    // VAULT hoard grid leaves it off — it's always a single seat.
    const ownerBorders = !!(opts && opts.ownerBorders);

    /** @type {string[]} */
    const parts = [];
    for (let i = 0; i < cap; i++) {
      const slot = i + 1;
      const slotLabel = String(slot).padStart(2, "0");
      const row = parcels[i];
      if (!row) {
        parts.push(
          `<div class="cc-vault-slot cc-vault-slot--empty" aria-label="slot ${slotLabel} empty">` +
            `<span class="cc-vault-slot-num">${slotLabel}</span>` +
          `</div>`,
        );
        continue;
      }
      let paint =
        row && row.paint && typeof row.paint === "object" ? row.paint : null;
      // v0.9.6 — if the server payload is missing a ``paint`` (legacy
      // refined parcel from before the engine started stamping fresh
      // paint per refine), derive it from tile_at_harvest +
      // purity_at_harvest. This keeps the vault truthful for older
      // hoard entries without requiring a one-time migration.
      if (!paint || typeof paint.ch !== "string") {
        const tileGuess =
          row?.tile_at_harvest ?? row?.origin_tile ?? null;
        const purityGuess =
          row?.purity_at_harvest ??
          row?.origin_purity ??
          row?.purity ??
          null;
        const derived = computeParcelPaintFallback(
          Number(tileGuess), Number(purityGuess),
        );
        if (derived) paint = derived;
      }
      let bg = paint && paint.bg ? String(paint.bg) : "#1a1322";
      let fg = paint && paint.fg ? String(paint.fg) : "#d14a4a";
      let ch = paint && typeof paint.ch === "string" ? paint.ch : "░░";
      // v0.9.5 — the engine paints the top tier (RED pure / BLUE
      // deep / GREEN) as a SOLID colour with whitespace glyph
      // (``ch = "  "``) so the terminal ANSI renderer shows a flat
      // block. The vault slots look inconsistent next to the
      // lower tiers (which draw a colored block glyph on a dark
      // void background), so we normalise: detect a whitespace
      // glyph and swap to the densest block ``██`` with the
      // saturated colour as foreground over the void background.
      // This keeps every tile in the vault rendered with the
      // same "glyph-on-void" template that the other tiers use.
      const _trimmedCh = ch.replace(/\s+/g, "");
      if (_trimmedCh === "" && bg) {
        fg = bg;
        bg = "rgb(14,11,22)";
        ch = "\u2588\u2588";
      }
      const sid = String(row.square_id || row.site_id || "—");
      // v0.9.9 — refined parcels carry the seed coords on
      // ``origin_x`` / ``origin_y`` and the day stamp on
      // ``harvested_day`` rather than ``x`` / ``y`` /
      // ``harvested_on_planning_day``. Fall back through both shapes so
      // the tooltip reads the right tile / night for both raw harvests
      // and refined parcels (§3.x refine produces a fresh sid + paint
      // but keeps the origin tile coords as provenance).
      const day =
        row.harvested_on_planning_day
        ?? row.stored_received_planning_day
        ?? row.harvested_day
        ?? "?";
      const purity = row.purity_at_harvest ?? row.origin_purity;
      const cx = row.x ?? row.origin_x ?? "?";
      const cy = row.y ?? row.origin_y ?? "?";
      const purityAttr =
        typeof purity === "number" ? ` data-purity="${escAttr(String(purity))}"` : "";
      // v0.9.6 — stamp the tile colour so the tooltip can decide
      // whether to render the RED-only score line.
      const tileCode = Number(
        row?.tile_at_harvest ?? row?.origin_tile ?? -1,
      );
      const tileTagAttr =
        tileCode === 2
          ? ' data-tile-tag="red"'
          : tileCode === 1
            ? ' data-tile-tag="green"'
            : tileCode === 3
              ? ' data-tile-tag="blue"'
              : "";
      const owner = ownerBorders && row && row.owner ? String(row.owner) : "";
      const ownerAttr = owner ? ` data-owner="${escAttr(owner)}"` : "";
      const ownerStyle = owner
        ? `;border:1.5px solid ${esc(ownerColor(owner))};box-shadow:inset 0 0 0 1px ${esc(ownerColor(owner))}`
        : "";
      // v0.9.x — shipped-record detail (public ledger): effective
      // purity, transit tax, yielded score, score tier, and refine
      // lineage. Only present on catapult-shipped rows.
      const shippedAttr =
        row && row.catapult_shipped ? ' data-shipped="1"' : "";
      const effAttr =
        typeof row.effective_purity === "number"
          ? ` data-eff="${escAttr(String(row.effective_purity))}"`
          : "";
      const taxAttr =
        typeof row.transit_charge === "number"
          ? ` data-tax="${escAttr(String(row.transit_charge))}"`
          : "";
      const scoreAttr =
        typeof row.score === "number"
          ? ` data-score="${escAttr(String(row.score))}"`
          : "";
      const scoreTierAttr = row.score_tier
        ? ` data-score-tier="${escAttr(String(row.score_tier))}"`
        : "";
      const refinedFrom = Array.isArray(row.refined_from)
        ? row.refined_from.filter(Boolean).map(String)
        : [];
      const refinedFromAttr = refinedFrom.length
        ? ` data-refined-from="${escAttr(refinedFrom.join(","))}"`
        : "";
      // v1.x — optimistic pending-refine preview: a queued (uncommitted)
      // refine output. White-bordered + tagged "pending"; display-only.
      const isPending = !!(row && row._pending);
      const pendingAttr = isPending
        ? ` data-pending="1" data-pending-tier="${escAttr(String(row._pendingTier || ""))}"`
        : "";
      const pendingStyle = isPending
        ? ";border:1.5px dashed #ffffff;box-shadow:inset 0 0 0 1px rgba(255,255,255,0.85)"
        : "";
      parts.push(
        `<div class="cc-vault-slot cc-vault-slot--filled${isPending ? " cc-vault-slot--pending" : ""}"` +
          ` data-slot="${escAttr(slotLabel)}"` +
          ` data-x="${escAttr(String(cx))}"` +
          ` data-y="${escAttr(String(cy))}"` +
          ` data-sid="${escAttr(sid)}"` +
          ` data-day="${escAttr(String(day))}"` +
          ownerAttr +
          purityAttr +
          tileTagAttr +
          shippedAttr +
          effAttr +
          taxAttr +
          scoreAttr +
          scoreTierAttr +
          refinedFromAttr +
          pendingAttr +
          ` style="background:${esc(bg)};color:${esc(fg)}${ownerStyle}${pendingStyle}">` +
          `<span class="cc-vault-tile">${esc(ch)}</span>` +
          `<span class="cc-vault-slot-num">${slotLabel}</span>` +
          (isPending ? `<span class="cc-vault-slot-pending-tag">pending</span>` : "") +
        `</div>`,
      );
    }
    host.innerHTML = parts.join("");
    bindStorageTooltip(host);
  }

  /* ── Custom vault tooltip ──────────────────────────────────────────
   * The native ``title`` attribute has a ~500 ms browser delay and is
   * styled by the OS. We replace it with a single body-mounted
   * tooltip that surfaces #slot · (x,y), the full square hash, and
   * the harvest night on a black background — matching the spec the
   * user sketched. It follows the cursor and appears instantly.
   */

  function ensureStorageTooltip() {
    let tip = document.getElementById("cc-vault-tooltip");
    if (tip) return tip;
    tip = document.createElement("div");
    tip.id = "cc-vault-tooltip";
    tip.className = "cc-vault-tooltip";
    tip.hidden = true;
    document.body.appendChild(tip);
    return tip;
  }

  /**
   * @param {HTMLElement} tip
   * @param {HTMLElement} slot
   */
  function fillStorageTooltip(tip, slot) {
    const num = slot.getAttribute("data-slot") || "?";
    const cx = slot.getAttribute("data-x") || "?";
    const cy = slot.getAttribute("data-y") || "?";
    const sid = slot.getAttribute("data-sid") || "—";
    const day = slot.getAttribute("data-day") || "?";
    const purity = slot.getAttribute("data-purity");
    const tileTag = slot.getAttribute("data-tile-tag") || "";
    // v1.x — pending refine output (queued, not committed). Show a compact
    // "pending" card instead of harvest coords/hash it doesn't have.
    if (slot.getAttribute("data-pending") === "1") {
      const ptier = slot.getAttribute("data-pending-tier") || "";
      tip.innerHTML =
        `<div class="cc-vault-tooltip-row cc-vault-tooltip-row--coord">#${esc(num)} · pending refine</div>` +
        (ptier
          ? `<div class="cc-vault-tooltip-row cc-vault-tooltip-row--meta">→ ${esc(ptier)}${purity != null ? ` · ${esc(purity)}p` : ""}</div>`
          : "") +
        `<div class="cc-vault-tooltip-row cc-vault-tooltip-row--meta">mints on commit — can't ship / re-refine this turn</div>`;
      return;
    }
    let purityRow = "";
    let scoreRow = "";
    if (purity != null) {
      const purityN = Number(purity);
      if (tileTag === "red" && Number.isFinite(purityN)) {
        // v0.9.6 — tier-multiplier scoring readout (RULEBOOK §3.1).
        // ``score = raw_purity \u00d7 MULT[tier]``. Multipliers live in
        // ``window.__SOC_QUALITY_MULT__`` (stashed from the agent
        // view); the default mirrors session.py if the table isn't
        // available (e.g. the user opened the tooltip before the
        // first /view fetch landed).
        const tier = redTierName(purityN);
        const mults =
          (window.__SOC_QUALITY_MULT__ &&
            typeof window.__SOC_QUALITY_MULT__ === "object" &&
            window.__SOC_QUALITY_MULT__) ||
          { trace: 0.75, vein: 1.0, mass: 1.5, pure: 3.0 };
        const mult = Number(mults[tier]) || 1.0;
        const score = Math.round(purityN * mult);
        purityRow =
          `<div class="cc-vault-tooltip-row cc-vault-tooltip-row--meta">` +
          `purity ${esc(purity)} \u00B7 ${esc(tier)} (\u00D7${mult})` +
          `</div>`;
        scoreRow =
          `<div class="cc-vault-tooltip-row cc-vault-tooltip-row--meta">` +
          `score if shipped: ${esc(String(score))}` +
          `</div>`;
      } else {
        purityRow =
          `<div class="cc-vault-tooltip-row cc-vault-tooltip-row--meta">` +
          `purity ${esc(purity)}` +
          `</div>`;
      }
    }
    // v0.9.11 — owner line for the all-players SHIPPED pane (replay).
    const owner = slot.getAttribute("data-owner") || "";
    const ownerRow = owner
      ? `<div class="cc-vault-tooltip-row cc-vault-tooltip-row--meta" style="color:${esc(ownerColor(owner))}">shipped by ${esc(playerDisplayName(owner))}</div>`
      : "";

    // v0.9.x — SHIPPED public ledger detail. A catapult-shipped parcel
    // (``data-shipped``) carries its full economics: effective purity
    // (post-transit), the transit TAX it paid, the SCORE it yielded, the
    // scoring tier, and — if refined — the parcel codes it was refined
    // from. Everything is public (shipping is a public act).
    const isShipped = slot.getAttribute("data-shipped") === "1";
    if (isShipped) {
      const eff = slot.getAttribute("data-eff");
      const tax = slot.getAttribute("data-tax");
      const score = slot.getAttribute("data-score");
      const sTier = slot.getAttribute("data-score-tier") || "";
      const refinedFrom = slot.getAttribute("data-refined-from") || "";
      const rows = [];
      // v1.0 — surface the tier multiplier from the canonical RED table
      // (same one the "score if shipped" preview uses) so the shipped
      // ledger shows purity · tier (×mult).
      const shipMults =
        (window.__SOC_QUALITY_MULT__ &&
          typeof window.__SOC_QUALITY_MULT__ === "object" &&
          window.__SOC_QUALITY_MULT__) ||
        { trace: 0.75, vein: 1.0, mass: 1.5, pure: 3.0 };
      const shipMult = sTier ? Number(shipMults[sTier]) : NaN;
      const multTxt = Number.isFinite(shipMult) ? ` (\u00D7${shipMult})` : "";
      // purity: effective, with raw original in parens when they differ.
      if (eff != null) {
        const rawTxt =
          purity != null && Number(purity) !== Number(eff)
            ? ` (raw ${esc(purity)})`
            : "";
        const tierTxt = sTier ? ` \u00B7 ${esc(sTier)}${multTxt}` : "";
        rows.push(
          `<div class="cc-vault-tooltip-row cc-vault-tooltip-row--meta">purity ${esc(eff)}${rawTxt}${tierTxt}</div>`,
        );
      } else if (purity != null) {
        rows.push(
          `<div class="cc-vault-tooltip-row cc-vault-tooltip-row--meta">purity ${esc(purity)}</div>`,
        );
      }
      if (tax != null) {
        rows.push(
          `<div class="cc-vault-tooltip-row cc-vault-tooltip-row--meta">shipping paid: ${esc(tax)}</div>`,
        );
      }
      if (score != null) {
        rows.push(
          `<div class="cc-vault-tooltip-row cc-vault-tooltip-row--meta">score yielded: ${esc(String(Math.round(Number(score))))}</div>`,
        );
      }
      if (refinedFrom) {
        const ids = refinedFrom.split(",").filter(Boolean);
        rows.push(
          `<div class="cc-vault-tooltip-row cc-vault-tooltip-row--meta">refined from ${ids.length} parcel(s):</div>` +
          ids
            .map(
              (id) =>
                `<div class="cc-vault-tooltip-row cc-vault-tooltip-row--hash">${esc(id)}</div>`,
            )
            .join(""),
        );
      }
      tip.innerHTML =
        `<div class="cc-vault-tooltip-row cc-vault-tooltip-row--coord">#${esc(num)} · (${esc(cx)},${esc(cy)})</div>` +
        `<div class="cc-vault-tooltip-row cc-vault-tooltip-row--hash">${esc(sid)}</div>` +
        ownerRow +
        `<div class="cc-vault-tooltip-row cc-vault-tooltip-row--meta">harvest Nox ${esc(day)}</div>` +
        rows.join("");
      return;
    }

    tip.innerHTML =
      `<div class="cc-vault-tooltip-row cc-vault-tooltip-row--coord">#${esc(num)} · (${esc(cx)},${esc(cy)})</div>` +
      `<div class="cc-vault-tooltip-row cc-vault-tooltip-row--hash">${esc(sid)}</div>` +
      ownerRow +
      `<div class="cc-vault-tooltip-row cc-vault-tooltip-row--meta">harvest Nox ${esc(day)}</div>` +
      purityRow +
      scoreRow;
  }

  /** v0.9.6 — discrete RED tier name from raw purity. Mirrors
   *  ``sea_of_colours.render.RED_LEVEL_NAMES`` (trace / vein / mass
   *  / pure) so the JS tooltip and the Python ``score_for`` agree. */
  function redTierName(purity) {
    const p = Math.max(0, Math.min(255, Number(purity) || 0));
    if (p <= 50) return "trace";
    if (p <= 150) return "vein";
    if (p <= 254) return "mass";
    return "pure";
  }

  /**
   * @param {HTMLElement} tip
   * @param {number} mx
   * @param {number} my
   */
  function positionStorageTooltip(tip, mx, my) {
    // Measure after content/visibility are set so layout has settled.
    const rect = tip.getBoundingClientRect();
    const margin = 14;
    let x = mx + margin;
    let y = my + margin;
    if (x + rect.width > window.innerWidth - 4) {
      x = mx - margin - rect.width;
    }
    if (y + rect.height > window.innerHeight - 4) {
      y = my - margin - rect.height;
    }
    if (x < 4) x = 4;
    if (y < 4) y = 4;
    tip.style.left = `${String(x)}px`;
    tip.style.top = `${String(y)}px`;
  }

  /**
   * Tooltip variant for the asset chips in the VAULT sub-sections.
   * Surfaces the full lifecycle stats (first deployed, days deployed,
   * red harvested, etc.) on hover with no browser delay.
   * @param {HTMLElement} tip
   * @param {HTMLElement} chip
   */
  function fillAssetTooltip(tip, chip) {
    /** @param {string} k */
    const at = (k) => chip.getAttribute(k);
    const id = at("data-asset-id") || "?";
    const kind = at("data-asset-type") || "?";
    const owner = at("data-owner") || "?";
    const bucket = at("data-bucket") || "";
    const created = at("data-created");
    const firstDep = at("data-first-deployed");
    const destroyed = at("data-destroyed");
    const destroyedBy = at("data-destroyed-by") || "";
    const totalRed = at("data-total-red") || "0";
    const daysSurfaced = at("data-days-surfaced") || "0";
    const posX = at("data-pos-x");
    const posY = at("data-pos-y");
    const cargo = at("data-cargo");
    const holdsRed = at("data-holds-red") === "1";
    // v0.9.5 — damaged + repair lifecycle bits the chip carries so
    // we can render the wrench state and "repaired N×" rows.
    const damaged = at("data-damaged") === "1";
    const repairCount = parseInt(at("data-repair-count") || "0", 10);
    const lastRepaired = at("data-last-repaired");
    const carryingRed = at("data-carrying-red") === "1";

    /** @param {string | null} val */
    const _daysSince = (val) => {
      if (val == null || val === "" || __currentGameDay == null) return null;
      const n = Number(val);
      if (!Number.isFinite(n)) return null;
      return Math.max(0, Number(__currentGameDay) - n);
    };

    const kindLabel =
      kind === "harvester" ? "Harvester"
      : kind === "orblift" ? "Orbital lifter"
      : kind === "probe" ? "Probe"
      : kind;
    const statusLabel =
      bucket === "destroyed" ? "destroyed"
      : bucket === "on_surface" ? "on surface"
      : bucket === "in_orbit" ? "in orbit"
      : "—";

    // v0.9.5 — header line + a state line that surfaces the wrench
    // / red-hold flags up front so the hover answers "what's wrong
    // with this unit?" in the first read. Pre-v0.9.5 a damaged
    // harvester looked identical to a healthy one until the user
    // dug into the chip class.
    const stateBits = [];
    if (kind === "harvester") {
      if (damaged) stateBits.push("DAMAGED");
      if (carryingRed) stateBits.push("hauling RED");
    }
    if (kind === "orblift" && holdsRed) stateBits.push("RED hold");
    const stateLabel = stateBits.length ? stateBits.join(" · ") : "ok";

    const rows = [
      `<div class="cc-vault-tooltip-row cc-vault-tooltip-row--coord">${esc(
        kindLabel,
      )} · ${esc(owner)}</div>`,
      `<div class="cc-vault-tooltip-row cc-vault-tooltip-row--hash">${esc(id)}</div>`,
      `<div class="cc-vault-tooltip-row cc-vault-tooltip-row--meta">status · ${esc(statusLabel)}${
        stateBits.length ? ` · <span class="${damaged ? "cc-vault-tooltip-pill--warn" : "cc-vault-tooltip-pill--ok"}">${esc(stateLabel)}</span>` : ""
      }</div>`,
    ];
    if (posX != null && posX !== "" && posY != null && posY !== "") {
      rows.push(
        `<div class="cc-vault-tooltip-row cc-vault-tooltip-row--meta">tile · (${esc(posX)},${esc(posY)})</div>`,
      );
    }
    // v0.9.5 — "created" + relative age ("· N days alive"). For
    // probes especially the user asked for "how many days?". The
    // relative tail is suppressed when ``__currentGameDay`` is
    // null (between status refreshes).
    const ageAlive = _daysSince(created);
    rows.push(
      `<div class="cc-vault-tooltip-row cc-vault-tooltip-row--meta">created · day ${esc(
        created || "?",
      )}${ageAlive != null && bucket !== "destroyed" ? ` · ${esc(String(ageAlive))} days alive` : ""}</div>`,
    );
    rows.push(
      `<div class="cc-vault-tooltip-row cc-vault-tooltip-row--meta">first deployed · ${esc(
        firstDep || "—",
      )}${firstDep && _daysSince(firstDep) != null && bucket !== "destroyed"
        ? ` · ${esc(String(_daysSince(firstDep)))} days ago`
        : ""}</div>`,
    );
    rows.push(
      `<div class="cc-vault-tooltip-row cc-vault-tooltip-row--meta">days on surface · ${esc(
        daysSurfaced,
      )}</div>`,
    );
    if (kind === "harvester") {
      rows.push(
        `<div class="cc-vault-tooltip-row cc-vault-tooltip-row--meta">red harvested (total) · ${esc(
          totalRed,
        )}</div>`,
      );
      if (cargo != null && cargo !== "") {
        rows.push(
          `<div class="cc-vault-tooltip-row cc-vault-tooltip-row--meta">cargo (now) · ${esc(
            cargo,
          )}</div>`,
        );
      }
      // v0.9.5 — repair history. ``repair_count`` rides on every
      // chip post-v0.9.5; older sessions deserialise as 0 so the
      // row is suppressed entirely. ``last_repaired_day`` is the
      // engine day stamp, surfaced with its relative age too.
      if (repairCount > 0) {
        const lastTail =
          lastRepaired && _daysSince(lastRepaired) != null
            ? ` · last day ${esc(lastRepaired)} (${esc(
                String(_daysSince(lastRepaired)),
              )} days ago)`
            : lastRepaired
              ? ` · last day ${esc(lastRepaired)}`
              : "";
        rows.push(
          `<div class="cc-vault-tooltip-row cc-vault-tooltip-row--meta">repaired · ${esc(
            String(repairCount),
          )}\u00D7${lastTail}</div>`,
        );
      }
    }
    if (kind === "orblift" && holdsRed) {
      rows.push(
        `<div class="cc-vault-tooltip-row cc-vault-tooltip-row--meta">orbital hold · Red</div>`,
      );
    }
    if (destroyed) {
      rows.push(
        `<div class="cc-vault-tooltip-row cc-vault-tooltip-row--destroyed">destroyed · day ${esc(
          destroyed,
        )}${destroyedBy ? ` · ${esc(destroyedBy)}` : ""}</div>`,
      );
    }
    tip.innerHTML = rows.join("");
  }

  /** @param {HTMLElement | null} host */
  function bindAssetTooltip(host) {
    if (!host) return;
    if (host.dataset.assetTipBound === "1") return;
    host.dataset.assetTipBound = "1";
    const tip = ensureStorageTooltip();
    host.addEventListener("mouseover", (ev) => {
      const target = /** @type {HTMLElement | null} */ (ev.target);
      const chip = target ? target.closest(".cc-asset-chip") : null;
      if (!chip) return;
      fillAssetTooltip(tip, /** @type {HTMLElement} */ (chip));
      tip.hidden = false;
      positionStorageTooltip(tip, ev.clientX, ev.clientY);
    });
    host.addEventListener("mousemove", (ev) => {
      if (tip.hidden) return;
      positionStorageTooltip(tip, ev.clientX, ev.clientY);
    });
    host.addEventListener("mouseout", (ev) => {
      const target = /** @type {HTMLElement | null} */ (ev.target);
      const fromChip = target ? target.closest(".cc-asset-chip") : null;
      const next = /** @type {HTMLElement | null} */ (ev.relatedTarget);
      const toChip = next && next.closest ? next.closest(".cc-asset-chip") : null;
      if (fromChip && toChip === fromChip) return;
      tip.hidden = true;
    });
    host.addEventListener("mouseleave", () => {
      tip.hidden = true;
    });
  }

  /** @param {HTMLElement | null} host */
  function bindStorageTooltip(host) {
    if (!host) return;
    if (host.dataset.vaultTipBound === "1") return;
    host.dataset.vaultTipBound = "1";
    const tip = ensureStorageTooltip();
    host.addEventListener("mouseover", (ev) => {
      const target = /** @type {HTMLElement | null} */ (ev.target);
      const slot = target ? target.closest(".cc-vault-slot--filled") : null;
      if (!slot) return;
      fillStorageTooltip(tip, /** @type {HTMLElement} */ (slot));
      tip.hidden = false;
      positionStorageTooltip(tip, ev.clientX, ev.clientY);
    });
    host.addEventListener("mousemove", (ev) => {
      if (tip.hidden) return;
      positionStorageTooltip(tip, ev.clientX, ev.clientY);
    });
    host.addEventListener("mouseout", (ev) => {
      const target = /** @type {HTMLElement | null} */ (ev.target);
      const fromSlot = target ? target.closest(".cc-vault-slot--filled") : null;
      const next = /** @type {HTMLElement | null} */ (ev.relatedTarget);
      const toSlot = next && next.closest ? next.closest(".cc-vault-slot--filled") : null;
      if (fromSlot && toSlot === fromSlot) return;
      tip.hidden = true;
    });
    host.addEventListener("mouseleave", () => {
      tip.hidden = true;
    });
  }

  /**
   * Paint both the VAULT (banked-on-planet hoard) and SHIPPED
   * (catapulted-to-orbit storage, placeholder for §4 mechanics) plus
   * the three asset sections (in-orbit / on-surface / destroyed)
   * that sit below the vault mosaic.
   * @param {any} inv
   */
  function _parcelIdOf(p) {
    return String((p && (p.square_id || p.site_id)) || "");
  }

  /**
   * @param {any} inv
   * @param {any[] | null} [shippedOverride] — when provided (replay
   *   mode), the SHIPPED grid renders THIS list — every player's bay
   *   aggregated, owner-tagged for seat-coloured borders — rather than
   *   the single-seat ``inv.shipped``. The hoard grid stays per-seat.
   */
  function renderVault(inv, shippedOverride) {
    const hoard = inv && Array.isArray(inv.hoard) ? inv.hoard : [];
    const cap = Number(inv && inv.hoard_capacity) || HOARD_CAP_FALLBACK;
    const allPlayersShipped = Array.isArray(shippedOverride);
    const shipped = allPlayersShipped
      ? shippedOverride
      : (inv && Array.isArray(inv.shipped) ? inv.shipped : []);
    // v0.9.x — SHIPPED is an uncapped PUBLIC record. Grow the grid to
    // exactly the number of parcels (no capacity padding); the panel
    // scrolls. A minimum of one empty rank keeps the layout from
    // collapsing when nothing has shipped yet.
    const shippedCap = Math.max(shipped.length, 0);

    if (ccTabVaultMeta) {
      const used = hoard.length;
      ccTabVaultMeta.textContent = `${String(used)}/${String(cap)}`;
      // v1.7 — persistent at-a-glance capacity warning (RULEBOOK §3.12/§3.14).
      // The vault is a fixed 15-slot tier ladder: once full, an incoming
      // square displaces the lowest-tier parcel rather than growing the grid,
      // so a human should see they're at/near the wall without waiting for the
      // TRANSMIT-time overflow toast.
      ccTabVaultMeta.classList.remove("cc-tab-meta--warn", "cc-tab-meta--full");
      if (cap > 0 && used >= cap) {
        ccTabVaultMeta.classList.add("cc-tab-meta--full");
        ccTabVaultMeta.title =
          `VAULT FULL (${used}/${cap}) — new squares displace the lowest-tier ` +
          `parcel (RULEBOOK \u00A73.14). The vault empties itself at the next orbit \u2014 this only bites if you overfill it tonight.`;
      } else if (cap > 0 && used >= Math.ceil(cap * 0.9)) {
        ccTabVaultMeta.classList.add("cc-tab-meta--warn");
        ccTabVaultMeta.title =
          `VAULT NEARLY FULL (${used}/${cap}) — it clears at the next orbit; ` +
          `overflow displaces the lowest tier.`;
      } else {
        ccTabVaultMeta.title = "";
      }
    }
    if (ccTabShippedMeta) {
      // Uncapped record: show the running count only, no denominator.
      ccTabShippedMeta.textContent = `${String(shipped.length)}`;
    }

    renderStorageGrid(vaultGridEl, hoard, cap);
    renderStorageGrid(
      shippedGridEl, shipped, shippedCap,
      { ownerBorders: allPlayersShipped },
    );
    renderAssetSections(inv);
    renderVaultMetaRow(shipped, shippedCap, hoard, inv);
  }

  /** Update the live readout strip at the top of the VAULT panel.
   *
   *  Shows three pills: credits, shipped RED purity sum, parcels
   *  shipped / capacity. ``credits`` is pulled from the latest agent
   *  ``orbit`` block (lastOrbitView); the shipped numbers come straight
   *  from the inventory payload that renderVault already has in hand. */
  function renderVaultMetaRow(shipped, shippedCap, hoard, inv) {
    const creditsEl = document.getElementById("vault-meta-credits");
    const redEl = document.getElementById("vault-meta-shipped-red");
    const countEl = document.getElementById("vault-meta-shipped-count");
    const blueEl = document.getElementById("vault-meta-blue-purity");
    if (creditsEl) {
      // v1.1 — in replay, prefer the per-tick credits reconstructed from
      // the frame snapshot so the readout tracks the cursor; fall back to
      // the live orbit view (live play, or Snowflake replays that dropped
      // the per-frame credits field).
      const c =
        inv && typeof inv.credits === "number"
          ? inv.credits
          : lastOrbitView && typeof lastOrbitView.credits === "number"
            ? lastOrbitView.credits
            : 0;
      creditsEl.textContent = `${String(c)}c`;
    }
    if (redEl) {
      const sum = shipped.reduce((acc, p) => {
        const v = p && (p.origin_purity ?? p.purity_at_harvest ?? p.purity);
        return acc + (Number.isFinite(Number(v)) ? Number(v) : 0);
      }, 0);
      redEl.textContent = String(sum);
    }
    if (countEl) {
      // SHIPPED is uncapped (public record) — show the running count.
      countEl.textContent = `${shipped.length}`;
    }
    // v0.9 — Blue-purity readout (weapons currency, RULEBOOK §4.9).
    // Mirrors the engine's blue_purity_available helper: sum the
    // ``purity`` field of every BLUE-tile parcel in the vault.
    if (blueEl) {
      const arr = Array.isArray(hoard) ? hoard : [];
      const sum = arr.reduce((acc, p) => {
        if (!p) return acc;
        const tile = Number(p.tile_at_harvest ?? p.origin_tile);
        // Tile.BLUE = 3 (mirrors generator.Tile enum). Keep this in
        // step with `Tile.BLUE` if the enum is ever renumbered.
        if (tile !== 3) return acc;
        const v = p.purity ?? p.purity_at_harvest ?? p.origin_purity;
        return acc + (Number.isFinite(Number(v)) ? Number(v) : 0);
      }, 0);
      blueEl.textContent = String(sum);
    }
  }

  // ── Per-player visual identity ───────────────────────────────────
  //
  // Fallback seat→colour map, aligned to ``SEAT_DEFAULT_COLORS`` in
  // ``sea_of_colours/game/session.py`` (the canonical palette defaults).
  // Only used when ``__SOC_PLAYER_META__`` hasn't loaded a real profile
  // colour yet (stale snapshot / pre-/status); a live session always
  // overrides this with the seat's actual custom/random palette colour.
  const OWNER_COLOR = {
    p1: "#FFFFFF", // white       → seat 1
    p2: "#FCF871", // yellow      → seat 2
    p3: "#E45EF0", // orchid pink → seat 3
    p4: "#82F4FB", // aqua        → seat 4
  };
  const OWNER_COLOR_DEFAULT = "#d8d8e0";
  const LOST_FG = "#6e6e7a";

  // v0.9.18 — player identity metadata (display_name, tag, color) for the
  // active session, keyed by seat id. Populated from /status (live) and
  // /replay (watch). Declared up here so the seat-colour helpers below can
  // read it without a temporal-dead-zone hazard. Single source of truth.
  let __SOC_PLAYER_META__ = {};

  function ownerColor(owner) {
    if (!owner) return OWNER_COLOR_DEFAULT;
    // v0.9.18 — prefer the live player profile colour (custom pick or the
    // random palette colour assigned to bots). __SOC_PLAYER_META__ is the
    // single source of truth populated from /status and /replay; the
    // hard-coded OWNER_COLOR map is only a fallback for stale snapshots.
    const meta = __SOC_PLAYER_META__ ? __SOC_PLAYER_META__[owner] : null;
    if (meta && meta.color) return meta.color;
    return OWNER_COLOR[owner] ?? OWNER_COLOR_DEFAULT;
  }

  /**
   * Glyph + colour for an asset chip — mirrors the in-game entity
   * overlay so the chip reads like a tiny replica of what the player
   * would see on the map. Returned values are pre-escaped HTML strings.
   *
   * Glyph table (kept aligned with ``ENTITY_GLYPHS`` server-side):
   *   harvester           → x  (lowercase, owner colour — empty)
   *   harvester carrying  → X  (uppercase, owner colour — loaded; cargo
   *                             is signalled by case, NOT colour, so
   *                             seat ownership stays readable)
   *   probe               → ·  (middle-dot, owner colour)
   *   orblift             → ▲  (up-triangle, owner colour — "lifts to orbit")
   *
   * @param {{ asset_type?: string, owner?: string, carrying_red?: boolean, alive?: boolean }} row
   */
  function assetChipVisual(row) {
    const kind = String(row.asset_type || "");
    const alive = row.alive !== false;
    const owner = String(row.owner || "");
    const baseFg = alive ? ownerColor(owner) : LOST_FG;
    if (kind === "harvester") {
      return {
        glyph: "X",
        fg: baseFg,
        bg: "#1a1322",
      };
    }
    if (kind === "orblift") {
      return {
        glyph: "\u25B2",
        fg: baseFg,
        bg: "#1a1322",
      };
    }
    if (kind === "probe") {
      return {
        glyph: "\u00B7",
        fg: baseFg,
        bg: "#1a1322",
      };
    }
    return { glyph: "?", fg: OWNER_COLOR_DEFAULT, bg: "#1a1322" };
  }

  /**
   * @param {HTMLElement | null} host
   * @param {any[]} rows
   * @param {string} bucketKey
   */
  function renderAssetChipRow(host, rows, bucketKey) {
    if (!host) return;
    if (!Array.isArray(rows) || !rows.length) {
      host.innerHTML = `<div class="cc-assets-empty dim">// none</div>`;
      bindAssetTooltip(host);
      return;
    }
    const parts = rows.map((row) => {
      const visual = assetChipVisual(row);
      const cls =
        "cc-asset-chip" +
        (bucketKey === "destroyed" ? " cc-asset-chip--destroyed" : "") +
        (row.alive === false && bucketKey !== "destroyed"
          ? " cc-asset-chip--ghost"
          : "");
      const data = [
        `data-asset-id="${escAttr(String(row.asset_id || ""))}"`,
        `data-asset-type="${escAttr(String(row.asset_type || ""))}"`,
        `data-owner="${escAttr(String(row.owner || ""))}"`,
        `data-created="${escAttr(String(row.created_on_day ?? ""))}"`,
        `data-first-deployed="${escAttr(
          row.first_deployed_day == null
            ? ""
            : String(row.first_deployed_day),
        )}"`,
        `data-destroyed="${escAttr(
          row.destroyed_on_day == null ? "" : String(row.destroyed_on_day),
        )}"`,
        `data-destroyed-by="${escAttr(String(row.destroyed_by || ""))}"`,
        `data-total-red="${escAttr(String(row.total_red_harvested ?? 0))}"`,
        `data-days-surfaced="${escAttr(
          String(row.total_days_on_surface ?? 0),
        )}"`,
        `data-bucket="${escAttr(bucketKey)}"`,
      ];
      if (Array.isArray(row.current_pos)) {
        data.push(
          `data-pos-x="${escAttr(String(row.current_pos[0]))}"`,
          `data-pos-y="${escAttr(String(row.current_pos[1]))}"`,
        );
      }
      if (typeof row.current_cargo_count === "number") {
        data.push(`data-cargo="${escAttr(String(row.current_cargo_count))}"`);
      }
      if (row.holds_red) data.push(`data-holds-red="1"`);
      const tile = `<span class="cc-asset-chip-glyph" style="background:${esc(
        visual.bg,
      )};color:${esc(visual.fg)}">${esc(visual.glyph)}</span>`;
      const label = `<span class="cc-asset-chip-label">${esc(
        shortAssetLabel(row),
      )}</span>`;
      return `<div class="${cls}" ${data.join(" ")}>${tile}${label}</div>`;
    });
    host.innerHTML = parts.join("");
    bindAssetTooltip(host);
  }

  /** @param {{ asset_id?: string, asset_type?: string }} row */
  function shortAssetLabel(row) {
    const id = String(row.asset_id || "");
    const t = String(row.asset_type || "");
    // v0.9.2 — drop the numbered sticker from probes (probes are
    // identical disposables; the user shouldn't have to track an
    // ID per probe). Harvesters keep their numbered badge — there
    // are at most three per seat and they're each individually
    // tracked across the season.
    if (t === "probe") return "prb";
    if (t === "harvester") {
      const m = /(\d+)$/.exec(id);
      return m ? `hv #${m[1]}` : "hv";
    }
    if (t === "orblift") return "lft";
    return id.split("_")[0] || id;
  }

  function renderAssetSections(inv) {
    const buckets = (inv && inv.assets_by_status) || {};
    renderAssetChipRow(
      vaultAssetsOrbitEl,
      Array.isArray(buckets.in_orbit) ? buckets.in_orbit : [],
      "in_orbit",
    );
    renderAssetChipRow(
      vaultAssetsSurfaceEl,
      Array.isArray(buckets.on_surface) ? buckets.on_surface : [],
      "on_surface",
    );
    renderAssetChipRow(
      vaultAssetsDestroyedEl,
      Array.isArray(buckets.destroyed) ? buckets.destroyed : [],
      "destroyed",
    );
    // v0.9.5 — weapons bays. ``weapon_stock`` rides on the
    // inventory_pack (current stockpile); ``weapons_used`` is the
    // append-only lifetime counter. Both render as the same chip
    // row but with different empty-state copy.
    renderVaultWeaponsBay(
      document.getElementById("vault-weapons-available"),
      (inv && inv.weapon_stock) || {},
      "available",
    );
    renderVaultWeaponsBay(
      document.getElementById("vault-weapons-used"),
      (inv && inv.weapons_used) || {},
      "used",
    );
    // Mirror the same roster into the ORDERS panel so the user can
    // compose moves from the unit chips themselves (v0.8.0).
    renderOrdersAssetRoster();
  }

  /**
   * v0.9.5 — Render one weapons bay (AVAILABLE or USED) into the
   * given host. Both bays use the same chip layout (icon + label
   * + count); the ``mode`` parameter picks the empty-state copy
   * and the chip's accent class.
   *
   * @param {HTMLElement | null} host
   * @param {Record<string, any>} counts
   * @param {"available" | "used"} mode
   */
  function renderVaultWeaponsBay(host, counts, mode) {
    if (!host) return;
    host.textContent = "";
    const emp = Math.max(0, Number(counts?.emp || 0));
    const mine = Math.max(0, Number(counts?.mine || 0));
    const chaff = Math.max(0, Number(counts?.chaff || 0));
    if (emp + mine + chaff === 0) {
      const empty = document.createElement("span");
      empty.className = "cc-assets-empty dim";
      empty.textContent =
        mode === "used"
          ? "// none fired yet"
          : "// bay empty · build in ORBIT phase";
      host.appendChild(empty);
      return;
    }
    /**
     * @param {string} kind
     * @param {string} label
     * @param {number} count
     */
    const makeChip = (kind, label, count) => {
      const chip = document.createElement("div");
      chip.className = `cc-asset-chip cc-weapon-bay-chip cc-weapon-bay-chip--${mode}`;
      chip.dataset.weaponKind = kind;
      chip.dataset.weaponMode = mode;
      const icon = document.createElement("span");
      icon.className = `cc-weapon-icon cc-weapon-icon-${kind}`;
      icon.setAttribute("aria-hidden", "true");
      chip.appendChild(icon);
      const lab = document.createElement("span");
      lab.className = "cc-asset-chip-label";
      lab.textContent = `${label} ${String(count)}`;
      chip.appendChild(lab);
      chip.title =
        mode === "used"
          ? `${label} fired this season: ${count}`
          : `${label} ready to fire: ${count} (build more in ORBIT)`;
      return chip;
    };
    host.appendChild(makeChip("emp", "EMP", emp));
    host.appendChild(makeChip("mine", "MINE", mine));
    host.appendChild(makeChip("chaff", "CHAFF", chaff));
  }

  /** v0.8.0 — Build the ORDERS-tab asset roster (a.k.a. the action
   *  picker). Each row is a tier of the asset hierarchy:
   *
   *    1. ORBLIFTS — render-only header with DROP / PICKUP sub-buttons.
   *    2. PROBES — single "stock" chip carrying the build count.
   *    3. HARVESTERS — one chip per live harvester, click to enter
   *       STEP mode (if on surface) or noop with a hint (if in orbit).
   *
   *  Selected chip carries ``.cc-asset-chip--active``; the rest dim
   *  so the eye lands on what's currently active. */
  function renderOrdersAssetRoster() {
    const host = document.getElementById("orders-asset-roster");
    if (!host) return;
    host.textContent = "";

    const inv = lastLiveInventory;
    const buckets = (inv && inv.assets_by_status) || {};
    const inOrbit = Array.isArray(buckets.in_orbit) ? buckets.in_orbit : [];
    const onSurface = Array.isArray(buckets.on_surface) ? buckets.on_surface : [];
    const orblifts = [
      ...inOrbit.map((r) => ({ row: r, bucket: "in_orbit" })),
      ...onSurface.map((r) => ({ row: r, bucket: "on_surface" })),
    ].filter((p) => p.row && p.row.asset_type === "orblift");

    // v0.9.5 — split the rosters into the same vault-style buckets
    // the VAULT panel uses (IN ORBIT / ON SURFACE) so the two
    // panels share a single visual language. Orblifts ride their
    // own POD up top so the [DROP] / [PICKUP] composer can sit
    // next to the chip in the same flex row.
    const orbitHarv = inOrbit.filter(
      (/** @type {any} */ r) => r && r.asset_type === "harvester",
    );
    const surfaceHarv = onSurface.filter(
      (/** @type {any} */ r) => r && r.asset_type === "harvester",
    );
    const surfaceProbes = onSurface.filter(
      (/** @type {any} */ r) => r && r.asset_type === "probe",
    );

    // ── ORBLIFT POD (chip + DROP / PICKUP buttons inline) ─────────
    // Single flex row carrying the orblift chip and its two
    // composer buttons. The chip itself uses the VAULT-style
    // compact chip so the visual language matches the rest of
    // the roster. Buttons remain mini CLI buttons but sit IN the
    // same pod (vs. the old row-below layout).
    const orbliftPod = document.createElement("div");
    orbliftPod.className = "cc-orders-pod cc-orders-pod--orblift";
    const orbliftPodHead = document.createElement("span");
    orbliftPodHead.className = "cc-orders-pod-label dim";
    orbliftPodHead.textContent = "// orblift";
    orbliftPod.appendChild(orbliftPodHead);
    if (orblifts.length === 0) {
      const empty = document.createElement("span");
      empty.className = "dim cc-orders-pod-empty";
      empty.textContent = "// none owned";
      orbliftPod.appendChild(empty);
    } else {
      const lift = orblifts[0];
      // Vault-style compact chip via the shared builder (same
      // data-* attributes + tooltip surface). v0.9.5 — wrap the
      // chip so its yellow "// in current plan" annotation can
      // surface every queued DROP / PICKUP across all harvesters
      // (the orblift is what executes both).
      const liftChip = buildVaultStyleChip(lift.row, lift.bucket);
      const liftPlan = planSummaryForOrblift();
      orbliftPod.appendChild(wrapChipWithPlan(liftChip, liftPlan));

      const dropBtn = document.createElement("button");
      dropBtn.type = "button";
      dropBtn.className = "cli-btn cc-orders-pod-btn";
      dropBtn.textContent = "[ DROP ]";
      dropBtn.title =
        "Drop a harvester from orbit onto a tile. Click DROP, then "
        + "a harvester in orbit, then the target cell.";
      dropBtn.addEventListener("click", () => {
        if (assetSelect && assetSelect.action === "drop") {
          exitAssetSelect();
          return;
        }
        enterAssetSelect({ action: "drop", awaiting: "unit" });
      });
      if (assetSelect && assetSelect.action === "drop")
        dropBtn.classList.add("cc-orders-pod-btn--active");
      orbliftPod.appendChild(dropBtn);

      const pickupBtn = document.createElement("button");
      pickupBtn.type = "button";
      pickupBtn.className = "cli-btn cc-orders-pod-btn";
      pickupBtn.textContent = "[ PICKUP ]";
      pickupBtn.title =
        "Recall a harvester back to orbit (banks its cargo). Click "
        + "PICKUP, then the on-surface harvester.";
      pickupBtn.addEventListener("click", () => {
        if (assetSelect && assetSelect.action === "pickup") {
          exitAssetSelect();
          return;
        }
        enterAssetSelect({ action: "pickup", awaiting: "unit" });
      });
      if (assetSelect && assetSelect.action === "pickup")
        pickupBtn.classList.add("cc-orders-pod-btn--active");
      orbliftPod.appendChild(pickupBtn);
    }
    host.appendChild(orbliftPod);

    // ── IN ORBIT row ──────────────────────────────────────────────
    // Mirror the VAULT panel's divider style. Carries every owned
    // harvester currently in orbit (no surface coords). Probe
    // stock + per-probe deployed chips ride the same row format
    // so the user sees one chip per orbital harvester + a single
    // "probe stock" affordance.
    appendOrdersDivider(host, "in orbit");
    const orbitRow = document.createElement("div");
    orbitRow.className = "cc-orders-row";

    // Probe stock chip — actionable, sits leftmost so it's easy
    // to find when deploying. v0.9.5 — wrap so the queued probe
    // deploys surface as a yellow plan annotation under the chip.
    const probeStock =
      (lastOrbitView && Number(lastOrbitView.probe_stock)) || 0;
    const probeChipEl = makeProbeStockChip(probeStock);
    const probesPlan = planSummaryForProbes();
    orbitRow.appendChild(wrapChipWithPlan(probeChipEl, probesPlan));

    if (orbitHarv.length === 0) {
      const empty = document.createElement("span");
      empty.className = "dim cc-orders-row-empty";
      empty.textContent = "// no harvesters in orbit";
      orbitRow.appendChild(empty);
    } else {
      for (const row of orbitHarv) {
        orbitRow.appendChild(
          buildOrdersHarvesterChip(row, "in_orbit"),
        );
      }
    }
    host.appendChild(orbitRow);

    // ── ON SURFACE row ────────────────────────────────────────────
    appendOrdersDivider(host, "on surface");
    const surfRow = document.createElement("div");
    surfRow.className = "cc-orders-row";
    if (surfaceHarv.length === 0 && surfaceProbes.length === 0) {
      const empty = document.createElement("span");
      empty.className = "dim cc-orders-row-empty";
      empty.textContent = "// nothing deployed yet";
      surfRow.appendChild(empty);
    } else {
      for (const row of surfaceHarv) {
        surfRow.appendChild(
          buildOrdersHarvesterChip(row, "on_surface"),
        );
      }
      for (const row of surfaceProbes) {
        surfRow.appendChild(
          buildVaultStyleChip(row, "on_surface"),
        );
      }
    }
    host.appendChild(surfRow);

    // ── DESTROYED / EXPIRED row ───────────────────────────────────
    // v0.9.18 — probes that ran out their lifetime (reason
    // ``probe_expired``) and any other lost assets move here so the
    // ORDERS picker mirrors the VAULT's destroyed bucket. Only shown
    // when something has actually been lost, to keep the roster tidy
    // during a clean game.
    const destroyedAssets = Array.isArray(buckets.destroyed)
      ? buckets.destroyed
      : [];
    if (destroyedAssets.length) {
      appendOrdersDivider(host, "destroyed");
      const deadRow = document.createElement("div");
      deadRow.className = "cc-orders-row cc-orders-row--destroyed";
      for (const row of destroyedAssets) {
        deadRow.appendChild(buildVaultStyleChip(row, "destroyed"));
      }
      host.appendChild(deadRow);
    }

    // ── WEAPONS BAY (AVAILABLE only, RULEBOOK §5.0) ───────────────
    // Weapons are BUILT during the ORBIT phase and drained from
    // stockpile during the night. ORDERS surfaces only the
    // available stock (the USED bay lives in the VAULT). Below
    // the chip row sits the WAIT button so the hour-scheduling
    // utility stays one click away. The bay uses the same divider
    // chrome as IN ORBIT / ON SURFACE.
    appendOrdersDivider(host, "weapons bay · available");
    const wepBody = document.createElement("div");
    wepBody.className = "cc-orders-row cc-orders-row--weapons";

    const ws = (lastOrbitView && lastOrbitView.weapon_stock) || {};
    const empStock = Math.max(0, Number(ws.emp || 0));
    const mineStock = Math.max(0, Number(ws.mine || 0));
    const chaffStock = Math.max(0, Number(ws.chaff || 0));
    const totalWeaponStock = empStock + mineStock + chaffStock;
    if (totalWeaponStock === 0) {
      const nudge = document.createElement("span");
      nudge.className = "dim cc-orders-row-empty";
      nudge.textContent =
        "// bay empty · build EMP / MINE / CHAFF in the ORBIT phase";
      wepBody.appendChild(nudge);
      // WAIT button — consume one hour slot without acting.
      const waitBtnEmpty = document.createElement("button");
      waitBtnEmpty.type = "button";
      waitBtnEmpty.className =
        "cli-btn cc-asset-chip cc-weapon-chip cc-weapon-chip--wait";
      waitBtnEmpty.textContent = "[ WAIT ]";
      waitBtnEmpty.title =
        "Add a WAIT slot (1 hour). Pad the queue to schedule a move " +
        "at a specific hour without firing a weapon.";
      waitBtnEmpty.addEventListener("click", () => {
        addQueueRow("wait");
      });
      wepBody.appendChild(
        wrapChipWithPlan(waitBtnEmpty, planSummaryForWeapon("wait")),
      );
      host.appendChild(wepBody);
      bindAssetTooltip(host);
      return;
    }

    // Helper: render a weapon button with embedded icon, stock chip,
    // and disabled-when-empty styling. The icon is the same DOM
    // marker used in the orbit readout so a single CSS rule covers
    // every surface (vault chip, orbit readout, orders chip, queue
    // row description).
    const makeWeaponButton = (slot, label, stock, title, onClick) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className =
        `cli-btn cc-asset-chip cc-weapon-chip cc-weapon-chip--${slot}`;
      const iconKey = (
        slot === "emp_launch" ? "emp"
        : slot === "mine_lay" ? "mine"
        : slot === "chaff_flare" ? "chaff"
        : slot
      );
      const icon = document.createElement("span");
      icon.className = `cc-weapon-icon cc-weapon-icon-${iconKey}`;
      icon.setAttribute("aria-hidden", "true");
      const text = document.createElement("span");
      text.className = "cc-weapon-chip-label";
      text.textContent = ` ${label} `;
      const stockChip = document.createElement("span");
      stockChip.className = "cc-weapon-chip-stock";
      stockChip.textContent = `(${stock})`;
      btn.append(document.createTextNode("[ "), icon, text, stockChip,
        document.createTextNode(" ]"));
      btn.title = title;
      if (stock <= 0) {
        btn.classList.add("is-disabled");
        btn.disabled = true;
        btn.title = title + "\n\n(stockpile empty — build one in ORBIT)";
      } else {
        btn.addEventListener("click", onClick);
      }
      return btn;
    };

    const empBtn = makeWeaponButton(
      "emp_launch",
      "EMP",
      empStock,
      "Orbital EMP salvo · ONE launch fires 3 simultaneous missiles, each "
      + "a radius-2 (Manhattan) cloud for 8h. Disables harvesters AND "
      + "destroys probes + mines caught in the blast (friendly fire on). "
      + "Open action. Built in ORBIT phase.",
      () => {
        if (assetSelect && assetSelect.action === "emp_launch") {
          exitAssetSelect();
          return;
        }
        enterAssetSelect({ action: "emp_launch", awaiting: "target" });
      },
    );
    if (assetSelect && assetSelect.action === "emp_launch") {
      empBtn.classList.add("cc-asset-chip--armed");
    }
    // v0.9.5 — wrap so queued EMP launches show "EMP @(x,y) @slot N"
    // as a yellow plan annotation under the chip. Same wrapper
    // applies to MINE / CHAFF / WAIT below.
    wepBody.appendChild(
      wrapChipWithPlan(empBtn, planSummaryForWeapon("emp")),
    );

    const mineBtn = makeWeaponButton(
      "mine_lay",
      "MINE",
      mineStock,
      "Caltrop mine cluster · one lay arms a hidden 5-cell (plus-shaped) "
      + "field; any harvester stepping onto a mined tile is damaged + step "
      + "cancelled. Hidden until a probe sees it (the minelayer's flight is "
      + "public). EMP clears mines. Built in ORBIT.",
      () => {
        if (assetSelect && assetSelect.action === "mine_lay") {
          exitAssetSelect();
          return;
        }
        enterAssetSelect({ action: "mine_lay", awaiting: "target" });
      },
    );
    if (assetSelect && assetSelect.action === "mine_lay") {
      mineBtn.classList.add("cc-asset-chip--armed");
    }
    wepBody.appendChild(
      wrapChipWithPlan(mineBtn, planSummaryForWeapon("mine")),
    );

    const chaffBtn = makeWeaponButton(
      "chaff_flare",
      "CHAFF",
      chaffStock,
      "Orbital chaff flare · jams EVERY house's actions (yours included) "
      + "for 3 turns. Occupies 3 queue slots: the launch + 2 self-jammed "
      + "turns. Open action. Built in ORBIT.",
      () => {
        addQueueRow("chaff_flare");
      },
    );
    wepBody.appendChild(
      wrapChipWithPlan(chaffBtn, planSummaryForWeapon("chaff")),
    );

    // WAIT — consume one hour slot without acting. Companion to the
    // weapons because the same UX pattern (hour-by-hour scheduling)
    // makes EMP / mines / chaff effective.
    const waitBtn = document.createElement("button");
    waitBtn.type = "button";
    waitBtn.className = "cli-btn cc-asset-chip cc-weapon-chip cc-weapon-chip--wait";
    waitBtn.textContent = "[ WAIT ]";
    waitBtn.title =
      "Add a WAIT slot (1 hour). Pad the queue to schedule a move at " +
      "a specific hour (e.g. 9 WAITs + EMP fires the warhead at hour 10).";
    waitBtn.addEventListener("click", () => {
      addQueueRow("wait");
    });
    wepBody.appendChild(
      wrapChipWithPlan(waitBtn, planSummaryForWeapon("wait")),
    );

    host.appendChild(wepBody);

    // v0.9.5 — share the VAULT's rich asset tooltip with this
    // roster so a hover on any chip surfaces created-on, last
    // deployed, total-red harvested, damaged flag, repair count,
    // etc. ``bindAssetTooltip`` is idempotent so re-render calls
    // are cheap.
    bindAssetTooltip(host);
  }

  /**
   * v0.9.5 — section divider mirroring the VAULT panel's
   * "— — — IN ORBIT — — —" chrome. Centralised so all ORDERS
   * rows render with identical spacing / typography.
   * @param {HTMLElement} host
   * @param {string} label
   */
  function appendOrdersDivider(host, label) {
    const div = document.createElement("div");
    div.className = "cc-assets-divider cc-orders-divider";
    div.setAttribute("role", "separator");
    const inner = document.createElement("span");
    inner.textContent = `— — — ${label} — — —`;
    div.appendChild(inner);
    host.appendChild(div);
  }

  /**
   * v0.9.5 — Build a VAULT-style compact chip (the same DOM the
   * VAULT panel emits via ``renderAssetChipRow``) for use in the
   * ORDERS roster. The chip carries every lifecycle ``data-*``
   * attribute so it surfaces the same rich tooltip on hover; the
   * caller can override clickability via ``onClick``.
   *
   * @param {any} row
   * @param {string} bucket
   * @param {{ onClick?: ((ev: MouseEvent) => void) | null, active?: boolean }} [opts]
   */
  function buildVaultStyleChip(row, bucket, opts) {
    const kind = String(row?.asset_type || "");
    const visual = assetChipVisual({
      asset_type: kind,
      owner: row?.owner,
      carrying_red: row?.carrying_red,
      alive: row?.alive !== false,
    });
    const chip = document.createElement("div");
    chip.className =
      "cc-asset-chip" +
      (row?.alive === false ? " cc-asset-chip--ghost" : "") +
      (row?.damaged ? " cc-asset-chip--damaged" : "") +
      (opts?.active ? " cc-asset-chip--active" : "");

    // Lifecycle data attributes — same shape the VAULT chips use
    // so the shared ``fillAssetTooltip`` shows the full provenance
    // card on hover.
    chip.dataset.assetId = String(row?.asset_id || "");
    chip.dataset.assetType = kind;
    chip.dataset.owner = String(row?.owner || "");
    chip.dataset.bucket = bucket;
    if (row?.created_on_day != null)
      chip.dataset.created = String(row.created_on_day);
    if (row?.first_deployed_day != null)
      chip.dataset.firstDeployed = String(row.first_deployed_day);
    if (row?.destroyed_on_day != null)
      chip.dataset.destroyed = String(row.destroyed_on_day);
    if (row?.destroyed_by) chip.dataset.destroyedBy = String(row.destroyed_by);
    chip.dataset.totalRed = String(row?.total_red_harvested ?? 0);
    chip.dataset.daysSurfaced = String(row?.total_days_on_surface ?? 0);
    if (row?.repair_count != null)
      chip.dataset.repairCount = String(row.repair_count);
    if (row?.last_repaired_day != null)
      chip.dataset.lastRepaired = String(row.last_repaired_day);
    if (row?.damaged) chip.dataset.damaged = "1";
    if (Array.isArray(row?.current_pos)) {
      chip.dataset.posX = String(row.current_pos[0]);
      chip.dataset.posY = String(row.current_pos[1]);
    }
    if (typeof row?.current_cargo_count === "number")
      chip.dataset.cargo = String(row.current_cargo_count);
    if (row?.holds_red) chip.dataset.holdsRed = "1";
    if (row?.carrying_red) chip.dataset.carryingRed = "1";

    const tile = document.createElement("span");
    tile.className = "cc-asset-chip-glyph";
    tile.style.background = visual.bg;
    tile.style.color = visual.fg;
    tile.textContent = visual.glyph;
    // Numbered sticker — harvesters keep it (3 max per seat, each
    // individually tracked). Probes drop it (disposables).
    if (kind === "harvester") {
      const ordinal = unitOrdinal(String(row?.asset_id || ""));
      if (Number.isFinite(ordinal)) {
        const badge = document.createElement("span");
        badge.className = "cc-asset-chip-sub";
        badge.textContent = String(ordinal);
        tile.appendChild(badge);
      }
    }
    chip.appendChild(tile);

    const label = document.createElement("span");
    label.className = "cc-asset-chip-label";
    let chipLabelText = shortAssetLabel(row || {});
    // v0.9.18 — probe lifetime, shown as concentric ring strokes on the
    // chip glyph (matching the map: double border = most life, single,
    // then bare on the final night) plus a concise "Nn left" label. A
    // destroyed/expired probe drops the rings (it's in the destroyed
    // bucket and already wears the wreck styling).
    if (kind === "probe" && row?.nights_remaining != null && bucket !== "destroyed") {
      const nr = Number(row.nights_remaining);
      if (Number.isFinite(nr)) {
        const rings = Math.max(0, Math.min(2, nr - 1));
        tile.classList.add(
          "cc-asset-chip-glyph--probe",
          `cc-asset-chip-glyph--probe-life-${rings}`,
        );
        const urgency = nr <= 1 ? " ⚠" : "";
        chipLabelText += ` · ${nr}N left${urgency}`;
        if (nr <= 1) chip.classList.add("cc-asset-chip--probe-urgent");
      }
    }
    label.textContent = chipLabelText;
    chip.appendChild(label);

    if (opts?.onClick) {
      // ``div`` chips aren't natively focusable / clickable —
      // wire it ourselves and add a cursor hint via the class.
      chip.classList.add("cc-asset-chip--clickable");
      chip.addEventListener("click", opts.onClick);
    }
    return chip;
  }

  /**
   * v0.9.5 — wrap a harvester chip with a yellow plan annotation
   * row showing what the queue is going to do to it ("dropped
   * @(4,9) · moved 3 steps · picked up"). Clicking the chip
   * arms / re-arms the path picker for that harvester.
   *
   * @param {any} row
   * @param {string} bucket
   */
  function buildOrdersHarvesterChip(row, bucket) {
    const armed =
      assetSelect &&
      assetSelect.unit &&
      String(assetSelect.unit) === String(row?.asset_id);
    const chip = buildVaultStyleChip(row, bucket, {
      active: Boolean(armed),
      onClick: () => onHarvesterChipClick({ ...row, _bucket: bucket }),
    });
    const plan = planSummaryForUnit(String(row?.asset_id || ""));
    return wrapChipWithPlan(chip, plan, {
      extraClass: armed ? "cc-orders-chip-wrap--armed" : "",
    });
  }

  /** Build a clickable roster chip for one asset row. The bucket key
   *  (``in_orbit`` / ``on_surface``) seeds the chip; for harvesters
   *  we then project the queue forward so the label reflects what
   *  the unit WILL look like at PRAXIS time (drop → surface, etc.). */
  function makeAssetChip(row, opts) {
    const kind = (opts && opts.kind) || row.asset_type;
    const isStatic = Boolean(opts && opts.static);
    const bucket = (opts && opts.bucket) || "in_orbit";
    let inOrbit = bucket === "in_orbit";
    let surfaced = bucket === "on_surface";
    let projectedPos = rowPosition(row);
    let projected = false;
    if (kind === "harvester" && !isStatic) {
      const proj = projectedUnitState(String(row.asset_id || ""));
      const projBucket = proj.bucket;
      if (
        (projBucket === "on_surface") !== surfaced ||
        (projBucket === "in_orbit") !== inOrbit
      ) {
        projected = true;
      }
      surfaced = projBucket === "on_surface";
      inOrbit = projBucket === "in_orbit";
      if (proj.pos) projectedPos = proj.pos;
    }

    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "cli-btn cc-asset-chip";
    chip.dataset.assetId = String(row.asset_id || "");
    chip.dataset.assetKind = String(kind);
    chip.dataset.assetState = bucket;
    // v0.9.5 — stamp the SAME lifecycle ``data-*`` attributes the
    // VAULT panel's ``renderAssetChipRow`` uses so the shared
    // ``fillAssetTooltip`` handler shows the full provenance card
    // here in ORDERS too. The roster host calls ``bindAssetTooltip``
    // after rendering, so the mouseover wiring is identical to the
    // vault's. Damaged / repair history rides as data-attrs as well
    // so the tooltip can render wrench state and repair counts.
    chip.dataset.assetType = String(row.asset_type || kind || "");
    chip.dataset.owner = String(row.owner || "");
    chip.dataset.bucket = bucket;
    if (row.created_on_day != null)
      chip.dataset.created = String(row.created_on_day);
    if (row.first_deployed_day != null)
      chip.dataset.firstDeployed = String(row.first_deployed_day);
    if (row.destroyed_on_day != null)
      chip.dataset.destroyed = String(row.destroyed_on_day);
    if (row.destroyed_by)
      chip.dataset.destroyedBy = String(row.destroyed_by);
    chip.dataset.totalRed = String(row.total_red_harvested ?? 0);
    chip.dataset.daysSurfaced = String(row.total_days_on_surface ?? 0);
    if (row.repair_count != null)
      chip.dataset.repairCount = String(row.repair_count);
    if (row.last_repaired_day != null)
      chip.dataset.lastRepaired = String(row.last_repaired_day);
    if (row.damaged) chip.dataset.damaged = "1";
    if (Array.isArray(row.current_pos)) {
      chip.dataset.posX = String(row.current_pos[0]);
      chip.dataset.posY = String(row.current_pos[1]);
    }
    if (typeof row.current_cargo_count === "number")
      chip.dataset.cargo = String(row.current_cargo_count);
    if (row.holds_red) chip.dataset.holdsRed = "1";
    if (row.carrying_red) chip.dataset.carryingRed = "1";

    // ``assetChipVisual`` was built for the VAULT panel. It expects
    // an ``alive`` flag which the bucketed roster row already carries.
    const visual = assetChipVisual({
      asset_type: kind,
      owner: row.owner,
      carrying_red: row.carrying_red,
      alive: row.alive !== false,
    });
    const glyph = document.createElement("span");
    glyph.className = "cc-asset-chip-glyph";
    glyph.style.color = visual.fg;
    glyph.textContent = visual.glyph;
    if (kind === "harvester" || kind === "probe") {
      // v0.8.1 — stamp the ordinal (1, 2, 3) on the chip glyph as a
      // bordered subscript tag (Option C) so the orders roster
      // matches the in-map badge convention.
      const ordinal = unitOrdinal(String(row.asset_id || ""));
      if (Number.isFinite(ordinal)) {
        const badge = document.createElement("span");
        badge.className = "cc-asset-chip-sub";
        badge.textContent = String(ordinal);
        glyph.appendChild(badge);
      }
    }
    chip.appendChild(glyph);

    const label = document.createElement("span");
    label.className = "cc-asset-chip-label";
    const stateTag = inOrbit ? "orbit" : surfaced ? "surface" : "destroyed";
    const posTag = projectedPos && surfaced ? ` @(${projectedPos[0]},${projectedPos[1]})` : "";
    const projTag = projected ? " *" : "";
    label.textContent = `${row.asset_id}${posTag} · ${stateTag}${projTag}`;
    if (projected) {
      label.title =
        "* shows projected state after queued moves (live state may differ)";
    }
    chip.appendChild(label);

    if (row.damaged) chip.classList.add("cc-asset-chip--damaged");
    if (row.alive === false) chip.classList.add("cc-asset-chip--dead");

    if (isStatic) {
      chip.disabled = true;
      chip.classList.add("cc-asset-chip--static");
      return chip;
    }

    if (kind === "harvester") {
      if (
        assetSelect &&
        assetSelect.unit &&
        String(assetSelect.unit) === String(row.asset_id)
      ) {
        chip.classList.add("cc-asset-chip--active");
      }
      chip.addEventListener("click", () =>
        onHarvesterChipClick({ ...row, _bucket: bucket }),
      );
      if (assetSelect && assetSelect.action === "drop" && inOrbit) {
        chip.title = `Drop ${row.asset_id} at a tile (click to choose)`;
      } else if (assetSelect && assetSelect.action === "pickup" && surfaced) {
        chip.title = `Pickup ${row.asset_id} (queue order)`;
      } else if (surfaced) {
        chip.title = `Step ${row.asset_id} (click to choose a neighbouring cell)`;
      } else if (inOrbit) {
        chip.title = `${row.asset_id} is in orbit — use ORBLIFT > DROP to deploy`;
      }
      return chip;
    }
    return chip;
  }

  /** v0.8.0 — single chip representing the seat's probe stock. Click
   *  to enter PROBE-target mode (next map click deploys). Disabled
   *  when the stock is 0 and the user has nothing buildable queued. */
  function makeProbeStockChip(stock) {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "cli-btn cc-asset-chip cc-asset-chip--probe-stock";

    const glyph = document.createElement("span");
    glyph.className = "cc-asset-chip-glyph";
    glyph.style.color = "#aaffd0";
    glyph.textContent = "\u00B7";
    chip.appendChild(glyph);

    const label = document.createElement("span");
    label.className = "cc-asset-chip-label";
    label.textContent = `probe stock: ${stock}`;
    chip.appendChild(label);

    if (stock <= 0) {
      chip.classList.add("cc-asset-chip--dead");
      chip.disabled = true;
      chip.title =
        "Probe stock exhausted — build a new probe in the next ORBIT phase.";
    } else {
      chip.title = "Deploy a probe (click, then choose a target cell)";
      if (assetSelect && assetSelect.action === "probe") {
        chip.classList.add("cc-asset-chip--active");
      }
      chip.addEventListener("click", () => {
        if (assetSelect && assetSelect.action === "probe") {
          exitAssetSelect();
          return;
        }
        enterAssetSelect({ action: "probe", awaiting: "target" });
      });
    }
    return chip;
  }

  function onHarvesterChipClick(row) {
    // v0.8.1 — validate against the harvester's PROJECTED state (live
    // state + queued moves so far), not just its live snapshot. The
    // "drop and pick up on the same night" rule means a unit that's
    // currently in orbit can legally be the target of a step or
    // pickup later in the queue, provided a drop is queued first.
    const unitId = String(row.asset_id);
    const proj = projectedUnitState(unitId);
    const surfaced = proj.bucket === "on_surface";
    const inOrbit = proj.bucket === "in_orbit";

    if (assetSelect && assetSelect.action === "drop" && assetSelect.awaiting === "unit") {
      if (!inOrbit) {
        flashHint(
          `${unitId} is already on surface — pickup first if you want to re-drop`,
        );
        return;
      }
      enterAssetSelect({
        action: "drop",
        unit: unitId,
        awaiting: "target",
      });
      return;
    }
    if (assetSelect && assetSelect.action === "pickup" && assetSelect.awaiting === "unit") {
      if (!surfaced) {
        flashHint(`${unitId} is in orbit — nothing to pickup`);
        return;
      }
      addQueueRow("pickup", undefined, undefined, unitId);
      exitAssetSelect();
      return;
    }
    // Default click → STEP mode. Valid when the harvester is or
    // WILL BE on surface by the time the new move runs (i.e. a drop
    // is already queued earlier in the chain).
    if (inOrbit) {
      flashHint(`${unitId} is in orbit — queue ORBLIFT > DROP first`);
      return;
    }
    if (row.damaged) {
      flashHint(`${unitId} is damaged — repair in next ORBIT phase`);
      return;
    }
    if (assetSelect && assetSelect.unit === unitId && assetSelect.action === "step") {
      exitAssetSelect();
      return;
    }
    enterAssetSelect({
      action: "step",
      unit: unitId,
      awaiting: "target",
    });
  }

  /** Briefly surface a hint line above the asset roster. Used to flag
   *  things like "this harvester is in orbit, use ORBLIFT > DROP". */
  let _flashTimer = null;
  function flashHint(text) {
    const host = document.getElementById("orders-asset-roster");
    if (!host) return;
    let hint = host.querySelector(".cc-asset-roster-hint");
    if (!hint) {
      hint = document.createElement("div");
      hint.className = "cc-asset-roster-hint";
      host.prepend(hint);
    }
    hint.textContent = text;
    hint.classList.add("cc-asset-roster-hint--visible");
    if (_flashTimer) window.clearTimeout(_flashTimer);
    _flashTimer = window.setTimeout(() => {
      hint?.classList.remove("cc-asset-roster-hint--visible");
    }, 2400);
  }

  function ingestEntityIds(hints) {
    const ids = hints && Array.isArray(hints.entity_ids) ? hints.entity_ids : [];
    soloIds.harvester =
      ids.find((k) => String(k).startsWith("harvester_")) ?? null;
    soloIds.lifter =
      ids.find((k) => String(k).startsWith("orblift_")) ?? null;
  }

  function syncSoloCliFakeBoxes() {
    if (soloExpertFake && soloExpert) {
      soloExpertFake.textContent = soloExpert.checked ? "[x]" : "[ ]";
    }
  }

  function syncExpertPanel() {
    const on = Boolean(soloExpert?.checked);
    if (soloExpertJson) soloExpertJson.disabled = !on;
    if (soloStandardFieldset) soloStandardFieldset.disabled = on;
    syncSoloCliFakeBoxes();
    if (on) syncExpertJsonFromQueue();
  }

  /* ── Move queue editor ───────────────────────────────────────── */

  function syncQueueCountBadge() {
    const n = soloQueue.length;
    // v0.9.9 — the queue is now hard-capped at ``MAX_MOVES`` (21) and
    // every row burns a slot — illegal moves don't get skipped, they
    // get struck through in the replay log so the seat can see what
    // failed without wasting headroom on retries. The badge therefore
    // reads as ``X/21 slots used`` to match the new rule.
    if (soloQueueCount) {
      soloQueueCount.textContent = `${String(n)}/${String(MAX_MOVES)} slots`;
      soloQueueCount.classList.toggle(
        "solo-queue-count--full",
        n >= MAX_MOVES,
      );
    }
    if (ccTabOrdersMeta) {
      ccTabOrdersMeta.textContent = `${String(n)}/${String(MAX_MOVES)}`;
    }
    if (mobileOrdersCountEl) {
      mobileOrdersCountEl.textContent = String(n);
    }
    syncMobileOrdersBar();
  }

  /** v0.9.13 — show the sticky mobile orders bar only once a live game
   *  exists; CSS gates it to the <=900px stacked layout. */
  function syncMobileOrdersBar() {
    if (!mobileOrdersBar) return;
    // v1.0 — no command bar once the season is complete (a finished MP
    // game is view-only) or in the read-only watcher.
    const active =
      !!sessionId && !WATCH_MODE && livePhase !== "season_complete";
    mobileOrdersBar.hidden = !active;
  }

  /** v0.9.13 — map-first mobile sheet. The panels slide up over the map;
   *  these toggle ``body.cc-sheet-open`` (CSS does the transform). On
   *  desktop the class is inert (the sheet rules are ≤900px only). */
  function openMobileSheet() {
    document.body.classList.add("cc-sheet-open");
  }
  function closeMobileSheet() {
    document.body.classList.remove("cc-sheet-open");
  }
  function isMobileSheetOpen() {
    return document.body.classList.contains("cc-sheet-open");
  }

  /** Route the mobile bar's TRANSMIT to whichever commit is live now:
   *  the ORBIT commit when that panel is on-screen, else night/PRAXIS. */
  function mobileTransmitProxy() {
    const orbitBtn = document.getElementById("solo-commit-orbit");
    if (orbitBtn && orbitBtn.offsetParent !== null && !orbitBtn.disabled) {
      orbitBtn.click();
      return;
    }
    if (soloCommitBtn && !soloCommitBtn.disabled) soloCommitBtn.click();
  }

  /** Refresh the small meta labels on the right-edge tab strip. */
  function updateCcTabMeta() {
    if (ccTabReplayMeta) {
      ccTabReplayMeta.textContent =
        replayWindowCount > 0 ? `${String(replayWindowCount)}f` : "·";
    }
  }

  function actionNeedsXY(action) {
    return (
      action === "probe" ||
      action === "drop" ||
      action === "step" ||
      action === "emp_launch" ||
      action === "mine_lay"
    );
  }

  function actionNeedsUnit(action) {
    return action === "drop" || action === "step" || action === "pickup";
  }

  function actionLabel(action) {
    if (action === "probe") return "probe @";
    if (action === "drop") return "drop";
    if (action === "step") return "step";
    if (action === "pickup") return "pickup";
    if (action === "wait") return "wait";
    if (action === "emp_launch") return "EMP @";
    if (action === "mine_lay") return "MINE @";
    if (action === "chaff_flare") return "CHAFF";
    return String(action || "?");
  }

  /** Short, render-safe unit label for the queue row. Falls back to the
   *  raw entity id if no friendlier alias is known. */
  function unitShortLabel(unit) {
    if (!unit) return "??";
    const s = String(unit);
    if (s.startsWith("harvester_")) {
      const tail = s.slice("harvester_".length);
      return `H · ${tail}`;
    }
    if (s.startsWith("orblift_")) {
      const tail = s.slice("orblift_".length);
      return `O · ${tail}`;
    }
    return s;
  }

  /** v0.9.16 — keep every ``chaff_flare`` row trailed by exactly
   *  ``CHAFF_SELF_JAM_SLOTS`` locked "self-jam" rows so a flare visibly
   *  occupies its full 3-turn cost in the composer (the engine jams the
   *  launcher for the carry-over hours regardless). Idempotent + timing
   *  preserving: a plain WAIT already sitting right after a chaff is
   *  *claimed* as a jam slot (that hour is jammed anyway) rather than
   *  net-adding one, so re-running never grows the queue and a deliberate
   *  run of waits keeps its length. Only runs in the point-and-click
   *  composer; EXPERT mode hand-writes its own queue. */
  function normalizeChaffJamRows() {
    if (!Array.isArray(soloQueue) || !soloQueue.length) return;
    // Strip existing jam markers first; we re-derive them below so the
    // pass is fully idempotent regardless of prior reorders/removals.
    const base = soloQueue.filter((m) => m && !m._chaffJam);
    const result = [];
    for (let i = 0; i < base.length; i += 1) {
      const m = base[i];
      result.push(m);
      if (m.a !== "chaff_flare") continue;
      let claimed = 0;
      while (claimed < CHAFF_SELF_JAM_SLOTS && result.length < MAX_MOVES) {
        const nxt = base[i + 1];
        // Absorb a plain trailing WAIT (that hour is jammed anyway) so
        // we never duplicate slots on a round-trip; otherwise insert a
        // fresh locked jam row.
        if (nxt && nxt.a === "wait" && !nxt._chaffJam) i += 1;
        result.push({ a: "wait", _chaffJam: true });
        claimed += 1;
      }
    }
    soloQueue = result.slice(0, MAX_MOVES);
  }

  function renderSoloQueue() {
    if (!soloQueueHost) return;
    // v0.9.16 — reserve the chaff self-jam slots before anything reads
    // the queue length / renders rows (skipped in EXPERT JSON mode).
    if (!soloExpert?.checked) normalizeChaffJamRows();
    // v0.9.15 — the queue changed, so any prior strand acknowledgement
    // is stale; a fresh strand must re-warn before submit.
    strandWarnAcked = false;
    // v0.9.13 — likewise re-arm the full-vault overflow warning.
    vaultFullWarnAcked = false;
    syncQueueCountBadge();
    soloQueueHost.textContent = "";
    // v0.8.0 — keep the ORDERS-tab asset roster's "active" / "invalid"
    // visual state in lockstep with the queue. Cheap to re-render.
    renderOrdersAssetRoster();
    // v0.9.5 — the path-badge overlay on the map mirrors the queue,
    // so a re-render must refresh those badges too. If no unit is
    // currently armed the helper is a no-op.
    paintHarvesterPathBadges();

    if (!soloQueue.length && !soloQueueShowAll) {
      const empty = document.createElement("p");
      empty.className = "dim solo-queue-empty";
      empty.textContent = "# queue empty · add moves below ↓";
      soloQueueHost.appendChild(empty);
      if (soloExpert?.checked) syncExpertJsonFromQueue();
      return;
    }

    // v0.9.5 — when the "show all 21 slots" toggle is on, pad the
    // rendered list with placeholder rows up to ``MAX_MOVES`` so
    // the seat can see the entire night timeline at once. Real
    // moves keep their original queue index; placeholders carry a
    // sentinel ``__placeholder`` flag so the renderer can style and
    // skip the queue-controls for them. Drag-drop targets work
    // against both kinds of row.
    /** @type {Array<{ m: any, ix: number, placeholder: boolean }>} */
    const rows = soloQueue.map((m, ix) => ({ m, ix, placeholder: false }));
    if (soloQueueShowAll) {
      const padTo = MAX_MOVES;
      let nextSlot = soloQueue.length + 1;
      while (rows.length < padTo) {
        rows.push({
          m: { a: "__wait_placeholder", _slot: nextSlot },
          ix: rows.length,
          placeholder: true,
        });
        nextSlot += 1;
      }
    }

    rows.forEach(({ m, ix, placeholder }) => {
      // v0.9.16 — chaff self-jam rows are real queue slots but locked:
      // inert like a show-all placeholder, just labelled as the flare's
      // carry-over jam so the 3-slot cost is explicit.
      const jam = !placeholder && !!(m && m._chaffJam);
      const row = document.createElement("div");
      row.className =
        "solo-queue-row" +
        (placeholder ? " solo-queue-row--placeholder" : "") +
        (jam ? " solo-queue-row--chaff-jam" : "");
      row.dataset.idx = String(ix);
      if (placeholder) row.dataset.placeholder = "1";
      if (jam) row.dataset.chaffJam = "1";
      // v0.9.5 — drag-and-drop reorder. Real queued rows are
      // draggable; placeholder ``(wait)`` rows are NOT draggable
      // (nothing to grab) but remain valid drop targets so the
      // user can drop a real row onto a specific hour. Chaff self-jam
      // rows are likewise non-draggable (they snap back to their flare).
      // ``moveQueueRow`` pads the queue with ``wait`` actions as
      // needed to reach the target slot.
      row.draggable = !placeholder && !jam;
      row.addEventListener("dragstart", (ev) => {
        row.classList.add("solo-queue-row--dragging");
        try {
          if (ev.dataTransfer) {
            ev.dataTransfer.effectAllowed = "move";
            ev.dataTransfer.setData("text/plain", String(ix));
          }
        } catch (_e) { /* Safari occasionally blocks setData */ }
      });
      row.addEventListener("dragend", () => {
        row.classList.remove("solo-queue-row--dragging");
        soloQueueHost
          ?.querySelectorAll(".solo-queue-row--drop-target")
          ?.forEach((n) => n.classList.remove("solo-queue-row--drop-target"));
      });
      row.addEventListener("dragover", (ev) => {
        ev.preventDefault();
        if (ev.dataTransfer) ev.dataTransfer.dropEffect = "move";
        soloQueueHost
          ?.querySelectorAll(".solo-queue-row--drop-target")
          ?.forEach((n) => n.classList.remove("solo-queue-row--drop-target"));
        row.classList.add("solo-queue-row--drop-target");
      });
      row.addEventListener("drop", (ev) => {
        ev.preventDefault();
        row.classList.remove("solo-queue-row--drop-target");
        const fromAttr = ev.dataTransfer?.getData("text/plain");
        const fromIx = fromAttr != null ? Number(fromAttr) : NaN;
        if (!Number.isFinite(fromIx) || fromIx === ix) return;
        moveQueueRow(fromIx, ix);
      });

      const drag = document.createElement("span");
      drag.className = "dim solo-queue-drag";
      drag.textContent = "⋮⋮";
      drag.title = placeholder
        ? "idle slot · drag a queued row here to place it at this hour"
        : jam
          ? "locked · your chaff jams this hour"
          : "drag to reorder";
      row.appendChild(drag);

      const num = document.createElement("span");
      num.className = "dim solo-queue-num";
      // v0.9.5 — slot numbers always reflect the hour-of-night the
      // row will execute against, which is just ``ix + 1`` for both
      // real and placeholder rows in the padded view.
      num.textContent = `${String(ix + 1).padStart(2, " ")}.`;
      row.appendChild(num);

      const label = document.createElement("span");
      label.className = "solo-queue-label";
      if (placeholder) {
        // v0.9.5 — placeholder rows surface the "idle" intent for
        // any hour the seat hasn't filled. The text is intentionally
        // dim and not interactive (no controls below).
        label.classList.add("dim", "solo-queue-label--placeholder");
        label.textContent = "(wait · idle)";
        row.appendChild(label);
        // Placeholders are inert beyond the drag-drop target. No
        // controls, no inputs — just append and move on.
        soloQueueHost.appendChild(row);
        return;
      }
      if (jam) {
        // v0.9.16 — locked chaff carry-over slot. Inert: it shows the
        // self-jam so the flare's 3-turn cost is visible, but carries no
        // controls (it's removed/re-derived with its parent flare).
        label.classList.add("dim", "solo-queue-label--chaff-jam");
        label.textContent = "\u21AF self-jammed (chaff)";
        label.title =
          "Your own chaff jams this hour. A flare occupies 3 slots: "
          + "the launch + 2 self-jammed turns.";
        row.appendChild(label);
        soloQueueHost.appendChild(row);
        return;
      }
      if (actionNeedsUnit(m.a) && m.unit) {
        label.textContent = `${actionLabel(m.a)} · ${unitShortLabel(m.unit)}`;
      } else if (
        m.a === "emp_launch" && Array.isArray(m.ats) && m.ats.length > 1
      ) {
        // v0.9.x — multi-missile salvo: show the count + extra cells.
        const extra = m.ats
          .slice(1)
          .map((t) => `(${t[0]},${t[1]})`)
          .join(" ");
        label.textContent = `EMP salvo ×${m.ats.length} → +${extra}`;
        label.title = m.ats.map((t) => `(${t[0]},${t[1]})`).join("  ");
      } else {
        label.textContent = actionLabel(m.a);
      }
      // Annotate invalid rows so the user sees the issue inline.
      const owned = ownedAssetIds();
      if (actionNeedsUnit(m.a)) {
        if (!m.unit || !owned.has(String(m.unit))) {
          row.classList.add("solo-queue-row--invalid");
          label.title =
            "This unit doesn't exist in your roster — the order will be cancelled.";
        }
      }
      row.appendChild(label);

      if (actionNeedsXY(m.a)) {
        const xWrap = document.createElement("label");
        xWrap.className = "dim solo-queue-xy";
        xWrap.append("x ");
        const xIn = document.createElement("input");
        xIn.type = "number";
        xIn.className = "solo-num-input";
        xIn.value = Number.isFinite(m.x) ? String(m.x) : "";
        xIn.addEventListener("input", () => {
          const v = Number(xIn.value);
          m.x = Number.isFinite(v) ? v : undefined;
          if (soloExpert?.checked) syncExpertJsonFromQueue();
        });
        xWrap.appendChild(xIn);
        row.appendChild(xWrap);

        const yWrap = document.createElement("label");
        yWrap.className = "dim solo-queue-xy";
        yWrap.append("y ");
        const yIn = document.createElement("input");
        yIn.type = "number";
        yIn.className = "solo-num-input";
        yIn.value = Number.isFinite(m.y) ? String(m.y) : "";
        yIn.addEventListener("input", () => {
          const v = Number(yIn.value);
          m.y = Number.isFinite(v) ? v : undefined;
          if (soloExpert?.checked) syncExpertJsonFromQueue();
        });
        yWrap.appendChild(yIn);
        row.appendChild(yWrap);
      }

      const controls = document.createElement("span");
      controls.className = "solo-queue-controls";

      const up = document.createElement("button");
      up.type = "button";
      up.className = "cli-btn solo-queue-mini";
      // v0.8.1 — Unicode arrows (↑ ↓) silently fall back to glyphs
      // missing in many VT-style monospace fonts. Use ASCII-safe
      // ``up`` / ``dn`` text so the controls render consistently
      // across font stacks.
      up.textContent = "[ up ]";
      up.title = "Move this row up";
      up.disabled = ix === 0;
      up.addEventListener("click", () => moveQueueRow(ix, ix - 1));
      controls.appendChild(up);

      const down = document.createElement("button");
      down.type = "button";
      down.className = "cli-btn solo-queue-mini";
      down.textContent = "[ dn ]";
      down.title = "Move this row down";
      down.disabled = ix === soloQueue.length - 1;
      down.addEventListener("click", () => moveQueueRow(ix, ix + 1));
      controls.appendChild(down);

      const rm = document.createElement("button");
      rm.type = "button";
      rm.className = "cli-btn solo-queue-mini";
      rm.textContent = "[ x ]";
      rm.title = "Remove this row";
      rm.addEventListener("click", () => {
        soloQueue.splice(ix, 1);
        renderSoloQueue();
      });
      controls.appendChild(rm);

      row.appendChild(controls);
      soloQueueHost.appendChild(row);
    });

    if (soloExpert?.checked) syncExpertJsonFromQueue();
  }

  function moveQueueRow(from, to) {
    if (to < 0 || from === to) return;
    if (from < 0 || from >= soloQueue.length) return;
    // v0.9.5 — when "show all 21 slots" is on, dropping a real row
    // onto a placeholder ``to`` index that's past the end of the
    // queue pads the queue with explicit ``wait`` moves so the
    // dragged action lands at the requested hour. Without the
    // padding, ``splice`` would silently clip the move to the
    // current tail. The cap is ``MAX_MOVES`` so the seat can't
    // pad beyond the engine's hard cap.
    if (to >= soloQueue.length) {
      const cap = Math.max(0, MAX_MOVES - 1);
      const targetSlot = Math.min(to, cap);
      const [item] = soloQueue.splice(from, 1);
      while (soloQueue.length < targetSlot) {
        soloQueue.push({ a: "wait" });
      }
      soloQueue.splice(targetSlot, 0, item);
      renderSoloQueue();
      return;
    }
    const [item] = soloQueue.splice(from, 1);
    soloQueue.splice(to, 0, item);
    renderSoloQueue();
  }

  function addQueueRow(action, x, y, unit) {
    if (soloQueue.length >= maxQueueLen) return;
    const entry = { a: action };
    if (actionNeedsXY(action)) {
      entry.x = Number.isFinite(x) ? x : undefined;
      entry.y = Number.isFinite(y) ? y : undefined;
    }
    if (actionNeedsUnit(action) && unit) {
      entry.unit = String(unit);
    }
    soloQueue.push(entry);
    renderSoloQueue();
  }

  /** v0.9.x — Max EMP missiles per launch. Mirrors
   *  ``weapons.EMP_MISSILES_PER_LAUNCH``; stashed on window from the
   *  agent view's orbit block when available, else the engine default. */
  function empMaxMissiles() {
    const n = Number(window.__SOC_EMP_MISSILES__);
    return Number.isFinite(n) && n >= 1 ? Math.floor(n) : 3;
  }

  /** Toggle a target cell on the in-progress EMP salvo. Builds (or
   *  updates) a single ``emp_launch`` queue row carrying an ``ats``
   *  list of up to ``empMaxMissiles()`` cells. Auto-stops the picker
   *  when the salvo is full or emptied. */
  function empSalvoToggleTarget(x, y) {
    if (!assetSelect || assetSelect.action !== "emp_launch") return;
    let row = assetSelect.empRow;
    if (!row) {
      if (soloQueue.length >= maxQueueLen) {
        flashHint("order queue full");
        exitAssetSelect();
        return;
      }
      row = { a: "emp_launch", ats: [], x: undefined, y: undefined };
      soloQueue.push(row);
      assetSelect.empRow = row;
    }
    if (!Array.isArray(row.ats)) row.ats = [];
    const idx = row.ats.findIndex(
      (t) => Array.isArray(t) && t[0] === x && t[1] === y,
    );
    if (idx >= 0) {
      row.ats.splice(idx, 1);
    } else if (row.ats.length < empMaxMissiles()) {
      row.ats.push([x, y]);
    } else {
      flashHint(`EMP salvo is full (${empMaxMissiles()} missiles)`);
      return;
    }
    // Mirror the primary target onto x/y for legacy display paths.
    if (row.ats.length) {
      row.x = row.ats[0][0];
      row.y = row.ats[0][1];
    } else {
      // Emptied — drop the row entirely and disarm.
      const at = soloQueue.indexOf(row);
      if (at >= 0) soloQueue.splice(at, 1);
      assetSelect.empRow = null;
      exitAssetSelect();
      renderSoloQueue();
      return;
    }
    renderSoloQueue();
    updateAssetSelectBanner();
    if (row.ats.length >= empMaxMissiles()) {
      // Salvo full — auto-stop so the next click doesn't start adding
      // to a second order by accident.
      assetSelect.empRow = null;
      exitAssetSelect();
    }
  }

  const pickBanner = document.getElementById("pick-mode-banner");
  const pickBannerLabel = document.getElementById("pick-mode-label");

  function enterPickMode(action) {
    pickMode = action;
    if (mapPlayer) mapPlayer.classList.add("map--pick-mode");
    if (pickBannerLabel) pickBannerLabel.textContent = actionLabel(action);
    if (pickBanner) pickBanner.hidden = false;
    // Mobile: drop the sheet so the map is tappable for the target.
    closeMobileSheet();
  }

  function exitPickMode() {
    pickMode = null;
    if (mapPlayer) mapPlayer.classList.remove("map--pick-mode");
    if (pickBanner) pickBanner.hidden = true;
  }

  // ── v0.8.0 asset-first action state machine ─────────────────────
  //
  // The legacy ``[+probe][+drop][+step][+pickup]`` toolbar was
  // replaced with chips: clicking a unit IS the action selector.
  // This state machine tracks "what is the user composing right now"
  // so the next chip / map click can finish the order.
  //
  // Shape:
  //   null
  //   { action: "step",   unit, awaiting: "target" }   // map click expected
  //   { action: "probe",  awaiting: "target" }         // map click expected
  //   { action: "drop",   awaiting: "unit" }           // chip click expected
  //   { action: "drop",   unit, awaiting: "target" }   // map click expected
  //   { action: "pickup", awaiting: "unit" }           // chip click expected
  /** @type {null | { action: string; unit?: string; awaiting: "unit" | "target" }} */
  let assetSelect = null;

  /** Set of entity ids the active seat currently owns (alive).
   *  Drives both the asset-roster render AND the per-row validity
   *  annotation in the queue. Built from the live inventory's
   *  ``assets_by_status`` buckets. */
  function ownedAssetIds() {
    const inv = lastLiveInventory;
    if (!inv || !inv.assets_by_status) return new Set();
    const buckets = inv.assets_by_status;
    const out = new Set();
    for (const k of ["in_orbit", "on_surface"]) {
      const rows = Array.isArray(buckets[k]) ? buckets[k] : [];
      for (const row of rows) {
        if (row && row.alive !== false && row.asset_id) {
          out.add(String(row.asset_id));
        }
      }
    }
    return out;
  }

  /** Look up a roster row by id, attaching the inferred state bucket
   *  (``in_orbit`` / ``on_surface`` / ``destroyed``) so callers can
   *  branch on it. Returns ``null`` when the unit is absent. */
  function findAssetRow(unit) {
    const inv = lastLiveInventory;
    if (!inv || !inv.assets_by_status || !unit) return null;
    const buckets = inv.assets_by_status;
    for (const k of ["in_orbit", "on_surface", "destroyed"]) {
      const rows = Array.isArray(buckets[k]) ? buckets[k] : [];
      for (const row of rows) {
        if (row && String(row.asset_id) === String(unit)) {
          return { ...row, _bucket: k };
        }
      }
    }
    return null;
  }

  /** Mirror of ``_unit_ordinal`` in session.py — derive a 1-based
   *  index from a harvester / probe / orblift id so the UI can
   *  stamp a small numbered subscript tag on each chip (matching
   *  the in-map badge). */
  function unitOrdinal(unitId) {
    if (typeof unitId !== "string") return 1;
    const parts = unitId.split("_");
    if (parts.length >= 3 && ["harvester", "probe", "orblift"].includes(parts[0])) {
      const n = Number(parts[parts.length - 1]);
      if (Number.isFinite(n)) return n;
    }
    return 1;
  }

  /** Extract a [x, y] position from a roster row.
   *  Prefer the live ``current_pos`` (set when the entity is on
   *  surface), fall back to the persisted ``last_seen_x`` /
   *  ``last_seen_y`` from the asset record. */
  function rowPosition(row) {
    if (!row) return null;
    if (Array.isArray(row.current_pos) && row.current_pos.length === 2) {
      const [x, y] = row.current_pos;
      if (x != null && y != null) return [Number(x), Number(y)];
    }
    if (row.last_seen_x != null && row.last_seen_y != null) {
      return [Number(row.last_seen_x), Number(row.last_seen_y)];
    }
    return null;
  }

  /** Project a harvester's state forward through the current
   *  ``soloQueue`` so click handlers can validate the NEXT move
   *  against what the harvester will actually look like at
   *  PRAXIS time — not just its live snapshot.
   *
   *  The rule "a harvester must be dropped AND picked up on the
   *  same night" means a single ORDERS pane often composes
   *  drop → step* → pickup against a unit that's currently in
   *  orbit. Without this projection the UI would refuse to let
   *  the user queue a step after a drop.
   *
   *  @returns {{bucket: "in_orbit"|"on_surface", pos: [number,number]|null}}
   */
  function projectedUnitState(unitId) {
    const row = findAssetRow(unitId);
    let bucket = row?._bucket === "on_surface" ? "on_surface" : "in_orbit";
    let pos = rowPosition(row);
    for (const m of soloQueue) {
      if (!m || m.unit !== unitId) continue;
      if (m.a === "drop") {
        bucket = "on_surface";
        if (Number.isFinite(m.x) && Number.isFinite(m.y)) {
          pos = [Number(m.x), Number(m.y)];
        }
      } else if (m.a === "step") {
        if (Number.isFinite(m.x) && Number.isFinite(m.y)) {
          pos = [Number(m.x), Number(m.y)];
        }
      } else if (m.a === "pickup") {
        bucket = "in_orbit";
        pos = null;
      }
    }
    return { bucket, pos };
  }

  /**
   * v0.9.5 — short label for a queued move's target slot, used by
   * the per-chip plan summarisers. Slot numbers reflect the queue
   * index (1-based) so the user can correlate the chip's plan
   * annotation with the queue rows below.
   *
   * @param {number} ix
   */
  function _slotTag(ix) {
    return `@slot ${String(ix + 1)}`;
  }

  /**
   * v0.9.5 — summarise the queued plan for a single unit, used to
   * render the yellow "// in current plan" annotation below an
   * asset chip. Returns ``null`` when the queue has no moves for
   * the unit so the caller can skip the annotation row entirely.
   * Otherwise returns a short, human-scannable string like:
   *   "dropped @(4,9) · moved 3 steps · picked up"
   *   "moved 2 steps → @(7,9)"
   *   "picked up"
   *
   * @param {string} unitId
   * @returns {string | null}
   */
  function planSummaryForUnit(unitId) {
    if (!unitId) return null;
    let drops = 0;
    let steps = 0;
    let pickups = 0;
    let lastStep = null;
    let dropAt = null;
    for (const m of soloQueue) {
      if (!m || m.unit !== unitId) continue;
      if (m.a === "drop") {
        drops += 1;
        if (Number.isFinite(m.x) && Number.isFinite(m.y)) {
          dropAt = [Number(m.x), Number(m.y)];
        }
      } else if (m.a === "step") {
        steps += 1;
        if (Number.isFinite(m.x) && Number.isFinite(m.y)) {
          lastStep = [Number(m.x), Number(m.y)];
        }
      } else if (m.a === "pickup") {
        pickups += 1;
      }
    }
    if (drops + steps + pickups === 0) return null;
    /** @type {string[]} */
    const bits = [];
    if (drops > 0) {
      bits.push(
        dropAt ? `dropped @(${dropAt[0]},${dropAt[1]})` : "dropped",
      );
    }
    if (steps > 0) {
      const stepLabel = steps === 1 ? "moved 1 step" : `moved ${steps} steps`;
      bits.push(
        lastStep ? `${stepLabel} → @(${lastStep[0]},${lastStep[1]})` : stepLabel,
      );
    }
    if (pickups > 0) bits.push("picked up");
    return bits.join(" · ");
  }

  /**
   * v0.9.5 — summarise every DROP / PICKUP queued through the
   * orblift across all harvesters. Surfaced under the orblift chip
   * so the user can see what the lifter will do this turn at a
   * glance. Returns ``null`` when nothing is queued.
   *
   * @returns {string | null}
   */
  function planSummaryForOrblift() {
    /** @type {string[]} */
    const bits = [];
    soloQueue.forEach((m, ix) => {
      if (!m) return;
      const unit = m.unit ? unitShortLabel(m.unit) : "?";
      if (m.a === "drop") {
        const at =
          Number.isFinite(m.x) && Number.isFinite(m.y)
            ? ` @(${m.x},${m.y})`
            : "";
        bits.push(`drop ${unit}${at} ${_slotTag(ix)}`);
      } else if (m.a === "pickup") {
        bits.push(`pickup ${unit} ${_slotTag(ix)}`);
      }
    });
    return bits.length ? bits.join(" · ") : null;
  }

  /**
   * v0.9.5 — summarise queued probe deploys. Surfaced under the
   * probe stock chip so the seat can see "2 probes → (5,5), (8,10)"
   * before transmitting. Returns ``null`` when none are queued.
   *
   * @returns {string | null}
   */
  function planSummaryForProbes() {
    /** @type {string[]} */
    const hits = [];
    soloQueue.forEach((m, ix) => {
      if (!m || m.a !== "probe") return;
      const at =
        Number.isFinite(m.x) && Number.isFinite(m.y)
          ? `(${m.x},${m.y})`
          : "(?)";
      hits.push(`${at} ${_slotTag(ix)}`);
    });
    if (!hits.length) return null;
    const word = hits.length === 1 ? "probe" : "probes";
    return `${hits.length} ${word} → ${hits.join(", ")}`;
  }

  /**
   * v0.9.5 — summarise queued fires for one weapon ``kind``
   * (``"emp"`` / ``"mine"`` / ``"chaff"``) or padding (``"wait"``).
   * Each hit lists its hour slot so the user can see exactly when
   * the warhead lands relative to other moves.
   *
   * @param {"emp"|"mine"|"chaff"|"wait"} kind
   * @returns {string | null}
   */
  function planSummaryForWeapon(kind) {
    const actionKey =
      kind === "emp" ? "emp_launch"
      : kind === "mine" ? "mine_lay"
      : kind === "chaff" ? "chaff_flare"
      : "wait";
    /** @type {string[]} */
    const hits = [];
    soloQueue.forEach((m, ix) => {
      if (!m || m.a !== actionKey) return;
      if (kind === "emp" || kind === "mine") {
        const at =
          Number.isFinite(m.x) && Number.isFinite(m.y)
            ? `(${m.x},${m.y})`
            : "(?)";
        hits.push(`${at} ${_slotTag(ix)}`);
      } else {
        hits.push(_slotTag(ix));
      }
    });
    if (!hits.length) return null;
    const label =
      kind === "emp" ? "EMP"
      : kind === "mine" ? "MINE"
      : kind === "chaff" ? "CHAFF"
      : "WAIT";
    return `${hits.length}× ${label} · ${hits.join(", ")}`;
  }

  /**
   * v0.9.5 — wrap an arbitrary chip element with a yellow "// in
   * current plan:" annotation underneath it. Mirrors the layout
   * used by ``buildOrdersHarvesterChip`` so every chip in the
   * ORDERS roster shares the same visual contract. Returns the
   * wrap div (the chip ALWAYS sits at the top; the plan note is
   * appended below when ``planText`` is non-empty).
   *
   * Callers pass ``planText = null`` to skip the annotation (the
   * wrap is still emitted so flex layout stays consistent across
   * chips with and without plans). Pass ``extraClass`` to add a
   * variant class for kind-specific styling.
   *
   * @param {HTMLElement} chip
   * @param {string | null} planText
   * @param {{ extraClass?: string }} [opts]
   */
  function wrapChipWithPlan(chip, planText, opts) {
    const wrap = document.createElement("div");
    wrap.className =
      "cc-orders-chip-wrap" +
      (opts?.extraClass ? ` ${opts.extraClass}` : "");
    wrap.appendChild(chip);
    if (planText) {
      const note = document.createElement("div");
      note.className = "cc-orders-chip-plan";
      const tag = document.createElement("span");
      tag.className = "cc-orders-chip-plan-tag";
      tag.textContent = "// in current plan:";
      const txt = document.createElement("span");
      txt.className = "cc-orders-chip-plan-txt";
      txt.textContent = ` ${planText}`;
      note.append(tag, txt);
      wrap.appendChild(note);
    }
    return wrap;
  }

  function enterAssetSelect(spec) {
    assetSelect = spec;
    if (mapPlayer) mapPlayer.classList.add("map--pick-mode");
    if (pickBannerLabel) {
      pickBannerLabel.textContent = describeAssetSelect(spec);
    }
    if (pickBanner) pickBanner.hidden = false;
    renderOrdersAssetRoster();
    paintHarvesterPathBadges();
    // Mobile: drop the sheet so the map is tappable for the target.
    closeMobileSheet();
  }

  function exitAssetSelect() {
    assetSelect = null;
    if (mapPlayer) mapPlayer.classList.remove("map--pick-mode");
    if (pickBanner) pickBanner.hidden = true;
    renderOrdersAssetRoster();
    paintHarvesterPathBadges();
  }

  /** Refresh the picker banner label from the current assetSelect
   *  state (used while composing a multi-cell EMP salvo). */
  function updateAssetSelectBanner() {
    if (pickBannerLabel && assetSelect) {
      pickBannerLabel.textContent = describeAssetSelect(assetSelect);
    }
  }

  /** v0.9.5 — paint numbered path badges on the map showing the
   *  queued waypoints for the harvester currently armed in the
   *  picker. The first badge is the unit's projected starting cell
   *  (live pos if surfaced, or the cell of a queued ``drop`` if
   *  the unit is still in orbit), then every queued ``step`` adds
   *  a numbered marker. The badges live on ``collisionFxLayer``
   *  (same overlay surface used by mines / EMP markers / collision
   *  rings) so they sit ABOVE the map cells without blocking
   *  clicks. */
  // v0.9.13 — planned-orders overlay. Draws EVERY queued action on the live
  // player map: each harvester's chained path (anchor → steps → drop →
  // pickup), plus standalone markers for probe deploys and weapon targets.
  // Recomputed on queue change, map repaint, and zoom. Replaces the old
  // single-armed-unit path renderer; ``paintHarvesterPathBadges`` is kept as a
  // back-compat alias for the existing call sites.

  /** Bounding rect for the map cell at (x,y), or null when off-grid / fogged. */
  function _orderCellRect(x, y) {
    if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
    const cell = mapPlayer.querySelector(`[data-x="${x}"][data-y="${y}"]`);
    return cell ? cell.getBoundingClientRect() : null;
  }

  /** Seat id (``p1``..``p4``) parsed from a unit id like
   *  ``harvester_p2_3`` so the path can be drawn in that player's colour
   *  rather than an arbitrary per-unit hue. */
  function _unitOwner(unitId) {
    const parts = String(unitId).split("_");
    return parts.find((p) => /^p\d+$/.test(p)) || null;
  }

  /** Reconstruct one harvester's waypoint chain from its live position +
   *  every queued move that references it. */
  function _unitWaypoints(unitId) {
    const waypoints = [];
    const row = findAssetRow(unitId);
    let pos = null;
    if (row && row._bucket === "on_surface") {
      pos = rowPosition(row);
      if (pos) waypoints.push({ x: pos[0], y: pos[1], kind: "anchor" });
    }
    for (const m of soloQueue) {
      if (!m || String(m.unit) !== unitId) continue;
      if (m.a === "drop" && Number.isFinite(m.x) && Number.isFinite(m.y)) {
        pos = [Number(m.x), Number(m.y)];
        waypoints.push({ x: pos[0], y: pos[1], kind: "drop" });
      } else if (m.a === "step" && Number.isFinite(m.x) && Number.isFinite(m.y)) {
        pos = [Number(m.x), Number(m.y)];
        waypoints.push({ x: pos[0], y: pos[1], kind: "step" });
      } else if (m.a === "pickup" && pos) {
        waypoints.push({ x: pos[0], y: pos[1], kind: "pickup" });
      }
    }
    return waypoints;
  }

  function _drawUnitPath(unitId, hostRect, dimmed) {
    const waypoints = _unitWaypoints(unitId);
    if (waypoints.length === 0) return;
    const color = ownerColor(_unitOwner(unitId));

    // Assign the move ordinal up front: landing reads as 0, each step
    // 1..N, and the pickup re-uses the final step number (it lifts from
    // wherever the chain ended).
    let stepIx = 0;
    const items = waypoints.map((wp) => {
      if (wp.kind === "step") return { ...wp, num: ++stepIx };
      if (wp.kind === "drop") return { ...wp, num: 0 };
      if (wp.kind === "pickup") return { ...wp, num: stepIx };
      return { ...wp, num: null };
    });
    // The pickup triangle REPLACES the square of the step it lifts from,
    // so drop any step badge sharing the pickup's cell.
    const pickup = items.find((it) => it.kind === "pickup");
    const renderItems = pickup
      ? items.filter(
          (it) => !(it.kind === "step" && it.x === pickup.x && it.y === pickup.y),
        )
      : items;

    // Thin dashed connector legs first (under the badges via z-index) so
    // the eye reads the path as one continuous chain.
    for (let i = 1; i < waypoints.length; i++) {
      const ra = _orderCellRect(waypoints[i - 1].x, waypoints[i - 1].y);
      const rb = _orderCellRect(waypoints[i].x, waypoints[i].y);
      if (!ra || !rb) continue;
      const ax = ra.left + ra.width / 2 - hostRect.left;
      const ay = ra.top + ra.height / 2 - hostRect.top;
      const bx = rb.left + rb.width / 2 - hostRect.left;
      const by = rb.top + rb.height / 2 - hostRect.top;
      const dx = bx - ax;
      const dy = by - ay;
      const len = Math.hypot(dx, dy);
      if (len < 1) continue;
      const leg = document.createElement("div");
      leg.className = "harvester-path-leg" + (dimmed ? " harvester-path-leg--dim" : "");
      leg.style.left = `${ax}px`;
      leg.style.top = `${ay}px`;
      leg.style.width = `${len}px`;
      leg.style.transform = `rotate(${Math.atan2(dy, dx)}rad)`;
      leg.style.setProperty("--cc-path-col", color);
      collisionFxLayer.appendChild(leg);
    }

    // Badges on top — square strokes for steps, big numbered triangles
    // for the landing + pickup, all in the owning player's colour.
    for (const it of renderItems) {
      const rect = _orderCellRect(it.x, it.y);
      if (!rect) continue;
      const badge = document.createElement("div");
      badge.className =
        `harvester-path-badge harvester-path-badge--${it.kind}` +
        (dimmed ? " harvester-path-badge--dim" : "");
      badge.style.left = `${rect.left - hostRect.left}px`;
      badge.style.top = `${rect.top - hostRect.top}px`;
      badge.style.width = `${Math.ceil(rect.width)}px`;
      badge.style.height = `${Math.ceil(rect.height)}px`;
      badge.style.color = color;

      if (it.kind === "anchor") {
        badge.textContent = "\u25CB"; // ○ current position
      } else if (it.kind === "step") {
        const num = document.createElement("span");
        num.className = "hp-step-num";
        num.textContent = String(it.num);
        badge.appendChild(num);
      } else {
        // drop (landing) + pickup: down-triangle filled in the player
        // colour with the ordinal punched out in the map-background colour.
        const tri = document.createElement("span");
        tri.className = "hp-tri";
        tri.style.background = color;
        badge.appendChild(tri);
        const num = document.createElement("span");
        num.className = "hp-tri-num";
        num.textContent = String(it.num);
        badge.appendChild(num);
      }
      collisionFxLayer.appendChild(badge);
    }
  }

  function _drawOrderMarker(x, y, kind, glyph, hostRect) {
    const rect = _orderCellRect(x, y);
    if (!rect) return;
    const el = document.createElement("div");
    el.className = `cc-order-marker cc-order-marker--${kind}`;
    el.style.left = `${rect.left - hostRect.left}px`;
    el.style.top = `${rect.top - hostRect.top}px`;
    el.style.width = `${Math.ceil(rect.width)}px`;
    el.style.height = `${Math.ceil(rect.height)}px`;
    el.textContent = glyph;
    collisionFxLayer.appendChild(el);
  }

  function paintPlannedOrdersOverlay() {
    if (!collisionFxLayer || !mapPlayer) return;
    collisionFxLayer
      .querySelectorAll(".harvester-path-badge, .harvester-path-leg, .cc-order-marker")
      .forEach((n) => n.remove());
    // Only meaningful on the live player's own map (not replay scrubbing).
    if (mainMapSource !== "live") return;
    const armedUnit =
      assetSelect && assetSelect.unit ? String(assetSelect.unit) : null;
    if (!soloQueue.length && !armedUnit) return;

    const hostRect = collisionFxLayer.getBoundingClientRect();

    // 1) Harvester paths, grouped by unit. The armed unit (the one you're
    //    actively chaining) draws solid; the rest dim so it stands out.
    const units = [];
    for (const m of soloQueue) {
      if (m && (m.a === "drop" || m.a === "step" || m.a === "pickup") && m.unit) {
        const u = String(m.unit);
        if (!units.includes(u)) units.push(u);
      }
    }
    if (
      armedUnit &&
      !units.includes(armedUnit) &&
      (assetSelect.action === "step" || assetSelect.action === "drop")
    ) {
      units.push(armedUnit);
    }
    units.forEach((u) =>
      _drawUnitPath(u, hostRect, armedUnit ? u !== armedUnit : false),
    );

    // 2) Probe deploys + weapon targets (standalone cell markers).
    for (const m of soloQueue) {
      if (!m) continue;
      if (m.a === "probe") {
        _drawOrderMarker(Number(m.x), Number(m.y), "probe", "\u25CF", hostRect); // ● circle
      } else if (m.a === "mine_lay") {
        _drawOrderMarker(Number(m.x), Number(m.y), "mine", "\u25C6", hostRect); // ◆ rhombus
      } else if (m.a === "emp_launch" && Array.isArray(m.ats)) {
        m.ats.forEach((t) => {
          if (Array.isArray(t)) {
            _drawOrderMarker(Number(t[0]), Number(t[1]), "emp", "\u25CF", hostRect); // ● cyan circle
          }
        });
      }
    }
  }

  /** Back-compat alias — existing call sites refresh the overlay via this. */
  function paintHarvesterPathBadges() {
    paintPlannedOrdersOverlay();
  }

  function describeAssetSelect(spec) {
    if (!spec) return "";
    if (spec.action === "probe") return "click a cell to deploy probe";
    if (spec.action === "step")
      return `path · ${unitShortLabel(spec.unit)} → click neighbour to chain · [stop] when done`;
    if (spec.action === "drop") {
      if (spec.awaiting === "unit")
        return "drop · click an in-orbit harvester chip";
      return `drop · ${unitShortLabel(spec.unit)} → click landing cell · chains into steps`;
    }
    if (spec.action === "pickup") {
      if (spec.awaiting === "unit")
        return "pickup · click an on-surface harvester chip";
      return `pickup · ${unitShortLabel(spec.unit)}`;
    }
    // v0.9 — weapon targeting prompts.
    if (spec.action === "emp_launch") {
      const n = spec.empRow && Array.isArray(spec.empRow.ats)
        ? spec.empRow.ats.length
        : 0;
      const max = empMaxMissiles();
      if (n <= 0)
        return `EMP salvo · click up to ${max} target tiles · click chip to fire`;
      return `EMP salvo · ${n}/${max} targets · click more, re-click to remove, or chip to fire`;
    }
    if (spec.action === "mine_lay")
      return "mine_lay · click target tile (lays a hidden cluster)";
    return spec.action || "";
  }

  function clearQueue() {
    soloQueue = [];
    strandWarnAcked = false;
    vaultFullWarnAcked = false;
    renderSoloQueue();
  }

  /** v0.9.15 — harvesters that, after the queued moves are applied, are
   *  still projected to sit ON THE SURFACE at PRAXIS time. The planet
   *  destroys every non-probe surface unit at dawn (RULEBOOK §3.11.2),
   *  so these will be lost unless a pickup is queued. Human-only guard
   *  (the solo/p1 submit path). */
  function strandedHarvesterIds() {
    const out = [];
    for (const id of ownedAssetIds()) {
      if (!String(id).startsWith("harvester")) continue;
      if (projectedUnitState(String(id)).bucket === "on_surface") {
        out.push(String(id));
      }
    }
    return out;
  }

  /** v0.9.13 — full-vault overflow guard (human-only). When the vault
   *  is already at capacity and a queued pickup will return a harvester
   *  carrying parcels, the §3.14 deposit cascade keeps only the best
   *  parcels and jettisons the rest. Returns a warning string (with the
   *  offending harvesters + projected cargo) or ``null`` when nothing is
   *  at risk. The agent gets the equivalent signal via
   *  ``hud.hoard.warning`` (engine), so this only covers the human seat.
   *  Note the projected cargo is an upper bound: it sums the harvester's
   *  current hold plus its queued drop/step moves (each colour harvested
   *  banks one parcel), capped at the 6-parcel hold. */
  function fullVaultPickupWarning() {
    const inv = lastLiveInventory;
    if (!inv || !Array.isArray(inv.hoard)) return null;
    const used = inv.hoard.length;
    const cap = Number(inv.hoard_capacity) || HOARD_CAP_FALLBACK;
    if (!cap || used < cap) return null; // only when the vault is FULL

    const pickedUp = new Set();
    for (const m of soloQueue) {
      if (m && m.a === "pickup" && m.unit) pickedUp.add(String(m.unit));
    }
    if (!pickedUp.size) return null;

    const offenders = [];
    for (const unit of pickedUp) {
      if (!unit.startsWith("harvester")) continue;
      const row = findAssetRow(unit);
      const cargoNow =
        row && Number.isFinite(Number(row.current_cargo_count))
          ? Number(row.current_cargo_count)
          : 0;
      let harvestMoves = 0;
      for (const m of soloQueue) {
        if (m && (m.a === "drop" || m.a === "step") && String(m.unit) === unit) {
          harvestMoves += 1;
        }
      }
      const incoming = Math.min(6, cargoNow + harvestMoves);
      if (incoming > 0) offenders.push({ unit, incoming });
    }
    if (!offenders.length) return null;

    const list = offenders
      .map((o) => `${o.unit} (${o.incoming} parcel${o.incoming === 1 ? "" : "s"})`)
      .join(", ");
    return (
      `\u26A0 vault is FULL (${used}/${cap}) \u2014 ${list} will return into ` +
      `it; the \u00A73.14 cascade keeps only the BEST parcels and jettisons ` +
      `the rest to space. Click TRANSMIT again to proceed.`
    );
  }

  /** Convert UI rows → wire moves. Each row carries its own ``unit``
   *  (v0.8.0 — was a single global ``hvId`` in v0.7.x). Bad/missing
   *  coords or unit IDs become ``waste`` markers; the server still
   *  rejects them with a yellow log line. */
  function queueToWireMoves() {
    return soloQueue.map((m) => {
      if (m.a === "probe") {
        if (!Number.isFinite(m.x) || !Number.isFinite(m.y))
          return { a: "probe", at: [Number.NaN, Number.NaN] };
        return { a: "probe", at: [Number(m.x), Number(m.y)] };
      }
      const unit = m.unit ? String(m.unit) : null;
      if (m.a === "drop") {
        if (!unit) return { a: "waste", reason: "drop missing unit" };
        return {
          a: "drop",
          unit,
          at: [Number(m.x), Number(m.y)],
        };
      }
      if (m.a === "step") {
        if (!unit) return { a: "waste", reason: "step missing unit" };
        return {
          a: "step",
          unit,
          to: [Number(m.x), Number(m.y)],
        };
      }
      if (m.a === "pickup") {
        if (!unit) return { a: "waste", reason: "pickup missing unit" };
        return { a: "pickup", unit };
      }
      // v0.9 — Weapons & WAIT (RULEBOOK §4.9). Mirror the engine's
      // policy parser: ``wait`` carries no payload; ``emp_launch`` /
      // ``mine_lay`` carry an [x, y] target; ``chaff_flare`` is
      // payload-free.
      if (m.a === "wait") return { a: "wait" };
      if (m.a === "emp_launch") {
        // v0.9.x — salvo: ``ats`` carries 1-3 target cells. Emit a list
        // ``at: [[x,y], ...]`` for a multi-missile launch, or a plain
        // ``[x,y]`` for a single target (back-compat with the engine).
        const ats = Array.isArray(m.ats)
          ? m.ats.filter(
              (t) =>
                Array.isArray(t) &&
                Number.isFinite(Number(t[0])) &&
                Number.isFinite(Number(t[1])),
            )
          : [];
        if (ats.length > 1) {
          return {
            a: "emp_launch",
            at: ats.map((t) => [Number(t[0]), Number(t[1])]),
          };
        }
        if (ats.length === 1) {
          return { a: "emp_launch", at: [Number(ats[0][0]), Number(ats[0][1])] };
        }
        if (!Number.isFinite(m.x) || !Number.isFinite(m.y))
          return { a: "waste", reason: "emp_launch missing target" };
        return { a: "emp_launch", at: [Number(m.x), Number(m.y)] };
      }
      if (m.a === "mine_lay") {
        if (!Number.isFinite(m.x) || !Number.isFinite(m.y))
          return { a: "waste", reason: "mine_lay missing target" };
        return { a: "mine_lay", at: [Number(m.x), Number(m.y)] };
      }
      if (m.a === "chaff_flare") return { a: "chaff_flare" };
      return { a: "waste" };
    });
  }

  function syncExpertJsonFromQueue() {
    if (!soloExpertJson) return;
    soloExpertJson.value = JSON.stringify(queueToWireMoves(), null, 2);
  }

  function buildSoloMoves() {
    return queueToWireMoves();
  }

  /** @param {any[] | object} hintJson */
  function applyHintQueue(hintJson) {
    const arr = Array.isArray(hintJson) ? hintJson : hintJson?.moves;
    if (!Array.isArray(arr)) return;
    soloQueue = arr.slice(0, maxQueueLen).map((entry) => {
      if (!entry || typeof entry !== "object") return { a: "pickup" };
      const action = String(entry.a || entry.action || "").toLowerCase();
      const unit = entry.unit ? String(entry.unit) : undefined;
      if (action === "probe") {
        const at = Array.isArray(entry.at) ? entry.at : [];
        return { a: "probe", x: Number(at[0]), y: Number(at[1]) };
      }
      if (action === "drop") {
        const at = Array.isArray(entry.at) ? entry.at : [];
        return { a: "drop", x: Number(at[0]), y: Number(at[1]), unit };
      }
      if (action === "step") {
        const to = Array.isArray(entry.to) ? entry.to : [];
        return { a: "step", x: Number(to[0]), y: Number(to[1]), unit };
      }
      return { a: "pickup", unit };
    });
    renderSoloQueue();
  }

  /** @param {any[] | object} fragment */
  function mergePolicySnippet(fragment) {
    if (!soloExpertJson) return;
    soloExpert && (soloExpert.checked = true);
    syncExpertPanel();
    const arr = Array.isArray(fragment) ? fragment : fragment?.moves;
    soloExpertJson.value = JSON.stringify(
      Array.isArray(arr) ? arr : fragment,
      null,
      2,
    );
  }

  /** @param {any} hints */
  function prefetchSoloDefaultsFromHints(hints) {
    lastHints = hints ?? null;
    // No auto-fill — user adds orders manually
  }

  /** @param {any} hints */
  function renderPolicyHints(hints) {
    const host = document.getElementById("policy-hints-player");
    if (!host) return;
    host.innerHTML = "";
    if (
      !hints ||
      typeof hints !== "object" ||
      !Array.isArray(hints.quick_inserts)
    )
      return;

    const heading = document.createElement("span");
    heading.className = "policy-hints-label dim";
    const ids =
      Array.isArray(hints.entity_ids) ?
        hints.entity_ids.join(", ")
      : "";
    heading.textContent = `# presets · ${ids || "—"}`;
    host.appendChild(heading);

    for (const qi of hints.quick_inserts) {
      if (!qi || !qi.label || qi.json == null) continue;
      const b = document.createElement("button");
      b.type = "button";
      b.className = "hint-chip";
      b.textContent = qi.label || qi.id || "snippet";
      b.addEventListener("click", () => {
        ingestEntityIds(hints);
        if (soloExpert?.checked) mergePolicySnippet(qi.json);
        else applyHintQueue(qi.json);
        syncSoloCliFakeBoxes();
      });
      host.appendChild(b);
    }
  }

  /** @returns {Promise<Record<string, any>>} */
  async function postPolicy(pid, moves) {
    const res = await fetch(`/api/game/${sessionId}/policy`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ player: pid, moves }),
      cache: "no-store",
    });
    const out = await res.json().catch(() => ({}));
    if (!res.ok) {
      const detail = out.detail;
      const detailStr =
        typeof detail === "string" ?
          detail
        : Array.isArray(detail) ?
          detail.map((d) => d.msg || JSON.stringify(d)).join("; ")
        : JSON.stringify(detail ?? out);
      throw new Error(detailStr || `HTTP ${res.status}`);
    }
    if (!out.ok) {
      throw new Error(
        (Array.isArray(out.errors) ? out.errors.join("; ") : null) ||
          "policy rejected",
      );
    }
    return out;
  }

  /** POST an orbit action queue (module-level twin of the inline submit in
   *  submitSoloOrbit) so the agent-resubmit scheduler can retry it. */
  async function postOrbitActions(pid, actions) {
    const res = await fetch(`/api/game/${sessionId}/orbit`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ player: pid, actions }),
      cache: "no-store",
    });
    const out = await res.json().catch(() => ({}));
    if (!res.ok || out.ok === false) {
      throw new Error(
        (Array.isArray(out.errors) ? out.errors.join("; ") : null) ||
          `orbit ${pid} failed`,
      );
    }
    return out;
  }

  /** v1.11 — the non-blocking slow (agent) submit returns ``agent_busy`` when
   *  the agent was mid-turn holding the game lock, so our moves were NOT
   *  stashed. Keep retrying (short cadence) until the agent frees the lock and
   *  our submit lands; then either the resolution rides in inline or the
   *  live-sync poller reveals it. Bounded so a stuck agent can't retry forever. */
  function _scheduleAgentResubmit(seat, payload, mode, attempt = 0) {
    if (attempt > 90) return; // ~ several minutes of 900ms retries — safety cap
    window.setTimeout(async () => {
      if (!_awaitingHumanResolution || !sessionId) return; // resolved/cleared
      inFlightSubmit = true; // block pollLiveSync during the retry POST
      let body = null;
      try {
        body = mode === "orbit"
          ? await postOrbitActions(seat, payload)
          : await postPolicy(seat, payload);
      } catch (_e) {
        inFlightSubmit = false;
        _scheduleAgentResubmit(seat, payload, mode, attempt + 1);
        return;
      }
      inFlightSubmit = false;
      if (body && body.agent_busy) {
        _scheduleAgentResubmit(seat, payload, mode, attempt + 1);
        return;
      }
      // Stashed. Clear the composer queue so a later phase starts clean.
      if (mode === "orbit") clearOrbitQueue(); else clearQueue();
      const resolved = mode === "orbit" ? body?.orbit_resolved : body?.night_resolved;
      if (resolved) {
        clearHumanWaitFrame();
        try { await pullAllMaps({ playFx: true }); } catch (_e) { /* ignore */ }
      }
      // else: stashed, agent still finishing — pollLiveSync resolves + animates.
    }, 900);
  }

  function soloMovesForSubmit() {
    if (soloExpert?.checked && soloExpertJson && soloExpertJson.value.trim()) {
      try {
        const parsed = JSON.parse(soloExpertJson.value.trim());
        if (Array.isArray(parsed)) return parsed;
        if (parsed && Array.isArray(parsed.moves)) return parsed.moves;
        throw new Error("expert JSON must be an array of moves");
      } catch (e) {
        throw new Error(`Expert JSON: ${e.message || e}`);
      }
    }
    return buildSoloMoves();
  }

  /**
   * Fire one agent turn for a given seat.
   *
   * Shared core used by:
   *   * the single-turn button (p1 only, partner auto-locked empty),
   *   * the autoplay loop (p1 only, partner auto-locked empty),
   *   * the VERSUS loop (called twice per night: once for p1, once
   *     for p2, no auto-lock because the second call resolves the night).
   *
   * Does NOT touch button state — callers manage their own UI. DOES
   * surface the rationale to the LOG and (optionally) re-pull maps.
   *
   * @param {{
   *   player?: "p1"|"p2",
   *   runtime?: "heuristic"|"cortex"|null,
   *   autoLockPartner?: boolean,
   *   refreshMaps?: boolean,
   * }} opts
   */
  async function runAgentTurnOnce({
    player = "p1",
    runtime = null,
    autoLockPartner = true,
    refreshMaps = true,
    timeoutMs = 90000,
    // When a loop (autoplay / versus) drives the per-turn status banner
    // itself, it passes statusMeta so this core function can stamp the
    // banner with the correct turn N/M while transitioning through the
    // observable phases. Single-turn callers can leave it null and we
    // still surface every phase, just without a turn number.
    statusMeta = null,
  } = {}) {
    if (!sessionId) {
      throw new Error("no active session");
    }
    const qs = new URLSearchParams({ player });
    if (runtime) qs.set("runtime", runtime);
    // Surface the phase before we even open the socket — the
    // Snowflake-cold-start case can spend a few seconds in TLS / auth
    // before any bytes flow, and the user shouldn't think we hung.
    const phaseRuntime = statusMeta?.runtime ?? runtime;
    const turnArg = statusMeta?.turn ?? null;
    const totalArg = statusMeta?.total ?? null;
    setAgentStatus({
      state: "working",
      runtime: phaseRuntime,
      turn: turnArg,
      total: totalArg,
      phase:
        phaseRuntime === "cortex"
          ? `contacting Snowflake Cortex (${player})…`
          : `running RED_HARVEST (${player})…`,
      detail: null,
      resetElapsed: statusMeta?.resetElapsed !== false,
    });
    // Wrap the fetch in an AbortController so a wedged Snowflake call
    // surfaces as a normal error after ``timeoutMs`` instead of hanging
    // the UI forever. 90s is generous for a single agent turn even on
    // a cold Snowflake warehouse, but stops "press once and stare at a
    // frozen button" pathologies dead.
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), timeoutMs);
    let res;
    try {
      // Once the request is actually in flight, swap the phase to
      // "thinking" — this is where the bulk of the wall-clock time
      // sits (10-90s for Cortex, ~5-10s for RED_HARVEST).
      setAgentStatus({
        state: "working",
        phase:
          phaseRuntime === "cortex"
            ? `AI AGENT thinking… (${player})`
            : `RED_HARVEST thinking… (${player})`,
      });
      res = await fetch(
        `/api/game/${sessionId}/agent/think?${qs.toString()}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          cache: "no-store",
          signal: ctl.signal,
        },
      );
    } catch (e) {
      if (e && e.name === "AbortError") {
        setAgentStatus({
          state: "error",
          phase: `timed out after ${Math.round(timeoutMs / 1000)}s`,
          detail: `${player} (${phaseRuntime ?? "agent"})`,
        });
        throw new Error(
          `agent/think timed out after ${Math.round(timeoutMs / 1000)}s ` +
          `(${player}) — Snowflake backend may be cold; try again or ` +
          `switch SOC_BACKEND=memory for snappier iteration`
        );
      }
      setAgentStatus({
        state: "error",
        phase: `fetch failed: ${e.message || e}`,
        detail: `${player} (${phaseRuntime ?? "agent"})`,
      });
      throw e;
    } finally {
      clearTimeout(timer);
    }
    setAgentStatus({
      state: "working",
      phase: `parsing response (${player})…`,
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok || !body.ok) {
      const detail = body.detail ?? body.error ?? `HTTP ${res.status}`;
      const detailStr =
        typeof detail === "string" ? detail : JSON.stringify(detail);
      setAgentStatus({
        state: "error",
        phase: `agent error (${player})`,
        detail: detailStr,
      });
      throw new Error(detailStr || "agent failed");
    }
    // Append rationale to the log panel so the user sees what the
    // agent thought — server already logged it server-side too, but
    // surfacing it on-screen is the whole point of the button.
    if (orchLogEl && body.rationale) {
      const line = document.createElement("div");
      line.className = "log-line log-line--agent";
      // Server tells us *who* actually played — RED_HARVEST for the
      // heuristic, or whichever AI agent name when SOC_AGENT_RUNTIME=
      // cortex is in effect. Fall back to RED_HARVEST so the log line
      // never goes nameless on an older server.
      const who = body.agent_id || "RED_HARVEST";
      const runtimeTag = body.runtime ? `[${body.runtime}] ` : "";
      line.textContent = `[${who}] ${runtimeTag}(${player}) ${body.rationale}`;
      orchLogEl.appendChild(line);
      orchLogEl.scrollTop = orchLogEl.scrollHeight;
      // v0.7.5 — also pipe into the structured agent bucket so the
      // AGENT panel (per-seat sub-tabs) renders this turn's rationale
      // without parsing the log scrollback.
      captureAgentRationale({
        ts: Date.now(),
        day: Number(body.day) || (lastLiveInventory?.day ?? 0),
        seat: player,
        agent_id: who,
        runtime: body.runtime || "",
        text: body.response_text || body.rationale,
        ms_elapsed: body.ms_elapsed,
        tool_calls: body.tool_calls,
      });
      renderAgentFeed();
    }
    // SOLO MODE PARITY: the human's [TRANSMIT] button auto-locks the
    // *other* seat with an empty queue so the night resolves
    // immediately. The single-turn / autoplay buttons inherit this so
    // a one-click "agent move" actually advances the night. The
    // VERSUS loop opts out (autoLockPartner=false) because it submits
    // a real policy for the other seat itself.
    //
    // v0.9.7 — only do this hard-pair in 2-seat sessions. For 3- and
    // 4-seat games the assumption "the OTHER seat is the only other
    // seat" is wrong and would leave p3/p4 stuck. Skip the empty-
    // policy partner lock and let the main PRAXIS button (or another
    // /agent/think call) drive the remaining seats explicitly.
    let nightResolved = Boolean(body.night_resolved);
    const knownSeats =
      Array.isArray(window.__SOC_LAST_NEWGAME__?.players)
        ? window.__SOC_LAST_NEWGAME__.players
        : ["p1", "p2"];
    if (autoLockPartner && !nightResolved && knownSeats.length === 2) {
      const partner = player === "p1" ? "p2" : "p1";
      setAgentStatus({
        state: "working",
        phase: `auto-locking ${partner} (empty policy) for PRAXIS…`,
      });
      try {
        const lockBody = await postPolicy(partner, []);
        nightResolved =
          Boolean(lockBody?.night_resolved) ||
          Boolean(lockBody?.resolved) ||
          nightResolved;
      } catch (e) {
        setAgentStatus({
          state: "error",
          phase: `${partner} auto-lock failed`,
          detail: e.message || String(e),
        });
        if (errSoloEl) {
          errSoloEl.textContent =
            `! agent ok, but ${partner} auto-lock failed: ` + (e.message || e);
          errSoloEl.hidden = false;
        }
        throw e;
      }
    }
    if (refreshMaps) {
      setAgentStatus({ state: "working", phase: "refreshing maps…" });
      await pullAllMaps({ playFx: true });
    }
    // Final "done" stamp so the user can see the turn landed cleanly —
    // includes a one-line summary of what the agent actually did.
    const moveCount = Array.isArray(body.moves) ? body.moves.length : 0;
    setAgentStatus({
      state: "done",
      phase:
        nightResolved
          ? `PRAXIS resolved (${player} · ${moveCount} move${moveCount === 1 ? "" : "s"})`
          : `${player} policy submitted (${moveCount} move${moveCount === 1 ? "" : "s"})`,
      detail: (body.rationale || "").slice(0, 140),
    });
    return { ...body, night_resolved: nightResolved };
  }

  /**
   * Single-turn click handler — manages button state, then delegates
   * to the shared core. Kept thin so the autoplay loop can reuse the
   * exact same per-turn behaviour without ever fighting the button.
   *
   * Reads the AGENT: dropdown so a click of LET THE AGENT PLAY runs
   * whichever runtime the user picked (heuristic by default, Cortex
   * when they want to see the AI agent reason).
   */
  async function runAgentTurn() {
    if (!sessionId || !errSoloEl || !soloAgentBtn) return;
    errSoloEl.hidden = true;
    soloAgentBtn.disabled = true;
    const prevLabel = soloAgentBtn.textContent;
    const runtime = selectedAgentRuntime();
    const runtimeLabel = runtime === "cortex" ? "AI AGENT" : "RED_HARVEST";
    soloAgentBtn.textContent = `[ ... ${runtimeLabel} thinking ]`;
    try {
      await runAgentTurnOnce({
        runtime,
        statusMeta: { runtime, turn: 1, total: 1, resetElapsed: true },
      });
    } catch (e) {
      if (!errSoloEl.textContent) {
        errSoloEl.textContent = "! " + (e.message || e);
        errSoloEl.hidden = false;
      }
    } finally {
      soloAgentBtn.textContent = prevLabel;
      soloAgentBtn.disabled = false;
    }
  }

  // ── Autoplay loop ────────────────────────────────────────────────
  //
  // Controls for the "[ >> AUTOPLAY ]" button. The loop runs
  // ``runAgentTurnOnce`` back-to-back up to ``max_turns`` times, and
  // the button itself doubles as a kill switch: clicking again while
  // the loop is active flips ``autoplayCancel`` so the next iteration
  // bails out cleanly (we never abort mid-fetch, which would risk
  // half-submitting a policy and bricking a seat).
  let autoplayRunning = false;
  let autoplayCancel = false;

  function setAutoplayLabel(turn, total, base, suffix = "") {
    if (!soloAgentAutoplayBtn) return;
    if (autoplayRunning) {
      const tail = suffix ? ` ${suffix}` : "";
      soloAgentAutoplayBtn.textContent =
        `[ \u25A0 STOP \u00B7 ${turn}/${total}${tail} ]`;
    } else {
      soloAgentAutoplayBtn.textContent = base;
    }
  }

  // ── Versus loop (AI agent vs RED_HARVEST) ────────────────────────
  //
  // Per night: run an AI agent on p1 (white seat) and RED_HARVEST on
  // p2 (yellow seat). Each call goes through the same ``/agent/think``
  // endpoint, just with a different ``?runtime=...`` override. The
  // first call locks p1; the second call lands a real policy for p2
  // and — since both seats are now ready — resolves the night.
  // Cortex failures gracefully fall back to RED_HARVEST inside
  // ``run_agent_turn``, so the loop still progresses end-to-end even
  // when no PAT is configured (you'll just see "RED_HARVEST vs
  // RED_HARVEST" in the LOG, which is also useful for sanity checks).
  let versusRunning = false;
  let versusCancel = false;

  // Initial render of the VERSUS button label now that versusRunning
  // has been initialised (it's read inside refreshVersusButtonLabel,
  // so calling earlier would TDZ-fault). Safe to call repeatedly.
  refreshVersusButtonLabel();

  function setVersusLabel(turn, total, base, suffix = "") {
    if (!soloAgentVersusBtn) return;
    if (versusRunning) {
      const tail = suffix ? ` ${suffix}` : "";
      soloAgentVersusBtn.textContent =
        `[ \u25A0 STOP \u00B7 ${turn}/${total}${tail} ]`;
    } else {
      soloAgentVersusBtn.textContent = base;
    }
  }

  async function runAgentVersus() {
    console.debug("[versus] click", {
      hasSession: !!sessionId,
      hasErrEl: !!errSoloEl,
      hasBtn: !!soloAgentVersusBtn,
      running: versusRunning,
    });
    if (!soloAgentVersusBtn) {
      console.warn("[versus] button element missing — listener mis-wired");
      return;
    }
    if (!sessionId) {
      if (errSoloEl) {
        errSoloEl.textContent =
          "! versus needs an active session — press NEW GAME first";
        errSoloEl.hidden = false;
      }
      return;
    }
    if (versusRunning) {
      versusCancel = true;
      return;
    }
    const maxTurns = Math.max(
      1,
      parseInt(soloAgentVersusBtn.dataset.maxTurns ?? "10", 10) || 10,
    );
    // Read the matchup BEFORE we lock the loop so the dropdowns can be
    // disabled below and the user can't change midway. Each seat's
    // chosen runtime drives that seat's `/agent/think` call each night.
    const matchup = selectedVersusMatchup();
    const baseLabel =
            `[ >> ${runtimeShortLabel(matchup.p1)} vs ${runtimeShortLabel(matchup.p2)} · ${maxTurns} Nox ]`;
    versusRunning = true;
    versusCancel = false;
    if (errSoloEl) errSoloEl.hidden = true;
    if (soloAgentBtn) soloAgentBtn.disabled = true;
    if (soloAgentAutoplayBtn) soloAgentAutoplayBtn.disabled = true;
    if (soloVersusP1) soloVersusP1.disabled = true;
    if (soloVersusP2) soloVersusP2.disabled = true;
    setVersusLabel(0, maxTurns, baseLabel);

    let i = 0;
    let lastP2 = null;
    try {
      for (i = 1; i <= maxTurns; i += 1) {
        if (versusCancel) break;
        setVersusLabel(i, maxTurns, baseLabel);
        // Mark the night in the LOG so the user can see progress while
        // a 30-60s Cortex call is in flight.
        if (orchLogEl) {
          const line = document.createElement("div");
          line.className = "log-line log-line--agent";
          line.textContent =
            `[versus] Nox ${i}/${maxTurns}: ` +
            `${runtimeShortLabel(matchup.p1)} (p1) vs ` +
            `${runtimeShortLabel(matchup.p2)} (p2)…`;
          orchLogEl.appendChild(line);
          orchLogEl.scrollTop = orchLogEl.scrollHeight;
        }
        // p1 — whichever runtime the user selected for the white seat.
        // run_agent_turn() will gracefully fall back to RED_HARVEST on
        // the server if cortex is asked for but no PAT is configured.
        // We don't auto-lock the partner because the next call below
        // submits p2 for real. refreshMaps stays default (true) so the
        // status pane shows "p1 locked, p2 pending" while p2 thinks.
        await runAgentTurnOnce({
          player: "p1",
          runtime: matchup.p1,
          autoLockPartner: false,
          statusMeta: {
            runtime: matchup.p1,
            turn: i,
            total: maxTurns,
            resetElapsed: true,
          },
        });
        if (versusCancel) break;
        // p2 — whichever runtime the user selected for the yellow seat.
        // Submitting this second seat is what flips both_ready() to
        // True and resolves the night inside the engine. The map
        // repaint after this call shows the resolved-night state.
        lastP2 = await runAgentTurnOnce({
          player: "p2",
          runtime: matchup.p2,
          autoLockPartner: false,
          statusMeta: {
            runtime: matchup.p2,
            turn: i,
            total: maxTurns,
            // Don't reset elapsed — keep the night's total wall-clock
            // visible so e.g. "AI 62s + RED_HARVEST 8s" both contribute.
            resetElapsed: false,
          },
        });
        const phase = lastP2?.submit_result?.phase ?? lastP2?.phase;
        if (
          phase === "season_complete" ||
          phase === "game_over" ||
          phase === "ended"
        ) {
          break;
        }
      }
    } catch (e) {
      setAgentStatus({
        state: "error",
        phase: `versus stopped at Nox ${i}`,
        detail: e.message || String(e),
      });
      if (!errSoloEl.textContent) {
        errSoloEl.textContent =
          "! versus stopped at Nox " + i + ": " + (e.message || e);
        errSoloEl.hidden = false;
      }
    } finally {
      if (versusCancel) {
        setAgentStatus({
          state: "done",
          phase: `versus STOPPED at Nox ${i} / ${maxTurns}`,
        });
      } else if (
        agentStatusEl &&
        agentStatusEl.dataset.state === "working"
      ) {
        setAgentStatus({
          state: "done",
          phase: `versus complete · ${i} Nox`,
        });
      }
      versusRunning = false;
      versusCancel = false;
      if (soloAgentBtn) soloAgentBtn.disabled = false;
      if (soloAgentAutoplayBtn) soloAgentAutoplayBtn.disabled = false;
      if (soloVersusP1) soloVersusP1.disabled = false;
      if (soloVersusP2) soloVersusP2.disabled = false;
      // Restore the matchup-aware label so the user sees the next
      // matchup they're about to run (they may have changed the
      // dropdowns mid-loop — wait, we disabled them, never mind — but
      // this still re-renders cleanly if they switch immediately).
      refreshVersusButtonLabel();
      try {
        await pullAllMaps({ playFx: true });
      } catch (_) {
        /* swallow */
      }
    }
  }

  async function runAgentAutoplay() {
    // Always log so the user can verify the click reached us at all
    // (useful when debugging "nothing happens" reports — open DevTools
    // and watch the console). The console line is also our breadcrumb
    // for the silent early-return branches below.
    console.debug("[autoplay] click", {
      hasSession: !!sessionId,
      hasErrEl: !!errSoloEl,
      hasBtn: !!soloAgentAutoplayBtn,
      running: autoplayRunning,
    });
    if (!soloAgentAutoplayBtn) {
      console.warn("[autoplay] button element missing — listener mis-wired");
      return;
    }
    if (!sessionId) {
      // Silently no-op'ing here was the cause of "press autoplay,
      // nothing happens" — there was just no game yet. Surface it.
      if (errSoloEl) {
        errSoloEl.textContent =
          "! autoplay needs an active session — press NEW GAME first";
        errSoloEl.hidden = false;
      }
      return;
    }
    if (!errSoloEl) {
      console.warn("[autoplay] err-solo element missing");
      // We can still try to run, just no inline error UI.
    }
    // Toggle behaviour: if already running, the click is a cancel.
    if (autoplayRunning) {
      autoplayCancel = true;
      return;
    }
    const maxTurns = Math.max(
      1,
      parseInt(soloAgentAutoplayBtn.dataset.maxTurns ?? "10", 10) || 10,
    );
    const runtime = selectedAgentRuntime();
    const runtimeLabel = runtime === "cortex" ? "AI AGENT" : "RED_HARVEST";
    const baseLabel = soloAgentAutoplayBtn.textContent ?? "[ >> AUTOPLAY ]";
    autoplayRunning = true;
    autoplayCancel = false;
    if (errSoloEl) errSoloEl.hidden = true;
    if (soloAgentBtn) soloAgentBtn.disabled = true;
    if (soloAgentRuntime) soloAgentRuntime.disabled = true;
    setAutoplayLabel(0, maxTurns, baseLabel);

    let lastBody = null;
    let i = 0;
    // Snowflake backend = many round trips per turn → seconds each.
    // Show an elapsed-seconds badge inside the button so the user knows
    // we're alive even when a single turn takes 15-30s on cold Snowpark.
    let tickHandle = null;
    function startTick() {
      const startedAt = Date.now();
      stopTick();
      tickHandle = setInterval(() => {
        const elapsed = Math.round((Date.now() - startedAt) / 1000);
        setAutoplayLabel(i, maxTurns, baseLabel, `\u00B7 ${elapsed}s`);
      }, 1000);
    }
    function stopTick() {
      if (tickHandle != null) {
        clearInterval(tickHandle);
        tickHandle = null;
      }
    }
    try {
      for (i = 1; i <= maxTurns; i += 1) {
        if (autoplayCancel) break;
        setAutoplayLabel(i, maxTurns, baseLabel, "\u00B7 thinking");
        startTick();
        // Announce the turn in the LOG panel BEFORE the network call so
        // the user has a visible breadcrumb while we wait for Snowflake.
        // Without this, the only feedback during a 30-60s Cortex turn
        // was the elapsed-seconds badge on the button — easy to miss.
        if (orchLogEl) {
          const line = document.createElement("div");
          line.className = "log-line log-line--agent";
          line.textContent =
            `[autoplay] turn ${i}/${maxTurns}: ${runtimeLabel} thinking…`;
          orchLogEl.appendChild(line);
          orchLogEl.scrollTop = orchLogEl.scrollHeight;
        }
        // refreshMaps = true (default) so each completed turn repaints
        // the map, day counter, hoard count, and replay panel. The
        // "batched refresh at the end" optimisation was hiding all the
        // mid-loop progress — the per-turn refresh adds ~1s on top of a
        // 10-60s agent call, which is a great trade for live updates.
        //
        // statusMeta drives the dedicated agent status banner: every
        // turn resets the elapsed counter and re-stamps the runtime /
        // turn / total so the user can see exactly which iteration is
        // in flight without having to read the squished button label.
        lastBody = await runAgentTurnOnce({
          runtime,
          statusMeta: {
            runtime,
            turn: i,
            total: maxTurns,
            resetElapsed: true,
          },
        });
        stopTick();
        // Terminal-phase guard: when Phase 2 lands the engine will
        // flip to ``season_complete`` after the cap. Stop early so
        // we don't keep hammering the seat past end-of-season.
        const phase = lastBody?.submit_result?.phase ?? lastBody?.phase;
        if (
          phase === "season_complete" ||
          phase === "game_over" ||
          phase === "ended"
        ) {
          break;
        }
      }
    } catch (e) {
      stopTick();
      setAgentStatus({
        state: "error",
        phase: `autoplay stopped at turn ${i}`,
        detail: e.message || String(e),
      });
      if (errSoloEl && !errSoloEl.textContent) {
        errSoloEl.textContent =
          "! autoplay stopped at turn " + i + ": " + (e.message || e);
        errSoloEl.hidden = false;
      }
    } finally {
      stopTick();
      // If the loop ran to completion without errors, mark the banner
      // as "done" so the pulsing animation stops. The user-initiated
      // cancel path also lands here; show a clear STOPPED message.
      if (autoplayCancel) {
        setAgentStatus({
          state: "done",
          phase: `autoplay STOPPED at turn ${i} / ${maxTurns}`,
        });
      } else if (
        agentStatusEl &&
        agentStatusEl.dataset.state === "working"
      ) {
        setAgentStatus({
          state: "done",
          phase: `autoplay complete · ${i} turn${i === 1 ? "" : "s"}`,
        });
      }
      autoplayRunning = false;
      autoplayCancel = false;
      if (soloAgentBtn) soloAgentBtn.disabled = false;
      if (soloAgentRuntime) soloAgentRuntime.disabled = false;
      soloAgentAutoplayBtn.textContent = baseLabel;
      // One batched refresh so the maps reflect the final state.
      try {
        await pullAllMaps();
      } catch (_) {
        /* swallow — the per-turn errors already surfaced */
      }
    }
  }

  /* ── v0.8.0 ORBIT panel helpers ─────────────────────────────────── */

  /** Human-friendly summary of an Orbit action for the queue UI. */
  function describeOrbitAction(a) {
    if (!a || typeof a !== "object") return JSON.stringify(a);
    switch (a.a) {
      case "build_harvester":
        return "build harvester (1500c)";
      case "build_probe": {
        const n = Math.max(1, Number(a.count || 1));
        return n > 1
          ? `build probes \u00D7${n} (${n * 250}c)`
          : "build probes \u00D71 (250c)";
      }
      case "repair":
        return `repair ${a.unit || "?"} (500c)`;
      // v0.9.3 — three build-weapons actions. Each enqueues the
      // batch count + the per-unit blue+credit cost so the seat can
      // eyeball the wallet hit before TRANSMIT.
      case "build_emp": {
        const n = Math.max(1, Number(a.count || 1));
        return `build EMP \u00D7${n} (${n * 200}b/${n * 250}c)`;
      }
      case "build_mine": {
        const n = Math.max(1, Number(a.count || 1));
        return `build MINE \u00D7${n} (${n * 100}b/${n * 100}c)`;
      }
      case "build_chaff": {
        const n = Math.max(1, Number(a.count || 1));
        return `build CHAFF \u00D7${n} (${n * 255}b)`;
      }
      default:
        return JSON.stringify(a);
    }
  }

  /** v1.2 — per-action wallet cost (credits + blue), mirroring the
   *  engine's declared-order locking model (RULEBOOK §4.3). Prices come
   *  off the live ``ship_prices`` block when present, falling back to
   *  the canonical constants. */
  function orbitActionCost(a) {
    const prices = (lastOrbitView && lastOrbitView.ship_prices) || {};
    const HARV = Number(prices.harvester_build ?? 1500);
    const PROBE = Number(prices.probe_build ?? 250);
    const REPAIR = Number(prices.repair ?? 500);
    const out = { cr: 0, blue: 0 };
    if (!a || typeof a !== "object") return out;
    switch (a.a) {
      case "build_harvester":
        out.cr = HARV;
        break;
      case "build_probe": {
        const n = Math.max(1, Number(a.count || 1));
        out.cr = PROBE * n;
        // v1.2 — probes partial-fill (buy what's affordable), so the
        // projector needs the per-unit cost + count to mirror the
        // engine's unit-by-unit purchase.
        out.units = { each: PROBE, count: n };
        break;
      }
      case "repair":
        out.cr = REPAIR;
        break;
      case "build_emp": {
        const n = Math.max(1, Number(a.count || 1));
        out.cr = 250 * n;
        out.blue = 200 * n;
        break;
      }
      case "build_mine": {
        const n = Math.max(1, Number(a.count || 1));
        out.cr = 100 * n;
        out.blue = 100 * n;
        break;
      }
      case "build_chaff": {
        const n = Math.max(1, Number(a.count || 1));
        out.blue = 255 * n;
        break;
      }
      default:
        break;
    }
    return out;
  }

  /** v1.13 — "what your vault does when you hit TRANSMIT".
   *
   *  Settlement is automatic, so the orbit panel has no control for it —
   *  but a player still needs to see it coming, especially the green
   *  penalty, which is the only way the board takes points off you.
   *  Reads the same view fields the panel readouts already use, and
   *  prices RED off ``ship_prices.quality_mult`` so a retune of the tier
   *  multipliers doesn't need a change here. */
  function _updateSettlementPreview(orbitView, tierCounts) {
    const redEl = document.getElementById("cc-settle-red");
    const greenEl = document.getElementById("cc-settle-green");
    if (!redEl && !greenEl) return;
    const mult = (orbitView && orbitView.ship_prices
      && orbitView.ship_prices.quality_mult)
      || window.__SOC_QUALITY_MULT__
      || { trace: 0.75, vein: 1.0, mass: 1.5, pure: 3.0 };
    if (redEl) {
      const tc = tierCounts || {};
      const n = ["trace", "vein", "mass", "pure"]
        .reduce((s, k) => s + (Number(tc[k]) || 0), 0);
      if (!n) {
        redEl.textContent = "no RED to ship";
        redEl.classList.add("dim");
      } else {
        // Purity isn't broken down per tier in the view, so quote the
        // spread of multipliers in play rather than inventing a total
        // the settlement might not match.
        const best = ["pure", "mass", "vein", "trace"]
          .find((k) => Number(tc[k]) > 0);
        redEl.textContent =
          `${n} RED ship for score \u00B7 best tier ${best} \u00D7${mult[best] ?? 1}`;
        redEl.classList.remove("dim");
      }
    }
    if (greenEl) {
      const g = Number(orbitView && orbitView.green_owned_count) || 0;
      const per = Number(
        (orbitView && orbitView.settlement
          && orbitView.settlement.green_penalty) ?? 100,
      );
      if (!g) {
        greenEl.textContent = "no GREEN to dump";
        greenEl.classList.add("dim");
      } else {
        greenEl.textContent = `${g} GREEN dumped \u00B7 \u2212${g * per} score`;
        greenEl.classList.remove("dim");
      }
    }
  }

  /** v1.2 — simulate the engine's declared-order locking over the
   *  queued orbit actions to project the seat's end-of-turn wallet
   *  (credits + blue). Build and repair debit atomically (an
   *  unaffordable one is rejected whole); a batched build fills unit by
   *  unit until the credits run out. Returns the running remainder, the
   *  total over-spend, and a per-row flag array so the queue can mark
   *  dropped / partially-filled orders. */
  function projectOrbitBudget() {
    const startCr = Math.max(0, Number(lastOrbitView?.credits ?? 0));
    const startBlue = Math.max(0, Number(lastOrbitView?.blue_purity_total ?? 0));
    let cr = startCr;
    let blue = startBlue;
    let overCr = 0;
    let overBlue = 0;
    const flags = [];
    orbitQueue.forEach((a, ix) => {
      const cost = orbitActionCost(a);
      if (cost.units && cost.units.count > 1) {
        // v1.2 — uniform-unit build (probes): buy as many as the wallet
        // covers, mirroring the engine's partial fill. A trimmed order
        // is flagged "partial" (not dropped) unless ZERO units fit.
        const each = Math.max(0, Number(cost.units.each) || 0);
        const want = Math.max(1, Number(cost.units.count) || 1);
        let bought = 0;
        for (let u = 0; u < want; u += 1) {
          if (cr >= each) {
            cr -= each;
            bought += 1;
          } else {
            overCr += each;
          }
        }
        if (bought === 0) {
          flags[ix] = { kind: "drop", note: `dropped · needs ${each}c` };
        } else if (bought < want) {
          flags[ix] = { kind: "partial", note: `buys ${bought}/${want}` };
        } else {
          flags[ix] = null;
        }
      } else {
        const okCr = cr >= cost.cr;
        const okBlue = blue >= cost.blue;
        if (okCr && okBlue) {
          cr -= cost.cr;
          blue -= cost.blue;
          flags[ix] = null;
        } else {
          if (!okCr) overCr += cost.cr;
          if (!okBlue) overBlue += cost.blue;
          const needs = [];
          if (!okCr) needs.push(`${cost.cr}c`);
          if (!okBlue) needs.push(`${cost.blue}b`);
          flags[ix] = { kind: "drop", note: `dropped · needs ${needs.join("/")}` };
        }
      }
    });
    return { startCr, cr, overCr, startBlue, blue, overBlue, flags };
  }

  /** v1.2 — repaint the ORBIT CREDITS / BLUE readouts with the
   *  projected end-of-turn remainder in brackets (and a warn tint when
   *  the queue overspends). Returns the projection so callers can reuse
   *  the per-row flags without recomputing. */
  function updateOrbitBudgetProjection(proj) {
    const p = proj || projectOrbitBudget();
    const queued = orbitQueue.length > 0;
    if (orbitCreditsEl) {
      let txt = `${p.startCr}c`;
      if (queued && (p.cr !== p.startCr || p.overCr > 0)) {
        txt += ` (\u2192${p.cr}c${p.overCr > 0 ? `, ${p.overCr} over` : ""})`;
      }
      orbitCreditsEl.textContent = txt;
      orbitCreditsEl.classList.toggle(
        "cc-orbit-readout-value--over",
        queued && p.overCr > 0,
      );
    }
    const blueTotalEl = document.getElementById("cc-orbit-blue-total");
    if (blueTotalEl) {
      let txt = `${p.startBlue}`;
      if (queued && (p.blue !== p.startBlue || p.overBlue > 0)) {
        txt += ` \u2192${p.blue}${p.overBlue > 0 ? ` (${p.overBlue} over)` : ""}`;
      }
      blueTotalEl.textContent = txt;
      blueTotalEl.classList.toggle(
        "cc-orbit-readout-value--over",
        queued && p.overBlue > 0,
      );
    }
    return p;
  }

  function renderOrbitQueue() {
    if (!orbitQueueHost) return;
    orbitQueueHost.textContent = "";
    if (!orbitQueue.length) {
      const empty = document.createElement("div");
      empty.className = "dim solo-queue-empty";
      empty.textContent = "// no actions queued — daytime is free.";
      orbitQueueHost.appendChild(empty);
    } else {
      // Project the wallet across the whole queue first so each row can
      // surface whether it'll be dropped / partially shipped at PRAXIS.
      const proj = projectOrbitBudget();
      orbitQueue.forEach((a, ix) => {
        const row = document.createElement("div");
        const flag = proj.flags[ix];
        row.className =
          "solo-queue-row" +
          (flag?.kind === "drop" ? " solo-queue-row--drop" : "") +
          (flag?.kind === "partial" ? " solo-queue-row--partial" : "");
        const num = document.createElement("span");
        num.className = "dim solo-queue-num";
        num.textContent = `${ix + 1}.`;
        const label = document.createElement("span");
        label.className = "solo-queue-label";
        label.textContent = describeOrbitAction(a);
        const note = document.createElement("span");
        note.className = "solo-queue-note";
        if (flag?.note) note.textContent = `⚠ ${flag.note}`;
        const drop = document.createElement("button");
        drop.type = "button";
        drop.className = "cli-btn cc-add-btn cc-clear-btn solo-queue-drop";
        drop.textContent = "[ x ]";
        drop.title = "Remove this action";
        drop.addEventListener("click", () => {
          orbitQueue.splice(ix, 1);
          renderOrbitQueue();
        });
        row.append(num, label, note, drop);
        orbitQueueHost.appendChild(row);
      });
      // Mirror the same projection into the CREDITS / BLUE readouts.
      updateOrbitBudgetProjection(proj);
    }
    if (!orbitQueue.length) updateOrbitBudgetProjection();
    // v1.13 — bare count, not "n/3". The action cap is gone; credits are
    // the limit, and the budget projection above already shows those.
    const n = orbitQueue.length;
    if (orbitQueueCount) orbitQueueCount.textContent = `${n}`;
    if (orbitTabMeta) orbitTabMeta.textContent = `${n}`;
    // Keep the orbital-station vault in step with the queue. Skip in
    // replay — the queue is a live-only concept.
    if (mainMapSource !== "replay") {
      try { repaintVaultForActiveSeat(); } catch (_e) { /* non-fatal */ }
      try {
        if (typeof window.osRefreshLiveVault === "function") {
          window.osRefreshLiveVault();
        }
      } catch (_e) { /* non-fatal */ }
    }
  }

  function clearOrbitQueue() {
    orbitQueue = [];
    renderOrbitQueue();
  }

  function isFinalOrbitView() {
    return !!(lastOrbitView && lastOrbitView.final_orbit);
  }

  /** Build an Orbit action dict from the toolbar button.
   *
   *  v1.13 — every action left here is a purchase, so all but ``repair``
   *  resolve synchronously off the button. Repair still opens a picker
   *  because it needs a unit id; it is the last of what were once four
   *  composer dialogs (ship / green flush / refine went with their
   *  mechanics). */
  function makeOrbitActionFromButton(kind) {
    switch (kind) {
      case "build_harvester":
        return { a: "build_harvester" };
      case "build_probe": {
        // v0.9.1 — batch probe builds. The companion <input> next to
        // the button carries the count; clamp to [1, 20] so a stray
        // 999 doesn't accidentally torch every credit in the seat's
        // wallet.
        const input = document.getElementById("solo-orbit-probe-count");
        let n = 1;
        if (input) {
          n = Math.max(1, Math.min(20, Number.parseInt(input.value, 10) || 1));
        }
        return n > 1 ? { a: "build_probe", count: n } : { a: "build_probe" };
      }
      case "repair": {
        openRepairSubmit();
        return null;
      }
      // v0.9.3 — Build-weapon actions read their count from the
      // matching numeric input. Same "batch or single" wire shape
      // as ``build_probe``: ``count`` is omitted when 1 to keep
      // older parsers happy.
      case "build_emp":
      case "build_mine":
      case "build_chaff": {
        const slot = kind.replace("build_", "");
        const input = document.getElementById(`solo-orbit-${slot}-count`);
        let n = 1;
        if (input) {
          n = Math.max(
            1, Math.min(10, Number.parseInt(input.value, 10) || 1),
          );
        }
        return n > 1 ? { a: kind, count: n } : { a: kind };
      }
      default:
        return null;
    }
  }

  function updateOrbitReadouts(orbitView) {
    if (!orbitView) return;
    // Base credits text; ``updateOrbitBudgetProjection`` (called at the
    // end) appends the projected end-of-turn remainder when the queue
    // has costed actions.
    if (orbitCreditsEl)
      orbitCreditsEl.textContent = `${orbitView.credits ?? 0}c`;
    if (orbitProbeStockEl)
      orbitProbeStockEl.textContent = String(orbitView.probe_stock ?? 0);
    if (orbitHarvestersEl)
      orbitHarvestersEl.textContent = `${orbitView.harvester_cap_used ?? 0}/${
        orbitView.harvester_cap_max ?? 3
      }`;
    if (orbitGreenEl)
      orbitGreenEl.textContent = `${orbitView.green_owned_count ?? 0} (\u03A3${
        orbitView.green_owned_purity_total ?? 0
      }p)`;
    // v1.13 — the RED tier pill is now a settlement preview rather than
    // a refine-affordance readout: these are the parcels that will ship
    // on resolve, broken down by the tier multiplier each will score at.
    const tc = (orbitView && orbitView.tier_counts) || {};
    const tierEl = document.getElementById("cc-orbit-tier-counts");
    if (tierEl) {
      tierEl.textContent =
        `trace ${tc.trace ?? 0} \u00B7 vein ${tc.vein ?? 0} \u00B7 mass ${tc.mass ?? 0} \u00B7 pure ${tc.pure ?? 0}`;
    }
    _updateSettlementPreview(orbitView, tc);
    // v0.9.5 — BLUE tier readout. Engine ships the same trace/vein/
    // mass/pure tier shape; the UI prefers the colloquial BLUE band
    // names (shallow / mid / sink / deep) so the watcher doesn't
    // have to remember that "blue trace" = shallow water.
    const bc = (orbitView && orbitView.blue_tier_counts) || {};
    const blueEl = document.getElementById("cc-orbit-blue-tier-counts");
    if (blueEl) {
      blueEl.textContent =
        `shallow ${bc.trace ?? 0} \u00B7 mid ${bc.vein ?? 0} \u00B7 sink ${bc.mass ?? 0} \u00B7 deep ${bc.pure ?? 0}`;
    }
    const blueTotalEl = document.getElementById("cc-orbit-blue-total");
    if (blueTotalEl)
      blueTotalEl.textContent = String(orbitView.blue_purity_total ?? 0);
    // v0.9.5 — render the assets roster + repair affordance count.
    // ``assets`` shipped via unit_summary_for_owner. Each row already
    // carries ``damaged``, ``pos``, ``orbit``, ``carrying_red`` so
    // the panel can paint each unit's status without further
    // cross-referencing.
    const assets = Array.isArray(orbitView && orbitView.assets)
      ? orbitView.assets
      : [];
    const harvesters = assets.filter(
      (/** @type {any} */ a) => a && a.type === "harvester",
    );
    const probes = assets.filter(
      (/** @type {any} */ a) => a && a.type === "probe",
    );
    const lifters = assets.filter(
      (/** @type {any} */ a) => a && a.type === "orblift",
    );
    const damagedCount = harvesters.reduce(
      (/** @type {number} */ acc, /** @type {any} */ a) =>
        acc + (a.damaged ? 1 : 0),
      0,
    );
    document
      .querySelectorAll("[data-orbit-damaged-count]")
      .forEach((el) => {
        el.textContent = String(damagedCount);
      });
    document
      .querySelectorAll('[data-orbit-action="repair"]')
      .forEach((b) => {
        b.classList.toggle("is-disabled", damagedCount === 0);
      });
    const assetsListEl = document.getElementById("cc-orbit-assets-list");
    const assetsSubEl = document.getElementById("cc-orbit-assets-sub");
    if (assetsListEl) {
      assetsListEl.textContent = "";
      const rows = [];
      for (const h of harvesters) {
        const loc = h.orbit
          ? "orbit"
          : Array.isArray(h.pos)
            ? `surface (${h.pos[0]},${h.pos[1]})`
            : "surface";
        const flags = [];
        if (h.damaged) flags.push("DAMAGED");
        if (h.carrying_red) flags.push("carrying RED");
        if (h.cargo_squares) flags.push(`${h.cargo_squares} cargo`);
        const tail = flags.length ? ` \u00B7 ${flags.join(" \u00B7 ")}` : "";
        rows.push({
          key: h.id,
          cls: h.damaged ? "is-damaged" : "",
          text: `X  ${h.label || h.id} \u00B7 ${loc}${tail}`,
        });
      }
      for (const lf of lifters) {
        const loc = lf.orbit ? "orbit" : "surface";
        const flags = [];
        if (lf.orbital_cargo_red) flags.push("holding RED");
        const tail = flags.length ? ` \u00B7 ${flags.join(" \u00B7 ")}` : "";
        rows.push({
          key: lf.id,
          cls: "",
          text: `\u25B2  ${lf.label || lf.id} \u00B7 ${loc}${tail}`,
        });
      }
      const probeStock = Number(orbitView.probe_stock || 0);
      if (probes.length || probeStock > 0) {
        const probeDeployed = probes.length;
        // Show per-probe expiry when lifetime knob is active.
        const minNr = probes.reduce((/** @type {number} */ m, /** @type {any} */ p) => {
          const nr = typeof p.nights_remaining === "number" ? p.nights_remaining : Infinity;
          return Math.min(m, nr);
        }, Infinity);
        const expiryNote = Number.isFinite(minNr)
          ? ` \u00B7 ${minNr <= 1 ? "\u26A0\uFE0F " : ""}soonest expires in ${minNr}N`
          : "";
        rows.push({
          key: "probes",
          cls: "is-stock" + (Number.isFinite(minNr) && minNr <= 1 ? " is-urgent" : ""),
          text:
            `\u00B7  probes \u00B7 ${probeDeployed} deployed \u00B7 ` +
            `${probeStock} in stock${expiryNote}`,
        });
      }
      for (const r of rows) {
        const li = document.createElement("li");
        li.className = `cc-orbit-asset ${r.cls}`;
        li.dataset.assetId = r.key;
        li.textContent = r.text;
        assetsListEl.appendChild(li);
      }
      if (assetsSubEl) {
        const pieces = [];
        pieces.push(
          `${harvesters.length}/${orbitView.harvester_cap_max ?? 3} harvesters`,
        );
        if (damagedCount) pieces.push(`${damagedCount} damaged`);
        pieces.push(`${lifters.length} lifters`);
        pieces.push(`${probes.length} probes deployed`);
        assetsSubEl.textContent = pieces.join(" \u00B7 ");
      }
    }
    const probeInput = document.getElementById("solo-orbit-probe-count");
    const probeChip = document.querySelector("[data-orbit-probe-count]");
    if (probeInput && probeChip) {
      const n = Math.max(1, Math.min(20, Number.parseInt(probeInput.value, 10) || 1));
      probeChip.textContent = String(n);
    }
    // v0.9.3 — render the weapon-stockpile readout and mirror each
    // build-weapon button's count chip from its numeric input. The
    // readout carries three chips (EMP / MINE / CHAFF) so the player
    // can see at a glance how many of each are in the magazine without
    // opening the Orders pane.
    const ws = (orbitView && orbitView.weapon_stock) || {};
    ["emp", "mine", "chaff"].forEach((slot) => {
      const stockEl = document.querySelector(
        `[data-weapon-stock-count="${slot}"]`,
      );
      if (stockEl) stockEl.textContent = String(ws[slot] ?? 0);
      const countInput = document.getElementById(`solo-orbit-${slot}-count`);
      const countChip = document.querySelector(
        `[data-orbit-weapon-count="${slot}"]`,
      );
      if (countInput && countChip) {
        const n = Math.max(
          1, Math.min(10, Number.parseInt(countInput.value, 10) || 1),
        );
        countChip.textContent = String(n);
      }
    });
    // v1.2 — overlay the projected end-of-turn wallet (credits + blue)
    // based on the currently-queued orbit actions, so the seat can see
    // what they'll have left BEFORE committing.
    updateOrbitBudgetProjection();
  }

  async function submitSoloOrbit() {
    if (!sessionId || !orbitCommitBtn) return;
    if (orbitErr) orbitErr.hidden = true;
    orbitCommitBtn.disabled = true;
    // v0.8.1 — same density-shade animation as the night transmit,
    // with an orbit-flavoured label so the user knows which phase
    // they're settling.
    const stopAnim = startTransmittingAnim(
      orbitCommitBtn,
      "[ %s TRANSMITTING / ORBIT %s ]",
    );
    // v1.1 — submission frame for the orbit phase: dim the composer +
    // foreground the progress timeline / locked-in actions recap.
    const resolvingList = beginResolvingFrame({
      headline: "orbit actions",
      recap: orbitQueue.map(_describeOrbitActionForRecap),
    });
    // v0.9.8 — live status feed.
    const progress = startTransmitProgress({
      listEl: resolvingList || document.getElementById("solo-commit-orbit-progress"),
      btnAnim: stopAnim,
      phaseSnapshot: { phase: "orbit", day: Number(lastLiveInventory?.day || 0) },
      mode: "orbit",
    });
    inFlightSubmit = true;
    try {
      // Solo flow mirrors :func:`submitSoloNight`: post p1's queue,
      // auto-lock p2 with an empty submission so the orbit phase
      // resolves and we drop into PLANNING.
      const submit = async (player, actions) =>
        fetch(`/api/game/${sessionId}/orbit`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ player, actions }),
        }).then(async (r) => {
          const body = await r.json().catch(() => ({}));
          if (!r.ok || body.ok === false) {
            throw new Error(
              (body.errors && body.errors.join(", ")) || `orbit ${player} failed`,
            );
          }
          return body;
        });
      // v0.9.7 — N-seat fix. Same rationale as ``submitSoloNight``:
      // the server's ``auto_fire_bot_seats`` handles every bot
      // seat after a human submit. Hard-firing ``p2`` here breaks
      // 3- and 4-seat games because by the time the second call
      // hits the server, the phase may have already rolled
      // (orbit → planning of the next day) and the endpoint
      // returns "wrong phase". Submit only the human and let the
      // server walk the rest of the seat list.
      const orbitActions = orbitQueue.slice();
      const body = await submit(MY_SEAT, orbitActions);
      // v1.11 — slow (agent) game: non-blocking submit; retry on agent_busy.
      if (body?.agent_busy) {
        enterHumanWaitFrame(progress, "orbit");
        _scheduleAgentResubmit(MY_SEAT, orbitActions, "orbit");
        return;
      }
      clearOrbitQueue();
      // v1.7 — multi-human: hold in a committed "waiting for players" frame
      // when our orbit submit didn't resolve the phase (bug #3). v1.11 — same
      // for a solo human-vs-agent game while the agent finishes. The live-sync
      // poller reveals the next night once everyone is in.
      if ((_multiHumanGame || _slowBotGame) && !body?.orbit_resolved) {
        enterHumanWaitFrame(progress, "orbit");
        return;
      }
      progress.pushLine(
        "ready",
        `day ${body?.day ?? "?"} · phase ${body?.phase ?? "?"} · your move`,
        "ok",
        "✓",
      );
      // v1.1 — orbital praxis closes the day: the sun sets and the next
      // NIGHT opens. Fade the resolving overlay, flash the "NIGHT n -
      // season" card, sweep the cool sunset front across the board (same
      // direction as sunrise) so the map settles into NIGHT, THEN reveal
      // the planning controls.
      if (replayLastTurnFx && !reduceMotionMq.matches) {
        stageCinematicTakeover();
        const seasonLabel = _currentSeasonLabel();
        await showMapTitleCard(
          `NOX ${body?.day ?? "—"} BEGINS`,
          seasonLabel ? `— ${seasonLabel} —` : "",
          { holdMs: 1750 },
        );
        const sweepMs = runHorizonSweep(mapPlayer, "sunset");
        if (sweepMs) await new Promise((r) => setTimeout(r, sweepMs));
      } else {
        setMapDaylight("night");
      }
      await pullAllMaps({ playFx: true });
      // v1.3 — the orbit resolved but emitted NO night frames (the night isn't
      // played yet), so the replay clock can't advance to a DUSK tick. Drive
      // the station's DUSK beat directly from the freshly-pulled resolve data
      // so the shipment + blue/consumption is reviewable during night planning.
      // (Season-close is skipped inside the helper — owned by the resolve beat.)
      _stageLiveOrbitBeat(body?.day);
    } catch (e) {
      if (orbitErr) {
        orbitErr.textContent = "! " + (e.message || e);
        orbitErr.hidden = false;
      }
      progress.pushLine("err", `transmit failed · ${e?.message || e}`, "warn", "!");
      try { await pullAllMaps({ playFx: true }); } catch { /* ignore */ }
    } finally {
      inFlightSubmit = false;
      stopAnim();
      if (_awaitingHumanResolution) {
        // Committed multi-human wait — keep the frame up + button locked.
        orbitCommitBtn.disabled = true;
      } else {
        progress.stop();
        orbitCommitBtn.disabled = false;
        // v1.1 — safety net (see submitSoloNight).
        endResolvingFrame();
        // v1.7 — re-seed the live-sync baseline (see submitSoloNight).
        liveSyncSig = "";
      }
    }
  }

  document.querySelectorAll(".solo-add-orbit").forEach((btn) => {
    btn.addEventListener("click", () => {
      // v0.9.1 — a disabled button (nothing affordable, 0 damaged, etc.)
      // must not enqueue a no-op. Repair is the exception: the modal opens
      // regardless so the player can see all harvester statuses.
      if (btn.classList.contains("is-disabled")) {
        const kind = btn.getAttribute("data-orbit-action") || "";
        if (kind === "repair") {
          openRepairSubmit();
          return;
        }
        if (orbitErr) {
          orbitErr.textContent = "! can't afford that right now";
          orbitErr.hidden = false;
        }
        return;
      }
      const kind = btn.getAttribute("data-orbit-action") || "";
      const action = makeOrbitActionFromButton(kind);
      if (action) {
        orbitQueue.push(action);
        renderOrbitQueue();
      }
    });
  });

  // Keep the "× N" chip on the build-probes button in sync with the
  // adjacent numeric input — purely cosmetic but lets the seat see
  // the cost ladder before they commit.
  document
    .getElementById("solo-orbit-probe-count")
    ?.addEventListener("input", () => {
      const chip = document.querySelector("[data-orbit-probe-count]");
      const v = Math.max(
        1,
        Math.min(
          20,
          Number.parseInt(
            (/** @type {HTMLInputElement} */
            (document.getElementById("solo-orbit-probe-count"))).value,
            10,
          ) || 1,
        ),
      );
      if (chip) chip.textContent = String(v);
    });
  // v0.9.3 — mirror the EMP / MINE / CHAFF build-count inputs into
  // the button-label chip exactly the way probe-count does. Clamp
  // to [1, 10] so a stray 999 doesn't accidentally drain the wallet.
  ["emp", "mine", "chaff"].forEach((slot) => {
    const input = document.getElementById(`solo-orbit-${slot}-count`);
    if (!input) return;
    input.addEventListener("input", () => {
      const chip = document.querySelector(
        `[data-orbit-weapon-count="${slot}"]`,
      );
      const v = Math.max(
        1,
        Math.min(
          10,
          Number.parseInt(
            (/** @type {HTMLInputElement} */ (input)).value,
            10,
          ) || 1,
        ),
      );
      if (chip) chip.textContent = String(v);
    });
  });
  orbitQueueClearBtn?.addEventListener("click", () => clearOrbitQueue());
  orbitCommitBtn?.addEventListener("click", () => {
    void submitSoloOrbit();
  });

  async function submitSoloNight() {
    if (!sessionId || !errSoloEl || !soloCommitBtn) return;
    errSoloEl.hidden = true;
    // v0.9.13 — reset the message styling to the dim baseline; the
    // full-vault guard below promotes it to the bright-red danger look.
    errSoloEl.classList.add("dim");
    errSoloEl.classList.remove("policy-err--danger");
    soloCommitBtn.disabled = true;

    /** @type {any[]} */
    let moves;
    try {
      moves = soloMovesForSubmit();
    } catch (e) {
      errSoloEl.textContent = "! " + (e.message || e);
      errSoloEl.hidden = false;
      soloCommitBtn.disabled = false;
      return;
    }

    // v0.9.15 — strand guard (human-only). If a harvester is queued to
    // end the night on the surface with no pickup, it's DESTROYED at
    // dawn. Warn on the FIRST TRANSMIT click and bail; a second click
    // (still acked) submits anyway.
    const stranded = strandedHarvesterIds();
    if (stranded.length && !strandWarnAcked) {
      strandWarnAcked = true;
      const list = stranded.join(", ");
      errSoloEl.textContent =
        `\u26A0 ${list} will be DESTROYED at Aurora (no pickup queued) ` +
        `\u2014 click TRANSMIT again to submit anyway`;
      errSoloEl.hidden = false;
      soloCommitBtn.disabled = false;
      return;
    }

    // v0.9.13 — full-vault overflow guard (human-only). A queued pickup
    // returning cargo into a FULL vault triggers the §3.14 cascade
    // (keep best, jettison rest). Warn in RED on the first TRANSMIT and
    // bail; a second click (still acked) submits anyway.
    const overflowWarn = fullVaultPickupWarning();
    if (overflowWarn && !vaultFullWarnAcked) {
      vaultFullWarnAcked = true;
      errSoloEl.textContent = overflowWarn;
      errSoloEl.classList.remove("dim");
      errSoloEl.classList.add("policy-err--danger");
      errSoloEl.hidden = false;
      soloCommitBtn.disabled = false;
      return;
    }

    // v0.8.1 — start the density-shade animation now that we know
    // we'll actually post to the server.
    const stopAnim = startTransmittingAnim(
      soloCommitBtn,
      "[ %s TRANSMITTING / PRAXIS %s ]",
    );

    // v1.1 — raise the submission frame: dim the composer, show the
    // "LOCKED IN" overlay with the foregrounded progress timeline + a
    // recap of the policy just committed. Falls back to the under-button
    // list if the overlay nodes are missing.
    const resolvingList = beginResolvingFrame({
      headline: "this Nox's policy",
      recap: moves.map(_describeNightMoveForRecap),
    });
    // v0.9.8 — live status feed. Polls /status while the submit is in
    // flight so the user sees each bot fire, the night resolve, and the
    // next day open in real time — now foregrounded on the overlay.
    const progress = startTransmitProgress({
      listEl: resolvingList || document.getElementById("solo-commit-progress"),
      btnAnim: stopAnim,
      phaseSnapshot: { phase: "planning", day: Number(lastLiveInventory?.day || 0) },
      mode: "praxis",
    });

    // v0.8.0 — drop orders that reference a missing / dead asset
    // BEFORE we transmit. Server would reject them anyway, but
    // surfacing the cull here lets the user see exactly which slots
    // were cancelled (yellow line in #err-solo) instead of finding
    // out via the PRAXIS log mid-replay.
    const owned = ownedAssetIds();
    const cancelled = [];
    const filtered = moves.filter((m, ix) => {
      if (m && (m.a === "drop" || m.a === "step" || m.a === "pickup")) {
        if (!m.unit || !owned.has(String(m.unit))) {
          cancelled.push(`row ${ix + 1} (${m.a}${m.unit ? " " + m.unit : ""})`);
          return false;
        }
      }
      return true;
    });
    if (cancelled.length) {
      errSoloEl.textContent =
        `! cancelled invalid order(s): ${cancelled.join(", ")}`;
      errSoloEl.hidden = false;
    }
    moves = filtered;

    inFlightSubmit = true;
    try {
      // v0.9.7 — N-seat fix. We used to follow the human's submit
      // with a hardcoded ``postPolicy("p2", [])`` because the
      // original solo flow predated server-side bot auto-firing.
      // The server's ``auto_fire_bot_seats`` (engine.py) now drives
      // every bot seat after a human submit AND walks the phase
      // graph (planning → night → dawn → orbit → planning) so it
      // also auto-fires the bots' orbit actions if the day flips
      // forward in the same call. The hard-coded second submit
      // would fire AFTER the server had already rolled the phase,
      // and in a 4-seat game that meant ``postPolicy("p2", [])``
      // hit the policy endpoint with ``phase=orbit`` and bounced
      // back ``"wrong phase (orbit); policies only during
      // planning."``. We now submit ONLY for the human seat and
      // let the server walk the rest of the seat list.
      const body = await postPolicy(MY_SEAT, moves);
      // v1.11 — slow (agent) game: the submit is non-blocking. If the agent
      // was mid-turn holding the lock, our moves weren't stashed — hold the
      // wait frame and retry until they land.
      if (body?.agent_busy) {
        enterHumanWaitFrame(progress, "praxis");
        _scheduleAgentResubmit(MY_SEAT, moves, "praxis");
        return;
      }
      clearQueue();
      // v1.7 — multi-human: if OUR submit didn't resolve the night, other
      // humans are still plotting. v1.11 — same for a solo human-vs-agent
      // game while the agent finishes its turn. Stay in a committed
      // "LOCKED IN — waiting" frame instead of bouncing to the composer
      // (bug #3); the standing live-sync poller drives the resolution
      // cinematic once everyone (agent/humans) is in.
      if ((_multiHumanGame || _slowBotGame) && !body?.night_resolved) {
        enterHumanWaitFrame(progress, "praxis");
        return;
      }
      // Push a final "ready" line so the user sees the click resolved
      // before we tear down the panel.
      progress.pushLine(
        "ready",
        `day ${body?.day ?? "?"} · phase ${body?.phase ?? "?"} · your move`,
        "ok",
        "✓",
      );
      await pullAllMaps({ playFx: true });
    } catch (e) {
      errSoloEl.textContent = "! " + (e.message || e);
      errSoloEl.hidden = false;
      progress.pushLine("err", `transmit failed · ${e?.message || e}`, "warn", "!");
      // Even on failure, refresh state so the UI catches any
      // phase change the server may have applied before the
      // rejection landed (e.g. a stale-phase submit raced with
      // the bot auto-fire path).
      try { await pullAllMaps({ playFx: true }); } catch { /* ignore */ }
    } finally {
      inFlightSubmit = false;
      stopAnim();
      if (_awaitingHumanResolution) {
        // Committed multi-human wait: keep the overlay + progress feed up and
        // the button locked. ``clearHumanWaitFrame`` (from the live-sync
        // poller) re-enables + the cinematic drops the frame on resolution.
        soloCommitBtn.disabled = true;
      } else {
        progress.stop();
        soloCommitBtn.disabled = false;
        // v1.1 — safety net. The cinematic's reveal path normally drops
        // the frame; this covers the no-cinematic / error / FX-off paths.
        endResolvingFrame();
        // v1.7 — we just consumed our own resolution (or errored); re-seed
        // the live-sync baseline so its next tick doesn't replay the same
        // night as a redundant reveal.
        liveSyncSig = "";
      }
    }
  }

  function resetSoloFormForNewGame() {
    clearQueue();
    if (soloExpert) soloExpert.checked = false;
    if (soloExpertJson) soloExpertJson.value = "";
    lastHints = null;
    soloIds = { harvester: null, lifter: null };
    prefetchPlanKey = "";
    mainMapSource = "live";
    lastLiveMapPayload = null;
    // v1.7 — clear any committed multi-human "waiting for players" latch so a
    // fresh session never boots with a stale locked overlay.
    _awaitingHumanResolution = false;
    _humanWaitProgress = null;
    // v1.11 — tear down the agent wait-frame ticker too.
    if (_waitTicker) { clearInterval(_waitTicker); _waitTicker = null; }
    _waitAgent = null;
    _waitHumans = [];
    // v1.1 — re-arm the opening NIGHT card + reset the board to night so
    // the new session opens on the surface-orders night.
    _openingCardShown = false;
    setMapDaylight("night");
    syncExpertPanel();
  }

  function stopReplayPlayback() {
    if (replayTicker !== null) {
      // v0.9.9 — ``replayTicker`` may hold a setTimeout id (new
      // chained-timeout loop) OR a setInterval id (legacy fixed
      // cadence). clearTimeout / clearInterval are interchangeable
      // for both in every supported browser; using both is a
      // belt-and-braces defence against any future refactor that
      // mixes the two modes.
      window.clearInterval(replayTicker);
      window.clearTimeout(replayTicker);
      replayTicker = null;
    }
    if (replayPlay) replayPlay.textContent = "[ play ]";
  }

  function syncReplayScrubUi() {
    if (!replayScrub) return;
    const n = replayTicks.length;
    replayScrub.min = "0";
    if (n === 0) {
      replayScrub.max = "0";
      replayScrub.value = "0";
      replayScrub.disabled = true;
      replayScrub.setAttribute("aria-valuemin", "0");
      replayScrub.setAttribute("aria-valuemax", "0");
      replayScrub.setAttribute("aria-valuenow", "0");
      replayScrub.setAttribute("aria-valuetext", "No replay loaded");
      return;
    }
    const maxIx = Math.max(0, n - 1);
    replayScrub.max = String(maxIx);
    replayScrub.disabled = false;
    const i = Math.max(0, Math.min(maxIx, replayTickIdx));
    replayScrub.value = String(i);
    replayScrub.setAttribute("aria-valuemin", "0");
    replayScrub.setAttribute("aria-valuemax", String(maxIx));
    replayScrub.setAttribute("aria-valuenow", String(i));
    replayScrub.setAttribute(
      "aria-valuetext",
      `${String(i + 1)} / ${String(n)} — ${replayCaptionEl?.textContent || ""}`,
    );
  }

  function syncReplayRowOnly() {
    // v0.7.5 — the universal strip / scoreboard / agent feed are
    // refreshed on every tick of the replay-row sync, whether or not
    // we're in replay mode. The function used to be a pure UI sync
    // for the toolbar; it now drives the always-visible surfaces too.
    updateNowPlayingStrip();
    renderScoreboard();
    renderAgentFeed();
    // v0.9.11 — replay report auto-pop is now driven entirely by the
    // synthetic pre/post-orbit ticks in ``paintReplayFrameOntoMain``
    // (gated by the "show orbital summaries as pop-ups" setting via
    // ``orbitFlashEnabled``); the old day-crossing auto-pop here is
    // gone so the report doesn't double-fire while scrubbing.
    if (!replayTicks.length) {
      if (replayCaptionEl) replayCaptionEl.textContent = "";
      if (replaySlotEl) replaySlotEl.textContent = "";
      if (replayDayBadge) {
        replayDayBadge.textContent = "";
        replayDayBadge.hidden = true;
      }
    } else {
      if (replayTickIdx < 0) replayTickIdx = 0;
      if (replayTickIdx >= replayTicks.length)
        replayTickIdx = replayTicks.length - 1;
      const tick = replayTicks[replayTickIdx];
      const frame = nightReplayFrames[tick.lastFrameIdx];
      if (replayCaptionEl)
        replayCaptionEl.textContent = String(frame?.caption ?? "");
      if (replaySlotEl)
        replaySlotEl.textContent = formatReplaySlotLabel(frame);
      const day = currentReplayDay();
      const days = uniqueReplayDays();
      if (replayDayBadge) {
        if (day) {
          replayDayBadge.textContent =
            days.length > 1 ? `D${day} / ${days.length} Nox` : `D${day}`;
          replayDayBadge.hidden = false;
        } else {
          replayDayBadge.textContent = "";
          replayDayBadge.hidden = true;
        }
      }
    }
    if (replayDayPrev)
      replayDayPrev.disabled = uniqueReplayDays().length < 2;
    if (replayDayNext)
      replayDayNext.disabled = uniqueReplayDays().length < 2;
    syncReplayScrubUi();
    renderReplayDayTicks();
    syncReplayDrawer();
    // v1.0 — auto-open the end-of-season results screen once the
    // scrub cursor reaches the final tick of a completed season.
    handleReplaySeasonState();
  }

  let lastPaintedReplayTickIdx = -1;
  /** @type {Set<HTMLElement>} */
  const liveAnimNodes = new Set();
  /** @type {Set<HTMLElement>} */
  const hiddenStaticOverlays = new Set();
  /** Cells masked while a probe streak is in flight. Cleared on landing
   *  or when the animation is force-cancelled (scrub / new frame). */
  const probeMaskedCells = new Set();

  function cancelInflightReplayAnimations() {
    for (const node of liveAnimNodes) {
      node.remove();
    }
    liveAnimNodes.clear();
    for (const overlay of hiddenStaticOverlays) {
      overlay.style.removeProperty("visibility");
    }
    hiddenStaticOverlays.clear();
    for (const cell of probeMaskedCells) {
      cell.classList.remove("cell--probe-pending");
      cell.classList.remove("cell--probe-revealing");
    }
    probeMaskedCells.clear();
  }

  /**
   * Find the per-entity rows that explain the current move.
   *
   * @param {any|null} prevFrame
   * @param {any} curFrame
   * @returns {{kind:string, from?:[number,number]|null, to?:[number,number]|null, glyph:string, fg:string}|null}
   */
  /** For an illegal / collision drop frame, find the tile the lifter
   *  tried (and failed) to set ``harvesterId`` down on. The backend
   *  folds the collision event onto the frame as ``frame.collisions``;
   *  the event carries the contested ``at`` and the list of involved
   *  harvester ids. Returns ``[x, y]`` or ``null``. */
  function dropBounceTarget(frame, harvesterId) {
    const cols = frame && Array.isArray(frame.collisions) ? frame.collisions : [];
    for (const ev of cols) {
      if (!ev || typeof ev !== "object") continue;
      if (ev.type !== "drop_on" && ev.type !== "simultaneous_drops") continue;
      const harvs = Array.isArray(ev.harvesters) ? ev.harvesters : [];
      if (harvesterId && harvs.length && !harvs.includes(harvesterId)) continue;
      const at = Array.isArray(ev.at) ? ev.at : null;
      if (at && at.length === 2) return [Number(at[0]), Number(at[1])];
    }
    return null;
  }

  function describeReplayDelta(prevFrame, curFrame) {
    const tag = curFrame && curFrame.tag;
    if (
      !tag
      || tag === "open"
      || tag === "dawn"
      || tag === "waste"
      || tag === "damaged"
    ) return null;

    /** @param {any} f */
    const ents = (f) => (f && Array.isArray(f.entities) ? f.entities : []);
    const prev = ents(prevFrame);
    const cur = ents(curFrame);
    /** @type {Record<string, any>} */
    const prevById = {};
    for (const row of prev) prevById[row.id] = row;
    const owner = curFrame.owner || null;

    // v0.9.14 — simultaneous-drop collision: two or more harvesters tried
    // to drop on the SAME tile in the same hour, so none land — all are
    // damaged and hauled back to orbit. The frame has no single owner, so
    // we fan out ONE orbital-bounce per involved harvester (each in its
    // own seat colour) converging on the contested tile and bouncing back
    // damaged. Returns an array (the tick runner animates each). Fog: a
    // single-seat view only shows its own harvester's bounce (the tile is
    // a private landing location); OBS / "both" shows every one.
    if (tag === "collision_simultaneous_drops") {
      const cols = Array.isArray(curFrame.collisions) ? curFrame.collisions : [];
      const ev = cols.find((c) => c && c.type === "simultaneous_drops");
      const at = ev && Array.isArray(ev.at) && ev.at.length === 2
        ? [Number(ev.at[0]), Number(ev.at[1])] : null;
      if (!at) return null;
      const harvs = Array.isArray(ev.harvesters) ? ev.harvesters : [];
      const singleSeat = replayViewSeat !== "obs" && replayViewSeat !== "both";
      const deltas = [];
      for (const hid of harvs) {
        const seat = String(hid).split("_")[1] || "";
        if (singleSeat && seat !== replayViewSeat) continue;
        deltas.push({
          kind: "drop_bounce", from: null, to: at, glyph: "X",
          fg: ownerColor(seat), damaged: true, idx: unitOrdinal(hid),
        });
      }
      return deltas.length ? deltas : null;
    }

    if (tag === "step" || tag === "drop" || tag === "pickup") {
      for (const row of cur) {
        if (row.t !== "harvester") continue;
        if (owner && row.owner !== owner) continue;
        const before = prevById[row.id];
        const beforePos =
          before && Array.isArray(before.surface) ? before.surface : null;
        const afterPos = Array.isArray(row.surface) ? row.surface : null;

        const seatColor = ownerColor(row.owner);
        if (tag === "step" && beforePos && afterPos &&
            (beforePos[0] !== afterPos[0] || beforePos[1] !== afterPos[1])) {
          // Detect harvest color from terrain at destination in prev frame.
          // Default to dim white (empty step / unrecognised tile).
          let harvestColor = "rgba(210,215,220,0.7)";
          let prevObsCell = null;
          const w = replayDims.width;
          const obsCell = prevFrame && Array.isArray(prevFrame.cells)
            ? prevFrame.cells[afterPos[1] * w + afterPos[0]] : null;
          if (obsCell && obsCell.kind !== "fog") {
            const bg = obsCell.bg || "", fg2 = obsCell.fg || "";
            if (bg.includes("255,0,0") || fg2.includes("255,0,0")) {
              harvestColor = "#ff4040"; prevObsCell = obsCell;
            } else if (bg.includes("63,185,80")) {
              harvestColor = "#3fb950"; prevObsCell = obsCell;
            } else if (bg.includes("59,143,224") || fg2.includes("59,143,224")) {
              harvestColor = "#58a6ff"; prevObsCell = obsCell;
            }
          }
          return { kind: "step", from: beforePos, to: afterPos, glyph: "X", fg: seatColor, harvestColor, prevObsCell };
        }
        if (tag === "drop" && !beforePos && afterPos) {
          return { kind: "drop", from: null, to: afterPos, glyph: "X", fg: seatColor, owner: row.owner, damaged: Boolean(row.damaged), idx: unitOrdinal(row.id) };
        }
        // v0.9.14 — illegal / collision drop: the harvester never lands
        // (it stays orbital and is damaged on contact). The contested tile
        // comes from the collision event folded onto this frame. Render it
        // as ONE orbital pass — the lifter hauls the unit back to orbit —
        // instead of a drop followed by a separate retrieve.
        if (tag === "drop" && !beforePos && !afterPos) {
          const bounceAt = dropBounceTarget(curFrame, row.id);
          if (bounceAt) {
            return { kind: "drop_bounce", from: null, to: bounceAt, glyph: "X", fg: seatColor, owner: row.owner, damaged: true, idx: unitOrdinal(row.id) };
          }
        }
        if (tag === "pickup" && beforePos && !afterPos) {
          // ``loaded`` = the recovered harvester was carrying RED (its cargo
          // hold was non-empty just before recall). Drives the station
          // recovery glyph: full ▲ when loaded, empty △ when not.
          const _loaded = before && Array.isArray(before.cargo)
            ? before.cargo.length > 0
            : Boolean(before?.carrying_red);
          return { kind: "pickup", from: beforePos, to: null, glyph: "X", fg: seatColor, owner: row.owner, damaged: Boolean(before?.damaged), loaded: _loaded, idx: unitOrdinal(row.id) };
        }
      }
      return null;
    }

    if (tag === "probe") {
      for (const row of cur) {
        if (row.t !== "probe") continue;
        if (owner && row.owner !== owner) continue;
        if (prevById[row.id]) continue;
        const at = Array.isArray(row.surface) ? row.surface : null;
        if (!at) continue;
        return { kind: "probe", to: at, glyph: "\u00B7", fg: ownerColor(row.owner), owner: row.owner };
      }
      return null;
    }
    return null;
  }

  /**
   * @param {HTMLElement} host
   * @param {number} x
   * @param {number} y
   */
  function findReplayCell(host, x, y) {
    const sel = `.cell[data-x="${String(x)}"][data-y="${String(y)}"]`;
    return /** @type {HTMLElement|null} */ (host.querySelector(sel));
  }

  /**
   * Spawn a positioned ghost ``<span>`` over the map host that carries
   * the entity's glyph. The caller wires up the CSS transition.
   *
   * @param {HTMLElement} host
   * @param {DOMRect} rect
   * @param {string} glyph
   * @param {string} fg
   */
  function spawnReplayGhost(host, rect, glyph, fg) {
    const hostRect = host.getBoundingClientRect();
    const ghost = document.createElement("span");
    ghost.className = "replay-anim-ghost";
    ghost.textContent = glyph;
    ghost.style.color = fg;
    ghost.style.left = `${String(rect.left - hostRect.left)}px`;
    ghost.style.top = `${String(rect.top - hostRect.top)}px`;
    ghost.style.width = `${String(rect.width)}px`;
    ghost.style.height = `${String(rect.height)}px`;
    host.appendChild(ghost);
    liveAnimNodes.add(ghost);
    return ghost;
  }

  /**
   * @param {HTMLElement} cell
   */
  function hideStaticEntityOverlay(cell) {
    const overlay = /** @type {HTMLElement|null} */ (
      cell.querySelector(".entity-overlay")
    );
    if (overlay) {
      overlay.style.visibility = "hidden";
      hiddenStaticOverlays.add(overlay);
    }
    return overlay;
  }

  /** v1.7 — overlay a cell with a supplied (pre-action) terrain appearance so
   *  a board effect that the just-painted end-state frame already shows — a
   *  harvest recolour, a freshly-laid trail glyph, a revealed tile — stays
   *  hidden until the incoming animation actually lands. Mirrors how a real
   *  cell renders (bg / fg / trail / terrain char) from the dense cell the
   *  VIEWING seat sees, so it holds the correct look in any perspective.
   *  Returns the overlay (or null when there's nothing to stand in for, e.g.
   *  the cell was fog for this viewer); the caller removes it at the landing
   *  beat. */
  function _layTerrainStandin(cellEl, beforeCell) {
    if (!cellEl || !beforeCell || beforeCell.kind === "fog") return null;
    const s = document.createElement("span");
    s.className = "harvest-terrain-standin";
    s.style.background = beforeCell.bg || "";
    if (beforeCell.fg) s.style.color = beforeCell.fg;
    s.innerHTML = renderTrailOverlayHtml(beforeCell) + esc(beforeCell.ch || "");
    cellEl.appendChild(s);
    return s;
  }

  /** Inner HTML for a harvester riding the orbital lifter (or the pickup
   *  stand-in left on the tile). A damaged unit uses the grey wreck glyph
   *  (matching the static map). Pass ``idx`` to stamp the seat-coloured
   *  ordinal sticker — only the on-tile stand-in does this; the flying
   *  cargo passes ``null`` so the mid-arc glyph stays clean. */
  function orbitCargoInnerHtml(glyph, fg, damaged, idx) {
    const g = damaged
      ? `<span style="${DAMAGED_GLYPH_CSS}">${esc(glyph)}</span>`
      : esc(glyph);
    const badge = idx != null
      ? `<span class="entity-overlay-sub" aria-hidden="true" style="color:${esc(fg)}">${esc(String(idx))}</span>`
      : "";
    return g + badge;
  }

  /**
   * Orbital lifter (▲) sweeps east-or-west across the entire map, passing
   * through the target cell at t=0.5.  Fast at the edges (high orbital
   * velocity), slow near the target (burn).  Always exits off-screen.
   *
   * Drop:   entity overlay is hidden until lifter reaches the cell (t=0.5),
   *         then revealed as the lifter accelerates away.
   * Pickup: entity overlay is hidden at t=0.5 as the lifter takes it.
   * Bounce: illegal/collision drop — cargo stays on the lifter the whole
   *         pass and turns grey (damaged) at t=0.5, hauled back to orbit.
   */
  function runOrbitalArcAnimation(host, delta) {
    const isPickup = delta.kind === "pickup";
    // v0.9.14 — an illegal / collision drop never lands: the lifter
    // carries the harvester in, fails to set it down on the occupied
    // tile, and hauls it straight back to orbit damaged. Rendered as ONE
    // arc — the cargo stays attached for the whole pass and turns into the
    // grey wreck glyph at the midpoint — instead of a drop then a
    // separate retrieve.
    const isBounce = delta.kind === "drop_bounce";
    const targetXY = /** @type {[number,number]} */ (isPickup ? delta.from : delta.to);
    const targetCell = findReplayCell(host, targetXY[0], targetXY[1]);
    if (!targetCell) return;

    // For pickup/drop: arc targets the cell above the harvester so the lifter
    // appears to swoop down. Entity hide/show still uses the actual harvester cell.
    const arcCell = findReplayCell(host, targetXY[0], targetXY[1] - 1) || targetCell;

    // For drops: hide entity overlay so it doesn't show while the lifter
    // carries it in. Restored at t=0.5 when the lifter deposits it.
    // For pickups: the current frame has no harvester on targetCell (already
    // picked up in the data). Inject a stand-in entity span so the harvester
    // is visible while the lifter approaches; remove it at t=0.5.
    let ownHiddenOverlay = null;
    let pickupStandin = null;
    if (isBounce) {
      // Bounce: a healthy defender already occupies the tile and the
      // dropping unit never lands. Leave every static overlay alone — the
      // cargo lives entirely on the flying lifter.
    } else if (!isPickup) {
      const ov = targetCell.querySelector(".entity-overlay");
      if (ov instanceof HTMLElement) {
        ov.style.visibility = "hidden";
        ownHiddenOverlay = ov;
      }
    } else {
      pickupStandin = document.createElement("span");
      pickupStandin.className = "entity-overlay";
      pickupStandin.style.color = delta.fg;
      pickupStandin.innerHTML = orbitCargoInnerHtml(delta.glyph, delta.fg, Boolean(delta.damaged), delta.idx);
      targetCell.appendChild(pickupStandin);
    }

    const hostRect = host.getBoundingClientRect();
    const cellRect = arcCell.getBoundingClientRect();
    // Use viewport-relative coords + position:fixed so the ghost isn't
    // destroyed when host.innerHTML is rebuilt on the next replay tick.
    // edgeT uses hostRect to constrain the arc to the map's visible area.
    const cx = cellRect.left + cellRect.width * 0.5;
    const cy = cellRect.top + cellRect.height * 0.5;
    const cw = cellRect.width;
    const ch = cellRect.height;

    // Always sweep east-to-west or west-to-east; slight vertical tilt (±20°).
    const goingRight = Math.random() < 0.5;
    const tilt = (Math.random() - 0.5) * 0.7;
    const dax = goingRight ? Math.cos(tilt) : -Math.cos(tilt);
    const day = Math.sin(tilt);

    function edgeT(ox, oy, dx, dy) {
      const ts = [];
      if (Math.abs(dx) > 1e-6) ts.push(dx > 0 ? (hostRect.right - ox) / dx : (hostRect.left - ox) / dx);
      if (Math.abs(dy) > 1e-6) ts.push(dy > 0 ? (hostRect.bottom - oy) / dy : (hostRect.top - oy) / dy);
      const valid = ts.filter((t) => t > 2);
      return valid.length ? Math.min(...valid) : Math.max(hostRect.width, hostRect.height);
    }

    const tFwd = edgeT(cx, cy, dax, day);
    const tBck = edgeT(cx, cy, -dax, -day);
    const ax = cx + dax * tFwd, ay = cy + day * tFwd;
    const bx = cx - dax * tBck, by = cy - day * tBck;
    const perpX = -day, perpY = dax;
    const curve = Math.min(hostRect.width, hostRect.height) * 0.28 * (Math.random() < 0.5 ? 1 : -1);
    const midX = (8 * cx - ax - bx) / 6;
    const midY = (8 * cy - ay - by) / 6;
    const c1x = midX + perpX * curve, c1y = midY + perpY * curve;
    const c2x = midX - perpX * curve, c2y = midY - perpY * curve;

    const ghost = document.createElement("span");
    ghost.className = "replay-anim-ghost replay-anim-ghost--orbital";
    ghost.style.color = delta.fg;
    ghost.style.width = `${String(Math.round(cw))}px`;
    ghost.style.height = `${String(Math.round(ch))}px`;
    ghost.style.left = "0";
    ghost.style.top = "0";
    ghost.style.position = "fixed";
    ghost.style.overflow = "visible";

    const lifterEl = document.createElement("span");
    lifterEl.textContent = "▲";
    lifterEl.style.cssText = "display:block;text-align:center;line-height:1";
    ghost.appendChild(lifterEl);

    // Cargo span positioned directly below the ▲ without affecting ghost's layout
    const cargoEl = document.createElement("span");
    cargoEl.style.cssText = "position:absolute;top:100%;left:50%;transform:translateX(-50%);pointer-events:none;line-height:1";
    // A bounce arrives carrying a HEALTHY unit (it only gets damaged on
    // the failed set-down at the midpoint); a pickup of a wreck shows it
    // grey from the moment it leaves the tile. No seat sticker on the
    // flying cargo — it reads as clutter mid-arc; the badge only shows
    // while the unit is down on the tile.
    cargoEl.innerHTML = orbitCargoInnerHtml(delta.glyph, delta.fg, isBounce ? false : Boolean(delta.damaged), null);

    // Drop / bounce: arrives carrying x/X. A drop releases it at the
    // midpoint; a bounce keeps it and hauls it back to orbit.
    // Pickup: arrives empty, picks up x/X at midpoint and departs carrying it.
    if (!isPickup) ghost.appendChild(cargoEl);

    document.body.appendChild(ghost);
    // Orbital lasts 1100ms — intentionally NOT in liveAnimNodes so the next
    // frame tick doesn't cancel it mid-flight via cancelInflightReplayAnimations.
    // Appended to body (not host) so host.innerHTML repaints don't destroy it.

    function easing(t) {
      if (t <= 0.5) { const u = t * 2; return 0.5 * (1 - Math.pow(1 - u, 2.5)); }
      const u = (t - 0.5) * 2; return 0.5 + 0.5 * Math.pow(u, 2.5);
    }
    function bez(p, s, cc1, cc2, e) {
      const q = 1 - p;
      return q*q*q*s + 3*q*q*p*cc1 + 3*q*p*p*cc2 + p*p*p*e;
    }

    const DURATION = 1100;
    let midTriggered = false;
    const t0 = performance.now();

    function tick(now) {
      if (!document.body.contains(ghost)) return;
      const rawT = Math.min(1, (now - t0) / DURATION);
      const p = easing(rawT);
      ghost.style.transform = `translate(${(bez(p,ax,c1x,c2x,bx) - cw*0.5).toFixed(1)}px,${(bez(p,ay,c1y,c2y,by) - ch*0.5).toFixed(1)}px)`;

      if (!midTriggered && rawT >= 0.5) {
        midTriggered = true;
        if (isBounce) {
          // Bounce: the set-down fails. The unit is damaged on contact and
          // stays on the lifter to be hauled back to orbit — swap it to the
          // grey wreck glyph; it never appears on the tile (no sticker on
          // the flying cargo).
          cargoEl.innerHTML = orbitCargoInnerHtml(delta.glyph, delta.fg, true, null);
        } else if (!isPickup) {
          // Drop: release cargo onto cell, depart empty
          cargoEl.remove();
          if (ownHiddenOverlay) {
            ownHiddenOverlay.style.removeProperty("visibility");
            ownHiddenOverlay = null;
          }
          // v1.7 — the unit is now down: pop any vision it revealed in
          // lockstep with the deposit (see the drop dispatch in
          // runSingleDeltaAnimation).
          if (typeof delta._onDeposit === "function") {
            try { delta._onDeposit(); } catch (_e) { /* best-effort UX */ }
          }
        } else {
          // Pickup: remove the stand-in harvester and carry it away
          if (pickupStandin) { pickupStandin.remove(); pickupStandin = null; }
          ghost.appendChild(cargoEl);
        }
      }

      if (rawT < 1) {
        requestAnimationFrame(tick);
      } else {
        ghost.remove();
        if (pickupStandin) { pickupStandin.remove(); pickupStandin = null; }
        if (ownHiddenOverlay) ownHiddenOverlay.style.removeProperty("visibility");
        if (isPickup && typeof osOnEntityArrival === "function")
          osOnEntityArrival(delta, targetCell);
      }
    }
    requestAnimationFrame(tick);
  }

  function spawnHarvestEffects(cell, color, terrainStandin, restoreOverlays) {
    const rect = cell.getBoundingClientRect();
    const cx = rect.left + rect.width * 0.5;
    const cy = rect.top + rect.height * 0.5;

    // Remove terrain standin exactly as the blink fires — the blink flash
    // covers the instant the old terrain disappears, hiding the hard cut.
    if (terrainStandin) terrainStandin.remove();

    // Blink overlay: sits inside the cell, flashes tile colour 3× then vanishes.
    // Entity overlay stays hidden until blink finishes so the harvester X
    // doesn't show through the "off" frames.
    const blink = document.createElement("div");
    blink.className = "harvest-blink-overlay";
    blink.style.setProperty("--blink-color", color);
    cell.appendChild(blink);
    blink.addEventListener("animationend", () => {
      blink.remove();
      if (typeof restoreOverlays === "function") restoreOverlays();
    }, { once: true });

    // Particle burst: 8 square pixels fly outward and fade
    const N = 8;
    for (let i = 0; i < N; i++) {
      const angle = (i / N) * Math.PI * 2 + (Math.random() - 0.5) * 0.4;
      const dist = rect.width * (1.8 + Math.random() * 1.4);
      const p = document.createElement("div");
      p.className = "harvest-particle";
      p.style.left = `${cx.toFixed(1)}px`;
      p.style.top = `${cy.toFixed(1)}px`;
      p.style.width = `${Math.max(2, Math.round(rect.width * 0.22))}px`;
      p.style.height = `${Math.max(2, Math.round(rect.height * 0.22))}px`;
      p.style.setProperty("--dx", `${(Math.cos(angle) * dist).toFixed(1)}px`);
      p.style.setProperty("--dy", `${(Math.sin(angle) * dist).toFixed(1)}px`);
      p.style.background = color;
      p.style.animationDelay = `${Math.round(Math.random() * 40)}ms`;
      document.body.appendChild(p);
      p.addEventListener("animationend", () => p.remove(), { once: true });
    }
  }

  // Orbit→surface sequencing (Settings: "sequence orbit launch → surface").
  // When ON, the on-board landing animation is held back by a per-kind lead
  // so the station launch plays FIRST, then the surface action executes. The
  // leads sit just under each station launch anim's duration ("nearly
  // finished" handoff). 0 lead ⇒ launch + landing play simultaneously.
  const _OS_LEAD_MS = { drop: 2600, drop_bounce: 2600, probe: 1600 };
  function _osOrbitLeadMs(kind) {
    if (window._osOrbitSeq === false) return 0;
    return _OS_LEAD_MS[kind] || 0;
  }

  function runSingleDeltaAnimation(host, delta, prevFrame, curFrame) {
    if (delta.kind === "step") {
      const fromXY = /** @type {[number,number]} */ (delta.from);
      const toXY = /** @type {[number,number]} */ (delta.to);
      const fromCell = findReplayCell(host, fromXY[0], fromXY[1]);
      const toCell = findReplayCell(host, toXY[0], toXY[1]);
      if (!toCell) return;
      hideStaticEntityOverlay(toCell);
      // v1.7 — hold BOTH the destination's post-step look (harvest recolour)
      // AND the departed cell's freshly-laid trail glyph at their pre-move
      // appearance until the walking harvester actually arrives. Previously
      // only a narrow set of recognised harvest colours on the destination
      // was deferred and the source's new trail popped instantly, so the
      // board "moved" a beat before the sprite did. We read the VIEWING
      // seat's own before-cells so the stand-in matches whatever perspective
      // is on screen (OBS or a single seat's fog view).
      const _pw = replayDims.width;
      const _prevCells = _frameSeatCells(prevFrame);
      const _beforeAt = (xy) =>
        Array.isArray(_prevCells) && _pw
          ? _prevCells[xy[1] * _pw + xy[0]]
          : null;
      const terrainStandin = _layTerrainStandin(toCell, _beforeAt(toXY));
      const srcStandin = fromCell
        ? _layTerrainStandin(fromCell, _beforeAt(fromXY))
        : null;
      const startRect = (fromCell || toCell).getBoundingClientRect();
      const endRect = toCell.getBoundingClientRect();
      const ghost = spawnReplayGhost(host, startRect, delta.glyph, delta.fg);
      ghost.classList.add("replay-anim-ghost--step");
      const dx = endRect.left - startRect.left;
      const dy = endRect.top - startRect.top;
      requestAnimationFrame(() => requestAnimationFrame(() => {
        ghost.style.transform = `translate(${String(dx)}px, ${String(dy)}px)`;
      }));
      cleanupGhostOnEnd(ghost, () => {
        if (srcStandin) srcStandin.remove();
        spawnHarvestEffects(toCell, delta.harvestColor, terrainStandin, () => {
          for (const ov of hiddenStaticOverlays) ov.style.removeProperty("visibility");
          hiddenStaticOverlays.clear();
        });
      }, /* skipOverlayRestore */ true);
    } else if (delta.kind === "drop" || delta.kind === "drop_bounce") {
      if (typeof osOnEntityArrival === "function")
        osOnEntityArrival({ kind: delta.kind, owner: delta.owner }, null);
      // v1.7 — defer the dropped harvester's newly-revealed vision until the
      // lifter deposits it (arc midpoint, t=0.5), matching the probe reveal
      // mask. Without this the ground the harvester "sees" pops open the
      // instant the frame is painted — well before it visually lands (and,
      // when orbit sequencing is on, before the ~2.6s launch lead even runs).
      // A bounce never lands, so it reveals nothing.
      if (delta.kind === "drop" && Array.isArray(delta.to)) {
        const _masks = collectNewlyRevealedCells(
          host, prevFrame, curFrame, delta.to[0], delta.to[1],
        );
        for (const m of _masks) {
          m.classList.add("cell--probe-pending");
          probeMaskedCells.add(m);
        }
        // v1.7 — also hold the LANDING cell's own post-drop recolour at its
        // pre-drop look until the lifter deposits the unit. A harvester
        // dropping onto a resource harvests it on contact, so the frame paints
        // the tile already depleted (green/red → dark) the instant it's shown
        // — the "landing square pre-filled as harvested" bug. Stand in the
        // viewer's pre-drop cell and lift it at the deposit beat (arc midpoint).
        const _lx = delta.to[0], _ly = delta.to[1];
        const _prevCells = _frameSeatCells(prevFrame);
        const _beforeLand = Array.isArray(_prevCells) && replayDims.width
          ? _prevCells[_ly * replayDims.width + _lx]
          : null;
        const _landStandin = _layTerrainStandin(
          findReplayCell(host, _lx, _ly), _beforeLand,
        );
        if (_masks.length || _landStandin) {
          delta._onDeposit = () => {
            if (_landStandin) _landStandin.remove();
            revealMaskedCells(_masks);
          };
        }
      }
      const _lead = _osOrbitLeadMs(delta.kind);
      if (_lead > 0) {
        // Sequenced: hold the surface landing until the orbital launch has
        // nearly arrived. Pre-hide the just-painted unit so it doesn't sit
        // on the tile during the lead (plain drop only — a bounce leaves the
        // occupying defender's overlay alone, matching runOrbitalArcAnimation).
        if (delta.kind === "drop" && Array.isArray(delta.to)) {
          const _tc = findReplayCell(host, delta.to[0], delta.to[1]);
          const _ov = _tc && _tc.querySelector(".entity-overlay");
          if (_ov instanceof HTMLElement) _ov.style.visibility = "hidden";
        }
        const _h = host, _d = delta;
        window.setTimeout(() => runOrbitalArcAnimation(_h, _d), _lead);
      } else {
        runOrbitalArcAnimation(host, delta);
      }
    } else if (delta.kind === "pickup") {
      runOrbitalArcAnimation(host, delta);
    } else if (delta.kind === "probe") {
      const toXY = /** @type {[number,number]} */ (delta.to);
      const toCell = findReplayCell(host, toXY[0], toXY[1]);
      if (!toCell) return;
      hideStaticEntityOverlay(toCell);

      const pendingMasks = collectNewlyRevealedCells(
        host,
        prevFrame,
        curFrame,
        toXY[0],
        toXY[1],
      );
      for (const m of pendingMasks) {
        m.classList.add("cell--probe-pending");
        probeMaskedCells.add(m);
      }
      // Pre-capture landing position while cell is still in the DOM
      const landingRect = toCell.getBoundingClientRect();
      const fgHex = (delta.fg || "#ffffff").replace("#", "");
      const rippleR = parseInt(fgHex.slice(0, 2), 16);
      const rippleG = parseInt(fgHex.slice(2, 4), 16);
      const rippleB = parseInt(fgHex.slice(4, 6), 16);

      if (typeof osOnEntityArrival === "function")
        osOnEntityArrival({ kind: "probe_emit", owner: delta.owner }, null);
      const _probeGo = () => spawnProbeTrail(toCell, "#ffffff", delta.fg, () => {
        for (const ov of hiddenStaticOverlays) ov.style.removeProperty("visibility");
        hiddenStaticOverlays.clear();
        // Ripple ring — uses pre-captured position and player color
        const ripple = document.createElement("div");
        ripple.className = "probe-ripple";
        ripple.style.left = `${(landingRect.left + landingRect.width * 0.5).toFixed(1)}px`;
        ripple.style.top  = `${(landingRect.top  + landingRect.height * 0.5).toFixed(1)}px`;
        ripple.style.setProperty("--rr", String(rippleR));
        ripple.style.setProperty("--rg", String(rippleG));
        ripple.style.setProperty("--rb", String(rippleB));
        document.body.appendChild(ripple);
        ripple.addEventListener("animationend", () => ripple.remove(), { once: true });

        for (const m of probeMaskedCells) {
          m.classList.add("cell--probe-revealing");
        }
        window.setTimeout(() => {
          for (const m of probeMaskedCells) {
            m.classList.remove("cell--probe-pending");
            m.classList.remove("cell--probe-revealing");
          }
          probeMaskedCells.clear();
        }, 280);
      });
      const _plead = _osOrbitLeadMs("probe");
      if (_plead > 0) window.setTimeout(_probeGo, _plead);
      else _probeGo();
    }
  }

  /**
   * @param {HTMLElement} host
   * @param {{ frames: any[], firstFrameIdx: number, lastFrameIdx: number }} tick
   * @param {any|null} beforeTickFrame
   */
  /** Is grid cell ``xy`` (``[x, y]``) currently in the viewing seat's
   *  fog-of-war view for ``frame``? OBS / "both" see everything. A
   *  single-seat view reads the same per-seat dense cells the static
   *  replay map paints from, so the animation gate matches exactly what
   *  is (or isn't) drawn: a cell counts as visible only when it is
   *  in live line-of-sight (not fog, not a stale memory tile). Falls
   *  back to permissive (true) when dims / cells are unavailable so we
   *  never silently swallow an animation on missing data. */
  function _replayCellVisibleToViewer(frame, xy) {
    if (replayViewSeat === "obs" || replayViewSeat === "both") return true;
    if (!Array.isArray(xy) || xy.length < 2) return false;
    const w = replayDims.width;
    const h = replayDims.height;
    if (!w || !h) return true;
    const x = Number(xy[0]);
    const y = Number(xy[1]);
    if (x < 0 || y < 0 || x >= w || y >= h) return false;
    const cells = (frame && frame.cells_by_seat && frame.cells_by_seat[replayViewSeat])
      || (frame && frame[`cells_player_${replayViewSeat}`])
      || (replayViewSeat === "p1" ? (frame && frame.cells_player) : null);
    if (!Array.isArray(cells) || !cells.length) return true;
    const c = cells[y * w + x];
    if (!c) return false;
    return c.kind !== "fog" && !c.stale;
  }

  /** Does the viewer have probe-echo intel at [x,y] in `frame`?
   *  A probe echo cell is kind:"fog" WITH an entity field — only
   *  via="probe_launch" markers carry an entity on a fog cell.
   *  OBS / "both" always returns true. Falls back to false (not
   *  permissive) so X markers don't appear for probes you never saw. */
  function _viewerHasProbeEchoAt(frame, xy) {
    if (replayViewSeat === "obs" || replayViewSeat === "both") return true;
    if (!Array.isArray(xy) || xy.length < 2) return false;
    const w = replayDims.width;
    if (!w) return false;
    const x = Number(xy[0]), y = Number(xy[1]);
    const cells = (frame?.cells_by_seat?.[replayViewSeat])
      || (frame?.cells_by_seat?.p1 && replayViewSeat === "p1" ? frame.cells_by_seat.p1 : null)
      || (frame && frame[`cells_player_${replayViewSeat}`])
      || (replayViewSeat === "p1" ? (frame && frame.cells_player) : null);
    if (!Array.isArray(cells)) return false;
    const c = cells[y * w + x];
    return !!(c && c.kind === "fog" && c.entity);
  }

  /** Should this delta animate for an ENEMY (non-owner) action in a
   *  single-seat view? Only when the unit is visible to the viewer, so
   *  we never reveal a move that happened in fog (and never trail a
   *  ghost across cells the player can't see). Origin visibility is
   *  read from the frame the unit departed (``prevFrame``), destination
   *  visibility from where it lands (``curFrame``) — matching the
   *  static paint. */
  function _enemyDeltaVisibleToViewer(d, prevFrame, curFrame) {
    switch (d && d.kind) {
      case "step":
        // Continuous on-map movement: both endpoints must be in sight.
        return _replayCellVisibleToViewer(prevFrame, d.from)
          && _replayCellVisibleToViewer(curFrame, d.to);
      case "drop":
      case "drop_bounce":
        return _replayCellVisibleToViewer(curFrame, d.to);
      case "pickup":
        return _replayCellVisibleToViewer(prevFrame, d.from);
      default:
        return true;
    }
  }

  function runReplayAnimationsTick(host, tick, beforeTickFrame) {
    cancelInflightReplayAnimations();
    let _maxLead = 0;   // longest orbit→surface sequencing lead this tick
    const singleSeat = replayViewSeat !== "obs" && replayViewSeat !== "both";
    for (let fi = 0; fi < tick.frames.length; fi++) {
      const curF = tick.frames[fi];
      const isEnemyFrame = singleSeat && curF.owner && curF.owner !== replayViewSeat;
      const prevF = fi === 0 ? beforeTickFrame : tick.frames[fi - 1];
      const delta = describeReplayDelta(prevF, curF);
      if (!delta) continue;
      // describeReplayDelta returns a single delta or, for a fan-out
      // event (e.g. a simultaneous-drop collision), an array of them.
      const list = Array.isArray(delta) ? delta : [delta];
      for (const d of list) {
        // In a single-seat view, an ENEMY action only animates when the
        // unit is actually visible to that seat (probe launches are the
        // exception — the launch streak/marker is public, §3.15, so it
        // always plays). Own-seat frames and OBS/both always animate.
        // This replaces the old blanket "skip every non-owner frame"
        // that made visible enemy steps / drops / pickups teleport.
        if (isEnemyFrame && curF.tag !== "probe"
            && !_enemyDeltaVisibleToViewer(d, prevF, curF)) {
          continue;
        }
        runSingleDeltaAnimation(host, d, prevF, curF);
        _maxLead = Math.max(_maxLead, _osOrbitLeadMs(d.kind));
      }
    }
    // Sequencing holds the surface landing back by _maxLead; extend the
    // replay dwell so autoplay doesn't step onto the next tick (and cancel
    // in-flight anims) before the launch→land sequence completes (~1300ms
    // for the arc/streak + a beat). Harmless when _maxLead is 0.
    if (_maxLead > 0) {
      const _cur = (typeof window._osPendingDwellMs === "number") ? window._osPendingDwellMs : 0;
      window._osPendingDwellMs = Math.max(_cur, _maxLead + 1300);
    }
  }

  /**
   * Cells currently in the player's view (i.e. non-fog) that were
   * *not* in the player's view on the previous frame and lie within
   * probe-vision range of ``(dropX, dropY)``. These are the cells the
   * streaking probe is responsible for revealing.
   *
   * Falls back to an empty list if dimensions are missing or the
   * previous frame's cell data is unavailable — in which case the
   * caller skips the mask and the animation still runs.
   *
   * @param {HTMLElement} host
   * @param {any|null} prevFrame
   * @param {any} curFrame
   * @param {number} dropX
   * @param {number} dropY
   */
  /** Dense per-cell array the ACTIVE replay-view seat actually sees for a
   *  frame. OBS / "both" read the global ``cells``; a single seat reads its
   *  own ``cells_by_seat`` (with the legacy p1 alias fallback). Used so the
   *  reveal mask matches the viewer's fog rather than always p1's. */
  function _frameSeatCells(frame) {
    if (!frame) return null;
    if (replayViewSeat === "obs" || replayViewSeat === "both") {
      return Array.isArray(frame.cells) ? frame.cells : null;
    }
    return (
      (frame.cells_by_seat && frame.cells_by_seat[replayViewSeat]) ||
      frame[`cells_player_${replayViewSeat}`] ||
      (replayViewSeat === "p1" ? frame.cells_player : null) ||
      null
    );
  }

  /** Fade a set of masked (``cell--probe-pending``) cells in — used by both
   *  the probe streak and the harvester-drop deposit so a freshly-revealed
   *  area only pops when the incoming unit actually lands, not when the board
   *  frame is first painted. Operates on the caller's own array so a
   *  concurrent probe reveal can't clear it out from under us. */
  function revealMaskedCells(masks) {
    if (!Array.isArray(masks) || !masks.length) return;
    for (const m of masks) m.classList.add("cell--probe-revealing");
    window.setTimeout(() => {
      for (const m of masks) {
        m.classList.remove("cell--probe-pending");
        m.classList.remove("cell--probe-revealing");
        probeMaskedCells.delete(m);
      }
    }, 280);
  }

  function collectNewlyRevealedCells(host, prevFrame, curFrame, dropX, dropY) {
    /** @type {HTMLElement[]} */
    const out = [];
    const width = replayDims.width;
    const height = replayDims.height;
    if (!width || !height) return out;
    const cur = _frameSeatCells(curFrame);
    const prev = _frameSeatCells(prevFrame);
    if (!Array.isArray(cur) || !cur.length) return out;
    // v1.7 — mask EVERY cell that flipped fog→visible on this frame, not just
    // a small disk around (dropX, dropY). A probe opens a Chebyshev-4 square
    // (up to ~49 cells, RULEBOOK §3.11), so the old Euclidean radius-2 gate
    // left the whole outer ring of the vision pop showing the instant the
    // frame painted — well before the streak landed. Each replay frame is a
    // single unit's action, so the frame-wide fog→visible delta is exactly
    // the vision that action is responsible for revealing. (dropX / dropY are
    // retained for signature compatibility but no longer gate the scan.)
    void dropX; void dropY;
    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        const idx = y * width + x;
        const c = cur[idx];
        if (!c) continue;
        // Currently visible means not fog and not stale.
        const isFreshNow = c.kind !== "fog" && !c.stale;
        if (!isFreshNow) continue;
        let wasFreshBefore = false;
        if (Array.isArray(prev) && prev[idx]) {
          const p = prev[idx];
          wasFreshBefore = p.kind !== "fog" && !p.stale;
        }
        if (wasFreshBefore) continue;
        const cellEl = findReplayCell(host, x, y);
        if (cellEl) out.push(cellEl);
      }
    }
    return out;
  }

  /**
   * @param {HTMLElement} ghost
   * @param {(() => void) | undefined} [onLand] Hook fired the instant
   *   the ghost finishes its transition / animation, *before* the
   *   ghost element is removed and static overlays are restored. The
   *   probe streak uses this to reveal masked cells in lockstep with
   *   the landing beat.
   */
  function cleanupGhostOnEnd(ghost, onLand, skipOverlayRestore = false) {
    let removed = false;
    const end = () => {
      if (removed) return;
      removed = true;
      if (typeof onLand === "function") {
        try {
          onLand();
        } catch (_err) {
          // Landing hooks are best-effort UX; never let a throw kill
          // the cleanup that restores the static entity overlays.
        }
      }
      ghost.remove();
      liveAnimNodes.delete(ghost);
      if (!skipOverlayRestore) {
        for (const overlay of hiddenStaticOverlays) {
          overlay.style.removeProperty("visibility");
        }
        hiddenStaticOverlays.clear();
      }
    };
    ghost.addEventListener("transitionend", end, { once: true });
    ghost.addEventListener("animationend", end, { once: true });
    window.setTimeout(end, 900);
  }

  /**
   * Repaint the main map with the current replay frame. ``mode``
   * controls whether to layer an entity animation on top:
   *
   *   "auto"     — animate when ``replayTickIdx`` advanced by exactly +1.
   *   "forward"  — force-animate (used by next / autoplay).
   *   "jump"     — no animation (scrub, live, fresh fetch).
   *
   * @param {"auto"|"forward"|"jump"} [mode]
   */
  /**
   * Merge two player cell arrays into a combined fog-of-war view.
   * For each position: live beats echo beats fog; entity/trail data preserved.
   */
  function mergeTwoPlayerCells(pc1, pc2, n) {
    return mergeAllPlayerCells([pc1, pc2], n);
  }

  /** v0.9.9 — N-seat fog-of-war merger. Replaces the hard-coded
   *  ``mergeTwoPlayerCells`` for OBS view in 3/4-seat games. The
   *  algorithm is the same per pair (prefer non-fog, then live over
   *  stale, then entity-bearing) folded across every seat. Falls
   *  back to the first non-empty seat array on inputs with zero
   *  seats so the painter never crashes mid-replay. */
  function mergeAllPlayerCells(seatCellArrays, n) {
    const lists = seatCellArrays.filter(
      (lst) => Array.isArray(lst) && lst.length,
    );
    if (!lists.length) return [];
    if (lists.length === 1) return lists[0].slice(0, n);
    const out = [];
    for (let i = 0; i < n; i++) {
      let best = null;
      for (const lst of lists) {
        const c = lst[i];
        if (!c) continue;
        if (best == null) { best = c; continue; }
        const bestFog = best.kind === "fog";
        const cFog = c.kind === "fog";
        if (bestFog && !cFog) { best = c; continue; }
        if (!bestFog && cFog) continue;
        if (bestFog && cFog) continue;
        const bestLive = !best.stale && !best.echo_probe;
        const cLive = !c.stale && !c.echo_probe;
        if (cLive && !bestLive) { best = c; continue; }
        if (bestLive && !cLive) continue;
        if (!best.entity && c.entity) best = c;
      }
      out.push(best);
    }
    return out;
  }

  /** Resolve a player colour for the collision-ring animation. v0.9.6
   *  — extended to 4 seats (p1=white-cream, p2=yellow, p3=magenta,
   *  p4=cyan). Falls back to plain white if the owner is unknown so
   *  legacy frames (or a corrupted owner string) still render. */
  function ownerColour(owner) {
    // v0.9.18 — unified: delegate to ownerColor() so the collision /
    // probe-crush / mine FX share the single seat→colour source of
    // truth (live profile → palette default) instead of a 4th divergent
    // fallback set. Kept as a thin alias for the existing call sites.
    return ownerColor(owner);
  }

  /** Read the canonical replay-frame day, honouring the
   *  ``frame.day`` payload added by the persisted-replay endpoint
   *  and falling back to whatever the day-index says when we're on
   *  a frame the store hasn't tagged. */
  function frameDayOf(frame) {
    if (!frame) return null;
    const d = frame.day;
    if (typeof d === "number" && Number.isFinite(d)) return d;
    return currentReplayDay();
  }

  /** Should this frame appear in the timeline for the current view?
   *
   *  ``open`` / ``dawn`` / ``collision_swap`` frames carry no owner —
   *  they're shared boundary events and always render. Per-seat
   *  action frames filter by the active P1 / P2 view button. ``Both``
   *  and ``obs`` show every seat (including p3/p4 in N-seat games).
   *  v0.9.7 — generalised so any pN seat passes when its own view
   *  button is active.
   */
  function shouldShowTimelineFrame(frame) {
    if (!frame) return false;
    const tag = frame.tag;
    if (tag === "open" || tag === "dawn" || tag === "collision_swap") return true;
    const owner = frame.owner;
    if (!owner) return true;
    if (replayViewSeat === "p1") return owner === "p1";
    if (replayViewSeat === "p2") return owner === "p2";
    if (replayViewSeat === "p3") return owner === "p3";
    if (replayViewSeat === "p4") return owner === "p4";
    return true;
  }

  /** Render the unified PRAXIS timeline (v0.7.4).
   *
   *  One row per replay frame in the current night, filtered by the
   *  view-seat buttons. Rendering rules:
   *  - **Pending** (frame index > cursor):  owner-seat colour at
   *    ~38% opacity. The watcher sees what's coming this night.
   *  - **Executed OK** (frame index ≤ cursor, outcome ok): owner-
   *    seat colour at full opacity.
   *  - **Failed** (outcome === "failed" or tag === "waste"): bright
   *    red, with the engine's failure reason rendered inline.
   *  - **Boundary** (no owner — open / dawn / swap collisions):
   *    dim neutral text — still positioned chronologically.
   *  - **Current** (last frame at-or-before the cursor): outlined +
   *    bg highlight so the eye lands on it.
   *
   *  Auto-scrolls the current row into view as the scrubber walks.
   */
  function renderReplayFeedTimeline() {
    if (!replayFeedTimelineEl) return;
    if (!replayTicks.length || !nightReplayFrames.length) {
      replayFeedTimelineEl.innerHTML =
        '<p class="cc-orders-empty"># quiet</p>';
      if (replayFeedDayEl) replayFeedDayEl.textContent = "";
      return;
    }
    const tickIdx = Math.max(
      0, Math.min(replayTickIdx, replayTicks.length - 1),
    );
    const tick = replayTicks[tickIdx];
    if (!tick) return;

    const cursorFrameIdx = tick.lastFrameIdx;
    const currentDay = frameDayOf(nightReplayFrames[cursorFrameIdx]);

    // Walk back to find the first frame for this night so we render
    // the full night-list, not the entire season.
    let startIdx = 0;
    for (let i = cursorFrameIdx; i >= 0; i -= 1) {
      const f = nightReplayFrames[i];
      if (!f) continue;
      if (currentDay != null && f.day != null && f.day !== currentDay) {
        startIdx = i + 1;
        break;
      }
      if (i === 0) startIdx = 0;
    }
    // Walk forward to find the last frame for this night (so the
    // "what's still coming" portion of the list is bounded).
    let endIdx = nightReplayFrames.length - 1;
    for (let i = cursorFrameIdx + 1; i < nightReplayFrames.length; i += 1) {
      const f = nightReplayFrames[i];
      if (!f) continue;
      if (currentDay != null && f.day != null && f.day !== currentDay) {
        endIdx = i - 1;
        break;
      }
    }

    const parts = [];
    let currentRowIdx = -1;

    // v0.9.1 — when the ORBIT chip is active (or ALL), prepend the
    // per-day orbit chatter. These render as boundary-styled rows at
    // the top of the day's feed since they all happen BEFORE any
    // night frame this day. NIGHT chip hides this block entirely.
    if (replayFeedFilter !== "night" && currentDay != null) {
      const orbitLines = orbitLogByDay[String(currentDay)] || [];
      for (const ln of orbitLines) {
        const isErr = ln.level === "error";
        const cls = [
          "cc-timeline-row",
          "cc-timeline-row--orbit",
          isErr ? "cc-timeline-row--failed" : "cc-timeline-row--boundary",
        ].join(" ");
        const txt = String(ln.text || "").replace(/^\[orbit\]\s*/, "");
        parts.push(
          `<div class="${cls}">` +
          `<span class="cc-timeline-stamp">ORB </span>` +
          `<span class="cc-timeline-owner">       </span>` +
          `<span class="cc-timeline-text">${esc(txt)}</span>` +
          `</div>`,
        );
      }
    }

    // Night frames — suppressed when ORBIT chip is the only active.
    if (replayFeedFilter === "orbit") {
      // Skip the per-hour night frames; orbit-only view already done.
      replayFeedTimelineEl.innerHTML = parts.join("")
        || '<p class="cc-orders-empty"># no orbit chatter</p>';
      if (replayFeedDayEl) {
        replayFeedDayEl.textContent = currentDay != null ? `· D${currentDay}` : "";
      }
      return;
    }

    for (let i = startIdx; i <= endIdx; i += 1) {
      const f = nightReplayFrames[i];
      if (!f) continue;
      if (!shouldShowTimelineFrame(f)) continue;
      const isBoundary = !f.owner;
      const isFailed = f.outcome === "failed"
        || f.tag === "waste"
        || f.tag === "damaged";
      const isPending = i > cursorFrameIdx;
      const isCollision = f.tag === "collision_swap"
        || (Array.isArray(f.collisions) && f.collisions.length);
      const isCrushed = Array.isArray(f.crushed_probes) && f.crushed_probes.length;
      const isCurrent = i === cursorFrameIdx;
      // State cascade. The rule the watcher reads: low-opacity
      // (seat colour) until the scrubber reaches the row, then
      // either full-opacity seat colour (ok) or red (failed). So
      // pending OUTRANKS failed visually — a row only "turns red"
      // once it's actually been executed under the cursor.
      let stateCls = "cc-timeline-row--ok";
      if (isBoundary && !isFailed) stateCls = "cc-timeline-row--boundary";
      if (isFailed && !isPending) stateCls = "cc-timeline-row--failed";
      if (isPending) stateCls = "cc-timeline-row--pending";
      const cls = [
        "cc-timeline-row",
        stateCls,
        isCollision ? "cc-timeline-row--collision" : "",
        isCrushed ? "cc-timeline-row--crushed" : "",
        isCurrent ? "cc-timeline-row--current" : "",
      ].filter(Boolean).join(" ");
      const seatAttr = f.owner ? ` data-seat="${esc(f.owner)}"` : "";
      const hourTag = (typeof f.hour === "number" && f.hour > 0)
        ? `H${String(f.hour).padStart(2, "0")} `
        : "    ";  // 4-space pad keeps captions column-aligned
      const ownerTag = f.owner ? `[${playerTag(f.owner)}] ` : "       ";
      // The engine's captions sometimes lead with the seat name
      // ("p1 dropped..." / "p1: step ...") — strip it because we
      // already render the owner tag in colour beside the caption.
      let caption = String(f.caption || "");
      if (f.owner) {
        const colonPrefix = `${f.owner}: `;
        const spacePrefix = `${f.owner} `;
        if (caption.startsWith(colonPrefix)) {
          caption = caption.slice(colonPrefix.length);
        } else if (caption.startsWith(spacePrefix)) {
          caption = caption.slice(spacePrefix.length);
        }
      }
      // Failed (and already executed) rows split the caption on the
      // engine's " — " separator so the reason can be rendered as a
      // red trailing span. Pending rows render the full caption so
      // the watcher doesn't get spoiled about the failure ahead of
      // time.
      let mainText = caption;
      let errReason = "";
      if (isFailed && !isPending) {
        const sep = caption.indexOf(" — ");
        if (sep > 0) {
          mainText = caption.slice(0, sep);
          errReason = caption.slice(sep + 3);
        }
      }
      const errHtml = errReason
        ? ` <span class="cc-timeline-reason">— ${esc(errReason)}</span>`
        : "";
      // v0.9.9 — wrap the action caption in ``.cc-timeline-caption``
      // so the failed-row strikeout CSS only crosses out the action
      // text, not the trailing error-reason fragment.
      parts.push(
        `<div class="${cls}"${seatAttr}>` +
        `<span class="cc-timeline-stamp">${esc(hourTag)}</span>` +
        `<span class="cc-timeline-owner">${esc(ownerTag)}</span>` +
        `<span class="cc-timeline-text">` +
        `<span class="cc-timeline-caption">${esc(mainText)}</span>` +
        `${errHtml}` +
        `</span>` +
        `</div>`,
      );
      if (isCurrent) currentRowIdx = parts.length - 1;
    }
    replayFeedTimelineEl.innerHTML = parts.join("")
      || '<p class="cc-orders-empty"># quiet</p>';
    if (currentRowIdx >= 0) {
      const currentEl = replayFeedTimelineEl
        .querySelector(".cc-timeline-row--current");
      if (currentEl && typeof currentEl.scrollIntoView === "function") {
        currentEl.scrollIntoView({ block: "nearest" });
      }
    }
    if (replayFeedDayEl) {
      replayFeedDayEl.textContent = currentDay != null ? `· D${currentDay}` : "";
    }
  }

  function syncReplayDrawer() {
    const inReplayMode = mainMapSource === "replay" && replayTicks.length > 0;
    // v0.9.8 — the LOG timeline (``#replay-feed``) ALSO shows up in
    // live mode now that the LOG tab is the canonical "what
    // happened on this day" surface. Pre-v0.9.8 the timeline was
    // hidden the moment the user dropped out of replay mode (e.g.
    // after the live-FX play handed control back to the live map),
    // which made the LOG tab look frozen until the user manually
    // scrubbed or clicked a filter chip. We now show it whenever
    // there are frames to render, and live mode focuses on the
    // latest day's tail. ``inReplayMode`` still drives extras like
    // the vault sync below.
    if (replayFeedEl) replayFeedEl.hidden = !(replayTicks.length > 0);
    // v0.7.5 — universal strip / scoreboard / agent feed / vault are
    // ALL kept synced to the scrub cursor on every drawer tick, not
    // just the timeline. The cost is cheap (these renderers read from
    // arrays we already have).
    updateNowPlayingStrip();
    renderScoreboard();
    const visibleDay = currentVisibleDay();
    if (visibleDay && replayTicks.length) {
      // Lazy-fetch rationale for whichever seats are visible.
      // v0.9.7 — N-seat games may have p3/p4 too; fetch any
      // seat that's appeared in the frame stream so its agent
      // log lines show up in the LOG / AGENT tabs.
      const seenSeats = new Set();
      for (const f of nightReplayFrames) {
        if (f && f.owner) seenSeats.add(String(f.owner));
      }
      seenSeats.add("p1");
      seenSeats.add("p2");
      for (const seat of seenSeats) ensureAgentLogForDay(visibleDay, seat);
    }
    // v0.9.8 — render the timeline unconditionally so the LOG tab
    // never goes stale. Was gated on ``inReplayMode`` pre-v0.9.8;
    // that gating is what caused "the LOG isn't updating with the
    // replay" — when live FX handed control back to live mode the
    // timeline rendered ONCE on the last replay tick and then sat
    // there forever until the user clicked a filter chip (which
    // calls ``renderReplayFeedTimeline`` directly).
    if (replayTicks.length) renderReplayFeedTimeline();
    if (inReplayMode) {
      repaintVaultForActiveSeat();
    }
    // v0.9.8 — hidden ``#orch-log`` buffer focuses on whatever day
    // the cursor is on (replay) or the live day (live).
    if (visibleDay && lastLogTail.length) {
      const dayBucket = logByDay[String(visibleDay)] || logByDay[visibleDay];
      const tailForFocus = Array.isArray(dayBucket) && dayBucket.length
        ? dayBucket
        : lastLogTail;
      renderOrchLog(tailForFocus, visibleDay);
    } else if (lastLogTail.length) {
      renderOrchLog(lastLogTail, lastLiveDay);
    }
    renderAgentFeed();
  }

  /** Spawn the v0.7.3 collision ring animation for every event on a
   *  freshly painted frame. The ring is positioned in screen-space
   *  on top of the cell at ``(x, y)`` using the map's pixel grid; we
   *  read the actual cell rect to stay in sync with the zoom slider. */
  function playCollisionFx(frame, delayMs = 0) {
    if (!collisionFxLayer || !mapPlayer) return;
    if (reduceMotionMq.matches) return;
    const events = Array.isArray(frame?.collisions) ? frame.collisions : [];
    if (!events.length) return;
    for (const ev of events) {
      const xy = Array.isArray(ev?.at) ? ev.at : null;
      if (!xy) continue;
      const owners = Array.isArray(ev?.owners) && ev.owners.length
        ? ev.owners
        : ["p1"];
      const a = ownerColour(owners[0]);
      const b = owners.length > 1 ? ownerColour(owners[1]) : a;
      const cellEl = mapPlayer.querySelector(
        `[data-x="${xy[0]}"][data-y="${xy[1]}"]`,
      );
      if (!cellEl || cellEl.classList.contains("cell--fog")) continue;
      spawnChainExplosion(cellEl, [a, b], delayMs);
      spawnXOverlay(cellEl, "#ff0000", delayMs > 0 ? 500 : 0);
      window.setTimeout(() => {
        cellEl.classList.add("cell--collision-flash");
        cellEl.addEventListener("animationend", () => cellEl.classList.remove("cell--collision-flash"), { once: true });
      }, delayMs);
    }
  }

  /** Spawn a small pixel-splash on every probe crushed this frame.
   *
   * Eight tiny squares fly out radially from the cell centre in the
   * probe-owner's seat colour, then fade. Old-school 8-bit feel —
   * roughly the same vibe as the collision ring but smaller and
   * monochrome (a probe is much smaller than a harvester, so the
   * splash matches the energy of the impact). Skips on reduced-motion.
   */
  function playProbeCrushFx(frame) {
    if (!collisionFxLayer || !mapPlayer) return;
    if (reduceMotionMq.matches) return;
    const events = Array.isArray(frame?.crushed_probes) ? frame.crushed_probes : [];
    if (!events.length) return;
    const hostRect = collisionFxLayer.getBoundingClientRect();
    for (const ev of events) {
      const xy = Array.isArray(ev?.at) ? ev.at : null;
      if (!xy) continue;
      const owner = ev?.probe_owner || "p1";
      const colour = ownerColour(owner);
      const cellEl = mapPlayer.querySelector(
        `[data-x="${xy[0]}"][data-y="${xy[1]}"]`,
      );
      if (!cellEl || cellEl.classList.contains("cell--fog")) continue;
      const cellRect = cellEl.getBoundingClientRect();
      const cx = cellRect.left - hostRect.left + cellRect.width / 2;
      const cy = cellRect.top - hostRect.top + cellRect.height / 2;
      const splash = document.createElement("div");
      splash.className = "probe-splash";
      splash.style.left = `${cx}px`;
      splash.style.top = `${cy}px`;
      splash.style.setProperty("--splash-colour", colour);
      // Eight pixel-shards radiating out in cardinal + diagonal
      // directions. The CSS uses each shard's own `--ang` to drive
      // the fly-out transform so we keep the markup compact.
      for (let i = 0; i < 8; i += 1) {
        const shard = document.createElement("span");
        shard.className = "probe-splash__shard";
        shard.style.setProperty("--ang", `${i * 45}deg`);
        splash.appendChild(shard);
      }
      collisionFxLayer.appendChild(splash);
      window.setTimeout(() => { splash.remove(); }, 700);
    }
  }

  /** v0.9.4 rev3 — EMP launch animation.
   *
   *  EXACT same diagonal streak as the probe drop, just with a
   *  different glyph + colour. The ghost spawns shifted to the
   *  upper-right (``translate(360px,-360px) scale(0.55)``) and
   *  transitions on a 420ms cubic-bezier to the target cell —
   *  identical to ``replay-anim-ghost--probe`` (see
   *  :func:`runSingleDeltaAnimation`'s probe-deploy branch).
   *
   *  No bloom, no ring, no glow — those were rejected. The only
   *  follow-up FX is the rhombus cloud field painted per-tick by
   *  :func:`paintEmpCloudOverlay`. */
  function playEmpFx(frame, prevFrame) {
    if (!mapPlayer) return;
    if (reduceMotionMq.matches) return;
    const events = Array.isArray(frame?.emp) ? frame.emp : [];
    if (!events.length) return;
    // v0.9.15 — an EMP launch is a SALVO: one launch fires up to
    // ``EMP_MISSILES_PER_LAUNCH`` (3) simultaneous missiles, each landing
    // on its own target. The event carries every target in ``targets``
    // (``at`` is just the first), so fly a trail per target instead of
    // only the primary. The ring expansion + persistent cloud overlay
    // fire ONCE, after the last missile across all salvos lands.
    const cells = [];
    for (const ev of events) {
      if (ev?.kind !== "emp_launch") continue;
      // Fire the launching platform's station animation (cyan ■ "emp").
      if (typeof osOnEntityArrival === "function")
        osOnEntityArrival({ kind: "emp_launch", owner: ev.owner }, null);
      const targets = Array.isArray(ev?.targets) && ev.targets.length
        ? ev.targets
        : (Array.isArray(ev?.at) ? [ev.at] : []);
      for (const xy of targets) {
        if (!Array.isArray(xy)) continue;
        const cellEl = mapPlayer.querySelector(
          `[data-x="${xy[0]}"][data-y="${xy[1]}"]`,
        );
        if (cellEl) cells.push(cellEl);
      }
    }
    if (!cells.length) return;
    // Block the cloud overlay until every missile lands + expansion plays.
    _empExpansionActive = true;
    _empExpansionLatestFrame = frame;
    let pending = cells.length;
    const onLanded = () => {
      pending -= 1;
      if (pending > 0) return;
      _playEmpExpansion(frame, () => {
        _empExpansionActive = false;
        const fEmp = _empExpansionLatestFrame || frame;
        paintEmpCloudOverlay(fEmp);
        // Spawn thin cyan X on each probe destroyed by this EMP, gated by
        // live vision at the moment of impact (prevFrame = pre-EMP cells,
        // since probe echoes are already cleared when the EMP frame is baked).
        if (!reduceMotionMq.matches) {
          const refFrame = prevFrame || fEmp;
          for (const ev of (Array.isArray(fEmp?.emp) ? fEmp.emp : [])) {
            if (!Array.isArray(ev?.destroyed_probes)) continue;
            for (const dp of ev.destroyed_probes) {
              const at = Array.isArray(dp?.at) ? dp.at : null;
              if (!at) continue;
              const liveVision = dp.owner === replayViewSeat
                || _replayCellVisibleToViewer(refFrame, at)
                || _viewerHasProbeEchoAt(refFrame, at);
              if (!liveVision) continue;
              const cellEl = mapPlayer.querySelector(
                `[data-x="${at[0]}"][data-y="${at[1]}"]`,
              );
              if (cellEl) spawnXOverlay(cellEl, "#00e8ff", 200, { thin: true });
            }
          }
        }
      });
    };
    for (const cellEl of cells) {
      spawnProbeTrail(cellEl, "#00e8ff", "#00e8ff", onLanded);
    }
  }

  /** v0.9.4 (rev2) — Mine-lay choreography:
   *
   *  1. **Minelayer flies in like the orblift.** A rhombus glyph
   *     (``\u25C6``) in the seat colour sweeps across the entire
   *     map on a Bezier arc — identical sweep math to the orblift
   *     descent (see ``runOrbitalArcAnimation``) so the craft
   *     visibly enters from one map edge and exits the other. The
   *     only difference from the orblift is the glyph itself, so
   *     the watcher immediately reads "this is a minelayer, not
   *     a harvester orblift".
   *
   *  2. **Hover beat.** Between t=0.40 and t=0.70 the arc
   *     position is clamped so the craft sits above the target
   *     cell. That's the cue for the pixel rain.
   *
   *  3. **Pixel rain.** During the hover the craft sheds a
   *     ``smattering`` of flat purple pixels — many small pixels
   *     dropped at randomised positions in/near the target cell.
   *     No glow, no halo: each pixel is a hard 2-3 px square. The
   *     same scatter pattern is then restamped per-replay-tick by
   *     :func:`paintMinesOverlay` so the cell's mine footprint
   *     persists across the rest of the replay.
   *
   *  4. **Departure.** The craft completes the arc and exits
   *     off-map. No fade — it just flies out.
   *
   *  ``mine_detonate`` is unchanged: a sharp orange pulse on the
   *  triggering cell.
   */
  function playMineFx(frame) {
    if (!collisionFxLayer || !mapPlayer) return;
    if (reduceMotionMq.matches) return;
    const events = Array.isArray(frame?.mine) ? frame.mine : [];
    if (!events.length) return;
    for (const ev of events) {
      const xy = Array.isArray(ev?.at) ? ev.at : null;
      if (!xy) continue;
      const colour = ownerColour(ev.owner || "p1");
      const cellEl = mapPlayer.querySelector(
        `[data-x="${xy[0]}"][data-y="${xy[1]}"]`,
      );
      if (!cellEl) continue;
      const isFog = cellEl.classList.contains("cell--fog");
      const isOwn = replayViewSeat === ev.owner;
      const isSpecificSeat = replayViewSeat !== "obs" && replayViewSeat !== "both";
      if (isSpecificSeat && !isOwn && isFog) continue;
      const cellRect = cellEl.getBoundingClientRect();
      if (ev.kind === "mine_lay") {
        _runMinelayerArc({
          targetCell: cellEl,
          targetCellRect: cellRect,
          ownerColour: colour,
        });
      } else if (ev.kind === "mine_detonate") {
        const harvXY = Array.isArray(ev?.harvester_at) ? ev.harvester_at : null;
        let harvEl = harvXY && mapPlayer.querySelector(
          `[data-x="${harvXY[0]}"][data-y="${harvXY[1]}"]`,
        );
        if (!harvEl) {
          // Old replay data without harvester_at: harvester tried to step
          // onto the mine but the step was cancelled, so it must be in one
          // of the four adjacent cells. Take the first one with an entity.
          const [mx, my] = xy;
          for (const [ax, ay] of [[mx-1,my],[mx+1,my],[mx,my-1],[mx,my+1]]) {
            const adj = mapPlayer.querySelector(`[data-x="${ax}"][data-y="${ay}"]`);
            if (adj && adj.querySelector(".entity-overlay")) { harvEl = adj; break; }
          }
        }
        const fxEl = harvEl || cellEl;
        const harvColour = ev.harvester_id
          ? ownerColour(String(ev.harvester_id).replace(/^harvester_/, "").replace(/_\d+$/, ""))
          : colour;
        spawnChainExplosion(fxEl, [colour, harvColour], 200);
        spawnXOverlay(fxEl, "#ff0000", 200);
        window.setTimeout(() => {
          cellEl.classList.add("cell--collision-flash");
          cellEl.addEventListener("animationend", () => cellEl.classList.remove("cell--collision-flash"), { once: true });
        }, 200);
      }
    }
  }

  /** 1-px-wide bezier trail for probes and EMP missiles.
   *
   * Entirely canvas-driven (no CSS ghost). Appended to document.body at
   * position:fixed so host repaints and cancelInflightReplayAnimations
   * cannot kill it mid-flight — same pattern as runOrbitalArcAnimation.
   *
   * probeColor  — color of the moving head dot (player seat color)
   * trailColor  — color of the 1-px trail (white for probe, cyan for EMP)
   * onLand      — called once when t≥1 (ripple, mask reveal, EMP expansion…)
   * durationMs  — travel time; fade plays out on top of this */
  function spawnProbeTrail(toLandingCell, trailColor, probeColor, onLand, durationMs = 540) {
    if (reduceMotionMq.matches) {
      if (typeof onLand === "function") window.setTimeout(onLand, 0);
      return;
    }

    const cellRect = toLandingCell.getBoundingClientRect();
    const mapHost = toLandingCell.closest(".map-host");
    const clipRect = mapHost ? mapHost.getBoundingClientRect() : null;
    const cw = cellRect.width;

    // Viewport coords for landing centre — captured now while cell is in DOM
    const toX = cellRect.left + cw / 2;
    const toY = cellRect.top  + cellRect.height / 2;
    const fromX = toX + 360;
    const fromY = toY - 360;

    const dx = toX - fromX, dy = toY - fromY;
    const len = Math.sqrt(dx * dx + dy * dy);
    const perpX = -dy / len, perpY = dx / len;
    const curveMag = (Math.random() < 0.5 ? 1 : -1) * (0.4 + Math.random() * 0.5) * cw;
    const cpX = (fromX + toX) / 2 + perpX * curveMag;
    const cpY = (fromY + toY) / 2 + perpY * curveMag;

    function parseHex(h) { const n = parseInt(h.replace("#", ""), 16); return [(n >> 16) & 0xff, (n >> 8) & 0xff, n & 0xff]; }
    const [tr, tg, tb] = parseHex(trailColor);
    const [pr, pg, pb] = parseHex(probeColor);

    const cW = window.innerWidth, cH = window.innerHeight;
    const canvas = document.createElement("canvas");
    canvas.width  = cW;
    canvas.height = cH;
    canvas.style.cssText = "position:fixed;left:0;top:0;pointer-events:none;z-index:9";
    document.body.appendChild(canvas);
    const ctx2 = /** @type {CanvasRenderingContext2D} */ (canvas.getContext("2d"));

    /** @type {Array<{x:number,y:number,startFadeAt:number,fadeDuration:number,alpha:number}>} */
    const trailPx = [];
    let prevX = /** @type {number|null} */ (null);
    let prevY = /** @type {number|null} */ (null);
    let landed = false;
    let onLandFired = false;
    let landFlashStart = -1;
    // Each probe in the same tick gets a random start offset so they stagger
    const startT = performance.now() + Math.floor(Math.random() * 200);

    function qbez(t, p0, cp, p1) { const u = 1 - t; return u * u * p0 + 2 * u * t * cp + t * t * p1; }

    function* bres(x0, y0, x1, y1) {
      const adx = Math.abs(x1 - x0), ady = Math.abs(y1 - y0);
      const sx = x0 < x1 ? 1 : -1, sy = y0 < y1 ? 1 : -1;
      let err = adx - ady;
      while (true) {
        yield [x0, y0];
        if (x0 === x1 && y0 === y1) break;
        const e2 = err * 2;
        if (e2 > -ady) { err -= ady; x0 += sx; }
        if (e2 <  adx) { err += adx; y0 += sy; }
      }
    }

    function tick(now) {
      const elapsed = now - startT;
      if (elapsed < 0) { requestAnimationFrame(tick); return; } // stagger delay

      const t  = Math.min(1, elapsed / durationMs);
      const cx = Math.round(qbez(t, fromX, cpX, toX));
      const cy = Math.round(qbez(t, fromY, cpY, toY));

      if (prevX === null) {
        trailPx.push({ x: cx, y: cy, startFadeAt: Infinity, fadeDuration: 1, alpha: 1 });
      } else {
        for (const [px, py] of bres(prevX, prevY, cx, cy)) {
          if (px === prevX && py === prevY) continue;
          trailPx.push({ x: px, y: py, startFadeAt: Infinity, fadeDuration: 1, alpha: 1 });
        }
      }
      prevX = cx; prevY = cy;

      if (t >= 1 && !landed) {
        landed = true;
        landFlashStart = now;
        for (const tp of trailPx) {
          tp.startFadeAt  = now + Math.random() * 900;
          tp.fadeDuration = 200 + Math.random() * 800;
        }
        if (!onLandFired) {
          onLandFired = true;
          if (typeof onLand === "function") try { onLand(); } catch (_) {}
        }
      }

      ctx2.clearRect(0, 0, cW, cH);
      const img = ctx2.getImageData(0, 0, cW, cH);
      const d = img.data;
      const clipL = clipRect ? Math.floor(clipRect.left)  : 0;
      const clipT = clipRect ? Math.floor(clipRect.top)   : 0;
      const clipR = clipRect ? Math.ceil(clipRect.right)  : cW;
      const clipB = clipRect ? Math.ceil(clipRect.bottom) : cH;
      let anyAlive = false;
      for (const tp of trailPx) {
        const alpha = now < tp.startFadeAt
          ? 1
          : Math.max(0, 1 - (now - tp.startFadeAt) / tp.fadeDuration);
        tp.alpha = alpha;
        if (alpha <= 0) continue;
        anyAlive = true;
        const px = tp.x | 0, py = tp.y | 0;
        if (px < clipL || px >= clipR || py < clipT || py >= clipB) continue;
        if (px < 0 || px >= cW || py < 0 || py >= cH) continue;
        const i = (py * cW + px) * 4;
        d[i]     = Math.min(255, d[i]     + ((tr * alpha) | 0));
        d[i + 1] = Math.min(255, d[i + 1] + ((tg * alpha) | 0));
        d[i + 2] = Math.min(255, d[i + 2] + ((tb * alpha) | 0));
        d[i + 3] = 255;
      }
      ctx2.putImageData(img, 0, 0);

      // Canvas-based landing flash — player-colored square at impact,
      // drawn entirely in canvas so it's immune to DOM repaint timing
      if (landFlashStart >= 0) {
        const fa = Math.max(0, 1 - (now - landFlashStart) / 280);
        if (fa > 0) {
          const fSize = cw * (0.35 + (1 - fa) * 0.55);
          ctx2.save();
          ctx2.beginPath();
          ctx2.rect(clipL, clipT, clipR - clipL, clipB - clipT);
          ctx2.clip();
          ctx2.globalAlpha = fa * 0.88;
          ctx2.fillStyle = probeColor;
          ctx2.fillRect(toX - fSize / 2, toY - fSize / 2, fSize, fSize);
          ctx2.globalAlpha = 1;
          ctx2.restore();
          anyAlive = true;
        }
      }

      // Moving probe head — player-colored dot while still in flight
      if (!landed) {
        ctx2.save();
        ctx2.beginPath();
        ctx2.rect(clipL, clipT, clipR - clipL, clipB - clipT);
        ctx2.clip();
        ctx2.fillStyle = `rgb(${pr},${pg},${pb})`;
        ctx2.fillRect(cx - 2, cy - 2, 4, 4);
        ctx2.restore();
      }

      if (landed && !anyAlive) { canvas.remove(); return; }
      requestAnimationFrame(tick);
    }

    requestAnimationFrame(tick);
  }

  /** Canvas-based pixel explosion. One pixel ≈ 1/8 cell so it stays
   *  compact but still scales with zoom. delayMs lets callers fire
   *  after a movement animation completes (e.g. 200ms for a step). */
  function spawnPixelExplosion(cellEl, colors, delayMs = 0) {
    if (!collisionFxLayer) return;
    const hostRect = collisionFxLayer.getBoundingClientRect();
    const cellRect = cellEl.getBoundingClientRect();
    const cx = cellRect.left - hostRect.left + cellRect.width / 2;
    const cy = cellRect.top - hostRect.top + cellRect.height / 2;

    const P       = Math.max(2, Math.round(cellRect.width / 6));
    const R       = 3;
    const LIFE    = 2;      // frames: 0=white flash, 1=owner colour, then gone
    const palette = colors.length ? colors : ["#ffffff"];

    function ringDensity(d) {
      const t = [1.0, 1.0, 0.95, 0.85, 0.70, 0.55, 0.40, 0.25];
      return t[Math.min(d, t.length - 1)];
    }

    const pixels = [];
    for (let dy = -R; dy <= R; dy++) {
      for (let dx = -R; dx <= R; dx++) {
        const d = Math.abs(dx) + Math.abs(dy);
        if (d > R) continue;
        if (d === 0 || Math.random() < ringDensity(d)) {
          pixels.push({ dx, dy, d, color: palette[Math.floor(Math.random() * palette.length)] });
        }
      }
    }
    const sparks = [];
    for (let dy = -(R + 1); dy <= R + 1; dy++) {
      for (let dx = -(R + 1); dx <= R + 1; dx++) {
        if (Math.abs(dx) + Math.abs(dy) !== R + 1) continue;
        if (Math.random() < 0.60) {
          sparks.push({ dx, dy, color: palette[Math.floor(Math.random() * palette.length)] });
        }
      }
    }

    const size   = (2 * (R + 2)) * P + P;
    const half   = Math.floor(P / 2);
    const ox     = size / 2;
    const oy     = size / 2;
    const canvas = document.createElement("canvas");
    canvas.width  = size;
    canvas.height = size;
    canvas.style.cssText = `position:absolute;left:${cx - size / 2}px;top:${cy - size / 2}px;pointer-events:none;image-rendering:pixelated;`;
    // Register immediately so cancelInflightReplayAnimations can clear it
    // even before the delay fires.
    liveAnimNodes.add(canvas);

    window.setTimeout(() => {
      if (!liveAnimNodes.has(canvas)) return; // cancelled during delay
      collisionFxLayer.appendChild(canvas);
      const ctx2  = canvas.getContext("2d");
      let frame   = 0;
      const timer = setInterval(() => {
        if (!canvas.isConnected) { clearInterval(timer); return; }
        ctx2.clearRect(0, 0, size, size);
        for (const { dx, dy, d, color } of pixels) {
          const age = frame - d;
          if (age < 0 || age >= LIFE) continue;
          ctx2.fillStyle = age === 0 ? "#ffffff" : color;
          ctx2.fillRect(ox + dx * P - half, oy + dy * P - half, P, P);
        }
        const si = frame - (R - 1);
        if (si >= 0 && si < LIFE) {
          for (const { dx, dy, color } of sparks) {
            ctx2.fillStyle = si === 0 ? "#ffffff" : color;
            ctx2.fillRect(ox + dx * P - half, oy + dy * P - half, P, P);
          }
        }
        frame++;
        if (frame > R + LIFE + 1) {
          clearInterval(timer);
          canvas.remove();
          liveAnimNodes.delete(canvas);
        }
      }, 75);
    }, delayMs);
  }

  /** Chain of pixel explosions scattered around a collision cell.
   *  Fires the central burst immediately then adds 6 secondary pops
   *  at varying offsets and delays, giving the "harvester destroyed"
   *  chain-detonation feel.  Uses proxy divs as positioning scaffolds
   *  so each secondary pop still goes through spawnPixelExplosion. */
  function spawnChainExplosion(cellEl, colors, baseDelayMs) {
    baseDelayMs = baseDelayMs || 0;
    if (!collisionFxLayer) return;
    const hostRect = collisionFxLayer.getBoundingClientRect();
    const cellRect = cellEl.getBoundingClientRect();
    const ccx = cellRect.left - hostRect.left + cellRect.width  / 2;
    const ccy = cellRect.top  - hostRect.top  + cellRect.height / 2;
    const C   = cellRect.width;

    spawnPixelExplosion(cellEl, colors, baseDelayMs);

    for (let i = 0; i < 2; i++) {
      const angle = Math.random() * Math.PI * 2;
      const dist  = C * (0.3 + Math.random() * 0.4);
      const ox    = Math.cos(angle) * dist;
      const oy    = Math.sin(angle) * dist;
      const delay = 90 + i * 130;
      const proxy = document.createElement("div");
      proxy.style.cssText = `position:absolute;width:${C}px;height:${C}px;` +
        `left:${ccx + ox - C / 2}px;top:${ccy + oy - C / 2}px;pointer-events:none;`;
      collisionFxLayer.appendChild(proxy);
      liveAnimNodes.add(proxy);
      const totalDelay = baseDelayMs + delay;
      spawnPixelExplosion(proxy, [...colors].reverse(), totalDelay);
      window.setTimeout(() => {
        proxy.remove();
        liveAnimNodes.delete(proxy);
      }, totalDelay + 700);
    }
  }

  function spawnXOverlay(cellEl, color, delayMs, opts) {
    delayMs = delayMs || 0;
    // v1.1 — ``opts.thin`` renders a slimmer, slightly tighter X. Used
    // by the dawn sweep so a destroyed probe's marker reads as lighter
    // than a harvester's heavier collision X.
    const thin = !!(opts && opts.thin);
    if (!collisionFxLayer) return;
    if (reduceMotionMq.matches) return;
    // Measure font metrics now (cell is in DOM); geometry is captured
    // fresh inside the timeout so positions are correct after repaints.
    const eoEl = cellEl.querySelector(".entity-overlay");
    const fs = eoEl ? parseFloat(getComputedStyle(eoEl).fontSize) : 18;
    const ff = eoEl ? getComputedStyle(eoEl).fontFamily : "ui-monospace,monospace";
    const tmp = document.createElement("canvas");
    const tctx = tmp.getContext("2d");
    tctx.font = `600 ${fs}px ${ff}`;
    const m = tctx.measureText("X");
    const rx_f = m.width / 2;
    const ry_f = (m.actualBoundingBoxAscent + Math.max(0, m.actualBoundingBoxDescent)) / 2;
    const lw = thin ? Math.max(1.5, fs * 0.13) : Math.max(3, fs * 0.26);
    const SPREAD = thin ? 1.1 : 1.4;
    const GROW = 360, SHRINK = 280, HOLD = 200, FADE = 400;
    window.setTimeout(() => {
      // Re-measure cell position at fire time so delayed calls (e.g. 500ms)
      // use the post-repaint coordinates, not stale pre-repaint ones.
      const cellRect = cellEl.getBoundingClientRect();
      const cw = cellRect.width, ch = cellRect.height;
      const rx_s = cw / 2 * SPREAD;
      const ry_s = ch / 2 * SPREAD;
      const W = Math.ceil(cw * SPREAD) + 2, H = Math.ceil(ch * SPREAD) + 2;
      const lx = W / 2, ly = H / 2;
      const cv = document.createElement("canvas");
      cv.width  = W;
      cv.height = H;
      cv.style.cssText = `position:fixed;` +
        `left:${cellRect.left - (W - cw) / 2}px;` +
        `top:${cellRect.top  - (H - ch) / 2}px;` +
        `pointer-events:none;z-index:20;`;
      // Intentionally NOT added to liveAnimNodes — same pattern as the
      // orbital arc ghost. The X spans a replay tick boundary, so we
      // let it self-clean rather than have cancelInflightReplayAnimations
      // kill it mid-flight.
      document.body.appendChild(cv);
      const xctx = cv.getContext("2d");
      let t0 = null;
      function tick(ts) {
        if (t0 === null) t0 = ts;
        const el = ts - t0;
        if (el >= GROW + SHRINK + HOLD + FADE) {
          xctx.clearRect(0, 0, W, H);
          cv.remove();
          return;
        }
        xctx.clearRect(0, 0, W, H);
        xctx.save();
        xctx.strokeStyle = color;
        xctx.lineWidth = lw;
        xctx.lineCap = "butt";
        if (el < GROW) {
          const e = 1 - Math.pow(1 - el / GROW, 3);
          const frac = 1 - e;
          [[-1, -1], [+1, -1], [+1, +1], [-1, +1]].forEach(([sx, sy]) => {
            xctx.beginPath();
            xctx.moveTo(lx + sx * rx_s, ly + sy * ry_s);
            xctx.lineTo(lx + sx * rx_s * frac, ly + sy * ry_s * frac);
            xctx.stroke();
          });
        } else {
          const p2 = Math.min(1, (el - GROW) / SHRINK);
          const e2 = 1 - Math.pow(1 - p2, 3);
          const ex = rx_s + (rx_f - rx_s) * e2;
          const ey = ry_s + (ry_f - ry_s) * e2;
          const fadeStart = GROW + SHRINK + HOLD;
          xctx.globalAlpha = el > fadeStart ? Math.max(0, 1 - (el - fadeStart) / FADE) : 1;
          xctx.beginPath(); xctx.moveTo(lx - ex, ly - ey); xctx.lineTo(lx + ex, ly + ey); xctx.stroke();
          xctx.beginPath(); xctx.moveTo(lx + ex, ly - ey); xctx.lineTo(lx - ex, ly + ey); xctx.stroke();
        }
        xctx.restore();
        requestAnimationFrame(tick);
      }
      requestAnimationFrame(tick);
    }, delayMs);
  }

  /** Sweep a minelayer (``◆``) across the map on a Bezier arc and
   *  HOVER ABOVE the target cell (offset upward by ~1.5 cell
   *  heights — same vertical relationship the orblift drops have).
   *
   *  Deliberately slow + chunky:
   *   * DURATION  2400ms (vs orblift's 1100ms) so the watcher has
   *     time to register the deploy.
   *   * Hover window is wide (t=0.30..0.70).
   *   * Craft glyph is rendered at 28px so it's clearly bigger
   *     than a probe/harvester glyph.
   *
   *  During the hover, ``_spawnMinePixelRain`` lets a smattering
   *  of purple particles fall FROM the hover point DOWN onto the
   *  target cell, each leaving a short vertical trail. The
   *  persistent mine marker is then revealed ~500ms after the
   *  rain begins (via the ``mine-cell-marker--deploying`` class
   *  on ``paintMinesOverlay``'s next paint). */
  function _runMinelayerArc(opts) {
    if (!mapPlayer) return;
    const cellRect = opts.targetCellRect;
    const ownerColourValue = opts.ownerColour;

    const mapRect = mapPlayer.getBoundingClientRect();
    const cx = cellRect.left + cellRect.width * 0.5;
    const cy = cellRect.top + cellRect.height * 0.5;
    const cw = cellRect.width;
    const ch = cellRect.height;
    // The minelayer hovers ABOVE the target cell so the rain
    // visibly falls from craft → cell. Offset by 1.5 cell-heights.
    const hoverCy = cy - ch * 1.5;

    const goingRight = Math.random() < 0.5;
    const tilt = (Math.random() - 0.5) * 0.7;
    const dax = goingRight ? Math.cos(tilt) : -Math.cos(tilt);
    const day = Math.sin(tilt);

    function edgeT(ox, oy, dx, dy) {
      const ts = [];
      if (Math.abs(dx) > 1e-6) {
        ts.push(dx > 0 ? (mapRect.right - ox) / dx : (mapRect.left - ox) / dx);
      }
      if (Math.abs(dy) > 1e-6) {
        ts.push(dy > 0 ? (mapRect.bottom - oy) / dy : (mapRect.top - oy) / dy);
      }
      const valid = ts.filter((t) => t > 2);
      return valid.length ? Math.min(...valid) : Math.max(mapRect.width, mapRect.height);
    }

    const tFwd = edgeT(cx, hoverCy, dax, day);
    const tBck = edgeT(cx, hoverCy, -dax, -day);
    const ax = cx + dax * tFwd, ay = hoverCy + day * tFwd;
    const bx = cx - dax * tBck, by = hoverCy - day * tBck;
    const perpX = -day, perpY = dax;
    const curve = Math.min(mapRect.width, mapRect.height) * 0.22 * (Math.random() < 0.5 ? 1 : -1);
    const midX = (8 * cx - ax - bx) / 6;
    const midY = (8 * hoverCy - ay - by) / 6;
    const c1x = midX + perpX * curve, c1y = midY + perpY * curve;
    const c2x = midX - perpX * curve, c2y = midY - perpY * curve;

    const ghost = document.createElement("span");
    ghost.className = "minelayer-craft";
    ghost.style.color = ownerColourValue;
    ghost.style.width = `${String(Math.round(cw))}px`;
    ghost.style.height = `${String(Math.round(ch))}px`;
    ghost.style.left = "0";
    ghost.style.top = "0";
    ghost.style.position = "fixed";
    ghost.textContent = "\u25C6";
    document.body.appendChild(ghost);

    function bez(p, s, c1, c2, e) {
      const q = 1 - p;
      return q * q * q * s + 3 * q * q * p * c1 + 3 * q * p * p * c2 + p * p * p * e;
    }
    function easing(t) {
      if (t <= 0.5) { const u = t * 2; return 0.5 * (1 - Math.pow(1 - u, 2.5)); }
      const u = (t - 0.5) * 2; return 0.5 + 0.5 * Math.pow(u, 2.5);
    }

    const DURATION = 1200;
    const HOVER_FROM = 0.30;
    const HOVER_TO = 0.70;
    let rainTriggered = false;
    const t0 = performance.now();

    function tick(now) {
      if (!document.body.contains(ghost)) return;
      const rawT = Math.min(1, (now - t0) / DURATION);

      let posT;
      if (rawT < HOVER_FROM) {
        posT = easing(rawT / HOVER_FROM * 0.5);
      } else if (rawT < HOVER_TO) {
        posT = 0.5;
      } else {
        const u = (rawT - HOVER_TO) / (1 - HOVER_TO);
        posT = 0.5 + easing(0.5 + u * 0.5) - 0.5;
      }

      const px = bez(posT, ax, c1x, c2x, bx) - cw * 0.5;
      const py = bez(posT, ay, c1y, c2y, by) - ch * 0.5;
      ghost.style.transform = `translate(${px.toFixed(1)}px,${py.toFixed(1)}px)`;

      if (!rainTriggered && rawT >= HOVER_FROM) {
        rainTriggered = true;
        _spawnMinePixelRain(opts.targetCell, {
          rhombusCx: cx,
          rhombusCy: hoverCy + ch * 0.5,
          rhombusHalfW: cw * 0.5,
          rhombusHalfH: ch * 0.5,
        });
      }

      if (rawT < 1) {
        requestAnimationFrame(tick);
      } else {
        ghost.remove();
      }
    }
    requestAnimationFrame(tick);
  }

  /** Drip purple particles FROM the rhombus minelayer's outline
   *  DOWN onto ``cellEl``. Each particle starts at a random point
   *  on the rhombus perimeter and falls straight down into the
   *  target cell. No trailing streak — just plain purple pixels.
   *
   *  ``opts.rhombusCx`` / ``opts.rhombusCy`` are the hover-frame
   *  centre of the minelayer (viewport coords). ``rhombusHalfW``
   *  / ``rhombusHalfH`` describe the inscribed diamond. */
  /** Drop a single ◆ glyph from the craft hover centre straight down
   *  to the target cell centre. Smooth ease-in fall. */
  function _spawnMinePixelRain(cellEl, opts) {
    if (!cellEl) return;
    const rect = cellEl.getBoundingClientRect();
    const sx = opts?.rhombusCx ?? rect.left + rect.width * 0.5;
    const sy = opts?.rhombusCy ?? rect.top - rect.height * 1.5;

    // Mirror the quincunx background-position percentages from CSS.
    // Each drop flies to the centre of its own 3×3px pixel square.
    const pixelSize = 3;
    const targets = [
      [0.20, 0.20],
      [0.80, 0.20],
      [0.50, 0.50],
      [0.20, 0.80],
      [0.80, 0.80],
    ];

    targets.forEach(([px, py], i) => {
      const endX = rect.left + (rect.width  - pixelSize) * px + pixelSize * 0.5;
      const endY = rect.top  + (rect.height - pixelSize) * py + pixelSize * 0.5;
      const drop = document.createElement("span");
      drop.className = "minelayer-drop-glyph";
      drop.textContent = "◆";
      drop.style.left = `${sx.toFixed(1)}px`;
      drop.style.top  = `${sy.toFixed(1)}px`;
      drop.style.setProperty("--dx", `${(endX - sx).toFixed(1)}px`);
      drop.style.setProperty("--dy", `${(endY - sy).toFixed(1)}px`);
      drop.style.animationDelay = `${i * 65}ms`;
      document.body.appendChild(drop);
      drop.addEventListener("animationend", () => drop.remove(), { once: true });
    });
  }

  /** v0.9.4 rev6 — Paint persistent mine markers as a static
   *  unicode square glyph (``■``) centred in the cell. No
   *  shimmer, no opacity pulse, no full-cell fill — just a
   *  visible purple glyph that reads as "mine present here".
   *
   *  Newly-laid mines (those matching a ``mine_lay`` event in
   *  ``frame.mine``) get a one-shot fade-in so the glyph never
   *  appears BEFORE the rain starts. Existing mines paint
   *  immediately. */
  function paintMinesOverlay(frame) {
    if (!collisionFxLayer || !mapPlayer) return;
    const stale = collisionFxLayer.querySelectorAll(".mine-cell-marker");
    stale.forEach((n) => n.remove());
    const mines = Array.isArray(frame?.mines_active) ? frame.mines_active : [];
    if (!mines.length) return;
    const newlyLaid = new Set();
    const mineEvents = Array.isArray(frame?.mine) ? frame.mine : [];
    for (const ev of mineEvents) {
      if (ev?.kind !== "mine_lay") continue;
      const at = Array.isArray(ev.at) ? ev.at : null;
      if (at) newlyLaid.add(`${at[0]}:${at[1]}`);
    }
    const hostRect = collisionFxLayer.getBoundingClientRect();
    for (const m of mines) {
      const x = Number(m.x);
      const y = Number(m.y);
      const cellEl = mapPlayer.querySelector(
        `[data-x="${x}"][data-y="${y}"]`,
      );
      if (!cellEl) continue;
      const cellRect = cellEl.getBoundingClientRect();
      const marker = document.createElement("div");
      marker.className = "mine-cell-marker";
      marker.textContent = "";
      if (newlyLaid.has(`${x}:${y}`)) {
        marker.classList.add("mine-cell-marker--deploying");
      }
      marker.style.left = `${cellRect.left - hostRect.left}px`;
      marker.style.top = `${cellRect.top - hostRect.top}px`;
      marker.style.width = `${Math.ceil(cellRect.width)}px`;
      marker.style.height = `${Math.ceil(cellRect.height)}px`;
      collisionFxLayer.appendChild(marker);
    }
  }

  /** v0.9.4 rev3 — Whole-map chaff static + CRT-mode easter egg.
   *
   *  Visual is the simple v0.9 whole-map snowstorm: a brief
   *  repeating-linear-gradient overlay covers the map for ~600ms
   *  signalling that every other seat's hour got smothered. The
   *  overlay is sized to the visible map (``map-player`` bounding
   *  box) so it never bleeds outside the play area.
   *
   *  Easter egg: if the user is currently in **CRT graphics mode**
   *  (and hasn't disabled glitches), we additionally trigger the
   *  existing screen-wide CRT glitch (the same one
   *  :func:`scheduleCrtGlitch` fires periodically). That's done by
   *  flipping the ``crt-viewport--glitch`` class on ``crtViewport``
   *  for the keyframe duration — no extra DOM/FX of our own. If
   *  CRT mode is off, no glitch fires; the chaff just plays as the
   *  flat white static. */
  // One whole-map static burst (~700ms) + optional CRT glitch. Split
  // out of playChaffFx so the multi-turn jam can re-fire it per turn.
  function _renderChaffStatic() {
    if (!collisionFxLayer || !mapPlayer) return;
    if (reduceMotionMq.matches) return;
    // Size the static overlay to the visible map, not the FX
    // layer, so it never bleeds outside the play area.
    const hostRect = collisionFxLayer.getBoundingClientRect();
    const mapRect = mapPlayer.getBoundingClientRect();
    const flash = document.createElement("div");
    flash.className = "chaff-static";
    flash.setAttribute(
      "style",
      `left:${mapRect.left - hostRect.left}px; ` +
      `top:${mapRect.top - hostRect.top}px; ` +
      `width:${mapRect.width}px; height:${mapRect.height}px;`,
    );
    collisionFxLayer.appendChild(flash);
    window.setTimeout(() => { flash.remove(); }, 700);

    // Easter egg: piggyback the existing CRT glitch effect — but
    // ONLY when the user is actually in CRT graphics mode with
    // glitches enabled. Re-using ``crt-viewport--glitch`` keeps
    // the chaff-triggered glitch visually identical to the
    // ambient periodic one from ``scheduleCrtGlitch``.
    const crtOn = crtEl?.checked ?? false;
    const glitchOn = glitchEl?.checked ?? true;
    if (crtOn && glitchOn && crtViewport) {
      crtViewport.classList.add("crt-viewport--glitch");
      window.setTimeout(() => {
        if (crtViewport) crtViewport.classList.remove("crt-viewport--glitch");
      }, 360);
    }
  }

  function playChaffFx(frame) {
    if (!collisionFxLayer || !mapPlayer) return;
    if (reduceMotionMq.matches) return;
    const events = Array.isArray(frame?.chaff) ? frame.chaff : [];
    if (!events.length) return;
    // v0.9.16 — chaff jams the field for CHAFF_DURATION_HOURS *turns*,
    // not a single hour. The launch event carries ``from_hour`` /
    // ``until_hour``, so replay one static burst per active turn (spaced
    // to the replay tick cadence) — the watcher sees the full multi-turn
    // jam instead of one flash that undersells how powerful chaff is.
    let turns = 1;
    for (const ev of events) {
      // Fire the launching platform's station animation (✶ burst "chaff").
      if (typeof osOnEntityArrival === "function")
        osOnEntityArrival({ kind: "chaff_flare", owner: ev.owner }, null);
      const span = Number(ev?.until_hour) - Number(ev?.from_hour) + 1;
      if (Number.isFinite(span) && span > turns) turns = span;
    }
    turns = Math.max(1, Math.min(turns, 6));
    for (let k = 0; k < turns; k += 1) {
      window.setTimeout(() => _renderChaffStatic(), k * 620);
    }
  }

  /** Play all replay animations for newly-resolved turn ticks on the
   *  live map. Iterates ticks from `startTickIdx` to the end of
   *  `replayTicks`, calling `paintReplayFrameOntoMain("forward")` on
   *  each with 620ms spacing (matching the replay ticker cadence).
   *  On completion, restores the live map view. */
  async function _playLiveTurnAnimations(startTickIdx) {
    if (_liveFxPlaying || replayTicker) return;
    if (reduceMotionMq.matches) return;
    if (startTickIdx >= replayTicks.length) return;
    _liveFxPlaying = true;
    const showEmpLulls = empLullsEl?.checked ?? true;
    try {
      for (let t = startTickIdx; t < replayTicks.length; t++) {
        if (!showEmpLulls) {
          const tick = replayTicks[t];
          if (tick?.frames?.length && tick.frames.every((f) => f?.tag === "empd")) continue;
        }
        replayTickIdx = t;
        // v1.6 — honour the launch-sequencing dwell so deferred probe/drop
        // trails (held back by ~1600ms, see _OS_LEAD_MS) finish before the
        // next tick repaints the board. Matches the replay ticker + the main
        // night cinematic; without it live playback dropped probe trails that
        // the scrubber showed fine.
        window._osPendingDwellMs = 0;
        paintReplayFrameOntoMain("forward");
        if (t < replayTicks.length - 1) {
          const dwell = Math.max(620, Number(window._osPendingDwellMs) || 0);
          await new Promise((r) => setTimeout(r, dwell));
        }
        if (mainMapSource !== "replay" || replayTicker) return;
      }
      // Let the last frame's CSS transitions finish before returning to live.
      await new Promise((r) => setTimeout(r, 820));
      if (mainMapSource === "replay" && !replayTicker) {
        mainMapSource = "live";
        if (lastLiveMapPayload && mapPlayer) paintPlayerMap(mapPlayer, lastLiveMapPayload);
      }
    } finally {
      _liveFxPlaying = false;
    }
  }

  // ── v1.1 Live turn dawn cinematic ───────────────────────────────
  //
  // Submission framing + title cards + the dawn sweep itself. The
  // sweep lives in the shared replay engine (see ``runDawnSweep`` and
  // its dispatch in ``paintReplayFrameOntoMain``) so it plays both
  // live and on forward scrub onto a ``dawn`` tick. The framing /
  // cards below only fire during the live night-resolution sequence.

  /** True between TRANSMIT and the end of the night cinematic. */
  let _resolvingActive = false;
  /** Set once the cinematic has taken the map over from the overlay. */
  let _cinematicStaged = false;
  /** Duration (ms) the most recently painted dawn sweep will run; read
   *  by ``_playNightCinematic`` so the post-dawn hold covers it. */
  // ── Heat-sweep FX (replaces cc-daylight-wash clip-path animation) ──────────
  // Engine state
  let _heatPhase      = 'off';   // 'in' | 'hold' | 'out' | 'off'
  let _heatSweepRaf   = null;
  let _heatShimmerRaf = null;
  let _heatShimmerHost = null;

  function _heatDiag(x, y) { return x * 0.85 + y * 1.15; }

  function _heatLevel(d, front, phase) {
    const dist = front - d;
    if (phase === 'hold') return 0.52;
    if (phase === 'in') {
      if (dist < -2) return 0;
      if (dist <  2) return Math.max(0, (dist + 2) / 4);
      if (dist <  6) return 1.0 - (dist - 2) / 4 * 0.48;
      return 0.52;
    }
    if (phase === 'out') {
      if (dist < -2) return 0.52;
      if (dist <  2) return 0.52 * (1 - (dist + 2) / 4);
      return 0;
    }
    return 0;
  }

  function _heatApplyCell(cell, heat, wallT) {
    const glyph = /** @type {HTMLElement|null} */ (cell.firstElementChild);
    if (!glyph) return;

    if (heat < 0.015) {
      glyph.style.filter      = '';
      glyph.style.transform   = '';
      glyph.style.textShadow  = '';
      if (glyph._hOrigText !== undefined) {
        glyph.textContent  = glyph._hOrigText;
        glyph.style.color  = glyph._hOrigColor || '';
        delete glyph._hOrigText;
        delete glyph._hOrigColor;
      }
      if (cell._hOrigBg !== undefined) {
        cell.style.background = cell._hOrigBg;
        delete cell._hOrigBg;
        delete cell._hBgRgb;
      }
      return;
    }

    if (cell._hOrigBg === undefined) {
      cell._hOrigBg = cell.style.background;
      // cache computed bg once so we can lift it without losing original colour
      const cs = getComputedStyle(cell);
      const m  = cs.backgroundColor.match(/\d+/g);
      cell._hBgRgb = m ? [+m[0], +m[1], +m[2]] : [10, 8, 18];
    }

    const isFog = cell.classList.contains('cell--fog');
    if (isFog) {
      // Probe echo cells (cell--fog-probe) keep their glyph visible through
      // the dawn sweep — only replace with ▒▒ for plain fog cells.
      if (!cell.classList.contains('cell--fog-probe')) {
        if (glyph._hOrigText === undefined) {
          glyph._hOrigText  = glyph.textContent;
          glyph._hOrigColor = glyph.style.color;
        }
        glyph.textContent = '\u2592\u2592'; // ▒▒
        const w = Math.round(90 + heat * 165);
        glyph.style.color  = `rgb(${w},${w},${w})`;
      }
      glyph.style.filter = '';
      // lift fog background toward a warm dark as heat rises
      const br = Math.round(15 + heat * 22);
      const bg = Math.round(12 + heat * 14);
      const bb = Math.round(24 + heat * 16);
      cell.style.background = `rgba(${br},${bg},${bb},0.96)`;
    } else {
      const sat = (1 + heat * 1.5).toFixed(2);
      const bri = (1 + heat * 0.45).toFixed(2);
      glyph.style.filter = `saturate(${sat}) brightness(${bri})`;
      // lift the actual cell background colour — dark cells get a warm brightening
      const [cr, cg, cb] = cell._hBgRgb;
      const lr = Math.min(255, Math.round(cr + heat * 42));
      const lg = Math.min(255, Math.round(cg + heat * 32));
      const lb = Math.min(255, Math.round(cb + heat * 24));
      cell.style.background = `rgb(${lr},${lg},${lb})`;
    }

    // warm glow via text-shadow
    const glowA  = Math.max(0, (heat - 0.2) / 0.8);
    const blur   = Math.round(3 + glowA * 5);
    const a      = (glowA * 0.7).toFixed(2);
    glyph.style.textShadow = `0 0 ${blur}px rgba(255,200,80,${a})`;

    // shimmer: char wobble (background stays grid-locked)
    if (wallT > 0 && heat > 0.15) {
      const t   = wallT * 0.001;
      const cx  = Number(cell.dataset.x) || 0;
      const cy  = Number(cell.dataset.y) || 0;
      const amp = 1.8 * Math.min(1, heat * 1.6);
      const dx  = (Math.sin(cx * 0.55 + t * 4.3 + cy * 0.31) * amp).toFixed(1);
      const dy  = (Math.cos(cy * 0.63 + t * 3.8 + cx * 0.44) * amp * 0.5).toFixed(1);
      glyph.style.transform = `translate(${dx}px,${dy}px)`;
    }
  }

  function _heatClearAll(host) {
    _heatPhase = 'off';
    if (_heatSweepRaf)   { cancelAnimationFrame(_heatSweepRaf);   _heatSweepRaf   = null; }
    if (_heatShimmerRaf) { cancelAnimationFrame(_heatShimmerRaf); _heatShimmerRaf = null; }
    _heatShimmerHost = null;
    if (host) host.style.filter = '';
    if (!host) return;
    for (const cell of host.querySelectorAll('.cell[data-x][data-y]'))
      _heatApplyCell(cell, 0, 0);
  }

  function _heatApplyInstant(host, heat) {
    if (!host) return;
    _heatPhase = heat > 0 ? 'hold' : 'off';
    for (const cell of host.querySelectorAll('.cell[data-x][data-y]'))
      _heatApplyCell(cell, heat, 0);
    if (heat > 0) {
      _heatStartShimmer(host);
    } else {
      if (host) host.style.filter = '';
    }
  }

  function _heatStartShimmer(host) {
    if (_heatShimmerRaf) cancelAnimationFrame(_heatShimmerRaf);
    _heatShimmerHost = host;
    if (host) host.style.filter = 'brightness(1.12) sepia(0.05)';
    (function shimFrame(ts) {
      if (_heatPhase !== 'hold' || !_heatShimmerHost) return;
      for (const cell of _heatShimmerHost.querySelectorAll('.cell[data-x][data-y]')) {
        const glyph = /** @type {HTMLElement|null} */ (cell.firstElementChild);
        if (!glyph) continue;
        const t   = ts * 0.001;
        const cx  = Number(cell.dataset.x) || 0;
        const cy  = Number(cell.dataset.y) || 0;
        const dx  = (Math.sin(cx * 0.55 + t * 4.3 + cy * 0.31) * 1.8).toFixed(1);
        const dy  = (Math.cos(cy * 0.63 + t * 3.8 + cx * 0.44) * 0.9).toFixed(1);
        glyph.style.transform = `translate(${dx}px,${dy}px)`;
      }
      _heatShimmerRaf = requestAnimationFrame(shimFrame);
    }(performance.now()));
  }

  function _runHeatSweep(host, kind, durationMs) {
    if (_heatSweepRaf)   { cancelAnimationFrame(_heatSweepRaf);   _heatSweepRaf   = null; }
    if (_heatShimmerRaf) { cancelAnimationFrame(_heatShimmerRaf); _heatShimmerRaf = null; }
    if (!host) return;
    const cells = Array.from(host.querySelectorAll('.cell[data-x][data-y]'));
    if (!cells.length) return;

    const phase  = kind === 'sunset' ? 'out' : 'in';
    _heatPhase   = phase;
    const MIN_D  = -4;
    let maxD     = 0;
    for (const c of cells) {
      const d = _heatDiag(Number(c.dataset.x), Number(c.dataset.y));
      if (d > maxD) maxD = d;
    }
    const MAX_D = maxD + 6;
    const rate  = (MAX_D - MIN_D) / durationMs;
    let front   = MIN_D;
    let lastTs  = null;

    (function frame(ts) {
      if (_heatPhase !== phase) return; // cancelled externally
      if (lastTs !== null) front += rate * Math.min(ts - lastTs, 50);
      lastTs = ts;
      for (const cell of cells)
        _heatApplyCell(cell, _heatLevel(_heatDiag(Number(cell.dataset.x), Number(cell.dataset.y)), front, phase), ts);

      if (front < MAX_D) {
        _heatSweepRaf = requestAnimationFrame(frame);
      } else {
        _heatSweepRaf = null;
        if (phase === 'in') {
          _heatPhase = 'hold';
          _heatStartShimmer(host);
        } else {
          // dusk done — restore everything
          for (const cell of cells) _heatApplyCell(cell, 0, 0);
          _heatPhase = 'off';
          if (host) host.style.filter = '';
        }
      }
    }(performance.now()));
  }
  // ── end heat-sweep engine ─────────────────────────────────────────────────

  let _lastDawnSweepMs = 0;
  /** Persistent board daylight ("day" | "night"). PLANNING reads night,
   *  ORBIT reads day; the horizon sweep transitions between them. */
  let _mapDaylight = "night";
  /** True once the opening NIGHT 1 card has been shown for a session. */
  let _openingCardShown = false;

  /** True while a daylight wipe animation is running (so per-frame tint
   *  flips don't fight it mid-sweep). */
  let _washAnimating = false;
  /** Replay sunrise dedupe: nights (day numbers) we've already swept this
   *  playthrough, + the previously painted frame's day. Lets the dawn
   *  wipe fire ONCE per night on forward play — keyed off the day
   *  boundary so it works even on older seasons that lack a dawn frame. */
  let _sweptReplayNights = new Set();
  let _prevPaintedReplayDay = null;

  /** Set the board daylight INSTANTLY (no wipe). DAY = the yellow wash
   *  film over the play area; NIGHT = transparent. Used for polling /
   *  replay scrub / opening. Skipped while a wipe is animating. */
  function setMapDaylight(mode) {
    _mapDaylight = mode === "day" ? "day" : "night";
    if (_washAnimating) return;
    if (_mapDaylight === "day") {
      _heatClearAll(mapPlayer);
      _heatApplyInstant(mapPlayer, 0.52);
    } else {
      _heatClearAll(mapPlayer);
    }
    // Keep .is-day in sync for any CSS that still reads it (e.g. scoreboard tints).
    if (daylightWashEl) {
      daylightWashEl.classList.remove("sweep-sunrise", "sweep-sunset");
      daylightWashEl.classList.toggle("is-day", _mapDaylight === "day");
    }
  }

  /** Play the dawn/dusk WIPE on the single yellow wash element. The film
   *  is revealed (sunrise) or cleared (sunset) left→right via clip-path.
   *  Returns the wipe duration (also stashed in ``_lastDawnSweepMs`` so
   *  the cinematic / replay autoplay holds for it). */
  function playDaylightSweep(kind) {
    const sunrise = kind !== "sunset";
    _mapDaylight = sunrise ? "day" : "night";
    _lastDawnSweepMs = 0;
    if (reduceMotionMq.matches || (!replayLastTurnFx && mainMapSource === "live")) {
      // No animation — snap to end state instantly.
      if (sunrise) { _heatClearAll(mapPlayer); _heatApplyInstant(mapPlayer, 0.52); }
      else _heatClearAll(mapPlayer);
      if (daylightWashEl) daylightWashEl.classList.toggle("is-day", sunrise);
      return 0;
    }
    const SWEEP_DUR = 2200;
    _washAnimating = true;
    _runHeatSweep(mapPlayer, kind, SWEEP_DUR);
    window.setTimeout(() => {
      _washAnimating = false;
      // dusk sweep: engine already cleared cells; dawn: already in hold+shimmer.
      if (daylightWashEl) daylightWashEl.classList.toggle("is-day", sunrise);
    }, SWEEP_DUR + 100);
    _lastDawnSweepMs = SWEEP_DUR + 120;
    return _lastDawnSweepMs;
  }

  /** Phase → daylight. Live only, and never while the cinematic /
   *  resolving frame owns the tint (it sets the final state itself). */
  function applyPhaseDaylight(phase) {
    if (mainMapSource !== "live") return;
    if (_resolvingActive || _liveFxPlaying) return;
    setMapDaylight(String(phase || "") === "orbit" ? "day" : "night");
  }

  /** Daylight a replay frame paints under: only the ``dawn`` (sunrise)
   *  frame reads as DAY (yellow wash); every other frame is NIGHT. The
   *  yellow is a brief dawn flash between nights during replay. */
  function _replayFrameDaylight(frame) {
    return frame && frame.tag === "dawn" ? "day" : "night";
  }

  /** Opening "NIGHT n BEGINS" card — fires once per fresh live session
   *  the first time we land in PLANNING (the first surface-orders night).
   *  Subsequent nights get their card from the orbit-commit sunset. */
  function maybeShowOpeningNightCard(st) {
    if (_openingCardShown) return;
    if (mainMapSource !== "live") return;
    if (_resolvingActive || _liveFxPlaying) return;
    if (!st || String(st.phase) !== "planning") return;
    _openingCardShown = true;
    setMapDaylight("night");
    if (replayLastTurnFx && !reduceMotionMq.matches) {
      const seasonLabel = _currentSeasonLabel();
      void showMapTitleCard(
        `NOX ${st.day || 1} BEGINS`,
        seasonLabel ? `— ${seasonLabel} —` : "",
        { holdMs: 1750 },
      );
    }
  }

  /** Short unit label for recaps / captions ("harvester_p1" → "H1"). */
  function _shortUnitLabel(unit) {
    const s = String(unit || "");
    if (s.startsWith("harvester")) {
      const m = s.match(/(\d+)\s*$/);
      return m ? `H${m[1]}` : "H";
    }
    if (s.startsWith("probe")) return "probe";
    if (s.startsWith("lifter") || s.startsWith("orblift")) return "lifter";
    return s || "unit";
  }

  /** Format one submitted night move into a readable recap line. */
  function _describeNightMoveForRecap(m) {
    if (!m || typeof m !== "object") return "wait";
    const a = String(m.a || "").toLowerCase();
    const at = Array.isArray(m.at) ? m.at : null;
    const to = Array.isArray(m.to) ? m.to : null;
    const xy = (p) => (p && p.length === 2 ? `(${p[0]},${p[1]})` : "");
    const unit = m.unit ? _shortUnitLabel(m.unit) : "";
    switch (a) {
      case "probe":      return `deploy probe → ${xy(at)}`;
      case "drop":       return `drop ${unit} → ${xy(at)}`;
      case "step":       return `step ${unit} → ${xy(to)}`;
      case "pickup":     return `pickup ${unit}`;
      case "wait":       return "wait";
      case "emp_launch": return `EMP launch${at ? " → " + xy(at) : ""}`;
      case "mine_lay":   return `lay mine${at ? " → " + xy(at) : ""}`;
      case "chaff_flare":return "chaff flare";
      case "waste":      return `(void) ${m.reason || "illegal"}`;
      default:           return a || "wait";
    }
  }

  /** Format one submitted orbit action into a readable recap line. */
  function _describeOrbitActionForRecap(a) {
    if (!a || typeof a !== "object") return "—";
    const kind = String(a.a || a.action || "").toLowerCase();
    switch (kind) {
      case "build_probes":   return `build ×${a.count ?? a.n ?? "?"} probes`;
      case "build_harvester":return "build harvester";
      case "build_emp":      return `build ×${a.count ?? 1} EMP`;
      case "build_mine":     return `build ×${a.count ?? 1} mine`;
      case "build_chaff":    return `build ×${a.count ?? 1} chaff`;
      default:               return kind || "—";
    }
  }

  /** Render the locked-in policy recap into the resolving overlay. */
  function _renderResolvingRecap(headline, lines) {
    if (!resolvingRecapEl) return;
    const rows = Array.isArray(lines) ? lines : [];
    const head =
      `<div class="cc-resolving-recap-head">${esc(headline)}</div>`;
    if (!rows.length) {
      resolvingRecapEl.innerHTML =
        head +
        `<div class="cc-resolving-recap-empty">// no orders — holding position</div>`;
      return;
    }
    const lis = rows
      .map(
        (text, ix) =>
          `<li><span class="cc-resolving-recap-slot">${ix + 1}</span>` +
          `<span>${esc(text)}</span></li>`,
      )
      .join("");
    resolvingRecapEl.innerHTML =
      head + `<ul class="cc-resolving-recap-list">${lis}</ul>`;
  }

  /** Phase 1 — raise the submission frame: dim the composer, show the
   *  overlay (banner + foregrounded progress + policy recap). Returns
   *  the ``<ol>`` the transmit-progress feed should write into so the
   *  timeline reads on the prominent panel rather than under the
   *  button. */
  function beginResolvingFrame({ headline, recap } = {}) {
    // v1.1 — gated by the same "last-turn FX" toggle as the cinematic.
    // When the player has turned the show off, skip the framing entirely
    // and let the transmit feed fall back to the under-button list.
    if (!replayLastTurnFx) {
      endResolvingFrame();
      return null;
    }
    _resolvingActive = true;
    _cinematicStaged = false;
    document.body.classList.add("cc-resolving");
    _renderResolvingRecap(headline || "your policy", recap || []);
    if (resolvingProgressEl) resolvingProgressEl.innerHTML = "";
    if (resolvingOverlayEl) {
      resolvingOverlayEl.classList.remove("cc-resolving-overlay--out");
      resolvingOverlayEl.hidden = false;
    }
    return resolvingProgressEl;
  }

  /** Hand the map over from the resolving overlay to the cinematic —
   *  fade the overlay out (keep the composer dim) so the dawn sweep /
   *  title cards animate on a clean board. Idempotent. */
  function stageCinematicTakeover() {
    if (_cinematicStaged) return;
    _cinematicStaged = true;
    if (resolvingOverlayEl && !resolvingOverlayEl.hidden) {
      resolvingOverlayEl.classList.add("cc-resolving-overlay--out");
      window.setTimeout(() => {
        if (_cinematicStaged && resolvingOverlayEl) {
          resolvingOverlayEl.hidden = true;
          resolvingOverlayEl.classList.remove("cc-resolving-overlay--out");
        }
      }, 480);
    }
  }

  /** Phase 3 — drop the submission frame entirely (overlay hidden +
   *  composer un-dimmed). Called once the whole cinematic + reveal is
   *  done. Idempotent. */
  function endResolvingFrame() {
    _resolvingActive = false;
    _cinematicStaged = false;
    document.body.classList.remove("cc-resolving");
    if (resolvingOverlayEl) {
      resolvingOverlayEl.hidden = true;
      resolvingOverlayEl.classList.remove("cc-resolving-overlay--out");
    }
  }

  let _tcGlitchRaf = null;

  /** Flash a title card over the map (PRAXIS BEGINS / NIGHT n - …).
   *  Resolves after the card has played so callers can sequence. */
  function showMapTitleCard(main, sub, { dawn = false, holdMs = 1600 } = {}) {
    return new Promise((resolve) => {
      if (!titleCardsEnabled) { resolve(); return; }
      if (!mapTitleCardEl || reduceMotionMq.matches) {
        window.setTimeout(resolve, reduceMotionMq.matches ? 240 : 0);
        return;
      }

      if (_tcGlitchRaf) { cancelAnimationFrame(_tcGlitchRaf); _tcGlitchRaf = null; }

      // Sync overlay dimensions to the visible map area.
      if (mapPlayer) {
        mapTitleCardEl.style.width  = mapPlayer.offsetWidth  + "px";
        mapTitleCardEl.style.height = mapPlayer.offsetHeight + "px";
      }

      mapTitleCardEl.innerHTML = "";
      const card = document.createElement("div");
      card.className = "cc-titlecard-card" + (dawn ? " cc-titlecard-card--dawn" : "");

      const mainEl = document.createElement("div");
      mainEl.className = "cc-titlecard-main";
      card.appendChild(mainEl);

      const subStr = String(sub || "");
      let subEl = null;
      if (subStr) {
        subEl = document.createElement("div");
        subEl.className = "cc-titlecard-sub";
        card.appendChild(subEl);
      }
      mapTitleCardEl.appendChild(card);
      mapTitleCardEl.hidden = false;

      void card.offsetWidth;
      card.classList.add("cc-titlecard-card--in");

      const GLITCH = "░▒▓█▓▒░·:;!?#%@$&*^~<>[]{}|\/-+=▲▼◆◈";
      const mainStr = String(main || "");
      const mainSpans = [], subSpans = [];

      for (const ch of mainStr) {
        const sp = document.createElement("span");
        sp.style.display = "inline-block";
        sp.textContent = ch === " " ? " " : GLITCH[Math.random() * GLITCH.length | 0];
        mainEl.appendChild(sp);
        if (ch !== " ") mainSpans.push({ sp, target: ch });
      }
      if (subEl) {
        for (const ch of subStr) {
          const sp = document.createElement("span");
          sp.style.display = "inline-block";
          sp.textContent = ch === " " ? " " : GLITCH[Math.random() * GLITCH.length | 0];
          subEl.appendChild(sp);
          if (ch !== " ") subSpans.push({ sp, target: ch });
        }
      }

      const allSpans = [...mainSpans, ...subSpans];
      const CHAR_STEP = 22;
      const SCRAMBLE  = 80;
      const t0 = performance.now();

      function glitchTick(ts) {
        const elapsed = ts - t0;
        let allResolved = true;
        allSpans.forEach(({ sp, target }, i) => {
          const charStart = i * CHAR_STEP;
          const charSnap  = charStart + SCRAMBLE;
          if (elapsed < charStart) {
            allResolved = false;
          } else if (elapsed < charSnap) {
            sp.textContent = GLITCH[((ts * 0.3 + i * 7.3) | 0) % GLITCH.length];
            allResolved = false;
          } else {
            sp.textContent = target;
          }
        });
        if (!allResolved) { _tcGlitchRaf = requestAnimationFrame(glitchTick); return; }

        _tcGlitchRaf = null;
        window.setTimeout(() => {
          card.classList.remove("cc-titlecard-card--in");
          card.classList.add("cc-titlecard-card--out");
          const cleanup = () => {
            window.clearTimeout(fallback);
            mapTitleCardEl.hidden = true;
            mapTitleCardEl.innerHTML = "";
            resolve();
          };
          const fallback = window.setTimeout(cleanup, 500);
          card.addEventListener("animationend", cleanup, { once: true });
        }, holdMs);
      }
      _tcGlitchRaf = requestAnimationFrame(glitchTick);
    });
  }

  /** Best-effort season name for the NIGHT title card. */
  function _currentSeasonLabel() {
    if (endgameMeta && endgameMeta.seasonName) return String(endgameMeta.seasonName);
    if (watchPickerEl && watchPickerEl.selectedOptions?.length) {
      const t = watchPickerEl.selectedOptions[0].textContent || "";
      const head = t.split("·")[0].trim();
      if (head) return head;
    }
    return "";
  }

  /** Build {id → entity-row} maps + collect surface harvesters / probes
   *  from a replay frame's ``entities`` list. */
  function _indexFrameEntities(frame) {
    const byId = new Map();
    const ents = frame && Array.isArray(frame.entities) ? frame.entities : [];
    for (const row of ents) {
      if (row && row.id) byId.set(row.id, row);
    }
    return byId;
  }

  /** Decide the X colour for a dawn-destroyed entity: cyan when it was
   *  taken by an EMP (emp / crushed_probes event on the dawn frame at
   *  its cell, or ``destroyed_by`` mentions emp), else dawn-red. */
  function _dawnDestroyColor(dawnFrame, pos, id) {
    const CYAN = "#00e8ff";
    const RED = "#ff4d4d";
    if (!pos) return RED;
    const [x, y] = pos;
    const hitAt = (list) =>
      Array.isArray(list) &&
      list.some((e) => {
        const at = e && (e.at || e.cell || (e.cx != null ? [e.cx, e.cy] : null));
        return Array.isArray(at) && Number(at[0]) === x && Number(at[1]) === y;
      });
    if (hitAt(dawnFrame?.emp) || hitAt(dawnFrame?.crushed_probes)) return CYAN;
    const row = _indexFrameEntities(dawnFrame).get(id);
    if (row && /emp/i.test(String(row.destroyed_by || ""))) return CYAN;
    return RED;
  }

  /** Horizon sweep — drives the single yellow daylight WASH (no per-cell
   *  overlays) and, on sunrise, fires the dawn destruction FX in time
   *  with the wipe (which travels left→right):
   *    * ``"sunrise"`` — wipe the yellow film IN (→ DAY); diff prev vs
   *      dawn frame so destroyed harvesters explode → carcass, expired
   *      probes get a thin X, survivors get a decay pulse.
   *    * ``"sunset"`` — wipe the film OUT (→ NIGHT); no destruction.
   *
   *  Returns the wipe duration (also in ``_lastDawnSweepMs``) so the
   *  cinematic / replay autoplay holds for the full run. */
  function runHorizonSweep(host, kind, prevFrame, dawnFrame) {
    const sunrise = kind !== "sunset";
    const total = playDaylightSweep(sunrise ? "sunrise" : "sunset");
    if (!sunrise || !host || total <= 0 || reduceMotionMq.matches) return total;

    // Spread the dawn destruction across the wipe, synced to the diagonal
    // heat-sweep front (d = x*0.85 + y*1.15, same formula as _heatDiag).
    const cells = host.querySelectorAll(".cell[data-x][data-y]");
    if (!cells.length) return total;
    let maxD = 0;
    for (const cell of cells) {
      const d = Number(cell.dataset.x) * 0.85 + Number(cell.dataset.y) * 1.15;
      if (Number.isFinite(d)) maxD = Math.max(maxD, d);
    }
    const cellAt = (x, y) =>
      host.querySelector(`.cell[data-x="${x}"][data-y="${y}"]`);
    const delayFor = (x, y) =>
      maxD > 0 ? Math.round(((x * 0.85 + y * 1.15) / maxD) * total * 0.82) : 0;

    const prevById = _indexFrameEntities(prevFrame);
    const dawnById = _indexFrameEntities(dawnFrame);
    for (const [id, prev] of prevById) {
      const after = dawnById.get(id);
      const pos = Array.isArray(prev.surface) ? prev.surface : null;
      if (!pos) continue;
      const cell = cellAt(pos[0], pos[1]);
      if (!cell) continue;
      const delay = delayFor(Number(pos[0]), Number(pos[1]));
      if (prev.t === "harvester") {
        const afterSurface = after && Array.isArray(after.surface);
        if (!after || !afterSurface) {
          const color = _dawnDestroyColor(dawnFrame, pos, id);
          spawnChainExplosion(cell, [color, "#ffd166", "#ff7a3c"], delay + 40);
          spawnXOverlay(cell, color, delay + 260, { thin: false });
        }
      } else if (prev.t === "probe") {
        if (!after) {
          const liveVision = prev.owner === replayViewSeat
            || _replayCellVisibleToViewer(prevFrame, pos)
            || _viewerHasProbeEchoAt(prevFrame, pos);
          if (liveVision) {
            spawnXOverlay(cell, _dawnDestroyColor(dawnFrame, pos, id), delay + 100, { thin: true });
          }
        } else {
          window.setTimeout(() => {
            cell.classList.add("cell--dawn-decay");
            window.setTimeout(() => cell.classList.remove("cell--dawn-decay"), 640);
          }, delay + 40);
        }
      }
    }
    return total;
  }

  /** Back-compat shim: the replay dispatch calls the sunrise sweep. */
  function runDawnSweep(host, prevFrame, dawnFrame) {
    return runHorizonSweep(host, "sunrise", prevFrame, dawnFrame);
  }

  /** v0.9.13 — night-turn cinematic. Plays the just-resolved night as a
   *  forward replay on the main map, THEN reveals the live end-state, THEN
   *  lets ``refreshStatus`` pop the pre-orbital recap (+ briefing) — the
   *  reveal order the player asked for. ``startTickIdx`` is the first tick
   *  of the freshly-landed night (``prevTickCount`` from the replay pull).
   *
   *  The DUSK slot tick is SKIPPED during the animation pass (the night
   *  already opened via the orbit-commit sunset); the DAWN slot plays its
   *  sunrise wash but its recap is suppressed and pops once, at the end,
   *  after the live swap. If the user
   *  scrubs / jumps mid-cinematic (``mainMapSource`` flips off "replay" or a
   *  ``replayTicker`` starts) we bail and leave their interaction alone. */
  async function _playNightCinematic(startTickIdx) {
    const revealLiveAndReport = async () => {
      mainMapSource = "live";
      if (lastLiveMapPayload && mapPlayer) {
        paintPlayerMap(mapPlayer, lastLiveMapPayload);
        if (_heatPhase === "hold") _heatApplyInstant(mapPlayer, 0.52);
        try { paintBlueSignOverlay(lastBlueSign); } catch (_e) {}
        try { paintRedsignOverlay(); } catch (_e) {}
        try { paintPlannedOrdersOverlay(); } catch (_e) {}
      }
      // refreshStatus now pops the recap/briefing (suppress flag is clear,
      // mainMapSource is "live") — i.e. AFTER the replay + end-state reveal.
      await refreshStatus();
      // v1.1 — the whole cinematic + reveal + recap is done; drop the
      // submission frame (overlay hidden, composer un-dimmed) so the
      // next-phase controls come back.
      endResolvingFrame();
    };

    if (startTickIdx >= replayTicks.length || _liveFxPlaying || replayTicker) {
      await revealLiveAndReport();
      return;
    }

    _liveFxPlaying = true;
    const showEmpLulls = empLullsEl?.checked ?? true;
    let interrupted = false;
    try {
      // v1.1 — hand the map over from the resolving overlay.
      stageCinematicTakeover();
      // v1.3 — DUSK (hour 0) is the ORBITAL RESOLVE beat: it owns the
      // post-orbital opening board and drives the station's catapult-load /
      // blue-lift / +score staging. Play it FIRST so the freshly-committed
      // orbit is reviewable before the surface phase. The orbit-commit sunset
      // already washed the map to night, so paint it "jump" (no double
      // wash / "NIGHT n begins" card) and hold for the load animation.
      let firstTick = startTickIdx;
      if (replayTicks[startTickIdx]?.slot === "dusk") {
        replayTickIdx = startTickIdx;
        _lastDawnSweepMs = 0;
        paintReplayFrameOntoMain("jump");
        const duskHold = Math.max(900, Number(window._osPendingDwellMs) || 0);
        await new Promise((r) => setTimeout(r, duskHold));
        if (mainMapSource !== "replay" || replayTicker) {
          interrupted = true;
          return;
        }
        firstTick = startTickIdx + 1;
      }
      // Then open the surface phase with the PRAXIS BEGINS card.
      await showMapTitleCard("PRAXIS BEGINS", "", { holdMs: 1750 });
      // Only bail if the user kicked off their own playback while the
      // opening card played.
      if (replayTicker) {
        interrupted = true;
        return;
      }
      for (let t = firstTick; t < replayTicks.length; t++) {
        const tick = replayTicks[t];
        // Safety: any stray DUSK past the opener (shouldn't occur mid-night)
        // is skipped — the opener above already played this night's DUSK.
        if (tick && tick.slot === "dusk") {
          continue;
        }
        if (
          !showEmpLulls
          && tick?.frames?.length
          && tick.frames.every((f) => f?.tag === "empd")
        ) {
          continue;
        }
        replayTickIdx = t;
        // Reset the sweep clock so a non-dawn tick doesn't inherit the
        // previous dawn's hold; ``paintReplayFrameOntoMain`` re-sets it
        // when it actually runs the sweep.
        _lastDawnSweepMs = 0;
        // v1.6 — reset the sequencing dwell before painting so it reflects
        // only THIS tick's request. ``runReplayAnimationsTick`` bumps it to
        // ``_maxLead + 1300`` on a tick that fires a launch→surface sequence
        // (probe/harvester drop is held back by ~1600ms, see _OS_LEAD_MS);
        // the station catapult LOAD/LAUNCH may also raise it. Without honouring
        // it here the fixed 620ms hold steps onto the next tick — which
        // repaints the board — before the deferred probe streak ever fires,
        // so live cinematic dropped probe trails that scrub/autoplay showed.
        window._osPendingDwellMs = 0;
        paintReplayFrameOntoMain("forward");
        // Hold longer on the dawn tick so the sunrise sweep + destruction
        // finishes before we step away (or reveal), and at least as long as
        // any pending launch-sequencing dwell requested during the paint.
        let holdMs = _lastDawnSweepMs > 0 ? Math.max(620, _lastDawnSweepMs) : 620;
        holdMs = Math.max(holdMs, Number(window._osPendingDwellMs) || 0);
        if (t < replayTicks.length - 1) {
          await new Promise((r) => setTimeout(r, holdMs));
        }
        if (mainMapSource !== "replay" || replayTicker) {
          interrupted = true;
          return;
        }
      }
      // Let the last frame's CSS transitions (and any dawn sweep that
      // landed on the final tick) settle before the live swap.
      await new Promise((r) => setTimeout(r, Math.max(820, _lastDawnSweepMs)));
      if (mainMapSource !== "replay" || replayTicker) {
        interrupted = true;
      }
      // v1.1 — the NIGHT n - season card belongs to the ORBIT submit
      // ("orbital praxis on"), not the end of the surface-policy night.
      // It fires from ``submitSoloOrbit`` as the next night opens.
    } finally {
      _liveFxPlaying = false;
    }
    if (interrupted) return;
    await revealLiveAndReport();
  }

  /** v0.9.4 rev4 — Rhombus EMP cloud overlay (max-minimalist).
   *
   *  Visual rules:
   *
   *  * **Shape = rhombus / Manhattan disk.** Iterate ``|dx|+|dy|
   *    <= r`` so the AoE reads as a clean diamond.
   *  * **Each tile fully covers its cell.** No glyphs, no
   *    centered text. We render four discrete "fill rates" by
   *    setting a flat blue background at one of four opacity
   *    levels (mapping to ``░ ▒ ▓ █`` = 25/50/75/100%). The cells
   *    are positioned edge-to-edge so the rhombus reads as one
   *    contiguous block, not a grid of dotted tiles.
   *  * **Random fill rate per cell.** Each tile picks one of the
   *    four shade levels on every ticker tick so the field
   *    shimmers like static.
   *  * **Opacity pulse only.** The animation pulses the cell's
   *    own opacity multiplier between 0.40 and 1.00 so the
   *    underlying terrain stays partially visible through the
   *    cloud.
   *  * **No glow, no border, no halo.** */

  // ASCII density ramp — sparse to dense. The wave function maps
  // a 0..1 value onto this array; the result flows across the grid
  // over time, producing rolling cloud bands.
  const _EMP_CHARS = ["░░", "░▒", "▒▒", "▒▓", "▓▓", "██"];

  // Paint one cloud tile for time ``t``: stamp the density glyph.
  function _applyEmpTile(tile, t) {
    tile.textContent = _empCharAt(Number(tile.dataset.gx), Number(tile.dataset.gy), t);
  }

  function _empCharAt(gx, gy, t) {
    const v = Math.sin(gx * 0.85 + t * 1.1)
            + Math.sin(gy * 0.72 + t * 0.8)
            + Math.sin((gx - gy) * 0.55 + t * 1.5) * 0.6;
    const norm = Math.max(0, Math.min(1, (v / 2.6 + 1) * 0.5));
    // v0.9.15 — bias the ramp toward the LOW-density end (gamma > 1) so the
    // sparse "░░" block shows more often and the full cyan "██" square is
    // comparatively rare; the cloud reads lighter / patchier overall.
    const biased = Math.pow(norm, 2.0);
    return _EMP_CHARS[Math.min(_EMP_CHARS.length - 1, Math.floor(biased * _EMP_CHARS.length))];
  }

  let _empCloudT = 0;
  let _empExpansionActive = false;
  let _empExpansionLatestFrame = null;
  let _empDissipating = false;
  let _empDissipateTimer = null;
  // Tracks which (gx,gy) cells had BOTH a cloud AND a harvester on the
  // previous paintEmpCloudOverlay call. X fires only on the delta so it
  // triggers once per entry event regardless of scrub direction.
  const _prevEmpHarvesterKeys = new Set();

  function _cancelEmpDissipate() {
    if (_empDissipateTimer) { clearTimeout(_empDissipateTimer); _empDissipateTimer = null; }
    _empDissipating = false;
  }

  // Cycle tiles down through the density ramp then fade + remove.
  function _dissipateEmpCells(cells) {
    if (!cells.length) return;
    _stopEmpScrambleTicker();
    _empDissipating = true;
    const STEP_MS = 58;
    const FADE_MS = 220;

    // Each tile steps down independently from wherever the scramble left it.
    // A small position-derived start delay breaks lockstep so the cloud
    // crumbles in a ripple rather than all at once.
    function dissipeTile(tile, idx) {
      if (!_empDissipating || !tile.isConnected) return;
      if (idx > 0) {
        tile.textContent = _EMP_CHARS[idx - 1];
        const jitter = (Math.random() - 0.5) * 18; // ±9 ms per step
        setTimeout(() => dissipeTile(tile, idx - 1), STEP_MS + jitter);
      } else {
        tile.style.transition = `opacity ${FADE_MS}ms ease-out`;
        tile.style.opacity = "0";
        setTimeout(() => { if (tile.isConnected) tile.remove(); }, FADE_MS + 20);
      }
    }

    for (const tile of cells) {
      const cur = tile.textContent;
      const idx = _EMP_CHARS.indexOf(cur);
      const startIdx = idx >= 0 ? idx : _EMP_CHARS.length - 1;
      // 0–50 ms stagger derived from tile position — nearby tiles feel continuous
      const gx = Number(tile.dataset.gx) || 0;
      const gy = Number(tile.dataset.gy) || 0;
      const startDelay = ((gx * 17 + gy * 31) % 6) * 10;
      setTimeout(() => dissipeTile(tile, startIdx), startDelay);
    }

    // _empDissipating is cleared by _cancelEmpDissipate or when all tiles
    // self-remove; mark timer null since we no longer use a single handle.
    _empDissipateTimer = null;
  }

  // Fog wave: summed-sine plasma pattern animates fog glyph opacity.
  let _fogWaveT = 0;

  function _fogOpacityAt(x, y, t) {
    const v = Math.sin(x * 0.38 + t * 0.28)
            + Math.sin(y * 0.32 + t * 0.22)
            + Math.sin(x * 0.55 + y * 0.71 + t * 0.38);
    const norm = Math.max(0, Math.min(1, (v / 3.0 + 1) * 0.5));
    return (0.19 + norm * 0.26).toFixed(3);
  }

  function _applyFogWave() {
    if (!mapPlayer || reduceMotionMq.matches) return;
    for (const cell of mapPlayer.querySelectorAll(".cell--fog")) {
      const glyph = /** @type {HTMLElement|null} */ (cell.firstElementChild);
      if (!glyph) continue;
      glyph.style.opacity = _fogOpacityAt(
        Number(cell.dataset.x), Number(cell.dataset.y), _fogWaveT,
      );
    }
  }

  function _startFogWaveTicker() {
    if (window._fogWaveTimer) return;
    window._fogWaveTimer = setInterval(() => {
      _fogWaveT += 0.35;
      _applyFogWave();
    }, 250);
  }

  function _stopEmpScrambleTicker() {
    if (window._empScrambleTimer) {
      clearInterval(window._empScrambleTimer);
      window._empScrambleTimer = null;
    }
  }

  // Flash each Manhattan-distance ring of the EMP footprint in sequence,
  // then call onDone so the persistent cloud overlay can be painted.
  function _playEmpExpansion(frame, onDone) {
    const clouds = Array.isArray(frame?.emp_clouds) ? frame.emp_clouds : [];
    if (!clouds.length || !collisionFxLayer || !mapPlayer) {
      onDone();
      return;
    }
    const hostRect = collisionFxLayer.getBoundingClientRect();
    const RING_STAGGER = 28;
    const RING_DUR = 100;
    let maxDist = 0;
    for (const cloud of clouds) {
      const cx0 = Number(cloud.cx);
      const cy0 = Number(cloud.cy);
      const r = Number(cloud.r || 0);
      for (let dy = -r; dy <= r; dy++) {
        for (let dx = -r; dx <= r; dx++) {
          const dist = Math.abs(dx) + Math.abs(dy);
          if (dist > r) continue;
          maxDist = Math.max(maxDist, dist);
          const cellEl = mapPlayer.querySelector(
            `[data-x="${cx0 + dx}"][data-y="${cy0 + dy}"]`,
          );
          if (!cellEl) continue;
          const cellRect = cellEl.getBoundingClientRect();
          const tile = document.createElement("div");
          tile.className = "emp-expand-cell";
          tile.style.left   = `${cellRect.left - hostRect.left}px`;
          tile.style.top    = `${cellRect.top  - hostRect.top}px`;
          tile.style.width  = `${Math.ceil(cellRect.width)}px`;
          tile.style.height = `${Math.ceil(cellRect.height)}px`;
          tile.style.animationDelay = `${dist * RING_STAGGER}ms`;
          collisionFxLayer.appendChild(tile);
        }
      }
    }
    const totalMs = maxDist * RING_STAGGER + RING_DUR + 60;
    setTimeout(() => {
      collisionFxLayer.querySelectorAll(".emp-expand-cell").forEach((t) => t.remove());
      onDone();
    }, totalMs);
  }

  function paintEmpCloudOverlay(frame) {
    if (!collisionFxLayer || !mapPlayer) return;
    _stopEmpScrambleTicker();
    if (_empExpansionActive) {
      _empExpansionLatestFrame = frame;
      return;
    }
    const clouds = Array.isArray(frame?.emp_clouds) ? frame.emp_clouds : [];
    const staleEls = Array.from(collisionFxLayer.querySelectorAll(".emp-cloud-cell"));
    if (!clouds.length) {
      // No cloud this frame — dissolve any lingering tiles organically.
      if (staleEls.length && !_empDissipating) _dissipateEmpCells(staleEls);
      return;
    }
    // New cloud incoming — cancel any in-progress dissolve and repaint.
    _cancelEmpDissipate();
    staleEls.forEach((n) => n.remove());
    const hostRect = collisionFxLayer.getBoundingClientRect();
    const cells = [];
    for (const cloud of clouds) {
      const cx0 = Number(cloud.cx);
      const cy0 = Number(cloud.cy);
      const r = Number(cloud.r || 0);
      for (let dy = -r; dy <= r; dy += 1) {
        const absDy = Math.abs(dy);
        for (let dx = -r; dx <= r; dx += 1) {
          if (Math.abs(dx) + absDy > r) continue;
          const cellEl = mapPlayer.querySelector(
            `[data-x="${cx0 + dx}"][data-y="${cy0 + dy}"]`,
          );
          if (!cellEl) continue;
          const cellRect = cellEl.getBoundingClientRect();
          const tile = document.createElement("div");
          tile.className = "emp-cloud-cell";
          // Cover the EXACT cell bounds so the rhombus reads as
          // one contiguous shape, not a centered chip. Use
          // Math.ceil on width/height to bleed an extra subpixel
          // and kill any anti-aliased gaps between adjacent tiles.
          tile.style.left = `${cellRect.left - hostRect.left}px`;
          tile.style.top = `${cellRect.top - hostRect.top}px`;
          tile.style.width = `${Math.ceil(cellRect.width)}px`;
          tile.style.height = `${Math.ceil(cellRect.height)}px`;
          const gx = cx0 + dx;
          const gy = cy0 + dy;
          const cycleMs = 1400;
          const cellPhase = ((gx * 1237 + gy * 2749) % cycleMs + cycleMs) % cycleMs;
          const wallD = (performance.now() % cycleMs + cellPhase) % cycleMs;
          tile.style.animationDelay = `-${wallD.toFixed(0)}ms`;
          tile.dataset.gx = String(gx);
          tile.dataset.gy = String(gy);
          _applyEmpTile(tile, _empCloudT);
          collisionFxLayer.appendChild(tile);
          cells.push(tile);
        }
      }
    }
    if (cells.length) {
      window._empScrambleTimer = window.setInterval(() => {
        _empCloudT += 0.18;
        for (const tile of cells) {
          _applyEmpTile(tile, _empCloudT);
        }
      }, 90);
      // Cyan X on harvesters that are newly inside the cloud this render.
      // Compare against previous call's snapshot so the X fires on the
      // delta: once per entry event, re-fires correctly when scrubbing
      // back through the transition tick.
      const curHarvKeys = new Set();
      if (mapPlayer && !reduceMotionMq.matches) {
        for (const tile of cells) {
          const key = `${tile.dataset.gx},${tile.dataset.gy}`;
          const cellEl = mapPlayer.querySelector(
            `[data-x="${tile.dataset.gx}"][data-y="${tile.dataset.gy}"]`,
          );
          if (cellEl && cellEl.querySelector(".entity-overlay")) {
            curHarvKeys.add(key);
            if (!_prevEmpHarvesterKeys.has(key)) {
              spawnXOverlay(cellEl, "#00e8ff", 0);
            }
          }
        }
      }
      _prevEmpHarvesterKeys.clear();
      for (const k of curHarvKeys) _prevEmpHarvesterKeys.add(k);
    } else {
      _prevEmpHarvesterKeys.clear();
    }
  }

  // v0.9.x — BLUE-SIGN overlay (RULEBOOK §4.6). A static, persistent,
  // fog-independent radiative smear over each blue pocket, visible from
  // orbit to every house. It deliberately does NOT mark the exact blue
  // squares — the centroid is jittered off-true and the area bleeds —
  // so it only hints "blue is roughly around here". Painted on the
  // shared FX layer over the player map (including fog cells), modelled
  // on ``paintEmpCloudOverlay``. Intensity drives the cell opacity.
  function paintBlueSignOverlay(_regions) {
    // Blue-sign is now baked into fog glyph colour during map render.
    // Clear any divs left from before the migration.
    collisionFxLayer
      ?.querySelectorAll(".blue-sign-cell")
      .forEach((n) => n.remove());
  }

  /** v1.x — paint the REDSIGN pulse overlay (RULEBOOK §4.11).
   *
   *  For every visible region (day-gated in replay), drop a pulsing red
   *  blob over each smear cell. Fog cells get a strong glow; echo/visible
   *  cells get a translucent glow so the underlying terrain still reads.
   *  A brighter "beacon" pulse marks the (approximate, jittered) centre —
   *  the map never pinpoints the exact pure square. Rebuilt only when the
   *  overlay changes or the map resizes, so the CSS pulse breathes
   *  smoothly across ordinary repaints. */
  function paintRedsignOverlay() {
    if (!collisionFxLayer || !mapPlayer) return;
    collisionFxLayer
      .querySelectorAll(".redsign-cell,.redsign-beacon")
      .forEach((n) => n.remove());
    const regions = _redsignVisibleRegions();
    if (!regions.length) return;
    const hostRect = collisionFxLayer.getBoundingClientRect();
    for (const region of regions) {
      const cells = Array.isArray(region?.cells) ? region.cells : [];
      for (const c of cells) {
        const x = Number(c[0]);
        const y = Number(c[1]);
        const intensity = Math.max(0, Math.min(1, Number(c[2]) || 0));
        if (!intensity) continue;
        const cellEl = mapPlayer.querySelector(
          `[data-x="${x}"][data-y="${y}"]`,
        );
        if (!cellEl) continue;
        // Only hint through the UNKNOWN. On live/echo tiles the player can
        // actually see the terrain (including the pure RED seam itself), so
        // the smear is redundant/ugly there — suppress it. It lives on fog
        // only; as you explore toward the seam the sign recedes to the
        // remaining fog and the revealed terrain speaks for itself.
        if (!cellEl.classList.contains("cell--fog")) continue;
        const cellRect = cellEl.getBoundingClientRect();
        if (!cellRect.width) continue;
        const blob = document.createElement("div");
        blob.className = "redsign-cell redsign-cell--fog";
        // Light-shade unicode fill (two chars = one 2ch board cell); a
        // touch denser toward the seam centre so intensity still reads.
        blob.textContent = intensity >= 0.7 ? "▒▒" : "░░";
        blob.style.left = `${cellRect.left - hostRect.left}px`;
        blob.style.top = `${cellRect.top - hostRect.top}px`;
        blob.style.width = `${cellRect.width}px`;
        blob.style.height = `${cellRect.height}px`;
        // Match the board's cell metric (2ch × 1em) so ``░░`` tiles exactly.
        blob.style.fontSize = `${cellRect.height}px`;
        blob.style.lineHeight = `${cellRect.height}px`;
        blob.style.setProperty("--rs-int", String(intensity));
        // Pseudo-random per-cell phase across the full 2.4s cycle so the
        // field shimmers unevenly rather than blinking in unison.
        blob.style.animationDelay = `${(((x * 7 + y * 13) % 24) * 0.1).toFixed(2)}s`;
        collisionFxLayer.appendChild(blob);
      }
      // Approximate centre beacon — a stronger pulse ring. Anchored on the
      // rounded centre cell (already jittered off the true seam server-side).
      const ctr = Array.isArray(region?.center) ? region.center : null;
      if (ctr) {
        const cxi = Math.max(0, Math.round(Number(ctr[0])));
        const cyi = Math.max(0, Math.round(Number(ctr[1])));
        const cEl = mapPlayer.querySelector(
          `[data-x="${cxi}"][data-y="${cyi}"]`,
        );
        if (cEl) {
          const r = cEl.getBoundingClientRect();
          if (r.width) {
            const beacon = document.createElement("div");
            beacon.className = "redsign-beacon";
            beacon.style.left = `${r.left - hostRect.left + r.width / 2}px`;
            beacon.style.top = `${r.top - hostRect.top + r.height / 2}px`;
            beacon.title = "RED SIGN — a pure RED seam blazed into view near here";
            collisionFxLayer.appendChild(beacon);
          }
        }
      }
    }
  }

  /** v1.x — one-shot discovery BURST for a redsign region: a red RHOMBUS
   *  pulse that expands + fades over the (jittered) seam centre, echoing the
   *  player-coloured probe-landing ripple but diamond-shaped and always red.
   *  Fired once at the discovery frame (see the trigger in the replay
   *  painter), delayed so it lands AFTER the probe streak / harvester step
   *  that revealed the seam. Body-anchored + fixed like ``.probe-ripple`` so
   *  a following tick's ``cancelInflightReplayAnimations`` never clears it. */
  function spawnRedsignBurst(region) {
    if (!mapPlayer) return;
    const ctr = Array.isArray(region?.center) ? region.center : null;
    if (!ctr) return;
    const cx = Math.max(0, Math.round(Number(ctr[0])));
    const cy = Math.max(0, Math.round(Number(ctr[1])));
    const cEl = mapPlayer.querySelector(`[data-x="${cx}"][data-y="${cy}"]`);
    if (!cEl) return;
    const r = cEl.getBoundingClientRect();
    if (!r.width) return;
    const burst = document.createElement("div");
    burst.className = "redsign-burst";
    burst.style.left = `${(r.left + r.width * 0.5).toFixed(1)}px`;
    burst.style.top = `${(r.top + r.height * 0.5).toFixed(1)}px`;
    document.body.appendChild(burst);
    burst.addEventListener("animationend", () => burst.remove(), { once: true });
    // Safety sweep in case the element is scrolled off before animationend.
    window.setTimeout(() => { try { burst.remove(); } catch (_e) {} }, 2600);
  }

  // ─────────────────────────────────────────────────────────────────
  // v0.7.5 — Universal replay strip, scoreboard, agent feed, vault
  // reconstruction. All of this layer is read-only / view-only; the
  // canonical state lives on the server (live: status / inventory;
  // replay: persisted replay frames + SOC_AGENT_INVOCATION rows).
  // ─────────────────────────────────────────────────────────────────

  /** Build the human-readable slot label that sits beside the
   *  scrub controls. Replaces the old ``# 8 / 62`` global tick
   *  counter with the in-game ``Night 3 · praxis hour 07`` that
   *  actually means something to the watcher. Boundary frames
   *  (opening / dawn) get a tag instead of an hour. */
  function formatReplaySlotLabel(frame) {
    if (!frame) return "";
    const day = frame.day != null ? Number(frame.day) : null;
    const hour = (typeof frame.hour === "number" && frame.hour > 0)
      ? Number(frame.hour) : null;
    if (day == null) return "";
    if (hour != null) {
      return `Nox ${day} · praxis hour ${String(hour).padStart(2, "0")}`;
    }
    // Boundary frames: opening, dawn, swap-collision summary.
    if (frame.tag === "open") return `Nox ${day} · praxis opens`;
    if (frame.tag === "dawn") return `Nox ${day} · Aurora`;
    return `Nox ${day}`;
  }

  /** Phases where the engine is still accepting policies (i.e. the
   *  game is live, not just being replayed). Used to drive the LIVE
   *  button pulse animation. */
  const LIVE_ACTIVE_PHASES = new Set([
    "planning",
    "policy_open",
    "night_resolving",
    "dawn",
    "dawn_phase",
  ]);

  /** True iff the active session is a finished season (read-only) or
   *  no session is loaded. Replay/watch mode loads a finished season
   *  so the LIVE button stops pulsing. */
  function isLiveGameActive() {
    if (WATCH_MODE) return false;
    if (!sessionId) return false;
    if (!livePhase) return false;
    if (livePhase === "season_complete") return false;
    return LIVE_ACTIVE_PHASES.has(livePhase);
  }

  /** Toggle the pulse class on the LIVE button. Idempotent. */
  function updateLiveButtonPulse() {
    if (!replayLiveBtn) return;
    if (isLiveGameActive()) {
      replayLiveBtn.classList.add("cli-btn--live-pulse");
    } else {
      replayLiveBtn.classList.remove("cli-btn--live-pulse");
    }
  }

  /** Whether the opponent's per-seat perspective (OBS / Pn view
   *  buttons, rival vault tabs) should be exposed.
   *
   *  This is a SESSION-CONTEXT privilege, not a playback-state one:
   *    - WATCH_MODE          — the dedicated watcher/replay page is
   *                            omniscient (?session / ?season / ?watch).
   *    - season_complete     — the game is over, so even on the live
   *                            page the rival's vault is fair game.
   *
   *  Crucially it is NOT keyed on ``mainMapSource === "replay"``. On
   *  the live page the source flips to "replay" the instant the human
   *  hits PLAY to review THEIR OWN last night — that must stay
   *  self-only (no rival fog-of-war / vault leak), while still letting
   *  the player scrub their own animations and watch their own vault
   *  update. */
  function opponentSeatVisible() {
    if (WATCH_MODE) return true;
    if (livePhase === "season_complete") return true;
    return false;
  }

  /** Show/hide the per-seat sub-tabs based on the current mode. */
  function updateSeatTabVisibility() {
    const showOpp = opponentSeatVisible();
    // v0.9.11 — VAULT tabs are now rebuilt dynamically (N-seat aware).
    renderVaultSeatTabs();
    // v0.9.18 — AGENT tabs are likewise rebuilt dynamically (one per
    // active seat) so p3/p4 feeds are reachable in 3-/4-player replays.
    renderAgentSeatTabs();
    // If we're sitting on a now-hidden opponent tab, snap back to self.
    if (!showOpp && agentSeat !== MY_SEAT) setAgentSeat(MY_SEAT);
    syncFullMapCheatVisibility();
  }

  /** v0.9.x — the FULL MAP (omniscient, no-fog) observer view is a CHEAT
   *  during live play. Expose it only in an omniscient session context
   *  (the dedicated watcher page or a finished season — i.e. whenever
   *  ``opponentSeatVisible()`` is true); hide it outright while a game is
   *  actively being played so the player can't peek the whole board. */
  function syncFullMapCheatVisibility() {
    if (!fullMapBlock) return;
    fullMapBlock.hidden = !opponentSeatVisible();
  }

  /** Update the single-line "now playing" ticker pinned below the
   *  replay controls. Always reflects the most recent action — the
   *  cursor frame in replay mode, or the latest engine caption in
   *  live mode. */
  function updateNowPlayingStrip() {
    if (!replayNowClockEl || !replayNowCaptionEl) return;

    // Replay mode — drive from the cursor frame.
    if (mainMapSource === "replay" && replayTicks.length) {
      const tickIdx = Math.max(
        0, Math.min(replayTickIdx, replayTicks.length - 1),
      );
      const tick = replayTicks[tickIdx];
      const frame = nightReplayFrames[tick?.lastFrameIdx];
      const day = frame && frame.day != null ? Number(frame.day) : null;
      const hour = (typeof frame?.hour === "number" && frame.hour > 0)
        ? Number(frame.hour) : null;
      replayNowClockEl.textContent =
        `D${day ?? "—"} H${hour != null ? String(hour).padStart(2, "0") : "—"}`;
      // Caption: strip duplicate owner prefix so the row reads clean.
      let caption = String(frame?.caption || "");
      if (frame?.owner) {
        const colonPrefix = `${frame.owner}: `;
        const spacePrefix = `${frame.owner} `;
        if (caption.startsWith(colonPrefix)) caption = caption.slice(colonPrefix.length);
        else if (caption.startsWith(spacePrefix)) caption = caption.slice(spacePrefix.length);
      }
      const ownerTag = frame?.owner ? `[${playerTag(frame.owner)}] ` : "";
      replayNowCaptionEl.textContent = ownerTag + caption;
      // State data-attrs drive the colour cascade in CSS.
      replayNowCaptionEl.dataset.seat = frame?.owner || "";
      const failed = frame?.outcome === "failed"
        || frame?.tag === "waste"
        || frame?.tag === "damaged";
      const boundary = !frame?.owner;
      replayNowCaptionEl.dataset.state = failed
        ? "failed"
        : boundary
        ? "boundary"
        : "ok";
      return;
    }

    // Live mode — drive from the latest server log entry. We pull
    // the day from livePhase context; hour stays "--" because the
    // night hasn't resolved yet for the entry the user is reading.
    const liveCap = lastLiveLogLine();
    if (!liveCap) {
      replayNowClockEl.textContent = "D— H—";
      replayNowCaptionEl.textContent = sessionId
        ? "# waiting for engine…"
        : "# idle — start NEW GAME";
      delete replayNowCaptionEl.dataset.seat;
      delete replayNowCaptionEl.dataset.state;
      return;
    }
    replayNowClockEl.textContent =
      `D${liveCap.day ?? "—"} H${liveCap.hour != null ? String(liveCap.hour).padStart(2, "0") : "—"}`;
    replayNowCaptionEl.textContent = liveCap.text;
    if (liveCap.seat) replayNowCaptionEl.dataset.seat = liveCap.seat;
    else delete replayNowCaptionEl.dataset.seat;
    replayNowCaptionEl.dataset.state = liveCap.failed ? "failed" : "ok";
  }

  /** Pull the most recent line from the hidden #orch-log buffer
   *  (which is kept in sync with st.log_tail by renderOrchLog) and
   *  return a structured snapshot for the now-playing strip. */
  function lastLiveLogLine() {
    if (!orchLogEl) return null;
    const lines = orchLogEl.querySelectorAll(".log-line");
    if (!lines.length) return null;
    const last = lines[lines.length - 1];
    const text = String(last.textContent || "").trim();
    if (!text || text.startsWith("#")) return null;
    // Try to parse "[Hxx] " prefix the engine emits during PRAXIS.
    let hour = null;
    const hMatch = text.match(/^\[H(\d{2})\]\s+/);
    let bare = text;
    if (hMatch) {
      hour = Number(hMatch[1]);
      bare = bare.slice(hMatch[0].length);
    }
    // Seat tag — engine prefixes most action captions with the seat
    // name. We strip the duplicate so the strip stays compact.
    let seat = null;
    const sMatch = bare.match(/^(p[12])[:\s]\s*/);
    if (sMatch) {
      seat = sMatch[1];
      bare = bare.slice(sMatch[0].length);
    }
    const failed = last.classList.contains("log-line--error");
    return { text: bare, hour, seat, day: null, failed };
  }

  // ── Agent rationale capture ─────────────────────────────────────

  /** Record one rationale entry into the per-seat per-day bucket.
   *  Called from the live agent-think handler (where rationales
   *  come back inline) and from the lazy fetch of /agent-log when a
   *  replay opens a persisted season. Deduplicates on (day, seat,
   *  text) so re-fetches don't double up. */
  function captureAgentRationale(entry) {
    if (!entry || !entry.text) return;
    // v0.9.8 — accept any valid seat slug (p1..p4). Pre-v0.9.8 the
    // ternary forced everything into p1/p2 buckets which corrupted
    // 3- and 4-seat AGENT views.
    const rawSeat = String(entry.seat || "").toLowerCase();
    const seat = /^p[1-4]$/.test(rawSeat) ? rawSeat : "p1";
    const day = Number.isFinite(Number(entry.day)) ? Number(entry.day) : 0;
    const bucket = _agentBucketFor(seat);
    if (!bucket) return;
    if (!bucket.has(day)) bucket.set(day, []);
    const list = bucket.get(day);
    // Dedupe by trimmed body — the lazy fetch can race the in-flight
    // live append.
    const trimmed = String(entry.text).trim();
    for (const row of list) {
      if (String(row.text || "").trim() === trimmed) return;
    }
    list.push({
      ts: entry.ts || Date.now(),
      day,
      seat,
      agent_id: entry.agent_id || "",
      runtime: entry.runtime || "",
      text: trimmed,
      // v1.1 — the AGENT tab is now a "thinking" view: carry the
      // response time and the moves the agent actually submitted so
      // renderAgentFeed can show them alongside the reasoning.
      ms_elapsed: Number.isFinite(Number(entry.ms_elapsed))
        ? Number(entry.ms_elapsed) : null,
      tool_calls: Array.isArray(entry.tool_calls) ? entry.tool_calls : [],
    });
  }

  /** What day does the AGENT/SCOREBOARD/VAULT panel currently care
   *  about? Replay mode = cursor day; live mode = livePhase day from
   *  the most recent status refresh (cached on the inventory). */
  function currentVisibleDay() {
    if (mainMapSource === "replay" && replayTicks.length) {
      const tickIdx = Math.max(
        0, Math.min(replayTickIdx, replayTicks.length - 1),
      );
      const tick = replayTicks[tickIdx];
      const frame = nightReplayFrames[tick?.lastFrameIdx];
      if (frame && frame.day != null) return Number(frame.day);
    }
    if (lastLiveInventory && lastLiveInventory.day != null) {
      return Number(lastLiveInventory.day);
    }
    return 0;
  }

  /** When loading a persisted season into replay/watch mode, pull
   *  the rationale rows for (day, seat) from the server and fold
   *  them into the in-memory bucket. */
  async function ensureAgentLogForDay(day, seat) {
    if (!sessionId || !Number.isFinite(day) || day <= 0) return;
    const key = `${sessionId}|${day}|${seat}`;
    if (agentLogFetched.has(key)) return;
    agentLogFetched.add(key);
    try {
      const url = `/api/game/${sessionId}/agent-log?day=${day}&player=${seat}`;
      const res = await fetch(url, { cache: "no-store" });
      if (!res.ok) return;
      const j = await res.json();
      const rows = Array.isArray(j.invocations) ? j.invocations : [];
      for (const row of rows) {
        // v1.1 — prefer the full reasoning (response_text) for the
        // thinking view; fall back to the short rationale for legacy
        // rows / heuristic seats that have no chain-of-thought.
        captureAgentRationale({
          ts: Date.now(),
          day: row.day,
          seat: row.player,
          agent_id: row.agent_id,
          runtime: row.runtime || "",
          text: row.response_text || row.rationale || "",
          ms_elapsed: row.ms_elapsed,
          tool_calls: row.tool_calls,
        });
      }
      renderAgentFeed();
    } catch {
      // Silent — agent log is best-effort. Engine + scoreboard +
      // timeline all still render fine without it.
    }
  }

  /** When the live runtime falls back from Cortex to RED_HARVEST it
   *  concatenates both rationales with this sentinel. We split on it
   *  in the AGENT feed so the watcher gets TWO clearly-labelled
   *  entries: the Cortex attempt (often long chain-of-thought that
   *  never submitted) and the RED_HARVEST one-liner that actually
   *  carried the turn. */
  const FALLBACK_SENTINEL = " | [fallback] ";

  /** Try to parse the runtime's combined cortex-then-heuristic
   *  rationale into the two underlying entries. Returns ``null`` if
   *  the row isn't a fallback row. */
  function splitFallbackRow(row) {
    const text = String(row.text || "");
    const idx = text.indexOf(FALLBACK_SENTINEL);
    if (idx < 0) return null;
    const cortexBody = text.slice(0, idx).trimEnd();
    const fallbackBody = text.slice(idx + FALLBACK_SENTINEL.length).trim();
    // The fallback body itself starts with "<agent_id> did not call
    // soc_submit_policy; RED_HARVEST took over: <plan>". Strip the
    // boilerplate so the heuristic entry reads cleanly.
    const tookOver = " took over: ";
    const tIdx = fallbackBody.indexOf(tookOver);
    const heuristicBody = tIdx >= 0
      ? fallbackBody.slice(tIdx + tookOver.length).trim()
      : fallbackBody;
    return {
      cortex: {
        ...row,
        agent_id: row.agent_id && row.agent_id !== "RED_HARVEST"
          ? row.agent_id : "SOC_RED_REAPER",
        runtime: "cortex",
        text: cortexBody,
        _tag: "failed to submit · fallback to RED_HARVEST",
      },
      heuristic: {
        ...row,
        agent_id: "RED_HARVEST",
        runtime: "heuristic",
        text: heuristicBody,
        _tag: "fallback policy",
      },
    };
  }

  /** Render the AGENT feed for the active seat sub-tab, scoped to
   *  the day currently in view (replay cursor day, or live current
   *  day). Older days are hidden by design — "current turn only". */
  function renderAgentFeed() {
    if (!agentFeedEl) return;
    const day = currentVisibleDay();
    const bucket = _agentBucketFor(agentSeat) || new Map();
    const entries = bucket.get(day) || [];
    if (!entries.length) {
      agentFeedEl.innerHTML =
        `<p class="cc-agent-empty">// no agent thinking captured for ${esc(playerTag(agentSeat))} · D${day || "—"}</p>`;
      return;
    }
    // Expand each raw bucket entry into one or two visible entries —
    // Cortex-fell-back-to-heuristic rows split into two so the
    // watcher can see both halves separately.
    /** @type {any[]} */
    const expanded = [];
    for (const row of entries) {
      const split = splitFallbackRow(row);
      if (split) {
        expanded.push(split.cortex);
        expanded.push(split.heuristic);
      } else {
        expanded.push(row);
      }
    }
    const parts = expanded.map((row) => {
      const seat = row.seat || agentSeat;
      const head = [
        row.agent_id || (row.runtime === "cortex" ? "AI AGENT" : "RED_HARVEST"),
        row.runtime ? `[${row.runtime}]` : "",
        `(${playerTag(seat)})`,
        `· D${row.day || day}`,
        row._tag ? `· ${row._tag}` : "",
      ].filter(Boolean).join(" ");
      const failedAttr = row._tag && row._tag.startsWith("failed")
        ? ` data-failed="1"` : "";
      // v1.1 — meta row: how long the agent took + which tools it
      // called this turn (the AGENT tab is now a reasoning trace).
      const metaBits = [];
      const ms = Number(row.ms_elapsed);
      if (Number.isFinite(ms) && ms > 0) {
        const secs = ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`;
        metaBits.push(
          `<span class="cc-agent-meta-chip cc-agent-meta-time" title="agent response time">\u23f1 ${esc(secs)}</span>`,
        );
      }
      for (const chip of summariseToolCalls(row.tool_calls)) {
        metaBits.push(
          `<span class="cc-agent-meta-chip cc-agent-meta-tool" title="tool call submitted">\u2699 ${esc(chip)}</span>`,
        );
      }
      const metaRow = metaBits.length
        ? `<div class="cc-agent-entry-meta">${metaBits.join("")}</div>`
        : "";
      return (
        `<div class="cc-agent-entry" data-seat="${esc(seat)}" data-runtime="${esc(row.runtime || "")}"${failedAttr}>` +
        `<span class="cc-agent-entry-head">${esc(head)}</span>` +
        metaRow +
        `<span class="cc-agent-entry-body">${esc(String(row.text || ""))}</span>` +
        `</div>`
      );
    });
    agentFeedEl.innerHTML = parts.join("");
  }

  /** Collapse a row's tool_calls into short display chips like
   *  ``soc_submit_policy ×1``. Tool-call entries come either as
   *  ``{name}`` (executing_tool events) or richer ``tool_use``
   *  objects; we key on whatever name field is present. */
  function summariseToolCalls(toolCalls) {
    if (!Array.isArray(toolCalls) || !toolCalls.length) return [];
    const counts = new Map();
    for (const tc of toolCalls) {
      const name = typeof tc === "string"
        ? tc
        : (tc && (tc.name || tc.tool)) || "";
      if (!name) continue;
      counts.set(name, (counts.get(name) || 0) + 1);
    }
    const out = [];
    for (const [name, n] of counts) {
      out.push(n > 1 ? `${name} \u00d7${n}` : name);
    }
    return out;
  }

  function setAgentSeat(seat) {
    // v0.9.8 — accept p1..p4. The p1 / p2 toggle buttons stay (legacy
    // 2-seat HUD), but the underlying ``agentSeat`` honours whatever
    // valid slug is passed so other code paths (e.g. the replay
    // scrubber's per-seat panels) can target p3/p4 buckets.
    const rawSeat = String(seat || "").toLowerCase();
    agentSeat = /^p[1-4]$/.test(rawSeat) ? rawSeat : "p1";
    syncAgentSeatBtns();
    renderAgentFeed();
  }

  function setVaultSeat(seat) {
    const rawSeat = String(seat || "").toLowerCase();
    vaultSeat = /^p[1-4]$/.test(rawSeat) ? rawSeat : "p1";
    syncVaultSeatBtns();
    repaintVaultForActiveSeat();
  }

  /** Sync the active class on whatever vault seat buttons currently
   *  exist (they're rebuilt dynamically by ``renderVaultSeatTabs``). */
  function syncVaultSeatBtns() {
    if (!vaultSeatTabsEl) return;
    vaultSeatTabsEl
      .querySelectorAll(".cc-replay-view-btn--seat")
      .forEach((btn) => {
        btn.classList.toggle(
          "cc-replay-view-btn--active",
          btn.getAttribute("data-seat") === vaultSeat,
        );
      });
  }

  /** v0.9.11 — Build the VAULT seat sub-tabs dynamically (one per
   *  active seat, seat-coloured) so 3-/4-player replays can inspect
   *  every vault. In live play only the player's own seat (p1) shows —
   *  you can't peek at a rival's vault mid-season. Replaces the
   *  hard-coded P1/P2 markup. */
  function renderVaultSeatTabs() {
    if (!vaultSeatTabsEl) return;
    const multi = opponentSeatVisible();
    const seats = multi ? _activeSeatsForView() : [MY_SEAT];
    if (!seats.includes(vaultSeat)) vaultSeat = seats[0] || MY_SEAT;
    vaultSeatTabsEl.textContent = "";
    seats.forEach((seat) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.id = `vault-seat-${seat}`;
      btn.className = "cli-btn cc-replay-view-btn cc-replay-view-btn--seat";
      btn.dataset.seat = seat;
      const color = ownerColor(seat) || "#9fa6ad";
      btn.style.setProperty("--cc-replay-seat-stroke", color);
      btn.textContent = `[ ${playerTag(seat)} ]`;
      if (seat === vaultSeat) btn.classList.add("cc-replay-view-btn--active");
      btn.addEventListener("click", () => setVaultSeat(seat));
      vaultSeatTabsEl.appendChild(btn);
    });
    // A lone self-tab in live play is noise — hide the strip entirely.
    vaultSeatTabsEl.hidden = seats.length <= 1;
  }

  /** v0.9.18 — Build the AGENT-rationale seat sub-tabs dynamically (one
   *  per active seat, seat-coloured, tag-labelled) so 3-/4-player
   *  replays expose every agent's feed. Mirrors renderVaultSeatTabs();
   *  replaces the hard-coded p1/p2 markup that left p3/p4 unreachable. */
  function renderAgentSeatTabs() {
    if (!agentSeatTabsEl) return;
    const multi = opponentSeatVisible();
    const seats = multi ? _activeSeatsForView() : [MY_SEAT];
    if (!seats.includes(agentSeat)) agentSeat = seats[0] || MY_SEAT;
    agentSeatTabsEl.textContent = "";
    seats.forEach((seat) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.id = `agent-seat-${seat}`;
      btn.className = "cli-btn cc-replay-view-btn cc-replay-view-btn--seat";
      btn.dataset.seat = seat;
      const color = ownerColor(seat) || "#9fa6ad";
      btn.style.setProperty("--cc-replay-seat-stroke", color);
      btn.textContent = `[ ${playerTag(seat)} ]`;
      if (seat === agentSeat) btn.classList.add("cc-replay-view-btn--active");
      btn.addEventListener("click", () => setAgentSeat(seat));
      agentSeatTabsEl.appendChild(btn);
    });
    // A lone self-tab in live play is noise — hide the strip entirely.
    agentSeatTabsEl.hidden = seats.length <= 1;
  }

  /** Sync the active class on whatever agent seat buttons currently
   *  exist (they're rebuilt dynamically by ``renderAgentSeatTabs``). */
  function syncAgentSeatBtns() {
    if (!agentSeatTabsEl) return;
    agentSeatTabsEl
      .querySelectorAll(".cc-replay-view-btn--seat")
      .forEach((btn) => {
        btn.classList.toggle(
          "cc-replay-view-btn--active",
          btn.getAttribute("data-seat") === agentSeat,
        );
      });
  }

  /** Render the vault either from the live inventory (P1 only in
   *  live play) or from a frame-walked reconstruction (replay/watch
   *  mode). The reconstructed payload uses the same shape as the
   *  live ``inventory`` object so renderVault() doesn't need to know
   *  the difference. */
  function repaintVaultForActiveSeat() {
    if (!vaultGridEl) return;
    // Keep the seat sub-tabs in step with the current mode (live = self
    // only; replay = every active seat) and a valid selection.
    renderVaultSeatTabs();
    if (mainMapSource === "replay" && replayTicks.length) {
      const tickIdx = Math.max(
        0, Math.min(replayTickIdx, replayTicks.length - 1),
      );
      const inv = reconstructVaultAtTick(tickIdx, vaultSeat);
      // v0.9.11 — the SHIPPED pane shows EVERY player's bay (owner
      // border-coloured), reconstructed from catapult settlements up to
      // the cursor day. The hoard grid stays scoped to the selected
      // vault seat.
      //
      // Live-play self-replay (opponentSeatVisible() === false): the
      // human is reviewing their OWN night, so scope the shipped pane
      // to p1 only — surfacing rivals' shipped parcels here would be
      // the same leak we hide everywhere else mid-season.
      // v0.9.x — SHIPPED is a fully PUBLIC, uncapped record now, so the
      // pane shows EVERY house's shipments in all contexts (no live-play
      // self-scoping). The hoard grid stays scoped to the selected seat.
      const cursorDay = currentReplayDay();
      const shippedAll = reconstructAllShipped(cursorDay);
      renderVault(inv, shippedAll);
      return;
    }
    // Live mode — the hoard is self-only (MY_SEAT from /view?player=MY_SEAT),
    // but the SHIPPED pane renders the all-seat public ledger.
    if (vaultSeat === MY_SEAT) {
      renderVault(lastLiveInventory, lastLiveShippedRecord);
    } else {
      // Defensive: should never happen because we hide rivals in live.
      renderVault(null);
    }
  }

  // ── Vault state reconstruction from replay frames ───────────────
  //
  // The replay payload doesn't carry a per-tick inventory snapshot
  // (would balloon the size), but EVERY frame stamps an authoritative
  // ``entities`` summary plus a per-seat hoard snapshot. We derive the
  // vault buckets straight from that live truth (see
  // ``reconstructVaultAtTick``) instead of parsing captions, so a
  // crushed/expired probe or a dawn-stranded harvester leaves IN ORBIT
  // / ON SURFACE and lands in DESTROYED exactly as it does on the live
  // HUD's ``_assets_by_status``.

  /** Best-effort cause-of-death for an asset that dropped out of the
   *  entity list on ``frame``. Used only to colour the destroyed
   *  chip's tooltip — the bucket itself is driven by the entity diff,
   *  not by this string. */
  function _vaultDisappearReason(frame, id, type) {
    if (frame) {
      const cp = Array.isArray(frame.crushed_probes) ? frame.crushed_probes : [];
      for (const c of cp) {
        if (c && (c.id === id || c.probe === id || c.probe_id === id))
          return "crushed";
      }
      if (frame.tag === "dawn") return type === "probe" ? "expired" : "stranded";
      if (
        type === "probe"
        && (frame.tag === "emp_launch"
          || (Array.isArray(frame.emp) && frame.emp.length))
      ) {
        return "emp";
      }
    }
    return type === "probe" ? "expired" : "destroyed";
  }

  /** Build ``id -> nights_remaining`` for probes from a seat's dense
   *  cell snapshot so the vault chip can render the same concentric
   *  rings the map shows (the engine degrades these AT dawn). */
  function _probeLifeFromCells(cells) {
    const out = new Map();
    if (!Array.isArray(cells)) return out;
    for (const c of cells) {
      if (!c) continue;
      const occ = Array.isArray(c.occupants) ? c.occupants : [];
      for (const o of occ) {
        if (
          o && o.type === "probe" && o.id != null && o.nights_remaining != null
        ) {
          out.set(String(o.id), Number(o.nights_remaining));
        }
      }
      if (
        c.entity && c.entity.id != null && c.entity.nights_remaining != null
        && (c.entity.type === "probe"
          || String(c.entity.id).startsWith("probe"))
      ) {
        out.set(String(c.entity.id), Number(c.entity.nights_remaining));
      }
    }
    return out;
  }

  /** Walk frames [0..lastFrameIdx for tickIdx] and emit an inventory
   *  payload for ``seat`` matching the shape renderVault expects.
   *
   *  v1.2 — driven by each frame's authoritative ``entities`` summary
   *  (``_replay_entity_summaries`` server-side) rather than the old
   *  caption-grammar heuristic. The engine stamps every live entity on
   *  every frame, so the buckets mirror its own ``_assets_by_status``
   *  exactly: an asset present in the cursor frame is bucketed by
   *  position (orbit when it has no surface coord, else on-surface),
   *  and any asset we saw earlier but is now gone from the list is
   *  DESTROYED — which is precisely how a crushed/expired probe or a
   *  dawn-stranded harvester leaves the live HUD. Captions are no
   *  longer parsed; this fixes destroyed probes never leaving orbit. */
  function reconstructVaultAtTick(tickIdx, seat) {
    if (!replayTicks.length) return _emptyInventory();
    const i = Math.max(0, Math.min(tickIdx, replayTicks.length - 1));
    const tick = replayTicks[i];
    const cap = tick?.lastFrameIdx ?? -1;
    if (cap < 0) return _emptyInventory();

    // First pass — accumulate the per-seat hoard snapshot (the only
    // correct source for the hoard grid: caption math overcounts) and
    // the full lifecycle of every owned asset. ``everSeen`` records
    // each id we ever observed; ``gone`` notes when/why it vanished.
    let lastHoardSnapshot = null;
    let lastWeaponsSnapshot = null;
    let lastCreditsSnapshot = null;
    // v1.1 — derive USED weapons by tallying this seat's launch frames
    // up to the cursor. This is store-independent: the ``weapons``
    // snapshot is dropped on the Snowflake round-trip (and absent from
    // seasons minted before it existed), but the launch frames
    // themselves (tag + owner) always persist. One launch frame drains
    // exactly one weapon, so the count equals ``weapons_used``.
    const derivedUsed = { emp: 0, mine: 0, chaff: 0 };
    const everSeen = new Map();   // id -> { type, owner }
    const gone = new Map();       // id -> { day, by }
    let prevPresent = new Set();
    let prevDay = 0;
    for (let f = 0; f <= cap; f += 1) {
      const frame = nightReplayFrames[f];
      if (!frame) continue;
      if (frame.hoard && typeof frame.hoard === "object") {
        lastHoardSnapshot = frame.hoard;
      }
      if (frame.weapons && typeof frame.weapons === "object") {
        lastWeaponsSnapshot = frame.weapons;
      }
      if (frame.credits && typeof frame.credits === "object") {
        lastCreditsSnapshot = frame.credits;
      }
      if (frame.owner === seat) {
        if (frame.tag === "emp_launch") derivedUsed.emp += 1;
        else if (frame.tag === "mine_lay") derivedUsed.mine += 1;
        else if (frame.tag === "chaff_flare") derivedUsed.chaff += 1;
      }
      if (!Array.isArray(frame.entities)) continue;
      const fday = frame.day != null ? Number(frame.day) : prevDay;
      const present = new Set();
      for (const e of frame.entities) {
        if (!e || e.id == null) continue;
        const id = String(e.id);
        present.add(id);
        everSeen.set(id, { type: e.t, owner: e.owner });
        gone.delete(id); // reappeared (defensive) — no longer destroyed
      }
      for (const id of prevPresent) {
        if (!present.has(id)) {
          const meta = everSeen.get(id) || {};
          gone.set(id, {
            day: prevDay,
            by: _vaultDisappearReason(frame, id, meta.type),
          });
        }
      }
      prevPresent = present;
      prevDay = fday;
    }

    // Authoritative live snapshot at the cursor frame.
    const capFrame = nightReplayFrames[cap] || null;
    const liveEntities = Array.isArray(capFrame && capFrame.entities)
      ? capFrame.entities
      : [];
    const seatCells =
      (capFrame && capFrame.cells_by_seat && capFrame.cells_by_seat[seat]) ||
      (capFrame && capFrame[`cells_player_${seat}`]) ||
      (seat === "p1" ? capFrame && capFrame.cells_player : null) ||
      [];
    const probeLife = _probeLifeFromCells(seatCells);

    const inOrbit = [];
    const onSurface = [];
    const destroyed = [];
    const damaged = [];
    const aliveIds = new Set();
    for (const e of liveEntities) {
      if (!e || e.owner !== seat || e.id == null) continue;
      const id = String(e.id);
      aliveIds.add(id);
      const onGround = Array.isArray(e.surface);
      const row = {
        asset_id: id,
        asset_type: e.t,
        owner: seat,
        alive: true,
        current_pos: onGround ? [e.surface[0], e.surface[1]] : null,
      };
      if (e.t === "harvester") {
        row.carrying_red = Array.isArray(e.cargo) && e.cargo.length > 0;
        row.current_cargo_count = Array.isArray(e.cargo) ? e.cargo.length : 0;
        row.damaged = e.damaged === true;
        if (row.damaged) damaged.push(row);
      }
      if (e.t === "probe" && probeLife.has(id)) {
        row.nights_remaining = probeLife.get(id);
      }
      if (onGround) onSurface.push(row);
      else inOrbit.push(row);
    }

    // DESTROYED = everything this seat owned that's no longer live.
    for (const [id, meta] of everSeen) {
      if (meta.owner !== seat || aliveIds.has(id)) continue;
      const g = gone.get(id) || {};
      destroyed.push({
        asset_id: id,
        asset_type: meta.type,
        owner: seat,
        alive: false,
        destroyed_on_day: g.day != null ? g.day : currentReplayDay(),
        destroyed_by: g.by || (meta.type === "probe" ? "expired" : "destroyed"),
      });
    }

    const byTypeId = (a, b) =>
      `${a.asset_type}${a.asset_id}`.localeCompare(`${b.asset_type}${b.asset_id}`);
    inOrbit.sort(byTypeId);
    onSurface.sort(byTypeId);
    destroyed.sort(
      (a, b) =>
        (a.destroyed_on_day - b.destroyed_on_day) ||
        String(a.asset_id).localeCompare(String(b.asset_id)),
    );

    // Hoard parcels from the authoritative per-frame snapshot. Each
    // site is ``{cell:[x,y], id, ...}``; map it to the parcel shape
    // ``renderStorageGrid`` expects (paint / purity / harvest metadata
    // carried through so the scrubbed grid matches the live one).
    // At the terminal SETTLEMENT (resolve) tick the final refinery + ship
    // run in the ORBIT phase — no night frames — so ``lastHoardSnapshot``
    // (bound to the last night frame) is stale: it still holds the RED that
    // was shipped/refined away in the closing orbit. Swap in the
    // authoritative post-settlement hoard so the vault matches the score.
    let hoardSnap = lastHoardSnapshot;
    if (
      tick && tick.slot === "resolve" &&
      finalHoardSnapshot && finalHoardSnapshot[seat]
    ) {
      hoardSnap = finalHoardSnapshot;
    }
    let hoardParcels = [];
    if (hoardSnap && hoardSnap[seat]) {
      const snap = hoardSnap[seat];
      const sites = Array.isArray(snap.sites) ? snap.sites : [];
      hoardParcels = sites.map((site) => {
        const cell = Array.isArray(site.cell) ? site.cell : [];
        return {
          square_id: site.id,
          site_id: site.id,
          x: cell[0],
          y: cell[1],
          paint: site.paint || null,
          tile_at_harvest: site.tile_at_harvest,
          purity_at_harvest: site.purity_at_harvest,
          harvested_on_planning_day: site.harvested_on_planning_day,
        };
      });
    }

    // Weapons bays from the authoritative per-frame snapshot
    // (``_weapons_snap_payload`` server-side). ``renderVaultWeaponsBay``
    // reads ``weapon_stock`` (AVAILABLE) and ``weapons_used`` (USED
    // lifetime). Legacy replays minted before the snapshot existed
    // simply leave both empty — the same "// bay empty" copy the
    // vault showed before this change.
    const wSnap =
      lastWeaponsSnapshot && lastWeaponsSnapshot[seat]
        ? lastWeaponsSnapshot[seat]
        : null;
    const weaponStock = (wSnap && wSnap.stock) || {};
    // Prefer the authoritative snapshot when it actually carries a fired
    // count; otherwise fall back to the launch-frame tally so USED still
    // populates on Snowflake-backed / pre-snapshot replays.
    const snapUsed = (wSnap && wSnap.used) || null;
    const snapHasUsed =
      snapUsed &&
      ((snapUsed.emp || 0) + (snapUsed.mine || 0) + (snapUsed.chaff || 0)) > 0;
    const weaponsUsed = snapHasUsed ? snapUsed : derivedUsed;

    // Per-tick credits: the snapshot (file store) wins; on Snowflake the
    // field is dropped, so leave it null and let renderVaultMetaRow fall
    // back to the live orbit readout.
    const creditsAtTick =
      lastCreditsSnapshot && typeof lastCreditsSnapshot[seat] === "number"
        ? lastCreditsSnapshot[seat]
        : null;

    return {
      credits: creditsAtTick,
      hoard: hoardParcels,
      hoard_capacity: 15,
      shipped: [],
      shipped_capacity: 25,
      // ``renderAssetSections`` (in renderVault) reads
      // ``inv.assets_by_status.{in_orbit,on_surface,destroyed}``.
      assets_by_status: {
        in_orbit: inOrbit,
        on_surface: onSurface,
        destroyed,
      },
      assets_damaged: damaged,
      weapon_stock: weaponStock,
      weapons_used: weaponsUsed,
    };
  }

  function _emptyInventory() {
    return {
      hoard: [], hoard_capacity: HOARD_CAP_FALLBACK,
      shipped: [], shipped_capacity: 50,
      assets_by_status: { in_orbit: [], on_surface: [], destroyed: [] },
      assets_damaged: [],
    };
  }

  /** v0.9.11 — Reconstruct a seat's cumulative SHIPPED bay up to (and
   *  including) ``uptoDay`` by accumulating every catapult settlement's
   *  per-seat ``shipped_parcels``. The replay payload doesn't snapshot
   *  shipped bays per frame, but ``catapultByDay`` carries each night's
   *  newly-shipped parcels with full provenance — summed across days
   *  ≤ cursor this IS the cumulative bay. Each parcel is tagged with its
   *  ``owner`` so the grid can border-colour by seat. */
  function reconstructShippedForSeat(seat, uptoDay) {
    const out = [];
    const cap = Number.isFinite(Number(uptoDay)) ? Number(uptoDay) : Infinity;
    const days = Object.keys(catapultByDay || {})
      .map((k) => Number(k))
      .filter((d) => Number.isFinite(d) && d <= cap)
      .sort((a, b) => a - b);
    for (const d of days) {
      const blob = catapultByDay[String(d)];
      const seatBlob = blob && blob.catapult
        && blob.catapult.seats && blob.catapult.seats[seat];
      const parcels = seatBlob && Array.isArray(seatBlob.shipped_parcels)
        ? seatBlob.shipped_parcels
        : [];
      for (const p of parcels) {
        if (p && typeof p === "object") out.push({ ...p, owner: seat });
      }
    }
    return out;
  }

  /** Every active seat's shipped parcels, owner-tagged, in one list —
   *  the data for the replay SHIPPED pane (all players at once). */
  function reconstructAllShipped(uptoDay) {
    let all = [];
    for (const seat of _activeSeatsForView()) {
      all = all.concat(reconstructShippedForSeat(seat, uptoDay));
    }
    return all;
  }

  // ── Scoreboard ──────────────────────────────────────────────────

  /** v0.9.6 — return the seat list for the active session, defaulting
   *  to the legacy 2-seat shape when the server hasn't told us yet.
   *  Reads from the most recent /view response (cached in
   *  ``window.__SOC_PLAYERS__``) so every callsite agrees on the same
   *  truth without needing to thread the value through their stack. */
  function activeSeats() {
    const sx = window.__SOC_PLAYERS__;
    if (Array.isArray(sx) && sx.length) return sx.slice(0, 4);
    return ["p1", "p2"];
  }

  /** Render the per-seat scoreboard inside the LOG panel. Driven by
   *  per-seat reconstructions in replay/watch mode, or by the live
   *  inventory + last status snapshot in live play. v0.9.6 —
   *  generalised to N seats (1-4): rows for seats not in the active
   *  session are hidden, every active seat row is updated. */
  /** v0.9.9 — Render the permanent top-right HUD scoreboard.
   *
   *  Reads ``cumulative_shipped_score`` straight off /status (live)
   *  or /replay (final season totals). One row per active seat; the
   *  panel itself is hidden when no session is live or when the
   *  status payload omits the field (legacy server / pre-v0.9.9).
   *
   *  We deliberately do NOT walk ``shipped_squares`` here — the
   *  engine bumps the running counter at catapult settlement time
   *  (see ``_settle_catapult`` v0.9.9), so this is an O(1) read.
   *
   *  @param {Record<string, number> | null | undefined} scoresByPlayer
   *  @param {string[] | null | undefined} sessionPlayers
   */
  /** v0.9.9 — companion stats panel pinned to the SHIPPED tab so the
   *  tab isn't just "25 empty slots" before anyone has shipped. Lists
   *  every active seat with its cumulative tier-multiplier score and
   *  the parcel count currently in their shipped bay. Reads the same
   *  payload as ``renderHudScoreboard`` so both surfaces stay in
   *  sync.
   *
   *  @param {Record<string, number> | null | undefined} scoresByPlayer
   *  @param {string[] | null | undefined} sessionPlayers
   *  @param {number} viewerShippedCount — how many parcels are
   *    currently in the viewer's shipped bay (from inv.shipped).
   *  @param {number} viewerShippedCap — viewer's shipped capacity.
   */
  function renderShippedStats(
    scoresByPlayer, sessionPlayers,
    viewerShippedCount, viewerShippedCap,
  ) {
    const host = document.getElementById("cc-shipped-stats");
    if (!host) return;
    const seats = (
      Array.isArray(sessionPlayers) && sessionPlayers.length
        ? sessionPlayers
        : (Array.isArray(window.__SOC_PLAYERS__) && window.__SOC_PLAYERS__.length
          ? window.__SOC_PLAYERS__
          : (scoresByPlayer && typeof scoresByPlayer === "object"
            ? Object.keys(scoresByPlayer)
            : []))
    ).slice(0, 4);
    host.textContent = "";
    if (!seats.length) {
      host.hidden = true;
      return;
    }
    host.hidden = false;
    const safeScores =
      scoresByPlayer && typeof scoresByPlayer === "object"
        ? scoresByPlayer
        : {};
    const head = document.createElement("div");
    head.className = "cc-shipped-stats-head dim";
    head.textContent =
      `// shipped score \u00B7 your bay ${viewerShippedCount}`;
    host.appendChild(head);
    const rows = document.createElement("div");
    rows.className = "cc-shipped-stats-rows";
    for (const seat of seats) {
      const row = document.createElement("div");
      row.className = "cc-shipped-stats-row";
      row.setAttribute("data-seat", String(seat));
      const tag = document.createElement("span");
      tag.className = "cc-shipped-stats-tag";
      tag.textContent = playerTag(seat);
      tag.style.color = ownerColor(seat);
      const val = document.createElement("span");
      val.className = "cc-shipped-stats-val";
      const raw = Number(safeScores[seat] || 0);
      val.textContent = `${Math.round(raw).toLocaleString("en-US")} pts`;
      row.append(tag, val);
      rows.appendChild(row);
    }
    host.appendChild(rows);
  }

  function renderHudScoreboard(scoresByPlayer, sessionPlayers) {
    const host = document.getElementById("cc-hud-scoreboard");
    const rowsHost = document.getElementById("cc-hud-scoreboard-rows");
    if (!host || !rowsHost) return;
    // v0.9.9 — only fully hide when we have no session at all (no
    // players known anywhere). When a session is active but no
    // shipping has happened yet, ``scoresByPlayer`` may be {} or
    // even null; we still want the board visible with zeros so the
    // user sees the HUD position and learns it's empty (not broken).
    const seats = (
      Array.isArray(sessionPlayers) && sessionPlayers.length
        ? sessionPlayers
        : (Array.isArray(window.__SOC_PLAYERS__) && window.__SOC_PLAYERS__.length
          ? window.__SOC_PLAYERS__
          : (scoresByPlayer && typeof scoresByPlayer === "object"
            ? Object.keys(scoresByPlayer)
            : []))
    ).slice(0, 4);
    if (!seats.length) {
      host.hidden = true;
      return;
    }
    const safeScores =
      scoresByPlayer && typeof scoresByPlayer === "object"
        ? scoresByPlayer
        : {};
    rowsHost.textContent = "";
    for (const seat of seats) {
      const row = document.createElement("div");
      row.className = "cc-hud-scoreboard-row";
      row.setAttribute("data-seat", String(seat));
      
      // v0.9.18 — apply custom seat color as inline style
      const customColor = playerColor(seat);
      if (customColor) {
        row.style.setProperty("--seat-color", customColor);
      }
      
      const tag = document.createElement("span");
      tag.className = "cc-hud-scoreboard-tag";
      // v0.9.18 — use player tag (3-letter) instead of seat ID
      tag.textContent = playerTag(seat);
      
      const val = document.createElement("span");
      val.className = "cc-hud-scoreboard-val";
      const raw = Number(safeScores[seat] || 0);
      val.textContent = Math.round(raw).toLocaleString("en-US");
      row.append(tag, val);
      rowsHost.appendChild(row);
    }
    if (typeof osOnScoreUpdate === "function") {
      const _sb = {};
      for (const seat of seats) _sb[seat] = { score: Number(safeScores[seat] || 0) };
      osOnScoreUpdate(_sb);
    }
    host.hidden = false;
  }

  function renderScoreboard() {
    if (!replayScoreboardEl) return;
    const allRows = replayScoreboardEl.querySelectorAll(".cc-scoreboard-row");
    const seats = activeSeats();
    const showOpp = opponentSeatVisible();
    allRows.forEach((row) => {
      const seat = row.dataset.seat;
      if (!seats.includes(seat)) {
        row.hidden = true;
        return;
      }
      row.hidden = false;
      if (seat !== MY_SEAT && !showOpp) {
        row.classList.add("cc-scoreboard-row--inactive");
      } else {
        row.classList.remove("cc-scoreboard-row--inactive");
      }
      
      // v0.9.18 — update tag element with player tag + apply custom color
      const tagEl = row.querySelector(".cc-scoreboard-tag");
      if (tagEl) {
        tagEl.textContent = playerTag(seat);
        const customColor = playerColor(seat);
        if (customColor) {
          row.style.setProperty("--seat-color", customColor);
        }
      }
      
      const stats = scoreboardStatsFor(seat);
      const cells = row.querySelectorAll(".cc-scoreboard-cell");
      cells.forEach((cell) => {
        const k = cell.dataset.stat;
        if (k === "score") cell.textContent = `score ${stats.score}`;
        else if (k === "vault") cell.textContent = `vault ${stats.vault}/15`;
        else if (k === "surface") cell.textContent = `surface ${stats.surface}`;
        else if (k === "damaged") cell.textContent = `damaged ${stats.damaged}`;
        else if (k === "destroyed") cell.textContent = `destroyed ${stats.destroyed}`;
      });
    });
  }

  function scoreboardStatsFor(seat) {
    if (mainMapSource === "replay" && replayTicks.length) {
      const inv = reconstructVaultAtTick(replayTickIdx, seat);
      return _statsFromInventory(inv);
    }
    // Live mode — only our own seat is meaningful. The opponent row
    // stays at zeros (and is dimmed via cc-scoreboard-row--inactive).
    if (seat === MY_SEAT && lastLiveInventory) {
      return _statsFromInventory(lastLiveInventory);
    }
    return { score: 0, vault: 0, surface: 0, damaged: 0, destroyed: 0 };
  }

  /** Shared shape — inventory payload (live or reconstructed) -> the
   *  five scoreboard cells. We tolerate both the legacy
   *  ``assets_in_orbit`` / ``assets_on_surface`` keys and the modern
   *  ``assets_by_status`` shape so the renderer stays robust to
   *  back-end changes. */
  function _statsFromInventory(inv) {
    if (!inv) return { score: 0, vault: 0, surface: 0, damaged: 0, destroyed: 0 };
    const byStatus = inv.assets_by_status || {};
    const surfaceList =
      Array.isArray(byStatus.on_surface) ? byStatus.on_surface
      : Array.isArray(inv.assets_on_surface) ? inv.assets_on_surface
      : [];
    const destroyedList =
      Array.isArray(byStatus.destroyed) ? byStatus.destroyed
      : Array.isArray(inv.assets_destroyed) ? inv.assets_destroyed
      : [];
    const damagedList =
      Array.isArray(inv.assets_damaged) ? inv.assets_damaged
      : [];
    const vault = Array.isArray(inv.hoard) ? inv.hoard.length : 0;
    const surface = surfaceList.length;
    const damaged = damagedList.length;
    const destroyed = destroyedList.filter(
      (r) => r.asset_type === "harvester",
    ).length;
    // Score = sum of parcel values. The server-side inventory carries
    // real ``value`` per parcel (SOC_LEDGER); our replay-walked
    // reconstruction uses 1-per-parcel placeholders.
    const score = Array.isArray(inv.hoard)
      ? inv.hoard.reduce((acc, p) => acc + (Number(p.value) || 1), 0)
      : 0;
    return { score, vault, surface, damaged, destroyed };
  }

  // ── Status-poll bridge: pull rationales out of the server log ──

  /** Harvest rationale-tagged entries from the server's log_tail and
   *  bucket them into agentLogByDay. The orchestrator emits lines
   *  like ``[SOC_RED_REAPER] [cortex] (p1) day 3 plan: ...`` — the
   *  regex picks (agent_id, runtime, seat, body) cleanly.
   *
   *  v0.9.8 — N-seat-aware. The regex now accepts (p1|p2|p3|p4) and
   *  each entry honours its own ``day`` field (server stamps every
   *  log entry with ``day`` at write time) before falling back to
   *  ``defaultDay``. Pre-v0.9.8 ALL lines got bucketed under the
   *  caller's ``defaultDay`` (= live ``sess.day``), so when the
   *  batched fan-out wrote multiple days of rationale in a single
   *  shot, day-N events showed up under day-N+1 in the AGENT panel.
   */
  function harvestAgentLinesFromStatus(logTail, defaultDay) {
    if (!Array.isArray(logTail)) return;
    for (const entry of logTail) {
      const text = typeof entry === "string"
        ? entry
        : String(entry?.text || "");
      const m = text.match(AGENT_RATIONALE_RE);
      if (!m) continue;
      let entryDay = defaultDay;
      if (entry && typeof entry === "object" && Number.isFinite(Number(entry.day))) {
        entryDay = Number(entry.day);
      }
      captureAgentRationale({
        ts: Date.now(),
        day: entryDay,
        seat: m[3].toLowerCase(),
        agent_id: m[1],
        runtime: m[2] || "",
        text: m[4].trim(),
      });
    }
  }

  /** Paint a replay frame's board (cells) onto the main map host, honouring
   *  the active replay-view seat (OBS combined vision vs a single seat) and
   *  stashing the frame's mine / EMP-cloud snapshot for the hover tooltip.
   *  Pure board paint — no tint, FX, captions or scrub-UI sync. */
  function _paintReplayBoard(frame) {
    const dims = { width: replayDims.width, height: replayDims.height };
    const activeSeats = _activeSeatsForView();
    const seatCells = (seat) =>
      frame?.cells_by_seat?.[seat] ||
      frame?.[`cells_player_${seat}`] ||
      (seat === "p1" ? frame?.cells_player : null) ||
      [];
    if (replayViewSeat === "obs") {
      const perSeat = activeSeats.map(seatCells);
      if (Array.isArray(frame?.cells) && frame.cells.length) {
        paintObsVisionMap(mapPlayer, dims, frame.cells, ...perSeat);
      } else {
        paintPlaceholder(mapPlayer, "# replay frame · no cells");
      }
    } else {
      const pc = seatCells(replayViewSeat);
      if (Array.isArray(pc) && pc.length) {
        paintPlayerMap(mapPlayer, { ...dims, cells: pc }, replayViewSeat);
      } else {
        paintPlaceholder(
          mapPlayer,
          `# replay frame · no ${replayViewSeat} cells`,
        );
      }
    }
    const _store = /** @type {any} */ (mapPlayer).__cellStore;
    if (_store) {
      _store.mines = Array.isArray(frame?.mines_active) ? frame.mines_active : [];
      _store.empClouds = Array.isArray(frame?.emp_clouds) ? frame.emp_clouds : [];
    }
    syncGridlinesClass();
  }

  function _paintReplayFrameMain(mode) {
    if (!mapPlayer) return;
    mainMapSource = "replay";
    if (!replayTicks.length) {
      lastPaintedReplayTickIdx = -1;
      syncReplayRowOnly();
      return;
    }
    if (replayTickIdx < 0) replayTickIdx = 0;
    if (replayTickIdx >= replayTicks.length)
      replayTickIdx = replayTicks.length - 1;
    const tick = replayTicks[replayTickIdx];
    if (typeof osOnReplayTick === "function" && tick) {
      // Pass the frame tag for non-slot ticks so station.js can detect the
      // "praxis begins" (open) frame, which shares lastFrameIdx with DUSK and
      // would otherwise show stale pre-catapult hoard data.
      const _rfFrame = nightReplayFrames[tick.lastFrameIdx];
      const _rfTag = tick.slot ? null : (_rfFrame?.tag || null);
      // Only the synthetic DUSK/DAWN slot ticks carry ``tick.day``; ordinary
      // frame ticks don't, so resolve the day from the underlying frame.
      // Without this, station.js sees day===undefined every night frame and
      // its per-day score/catapult sync collapses to zero.
      const _rfDay = (tick.day != null) ? tick.day : (_rfFrame?.day ?? null);
      osOnReplayTick({ slot: tick.slot || null, day: _rfDay, tag: _rfTag, idx: replayTickIdx });
    }
    // v1.2 — DAWN / DUSK slot tick. These own the day↔night transition
    // and the orbit reports; they don't paint a fresh board (the map
    // keeps the last night's cells), they just wash the daylight over
    // it and (forward play only) pop the matching report.
    //   DAWN -> full DAY  (sunrise wipe), pre-orbital RECAP for day N
    //   DUSK -> full NIGHT (sunset wipe),  "NIGHT n begins" + post-
    //           orbital BRIEFING for day N
    // Crucially the wipe ANIMATES only when we played/stepped FORWARD
    // onto the slot; a direct scrub / pip click / back-step SNAPS to
    // the resolved end state with no animation (per spec: HOUR 22 is
    // always full dawn, HOUR 0 always full night when resolved).
    if (tick && (tick.slot === "dawn" || tick.slot === "dusk")) {
      const isDawn = tick.slot === "dawn";
      const day = Number(tick.day || 0) || 0;
      const movingForward = replayTickIdx > lastPaintedReplayTickIdx;
      const animate = mode === "forward" && movingForward
        && !reduceMotionMq.matches;
      // The DAWN slot OWNS the hour-22 dawn frame: paint its post-dawn
      // board (carcasses + degraded probe rings) here so dawn is a single
      // position (no separate hour-22 tick) and the loss shows AT dawn.
      let preDawn = null;
      let dawnFrame = null;
      if (isDawn) {
        const dIdx = Number.isFinite(tick.dawnFrameIdx)
          ? tick.dawnFrameIdx : tick.lastFrameIdx;
        const df = nightReplayFrames[dIdx];
        if (df && df.tag === "dawn") {
          dawnFrame = df;
          preDawn = dIdx > 0 ? nightReplayFrames[dIdx - 1] : null;
          _paintReplayBoard(dawnFrame);
        }
      } else {
        // v1.3 — DUSK now OWNS the hour-0 ``open`` frame: paint its
        // post-orbital-resolve opening board (shipped parcels already gone)
        // so the dusk beat shows the resolved orbit instead of stale cells.
        const uIdx = Number.isFinite(tick.duskFrameIdx)
          ? tick.duskFrameIdx : tick.lastFrameIdx;
        const uf = nightReplayFrames[uIdx];
        if (uf) _paintReplayBoard(uf);
      }
      if (animate) {
        // Diff pre-dawn vs dawn so the destruction / probe-decay FX ride
        // the sunrise; sunset just clears the film (no FX).
        runHorizonSweep(
          mapPlayer, isDawn ? "sunrise" : "sunset", preDawn, dawnFrame,
        );
      } else {
        setMapDaylight(isDawn ? "day" : "night");
      }
      // DUSK opens a night → flash the "NIGHT n begins" card (forward
      // play only, gated by the optional title-cards setting).
      if (!isDawn && animate && titleCardsEnabled && day) {
        const seasonLabel = _currentSeasonLabel();
        void showMapTitleCard(
          `NOX ${day} BEGINS`,
          seasonLabel ? `— ${seasonLabel} —` : "",
          { holdMs: 1500 },
        );
      }
      // Orbit report: auto-pop on forward play when the setting is on
      // and there's content. Suppressed during the live cinematic
      // (``_liveFxPlaying``) — there the recap pops once at the reveal.
      const kind = isDawn ? "recap" : "briefing";
      const hasContent = isDawn ? dayHasRecap(day) : dayHasBriefing(day);
      if (animate && !_liveFxPlaying && orbitFlashEnabled
          && day && hasContent) {
        const guardKey = `${kind}:${day}`;
        if (orbitFlashLastDay !== guardKey) {
          orbitFlashLastDay = guardKey;
          openReport(kind, day);
        }
      }
      if (replayCaptionEl) {
        replayCaptionEl.textContent = isDawn
          ? `[H22] AURORA · Nox ${day} ends — day breaks`
          : `[H00] VESPERA · Nox ${day} begins`;
      }
      if (replaySlotEl) {
        replaySlotEl.textContent = isDawn
          ? `Nox ${day} · AURORA` : `Nox ${day} · VESPERA`;
      }
      syncReplayScrubUi();
      lastPaintedReplayTickIdx = replayTickIdx;
      return;
    }
    // Terminal RESOLVE beat (#8) — the final settlement orbit. No night
    // frames follow, so keep the last night's board (its cells never change:
    // settlement is purely orbital) under a sunset film while station.js
    // plays the last catapult launch + vault settlement + score fold.
    if (tick && tick.slot === "resolve") {
      const day = Number(tick.day || 0) || 0;
      const movingForward = replayTickIdx > lastPaintedReplayTickIdx;
      const animate = mode === "forward" && movingForward
        && !reduceMotionMq.matches;
      const uf = nightReplayFrames[tick.lastFrameIdx];
      if (uf) _paintReplayBoard(uf);
      if (animate) runHorizonSweep(mapPlayer, "sunset", null, null);
      else setMapDaylight("night");
      if (animate && titleCardsEnabled) {
        const seasonLabel = _currentSeasonLabel();
        void showMapTitleCard(
          "SEASON RESOLVES",
          seasonLabel ? `— ${seasonLabel} —` : "",
          { holdMs: 1600 },
        );
      }
      if (replayCaptionEl)
        replayCaptionEl.textContent =
          "[H00] RESOLVE · final settlement — the season closes";
      if (replaySlotEl) replaySlotEl.textContent = "SEASON · RESOLVE";
      syncReplayScrubUi();
      lastPaintedReplayTickIdx = replayTickIdx;
      return;
    }
    const frameIdx = tick.lastFrameIdx;
    const frame = nightReplayFrames[frameIdx];
    if (replayCaptionEl)
      replayCaptionEl.textContent = String(frame?.caption ?? "");
    if (replaySlotEl)
      replaySlotEl.textContent = formatReplaySlotLabel(frame);

    // v0.9.9 — N-seat replay view dispatch (OBS combined vision vs a
    // single seat) + mine/EMP-cloud snapshot stash. See _paintReplayBoard.
    _paintReplayBoard(frame);
    syncReplayScrubUi();

    const decided =
      mode === "forward" ? "forward"
      : mode === "jump" ? "jump"
      : (replayTickIdx === lastPaintedReplayTickIdx + 1 ? "forward" : "jump");

    // v0.9.4 rev7 — only re-run delta animations on an ACTUAL tick
    // change. Same-tick re-renders (e.g. view-toggle clicks, repeat
    // scrub-input events at the same slider position) used to
    // re-fire weapon FX, which read as the animation "repeating
    // multiple times" while scrolling.
    const tickChanged = replayTickIdx !== lastPaintedReplayTickIdx;

    if (decided === "forward" && !reduceMotionMq.matches) {
      const beforeTickFrame = tick.firstFrameIdx > 0
        ? nightReplayFrames[tick.firstFrameIdx - 1]
        : null;
      runReplayAnimationsTick(mapPlayer, tick, beforeTickFrame);
    }
    // v1.2 — daylight is owned by the DAWN / DUSK slot ticks (handled
    // in the early slot branch above); every REAL frame is plain NIGHT.
    // The sunrise/sunset wipe runs only when we play/step onto a slot,
    // so here we just snap normal frames back to night (unless a slot's
    // wash is mid-flight, in which case we leave it alone).
    _prevPaintedReplayDay = frameDayOf(frame);
    if (!_washAnimating) {
      setMapDaylight("night");
    }
    // v0.7.3 — spawn collision rings whenever the tick frame (or any
    // frame in this tick's range) carries collision events. Forward
    // playback only; jumps fire the animation once for the destination
    // frame so the watcher gets a visual cue when scrubbing too.
    // v0.7.4 — same treatment for probe-crush splashes; events ride
    // on ``frame.crushed_probes`` populated by the engine when a
    // harvester drop/step lands on a probe (RULEBOOK §3.11.1).
    for (let i = tick.firstFrameIdx; i <= tick.lastFrameIdx; i += 1) {
      const f = nightReplayFrames[i];
      if (f && Array.isArray(f.collisions) && f.collisions.length) {
        playCollisionFx(f, decided === "forward" ? 160 : 0);
      }
      if (f && Array.isArray(f.crushed_probes) && f.crushed_probes.length) {
        playProbeCrushFx(f);
      }
    }
    // v0.9 — weapon FX (RULEBOOK §4.9). Forward playback only,
    // and only on an ACTUAL tick change: the minelayer arc / EMP
    // streak / chaff static are long showpiece animations, and
    // re-firing them on every scrub tick read as "the animation
    // repeats and streaks multiple times" while dragging the
    // slider. Persistent overlays (``paintMinesOverlay`` /
    // ``paintEmpCloudOverlay``) below still render the current
    // state at any scrub position, so skipping the one-shot FX
    // on jumps doesn't hide info.
    if (decided === "forward" && tickChanged) {
      for (let i = tick.firstFrameIdx; i <= tick.lastFrameIdx; i += 1) {
        const f = nightReplayFrames[i];
        if (f && Array.isArray(f.emp) && f.emp.length) {
          playEmpFx(f, i > 0 ? nightReplayFrames[i - 1] : null);
        }
        if (f && Array.isArray(f.mine) && f.mine.length) {
          playMineFx(f);
        }
        if (f && Array.isArray(f.chaff) && f.chaff.length) {
          playChaffFx(f);
        }
      }
    }
    // v0.9.11 — the transient on-map orbit banner was retired in
    // favour of the full-screen orbit reports (recap/briefing). Orbit
    // settlement intel now surfaces through the synthetic report ticks
    // + the [ RECAP ] / [ BRIEFING ] buttons, not a fading overlay.
    // EMP cloud overlay is a SNAPSHOT (re-painted every tick), so
    // pull it from the last frame in the tick range and render the
    // disk-of-cells overlay for any clouds still alive.
    const lastFrame = nightReplayFrames[tick.lastFrameIdx];
    paintEmpCloudOverlay(lastFrame);
    // v0.9.4 — mines are also persistent. Stamp the static
    // pixel-field marker on every cell currently in
    // ``mines_active``; the per-tick re-paint mirrors the EMP
    // cloud's "paint on every scrub" pattern so the footprint
    // never goes stale during a replay.
    paintMinesOverlay(lastFrame);
    // v1.x — redsign pulse overlay, gated to the current scrub (day, hour)
    // so a beacon pops at the exact discovery frame, then persists. Slot
    // ticks: DAWN = night resolved (show all that night's finds); DUSK =
    // night just beginning (hour 0, hide finds until their hour is reached).
    _redsignDayCutoff = Number(
      (tick && tick.day != null) ? tick.day : (lastFrame?.day ?? 0),
    ) || 0;
    const _rsSlot = tick && tick.slot;
    if (_rsSlot === "dawn") _redsignHourCutoff = Infinity;
    else if (_rsSlot === "dusk") _redsignHourCutoff = 0;
    else _redsignHourCutoff = Number(lastFrame?.hour) || 0;
    // v1.x — DISCOVERY BURST + delayed smear. On forward play, the instant a
    // region's (day, hour) is reached we (a) HOLD its fog smear back and (b)
    // schedule a one-shot red rhombus pulse — both timed to the tick's
    // sequencing dwell so they land AFTER the probe streak / harvester step
    // that revealed the seam, never a beat before it. The timer then reveals
    // the smear WITH the burst. Scrubs reset both sets so replays re-fire.
    // (Runs BEFORE the paint below so held regions are excluded this frame.)
    if (decided === "forward" && tickChanged && !reduceMotionMq.matches) {
      const _rsDay = _redsignDayCutoff;
      const _rsHour = _redsignHourCutoff;
      // ``_osPendingDwellMs`` == _maxLead + 1300 (probe ≈ 2900ms, drop ≈
      // 3900ms); the seam reveal completes ~(_maxLead + 820)ms in, so keying
      // to the full dwell guarantees burst + smear land AFTER the action.
      // Floor 850ms covers a lead-less harvester STEP; cap 4200ms is a belt.
      const _burstDelay = Math.min(
        4200, Math.max(850, Number(window._osPendingDwellMs) || 0),
      );
      for (const region of (Array.isArray(lastRedSign) ? lastRedSign : [])) {
        const rid = region && region.id;
        if (!rid || _redsignBurstFired.has(rid)) continue;
        const rd = Number(region.day);
        const rh = Number(region.hour) || 0;
        if (!Number.isFinite(rd) || rd !== _rsDay) continue;
        if (Number.isFinite(_rsHour) && _rsHour < rh) continue;
        _redsignBurstFired.add(rid);
        _redsignPendingReveal.add(rid);   // hide the smear until the burst
        const _rg = region;
        window.setTimeout(() => {
          _redsignPendingReveal.delete(rid);
          try { spawnRedsignBurst(_rg); } catch (_e2) {}
          try { paintRedsignOverlay(); } catch (_e3) {}
        }, _burstDelay);
      }
    } else if (decided !== "forward") {
      _redsignBurstFired.clear();
      _redsignPendingReveal.clear();
    }
    try { paintRedsignOverlay(); } catch (_e) {}
    syncReplayDrawer();
    lastPaintedReplayTickIdx = replayTickIdx;
  }

  /** Paint a replay tick, then run the end-of-season check. Every replay
   *  control (play loop, next/prev, scrub, day-nav) routes through here,
   *  so wrapping the core paint guarantees the closing settlement +
   *  victory celebration + score card fire whenever the cursor lands on
   *  the final tick — regardless of how it got there. ``_paintReplayFrameMain``
   *  has several early returns (slot / resolve ticks are exactly the
   *  terminal ones), so the check must sit in the wrapper, not inside. */
  function paintReplayFrameOntoMain(mode) {
    _paintReplayFrameMain(mode);
    try { handleReplaySeasonState(); } catch (_e) { /* non-fatal */ }
  }

  async function refreshNightReplay({ playFx = false } = {}) {
    if (!sessionId || !replayBar) return;
    // v0.7.5 — the replay BAR (controls) now lives in the universal
    // strip below the map and stays ALWAYS visible. We never hide
    // it; the scrub slider's ``disabled`` attribute handles the
    // empty-replay case for individual controls.
    const prevTickCount = replayTicks.length;
    if (!replayWindowCount) {
      nightReplayFrames = [];
      replayTicks = [];
      syncReplayRowOnly();
      return { newDayLanded: false, prevTickCount, tickCount: 0 };
    }
    try {
      const res = await fetch(`/api/game/${sessionId}/replay`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const payload = await res.json();
      const incoming = Array.isArray(payload.frames) ? payload.frames : [];
      const prevLastDay =
        nightReplayFrames.length > 0
          ? Number(nightReplayFrames[nightReplayFrames.length - 1]?.day || 0)
          : 0;
      const incomingLastDay =
        incoming.length > 0
          ? Number(incoming[incoming.length - 1]?.day || 0)
          : 0;
      const newDayLanded = incomingLastDay > prevLastDay;
      nightReplayFrames = incoming;
      // Fresh replay data → re-arm the per-night dawn-wipe dedupe.
      _sweptReplayNights = new Set();
      _prevPaintedReplayDay = null;
      replayDayIndex = Array.isArray(payload.day_index)
        ? payload.day_index
        : [];
      // v0.9.10 — stash the seat list from the replay response so
      // the replay-view buttons show all active seats (p3/p4 too).
      if (Array.isArray(payload.players) && payload.players.length) {
        window.__SOC_PLAYERS__ = payload.players.slice(0, 4);
        try { renderReplayViewButtons(); } catch (_e) {}
      }
      // v0.9.18 — populate player identity metadata (names, tags, colors)
      // from the replay payload so the watcher renders named, coloured
      // seats (scoreboard tags, end screen, vault borders) in replay mode.
      // setPlayerMeta also syncs the --seat-pN CSS vars.
      setPlayerMeta(payload.player_profiles);
      // v1.x — discovery-triggered redsign beacons for the replay. The
      // full final list is carried with per-region ``day``; the tick
      // painter day-gates it via ``_redsignDayCutoff``.
      lastRedSign = Array.isArray(payload.redsign) ? payload.redsign : [];
      // Fresh replay load → let every discovery burst fire again.
      _redsignBurstFired = new Set();
      _redsignPendingReveal = new Set();
      // v0.8.0 — cache per-day catapult settlements so the ORBIT
      // flash overlay can render without re-fetching.
      catapultByDay =
        (payload && payload.catapult_by_day) || {};
      // v1.x — final settlement breakdown ({} until season complete).
      settlementBySeat =
        (payload && payload.settlement) || {};
      // v1.x — authoritative post-settlement hoard ({} until complete).
      finalHoardSnapshot =
        (payload && payload.final_hoard) || {};
      // v1.0 — end-of-season replay metadata. If this is a freshly
      // loaded session, clear the auto-shown latch so the results
      // screen can pop again when the scrub reaches the end.
      if (endgameMeta.summaryFor !== sessionId) {
        endgameMeta.summary = null;
        endgameMeta.summaryFor = null;
        endgameMeta.replayAutoShown = false;
      }
      endgameMeta.replayComplete = !!(payload && payload.is_season_complete);
      endgameMeta.seasonName = (payload && payload.season_name) || null;
      replaySeasonDayCap = Number(payload && payload.season_day_cap) || 0;
      orbitLogByDay =
        (payload && payload.orbit_log_by_day) || {};
      // v0.9.8 — full per-day log payload so the LOG drawer can
      // refocus on the scrubber day even when the live tail no
      // longer covers it.
      logByDay =
        (payload && payload.log_by_day) || {};
      // v0.9.11 — per-day station-observation snapshots ({pre,post})
      // + observable orbital-activity tallies for the orbit reports.
      stationObsByDay =
        (payload && payload.station_obs_by_day) || {};
      orbitalActivityByDay =
        (payload && payload.orbital_activity_by_day) || {};
      orbitalEventsByDay =
        (payload && payload.orbital_events_by_day) || {};
      // Optional station UI hook — expose replay data + report renderers on
      // ``window`` so station.js (loaded after app.js) can build the inline
      // orbital panels without duplicating any report logic. Harmless no-ops
      // when the station UI is disabled (osOnOrbitalDataLoaded is undefined).
      window._socOrbitalData = {
        stationObsByDay, orbitalActivityByDay, orbitalEventsByDay,
        catapultByDay, playerProfiles: (payload && payload.player_profiles) || {}
      };
      window._socReplayViewSeat = replayViewSeat;
      window._socReconstructVault = (seat) => reconstructVaultAtTick(replayTickIdx, seat);
      // Reconstruct a seat's vault at an ARBITRARY tick index (not just the
      // cursor). DUSK uses ``idx-1`` to show the PRE-orbital vault (end of the
      // previous night) so the orbital depletion can animate down to post[N].
      window._socReconstructVaultAt = (tickIdx, seat) => reconstructVaultAtTick(tickIdx, seat);
      window._osOpenReport           = (kind, day) => openReport(kind, day);
      window._osRenderStationObs     = (day, phase, lbl, seat) => renderStationObsPanel(day, phase, lbl, seat);
      window._osRenderOrbitalObs     = (day, seat) => renderOrbitalObservations(day, seat);
      window._osRenderCatGrid        = (slots) => _orbitFlashRenderCatGrid(slots);
      window._osRenderCatLegend      = (slots, seats) => _orbitFlashRenderLegend(slots, seats);
      window._osGetCatapultBlob      = (day) => catapultByDay[String(day)] || null;
      // Green disposal manifest for the station's right-side hover card.
      // Mirrors _osRenderCatGrid but for the GREEN lane. v1.13 — the
      // second argument (slot total) is gone: the grid is exactly as long
      // as the manifest.
      window._osRenderGreenGrid      = (slots) =>
        _orbitFlashRenderGreenGrid(Array.isArray(slots) ? slots : []);
      window._osGetActiveSeatsList   = () => observedSeats();
      // Cumulative RED shipped score through (and including) ``throughDay``.
      // The station score readouts count up to this as the replay plays: at
      // each night's catapult launch the seat's score_shipped for that day
      // is folded in. Green (solar jettison) is disposal and adds no score.
      window._osGetCumulativeScore   = (throughDay) => {
        const out = {};
        const cap = Number(throughDay);
        if (!Number.isFinite(cap)) return out;
        for (const [dayKey, blob] of Object.entries(catapultByDay || {})) {
          if (Number(dayKey) > cap) continue;
          const seats = (blob && blob.catapult && blob.catapult.seats) || {};
          for (const [seat, sb] of Object.entries(seats)) {
            out[seat] = (out[seat] || 0) + (Number(sb && sb.score_shipped) || 0);
          }
        }
        return out;
      };
      // v1.x — per-seat final settlement breakdown for the closing RESOLVE
      // beat's +/- delta lines. Empty object until the season is complete.
      window._osGetSettlement        = () => settlementBySeat || {};
      // The day of the replay tick currently on screen (the night playing, or
      // the latest night that has played). Station hover/click cards read this
      // so they always reflect the live scrub position rather than a cached day.
      window._osGetCurrentReplayDay  = () => {
        try { return replayTicks[replayTickIdx]?.day ?? null; } catch (_) { return null; }
      };
      if (typeof osOnOrbitalDataLoaded === "function") osOnOrbitalDataLoaded();
      // v0.9.9 — final cumulative shipped score per seat (from the
      // hydrated session blob the replay endpoint just walked). The
      // HUD scoreboard reads this in replay mode so the totals
      // reflect the WHOLE season, not whatever frame the cursor
      // happens to be on.
      if (payload && payload.cumulative_shipped_score) {
        renderHudScoreboard(
          payload.cumulative_shipped_score,
          Array.isArray(payload.players) ? payload.players : null,
        );
        // v0.9.9 — keep the SHIPPED tab stats in sync with replay
        // scrubbing too. Bay count uses the live inventory cache;
        // in pure replay mode (no live session) it's just 0.
        const _shippedNow =
          lastLiveInventory && Array.isArray(lastLiveInventory.shipped)
            ? lastLiveInventory.shipped.length
            : 0;
        const _shippedCap =
          (lastLiveInventory && lastLiveInventory.shipped_capacity) || 25;
        renderShippedStats(
          payload.cumulative_shipped_score,
          Array.isArray(payload.players) ? payload.players : null,
          _shippedNow, _shippedCap,
        );
      }
      if (typeof payload.width === "number") replayDims.width = payload.width;
      if (typeof payload.height === "number") replayDims.height = payload.height;
      buildReplayTicks(nightReplayFrames);
      if (newDayLanded && nightReplayFrames.length) {
        replayTickIdx = findFirstTickOfDay(incomingLastDay);
      }
      if (replayTickIdx >= replayTicks.length)
        replayTickIdx = Math.max(0, replayTicks.length - 1);
      syncReplayRowOnly();
      if (mainMapSource === "replay") paintReplayFrameOntoMain();
      if (playFx && replayLastTurnFx && !_liveFxPlaying && replayTicks.length > prevTickCount) {
        void _playLiveTurnAnimations(prevTickCount);
      }
      return { newDayLanded, prevTickCount, tickCount: replayTicks.length };
    } catch {
      nightReplayFrames = [];
      replayTicks = [];
      replayDayIndex = [];
      syncReplayRowOnly();
      return { newDayLanded: false, prevTickCount, tickCount: 0 };
    }
  }

  // ── Multi-day replay helpers (Phase 4) ──────────────────────────
  const ACTIONABLE_TAGS = new Set(["step", "drop", "pickup", "probe"]);
  // v1.1 — dawn-boundary frame tags that drive the sunrise sweep. The
  // engine only stamps one of these when an entity is culled at dawn:
  // ``dawn`` = stranded harvesters destroyed; ``probe_decay`` = probes
  // expired by lifetime. Both fire ``runDawnSweep``.
  const DAWN_SWEEP_TAGS = new Set(["dawn", "probe_decay"]);

  /** v0.9.11 — does this day have a recap worth a synthetic tick?
   *  (A resolved night always logs something or stamps a pre-obs.) */
  function dayHasRecap(day) {
    if (!day) return false;
    const log = logByDay[String(day)] || logByDay[day];
    if (Array.isArray(log) && log.length) return true;
    const so = stationObsByDay[String(day)];
    return !!(so && so.pre);
  }

  /** v0.9.11 — does this day have a briefing worth a synthetic tick? */
  function dayHasBriefing(day) {
    if (!day) return false;
    return !!(catapultByDay[String(day)]
      && orbitBlobHasActivity(catapultByDay[String(day)]));
  }

  function buildReplayTicks(frames) {
    replayTicks = [];
    let i = 0;
    let lastDayBeforePush = null;
    // v1.2 — DAWN / DUSK slots. Each night N is bracketed by two
    // synthetic slot ticks that own the day/night transition + the
    // orbit reports:
    //   * DUSK(N)  — opens night N (full NIGHT, "NIGHT n begins" card,
    //                post-orbital BRIEFING for day N). ``lastFrameIdx``
    //                points at night N's FIRST frame so it labels as
    //                night N.
    //   * DAWN(N)  — closes night N (full DAY, pre-orbital RECAP for
    //                day N + the sunrise destruction FX). ``lastFrameIdx``
    //                / ``dawnFrameIdx`` point at night N's LAST frame
    //                (the hour-22 ``dawn`` frame on new seasons).
    // Slots are ALWAYS inserted (every season, regardless of the
    // "auto-pop reports" setting) so the scrubber timeline is uniform;
    // the wash animates only on forward play and the report auto-pop
    // stays gated by ``orbitFlashEnabled`` at paint time.
    const pushSlot = (slot, day, frameIdx, extra) => {
      replayTicks.push({
        frames: [], firstFrameIdx: frameIdx, lastFrameIdx: frameIdx,
        tag: slot, slot, day, ...(extra || {}),
      });
    };
    while (i < frames.length) {
      const f = frames[i];
      const next = frames[i + 1];
      // Order reads chronologically during forward auto-play:
      //   [night D-1 frames] -> DAWN(D-1) -> DUSK(D) -> [night D frames]
      const currentDay = f ? Number(f.day || 0) : 0;
      if (currentDay !== lastDayBeforePush) {
        if (lastDayBeforePush != null && lastDayBeforePush > 0 && i > 0) {
          // DAWN of the night that just ended → bind to its last frame.
          pushSlot("dawn", lastDayBeforePush, i - 1, { dawnFrameIdx: i - 1 });
        }
        if (currentDay > 0) {
          // DUSK opening the new night → bind to (and OWN) its hour-0 frame.
          // The ORBIT phase already resolved before this frame exists (ships
          // launched, blue burned, post[N] stamped), so hour 0 IS the
          // pre-praxis DUSK beat: post-orbital board + briefing. We no longer
          // emit a separate hour-0 "praxis begins" tick — see the open-skip
          // branch below.
          pushSlot("dusk", currentDay, i, { duskFrameIdx: i });
        }
      }
      // v0.9.9 — N-seat-aware pairing (true simultaneity). Pre-v0.9.9
      // we hard-coded the pair to 2 frames which meant in a 4-seat
      // game p1+p2 would group as one tick and p3+p4 would group as
      // a SEPARATE following tick — visually "first two play, then
      // the other two play" which is wrong. Every hour of PRAXIS
      // actually has one applied move per seat, so the correct
      // pairing is to grab ALL adjacent actionable frames from
      // DIFFERENT seats on the same day, up to seat count, into a
      // single tick. The simulator emits one frame per seat per
      // hour in seat-order, so the next N frames after ``i`` are
      // guaranteed to be the same hour's batch.
      if (f && ACTIONABLE_TAGS.has(f.tag) && f.owner) {
        const batch = [f];
        const seenOwners = new Set([f.owner]);
        let j = i + 1;
        const dayKey = Number(f.day);
        while (j < frames.length) {
          const cand = frames[j];
          if (!cand) break;
          if (!ACTIONABLE_TAGS.has(cand.tag)) break;
          if (!cand.owner) break;
          if (seenOwners.has(cand.owner)) break;
          if (Number(cand.day) !== dayKey) break;
          batch.push(cand);
          seenOwners.add(cand.owner);
          j += 1;
        }
        replayTicks.push({
          frames: batch,
          firstFrameIdx: i,
          lastFrameIdx: j - 1,
        });
        i = j;
      } else if (f && f.tag === "open") {
        // v1.3 — the hour-0 ``open`` frame gets NO standalone scrubber
        // position; the DUSK slot inserted at the day boundary owns it (it's
        // the pre-praxis orbital-resolve beat). This "combines" the redundant
        // synthetic-DUSK + hour-0 pair into one beat.
        i += 1;
      } else if (f && f.tag === "dawn") {
        // v1.2 — the hour-22 ``dawn`` frame gets NO standalone scrubber
        // position; the DAWN slot inserted at the day boundary owns it
        // (paints its post-dawn board + runs the sunrise wash + FX), so
        // there's a single DAWN position instead of a duplicate pair.
        i += 1;
      } else {
        replayTicks.push({
          frames: [f],
          firstFrameIdx: i,
          lastFrameIdx: i,
        });
        i += 1;
      }
      lastDayBeforePush = currentDay;
    }
    // Trailing DAWN — the LAST night's frames just ended, so cap the
    // timeline with that night's sunrise + RECAP slot.
    if (lastDayBeforePush != null && lastDayBeforePush > 0 && frames.length > 0) {
      pushSlot("dawn", lastDayBeforePush, frames.length - 1, {
        dawnFrameIdx: frames.length - 1,
      });
    }
    // Terminal RESOLVE beat (#8) — the FINAL settlement orbit closes the
    // season on ``day = cap + 1`` (refine / ship / green-flush only) with NO
    // night frames of its own. Append one synthetic tick so the last
    // catapult launch, GREEN flush, blue burn, +score lines and vault
    // settlement actually play out (and the winner celebration can fire)
    // instead of the results screen popping over an un-animated finale.
    if (endgameMeta.replayComplete && frames.length > 0) {
      const finalDay = (replaySeasonDayCap || lastDayBeforePush || 0) + 1;
      const finalBlob = catapultByDay[String(finalDay)];
      if (finalBlob && orbitBlobHasActivity(finalBlob)) {
        pushSlot("resolve", finalDay, frames.length - 1, { resolveDay: finalDay });
      }
    }
  }

  // ── REPAIR HARVESTER dialog ──────────────────────────────────────
  //
  // Vault-style modal replacing the legacy window.prompt for the
  // ``repair`` orbit action. Shows all harvesters; only damaged ones
  // are selectable (one per action). On confirm pushes
  // ``{a:"repair", unit:<id>}`` onto orbitQueue.

  const repairSubmitEl        = document.getElementById("cc-repair-submit");
  const repairSubmitBackdrop  = document.getElementById("cc-repair-submit-backdrop");
  const repairSubmitCloseBtn  = document.getElementById("cc-repair-submit-close");
  const repairSubmitCancelBtn = document.getElementById("cc-repair-submit-cancel");
  const repairSubmitOkBtn     = document.getElementById("cc-repair-submit-ok");
  const repairSubmitListEl    = document.getElementById("cc-repair-submit-list");
  const repairSubmitListEmptyEl = document.getElementById("cc-repair-submit-list-empty");
  const repairSubmitMetaUnitEl    = document.getElementById("cc-repair-submit-meta-unit");
  const repairSubmitMetaStatusEl  = document.getElementById("cc-repair-submit-meta-status");
  const repairSubmitMetaCostEl    = document.getElementById("cc-repair-submit-meta-cost");
  const repairSubmitMetaWalletEl  = document.getElementById("cc-repair-submit-meta-wallet");
  const repairSubmitMetaBalanceEl = document.getElementById("cc-repair-submit-meta-balance");

  const repairSubmitState = {
    /** @type {Array<any>} */ harvesters: [],
    /** @type {string|null} */ selectedId: null,
  };

  function _repairPrice() {
    const prices = (lastOrbitView && lastOrbitView.ship_prices) || {};
    return Number(prices.repair ?? 500);
  }

  function openRepairSubmit() {
    if (!repairSubmitEl) return;
    const assets = Array.isArray(lastOrbitView?.assets) ? lastOrbitView.assets : [];
    repairSubmitState.harvesters = assets.filter((a) => a && a.type === "harvester");
    repairSubmitState.selectedId = null;
    repairSubmitEl.hidden = false;
    repairSubmitEl.setAttribute("aria-hidden", "false");
    renderRepairSubmitList();
    updateRepairSubmitMeta();
  }

  function closeRepairSubmit() {
    if (!repairSubmitEl) return;
    repairSubmitEl.hidden = true;
    repairSubmitEl.setAttribute("aria-hidden", "true");
  }

  function renderRepairSubmitList() {
    if (!repairSubmitListEl) return;
    repairSubmitListEl.textContent = "";
    const harvesters = repairSubmitState.harvesters;
    if (repairSubmitListEmptyEl) repairSubmitListEmptyEl.hidden = harvesters.length > 0;
    for (const h of harvesters) {
      const id = String(h.id || "");
      const label = String(h.label || h.id || "");
      const loc = h.orbit
        ? "orbit"
        : Array.isArray(h.pos)
          ? `surface (${h.pos[0]},${h.pos[1]})`
          : "surface";
      const flags = [];
      if (h.carrying_red) flags.push("carrying RED");
      if (h.cargo_squares) flags.push(`${h.cargo_squares} cargo`);
      if (typeof h.repair_count === "number" && h.repair_count > 0)
        flags.push(`repaired ×${h.repair_count}`);
      const isSelected = repairSubmitState.selectedId === id;
      const row = document.createElement("div");
      row.className = "cc-repair-submit-unit" +
        (h.damaged ? " cc-repair-submit-unit--damaged" : " cc-repair-submit-unit--ok") +
        (isSelected ? " cc-repair-submit-unit--selected" : "");
      const nameEl = document.createElement("span");
      nameEl.className = "cc-repair-submit-unit-name";
      nameEl.textContent = label;
      const statusEl = document.createElement("span");
      statusEl.className = "cc-repair-submit-unit-status";
      statusEl.textContent = h.damaged ? "DAMAGED" : "ok";
      const locEl = document.createElement("span");
      locEl.className = "cc-repair-submit-unit-loc dim";
      locEl.textContent = loc + (flags.length ? ` · ${flags.join(" · ")}` : "");
      row.appendChild(nameEl);
      row.appendChild(statusEl);
      row.appendChild(locEl);
      if (h.damaged) {
        row.addEventListener("click", () => {
          repairSubmitState.selectedId = isSelected ? null : id;
          renderRepairSubmitList();
          updateRepairSubmitMeta();
        });
      } else {
        row.title = "not damaged — no repair needed";
      }
      repairSubmitListEl.appendChild(row);
    }
  }

  function updateRepairSubmitMeta() {
    const cost   = _repairPrice();
    const wallet = Math.max(0, Number(lastOrbitView?.credits ?? 0));
    const id     = repairSubmitState.selectedId;
    const h      = repairSubmitState.harvesters.find((x) => x.id === id) || null;
    const balance = wallet - cost;
    const canAfford = wallet >= cost;
    const isValid = !!id && !!h?.damaged && canAfford;

    if (repairSubmitMetaUnitEl)
      repairSubmitMetaUnitEl.textContent = h ? String(h.label || h.id) : "—";
    if (repairSubmitMetaStatusEl) {
      repairSubmitMetaStatusEl.textContent = h ? (h.damaged ? "DAMAGED" : "ok") : "—";
      repairSubmitMetaStatusEl.style.color = h?.damaged ? "#ffa03c" : "";
    }
    if (repairSubmitMetaCostEl)
      repairSubmitMetaCostEl.textContent = id ? String(cost) : "—";
    if (repairSubmitMetaWalletEl)
      repairSubmitMetaWalletEl.textContent = String(wallet);
    if (repairSubmitMetaBalanceEl) {
      repairSubmitMetaBalanceEl.textContent = id ? `${balance} cr` : "—";
      repairSubmitMetaBalanceEl.style.color = !id ? "" : canAfford ? "#6fdc8c" : "#e05050";
    }
    if (repairSubmitOkBtn) repairSubmitOkBtn.toggleAttribute("disabled", !isValid);
  }

  function _repairSubmitConfirm() {
    const id = repairSubmitState.selectedId;
    if (!id) return;
    orbitQueue.push({ a: "repair", unit: id });
    renderOrbitQueue();
    closeRepairSubmit();
  }

  repairSubmitCloseBtn?.addEventListener("click",  () => closeRepairSubmit());
  repairSubmitBackdrop?.addEventListener("click",  () => closeRepairSubmit());
  repairSubmitCancelBtn?.addEventListener("click", () => closeRepairSubmit());
  repairSubmitOkBtn?.addEventListener("click",     () => _repairSubmitConfirm());

  // ── v0.8.0 ORBIT phase replay overlay ────────────────────────────
  //
  // The overlay reuses the per-day ``catapult_by_day`` blob attached
  // to the replay payload. Each day entry has ``auction`` /
  // ``tithe`` / ``jettison`` sections describing the settlement.
  // The overlay also reads ``currentReplayActiveSeats()`` to honour
  // the user's P1 / P2 / P1+P2 view filter (so we never reveal a
  // seat that's currently hidden in fog-of-war mode).
  // v0.9.11 — unified full-screen orbit report shell.
  const reportEl = document.getElementById("cc-report");
  const reportBodyEl = document.getElementById("cc-report-body");
  const reportDayEl = document.getElementById("cc-report-day");
  const reportTitleEl = document.getElementById("cc-report-title");
  const reportBackdrop = document.getElementById("cc-report-backdrop");
  const reportCloseBtn = document.getElementById("cc-report-close");
  const reportTabRecapBtn = document.getElementById("cc-report-tab-recap");
  const reportTabBriefingBtn = document.getElementById("cc-report-tab-briefing");
  const replayRecapBtn = document.getElementById("replay-recap-btn");
  const replayBriefingBtn = document.getElementById("replay-briefing-btn");

  /** Active seats in the current replay view perspective. The
   *  overlay hides seats not in this set (e.g. if you're watching
   *  P1's fog-of-war view, P2's actions get masked).
   *
   *  v0.9.9 — uses ``replayViewSeat`` directly so the function is
   *  N-seat-aware (1..4 seats). OBS = every active seat in the
   *  session. Single-seat view = only that seat. The pre-v0.9.9
   *  hard-coded p1/p2 dispatch is gone. */
  function currentReplayActiveSeats() {
    const all = _activeSeatsForView();
    if (replayViewSeat === "obs" || replayViewSeat === "both") {
      return new Set(all);
    }
    if (typeof replayViewSeat === "string" && /^p[1-9]$/.test(replayViewSeat)) {
      return new Set([replayViewSeat]);
    }
    return new Set(all.length ? all : ["p1"]);
  }

  /** Build & display the ORBIT modal for the given day. */
  /** v0.9.9 — does this catapult_history blob represent something
   *  worth surfacing? Every orbit phase appends a blob even when both
   *  vaults were empty, so the auto-pop logic + replay timeline
   *  insertion need an activity gate to avoid popping a blank modal on
   *  a quiet day.
   *
   *  v1.13 — "activity" used to include intent as well as outcome: a
   *  submitted-but-losing bid was worth showing, because being outbid
   *  was a thing that happened *to* you. Settlement is unconditional
   *  now, so intent and outcome are the same thing and the gate is
   *  simply "did anything move".
   *
   *  @param {any} blob — single ``catapult_history`` entry
   *  (``{day, catapult, jettison}``). */
  function orbitBlobHasActivity(blob) {
    if (!blob || typeof blob !== "object") return false;
    const shipped = blob.catapult?.slot_assignments;
    if (Array.isArray(shipped) && shipped.length) return true;
    const dumped = blob.jettison?.slot_assignments;
    if (Array.isArray(dumped) && dumped.length) return true;
    // Fall back to the per-seat counts for blobs written before the
    // manifest existed, so old replays still open their briefing.
    for (const section of [blob.catapult, blob.jettison]) {
      const seats = (section && section.seats) || {};
      for (const seat of Object.keys(seats)) {
        if (Number(seats[seat]?.awarded ?? 0) > 0) return true;
      }
    }
    return false;
  }

  /** v0.9.11 — open the unified orbit report for ``day`` showing the
   *  ``kind`` view ("recap" | "briefing"). Always renders something —
   *  a "waiting for info" empty state when the requested phase hasn't
   *  produced data yet — so the manual replay-strip buttons never
   *  no-op. ``day`` defaults to the current context day. */
  function openReport(kind, day) {
    if (!reportEl || !reportBodyEl) return;
    reportKind = kind === "briefing" ? "briefing" : "recap";
    reportDay = Number(day || 0) || currentContextDay();
    syncReportTabs();
    renderReportBody();
    reportEl.hidden = false;
    reportEl.setAttribute("aria-hidden", "false");
  }

  /** Re-render whichever report is currently open (kind + day). */
  function renderReportBody() {
    if (!reportBodyEl) return;
    if (reportDayEl) reportDayEl.textContent = `day ${reportDay || "—"}`;
    if (reportTitleEl) {
      reportTitleEl.textContent =
        reportKind === "briefing" ? "POST-ORBITAL BRIEFING" : "PRE-ORBITAL RECAP";
    }
    if (reportKind === "briefing") renderPostOrbitBriefing(reportDay);
    else renderPreOrbitRecap(reportDay);
  }

  function syncReportTabs() {
    reportTabRecapBtn?.classList.toggle(
      "cc-report-seg-btn--active", reportKind === "recap",
    );
    reportTabBriefingBtn?.classList.toggle(
      "cc-report-seg-btn--active", reportKind === "briefing",
    );
  }

  function closeReport() {
    if (!reportEl) return;
    const wasOpen = !reportEl.hidden;
    reportEl.hidden = true;
    reportEl.setAttribute("aria-hidden", "true");
    // Closing the live-mode report triggers a full refresh so any
    // state that landed while it was up (next orbit resolving in the
    // background, opponent submissions, etc.) is reflected in the
    // panels the user is about to interact with.
    if (wasOpen && mainMapSource === "live" && sessionId) {
      void pullAllMaps();
    }
  }

  // ── v1.0 END-OF-SEASON results screen ───────────────────────────
  const endgameEl = document.getElementById("cc-endgame");
  const endgameBodyEl = document.getElementById("cc-endgame-body");
  const endgameSeasonEl = document.getElementById("cc-endgame-season");
  const endgameBackdrop = document.getElementById("cc-endgame-backdrop");
  const endgameCloseBtn = document.getElementById("cc-endgame-close");
  const endgameReopenBtn = document.getElementById("cc-endgame-reopen");
  const replayResultsBtn = document.getElementById("replay-results-btn");

  const endgameMeta = {
    /** Latest fetched summary payload (so the reopen pill + manifest
     *  sort can re-render without a round-trip). */
    summary: null,
    /** Session id the cached summary belongs to. */
    summaryFor: null,
    /** Manifest sort key: "value" | "player" | "day". */
    manifestSort: "value",
    /** True once we've auto-popped this completed live season. */
    liveAutoShown: false,
    /** Tracks the live completion edge so we only fade in on transition. */
    liveWasComplete: false,
    /** True once the replay scrub has auto-popped at its end. */
    replayAutoShown: false,
    /** True once the winner celebration + results have fired for this
     *  end-state. Reset when the user scrubs off the finale so it can
     *  replay. Dedupes the station resolve callback vs the scrub fallback. */
    finaleShown: false,
    /** Replay metadata captured from the /replay payload. */
    replayComplete: false,
    seasonName: null,
  };

  function egEsc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, (c) => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]
    ));
  }

  async function fetchEndgameSummary(force) {
    if (!sessionId) return null;
    if (
      !force
      && endgameMeta.summary
      && endgameMeta.summaryFor === sessionId
    ) {
      return endgameMeta.summary;
    }
    try {
      const res = await fetch(`/api/game/${sessionId}/summary`, {
        cache: "no-store",
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      endgameMeta.summary = data;
      endgameMeta.summaryFor = sessionId;
      return data;
    } catch (_e) {
      return null;
    }
  }

  async function openEndGameModal(force) {
    if (!endgameEl || !endgameBodyEl) return;
    const summary = await fetchEndgameSummary(force);
    if (!summary) return;
    renderEndgame(summary);
    endgameEl.hidden = false;
    endgameEl.setAttribute("aria-hidden", "false");
    endgameEl.classList.add("cc-endgame--in");
  }

  function closeEndGameModal() {
    if (!endgameEl) return;
    endgameEl.hidden = true;
    endgameEl.setAttribute("aria-hidden", "true");
    endgameEl.classList.remove("cc-endgame--in");
  }

  /** Show / hide the floating "SEASON RESULTS" reopen pill. */
  function updateEndgameReopen(visible) {
    if (endgameReopenBtn) endgameReopenBtn.hidden = !visible;
    // v1.0 — the [ RESULTS ] button sits in the replay-view row next to
    // [ RECAP ] / [ BRIEFING ] and is only meaningful for a finished
    // season (live completion or a complete replay).
    if (replayResultsBtn) replayResultsBtn.hidden = !visible;
  }

  function renderEndgame(summary) {
    if (!endgameBodyEl) return;
    const players = Array.isArray(summary.players) ? summary.players : [];
    if (endgameSeasonEl) {
      const cap = summary.season_day_cap || 0;
      endgameSeasonEl.textContent =
        (summary.season_name ? summary.season_name + " · " : "")
        + (cap ? `${cap}-Nox season` : "");
    }
    const winner = players[0];
    const runners = players.slice(1);

    const winnerHtml = winner
      ? `
        <div class="eg-winner">
          <div class="eg-winner-crown dim">// season victor</div>
          <div class="eg-winner-row">
            <span class="eg-dot" style="background:${egEsc(winner.color)}"></span>
            <span class="eg-winner-name">${egEsc(winner.name)}</span>
            <span class="eg-winner-score">${winner.score}</span>
          </div>
          <div class="eg-winner-sub dim">
            ${winner.is_human ? "human" : "agent"} ·
            ${winner.red_harvested} red harvested ·
            ${winner.harvesters_built} harvesters built
          </div>
        </div>`
      : `<div class="eg-winner dim">no players</div>`;

    const runnersHtml = runners.length
      ? `<div class="eg-runners">${runners.map((p) => `
          <div class="eg-runner">
            <span class="eg-rank dim">#${p.rank}</span>
            <span class="eg-dot" style="background:${egEsc(p.color)}"></span>
            <span class="eg-runner-name">${egEsc(p.name)}</span>
            <span class="eg-runner-score">${p.score}</span>
          </div>`).join("")}</div>`
      : "";

    const combatSeats = Array.isArray(summary.combat_seats)
      ? summary.combat_seats
      : players.map((p) => ({ seat: p.seat, name: p.name, color: p.color }));
    const tallyHtml = `
      <div class="eg-section-head dim">// final tallies</div>
      <div class="eg-tally-grid">
        ${players.map((p) => egTallyCard(p, combatSeats)).join("")}
      </div>`;

    const chartHtml = `
      <div class="eg-charts-2up">
        <div class="eg-chart-block">
          <div class="eg-section-head dim">// red harvested</div>
          <div class="eg-chart">${buildSeriesChartSvg(summary, "red_by_day", "Cumulative red harvested per player")}</div>
        </div>
        <div class="eg-chart-block">
          <div class="eg-section-head dim">// shipped score</div>
          <div class="eg-chart">${buildSeriesChartSvg(summary, "shipped_by_day", "Cumulative shipped score per player")}</div>
        </div>
      </div>`;

    const manifestHtml = `
      <div class="eg-section-head eg-manifest-head dim">
        <span>// shipping manifest</span>
        <label class="eg-sort">sort
          <select id="eg-manifest-sort" class="cli-select">
            <option value="value">by parcel value</option>
            <option value="player">by player</option>
            <option value="day">by day</option>
          </select>
        </label>
      </div>
      <div id="eg-manifest" class="eg-manifest"></div>`;

    endgameBodyEl.innerHTML =
      winnerHtml + runnersHtml + tallyHtml + chartHtml + manifestHtml;

    const sortSel = document.getElementById("eg-manifest-sort");
    if (sortSel) {
      sortSel.value = endgameMeta.manifestSort;
      sortSel.addEventListener("change", () => {
        endgameMeta.manifestSort = sortSel.value;
        renderManifest(summary, endgameMeta.manifestSort);
      });
    }
    renderManifest(summary, endgameMeta.manifestSort);
  }

  /** v1.6 — one kill-feed row: a stat label followed by N slash-separated
   *  counts, each rendered in the VICTIM seat's colour (FPS kill-feed style).
   *  Column ``i`` is the seat at ``combatSeats[i]``; a player's own column is
   *  included (you can crush your own probe). A zero shows dim/greyed. */
  function egKillfeedRow(label, counts, combatSeats) {
    const nums = combatSeats.map((s, i) => {
      const n = Number((counts || [])[i] || 0);
      const cls = n > 0 ? "eg-kf-num" : "eg-kf-num eg-kf-num--zero";
      const style = n > 0 ? ` style="color:${egEsc(s.color)}"` : "";
      return `<span class="${cls}"${style}>${n}</span>`;
    }).join('<span class="eg-kf-slash">/</span>');
    return `<div class="eg-kf-row"><span class="eg-kf-label">${label}</span>`
      + `<span class="eg-kf-nums">${nums}</span></div>`;
  }

  function egTallyCard(p, combatSeats) {
    const v = p.vault || {};
    const bd = p.breakdown || {};
    const kf = p.killfeed || {};
    const per = p.personal || {};
    const seats = Array.isArray(combatSeats) ? combatSeats : [];

    // Kill-feed (attacker→victim). Only show rows with at least one hit.
    const kfDefs = [
      ["probes crushed", "probes_crushed"],
      ["probes superseded", "probes_superseded"],
      ["EMP\u2019d probes", "emp_probes"],
      ["EMP\u2019d harvesters", "emp_harvesters"],
      ["chaff jams", "chaff_jams"],
      ["harvesters damaged", "harv_damaged"],
      ["harvesters lost (your chaff)", "harv_lost_chaff"],
    ];
    const kfRows = kfDefs
      .filter(([, key]) => (kf[key] || []).some((n) => Number(n) > 0))
      .map(([label, key]) => egKillfeedRow(label, kf[key], seats))
      .join("");
    const kfLegend = seats.map((s) =>
      `<span class="eg-kf-legend"><span class="eg-dot" style="background:`
      + `${egEsc(s.color)}"></span>${egEsc(s.tag || s.name || s.seat)}</span>`
    ).join("");
    const killfeedHtml = kfRows
      ? `<div class="eg-kf">
           <div class="eg-kf-head dim">// kill feed <span class="eg-kf-legend-row">${kfLegend}</span></div>
           ${kfRows}
         </div>`
      : "";

    // Personal (non-attributed) operations.
    const perDefs = [
      ["probes launched", "probes_launched"],
      ["harvesters dropped", "harvesters_dropped"],
      ["harvesters recovered", "harvesters_recovered"],
      ["red harvested", "red_harvested"],
      ["green harvested", "green_harvested"],
      ["blue harvested", "blue_harvested"],
      ["EMPs fired", "emps_fired"],
      ["chaff fired", "chaff_fired"],
      ["mines laid", "mines_laid"],
      ["moves cancelled", "moves_cancelled"],
    ];
    const perRows = perDefs
      .filter(([, key]) => Number(per[key] || 0) > 0)
      .map(([label, key]) =>
        `<div class="eg-trow"><span>${label}</span><span>${Number(per[key] || 0)}</span></div>`)
      .join("");
    const personalHtml = perRows
      ? `<div class="eg-tally-rows eg-tally-rows--sub">
           <div class="eg-kf-head dim">// operations</div>
           ${perRows}
         </div>`
      : "";

    return `
      <div class="eg-tally-card">
        <div class="eg-tally-head">
          <span class="eg-dot" style="background:${egEsc(p.color)}"></span>
          <span class="eg-tally-name">${egEsc(p.name)}</span>
          <span class="eg-tally-score">${p.score}</span>
        </div>
        <div class="eg-tally-rows">
          <div class="eg-trow"><span>shipped score</span><span>${bd.shipped ?? 0}</span></div>
          <div class="eg-trow"><span>vault red (sold at loss)</span><span>+${bd.vault_red_loss ?? 0}</span></div>
          <div class="eg-trow eg-trow--neg"><span>green penalty</span><span>-${bd.green_penalty ?? 0}</span></div>
          <div class="eg-trow eg-trow--sep"><span>credits spent</span><span>${p.credits_spent}</span></div>
          <div class="eg-trow"><span>harvesters built</span><span>${p.harvesters_built}</span></div>
          <div class="eg-trow"><span>blue used</span><span>${p.blue_spent}</span></div>
          <div class="eg-trow"><span>green jettisoned</span><span>${p.green_jettisoned}</span></div>
          <div class="eg-trow eg-trow--sep"><span>vault: red / green / blue</span><span>${v.red_total ?? 0} / ${v.green ?? 0} / ${v.blue ?? 0}</span></div>
          <div class="eg-trow"><span>green still held</span><span>${p.green_held}</span></div>
        </div>
        ${killfeedHtml}
        ${personalHtml}
      </div>`;
  }

  /** Inline SVG step chart of cumulative RED harvested per player. */
  /** Compact inline SVG step chart of a cumulative per-player series.
   *  ``seriesKey`` selects the per-seat day-indexed arrays on the
   *  summary (``red_by_day`` or ``shipped_by_day``). Sized small so two
   *  sit side-by-side; values can be negative (clamped axis at 0). */
  function buildSeriesChartSvg(summary, seriesKey, ariaLabel) {
    const days = Array.isArray(summary.days) ? summary.days : [];
    const players = Array.isArray(summary.players) ? summary.players : [];
    const series = (summary && summary[seriesKey]) || {};
    const W = 340;
    const H = 150;
    const padL = 30;
    const padR = 8;
    const padT = 8;
    const padB = 18;
    const n = days.length;
    let maxV = 1;
    let minV = 0;
    for (const p of players) {
      const arr = series[p.seat] || [];
      for (const v of arr) {
        if (v > maxV) maxV = v;
        if (v < minV) minV = v;
      }
    }
    const span = (maxV - minV) || 1;
    const plotW = W - padL - padR;
    const plotH = H - padT - padB;
    const xFor = (i) => padL + (n <= 1 ? 0 : (plotW * i) / (n - 1));
    const yFor = (v) => padT + plotH - (plotH * (v - minV)) / span;

    let grid = "";
    const bands = 3;
    for (let b = 0; b <= bands; b += 1) {
      const val = Math.round(minV + (span * b) / bands);
      const y = yFor(val);
      grid += `<line class="eg-grid" x1="${padL}" y1="${y.toFixed(1)}" x2="${W - padR}" y2="${y.toFixed(1)}"/>`;
      grid += `<text class="eg-axis" x="${padL - 5}" y="${(y + 3).toFixed(1)}" text-anchor="end">${val}</text>`;
    }
    let xlabels = "";
    const stride = n > 8 ? Math.ceil(n / 8) : 1;
    days.forEach((d, i) => {
      if (i % stride !== 0 && i !== n - 1) return;
      const x = xFor(i);
      xlabels += `<text class="eg-axis" x="${x.toFixed(1)}" y="${H - 6}" text-anchor="middle">${d}</text>`;
    });
    let paths = "";
    for (const p of players) {
      const arr = series[p.seat] || [];
      if (!arr.length) continue;
      let d = `M ${xFor(0).toFixed(1)} ${yFor(arr[0]).toFixed(1)}`;
      for (let i = 1; i < arr.length; i += 1) {
        const x = xFor(i).toFixed(1);
        const yPrev = yFor(arr[i - 1]).toFixed(1);
        const y = yFor(arr[i]).toFixed(1);
        d += ` L ${x} ${yPrev} L ${x} ${y}`;
      }
      paths += `<path class="eg-line" d="${d}" fill="none" stroke="${egEsc(p.color)}" stroke-width="2"/>`;
    }
    return `
      <svg viewBox="0 0 ${W} ${H}" class="eg-chart-svg" preserveAspectRatio="xMidYMid meet" role="img" aria-label="${egEsc(ariaLabel)}">
        ${grid}${paths}${xlabels}
      </svg>`;
  }

  function renderManifest(summary, sortKey) {
    const host = document.getElementById("eg-manifest");
    if (!host) return;
    const rows = Array.isArray(summary.manifest) ? summary.manifest.slice() : [];
    const cmp = {
      value: (a, b) => b.value - a.value,
      day: (a, b) => (a.day - b.day) || (b.value - a.value),
      player: (a, b) => String(a.name).localeCompare(String(b.name)) || (b.value - a.value),
    }[sortKey] || ((a, b) => b.value - a.value);
    rows.sort(cmp);
    if (!rows.length) {
      host.classList.remove("cc-vault-grid");
      host.innerHTML = `<div class="dim eg-manifest-empty">nothing shipped this season.</div>`;
      return;
    }
    // v1.0 — render the manifest with the exact same vault/shipping
    // squares the live game uses: seat-coloured frames + the on-hover
    // tooltip (effective purity, shipping paid, tier × multiplier,
    // score yielded). ``renderStorageGrid`` reads full parcel objects
    // and binds the shared storage tooltip.
    host.classList.add("cc-vault-grid");
    renderStorageGrid(host, rows, rows.length, { ownerBorders: true });
  }

  /** Final-orbit UI. Driven off the live /status ``final_orbit`` flag.
   *
   *  v1.13 — this used to grey out every build and repair, leaving only
   *  refine / ship / flush, because those were the last-turn moves that
   *  still paid. All three are gone and settlement happens on its own,
   *  so there is nothing left to protect the player from except wasting
   *  their own credits — which the banner warns about and the engine
   *  now permits. The buttons stay live; we only clear any lock a
   *  previous version of this code may have left on them. */
  function updateFinalOrbitUi(isFinal) {
    const banner = document.getElementById("final-orbit-banner");
    if (banner) banner.hidden = !isFinal;
    document.querySelectorAll("[data-orbit-action]").forEach((btn) => {
      btn.classList.remove("orbit-btn--locked");
      btn.removeAttribute("disabled");
    });
  }

  // ── v1.4 Winner celebration (#8) ─────────────────────────────────
  //
  // A full-bleed overlay that sweeps the winner's colour across the screen
  // with a "SEASON VICTOR" banner before the detailed results modal opens.
  // The overlay DOM is created lazily (no index.html markup needed); styles
  // live in styles.css (``.cc-victor*``). Resolves when the beat ends or the
  // viewer clicks to skip.
  function showWinnerCelebration(summary) {
    return new Promise((resolve) => {
      const players = Array.isArray(summary && summary.players)
        ? summary.players : [];
      if (!players.length) { resolve(); return; }
      const winner = players[0];
      const tie = players.length > 1
        && Number(players[1].score) === Number(winner.score);
      const color = winner.color || "#e8543f";
      let ov = document.getElementById("cc-victor");
      if (!ov) {
        ov = document.createElement("div");
        ov.id = "cc-victor";
        ov.className = "cc-victor";
        ov.innerHTML =
          '<div class="cc-victor-sweep"></div>' +
          '<div class="cc-victor-core">' +
          '<div class="cc-victor-kicker"></div>' +
          '<div class="cc-victor-name"></div>' +
          '<div class="cc-victor-score"></div>' +
          '<div class="cc-victor-hint">click to see full results</div>' +
          "</div>";
        document.body.appendChild(ov);
      }
      ov.style.setProperty("--victor-color", color);
      ov.querySelector(".cc-victor-kicker").textContent =
        tie ? "// season draw" : "// season victor";
      const nameEl = ov.querySelector(".cc-victor-name");
      nameEl.textContent = tie
        ? "STALEMATE"
        : (winner.name || String(winner.seat || "").toUpperCase());
      nameEl.style.color = tie ? "" : color;
      ov.querySelector(".cc-victor-score").textContent =
        `${Number(winner.score || 0).toLocaleString()} pts`;
      ov.hidden = false;
      void ov.offsetWidth;  // reflow so the transition plays
      ov.classList.add("cc-victor--in");
      let done = false;
      const finish = () => {
        if (done) return;
        done = true;
        ov.classList.remove("cc-victor--in");
        window.setTimeout(() => { ov.hidden = true; }, 420);
        ov.removeEventListener("click", finish);
        resolve();
      };
      ov.addEventListener("click", finish);
      window.setTimeout(finish, 3600);
    });
  }

  /** Play the winner celebration then open the results modal. Idempotent
   *  via ``endgameMeta.finaleShown`` so the replay resolve callback and the
   *  scrub-to-end fallback can't double-fire. */
  async function triggerSeasonFinale(force) {
    if (endgameMeta.finaleShown && !force) return;
    endgameMeta.finaleShown = true;
    const summary = await fetchEndgameSummary(!!force);
    if (!summary) { endgameMeta.finaleShown = false; return; }
    if (!reduceMotionMq.matches) {
      try { await showWinnerCelebration(summary); } catch (e) { /* noop */ }
    }
    await openEndGameModal(true);
  }

  // Station hook: the final RESOLVE replay tick calls this once its launch
  // animation has fully played out, so the celebration lands AFTER the last
  // catapult fires + vaults settle rather than over an un-animated finale.
  window._osOnSeasonResolved = function () {
    // In replay, honour the "play ending on replay" setting: when OFF the
    // RESOLVE beat still animates the final settlement, but we don't auto-pop
    // the victory celebration + score card (reachable via the results pill).
    if (mainMapSource === "replay" && !replayEndAnimEnabled) return;
    void triggerSeasonFinale(false);
  };

  /** Live-mode hook: fade in the results screen the moment a season
   *  completes, and keep the reopen pill available afterwards. */
  function handleLiveSeasonState(st) {
    const complete = !!(st && st.is_season_complete);
    const isFinal = !!(st && st.final_orbit);
    updateFinalOrbitUi(isFinal && !complete);
    if (mainMapSource !== "live") return;
    if (complete) {
      updateEndgameReopen(true);
      if (!endgameMeta.liveWasComplete && !endgameMeta.liveAutoShown) {
        endgameMeta.liveAutoShown = true;
        // #4 — play the FINAL settlement resolve beat (catapult launch + score
        // fold) FIRST, then celebrate. The confetti must land after the last
        // scores are on the board, not before the orbit even resolves.
        //
        // Bug B — this hook runs inside ``refreshStatus``, which in
        // ``pullAllMaps`` races ``refreshNightReplay`` (they run in parallel).
        // On the season-closing pull the final day's orbital blob
        // (``catapultByDay[day]``) may not be loaded yet, so a naive check fell
        // straight through to an un-animated ``triggerSeasonFinale`` — the score
        // card popped BEFORE the settlement played. Retry briefly until the blob
        // lands (refreshNightReplay populates it), then play the resolve beat;
        // only fall back to a direct finale if it never arrives.
        if (reduceMotionMq.matches) {
          void triggerSeasonFinale(true);
        } else {
          const _tryResolveBeat = () => {
            const _day = Number(lastLiveInventory?.day) || 0;
            const _blob = window._socOrbitalData?.catapultByDay?.[String(_day)];
            if (_day > 0 && _blob && orbitBlobHasActivity(_blob)
                && typeof window.osOnLiveResolve === "function") {
              window.osOnLiveResolve(_day, () => { void triggerSeasonFinale(true); });
              return true;
            }
            return false;
          };
          if (!_tryResolveBeat()) {
            let _tries = 0;
            const _iv = window.setInterval(() => {
              _tries += 1;
              if (_tryResolveBeat()) { clearInterval(_iv); return; }
              if (_tries >= 16) {  // ~4s — blob truly absent (no orbital activity)
                clearInterval(_iv);
                if (!endgameMeta.finaleShown) void triggerSeasonFinale(true);
              }
            }, 250);
          }
        }
      }
    }
    endgameMeta.liveWasComplete = complete;
  }

  /** Replay-mode hook: auto-open the results screen once the scrub
   *  reaches the final tick of a completed season; keep the reopen
   *  pill available whenever the loaded replay is complete. */
  function handleReplaySeasonState() {
    if (mainMapSource !== "replay") return;
    if (!endgameMeta.replayComplete) {
      updateEndgameReopen(false);
      return;
    }
    updateEndgameReopen(true);
    const atEnd =
      replayTicks.length > 0 && replayTickIdx >= replayTicks.length - 1;
    if (atEnd && !endgameMeta.replayAutoShown) {
      endgameMeta.replayAutoShown = true;
      // "play ending on replay" OFF → stop on the last window without the
      // auto settlement/victory pop. The results pill stays available above so
      // the score card is still one click away.
      if (!replayEndAnimEnabled) return;
      const lastTick = replayTicks[replayTicks.length - 1];
      const isResolve = !!(lastTick && lastTick.slot === "resolve");
      if (isResolve) {
        // The RESOLVE beat drives the finale via ``_osOnSeasonResolved`` once
        // its catapult launch has played. Fallback: if that callback never
        // arrives (station UI off, or a direct scrub onto the finale), fire
        // the finale after the resolve dwell so results still pop.
        const dwell = Number(window._osPendingDwellMs) || 0;
        window.setTimeout(() => {
          if (!endgameMeta.finaleShown) void triggerSeasonFinale(false);
        }, dwell > 0 ? dwell + 400 : 1200);
      } else {
        void triggerSeasonFinale(false);
      }
    } else if (!atEnd) {
      // Allow it to re-pop if the user scrubs back then to the end.
      endgameMeta.replayAutoShown = false;
      endgameMeta.finaleShown = false;
    }
  }

  if (endgameCloseBtn) endgameCloseBtn.addEventListener("click", closeEndGameModal);
  if (endgameBackdrop) endgameBackdrop.addEventListener("click", closeEndGameModal);
  if (endgameReopenBtn) {
    endgameReopenBtn.addEventListener("click", () => { void openEndGameModal(false); });
  }
  if (replayResultsBtn) {
    replayResultsBtn.addEventListener("click", () => { void openEndGameModal(false); });
  }
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && endgameEl && !endgameEl.hidden) closeEndGameModal();
  });

  /** The day a manual report button should target. In replay the day
   *  at the scrub cursor bundles both reports, so either kind uses
   *  ``currentReplayDay()``. Live is kind-aware: the BRIEFING binds to
   *  the latest orbit settlement (``catapultByDay``), while the RECAP
   *  binds to the most-recently-resolved night (latest ``pre``
   *  snapshot), which is the previous day number. */
  function contextDayForReport(kind) {
    if (mainMapSource === "replay" && replayTicks.length) {
      const d = currentReplayDay();
      if (d) return d;
    }
    if (kind === "briefing") {
      let best = 0;
      for (const k of Object.keys(catapultByDay || {})) {
        const n = Number(k);
        if (Number.isFinite(n) && n > best) best = n;
      }
      return best || Number(lastLiveDay || 0) || 0;
    }
    let best = 0;
    for (const k of Object.keys(stationObsByDay || {})) {
      const n = Number(k);
      if (Number.isFinite(n) && n > best
        && stationObsByDay[k] && stationObsByDay[k].pre) best = n;
    }
    return best || Math.max(0, (Number(lastLiveDay || 0) || 0) - 1);
  }

  /** Default context day for opening a report (kind-agnostic). */
  function currentContextDay() {
    return contextDayForReport(reportKind);
  }

  /** Render the modal body from a single day's catapult payload.
   *
   *  v0.9.9 — full rewrite. Two-column layout per the orbital replay
   *  spec:
   *
   *    LEFT  · YOUR ACTIONS THIS NIGHT
   *      Filtered ``log_by_day[N]`` entries belonging to the active
   *      seat (drops/picks/repairs/builds/jettisons).
   *    RIGHT · INTERACTIVE 4×5 CATAPULT GRID
   *      Drawn from the engine's new ``slot_assignments`` ledger.
   *      Edge colour = owner seat; mouseover via the shared vault
   *      tooltip system exposes ``owner / coords / tier / raw +
   *      effective purity / multiplier / final score`` for EVERY
   *      seat (no fog gating — this is the post-orbit settlement
   *      reveal). Failed-row slots render dashed with a "fuel paid,
   *      no ship" tooltip.
   *    FOOTER · per-seat totals row
   *      Mirrors the HUD scoreboard so the watcher reads the day's
   *      score change at a glance.
   *
   *  The active-seat filter still honours the replay
   *  view-perspective (P1 / P2 / OBS); a hidden seat's actions
   *  collapse to a single "// hidden in current view" line. The
   *  catapult GRID itself is NOT fog-gated per the user's spec.
   */
  /** v0.9.11 — POST-ORBITAL BRIEFING: this day's catapult settlement
   *  (shipping grid + solar jettison + per-seat totals) folded in from
   *  the legacy orbit-flash renderer, plus post-settlement station
   *  observations and a per-player orbit action log. */
  function renderPostOrbitBriefing(day) {
    if (!reportBodyEl) return;
    reportBodyEl.textContent = "";
    day = Number(day || 0) || 0;
    if (typeof osOnOrbitalReportDay === "function") osOnOrbitalReportDay("briefing", day);
    const blob = catapultByDay[String(day)];
    // "Waiting for info" — the night has resolved but this day's
    // orbit hasn't settled yet (no catapult blob), so there's nothing
    // to brief on. Render an explicit empty state rather than no-op.
    if (!blob) {
      const empty = document.createElement("div");
      empty.className = "cc-report-empty dim";
      empty.textContent =
        "// post-orbital briefing \u2014 waiting for settlement\u2026";
      reportBodyEl.appendChild(empty);
      return;
    }
    const cat = blob?.catapult || {};
    const slotAssignments = Array.isArray(cat?.slot_assignments)
      ? cat.slot_assignments
      : [];
    const allSeats =
      Array.isArray(window.__SOC_PLAYERS__) && window.__SOC_PLAYERS__.length
        ? window.__SOC_PLAYERS__
        : ["p1", "p2"];

    const wrap = document.createElement("div");
    wrap.className = "cc-orbit-flash-grid-wrap";

    // ── LEFT: actions panel ─────────────────────────────────────
    const actionsCol = document.createElement("div");
    actionsCol.className = "cc-orbit-flash-actions";
    const actionsHead = document.createElement("div");
    actionsHead.className = "cc-orbit-flash-actions-head";
    const viewerSeat = _orbitFlashViewerSeat();
    actionsHead.textContent =
      `// ${playerTag(viewerSeat)} actions \u00B7 Nox ${day}`;
    actionsCol.appendChild(actionsHead);
    const actionRows = _orbitFlashActionRows(day, viewerSeat);
    if (!actionRows.length) {
      const empty = document.createElement("div");
      empty.className = "cc-orbit-flash-action cc-orbit-flash-action--dim";
      empty.textContent = "// no orders logged";
      actionsCol.appendChild(empty);
    } else {
      for (const line of actionRows) {
        const node = document.createElement("div");
        node.className = line.level === "error"
          ? "cc-orbit-flash-action cc-orbit-flash-action--err"
          : "cc-orbit-flash-action";
        node.textContent = String(line.text || "");
        actionsCol.appendChild(node);
      }
    }
    wrap.appendChild(actionsCol);

    // ── RIGHT: interactive catapult grid ────────────────────────
    const rightCol = document.createElement("div");
    rightCol.className = "cc-orbit-flash-grid-side";
    const gridHead = document.createElement("div");
    gridHead.className = "cc-orbit-flash-section-head";
    const slotsTotal = cat?.slots_total ?? 20;
    const slotsAwarded = cat?.slots_awarded ?? 0;
    // v0.9.9 — when zero seats submitted a bid the grid would
    // render as 20 empty pips with no context. Detect that case
    // (no slot assignments AND no submitter) and show a clean
    // "quiet orbit" panel instead of the empty 4x5 lattice.
    const anyBids = Object.values(cat?.seats || {}).some(
      (s) => s && s.submitted,
    );
    gridHead.textContent =
      `SHIPPING CATAPULT \u00B7 ${slotsAwarded}/${slotsTotal} slots shipped`;
    rightCol.appendChild(gridHead);
    if (!slotAssignments.length && !anyBids) {
      const quiet = document.createElement("div");
      quiet.className = "cc-orbit-flash-quiet";
      quiet.textContent =
        "// no catapult bids this Nox \u00B7 quiet orbit";
      rightCol.appendChild(quiet);
    } else {
      rightCol.appendChild(_orbitFlashRenderCatGrid(slotAssignments));
      rightCol.appendChild(_orbitFlashRenderLegend(slotAssignments, allSeats));
    }
    wrap.appendChild(rightCol);

    reportBodyEl.appendChild(wrap);

    // ── FOOTER: per-seat totals row + solar jettison line ───────
    const totals = document.createElement("div");
    totals.className = "cc-orbit-flash-totals";
    for (const seat of allSeats) {
      const seatBlob = cat?.seats?.[seat] || {};
      const row = document.createElement("div");
      row.className = "cc-orbit-flash-total-row";
      row.setAttribute("data-seat", seat);
      // v0.9.x — RED catapult is a per-parcel CREDIT-bid draft, not a
      // fuel burn: report shipped count, credits committed, and score.
      const shipped = seatBlob.awarded ?? seatBlob.shipped_count ?? 0;
      const credits = seatBlob.credits_committed ?? 0;
      const score = Math.round(Number(seatBlob.score_shipped) || 0);
      const tag = document.createElement("span");
      tag.textContent = playerTag(seat);
      tag.style.color = ownerColor(seat);
      const val = document.createElement("span");
      val.textContent =
        `${shipped} \u00B7 ${credits} cr \u00B7 +${score}`;
      row.append(tag, val);
      totals.appendChild(row);
    }
    reportBodyEl.appendChild(totals);

    // ── GREEN CATAPULT (flush) — always shown, public like RED ──────
    reportBodyEl.appendChild(_orbitFlashRenderGreenSection(blob?.jettison, allSeats));

    // ── Post-settlement station observations ────────────────────
    reportBodyEl.appendChild(
      renderStationObsPanel(day, "post", "STATION OBSERVATIONS \u00B7 post-settlement"),
    );

    // ── Per-player orbit action log ─────────────────────────────
    reportBodyEl.appendChild(renderPerPlayerOrbitLog(day));
  }

  /** v0.9.11 — PRE-ORBITAL RECAP: the "what happened / what I saw"
   *  record for the night that just resolved. Full night chronicle +
   *  per-platform orbital activity (launch/recovery counts, no coords)
   *  + end-of-night station observations. */
  function renderPreOrbitRecap(day) {
    if (!reportBodyEl) return;
    reportBodyEl.textContent = "";
    day = Number(day || 0) || 0;
    if (typeof osOnOrbitalReportDay === "function") osOnOrbitalReportDay("recap", day);
    const nightLog = logByDay[String(day)] || logByDay[day] || [];
    const hasPre = !!(stationObsByDay[String(day)]
      && stationObsByDay[String(day)].pre);
    if (!Array.isArray(nightLog) || (!nightLog.length && !hasPre)) {
      const empty = document.createElement("div");
      empty.className = "cc-report-empty dim";
      empty.textContent =
        "// pre-orbital recap \u2014 waiting for the Nox to resolve\u2026";
      reportBodyEl.appendChild(empty);
      return;
    }

    // v0.9.12 — ordered, full-width sections (was a 2-col grid):
    //   1. STATION OBSERVATIONS — per-seat hold / fissile / toxic cards.
    //   2. ORBITAL OBSERVATIONS — per-seat weather-style boxes, vault
    //      iconography (probes / drops / recoveries / weapons).
    //   3. SURFACE — the seat-coloured chronicle of witnessed events.
    reportBodyEl.appendChild(
      renderStationObsPanel(day, "pre", "STATION OBSERVATIONS \u00B7 end of Nox"),
    );
    reportBodyEl.appendChild(renderOrbitalObservations(day));
    reportBodyEl.appendChild(renderSurfaceLog(day));
  }

  // v0.9.13 — ORBITAL OBSERVATIONS is now a chronological EVENT LOG per
  // platform (probe launched → orblift dropped harvester → …) instead of
  // an aggregate count table. Glyphs still lean on the vault overlay so
  // each line reads at a glance; ordering follows the night's replay
  // frames. Coordinates are never surfaced (public silhouette only —
  // RULEBOOK §3.15.x).
  const ORBITAL_EVENT_GLYPHS = {
    probe: "\u00B7",
    drop: "\u25BC",
    pickup: "\u25B2",
    mine_lay: "\u25C6",
    emp_launch: "\u25CE",
    chaff_flare: "\u2736",
    abandoned: "\u2716", // heavy "X" — a dead harvester (harvesters are X)
    damaged: "\u26A0",   // warning — a harvester limped back damaged
  };

  /** Map one orbital-event record ``{tag, carrying?, damaged?, emped?}``
   *  to a ``{glyph, glyphTone?, parts:[{text,tone?}]}`` segment list, or
   *  null for an unknown tag. ``parts`` lets the renderer tint/embolden
   *  individual phrases: bold "carrying cargo", red "empty" / "damaged" /
   *  "abandoned", cyan "emp'ed". The record is built server-side
   *  (``GameSession.tally_orbital_events``) and never carries coords. */
  function orbitalEventForRecord(rec) {
    if (!rec) return null;
    const glyph = ORBITAL_EVENT_GLYPHS[rec.tag];
    if (!glyph) return null;
    switch (rec.tag) {
      case "probe":
        return { glyph, parts: [{ text: "probe launched" }] };
      case "drop":
        return { glyph, parts: [{ text: "orblift dropped harvester" }] };
      case "pickup": {
        const parts = [{ text: "orblift recovered harvester \u2014 " }];
        if (rec.carrying) parts.push({ text: "carrying cargo", tone: "cargo" });
        else parts.push({ text: "empty", tone: "empty" });
        if (rec.damaged) {
          parts.push({ text: " \u00B7 " }, { text: "damaged", tone: "damaged" });
        }
        if (rec.emped) {
          parts.push({ text: " \u00B7 " }, { text: "emp\u2019ed", tone: "emped" });
        }
        return { glyph, parts };
      }
      case "abandoned": {
        const parts = [
          { text: "a harvester was abandoned on the surface", tone: "abandoned" },
        ];
        if (rec.damaged) {
          parts.push({ text: " \u00B7 " }, { text: "damaged", tone: "damaged" });
        }
        if (rec.emped) {
          parts.push({ text: " \u00B7 " }, { text: "emp\u2019ed", tone: "emped" });
        }
        return { glyph, glyphTone: "abandoned", parts };
      }
      case "damaged": {
        const parts = [
          { text: "a harvester is ", tone: "damaged" },
          { text: "damaged", tone: "damaged" },
          { text: ", awaiting pickup", tone: "damaged" },
        ];
        if (rec.emped) {
          parts.push({ text: " \u00B7 " }, { text: "emp\u2019ed", tone: "emped" });
        }
        return { glyph, glyphTone: "damaged", parts };
      }
      case "mine_lay":
        return { glyph, parts: [{ text: "minelayer deployed" }] };
      case "emp_launch":
        return { glyph, parts: [{ text: "EMP fired" }] };
      case "chaff_flare":
        return { glyph, parts: [{ text: "chaff flare" }] };
      default:
        return null;
    }
  }

  /** Reconstruct an ordered-ish orbital event list from a per-seat COUNT
   *  tally (the legacy ``orbital_activity_by_day`` shape). Used as a
   *  fallback for sessions / nights that predate the ordered event log
   *  (``orbital_events_by_day``) — e.g. a night that resolved on an older
   *  server build — so the Orbital Observations box still shows real
   *  activity instead of a misleading "quiet platform". Grouped by kind
   *  (probe → drop → recovery → ordnance); exact interleaving isn't
   *  recoverable from counts. */
  function eventsFromActivityTally(tally) {
    if (!tally || typeof tally !== "object") return [];
    const num = (v) => (Number.isFinite(Number(v)) ? Math.max(0, Number(v)) : 0);
    const out = [];
    for (let i = 0; i < num(tally.probes); i++) out.push({ tag: "probe" });
    for (let i = 0; i < num(tally.dropped); i++) out.push({ tag: "drop" });
    const carrying = num(tally.recovered_carrying);
    const damaged = num(tally.recovered_damaged) || num(tally.picked_up_damaged);
    const recovered = Math.max(
      num(tally.recovered) || num(tally.picked_up),
      carrying,
      damaged,
    );
    for (let i = 0; i < recovered; i++) {
      const rec = { tag: "pickup" };
      if (i < carrying) rec.carrying = true;
      if (i < damaged) rec.damaged = true;
      out.push(rec);
    }
    for (let i = 0; i < num(tally.mines); i++) out.push({ tag: "mine_lay" });
    for (let i = 0; i < num(tally.emps); i++) out.push({ tag: "emp_launch" });
    for (let i = 0; i < num(tally.chaff); i++) out.push({ tag: "chaff_flare" });
    // v0.9.15 — harvester field-state losses. ``abandoned_emped`` / the
    // survivor ``emped`` count tint the first N matching lines, mirroring
    // how carrying/damaged flag the first N pickups above.
    const abandonedEmped = num(tally.abandoned_emped);
    for (let i = 0; i < num(tally.abandoned); i++) {
      out.push({ tag: "abandoned", emped: i < abandonedEmped });
    }
    const damagedEmped = num(tally.emped);
    for (let i = 0; i < num(tally.damaged); i++) {
      out.push({ tag: "damaged", emped: i < damagedEmped });
    }
    return out;
  }

  /** Per-platform ORBITAL OBSERVATIONS — one weather-style box per
   *  observed seat, each holding the ordered list of that platform's
   *  witnessed launches / recoveries / ordnance for the night. Reads the
   *  server-side ``orbitalEventsByDay`` cache (fed by BOTH /status and
   *  /replay) so it renders live without depending on the replay-frame
   *  table. Public per RULEBOOK §3.15.x (every active platform shown,
   *  no coords). */
  function renderOrbitalObservations(day, seatFilter) {
    const panel = document.createElement("div");
    panel.className = "cc-report-orbital-panel";
    const head = document.createElement("div");
    head.className = "cc-report-section-head";
    head.textContent = "ORBITAL OBSERVATIONS \u00B7 launches / recoveries / ordnance";
    panel.appendChild(head);

    // v1.x — REDSIGN (RULEBOOK §4.11). Global + anonymous, so it sits
    // ABOVE the per-seat boxes as a plain red event line in the same
    // style as the per-seat orblift / probe rows. One line per pure-RED
    // seam DISCOVERED on this day, with the approximate location.
    const rsToday = (Array.isArray(lastRedSign) ? lastRedSign : []).filter(
      (r) => Number(r?.day) === Number(day),
    );
    for (const r of rsToday) {
      const ctr = Array.isArray(r?.center) ? r.center : [0, 0];
      const row = document.createElement("div");
      row.className =
        "cc-report-orbital-event cc-report-orbital-event--redsign";
      const g = document.createElement("span");
      g.className = "cc-report-orbital-glyph";
      g.textContent = "\u2B22"; // ⬢
      const t = document.createElement("span");
      t.className = "cc-report-orbital-label";
      t.textContent =
        `RED SIGN \u2014 pure RED seam near ` +
        `(~${Math.round(Number(ctr[0]))}, ~${Math.round(Number(ctr[1]))})`;
      row.append(g, t);
      panel.appendChild(row);
    }

    // Optional single-seat filter (station-panel hover cards pass the
    // moused-over seat so only that platform's box renders).
    const seats = seatFilter
      ? observedSeats().filter((s) => s === seatFilter)
      : observedSeats();
    if (!seats.length) {
      const empty = document.createElement("div");
      empty.className = "cc-report-empty dim";
      empty.textContent = "// orbital activity \u2014 waiting for info\u2026";
      panel.appendChild(empty);
      return panel;
    }

    // Pull the ordered per-seat event log for this day from the
    // session-blob-backed cache (resilient to the replay-frame table
    // not having loaded yet in live play).
    const dayEvents = orbitalEventsByDay[String(day)] || orbitalEventsByDay[day] || {};
    // v0.9.14 — resilient fallback. The ordered event log is only stamped
    // by builds at/after the event-log change, so a night that resolved
    // on an older server (or before a restart) carries only the COUNT
    // tally (orbital_activity_by_day). When a seat has no ordered events
    // for the day, synthesise the list from its counts so the box shows
    // real activity instead of a misleading "quiet platform".
    const dayActivity = orbitalActivityByDay[String(day)] || orbitalActivityByDay[day] || {};
    const eventsBySeat = {};
    for (const seat of seats) {
      let recs = Array.isArray(dayEvents[seat]) ? dayEvents[seat] : [];
      if (!recs.length && dayActivity[seat]) {
        recs = eventsFromActivityTally(dayActivity[seat]);
      }
      eventsBySeat[seat] = recs
        .map(orbitalEventForRecord)
        .filter(Boolean);
    }

    const boxes = document.createElement("div");
    boxes.className = "cc-report-orbital-boxes";
    for (const seat of seats) {
      const color = ownerColor(seat);
      const box = document.createElement("div");
      box.className = "cc-report-orbital-box";
      box.setAttribute("data-seat", seat);
      box.style.setProperty("--seat-color", color);

      const boxHead = document.createElement("div");
      boxHead.className = "cc-report-orbital-box-head";
      const dot = document.createElement("span");
      dot.className = "cc-report-seat-dot";
      dot.style.background = color;
      const lbl = document.createElement("span");
      lbl.className = "cc-report-seat-lbl";
      lbl.textContent = playerDisplayName(seat);
      lbl.style.color = color;
      boxHead.append(dot, lbl);
      box.appendChild(boxHead);

      const list = eventsBySeat[seat];
      if (!list.length) {
        const quiet = document.createElement("div");
        quiet.className = "cc-report-orbital-quiet dim";
        quiet.textContent = "\u00B7 quiet platform";
        box.appendChild(quiet);
      } else {
        const rows = document.createElement("div");
        rows.className = "cc-report-orbital-rows";
        list.forEach((ev) => {
          const row = document.createElement("div");
          row.className = "cc-report-orbital-event";
          const g = document.createElement("span");
          g.className = "cc-report-orbital-glyph";
          if (ev.glyphTone) {
            g.classList.add(`cc-orbital-tone-${ev.glyphTone}`);
          } else {
            g.style.color = color;
          }
          g.textContent = ev.glyph;
          const t2 = document.createElement("span");
          t2.className = "cc-report-orbital-label";
          const parts = Array.isArray(ev.parts)
            ? ev.parts
            : [{ text: String(ev.label || "") }];
          for (const p of parts) {
            const s = document.createElement("span");
            if (p.tone) s.className = `cc-orbital-tone-${p.tone}`;
            s.textContent = String(p.text || "");
            t2.appendChild(s);
          }
          row.append(g, t2);
          rows.appendChild(row);
        });
        box.appendChild(rows);
      }
      boxes.appendChild(box);
    }
    panel.appendChild(boxes);
    return panel;
  }

  /** SURFACE — the chronicle of witnessed surface events (orders,
   *  observed competitor moves, probe/weapon landings the viewer
   *  could see), each line tinted by the seat it belongs to. Fog-of-
   *  war: ``viewerMaySeeLogEntry`` drops opponents' private rationale,
   *  so OBS replay shows everything and a single-seat view shows only
   *  what that seat witnessed. */
  function renderSurfaceLog(day) {
    const panel = document.createElement("div");
    panel.className = "cc-report-surface";
    const head = document.createElement("div");
    head.className = "cc-report-section-head";
    head.textContent = `SURFACE \u00B7 witnessed events \u00B7 Nox ${day}`;
    panel.appendChild(head);

    const nightLog = logByDay[String(day)] || logByDay[day] || [];
    const chronicle = (Array.isArray(nightLog) ? nightLog : [])
      .filter((e) => e && typeof e === "object")
      .filter(viewerMaySeeLogEntry);

    const box = document.createElement("div");
    box.className = "cc-report-surface-log";
    if (!chronicle.length) {
      const dim = document.createElement("div");
      dim.className = "cc-report-surface-line dim";
      dim.textContent = "// no surface events witnessed this Nox";
      box.appendChild(dim);
      panel.appendChild(box);
      return panel;
    }
    for (const entry of chronicle) {
      const seat = surfaceLineSeat(entry);
      const line = document.createElement("div");
      line.className = entry.level === "error"
        ? "cc-report-surface-line cc-report-surface-line--err"
        : entry.level === "warn"
          ? "cc-report-surface-line cc-report-surface-line--warn"
          : "cc-report-surface-line";
      if (seat) {
        line.setAttribute("data-seat", seat);
        line.style.setProperty("--seat-color", ownerColor(seat));
      }
      line.textContent = String(entry.text || "");
      box.appendChild(line);
    }
    panel.appendChild(box);
    return panel;
  }

  /** Best-effort seat attribution for a surface log line: explicit
   *  ``data.seat`` first, then an agent-rationale ``(pN)`` prefix, then
   *  a loose ``pN`` token in the text. Returns null when unattributable
   *  (rendered in the neutral colour). */
  function surfaceLineSeat(entry) {
    if (entry && entry.data && /^p[1-4]$/.test(String(entry.data.seat || ""))) {
      return String(entry.data.seat);
    }
    return rationaleSeatOf(entry) || _orbitFlashGuessSeat(entry && entry.text);
  }

  /** Per-seat station-observation panel for ``phase`` ("pre"|"post").
   *  The viewer seat (self) shows EXACT readings; opponents show only
   *  fuzzy grade bands / count ranges. In OBS replay every seat is
   *  shown exact (omniscient cheat view). */
  function renderStationObsPanel(day, phase, headLabel, seatFilter) {
    const panel = document.createElement("div");
    panel.className = "cc-report-obs";
    const head = document.createElement("div");
    head.className = "cc-report-section-head";
    head.textContent = headLabel || "STATION OBSERVATIONS";
    panel.appendChild(head);
    const byPhase = stationObsByDay[String(day)] || {};
    const obs = byPhase[phase] || {};
    // Optional single-seat filter (station-panel hover cards pass the
    // moused-over seat so only that platform's card renders).
    const seats = seatFilter
      ? observedSeats().filter((s) => s === seatFilter)
      : observedSeats();
    if (!seats.length || !Object.keys(obs).length) {
      const empty = document.createElement("div");
      empty.className = "cc-report-empty dim";
      empty.textContent = "// station readings \u2014 waiting for info\u2026";
      panel.appendChild(empty);
      return panel;
    }
    const exactSeats = reportExactSeats();
    const cards = document.createElement("div");
    cards.className = "cc-report-obs-cards";
    for (const seat of seats) {
      const reading = obs[seat];
      if (!reading) continue;
      const exact = exactSeats.has(seat);
      cards.appendChild(buildStationObsCard(seat, reading, exact));
    }
    panel.appendChild(cards);
    return panel;
  }

  function buildStationObsCard(seat, reading, exact) {
    const card = document.createElement("div");
    card.className = "cc-report-obs-card";
    card.setAttribute("data-seat", seat);
    card.style.setProperty("--seat-color", ownerColor(seat));
    const head = document.createElement("div");
    head.className = "cc-report-obs-card-head";
    const dot = document.createElement("span");
    dot.className = "cc-report-seat-dot";
    dot.style.background = ownerColor(seat);
    const lbl = document.createElement("span");
    lbl.className = "cc-report-seat-lbl";
    lbl.textContent = playerDisplayName(seat);
    lbl.style.color = ownerColor(seat);
    const tag = document.createElement("span");
    tag.className = "cc-report-obs-card-tag dim";
    tag.textContent = exact ? "exact" : "estimate";
    head.append(dot, lbl, tag);
    card.appendChild(head);
    for (const row of formatStationObsRows(reading, exact)) {
      const r = document.createElement("div");
      r.className = "cc-report-obs-row";

      const top = document.createElement("div");
      top.className = "cc-report-obs-rowtop";
      const glyph = document.createElement("span");
      glyph.className = "cc-report-obs-glyph";
      glyph.textContent = row.glyph;
      glyph.style.color = row.color;
      const k = document.createElement("span");
      k.className = "cc-report-obs-key dim";
      k.textContent = row.key;
      const v = document.createElement("span");
      v.className = "cc-report-obs-val";
      v.textContent = row.val;
      top.append(glyph, k, v);

      const meter = document.createElement("div");
      meter.className = "cc-report-obs-meter";
      for (let i = 0; i < row.segments; i++) {
        const seg = document.createElement("span");
        seg.className = "cc-report-obs-seg";
        if (i < row.level) {
          seg.classList.add("is-on");
          seg.style.background = row.color;
        }
        meter.appendChild(seg);
      }

      r.append(top, meter);
      card.appendChild(r);
    }
    return card;
  }

  // v0.9.14 — station-obs meters. Each coarse grade maps to a discrete
  // fill level so the card can render a segmented bar gauge instead of
  // a bare word. Mirrors the backend bands in session.py.
  const _FULLNESS_LEVEL = { empty: 0, low: 1, half: 2, high: 3, full: 4 };
  const _PURITY_LEVEL = { none: 0, low: 1, medium: 2, high: 3 };
  const _GREEN_COUNT_LEVEL = { "0": 0, "1-3": 1, "4-7": 2, "8-12": 3, "13+": 4 };

  function _greenLevelFromCount(c) {
    c = Number(c) || 0;
    if (c <= 0) return 0;
    if (c <= 3) return 1;
    if (c <= 7) return 2;
    if (c <= 12) return 3;
    return 4;
  }

  /** Turn a station-obs reading dict into three meter rows: hold
   *  (material in vault), fissile (blue purity), and green squares
   *  (count). The toxic-green PURITY row is intentionally dropped —
   *  every green square is canonically 255 purity, so its purity grade
   *  carries no signal; only the square COUNT matters. ``exact`` appends
   *  the raw numbers the engine only reveals to self. */
  function formatStationObsRows(reading, exact) {
    const f = reading.fullness || {};
    const b = reading.blue || {};
    const g = reading.green || {};
    const fGrade = f.grade ?? "\u2014";
    const bGrade = b.grade ?? "\u2014";
    const gEst = g.estimate ?? "\u2014";
    return [
      {
        key: "hold",
        glyph: "\u25A6",            // ▦ — the vault hold
        color: "#c9d1d9",
        segments: 4,
        level: _FULLNESS_LEVEL[fGrade] ?? 0,
        val: exact && f.count != null
          ? `${fGrade} (${f.count}/${f.capacity ?? 25})`
          : String(fGrade),
      },
      {
        key: "fissile (blue)",
        glyph: "\u25C6",            // ◆ — fissile crystal
        color: "#58a6ff",
        segments: 3,
        level: _PURITY_LEVEL[bGrade] ?? 0,
        val: exact && b.total != null
          ? `${bGrade} (\u03A3${b.total}p)`
          : String(bGrade),
      },
      {
        key: "green squares",
        glyph: "\u25C6",            // ◆ — toxic-green parcel
        color: "#3fb950",
        segments: 4,
        level: exact && g.count != null
          ? _greenLevelFromCount(g.count)
          : (_GREEN_COUNT_LEVEL[gEst] ?? 0),
        val: exact && g.count != null
          ? `${g.count}`
          : `~ ${gEst}`,
      },
    ];
  }

  /** Per-player orbit action log for ``day`` — money spent, builds,
   *  refines, failed actions. One column per visible seat. */
  function renderPerPlayerOrbitLog(day) {
    const panel = document.createElement("div");
    panel.className = "cc-report-orbitlog";
    const head = document.createElement("div");
    head.className = "cc-report-section-head";
    head.textContent = "ORBIT ACTION LOG \u00B7 per player";
    panel.appendChild(head);
    const bucket = orbitLogByDay[String(day)] || orbitLogByDay[day] || [];
    const seats = reportVisibleSeats();
    const cols = document.createElement("div");
    cols.className = "cc-report-orbitlog-cols";
    for (const seat of seats) {
      const col = document.createElement("div");
      col.className = "cc-report-orbitlog-col";
      col.setAttribute("data-seat", seat);
      const colHead = document.createElement("div");
      colHead.className = "cc-report-orbitlog-head";
      colHead.textContent = playerTag(seat);
      colHead.style.color = ownerColor(seat);
      col.appendChild(colHead);
      const lines = Array.isArray(bucket)
        ? bucket.filter((e) => {
            if (!e || typeof e !== "object") return false;
            const hint = (e.data && e.data.seat) || _orbitFlashGuessSeat(e.text || "");
            return hint === seat;
          })
        : [];
      if (!lines.length) {
        const dim = document.createElement("div");
        dim.className = "cc-report-orbitlog-line dim";
        dim.textContent = "// no orbit actions";
        col.appendChild(dim);
      } else {
        for (const e of lines) {
          const ln = document.createElement("div");
          ln.className = e.level === "error"
            ? "cc-report-orbitlog-line cc-report-orbitlog-line--err"
            : "cc-report-orbitlog-line";
          // Strip the leading "[orbit] pN:" noise for compactness.
          ln.textContent = String(e.text || "")
            .replace(/^\[orbit\]\s*/, "")
            .replace(new RegExp(`^${seat}:\\s*`, "i"), "");
          col.appendChild(ln);
        }
      }
      cols.appendChild(col);
    }
    panel.appendChild(cols);
    return panel;
  }

  /** Seats whose readings the report should display. Live = self only
   *  (p1); replay = the perspective's active seats (single seat, or
   *  every seat in OBS). */
  function reportVisibleSeats() {
    if (mainMapSource === "replay") {
      return [...currentReplayActiveSeats()];
    }
    return [MY_SEAT];
  }

  /** Seats whose ORBITAL SILHOUETTE we can read — station observations
   *  and launch/recovery activity (counts, no coords) are picked up
   *  from orbit for EVERY active platform, not just our own. Self is
   *  shown EXACT (see ``reportExactSeats``); rivals are fuzzed. Both
   *  live and replay surface all active seats here. */
  function observedSeats() {
    const seats = _activeSeatsForView();
    return seats.includes(MY_SEAT)
      ? [MY_SEAT, ...seats.filter((s) => s !== MY_SEAT)]
      : seats;
  }

  /** Seats shown with EXACT readings (everyone else is fuzzed). Live =
   *  self (p1); replay OBS = all (omniscient); single-seat replay =
   *  that seat. */
  function reportExactSeats() {
    if (mainMapSource === "replay") {
      if (replayViewSeat === "obs" || replayViewSeat === "both") {
        return new Set(reportVisibleSeats());
      }
      return new Set([replayViewSeat]);
    }
    return new Set([MY_SEAT]);
  }

  /** Pick the "viewer" seat for the actions panel — replay-mode
   *  honors the perspective buttons, live mode is always P1. */
  function _orbitFlashViewerSeat() {
    if (mainMapSource === "replay") {
      const seats = currentReplayActiveSeats();
      if (seats.has(MY_SEAT)) return MY_SEAT;
      const first = seats.values().next().value;
      return first || "p1";
    }
    return MY_SEAT;
  }

  /** Pull this seat's relevant log entries for the given day.
   *  Filters for action-like entries (drops/picks/builds/refines/
   *  catapult/jettison) so the modal doesn't dump every chatter
   *  line. */
  function _orbitFlashActionRows(day, viewerSeat) {
    if (!day) return [];
    const bucket = logByDay[String(day)] || logByDay[day];
    if (!Array.isArray(bucket)) return [];
    const out = [];
    for (const entry of bucket) {
      if (!entry || typeof entry !== "object") continue;
      const txt = String(entry.text || "");
      // Seat tag may be in the text body ("[orbit] p1: ...") OR on
      // the structured ``data.seat`` field. Take whichever surfaces.
      const seatHint =
        (entry.data && entry.data.seat)
        || _orbitFlashGuessSeat(txt);
      if (seatHint && seatHint !== viewerSeat) continue;
      out.push({ level: entry.level || "info", text: txt });
    }
    return out;
  }

  function _orbitFlashGuessSeat(text) {
    // Detect a seat token (p1..p4) even when embedded in an entity name
    // such as "harvester_p2" or "probe_p3_4" — the char before "p" may
    // be an underscore, bracket, or boundary, but must NOT be a letter
    // or digit (so "p12" / "spring" never read as a seat). Returns the
    // FIRST seat mentioned: for a viewer's own action line
    // ("p1 dropped harvester_p1_2 …") that is the viewer; for a witnessed
    // rival surface event ("harvester_p2 harvested …") it is the rival,
    // so the fail-closed filter in ``_orbitFlashActionRows`` hides it.
    // Without this, rival harvester/probe moves (with exact coords) leak
    // into the "your actions" panel of the post-orbital briefing.
    const m = /(?:^|[^a-z0-9])p([1-4])(?![0-9])/i.exec(text || "");
    if (!m) return null;
    return `p${m[1]}`;
  }

  /** Render the catapult slot grid from the engine's ``slot_assignments``
   *  manifest. Each cell gets a per-seat edge variant + a mouseover
   *  tooltip via the existing ``cc-vault-tooltip`` host system.
   *
   *  v1.13 — the grid was a fixed 4×5 because 20 slots were what seats
   *  bid over, and a cell could be empty (nobody wanted it) or "failed"
   *  (outbid). Shipping is unconditional now: the manifest is exactly
   *  what flew, every cell is filled, and it can run past 20 on a night
   *  when both vaults empty. Rounded up to a whole row of five, with a
   *  20-cell resting size so an idle catapult still reads as one. */
  function _orbitFlashRenderCatGrid(slotAssignments) {
    const grid = document.createElement("div");
    grid.className = "cc-cat-grid";
    const SEAT_TO_TIER_MULT = window.__SOC_QUALITY_MULT__
      || { trace: 0.75, vein: 1.0, mass: 1.5, pure: 3.0 };
    const n = Array.isArray(slotAssignments) ? slotAssignments.length : 0;
    const cells = Math.max(20, Math.ceil(n / 5) * 5);
    for (let i = 0; i < cells; i++) {
      const a = slotAssignments[i] || {};
      const seat = a.seat || null;
      const cell = document.createElement("div");
      const state = a.shipped ? "shipped" : (a.disposition || "empty");
      cell.className =
        `cc-cat-slot ${seat ? `cc-cat-slot--${seat}` : ""}`.trim();
      cell.setAttribute("data-slot-state", state);
      cell.setAttribute("data-row", String(Math.floor(i / 5)));
      cell.setAttribute("data-slot", String(i));
      if (seat) cell.setAttribute("data-seat", seat);
      const purityNum = Number(a.effective_purity ?? 0);
      const tier = a.tier || (a.parcel ? "?" : "");
      const mult = a.tier_multiplier != null
        ? Number(a.tier_multiplier)
        : (tier ? Number(SEAT_TO_TIER_MULT[tier] || 1) : null);
      const score = a.score != null ? Math.round(Number(a.score)) : null;
      const ox = a?.parcel?.x ?? a?.parcel?.origin_x;
      const oy = a?.parcel?.y ?? a?.parcel?.origin_y;
      const sid = a?.parcel?.square_id || a?.parcel?.site_id || "";
      const rawPurity =
        a?.parcel?.purity_at_harvest
        ?? a?.parcel?.origin_purity
        ?? null;
      // v0.9.13 — the density glyph reads the parcel's TIER (raw harvest
      // purity), exactly like the vault hoard square, so a high-tier
      // parcel taxed down to a low effective purity still shows its real
      // block. Using effective_purity here meant a trace parcel taxed to
      // 0 fell through catTierGlyph to the solid ██ "pure" block.
      const glyphPurity = rawPurity != null ? Number(rawPurity) : purityNum;
      const glyph = a.shipped ? catTierGlyph(glyphPurity) : "\u00B7";
      // v1.13 — the top-right corner used to carry the credit bid that
      // won the slot. There is no bid; it now carries the score the
      // parcel actually banked, which is the number a player is
      // reading the grid for.
      cell.innerHTML =
        `<span class="cc-cat-slot-label">${a.shipped ? tier : ""}</span>` +
        (a.shipped && score != null
          ? `<span class="cc-cat-slot-bid">+${score}</span>`
          : "") +
        `<span class="cc-cat-slot-glyph">${glyph}</span>` +
        (a.shipped
          ? `<span class="cc-cat-slot-purity">${purityNum}</span>`
          : "");
      if (seat && a.shipped) {
        cell.setAttribute("data-tooltip-kind", "cat-slot");
        cell.setAttribute("data-tooltip-seat", seat);
        cell.setAttribute("data-tooltip-sid", String(sid));
        cell.setAttribute("data-tooltip-ox", String(ox ?? ""));
        cell.setAttribute("data-tooltip-oy", String(oy ?? ""));
        cell.setAttribute("data-tooltip-tier", String(tier));
        cell.setAttribute("data-tooltip-raw", String(rawPurity ?? ""));
        cell.setAttribute("data-tooltip-eff", String(purityNum));
        cell.setAttribute("data-tooltip-mult", String(mult ?? ""));
        cell.setAttribute("data-tooltip-score", String(score ?? ""));
      } else {
        cell.setAttribute("data-tooltip-kind", "cat-slot-empty");
      }
      grid.appendChild(cell);
    }
    bindCatSlotTooltip(grid);
    return grid;
  }

  function _orbitFlashRenderLegend(slotAssignments, allSeats) {
    const legend = document.createElement("div");
    legend.className = "cc-orbit-flash-grid-legend";
    const present = new Set(
      slotAssignments.map((s) => s && s.seat).filter(Boolean),
    );
    for (const seat of allSeats) {
      if (!present.has(seat)) continue;
      const chip = document.createElement("span");
      chip.className = "cc-orbit-flash-grid-legend-chip";
      chip.style.setProperty("--seat-color", ownerColor(seat));
      const swatch = document.createElement("span");
      swatch.className = "cc-orbit-flash-grid-legend-swatch";
      chip.appendChild(swatch);
      const lbl = document.createElement("span");
      lbl.textContent = playerTag(seat);
      chip.appendChild(lbl);
      legend.appendChild(chip);
    }
    return legend;
  }

  /** v1.13 — GREEN disposal section for the post-orbital briefing.
   *
   *  Was a 12-slot shared lattice with a diminishing RED-fuel cost ramp
   *  that houses drafted for. Disposal is now automatic and flat-priced,
   *  so there is no lane to draw and no scarcity to show: this renders
   *  the manifest of what each house dumped and what it cost them.
   *  Still always rendered, even on a night nobody held green, because
   *  its absence is itself the information (a clean vault). */
  function _orbitFlashRenderGreenSection(jet, allSeats) {
    const section = document.createElement("div");
    section.className = "cc-orbit-flash-green";
    const assignments = Array.isArray(jet?.slot_assignments)
      ? jet.slot_assignments
      : [];
    const head = document.createElement("div");
    head.className = "cc-orbit-flash-section-head";
    head.textContent = assignments.length
      ? `SOLAR CATAPULT \u00B7 ${assignments.length} dumped`
      : "SOLAR CATAPULT \u00B7 nothing held";
    section.appendChild(head);
    // Always draw the lane, even on a night nobody held green — an idle
    // catapult is information too, and it keeps the briefing's shape
    // stable between days.
    section.appendChild(_orbitFlashRenderGreenGrid(assignments));
    section.appendChild(_orbitFlashRenderLegend(assignments, allSeats));

    // Per-seat totals for ALL seats, mirroring the RED row.
    const totals = document.createElement("div");
    totals.className = "cc-orbit-flash-totals";
    for (const seat of allSeats) {
      const sb = jet?.seats?.[seat] || {};
      const row = document.createElement("div");
      row.className = "cc-orbit-flash-total-row";
      row.setAttribute("data-seat", seat);
      const tag = document.createElement("span");
      tag.textContent = playerTag(seat);
      tag.style.color = ownerColor(seat);
      const val = document.createElement("span");
      const dumped = Number(sb.awarded || 0);
      const penalty = Number(sb.penalty || 0);
      val.textContent = dumped
        ? `${dumped} dumped \u00B7 \u2212${penalty}`
        : "clean";
      row.append(tag, val);
      totals.appendChild(row);
    }
    section.appendChild(totals);
    return section;
  }

  /** One cell per disposed parcel, padded out to a 12-cell resting lane
   *  (see ``_orbitFlashRenderCatGrid`` for why the size floats). */
  function _orbitFlashRenderGreenGrid(slotAssignments) {
    const grid = document.createElement("div");
    grid.className = "cc-cat-grid cc-cat-grid--green";
    const rows = Array.isArray(slotAssignments) ? slotAssignments : [];
    const cells = Math.max(12, Math.ceil(rows.length / 5) * 5);
    for (let i = 0; i < cells; i++) {
      const a = rows[i] || null;
      const seat = a?.seat || null;
      const penalty = Number(a?.penalty ?? 0);
      const cell = document.createElement("div");
      if (!a) {
        cell.className = "cc-cat-slot";
        cell.setAttribute("data-slot", String(i));
        cell.setAttribute("data-slot-state", "empty");
        cell.innerHTML =
          `<span class="cc-cat-slot-label">${i + 1}</span>` +
          `<span class="cc-cat-slot-glyph dim">\u00B7</span>`;
        cell.setAttribute("data-tooltip-kind", "green-slot-empty");
        grid.appendChild(cell);
        continue;
      }
      // v0.9.13 — GREEN is unsealed + public, so a dumped parcel shows as
      // a plain green block (██) exactly like the vault's green hold
      // square — no sealed/hazard glyph. The border is the OWNING seat's
      // colour (cc-cat-slot--pN); the green fill comes from the
      // grid-scoped ``.cc-cat-grid--green`` shipped rule.
      cell.className =
        `cc-cat-slot ${seat ? `cc-cat-slot--${seat}` : ""}`.trim();
      cell.setAttribute("data-slot", String(i));
      cell.setAttribute("data-slot-state", "shipped");
      if (seat) cell.setAttribute("data-seat", seat);
      cell.innerHTML =
        `<span class="cc-cat-slot-label">${i + 1}</span>` +
        `<span class="cc-cat-slot-glyph">\u2588\u2588</span>` +
        `<span class="cc-cat-slot-purity">\u2212${penalty}</span>`;
      const sid = a?.parcel?.square_id || a?.parcel?.site_id || "";
      cell.setAttribute("data-tooltip-kind", "green-slot");
      cell.setAttribute("data-tooltip-seat", String(seat || ""));
      cell.setAttribute("data-tooltip-sid", String(sid));
      cell.setAttribute("data-tooltip-cost", String(penalty));
      grid.appendChild(cell);
    }
    bindCatSlotTooltip(grid);
    return grid;
  }

  /** Attach a vault-style tooltip to every cc-cat-slot inside ``host``.
   *  Re-uses ``ensureStorageTooltip`` + ``positionStorageTooltip`` so
   *  the look + edge-clamping behaviour matches the VAULT panel's
   *  parcel mouseover; we only swap the row builder for the
   *  catapult-specific fields. */
  function bindCatSlotTooltip(host) {
    const tip = ensureStorageTooltip();
    host.addEventListener("mouseover", (ev) => {
      const target = /** @type {HTMLElement|null} */ (ev.target);
      const slot = target ? target.closest(".cc-cat-slot") : null;
      if (!slot) return;
      fillCatSlotTooltip(tip, /** @type {HTMLElement} */ (slot));
      tip.hidden = false;
      positionStorageTooltip(tip, ev.clientX, ev.clientY);
    });
    host.addEventListener("mousemove", (ev) => {
      if (tip.hidden) return;
      positionStorageTooltip(tip, ev.clientX, ev.clientY);
    });
    host.addEventListener("mouseout", (ev) => {
      const target = /** @type {HTMLElement|null} */ (ev.target);
      const fromSlot = target ? target.closest(".cc-cat-slot") : null;
      const next = /** @type {HTMLElement|null} */ (ev.relatedTarget);
      const toSlot = next && next.closest ? next.closest(".cc-cat-slot") : null;
      if (fromSlot && toSlot === fromSlot) return;
      tip.hidden = true;
    });
    host.addEventListener("mouseleave", () => {
      tip.hidden = true;
    });
  }

  function fillCatSlotTooltip(tip, slot) {
    const kind = slot.getAttribute("data-tooltip-kind") || "cat-slot-empty";
    const seat = slot.getAttribute("data-tooltip-seat") || "";
    const rows = [];
    if (kind === "cat-slot") {
      const sid = slot.getAttribute("data-tooltip-sid") || "";
      const ox = slot.getAttribute("data-tooltip-ox") || "?";
      const oy = slot.getAttribute("data-tooltip-oy") || "?";
      const tier = slot.getAttribute("data-tooltip-tier") || "";
      const raw = slot.getAttribute("data-tooltip-raw") || "";
      const eff = slot.getAttribute("data-tooltip-eff") || "";
      const mult = slot.getAttribute("data-tooltip-mult") || "";
      const score = slot.getAttribute("data-tooltip-score") || "";
      rows.push(
        `<div class="cc-vault-tooltip-row cc-vault-tooltip-row--coord">${esc(
          playerTag(seat),
        )} \u00B7 SHIPPED</div>`,
        `<div class="cc-vault-tooltip-row cc-vault-tooltip-row--hash">${esc(sid)}</div>`,
        `<div class="cc-vault-tooltip-row cc-vault-tooltip-row--meta">origin (${esc(ox)},${esc(oy)})</div>`,
        `<div class="cc-vault-tooltip-row cc-vault-tooltip-row--meta">tier ${esc(tier)} \u00B7 purity ${esc(eff)}${raw && raw !== eff ? ` (raw ${esc(raw)})` : ""}</div>`,
        `<div class="cc-vault-tooltip-row cc-vault-tooltip-row--meta">${esc(eff)} \u00D7 ${esc(mult)} = score ${esc(score)}</div>`,
      );
    } else if (kind === "green-slot") {
      const sid = slot.getAttribute("data-tooltip-sid") || "";
      const cost = slot.getAttribute("data-tooltip-cost") || "";
      rows.push(
        `<div class="cc-vault-tooltip-row cc-vault-tooltip-row--coord">${esc(
          playerTag(seat),
        )} \u00B7 GREEN DUMPED</div>`,
        `<div class="cc-vault-tooltip-row cc-vault-tooltip-row--hash">${esc(sid)}</div>`,
        `<div class="cc-vault-tooltip-row cc-vault-tooltip-row--meta">\u2212${esc(cost)} score \u00B7 automatic, no fuel</div>`,
      );
    } else {
      rows.push(
        `<div class="cc-vault-tooltip-row cc-vault-tooltip-row--meta">empty slot</div>`,
      );
    }
    tip.innerHTML = rows.join("");
  }

  /** v0.9.1 — Format the public inventory summary for the catapult
   *  modal. Returns the empty-label string when ``count`` is 0 so
   *  the renderer can show "x catapult empty" without branching. */
  function formatPublicInventory(inv, emptyLabel) {
    if (!inv || !inv.count) {
      return `// ${emptyLabel || "no shipments"}`;
    }
    const t = inv.tier_counts || {};
    const c = inv.color_counts || {};
    const tiers = [
      t.trace ? `trace ${t.trace}` : null,
      t.vein ? `vein ${t.vein}` : null,
      t.mass ? `mass ${t.mass}` : null,
      t.pure ? `pure ${t.pure}` : null,
    ].filter(Boolean).join(" \u00B7 ");
    const colors = [
      c.red ? `R${c.red}` : null,
      c.green ? `G${c.green}` : null,
      c.blue ? `B${c.blue}` : null,
    ].filter(Boolean).join("/");
    return (
      `${inv.count} parcel${inv.count === 1 ? "" : "s"} \u00B7 ` +
      `\u03A3${inv.total_purity}p` +
      (tiers ? ` \u00B7 ${tiers}` : "") +
      (colors ? ` \u00B7 ${colors}` : "")
    );
  }

  /** Render a single seat's contribution inside a catapult section. */
  function renderOrbitFlashSeat(seatBox, sectionKey, seatBlob, seat) {
    const addLine = (text, dim) => {
      const ln = document.createElement("div");
      ln.className = dim
        ? "cc-orbit-flash-seat-line cc-orbit-flash-seat-line--dim"
        : "cc-orbit-flash-seat-line";
      ln.textContent = text;
      seatBox.appendChild(ln);
    };

    if (!seatBlob || seatBlob.submitted === false) {
      addLine("// no submission", true);
      return;
    }
    // v0.9.1 — public inventory summary FIRST: counts + Σpurity +
    // tier breakdown. This is what the agent + the watcher both
    // need to learn about the OTHER seat's shipment without seeing
    // the parcel provenance. Empty inventory renders nothing here
    // (the seat may still have a useful "awarded 0 slots" line
    // below).
    const inv = seatBlob.inventory;
    if (inv && inv.count > 0) {
      addLine(formatPublicInventory(inv));
    }
    const awarded = seatBlob.awarded ?? 0;
    if (sectionKey === "catapult") {
      // v0.9.6 catapult per-seat readout (RULEBOOK §4.4).
      const wanted = seatBlob.wanted ?? awarded;
      const failed = seatBlob.failed_slots ?? 0;
      addLine(`awarded ${awarded}/${wanted} slot(s)`);
      if (failed > 0) addLine(`${failed} slot(s) in failed row(s)`, true);
      if (seatBlob.fuel_per_slot != null) {
        addLine(`fps bid: ${seatBlob.fuel_per_slot}`, true);
      }
      if (seatBlob.fuel_burned != null) {
        const due = seatBlob.fuel_total_due ?? seatBlob.fuel_burned;
        addLine(`fuel burned: ${seatBlob.fuel_burned}/${due}p`, true);
      }
      if (seatBlob.cannibalised_per_parcel) {
        addLine(
          `cannibalised: -${seatBlob.cannibalised_per_parcel}p/parcel`,
          true,
        );
      }
      if (seatBlob.jettisoned_overflow) {
        addLine(
          `overflow lost: ${seatBlob.jettisoned_overflow} parcel(s)`,
          true,
        );
      }
      if (seatBlob.dropped) addLine(`dropped: ${seatBlob.dropped}`, true);
    } else if (sectionKey === "jettison") {
      addLine(`jettisoned ${awarded} parcel(s)`);
      if (seatBlob.price_per_parcel != null) {
        addLine(`@ ${seatBlob.price_per_parcel}p/parcel`, true);
      }
      if (seatBlob.fuel_burned != null) {
        addLine(`fuel burned: ${seatBlob.fuel_burned}p`, true);
      }
    }

    // Parcels list. ``shipped_parcels`` / ``jettisoned_parcels`` are
    // emitted optionally — older sessions don't have them. When they
    // ARE present we render owner-bordered chips with vault-style
    // tooltips so the user can hover for full provenance.
    const parcels = Array.isArray(seatBlob.shipped_parcels)
      ? seatBlob.shipped_parcels
      : Array.isArray(seatBlob.jettisoned_parcels)
        ? seatBlob.jettisoned_parcels
        : Array.isArray(seatBlob.parcels)
          ? seatBlob.parcels
          : [];
    if (parcels.length) {
      const grid = document.createElement("div");
      grid.className = "cc-orbit-flash-parcels";
      for (const p of parcels) {
        grid.appendChild(makeOrbitParcelChip(p, seat));
      }
      seatBox.appendChild(grid);
    }
  }

  function makeOrbitParcelChip(parcel, seat) {
    const el = document.createElement("span");
    el.className = "cc-orbit-flash-parcel";
    const tile = Number(parcel?.tile_at_harvest);
    el.dataset.tile = tile === 1 ? "green" : tile === 2 ? "red" : "neutral";
    el.style.color = ownerColor(seat);
    const purity = Number(
      parcel?.origin_purity ?? parcel?.purity_at_harvest ?? parcel?.purity ?? 0,
    );
    el.textContent = String(purity);
    const ox = parcel?.origin_x;
    const oy = parcel?.origin_y;
    const tier = parcel?.tier ? ` · ${parcel.tier}` : "";
    el.title =
      `parcel${parcel?.parcel_id ? " " + parcel.parcel_id : ""}\n` +
      `seat: ${playerDisplayName(seat)}\n` +
      `purity: ${purity}${tier}\n` +
      (ox != null && oy != null ? `origin: (${ox}, ${oy})\n` : "") +
      (parcel?.harvest_day != null ? `harvest day: ${parcel.harvest_day}` : "");
    return el;
  }

  // v0.9.1 — LOG tab phase filter chips (ALL / NIGHT / ORBIT).
  document.querySelectorAll("[data-log-filter]").forEach((chip) => {
    chip.addEventListener("click", () => {
      const filter = chip.getAttribute("data-log-filter") || "all";
      replayFeedFilter = filter;
      document.querySelectorAll("[data-log-filter]").forEach((c) => {
        c.classList.toggle(
          "cc-log-filter-chip--active",
          c === chip,
        );
      });
      renderReplayFeedTimeline();
    });
  });

  reportCloseBtn?.addEventListener("click", () => closeReport());
  reportBackdrop?.addEventListener("click", () => closeReport());
  // Segmented header toggle — flip between RECAP and BRIEFING for the
  // same context day without leaving the report shell.
  reportTabRecapBtn?.addEventListener("click", () => {
    reportKind = "recap";
    reportDay = contextDayForReport("recap");
    syncReportTabs();
    renderReportBody();
  });
  reportTabBriefingBtn?.addEventListener("click", () => {
    reportKind = "briefing";
    reportDay = contextDayForReport("briefing");
    syncReportTabs();
    renderReportBody();
  });
  // Replay-strip manual buttons — always open the correct report for
  // the current context day (replay cursor day, or live session day).
  replayRecapBtn?.addEventListener("click", () => {
    openReport("recap", contextDayForReport("recap"));
  });
  replayBriefingBtn?.addEventListener("click", () => {
    openReport("briefing", contextDayForReport("briefing"));
  });

  // v0.9.9 — orbit summary flash duration slider. Persists to
  // localStorage so a tweak survives a hard reload.
  const ORBIT_FLASH_LS_KEY = "soc.replay.orbitFlashSeconds";
  const orbitFlashSlider = /** @type {HTMLInputElement|null} */ (
    document.getElementById("replay-orbit-flash-secs")
  );
  const orbitFlashSliderVal = document.getElementById(
    "replay-orbit-flash-secs-val",
  );
  try {
    const raw = window.localStorage.getItem(ORBIT_FLASH_LS_KEY);
    if (raw != null) {
      const v = Number.parseFloat(raw);
      if (Number.isFinite(v)) {
        orbitFlashSeconds = Math.max(0.5, Math.min(5, v));
      }
    }
  } catch (_e) { /* localStorage may be unavailable */ }
  if (orbitFlashSlider) {
    orbitFlashSlider.value = String(orbitFlashSeconds);
  }
  if (orbitFlashSliderVal) {
    orbitFlashSliderVal.textContent = `${orbitFlashSeconds.toFixed(1)}s`;
  }
  orbitFlashSlider?.addEventListener("input", () => {
    const v = Number.parseFloat(orbitFlashSlider.value);
    if (!Number.isFinite(v)) return;
    orbitFlashSeconds = Math.max(0.5, Math.min(5, v));
    if (orbitFlashSliderVal) {
      orbitFlashSliderVal.textContent = `${orbitFlashSeconds.toFixed(1)}s`;
    }
    try {
      window.localStorage.setItem(
        ORBIT_FLASH_LS_KEY,
        String(orbitFlashSeconds),
      );
    } catch (_e) { /* ignore */ }
  });

  /** v0.9.11 — apply a change to the "show orbital summaries as
   *  pop-ups" setting: rebuild the replay ticks so the synthetic
   *  recap/briefing ticks (and their timeline pips) appear or vanish,
   *  preserving the scrub cursor's day as best-effort. */
  function applyAutoPopSetting() {
    renderReplayDayTicks();
    const prevDay = (() => {
      const tk = replayTicks[replayTickIdx];
      if (!tk) return null;
      if (tk.slot === "dawn" || tk.slot === "dusk") {
        return Number(tk.day) || null;
      }
      const fr = nightReplayFrames[tk.lastFrameIdx];
      return fr ? Number(fr.day) || null : null;
    })();
    buildReplayTicks(nightReplayFrames);
    if (prevDay != null && replayTicks.length) {
      replayTickIdx = Math.min(
        findFirstTickOfDay(prevDay),
        replayTicks.length - 1,
      );
    } else if (replayTickIdx >= replayTicks.length) {
      replayTickIdx = Math.max(0, replayTicks.length - 1);
    }
    renderReplayDayTicks();
    syncReplayRowOnly();
    if (!orbitFlashEnabled) {
      closeReport();
      orbitFlashLastDay = 0;
    }
  }

  function findFirstTickOfDay(day) {
    for (let i = 0; i < replayTicks.length; i += 1) {
      const t = replayTicks[i];
      const f = nightReplayFrames[t.lastFrameIdx];
      if (f && Number(f.day) === Number(day)) return i;
    }
    return 0;
  }

  function currentReplayDay() {
    if (!replayTicks.length) return 0;
    const tick = replayTicks[replayTickIdx];
    if (!tick) return 0;
    const frame = nightReplayFrames[tick.lastFrameIdx];
    if (frame && Number(frame.day)) return Number(frame.day);
    // Synthetic report ticks (empty frames) carry their own day.
    return Number(tick.day) || 0;
  }

  function uniqueReplayDays() {
    if (!replayDayIndex.length) {
      const seen = new Set();
      for (const f of nightReplayFrames) {
        if (f && f.day != null) seen.add(Number(f.day));
      }
      return [...seen].sort((a, b) => a - b);
    }
    return replayDayIndex.map((r) => Number(r.day)).sort((a, b) => a - b);
  }

  function jumpReplayByDay(direction) {
    if (!replayTicks.length) return;
    const days = uniqueReplayDays();
    if (!days.length) return;
    const here = currentReplayDay();
    const idx = days.indexOf(here);
    let targetDay;
    if (direction > 0) {
      targetDay = idx === -1 ? days[0] : days[Math.min(days.length - 1, idx + 1)];
    } else {
      targetDay = idx === -1 ? days[0] : days[Math.max(0, idx - 1)];
    }
    replayTickIdx = findFirstTickOfDay(targetDay);
    paintReplayFrameOntoMain("jump");
  }

  function renderReplayDayTicks() {
    if (!replayDayTicks) return;
    replayDayTicks.innerHTML = "";
    const n = replayTicks.length;
    if (n < 2) return;
    const ticks = [];
    const seenDayStart = new Map();
    let lastDay = null;
    for (let i = 0; i < n; i += 1) {
      const t = replayTicks[i];
      // v0.9.9 — synthetic ticks (orbit_summary) carry their own
      // ``day`` field and have an empty frames array. Fall back to
      // the real frame's day for normal ticks but trust the
      // synthetic-tick stamp first so trailing orbit ticks (which
      // sit at frames.length and would otherwise read NaN from
      // out-of-bounds lookups) get labelled correctly.
      const synthDay = Number(t?.day);
      const f = nightReplayFrames[t.lastFrameIdx];
      const frameDay = Number(f?.day);
      const day = Number.isFinite(synthDay) && synthDay > 0
        ? synthDay
        : frameDay;
      if (
        Number.isFinite(day)
        && lastDay !== null
        && day !== lastDay
      ) {
        ticks.push({ idx: i, day });
      }
      if (Number.isFinite(day) && !seenDayStart.has(day)) {
        seenDayStart.set(day, i);
      }
      if (Number.isFinite(day)) lastDay = day;
    }
    for (const tick of ticks) {
      const pct = (tick.idx / (n - 1)) * 100;
      const el = document.createElement("span");
      el.className = "cc-replay-day-tick";
      el.style.left = `${pct.toFixed(2)}%`;
      el.title = `Day ${tick.day} begins here`;
      el.textContent = `D${tick.day}`;
      replayDayTicks.appendChild(el);
    }

    // v1.2 — one marker per DAWN / DUSK slot. These are ALWAYS rendered
    // (structural, not gated by the auto-pop setting) so the timeline
    // reads dawn↔dusk uniformly. A direct click JUMPS to the slot
    // (snaps the map to full day/night — no wash) and opens the matching
    // orbit report when there's one (DUSK on night 1 is an empty button).
    for (let i = 0; i < n; i += 1) {
      const t = replayTicks[i];
      if (!t || (t.slot !== "dawn" && t.slot !== "dusk")) continue;
      const day = Number(t.day || 0) || 0;
      if (!day) continue;
      const isDawn = t.slot === "dawn";
      const kind = isDawn ? "recap" : "briefing";
      const hasContent = isDawn ? dayHasRecap(day) : dayHasBriefing(day);
      const pct = (i / (n - 1)) * 100;
      const pip = document.createElement("button");
      pip.type = "button";
      pip.className = isDawn
        ? "cc-replay-orbit-pip cc-replay-orbit-pip--dawn"
        : "cc-replay-orbit-pip cc-replay-orbit-pip--dusk";
      pip.style.left = `${pct.toFixed(2)}%`;
      pip.title = isDawn
        ? `Nox ${day} — AURORA${hasContent ? " · pre-orbital recap (click to view)" : ""}`
        : `Nox ${day} — VESPERA${hasContent ? " · post-orbital briefing (click to view)" : ""}`;
      pip.setAttribute("aria-label", `Nox ${day} ${isDawn ? "Aurora" : "Vespera"}`);
      pip.textContent = isDawn ? "\u2600" : "\u263E"; // ☀ / ☾
      pip.addEventListener("click", (ev) => {
        ev.stopPropagation();
        stopReplayPlayback();
        replayTickIdx = i;
        paintReplayFrameOntoMain("jump"); // snap tint, no wash
        if (orbitFlashEnabled && hasContent) {
          orbitFlashLastDay = `${kind}:${day}`;
          openReport(kind, day);
        }
      });
      replayDayTicks.appendChild(pip);
    }

    // v1.0 — a single results pip pinned to the end of a COMPLETE
    // season's timeline. Click jumps to the final tick and opens the
    // end-of-season results screen.
    if (endgameMeta.replayComplete && mainMapSource === "replay") {
      const pip = document.createElement("button");
      pip.type = "button";
      pip.className = "cc-replay-results-pip";
      pip.style.left = "100%";
      pip.title = "Season results (click to view)";
      pip.setAttribute("aria-label", "Season results");
      pip.textContent = "\u2691"; // ⚑ flag
      pip.addEventListener("click", (ev) => {
        ev.stopPropagation();
        replayTickIdx = n - 1;
        syncReplayScrubPosition();
        void openEndGameModal(false);
      });
      replayDayTicks.appendChild(pip);
    }
  }

  /** Best-effort day extraction for a log entry.
   *
   *  v0.9.8 — the engine now stamps every log entry with ``day`` at
   *  write time (see ``session.log_info``), so the structured field
   *  is the primary signal. Legacy sessions (whose blobs predate
   *  v0.9.8) only carry the day inline in the text — we sniff out
   *  the ``day N:`` / ``[orbit] day N:`` prefixes as a fallback so
   *  rolling forward into a freshly-resumed live session doesn't
   *  blank the LOG until the next TRANSMIT. */
  function _logEntryDay(entry) {
    if (entry && typeof entry === "object") {
      const d = Number(entry.day);
      if (Number.isFinite(d) && d > 0) return d;
    }
    const text = typeof entry === "string"
      ? entry
      : String(entry?.text || "");
    const m = text.match(/(?:^|\W)day\s+(\d+)\b/i);
    if (m) {
      const d = Number(m[1]);
      if (Number.isFinite(d) && d > 0) return d;
    }
    return null;
  }

  /**
   * Render the orchestrator log into the LOG drawer. Each entry is a
   * structured ``{level, text, day}`` object (`info` or `error`).
   * Errors are painted yellow and prefixed with ``[!]`` so they
   * stand out next to the attempted action. Falls back gracefully
   * if the server still emits the legacy plain-string log.
   *
   * v0.9.8 — filter to ``focusDay`` (the live ``sess.day`` in live
   * mode, the scrub cursor day in replay mode). With the batched
   * bot fan-out a single TRANSMIT can append 30+ lines spanning
   * 2-3 days; without the filter the LOG looks like an incoherent
   * mishmash from day 1 stacked on top of day 2 orbit chatter,
   * which is what the v0.9.8 regression actually was.
   *
   * @param {any} tail
   * @param {number|null} focusDay
   */
  function renderOrchLog(tail, focusDay) {
    if (!orchLogEl) return;
    if (!Array.isArray(tail) || !tail.length) {
      orchLogEl.textContent = "# quiet";
      return;
    }
    const focus = Number.isFinite(Number(focusDay)) && Number(focusDay) > 0
      ? Number(focusDay)
      : null;
    // Fog-of-war: never surface another seat's private agent-rationale
    // line in the shared LOG (live = self only; replay honours the
    // chosen perspective / OBS omniscience).
    let filtered = tail.filter(viewerMaySeeLogEntry);
    if (focus !== null) {
      filtered = filtered.filter((entry) => {
        const d = _logEntryDay(entry);
        // Entries without a day attribution stay visible — they're
        // legacy lines or one-off boot chatter that doesn't fit a day.
        return d === null || d === focus;
      });
      if (!filtered.length) {
        orchLogEl.innerHTML =
          `<div class="log-line"># quiet · day ${focus}</div>`;
        return;
      }
    }
    if (!filtered.length) {
      orchLogEl.textContent = "# quiet";
      return;
    }
    const parts = filtered.map((entry) => {
      if (typeof entry === "string") {
        return `<div class="log-line">${esc(entry)}</div>`;
      }
      if (entry && typeof entry === "object") {
        const level = String(entry.level || "info");
        const text = String(entry.text || "");
        const cls = level === "error" ? "log-line log-line--error" : "log-line";
        const prefix = level === "error" ? "[!] " : "";
        return `<div class="${cls}">${esc(prefix + text)}</div>`;
      }
      return `<div class="log-line">${esc(String(entry))}</div>`;
    });
    orchLogEl.innerHTML = parts.join("");
  }

  async function refreshStatus() {
    if (!sessionId) {
      phaseLine.textContent = "# idle — start a session";
      orchLogEl.textContent = "# quiet — start NEW GAME";
      replayWindowCount = 0;
      updateCcTabMeta();
      stopReplayPlayback();
      stopAgentThinking();
      stopAgentPoll();
      // v1.0 — drop any end-of-season screen state from the prior game.
      closeEndGameModal();
      updateEndgameReopen(false);
      updateFinalOrbitUi(false);
      endgameMeta.summary = null;
      endgameMeta.summaryFor = null;
      endgameMeta.liveAutoShown = false;
      endgameMeta.liveWasComplete = false;
      endgameMeta.replayAutoShown = false;
      endgameMeta.replayComplete = false;
      mainMapSource = "live";
      lastLiveMapPayload = null;
      // v0.7.5 — reset every replay-strip / scoreboard / agent
      // surface so they don't carry stale state into the next game.
      livePhase = null;
      lastLiveInventory = null;
      lastShownOrbitDay = 0;
      lastShownRecapDay = 0;
      for (const seat of Object.keys(agentLogByDay)) {
        agentLogByDay[seat]?.clear();
      }
      agentLogFetched.clear();
      // v0.9.18 — wipe seat identity (names/tags/colours) so the next
      // session starts from the canonical defaults instead of inheriting
      // the previous game's profiles.
      clearPlayerMeta();
      updateLiveButtonPulse();
      updateSeatTabVisibility();
      updateNowPlayingStrip();
      renderScoreboard();
      renderHudScoreboard(null, null);
      renderAgentFeed();
      return;
    }
    try {
      const res = await fetch(`/api/game/${sessionId}/status`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const st = await res.json();
      
      // v0.9.18 — populate player metadata (names, tags, colors) from status
      // (also pushes colours into the --seat-pN CSS vars for stylesheet rules)
      setPlayerMeta(st.player_profiles);
      
      const night =
        st.phase === "planning" ?
          st.pending?.[MY_SEAT] ?
            (waitingForLabel(st) || "locking…")
          : "pick orders → TRANSMIT · rival auto-idle"
        : String(st.phase);
      phaseLine.textContent = `# day ${st.day} · ${night}`;
      // v0.9.12 — surface the cross-browser "waiting for: pN" strip from
      // the per-seat pending map (only meaningful in a multi-human game).
      renderWaitingStrip(st);
      // v1.11 — "agent is thinking · Ns" pill for slow (Cortex/harness)
      // seats that the server pre-fires while the human deliberates. Start
      // the lightweight solo poller so the pill keeps ticking between the
      // (infrequent) solo status refreshes.
      renderAgentThinking(st);
      _slowBotGame = _hasSlowBotSeat(st.agents);
      if (!WATCH_MODE && _slowBotGame) startAgentPoll();
      else stopAgentPoll();
      replayWindowCount = Number(st.replay_windows || 0);
      if (Number.isFinite(Number(st.max_queue_len))) {
        // v0.9.9 — the engine now treats the queue as the slot budget
        // itself (illegal moves are struck-through, not skipped) so
        // we clamp the client cap to MAX_MOVES rather than the
        // historical 100-deep parse window. Older servers still
        // advertise 100; pin the client cap to ``MAX_MOVES`` so the
        // composer stays honest.
        maxQueueLen = Math.min(MAX_MOVES, Math.max(1, Number(st.max_queue_len)));
      }
      // v0.7.5 — snapshot the live phase so the LIVE-button pulse +
      // seat-tab visibility can react. Also pull any rationale-tagged
      // entries out of the log tail into the AGENT bucket.
      livePhase = st.phase || null;
      // v1.1 — persistent board daylight tracks the phase (PLANNING =
      // night surface orders, ORBIT = bright burning day). Skipped while
      // the cinematic owns the tint. Then the opening "NIGHT 1 BEGINS"
      // card fires once per fresh session.
      applyPhaseDaylight(st.phase);
      maybeShowOpeningNightCard(st);
      // v1.0 — final-orbit greying + end-of-season results auto-pop.
      handleLiveSeasonState(st);
      updateLiveButtonPulse();
      updateSeatTabVisibility();
      updateOrbitTabVisibility();
      syncMobileOrdersBar();
      harvestAgentLinesFromStatus(st.log_tail, Number(st.day) || 0);
      // v0.9.8 — stash the most recent log tail so replay scrubbing
      // can re-render the LOG drawer with a different ``focusDay``
      // (cursor day instead of live day) without re-fetching.
      lastLogTail = Array.isArray(st.log_tail) ? st.log_tail : [];
      lastLiveDay = Number(st.day) || null;
      const focusDay = mainMapSource === "replay" && replayTicks.length
        ? currentVisibleDay()
        : lastLiveDay;
      renderOrchLog(lastLogTail, focusDay);
      updateNowPlayingStrip();
      renderScoreboard();
      // v0.9.9 — top-right HUD scoreboard reads ``cumulative_shipped_score``
      // straight off /status, no extra fetch.
      renderHudScoreboard(st.cumulative_shipped_score, st.players);
      // v0.9.9 — SHIPPED tab companion stats panel. Reads the
      // viewer's shipped count off the cached inventory (set by
      // pullAllMaps' /view round-trip) so the "your bay X/Y" line
      // tracks the same number the grid shows.
      const _shippedNow =
        lastLiveInventory && Array.isArray(lastLiveInventory.shipped)
          ? lastLiveInventory.shipped.length
          : 0;
      const _shippedCap =
        (lastLiveInventory && lastLiveInventory.shipped_capacity) || 25;
      renderShippedStats(
        st.cumulative_shipped_score, st.players,
        _shippedNow, _shippedCap,
      );
      // v0.9.9 — auto-pop the orbital summary modal once per fresh
      // catapult settlement. The status payload now carries the most
      // recent ``catapult_history`` entry; we cache it into
      // ``catapultByDay`` so the modal renderer sees a complete blob
      // (including ``slot_assignments``) BEFORE the next /replay
      // poll fans the rest of the history in.
      // v0.9.11 — merge the latest station-obs snapshots ({pre,post})
      // + observable orbital-activity tally into the per-day caches so
      // the orbit reports can render live without waiting for the next
      // /replay poll.
      if (st.latest_station_obs && typeof st.latest_station_obs === "object") {
        const lso = st.latest_station_obs;
        const soDay = Number(lso.day || 0) || 0;
        if (soDay > 0) {
          const key = String(soDay);
          const merged = Object.assign({}, stationObsByDay[key] || {});
          if (lso.pre && Object.keys(lso.pre).length) merged.pre = lso.pre;
          if (lso.post && Object.keys(lso.post).length) merged.post = lso.post;
          if (Object.keys(merged).length) stationObsByDay[key] = merged;
          if (lso.activity && Object.keys(lso.activity).length) {
            orbitalActivityByDay[key] = lso.activity;
          }
          if (lso.events && Object.keys(lso.events).length) {
            orbitalEventsByDay[key] = lso.events;
          }
          // v0.9.11 — auto-pop the Pre-Orbital Recap once per fresh
          // night (gated by the "show orbital summaries as pop-ups"
          // setting). Fires on the night_resolving -> orbit hand-off:
          // the engine has stamped a ``pre`` snapshot for the night
          // that just resolved and the phase has opened ORBIT.
          if (
            orbitFlashEnabled
            && mainMapSource === "live"
            && !_suppressLiveReveal
            && soDay > lastShownRecapDay
            && lso.pre && Object.keys(lso.pre).length
            && (st.phase === "orbit" || st.phase === "planning")
          ) {
            lastShownRecapDay = soDay;
            openReport("recap", soDay);
          }
        }
      }
      if (st.latest_catapult && typeof st.latest_catapult === "object") {
        const lc = st.latest_catapult;
        const lcDay = Number(lc.day || 0) || 0;
        if (lcDay > 0) {
          catapultByDay[String(lcDay)] = lc;
          // v0.9.9 — bump ``lastShownOrbitDay`` unconditionally on
          // every new day (even quiet orbits) so we don't try to
          // auto-pop a stale day's modal later. But only actually
          // open the Briefing when something happened — quiet orbits
          // (no bids, no shipping, no jettison) skip the pop entirely
          // and the user sees the planning panel directly. Gated by
          // the "show orbital summaries as pop-ups" setting.
          if (
            orbitFlashEnabled
            && mainMapSource === "live"
            && !_suppressLiveReveal
            && lcDay > lastShownOrbitDay
          ) {
            lastShownOrbitDay = lcDay;
            if (orbitBlobHasActivity(lc)) {
              openReport("briefing", lcDay);
            }
          }
        }
      }
      renderAgentFeed();
      // v0.9.11 — if an orbit report is open live, re-render it so
      // late-arriving night-log / catapult / station-obs data fills in
      // (the report doesn't poll on its own).
      if (reportEl && !reportEl.hidden && mainMapSource === "live") {
        renderReportBody();
      }
      syncQueueCountBadge();
      updateCcTabMeta();
      // v0.9.8 — also re-sync the LOG timeline drawer on every
      // status poll, so a new turn landing while the user has the
      // LOG tab open shows the new day's events immediately rather
      // than waiting for a scrub or filter-chip click.
      syncReplayDrawer();
    } catch (e) {
      phaseLine.textContent = `! status: ${String(e.message || e)}`;
    }
  }

  async function refreshObserverMap() {
    if (!sessionId) {
      paintPlaceholder(mapObserver, "# observer — NEW GAME");
      return;
    }
    // v0.9.x — the omniscient /observer view is a CHEAT during live play.
    // Don't even fetch it unless the session context is allowed to be
    // omniscient (watcher page or finished season); otherwise a player
    // could read the full no-fog board off the GRAPHICS tab.
    if (!opponentSeatVisible()) {
      syncFullMapCheatVisibility();
      paintPlaceholder(
        mapObserver,
        "# full map — replay / finished-season only",
      );
      return;
    }
    try {
      const res = await fetch(`/api/game/${sessionId}/observer`, {
        cache: "no-store",
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const j = await res.json();
      // v0.9.10 — stash the seat list from the observer response so
      // the replay-view buttons show all active seats (p3/p4 too).
      // Mirrors the same stash in ``refreshSoloPlayerMap``.
      if (Array.isArray(j.players) && j.players.length) {
        window.__SOC_PLAYERS__ = j.players.slice(0, 4);
        try { renderReplayViewButtons(); } catch (_e) {}
      }
      if (j.agents) window.__SOC_AGENTS__ = j.agents;
      if (j.visibility_mode) window.__SOC_VISIBILITY__ = j.visibility_mode;
      paintObserverMap(mapObserver, j);
    } catch (e) {
      paintPlaceholder(mapObserver, `! observer: ${e.message}`);
    }
  }

  async function refreshSoloPlayerMap() {
    const unitsEl = document.getElementById("units-player");
    const inventEl = document.getElementById("inventory-player");
    if (!sessionId || !mapPlayer) {
      if (mapPlayer) paintPlaceholder(mapPlayer, "# start NEW GAME");
      lastLiveMapPayload = null;
      if (unitsEl) unitsEl.textContent = "";
      if (inventEl) inventEl.textContent = "";
      renderPolicyHints(null);
      renderVault(null);
      prefetchPlanKey = "";
      return;
    }
    try {
      const res = await fetch(`/api/game/${sessionId}/view?player=${MY_SEAT}`, {
        cache: "no-store",
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const j = await res.json();
      // v0.9.6 — stash the seat list + agent map + visibility mode
      // from the /view response on a window-scoped global so
      // ``activeSeats()`` and friends can drive N-seat rendering
      // without threading the value through every caller.
      if (Array.isArray(j.players) && j.players.length) {
        window.__SOC_PLAYERS__ = j.players.slice(0, 4);
        // v0.9.9 — the replay-view row is N-seat aware. Re-render
        // every time the canonical seat list updates so a fresh
        // session (or a load-from-id navigation) gets per-seat
        // buttons stroked in their owner colour.
        try { renderReplayViewButtons(); } catch (_e) {}
      }
      if (j.agents) window.__SOC_AGENTS__ = j.agents;
      if (j.visibility_mode) window.__SOC_VISIBILITY__ = j.visibility_mode;
      // Build the orbital-station skeleton from the live player list so the
      // stations appear on turn 1 (before any night/replay data exists).
      if (typeof window.osOnLivePlayers === "function") {
        try {
          window.osOnLivePlayers(
            window.__SOC_PLAYERS__ || null,
            j.player_profiles || null,
            MY_SEAT,
          );
        } catch (_e) {}
      }
      // v0.9.6 — stash the tunable RED tier multipliers so the vault
      // tooltip can render ``score = purity \u00d7 mult`` without
      // hard-coding the table (RULEBOOK §3.1). Falls back to the
      // session.py defaults if the agent view didn't surface them.
      const qmult =
        j?.agent_view?.orbit?.ship_prices?.quality_mult
        ?? j?.orbit?.ship_prices?.quality_mult;
      if (qmult && typeof qmult === "object") {
        window.__SOC_QUALITY_MULT__ = qmult;
      }
      // v0.9.x — live EMP salvo size for the targeting picker.
      const empSpec =
        j?.agent_view?.orbit?.weapon_specs?.emp
        ?? j?.orbit?.weapon_specs?.emp;
      if (empSpec && Number.isFinite(Number(empSpec.missiles_per_launch))) {
        window.__SOC_EMP_MISSILES__ = Number(empSpec.missiles_per_launch);
      }
      // v0.9.x — stash the static blue-sign overlay (orbit-wide,
      // fog-independent radiative signatures) for the map painter.
      lastBlueSign = Array.isArray(j.blue_sign) ? j.blue_sign : [];
      _buildBlueSignMap(lastBlueSign);
      // v1.x — discovery-triggered redsign beacons. Live view shows every
      // beacon discovered so far (cutoff = Infinity).
      lastRedSign = Array.isArray(j.redsign) ? j.redsign : [];
      _redsignDayCutoff = Infinity;
      _redsignHourCutoff = Infinity;
      lastLiveMapPayload = {
        width: j.width,
        height: j.height,
        cells: j.cells || [],
      };
      if (mainMapSource === "live" && !_suppressLiveReveal) {
        paintPlayerMap(mapPlayer, lastLiveMapPayload);
        if (_heatPhase === "hold") _heatApplyInstant(mapPlayer, 0.52);
        try { paintBlueSignOverlay(lastBlueSign); } catch (_e) {}
        try { paintRedsignOverlay(); } catch (_e) {}
        // v0.9.13 — repaint rebuilds the cell DOM, so re-anchor the planned
        // orders overlay against the fresh cell rects.
        try { paintPlannedOrdersOverlay(); } catch (_e) {}
      }
      if (unitsEl) {
        unitsEl.textContent =
          `# units:\n${fmtUnits(j.units || [])}`;
      }
      if (inventEl) {
        inventEl.textContent =
          `# inventory · day ${String(j.day)} phase ${String(j.phase)}\n${fmtInventory(j.inventory)}`;
      }
      if (ccTabIntelMeta) {
        const hoardN =
          j.inventory && Array.isArray(j.inventory.hoard)
            ? j.inventory.hoard.length
            : 0;
        const cap = (j.inventory && j.inventory.hoard_capacity) || HOARD_CAP_FALLBACK;
        ccTabIntelMeta.textContent = `${String(hoardN)}/${String(cap)}`;
      }
      // v0.7.5 — cache the live inventory so the scoreboard renderer
      // (LOG panel) can read it between status pings. Carry the day
      // through so AGENT/feed renderers can bucket the right turn.
      lastLiveInventory = j.inventory
        ? { ...j.inventory, day: j.day }
        : null;
      // v0.9.x — cache the all-seat public shipped ledger so the VAULT
      // SHIPPED pane renders every house's shipments during live play.
      lastLiveShippedRecord = Array.isArray(j.shipped_record)
        ? j.shipped_record
        : [];
      // v0.9.5 — stash the live game day on the module-level
      // ``__currentGameDay`` so the shared asset tooltip can render
      // "alive · N days" / "deployed · N days ago" without each
      // chip needing to carry the snapshot day. Falls back to
      // ``null`` between session refreshes so the tooltip simply
      // omits the relative-age rows in that gap.
      try {
        __currentGameDay = j && j.day != null ? Number(j.day) : null;
      } catch (_e) {
        __currentGameDay = null;
      }
      // v0.8.0 — pull the orbit block off the agent view BEFORE
      // renderVault so the new VAULT-tab live readouts (credits etc.)
      // read the freshest snapshot rather than the previous tick's.
      const orbitView = (j.agent_view && j.agent_view.orbit) || null;
      if (orbitView) {
        lastOrbitView = orbitView;
        updateOrbitReadouts(orbitView);
      }
      // v0.9.13 — SHIPPED is an uncapped PUBLIC ledger: pass the
      // all-seat owner-tagged record (set just above) so the SHIPPED
      // pane shows every house's shipments, not just our own bay.
      renderVault(j.inventory, lastLiveShippedRecord);
      renderScoreboard();
      lastHints = j.policy_hints ?? null;
      renderPolicyHints(j.policy_hints ?? null);
      // Hoard meta on the INTEL tab — denominator is the engine-reported
      // capacity (15, RULEBOOK §3.12) with a matching fallback.
      if (ccTabIntelMeta && j.inventory) {
        const hoardN = Array.isArray(j.inventory.hoard)
          ? j.inventory.hoard.length : 0;
        const cap = j.inventory.hoard_capacity || HOARD_CAP_FALLBACK;
        ccTabIntelMeta.textContent = `${String(hoardN)}/${String(cap)}`;
      }

      const pk = `${sessionId}|${String(j.day)}|${String(j.phase)}`;
      if (prefetchPlanKey !== pk) {
        prefetchPlanKey = pk;
        ingestEntityIds(j.policy_hints);
        prefetchSoloDefaultsFromHints(j.policy_hints);
        syncSoloCliFakeBoxes();
      }
    } catch (e) {
      lastLiveMapPayload = null;
      paintPlaceholder(mapPlayer, `! map: ${String(e.message || e)}`);
      if (unitsEl) unitsEl.textContent = "";
      if (inventEl) inventEl.textContent = "";
      renderPolicyHints(null);
    }
  }

  /** Drive the station's DUSK beat (catapult load + "+X" score lines + blue
   *  lift) for a just-resolved orbit that emitted NO night frames. Shared by
   *  the inline orbit-commit path (``submitSoloOrbit``) and the live-sync
   *  resolver (``pullAllMaps`` when a *waiting* player's orbit resolves through
   *  the poller) so every client — not just the last submitter — sees the
   *  orbital play. Season-close is intentionally skipped: it's owned by
   *  ``handleLiveSeasonState`` → ``osOnLiveResolve`` (launch + score fold +
   *  celebration). Cosmetic + fully guarded; a no-op when there's no activity. */
  function _stageLiveOrbitBeat(dayHint) {
    try {
      const _day =
        Number(dayHint) || Number(lastLiveInventory?.day) || Number(lastLiveDay) || 0;
      if (!_day) return;
      if (livePhase === "season_complete") return;
      const _blob = window._socOrbitalData?.catapultByDay?.[String(_day)];
      if (!_blob || !orbitBlobHasActivity(_blob)) return;
      if (typeof window.osOnLiveDusk !== "function") return;
      window.osOnLiveDusk(_day);
      if (replaySlotEl) replaySlotEl.textContent = `Day ${_day} · VESPERA`;
      if (replayCaptionEl)
        replayCaptionEl.textContent =
          `[H00] VESPERA · day ${_day} orbit resolved — plan the Nox`;
    } catch (_e) { /* non-fatal cosmetic drive */ }
  }

  async function pullAllMaps({ playFx = false, stageOrbitBeat = false } = {}) {
    mainMapSource = "live";
    // v0.9.13 — night-turn reveal ordering. When ``playFx`` is set (a turn
    // was just transmitted) we hold back the live end-state paint AND the
    // orbit-report pop via ``_suppressLiveReveal`` while we pull status +
    // build the replay. If a fresh night actually landed we then play that
    // night as a replay cinematic and only afterwards reveal the live map
    // and pop the pre-orbital recap. ``refreshStatus`` must run BEFORE
    // ``refreshNightReplay`` because it seeds ``replayWindowCount``.
    _suppressLiveReveal = !!playFx;
    let info;
    try {
      await Promise.all([
        refreshStatus(),
        refreshObserverMap(),
        refreshSoloPlayerMap(),
      ]);
      info = await refreshNightReplay({ playFx: false });
    } finally {
      _suppressLiveReveal = false;
    }
    const wantCinematic =
      playFx
      && replayLastTurnFx
      && !reduceMotionMq.matches
      && !_liveFxPlaying
      && !replayTicker
      && info
      && info.newDayLanded
      && info.tickCount > info.prevTickCount;
    if (wantCinematic) {
      await _playNightCinematic(info.prevTickCount);
    } else if (playFx) {
      // No cinematic to play, but we suppressed the reveal above — surface
      // the live end-state + any orbit report now (e.g. an orbit settle
      // that didn't add night frames, or reduced-motion / FX-off users).
      mainMapSource = "live";
      if (lastLiveMapPayload && mapPlayer) {
        paintPlayerMap(mapPlayer, lastLiveMapPayload);
        if (_heatPhase === "hold") _heatApplyInstant(mapPlayer, 0.52);
        try { paintBlueSignOverlay(lastBlueSign); } catch (_e) {}
        try { paintRedsignOverlay(); } catch (_e) {}
        try { paintPlannedOrdersOverlay(); } catch (_e) {}
      }
      await refreshStatus();
      // Bug A — a WAITING player's orbit resolves through the live-sync poller,
      // which lands here (no night frames ⇒ no cinematic). Drive the station's
      // DUSK beat so they see the loaded catapults + "+X" score lines too — the
      // inline last-submitter path already does this after its own pull.
      if (stageOrbitBeat) _stageLiveOrbitBeat();
    }
    syncGridlinesClass();
  }

  /**
   * v0.9.6 — N-seat launcher state. ``newGameModalState`` tracks the
   * launcher modal's current shape (seat count, per-seat agents,
   * visibility). The modal is opened by the header [NEW GAME]
   * button; the [SPAWN SESSION] button inside calls ``newGame`` with
   * the captured config so a 1/2/3/4-seat session can spawn without
   * touching URL params.
   * 
   * v0.9.18 — player_profiles (display_name, tag, color) per seat.
   */
  const newGameModalState = {
    seatCount: 2,
    // Default 2-seat game is human vs the no-weapons bot, so NEW GAME →
    // START is a playable match with zero configuration.
    agents: {
      p1: "human",
      p2: "red_harvest_lite",
      p3: "red_harvest_lite",
      p4: "red_harvest_lite",
    },
    visibility: "hidden",
    // v1.14 — storage is a per-game choice. "" means "whatever the
    // server defaults to"; the real value arrives with the options.
    backend: "",
    player_profiles: {
      p1: { display_name: "", tag: "", color: "" },
      p2: { display_name: "", tag: "", color: "" },
      p3: { display_name: "", tag: "", color: "" },
      p4: { display_name: "", tag: "", color: "" },
    },
  };
  const NGM_SEAT_IDS = ["p1", "p2", "p3", "p4"];
  const NGM_SEAT_LABELS = { p1: "WHITE", p2: "YELLOW", p3: "MAGENTA", p4: "CYAN" };

  // v1.12 — the selectable-agent roster, served from the binding
  // registry at /api/meta/agents. Kept as a module-level cache so
  // renderNewGameSeats() stays synchronous; the fallback is the shipped
  // roster, so the modal still works if the fetch fails.
  let _AGENT_ROSTER = null;
  const _AGENT_ROSTER_FALLBACK = [
    { value: "human", label: "HUMAN — pilot from this browser", needs_llm: false },
    { value: "red_harvest_lite", label: "RED_HARVEST_LITE — heuristic bot, no weapons (start here)", needs_llm: false },
    { value: "red_harvest", label: "RED_HARVEST — heuristic bot, weapons on", needs_llm: false },
    { value: "tabula_v12", label: "V12 — LLM agent (needs a Snowflake PAT · slow)", needs_llm: true },
  ];

  function agentRoster() {
    return (_AGENT_ROSTER && _AGENT_ROSTER.length)
      ? _AGENT_ROSTER
      : _AGENT_ROSTER_FALLBACK;
  }

  /** The roster minus anything the chosen backend won't run.
   *  Memory games are heuristics-only: an LLM match leaves no persisted
   *  season, so there's nothing for the turn suite or the advisor to
   *  read back — which is the whole point of playing one. */
  function agentRosterForBackend() {
    const backend = selectedBackend();
    if (backend && backend.allows_llm === false) {
      return agentRoster().filter((e) => !e.needs_llm);
    }
    return agentRoster();
  }

  /** Refresh the roster from the server. Called before the New Game
   *  modal opens so a freshly-registered fork appears without a reload. */
  async function loadAgentRoster() {
    try {
      const r = await fetch("/api/meta/agents", { cache: "no-store" });
      if (!r.ok) return;
      const j = await r.json();
      if (j && Array.isArray(j.agents) && j.agents.length) _AGENT_ROSTER = j.agents;
    } catch (_e) { /* keep the fallback */ }
  }

  // v1.14 — per-game storage backend. Memory is instant but disposable;
  // Snowflake persists the season (and the agent's reasoning, which is
  // what the replay tooling reads). Options come from the server so an
  // unavailable Snowflake store can be shown greyed-out with the reason
  // instead of vanishing, which reads as a missing feature.
  let _BACKEND_OPTIONS = null;
  const _BACKEND_OPTIONS_FALLBACK = [
    {
      value: "memory", label: "MEMORY", available: true, persists: false,
      allows_llm: false, default: true,
      blurb: "Instant moves. The season vanishes when the server stops.",
    },
  ];

  function backendOptions() {
    return (_BACKEND_OPTIONS && _BACKEND_OPTIONS.length)
      ? _BACKEND_OPTIONS
      : _BACKEND_OPTIONS_FALLBACK;
  }

  function selectedBackend() {
    const opts = backendOptions();
    const chosen = opts.find((o) => o.value === newGameModalState.backend);
    if (chosen && chosen.available) return chosen;
    return opts.find((o) => o.default && o.available)
      || opts.find((o) => o.available)
      || opts[0];
  }

  async function loadBackendOptions() {
    try {
      const r = await fetch("/api/meta/backend", { cache: "no-store" });
      if (!r.ok) return;
      const j = await r.json();
      if (j && Array.isArray(j.options) && j.options.length) {
        _BACKEND_OPTIONS = j.options;
        const cur = j.options.find((o) => o.value === newGameModalState.backend);
        if (!cur || !cur.available) {
          const def = j.options.find((o) => o.default && o.available)
            || j.options.find((o) => o.available);
          newGameModalState.backend = def ? def.value : "";
        }
      }
    } catch (_e) { /* keep the fallback */ }
  }

  /** Render the STORAGE radio group. Unavailable backends stay visible
   *  but disabled, captioned with the reason and the fix — a hidden
   *  option looks like the feature doesn't exist. */
  function renderNewGameBackends() {
    const host = document.getElementById("ngm-backend");
    if (!host) return;
    host.innerHTML = "";
    const active = selectedBackend();
    for (const opt of backendOptions()) {
      const label = document.createElement("label");
      label.className = "cc-newgame-visopt";
      if (!opt.available) label.classList.add("is-disabled");

      const radio = document.createElement("input");
      radio.type = "radio";
      radio.name = "ngm-backend";
      radio.value = opt.value;
      radio.disabled = !opt.available;
      radio.checked = !!active && opt.value === active.value;
      radio.addEventListener("change", () => {
        if (!radio.checked) return;
        newGameModalState.backend = opt.value;
        // The roster depends on the backend (no LLM seats on memory), so
        // the seat list has to be rebuilt, not just re-labelled.
        renderNewGameSeats();
      });

      const span = document.createElement("span");
      let text = `${opt.label.toUpperCase()} — ${opt.blurb || ""}`.trim();
      if (!opt.available && opt.reason) {
        text += ` [unavailable: ${opt.reason}${opt.fix ? ` · ${opt.fix}` : ""}]`;
      }
      span.textContent = text;

      label.appendChild(radio);
      label.appendChild(span);
      host.appendChild(label);
    }
  }
  
  // v0.9.18 — color palette for player customization (fetched from /api/game/palette)
  // The fallback mirrors SEAT_COLOR_PALETTE in session.py so the picker is
  // fully usable even when the palette fetch fails (offline / server hiccup).
  const __SOC_FALLBACK_PALETTE__ = [
    { hex: "#FFFFFF", rgb: [255, 255, 255] },
    { hex: "#FCF871", rgb: [252, 248, 113] },
    { hex: "#85F57E", rgb: [133, 245, 126] },
    { hex: "#82F4FB", rgb: [130, 244, 251] },
    { hex: "#E45EF0", rgb: [228, 94, 240] },
    { hex: "#B6FF3A", rgb: [182, 255, 58] },
    { hex: "#FF8A1E", rgb: [255, 138, 30] },
    { hex: "#FF49B0", rgb: [255, 73, 176] },
    { hex: "#C29BFF", rgb: [194, 155, 255] },
  ];
  const __SOC_FALLBACK_DEFAULTS__ = { p1: "#FFFFFF", p2: "#FCF871", p3: "#E45EF0", p4: "#82F4FB" };
  let __SOC_COLOR_PALETTE__ = [];
  let __SOC_DEFAULT_COLORS__ = {};
  
  /**
   * v0.9.18 — Get a player's display name (full name for end screen, etc.)
   * Falls back to seat color label if no custom name is set.
   */
  function playerDisplayName(seat) {
    const profile = __SOC_PLAYER_META__[seat];
    if (profile && profile.display_name) return profile.display_name;
    // Fallback to color labels
    const labels = { p1: "WHITE", p2: "YELLOW", p3: "MAGENTA", p4: "CYAN" };
    return labels[seat] || String(seat).toUpperCase();
  }
  
  /**
   * v0.9.18 — Get a player's 3-letter tag for compact UI (scoreboard, HUD)
   */
  function playerTag(seat) {
    const profile = __SOC_PLAYER_META__[seat];
    if (profile && profile.tag) return profile.tag;
    // Fallback to first 3 chars of seat ID
    return String(seat).slice(0, 3).toUpperCase();
  }
  
  /**
   * v0.9.18 — Get a player's custom color (hex) or fall back to defaults
   */
  function playerColor(seat) {
    const profile = __SOC_PLAYER_META__[seat];
    if (profile && profile.color) return profile.color;
    // Fallback to default colors
    const defaults = { p1: "#FFFFFF", p2: "#FCF871", p3: "#E45EF0", p4: "#82F4FB" };
    return defaults[seat] || "#FFFFFF";
  }

  /**
   * v0.9.18 — Push the active session's seat colours into the global
   * ``--seat-pN`` CSS custom properties on :root. Every stylesheet rule
   * that references ``var(--seat-pN)`` (catapult slots, timeline rows,
   * now-playing caption, vault borders, scoreboards, etc.) then renders
   * with the player's real colour without us having to touch each rule.
   * This is the single choke-point that keeps CSS and JS colours in sync.
   */
  function applySeatColorVars() {
    const root = document.documentElement;
    if (!root) return;
    for (const seat of ["p1", "p2", "p3", "p4"]) {
      const meta = __SOC_PLAYER_META__[seat];
      if (meta && meta.color) {
        root.style.setProperty(`--seat-${seat}`, meta.color);
      } else {
        // Clear any prior override so the stylesheet default re-applies.
        root.style.removeProperty(`--seat-${seat}`);
      }
    }
  }

  /**
   * v0.9.18 — Single entry point for adopting player identity metadata
   * (names, tags, colours) from a /status or /replay payload. Updates the
   * meta map AND the root colour variables so live + replay surfaces stay
   * consistent. Ignores empty/missing payloads.
   */
  function setPlayerMeta(profiles) {
    if (profiles && typeof profiles === "object" && Object.keys(profiles).length) {
      __SOC_PLAYER_META__ = profiles;
      applySeatColorVars();
    }
  }

  /**
   * v0.9.18 — drop all player identity metadata and clear the root
   * ``--seat-pN`` overrides so the stylesheet defaults re-apply. Called
   * on session reset / new game so one game's custom names + colours
   * never leak into the next (the "stale meta never cleared" bug).
   */
  function clearPlayerMeta() {
    __SOC_PLAYER_META__ = {};
    applySeatColorVars();
  }

  function renderNewGameSeats() {
    const ul = document.getElementById("ngm-seats");
    if (!ul) return;
    // v0.9.18 — never render an empty picker; fall back to the full palette
    // if the async fetch hasn't populated it yet (e.g. seat-count re-render).
    const palette = (__SOC_COLOR_PALETTE__ && __SOC_COLOR_PALETTE__.length)
      ? __SOC_COLOR_PALETTE__ : __SOC_FALLBACK_PALETTE__;
    const defaultColors = (__SOC_DEFAULT_COLORS__ && Object.keys(__SOC_DEFAULT_COLORS__).length)
      ? __SOC_DEFAULT_COLORS__ : __SOC_FALLBACK_DEFAULTS__;
    ul.innerHTML = "";
    for (let i = 0; i < newGameModalState.seatCount; i++) {
      const sid = NGM_SEAT_IDS[i];
      const li = document.createElement("li");
      li.className = "cc-newgame-seat";
      li.dataset.seat = sid;
      
      // Seat header row: ID + agent selector
      const headerRow = document.createElement("div");
      headerRow.className = "cc-newgame-seat-header";
      
      const idEl = document.createElement("span");
      idEl.className = "cc-newgame-seat-id";
      idEl.textContent = `${sid.toUpperCase()} · ${NGM_SEAT_LABELS[sid]}`;
      
      const sel = document.createElement("select");
      sel.className = "cc-newgame-seat-select";
      sel.setAttribute("aria-label", `${sid} agent`);
      // v1.12 — roster comes from /api/meta/agents (the binding
      // registry), not a list here. A hackathon fork that registers a
      // binding shows up in this dropdown with no frontend edit; the
      // hardcoded version meant teams shipped an agent they couldn't
      // select. _AGENT_ROSTER is the last fetched copy, with the
      // shipped roster as a cold-start fallback.
      const roster = agentRosterForBackend();
      for (const entry of roster) {
        const opt = document.createElement("option");
        opt.value = entry.value;
        opt.textContent = entry.label;
        sel.appendChild(opt);
      }
      // Default rivals to the no-weapons bot: a first-timer shouldn't be
      // mined and EMP'd before they know what a parcel is.
      let want = newGameModalState.agents[sid] || (i === 0 ? "human" : "red_harvest_lite");
      // Switching to a memory game drops the LLM entries, and a <select>
      // silently blanks when its value is gone — which would post an
      // empty agent. Fall back to the safe default instead.
      if (!roster.some((e) => e.value === want)) {
        want = i === 0 ? "human" : "red_harvest_lite";
      }
      sel.value = want;
      newGameModalState.agents[sid] = sel.value;
      sel.addEventListener("change", () => {
        newGameModalState.agents[sid] = sel.value;
      });
      
      headerRow.appendChild(idEl);
      headerRow.appendChild(sel);
      li.appendChild(headerRow);
      
      // v0.9.18 — Player customization row: name, tag, color
      const custRow = document.createElement("div");
      custRow.className = "cc-newgame-seat-cust";
      
      // Name input
      const nameLabel = document.createElement("label");
      nameLabel.className = "cc-newgame-cust-label";
      nameLabel.textContent = "name";
      const nameInput = document.createElement("input");
      nameInput.type = "text";
      nameInput.className = "cc-newgame-cust-input cc-newgame-cust-name";
      nameInput.placeholder = NGM_SEAT_LABELS[sid];
      nameInput.maxLength = 24;
      nameInput.value = newGameModalState.player_profiles[sid]?.display_name || "";
      nameInput.addEventListener("input", () => {
        if (!newGameModalState.player_profiles[sid]) {
          newGameModalState.player_profiles[sid] = { display_name: "", tag: "", color: "" };
        }
        newGameModalState.player_profiles[sid].display_name = nameInput.value.trim();
        const label = nameInput.value.trim() || NGM_SEAT_LABELS[sid];
        idEl.textContent = `${sid.toUpperCase()} · ${label.toUpperCase()}`;
        // Auto-generate tag from name (first 3 alnum chars, uppercase)
        if (!tagInput.dataset.userEdited) {
          const autoTag = nameInput.value.replace(/[^a-zA-Z0-9]/g, "").slice(0, 3).toUpperCase();
          tagInput.value = autoTag;
          if (newGameModalState.player_profiles[sid]) {
            newGameModalState.player_profiles[sid].tag = autoTag;
          }
        }
      });
      
      // Tag input (3-letter)
      const tagLabel = document.createElement("label");
      tagLabel.className = "cc-newgame-cust-label";
      tagLabel.textContent = "tag";
      const tagInput = document.createElement("input");
      tagInput.type = "text";
      tagInput.className = "cc-newgame-cust-input cc-newgame-cust-tag";
      tagInput.placeholder = sid.toUpperCase().slice(0, 3);
      tagInput.maxLength = 3;
      tagInput.value = newGameModalState.player_profiles[sid]?.tag || "";
      tagInput.addEventListener("input", () => {
        tagInput.dataset.userEdited = "true";
        if (!newGameModalState.player_profiles[sid]) {
          newGameModalState.player_profiles[sid] = { display_name: "", tag: "", color: "" };
        }
        newGameModalState.player_profiles[sid].tag = tagInput.value.toUpperCase().slice(0, 3);
        tagInput.value = tagInput.value.toUpperCase().slice(0, 3);
      });
      
      // Color picker (palette swatches)
      const colorLabel = document.createElement("label");
      colorLabel.className = "cc-newgame-cust-label";
      colorLabel.textContent = "color";
      const colorPicker = document.createElement("div");
      colorPicker.className = "cc-newgame-cust-colorpicker";
      
      // Default color for this seat
      const defaultColor = defaultColors[sid] || "#FFFFFF";
      const currentColor = newGameModalState.player_profiles[sid]?.color || defaultColor;
      li.style.setProperty("--seat-color", currentColor);

      // Render color swatches
      for (const colorEntry of palette) {
        const swatch = document.createElement("button");
        swatch.type = "button";
        swatch.className = "cc-newgame-cust-swatch";
        swatch.style.backgroundColor = colorEntry.hex;
        swatch.title = colorEntry.hex;
        swatch.setAttribute("aria-label", `Select color ${colorEntry.hex}`);
        if (colorEntry.hex === currentColor) {
          swatch.classList.add("cc-newgame-cust-swatch--selected");
        }
        swatch.addEventListener("click", () => {
          // Remove selection from all swatches in this picker
          colorPicker.querySelectorAll(".cc-newgame-cust-swatch").forEach(s => {
            s.classList.remove("cc-newgame-cust-swatch--selected");
          });
          swatch.classList.add("cc-newgame-cust-swatch--selected");
          if (!newGameModalState.player_profiles[sid]) {
            newGameModalState.player_profiles[sid] = { display_name: "", tag: "", color: "" };
          }
          newGameModalState.player_profiles[sid].color = colorEntry.hex;
          li.style.setProperty("--seat-color", colorEntry.hex);
        });
        colorPicker.appendChild(swatch);
      }
      
      // Assemble customization row
      const nameGroup = document.createElement("div");
      nameGroup.className = "cc-newgame-cust-group";
      nameGroup.appendChild(nameLabel);
      nameGroup.appendChild(nameInput);
      
      const tagGroup = document.createElement("div");
      tagGroup.className = "cc-newgame-cust-group cc-newgame-cust-group--tag";
      tagGroup.appendChild(tagLabel);
      tagGroup.appendChild(tagInput);
      
      const colorGroup = document.createElement("div");
      colorGroup.className = "cc-newgame-cust-group cc-newgame-cust-group--color";
      colorGroup.appendChild(colorLabel);
      colorGroup.appendChild(colorPicker);
      
      custRow.appendChild(nameGroup);
      custRow.appendChild(tagGroup);
      custRow.appendChild(colorGroup);
      li.appendChild(custRow);
      
      ul.appendChild(li);
    }
  }

  function updateNewGameSeatCountButtons() {
    document.querySelectorAll("#ngm-seat-count .cc-newgame-seatbtn").forEach((b) => {
      const count = parseInt(b.dataset.count || "0", 10);
      b.classList.toggle("cc-newgame-seatbtn--on", count === newGameModalState.seatCount);
    });
  }

  async function openNewGameModal() {
    const modal = document.getElementById("new-game-modal");
    if (!modal) return;
    const status = document.getElementById("new-game-modal-status");
    if (status) status.textContent = "";

    // Refresh every open, not once per page load: a team registering a
    // fork restarts the server, and expecting them to also hard-refresh
    // the tab is the kind of papercut that reads as "my agent didn't
    // work".
    await loadAgentRoster();
    // Same reasoning: deploying a schema mid-session shouldn't need a
    // hard refresh before Snowflake becomes selectable.
    await loadBackendOptions();
    
    // v0.9.18 — fetch color palette if not already loaded
    if (__SOC_COLOR_PALETTE__.length === 0) {
      try {
        const res = await fetch("/api/game/palette", { cache: "no-store" });
        if (res.ok) {
          const data = await res.json();
          __SOC_COLOR_PALETTE__ = (data.palette && data.palette.length) ? data.palette : __SOC_FALLBACK_PALETTE__;
          __SOC_DEFAULT_COLORS__ = (data.defaults && Object.keys(data.defaults).length) ? data.defaults : __SOC_FALLBACK_DEFAULTS__;
        } else {
          throw new Error(`palette HTTP ${res.status}`);
        }
      } catch (err) {
        console.error("[soc] Failed to fetch color palette, using full fallback:", err);
        // Fall back to the FULL curated palette so the picker stays usable.
        __SOC_COLOR_PALETTE__ = __SOC_FALLBACK_PALETTE__.slice();
        __SOC_DEFAULT_COLORS__ = Object.assign({}, __SOC_FALLBACK_DEFAULTS__);
      }
    }
    
    // Sync the inline NIGHTS field into the modal so the two surfaces agree.
    const inlineCap = document.getElementById("new-game-cap");
    const modalCap = document.getElementById("ngm-cap");
    if (inlineCap && modalCap) modalCap.value = inlineCap.value;
    // Backends before seats: the roster is filtered by the choice.
    renderNewGameBackends();
    renderNewGameSeats();
    updateNewGameSeatCountButtons();
    modal.hidden = false;
  }

  function closeNewGameModal() {
    const modal = document.getElementById("new-game-modal");
    if (modal) modal.hidden = true;
  }

  function bindNewGameModal() {
    document.querySelectorAll("#ngm-seat-count .cc-newgame-seatbtn").forEach((b) => {
      b.addEventListener("click", () => {
        const count = Math.max(1, Math.min(4, parseInt(b.dataset.count || "2", 10)));
        newGameModalState.seatCount = count;
        renderNewGameSeats();
        updateNewGameSeatCountButtons();
      });
    });
    document.querySelectorAll('input[name="ngm-visibility"]').forEach((r) => {
      r.addEventListener("change", () => {
        if (r.checked) newGameModalState.visibility = r.value;
      });
    });
    const closeBtn = document.getElementById("new-game-modal-close");
    if (closeBtn) closeBtn.addEventListener("click", closeNewGameModal);
    const spawnBtn = document.getElementById("new-game-modal-spawn");
    if (spawnBtn) spawnBtn.addEventListener("click", () => {
      spawnFromModal();
    });
  }

  async function spawnFromModal() {
    const statusEl = document.getElementById("new-game-modal-status");
    const widthRaw = parseInt((document.getElementById("ngm-width") || {}).value, 10);
    const heightRaw = parseInt((document.getElementById("ngm-height") || {}).value, 10);
    const capRaw = parseInt((document.getElementById("ngm-cap") || {}).value, 10);
    const width = Number.isFinite(widthRaw) ? Math.max(8, Math.min(200, widthRaw)) : 40;
    const height = Number.isFinite(heightRaw) ? Math.max(8, Math.min(200, heightRaw)) : 28;
    const cap = Number.isFinite(capRaw) ? Math.max(1, Math.min(60, capRaw)) : 7;
    const players = NGM_SEAT_IDS.slice(0, newGameModalState.seatCount);
    const agents = {};
    for (const sid of players) agents[sid] = newGameModalState.agents[sid] || "human";
    
    // v0.9.18 — collect player_profiles (name, tag, color) for active human seats
    const player_profiles = {};
    for (const sid of players) {
      const profile = newGameModalState.player_profiles[sid];
      if (profile && (profile.display_name || profile.tag || profile.color)) {
        player_profiles[sid] = {
          display_name: profile.display_name || "",
          tag: profile.tag || "",
          color: profile.color || "",
        };
      }
    }
    
    if (statusEl) statusEl.textContent = "// spawning…";
    await newGame({
      width,
      height,
      season_day_cap: cap,
      players,
      agents,
      visibility_mode: newGameModalState.visibility,
      backend: (selectedBackend() || {}).value || "",
      player_profiles: Object.keys(player_profiles).length > 0 ? player_profiles : undefined,
    });
    if (statusEl) statusEl.textContent = "// session live.";
    closeNewGameModal();
  }

  async function newGame(opts) {
    newGameBtn.disabled = true;
    phaseLine.textContent = "# spawning session…";
    resetSoloFormForNewGame();
    if (errSoloEl) errSoloEl.hidden = true;
    try {
      const capInput = document.getElementById("new-game-cap");
      const capRaw = capInput ? parseInt(capInput.value, 10) : NaN;
      const fallbackCap = Number.isFinite(capRaw)
        ? Math.max(1, Math.min(60, capRaw))
        : 10;
      const body = {
        width: (opts && Number.isFinite(opts.width)) ? opts.width : 40,
        height: (opts && Number.isFinite(opts.height)) ? opts.height : 28,
        season_day_cap: (opts && Number.isFinite(opts.season_day_cap))
          ? opts.season_day_cap : fallbackCap,
        players: (opts && Array.isArray(opts.players) && opts.players.length)
          ? opts.players : ["p1", "p2"],
        agents: (opts && opts.agents) ? opts.agents : { p1: "human", p2: "human" },
        visibility_mode: (opts && opts.visibility_mode === "open") ? "open" : "hidden",
      };
      // v0.9.18 — player_profiles (custom names, tags, colors)
      if (opts && opts.player_profiles) {
        body.player_profiles = opts.player_profiles;
      }
      // v1.14 — omitted means "server default", so only send a real pick.
      if (opts && opts.backend) body.backend = opts.backend;
      const res = await fetch("/api/game/new", {
        method: "POST",
        cache: "no-store",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        // Surface the server's `detail` — it carries the actionable part
        // (e.g. "seat p2 is an LLM agent but there's no PAT; here's how
        // to fix it, or pick RED_HARVEST_LITE"). A bare "HTTP 400"
        // strands the player with nothing to act on.
        let detail = "";
        try {
          detail = (await res.json())?.detail || "";
        } catch { /* non-JSON body — fall back to the status code */ }
        throw new Error(detail || `HTTP ${res.status}`);
      }
      const respBody = await res.json();
      sessionId = respBody.session_id;
      window.__SOC_LAST_NEWGAME__ = respBody;
      // v0.9.9 — reset the live-mode orbit auto-pop guard so the new
      // session's first catapult settlement actually pops the modal
      // (rather than being shadow-suppressed by a stale guard left
      // over from the previous game).
      lastShownOrbitDay = 0;
      lastShownRecapDay = 0;
      orbitFlashLastDay = 0;
      stationObsByDay = {};
      orbitalActivityByDay = {};
      orbitalEventsByDay = {};
      await pullAllMaps();
      syncMobileOrdersBar();
      // v0.9.12 — a multi-human spawn surfaces shareable seat links + turns
      // on cross-browser sync. A solo game (one human) is a no-op here, so
      // the single-browser flow is unchanged.
      maybeOfferShareLinks(respBody);
    } catch (e) {
      sessionId = null;
      replayWindowCount = 0;
      nightReplayFrames = [];
      replayTicks = [];
      replayTickIdx = 0;
      prefetchPlanKey = "";
      resetSoloFormForNewGame();
      stopReplayPlayback();
      syncReplayRowOnly();
      phaseLine.textContent = `! ${e.message || e}`;
      if (mapPlayer) paintPlaceholder(mapPlayer, "# error");
      paintPlaceholder(mapObserver, "# error");
    } finally {
      newGameBtn.disabled = false;
    }
  }

  // ── Watcher-mode helpers (Phase C) ──────────────────────────────────

  /** Fetch every persisted season for the picker.
   * Returns the parsed payload (or an empty list shape on failure).
   * @returns {Promise<{ sessions: Array<Object> }>}
   */
  async function fetchSeasonList() {
    try {
      const res = await fetch("/api/sessions", { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const body = await res.json();
      return body && Array.isArray(body.sessions)
        ? body
        : { sessions: [] };
    } catch (e) {
      console.error("watch: /api/sessions failed", e);
      return { sessions: [] };
    }
  }

  /** Render the season picker dropdown from a payload. The picker shows
   * "<season_name> · DAY n · score p1-p2" so a watcher can pick by
   * outcome at a glance. The currently-loaded session is auto-selected.
   * @param {Array<Object>} sessions
   * @param {string} activeId
   */
  /** Format a season row's per-seat final scores for the picker label.
   *  ``row.scores`` is ``{seat: score}`` for every seat in the game
   *  (N-seat aware), using the same canonical ``score_for`` the
   *  end-of-game screen shows. Joined with " / " (rather than "-") so
   *  negative finals like "-135 / -612" stay legible. */
  function formatSeasonScores(row) {
    const s = (row && row.scores) || {};
    const seats = Object.keys(s).sort();
    if (!seats.length) return "0";
    return seats.map((k) => String(s[k])).join(" / ");
  }

  function renderSeasonPicker(sessions, activeId) {
    if (!watchPickerEl) return;
    watchPickerEl.innerHTML = "";
    // Test fixtures (frozen nights) and their clones share this table with
    // real seasons and outnumber them several to one. They never advance,
    // so they would otherwise fill the RESUME group forever. Hidden unless
    // the checkbox asks for them — or unless one is the active selection,
    // which happens when a fixture is opened by deep-link.
    const showFixtures = !!(watchFixturesEl && watchFixturesEl.checked);
    const isFixture = (row) => {
      const kind = String(row.kind || "");
      return kind === "fixture" || kind === "replay";
    };
    const visible = showFixtures
      ? sessions
      : sessions.filter((r) => !isFixture(r) || r.session_id === activeId);
    const hiddenCount = sessions.length - visible.length;
    if (watchFixturesEl) {
      watchFixturesEl.parentElement?.toggleAttribute(
        "hidden", !showFixtures && !hiddenCount,
      );
    }
    if (!visible.length) {
      const opt = document.createElement("option");
      opt.value = "";
      opt.textContent = hiddenCount
        ? `// ${hiddenCount} fixture(s) hidden — tick "fixtures" to show`
        : "// no persisted seasons yet";
      watchPickerEl.appendChild(opt);
      watchPickerEl.disabled = true;
      return;
    }
    watchPickerEl.disabled = false;
    // v1.0 — split into RESUME (in-progress, playable) vs REPLAYS
    // (finished, watch-only). A finished season is one whose phase is
    // ``season_complete``; everything else is still mid-flight and can
    // be re-entered as a human seat.
    const isFinished = (row) => String(row.phase || "") === "season_complete";
    const resumable = visible.filter((r) => !isFinished(r) && !isFixture(r));
    const replays = visible.filter(isFinished);
    const fixtures = visible.filter((r) => isFixture(r) && !isFinished(r));

    const buildOption = (row, playable) => {
      const opt = document.createElement("option");
      opt.value = row.session_id;
      // Origin glyph: cloud = Snowflake, floppy/disk = local file store.
      const srcGlyph =
        row.source === "snowflake" ? "\u2601 " :   // ☁
        row.source === "local" ? "\uD83D\uDCBE " : // 💾
        "";
      // A season NAME is not unique — a sweep runs the same name many times,
      // and the list then shows a dozen identical rows. The short session id
      // is the only thing that tells them apart, and it is what every report,
      // snapshot id and deep link refers to, so show it alongside.
      const shortId = row.session_id.slice(0, 8);
      const label =
        srcGlyph +
        (row.season_name ? `${row.season_name} · ${shortId}` : shortId) +
        ` · D${String(row.day || 0)}` +
        ` · ${formatSeasonScores(row)}` +
        (playable ? " · resume" : " · done");
      opt.textContent = label;
      if (row.season_slug) opt.dataset.slug = row.season_slug;
      if (row.source) opt.dataset.source = row.source;
      opt.dataset.resumable = playable ? "1" : "0";
      return opt;
    };

    if (resumable.length) {
      const grp = document.createElement("optgroup");
      grp.label = "Resume — in progress (playable)";
      for (const row of resumable) grp.appendChild(buildOption(row, true));
      watchPickerEl.appendChild(grp);
    }
    if (replays.length) {
      const grp = document.createElement("optgroup");
      grp.label = "Replays — finished (watch only)";
      for (const row of replays) grp.appendChild(buildOption(row, false));
      watchPickerEl.appendChild(grp);
    }
    if (fixtures.length) {
      const grp = document.createElement("optgroup");
      grp.label = "Fixtures — frozen test nights";
      for (const row of fixtures) grp.appendChild(buildOption(row, true));
      watchPickerEl.appendChild(grp);
    }
    if (activeId) watchPickerEl.value = activeId;
    if (watchDeleteBtn) watchDeleteBtn.hidden = !visible.length;
  }

  /** Resume an in-progress season as a playable human seat. Fetches the
   *  session's agent map to bind to its first human seat (default p1),
   *  then deep-links into JOIN_MODE on the play surface. */
  async function resumeSession(sid) {
    if (!sid) return;
    let seat = "p1";
    try {
      const res = await fetch(`/api/game/${encodeURIComponent(sid)}/status`, {
        cache: "no-store",
      });
      if (res.ok) {
        const st = await res.json();
        const players = Array.isArray(st.players) ? st.players : [];
        const agents = (st.agents && typeof st.agents === "object") ? st.agents : {};
        const human = players.find(
          (p) => String(agents[p] || "human").toLowerCase() === "human",
        );
        if (human) seat = human;
      }
    } catch (_e) { /* fall back to p1 */ }
    const url = new URL(window.location.origin + "/play");
    url.searchParams.set("session", sid);
    url.searchParams.set("player", seat);
    window.location.href = url.toString();
  }

  /** Delete the currently-selected replay (bin button). Confirms first,
   *  calls DELETE /api/game/<id>, then reloads the picker to the next
   *  available season (or clears the deep-link when none remain). */
  async function deleteSelectedSeason() {
    if (!watchPickerEl) return;
    const sid = watchPickerEl.value;
    if (!sid) return;
    const opt = watchPickerEl.options[watchPickerEl.selectedIndex];
    const label = (opt && opt.textContent) || sid;
    if (!window.confirm(`Delete this replay permanently?\n\n${label}`)) return;
    try {
      const res = await fetch(`/api/game/${encodeURIComponent(sid)}`, {
        method: "DELETE",
        cache: "no-store",
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
    } catch (e) {
      console.error("watch: delete failed", e);
      window.alert("Delete failed — see console.");
      return;
    }
    // Reload the picker; jump to the freshest remaining season (or a
    // clean watch landing when the store is now empty).
    const body = await fetchSeasonList();
    const sessions = body.sessions || [];
    const url = new URL(window.location.href);
    url.searchParams.delete("season");
    url.searchParams.delete("watch");
    if (sessions.length) {
      url.searchParams.set("session", sessions[0].session_id);
    } else {
      url.searchParams.delete("session");
      url.searchParams.set("watch", "1");
    }
    window.location.href = url.toString();
  }

  /** Drive a specific persisted session into the replay panel.
   * Mirrors :func:`newGame` but skips the POST-to-create — the session
   * already exists in Snowflake (or the memory store). Everything else
   * (status, observer, view, replay) is the same pipeline.
   * @param {string} id
   */
  async function loadWatcherSession(id) {
    if (!id) return;
    if (phaseLine) phaseLine.textContent = `# loading season…`;
    sessionId = id;
    try {
      await pullAllMaps();
      // Default tab in watcher mode is REPLAY — that's the whole point.
      activateCcTab("replay");
    } catch (e) {
      if (phaseLine) phaseLine.textContent = `! ${e?.message || e}`;
      if (mapPlayer) paintPlaceholder(mapPlayer, "# error loading season");
    }
  }

  // ── v0.9.12 — cross-browser multiplayer (seat binding + share + sync) ──

  /** Seat ids in this game whose agent is "human" (vs a bot). Reads the
   *  status/view ``agents`` map, defaulting unknown seats to human. */
  function humanSeatsFromState(st) {
    const players =
      Array.isArray(st?.players) && st.players.length
        ? st.players
        : Array.isArray(window.__SOC_PLAYERS__)
          ? window.__SOC_PLAYERS__
          : [];
    const agents =
      st?.agents && typeof st.agents === "object"
        ? st.agents
        : window.__SOC_AGENTS__ && typeof window.__SOC_AGENTS__ === "object"
          ? window.__SOC_AGENTS__
          : {};
    return players.filter(
      (p) => String(agents[p] || "human").toLowerCase() === "human",
    );
  }

  function seatLabel(seat) {
    // v0.9.18 — prefer the player's real display name when a session
    // profile exists (playerDisplayName falls back to the legacy colour
    // label, e.g. WHITE/YELLOW, when no custom name is set).
    return playerDisplayName(seat);
  }

  /** Reflect MY_SEAT across the perspective sub-tabs + the identity badge. */
  function applySeatIdentity() {
    agentSeat = MY_SEAT;
    vaultSeat = MY_SEAT;
    if (mainMapSource !== "replay") replayViewSeat = MY_SEAT;
    updateSeatIdentityBadge();
  }

  /** Bind the local "this is me" seat and keep the URL refresh-safe. */
  function setMySeat(seat) {
    const s = String(seat || "").toLowerCase();
    if (!/^p[1-4]$/.test(s)) return;
    MY_SEAT = s;
    try {
      const u = new URL(window.location.href);
      u.searchParams.set("session", sessionId || WATCH_SESSION_ID || "");
      u.searchParams.set("player", s);
      window.history.replaceState(null, "", u.toString());
    } catch (_e) {
      /* history API unavailable — non-fatal */
    }
    applySeatIdentity();
  }

  /** Top-left "You are PN" badge, shown only in a multi-human game. */
  function updateSeatIdentityBadge() {
    let el = document.getElementById("cc-seat-identity");
    if (!_multiHumanGame) {
      if (el) el.hidden = true;
      return;
    }
    if (!el) {
      el = document.createElement("div");
      el.id = "cc-seat-identity";
      el.className = "cc-seat-identity";
      document.body.appendChild(el);
    }
    el.innerHTML =
      `<span class="cc-seat-identity__dot" style="background:${ownerColour(
        MY_SEAT,
      )}"></span>` + `YOU ARE ${playerTag(MY_SEAT)} · ${playerDisplayName(MY_SEAT)}`;
    el.hidden = false;
  }

  /** Modal seat picker for a joiner whose link lacks a valid human seat. */
  function promptSeatPicker(seats) {
    return new Promise((resolve) => {
      const list = seats && seats.length ? seats : ["p1"];
      const overlay = document.createElement("div");
      overlay.className = "cc-seat-picker-overlay";
      const card = document.createElement("div");
      card.className = "cc-seat-picker-card";
      const title = document.createElement("div");
      title.className = "cc-seat-picker-title";
      title.textContent = "// JOIN GAME — choose your seat";
      card.appendChild(title);
      list.forEach((seat) => {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "cli-btn cc-seat-picker-btn";
        b.textContent = `[ ${playerTag(seat)} · ${playerDisplayName(seat)} ]`;
        b.style.setProperty("--cc-replay-seat-stroke", ownerColour(seat));
        b.addEventListener("click", () => {
          if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
          resolve(seat);
        });
        card.appendChild(b);
      });
      overlay.appendChild(card);
      document.body.appendChild(overlay);
    });
  }

  /** Build a seat link against an arbitrary origin (defaults to the
   *  current page origin). */
  function buildSeatUrl(originUrl, sid, seat) {
    const u = new URL(originUrl || window.location.href);
    u.hash = "";
    u.search = "";
    // v1.12 — pin the path. This used to inherit whatever path the
    // caller's URL had, which was fine for same-origin links (you are
    // already on /play) but silently wrong for LAN links: fetchLanOrigin
    // returns a bare origin like http://192.168.1.42:8000, whose path is
    // "/" — the landing page, which ignores ?session/?player entirely.
    // So every QR a phone scanned opened the title screen instead of the
    // game. Setting it explicitly makes the link correct no matter what
    // the caller passes in.
    u.pathname = "/play";
    u.searchParams.set("session", sid);
    u.searchParams.set("player", seat);
    return u.toString();
  }

  /** Build a shareable seat link for the current origin. */
  function shareLinkFor(sid, seat) {
    return buildSeatUrl(window.location.href, sid, seat);
  }

  /** Resolve the host's LAN origin once (e.g. "http://192.168.1.42:8000")
   *  so invite links / QR codes work from a phone. Returns "" when the
   *  server is offline or only on loopback. */
  async function fetchLanOrigin() {
    if (_lanOrigin !== null) return _lanOrigin;
    try {
      const r = await fetch("/api/meta/lan", { cache: "no-store" });
      const j = await r.json();
      if (j && j.lan_ip) {
        const port = window.location.port ? `:${window.location.port}` : "";
        _lanOrigin = `${window.location.protocol}//${j.lan_ip}${port}`;
      } else {
        _lanOrigin = "";
      }
    } catch (_e) {
      _lanOrigin = "";
    }
    return _lanOrigin;
  }

  /** Render a scannable QR for ``text`` into ``container`` (offline, via
   *  the vendored qrcode-generator global). Returns false if the lib is
   *  missing or encoding fails. */
  function renderQrInto(container, text) {
    container.innerHTML = "";
    if (typeof window.qrcode !== "function") return false;
    try {
      const qr = window.qrcode(0, "M");
      qr.addData(String(text));
      qr.make();
      container.innerHTML = qr.createImgTag(4, 8);
      const img = container.querySelector("img");
      if (img) {
        img.removeAttribute("width");
        img.removeAttribute("height");
        img.className = "cc-share-qr-img";
        img.alt = "Scan to join on your phone";
      }
      return true;
    } catch (_e) {
      return false;
    }
  }

  /** Tunnel helper modal: shown when on localhost, guides user to start
   *  cloudflared for reliable multiplayer. */
  function showTunnelHelperModal(sid, humans) {
    const overlay = document.createElement("div");
    overlay.className = "cc-share-overlay";
    const card = document.createElement("div");
    card.className = "cc-share-card";
    
    const title = document.createElement("div");
    title.className = "cc-share-title";
    title.textContent = "// MULTIPLAYER TUNNEL REQUIRED";
    
    const warning = document.createElement("div");
    warning.className = "cc-share-sub";
    warning.style.color = "#FF8A1E";
    warning.style.marginBottom = "16px";
    warning.innerHTML = `⚠️ You're browsing on <code>localhost</code> — multiplayer links won't work reliably.<br>Your firewall blocks incoming connections (even same WiFi).`;
    
    const solution = document.createElement("div");
    solution.className = "cc-share-sub";
    solution.style.marginBottom = "12px";
    solution.innerHTML = `<strong>Solution:</strong> Start a Cloudflare quick tunnel (free, no account needed):`;
    
    const commandBox = document.createElement("div");
    commandBox.style.cssText = "background:rgba(0,0,0,0.4);border:1px solid rgba(255,255,255,0.2);border-radius:4px;padding:12px;margin:12px 0;font-family:monospace;font-size:13px;";
    const commandText = document.createElement("div");
    commandText.textContent = "cloudflared tunnel --url http://localhost:8000";
    commandText.style.marginBottom = "8px";
    const commandCopy = document.createElement("button");
    commandCopy.type = "button";
    commandCopy.className = "cli-btn";
    commandCopy.textContent = "[ COPY COMMAND ]";
    commandCopy.style.fontSize = "11px";
    commandCopy.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText("cloudflared tunnel --url http://localhost:8000");
        commandCopy.textContent = "[ COPIED ]";
        setTimeout(() => { commandCopy.textContent = "[ COPY COMMAND ]"; }, 1500);
      } catch (e) {}
    });
    commandBox.appendChild(commandText);
    commandBox.appendChild(commandCopy);
    
    const steps = document.createElement("div");
    steps.className = "cc-share-sub";
    steps.style.fontSize = "12px";
    steps.style.marginTop = "12px";
    steps.innerHTML = `
      <strong>Then:</strong><br>
      1. Run the command above in a terminal<br>
      2. Copy the <code>https://random-words.trycloudflare.com</code> URL it prints<br>
      3. Open that URL in this browser (replace localhost)<br>
      4. Create your game from the tunnel URL — QR codes will work everywhere
    `;
    
    card.appendChild(title);
    card.appendChild(warning);
    card.appendChild(solution);
    card.appendChild(commandBox);
    card.appendChild(steps);
    
    const btnRow = document.createElement("div");
    btnRow.style.cssText = "display:flex;gap:8px;margin-top:20px;";
    
    const proceedAnyway = document.createElement("button");
    proceedAnyway.type = "button";
    proceedAnyway.className = "cli-btn";
    proceedAnyway.textContent = "[ SHOW LINKS ANYWAY ]";
    proceedAnyway.style.opacity = "0.6";
    proceedAnyway.addEventListener("click", () => {
      if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
      showShareLinksModalDirect(sid, humans);
    });
    
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "cli-btn";
    cancel.textContent = "[ CANCEL ]";
    cancel.addEventListener("click", () => {
      if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
    });
    
    btnRow.appendChild(proceedAnyway);
    btnRow.appendChild(cancel);
    card.appendChild(btnRow);
    
    overlay.appendChild(card);
    document.body.appendChild(overlay);
  }

  /** Post-spawn invite modal: one copyable link + scannable QR per human
   *  seat, addressed to the host's LAN IP so a phone can join. */
  function showShareLinksModalDirect(sid, humans) {
    const overlay = document.createElement("div");
    overlay.className = "cc-share-overlay";
    const card = document.createElement("div");
    card.className = "cc-share-card";
    const title = document.createElement("div");
    title.className = "cc-share-title";
    title.textContent = "// INVITE PLAYERS";
    const sub = document.createElement("div");
    sub.className = "cc-share-sub";
    sub.textContent = `You are ${playerTag(humans[0])} (${playerDisplayName(
      humans[0],
    )}). Scan a seat's QR on a phone (same Wi-Fi) or copy its link.`;
    card.appendChild(title);
    card.appendChild(sub);

    // Build the rows first against the page origin; once the LAN origin
    // resolves we rewrite the links + QR so they're phone-reachable.
    const rows = humans.map((seat, ix) => {
      const link = shareLinkFor(sid, seat);
      const row = document.createElement("div");
      row.className = "cc-share-row";
      const tag = document.createElement("span");
      tag.className = "cc-share-seat";
      tag.style.setProperty("--cc-seat", ownerColour(seat));
      tag.textContent = `${playerTag(seat)} · ${playerDisplayName(seat)}${
        ix === 0 ? " (you)" : ""
      }`;
      const input = document.createElement("input");
      input.className = "cc-share-input";
      input.readOnly = true;
      input.value = link;
      const copyBtn = document.createElement("button");
      copyBtn.type = "button";
      copyBtn.className = "cli-btn cc-share-copy";
      copyBtn.textContent = "[ COPY ]";
      copyBtn.addEventListener("click", async () => {
        try {
          await navigator.clipboard.writeText(input.value);
        } catch (_e) {
          input.select();
          try { document.execCommand("copy"); } catch (_e2) {}
        }
        copyBtn.textContent = "[ COPIED ]";
        setTimeout(() => {
          copyBtn.textContent = "[ COPY ]";
        }, 1500);
      });
      const top = document.createElement("div");
      top.className = "cc-share-row-top";
      top.appendChild(tag);
      top.appendChild(input);
      top.appendChild(copyBtn);
      const qr = document.createElement("div");
      qr.className = "cc-share-qr";
      renderQrInto(qr, link);

      row.appendChild(top);
      row.appendChild(qr);

      // v1.13 — the second "MOBILE ▶" link/QR pointing at /mobile is
      // gone with that fork. /play is responsive, so one link per seat
      // works on every device and there's nothing to pick between.
      card.appendChild(row);
      return { seat, input, qr };
    });

    const lanNote = document.createElement("div");
    lanNote.className = "cc-share-sub cc-share-lan-note";
    card.appendChild(lanNote);

    // Only rewrite links to the LAN IP when the page is being served from
    // loopback (``localhost`` / ``127.*`` / ``::1``). If you're already on a
    // routable host — a cloudflared/ngrok tunnel, or the LAN IP itself —
    // the current origin is what friends should use, so we leave the links
    // (which derive from ``window.location``) untouched. This is what makes
    // the QR "just work" for every new game when you play on the tunnel URL.
    const host = window.location.hostname;
    const isLoopback =
      host === "localhost" ||
      host === "127.0.0.1" ||
      host === "::1" ||
      host === "[::1]";

    if (!isLoopback) {
      lanNote.textContent = `Links point at ${window.location.origin} — works for anyone who can reach this address.`;
    } else {
      lanNote.textContent = "↻ resolving your network address…";
      void fetchLanOrigin().then((origin) => {
        if (origin) {
          rows.forEach(({ seat, input, qr }) => {
            const lanUrl = buildSeatUrl(origin, sid, seat);
            input.value = lanUrl;
            renderQrInto(qr, lanUrl);
          });
          lanNote.textContent = `Links point at ${origin} — phones must be on the same Wi-Fi. For remote players, run a tunnel and open the laptop on its URL.`;
        } else {
          lanNote.textContent =
            "Couldn't detect a LAN address — links use this machine's origin. On another device, swap in this computer's IP (or use a tunnel).";
        }
      });
    }

    const close = document.createElement("button");
    close.type = "button";
    close.className = "cli-btn cc-share-close";
    close.textContent = "[ START PLAYING ]";
    close.addEventListener("click", () => {
      if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
    });
    card.appendChild(close);
    overlay.appendChild(card);
    document.body.appendChild(overlay);
  }

  /** Smart multiplayer modal: detects localhost and shows tunnel helper,
   *  otherwise shows invite links directly. */
  function showShareLinksModal(sid, humans) {
    const host = window.location.hostname;
    const isLoopback =
      host === "localhost" ||
      host === "127.0.0.1" ||
      host === "::1" ||
      host === "[::1]";
    
    if (isLoopback) {
      showTunnelHelperModal(sid, humans);
    } else {
      showShareLinksModalDirect(sid, humans);
    }
  }

  /** After spawning a game: if 2+ human seats, bind the host to the first
   *  one, start cross-browser sync, and surface the invite links. Solo
   *  games (one human) keep the original single-browser flow untouched. */
  function maybeOfferShareLinks(respBody) {
    const players = Array.isArray(respBody?.players) ? respBody.players : [];
    const agents =
      respBody?.agents && typeof respBody.agents === "object"
        ? respBody.agents
        : {};
    const humans = players.filter(
      (p) => String(agents[p] || "human").toLowerCase() === "human",
    );
    if (humans.length < 2) {
      _multiHumanGame = false;
      updateSeatIdentityBadge();
      stopLiveSync();
      return;
    }
    _multiHumanGame = true;
    setMySeat(humans[0]);
    startLiveSync();
    showShareLinksModal(respBody.session_id, humans);
  }

  /** Boot a friend's shareable seat link into a live, playable surface. */
  async function bootJoinMode() {
    const id = WATCH_SESSION_ID;
    if (!id) {
      if (phaseLine) phaseLine.textContent = "! no session id in link";
      return;
    }
    sessionId = id;
    if (phaseLine) phaseLine.textContent = "# joining session…";
    let st = null;
    try {
      const res = await fetch(`/api/game/${id}/status`, { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      st = await res.json();
    } catch (e) {
      sessionId = null;
      if (phaseLine) phaseLine.textContent = `! join failed · ${e?.message || e}`;
      if (mapPlayer) paintPlaceholder(mapPlayer, "# session not found");
      return;
    }
    const players = Array.isArray(st.players) ? st.players : [];
    const agents =
      st.agents && typeof st.agents === "object" ? st.agents : {};
    const humans = players.filter(
      (p) => String(agents[p] || "human").toLowerCase() === "human",
    );
    _multiHumanGame = humans.length >= 2;
    const seatOk =
      players.includes(MY_SEAT) &&
      String(agents[MY_SEAT] || "human").toLowerCase() === "human";
    if (!seatOk) {
      const picked = await promptSeatPicker(humans.length ? humans : players);
      if (!picked) {
        if (phaseLine) phaseLine.textContent = "# pick a seat to join";
        return;
      }
      setMySeat(picked);
    } else {
      applySeatIdentity();
    }
    try {
      await pullAllMaps();
      activateCcTab(String(st.phase) === "orbit" ? "orbit" : "orders");
      syncMobileOrdersBar();
    } catch (e) {
      if (phaseLine) phaseLine.textContent = `! ${e?.message || e}`;
      if (mapPlayer) paintPlaceholder(mapPlayer, "# error joining session");
      return;
    }
    startLiveSync();
  }

  // ── Standing live-sync poller (multiplayer) ─────────────────────────
  let liveSyncTimer = null;
  let liveSyncSig = "";
  let liveSyncBusy = false;
  /** v1.7 — last-seen day / phase / replay-window count, so the poller can
   *  tell a real night/orbit RESOLUTION (day rolled, phase flipped, or new
   *  night frames landed) apart from a mere opponent lock (pending flip).
   *  Only a real resolution drives the reveal/cinematic. */
  let liveSyncDay = 0;
  let liveSyncPhase = "";
  let liveSyncWindows = 0;

  function statusSignature(st) {
    if (!st) return "";
    const pend =
      st.pending && typeof st.pending === "object"
        ? Object.keys(st.pending)
            .sort()
            .map((k) => `${k}:${st.pending[k] ? 1 : 0}`)
            .join(",")
        : "";
    return `${st.day}|${st.phase}|${pend}|${st.replay_windows || 0}`;
  }

  function startLiveSync() {
    if (liveSyncTimer) return;
    liveSyncSig = "";
    liveSyncDay = 0;
    liveSyncPhase = "";
    liveSyncWindows = 0;
    liveSyncTimer = window.setInterval(pollLiveSync, 2500);
  }

  function stopLiveSync() {
    if (liveSyncTimer) {
      window.clearInterval(liveSyncTimer);
      liveSyncTimer = null;
    }
    const strip = document.getElementById("cc-waiting-strip");
    if (strip) strip.hidden = true;
  }

  // ── Agent-thinking poller (solo human-vs-bot) ───────────────────────
  // Multi-human games already poll /status via ``pollLiveSync`` (which now
  // paints the agent-thinking pill). A SOLO human-vs-bot game has no such
  // poller, so the pill would never tick while the human deliberates. This
  // lightweight poller ONLY refreshes the pill — it deliberately does no
  // resolution / cinematic work, so it can't race the solo submit flow.
  let agentPollTimer = null;

  function startAgentPoll() {
    if (agentPollTimer || liveSyncTimer) return; // liveSync already covers it
    agentPollTimer = window.setInterval(pollAgentThinking, 2000);
  }

  function stopAgentPoll() {
    if (agentPollTimer) {
      window.clearInterval(agentPollTimer);
      agentPollTimer = null;
    }
  }

  async function pollAgentThinking() {
    if (!sessionId || WATCH_MODE || liveSyncTimer) return;
    if (inFlightSubmit || document.hidden) return;
    try {
      const res = await fetch(`/api/game/${sessionId}/status`, {
        cache: "no-store",
      });
      if (!res.ok) return;
      const st = await res.json();
      renderAgentThinking(st);
    } catch (_e) {
      /* transient — retry next tick */
    }
  }

  async function pollLiveSync() {
    if (!sessionId || WATCH_MODE) return;
    // Never fight the submit's own refresh, an in-flight poll, or a cinematic
    // that's mid-play (the latter would half-paint / cancel the animation —
    // this was the "breaks for every player except the last" symptom, bug #4).
    if (liveSyncBusy || inFlightSubmit || _liveFxPlaying) return;
    if (document.hidden) return;
    liveSyncBusy = true;
    try {
      const res = await fetch(`/api/game/${sessionId}/status`, {
        cache: "no-store",
      });
      if (!res.ok) return;
      const st = await res.json();
      renderWaitingStrip(st);
      renderAgentThinking(st);
      // Keep the committed "waiting for players" overlay's who-list fresh.
      if (_awaitingHumanResolution) renderHumanWaitFrame(st);
      const sig = statusSignature(st);
      if (!sig || sig === liveSyncSig) return;
      const first = liveSyncSig === "";
      const prevDay = liveSyncDay;
      const prevPhase = liveSyncPhase;
      const prevWindows = liveSyncWindows;
      liveSyncSig = sig;
      liveSyncDay = Number(st.day || 0);
      liveSyncPhase = String(st.phase || "");
      liveSyncWindows = Number(st.replay_windows || 0);
      // First sample just seeds the baseline; never act on it. Also stay out
      // of the way while the user is scrubbing replay frames.
      if (first || mainMapSource !== "live") return;
      // A fresh night/orbit RESOLVED only when a new replay window (night
      // frames) landed, a new day rolled, or the phase flipped (orbit→planning
      // resolves without new night frames). That's the sole signal that drives
      // the reveal/cinematic (``pullAllMaps`` still frame-gates the actual
      // animation so the resolver never double-plays). A bare opponent-lock
      // (pending flip, same day/phase) must NOT trigger a cinematic or a
      // jarring full reveal — it only refreshes the waiting strip + phase line.
      const nightLanded =
        liveSyncWindows > prevWindows ||
        liveSyncDay > prevDay ||
        liveSyncPhase !== prevPhase;
      if (nightLanded) {
        if (_awaitingHumanResolution) clearHumanWaitFrame();
        await pullAllMaps({ playFx: true, stageOrbitBeat: true });
        // Safety net: the cinematic's reveal drops the resolving overlay on
        // the happy path (idempotent here); this covers an interrupted /
        // FX-off cinematic so a committed-wait frame can't get stuck up.
        endResolvingFrame();
      } else {
        await refreshStatus();
      }
    } catch (_e) {
      /* transient — retry next tick */
    } finally {
      liveSyncBusy = false;
    }
  }

  /** Human seats (excluding us) that haven't locked yet this phase. */
  function _otherHumansPending(st) {
    const humans = humanSeatsFromState(st);
    if (humans.length < 2) return [];
    const pend = st?.pending || {};
    return humans.filter((p) => p !== MY_SEAT && !pend[p]);
  }

  /** v1.7 — commit the player into a "locked in · waiting for other humans"
   *  frame after a non-resolving multi-human submit. Keeps the resolving
   *  overlay up (no bounce to the composer, bug #3) and freezes the transmit
   *  feed on a persistent waiting line. Cleared by ``clearHumanWaitFrame``
   *  once the live-sync poller sees the night/orbit resolve. */
  function enterHumanWaitFrame(progress, mode) {
    _awaitingHumanResolution = true;
    _awaitingHumanMode = mode || "praxis";
    _humanWaitProgress = progress || null;
    // Freeze the synthetic "warehouse cold start?" timeline + its /status
    // poll (misleading — we're waiting on a human, not on Snowflake) but
    // keep the lines the user already saw.
    try { _humanWaitProgress?.stop?.({ keepLines: true }); } catch (_e) { /* noop */ }
    startLiveSync();
    renderHumanWaitFrame();
  }

  /** Paint the committed-wait headline from ``_waitAgent`` / ``_waitHumans``.
   *  Called every 500ms by ``_waitTicker`` so the agent countdown ticks live
   *  between the (2.5s) status polls. */
  function _paintWaitHeadline() {
    const recapHead = document.querySelector(".cc-resolving-recap-head");
    if (!recapHead) return;
    let txt;
    if (_waitHumans.length) {
      txt = `LOCKED IN — waiting for ${_waitHumans.join(", ")}`;
    } else if (_waitAgent) {
      const a = String(_waitAgent.agent || "agent").toUpperCase();
      if (_waitAgent.baseMs == null) {
        txt = `LOCKED IN — ${a} is starting…`;
      } else {
        const secs = Math.max(
          0, Math.round((performance.now() - _waitAgent.baseMs) / 1000),
        );
        const cap = Math.round(
          (_waitAgent.capMs || _AGENT_CAP_MS_FALLBACK) / 1000,
        );
        txt = secs >= cap
          ? `LOCKED IN — ${a} over budget · auto-playing…`
          : `LOCKED IN — waiting on ${a} · ${secs}s / ~${cap}s`;
      }
    } else {
      txt = "LOCKED IN — resolving…";
    }
    recapHead.textContent = txt;
  }

  /** Repaint the committed-wait frame. Works for BOTH a multi-human wait
   *  (other humans still plotting) and a solo human-vs-agent wait (the agent
   *  is thinking). ``st.waiting_on`` / ``st.bot_turn`` drive the "who". */
  function renderHumanWaitFrame(st) {
    if (!_awaitingHumanResolution) return;
    const others = st ? _otherHumansPending(st) : [];
    if (others.length) {
      _waitHumans = others.map(seatLabel);
      _waitAgent = null;
    } else {
      // No other humans pending → we're waiting on the agent (if any).
      _waitHumans = [];
      const bt = st && st.bot_turn;
      const waiting = (st && st.waiting_on) || [];
      const pendingBot = waiting.find((w) => w && !w.is_human);
      if (bt) {
        _waitAgent = {
          agent: bt.agent,
          seat: bt.seat,
          baseMs: performance.now() - (Number(bt.elapsed_ms) || 0),
          capMs: Number(bt.cap_ms) || _AGENT_CAP_MS_FALLBACK,
        };
      } else if (pendingBot) {
        // Agent hasn't started its turn yet (worker about to fire it).
        _waitAgent = {
          agent: pendingBot.agent, seat: pendingBot.seat,
          baseMs: null, capMs: _AGENT_CAP_MS_FALLBACK,
        };
      } else {
        _waitAgent = null; // everyone in — just resolving
      }
    }
    _paintWaitHeadline();
    if (!_waitTicker) _waitTicker = setInterval(_paintWaitHeadline, 500);
    if (_humanWaitProgress) {
      _humanWaitProgress.pushLine(
        "human-wait",
        _waitAgent
          ? `\u2713 you locked in · the agent is finishing its turn`
          : `\u2713 you locked in · waiting for other players`,
        "ok",
        "you",
      );
    }
  }

  /** Reset the committed-wait state + re-enable the composers. The resolution
   *  cinematic (``_playNightCinematic`` → ``endResolvingFrame``) drops the
   *  overlay itself; this just clears the latch so the next phase is live. */
  function clearHumanWaitFrame() {
    _awaitingHumanResolution = false;
    _humanWaitProgress = null;
    if (_waitTicker) { clearInterval(_waitTicker); _waitTicker = null; }
    _waitAgent = null;
    _waitHumans = [];
    if (soloCommitBtn) soloCommitBtn.disabled = false;
    if (orbitCommitBtn) orbitCommitBtn.disabled = false;
  }

  /** Short phase-line suffix once we've locked but other humans haven't. */
  function waitingForLabel(st) {
    const humans = humanSeatsFromState(st);
    if (humans.length < 2) return "";
    const pend = st?.pending || {};
    const others = humans.filter((p) => p !== MY_SEAT && !pend[p]);
    if (!others.length) return "resolving…";
    return `waiting for: ${others.map(seatLabel).join(", ")}`;
  }

  /** Bottom "who has locked" strip for a multi-human game. */
  function renderWaitingStrip(st) {
    const humans = humanSeatsFromState(st);
    let el = document.getElementById("cc-waiting-strip");
    if (humans.length < 2 || String(st?.phase) === "season_complete") {
      if (el) el.hidden = true;
      return;
    }
    if (!el) {
      el = document.createElement("div");
      el.id = "cc-waiting-strip";
      el.className = "cc-waiting-strip";
      document.body.appendChild(el);
    }
    const pend = st?.pending || {};
    const chips = humans
      .map((p) => {
        const locked = !!pend[p];
        const me = p === MY_SEAT ? " (you)" : "";
        return (
          `<span class="cc-waiting-chip ${
            locked ? "is-locked" : "is-pending"
          }" style="--cc-seat:${ownerColour(p)}">` +
          `${locked ? "\u2713" : "\u2026"} ${seatLabel(p)}${me}</span>`
        );
      })
      .join("");
    const phaseLabel = String(st?.phase) === "orbit" ? "ORBIT" : "PRAXIS";
    el.innerHTML =
      `<span class="cc-waiting-strip__label">${phaseLabel} · day ${
        st?.day ?? "?"
      }</span>` + chips;
    el.hidden = false;
  }

  // ── Agent-thinking indicator ("who is being waited on" + live timer) ──
  // An LLM harness seat (e.g. tabula_v12) takes ~30-80s per turn. The
  // server pre-fires it in the background while the human deliberates and
  // reports the in-flight turn via ``status.bot_turn`` (seat + elapsed_ms).
  // We surface that as a small pill with a client-ticked seconds counter so
  // the human can see the agent is already working — and how long on it.
  let _agentThinkTimer = null;
  let _agentThinkBaseMs = 0; // performance.now() anchored to server elapsed
  let _agentThinkSeat = "";
  let _agentThinkAgent = "";
  let _agentThinkCapMs = 80_000; // per-turn ceiling hint from the server

  const _HEURISTIC_AGENT_LABELS = new Set(["human", "red_harvest", "heuristic"]);

  /** True when any seat runs a slow (Cortex/harness) agent. */
  function _hasSlowBotSeat(agents) {
    if (!agents || typeof agents !== "object") return false;
    return Object.values(agents).some((a) => {
      const s = String(a || "").trim().toLowerCase();
      return s && !_HEURISTIC_AGENT_LABELS.has(s);
    });
  }

  function _agentThinkEl() {
    let el = document.getElementById("cc-agent-thinking");
    if (!el) {
      el = document.createElement("div");
      el.id = "cc-agent-thinking";
      el.className = "cc-agent-thinking";
      el.hidden = true;
      document.body.appendChild(el);
    }
    return el;
  }

  function _paintAgentThinking() {
    const el = document.getElementById("cc-agent-thinking");
    if (!el || el.hidden) return;
    const secs = Math.max(
      0,
      Math.round((performance.now() - _agentThinkBaseMs) / 1000),
    );
    const cap = Math.round((_agentThinkCapMs || _AGENT_CAP_MS_FALLBACK) / 1000);
    const overBudget = secs >= cap;
    const agent = (_agentThinkAgent || "agent").toUpperCase();
    const who = _agentThinkSeat ? seatLabel(_agentThinkSeat) : "";
    el.innerHTML =
      `<span class="cc-agent-thinking__spin" aria-hidden="true"></span>` +
      `<span class="cc-agent-thinking__who" style="--cc-seat:${ownerColour(
        _agentThinkSeat,
      )}">${esc(agent)}${who ? " · " + esc(who) : ""}</span>` +
      `<span class="cc-agent-thinking__msg">${
        overBudget ? "finalizing" : "thinking"
      }</span>` +
      `<span class="cc-agent-thinking__timer">${secs}s / ~${cap}s</span>`;
  }

  function stopAgentThinking() {
    if (_agentThinkTimer) {
      clearInterval(_agentThinkTimer);
      _agentThinkTimer = null;
    }
    const el = document.getElementById("cc-agent-thinking");
    if (el) el.hidden = true;
    _agentThinkSeat = "";
    _agentThinkAgent = "";
  }

  /** Show/refresh the "agent is thinking · Ns" pill from ``status.bot_turn``. */
  function renderAgentThinking(st) {
    const turn = st && st.bot_turn;
    // During a committed wait the resolving overlay shows the countdown
    // (``renderHumanWaitFrame``), so hide the bottom pill to avoid doubling.
    if (!turn || _awaitingHumanResolution ||
        String(st?.phase) === "season_complete") {
      stopAgentThinking();
      return;
    }
    // Re-anchor the client baseline to the server's reported elapsed each
    // poll so the ticker stays truthful without drifting between polls.
    const elapsed = Number(turn.elapsed_ms) || 0;
    _agentThinkBaseMs = performance.now() - elapsed;
    _agentThinkSeat = String(turn.seat || "");
    _agentThinkAgent = String(turn.agent || "");
    _agentThinkCapMs = Number(turn.cap_ms) || _AGENT_CAP_MS_FALLBACK;
    const el = _agentThinkEl();
    el.hidden = false;
    _paintAgentThinking();
    if (!_agentThinkTimer) {
      _agentThinkTimer = setInterval(_paintAgentThinking, 500);
    }
  }

  /** Populate watcher meta line with season summary so the user can
   * see which season is loaded at a glance.
   * @param {Object} row
   */
  function renderWatcherMeta(row) {
    if (!watchPickerMetaEl) return;
    if (!row) {
      watchPickerMetaEl.textContent = "";
      return;
    }
    const shortId = row.session_id.slice(0, 8);
    const name = row.season_name ? `${row.season_name} · ${shortId}` : shortId;
    const day = String(row.day || 0);
    watchPickerMetaEl.textContent =
      `${name} · day ${day} · ${formatSeasonScores(row)}` +
      (row.phase === "season_complete" ? " · season_complete" : "");
  }

  /** Resolve a season slug to a session_id via the cached payload.
   * Returns "" when the slug doesn't match any persisted season.
   * @param {string} slug
   * @param {Array<Object>} sessions
   */
  function resolveSlug(slug, sessions) {
    if (!slug) return "";
    const target = String(slug).toLowerCase();
    for (const row of sessions) {
      if ((row.season_slug || "").toLowerCase() === target) {
        return row.session_id;
      }
    }
    return "";
  }

  /** Phase C bootstrap. Fetches the season list, populates the picker,
   * resolves whichever URL signal the user arrived with, and loads
   * that specific season's replay. */
  async function bootWatcherMode() {
    if (watchPickerWrap) watchPickerWrap.hidden = false;
    const body = await fetchSeasonList();
    const sessions = body.sessions || [];
    let targetId = WATCH_SESSION_ID;
    if (!targetId && WATCH_SEASON_SLUG) {
      targetId = resolveSlug(WATCH_SEASON_SLUG, sessions);
      if (!targetId && phaseLine) {
        phaseLine.textContent = `! season slug "${WATCH_SEASON_SLUG}" not found`;
      }
    }
    if (!targetId && sessions.length) {
      // No specific selection — default to the most recently played
      // (the list is sorted ``last_touched_at DESC`` by the backend).
      // Skip fixtures: a capture batch leaves hundreds of them at the top
      // of the list and landing on one is never what a watcher wanted.
      const firstReal = sessions.find((s) => String(s.kind || "season") === "season");
      targetId = (firstReal || sessions[0]).session_id;
    }
    renderSeasonPicker(sessions, targetId);
    if (watchFixturesEl) {
      watchFixturesEl.addEventListener("change", () => {
        renderSeasonPicker(sessions, watchPickerEl ? watchPickerEl.value : targetId);
      });
    }
    const activeRow = sessions.find((s) => s.session_id === targetId);
    renderWatcherMeta(activeRow || null);
    if (targetId) {
      await loadWatcherSession(targetId);
    } else if (mapPlayer) {
      paintPlaceholder(mapPlayer, "# no persisted seasons — run scripts/run_season.py");
    }
    // Wire the picker change handler — switching season reloads with
    // a fresh ?session= query so the deep-link is shareable.
    if (watchPickerEl) {
      watchPickerEl.addEventListener("change", () => {
        const sid = watchPickerEl.value;
        if (!sid) return;
        const opt = watchPickerEl.options[watchPickerEl.selectedIndex];
        // v1.0 — a RESUME pick re-enters the game as a playable seat;
        // a REPLAY pick stays in the read-only watcher.
        if (opt && opt.dataset && opt.dataset.resumable === "1") {
          void resumeSession(sid);
          return;
        }
        const url = new URL(window.location.href);
        url.searchParams.delete("season");
        url.searchParams.delete("watch");
        url.searchParams.set("session", sid);
        window.location.href = url.toString();
      });
    }
    if (watchDeleteBtn) {
      watchDeleteBtn.addEventListener("click", () => {
        void deleteSelectedSeason();
      });
    }
  }

  /* ── Map zoom (dragger in the .cc-map-frame-head) ─────────────────
   *
   * The map cell width is declared in ``ch`` units so the entire grid
   * tracks the ``--map-font-size`` CSS variable. This slider clamps
   * between MAP_ZOOM_MIN/MAX and writes the value to the document
   * root + localStorage. Ctrl/Cmd + wheel over the map nudges it too
   * (preventing default scroll so the page doesn't jump).
   */

  /** @param {number} px */
  function clampZoom(px) {
    if (!Number.isFinite(px)) return MAP_ZOOM_DEFAULT;
    return Math.max(MAP_ZOOM_MIN, Math.min(MAP_ZOOM_MAX, Math.round(px)));
  }

  /** @param {number} px */
  function applyMapZoom(px) {
    const clamped = clampZoom(px);
    document.documentElement.style.setProperty(
      "--map-font-size",
      `${String(clamped)}px`,
    );
    if (mapZoomSliderEl && Number(mapZoomSliderEl.value) !== clamped) {
      mapZoomSliderEl.value = String(clamped);
    }
    if (mapZoomReadoutEl) {
      const pct = Math.round((clamped / MAP_ZOOM_DEFAULT) * 100);
      mapZoomReadoutEl.textContent = `${String(pct)}%`;
    }
    try {
      localStorage.setItem(MAP_ZOOM_KEY, String(clamped));
    } catch (_) {
      /* ignore — private mode etc. */
    }
    // v0.9.13 — cells resized; re-anchor the planned-orders overlay once
    // layout settles so badges/legs track the new cell geometry.
    if (typeof requestAnimationFrame === "function") {
      requestAnimationFrame(() => {
        try { paintPlannedOrdersOverlay(); } catch (_e) { /* non-fatal */ }
      });
    }
    // The blue-sign overlay is positioned in absolute pixels snapshotted
    // from the cell rects, so a zoom change (which resizes cells via
    // --map-font-size) leaves it stranded. Repaint it against the
    // freshly-laid-out grid so it tracks the zoom. requestAnimationFrame
    // lets the CSS reflow settle first.
    if (mainMapSource === "live") {
      requestAnimationFrame(() => {
        try { paintBlueSignOverlay(lastBlueSign); } catch (_e) {}
      });
    }
    // The redsign pulse overlay is likewise pixel-anchored, and it renders
    // in BOTH live and replay — re-anchor it after any resize/zoom.
    requestAnimationFrame(() => {
      try { paintRedsignOverlay(); } catch (_e) {}
    });
  }

  // Optional station UI hook — expose zoom controls so station.js can set a
  // fit-to-width baseline as "100%". No effect when the station UI is off.
  window._osApplyMapZoom      = applyMapZoom;
  window._osSetMapZoomDefault = (px) => { MAP_ZOOM_DEFAULT = clampZoom(px); };

  /** @param {number} delta */
  function nudgeMapZoom(delta) {
    const cur = clampZoom(
      mapZoomSliderEl ? Number(mapZoomSliderEl.value) : MAP_ZOOM_DEFAULT,
    );
    applyMapZoom(cur + delta);
  }

  try {
    const saved = localStorage.getItem(MAP_ZOOM_KEY);
    if (saved !== null) {
      const n = Number.parseInt(saved, 10);
      if (Number.isFinite(n)) applyMapZoom(n);
      else applyMapZoom(MAP_ZOOM_DEFAULT);
    } else {
      applyMapZoom(MAP_ZOOM_DEFAULT);
    }
  } catch (_) {
    applyMapZoom(MAP_ZOOM_DEFAULT);
  }

  mapZoomSliderEl?.addEventListener("input", () => {
    applyMapZoom(Number(mapZoomSliderEl.value));
  });
  mapZoomInBtn?.addEventListener("click", () => nudgeMapZoom(+2));
  mapZoomOutBtn?.addEventListener("click", () => nudgeMapZoom(-2));

  // Keep the absolutely-positioned blue-sign overlay aligned when the
  // window (and therefore the grid) reflows.
  let _blueSignResizeRaf = 0;
  window.addEventListener("resize", () => {
    if (_blueSignResizeRaf) cancelAnimationFrame(_blueSignResizeRaf);
    _blueSignResizeRaf = requestAnimationFrame(() => {
      _blueSignResizeRaf = 0;
      if (mainMapSource === "live") {
        try { paintBlueSignOverlay(lastBlueSign); } catch (_e) {}
      }
      try { paintRedsignOverlay(); } catch (_e) {}
    });
  });

  // Ctrl/Cmd + wheel over the map = zoom (matches OS conventions).
  // We attach to the host directly so we don't fight the page's
  // normal scroll wheel anywhere else.
  if (mapHostMainEl) {
    mapHostMainEl.addEventListener(
      "wheel",
      (ev) => {
        if (!ev.ctrlKey && !ev.metaKey) return;
        ev.preventDefault();
        // deltaY > 0 → scrolling down → smaller; negate for natural feel.
        const step = ev.deltaY > 0 ? -1 : +1;
        nudgeMapZoom(step);
      },
      { passive: false },
    );
  }

  // ── Touch gestures on the player map ───────────────────────────
  //
  // One finger pans via the host's native ``overflow: auto`` scroll
  // (``touch-action: pan-x pan-y`` is set in CSS). Two fingers pinch to
  // zoom: because the grid is sized by ``--map-font-size`` (not a CSS
  // transform), we map the pinch distance ratio onto the font size and
  // route it through ``applyMapZoom`` so cells + overlays stay in sync.
  // A trailing synthetic click after any pan/pinch is suppressed via
  // ``_suppressNextMapClick`` so gestures never deploy a stray order.
  if (mapHostMainEl && typeof window.PointerEvent === "function") {
    const _pts = new Map();
    let _pinchStartDist = 0;
    let _pinchStartFont = MAP_ZOOM_DEFAULT;
    let _didPinch = false;
    let _downX = 0;
    let _downY = 0;
    let _moved = false;
    const TAP_SLOP = 10; // px before a single-finger touch counts as a drag

    const _pinchDist = () => {
      const a = Array.from(_pts.values());
      if (a.length < 2) return 0;
      return Math.hypot(a[0].x - a[1].x, a[0].y - a[1].y);
    };

    mapHostMainEl.addEventListener(
      "pointerdown",
      (ev) => {
        if (ev.pointerType !== "touch") return;
        _pts.set(ev.pointerId, { x: ev.clientX, y: ev.clientY });
        if (_pts.size === 1) {
          _downX = ev.clientX;
          _downY = ev.clientY;
          _moved = false;
        } else if (_pts.size === 2) {
          _pinchStartDist = _pinchDist();
          _pinchStartFont = clampZoom(
            mapZoomSliderEl ? Number(mapZoomSliderEl.value) : MAP_ZOOM_DEFAULT,
          );
          _didPinch = true;
        }
      },
      { passive: true },
    );

    mapHostMainEl.addEventListener(
      "pointermove",
      (ev) => {
        if (ev.pointerType !== "touch" || !_pts.has(ev.pointerId)) return;
        _pts.set(ev.pointerId, { x: ev.clientX, y: ev.clientY });
        if (_pts.size >= 2 && _pinchStartDist > 0) {
          // Two-finger pinch — own the gesture (stop native scroll) and
          // resize the grid proportionally to the finger spread.
          ev.preventDefault();
          const ratio = _pinchDist() / _pinchStartDist;
          if (Number.isFinite(ratio) && ratio > 0) {
            applyMapZoom(_pinchStartFont * ratio);
          }
        } else if (_pts.size === 1 && !_moved) {
          if (
            Math.abs(ev.clientX - _downX) > TAP_SLOP ||
            Math.abs(ev.clientY - _downY) > TAP_SLOP
          ) {
            _moved = true;
          }
        }
      },
      { passive: false },
    );

    const _endPointer = (ev) => {
      if (ev.pointerType !== "touch" || !_pts.has(ev.pointerId)) return;
      _pts.delete(ev.pointerId);
      if (_pts.size < 2) _pinchStartDist = 0;
      if (_pts.size === 0) {
        // After a pinch or a single-finger drag, eat the trailing click.
        if (_didPinch || _moved) _suppressNextMapClick = true;
        _didPinch = false;
        _moved = false;
      }
    };
    mapHostMainEl.addEventListener("pointerup", _endPointer, { passive: true });
    mapHostMainEl.addEventListener("pointercancel", _endPointer, {
      passive: true,
    });

    // The planned-orders + blue-sign overlays are absolutely positioned
    // from cell rects, so a native pan (the grid scrolling inside the
    // host) would leave them stranded. Re-anchor them on scroll, rAF-
    // throttled so a fast drag stays smooth.
    let _mapScrollRaf = 0;
    mapHostMainEl.addEventListener(
      "scroll",
      () => {
        if (_mapScrollRaf) return;
        _mapScrollRaf = requestAnimationFrame(() => {
          _mapScrollRaf = 0;
          try { paintPlannedOrdersOverlay(); } catch (_e) { /* non-fatal */ }
          if (mainMapSource === "live") {
            try { paintBlueSignOverlay(lastBlueSign); } catch (_e) {}
          }
          try { paintRedsignOverlay(); } catch (_e) {}
        });
      },
      { passive: true },
    );
  }

  // Keyboard: Ctrl/Cmd + "+" / "-" / "0" (reset) — but only when the
  // user isn't typing into a text field, so we don't hijack browser zoom
  // while they're editing the orders JSON.
  document.addEventListener("keydown", (ev) => {
    if (!(ev.ctrlKey || ev.metaKey)) return;
    const tgt = ev.target;
    if (tgt instanceof HTMLElement) {
      const t = tgt.tagName;
      if (t === "INPUT" || t === "TEXTAREA" || tgt.isContentEditable) return;
    }
    if (ev.key === "+" || ev.key === "=") {
      ev.preventDefault();
      nudgeMapZoom(+2);
    } else if (ev.key === "-" || ev.key === "_") {
      ev.preventDefault();
      nudgeMapZoom(-2);
    } else if (ev.key === "0") {
      ev.preventDefault();
      applyMapZoom(MAP_ZOOM_DEFAULT);
    }
  });

  /* ── CRT (cosmetic shell) ─────────────────────────────────────── */

  function readCrtIntensity() {
    const v = Number(crtIntensityEl.value);
    if (Number.isFinite(v)) {
      return Math.max(0, Math.min(100, v)) / 100;
    }
    return 0.45;
  }

  function applyCrtCssVars(i01) {
    if (!crtViewport) return;
    crtViewport.style.setProperty("--crt-intensity", String(i01));
    const px = 0.35 + i01 * 1.85;
    crtViewport.style.setProperty("--crt-aberration", `${px.toFixed(2)}px`);
    const cv = Number(crtCurveEl?.value ?? 60);
    const c01 = Number.isFinite(cv) ? Math.max(0, Math.min(100, cv)) / 100 : 0.60;
    crtViewport.style.setProperty("--crt-curve", String(c01));
  }

  function syncCrtPointerChrome() {
    const fakePointer =
      Boolean(crtEl.checked) &&
      crtViewport?.classList.contains("crt-viewport--on") &&
      !reduceMotionMq.matches;
    if (crtViewport) {
      crtViewport.classList.toggle("crt-viewport--fake-pointer", fakePointer);
    }
    if (!fakePointer && crtCursorFollower) {
      crtCursorFollower.classList.remove("crt-cursor-follower--visible");
    }
  }

  function syncCrtUi() {
    const on = crtEl.checked;
    if (crtBox) {
      crtBox.textContent = on ? "[x]" : "[ ]";
    }
    const glitchOn = glitchEl?.checked ?? true;
    if (glitchBox) {
      glitchBox.textContent = glitchOn ? "[x]" : "[ ]";
    }
    try {
      localStorage.setItem(CRT_ON_KEY, on ? "1" : "0");
    } catch (_) {
      /* ignore */
    }
    const i01 = readCrtIntensity();
    try {
      localStorage.setItem(CRT_INTENSITY_KEY, String(Math.round(i01 * 100)));
    } catch (_) {
      /* ignore */
    }
    const cv = Number(crtCurveEl?.value ?? 60);
    const c01 = Number.isFinite(cv) ? Math.max(0, Math.min(100, cv)) / 100 : 0.60;
    try {
      localStorage.setItem(CRT_CURVE_KEY, String(Math.round(c01 * 100)));
    } catch (_) {
      /* ignore */
    }
    try {
      localStorage.setItem(CRT_GLITCH_KEY, glitchOn ? "1" : "0");
    } catch (_) {
      /* ignore */
    }
    applyCrtCssVars(i01);
    if (crtViewport) {
      crtViewport.classList.toggle("crt-viewport--on", on);
      if (!on) {
        crtViewport.classList.remove("crt-viewport--glitch");
      }
    }
    rescheduleCrtGlitch();
    syncCrtPointerChrome();
  }

  function clearGlitchSchedule() {
    if (glitchTimerId !== null) {
      window.clearTimeout(glitchTimerId);
      glitchTimerId = null;
    }
    if (crtViewport) {
      crtViewport.classList.remove("crt-viewport--glitch");
    }
  }

  function scheduleCrtGlitch() {
    if (glitchTimerId !== null) return;
    const glitchEnabled = glitchEl?.checked ?? true;
    if (!crtEl.checked || !glitchEnabled || reduceMotionMq.matches) return;

    const delayMs = 12000 + Math.random() * 33000;
    glitchTimerId = window.setTimeout(() => {
      glitchTimerId = null;
      const stillEnabled = glitchEl?.checked ?? true;
      if (!crtEl.checked || !stillEnabled || !crtViewport || reduceMotionMq.matches) return;
      crtViewport.classList.add("crt-viewport--glitch");
      // Hold long enough for the 320ms keyframe animation to complete.
      const hold = 280 + Math.random() * 140;
      window.setTimeout(() => {
        if (crtViewport) crtViewport.classList.remove("crt-viewport--glitch");
        // ~30% chance of a quick echo glitch — like a tape catching twice.
        if (Math.random() < 0.30) {
          const echoDelay = 80 + Math.random() * 100;
          window.setTimeout(() => {
            const echoEnabled = glitchEl?.checked ?? true;
            if (!crtEl.checked || !echoEnabled || !crtViewport || reduceMotionMq.matches) return;
            crtViewport.classList.add("crt-viewport--glitch");
            const echoHold = 180 + Math.random() * 80;
            window.setTimeout(() => {
              if (crtViewport) crtViewport.classList.remove("crt-viewport--glitch");
              scheduleCrtGlitch();
            }, echoHold);
          }, echoDelay);
        } else {
          scheduleCrtGlitch();
        }
      }, hold);
    }, delayMs);
  }

  function rescheduleCrtGlitch() {
    clearGlitchSchedule();
    if (crtEl.checked && !reduceMotionMq.matches) {
      scheduleCrtGlitch();
    }
  }

  try {
    const saved = localStorage.getItem(GRID_LINES_KEY);
    if (gridlinesEl && saved === "0") gridlinesEl.checked = false;
    if (gridlinesEl && saved === "1") gridlinesEl.checked = true;
  } catch (_) {
    /* ignore */
  }
  syncGridlinesClass();

  try {
    const empLullsSaved = localStorage.getItem(EMP_LULLS_KEY);
    if (empLullsEl) {
      if (empLullsSaved === "0") {
        empLullsEl.checked = false;
        if (empLullsBox) empLullsBox.textContent = "[ ]";
      } else {
        // default: checked
        empLullsEl.checked = true;
        if (empLullsBox) empLullsBox.textContent = "[x]";
      }
    }
  } catch (_) {
    /* ignore */
  }

  // v0.9.11 — load the two orbit-report settings. last-turn FX defaults ON;
  // auto-pop orbital reports now defaults OFF (inline station panels replace
  // the pop-ups) but an explicit opt-in in Settings is still honoured.
  try {
    const ltSaved = localStorage.getItem(LAST_TURN_FX_KEY);
    replayLastTurnFx = ltSaved !== "0";
    if (lastTurnFxEl) lastTurnFxEl.checked = replayLastTurnFx;
    if (lastTurnFxBox) lastTurnFxBox.textContent = replayLastTurnFx ? "[x]" : "[ ]";

    // Orbital reports now default to NO auto-pop (the inline station panels
    // surface the same detail). We still honour an explicit opt-in: if the
    // user has turned auto-pop ON in Settings, keep popping the reports.
    const apSaved = localStorage.getItem(AUTOPOP_REPORTS_KEY);
    orbitFlashEnabled = apSaved === "1";
    if (autoPopReportsEl) autoPopReportsEl.checked = orbitFlashEnabled;
    if (autoPopReportsBox) {
      autoPopReportsBox.textContent = orbitFlashEnabled ? "[x]" : "[ ]";
    }

    // v1.1 — cinematic title cards (default ON).
    const tcSaved = localStorage.getItem(TITLE_CARDS_KEY);
    titleCardsEnabled = tcSaved !== "0";
    if (titleCardsEl) titleCardsEl.checked = titleCardsEnabled;
    if (titleCardsBox) titleCardsBox.textContent = titleCardsEnabled ? "[x]" : "[ ]";

    // Orbit→surface launch sequencing (default ON).
    const osqSaved = localStorage.getItem(ORBIT_SEQ_KEY);
    window._osOrbitSeq = osqSaved !== "0";
    if (orbitSeqEl) orbitSeqEl.checked = window._osOrbitSeq;
    if (orbitSeqBox) orbitSeqBox.textContent = window._osOrbitSeq ? "[x]" : "[ ]";

    // Replay loop (default OFF) — stop at the last window unless enabled.
    const rlSaved = localStorage.getItem(REPLAY_LOOP_KEY);
    replayLoopEnabled = rlSaved === "1";
    if (replayLoopEl) replayLoopEl.checked = replayLoopEnabled;
    if (replayLoopBox) replayLoopBox.textContent = replayLoopEnabled ? "[x]" : "[ ]";

    // Replay end-of-timeline animation (default ON) — play the closing
    // settlement + victory + score card when the timeline ends without looping.
    const reaSaved = localStorage.getItem(REPLAY_END_ANIM_KEY);
    replayEndAnimEnabled = reaSaved !== "0";
    if (replayEndAnimEl) replayEndAnimEl.checked = replayEndAnimEnabled;
    if (replayEndAnimBox)
      replayEndAnimBox.textContent = replayEndAnimEnabled ? "[x]" : "[ ]";
  } catch (_) {
    /* ignore */
  }

  try {
    const crtSaved = localStorage.getItem(CRT_ON_KEY);
    if (crtEl && crtSaved === "1") crtEl.checked = true;
    if (crtEl && crtSaved === "0") crtEl.checked = false;
    const intSaved = localStorage.getItem(CRT_INTENSITY_KEY);
    if (intSaved !== null && crtIntensityEl) {
      const n = Number.parseInt(intSaved, 10);
      if (Number.isFinite(n)) {
        crtIntensityEl.value = String(Math.max(0, Math.min(100, n)));
      }
    }
    const curveSaved = localStorage.getItem(CRT_CURVE_KEY);
    if (curveSaved !== null && crtCurveEl) {
      const n = Number.parseInt(curveSaved, 10);
      if (Number.isFinite(n)) {
        crtCurveEl.value = String(Math.max(0, Math.min(100, n)));
      }
    }
    const glitchSaved = localStorage.getItem(CRT_GLITCH_KEY);
    if (glitchEl && glitchSaved === "0") glitchEl.checked = false;
    if (glitchEl && glitchSaved === "1") glitchEl.checked = true;
  } catch (_) {
    /* ignore */
  }
  syncCrtUi();

  gridlinesEl?.addEventListener("change", () => {
    syncGridlinesClass();
  });
  empLullsEl?.addEventListener("change", () => {
    if (empLullsBox) empLullsBox.textContent = empLullsEl.checked ? "[x]" : "[ ]";
    try { localStorage.setItem(EMP_LULLS_KEY, empLullsEl.checked ? "1" : "0"); } catch (_) { /* ignore */ }
  });
  // v0.9.11 — "replay last turn animation": gates the auto-play of the
  // just-resolved night animation in refreshNightReplay({playFx}).
  lastTurnFxEl?.addEventListener("change", () => {
    replayLastTurnFx = !!lastTurnFxEl.checked;
    if (lastTurnFxBox) lastTurnFxBox.textContent = replayLastTurnFx ? "[x]" : "[ ]";
    try { localStorage.setItem(LAST_TURN_FX_KEY, replayLastTurnFx ? "1" : "0"); } catch (_) { /* ignore */ }
  });
  // v0.9.11 — "show orbital summaries as pop-ups": gates the auto-pop
  // of the recap/briefing reports (live + replay synthetic ticks).
  autoPopReportsEl?.addEventListener("change", () => {
    orbitFlashEnabled = !!autoPopReportsEl.checked;
    if (autoPopReportsBox) {
      autoPopReportsBox.textContent = orbitFlashEnabled ? "[x]" : "[ ]";
    }
    try { localStorage.setItem(AUTOPOP_REPORTS_KEY, orbitFlashEnabled ? "1" : "0"); } catch (_) { /* ignore */ }
    applyAutoPopSetting();
  });
  // v1.1 — "show title cards": gates the NIGHT n / PRAXIS BEGINS cards.
  titleCardsEl?.addEventListener("change", () => {
    titleCardsEnabled = !!titleCardsEl.checked;
    if (titleCardsBox) titleCardsBox.textContent = titleCardsEnabled ? "[x]" : "[ ]";
    try { localStorage.setItem(TITLE_CARDS_KEY, titleCardsEnabled ? "1" : "0"); } catch (_) { /* ignore */ }
  });
  // "sequence orbit launch → surface": station launch plays before the
  // on-board landing (OFF = simultaneous). Drives window._osOrbitSeq.
  orbitSeqEl?.addEventListener("change", () => {
    window._osOrbitSeq = !!orbitSeqEl.checked;
    if (orbitSeqBox) orbitSeqBox.textContent = window._osOrbitSeq ? "[x]" : "[ ]";
    try { localStorage.setItem(ORBIT_SEQ_KEY, window._osOrbitSeq ? "1" : "0"); } catch (_) { /* ignore */ }
  });
  // "loop replay": wrap back to day 1 at the end of the timeline (OFF = stop
  // on the last available window).
  replayLoopEl?.addEventListener("change", () => {
    replayLoopEnabled = !!replayLoopEl.checked;
    if (replayLoopBox) replayLoopBox.textContent = replayLoopEnabled ? "[x]" : "[ ]";
    try { localStorage.setItem(REPLAY_LOOP_KEY, replayLoopEnabled ? "1" : "0"); } catch (_) { /* ignore */ }
  });
  // "play ending on replay": final settlement + victory + score card when the
  // timeline ends without looping.
  replayEndAnimEl?.addEventListener("change", () => {
    replayEndAnimEnabled = !!replayEndAnimEl.checked;
    if (replayEndAnimBox)
      replayEndAnimBox.textContent = replayEndAnimEnabled ? "[x]" : "[ ]";
    try { localStorage.setItem(REPLAY_END_ANIM_KEY, replayEndAnimEnabled ? "1" : "0"); } catch (_) { /* ignore */ }
  });
  crtEl?.addEventListener("change", syncCrtUi);
  crtIntensityEl?.addEventListener("input", syncCrtUi);
  crtCurveEl?.addEventListener("input", syncCrtUi);
  glitchEl?.addEventListener("change", () => {
    if (glitchEl.checked) {
      rescheduleCrtGlitch();
    } else {
      clearGlitchSchedule();
    }
    syncCrtUi();
  });

  reduceMotionMq.addEventListener("change", () => {
    rescheduleCrtGlitch();
    syncCrtUi();
  });

  if (crtViewport && crtCursorFollower) {
    crtViewport.addEventListener("pointermove", (ev) => {
      if (!crtViewport.classList.contains("crt-viewport--fake-pointer")) return;
      const r = crtViewport.getBoundingClientRect();
      crtCursorFollower.style.left = `${ev.clientX - r.left}px`;
      crtCursorFollower.style.top = `${ev.clientY - r.top}px`;
      crtCursorFollower.classList.add("crt-cursor-follower--visible");
    });
    crtViewport.addEventListener("pointerleave", () => {
      crtCursorFollower.classList.remove("crt-cursor-follower--visible");
    });
  }

  /* ── Tabs / drawer ─────────────────────────────────────────────── */

  /** Phase-aware visibility for ORBIT vs ORDERS tabs (v0.8.0).
   *
   *  When ``livePhase === "orbit"`` we want the seat to land on the
   *  ORBIT panel; otherwise we hide it so the existing ORDERS-first
   *  muscle memory still works. Hiding is non-destructive: pressing
   *  the ``[1]`` shortcut still re-enables the tab if you want to
   *  inspect a stashed orbit queue. */
  function updateOrbitTabVisibility() {
    const orbitTab = document.querySelector('.cc-tab[data-cc-tab="orbit"]');
    const ordersTab = document.querySelector('.cc-tab[data-cc-tab="orders"]');
    // v1.0 — once the season is over there is nothing to submit, and
    // the omniscient watcher never submits. In both cases hide BOTH
    // command tabs so neither the ORBIT builder nor the surface/night
    // composer can take input (a finished MP game or replay is
    // view-only), and snap off either command tab.
    const locked = WATCH_MODE || livePhase === "season_complete";
    const isOrbit = !locked && livePhase === "orbit";
    if (orbitTab) {
      orbitTab.classList.toggle("cc-tab--hidden", locked || !isOrbit);
    }
    if (ordersTab) {
      ordersTab.classList.toggle("cc-tab--hidden", locked || isOrbit);
    }
    // Snap the active tab if the user was on the wrong one for the
    // current phase. We avoid yanking them off LOG / AGENT / etc.
    const activeBtn = document.querySelector(".cc-tab--active");
    const activeId = activeBtn?.getAttribute("data-cc-tab");
    if (locked) {
      if (activeId === "orbit" || activeId === "orders") {
        activateCcTab("replay");
      }
      return;
    }
    if (isOrbit && activeId === "orders") {
      activateCcTab("orbit");
    } else if (!isOrbit && activeId === "orbit") {
      activateCcTab("orders");
    }
  }

  /** @param {string} tabId */
  function activateCcTab(tabId) {
    ccTabs.forEach((btn) => {
      const on = btn.getAttribute("data-cc-tab") === tabId;
      btn.classList.toggle("cc-tab--active", on);
      btn.setAttribute("aria-selected", on ? "true" : "false");
    });
    ccPanels.forEach((panel) => {
      const on = panel.getAttribute("data-cc-panel") === tabId;
      panel.classList.toggle("cc-panel--active", on);
      panel.hidden = !on;
    });
    if (tabId === "graphics") {
      void refreshObserverMap().then(() => syncGridlinesClass());
    }
    // v0.9.8 — opening the LOG tab mid-game forces an immediate
    // timeline refresh. Without this the timeline could show stale
    // content from whenever the last scrub / status-poll ran.
    if (tabId === "replay") {
      syncReplayDrawer();
    }
  }

  ccTabs.forEach((btn) => {
    btn.addEventListener("click", () => {
      const tabId = btn.getAttribute("data-cc-tab");
      if (tabId) activateCcTab(tabId);
    });
  });

  // v0.9.13 — sticky mobile orders bar wiring.
  mobileOrdersOpenBtn?.addEventListener("click", () => {
    // Toggle the slide-up panel sheet. When opening, snap to the phase's
    // relevant panel (ORBIT during orbit, else ORDERS).
    if (isMobileSheetOpen()) {
      closeMobileSheet();
      return;
    }
    const orbitBtn = document.getElementById("solo-commit-orbit");
    const onOrbit = orbitBtn && orbitBtn.offsetParent !== null;
    activateCcTab(onOrbit ? "orbit" : "orders");
    openMobileSheet();
  });
  mobileOrdersTxBtn?.addEventListener("click", () => mobileTransmitProxy());

  replayLiveBtn?.addEventListener("click", () => {
    stopReplayPlayback();
    cancelInflightReplayAnimations();
    // Clear persistent collisionFxLayer overlays that cancelInflightReplayAnimations
    // doesn't cover — EMP clouds and mines are painted independently via their
    // own functions and must be explicitly wiped when leaving replay mode.
    paintEmpCloudOverlay({});
    paintMinesOverlay({});
    // Snap scrubber to the rightmost position so the bar reads "at the front".
    replayTickIdx = Math.max(0, replayTicks.length - 1);
    mainMapSource = "live";
    // Replay scrubbing can leave _heatPhase='hold' even when the live game is
    // past dawn. Sync to the actual live phase before repainting.
    if (livePhase !== "orbit") _heatClearAll(mapPlayer);
    if (lastLiveMapPayload && mapPlayer) {
      paintPlayerMap(mapPlayer, lastLiveMapPayload);
      if (_heatPhase === "hold") _heatApplyInstant(mapPlayer, 0.52);
      syncGridlinesClass();
      try { paintPlannedOrdersOverlay(); } catch (_e) { /* non-fatal */ }
    } else {
      void refreshSoloPlayerMap();
    }
    syncReplayRowOnly();
    // v0.7.3 — collapse the synced feed when leaving replay mode.
    if (replayFeedEl) replayFeedEl.hidden = true;
    // v0.7.5 — leaving replay collapses the opponent sub-tabs (live
    // mode hides them) and snaps the vault/agent feed back to live.
    updateSeatTabVisibility();
    updateNowPlayingStrip();
    renderScoreboard();
    repaintVaultForActiveSeat();
    renderAgentFeed();
    // Snap the orbital-station panel back to the live board. If the orbit for
    // the current day has resolved but its night hasn't been played yet
    // (livePhase "planning"), or the season just closed on the final
    // settlement ("season_complete"), returning to LIVE should show the
    // reviewable DUSK beat — catapults loaded, "+X" score lines, blue lift —
    // NOT snap to the previous night's stale dawn. Otherwise fall back to the
    // plain live snap (clears staging, restores cumulative score).
    try {
      const _liveDay =
        Number(lastLiveInventory?.day) || Number(lastLiveDay) || 0;
      const _duskBlob =
        window._socOrbitalData?.catapultByDay?.[String(_liveDay)];
      const _stageDusk = _liveDay > 0
        && (livePhase === "planning" || livePhase === "season_complete")
        && _duskBlob && orbitBlobHasActivity(_duskBlob);
      if (_stageDusk && typeof window.osOnLiveDusk === "function") {
        window.osOnLiveDusk(_liveDay);
        const _done = livePhase === "season_complete";
        if (replaySlotEl)
          replaySlotEl.textContent =
            _done ? "Season · RESOLVE" : `Day ${_liveDay} · VESPERA`;
        if (replayCaptionEl)
          replayCaptionEl.textContent = _done
            ? "[H00] RESOLVE · final settlement — season complete"
            : `[H00] VESPERA · day ${_liveDay} orbit resolved — plan the Nox`;
      } else if (typeof window.osOnLive === "function") {
        window.osOnLive(_liveDay);
      }
    } catch (_e) { /* non-fatal cosmetic drive */ }
  });

  replayPrev?.addEventListener("click", () => {
    stopReplayPlayback();
    if (!replayTicks.length) return;
    replayTickIdx =
      (replayTickIdx - 1 + replayTicks.length) % replayTicks.length;
    paintReplayFrameOntoMain("jump");
  });

  replayNext?.addEventListener("click", () => {
    stopReplayPlayback();
    if (!replayTicks.length) return;
    // Respect the loop setting: at the last window, stay put unless cycling is
    // enabled (avoids the surprising jump back to day 1 on a manual step).
    if (replayTickIdx >= replayTicks.length - 1 && !replayLoopEnabled) {
      paintReplayFrameOntoMain("jump");
      return;
    }
    const wrapped = (replayTickIdx + 1) % replayTicks.length;
    const forward = wrapped === replayTickIdx + 1;
    replayTickIdx = wrapped;
    paintReplayFrameOntoMain(forward ? "forward" : "jump");
  });

  replayDayPrev?.addEventListener("click", () => {
    stopReplayPlayback();
    jumpReplayByDay(-1);
  });

  replayDayNext?.addEventListener("click", () => {
    stopReplayPlayback();
    jumpReplayByDay(1);
  });

  replayScrub?.addEventListener("input", () => {
    if (!replayTicks.length || replayScrub.disabled) return;
    stopReplayPlayback();
    replayTickIdx = Number.parseInt(String(replayScrub.value), 10) || 0;
    paintReplayFrameOntoMain("jump");
  });

  replayPlay?.addEventListener("click", () => {
    if (!replayTicks.length) return;
    if (replayTicker !== null) {
      stopReplayPlayback();
      return;
    }
    if (reduceMotionMq.matches) {
      if (replayTickIdx >= replayTicks.length - 1 && !replayLoopEnabled) {
        paintReplayFrameOntoMain("jump");
        renderReplayFeedTimeline();
        return;
      }
      replayTickIdx = (replayTickIdx + 1) % replayTicks.length;
      paintReplayFrameOntoMain("jump");
      // v0.9.8 — explicit timeline render so the LOG highlight + caret
      // follow the playback even on reduced-motion (one-shot step).
      renderReplayFeedTimeline();
      return;
    }
    // v0.9.9 — chained setTimeout instead of a fixed setInterval so
    // the auto-play can pause for ``orbitFlashSeconds`` whenever it
    // lands on a synthetic orbit_summary tick. The previous
    // interval-based loop fired every 620 ms regardless of tick
    // kind, which would have skipped the modal flash too fast for
    // the watcher to read. Storing the timeout id in
    // ``replayTicker`` keeps ``stopReplayPlayback`` working
    // unchanged (it still calls ``clearInterval``; ``clearTimeout``
    // and ``clearInterval`` are interchangeable in modern browsers).
    const BASE_DELAY = 620;
    const scheduleNext = (delay) => {
      replayTicker = window.setTimeout(() => {
        // End of timeline. When looping is OFF (default) we stop on the last
        // available window rather than cycling back to day 1. The final frame
        // is already painted, so ``handleReplaySeasonState`` (invoked by that
        // paint) drives the closing settlement + victory + score card when the
        // "play ending on replay" setting is enabled.
        if (replayTickIdx >= replayTicks.length - 1 && !replayLoopEnabled) {
          stopReplayPlayback();
          return;
        }
        const wrapped = (replayTickIdx + 1) % replayTicks.length;
        const forward = wrapped === replayTickIdx + 1;
        replayTickIdx = wrapped;
        // Looped back to the top → re-arm the dawn-wipe dedupe so the
        // next pass shows sunrises again.
        if (!forward) {
          _sweptReplayNights = new Set();
          _prevPaintedReplayDay = null;
        }
        // Reset the sweep clock so a non-dawn tick doesn't inherit the
        // previous dawn's hold; the paint re-sets it if it runs a sweep.
        _lastDawnSweepMs = 0;
        paintReplayFrameOntoMain(forward ? "forward" : "jump");
        renderReplayFeedTimeline();
        const nextTick = replayTicks[replayTickIdx];
        const isSlotTick = nextTick
          && (nextTick.slot === "dawn" || nextTick.slot === "dusk");
        let nextDelay = isSlotTick
          ? Math.max(500, Math.round(orbitFlashSeconds * 1000))
          : BASE_DELAY;
        // v1.1 — when the just-painted tick fired the dawn white sweep,
        // give it the full run (plus a beat) before stepping on so the
        // wave is never cut short during autoplay.
        if (_lastDawnSweepMs > 0) {
          nextDelay = Math.max(nextDelay, _lastDawnSweepMs + 280);
        }
        // Station UI (opt-in) may ask for extra dwell on the ticks where it
        // runs the catapult LOAD / LAUNCH + score count-up animations, so
        // those aren't cut short by the base cadence. Harmless (0) otherwise.
        if (typeof window._osPendingDwellMs === "number") {
          nextDelay = Math.max(nextDelay, window._osPendingDwellMs);
        }
        scheduleNext(nextDelay);
      }, delay);
    };
    scheduleNext(BASE_DELAY);
    if (replayPlay) replayPlay.textContent = "[ pause ]";
  });

  // v0.9.9 — dynamic per-seat replay-view buttons.
  //
  // Builds one ``[ Pn ]`` button per active seat (in seat order, with
  // each button's bracket text stroked in the seat's owner colour) and
  // injects them before the existing OBS button. The OBS button is
  // declared statically in HTML (so its click handler can be bound
  // once at page-load) and is repurposed by this function as "view
  // every seat's vision combined" — pre-v0.9.9 OBS only widened to
  // p1+p2, which left p3/p4 invisible in 4-seat games.
  //
  // ``replayViewSeat`` accepts any of:
  //   - a literal seat id (``"p1"`` .. ``"p4"``) — show that seat's
  //     fog-of-war view
  //   - ``"obs"`` — show every active seat's vision combined
  //
  // The legacy ``"both"`` value is gone (it was a 2-seat-only
  // shortcut). Any persisted ``"both"`` is coerced to ``"obs"`` on
  // first render. ``replayViewP1Btn`` / ``P2Btn`` / ``BothBtn`` are
  // also gone — refs are now looked up by current id each render.
  function _activeSeatsForView() {
    const w = /** @type {any} */ (window);
    const fromGlobal = Array.isArray(w.__SOC_PLAYERS__) && w.__SOC_PLAYERS__.length
      ? w.__SOC_PLAYERS__
      : null;
    const fromLastNew = Array.isArray(w.__SOC_LAST_NEWGAME__?.players)
      && w.__SOC_LAST_NEWGAME__.players.length
      ? w.__SOC_LAST_NEWGAME__.players
      : null;
    const list = fromGlobal || fromLastNew || ["p1", "p2"];
    return list.filter((p) => typeof p === "string" && /^p[1-9]$/.test(p));
  }

  function renderReplayViewButtons() {
    if (!replayViewRowEl) return;
    if (!replayViewObsBtn) return;
    if (replayViewSeat === "both") replayViewSeat = "obs";
    const seats = _activeSeatsForView();

    // Drop every previously-injected per-seat button (keep OBS + any
    // siblings that come AFTER OBS in the row, like the ORBIT toggle
    // and the FLASH slider label).
    Array.from(replayViewRowEl.children).forEach((node) => {
      if (node === replayViewObsBtn) return;
      if (node.classList?.contains("cc-replay-view-btn--seat")) {
        node.remove();
      }
    });

    // v0.9.11 — multi-perspective (OBS + per-seat fog views) is a
    // replay/watch/season-complete privilege ONLY. During live play the
    // human watches their own last night from their own seat, so we
    // hide OBS and inject NO seat buttons (seeing a rival's fog-of-war
    // mid-season would be a leak). The RECAP / BRIEFING buttons that
    // share this row stay put. Force the view back to self (p1) so the
    // map paints the player's own perspective when they scrub.
    if (!opponentSeatVisible()) {
      replayViewObsBtn.hidden = true;
      replayViewSeat = MY_SEAT;
      syncReplayViewBtns();
      return;
    }
    replayViewObsBtn.hidden = false;

    // If the active seat is no longer present (e.g. user navigated
    // from a 4-seat replay back to a 2-seat one), reset to OBS so
    // the map doesn't silently render an empty fog overlay.
    if (replayViewSeat !== "obs" && !seats.includes(replayViewSeat)) {
      replayViewSeat = seats[0] || "obs";
    }

    seats.forEach((seat) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.id = `replay-view-${seat}`;
      btn.className = "cli-btn cc-replay-view-btn cc-replay-view-btn--seat";
      btn.dataset.seat = seat;
      // v0.9.18 — use custom player color
      const color = playerColor(seat) || ownerColor(seat) || "#9fa6ad";
      btn.style.setProperty("--cc-replay-seat-stroke", color);
      // v0.9.18 — use player tag in button label
      const label = playerTag(seat);
      btn.title = `${label} (${seat}) fog-of-war view`;
      btn.textContent = `[ ${label} ]`;
      if (replayViewSeat === seat) {
        btn.classList.add("cc-replay-view-btn--active");
      }
      btn.addEventListener("click", () => {
        replayViewSeat = seat;
        syncReplayViewBtns();
        if (mainMapSource === "replay") paintReplayFrameOntoMain("jump");
        if (typeof osOnViewerChange === "function") osOnViewerChange(replayViewSeat);
      });
      replayViewRowEl.insertBefore(btn, replayViewObsBtn);
    });

    syncReplayViewBtns();
  }

  function syncReplayViewBtns() {
    if (!replayViewRowEl) return;
    replayViewRowEl
      .querySelectorAll(".cc-replay-view-btn--seat")
      .forEach((btn) => {
        const seat = btn.getAttribute("data-seat");
        btn.classList.toggle(
          "cc-replay-view-btn--active",
          seat === replayViewSeat,
        );
      });
    replayViewObsBtn?.classList.toggle(
      "cc-replay-view-btn--active",
      replayViewSeat === "obs",
    );
  }

  replayViewObsBtn?.addEventListener("click", () => {
    replayViewSeat = "obs";
    syncReplayViewBtns();
    if (mainMapSource === "replay") paintReplayFrameOntoMain("jump");
    if (typeof osOnViewerChange === "function") osOnViewerChange("obs");
  });

  // v0.9.18 — AGENT per-seat sub-tabs are now built dynamically by
  // renderAgentSeatTabs() (one per active seat, p3/p4 reachable); their
  // click handlers are wired there, mirroring the VAULT tabs.

  // v0.9.6 — header [NEW GAME] now opens the N-seat launcher modal
  // instead of immediately spawning a 2-seat game. The legacy
  // instant-spawn path is preserved for any caller that imports
  // ``newGame`` directly (eval harness, console).
  newGameBtn.addEventListener("click", openNewGameModal);
  bindNewGameModal();

  soloExpert?.addEventListener("change", () => syncExpertPanel());

  // v0.8.0 — legacy ``.solo-add-move`` buttons are gone. The wireframe
  // querySelector below is retained as a guard so any third-party
  // injection of those buttons still works during transition.
  document.querySelectorAll(".solo-add-move").forEach((btn) => {
    btn.addEventListener("click", () => {
      const a = btn.getAttribute("data-action");
      if (!a) return;
      if (actionNeedsXY(a)) {
        enterPickMode(a);
      } else {
        addQueueRow(a);
      }
    });
  });

  soloQueueClearBtn?.addEventListener("click", () => clearQueue());

  // v0.9.5 — "show all 21 slots" toggle. Flips ``soloQueueShowAll``
  // and re-renders the queue. The button itself is the source of
  // truth for the pressed state (aria-pressed + body class via
  // ``cc-queue-show-all-btn--on``); the renderer just reads the
  // boolean.
  soloQueueShowAllBtn?.addEventListener("click", () => {
    soloQueueShowAll = !soloQueueShowAll;
    soloQueueShowAllBtn.setAttribute(
      "aria-pressed",
      soloQueueShowAll ? "true" : "false",
    );
    soloQueueShowAllBtn.classList.toggle(
      "cc-queue-show-all-btn--on",
      soloQueueShowAll,
    );
    soloQueueShowAllBtn.textContent = soloQueueShowAll
      ? "[ collapse to queued ]"
      : "[ show all 21 slots ]";
    renderSoloQueue();
  });

  soloAgentBtn?.addEventListener("click", () => {
    void runAgentTurn();
  });

  soloAgentAutoplayBtn?.addEventListener("click", () => {
    void runAgentAutoplay();
  });

  soloAgentVersusBtn?.addEventListener("click", () => {
    void runAgentVersus();
  });

  soloCommitBtn?.addEventListener("click", () => {
    void submitSoloNight();
  });

  window.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") {
      if (reportEl && !reportEl.hidden) {
        closeReport();
        return;
      }
      if (pickMode || assetSelect) {
        exitPickMode();
        exitAssetSelect();
        return;
      }
    }
    if (ev.target && /^(INPUT|TEXTAREA|SELECT)$/.test(ev.target.tagName))
      return;
    if (ev.key >= "1" && ev.key <= "8") {
      const idx = Number(ev.key) - 1;
      const btn = ccTabs[idx];
      const tabId = btn && btn.getAttribute("data-cc-tab");
      if (tabId) activateCcTab(tabId);
    }
  });

  mapPlayer?.addEventListener("click", (ev) => {
    // v0.9.13 — on mobile, a tap on the visible map while the panel sheet
    // is up just dismisses the sheet (doesn't deploy).
    if (isMobileSheetOpen()) {
      closeMobileSheet();
      ev.stopPropagation();
      return;
    }
    // v0.9.13 — touch tap-vs-drag guard. A pan/pinch gesture ends with a
    // synthetic click; swallow it so a scroll or zoom never deploys an
    // order onto whatever cell the finger lifted from.
    if (_suppressNextMapClick) {
      _suppressNextMapClick = false;
      ev.stopPropagation();
      return;
    }
    // v0.8.0 — asset-first flow takes precedence over the legacy
    // pickMode path. If a unit is queued for a target, the next map
    // click commits the order.
    if (assetSelect && assetSelect.awaiting === "target") {
      const target = /** @type {HTMLElement | null} */ (ev.target);
      const cell = target && target.closest ? target.closest(".cell") : null;
      if (!cell) return;
      const xAttr = cell.getAttribute("data-x");
      const yAttr = cell.getAttribute("data-y");
      const x = xAttr != null ? parseInt(xAttr, 10) : NaN;
      const y = yAttr != null ? parseInt(yAttr, 10) : NaN;
      if (!Number.isFinite(x) || !Number.isFinite(y)) return;
      const { action, unit } = assetSelect;
      if (action === "step") {
        // Reject non-adjacent step targets client-side using the
        // PROJECTED position (live + queued moves so far) so a
        // drop → step → step chain validates correctly. Engine
        // still applies its own bounds checks at PRAXIS time.
        const proj = projectedUnitState(unit);
        if (proj.pos) {
          const dx = Math.abs(x - proj.pos[0]);
          const dy = Math.abs(y - proj.pos[1]);
          if (dx + dy !== 1) {
            flashHint(
              `step targets must be a cardinal neighbour of (${proj.pos[0]},${proj.pos[1]})`,
            );
            return;
          }
        }
      }
      // v0.9.x — EMP is a SALVO: one launch fires up to
      // ``EMP_MISSILES_PER_LAUNCH`` (3) missiles. Accumulate target
      // cells onto one queue row; re-clicking a chosen cell removes it,
      // and the picker auto-stops once the salvo is full. The user can
      // also stop early by clicking the EMP chip again.
      if (action === "emp_launch") {
        empSalvoToggleTarget(x, y);
        ev.stopPropagation();
        return;
      }
      // v0.9.5 — STICKY path-picker mode. When the user is composing
      // a unit's path (step or drop), the picker stays armed after
      // each click and re-arms as STEP for the next map click. So a
      // single chip-click can compose drop → step → step → step …
      // The user explicitly exits via the banner's [stop] button
      // (or by clicking the chip a second time). Probe / mine
      // remain single-shot — they target a tile, not a chain.
      const chainable = action === "step" || action === "drop";
      addQueueRow(action, x, y, unit);
      if (chainable && unit) {
        // Re-arm as STEP for the same unit; the engine validates
        // adjacency at PRAXIS time and the picker's own check
        // above clamps obvious mis-clicks.
        enterAssetSelect({
          action: "step",
          unit,
          awaiting: "target",
        });
      } else {
        exitAssetSelect();
      }
      ev.stopPropagation();
      return;
    }
    if (!pickMode) return;
    const target = /** @type {HTMLElement | null} */ (ev.target);
    const cell = target && target.closest ? target.closest(".cell") : null;
    if (!cell) return;
    const xAttr = cell.getAttribute("data-x");
    const yAttr = cell.getAttribute("data-y");
    const x = xAttr != null ? parseInt(xAttr, 10) : NaN;
    const y = yAttr != null ? parseInt(yAttr, 10) : NaN;
    if (!Number.isFinite(x) || !Number.isFinite(y)) return;
    const action = pickMode;
    exitPickMode();
    addQueueRow(action, x, y);
    ev.stopPropagation();
  });

  document.getElementById("pick-mode-cancel")?.addEventListener("click", () => {
    exitPickMode();
    exitAssetSelect();
  });

  syncExpertPanel();
  renderSoloQueue();
  renderOrbitQueue();
  renderOrdersAssetRoster();
  updateOrbitTabVisibility();
  // v0.9.9 — initial paint of the dynamic replay-view button row so
  // the OBS button is joined by per-seat buttons even before the
  // first /view call lands.
  renderReplayViewButtons();

  // v0.7.5 — initial paint of the universal replay strip + scoreboard
  // + agent feed so they don't look broken before the first status
  // refresh lands.
  updateSeatTabVisibility();
  updateLiveButtonPulse();
  updateNowPlayingStrip();
  renderScoreboard();
  renderAgentFeed();

  if (JOIN_MODE) {
    // v0.9.12 — a friend opened a shareable seat link. Bind into the
    // existing session as a live, playable seat (fog-of-war percept,
    // ORDERS/ORBIT tabs, TRANSMIT) — NOT the omniscient watcher.
    paintPlaceholder(mapPlayer, "# joining session…");
    paintPlaceholder(mapObserver, "# full map · GRAPHICS tab");
    bootJoinMode();
  } else if (WATCH_MODE) {
    // Phase C watcher: skip the "# start NEW GAME" placeholder and
    // boot directly into the season-loading flow. The picker bar
    // unhides itself inside ``bootWatcherMode`` so the user can
    // switch seasons without a manual reload.
    paintPlaceholder(mapPlayer, "# loading season…");
    paintPlaceholder(mapObserver, "# loading season…");
    bootWatcherMode();
  } else {
    paintPlaceholder(mapPlayer, "# start NEW GAME");
    paintPlaceholder(mapObserver, "# full map · GRAPHICS tab");
    // Landing-page "Multiplayer" deep-link: ?new=multi auto-opens the
    // NEW GAME modal preset to two HUMAN seats so the host just hits
    // SPAWN and gets the INVITE PLAYERS QR (links are public when this
    // page was reached via the tunnel origin).
    try {
      const _np = new URLSearchParams(window.location.search).get("new");
      if (_np === "multi" && typeof openNewGameModal === "function") {
        newGameModalState.seatCount = 2;
        newGameModalState.agents.p1 = "human";
        newGameModalState.agents.p2 = "human";
        openNewGameModal();
      } else if (_np === "quick" && typeof newGame === "function") {
        // v1.12 — landing-page "Quick game": skip the launcher entirely
        // and spawn the standard first game (you vs RED_HARVEST_LITE).
        // Every field in that modal has a right answer for a first-timer
        // and no way to know it, so the four decisions between launching
        // the server and the first move were pure stall. The launcher is
        // still there for anyone who wants to change something.
        //
        // v1.14 — pinned to the memory backend rather than the server
        // default. This is the "just let me play" button, and on a
        // machine with Snowflake credentials the default would make
        // every move a warehouse round-trip — the slowest possible
        // version of the fastest possible path.
        newGame({
          players: ["p1", "p2"],
          agents: { p1: "human", p2: "red_harvest_lite" },
          backend: "memory",
        });
      }
    } catch (_e) { /* non-fatal */ }
  }
})();
