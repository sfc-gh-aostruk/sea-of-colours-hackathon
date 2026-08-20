/* orbital_exp/station.js — space station panels, minimalist unicode */
/* jshint esversion:11 */

(function () {
  "use strict";

  /* ── constants ────────────────────────────────────────────────────── */

  // Fallback seat colors (matches app.js OWNER_COLOR + playerColor defaults)
  const OS_COLOR_DEFAULTS = {
    p1: "#FFFFFF",
    p2: "#FCF871",
    p3: "#E45EF0",
    p4: "#82F4FB",
  };

  const OS_LEFT_SEATS  = ["p1", "p3"];
  const OS_RIGHT_SEATS = ["p2", "p4"];

  // Diamond geometry — matches demo.html
  const OS_DIA_HALF    = 5;
  const OS_DIA_SIZE    = OS_DIA_HALF * 2 - 1;  // 9
  const OS_VAULT_ROWS  = 4;
  const OS_VAULT_COLS  = 4;
  const OS_VAULT_CELLS = OS_VAULT_ROWS * OS_VAULT_COLS;  // 16

  const OS_DENSITY = ["░", "▒", "▓", "█"];
  const OS_VAULT_COLORS = {
    red:   "#ff4444",
    green: "#44cc44",
    blue:  "#4488ff",
    grey:  "#444455",
  };

  // Grade → approximate parcel counts (HOARD_CAPACITY=15)
  // empty=0, low<25%(<4)→2, half<60%(<9)→5, high<90%(<14)→10, full≥90%(14-15)→14
  const OS_FULLNESS_TO_CELLS = { empty: 0, low: 2, half: 5, high: 10, full: 14 };
  // Green estimate strings → midpoint counts
  const OS_GREEN_EST_CELLS   = { "0": 0, "1-3": 2, "4-7": 5, "8-12": 10, "13+": 13 };

  const OS_TIER_GLYPH  = { trace: "░", vein: "▒", mass: "▓", pure: "█" };

  const OS_EVENT_LABEL = {
    probe:       "probe launched",
    drop:        "orblift dropped harvester",
    drop_bounce: "orblift failed (bounce)",
    pickup:      "orblift recovered harvester",
    mine_lay:    "mine laid",
    emp_launch:  "EMP launched",
    chaff_flare: "chaff flare",
    abandoned:   "abandoned",
    damaged:     "damaged",
  };

  const OS_EVENT_GLYPH = {
    probe: "·", drop: "▼", drop_bounce: "▼", pickup: "▲",
    mine_lay: "◆", emp_launch: "◯", chaff_flare: "✶",
    abandoned: "✖", damaged: "⚠",
  };

  /* ── state ────────────────────────────────────────────────────────── */

  let _initialized   = false;
  let _activeSeats   = [];
  let _stationObs    = {};    // seat → latest obs snapshot
  let _catData       = null;  // latest catapult.slot_assignments array
  let _scores        = {};    // seat → {score}
  let _lastActivity  = {};    // seat → event array from last briefing
  let _catLaunchTimers = [];  // pending setTimeout ids for catapult clear-after-launch
  let _viewerSeat      = null;  // "p1"/"p2"/"p3"/"p4"/"obs" — current replay POV
  let _currentDay    = null;  // day number of the last rendered tick
  let _currentPhase  = "day"; // "day" | "night" — tracks most recent dawn/dusk

  /* ── color helpers ────────────────────────────────────────────────── */

  function _seatColor(seat) {
    const d = window._socOrbitalData;
    const c = d?.playerProfiles?.[seat]?.color;
    return (c && c !== "") ? c : (OS_COLOR_DEFAULTS[seat] || "#FFFFFF");
  }

  /* ── launch delay setting ─────────────────────────────────────────── */

  window._osLaunchDelay = 0;

  function _osToggleDelay(btn) {
    window._osLaunchDelay = window._osLaunchDelay ? 0 : 220;
    btn.textContent = `LAUNCH DELAY: ${window._osLaunchDelay ? "ON" : "OFF"}`;
    btn.classList.toggle("os-setting--on", !!window._osLaunchDelay);
  }

  function _osInjectSetting() {
    if (document.getElementById("os-setting-delay")) return;
    const controls = document.querySelector(".cc-replay-toolbar");
    if (!controls) return;
    const btn = document.createElement("button");
    btn.id = "os-setting-delay";
    btn.className = "os-setting-btn";
    btn.textContent = "LAUNCH DELAY: OFF";
    btn.addEventListener("click", () => _osToggleDelay(btn));
    controls.appendChild(btn);
  }

  /* ── public hooks ─────────────────────────────────────────────────── */

  window.osOnOrbitalDataLoaded = function () {
    _viewerSeat = window._socReplayViewSeat || null;
    _osInitPanels();
    _osInjectSetting();
    _initialized = true;
    _osFitMapZoom(0);
    _osInstallResizeFit();
  };

  window.osOnViewerChange = function (seat) {
    _viewerSeat = seat;
    _osRefreshAllVaults();
  };

  window.osOnOrbitalReportDay = function (kind, day) {
    const d = window._socOrbitalData;
    if (!d) return;
    const phase = kind === "recap" ? "pre" : "post";
    const obs = d.stationObsByDay?.[String(day)]?.[phase] || {};
    for (const [seat, sObs] of Object.entries(obs)) {
      _stationObs[seat] = sObs;
      _osRenderVault(seat);
    }
    if (kind === "briefing") {
      const cat = d.catapultByDay?.[String(day)]?.catapult;
      if (cat) { _catData = cat.slot_assignments; _osRenderCatPips(); }
      const evts = d.orbitalEventsByDay?.[String(day)] || {};
      for (const [seat, list] of Object.entries(evts)) { _lastActivity[seat] = list; }
    }
  };

  window.osOnReplayTick = function ({ slot, day, tag }) {
    const d = window._socOrbitalData;
    if (!d) return;

    // Cancel any pending catapult-clear timers so scrubbing doesn't leave stale state.
    for (const t of _catLaunchTimers) clearTimeout(t);
    _catLaunchTimers = [];

    if (slot === "dusk") {
      const cat = d.catapultByDay?.[String(day)]?.catapult;
      _catData = cat ? cat.slot_assignments : null;
      _osRenderCatSlots();
      _osCatLoadAnim();   // parcels fly from station diamonds into the catapult
      const postObs = d.stationObsByDay?.[String(day)]?.post || {};
      for (const [seat, sObs] of Object.entries(postObs)) { _stationObs[seat] = sObs; }
      _osSetPhase("night");
      _currentDay = day; _currentPhase = "night";
      // Force obs: reconstructVaultAtTick at DUSK reads through the previous
      // night's frames (catapult hasn't fired yet in frame history), so it
      // returns stale pre-catapult hoard. Post obs is the accurate state here.
      _osRefreshAllVaults(true);

    } else if (slot === "dawn") {
      _catData = null;
      _osRenderCatSlots();
      const obs = d.stationObsByDay?.[String(day)]?.pre || {};
      for (const [seat, sObs] of Object.entries(obs)) { _stationObs[seat] = sObs; }
      _osSetPhase("day");
      _currentDay = day; _currentPhase = "day";
      // Frame reconstruction at dawn is correct: lastFrameIdx = last night frame
      // which carries the post-harvest, pre-catapult-N+1 hoard. Matches pre obs.
      _osRefreshAllVaults(false);

    } else if (day !== _currentDay) {
      // User scrubbed directly to a different day's night frame.
      // Load post obs (start-of-night state) as best available snapshot.
      const obs = d.stationObsByDay?.[String(day)]?.post
        || d.stationObsByDay?.[String(day)]?.pre
        || {};
      for (const [seat, sObs] of Object.entries(obs)) { _stationObs[seat] = sObs; }
      const cat = d.catapultByDay?.[String(day)]?.catapult;
      _catData = cat ? cat.slot_assignments : null;
      _osRenderCatSlots();
      _currentDay = day; _currentPhase = "night";
      _osRefreshAllVaults(false);

    } else if (tag === "open") {
      // "Praxis begins" frame: launch everything from the catapult, then clear it.
      // Also force obs (shares lastFrameIdx with DUSK, so frame hoard is stale).
      _osCatLaunchAnim();
      _osRefreshAllVaults(true);

    } else {
      // Normal night frame — use frame reconstruction for own station.
      _osRefreshAllVaults(false);
    }
  };

  function _osRefreshAllVaults(forceObs) {
    const fn = window._socReconstructVault;
    for (const s of _activeSeats) {
      const isOwn = _viewerSeat === "obs" || _viewerSeat === s;
      if (isOwn && fn && !forceObs) {
        try {
          const inv = fn(s);
          if (Array.isArray(inv?.hoard) && inv.hoard.length > 0) {
            _osRenderVaultFromHoard(s, inv);
          } else {
            _osRenderVault(s);  // fall back to obs grades when no hoard snapshot
          }
        } catch (e) {
          _osRenderVault(s);
        }
      } else {
        _osRenderVault(s);
      }
    }
  }

  window.osOnEntityArrival = function (delta, _targetCell) {
    if (!delta) return;
    const seat  = delta.owner || "p1";
    const side  = OS_LEFT_SEATS.includes(seat) ? "left" : "right";
    const color = _seatColor(seat);

    if (delta.kind === "probe_emit") {
      const yOff = (Math.random() - 0.5) * 90;
      _osQueueAnim(seat, "■", color, side, "out", { dur: 2200, ease: "in", size: 7, yOff });
    } else if (delta.kind === "emp_launch") {
      const yOff = (Math.random() - 0.5) * 90;
      _osQueueAnim(seat, "■", "#00ffff", side, "out", { dur: 2200, ease: "in", size: 7, yOff });
    } else if (delta.kind === "chaff_flare") {
      // Scatter burst: 8 density/noise chars fanning outward at different angles
      const BURST = [
        { ch: "░", yOff: -80, delay:   0, dur: 750, col: "#cccccc" },
        { ch: "▒", yOff: -50, delay:  25, dur: 900, col: "#999999" },
        { ch: "▓", yOff: -20, delay:  50, dur: 820, col: "#dddddd" },
        { ch: "░", yOff:  10, delay:  15, dur: 700, col: "#aaaaaa" },
        { ch: "▒", yOff:  35, delay:  60, dur: 860, col: "#bbbbbb" },
        { ch: "░", yOff:  60, delay:  35, dur: 780, col: "#888888" },
        { ch: "▓", yOff: -65, delay:  70, dur: 680, col: "#eeeeee" },
        { ch: "▒", yOff:  82, delay:  45, dur: 930, col: "#aaaaaa" },
      ];
      for (const p of BURST) {
        _osQueueAnim(seat, p.ch, p.col, side, "out", { dur: p.dur, ease: "out", size: 5, yOff: p.yOff, delay: p.delay });
      }
    } else if (delta.kind === "drop") {
      _osQueueAnim(seat, "▲", color, side, "out", { dur: 3400, ease: "in", size: 18, yOff: 30 });
    } else if (delta.kind === "drop_bounce") {
      _osQueueAnim(seat, "▲", color + "88", side, "out", { dur: 3400, ease: "in", size: 18, yOff: 30 });
    } else if (delta.kind === "pickup") {
      const emped = delta.emped;
      const dmg   = delta.damaged;
      const glyph = (dmg || emped) ? "▲" : "△";
      const col   = emped ? "#00ffff" : dmg ? "#ff4444" : color;
      _osQueueAnim(seat, glyph, col, side, "in", { dur: 3400, ease: "out", size: 18, yOff: dmg ? 55 : 30 });
    }
  };

  window.osOnScoreUpdate = function (bySeat) {
    if (!bySeat) return;
    _scores = bySeat;
    for (const [seat, s] of Object.entries(bySeat)) {
      _osRenderScore(seat, s.score ?? 0);
    }
    _osUpdateLeader();
  };

  /* ── init ─────────────────────────────────────────────────────────── */

  function _osInitPanels() {
    const d = window._socOrbitalData;
    if (!d) return;

    const seen = new Set();
    for (const dayData of Object.values(d.stationObsByDay || {}))
      for (const phase of Object.values(dayData || {}))
        for (const seat of Object.keys(phase || {})) seen.add(seat);
    const fromProfiles = Object.keys(d.playerProfiles || {});
    const all = seen.size ? [...seen] : fromProfiles.length ? fromProfiles : ["p1", "p2"];
    const ORDER = ["p1", "p2", "p3", "p4"];
    _activeSeats = ORDER.filter(s => all.includes(s));

    const leftEl  = document.getElementById("os-side-left");
    const rightEl = document.getElementById("os-side-right");
    if (!leftEl || !rightEl) return;
    leftEl.innerHTML  = "";
    rightEl.innerHTML = "";

    for (const seat of _activeSeats) {
      const el = _osBuildStation(seat, d.playerProfiles);
      (OS_LEFT_SEATS.includes(seat) ? leftEl : rightEl).appendChild(el);
    }

    // Central catapult panel at bottom of left column.
    leftEl.appendChild(_osBuildCatapultPanel());

    // Pre-populate _stationObs with day 1 post obs (after orbit 1 fires, before
    // night 1 starts). The replay's first tick is DUSK(1) which also loads post
    // obs, so this matches what the user will see once the replay starts.
    const days = Object.keys(d.stationObsByDay || {}).map(Number).sort((a, b) => a - b);
    if (days.length) {
      _currentDay = days[0];
      _currentPhase = "night";
      const firstPost = d.stationObsByDay[String(days[0])]?.post
        || d.stationObsByDay[String(days[0])]?.pre
        || {};
      for (const [seat, sObs] of Object.entries(firstPost)) _stationObs[seat] = sObs;
    }

    _osRefreshAllVaults();
    _osBindHover();
  }

  function _osBuildStation(seat, profiles) {
    const color  = _seatColor(seat);
    const rawTag = profiles?.[seat]?.tag || seat.toUpperCase();
    const tag    = rawTag.slice(0, 3).padEnd(3).toUpperCase();
    const side   = OS_LEFT_SEATS.includes(seat) ? "left" : "right";

    const div = document.createElement("div");
    div.className = "os-station";
    div.dataset.osStation = seat;
    div.style.setProperty("--os-color", color);

    div.innerHTML = `
<div class="os-diamond-wrap">
  <pre class="os-diamond" data-os-diamond="${seat}" style="color:${color}"></pre>
  <pre class="os-vault-pre" data-os-vault="${seat}"></pre>
  <span class="os-diamond-tag">${tag}</span>
</div>
<div class="os-score" data-os-score="${seat}">—</div>`;

    // Render static diamond body with vault region left as spaces (hole)
    const preEl = div.querySelector(`[data-os-diamond="${seat}"]`);
    if (preEl) _osRebuildDiamond(preEl, side === "right");

    return div;
  }

  /* ── diamond / vault rendering ────────────────────────────────────── */

  // Diamond body: renders the player-colored shape, leaving vault region as spaces (the "hole").
  function _osRebuildDiamond(el, mirror) {
    const SIZE = OS_DIA_SIZE, HALF = OS_DIA_HALF;
    let html = "";
    for (let r = 0; r < SIZE; r++) {
      const dist     = Math.abs(r - (HALF - 1));
      const diaStart = dist;
      const diaEnd   = SIZE - 1 - dist;
      for (let c = 0; c < SIZE; c++) {
        const inDiamond = c >= diaStart && c <= diaEnd;
        const inVault   = r < OS_VAULT_ROWS && (mirror
          ? c >= SIZE - OS_VAULT_COLS
          : c < OS_VAULT_COLS);
        html += (!inVault && inDiamond) ? "█" : " ";
      }
      if (r < SIZE - 1) html += "\n";
    }
    el.innerHTML = html;
  }

  // Vault overlay pre: renders only the vault chars, positioned atop the diamond.
  // The main pre has spaces where the vault is, so no body chars bleed through.
  function _osRenderVaultPre(seat, cells, mirror) {
    const el = document.querySelector(`[data-os-vault="${seat}"]`);
    if (!el) return;
    const SIZE = OS_DIA_SIZE;
    let html = "";
    for (let r = 0; r < SIZE; r++) {
      for (let c = 0; c < SIZE; c++) {
        const inVault = r < OS_VAULT_ROWS && (mirror
          ? c >= SIZE - OS_VAULT_COLS
          : c < OS_VAULT_COLS);
        if (inVault) {
          const vIdx = mirror
            ? r * OS_VAULT_COLS + (c - (SIZE - OS_VAULT_COLS))
            : r * OS_VAULT_COLS + c;
          const cell = cells[vIdx] || null;
          if (cell) {
            const ch  = OS_DENSITY[(cell.density ?? 4) - 1] || "█";
            const col = OS_VAULT_COLORS[cell.type] || "#888";
            html += `<span style="color:${col}">${ch}</span>`;
          } else {
            html += " ";  // empty vault cell → space (station bg = black = the "hole")
          }
        } else {
          html += " ";
        }
      }
      if (r < SIZE - 1) html += "\n";
    }
    el.innerHTML = html;
  }

  function _osRenderVaultFromHoard(seat, inv) {
    const mirror = OS_RIGHT_SEATS.includes(seat);
    const hoard  = Array.isArray(inv?.hoard) ? inv.hoard : [];
    const cells  = Array(OS_VAULT_CELLS).fill(null);
    hoard.slice(0, OS_VAULT_CELLS).forEach((p, i) => {
      const tile = Number(p.tile_at_harvest ?? p.origin_tile ?? -1);
      const pur  = Number(p.purity_at_harvest ?? 0);
      const type = tile === 1 ? "green" : tile === 3 ? "blue" : "red";
      cells[i]   = { type, density: Math.max(1, Math.min(4, Math.ceil(pur / 64) || 1)) };
    });
    _osRenderVaultPre(seat, cells, mirror);
  }

  function _osRenderVault(seat) {
    const mirror = OS_RIGHT_SEATS.includes(seat);
    const obs    = _stationObs[seat] || {};
    const isOwn  = _viewerSeat === "obs" || _viewerSeat === seat;
    const cells  = Array(OS_VAULT_CELLS).fill(null);

    if (isOwn) {
      const count      = Math.max(0, Math.min(OS_VAULT_CELLS, obs.fullness?.count ?? 0));
      const greenCount = Math.max(0, Math.min(count, obs.green?.count ?? 0));
      const redCount   = count - greenCount;
      const gPurity    = greenCount > 0 ? (obs.green?.total ?? 0) / greenCount : 0;
      const gDens      = Math.max(1, Math.min(4, Math.ceil(gPurity / 64)));
      let i = 0;
      for (let g = 0; g < greenCount && i < OS_VAULT_CELLS; g++, i++) cells[i] = { type: "green", density: gDens };
      for (let r = 0; r < redCount   && i < OS_VAULT_CELLS; r++, i++) cells[i] = { type: "red",   density: 3 };
    } else {
      const totalCells = OS_FULLNESS_TO_CELLS[obs.fullness?.grade] ?? 0;
      const greenCells = Math.min(totalCells, OS_GREEN_EST_CELLS[obs.green?.estimate] ?? 0);
      const greyCells  = totalCells - greenCells;
      let i = 0;
      for (let g = 0; g < greenCells && i < OS_VAULT_CELLS; g++, i++) cells[i] = { type: "green", density: 1 };
      for (let r = 0; r < greyCells  && i < OS_VAULT_CELLS; r++, i++) cells[i] = { type: "grey",  density: 1 };
    }

    _osRenderVaultPre(seat, cells, mirror);
  }

  /* ── central catapult panel ──────────────────────────────────────── */

  function _osBuildCatapultPanel() {
    const div = document.createElement("div");
    div.className = "os-catapult";
    div.id = "os-catapult";
    const lbl = document.createElement("div");
    lbl.className = "os-catapult-label";
    lbl.textContent = "CATAPULT";
    div.appendChild(lbl);
    const grid = document.createElement("div");
    grid.className = "os-catapult-grid";
    grid.id = "os-catapult-grid";
    for (let i = 0; i < 20; i++) {
      const sq = document.createElement("span");
      sq.className = "os-cat-slot";
      sq.dataset.osCatSlot = String(i);
      grid.appendChild(sq);
    }
    div.appendChild(grid);
    return div;
  }

  function _osRenderCatSlots() {
    const grid = document.getElementById("os-catapult-grid");
    if (!grid) return;
    const slots = grid.querySelectorAll("[data-os-cat-slot]");
    slots.forEach((sq, i) => {
      const entry = _catData ? _catData[i] : null;
      if (entry && entry.seat) {
        const color = _seatColor(entry.seat);
        sq.style.setProperty("--os-color", color);
        sq.textContent = OS_TIER_GLYPH[entry.tier] || "░";
        sq.dataset.active = "1";
      } else {
        sq.style.removeProperty("--os-color");
        sq.textContent = "";
        delete sq.dataset.active;
      }
    });
  }

  // Animate parcels flying from each station's diamond to the catapult grid (at DUSK).
  function _osCatLoadAnim() {
    if (!_catData) return;
    const grid = document.getElementById("os-catapult-grid");
    if (!grid) return;
    const slots = grid.querySelectorAll("[data-os-cat-slot]");
    for (let i = 0; i < _catData.length && i < slots.length; i++) {
      const entry = _catData[i];
      if (!entry?.seat) continue;
      const stEl  = document.querySelector(`[data-os-station="${entry.seat}"]`);
      if (!stEl) continue;
      const wrapEl = stEl.querySelector(".os-diamond-wrap") || stEl;
      const wr = wrapEl.getBoundingClientRect();
      const sr = slots[i].getBoundingClientRect();
      const x0 = OS_RIGHT_SEATS.includes(entry.seat) ? wr.left : wr.right;
      const y0 = wr.top + wr.height * 0.5;
      const x1 = sr.left + sr.width  * 0.5;
      const y1 = sr.top  + sr.height * 0.5;
      _osQueuePtAnim(x0, y0, x1, y1, OS_TIER_GLYPH[entry.tier] || "░",
        _seatColor(entry.seat), { dur: 500, ease: "inout", size: 8, delay: i * 50 });
    }
  }

  // Dematerialise each loaded slot in a wave: brief bright flash then the
  // density char cycles down (▓→▒→░→·→gone). Pure DOM, no canvas, no glow.
  function _osCatLaunchAnim() {
    if (!_catData) return;
    const grid = document.getElementById("os-catapult-grid");
    if (!grid) return;
    const slots = grid.querySelectorAll("[data-os-cat-slot]");

    const SEQ   = ["▓", "▒", "░", "·", ""];  // dissolve steps
    const FRAME = 80;   // ms per dissolve step
    const LAG   = 38;   // ms stagger between slots

    let maxEnd = 0;
    for (let i = 0; i < _catData.length && i < slots.length; i++) {
      const entry = _catData[i];
      if (!entry?.seat) continue;
      const sq    = slots[i];
      const start = i * LAG;
      maxEnd = Math.max(maxEnd, start + SEQ.length * FRAME);

      // Flash bright at launch moment
      _catLaunchTimers.push(setTimeout(() => { sq.dataset.firing = "1"; }, start));

      SEQ.forEach((ch, step) => {
        _catLaunchTimers.push(setTimeout(() => {
          sq.textContent = ch;
          delete sq.dataset.firing;
          if (ch === "") {
            delete sq.dataset.active;
            sq.style.removeProperty("--os-color");
          }
        }, start + (step + 1) * FRAME));
      });
    }

    _catLaunchTimers.push(setTimeout(() => {
      _catData = null;
      _osRenderCatSlots();
    }, maxEnd + 60));
  }

  /* ── score ────────────────────────────────────────────────────────── */

  function _osRenderScore(seat, val) {
    const el = document.querySelector(`[data-os-score="${seat}"]`);
    if (el) el.textContent = Number(val).toLocaleString();
  }

  function _osUpdateLeader() {
    if (!_scores || !_activeSeats.length) return;
    let maxScore = -Infinity;
    for (const s of _activeSeats) maxScore = Math.max(maxScore, _scores[s]?.score ?? 0);
    for (const s of _activeSeats) {
      const el = document.querySelector(`[data-os-score="${s}"]`);
      if (!el) continue;
      const leading = (_scores[s]?.score ?? 0) >= maxScore && maxScore > 0;
      el.classList.toggle("os-score--lead", leading);
    }
  }

  /* ── phase ────────────────────────────────────────────────────────── */

  function _osSetPhase(phase) {
    document.querySelectorAll(".os-station").forEach(el => {
      el.classList.toggle("os-station--night", phase === "night");
      el.classList.toggle("os-station--day",   phase === "day");
    });
  }

  /* ── point-to-point canvas animation ────────────────────────────── */

  // Queues an animation between two absolute screen coordinates.
  // Supports `delay` in opts to stagger multiple animations.
  function _osQueuePtAnim(x0, y0, x1, y1, glyph, color, opts) {
    _osEnsureCanvas();
    _anims.push({
      glyph, color, x0, y0, x1, y1,
      dur:   opts?.dur   ?? 600,
      ease:  opts?.ease  ?? "inout",
      size:  opts?.size  ?? 8,
      start: performance.now() + (opts?.delay ?? 0),
      slot: 0, seat: "_cat", dir: "_",
    });
    if (!_animRaf) _animRaf = requestAnimationFrame(_osAnimLoop);
  }

  /* ── animation canvas ─────────────────────────────────────────────── */

  let _animCvs = null;
  let _animCtx = null;
  let _animRaf = null;
  const _anims = [];
  const _animSlot = {};

  function _osEnsureCanvas() {
    if (_animCvs) return;
    _animCvs = document.createElement("canvas");
    _animCvs.style.cssText = "position:fixed;inset:0;width:100%;height:100%;pointer-events:none;z-index:9500";
    _animCvs.width  = window.innerWidth;
    _animCvs.height = window.innerHeight;
    document.body.appendChild(_animCvs);
    _animCtx = _animCvs.getContext("2d");
    window.addEventListener("resize", () => {
      if (!_animCvs) return;
      _animCvs.width  = window.innerWidth;
      _animCvs.height = window.innerHeight;
    });
  }

  function _osEase(raw, kind) {
    if (kind === "in")    return raw * raw;
    if (kind === "out")   return 1 - (1 - raw) * (1 - raw);
    if (kind === "inout") return raw * raw * (3 - 2 * raw);
    return raw;
  }

  function _osQueueAnim(seat, glyph, color, side, dir, opts) {
    _osEnsureCanvas();

    const stEl  = document.querySelector(`[data-os-station="${seat}"]`);
    const mapEl = document.querySelector(".cc-map-area");
    if (!stEl || !mapEl) return;

    const wrapEl = stEl.querySelector(".os-diamond-wrap") || stEl;
    const rr = wrapEl.getBoundingClientRect();
    const mr = mapEl.getBoundingClientRect();
    const sr = stEl.getBoundingClientRect();

    const slot = _animSlot[seat + dir] || 0;
    _animSlot[seat + dir] = slot + 1;

    const yOff = opts?.yOff ?? 0;
    const cy   = rr.top + rr.height * 0.5;

    // Outbound: launch from diamond edge, land 35% into the map.
    // Inbound: start from 35% into the map, arrive at diamond edge.
    // Using rr (diamond wrap) for station anchor, not sr (full panel).
    const mapDepth = mr.width * 0.35;
    let x0, x1, y0, y1;
    if (dir === "out") {
      x0 = side === "left" ? rr.right : rr.left;
      x1 = side === "left" ? mr.left + mapDepth : mr.right - mapDepth;
      y0 = cy;
      y1 = cy + yOff;
    } else {
      x0 = side === "left" ? mr.left + mapDepth : mr.right - mapDepth;
      x1 = side === "left" ? rr.right : rr.left;
      y0 = cy + yOff;
      y1 = cy;
    }

    _anims.push({
      glyph, color, x0, y0, x1, y1,
      dur:   opts?.dur   ?? 600,
      ease:  opts?.ease  ?? "inout",
      size:  opts?.size  ?? 9,
      slot, seat, dir,
      start: performance.now() + (opts?.delay ?? 0),
    });

    if (!_animRaf) _animRaf = requestAnimationFrame(_osAnimLoop);
  }

  function _osAnimLoop(now) {
    if (!_animCtx) return;
    _animCtx.clearRect(0, 0, _animCvs.width, _animCvs.height);

    _animCtx.textAlign    = "center";
    _animCtx.textBaseline = "middle";

    const alive = [];
    for (const a of _anims) {
      const elapsed = now - a.start;
      if (elapsed < 0) { alive.push(a); continue; }  // delayed start not yet reached
      const raw = Math.min(elapsed / a.dur, 1);
      const t   = _osEase(raw, a.ease);
      const x   = a.x0 + (a.x1 - a.x0) * t;
      const y   = a.y0 + (a.y1 - a.y0) * t;

      const dx  = a.x1 - a.x0, dy = a.y1 - a.y0;
      const len = Math.sqrt(dx * dx + dy * dy) || 1;
      const ux  = -dx / len, uy = -dy / len;

      const trailSize = Math.max(6, a.size * 0.65);
      _animCtx.font = `${trailSize}px 'Courier New',monospace`;
      for (let d = 1; d <= 3; d++) {
        _animCtx.globalAlpha = Math.max(0, 0.25 - d * 0.07);
        _animCtx.fillStyle   = a.color;
        _animCtx.fillText("·", x + ux * d * 8, y + uy * d * 8);
      }

      _animCtx.font        = `${a.size}px 'Courier New',monospace`;
      _animCtx.globalAlpha = raw > 0.95 ? 1 - (raw - 0.95) * 20 : 1;
      _animCtx.fillStyle   = a.color;
      _animCtx.fillText(a.glyph, x, y);
      _animCtx.globalAlpha = 1;

      if (raw < 1) {
        alive.push(a);
      } else {
        if ((_animSlot[a.seat + a.dir] || 0) > 0) _animSlot[a.seat + a.dir]--;
      }
    }

    _anims.length = 0;
    _anims.push(...alive);

    if (_anims.length > 0) {
      _animRaf = requestAnimationFrame(_osAnimLoop);
    } else {
      _animCtx.clearRect(0, 0, _animCvs.width, _animCvs.height);
      _animRaf = null;
    }
  }

  /* ── hover cards ─────────────────────────────────────────────────── */

  const _cards     = {};
  const _hideDelay = {};

  function _osBindHover() {
    // Station panels: hover = pre-orbital recap (station obs + orbital obs)
    for (const seat of _activeSeats) {
      const el = document.querySelector(`[data-os-station="${seat}"]`);
      if (!el) continue;
      const key = "st_" + seat;
      el.addEventListener("mouseenter", () => {
        clearTimeout(_hideDelay[key]);
        _osShowCard(key, () => _osBuildStationCard(), el);
      });
      el.addEventListener("mouseleave", () => {
        _hideDelay[key] = setTimeout(() => _osHideCard(key), 120);
      });
    }

    // Catapult panel: hover = catapult grid; click = full post-orbital briefing
    const catEl = document.getElementById("os-catapult");
    if (catEl) {
      const key = "catapult";
      catEl.style.cursor = "pointer";
      catEl.addEventListener("mouseenter", () => {
        clearTimeout(_hideDelay[key]);
        _osShowCard(key, _osBuildCatCard, catEl);
      });
      catEl.addEventListener("mouseleave", () => {
        _hideDelay[key] = setTimeout(() => _osHideCard(key), 120);
      });
      catEl.addEventListener("click", () => {
        if (typeof window._osOpenReport === "function" && _currentDay)
          window._osOpenReport("briefing", _currentDay);
      });
    }
  }

  function _osShowCard(key, builder, anchorEl) {
    _osHideCard(key);
    const card = builder();
    if (!card) return;
    document.body.appendChild(card);
    _cards[key] = card;

    card.addEventListener("mouseenter", () => clearTimeout(_hideDelay[key]));
    card.addEventListener("mouseleave", () => {
      _hideDelay[key] = setTimeout(() => _osHideCard(key), 80);
    });

    // Position: right of anchor for left-side elements, left of anchor for right-side
    const ar   = anchorEl.getBoundingClientRect();
    const onLeft = ar.left < window.innerWidth / 2;
    // After inserting, measure and clamp vertically
    requestAnimationFrame(() => {
      const ch = card.offsetHeight;
      const top = Math.max(4, Math.min(ar.top, window.innerHeight - ch - 8));
      card.style.top = top + "px";
      if (onLeft) {
        card.style.left  = (ar.right + 6) + "px";
      } else {
        card.style.right = (window.innerWidth - ar.left + 6) + "px";
      }
    });
  }

  function _osHideCard(key) {
    if (_cards[key]) { _cards[key].remove(); delete _cards[key]; }
  }

  // Station hover: STATION OBSERVATIONS (pre) + ORBITAL OBSERVATIONS for current day
  function _osBuildStationCard() {
    const day = _currentDay;
    if (!day || !window._osRenderStationObs || !window._osRenderOrbitalObs) return null;
    const card = document.createElement("div");
    card.className = "os-hover-card";
    try {
      card.appendChild(window._osRenderStationObs(
        day, "pre", "STATION OBSERVATIONS · end of night"
      ));
      card.appendChild(window._osRenderOrbitalObs(day));
    } catch (e) {
      card.textContent = "// data not available";
    }
    return card;
  }

  // Catapult hover: shipping catapult grid for current day
  function _osBuildCatCard() {
    const day = _currentDay;
    if (!day || !window._osGetCatapultBlob || !window._osRenderCatGrid) return null;
    const blob = window._osGetCatapultBlob(day);
    if (!blob) return null;
    const cat   = blob.catapult || {};
    const slots = Array.isArray(cat.slot_assignments) ? cat.slot_assignments : [];

    const card = document.createElement("div");
    card.className = "os-hover-card os-hover-card--cat";

    const head = document.createElement("div");
    head.className = "os-hover-card-head";
    head.textContent =
      `SHIPPING CATAPULT · ${cat.slots_awarded ?? 0}/${cat.slots_total ?? 20} slots shipped`;
    card.appendChild(head);

    if (!slots.length) {
      const dim = document.createElement("div");
      dim.className = "os-hover-card-dim";
      dim.textContent = "// quiet orbit";
      card.appendChild(dim);
    } else {
      card.appendChild(window._osRenderCatGrid(slots));
      if (window._osRenderCatLegend) {
        const allSeats = window._osGetActiveSeatsList ? window._osGetActiveSeatsList() : [];
        card.appendChild(window._osRenderCatLegend(slots, allSeats));
      }
    }

    const hint = document.createElement("div");
    hint.className = "os-hover-card-hint";
    hint.textContent = "click — full briefing";
    card.appendChild(hint);
    return card;
  }

  /* ── fit map to available width ──────────────────────────────────── */

  // Compute and apply the font-size that makes the map fill the available width.
  // Also sets MAP_ZOOM_DEFAULT so "100%" always means fit-to-width.
  function _osFitMapZoom(attempt) {
    const mapArea     = document.querySelector(".cc-map-area");
    const viewport    = document.querySelector(".cc-map-viewport");
    const mapGrid     = document.querySelector("#map-player .map-grid");
    const gridW       = mapGrid && mapGrid.getBoundingClientRect().width;
    if (!mapArea || !viewport || !gridW) {
      if ((attempt || 0) < 30) setTimeout(() => _osFitMapZoom((attempt || 0) + 1), 80);
      return;
    }
    const currentFont = parseFloat(
      getComputedStyle(document.documentElement).getPropertyValue("--map-font-size")
    ) || 14;
    // Use scrollHeight to get the natural (unclipped) grid height
    const gridH   = mapGrid.scrollHeight || mapGrid.getBoundingClientRect().height;
    const targetW = (currentFont * mapArea.clientWidth)   / gridW;
    const targetH = (currentFont * viewport.clientHeight) / gridH;
    const target  = Math.min(targetW, targetH);
    if (typeof window._osSetMapZoomDefault === "function") window._osSetMapZoomDefault(target);
    if (typeof window._osApplyMapZoom      === "function") window._osApplyMapZoom(target);
  }

  // Re-fit whenever the map area is resized (window resize, panel changes, etc.)
  function _osInstallResizeFit() {
    const mapArea = document.querySelector(".cc-map-area");
    if (!mapArea || !window.ResizeObserver) return;
    let pending = false;
    new ResizeObserver(() => {
      if (pending) return;
      pending = true;
      requestAnimationFrame(() => { pending = false; _osFitMapZoom(0); });
    }).observe(mapArea);
  }

  /* ── DOM ready ────────────────────────────────────────────────────── */

  if (window._socOrbitalData) {
    _viewerSeat = window._socReplayViewSeat || null;
    window.osOnOrbitalDataLoaded();
  }
})();
