/* sea_of_colours · manual — interactive.
 *
 * paintTile() mirrors app.js:2155 computeParcelPaintFallback and
 * render.py cell_visual, so a manual tile paints identically to a live
 * game tile at the same purity.
 */
(() => {
  "use strict";

  // ─── constants ─────────────────────────────────────────────────
  const TILE = { EMPTY: 0, GREEN: 1, RED: 2, BLUE: 3 };
  const VOID = "rgb(14,11,22)";
  const RED_FG = "rgb(255,0,0)";
  const BLUE_FG = "rgb(59,143,224)";
  const GREEN_FG = "rgb(63,185,80)";
  const CH_LIGHT = "\u2591\u2591"; // ░░
  const CH_MED   = "\u2592\u2592"; // ▒▒
  const CH_HEAVY = "\u2593\u2593"; // ▓▓
  const CH_FULL  = "\u2588\u2588"; // ██
  const GLYPH_HARVESTER = "X";
  const GLYPH_PROBE = "\u00B7"; // ·
  const GLYPH_LIFT = "\u25B2";  // ▲

  const TIER_INFO_RED = [
    { name: "trace", range: "0-50",   glyph: CH_LIGHT, body: "Seam edge — 1-2 cells from non-RED. Cheap to reach, cheap to score." },
    { name: "vein",  range: "51-150", glyph: CH_MED,   body: "Shallow interior. Steady payload if you can commit a Nox to it." },
    { name: "mass",  range: "151-254",glyph: CH_HEAVY, body: "Deep interior, just shy of the core. High per-parcel value." },
    { name: "pure",  range: "255",    glyph: CH_FULL,  body: "Seam core. Manhattan depth ≥ 3. 255 × 3.0 = 765 pts per parcel." },
  ];
  const TIER_INFO_BLUE = [
    { name: "shallow", range: "0-50",   glyph: CH_LIGHT, body: "Pocket edge. The engine floors purity at 40 — no fade-to-nothing." },
    { name: "mid",     range: "51-150", glyph: CH_MED,   body: "Between rim and peak. The bread-and-butter of a blue haul." },
    { name: "sink",    range: "151-254",glyph: CH_HEAVY, body: "Near the peak. Chebyshev distance transform picks the pocket centre." },
    { name: "deep",    range: "255",    glyph: CH_FULL,  body: "The pocket peak — one cell per connected blob. Fissile." },
  ];

  // RULEBOOK §2.2 red tier bounds + §3.1 quality multipliers.
  // score(parcel) = effective_purity × MULT[tier].
  const TIER_BOUNDS = {
    trace: [1, 50],
    vein:  [51, 150],
    mass:  [151, 254],
    pure:  [255, 255],
  };
  const RED_MULT = { trace: 0.75, vein: 1.0, mass: 1.5, pure: 3.0 };
  function randPurity(tier) {
    const [lo, hi] = TIER_BOUNDS[tier];
    return lo + Math.floor(Math.random() * (hi - lo + 1));
  }
  function tierOf(purity) {
    if (purity >= 255) return "pure";
    if (purity >= 151) return "mass";
    if (purity >= 51)  return "vein";
    return "trace";
  }

  /**
   * Paint a tile → { fg, bg, ch }. Mirrors app.js computeParcelPaintFallback.
   * @param {number} tile  TILE.EMPTY/GREEN/RED/BLUE
   * @param {number} purity 0..255
   */
  function paintTile(tile, purity) {
    const p = Math.max(0, Math.min(255, purity | 0));
    if (tile === TILE.EMPTY) return { fg: VOID, bg: VOID, ch: CH_FULL };
    if (tile === TILE.GREEN) return { fg: GREEN_FG, bg: VOID, ch: CH_FULL };
    const fg = tile === TILE.RED ? RED_FG : BLUE_FG;
    let ch;
    if (p >= 255)      ch = CH_FULL;
    else if (p >= 151) ch = CH_HEAVY;
    else if (p >= 51)  ch = CH_MED;
    else               ch = CH_LIGHT;
    return { fg, bg: VOID, ch };
  }

  /**
   * Render a board (grid of cells) into `host`. Each cell is:
   *   { tile, purity, entity?: 'X'|'·'|'▲', trail?: 1..4, fog?: bool }
   * Board dimensions default to a single row inferred from cells.length.
   *
   * Cells are ABSOLUTELY POSITIONED — we tried CSS grid and it kept
   * inflating rows via inherited line-height. Absolute positioning
   * anchors every cell to exact left/top pixel coords so tiles butt
   * up edge-to-edge with no possibility of gaps.
   */
  function renderBoard(host, cells, opts = {}) {
    host.innerHTML = "";
    const cols = opts.cols || cells.length;
    const rows = opts.rows || Math.ceil(cells.length / cols);
    // Cell dimensions in px — read from the caller's CSS custom-properties
    // if set, else fall back to the :root defaults (24×24). We compute
    // numeric values so we can also drive the absolute left/top math.
    const cellW = opts.cellW != null ? opts.cellW : 24;
    const cellH = opts.cellH != null ? opts.cellH : 24;
    const board = document.createElement("div");
    board.className = "mn-board";
    board.style.setProperty("--cell-w", `${cellW}px`);
    board.style.setProperty("--cell-h", `${cellH}px`);
    board.style.width  = `${cols * cellW}px`;
    board.style.height = `${rows * cellH}px`;

    for (let i = 0; i < cells.length; i++) {
      const c = cells[i] || { tile: TILE.EMPTY, purity: 0 };
      const paint = paintTile(c.tile, c.purity);
      const cellEl = document.createElement("div");
      cellEl.className = "mn-cell";
      cellEl.dataset.idx = String(i);
      cellEl.style.left = `${(i % cols) * cellW}px`;
      cellEl.style.top  = `${Math.floor(i / cols) * cellH}px`;
      cellEl.style.width  = `${cellW}px`;
      cellEl.style.height = `${cellH}px`;

      const terr = document.createElement("span");
      terr.className = "mn-cell-terrain";
      terr.style.background = paint.bg;
      terr.style.color = paint.fg;
      terr.textContent = paint.ch;
      cellEl.appendChild(terr);

      const trail = document.createElement("span");
      trail.className = "mn-cell-trail";
      if (c.trail) {
        trail.textContent = trailGlyph(c.trail);
        trail.classList.add("is-on");
      }
      cellEl.appendChild(trail);

      const ent = document.createElement("span");
      ent.className = "mn-cell-entity";
      if (c.entity) ent.textContent = c.entity;
      cellEl.appendChild(ent);

      const fog = document.createElement("span");
      fog.className = "mn-cell-fog";
      // Engine fog: ░░ (light shade block) in --dim @ opacity 0.24 —
      // see app.js:1904 + styles.css:1357,1372.
      fog.textContent = CH_LIGHT;
      if (c.fog) {
        cellEl.classList.add("is-fogged");
      } else {
        fog.classList.add("is-clear");
      }
      cellEl.appendChild(fog);

      board.appendChild(cellEl);
    }
    host.appendChild(board);
    return board;
  }

  function trailGlyph(n) {
    if (n >= 4) return CH_FULL;
    if (n === 3) return CH_HEAVY;
    if (n === 2) return CH_MED;
    return CH_LIGHT;
  }

  // ─── mutation helpers ─────────────────────────────────────────
  function boardCell(board, idx) { return board.children[idx]; }
  function setTerrain(cellEl, tile, purity) {
    const paint = paintTile(tile, purity);
    const t = cellEl.querySelector(".mn-cell-terrain");
    t.style.background = paint.bg;
    t.style.color = paint.fg;
    t.textContent = paint.ch;
  }
  function setEntity(cellEl, glyph, seatVar = "--seat-p1") {
    const e = cellEl.querySelector(".mn-cell-entity");
    e.textContent = glyph || "";
    e.style.color = glyph ? `var(${seatVar})` : "";
    // Clear any probe classes on transition — they'll be re-added by
    // setProbe() if this entity is actually a fresh probe.
    e.classList.remove(
      "mn-cell-entity--probe",
      "mn-cell-entity--probe-life-1",
      "mn-cell-entity--probe-life-2",
    );
  }
  /**
   * Set a probe with `nightsRemaining` (1-3+). Mirrors app.js:1765-1775 —
   * rings = clamp(nights - 1, 0, 2). 3+ nights → 2 rings (fresh),
   * 2 nights → 1 ring, 1 night → bare · glyph.
   */
  function setProbe(cellEl, nightsRemaining, seatVar = "--seat-p1") {
    setEntity(cellEl, GLYPH_PROBE, seatVar);
    const e = cellEl.querySelector(".mn-cell-entity");
    e.classList.add("mn-cell-entity--probe");
    const rings = Math.max(0, Math.min(2, (nightsRemaining | 0) - 1));
    if (rings > 0) e.classList.add(`mn-cell-entity--probe-life-${rings}`);
  }
  function bumpTrail(cellEl, currentByIdx, idx) {
    const n = (currentByIdx[idx] || 0) + 1;
    currentByIdx[idx] = n;
    const t = cellEl.querySelector(".mn-cell-trail");
    t.textContent = trailGlyph(n);
    t.classList.add("is-on");
  }
  function setFog(cellEl, on) {
    const f = cellEl.querySelector(".mn-cell-fog");
    if (on) {
      f.classList.remove("is-clear");
      cellEl.classList.add("is-fogged");
    } else {
      f.classList.add("is-clear");
      cellEl.classList.remove("is-fogged");
    }
  }

  // ─── tooltip ──────────────────────────────────────────────────
  const ttEl = document.getElementById("mn-tt");
  function ttShow(anchor, title, body, cite) {
    ttEl.innerHTML =
      `<div class="mn-tt-title">${title}</div>` +
      `<div class="mn-tt-body">${body}</div>` +
      (cite ? `<div class="mn-tt-cite">${cite}</div>` : "");
    const r = anchor.getBoundingClientRect();
    const cx = r.left + r.width / 2;
    const top = r.bottom + 8;
    ttEl.style.left = `${Math.min(window.innerWidth - 300, Math.max(8, cx - 140))}px`;
    ttEl.style.top = `${top}px`;
    ttEl.classList.add("is-on");
    ttEl.setAttribute("aria-hidden", "false");
  }
  function ttHide() {
    ttEl.classList.remove("is-on");
    ttEl.setAttribute("aria-hidden", "true");
  }

  function attachTierTooltip(cellEl, tier, kind) {
    cellEl.addEventListener("mouseenter", () => {
      const title = `${kind.toUpperCase()} · ${tier.name.toUpperCase()}`;
      const body = `<b>purity ${tier.range}</b> — ${tier.body}`;
      const cite = kind === "red" ? "RULEBOOK §2.2" : "RULEBOOK §2.4";
      ttShow(cellEl, title, body, cite);
    });
    cellEl.addEventListener("mouseleave", ttHide);
    cellEl.addEventListener("focusin",  () => cellEl.dispatchEvent(new Event("mouseenter")));
    cellEl.addEventListener("focusout", ttHide);
    cellEl.tabIndex = 0;
  }

  // ─── tab wiring ───────────────────────────────────────────────
  const tabs = Array.from(document.querySelectorAll(".mn-tab"));
  const panes = Array.from(document.querySelectorAll(".mn-tabpane"));
  function activateTab(name) {
    tabs.forEach((t) => {
      const on = t.dataset.tab === name;
      t.classList.toggle("is-active", on);
      t.setAttribute("aria-selected", String(on));
    });
    panes.forEach((p) => p.classList.toggle("is-active", p.dataset.tabpane === name));
    if (name === "tiles") tab1_render();
    if (name === "purities") tab2_render();
    if (name === "loop") tab3_start(); else tab3_stop();
    if (name === "orders") tab4_start(); else tab4_stop();
    if (name === "vision") tab5_start(); else tab5_stop();
    if (name === "opponents") tab6_start(); else tab6_stop();
    if (name === "maps") tab7_start(); else tab7_stop();
    if (name === "season") tab8_start(); else tab8_stop();
    if (name === "probes") tab9_start(); else tab9_stop();
    if (name === "harvesters") tab10_start(); else tab10_stop();
  }
  tabs.forEach((t) => t.addEventListener("click", () => activateTab(t.dataset.tab)));
  document.getElementById("mn-tab-prev").addEventListener("click", () => stepTab(-1));
  document.getElementById("mn-tab-next").addEventListener("click", () => stepTab(+1));
  window.addEventListener("keydown", (e) => {
    if (e.target && /INPUT|TEXTAREA|SELECT/.test(e.target.tagName)) return;
    // Which tab is active?
    const activeTab = tabs.find((t) => t.classList.contains("is-active"))?.dataset.tab;
    if (e.key === "ArrowLeft") {
      e.preventDefault();
      if (activeTab === "loop" && tab3_state && tab3_state.goStage) {
        tab3_state.goStage(tab3_state.stageIdx - 1);
      } else if (activeTab === "orders" && tab4_state && tab4_state.goStage) {
        tab4_state.goStage(tab4_state.stageIdx - 1);
      } else if (activeTab === "vision" && tab5_state && tab5_state.goStage) {
        tab5_state.goStage(tab5_state.stageIdx - 1);
      } else if (activeTab === "opponents" && tab6_state && tab6_state.goStage) {
        tab6_state.goStage(tab6_state.stageIdx - 1);
      } else if (activeTab === "season" && tab8_state && tab8_state.goStage) {
        tab8_state.goStage(tab8_state.stageIdx - 1);
      } else if (activeTab === "probes" && tab9_state && tab9_state.goStage) {
        tab9_state.goStage(tab9_state.stageIdx - 1);
      } else if (activeTab === "harvesters" && tab10_state && tab10_state.goStage) {
        tab10_state.goStage(tab10_state.stageIdx - 1);
      } else {
        stepTab(-1);
      }
    }
    if (e.key === "ArrowRight") {
      e.preventDefault();
      if (activeTab === "loop" && tab3_state && tab3_state.goStage) {
        tab3_state.goStage(tab3_state.stageIdx + 1);
      } else if (activeTab === "orders" && tab4_state && tab4_state.goStage) {
        tab4_state.goStage(tab4_state.stageIdx + 1);
      } else if (activeTab === "vision" && tab5_state && tab5_state.goStage) {
        tab5_state.goStage(tab5_state.stageIdx + 1);
      } else if (activeTab === "opponents" && tab6_state && tab6_state.goStage) {
        tab6_state.goStage(tab6_state.stageIdx + 1);
      } else if (activeTab === "season" && tab8_state && tab8_state.goStage) {
        tab8_state.goStage(tab8_state.stageIdx + 1);
      } else if (activeTab === "probes" && tab9_state && tab9_state.goStage) {
        tab9_state.goStage(tab9_state.stageIdx + 1);
      } else if (activeTab === "harvesters" && tab10_state && tab10_state.goStage) {
        tab10_state.goStage(tab10_state.stageIdx + 1);
      } else {
        stepTab(+1);
      }
    }
  });
  function stepTab(dir) {
    const idx = tabs.findIndex((t) => t.classList.contains("is-active"));
    const nx = (idx + dir + tabs.length) % tabs.length;
    activateTab(tabs[nx].dataset.tab);
  }

  // ═══════════════════════════════════════════════════════════════
  // TAB 1 — meet the tiles
  // ═══════════════════════════════════════════════════════════════
  function tab1_render() {
    const host = document.getElementById("mn-board-tiles");
    // 5-cell strip: RED_pure — empty — BLUE_deep — empty — GREEN
    const cells = [
      { tile: TILE.RED,   purity: 255 },
      { tile: TILE.EMPTY, purity: 0   },
      { tile: TILE.BLUE,  purity: 255 },
      { tile: TILE.EMPTY, purity: 0   },
      { tile: TILE.GREEN, purity: 255 },
    ];
    const board = renderBoard(host, cells, { cols: 5, rows: 1, cellW: 48, cellH: 48 });
    // pulse each terrain tile once on enter (skip the empty gap cells)
    [0, 2, 4].forEach((i, k) => {
      setTimeout(() => {
        boardCell(board, i).classList.add("is-pulsing");
      }, 220 + k * 220);
    });
    // hover tooltips per named tile
    boardCell(board, 0).addEventListener("mouseenter", () =>
      ttShow(boardCell(board, 0), "RED · the prize",
        "<b>the Red.</b> A pinch powers a city for a year. Every parcel you catapult home scores tier-weighted. §3.3",
        "RULEBOOK §3.3")
    );
    boardCell(board, 0).addEventListener("mouseleave", ttHide);
    boardCell(board, 2).addEventListener("mouseenter", () =>
      ttShow(boardCell(board, 2), "BLUE · fissile",
        "<b>radioactive pocket.</b> Funds weapons and refining. Glows through fog — every pocket puts a blue-sign on the orbital map. §3.5 · §4.10",
        "RULEBOOK §3.5")
    );
    boardCell(board, 2).addEventListener("mouseleave", ttHide);
    boardCell(board, 4).addEventListener("mouseenter", () =>
      ttShow(boardCell(board, 4), "GREEN · liability",
        "<b>poison.</b> Occupies hold. Costs −100 per parcel if it's still in the vault at Aurora. Every RED you harvest leaves a GREEN behind. §3.4",
        "RULEBOOK §3.4")
    );
    boardCell(board, 4).addEventListener("mouseleave", ttHide);
    [0, 2, 4].forEach((i) => (boardCell(board, i).tabIndex = 0));
  }

  // ═══════════════════════════════════════════════════════════════
  // TAB 2 — purities + harvester trail
  // ═══════════════════════════════════════════════════════════════
  let tab2_timer = null;
  function tab2_stop() {
    if (tab2_timer) { clearTimeout(tab2_timer); tab2_timer = null; }
  }
  function tab2_render() {
    tab2_stop();
    const host = document.getElementById("mn-board-purities");
    const status = document.getElementById("mn-purities-status");
    // Row layout (13 cells wide, 3 rows tall):
    //   row 0: RED trace vein mass pure  _ pad _ BLUE shallow mid sink deep
    //   row 1: (labels drawn below, via css-free glyphs — keep simple)
    //   row 2: (harvester lane: 4 red cells with harvester + trail)
    // For simplicity: 2 rows.
    //   row 0: RED_TR RED_VE RED_MA RED_PU  _  BLU_SH BLU_MI BLU_SI BLU_DP  _  GREEN
    //   row 1: (empty)                          (empty)                    HARVESTER LANE (4 red cells)
    // Actually simpler: two independent boards would be cleaner, but keep one.
    const cols = 13;
    const rows = 3;
    const total = cols * rows;
    const cells = new Array(total).fill(null).map(() => ({ tile: TILE.EMPTY, purity: 0 }));

    // Row 0: red ramp (cols 0..3), gap 4, blue ramp (cols 5..8), gap 9, green (col 10)
    const redRamp = [25, 100, 200, 255];
    const blueRamp = [25, 100, 200, 255];
    redRamp.forEach((p, i)  => (cells[0 * cols + i]     = { tile: TILE.RED,  purity: p }));
    blueRamp.forEach((p, i) => (cells[0 * cols + 5 + i] = { tile: TILE.BLUE, purity: p }));
    cells[0 * cols + 10] = { tile: TILE.GREEN, purity: 255 };

    // Row 2: harvester lane — 4 RED cells (trace, vein, mass, pure) followed by empty gap
    redRamp.forEach((p, i) => (cells[2 * cols + i] = { tile: TILE.RED, purity: p }));

    const board = renderBoard(host, cells, { cols, rows });

    // Attach tooltips on each purity cell (red row + blue row)
    for (let i = 0; i < 4; i++) {
      attachTierTooltip(boardCell(board, i),     TIER_INFO_RED[i],  "red");
      attachTierTooltip(boardCell(board, 5 + i), TIER_INFO_BLUE[i], "blue");
    }
    // Green cell tooltip
    const greenIdx = 10;
    boardCell(board, greenIdx).tabIndex = 0;
    boardCell(board, greenIdx).addEventListener("mouseenter", () =>
      ttShow(boardCell(board, greenIdx), "GREEN",
        "Always purity 255 in v0.2 — no tiers yet. Poisons whatever is beneath. §3.4",
        "RULEBOOK §3.4")
    );
    boardCell(board, greenIdx).addEventListener("mouseleave", ttHide);

    // Harvester animation on the bottom lane (row 2, cols 0..3)
    const trailByIdx = {};
    const laneStart = 2 * cols;
    // Drop the harvester on col 0 (trace red). This immediately harvests → GREEN + trail.
    // Then step 1..3 through vein/mass/pure — each converts.
    const laneCells = [0, 1, 2, 3].map((c) => boardCell(board, laneStart + c));

    function playHarvest() {
      // Reset lane visually
      laneCells.forEach((cellEl, i) => {
        const t = cellEl.querySelector(".mn-cell-trail");
        t.classList.remove("is-on");
        t.textContent = "";
        setEntity(cellEl, "");
        setTerrain(cellEl, TILE.RED, redRamp[i]);
        delete trailByIdx[laneStart + i];
      });
      status.textContent = "# X drops on trace-red";

      // Drop on col 0
      tab2_timer = setTimeout(() => {
        setEntity(laneCells[0], GLYPH_HARVESTER);
        setTerrain(laneCells[0], TILE.GREEN, 255);
        bumpTrail(laneCells[0], trailByIdx, laneStart + 0);
        status.textContent = "# harvest: RED → GREEN, trail ░░";
        step(1);
      }, 500);

      function step(k) {
        if (k > 3) {
          // Final: bump trail on col 0 again to show "revisit" density if we walked back
          status.textContent = "# 4 parcels hoarded · harvester ready for lift";
          return;
        }
        tab2_timer = setTimeout(() => {
          setEntity(laneCells[k - 1], "");
          setEntity(laneCells[k], GLYPH_HARVESTER);
          setTerrain(laneCells[k], TILE.GREEN, 255);
          bumpTrail(laneCells[k], trailByIdx, laneStart + k);
          const tierName = TIER_INFO_RED[k].name;
          status.textContent = `# step ${k}: harvested ${tierName} (purity ${redRamp[k]})`;
          step(k + 1);
        }, 750);
      }
    }
    document.getElementById("mn-purities-replay").onclick = playHarvest;

    // First run on entering the tab
    tab2_timer = setTimeout(playHarvest, 400);
  }

  // ═══════════════════════════════════════════════════════════════
  // TAB 3 — fog → probe → harvest → lift → fog loop
  //
  // Animations ported from the production engine:
  //   probe arc    ← app.js spawnProbeTrail (8654-8804)
  //   orblift arc  ← app.js runOrbitalArcAnimation (7447-7616)
  //
  // Both use position:fixed nodes appended to document.body so they
  // survive DOM repaints and use viewport-relative geometry, matching
  // the engine's own scheme.
  // ═══════════════════════════════════════════════════════════════
  let tab3_state = null;
  function tab3_stop() {
    if (tab3_state) {
      tab3_state.stopped = true;
      tab3_state.timers.forEach((t) => clearTimeout(t));
      tab3_state.timers = [];
      if (tab3_state.heatRaf) cancelAnimationFrame(tab3_state.heatRaf);
      tab3_state.heatRaf = null;
      // remove any lingering fx nodes
      tab3_state.fxNodes.forEach((n) => n.remove());
      tab3_state.fxNodes.clear();
      tab3_state = null;
    }
  }

  /**
   * spawnProbeTrail — port of server/static/app.js:8654-8804.
   *
   * Fires a probe from (toX+360, toY-360) in viewport coords to the
   * centre of `landingCell`. Path is a quadratic bezier with a
   * perpendicular midpoint offset. Trail is written per-pixel via
   * Bresenham into an ImageData buffer, additively blended. Landing
   * flash: player-coloured square, 280ms fade, size grows from
   * 0.35*cw to 0.90*cw. Trail pixels then random-fade individually.
   */
  function spawnProbeTrail(landingCell, trailColor, probeColor, onLand, durationMs, state) {
    if (typeof durationMs !== "number") durationMs = 540;
    const cellRect = landingCell.getBoundingClientRect();
    // Use the .mn-loop-stage that OWNS the landing cell — not document's
    // first match. Tab 3 and tab 4 both have a .mn-loop-stage, and the
    // wrong one has a zero-sized rect when its pane is hidden, which
    // would clip the trail canvas to nothing.
    const ownerStage = landingCell.closest(".mn-loop-stage")
                    || document.querySelector(".mn-tabpane.is-active .mn-loop-stage")
                    || document.querySelector(".mn-loop-stage");
    const stageRect = ownerStage.getBoundingClientRect();
    const cw = cellRect.width;
    const toX = cellRect.left + cw / 2;
    const toY = cellRect.top + cellRect.height / 2;
    const fromX = toX + 360;
    const fromY = toY - 360;
    const dx = toX - fromX, dy = toY - fromY;
    const len = Math.sqrt(dx * dx + dy * dy);
    const perpX = -dy / len, perpY = dx / len;
    const curveMag = (Math.random() < 0.5 ? 1 : -1) * (0.4 + Math.random() * 0.5) * cw;
    const cpX = (fromX + toX) / 2 + perpX * curveMag;
    const cpY = (fromY + toY) / 2 + perpY * curveMag;

    function parseHex(h) {
      const n = parseInt(h.replace("#", ""), 16);
      return [(n >> 16) & 0xff, (n >> 8) & 0xff, n & 0xff];
    }
    const [tr, tg, tb] = parseHex(trailColor);
    const [pr, pg, pb] = parseHex(probeColor);

    const cW = window.innerWidth, cH = window.innerHeight;
    const canvas = document.createElement("canvas");
    canvas.width = cW;
    canvas.height = cH;
    canvas.className = "mn-fx-canvas";
    canvas.style.cssText = "position:fixed;left:0;top:0;pointer-events:none;z-index:9";
    document.body.appendChild(canvas);
    state.fxNodes.add(canvas);
    const ctx2 = canvas.getContext("2d");

    const trailPx = [];
    let prevX = null, prevY = null;
    let landed = false, onLandFired = false, landFlashStart = -1;
    const startT = performance.now();

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

    // Clip to the loop-stage viewport rect so trail pixels straying
    // outside the board are hidden (mirrors app.js clipRect logic).
    const clipL = Math.floor(stageRect.left);
    const clipT = Math.floor(stageRect.top);
    const clipR = Math.ceil(stageRect.right);
    const clipB = Math.ceil(stageRect.bottom);

    function tick(now) {
      if (state.stopped || !document.body.contains(canvas)) return;
      const elapsed = now - startT;
      const t = Math.min(1, elapsed / durationMs);
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
          tp.startFadeAt = now + Math.random() * 900;
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

      if (!landed) {
        ctx2.save();
        ctx2.beginPath();
        ctx2.rect(clipL, clipT, clipR - clipL, clipB - clipT);
        ctx2.clip();
        ctx2.fillStyle = `rgb(${pr},${pg},${pb})`;
        ctx2.fillRect(cx - 2, cy - 2, 4, 4);
        ctx2.restore();
      }

      if (landed && !anyAlive) {
        canvas.remove();
        state.fxNodes.delete(canvas);
        return;
      }
      requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }

  /**
   * runOrbitalArcAnimation — port of server/static/app.js:7447-7616.
   *
   * One lifter ▲ sweeps east-to-west or west-to-east across the stage
   * on a cubic bezier arc, targeting the cell ABOVE the drop tile
   * (arcCell y-1). Duration 1100ms, easing accelerates away from the
   * edges (fast entry, slow at t=0.5, fast exit). At t=0.5 the cargo
   * (X harvester) is deposited or picked up.
   */
  function runOrbitalArcAnimation(boardEl, targetCellEl, kind, seatVar, cargoGlyph, onDeposit, state) {
    // Owner-stage lookup so tab-4 orblifts don't clip against tab-3's
    // hidden stage rect (same bug as spawnProbeTrail).
    const stage = targetCellEl.closest(".mn-loop-stage")
              || document.querySelector(".mn-tabpane.is-active .mn-loop-stage")
              || document.querySelector(".mn-loop-stage");
    const stageRect = stage.getBoundingClientRect();
    const cellRect = targetCellEl.getBoundingClientRect();
    const cw = cellRect.width, ch = cellRect.height;
    // Aim the arc one row above the target so the lifter "swoops" onto it.
    const cx = cellRect.left + cw * 0.5;
    const cy = cellRect.top + ch * 0.5 - ch;

    const goingRight = Math.random() < 0.5;
    const tilt = (Math.random() - 0.5) * 0.7;
    const dax = goingRight ? Math.cos(tilt) : -Math.cos(tilt);
    const day = Math.sin(tilt);

    function edgeT(ox, oy, ddx, ddy) {
      const ts = [];
      if (Math.abs(ddx) > 1e-6) ts.push(ddx > 0 ? (stageRect.right - ox) / ddx : (stageRect.left - ox) / ddx);
      if (Math.abs(ddy) > 1e-6) ts.push(ddy > 0 ? (stageRect.bottom - oy) / ddy : (stageRect.top - oy) / ddy);
      const valid = ts.filter((t) => t > 2);
      return valid.length ? Math.min(...valid) : Math.max(stageRect.width, stageRect.height);
    }

    const tFwd = edgeT(cx, cy, dax, day);
    const tBck = edgeT(cx, cy, -dax, -day);
    const ax = cx + dax * tFwd, ay = cy + day * tFwd;
    const bx = cx - dax * tBck, by = cy - day * tBck;
    const perpX = -day, perpY = dax;
    const curve = Math.min(stageRect.width, stageRect.height) * 0.28 * (Math.random() < 0.5 ? 1 : -1);
    const midX = (8 * cx - ax - bx) / 6;
    const midY = (8 * cy - ay - by) / 6;
    const c1x = midX + perpX * curve, c1y = midY + perpY * curve;
    const c2x = midX - perpX * curve, c2y = midY - perpY * curve;

    const isPickup = kind === "pickup";

    const ghost = document.createElement("span");
    ghost.className = "mn-orblift-ghost";
    ghost.style.width = `${Math.round(cw)}px`;
    ghost.style.height = `${Math.round(ch)}px`;
    ghost.style.color = `var(${seatVar})`;
    ghost.style.fontSize = `${Math.round(cw * 1.1)}px`;

    const lifterEl = document.createElement("span");
    lifterEl.className = "mn-orblift-glyph";
    lifterEl.textContent = GLYPH_LIFT;
    ghost.appendChild(lifterEl);

    const cargoEl = document.createElement("span");
    cargoEl.className = "mn-orblift-cargo";
    cargoEl.textContent = cargoGlyph || GLYPH_HARVESTER;
    cargoEl.style.color = `var(${seatVar})`;
    cargoEl.style.fontSize = `${Math.round(cw * 0.8)}px`;
    if (!isPickup) ghost.appendChild(cargoEl);

    document.body.appendChild(ghost);
    state.fxNodes.add(ghost);

    // Engine easing (7559-7562): fast near edges, slow near t=0.5.
    function easing(t) {
      if (t <= 0.5) { const u = t * 2; return 0.5 * (1 - Math.pow(1 - u, 2.5)); }
      const u = (t - 0.5) * 2;
      return 0.5 + 0.5 * Math.pow(u, 2.5);
    }
    function bez(p, s, cc1, cc2, e) {
      const q = 1 - p;
      return q*q*q*s + 3*q*q*p*cc1 + 3*q*p*p*cc2 + p*p*p*e;
    }

    const DURATION = 1100;
    let midTriggered = false;
    const t0 = performance.now();

    function tick(now) {
      if (state.stopped || !document.body.contains(ghost)) return;
      const rawT = Math.min(1, (now - t0) / DURATION);
      const p = easing(rawT);
      const tx = bez(p, ax, c1x, c2x, bx) - cw * 0.5;
      const ty = bez(p, ay, c1y, c2y, by) - ch * 0.5;
      ghost.style.transform = `translate(${tx.toFixed(1)}px, ${ty.toFixed(1)}px)`;

      if (!midTriggered && rawT >= 0.5) {
        midTriggered = true;
        if (!isPickup) {
          cargoEl.remove();
          if (typeof onDeposit === "function") try { onDeposit(); } catch (_) {}
        } else {
          ghost.appendChild(cargoEl);
          if (typeof onDeposit === "function") try { onDeposit(); } catch (_) {}
        }
      }
      if (rawT >= 1) {
        ghost.remove();
        state.fxNodes.delete(ghost);
        return;
      }
      requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }

  // ─── event log ────────────────────────────────────────────────
  function pushLog(kind, msg, logId) {
    const el = document.getElementById(logId || "mn-eventlog");
    if (!el) return;
    const now = new Date();
    const hh = String(now.getHours()).padStart(2, "0");
    const mm = String(now.getMinutes()).padStart(2, "0");
    const ss = String(now.getSeconds()).padStart(2, "0");
    const line = document.createElement("div");
    line.className = `mn-eventlog-line k-${kind}`;
    line.innerHTML = `<span class="ts">${hh}:${mm}:${ss}</span>${msg}`;
    el.prepend(line);
    // Keep only 8 lines
    while (el.children.length > 8) el.removeChild(el.lastChild);
  }
  function clearLog(logId) {
    const el = document.getElementById(logId || "mn-eventlog");
    if (el) el.innerHTML = "";
  }

  // ─── vault ────────────────────────────────────────────────────
  // Renders a 6-slot hoard grid mirroring the game VAULT drawer
  // (app.js:2197). Each slot is painted with the origin tile's paint
  // (via paintTile) at harvest time, with a slot-number badge.
  //
  // Score animation: after each fill we ease-cubic from the current
  // total to (total + parcelScore) over 500ms so the running RED
  // score counts up as parcels land.
  const _vaultState = { currentScore: 0, currentTarget: 0, raf: null };
  function _showVaultSlotTooltip(slot, idx) {
    const num = String(idx + 1).padStart(2, "0");
    if (slot.classList.contains("mn-vault-slot--empty")) {
      ttShow(slot, `SLOT ${num}`,
        "Empty. A picked-up harvester banks one parcel per slot at Aurora.",
        "RULEBOOK §3.13");
      return;
    }
    const purity = Number(slot.dataset.purity || 0);
    const tier   = String(slot.dataset.tier || "");
    const mult   = Number(slot.dataset.mult || 0);
    const score  = Math.round(purity * mult);
    const glyph  = String(slot.dataset.glyph || "");
    ttShow(slot,
      `PARCEL ${num} · ${tier.toUpperCase()}`,
      `<b>purity ${purity}</b> × MULT ${mult.toFixed(2)} = <b>${score} pts</b><br>` +
      `<span class="dim">tier <b>${tier}</b> · glyph ${glyph} · RED harvest</span>`,
      "RULEBOOK §2.2 · §3.1");
  }
  function resetVault() {
    const grid = document.getElementById("mn-vault-grid");
    if (!grid) return;
    grid.innerHTML = "";
    for (let i = 0; i < 6; i++) {
      const slot = document.createElement("div");
      slot.className = "mn-vault-slot mn-vault-slot--empty";
      slot.setAttribute("data-slot", String(i + 1).padStart(2, "0"));
      slot.tabIndex = 0;
      const num = document.createElement("span");
      num.className = "mn-vault-slot-num";
      num.textContent = String(i + 1).padStart(2, "0");
      slot.appendChild(num);
      // Hover / focus tooltip — reveals purity, tier, multiplier, score.
      slot.addEventListener("mouseenter", () => _showVaultSlotTooltip(slot, i));
      slot.addEventListener("mouseleave", ttHide);
      slot.addEventListener("focus", () => _showVaultSlotTooltip(slot, i));
      slot.addEventListener("blur", ttHide);
      grid.appendChild(slot);
    }
    _vaultState.currentScore = 0;
    _vaultState.currentTarget = 0;
    const scoreEl = document.getElementById("mn-vault-score");
    if (scoreEl) scoreEl.innerHTML = "score · <b>0</b> pts";
    if (_vaultState.raf) cancelAnimationFrame(_vaultState.raf);
    _vaultState.raf = null;
  }
  function fillVaultSlot(slotIdx, tile, purity) {
    const grid = document.getElementById("mn-vault-grid");
    if (!grid) return;
    const slot = grid.children[slotIdx];
    if (!slot) return;
    slot.classList.remove("mn-vault-slot--empty");
    slot.classList.add("mn-vault-slot--full");
    // Strip any prior glyph and re-add
    const priorGlyph = slot.querySelector(".mn-vault-slot-glyph");
    if (priorGlyph) priorGlyph.remove();
    const paint = paintTile(tile, purity);
    const glyph = document.createElement("span");
    glyph.className = "mn-vault-slot-glyph";
    glyph.style.color = paint.fg;
    glyph.style.background = paint.bg;
    glyph.textContent = paint.ch;
    slot.appendChild(glyph);
    // Stamp parcel metadata onto the slot so the hover tooltip can
    // read tier / purity / multiplier without a lookup.
    if (tile === TILE.RED) {
      const t = tierOf(purity);
      const mult = RED_MULT[t];
      slot.dataset.purity = String(purity);
      slot.dataset.tier   = t;
      slot.dataset.mult   = String(mult);
      slot.dataset.glyph  = paint.ch;
      const parcelScore = Math.round(purity * mult);
      _animateScoreBy(parcelScore);
    }
  }
  function _animateScoreBy(delta) {
    const scoreEl = document.getElementById("mn-vault-score");
    if (!scoreEl) return;
    const from = _vaultState.currentScore;
    _vaultState.currentTarget += delta;
    const target = _vaultState.currentTarget;
    const start = performance.now();
    const dur = 500;
    if (_vaultState.raf) cancelAnimationFrame(_vaultState.raf);
    function step(now) {
      const t = Math.min(1, (now - start) / dur);
      const eased = 1 - Math.pow(1 - t, 3); // ease-out cubic
      const v = Math.round(from + (target - from) * eased);
      _vaultState.currentScore = v;
      scoreEl.innerHTML = `score · <b>${v}</b> pts`;
      if (t < 1) _vaultState.raf = requestAnimationFrame(step);
      else _vaultState.raf = null;
    }
    _vaultState.raf = requestAnimationFrame(step);
  }

  function tab3_start() {
    tab3_stop();
    const host = document.getElementById("mn-board-loop");
    const status = document.getElementById("mn-loop-status");
    const phase = document.getElementById("mn-loop-phase");
    const btnToggle = document.getElementById("mn-loop-toggle");
    const btnRestart = document.getElementById("mn-loop-step");
    const auroraWash = document.getElementById("mn-aurora-wash");

    // 20 × 12 board with a Manhattan-friendly staircase red seam and a
    // small blue pocket for world flavour (never harvested).
    const cols = 20, rows = 12;
    const total = cols * rows;
    const base = new Array(total).fill(null).map(() => ({ tile: TILE.EMPTY, purity: 0, fog: true }));

    // Red seam PLAN — coordinates + tier only. Purities are randomised
    // within their tier bounds each loop so the vault + score change
    // slightly between Nox iterations (rulebook §2.2 tier bands).
    // Every walked seam cell is Manhattan-1 from the previous.
    const seamPlan = [
      { x: 5, y: 3, tier: "trace" }, // drop
      { x: 6, y: 3, tier: "vein"  },
      { x: 7, y: 3, tier: "vein"  },
      { x: 7, y: 4, tier: "mass"  },
      { x: 8, y: 4, tier: "mass"  },
      { x: 8, y: 5, tier: "pure"  }, // core
      // Non-walked spurs — for seam width only.
      { x: 9, y: 5, tier: "mass"  },
      { x: 9, y: 6, tier: "vein"  },
      { x: 10, y: 6, tier: "trace" },
    ];
    /** Roll fresh random purities per tier and stamp them into `base`.
     * Called at the start of every runLoop so the seam looks slightly
     * different (and scores slightly differently) each Nox. */
    function rerollSeam() {
      seamPlan.forEach(({ x, y, tier }) => {
        base[y * cols + x] = {
          tile: TILE.RED,
          purity: tier === "pure" ? 255 : randPurity(tier),
          fog: true,
        };
      });
    }
    rerollSeam();

    // Blue pocket peek — world flavour, never harvested in this loop.
    const pocket = [
      { x: 2, y: 9,  p: 60  },
      { x: 3, y: 9,  p: 180 },
      { x: 3, y: 10, p: 255 },
      { x: 4, y: 10, p: 130 },
    ];
    pocket.forEach(({ x, y, p }) => (base[y * cols + x] = { tile: TILE.BLUE, purity: p, fog: true }));

    const cells = base.map((c) => ({ ...c }));
    const board = renderBoard(host, cells, { cols, rows, cellW: 22, cellH: 22 });

    const idxAt = (x, y) => y * cols + x;
    const inBounds = (x, y) => x >= 0 && y >= 0 && x < cols && y < rows;
    const eucDisk = (cx, cy, r) => {
      const out = [];
      const r2 = r * r;
      for (let y = cy - r; y <= cy + r; y++) {
        for (let x = cx - r; x <= cx + r; x++) {
          if (!inBounds(x, y)) continue;
          const dx = x - cx, dy = y - cy;
          if (dx * dx + dy * dy <= r2) out.push(idxAt(x, y));
        }
      }
      return out;
    };

    // Probe target — placed to the RIGHT of the seam (outside the
    // 6-cell walk) so the harvester never rolls over it and crushes
    // it (§3.11 probe crush rule). Radius-4 disk from (9, 3) still
    // covers every walked cell — verified: max Euclidean d² to the
    // walk is 16 at (5,3).
    const probeXY = { x: 9, y: 3 };
    const dropXY  = { x: 5, y: 3 };

    // 5 Manhattan-1 steps from the drop, all cardinal. Each entry is a
    // pair of (dx, dy) with |dx|+|dy| === 1.
    const stepDeltas = [
      { dx: 1, dy: 0, dir: "E" }, // (5,3) → (6,3)
      { dx: 1, dy: 0, dir: "E" }, // (6,3) → (7,3)
      { dx: 0, dy: 1, dir: "S" }, // (7,3) → (7,4)
      { dx: 1, dy: 0, dir: "E" }, // (7,4) → (8,4)
      { dx: 0, dy: 1, dir: "S" }, // (8,4) → (8,5)
    ];
    // Compute absolute path coords from the deltas.
    const stepPath = [];
    {
      let cx = dropXY.x, cy = dropXY.y;
      for (const s of stepDeltas) {
        cx += s.dx; cy += s.dy;
        stepPath.push({ x: cx, y: cy, dir: s.dir });
      }
    }

    const state = {
      stopped: false,
      paused: false,
      timers: [],
      fxNodes: new Set(),
      trailByIdx: {},
      parcels: [],  // filled during drop/walk, banked one-by-one after pickup
    };
    tab3_state = state;

    function timer(fn, ms) {
      const t = setTimeout(() => {
        if (state.stopped) return;
        if (state.paused) {
          state.timers.push(setTimeout(() => timer(fn, 0), 250));
        } else {
          fn();
        }
      }, ms);
      state.timers.push(t);
      return t;
    }

    function resetBoard() {
      for (let i = 0; i < total; i++) {
        const cellEl = boardCell(board, i);
        setFog(cellEl, true);
        cellEl.querySelector(".mn-cell-fog").classList.remove("is-revealing");
        setEntity(cellEl, "");
        const t = cellEl.querySelector(".mn-cell-trail");
        t.classList.remove("is-on");
        t.textContent = "";
        const b = base[i];
        setTerrain(cellEl, b.tile, b.purity);
      }
      state.trailByIdx = {};
      auroraWash.classList.remove("is-on");
    }

    function fireProbeRipple(cellEl, color) {
      const r = cellEl.getBoundingClientRect();
      const el = document.createElement("div");
      el.className = "mn-probe-ripple";
      el.style.left = `${(r.left + r.width * 0.5).toFixed(1)}px`;
      el.style.top  = `${(r.top  + r.height * 0.5).toFixed(1)}px`;
      const [rr, gg, bb] = color;
      el.style.setProperty("--rr", String(rr));
      el.style.setProperty("--rg", String(gg));
      el.style.setProperty("--rb", String(bb));
      document.body.appendChild(el);
      state.fxNodes.add(el);
      el.addEventListener("animationend", () => {
        el.remove();
        state.fxNodes.delete(el);
      }, { once: true });
    }

    /**
     * Fire the engine's "harvest effect" on `cell`: a 3-flash blink
     * overlay in `color` plus 8 particles flying outward on random
     * angles for `~2.6× cell width`. Direct port of app.js:7619-7658
     * spawnHarvestEffects.
     */
    function spawnHarvestFx(cell, color) {
      const rect = cell.getBoundingClientRect();
      const cx = rect.left + rect.width * 0.5;
      const cy = rect.top + rect.height * 0.5;

      const blink = document.createElement("div");
      blink.className = "mn-harvest-blink";
      blink.style.setProperty("--blink-color", color);
      cell.appendChild(blink);
      state.fxNodes.add(blink);
      blink.addEventListener("animationend", () => {
        blink.remove();
        state.fxNodes.delete(blink);
      }, { once: true });

      const N = 8;
      for (let i = 0; i < N; i++) {
        const angle = (i / N) * Math.PI * 2 + (Math.random() - 0.5) * 0.4;
        const dist = rect.width * (1.8 + Math.random() * 1.4);
        const p = document.createElement("div");
        p.className = "mn-harvest-particle";
        p.style.left = `${cx.toFixed(1)}px`;
        p.style.top  = `${cy.toFixed(1)}px`;
        const sz = Math.max(2, Math.round(rect.width * 0.22));
        p.style.width  = `${sz}px`;
        p.style.height = `${sz}px`;
        p.style.setProperty("--dx", `${(Math.cos(angle) * dist).toFixed(1)}px`);
        p.style.setProperty("--dy", `${(Math.sin(angle) * dist).toFixed(1)}px`);
        p.style.background = color;
        p.style.animationDelay = `${Math.round(Math.random() * 40)}ms`;
        document.body.appendChild(p);
        state.fxNodes.add(p);
        p.addEventListener("animationend", () => {
          p.remove();
          state.fxNodes.delete(p);
        }, { once: true });
      }
    }

    /**
     * Slide a harvester X ghost from `prevCell` to `nextCell` over
     * ~180ms with a stepped transition (matches engine .replay-anim-ghost--step
     * styles.css:6501). Hides both cells' entity overlays for the
     * duration; on arrival invokes `onArrive()` (caller commits terrain
     * / trail / entity / parcel push). If `blinkColor` is non-null,
     * fires spawnHarvestFx after arrival to flash + particle.
     */
    function animateStep(prevCell, nextCell, seatVar, blinkColor, onArrive) {
      const prevEntity = prevCell.querySelector(".mn-cell-entity");
      const nextEntity = nextCell.querySelector(".mn-cell-entity");
      prevEntity.textContent = "";
      const savedNextText = nextEntity.textContent;
      nextEntity.textContent = "";

      const pr = prevCell.getBoundingClientRect();
      const nr = nextCell.getBoundingClientRect();
      const ghost = document.createElement("span");
      ghost.className = "mn-step-ghost";
      ghost.textContent = GLYPH_HARVESTER;
      ghost.style.left = `${pr.left}px`;
      ghost.style.top  = `${pr.top}px`;
      ghost.style.width  = `${pr.width}px`;
      ghost.style.height = `${pr.height}px`;
      ghost.style.color  = `var(${seatVar})`;
      ghost.style.fontSize = `${Math.round(pr.width * 0.7)}px`;
      document.body.appendChild(ghost);
      state.fxNodes.add(ghost);

      const dx = nr.left - pr.left;
      const dy = nr.top  - pr.top;
      let done = false;
      const finish = () => {
        if (done || state.stopped) return;
        done = true;
        ghost.remove();
        state.fxNodes.delete(ghost);
        // Restore next entity (caller may overwrite via onArrive).
        if (savedNextText) nextEntity.textContent = savedNextText;
        onArrive();
        if (blinkColor) spawnHarvestFx(nextCell, blinkColor);
      };
      // Two rAFs so the browser paints the initial position before we
      // change the transform (mirrors engine app.js:7703).
      requestAnimationFrame(() => requestAnimationFrame(() => {
        ghost.style.transform = `translate(${dx.toFixed(1)}px, ${dy.toFixed(1)}px)`;
      }));
      ghost.addEventListener("transitionend", finish, { once: true });
      // Safety fallback: transitionend can misfire under aggressive
      // pause/resume — force finish after 260ms.
      state.timers.push(setTimeout(finish, 260));
    }

    // ── aurora heat-sweep ─────────────────────────────────────────
    // Faithful port of the engine's dawn heat sweep — app.js:9353-9540
    // (_runHeatSweep + _heatApplyCell). A diagonal front x*0.85 + y*1.15
    // advances across the board over 2.2s. Per-cell effect:
    //   • Non-fog cells: filter saturate/brightness on the terrain glyph,
    //     warm text-shadow bloom, and the cell BACKGROUND rgb lifts
    //     toward a warm dawn tint (cr+h*42, cg+h*32, cb+h*24).
    //   • Fog cells: fog glyph text swaps ░░ → ▒▒, color warms
    //     rgb(90+h*165, …), background lifts toward a warm dark.
    //   • Glyph shimmer: sine wobble via translate() while h > 0.15.
    // After the sweep completes it holds at 52% heat for a beat, then
    // cools back to 0 (styles restored). Probe cells get an additional
    // .cell--dawn-decay pulse — a warm shrink-scale on the probe glyph.
    const CELL_BG_RGB = [14, 11, 22];  // matches var(--tile-void)
    function _heatClearAllCells() {
      Array.from(board.children).forEach((c) => {
        c.style.background = "";
        const terr = c.querySelector(".mn-cell-terrain");
        if (terr) {
          terr.style.filter = "";
          terr.style.textShadow = "";
          terr.style.transform = "";
        }
        const fog = c.querySelector(".mn-cell-fog");
        if (fog) {
          fog.textContent = CH_LIGHT;   // restore ░░
          fog.style.color = "";
          fog.style.opacity = "";
        }
        c.classList.remove("mn-cell-dawn-decay");
      });
    }
    function playAuroraSweep(onDone) {
      const boardCells = Array.from(board.children);
      const cellData = boardCells.map((el, i) => ({
        el,
        terr: el.querySelector(".mn-cell-terrain"),
        fog:  el.querySelector(".mn-cell-fog"),
        cx: i % cols,
        cy: Math.floor(i / cols),
        d:  (i % cols) * 0.85 + Math.floor(i / cols) * 1.15,
      }));
      state.heatCells = cellData;   // captured for vespera cool-down
      let maxD = 0;
      for (const c of cellData) if (c.d > maxD) maxD = c.d;
      const MIN_D = -4;
      const MAX_D = maxD + 6;
      const durIn = 2200;
      const rate = (MAX_D - MIN_D) / durIn;
      const holdDur = 700;
      let front = MIN_D;
      let lastTs = null;
      let holdStart = 0;
      let phase = "in";
      let onDoneFired = false;

      const probeIdx = idxAt(probeXY.x, probeXY.y);
      let probeDecayFired = false;

      function heatLevel(d, front) {
        const dist = front - d;
        if (dist < -2) return 0;
        if (dist <  2) return Math.max(0, (dist + 2) / 4);
        if (dist <  6) return 1.0 - ((dist - 2) / 4) * 0.48;
        return 0.52;
      }
      function frame(ts) {
        if (state.stopped) return;
        if (lastTs === null) lastTs = ts;
        const dt = Math.min(ts - lastTs, 50);
        lastTs = ts;
        if (phase === "in") {
          front += rate * dt;
          for (const c of cellData) _applyHeat(c, heatLevel(c.d, front), ts, probeIdx, () => {
            if (!probeDecayFired) {
              probeDecayFired = true;
              const probeCell = boardCell(board, probeIdx);
              probeCell.classList.add("mn-cell-dawn-decay");
              state.timers.push(setTimeout(() => {
                probeCell.classList.remove("mn-cell-dawn-decay");
              }, 640));
            }
          }, front);
          if (front >= MAX_D) { phase = "hold"; holdStart = ts; }
        } else {
          // hold — keep the heat pinned at 0.52 indefinitely. Fires
          // onDone once after `holdDur`, then keeps the shimmer running
          // until vespera cools it back out (which cancels this rAF
          // externally via _cancelHeatRaf).
          for (const c of cellData) _applyHeat(c, 0.52, ts, probeIdx, () => {}, front);
          if (!onDoneFired && ts - holdStart >= holdDur) {
            onDoneFired = true;
            state.heatApplied = true;
            if (onDone) try { onDone(); } catch (_) {}
          }
        }
        state.heatRaf = requestAnimationFrame(frame);
      }
      state.heatRaf = requestAnimationFrame(frame);
    }

    /**
     * Vespera cool — the "out" half of the engine's heat sweep. From
     * the held 52% state, a diagonal front travels in the same direction
     * again and each cell cools back to 0 as it passes. Once cooled,
     * fog spans and cell backgrounds are fully restored. onDone fires
     * when the last cell settles.
     */
    function playVesperaSweep(onDone) {
      const cellData = state.heatCells || Array.from(board.children).map((el, i) => ({
        el,
        terr: el.querySelector(".mn-cell-terrain"),
        fog:  el.querySelector(".mn-cell-fog"),
        cx: i % cols,
        cy: Math.floor(i / cols),
        d:  (i % cols) * 0.85 + Math.floor(i / cols) * 1.15,
      }));
      let maxD = 0;
      for (const c of cellData) if (c.d > maxD) maxD = c.d;
      const MIN_D = -4;
      const MAX_D = maxD + 6;
      const durOut = 2000;
      const rate = (MAX_D - MIN_D) / durOut;
      let front = MIN_D;
      let lastTs = null;

      function coolLevel(d, front) {
        // Reverse of heatLevel: cells the front hasn't reached stay at
        // 0.52; the front knocks them down to 0 in a smooth band.
        const dist = front - d;
        if (dist < -2) return 0.52;
        if (dist <  2) return 0.52 * (1 - (dist + 2) / 4);
        return 0;
      }
      function frame(ts) {
        if (state.stopped) return;
        if (lastTs === null) lastTs = ts;
        const dt = Math.min(ts - lastTs, 50);
        lastTs = ts;
        front += rate * dt;
        for (const c of cellData) _applyHeat(c, coolLevel(c.d, front), ts, -1, () => {}, front);
        if (front < MAX_D) {
          state.heatRaf = requestAnimationFrame(frame);
        } else {
          _heatClearAllCells();
          state.heatApplied = false;
          state.heatCells = null;
          if (onDone) try { onDone(); } catch (_) {}
        }
      }
      state.heatRaf = requestAnimationFrame(frame);
    }

    /** Core per-cell heat application. Extracted so both sweep-in and
     *  sweep-out can share it. */
    function _applyHeat(c, h, wallT, probeIdx, onProbePassed, front) {
      const isFog = c.el.classList.contains("is-fogged");
      if (h < 0.015) {
        c.el.style.background = "";
        if (c.terr) {
          c.terr.style.filter = "";
          c.terr.style.textShadow = "";
          c.terr.style.transform = "";
        }
        if (c.fog) {
          c.fog.textContent = CH_LIGHT;
          c.fog.style.color = "";
        }
        return;
      }
      if (isFog && c.fog) {
        c.fog.textContent = "\u2592\u2592";
        const w = Math.round(90 + h * 165);
        c.fog.style.color = `rgb(${w},${w},${w})`;
        const br = Math.round(15 + h * 22);
        const bg = Math.round(12 + h * 14);
        const bb = Math.round(24 + h * 16);
        c.el.style.background = `rgba(${br},${bg},${bb},0.96)`;
        if (c.terr) c.terr.style.filter = "";
      } else if (c.terr) {
        const sat = (1 + h * 1.5).toFixed(2);
        const bri = (1 + h * 0.45).toFixed(2);
        c.terr.style.filter = `saturate(${sat}) brightness(${bri})`;
        const [cr, cg, cb] = CELL_BG_RGB;
        const lr = Math.min(255, Math.round(cr + h * 42));
        const lg = Math.min(255, Math.round(cg + h * 32));
        const lb = Math.min(255, Math.round(cb + h * 24));
        c.el.style.background = `rgb(${lr},${lg},${lb})`;
      }
      if (c.terr) {
        const glowA = Math.max(0, (h - 0.2) / 0.8);
        const blur  = Math.round(3 + glowA * 5);
        const a     = (glowA * 0.7).toFixed(2);
        c.terr.style.textShadow = `0 0 ${blur}px rgba(255,200,80,${a})`;
        if (wallT > 0 && h > 0.15) {
          const t   = wallT * 0.001;
          const amp = 1.8 * Math.min(1, h * 1.6);
          const dx = (Math.sin(c.cx * 0.55 + t * 4.3 + c.cy * 0.31) * amp).toFixed(1);
          const dy = (Math.cos(c.cy * 0.63 + t * 3.8 + c.cx * 0.44) * amp * 0.5).toFixed(1);
          c.terr.style.transform = `translate(${dx}px, ${dy}px)`;
        }
      }
      // Probe decay pulse: fires once when the front sweeps past.
      if (probeIdx >= 0 && c.el === boardCell(board, probeIdx)
          && front !== undefined && front - c.d > 0) {
        onProbePassed();
      }
    }

    // ── stage machine ─────────────────────────────────────────────
    const phaseEl  = document.getElementById("mn-loop-phase");
    const statusEl = status;
    const labelEl  = document.getElementById("mn-stage-label");
    const bodyEl   = document.getElementById("mn-stage-body");
    const citeEl   = document.getElementById("mn-stage-cite");
    const btnPrev  = document.getElementById("mn-stage-prev");
    const btnNext  = document.getElementById("mn-stage-next");

    // Helper: silently settle all state up to and including `settleStage(k)`
    // returns the harvester's final position (or null if not deployed).
    function _settleProbe() {
      const targetCell = boardCell(board, idxAt(probeXY.x, probeXY.y));
      setProbe(targetCell, 3, "--seat-p1");
      eucDisk(probeXY.x, probeXY.y, 4).forEach((i) => setFog(boardCell(board, i), false));
      state.probeLife = 3;
    }
    function _settleDrop() {
      _settleProbe();
      const idx = idxAt(dropXY.x, dropXY.y);
      const dropCell = boardCell(board, idx);
      const dropPurity = base[idx].purity;
      const dropTier = tierOf(dropPurity);
      setEntity(dropCell, GLYPH_HARVESTER, "--seat-p1");
      setTerrain(dropCell, TILE.GREEN, 255);
      bumpTrail(dropCell, state.trailByIdx, idx);
      state.parcels.push({ tile: TILE.RED, purity: dropPurity, tier: dropTier });
      return dropXY;
    }
    function _settleHarvest() {
      _settleDrop();
      let cur = { ...dropXY };
      stepPath.forEach((next) => {
        const prevCell = boardCell(board, idxAt(cur.x, cur.y));
        const nextCell = boardCell(board, idxAt(next.x, next.y));
        setEntity(prevCell, "");
        setEntity(nextCell, GLYPH_HARVESTER, "--seat-p1");
        const b = base[idxAt(next.x, next.y)];
        if (b.tile === TILE.RED) {
          setTerrain(nextCell, TILE.GREEN, 255);
          bumpTrail(nextCell, state.trailByIdx, idxAt(next.x, next.y));
          state.parcels.push({ tile: TILE.RED, purity: b.purity, tier: tierOf(b.purity) });
        }
        cur = { x: next.x, y: next.y };
      });
      return cur;
    }
    function _settleLift() {
      const last = _settleHarvest();
      setEntity(boardCell(board, idxAt(last.x, last.y)), "");
      state.parcels.forEach((p, i) => fillVaultSlot(i, p.tile, p.purity));
    }
    function _settleAurora() {
      _settleLift();
      const targetCell = boardCell(board, idxAt(probeXY.x, probeXY.y));
      setProbe(targetCell, 2, "--seat-p1");
      state.probeLife = 2;
    }

    const STAGES = [
      {
        label: "0 · NOX BEGINS",
        body: "The planet is only harvestable during the night. Aurora incinerates anything left on the surface.",
        cite: "§3.2 · Nox / Aurora cycle",
        settle: () => {},   // fully fogged (default state after reset)
        animate: () => {
          phaseEl.textContent = "# 21:00 — Nox begins";
          statusEl.textContent = "# stage 0 · press → to advance · press PLAY for auto";
          pushLog("fog", "Nox begins · the planet is only harvestable during the night · §3.2");
        },
        dur: 2800,
      },
      {
        label: "1 · FOG",
        body: "The magnetic cover hides everything. Orbital sensors read a blank rectangle.",
        cite: "§0.4 · magnetic cover",
        settle: () => {},
        animate: () => {
          statusEl.textContent = "# fog · orbital sensors are blind";
          pushLog("fog", "magnetic cover · you cannot see through it · §0.4");
        },
        dur: 2400,
      },
      {
        label: "2 · PROBE",
        body: "A ballistic · punches through the cover. Its landing point becomes a live Euclidean-radius-4 disk (~49 tiles).",
        cite: "§3.9 · §3.11 · §3.15",
        settle: () => { _settleProbe(); },
        animate: () => {
          const targetCell = boardCell(board, idxAt(probeXY.x, probeXY.y));
          pushLog("probe", `probe launched → (${probeXY.x},${probeXY.y}) · rivals see the coords · §3.15`);
          statusEl.textContent = "# probe · ballistic arc through the cover";
          spawnProbeTrail(
            targetCell,
            "#ffffff",
            "#FFFFFF",
            () => {
              if (state.stopped) return;
              setProbe(targetCell, 3, "--seat-p1");
              state.probeLife = 3;
              fireProbeRipple(targetCell, [255, 255, 255]);
              pushLog("cover", "probe punches through · sensor disk goes <b>live</b> · §3.11");
              statusEl.textContent = "# radius-4 disk live · seam revealed";
              const disk = eucDisk(probeXY.x, probeXY.y, 4);
              disk.sort((a, b) => {
                const ax = a % cols, ay = (a / cols) | 0;
                const bx = b % cols, by = (b / cols) | 0;
                return ((ax - probeXY.x) ** 2 + (ay - probeXY.y) ** 2)
                     - ((bx - probeXY.x) ** 2 + (by - probeXY.y) ** 2);
              });
              disk.forEach((i, k) => {
                state.timers.push(setTimeout(() => {
                  if (state.stopped) return;
                  setFog(boardCell(board, i), false);
                }, 60 + k * 25));
              });
            },
            900,
            state,
          );
        },
        dur: 3800,
      },
      {
        label: "3 · DROP",
        body: "An orblift bends the harvester X through the magnetic cover onto a live tile — rivals can't track it.",
        cite: "§0.4 · §3.9.7 · live_only drop mode",
        settle: () => { _settleDrop(); },
        animate: () => {
          // goStage() already ran STAGES[0..2].settle() for us, so the
          // probe is placed and the disk revealed. Don't re-settle here
          // — it would re-run pushes onto state.parcels.
          const dropCell = boardCell(board, idxAt(dropXY.x, dropXY.y));
          pushLog("drop", `orblift.deploy(harvester) → (${dropXY.x},${dropXY.y}) · §3.9.7`);
          statusEl.textContent = "# orblift descending · cargo detaches at midpoint";
          runOrbitalArcAnimation(
            board, dropCell, "drop", "--seat-p1", GLYPH_HARVESTER,
            () => {
              if (state.stopped) return;
              const idx = idxAt(dropXY.x, dropXY.y);
              const dp = base[idx].purity;
              const dt = tierOf(dp);
              setEntity(dropCell, GLYPH_HARVESTER, "--seat-p1");
              setTerrain(dropCell, TILE.GREEN, 255);
              bumpTrail(dropCell, state.trailByIdx, idx);
              spawnHarvestFx(dropCell, RED_FG);
              state.parcels.push({ tile: TILE.RED, purity: dp, tier: dt });
              pushLog("harvest", `harvester lands · <span class="fg-red">${dt}</span> (purity ${dp}) → <span class="fg-green">GREEN</span> · hold 1/6`);
              statusEl.textContent = `# drop harvested · trace (${dp}) → GREEN · hold 1/6`;
            },
            state,
          );
        },
        dur: 3600,
      },
      {
        label: "4 · HARVEST",
        body: "Harvester walks up to 5 tiles — cardinal only. Every coloured tile it enters is picked up (hold cap 6).",
        cite: "§3.9 · Manhattan-1 movement",
        settle: () => { _settleHarvest(); },
        animate: () => {
          // goStage() already ran STAGES[0..3].settle() → probe placed,
          // disk revealed, harvester on drop tile, parcel 1 in hold.
          // The DROP settle stopped after the drop tile — the walk still
          // needs to animate.
          statusEl.textContent = "# 5 Manhattan-1 steps · every RED converts to GREEN";
          let cur = { ...dropXY };
          stepPath.forEach((next, k) => {
            state.timers.push(setTimeout(() => {
              if (state.stopped) return;
              const prevIdx = idxAt(cur.x, cur.y);
              const nextIdx = idxAt(next.x, next.y);
              const prevCell = boardCell(board, prevIdx);
              const nextCell = boardCell(board, nextIdx);
              const b = base[nextIdx];
              const isHarvest = b.tile === TILE.RED;
              animateStep(prevCell, nextCell, "--seat-p1", isHarvest ? RED_FG : null, () => {
                if (state.stopped) return;
                setEntity(nextCell, GLYPH_HARVESTER, "--seat-p1");
                if (isHarvest) {
                  const purity = b.purity;
                  const tName = tierOf(purity);
                  setTerrain(nextCell, TILE.GREEN, 255);
                  bumpTrail(nextCell, state.trailByIdx, nextIdx);
                  state.parcels.push({ tile: TILE.RED, purity, tier: tName });
                  pushLog("harvest",
                    `step ${k + 1}/5 · ${next.dir} · ` +
                    `<span class="fg-red">${tName}</span> (purity ${purity}) → <span class="fg-green">GREEN</span> · hold ${k + 2}/6`);
                  statusEl.textContent = `# step ${k + 1}/5 · ${next.dir} · ${tName} (${purity}) · hold ${k + 2}/6`;
                }
              });
              cur = { x: next.x, y: next.y };
            }, 200 + k * 900));
          });
        },
        dur: 5400,
      },
      {
        label: "5 · LIFT",
        body: "Orblift returns for the loaded harvester. Only picked-up parcels bank to the vault (stranded loads are lost at Aurora).",
        cite: "§3.10 · §3.13 · §3.1",
        settle: () => { _settleLift(); },
        animate: () => {
          // goStage() already ran STAGES[0..4].settle() → harvester at
          // the final walked cell, 6 parcels in hold, ready to pickup.
          const last = stepPath[stepPath.length - 1];
          const lastCell = boardCell(board, idxAt(last.x, last.y));
          phaseEl.textContent = "# 04:30 — Aurora inbound";
          pushLog("lift", "orblift.pickup(harvester) · lifter sweeps back for the loaded unit");
          statusEl.textContent = "# orblift returning · cargo attaches at midpoint";
          runOrbitalArcAnimation(
            board, lastCell, "pickup", "--seat-p1", GLYPH_HARVESTER,
            () => {
              if (state.stopped) return;
              setEntity(lastCell, "");
              pushLog("lift", `harvester extracted · banking ${state.parcels.length} parcels to vault…`);
              state.parcels.forEach((p, i) => {
                state.timers.push(setTimeout(() => {
                  if (state.stopped) return;
                  fillVaultSlot(i, p.tile, p.purity);
                  const pts = Math.round(p.purity * RED_MULT[p.tier]);
                  pushLog("harvest",
                    `bank · slot ${String(i + 1).padStart(2, "0")} · ` +
                    `<span class="fg-red">${p.tier}</span> (purity ${p.purity}) · +${pts} pts`);
                  statusEl.textContent = `# banking ${i + 1}/${state.parcels.length} · +${pts} pts`;
                }, 300 + i * 500));
              });
            },
            state,
          );
        },
        dur: 5500,
      },
      {
        label: "6 · AURORA",
        body: "Sunrise incinerates the surface. Trails and terrain persist as scars. Probes survive but tick down one Nox of protection.",
        cite: "§3.10 · §3.9.1",
        settle: () => { _settleAurora(); },
        animate: () => {
          // goStage() already ran STAGES[0..5].settle() → harvester
          // extracted, all 6 parcels banked in vault, score at final total.
          phaseEl.textContent = "# 05:00 — Aurora";
          statusEl.textContent = "# Aurora heat sweep · surface incinerated";
          pushLog("aurora", "Aurora. Everything on the surface destroyed except probes · §3.10");
          playAuroraSweep(() => {
            if (state.stopped) return;
            const targetCell = boardCell(board, idxAt(probeXY.x, probeXY.y));
            setProbe(targetCell, 2, "--seat-p1");
            state.probeLife = 2;
            pushLog("probe", "probe ticks down · 2 Nox remaining · outer ring gone · §3.9.1");
            statusEl.textContent = "# Nox complete · probe lost a layer of protection";
          });
        },
        dur: 4500,
      },
    ];

    state.stageIdx = 0;
    state.autoPlay = false;
    state.probeLife = 0;
    state.heatApplied = false;
    state.heatCells = null;
    state.heatRaf = null;

    function updateCaption(idx) {
      const s = STAGES[idx];
      labelEl.textContent = s.label;
      bodyEl.textContent  = s.body;
      citeEl.textContent  = s.cite;
    }

    function _cancelHeatRaf() {
      if (state.heatRaf) { cancelAnimationFrame(state.heatRaf); state.heatRaf = null; }
    }

    function goStage(idx) {
      idx = ((idx % STAGES.length) + STAGES.length) % STAGES.length;
      // Cancel prior stage's animations
      state.timers.forEach((t) => clearTimeout(t));
      state.timers = [];
      state.fxNodes.forEach((n) => n.remove());
      state.fxNodes.clear();

      // Aurora → Nox transition: play the vespera cool-down first, then
      // continue into stage 0 setup. Matches the game's loop (dawn heat
      // holds, then vespera cools it out as the next Nox opens).
      if (idx === 0 && state.heatApplied) {
        _cancelHeatRaf();
        phaseEl.textContent = "# dusk — Vespera";
        statusEl.textContent = "# vespera · heat cools · fog closes back in";
        pushLog("aurora", "vespera · heat cools · fog closes back in over the surface");
        state.stageIdx = 0;
        updateCaption(0);
        labelEl.textContent = "vespera · cooling";
        bodyEl.textContent  = "Aurora heat sweeps back out. The surface cools; the magnetic cover re-closes; the next Nox opens.";
        citeEl.textContent  = "§3.2 · dusk / Vespera";
        playVesperaSweep(() => {
          if (state.stopped) return;
          // Cool completed — normal stage-0 setup + animate.
          resetBoard();
          resetVault();
          state.parcels = [];
          state.probeLife = 0;
          updateCaption(0);
          STAGES[0].animate();
          if (state.autoPlay) {
            state.timers.push(setTimeout(() => {
              if (state.stopped) return;
              goStage(1);
            }, STAGES[0].dur));
          }
        });
        return;
      }

      // Normal path: clear any lingering heat + reset board + settle
      // through preceding stages.
      _cancelHeatRaf();
      _heatClearAllCells();
      state.heatApplied = false;
      state.heatCells = null;
      resetBoard();
      resetVault();
      state.parcels = [];
      state.probeLife = 0;
      for (let i = 0; i < idx; i++) STAGES[i].settle();
      state.stageIdx = idx;
      updateCaption(idx);
      STAGES[idx].animate();
      if (state.autoPlay) {
        state.timers.push(setTimeout(() => {
          if (state.stopped) return;
          const next = idx + 1;
          if (next >= STAGES.length) {
            rerollSeam();   // start fresh loop with new purities
            goStage(0);
          } else {
            goStage(next);
          }
        }, STAGES[idx].dur));
      }
    }

    // Expose for outer arrow-key handler
    state.goStage = goStage;

    // Button wiring
    btnPrev.onclick = () => goStage(state.stageIdx - 1);
    btnNext.onclick = () => goStage(state.stageIdx + 1);
    btnToggle.textContent = "[ ⏵ PLAY ]";
    btnToggle.onclick = () => {
      state.autoPlay = !state.autoPlay;
      btnToggle.textContent = state.autoPlay ? "[ ⏸ PAUSE ]" : "[ ⏵ PLAY ]";
      if (state.autoPlay) goStage(state.stageIdx); // resume from here
    };
    btnRestart.onclick = () => {
      rerollSeam();
      state.autoPlay = false;
      btnToggle.textContent = "[ ⏵ PLAY ]";
      goStage(0);
    };

    goStage(0);
  }

  // ─── nav stubs ────────────────────────────────────────────────
  document.querySelectorAll(".mn-nav-list li.is-stub a").forEach((a) => {
    a.addEventListener("click", (e) => {
      e.preventDefault();
      const hint = document.getElementById("mn-hint");
      const original = hint.textContent;
      hint.textContent = "# that section is a stub — Basics is the only wired one in v0.1";
      setTimeout(() => (hint.textContent = original), 2200);
    });
  });

  // ─── keyboard help overlay ────────────────────────────────────
  window.addEventListener("keydown", (e) => {
    if (e.key === "?" || (e.key === "/" && e.shiftKey)) {
      const hint = document.getElementById("mn-hint");
      hint.textContent = "# keys: ← / → tabs · hover glyphs for tier details · ⏸ / ▶ / ⏭ on tab 3";
      setTimeout(() => (hint.textContent = "# ← / → switch tabs · hover glyphs for details · ? for keys"), 3500);
    }
  });

  // ═══════════════════════════════════════════════════════════════
  // TAB 4 — POLICY & PRAXIS
  //
  // Illustrates the 21-hour Nox and the ordered-slot policy queue.
  // Two nights across 7 stages:
  //   Night 1: 3 probes seeded at H1, H8, H15 (showing slot flexibility)
  //   Night 2: full 3-harvester operation, 15 RED banked over 18 slots
  //            + 3 idle WAITs
  //
  // Board is the same 20×12 as tab 3, but three separate seams are
  // stamped (A near (5-8, 3-5), B near (12-14, 5-7), C near (3-5, 8-10))
  // so each of the three probes covers exactly one seam.
  //
  // The vault is replaced by a 21-row policy roster; each row lights
  // up as its hour executes (yellow = running, green = done).
  //
  // Animation primitives are copied from tab 3's local versions
  // (spawnProbeTrail + runOrbitalArcAnimation are already at IIFE
  // scope; animateStep + spawnHarvestFx + aurora sweep are inlined
  // here to keep tab 3 untouched. Known duplication — see
  // ANIMATION_LOOPS.md § "Section coverage roadmap".)
  // ═══════════════════════════════════════════════════════════════
  let tab4_state = null;
  function tab4_stop() {
    if (tab4_state) {
      tab4_state.stopped = true;
      tab4_state.timers.forEach((t) => clearTimeout(t));
      tab4_state.timers = [];
      if (tab4_state.heatRaf) cancelAnimationFrame(tab4_state.heatRaf);
      tab4_state.heatRaf = null;
      tab4_state.fxNodes.forEach((n) => n.remove());
      tab4_state.fxNodes.clear();
      tab4_state = null;
    }
  }

  function tab4_start() {
    tab4_stop();
    const host      = document.getElementById("mn-board-orders");
    const status    = document.getElementById("mn-orders-status");
    const phase     = document.getElementById("mn-orders-phase");
    const btnPrev   = document.getElementById("mn-stage-prev-2");
    const btnNext   = document.getElementById("mn-stage-next-2");
    const btnToggle = document.getElementById("mn-orders-toggle");
    const btnRestart= document.getElementById("mn-orders-restart");
    const labelEl   = document.getElementById("mn-stage-label-2");
    const bodyEl    = document.getElementById("mn-stage-body-2");
    const citeEl    = document.getElementById("mn-stage-cite-2");
    const rosterListEl = document.getElementById("mn-roster-list");
    const rosterNoxEl  = document.getElementById("mn-roster-nox");
    const rosterFootEl = document.getElementById("mn-roster-foot");
    const coordTopEl   = document.getElementById("mn-coord-top");
    const coordLeftEl  = document.getElementById("mn-coord-left");

    // ── world geometry ────────────────────────────────────────────
    const cols = 20, rows = 12;
    const cellW = 22, cellH = 22;
    const total = cols * rows;

    // Three RED seams, one per harvester chain. Each seam has SIX red
    // tiles (drop + 5 walked cells), so a full drop + 5 steps + pickup
    // = 7 slots per harvester, × 3 harvesters = 21 slots exactly. Six
    // harvests per harvester × 3 = 18 red parcels banked on Night 2.
    // Every walked cell is Manhattan-1 from the previous.
    const seamA = [
      { x: 5,  y: 3, tier: "trace" }, // drop
      { x: 6,  y: 3, tier: "vein"  }, // E
      { x: 7,  y: 3, tier: "vein"  }, // E
      { x: 7,  y: 4, tier: "mass"  }, // S
      { x: 8,  y: 4, tier: "mass"  }, // E
      { x: 8,  y: 5, tier: "pure"  }, // S · core
    ];
    const seamB = [
      { x: 12, y: 4, tier: "trace" }, // drop
      { x: 12, y: 5, tier: "vein"  }, // S
      { x: 13, y: 5, tier: "vein"  }, // E
      { x: 13, y: 6, tier: "mass"  }, // S
      { x: 13, y: 7, tier: "mass"  }, // S
      { x: 14, y: 7, tier: "pure"  }, // E · core
    ];
    const seamC = [
      { x: 3,  y: 8,  tier: "trace" }, // drop
      { x: 4,  y: 8,  tier: "vein"  }, // E
      { x: 4,  y: 9,  tier: "vein"  }, // S
      { x: 5,  y: 9,  tier: "mass"  }, // E
      { x: 5,  y: 10, tier: "mass"  }, // S
      { x: 6,  y: 10, tier: "pure"  }, // E · core
    ];
    const seams = [seamA, seamB, seamC];

    // Blue pocket for flavour (never harvested).
    const pocket = [
      { x: 17, y: 9,  p: 60  },
      { x: 17, y: 10, p: 180 },
      { x: 18, y: 10, p: 255 },
    ];

    const base = new Array(total).fill(null).map(() => ({ tile: TILE.EMPTY, purity: 0, fog: true }));
    function stampSeams() {
      for (const seam of seams) {
        for (const { x, y, tier } of seam) {
          base[y * cols + x] = {
            tile: TILE.RED,
            purity: tier === "pure" ? 255 : randPurity(tier),
            fog: true,
          };
        }
      }
      pocket.forEach(({ x, y, p }) => (base[y * cols + x] = { tile: TILE.BLUE, purity: p, fog: true }));
    }
    stampSeams();

    // Board + coord axes.
    const cells = base.map((c) => ({ ...c }));
    const board = renderBoard(host, cells, { cols, rows, cellW, cellH });
    coordTopEl.innerHTML = "";
    for (let x = 0; x < cols; x++) {
      const s = document.createElement("span");
      s.className = "mn-coord-label";
      s.style.width  = cellW + "px";
      s.style.height = "12px";
      s.textContent  = String(x);
      s.dataset.x    = String(x);
      coordTopEl.appendChild(s);
    }
    coordLeftEl.innerHTML = "";
    for (let y = 0; y < rows; y++) {
      const s = document.createElement("span");
      s.className = "mn-coord-label";
      s.style.width  = "14px";
      s.style.height = cellH + "px";
      s.textContent  = String(y);
      s.dataset.y    = String(y);
      coordLeftEl.appendChild(s);
    }

    // Attach a coordinate tooltip to every cell on the map. On hover we
    // show (x, y) plus what kind of tile it is (RED tier / BLUE / EMPTY
    // / probe / drop point) so the user can inspect the plan target.
    Array.from(board.children).forEach((cellEl, i) => {
      const x = i % cols, y = Math.floor(i / cols);
      cellEl.tabIndex = 0;
      const showCoordTip = () => {
        const b = base[i];
        // Highlight the matching row/col labels while hovered.
        const topLbl = coordTopEl.children[x];
        const leftLbl = coordLeftEl.children[y];
        if (topLbl) topLbl.classList.add("is-highlight");
        if (leftLbl) leftLbl.classList.add("is-highlight");
        let kind = "empty";
        if (b.tile === TILE.RED)   kind = `RED · ${tierOf(b.purity)} (purity ${b.purity})`;
        if (b.tile === TILE.BLUE)  kind = `BLUE · pocket (purity ${b.purity})`;
        // Note if this coord is a probe/drop landmark.
        const marks = [];
        if (PROBE_A[0] === x && PROBE_A[1] === y) marks.push("probe A landing");
        if (PROBE_B[0] === x && PROBE_B[1] === y) marks.push("probe B landing");
        if (PROBE_C[0] === x && PROBE_C[1] === y) marks.push("probe C landing");
        for (const H of harvesterPlan) {
          if (H.drop[0] === x && H.drop[1] === y) marks.push(`${labelUnit(H.unit)} drop`);
        }
        ttShow(cellEl,
          `(${x}, ${y})`,
          `<b>${kind}</b>` + (marks.length ? `<br><span class="dim">${marks.join(" · ")}</span>` : ""),
          "RULEBOOK §3.11");
      };
      const hideCoordTip = () => {
        ttHide();
        const topLbl = coordTopEl.children[x];
        const leftLbl = coordLeftEl.children[y];
        if (topLbl) topLbl.classList.remove("is-highlight");
        if (leftLbl) leftLbl.classList.remove("is-highlight");
      };
      cellEl.addEventListener("mouseenter", showCoordTip);
      cellEl.addEventListener("mouseleave", hideCoordTip);
      cellEl.addEventListener("focus", showCoordTip);
      cellEl.addEventListener("blur", hideCoordTip);
    });

    // ── loop state ────────────────────────────────────────────────
    const state = {
      stopped: false,
      timers: [],
      fxNodes: new Set(),
      stageIdx: 0,
      autoPlay: false,
      heatApplied: false,
      heatCells: null,
      heatRaf: null,
      // per-loop bookkeeping
      trailByIdx: {},
      probeCells: [],    // cell indices of live probes (survive across nights)
      probeNights: 0,    // rings remaining on all live probes (3, then 2, then 1)
      night: 1,
      score: 0,
    };
    tab4_state = state;

    // ── unit + slot plans ─────────────────────────────────────────
    // Probes off the harvester walk paths so they never get crushed
    // (§3.11 probe crush rule). Each probe's radius-4 disk covers its
    // seam's 6 tiles — see per-seam verification comments.
    const PROBE_A = [6, 4];    // covers seamA (5,3)-(8,5); not on walk
    const PROBE_B = [14, 5];   // covers seamB (12,4)-(14,7); not on walk
    const PROBE_C = [4, 10];   // covers seamC (3,8)-(6,10); not on walk

    // Three probes at H1, H8, H15 — deliberately spread to show that
    // slot placement is free (front, mid, back — all legal).
    const probePlan = [
      { hour: 1,  verb: "probe", target: PROBE_A, seamIdx: 0 },
      { hour: 8,  verb: "probe", target: PROBE_B, seamIdx: 1 },
      { hour: 15, verb: "probe", target: PROBE_C, seamIdx: 2 },
    ];

    // Night 2 policy — 3 harvesters, 6 harvests each = 18 red parcels
    // over 21 slots (drop + 5 steps + pickup per harvester × 3 = 21).
    // Slots run edge-to-edge — no WAITs, we are at the 21-hour cap.
    // Every harvester uses the same seat color (--seat-p1) so the
    // demo doesn't imply cross-house rivalry.
    const harvesterPlan = [
      // A on seamA: drop (5,3), walk E,E,S,E,S → ends at (8,5)
      { unit: "A", drop: [5, 3],  steps: ["E","E","S","E","S"], seamIdx: 0, seat: "--seat-p1" },
      // B on seamB: drop (12,4), walk S,E,S,S,E → ends at (14,7)
      { unit: "B", drop: [12, 4], steps: ["S","E","S","S","E"], seamIdx: 1, seat: "--seat-p1" },
      // C on seamC: drop (3,8), walk E,S,E,S,E → ends at (6,10)
      { unit: "C", drop: [3, 8],  steps: ["E","S","E","S","E"], seamIdx: 2, seat: "--seat-p1" },
    ];

    // Build the 21-slot roster for a given night (returns Array<Slot|null>).
    function buildRosterSingleProbe(hour, target, seamIdx) {
      const slots = new Array(21).fill(null).map(() => ({ verb: "wait" }));
      slots[hour - 1] = {
        verb: "probe",
        target: `(${target[0]},${target[1]})`,
        unit: null,
        data: { verb: "probe", target, seamIdx, hour },
      };
      return slots;
    }
    function buildRosterAllProbes() {
      const slots = new Array(21).fill(null).map(() => ({ verb: "wait" }));
      for (const p of probePlan) {
        slots[p.hour - 1] = {
          verb: "probe",
          target: `(${p.target[0]},${p.target[1]})`,
          unit: null,
          data: p,
        };
      }
      return slots;
    }
    /** Place ONE harvester chain (drop + steps + pickup) starting at
     *  slot `hStart` (0-indexed). Used by the "configurations" demo. */
    function buildRosterSingleHarvester(hStart, H) {
      const slots = new Array(21).fill(null).map(() => ({ verb: "wait" }));
      let h = hStart;
      slots[h++] = {
        verb: "drop", target: `${labelUnit(H.unit)} → (${H.drop[0]},${H.drop[1]})`,
        unit: H.unit, data: { kind: "drop", harvester: H },
      };
      let cx = H.drop[0], cy = H.drop[1];
      for (const s of H.steps) {
        const d = DIR[s]; cx += d.dx; cy += d.dy;
        slots[h++] = {
          verb: "step", target: `${labelUnit(H.unit)} ${s} → (${cx},${cy})`,
          unit: H.unit, data: { kind: "step", harvester: H, dir: s, to: [cx, cy] },
        };
      }
      slots[h++] = {
        verb: "pickup", target: `${labelUnit(H.unit)} out`,
        unit: H.unit, data: { kind: "pickup", harvester: H, at: [cx, cy] },
      };
      return slots;
    }
    /** Same harvester spread across the 21 hours (non-contiguous). Used
     *  to visualise the "spread" configuration. Hours passed as 7-tuple. */
    function buildRosterSpreadHarvester(hours, H) {
      const slots = new Array(21).fill(null).map(() => ({ verb: "wait" }));
      slots[hours[0] - 1] = {
        verb: "drop", target: `${labelUnit(H.unit)} → (${H.drop[0]},${H.drop[1]})`,
        unit: H.unit, data: { kind: "drop", harvester: H },
      };
      let cx = H.drop[0], cy = H.drop[1];
      for (let i = 0; i < H.steps.length; i++) {
        const s = H.steps[i], d = DIR[s]; cx += d.dx; cy += d.dy;
        slots[hours[i + 1] - 1] = {
          verb: "step", target: `${labelUnit(H.unit)} ${s} → (${cx},${cy})`,
          unit: H.unit, data: { kind: "step", harvester: H, dir: s, to: [cx, cy] },
        };
      }
      slots[hours[6] - 1] = {
        verb: "pickup", target: `${labelUnit(H.unit)} out`,
        unit: H.unit, data: { kind: "pickup", harvester: H, at: [cx, cy] },
      };
      return slots;
    }
    function buildRosterAllHarvesters() {
      // 3 harvesters × (1 drop + 5 steps + 1 pickup) = 21 slots, no WAITs.
      const slots = new Array(21).fill(null).map(() => ({ verb: "wait" }));
      let h = 0;
      for (const H of harvesterPlan) {
        slots[h++] = {
          verb: "drop",
          target: `${labelUnit(H.unit)} → (${H.drop[0]},${H.drop[1]})`,
          unit: H.unit,
          data: { kind: "drop", harvester: H },
        };
        let cx = H.drop[0], cy = H.drop[1];
        for (const s of H.steps) {
          const d = DIR[s];
          cx += d.dx; cy += d.dy;
          slots[h++] = {
            verb: "step",
            target: `${labelUnit(H.unit)} ${s} → (${cx},${cy})`,
            unit: H.unit,
            data: { kind: "step", harvester: H, dir: s, to: [cx, cy] },
          };
        }
        slots[h++] = {
          verb: "pickup",
          target: `${labelUnit(H.unit)} out`,
          unit: H.unit,
          data: { kind: "pickup", harvester: H, at: [cx, cy] },
        };
      }
      // h === 21 here — the full 21-hour cap is used.
      return slots;
    }
    function labelUnit(u) { return "H_" + u; }
    const DIR = {
      "N": { dx: 0, dy: -1 },
      "S": { dx: 0, dy: 1 },
      "E": { dx: 1, dy: 0 },
      "W": { dx: -1, dy: 0 },
    };

    // ── roster rendering ──────────────────────────────────────────
    // Builds 21 rows. Each row = hour badge, verb, target coord.
    // Colours: empty (wait) is dim; queued is normal; running is yellow
    // border; done is green tint. Verbs are colour-hinted by data-verb.
    function renderRoster(slots, notation) {
      rosterListEl.innerHTML = "";
      rosterNoxEl.textContent = notation;
      for (let i = 0; i < 21; i++) {
        const slot = slots[i] || { verb: "wait" };
        const row = document.createElement("div");
        row.className = "mn-roster-slot";
        row.dataset.hour = String(i + 1);
        row.dataset.verb = slot.verb;
        if (slot.verb === "wait") row.classList.add("is-empty");
        else row.classList.add("is-queued");
        const hourStr = "H" + String(i + 1).padStart(2, "0");
        const verb = slot.verb.toUpperCase();
        const target = slot.target ? slot.target : (slot.verb === "wait" ? "—" : "");
        row.innerHTML =
          `<span class="mn-roster-hour">${hourStr}</span>` +
          `<span class="mn-roster-verb is-neutral">${verb}</span>` +
          `<span class="mn-roster-target">${target}</span>`;
        rosterListEl.appendChild(row);
      }
    }
    function slotEl(h) { return rosterListEl.children[h - 1]; }
    function markSlot(h, mode) {
      const row = slotEl(h);
      if (!row) return;
      row.classList.remove("is-running", "is-done");
      if (mode === "running") row.classList.add("is-running");
      else if (mode === "done") row.classList.add("is-done");
      // scroll into view (roster panel scrolls internally)
      row.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }

    // ── cell utils ────────────────────────────────────────────────
    const idxAt = (x, y) => y * cols + x;
    const inBounds = (x, y) => x >= 0 && y >= 0 && x < cols && y < rows;
    const eucDisk = (cx, cy, r) => {
      const out = [];
      const r2 = r * r;
      for (let y = cy - r; y <= cy + r; y++) {
        for (let x = cx - r; x <= cx + r; x++) {
          if (!inBounds(x, y)) continue;
          const dx = x - cx, dy = y - cy;
          if (dx * dx + dy * dy <= r2) out.push(idxAt(x, y));
        }
      }
      return out;
    };
    function resetBoard() {
      for (let i = 0; i < total; i++) {
        const cellEl = boardCell(board, i);
        setFog(cellEl, true);
        cellEl.querySelector(".mn-cell-fog").classList.remove("is-revealing");
        setEntity(cellEl, "");
        const t = cellEl.querySelector(".mn-cell-trail");
        t.classList.remove("is-on");
        t.textContent = "";
        const b = base[i];
        setTerrain(cellEl, b.tile, b.purity);
      }
      state.trailByIdx = {};
    }
    function timer(fn, ms) {
      const t = setTimeout(() => {
        if (state.stopped) return;
        fn();
      }, ms);
      state.timers.push(t);
      return t;
    }

    // ── inlined animation primitives ──────────────────────────────
    // (See ANIMATION_LOOPS.md — these are duplicates of tab 3's local
    // versions, retained here to avoid a risky refactor of tab 3.)

    function spawnHarvestFxLocal(cell, color) {
      const rect = cell.getBoundingClientRect();
      const cx = rect.left + rect.width * 0.5;
      const cy = rect.top + rect.height * 0.5;
      const blink = document.createElement("div");
      blink.className = "mn-harvest-blink";
      blink.style.setProperty("--blink-color", color);
      cell.appendChild(blink);
      state.fxNodes.add(blink);
      blink.addEventListener("animationend", () => { blink.remove(); state.fxNodes.delete(blink); }, { once: true });
      const N = 8;
      for (let i = 0; i < N; i++) {
        const angle = (i / N) * Math.PI * 2 + (Math.random() - 0.5) * 0.4;
        const dist = rect.width * (1.8 + Math.random() * 1.4);
        const p = document.createElement("div");
        p.className = "mn-harvest-particle";
        p.style.left = `${cx.toFixed(1)}px`;
        p.style.top  = `${cy.toFixed(1)}px`;
        const sz = Math.max(2, Math.round(rect.width * 0.22));
        p.style.width  = `${sz}px`;
        p.style.height = `${sz}px`;
        p.style.setProperty("--dx", `${(Math.cos(angle) * dist).toFixed(1)}px`);
        p.style.setProperty("--dy", `${(Math.sin(angle) * dist).toFixed(1)}px`);
        p.style.background = color;
        p.style.animationDelay = `${Math.round(Math.random() * 40)}ms`;
        document.body.appendChild(p);
        state.fxNodes.add(p);
        p.addEventListener("animationend", () => { p.remove(); state.fxNodes.delete(p); }, { once: true });
      }
    }
    function animateStepLocal(prevCell, nextCell, seatVar, blinkColor, onArrive) {
      const prevEntity = prevCell.querySelector(".mn-cell-entity");
      const nextEntity = nextCell.querySelector(".mn-cell-entity");
      prevEntity.textContent = "";
      const savedNextText = nextEntity.textContent;
      nextEntity.textContent = "";
      const pr = prevCell.getBoundingClientRect();
      const nr = nextCell.getBoundingClientRect();
      const ghost = document.createElement("span");
      ghost.className = "mn-step-ghost";
      ghost.textContent = GLYPH_HARVESTER;
      ghost.style.left = `${pr.left}px`;
      ghost.style.top  = `${pr.top}px`;
      ghost.style.width  = `${pr.width}px`;
      ghost.style.height = `${pr.height}px`;
      ghost.style.color  = `var(${seatVar})`;
      ghost.style.fontSize = `${Math.round(pr.width * 0.7)}px`;
      document.body.appendChild(ghost);
      state.fxNodes.add(ghost);
      const dx = nr.left - pr.left;
      const dy = nr.top  - pr.top;
      let done = false;
      const finish = () => {
        if (done || state.stopped) return;
        done = true;
        ghost.remove();
        state.fxNodes.delete(ghost);
        if (savedNextText) nextEntity.textContent = savedNextText;
        onArrive();
        if (blinkColor) spawnHarvestFxLocal(nextCell, blinkColor);
      };
      requestAnimationFrame(() => requestAnimationFrame(() => {
        ghost.style.transform = `translate(${dx.toFixed(1)}px, ${dy.toFixed(1)}px)`;
      }));
      ghost.addEventListener("transitionend", finish, { once: true });
      state.timers.push(setTimeout(finish, 260));
    }

    // Aurora heat sweep — same math as tab 3, but adapted for multiple
    // probe cells (tab 4 has 3 probes; each gets the decay pulse).
    const CELL_BG_RGB = [14, 11, 22];
    function _heatClearAllCells() {
      Array.from(board.children).forEach((c) => {
        c.style.background = "";
        const terr = c.querySelector(".mn-cell-terrain");
        if (terr) { terr.style.filter = ""; terr.style.textShadow = ""; terr.style.transform = ""; }
        const fog = c.querySelector(".mn-cell-fog");
        if (fog) { fog.textContent = CH_LIGHT; fog.style.color = ""; fog.style.opacity = ""; }
        c.classList.remove("mn-cell-dawn-decay");
      });
    }
    function _applyHeat(c, h, wallT, probeIdxSet, onProbePassed, front) {
      const isFog = c.el.classList.contains("is-fogged");
      if (h < 0.015) {
        c.el.style.background = "";
        if (c.terr) { c.terr.style.filter = ""; c.terr.style.textShadow = ""; c.terr.style.transform = ""; }
        if (c.fog)  { c.fog.textContent = CH_LIGHT; c.fog.style.color = ""; }
        return;
      }
      if (isFog && c.fog) {
        c.fog.textContent = "\u2592\u2592";
        const w = Math.round(90 + h * 165);
        c.fog.style.color = `rgb(${w},${w},${w})`;
        const br = Math.round(15 + h * 22);
        const bg = Math.round(12 + h * 14);
        const bb = Math.round(24 + h * 16);
        c.el.style.background = `rgba(${br},${bg},${bb},0.96)`;
        if (c.terr) c.terr.style.filter = "";
      } else if (c.terr) {
        const sat = (1 + h * 1.5).toFixed(2);
        const bri = (1 + h * 0.45).toFixed(2);
        c.terr.style.filter = `saturate(${sat}) brightness(${bri})`;
        const [cr, cg, cb] = CELL_BG_RGB;
        const lr = Math.min(255, Math.round(cr + h * 42));
        const lg = Math.min(255, Math.round(cg + h * 32));
        const lb = Math.min(255, Math.round(cb + h * 24));
        c.el.style.background = `rgb(${lr},${lg},${lb})`;
      }
      if (c.terr) {
        const glowA = Math.max(0, (h - 0.2) / 0.8);
        const blur  = Math.round(3 + glowA * 5);
        const a     = (glowA * 0.7).toFixed(2);
        c.terr.style.textShadow = `0 0 ${blur}px rgba(255,200,80,${a})`;
        if (wallT > 0 && h > 0.15) {
          const t   = wallT * 0.001;
          const amp = 1.8 * Math.min(1, h * 1.6);
          const dx = (Math.sin(c.cx * 0.55 + t * 4.3 + c.cy * 0.31) * amp).toFixed(1);
          const dy = (Math.cos(c.cy * 0.63 + t * 3.8 + c.cx * 0.44) * amp * 0.5).toFixed(1);
          c.terr.style.transform = `translate(${dx}px, ${dy}px)`;
        }
      }
      if (probeIdxSet && probeIdxSet.has(c.idx) && front !== undefined && front - c.d > 0) {
        onProbePassed(c.idx);
      }
    }
    function playAuroraSweepLocal(probeIdxs, onDone) {
      const boardCells = Array.from(board.children);
      const cellData = boardCells.map((el, i) => ({
        el, idx: i,
        terr: el.querySelector(".mn-cell-terrain"),
        fog:  el.querySelector(".mn-cell-fog"),
        cx: i % cols,
        cy: Math.floor(i / cols),
        d:  (i % cols) * 0.85 + Math.floor(i / cols) * 1.15,
      }));
      state.heatCells = cellData;
      let maxD = 0;
      for (const c of cellData) if (c.d > maxD) maxD = c.d;
      const MIN_D = -4, MAX_D = maxD + 6;
      const durIn = 2200, rate = (MAX_D - MIN_D) / durIn, holdDur = 700;
      let front = MIN_D, lastTs = null, holdStart = 0, phase = "in", onDoneFired = false;
      const probeSet = new Set(probeIdxs || []);
      const probeFired = new Set();
      function heatLevel(d, front) {
        const dist = front - d;
        if (dist < -2) return 0;
        if (dist <  2) return Math.max(0, (dist + 2) / 4);
        if (dist <  6) return 1.0 - ((dist - 2) / 4) * 0.48;
        return 0.52;
      }
      function onProbePassed(idx) {
        if (probeFired.has(idx)) return;
        probeFired.add(idx);
        const probeCell = boardCell(board, idx);
        probeCell.classList.add("mn-cell-dawn-decay");
        state.timers.push(setTimeout(() => probeCell.classList.remove("mn-cell-dawn-decay"), 640));
      }
      function frame(ts) {
        if (state.stopped) return;
        if (lastTs === null) lastTs = ts;
        const dt = Math.min(ts - lastTs, 50); lastTs = ts;
        if (phase === "in") {
          front += rate * dt;
          for (const c of cellData) _applyHeat(c, heatLevel(c.d, front), ts, probeSet, onProbePassed, front);
          if (front >= MAX_D) { phase = "hold"; holdStart = ts; }
        } else {
          for (const c of cellData) _applyHeat(c, 0.52, ts, probeSet, () => {}, front);
          if (!onDoneFired && ts - holdStart >= holdDur) {
            onDoneFired = true;
            state.heatApplied = true;
            if (onDone) try { onDone(); } catch (_) {}
          }
        }
        state.heatRaf = requestAnimationFrame(frame);
      }
      state.heatRaf = requestAnimationFrame(frame);
    }
    function playVesperaSweepLocal(onDone) {
      const cellData = state.heatCells || Array.from(board.children).map((el, i) => ({
        el, idx: i,
        terr: el.querySelector(".mn-cell-terrain"),
        fog:  el.querySelector(".mn-cell-fog"),
        cx: i % cols,
        cy: Math.floor(i / cols),
        d:  (i % cols) * 0.85 + Math.floor(i / cols) * 1.15,
      }));
      let maxD = 0;
      for (const c of cellData) if (c.d > maxD) maxD = c.d;
      const MIN_D = -4, MAX_D = maxD + 6;
      const durOut = 2000, rate = (MAX_D - MIN_D) / durOut;
      let front = MIN_D, lastTs = null;
      function coolLevel(d, front) {
        const dist = front - d;
        if (dist < -2) return 0.52;
        if (dist <  2) return 0.52 * (1 - (dist + 2) / 4);
        return 0;
      }
      function frame(ts) {
        if (state.stopped) return;
        if (lastTs === null) lastTs = ts;
        const dt = Math.min(ts - lastTs, 50); lastTs = ts;
        front += rate * dt;
        for (const c of cellData) _applyHeat(c, coolLevel(c.d, front), ts, null, () => {}, front);
        if (front < MAX_D) {
          state.heatRaf = requestAnimationFrame(frame);
        } else {
          _heatClearAllCells();
          state.heatApplied = false;
          state.heatCells = null;
          if (onDone) try { onDone(); } catch (_) {}
        }
      }
      state.heatRaf = requestAnimationFrame(frame);
    }
    function _cancelHeatRaf() {
      if (state.heatRaf) { cancelAnimationFrame(state.heatRaf); state.heatRaf = null; }
    }

    // ── slot execution ────────────────────────────────────────────
    /** Reveal a Euclidean disk of radius r around (cx,cy) as the probe
     *  intel comes online. Fogged cells get their `is-fogged` flag
     *  cleared (fog span fades via setFog animation). */
    function revealDisk(cx, cy, r) {
      const disk = eucDisk(cx, cy, r);
      disk.forEach((idx) => {
        const cellEl = boardCell(board, idx);
        setFog(cellEl, false);
      });
    }

    /** Execute one policy slot. Returns via onDone() when the slot's
     *  animation completes. Fires nothing visible if `verb === "wait"`
     *  beyond the roster highlight. */
    function executeSlot(slot, onDone) {
      switch (slot.verb) {
        case "probe": {
          const [tx, ty] = slot.data.target;
          const cell = boardCell(board, idxAt(tx, ty));
          // NOTE: spawnProbeTrail takes HEX color strings (#RRGGBB); it
          // parses them into RGB triples. Passing "rgb(...)" or a CSS
          // var causes parseHex to return NaN and the canvas draws
          // nothing — probe launch would be invisible.
          spawnProbeTrail(cell, "#ffffff", "#ffffff", () => {
            setFog(cell, false);
            revealDisk(tx, ty, 4);
            setProbe(cell, 3, "--seat-p1");
            state.probeCells.push(idxAt(tx, ty));
            pushLog("probe", `probe seeded at (${tx},${ty}) · 3 Nox life · §3.9.1`, "mn-eventlog-2");
            timer(onDone, 480);
          }, 900, state);
          break;
        }
        case "drop": {
          const H = slot.data.harvester;
          const [dx, dy] = H.drop;
          const cell = boardCell(board, idxAt(dx, dy));
          runOrbitalArcAnimation(board, cell, "drop", H.seat, GLYPH_HARVESTER, () => {
            // Harvest the drop cell (RED → GREEN).
            const baseTile = base[idxAt(dx, dy)];
            if (baseTile.tile === TILE.RED) {
              state.score += Math.round(baseTile.purity * RED_MULT[tierOf(baseTile.purity)]);
              setTerrain(cell, TILE.GREEN, 255);
              spawnHarvestFxLocal(cell, "#ff4040");
            }
            setEntity(cell, GLYPH_HARVESTER, H.seat);
            H._pos = [dx, dy];
            pushLog("drop", `${labelUnit(H.unit)} lands at (${dx},${dy}) — harvest on drop`, "mn-eventlog-2");
          }, state);
          timer(onDone, 1180);
          break;
        }
        case "step": {
          const H = slot.data.harvester;
          const [px, py] = H._pos;
          const [nx, ny] = slot.data.to;
          const prevCell = boardCell(board, idxAt(px, py));
          const nextCell = boardCell(board, idxAt(nx, ny));
          const baseTile = base[idxAt(nx, ny)];
          const willHarvest = baseTile.tile === TILE.RED;
          const blinkColor = willHarvest ? "#ff4040" : null;
          animateStepLocal(prevCell, nextCell, H.seat, blinkColor, () => {
            // Trail on the previous cell
            bumpTrail(prevCell, state.trailByIdx, idxAt(px, py));
            setEntity(prevCell, "");
            setEntity(nextCell, GLYPH_HARVESTER, H.seat);
            if (willHarvest) {
              state.score += Math.round(baseTile.purity * RED_MULT[tierOf(baseTile.purity)]);
              setTerrain(nextCell, TILE.GREEN, 255);
              pushLog("harvest", `${labelUnit(H.unit)} harvests (${nx},${ny}) — score → ${state.score}`, "mn-eventlog-2");
            }
            H._pos = [nx, ny];
          });
          timer(onDone, 520);
          break;
        }
        case "pickup": {
          const H = slot.data.harvester;
          const [px, py] = H._pos;
          const cell = boardCell(board, idxAt(px, py));
          runOrbitalArcAnimation(board, cell, "pickup", H.seat, GLYPH_HARVESTER, () => {
            setEntity(cell, "");
            pushLog("lift", `${labelUnit(H.unit)} lifted — cargo banked`, "mn-eventlog-2");
          }, state);
          timer(onDone, 1180);
          break;
        }
        default: {
          // wait — visible pause so the eye can register that the hour
          // did advance even though nothing else happened on the board.
          timer(onDone, 260);
        }
      }
    }

    /** Advance one hour at a time through the slot list. Each slot's
     *  row highlights running while it runs, done when its animation
     *  finishes. Between slots there's a short gap so the eye can
     *  track the cursor. Deliberately slow — the manual's pace is
     *  set for teaching, not speed-running. */
    function runPraxis(slots, onAllDone) {
      const HOUR_GAP = 260;
      let h = 0;
      function next() {
        if (state.stopped) return;
        if (h >= 21) { onAllDone && onAllDone(); return; }
        const slot = slots[h];
        markSlot(h + 1, "running");
        phase.textContent = `# H${String(h + 1).padStart(2, "0")} · ${slot.verb.toUpperCase()}`;
        executeSlot(slot, () => {
          markSlot(h + 1, "done");
          h += 1;
          timer(next, HOUR_GAP);
        });
      }
      next();
    }

    // ── stage machine ─────────────────────────────────────────────
    // 7 stages, teaching-paced:
    //   0 · POLICY intro
    //   1 · single probe (writes + PRAXIS)
    //   2 · single-harvester CONFIGURATIONS (LATE → SPREAD → EARLY, no PRAXIS)
    //   3 · single-harvester PRAXIS (early config)
    //   4 · three probes (writes + PRAXIS)
    //   5 · three-harvester WRITE (roster fills, no PRAXIS)
    //   6 · three-harvester PRAXIS (the full 21-hour cap operation)
    // Each stage has settle() (idempotent snap to end state) and
    // animate() (transition from stage-before to stage-current).
    let currentSlots = new Array(21).fill(null).map(() => ({ verb: "wait" }));

    function updateCaption(idx) {
      const s = STAGES[idx];
      labelEl.textContent = s.label;
      // body may contain <p> paragraphs and <span class="kw"> keywords —
      // render as HTML. Plain-text bodies still work (innerHTML with
      // no tags is identical to textContent).
      bodyEl.innerHTML    = s.body;
      citeEl.textContent  = s.cite;
    }

    /** Repaint the terrain of every seam cell from `base[]` (RED with its
     *  base purity). Used at the start of stages that begin a fresh
     *  Nox so any previously-harvested cells stop showing as GREEN. */
    function repaintSeamsRed() {
      for (const seam of seams) {
        for (const { x, y } of seam) {
          const b = base[idxAt(x, y)];
          setTerrain(boardCell(board, idxAt(x, y)), b.tile, b.purity);
        }
      }
    }

    /** Silently reveal a probe at `target` — no launch animation. */
    function silentSeedProbe(target) {
      const [tx, ty] = target;
      const cell = boardCell(board, idxAt(tx, ty));
      setFog(cell, false);
      revealDisk(tx, ty, 4);
      setProbe(cell, 3, "--seat-p1");
      const i = idxAt(tx, ty);
      if (!state.probeCells.includes(i)) state.probeCells.push(i);
    }
    function silentSeedAllProbes() {
      for (const p of probePlan) silentSeedProbe(p.target);
    }
    // ── PLAN markers on the map ──────────────────────────────────
    // Yellow squares on the exact cells the queued policy will touch,
    // with a small hour badge. Sit above the fog so you can see the
    // plan even before PRAXIS clears the map. This is the visual
    // heart of the "policy is decided in Orbit" lesson: you look at
    // the map before anything happens and see every future action.
    function addPlanMarker(cellIdx, label, tagBelow) {
      const cellEl = boardCell(board, cellIdx);
      if (!cellEl) return null;
      const marker = document.createElement("div");
      marker.className = "mn-plan-marker";
      if (label) {
        const tag = document.createElement("span");
        tag.className = "mn-plan-marker-tag" + (tagBelow ? " is-below" : "");
        tag.textContent = label;
        marker.appendChild(tag);
      }
      cellEl.appendChild(marker);
      state.fxNodes.add(marker);
      return marker;
    }
    function clearPlanMarkers() {
      Array.from(board.querySelectorAll(".mn-plan-marker")).forEach((m) => {
        m.remove();
        state.fxNodes.delete(m);
      });
    }

    /** Plan markers derived from a slots roster. Returns an array of
     *  { idx, label } — one per non-wait slot. Label format is
     *  "H<hours> (x,y)" so the coord is always visible on the marker
     *  itself. Multiple hours on the same cell (e.g. step + pickup)
     *  merge into "H6/7 (8,5)". */
    function planMarkersFromSlots(slots) {
      const byCell = new Map();  // idx -> { hours: [], x, y }
      for (let h = 0; h < slots.length; h++) {
        const slot = slots[h];
        if (!slot || slot.verb === "wait") continue;
        let x, y;
        if (slot.verb === "probe")  { [x, y] = slot.data.target; }
        else if (slot.verb === "drop") { const H = slot.data.harvester; [x, y] = H.drop; }
        else if (slot.verb === "step")   { [x, y] = slot.data.to; }
        else if (slot.verb === "pickup") { [x, y] = slot.data.at; }
        else continue;
        const idx = idxAt(x, y);
        if (!byCell.has(idx)) byCell.set(idx, { hours: [], x, y });
        byCell.get(idx).hours.push(h + 1);
      }
      const out = [];
      for (const [idx, info] of byCell) {
        const hStr = "H" + info.hours.join("/");
        out.push({ idx, label: `${hStr} (${info.x},${info.y})` });
      }
      return out;
    }

    // ── PLAN → PRAXIS overlay ─────────────────────────────────────
    // Every stage that has an "orbit plan, then night execution" beat
    // uses this. Shows a big PLAN card first so the caption + queued
    // roster have time to sink in, then transitions to PRAXIS BEGINS
    // and starts the execution. The point is to reinforce over and
    // over that policy is fully locked before the Nox — no reactive
    // play, no changes mid-execution.
    let _ppOverlay = null;
    function _ensureOverlay() {
      // Attach to the ancestor .mn-loop-stage, not host.parentElement.
      // In tab 4 the host's direct parent is .mn-board-wrap (a 2×2 grid
      // for the coord axes) which is not position:relative, and its
      // grid layout squashed the absolute-positioned overlay into a
      // 1-word-wide column. .mn-loop-stage is the positioned ancestor
      // both tab 3 and tab 4 share.
      const stage = host.closest(".mn-loop-stage") || host.parentElement;
      let ov = stage.querySelector(".mn-plan-praxis-overlay");
      if (!ov) {
        ov = document.createElement("div");
        ov.className = "mn-plan-praxis-overlay";
        ov.innerHTML =
          `<div class="mn-ppo-eyebrow"></div>` +
          `<div class="mn-ppo-title"></div>` +
          `<div class="mn-ppo-body"></div>` +
          `<div class="mn-ppo-sub dim"></div>`;
        stage.appendChild(ov);
      }
      _ppOverlay = ov;
      return ov;
    }
    function showPPO(eyebrow, title, body, sub, isPraxis) {
      const ov = _ensureOverlay();
      ov.querySelector(".mn-ppo-eyebrow").textContent = eyebrow || "";
      const titleEl = ov.querySelector(".mn-ppo-title");
      titleEl.textContent = title || "";
      titleEl.classList.toggle("is-praxis", !!isPraxis);
      ov.querySelector(".mn-ppo-body").textContent = body || "";
      ov.querySelector(".mn-ppo-sub").textContent  = sub || "";
      ov.classList.add("is-on");
    }
    function hidePPO() {
      if (_ppOverlay) _ppOverlay.classList.remove("is-on");
    }

    /** Small transient banner helpers — the visual is a compact
     *  chip at the top of the stage, not a full-map overlay. The
     *  teaching text lives in the caption panel on the right; the
     *  banner is a phase marker only. */
    function showPlanBanner() {
      showPPO("", "PLAN", "hit ▶ NEXT to execute", "", false);
    }
    function showPraxisBanner() {
      showPPO("", "PRAXIS", "", "", true);
      // Fade the PRAXIS chip after ~900ms so it doesn't linger.
      timer(() => hidePPO(), 900);
    }

    const STAGES = [
      // ── 0 · Intro ────────────────────────────────────────────────
      {
        label: "0 · NOX · POLICY · PRAXIS",
        body:
          '<p>Each turn is defined as a single Night (<span class="kw">Nox</span>) on the planet — exactly <span class="kw">21 hours</span> long.</p>' +
          '<p>Each player\'s turn is a <span class="kw">policy</span>: an <span class="kw">ordered sequence</span> of actions, each taking <span class="kw">an hour</span> (e.g. probe, drop, step, pickup).</p>' +
          '<p>An entire Nox\'s plan is drafted in a policy — every <span class="kw">action</span>, every <span class="kw">target</span>, decided ahead of time.</p>' +
          '<p><span class="kw">PRAXIS</span> is the execution of your POLICY (and opponents\') hour-by-hour in one sequence. When PRAXIS begins, the policy is <span class="kw">locked</span> and executes strictly in order — <span class="kw">one action per hour</span>, from H1 down to H21.</p>' +
          '<p>No reactions. No re-plans. Nothing you queued can be changed.</p>',
        cite:  "§3.10 · HOURS_PER_NIGHT = 21 · MAX_MOVES = 21",
        settle() {
          state.probeCells = [];
          state.probeNights = 0;
          state.score = 0;
          currentSlots = new Array(21).fill(null).map(() => ({ verb: "wait" }));
          renderRoster(currentSlots, "empty policy · 21 hours");
        },
        animate() {
          this.settle();
          phase.textContent = "# orbit · policy composer";
          status.textContent = "# 21 hours · up to 21 sequential actions · locked before Nox";
          pushLog("stage", "Nox = 21 hours. Policy = ordered actions. PRAXIS = deterministic playback.", "mn-eventlog-2");
          pushLog("stage", "orbit phase — draft your 21-hour policy · one action per hour", "mn-eventlog-2");
        },
        dur: 4200,
      },

      // ── 1 · SEED · one probe · PLAN ─────────────────────────────
      {
        label: "1 · SEED · PLAN",
        body:  `A single probe queued at H1 targeting (${PROBE_A[0]}, ${PROBE_A[1]}). The yellow marker on the map shows the exact cell your policy will touch. Hit NEXT to execute.`,
        cite:  "§3.9.1 · §3.11 · §3.15",
        settle() {
          state.probeCells = [];
          state.probeNights = 3;
          state.score = 0;
          currentSlots = buildRosterSingleProbe(1, PROBE_A, 0);
          renderRoster(currentSlots, "Nox · plan · 1 probe queued");
          // NOTE: no plan markers here — settle() is the "quiet end
          // state" that downstream stages chain through. If markers
          // were added here, entering stage 2 (PRAXIS) would re-add
          // them during its settle chain and the PRAXIS animation
          // would run on top of a stale yellow overlay. Markers live
          // only in this PLAN stage's animate().
        },
        animate() {
          this.settle();
          planMarkersFromSlots(currentSlots).forEach((m) => addPlanMarker(m.idx, m.label));
          phase.textContent = "# orbit · policy drafted";
          status.textContent = "# PLAN · 1 action queued · hit NEXT to execute";
          pushLog("orders",
            `policy: H1 = probe(${PROBE_A[0]},${PROBE_A[1]}) · H2-H21 = WAIT`,
            "mn-eventlog-2");
          showPlanBanner();
        },
        dur: 4500,
      },

      // ── 2 · SEED · PRAXIS ───────────────────────────────────────
      {
        label: "2 · SEED · PRAXIS",
        body:  "H1 fires: the probe launches, lands, sensor disk goes live. H2-H21 tick past as WAITs — the plan is done, the cursor rolls forward.",
        cite:  "§3.9.1 · §3.10",
        settle() {
          state.probeCells = [];
          state.probeNights = 3;
          state.score = 0;
          silentSeedProbe(PROBE_A);
          currentSlots = buildRosterSingleProbe(1, PROBE_A, 0);
          renderRoster(currentSlots, "Nox · 1 probe · done");
          for (let i = 1; i <= 21; i++) markSlot(i, "done");
        },
        animate() {
          state.probeCells = [];
          state.probeNights = 3;
          state.score = 0;
          currentSlots = buildRosterSingleProbe(1, PROBE_A, 0);
          renderRoster(currentSlots, "Nox · PRAXIS · 1 probe");
          phase.textContent = "# PRAXIS · executing";
          status.textContent = "# probe launches at H1 · then 20 hours of WAIT";
          showPraxisBanner();
          runPraxis(currentSlots, () => {
            status.textContent = "# probe landed · seam A visible · Nox complete";
            pushLog("stage", "probe seeded · sensor disk live", "mn-eventlog-2");
          });
        },
        dur: 13800,
      },

      // ── 3 · Configurations (LATE → SPREAD → EARLY) ─────────────
      {
        label: "3 · CONFIG · one harvester, three placements",
        body:  "Same 7-action chain, three legal placements: LATE, SPREAD, EARLY. All harvest the same 6 parcels. We settle on EARLY — no reason to wait.",
        cite:  "§3.10 · slot placement",
        settle() {
          state.probeCells = [];
          state.probeNights = 3;
          state.score = 0;
          silentSeedProbe(PROBE_A);
          const H = harvesterPlan[0];
          currentSlots = buildRosterSingleHarvester(0, H);
          renderRoster(currentSlots, "settled · EARLY (H1-H7)");
        },
        animate() {
          state.probeCells = [];
          state.probeNights = 3;
          state.score = 0;
          silentSeedProbe(PROBE_A);
          const H = harvesterPlan[0];
          phase.textContent = "# orbit · exploring 3 slot configurations";
          status.textContent = "# same 7-action plan · three placements";
          pushLog("orders", "three legal placements: LATE, SPREAD, EARLY", "mn-eventlog-2");
          timer(() => {
            currentSlots = buildRosterSingleHarvester(14, H);
            renderRoster(currentSlots, "config A · LATE (H15-H21)");
            pushLog("orders", "LATE — drop H15, walk H16-H20, pickup H21", "mn-eventlog-2");
            status.textContent = "# LATE — 14 hours of WAIT then the plan";
          }, 200);
          timer(() => {
            currentSlots = buildRosterSpreadHarvester([2, 5, 8, 11, 14, 17, 21], H);
            renderRoster(currentSlots, "config B · SPREAD (H2-H21, gaps)");
            pushLog("orders", "SPREAD — 7 actions scattered", "mn-eventlog-2");
            status.textContent = "# SPREAD — same plan, different hours";
          }, 2800);
          timer(() => {
            currentSlots = buildRosterSingleHarvester(0, H);
            renderRoster(currentSlots, "config C · EARLY (H1-H7)");
            pushLog("orders", "EARLY — drop H1, walk H2-H6, pickup H7 · settled", "mn-eventlog-2");
            status.textContent = "# settled on EARLY · finish first, wait later";
          }, 5600);
        },
        dur: 9200,
      },

      // ── 4 · EARLY · harvester · PLAN ───────────────────────────
      {
        label: "4 · EARLY · PLAN",
        body:  "Harvester A queued H1-H7 on the EARLY config. Yellow markers show every cell the plan touches — drop, five steps, pickup. Hit NEXT.",
        cite:  "§3.9 · §3.10",
        settle() {
          state.probeCells = [];
          state.probeNights = 3;
          state.score = 0;
          silentSeedProbe(PROBE_A);
          const H = harvesterPlan[0];
          H._pos = null;
          currentSlots = buildRosterSingleHarvester(0, H);
          renderRoster(currentSlots, "Nox · plan · 1 harvester · 7 slots");
          // Markers added only by animate() — see stage 1 note.
        },
        animate() {
          this.settle();
          planMarkersFromSlots(currentSlots).forEach((m) => addPlanMarker(m.idx, m.label));
          phase.textContent = "# orbit · 7-slot policy drafted";
          status.textContent = "# PLAN · 7 actions queued · hit NEXT to execute";
          pushLog("orders",
            "policy: H1 drop (5,3), H2-H6 step E/E/S/E/S, H7 pickup, H8-H21 WAIT",
            "mn-eventlog-2");
          showPlanBanner();
        },
        dur: 4500,
      },

      // ── 5 · EARLY · harvester · PRAXIS ─────────────────────────
      {
        label: "5 · EARLY · PRAXIS",
        body:  "H1-H7 fires. Six RED harvested along seam A, harvester lifted at H7. H8-H21 tick past as WAITs.",
        cite:  "§3.9 · §3.11 · §3.12",
        settle() {
          state.probeCells = [];
          state.probeNights = 3;
          state.score = 0;
          silentSeedProbe(PROBE_A);
          for (const { x, y } of seamA) {
            setTerrain(boardCell(board, idxAt(x, y)), TILE.GREEN, 255);
          }
          const H = harvesterPlan[0];
          H._pos = null;
          currentSlots = buildRosterSingleHarvester(0, H);
          renderRoster(currentSlots, "Nox · 1 harvester · done");
          for (let i = 1; i <= 21; i++) markSlot(i, "done");
        },
        animate() {
          state.probeCells = [];
          state.probeNights = 3;
          state.score = 0;
          silentSeedProbe(PROBE_A);
          const H = harvesterPlan[0];
          H._pos = null;
          currentSlots = buildRosterSingleHarvester(0, H);
          renderRoster(currentSlots, "Nox · PRAXIS · 1 harvester");
          phase.textContent = "# PRAXIS · executing";
          status.textContent = "# H1-H7 · 6 RED targeted";
          showPraxisBanner();
          runPraxis(currentSlots, () => {
            status.textContent = `# extracted at H7 · ${state.score} pts · H8-H21 idle`;
            pushLog("stage", `harvester complete · ${state.score} pts`, "mn-eventlog-2");
          });
        },
        dur: 15000,
      },

      // ── 6 · Three probes · PLAN ────────────────────────────────
      {
        label: "6 · THREE PROBES · PLAN",
        body:  "A fresh Nox. Three probes queued at H1, H8, H15 — spread across the night. Yellow markers show all three drop points. Hit NEXT.",
        cite:  "§3.9.1 · §3.10",
        settle() {
          // FRESH NOX — wipe every cell back to fully-fogged, clear
          // entities and trails, repaint terrain from base. Without
          // this, settle 5 (single harvester PRAXIS) leaves probe A
          // and the GREEN seam-A trail visible, and the stage looks
          // like a continuation of Night 1 instead of a new night.
          resetBoard();
          state.probeCells = [];
          state.probeNights = 3;
          state.score = 0;
          currentSlots = buildRosterAllProbes();
          renderRoster(currentSlots, "Nox · plan · 3 probes queued");
          // Markers added only by animate() — see stage 1 note.
        },
        animate() {
          this.settle();
          planMarkersFromSlots(currentSlots).forEach((m) => addPlanMarker(m.idx, m.label));
          phase.textContent = "# orbit · 3-probe policy drafted";
          status.textContent = "# PLAN · 3 actions queued · hit NEXT to execute";
          pushLog("orders",
            `probes queued H1(${PROBE_A[0]},${PROBE_A[1]}) · H8(${PROBE_B[0]},${PROBE_B[1]}) · H15(${PROBE_C[0]},${PROBE_C[1]})`,
            "mn-eventlog-2");
          showPlanBanner();
        },
        dur: 4800,
      },

      // ── 7 · Three probes · PRAXIS ──────────────────────────────
      {
        label: "7 · THREE PROBES · PRAXIS",
        body:  "Three probes fire on their scheduled hours (H1, H8, H15). All three seams surveyed by the end of the Nox.",
        cite:  "§3.10 · PRAXIS",
        settle() {
          resetBoard();                 // fresh Nox before anything else
          state.probeCells = [];
          state.probeNights = 3;
          state.score = 0;
          silentSeedAllProbes();
          currentSlots = buildRosterAllProbes();
          renderRoster(currentSlots, "Nox · 3 probes · done");
          for (let i = 1; i <= 21; i++) markSlot(i, "done");
        },
        animate() {
          resetBoard();                 // fresh Nox for the animation
          state.probeCells = [];
          state.probeNights = 3;
          state.score = 0;
          currentSlots = buildRosterAllProbes();
          renderRoster(currentSlots, "Nox · PRAXIS · 3 probes");
          phase.textContent = "# PRAXIS · executing";
          status.textContent = "# probes fire H1, H8, H15";
          showPraxisBanner();
          runPraxis(currentSlots, () => {
            status.textContent = "# 3 probes on surface · seams A, B, C surveyed";
            pushLog("stage", "3-probe survey complete", "mn-eventlog-2");
          });
        },
        dur: 16000,
      },

      // ── 8 · Three harvesters · PLAN ────────────────────────────
      {
        label: "8 · THREE HARVESTERS · PLAN",
        body:  "Full 21-hour policy. 3 harvesters × (drop + 5 steps + pickup) = 21 slots exactly — MAX_MOVES cap. 18 yellow markers cover every cell the plan will touch. Hit NEXT.",
        cite:  "§3.9 · §3.10 · MAX_MOVES = 21",
        settle() {
          resetBoard();                 // fresh Nox, then reveal probes
          state.probeCells = [];
          state.probeNights = 3;
          state.score = 0;
          silentSeedAllProbes();
          for (const H of harvesterPlan) H._pos = null;
          currentSlots = buildRosterAllHarvesters();
          renderRoster(currentSlots, "Nox · plan · 21/21 · full cap");
          // Markers added only by animate() — see stage 1 note.
        },
        animate() {
          this.settle();
          planMarkersFromSlots(currentSlots).forEach((m) => addPlanMarker(m.idx, m.label));
          phase.textContent = "# orbit · full 21-hour policy drafted";
          status.textContent = "# PLAN · 21 actions queued · MAX_MOVES saturated · hit NEXT";
          pushLog("orders",
            "3 harvesters × (drop + 5 steps + pickup) = 21 slots exactly · 18 RED targeted",
            "mn-eventlog-2");
          showPlanBanner();
        },
        dur: 6500,
      },

      // ── 9 · Three harvesters · PRAXIS ──────────────────────────
      {
        label: "9 · THREE HARVESTERS · PRAXIS",
        body:  "The 21-slot queue fires edge-to-edge. Harvester A works H1-H7 on seam A, B on H8-H14, C on H15-H21. 18 RED parcels banked in one Nox — the theoretical maximum.",
        cite:  "§3.9 · §3.11 · §3.12 · MAX_MOVES = 21",
        settle() {
          resetBoard();                 // fresh Nox baseline
          state.probeCells = [];
          state.probeNights = 3;
          state.score = 0;
          silentSeedAllProbes();
          let totalPts = 0;
          for (const seam of seams) {
            for (const { x, y } of seam) {
              const b = base[idxAt(x, y)];
              setTerrain(boardCell(board, idxAt(x, y)), TILE.GREEN, 255);
              totalPts += Math.round(b.purity * RED_MULT[tierOf(b.purity)]);
            }
          }
          state.score = totalPts;
          for (const H of harvesterPlan) H._pos = null;
          currentSlots = buildRosterAllHarvesters();
          renderRoster(currentSlots, "Nox · PRAXIS complete");
          for (let i = 1; i <= 21; i++) markSlot(i, "done");
        },
        animate() {
          resetBoard();                 // fresh Nox baseline
          state.probeCells = [];
          state.probeNights = 3;
          state.score = 0;
          silentSeedAllProbes();
          for (const H of harvesterPlan) H._pos = null;
          currentSlots = buildRosterAllHarvesters();
          renderRoster(currentSlots, "Nox · PRAXIS · 21/21");
          phase.textContent = "# PRAXIS · executing";
          status.textContent = "# 3 harvesters · 18 RED targeted";
          showPraxisBanner();
          runPraxis(currentSlots, () => {
            phase.textContent = "# 00:00 — Nox complete";
            status.textContent = `# Nox complete · ${state.score} pts · 18 parcels · cap saturated`;
            pushLog("stage",
              `Nox PRAXIS complete — ${state.score} pts across 18 parcels`,
              "mn-eventlog-2");
          });
        },
        dur: 22000,
      },
    ];

    function goStage(idx) {
      idx = ((idx % STAGES.length) + STAGES.length) % STAGES.length;
      state.timers.forEach((t) => clearTimeout(t));
      state.timers = [];
      state.fxNodes.forEach((n) => n.remove());
      state.fxNodes.clear();

      // Rip any leftover PLAN/PRAXIS overlay from the previous stage.
      hidePPO();
      clearPlanMarkers();

      _cancelHeatRaf();
      _heatClearAllCells();
      state.heatApplied = false;
      state.heatCells = null;
      resetBoard();
      state.probeCells = [];
      state.probeNights = 0;
      state.score = 0;
      for (const H of harvesterPlan) H._pos = null;

      for (let i = 0; i < idx; i++) STAGES[i].settle();
      state.stageIdx = idx;
      updateCaption(idx);
      STAGES[idx].animate();

      if (state.autoPlay) {
        state.timers.push(setTimeout(() => {
          if (state.stopped) return;
          const next = idx + 1;
          if (next >= STAGES.length) {
            stampSeams();          // fresh random purities per full cycle
            goStage(0);
          } else {
            goStage(next);
          }
        }, STAGES[idx].dur));
      }
    }
    state.goStage = goStage;

    btnPrev.onclick = () => goStage(state.stageIdx - 1);
    btnNext.onclick = () => goStage(state.stageIdx + 1);
    btnToggle.textContent = "[ ⏵ PLAY ]";
    btnToggle.onclick = () => {
      state.autoPlay = !state.autoPlay;
      btnToggle.textContent = state.autoPlay ? "[ ⏸ PAUSE ]" : "[ ⏵ PLAY ]";
      if (state.autoPlay) {
        state.timers.push(setTimeout(() => {
          if (state.stopped) return;
          const next = state.stageIdx + 1;
          if (next >= STAGES.length) goStage(0);
          else goStage(next);
        }, STAGES[state.stageIdx].dur));
      }
    };
    btnRestart.onclick = () => {
      state.autoPlay = false;
      btnToggle.textContent = "[ ⏵ PLAY ]";
      stampSeams();
      goStage(0);
    };

    goStage(0);
  }


  // ═══════════════════════════════════════════════════════════════
  // TAB 5 — VISION (fog · live · echo)
  //
  // 5 compact stages teaching the three canonical vision tiers
  // (RULEBOOK §3.8). The board is 20×12 at 24px cells (matching
  // section-3's density) with one seam cluster and one probe drop
  // point so the eye stays on the vision state transition, not
  // the terrain.
  //
  // Stage flow:
  //   0 · intro — three tiers named
  //   1 · fog — nothing revealed
  //   2 · live — probe drops, radius-4 disk goes live (white wash)
  //   3 · echo — probe decays over 3 Nox then dies; disk drops to
  //              echo (grey wash, desaturated terrain); a rival
  //              harvester walks the seam while we can't see
  //   4 · re-probe — drop a fresh probe, live re-established, the
  //              changed state (partial harvest, hold cap 6) becomes
  //              visible; 3 red cells were left uncooked
  //
  // Visual language:
  //   .is-live — subtle white wash on cells inside an active disk;
  //              adjacent cells fuse into one continuous highlight
  //   .is-echo — grey wash + desaturated terrain, "snapshot" look
  // Fog cells use the same rendering as everywhere else (░░ dim).
  // ═══════════════════════════════════════════════════════════════
  let tab5_state = null;
  function tab5_stop() {
    if (tab5_state) {
      tab5_state.stopped = true;
      tab5_state.timers.forEach((t) => clearTimeout(t));
      tab5_state.timers = [];
      tab5_state.fxNodes.forEach((n) => n.remove());
      tab5_state.fxNodes.clear();
      tab5_state = null;
    }
  }
  function tab5_start() {
    tab5_stop();
    const host        = document.getElementById("mn-board-vision");
    const status      = document.getElementById("mn-vision-status");
    const phase       = document.getElementById("mn-vision-phase");
    const labelEl     = document.getElementById("mn-stage-label-3");
    const bodyEl      = document.getElementById("mn-stage-body-3");
    const citeEl      = document.getElementById("mn-stage-cite-3");
    const btnPrev     = document.getElementById("mn-vision-prev");
    const btnNext     = document.getElementById("mn-vision-next");
    const btnToggle   = document.getElementById("mn-vision-toggle");
    const btnRestart  = document.getElementById("mn-vision-restart");

    // 20×12 board at 24px cells — same dimensions and density as
    // the section-3 harvester board, so the fog pattern reads tight
    // and flush (no horizontal banding from a cell taller than the
    // ░░ glyph). Radius-4 disk still covers ~49 cells; centre is at
    // (10, 6) so the disk sits inset from every edge.
    const cols = 20, rows = 12;
    const cellW = 24, cellH = 24;
    const total = cols * rows;

    // A small RED cluster with a mix of tiers — 9 cells: 4 trace,
    // 4 vein, 1 mass. Not a linear seam; a cluster around the probe
    // drop so we can show varied tier textures in the disk.
    const seam = [
      { x:  8, y: 5, tier: "trace" },
      { x:  9, y: 5, tier: "vein"  },
      { x:  8, y: 6, tier: "vein"  },
      { x:  9, y: 6, tier: "mass"  },  // the one mass
      { x: 10, y: 6, tier: "trace" },  // probe lands here
      { x: 11, y: 6, tier: "vein"  },
      { x:  9, y: 7, tier: "vein"  },
      { x: 10, y: 7, tier: "trace" },
      { x: 11, y: 7, tier: "trace" },
    ];
    const probeCoord = [10, 6];       // probe A lands here in stage 2/4
    // A rival harvester will walk while we can't see (during echo).
    // Drop at (8,5), step E,S,E,S,E → covers 6 red cells (drop + 5
    // steps = hold cap 6). Leaves 3 red cells UN-harvested so the
    // re-probe reveals a partial destruction, not a total wipe.
    // Walked path:
    //   (8,5) drop trace → (9,5) vein → (9,6) mass → (10,6) trace →
    //   (10,7) trace → (11,7) trace
    // Not walked: (8,6) vein, (11,6) vein, (9,7) vein
    const rivalDrop = [8, 5];
    const rivalSteps = ["E", "S", "E", "S", "E"];
    const DIR = { N: [0,-1], S: [0,1], E: [1,0], W: [-1,0] };

    const base = new Array(total).fill(null).map(() => ({ tile: TILE.EMPTY, purity: 0, fog: true }));
    for (const { x, y, tier } of seam) {
      base[y * cols + x] = {
        tile: TILE.RED,
        purity: tier === "pure" ? 255 : randPurity(tier),
        fog: true,
      };
    }

    const cells = base.map((c) => ({ ...c }));
    const board = renderBoard(host, cells, { cols, rows, cellW, cellH });

    const state = {
      stopped: false, timers: [], fxNodes: new Set(),
      stageIdx: 0, autoPlay: false,
    };
    tab5_state = state;

    function timer(fn, ms) {
      const t = setTimeout(() => { if (state.stopped) return; fn(); }, ms);
      state.timers.push(t);
      return t;
    }

    // ── helpers ───────────────────────────────────────────────────
    const idxAt = (x, y) => y * cols + x;
    const inBounds = (x, y) => x >= 0 && y >= 0 && x < cols && y < rows;
    function eucDisk(cx, cy, r) {
      const out = [];
      const r2 = r * r;
      for (let y = cy - r; y <= cy + r; y++) {
        for (let x = cx - r; x <= cx + r; x++) {
          if (!inBounds(x, y)) continue;
          const dx = x - cx, dy = y - cy;
          if (dx * dx + dy * dy <= r2) out.push(idxAt(x, y));
        }
      }
      return out;
    }

    /** Reset every cell: refog, clear entities/trails/echo/live markers,
     *  repaint terrain from base. Call at the start of every stage
     *  transition (goStage) and every full re-run. */
    function resetBoardVision() {
      for (let i = 0; i < total; i++) {
        const cellEl = boardCell(board, i);
        setFog(cellEl, true);
        setEntity(cellEl, "");
        const t = cellEl.querySelector(".mn-cell-trail");
        t.classList.remove("is-on");
        t.textContent = "";
        cellEl.classList.remove("is-live", "is-echo");
        const b = base[i];
        setTerrain(cellEl, b.tile, b.purity);
      }
    }

    /** Put a set of cell indices into LIVE state — unfog + tint
     *  with the white wash + clear any echo. Adjacent live cells
     *  fuse into one continuous highlight (no per-cell borders). */
    function setDiskLive(diskCells) {
      diskCells.forEach((i) => {
        const cellEl = boardCell(board, i);
        setFog(cellEl, false);
        cellEl.classList.remove("is-echo");
        cellEl.classList.add("is-live");
      });
    }
    /** Move the disk from LIVE → ECHO — desaturate terrain and add
     *  a grey wash to say "snapshot only, not live". */
    function setDiskEcho(diskCells) {
      diskCells.forEach((i) => {
        const cellEl = boardCell(board, i);
        setFog(cellEl, false);
        cellEl.classList.remove("is-live");
        cellEl.classList.add("is-echo");
      });
    }

    // ── stage machine ─────────────────────────────────────────────
    const STAGES = [
      // 0 · intro
      {
        label: "0 · VISION",
        body:
          '<p>Every cell is in one of three vision states: <span class="kw">fog</span>, <span class="kw">live</span>, <span class="kw">echo</span>.</p>' +
          '<p>Fog: never seen. Live: you see the current world right now (probe disk or harvester\'s plus). Echo: last-known snapshot — you saw this once, may be stale.</p>' +
          '<p><span class="kw">RULEBOOK §3.8.</span></p>',
        cite: "§3.8 · visibility tiers",
        settle() {
          resetBoardVision();
        },
        animate() {
          this.settle();
          phase.textContent = "# vision has three states";
          status.textContent = "# hit NEXT to walk through fog → live → echo";
          pushLog("stage", "vision tiers: fog · live · echo · §3.8", "mn-eventlog-3");
        },
        dur: 4200,
      },
      // 1 · fog
      {
        label: "1 · FOG · no intel",
        body:
          '<p><span class="kw">Fog</span> is the default. No probes down, no harvesters nearby — you see nothing but the ░░ blanket.</p>' +
          '<p>You know the surface is there, but the engine won\'t tell you what\'s on it.</p>',
        cite: "§3.8 · fog",
        settle() {
          resetBoardVision();
        },
        animate() {
          this.settle();
          phase.textContent = "# fog · no intel";
          status.textContent = "# fully fogged · nothing revealed · §3.8";
          pushLog("fog", "fog — cell tier = fog, no terrain, no entities visible", "mn-eventlog-3");
        },
        dur: 3800,
      },
      // 2 · live
      {
        label: "2 · LIVE · probe disk on",
        body:
          `<p>Drop a probe at <span class="kw">(${probeCoord[0]}, ${probeCoord[1]})</span>. Its radius-4 disk goes <span class="kw">live</span> — a soft white wash marks the visible area.</p>` +
          '<p>Every cell inside the disk shows the <span class="kw">current world state</span>: RED seam visible, entities visible, terrain fresh.</p>' +
          '<p><span class="kw">Harvesters can only land on LIVE cells.</span> A harvester drop into fog or echo is illegal — you must be looking at the ground to put a machine on it.</p>',
        cite: "§3.9.1 · §3.11 · SOC_DROP_MODE=live_only",
        settle() {
          resetBoardVision();
          const cell = boardCell(board, idxAt(probeCoord[0], probeCoord[1]));
          const disk = eucDisk(probeCoord[0], probeCoord[1], 4);
          setDiskLive(disk);
          setProbe(cell, 3, "--seat-p1");
        },
        animate() {
          resetBoardVision();
          phase.textContent = "# probe launches · disk goes live";
          status.textContent = "# radius-4 disk · white wash marks the LIVE area";
          pushLog("probe", `probe seeded at (${probeCoord[0]},${probeCoord[1]}) · disk = live · §3.11`, "mn-eventlog-3");
          const cell = boardCell(board, idxAt(probeCoord[0], probeCoord[1]));
          // Animate probe launch through fog
          spawnProbeTrail(cell, "#ffffff", "#ffffff", () => {
            if (state.stopped) return;
            const disk = eucDisk(probeCoord[0], probeCoord[1], 4);
            // Reveal disk cell by cell in a ripple from the probe
            disk.sort((a, b) => {
              const ax = a % cols, ay = (a / cols) | 0;
              const bx = b % cols, by = (b / cols) | 0;
              return ((ax - probeCoord[0]) ** 2 + (ay - probeCoord[1]) ** 2)
                   - ((bx - probeCoord[0]) ** 2 + (by - probeCoord[1]) ** 2);
            });
            disk.forEach((i, k) => {
              state.timers.push(setTimeout(() => {
                if (state.stopped) return;
                const c = boardCell(board, i);
                setFog(c, false);
                c.classList.add("is-live");
              }, 60 + k * 30));
            });
            state.timers.push(setTimeout(() => {
              if (state.stopped) return;
              setProbe(cell, 3, "--seat-p1");
              status.textContent = "# disk fully live · seam visible in current state";
              pushLog("cover", "disk cells kind=terrain, stale=false, echo_probe=false — LIVE", "mn-eventlog-3");
            }, 60 + disk.length * 30 + 200));
          }, 900, state);
        },
        dur: 5200,
      },
      // 3 · echo — probe decays over 3 Nox, then dies, disk drops to echo
      {
        label: "3 · ECHO · probe decays, disk falls to snapshot",
        body:
          '<p>Probes carry <span class="kw">3 Nox of life</span>. Each Aurora ticks the ring count down: 3 → 2 → 1 → destroyed.</p>' +
          '<p>When it dies the disk drops from live to <span class="kw">echo</span>: last-known snapshot, no longer refreshing. The terrain looks the same, but the world can change underneath.</p>' +
          '<p><span class="kw">RULEBOOK §3.11.</span></p>',
        cite: "§3.11 · probe lifetime · §3.8 echo",
        settle() {
          resetBoardVision();
          const disk = eucDisk(probeCoord[0], probeCoord[1], 4);
          setDiskEcho(disk);
        },
        animate() {
          resetBoardVision();
          const cell = boardCell(board, idxAt(probeCoord[0], probeCoord[1]));
          const disk = eucDisk(probeCoord[0], probeCoord[1], 4);
          // Start LIVE with a full-life probe (3 Nox remaining)
          setDiskLive(disk);
          setProbe(cell, 3, "--seat-p1");
          phase.textContent = "# Nox 1 · probe fresh · 3 rings";
          status.textContent = "# probe on surface · disk = live · 3 Nox to go";
          pushLog("probe", "probe on surface · life = 3 Nox · disk = live", "mn-eventlog-3");
          // Aurora 1 → 2 rings left
          state.timers.push(setTimeout(() => {
            if (state.stopped) return;
            setProbe(cell, 2, "--seat-p1");
            phase.textContent = "# Aurora 1 · probe ticks · 2 rings";
            status.textContent = "# still live · 2 Nox remaining";
            pushLog("aurora", "Aurora 1 · probe life 3 → 2 · rings decrement", "mn-eventlog-3");
          }, 1400));
          // Aurora 2 → 1 ring left
          state.timers.push(setTimeout(() => {
            if (state.stopped) return;
            setProbe(cell, 1, "--seat-p1");
            phase.textContent = "# Aurora 2 · probe ticks · 1 ring";
            status.textContent = "# still live · 1 Nox remaining · running out";
            pushLog("aurora", "Aurora 2 · probe life 2 → 1 · rings decrement", "mn-eventlog-3");
          }, 2800));
          // Aurora 3 → probe destroyed, disk drops to echo
          state.timers.push(setTimeout(() => {
            if (state.stopped) return;
            setEntity(cell, "");
            phase.textContent = "# Aurora 3 · probe expires · disk → ECHO";
            status.textContent = "# probe gone · disk fell to echo (snapshot state)";
            pushLog("aurora", "Aurora 3 · probe expires · disk transitions live → echo · §3.8", "mn-eventlog-3");
            disk.forEach((i) => {
              const c = boardCell(board, i);
              c.classList.remove("is-live");
              c.classList.add("is-echo");
            });
            state.timers.push(setTimeout(() => {
              if (state.stopped) return;
              status.textContent = "# echo cells: last-known state · may already be stale";
              pushLog("stage", "you see what was there when the probe died · not what's there now", "mn-eventlog-3");
            }, 900));
          }, 4200));
        },
        dur: 7200,
      },
      // 4 · re-probe reveals partial change
      {
        label: "4 · RE-PROBE · echo was stale",
        body:
          '<p>Drop a fresh probe. Disk goes <span class="kw">live</span> again — and we discover the world moved on.</p>' +
          '<p>A rival harvester dropped and walked through the seam while we were blind. It hit <span class="kw">6 cells</span> (its hold cap) before lifting — including the one mass. Three RED cells are still there; they didn\'t fit in the hold.</p>' +
          '<p>The GREEN + trail cells are the rival\'s work. The echo we\'d trusted was a lie, but only partially — some of the seam survived.</p>',
        cite: "§3.8 · §3.9.7 · §3.10 hold cap",
        settle() {
          resetBoardVision();
          const disk = eucDisk(probeCoord[0], probeCoord[1], 4);
          setDiskLive(disk);
          const cell = boardCell(board, idxAt(probeCoord[0], probeCoord[1]));
          setProbe(cell, 3, "--seat-p1");
          // Silent apply of rival walk to the 6 cells they harvested
          let cx = rivalDrop[0], cy = rivalDrop[1];
          for (const s of [null, ...rivalSteps]) {
            if (s) { const [dx, dy] = DIR[s]; cx += dx; cy += dy; }
            const b = base[idxAt(cx, cy)];
            if (b && b.tile === TILE.RED) {
              setTerrain(boardCell(board, idxAt(cx, cy)), TILE.GREEN, 255);
              const tr = boardCell(board, idxAt(cx, cy)).querySelector(".mn-cell-trail");
              tr.textContent = CH_LIGHT;
              tr.classList.add("is-on");
            }
          }
        },
        animate() {
          resetBoardVision();
          const disk = eucDisk(probeCoord[0], probeCoord[1], 4);
          // Start in ECHO (from stage 3 end state) — seam still looks RED
          // to us because that's the snapshot we're holding. The rival
          // has already come and gone during the echo period; we just
          // don't know it yet.
          setDiskEcho(disk);
          phase.textContent = "# echo on the seam · rival came and went while we were blind";
          status.textContent = "# under echo · rival already harvested · we still see the old snapshot";
          pushLog("stage", "echo snapshot: seam looks RED to us · rival's damage already done", "mn-eventlog-3");
          // Beat 1: launch a fresh probe → live
          state.timers.push(setTimeout(() => {
            if (state.stopped) return;
            const cell = boardCell(board, idxAt(probeCoord[0], probeCoord[1]));
            phase.textContent = "# re-probe · disk relights";
            spawnProbeTrail(cell, "#ffffff", "#ffffff", () => {
              if (state.stopped) return;
              // Convert echo → live for the disk
              disk.forEach((i) => {
                const c = boardCell(board, i);
                c.classList.remove("is-echo");
                c.classList.add("is-live");
              });
              setProbe(cell, 3, "--seat-p1");
              // Reveal the already-done rival harvest all at once —
              // 6 cells flip from RED to GREEN + trail. No walk animation,
              // no per-cell harvest flash, because the walk happened
              // earlier during echo, off-screen. This is just the truth
              // finally becoming visible.
              let cx = rivalDrop[0], cy = rivalDrop[1];
              const path = [];
              for (const s of [null, ...rivalSteps]) {
                if (s) { const [dx, dy] = DIR[s]; cx += dx; cy += dy; }
                path.push([cx, cy]);
              }
              path.forEach((p) => {
                const idx = idxAt(p[0], p[1]);
                const b = base[idx];
                const c = boardCell(board, idx);
                if (b && b.tile === TILE.RED) {
                  setTerrain(c, TILE.GREEN, 255);
                  const tr = c.querySelector(".mn-cell-trail");
                  tr.textContent = CH_LIGHT;
                  tr.classList.add("is-on");
                }
              });
              status.textContent = "# fresh live · 6 cells were harvested while we were blind · 3 red left";
              pushLog("cover", "re-probe · disk = live · revealed state differs from echo", "mn-eventlog-3");
              pushLog("harvest", "6 cells cooked (drop + 5 walked) · rival hit hold cap · 3 red left uncooked", "mn-eventlog-3");
              state.timers.push(setTimeout(() => {
                if (state.stopped) return;
                status.textContent = "# lesson: echo can be stale · the only way to know is to look again";
                pushLog("stage", "echo we trusted was a lie · the world moved while we were blind", "mn-eventlog-3");
              }, 1200));
            }, 900, state);
          }, 2200));
        },
        dur: 7500,
      },
    ];

    function updateCaption(idx) {
      const s = STAGES[idx];
      labelEl.textContent = s.label;
      bodyEl.innerHTML    = s.body;
      citeEl.textContent  = s.cite;
    }
    function goStage(idx) {
      idx = ((idx % STAGES.length) + STAGES.length) % STAGES.length;
      state.timers.forEach((t) => clearTimeout(t));
      state.timers = [];
      state.fxNodes.forEach((n) => n.remove());
      state.fxNodes.clear();
      resetBoardVision();
      for (let i = 0; i < idx; i++) STAGES[i].settle();
      state.stageIdx = idx;
      updateCaption(idx);
      STAGES[idx].animate();
      if (state.autoPlay) {
        state.timers.push(setTimeout(() => {
          if (state.stopped) return;
          goStage(idx + 1 >= STAGES.length ? 0 : idx + 1);
        }, STAGES[idx].dur));
      }
    }
    state.goStage = goStage;

    btnPrev.onclick    = () => goStage(state.stageIdx - 1);
    btnNext.onclick    = () => goStage(state.stageIdx + 1);
    btnToggle.textContent = "[ ⏵ PLAY ]";
    btnToggle.onclick  = () => {
      state.autoPlay = !state.autoPlay;
      btnToggle.textContent = state.autoPlay ? "[ ⏸ PAUSE ]" : "[ ⏵ PLAY ]";
      if (state.autoPlay) {
        state.timers.push(setTimeout(() => {
          if (state.stopped) return;
          const next = state.stageIdx + 1;
          goStage(next >= STAGES.length ? 0 : next);
        }, STAGES[state.stageIdx].dur));
      }
    };
    btnRestart.onclick = () => {
      state.autoPlay = false;
      btnToggle.textContent = "[ ⏵ PLAY ]";
      goStage(0);
    };

    goStage(0);
  }


  // ═══════════════════════════════════════════════════════════════
  // TAB 6 — OPPONENTS (simultaneous multi-seat PRAXIS)
  //
  // Step-by-step story of simultaneous execution across two Nox.
  // The board starts fully fogged — every reveal is caused by a
  // probe or a harvester the viewer just watched deploy.
  //
  // Two policy panels sit beside the board: YOUR (P1, white) and
  // OPPONENT (P2, yellow). Both are populated with the seat's real
  // per-hour intent. In-game you never see the opponent's policy;
  // we show it here for teaching.
  //
  // Stage flow:
  //   0 · fog · empty policies drafted
  //   1 · Nox 1 · both policies now show H01=PROBE
  //   2 · Nox 1 PRAXIS · both probes fire simultaneously (fog opens)
  //   3 · Nox 2 · both policies show drops + walks + pickups.
  //         YOUR walk is short (4 hours), OPPONENT's is longer (8).
  //   4 · Nox 2 PRAXIS · drops together at H01, walks in lockstep,
  //         YOUR pickup at H06, OPPONENT pickup delayed until H10.
  //
  // Reuses Tab 3's spawnProbeTrail + runOrbitalArcAnimation exactly.
  // ═══════════════════════════════════════════════════════════════
  let tab6_state = null;
  function tab6_stop() {
    if (tab6_state) {
      tab6_state.stopped = true;
      tab6_state.timers.forEach((t) => clearTimeout(t));
      tab6_state.timers = [];
      if (tab6_state.heatRaf) {
        cancelAnimationFrame(tab6_state.heatRaf);
        tab6_state.heatRaf = null;
      }
      tab6_state.fxNodes.forEach((n) => n.remove());
      tab6_state.fxNodes.clear();
      tab6_state = null;
    }
  }

  function tab6_start() {
    tab6_stop();
    const host       = document.getElementById("mn-board-opp");
    const status     = document.getElementById("mn-opp-status");
    const phase      = document.getElementById("mn-opp-phase");
    const labelEl    = document.getElementById("mn-stage-label-6");
    const bodyEl     = document.getElementById("mn-stage-body-6");
    const citeEl     = document.getElementById("mn-stage-cite-6");
    const btnPrev    = document.getElementById("mn-opp-prev");
    const btnNext    = document.getElementById("mn-opp-next");
    const btnToggle  = document.getElementById("mn-opp-toggle");
    const btnRestart = document.getElementById("mn-opp-restart");
    const policyList1 = document.getElementById("mn-opp-policy-list-1");
    const policyList2 = document.getElementById("mn-opp-policy-list-2");
    const policyList3 = document.getElementById("mn-opp-policy-list-3");
    const policyList4 = document.getElementById("mn-opp-policy-list-4");
    const policyNox1  = document.getElementById("mn-opp-policy-nox-1");
    const policyNox2  = document.getElementById("mn-opp-policy-nox-2");
    const policyNox3  = document.getElementById("mn-opp-policy-nox-3");
    const policyNox4  = document.getElementById("mn-opp-policy-nox-4");
    const policyTitle1 = document.getElementById("mn-opp-policy-title-1");
    const policyTitle2 = document.getElementById("mn-opp-policy-title-2");
    const policyTitle3 = document.getElementById("mn-opp-policy-title-3");
    const policyTitle4 = document.getElementById("mn-opp-policy-title-4");
    const policyPanels = document.querySelector('.mn-opp-policies');
    const policyPanel1 = document.querySelector('.mn-opp-policy[data-seat="p1"]');
    const policyPanel2 = document.querySelector('.mn-opp-policy[data-seat="p2"]');
    const policyPanel3 = document.querySelector('.mn-opp-policy[data-seat="p3"]');
    const policyPanel4 = document.querySelector('.mn-opp-policy[data-seat="p4"]');
    const noxSticker   = document.getElementById("mn-opp-nox-sticker");
    const noxSweep     = document.getElementById("mn-opp-nox-sweep");
    const noxSweepLabel = document.getElementById("mn-opp-nox-sweep-label");

    // 28×12 at 24px — Tab-3 style, just wider so both seats' zones
    // sit clear of each other.
    const cols = 28, rows = 12;
    const cellW = 24, cellH = 24;
    const total = cols * rows;

    // Two red seams under each seat's harvest zone.  There's a shared
    // central row (x=10..15, y=5) so both probes cover part of the
    // same seam and P2 walks through it into P1's disk.  Extras at
    // y=8, y=10, y=11 give the 4-seat scenario something to harvest.
    const RED_SEAM = [
      // P1 harvest cluster (top-left)
      { x:  8, y: 5 },
      { x:  9, y: 5 }, { x:  9, y: 6 },
      { x: 10, y: 6 }, { x: 10, y: 7 },
      // Shared central row — P2 walks westward through this
      { x: 10, y: 5 },
      { x: 11, y: 5 }, { x: 12, y: 5, mass: true }, { x: 13, y: 5 },
      { x: 14, y: 5 },
      { x: 15, y: 5 },
      // P2 side extras
      { x: 15, y: 4 }, { x: 15, y: 6 },
      // 4-seat P1 (offset drop) extras — path (9,5)→(10,5)→(10,6)→(11,6)→(11,7)
      { x: 11, y: 6 }, { x: 11, y: 7 },
      // 4-seat P2 walk zone — path (21,8)→(20,8)→...→(16,8)
      { x: 20, y: 8 }, { x: 21, y: 8 }, { x: 22, y: 8, mass: true },
      { x: 19, y: 8 }, { x: 18, y: 8 }, { x: 17, y: 8 }, { x: 16, y: 8 },
      // 4-seat P3 walk zone — path (5,8)→...→(9,8)
      { x:  5, y: 8 }, { x:  6, y: 8 }, { x:  7, y: 8 },
      { x:  8, y: 8 }, { x:  9, y: 8 },
      // 4-seat P4 walk zone — path (12,10)→(11,10)→(10,10)→(10,11)→(9,11)
      { x: 12, y: 10 }, { x: 11, y: 10 }, { x: 10, y: 10 },
      { x: 10, y: 11 }, { x:  9, y: 11 }, { x: 11, y: 11 },
      // P3's 2nd probe area (a lonely tile)
      { x: 24, y: 2 },
    ];

    const DIR = { N: [0,-1], S: [0,1], E: [1,0], W: [-1,0] };

    // Seat plan — probes are close enough (7 cells apart) that P2's
    // final walk steps enter P1's live probe disk.  Both harvesters
    // stay within hold-cap 6 (drop + up to 5 steps).
    const P1 = {
      color: "--seat-p1",
      probe: [ 8, 5],
      // Nox 2 policy: drop at H01, walk 4 steps, pickup at H06
      nox2: {
        drop:   [ 8, 5],
        steps:  ["E", "S", "E", "S"],       // hours 2..5
        pickAt: [10, 7],
        pickHour: 6,
      },
    };
    const P2 = {
      color: "--seat-p2",
      probe: [15, 5],
      // Nox 2 policy: drop, walk 5 steps west into P1's disk, pickup
      // at H07 (delayed by one hour vs P1).  Drop + 5 steps = 6 cells
      // = hold cap.
      nox2: {
        drop:   [15, 5],
        steps:  ["W", "W", "W", "W", "W"],   // hours 2..6
        pickAt: [10, 5],
        pickHour: 7,
      },
    };

    // Four-seat scenario data (stages 6 & 7).  Two seats (P1, P3) drop
    // two probes each; P2 and P4 drop one.  Total: 6 probes on Nox 1.
    // Then all 4 seats deploy one harvester each on Nox 2, with
    // intentionally overlapping paths so P2 and P3 both eventually
    // walk into P1's disks.
    const P3_S = { color: "--seat-p3", label: "P3" };
    const P4_S = { color: "--seat-p4", label: "P4" };
    const P1_S = { color: P1.color, label: "P1" };
    const P2_S = { color: P2.color, label: "P2" };
    const FOUR_PROBES = [
      { hour: 1, seat: P1_S, at: [ 8, 5] },
      { hour: 1, seat: P2_S, at: [22, 8] },
      { hour: 1, seat: P3_S, at: [ 4, 8] },
      { hour: 1, seat: P4_S, at: [12, 9] },
      { hour: 2, seat: P1_S, at: [16, 5] }, // P1's second probe
      { hour: 2, seat: P3_S, at: [24, 2] }, // P3's second probe
    ];
    const FOUR_HARVESTERS = [
      // Drops are offset one cell from the probe so the harvester
      // doesn't crush the probe on landing (illegal in-game).
      { seat: P1_S, drop: [ 9, 5], steps: ["E","S","E","S"],     pickAt: [11,  7], pickHour: 6 },
      { seat: P2_S, drop: [21, 8], steps: ["W","W","W","W","W"], pickAt: [16,  8], pickHour: 7 },
      { seat: P3_S, drop: [ 5, 8], steps: ["E","E","E","E"],     pickAt: [ 9,  8], pickHour: 6 },
      { seat: P4_S, drop: [12,10], steps: ["W","W","S","W"],     pickAt: [ 9, 11], pickHour: 6 },
    ];

    // Build base terrain — mostly EMPTY, red where the shared seam lives.
    const base = new Array(total).fill(null).map(() => ({ tile: TILE.EMPTY, purity: 0, fog: true }));
    for (const s of RED_SEAM) {
      base[s.y * cols + s.x] = {
        tile: TILE.RED,
        purity: s.mass ? 200 : randPurity("vein"),
        fog: true,
      };
    }

    const cells = base.map((c) => ({ ...c }));
    const board = renderBoard(host, cells, { cols, rows, cellW, cellH });

    const state = {
      stopped: false, timers: [], fxNodes: new Set(),
      stageIdx: 0, autoPlay: false,
      // Engine heat-sweep bookkeeping (see playAuroraSweepLocal /
      // playVesperaSweepLocal further down). Captured on Aurora,
      // consumed and cleared on Vespera.
      heatCells: null, heatRaf: null, heatApplied: false,
    };
    tab6_state = state;

    // ── helpers ───────────────────────────────────────────────────
    const idxAt = (x, y) => y * cols + x;
    const inBounds = (x, y) => x >= 0 && y >= 0 && x < cols && y < rows;
    const timer = (fn, ms) => {
      const t = setTimeout(() => { if (state.stopped) return; fn(); }, ms);
      state.timers.push(t);
      return t;
    };

    function eucDisk(cx, cy, r) {
      const out = [];
      const r2 = r * r;
      for (let y = cy - r; y <= cy + r; y++) {
        for (let x = cx - r; x <= cx + r; x++) {
          if (!inBounds(x, y)) continue;
          const dx = x - cx, dy = y - cy;
          if (dx * dx + dy * dy <= r2) out.push(idxAt(x, y));
        }
      }
      return out;
    }

    // Reset every cell to fully-fogged base terrain.
    function resetBoardOpp() {
      for (let i = 0; i < total; i++) {
        const cellEl = boardCell(board, i);
        setFog(cellEl, true);
        setEntity(cellEl, "");
        const t = cellEl.querySelector(".mn-cell-trail");
        t.classList.remove("is-on");
        t.textContent = "";
        cellEl.classList.remove("is-live", "is-echo");
        const b = base[i];
        setTerrain(cellEl, b.tile, b.purity);
      }
    }
    // Reveal a disk: unfog + light wash.
    function revealDisk(indices) {
      indices.forEach((i) => {
        const c = boardCell(board, i);
        setFog(c, false);
        c.classList.remove("is-echo");
        c.classList.add("is-live");
      });
    }
    // Cells covered by a harvester's plus-shape sensor: self + 4
    // cardinals. This is what a harvester adds to its owning seat's
    // LIVE set while it's on the surface. Once it lifts, those cells
    // (that weren't also in a probe disk) fall to ECHO.
    function plusCells(x, y) {
      const out = [];
      [[0,0],[1,0],[-1,0],[0,1],[0,-1]].forEach(([dx, dy]) => {
        const nx = x + dx, ny = y + dy;
        if (inBounds(nx, ny)) out.push(idxAt(nx, ny));
      });
      return out;
    }
    /** Build a live/echo painter closure that persists across step
     *  timers within a single stage. `probeDisks` is the union of
     *  every seat's active probe disks (always LIVE). `seenEver`
     *  tracks any cell that has been live at some point — those
     *  become ECHO once nobody's looking at them. */
    function makeVisionPainter(probeDiskIndices) {
      const probeDisks = new Set(probeDiskIndices);
      const seenEver = new Set(probeDiskIndices);
      return function paint(harvPluses) {
        const liveNow = new Set(probeDisks);
        for (const plus of harvPluses) plus.forEach((i) => liveNow.add(i));
        liveNow.forEach((i) => seenEver.add(i));
        for (let i = 0; i < total; i++) {
          const c = boardCell(board, i);
          if (liveNow.has(i)) {
            setFog(c, false);
            c.classList.remove("is-echo");
            c.classList.add("is-live");
          } else if (seenEver.has(i)) {
            setFog(c, false);
            c.classList.remove("is-live");
            c.classList.add("is-echo");
          }
          // fog stays fog otherwise
        }
      };
    }

    const SEAT_HEX = {
      "--seat-p1": "#FFFFFF",
      "--seat-p2": "#FCF871",
      "--seat-p3": "#FF7EB6",
      "--seat-p4": "#7EE0FF",
    };

    // Local harvest-flash — same as Tab 3, scoped for cleanup.
    function harvestFxLocal(cell, color) {
      const rect = cell.getBoundingClientRect();
      const cx = rect.left + rect.width * 0.5;
      const cy = rect.top + rect.height * 0.5;
      const blink = document.createElement("div");
      blink.className = "mn-harvest-blink";
      blink.style.setProperty("--blink-color", color);
      cell.appendChild(blink);
      state.fxNodes.add(blink);
      blink.addEventListener("animationend", () => { blink.remove(); state.fxNodes.delete(blink); }, { once: true });
      for (let i = 0; i < 6; i++) {
        const angle = (i / 6) * Math.PI * 2 + (Math.random() - 0.5) * 0.4;
        const dist = rect.width * (1.6 + Math.random() * 1.2);
        const p = document.createElement("div");
        p.className = "mn-harvest-particle";
        p.style.left = `${cx.toFixed(1)}px`;
        p.style.top  = `${cy.toFixed(1)}px`;
        const sz = Math.max(2, Math.round(rect.width * 0.20));
        p.style.width = `${sz}px`; p.style.height = `${sz}px`;
        p.style.setProperty("--dx", `${(Math.cos(angle) * dist).toFixed(1)}px`);
        p.style.setProperty("--dy", `${(Math.sin(angle) * dist).toFixed(1)}px`);
        p.style.background = color;
        document.body.appendChild(p);
        state.fxNodes.add(p);
        p.addEventListener("animationend", () => { p.remove(); state.fxNodes.delete(p); }, { once: true });
      }
    }

    // ── policy panel ──────────────────────────────────────────────
    // Render 21-hour policy into a given list element.
    // slots is an array indexed [0..20]; each is { verb, target } or
    // undefined (rendered as WAIT).
    function renderPolicy(listEl, slots) {
      listEl.innerHTML = "";
      for (let i = 0; i < 21; i++) {
        const slot = slots[i] || { verb: "wait" };
        const row = document.createElement("div");
        row.className = "mn-roster-slot";
        row.dataset.hour = String(i + 1);
        row.dataset.verb = slot.verb;
        if (slot.verb === "wait") row.classList.add("is-empty");
        else row.classList.add("is-queued");
        const hourStr = "H" + String(i + 1).padStart(2, "0");
        // Combine verb + target into a single compact string so each
        // row fits on one line in a narrow panel:
        //   probe (5,5) → "PROBE 5,5"
        //   step E      → "STEP E"
        //   pickup      → "PICKUP"
        //   wait        → "WAIT"
        let move = slot.verb.toUpperCase();
        if (slot.target) {
          const stripped = slot.target.replace(/[()]/g, "");
          move += " " + stripped;
        }
        row.innerHTML =
          `<span class="mn-roster-hour">${hourStr}</span>` +
          `<span class="mn-roster-verb is-neutral">${move}</span>`;
        listEl.appendChild(row);
      }
    }
    function markPolicySlot(listEl, hour, mode) {
      const row = listEl.children[hour - 1];
      if (!row) return;
      row.classList.remove("is-running", "is-done");
      if (mode === "running") row.classList.add("is-running");
      else if (mode === "done") row.classList.add("is-done");
    }
    // Fill a policy panel with redacted rows — used when the panel
    // is showing the opponent's script and we want to convey "hidden
    // in-game, shown here as a black bar per hour".
    function renderRedactedPolicy(listEl) {
      listEl.innerHTML = "";
      for (let i = 0; i < 21; i++) {
        const row = document.createElement("div");
        row.className = "mn-roster-slot";
        row.dataset.hour = String(i + 1);
        row.dataset.verb = "redacted";
        const hourStr = "H" + String(i + 1).padStart(2, "0");
        row.innerHTML =
          `<span class="mn-roster-hour">${hourStr}</span>` +
          `<span class="mn-roster-verb is-neutral">▓▓▓▓▓</span>`;
        listEl.appendChild(row);
      }
    }
    // Fire (visually mark) an hour in both policies at once.
    function fireHour(hour, p1Verb, p2Verb) {
      if (p1Verb) markPolicySlot(policyList1, hour, "running");
      if (p2Verb) markPolicySlot(policyList2, hour, "running");
      timer(() => {
        if (p1Verb) markPolicySlot(policyList1, hour, "done");
        if (p2Verb) markPolicySlot(policyList2, hour, "done");
      }, 500);
    }
    // Fire an hour across all four panels — seatVerbs is an object
    // like { P1: "probe", P2: null, P3: "probe", P4: null }.
    function fireHourAll(hour, seatVerbs) {
      const lists = { P1: policyList1, P2: policyList2, P3: policyList3, P4: policyList4 };
      for (const [k, v] of Object.entries(seatVerbs)) {
        if (v && lists[k]) markPolicySlot(lists[k], hour, "running");
      }
      timer(() => {
        for (const [k, v] of Object.entries(seatVerbs)) {
          if (v && lists[k]) markPolicySlot(lists[k], hour, "done");
        }
      }, 500);
    }

    // Build policy-slot arrays for the various stages.
    const EMPTY_POLICY = [];
    const NOX1_P1 = [{ verb: "probe", target: `(${P1.probe[0]},${P1.probe[1]})` }];
    const NOX1_P2 = [{ verb: "probe", target: `(${P2.probe[0]},${P2.probe[1]})` }];
    // Nox 2 build: H01=drop, H02..=step targeted at the destination
    // cell (coords, not compass), then pickup at seat.nox2.pickAt.
    // PICKUP has no target — it happens wherever the harvester is
    // sitting at pickHour, so a coordinate would be redundant.
    function buildNox2Policy(seat) {
      const arr = [{ verb: "drop", target: `(${seat.nox2.drop[0]},${seat.nox2.drop[1]})` }];
      let x = seat.nox2.drop[0], y = seat.nox2.drop[1];
      for (const s of seat.nox2.steps) {
        const [dx, dy] = DIR[s];
        x += dx; y += dy;
        arr.push({ verb: "step", target: `(${x},${y})` });
      }
      arr[seat.nox2.pickHour - 1] = { verb: "pickup" };
      return arr;
    }
    const NOX2_P1 = buildNox2Policy(P1);
    const NOX2_P2 = buildNox2Policy(P2);

    // Nox 1 policies for the 4-seat scenario, one array per seat.
    // Ordered by hour (index 0 = H01).  Empty slots default to WAIT.
    function nox1PolicyFor(seatKey) {
      const arr = [];
      for (const p of FOUR_PROBES) {
        if (p.seat.label === seatKey) {
          arr[p.hour - 1] = { verb: "probe", target: `(${p.at[0]},${p.at[1]})` };
        }
      }
      return arr;
    }
    // Nox 2 policies for the 4-seat scenario.  Same schema — step
    // targets are the destination cell, not a compass direction.
    // PICKUP is bare (no target) — it fires wherever the harvester
    // stands, coordinates would be redundant.
    function nox2PolicyFor4(harv) {
      const arr = [{ verb: "drop", target: `(${harv.drop[0]},${harv.drop[1]})` }];
      let x = harv.drop[0], y = harv.drop[1];
      for (const s of harv.steps) {
        const [dx, dy] = DIR[s];
        x += dx; y += dy;
        arr.push({ verb: "step", target: `(${x},${y})` });
      }
      arr[harv.pickHour - 1] = { verb: "pickup" };
      return arr;
    }
    const NOX1_4P = {
      P1: nox1PolicyFor("P1"),
      P2: nox1PolicyFor("P2"),
      P3: nox1PolicyFor("P3"),
      P4: nox1PolicyFor("P4"),
    };
    const NOX2_4P = {
      P1: nox2PolicyFor4(FOUR_HARVESTERS[0]),
      P2: nox2PolicyFor4(FOUR_HARVESTERS[1]),
      P3: nox2PolicyFor4(FOUR_HARVESTERS[2]),
      P4: nox2PolicyFor4(FOUR_HARVESTERS[3]),
    };

    // Show/hide panels for the current stage's layout.  Configuration:
    //   two-panel: P1 + P2 visible, both titled ("YOUR POLICY · P1", "OPPONENT · P2")
    //   four-panel: all 4 visible with compact titles ("P1", "P2", "P3", "P4")
    function configureTwoPanel(p2Title = "OPPONENT · P2") {
      policyPanels.setAttribute("data-panels", "2");
      policyPanel1.hidden = false;
      policyPanel2.hidden = false;
      policyPanel3.hidden = true;
      policyPanel4.hidden = true;
      // Also strip the fade-in class so P3/P4 don't have residual
      // animation state when they eventually reappear.
      policyPanel3.classList.remove("is-appearing");
      policyPanel4.classList.remove("is-appearing");
      policyTitle1.textContent = "YOUR POLICY · P1";
      policyTitle2.textContent = p2Title;
    }
    function configureFourPanel() {
      policyPanels.setAttribute("data-panels", "4");
      policyPanel1.hidden = false;
      policyPanel2.hidden = false;
      policyPanel3.hidden = false;
      policyPanel4.hidden = false;
      policyTitle1.textContent = "P1";
      policyTitle2.textContent = "P2";
      policyTitle3.textContent = "P3";
      policyTitle4.textContent = "P4";
      // Trigger the fade-in animation by removing + re-adding the
      // is-appearing class after a forced reflow so it plays every
      // time we enter a 4-panel stage.
      [policyPanel3, policyPanel4].forEach(p => {
        p.classList.remove("is-appearing");
        // eslint-disable-next-line no-unused-expressions
        p.offsetWidth;
        p.classList.add("is-appearing");
      });
    }
    // Clear ALL panels' redacted styling and rendering — called by
    // goStage() so entering a stage always starts from a known state.
    function clearRedactedFlags() {
      [policyPanel1, policyPanel2, policyPanel3, policyPanel4].forEach(p => p && p.classList.remove("is-redacted"));
    }
    // Nox-praxis sticker helpers. Called at the moment PRAXIS starts
    // firing for a given Nox to label the current animation.
    function showNoxSticker(text) {
      if (!noxSticker) return;
      noxSticker.textContent = text;
      noxSticker.hidden = false;
      // Force reflow so the transition kicks in
      // eslint-disable-next-line no-unused-expressions
      noxSticker.offsetHeight;
      noxSticker.classList.add("is-on");
    }
    function hideNoxSticker() {
      if (!noxSticker) return;
      noxSticker.classList.remove("is-on");
      // Leave it in the DOM (opacity fade) but re-hide after transition
      timer(() => { if (noxSticker) noxSticker.hidden = true; }, 320);
    }
    // ── engine-correct Aurora / Vespera sweep ────────────────────
    // Straight adaptation of Tab 4's playAuroraSweepLocal + playVesperaSweepLocal
    // (which themselves match Tab 3's engine sweep). A diagonal heat
    // front travels across the board: fog cells fill with ▒▒ and warm
    // colour, terrain cells brighten + jitter. Aurora holds the heat;
    // Vespera cools it back to zero. This is the graphic the engine
    // uses at end-of-Nox / start-of-Nox.
    const CELL_BG_RGB = [14, 11, 22];
    function _heatClearAllCells() {
      Array.from(board.children).forEach((c) => {
        c.style.background = "";
        const terr = c.querySelector(".mn-cell-terrain");
        if (terr) { terr.style.filter = ""; terr.style.textShadow = ""; terr.style.transform = ""; }
        const fog = c.querySelector(".mn-cell-fog");
        if (fog) { fog.textContent = CH_LIGHT; fog.style.color = ""; fog.style.opacity = ""; }
        c.classList.remove("mn-cell-dawn-decay");
      });
    }
    function _applyHeat(c, h, wallT, probeIdxSet, onProbePassed, front) {
      const isFog = c.el.classList.contains("is-fogged");
      if (h < 0.015) {
        c.el.style.background = "";
        if (c.terr) { c.terr.style.filter = ""; c.terr.style.textShadow = ""; c.terr.style.transform = ""; }
        if (c.fog)  { c.fog.textContent = CH_LIGHT; c.fog.style.color = ""; }
        return;
      }
      if (isFog && c.fog) {
        c.fog.textContent = "\u2592\u2592";
        const w = Math.round(90 + h * 165);
        c.fog.style.color = `rgb(${w},${w},${w})`;
        const br = Math.round(15 + h * 22);
        const bg = Math.round(12 + h * 14);
        const bb = Math.round(24 + h * 16);
        c.el.style.background = `rgba(${br},${bg},${bb},0.96)`;
        if (c.terr) c.terr.style.filter = "";
      } else if (c.terr) {
        const sat = (1 + h * 1.5).toFixed(2);
        const bri = (1 + h * 0.45).toFixed(2);
        c.terr.style.filter = `saturate(${sat}) brightness(${bri})`;
        const [cr, cg, cb] = CELL_BG_RGB;
        const lr = Math.min(255, Math.round(cr + h * 42));
        const lg = Math.min(255, Math.round(cg + h * 32));
        const lb = Math.min(255, Math.round(cb + h * 24));
        c.el.style.background = `rgb(${lr},${lg},${lb})`;
      }
      if (c.terr) {
        const glowA = Math.max(0, (h - 0.2) / 0.8);
        const blur  = Math.round(3 + glowA * 5);
        const a     = (glowA * 0.7).toFixed(2);
        c.terr.style.textShadow = `0 0 ${blur}px rgba(255,200,80,${a})`;
        if (wallT > 0 && h > 0.15) {
          const t   = wallT * 0.001;
          const amp = 1.8 * Math.min(1, h * 1.6);
          const dx = (Math.sin(c.cx * 0.55 + t * 4.3 + c.cy * 0.31) * amp).toFixed(1);
          const dy = (Math.cos(c.cy * 0.63 + t * 3.8 + c.cx * 0.44) * amp * 0.5).toFixed(1);
          c.terr.style.transform = `translate(${dx}px, ${dy}px)`;
        }
      }
      if (probeIdxSet && probeIdxSet.has(c.idx) && front !== undefined && front - c.d > 0) {
        onProbePassed(c.idx);
      }
    }
    function _cancelHeatRaf() {
      if (state.heatRaf) { cancelAnimationFrame(state.heatRaf); state.heatRaf = null; }
    }
    // Which probe cells (live) should get the "dawn-decay" pulse as
    // the heat front passes over them. In OPPONENTS we let every live
    // probe pulse — they don't actually expire mid-demo, but the pulse
    // reads as "the sun catches the beacon".
    function _liveProbeIdxs() {
      const out = [];
      for (let i = 0; i < total; i++) {
        const cellEl = boardCell(board, i);
        const ent = cellEl.querySelector(".mn-cell-entity");
        if (ent && ent.classList.contains("mn-cell-entity--probe")) out.push(i);
      }
      return out;
    }
    function playAuroraSweepLocal(probeIdxs, onDone) {
      const boardCells = Array.from(board.children);
      const cellData = boardCells.map((el, i) => ({
        el, idx: i,
        terr: el.querySelector(".mn-cell-terrain"),
        fog:  el.querySelector(".mn-cell-fog"),
        cx: i % cols,
        cy: Math.floor(i / cols),
        d:  (i % cols) * 0.85 + Math.floor(i / cols) * 1.15,
      }));
      state.heatCells = cellData;
      let maxD = 0;
      for (const c of cellData) if (c.d > maxD) maxD = c.d;
      const MIN_D = -4, MAX_D = maxD + 6;
      const durIn = 1100, rate = (MAX_D - MIN_D) / durIn, holdDur = 80;
      let front = MIN_D, lastTs = null, holdStart = 0, phase = "in", onDoneFired = false;
      const probeSet = new Set(probeIdxs || []);
      const probeFired = new Set();
      function heatLevel(d, front) {
        const dist = front - d;
        if (dist < -2) return 0;
        if (dist <  2) return Math.max(0, (dist + 2) / 4);
        if (dist <  6) return 1.0 - ((dist - 2) / 4) * 0.48;
        return 0.52;
      }
      function onProbePassed(idx) {
        if (probeFired.has(idx)) return;
        probeFired.add(idx);
        const probeCell = boardCell(board, idx);
        probeCell.classList.add("mn-cell-dawn-decay");
        state.timers.push(setTimeout(() => probeCell.classList.remove("mn-cell-dawn-decay"), 640));
        // Aurora ticks probe life by 1 (§3.11). Fresh probes dropped
        // this Nox sit at 2 rings; after this Aurora sweep they drop
        // to 1 ring (weathered — 2 nights of life left).
        const ent = probeCell.querySelector(".mn-cell-entity");
        if (!ent || !ent.classList.contains("mn-cell-entity--probe")) return;
        // Recover the seat var from the inline colour set by setEntity.
        const col = ent.style.color || "";
        const m   = col.match(/var\((--seat-[^)]+)\)/);
        const seatVar = m ? m[1] : "--seat-p1";
        // Read current ring class → decide new nights value → setProbe.
        const rings2 = ent.classList.contains("mn-cell-entity--probe-life-2");
        const rings1 = ent.classList.contains("mn-cell-entity--probe-life-1");
        const currentNights = (rings2 ? 3 : rings1 ? 2 : 1);
        const newNights = Math.max(1, currentNights - 1);
        setProbe(probeCell, newNights, seatVar);
      }
      function frame(ts) {
        if (state.stopped) return;
        if (lastTs === null) lastTs = ts;
        const dt = Math.min(ts - lastTs, 50); lastTs = ts;
        if (phase === "in") {
          front += rate * dt;
          for (const c of cellData) _applyHeat(c, heatLevel(c.d, front), ts, probeSet, onProbePassed, front);
          if (front >= MAX_D) { phase = "hold"; holdStart = ts; }
        } else {
          for (const c of cellData) _applyHeat(c, 0.52, ts, probeSet, () => {}, front);
          if (!onDoneFired && ts - holdStart >= holdDur) {
            onDoneFired = true;
            state.heatApplied = true;
            if (onDone) try { onDone(); } catch (_) {}
            // Hand off — do NOT schedule another Aurora frame. If we
            // did, Aurora's next rAF would overwrite state.heatRaf
            // (set by the caller inside onDone, typically Vespera),
            // orphaning it and leaving cells pinned at heat 0.52
            // even while Vespera thinks it's cooling.
            return;
          }
        }
        state.heatRaf = requestAnimationFrame(frame);
      }
      state.heatRaf = requestAnimationFrame(frame);
    }
    function playVesperaSweepLocal(onDone) {
      const cellData = state.heatCells || Array.from(board.children).map((el, i) => ({
        el, idx: i,
        terr: el.querySelector(".mn-cell-terrain"),
        fog:  el.querySelector(".mn-cell-fog"),
        cx: i % cols,
        cy: Math.floor(i / cols),
        d:  (i % cols) * 0.85 + Math.floor(i / cols) * 1.15,
      }));
      let maxD = 0;
      for (const c of cellData) if (c.d > maxD) maxD = c.d;
      const MIN_D = -4, MAX_D = maxD + 6;
      const durOut = 900, rate = (MAX_D - MIN_D) / durOut;
      let front = MIN_D, lastTs = null;
      function coolLevel(d, front) {
        const dist = front - d;
        if (dist < -2) return 0.52;
        if (dist <  2) return 0.52 * (1 - (dist + 2) / 4);
        return 0;
      }
      function frame(ts) {
        if (state.stopped) return;
        if (lastTs === null) lastTs = ts;
        const dt = Math.min(ts - lastTs, 50); lastTs = ts;
        front += rate * dt;
        for (const c of cellData) _applyHeat(c, coolLevel(c.d, front), ts, null, () => {}, front);
        if (front < MAX_D) {
          state.heatRaf = requestAnimationFrame(frame);
        } else {
          _heatClearAllCells();
          state.heatApplied = false;
          state.heatCells = null;
          if (onDone) try { onDone(); } catch (_) {}
        }
      }
      state.heatRaf = requestAnimationFrame(frame);
    }

    // Chain Aurora → Vespera between Nox 1 and Nox 2 to show a full
    // day flashing past. Same engine graphic used in Tab 3 · Part 6
    // and Tab 4, but tuned tight — Aurora sweeps the shimmer in, we
    // barely hold it, then Vespera cools it right back out. Total
    // ~2100ms end-to-end reads as "day happens" not "we live here".
    //   AURORA · Nox 1 closes   (heat sweeps in, tiny hold)
    //   VESPERA · Nox 2 opens   (heat cools back out immediately)
    const AURORA_MS  = 1180;   // 1100 in + 80 hold
    const VESPERA_MS = 900;
    const SWEEP_MS   = AURORA_MS + VESPERA_MS;   // ~2080ms total
    function playNoxSweep() {
      if (!noxSweep) return;
      // Show label overlay (heat effect lives on cells, not on the overlay)
      noxSweep.hidden = false;
      noxSweep.classList.remove("is-on");
      noxSweepLabel.classList.remove("is-aurora");
      noxSweepLabel.textContent = "AURORA \u00b7 Nox 1 closes";
      // eslint-disable-next-line no-unused-expressions
      noxSweep.offsetWidth;
      noxSweep.classList.add("is-on");
      playAuroraSweepLocal(_liveProbeIdxs(), () => {
        if (state.stopped) return;
        // Aurora keeps its own rAF alive in "hold" phase — cancel it
        // so Vespera can take over the heatRaf slot cleanly.
        _cancelHeatRaf();
        // Swap label into the Vespera half.
        noxSweepLabel.textContent = "VESPERA \u00b7 Nox 2 opens";
        noxSweepLabel.classList.add("is-aurora");
        playVesperaSweepLocal(() => {
          if (state.stopped) return;
          noxSweep.classList.remove("is-on");
          timer(() => { if (noxSweep) noxSweep.hidden = true; }, 320);
        });
      });
    }

    // ── stage machine ─────────────────────────────────────────────
    const STAGES = [
      // 0 · fog + empty policies
      {
        label: "0 · FOG · POLICIES DRAFTED",
        body:
          '<p>Every Nox, both seats draft a <span class="kw">POLICY</span> — a 21-hour script — in orbit. Once submitted, PRAXIS fires.</p>' +
          '<p>Every hour of PRAXIS, <span class="kw">every seat\'s action fires simultaneously</span>. Nobody reacts to anybody.</p>' +
          '<p>You never see the opponent\'s policy in-game. We show it here so you can watch the sync.</p>',
        cite: "§3.10 · praxis",
        settle() {
          resetBoardOpp();
          policyNox1.textContent = "Nox 1"; policyNox2.textContent = "Nox 1";
          renderPolicy(policyList1, EMPTY_POLICY);
          renderPolicy(policyList2, EMPTY_POLICY);
        },
        animate() {
          this.settle();
          phase.textContent = "# fog · policies blank · nothing has happened yet";
          status.textContent = "# hit NEXT to see Nox 1 policies";
          pushLog("stage", "orbit · both seats about to draft policies", "mn-eventlog-6");
        },
        dur: 4200,
      },

      // 1 · Nox 1 · policies drafted (probes)
      {
        label: "1 · NOX 1 · POLICIES SUBMITTED",
        body:
          '<p>Nox 1. Both seats plan one action: <span class="kw">H01 = PROBE</span>.</p>' +
          '<p>Policies are now <span class="kw">locked</span>. Neither seat has seen the other. PRAXIS is about to begin.</p>',
        cite: "§3.10 · §3.11",
        settle() {
          resetBoardOpp();
          policyNox1.textContent = "Nox 1"; policyNox2.textContent = "Nox 1";
          renderPolicy(policyList1, NOX1_P1);
          renderPolicy(policyList2, NOX1_P2);
        },
        animate() {
          this.settle();
          phase.textContent = "# Nox 1 · both policies locked";
          status.textContent = "# both seats queue a probe · hit NEXT to fire PRAXIS";
          pushLog("stage", `Nox 1 policies · P1 probe(${P1.probe[0]},${P1.probe[1]}) · P2 probe(${P2.probe[0]},${P2.probe[1]})`, "mn-eventlog-6");
        },
        dur: 4200,
      },

      // 2 · Nox 1 PRAXIS fires — both probes launch
      {
        label: "2 · NOX 1 · PRAXIS · H01 FIRES",
        body:
          '<p>H01 fires. Both probes launch <span class="kw">at the same instant</span>. Neither seat sees the other launching.</p>' +
          '<p>Fog opens in both disks — but only the seat who dropped each probe actually sees inside their disk.</p>',
        cite: "§3.11 · probes",
        settle() {
          resetBoardOpp();
          policyNox1.textContent = "Nox 1"; policyNox2.textContent = "Nox 1";
          renderPolicy(policyList1, NOX1_P1);
          renderPolicy(policyList2, NOX1_P2);
          markPolicySlot(policyList1, 1, "done");
          markPolicySlot(policyList2, 1, "done");
          revealDisk(eucDisk(P1.probe[0], P1.probe[1], 4));
          revealDisk(eucDisk(P2.probe[0], P2.probe[1], 4));
          setProbe(boardCell(board, idxAt(P1.probe[0], P1.probe[1])), 3, P1.color);
          setProbe(boardCell(board, idxAt(P2.probe[0], P2.probe[1])), 3, P2.color);
        },
        animate() {
          resetBoardOpp();
          policyNox1.textContent = "Nox 1"; policyNox2.textContent = "Nox 1";
          renderPolicy(policyList1, NOX1_P1);
          renderPolicy(policyList2, NOX1_P2);
          phase.textContent = "# Nox 1 · PRAXIS · H01 fires";
          status.textContent = "# both probes launching · same hour";
          pushLog("stage", "H01 · P1.probe + P2.probe · fire together", "mn-eventlog-6");
          showNoxSticker("NOX 1 · PRAXIS");
          fireHour(1, "probe", "probe");
          const p1Cell = boardCell(board, idxAt(P1.probe[0], P1.probe[1]));
          const p2Cell = boardCell(board, idxAt(P2.probe[0], P2.probe[1]));
          spawnProbeTrail(p1Cell, SEAT_HEX[P1.color], SEAT_HEX[P1.color], () => {
            if (state.stopped) return;
            revealDisk(eucDisk(P1.probe[0], P1.probe[1], 4));
            setProbe(p1Cell, 3, P1.color);
            pushLog("probe", `P1.probe seeded at (${P1.probe[0]},${P1.probe[1]})`, "mn-eventlog-6");
          }, 900, state);
          spawnProbeTrail(p2Cell, SEAT_HEX[P2.color], SEAT_HEX[P2.color], () => {
            if (state.stopped) return;
            revealDisk(eucDisk(P2.probe[0], P2.probe[1], 4));
            setProbe(p2Cell, 3, P2.color);
            pushLog("probe", `P2.probe seeded at (${P2.probe[0]},${P2.probe[1]})`, "mn-eventlog-6");
          }, 900, state);
        },
        dur: 4200,
      },

      // 3 · Nox 2 · policies drafted (drop + walk + pickup)
      {
        label: "3 · NOX 2 · POLICIES SUBMITTED",
        body:
          '<p>Nox 2. Both seats plan a full harvester deployment. <span class="kw">Hold cap = 6</span>, so drop + up to 5 walks.</p>' +
          '<p><span class="kw">YOU</span> drop, walk 4 short steps, pick up at H06. <span class="kw">OPPONENT</span> plans 5 walks westward — the tail will cross into your probe\'s disk. Pickup H07.</p>' +
          '<p>Same clock. Different plans. Neither seat has seen the other\'s.</p>',
        cite: "§3.10 · §3.9 · hold cap",
        settle() {
          // Board carries over Nox 1 state: both probes down + disks
          resetBoardOpp();
          revealDisk(eucDisk(P1.probe[0], P1.probe[1], 4));
          revealDisk(eucDisk(P2.probe[0], P2.probe[1], 4));
          setProbe(boardCell(board, idxAt(P1.probe[0], P1.probe[1])), 3, P1.color);
          setProbe(boardCell(board, idxAt(P2.probe[0], P2.probe[1])), 3, P2.color);
          policyNox1.textContent = "Nox 2"; policyNox2.textContent = "Nox 2";
          renderPolicy(policyList1, NOX2_P1);
          renderPolicy(policyList2, NOX2_P2);
        },
        animate() {
          this.settle();
          phase.textContent = "# Nox 2 · both policies locked · asymmetric plans";
          status.textContent = "# YOUR walk = 4 steps (H02-H05) · OPPONENT walk = 5 steps (H02-H06)";
          pushLog("stage", "Nox 2 policies · P1 drop+walk4+pickup@H06 · P2 drop+walk5+pickup@H07", "mn-eventlog-6");
        },
        dur: 4600,
      },

      // 4 · Nox 2 PRAXIS fires — everything simultaneous
      {
        label: "4 · NOX 2 · PRAXIS · H01 → H07",
        body:
          '<p>PRAXIS. <span class="kw">H01</span> — both harvesters arc down. <span class="kw">H02–H05</span> you walk 4 cells inside your disk. Opponent walks in lockstep — H05\'s step already brushes the edge of <span class="kw">your</span> probe disk.</p>' +
          '<p>A harvester adds its own <span class="kw">plus-shape sensor</span> (self + 4 cardinals) to LIVE while it stands there. Once it moves on, those cells fall to <span class="kw">echo</span> — unless a probe disk still covers them.</p>' +
          '<p>Your pickup lifts at H06. Opponent finishes their walk on <span class="kw">your</span> disk and lifts at H07 — still visible to your probe.</p>',
        cite: "§3.9 · §3.8 · §3.11",
        settle() {
          resetBoardOpp();
          const p1Disk = eucDisk(P1.probe[0], P1.probe[1], 4);
          const p2Disk = eucDisk(P2.probe[0], P2.probe[1], 4);
          const paint  = makeVisionPainter([...p1Disk, ...p2Disk]);
          setProbe(boardCell(board, idxAt(P1.probe[0], P1.probe[1])), 3, P1.color);
          setProbe(boardCell(board, idxAt(P2.probe[0], P2.probe[1])), 3, P2.color);
          policyNox1.textContent = "Nox 2"; policyNox2.textContent = "Nox 2";
          renderPolicy(policyList1, NOX2_P1);
          renderPolicy(policyList2, NOX2_P2);
          // Bake final board state: stamp trails + harvest reds along
          // BOTH walks, and feed every visited cell into the vision
          // painter so cells outside the probe disks end up in ECHO.
          const walkPath = (seat) => {
            let x = seat.nox2.drop[0], y = seat.nox2.drop[1];
            const cellsVisited = [];
            const stamp = (px, py) => {
              const c = boardCell(board, idxAt(px, py));
              const tr = c.querySelector(".mn-cell-trail");
              tr.textContent = CH_LIGHT; tr.classList.add("is-on");
              const b = base[idxAt(px, py)];
              if (b && b.tile === TILE.RED) setTerrain(c, TILE.GREEN, 255);
              cellsVisited.push(idxAt(px, py));
            };
            stamp(x, y);
            for (const s of seat.nox2.steps) {
              const [dx, dy] = DIR[s]; x += dx; y += dy;
              if (!inBounds(x, y)) break;
              stamp(x, y);
            }
            return cellsVisited;
          };
          const p1Trail = walkPath(P1);
          const p2Trail = walkPath(P2);
          // Feed every cell the harvesters (via plus sensor) touched
          // into the painter so it becomes "seen" — hence ECHO if not
          // covered by a probe disk.
          const feed = [];
          p1Trail.forEach(i => {
            const x = i % cols, y = (i / cols) | 0;
            feed.push(plusCells(x, y));
          });
          p2Trail.forEach(i => {
            const x = i % cols, y = (i / cols) | 0;
            feed.push(plusCells(x, y));
          });
          // Paint once with those plus-sets "seen", then again with
          // no harvesters (both picked up) so vision falls back to
          // disks-only + echoes.
          paint(feed);
          paint([]);
          // Mark all fired hours done
          [1, 2, 3, 4, 5, 6].forEach(h => markPolicySlot(policyList1, h, "done"));
          [1, 2, 3, 4, 5, 6, 7].forEach(h => markPolicySlot(policyList2, h, "done"));
        },
        animate() {
          resetBoardOpp();
          const p1Disk = eucDisk(P1.probe[0], P1.probe[1], 4);
          const p2Disk = eucDisk(P2.probe[0], P2.probe[1], 4);
          const paint  = makeVisionPainter([...p1Disk, ...p2Disk]);
          // Initial: probe disks only, no harvesters yet
          paint([]);
          setProbe(boardCell(board, idxAt(P1.probe[0], P1.probe[1])), 3, P1.color);
          setProbe(boardCell(board, idxAt(P2.probe[0], P2.probe[1])), 3, P2.color);
          policyNox1.textContent = "Nox 2"; policyNox2.textContent = "Nox 2";
          renderPolicy(policyList1, NOX2_P1);
          renderPolicy(policyList2, NOX2_P2);
          phase.textContent = "# Nox 2 · PRAXIS · harvester plus adds LIVE, echoes trail behind";
          status.textContent = "# H01 drops together · walks in sync · pickups on different hours";
          pushLog("stage", "Nox 2 PRAXIS begins · H01 → H10 · both seats simultaneous", "mn-eventlog-6");
          showNoxSticker("NOX 2 · PRAXIS");

          const HOUR_MS = 700;
          const p1Pos = { x: P1.nox2.drop[0], y: P1.nox2.drop[1], alive: false };
          const p2Pos = { x: P2.nox2.drop[0], y: P2.nox2.drop[1], alive: false };
          const currentPluses = () => {
            const out = [];
            if (p1Pos.alive) out.push(plusCells(p1Pos.x, p1Pos.y));
            if (p2Pos.alive) out.push(plusCells(p2Pos.x, p2Pos.y));
            return out;
          };

          // H01 — orbital drops
          timer(() => {
            fireHour(1, "drop", "drop");
            [P1, P2].forEach((s) => {
              const [x, y] = s.nox2.drop;
              const dropCell = boardCell(board, idxAt(x, y));
              runOrbitalArcAnimation(board, dropCell, "drop", s.color, GLYPH_HARVESTER, () => {
                if (state.stopped) return;
                const b = base[idxAt(x, y)];
                if (b.tile === TILE.RED) {
                  setTerrain(dropCell, TILE.GREEN, 255);
                  harvestFxLocal(dropCell, "#ff4040");
                }
                setEntity(dropCell, GLYPH_HARVESTER, s.color);
                const tr = dropCell.querySelector(".mn-cell-trail");
                tr.textContent = CH_LIGHT; tr.classList.add("is-on");
                if (s === P1) p1Pos.alive = true; else p2Pos.alive = true;
                paint(currentPluses());
                pushLog("harvest", `H01 · ${s === P1 ? "P1" : "P2"}.drop on (${x},${y})`, "mn-eventlog-6");
              }, state);
            });
          }, 200);

          // Hours 2..7 — walks + pickups.  P1 walks H02..H05, pickup
          // H06.  P2 walks H02..H06, pickup H07 (one hour later).
          const arcMs = 1400;
          for (let h = 2; h <= 7; h++) {
            timer(() => {
              const p1StepIdx = h - 2;
              const p2StepIdx = h - 2;
              const p1Verb = h < 6 ? "step" : (h === 6 ? "pickup" : null);
              const p2Verb = h < 7 ? "step" : "pickup";
              fireHour(h, p1Verb, p2Verb);

              // P1 step
              if (h >= 2 && h <= 5) {
                const s = P1.nox2.steps[p1StepIdx];
                const [dx, dy] = DIR[s];
                const prev = boardCell(board, idxAt(p1Pos.x, p1Pos.y));
                setEntity(prev, "");
                p1Pos.x += dx; p1Pos.y += dy;
                const c = boardCell(board, idxAt(p1Pos.x, p1Pos.y));
                setEntity(c, GLYPH_HARVESTER, P1.color);
                const tr = c.querySelector(".mn-cell-trail");
                tr.textContent = CH_LIGHT; tr.classList.add("is-on");
                const b = base[idxAt(p1Pos.x, p1Pos.y)];
                if (b && b.tile === TILE.RED) { setTerrain(c, TILE.GREEN, 255); harvestFxLocal(c, "#ff4040"); }
                pushLog("harvest", `H${String(h).padStart(2,"0")} · P1 step ${s} → (${p1Pos.x},${p1Pos.y})`, "mn-eventlog-6");
              }
              // P1 pickup
              if (h === 6) {
                const cell = boardCell(board, idxAt(P1.nox2.pickAt[0], P1.nox2.pickAt[1]));
                runOrbitalArcAnimation(board, cell, "pickup", P1.color, GLYPH_HARVESTER, () => {
                  if (state.stopped) return;
                  setEntity(cell, "");
                  p1Pos.alive = false;
                  paint(currentPluses());
                  pushLog("harvest", `H06 · P1.pickup from (${P1.nox2.pickAt[0]},${P1.nox2.pickAt[1]}) — cargo up`, "mn-eventlog-6");
                }, state);
              }
              // P2 step
              if (h >= 2 && h <= 6) {
                const s = P2.nox2.steps[p2StepIdx];
                const [dx, dy] = DIR[s];
                const prev = boardCell(board, idxAt(p2Pos.x, p2Pos.y));
                setEntity(prev, "");
                p2Pos.x += dx; p2Pos.y += dy;
                const c = boardCell(board, idxAt(p2Pos.x, p2Pos.y));
                setEntity(c, GLYPH_HARVESTER, P2.color);
                const tr = c.querySelector(".mn-cell-trail");
                tr.textContent = CH_LIGHT; tr.classList.add("is-on");
                const b = base[idxAt(p2Pos.x, p2Pos.y)];
                if (b && b.tile === TILE.RED) { setTerrain(c, TILE.GREEN, 255); harvestFxLocal(c, "#ff4040"); }
                pushLog("harvest", `H${String(h).padStart(2,"0")} · P2 step ${s} → (${p2Pos.x},${p2Pos.y})`, "mn-eventlog-6");
              }
              // P2 pickup
              if (h === 7) {
                const cell = boardCell(board, idxAt(P2.nox2.pickAt[0], P2.nox2.pickAt[1]));
                runOrbitalArcAnimation(board, cell, "pickup", P2.color, GLYPH_HARVESTER, () => {
                  if (state.stopped) return;
                  setEntity(cell, "");
                  p2Pos.alive = false;
                  paint(currentPluses());
                  pushLog("harvest", `H07 · P2.pickup from (${P2.nox2.pickAt[0]},${P2.nox2.pickAt[1]}) — cargo up`, "mn-eventlog-6");
                }, state);
              }
              // Repaint vision after every step so the harvester plus
              // shows as LIVE and cells left behind fall to ECHO.
              paint(currentPluses());
            }, 200 + arcMs + (h - 1) * HOUR_MS);
          }
        },
        dur: 9500,
      },

      // 5 · Replay everything from P1's view
      {
        label: "5 · P1 VIEW · REPLAY",
        body:
          '<p>Same two Nox, replayed from your seat only. <span class="kw">Only probes</span> are truly universal — you see them as entities anywhere they land.</p>' +
          '<p>Everything else is <span class="kw">vision-gated</span>: harvester drops, walks, trails, pickups — you only see them on cells your own probe disk or your own harvester\'s plus sensor covers. Rival activity in the fog is silent.</p>' +
          '<p>The opponent\'s policy is <span class="kw">redacted</span>. In-game you never see it.</p>',
        cite: "§3.8 · §3.11 · §3.12",
        settle() {
          resetBoardOpp();
          const p1Disk = eucDisk(P1.probe[0], P1.probe[1], 4);
          const p1DiskSet = new Set(p1Disk);
          const paint = makeVisionPainter(p1Disk);
          // Both probes always visible as entities
          setProbe(boardCell(board, idxAt(P1.probe[0], P1.probe[1])), 3, P1.color);
          setProbe(boardCell(board, idxAt(P2.probe[0], P2.probe[1])), 3, P2.color);
          policyNox1.textContent = "Nox 2"; policyNox2.textContent = "?????";
          renderPolicy(policyList1, NOX2_P1);
          renderRedactedPolicy(policyList2);
          document.querySelector('.mn-opp-policy[data-seat="p2"]').classList.add("is-redacted");
          // Bake P1 walk — everything visible (all in P1 disk)
          const stampVisible = (px, py) => {
            const c = boardCell(board, idxAt(px, py));
            const tr = c.querySelector(".mn-cell-trail");
            tr.textContent = CH_LIGHT; tr.classList.add("is-on");
            const b = base[idxAt(px, py)];
            if (b && b.tile === TILE.RED) setTerrain(c, TILE.GREEN, 255);
          };
          let x = P1.nox2.drop[0], y = P1.nox2.drop[1];
          stampVisible(x, y);
          for (const s of P1.nox2.steps) {
            const [dx, dy] = DIR[s]; x += dx; y += dy;
            stampVisible(x, y);
          }
          // Bake P2 walk — trail + terrain only render on cells P1 can see.
          // The rest is invisible to P1 (fog).
          x = P2.nox2.drop[0]; y = P2.nox2.drop[1];
          if (p1DiskSet.has(idxAt(x, y))) stampVisible(x, y);
          for (const s of P2.nox2.steps) {
            const [dx, dy] = DIR[s]; x += dx; y += dy;
            if (p1DiskSet.has(idxAt(x, y))) stampVisible(x, y);
          }
          paint([]);
          [1, 2, 3, 4, 5, 6].forEach(h => markPolicySlot(policyList1, h, "done"));
        },
        animate() {
          resetBoardOpp();
          const p1Disk = eucDisk(P1.probe[0], P1.probe[1], 4);
          const p1DiskSet = new Set(p1Disk);
          const paint = makeVisionPainter(p1Disk);
          policyNox1.textContent = "Nox 1"; policyNox2.textContent = "?????";
          renderPolicy(policyList1, NOX1_P1);
          renderRedactedPolicy(policyList2);
          document.querySelector('.mn-opp-policy[data-seat="p2"]').classList.add("is-redacted");
          paint([]);
          phase.textContent = "# P1 view · Nox 1 begins";
          status.textContent = "# probes are the only universal signal — you see both landings";
          pushLog("stage", "P1 view · Nox 1 · H01 · probe landings visible (probes broadcast)", "mn-eventlog-6");
          showNoxSticker("NOX 1 · PRAXIS");

          // From-P1 vision helpers
          const p1Pos = { x: P1.nox2.drop[0], y: P1.nox2.drop[1], alive: false };
          const p2Pos = { x: P2.nox2.drop[0], y: P2.nox2.drop[1], alive: false };
          const p1SeesCell = (x, y) => {
            if (p1DiskSet.has(idxAt(x, y))) return true;
            if (p1Pos.alive) {
              if (Math.abs(p1Pos.x - x) + Math.abs(p1Pos.y - y) <= 1) return true;
            }
            return false;
          };
          const currentPluses = () => {
            const out = [];
            if (p1Pos.alive) out.push(plusCells(p1Pos.x, p1Pos.y));
            // NB: P2's plus does NOT contribute to P1's vision
            return out;
          };

          // Nox 1: both probes orbital-fire simultaneously
          timer(() => {
            fireHour(1, "probe", null); // P2 is redacted — don't mark
            const p1Cell = boardCell(board, idxAt(P1.probe[0], P1.probe[1]));
            const p2Cell = boardCell(board, idxAt(P2.probe[0], P2.probe[1]));
            spawnProbeTrail(p1Cell, SEAT_HEX[P1.color], SEAT_HEX[P1.color], () => {
              if (state.stopped) return;
              paint([]); // P1 disk lights up (LIVE)
              setProbe(p1Cell, 3, P1.color);
              pushLog("probe", "P1 probe landed — your disk goes LIVE", "mn-eventlog-6");
            }, 900, state);
            spawnProbeTrail(p2Cell, SEAT_HEX[P2.color], SEAT_HEX[P2.color], () => {
              if (state.stopped) return;
              // P2 probe visible as entity (universal) but disk stays fogged
              setProbe(p2Cell, 3, P2.color);
              pushLog("probe", "P2 probe landed — visible as entity (broadcast) · their disk stays hidden", "mn-eventlog-6");
            }, 900, state);
          }, 200);

          // Nox 2 begins — but first, the Vespera→Aurora sweep to
          // signal that time passes between the two Noxes.
          const NOX1_END = 3800;
          timer(() => { playNoxSweep(); }, NOX1_END);
          timer(() => {
            renderPolicy(policyList1, NOX2_P1);
            renderRedactedPolicy(policyList2);
            policyNox1.textContent = "Nox 2"; policyNox2.textContent = "?????";
            phase.textContent = "# P1 view · Nox 2 · your harvester arcs down · opponent's doesn't";
            status.textContent = "# your drop is visible · rival drops off-vision · you'll never see it fall";
            pushLog("stage", "P1 view · Nox 2 · your drop arc visible · rival lands off-disk (silent)", "mn-eventlog-6");
            showNoxSticker("NOX 2 · PRAXIS");
          }, NOX1_END + SWEEP_MS);

          // H01 — orbital drops.  P1 arcs down inside their own disk
          // (visible).  P2 arcs down at (15,5) which is OUTSIDE P1's
          // vision — skip P2's arc entirely; from P1's POV, they just
          // know rival launched something (any activity in fog is
          // silent).  No trail, no entity, no landing effect.
          const H01_MS = NOX1_END + SWEEP_MS + 400;
          timer(() => {
            fireHour(1, "drop", null);
            const [px, py] = P1.nox2.drop;
            const p1DropCell = boardCell(board, idxAt(px, py));
            runOrbitalArcAnimation(board, p1DropCell, "drop", P1.color, GLYPH_HARVESTER, () => {
              if (state.stopped) return;
              setEntity(p1DropCell, GLYPH_HARVESTER, P1.color);
              const b = base[idxAt(px, py)];
              if (b.tile === TILE.RED) { setTerrain(p1DropCell, TILE.GREEN, 255); harvestFxLocal(p1DropCell, "#ff4040"); }
              const tr = p1DropCell.querySelector(".mn-cell-trail");
              tr.textContent = CH_LIGHT; tr.classList.add("is-on");
              p1Pos.alive = true;
              paint(currentPluses());
              pushLog("harvest", `H01 · P1 harvester lands at (${px},${py}) — inside your disk`, "mn-eventlog-6");
            }, state);
            // P2 drop happens simultaneously but off-vision — track
            // position, log the fact that something happened.
            p2Pos.alive = true;
            pushLog("cover", "H01 · rival did something in the fog — you can't see where", "mn-eventlog-6");
          }, H01_MS);

          // H02..H07 — walks + pickups
          const arcMs = 1400;
          const WALK_START = H01_MS + arcMs;
          const HOUR_MS = 700;
          for (let h = 2; h <= 7; h++) {
            timer(() => {
              const p1Verb = h < 6 ? "step" : (h === 6 ? "pickup" : null);
              fireHour(h, p1Verb, null); // never mark P2 — its policy is redacted

              // P1 step — always visible (always inside your disk)
              if (h >= 2 && h <= 5) {
                const s = P1.nox2.steps[h - 2];
                const [dx, dy] = DIR[s];
                const prev = boardCell(board, idxAt(p1Pos.x, p1Pos.y));
                setEntity(prev, "");
                p1Pos.x += dx; p1Pos.y += dy;
                const c = boardCell(board, idxAt(p1Pos.x, p1Pos.y));
                setEntity(c, GLYPH_HARVESTER, P1.color);
                const tr = c.querySelector(".mn-cell-trail");
                tr.textContent = CH_LIGHT; tr.classList.add("is-on");
                const b = base[idxAt(p1Pos.x, p1Pos.y)];
                if (b && b.tile === TILE.RED) { setTerrain(c, TILE.GREEN, 255); harvestFxLocal(c, "#ff4040"); }
                pushLog("harvest", `H${String(h).padStart(2,"0")} · P1 step ${s} → (${p1Pos.x},${p1Pos.y})`, "mn-eventlog-6");
              }
              // P1 pickup — always visible
              if (h === 6) {
                const cell = boardCell(board, idxAt(P1.nox2.pickAt[0], P1.nox2.pickAt[1]));
                runOrbitalArcAnimation(board, cell, "pickup", P1.color, GLYPH_HARVESTER, () => {
                  if (state.stopped) return;
                  setEntity(cell, "");
                  p1Pos.alive = false;
                  paint(currentPluses());
                  pushLog("harvest", "H06 · P1 pickup — cargo up", "mn-eventlog-6");
                }, state);
              }
              // P2 step — track silently; only render/harvest/trail on
              // cells P1 can actually see. Everything outside vision
              // stays invisible (the harvester might as well not exist
              // for you until it enters your disk).
              if (h >= 2 && h <= 6) {
                const s = P2.nox2.steps[h - 2];
                const [dx, dy] = DIR[s];
                // Clear entity from previous cell only if we had rendered
                // one there (i.e. P1 could see the previous position)
                const prevWasVisible = p1SeesCell(p2Pos.x, p2Pos.y);
                if (prevWasVisible) {
                  const prevCell = boardCell(board, idxAt(p2Pos.x, p2Pos.y));
                  setEntity(prevCell, "");
                  // If P2 walked off P2-probe cell, restore probe glyph
                  if (p2Pos.x === P2.probe[0] && p2Pos.y === P2.probe[1]) {
                    setProbe(prevCell, 3, P2.color);
                  }
                }
                p2Pos.x += dx; p2Pos.y += dy;
                if (p1SeesCell(p2Pos.x, p2Pos.y)) {
                  const c = boardCell(board, idxAt(p2Pos.x, p2Pos.y));
                  setEntity(c, GLYPH_HARVESTER, P2.color);
                  const tr = c.querySelector(".mn-cell-trail");
                  tr.textContent = CH_LIGHT; tr.classList.add("is-on");
                  const b = base[idxAt(p2Pos.x, p2Pos.y)];
                  if (b && b.tile === TILE.RED) { setTerrain(c, TILE.GREEN, 255); harvestFxLocal(c, "#ff4040"); }
                  pushLog("cover", `H${String(h).padStart(2,"0")} · P2 harvester enters your disk at (${p2Pos.x},${p2Pos.y})`, "mn-eventlog-6");
                }
                // Fog cells: no trail, no entity, no harvest. You have
                // no idea what happened there — that's the point.
              }
              // P2 pickup — the pickup cell (10,5) IS inside your disk,
              // so you see the orbital arc lift from a visible cell.
              if (h === 7) {
                const cell = boardCell(board, idxAt(P2.nox2.pickAt[0], P2.nox2.pickAt[1]));
                runOrbitalArcAnimation(board, cell, "pickup", P2.color, GLYPH_HARVESTER, () => {
                  if (state.stopped) return;
                  setEntity(cell, "");
                  p2Pos.alive = false;
                  paint(currentPluses());
                  pushLog("harvest", "H07 · P2 pickup — orbital arc visible (they lifted from inside your disk)", "mn-eventlog-6");
                }, state);
              }
              paint(currentPluses());
            }, WALK_START + (h - 1) * HOUR_MS);
          }
        },
        dur: 17800,
      },

      // 6 · Four seats, GOD'S EYE — all policies visible, all activity
      // visible (nothing vision-gated), but the board still starts
      // fogged and cells are revealed as probes land + harvesters walk.
      {
        label: "6 · 4 SEATS · GOD'S EYE",
        body:
          '<p>Sea of Colours hosts up to <span class="kw">4 seats</span> per game. Same rules — simultaneous PRAXIS, universal probes, vision-gated everything else.</p>' +
          '<p>Nox 1: six probes fire — P1 and P3 each drop two, P2 and P4 drop one. Nox 2: all four seats deploy harvesters. All 4 policies are shown side-by-side because this is god\'s-eye — nothing hidden, but the map still starts <span class="kw">fogged</span> and reveals as probes land.</p>',
        cite: "§3.10 · max seats",
        settle() {
          resetBoardOpp();  // fully fogged
          // Reveal every probe's disk
          for (const p of FOUR_PROBES) {
            eucDisk(p.at[0], p.at[1], 4).forEach((i) => {
              const c = boardCell(board, i);
              setFog(c, false);
              c.classList.add("is-live");
            });
            setProbe(boardCell(board, idxAt(p.at[0], p.at[1])), 3, p.seat.color);
          }
          // Bake harvester walks — every stepped cell is revealed too
          for (const h of FOUR_HARVESTERS) {
            let x = h.drop[0], y = h.drop[1];
            const stamp = (px, py) => {
              const c = boardCell(board, idxAt(px, py));
              setFog(c, false);
              const tr = c.querySelector(".mn-cell-trail");
              tr.textContent = CH_LIGHT; tr.classList.add("is-on");
              const b = base[idxAt(px, py)];
              if (b && b.tile === TILE.RED) setTerrain(c, TILE.GREEN, 255);
            };
            stamp(x, y);
            for (const s of h.steps) { const [dx, dy] = DIR[s]; x += dx; y += dy; if (inBounds(x, y)) stamp(x, y); }
          }
          [policyNox1, policyNox2, policyNox3, policyNox4].forEach(el => el.textContent = "Nox 2");
          renderPolicy(policyList1, NOX2_4P.P1);
          renderPolicy(policyList2, NOX2_4P.P2);
          renderPolicy(policyList3, NOX2_4P.P3);
          renderPolicy(policyList4, NOX2_4P.P4);
        },
        animate() {
          resetBoardOpp();  // fully fogged, no reveal yet
          [policyNox1, policyNox2, policyNox3, policyNox4].forEach(el => el.textContent = "Nox 1");
          renderPolicy(policyList1, NOX1_4P.P1);
          renderPolicy(policyList2, NOX1_4P.P2);
          renderPolicy(policyList3, NOX1_4P.P3);
          renderPolicy(policyList4, NOX1_4P.P4);
          phase.textContent = "# 4 seats · god's-eye · policies visible · map fogged until probes land";
          status.textContent = "# Nox 1 · six probes fire (H01 four probes, H02 two more)";
          pushLog("stage", "4-seat scenario · god's-eye · Nox 1 begins · board fogged", "mn-eventlog-6");
          showNoxSticker("NOX 1 · PRAXIS");

          // Helper: reveal a probe's disk when it lands
          function revealProbeDisk(px, py) {
            eucDisk(px, py, 4).forEach((i) => {
              const c = boardCell(board, i);
              setFog(c, false);
              c.classList.add("is-live");
            });
          }

          // H01 — 4 probes fire simultaneously (P1, P2, P3, P4 each drop one)
          timer(() => {
            fireHourAll(1, { P1: "probe", P2: "probe", P3: "probe", P4: "probe" });
            FOUR_PROBES.filter(p => p.hour === 1).forEach((p) => {
              const cell = boardCell(board, idxAt(p.at[0], p.at[1]));
              spawnProbeTrail(cell, SEAT_HEX[p.seat.color], SEAT_HEX[p.seat.color], () => {
                if (state.stopped) return;
                revealProbeDisk(p.at[0], p.at[1]);
                setProbe(cell, 3, p.seat.color);
                pushLog("probe", `${p.seat.label} probe at (${p.at[0]},${p.at[1]}) — disk revealed`, "mn-eventlog-6");
              }, 900, state);
            });
          }, 200);
          // H02 — 2 more (P1 second, P3 second)
          timer(() => {
            fireHourAll(2, { P1: "probe", P2: null, P3: "probe", P4: null });
            FOUR_PROBES.filter(p => p.hour === 2).forEach((p) => {
              const cell = boardCell(board, idxAt(p.at[0], p.at[1]));
              spawnProbeTrail(cell, SEAT_HEX[p.seat.color], SEAT_HEX[p.seat.color], () => {
                if (state.stopped) return;
                revealProbeDisk(p.at[0], p.at[1]);
                setProbe(cell, 3, p.seat.color);
                pushLog("probe", `${p.seat.label} 2nd probe at (${p.at[0]},${p.at[1]}) — disk revealed`, "mn-eventlog-6");
              }, 900, state);
            });
          }, 2600);
          // Nox 2 handoff — with sweep to signal Nox turnover.
          const NOX2_START = 4800;
          timer(() => { playNoxSweep(); }, NOX2_START);
          timer(() => {
            renderPolicy(policyList1, NOX2_4P.P1);
            renderPolicy(policyList2, NOX2_4P.P2);
            renderPolicy(policyList3, NOX2_4P.P3);
            renderPolicy(policyList4, NOX2_4P.P4);
            [policyNox1, policyNox2, policyNox3, policyNox4].forEach(el => el.textContent = "Nox 2");
            phase.textContent = "# 4 seats · Nox 2 · harvesters deploy · walks reveal cells they cross";
            status.textContent = "# 4 harvester drops fire at H01 · offset from each seat's probe";
            pushLog("stage", "4-seat · Nox 2 · 4 harvesters arc down together", "mn-eventlog-6");
            showNoxSticker("NOX 2 · PRAXIS");
          }, NOX2_START + SWEEP_MS);
          // H01 — 4 harvester drops (drop cell revealed on landing)
          timer(() => {
            fireHourAll(1, { P1: "drop", P2: "drop", P3: "drop", P4: "drop" });
            for (const h of FOUR_HARVESTERS) {
              const dropCell = boardCell(board, idxAt(h.drop[0], h.drop[1]));
              runOrbitalArcAnimation(board, dropCell, "drop", h.seat.color, GLYPH_HARVESTER, () => {
                if (state.stopped) return;
                setFog(dropCell, false);  // reveal the drop cell too
                setEntity(dropCell, GLYPH_HARVESTER, h.seat.color);
                const b = base[idxAt(h.drop[0], h.drop[1])];
                if (b && b.tile === TILE.RED) { setTerrain(dropCell, TILE.GREEN, 255); harvestFxLocal(dropCell, "#ff4040"); }
                const tr = dropCell.querySelector(".mn-cell-trail");
                tr.textContent = CH_LIGHT; tr.classList.add("is-on");
                pushLog("harvest", `H01 · ${h.seat.label} drops at (${h.drop[0]},${h.drop[1]})`, "mn-eventlog-6");
              }, state);
            }
          }, NOX2_START + SWEEP_MS + 400);
          // H02..MAX — walks + pickups (each stepped cell is revealed)
          const positions = FOUR_HARVESTERS.map(h => ({ h, x: h.drop[0], y: h.drop[1] }));
          const HOUR_MS = 700;
          const WALK_START = NOX2_START + SWEEP_MS + 400 + 1400;
          const MAX_H = Math.max(...FOUR_HARVESTERS.map(h => h.pickHour));
          for (let hour = 2; hour <= MAX_H; hour++) {
            timer(() => {
              const verbs = {};
              for (const h of FOUR_HARVESTERS) {
                if (hour < h.pickHour) verbs[h.seat.label] = "step";
                else if (hour === h.pickHour) verbs[h.seat.label] = "pickup";
                else verbs[h.seat.label] = null;
              }
              fireHourAll(hour, verbs);
              for (const pos of positions) {
                const h = pos.h;
                const stepIdx = hour - 2;
                if (stepIdx < h.steps.length && hour < h.pickHour) {
                  const s = h.steps[stepIdx];
                  const [dx, dy] = DIR[s];
                  const prev = boardCell(board, idxAt(pos.x, pos.y));
                  setEntity(prev, "");
                  pos.x += dx; pos.y += dy;
                  const c = boardCell(board, idxAt(pos.x, pos.y));
                  setFog(c, false);  // reveal walked cell
                  setEntity(c, GLYPH_HARVESTER, h.seat.color);
                  const tr = c.querySelector(".mn-cell-trail");
                  tr.textContent = CH_LIGHT; tr.classList.add("is-on");
                  const b = base[idxAt(pos.x, pos.y)];
                  if (b && b.tile === TILE.RED) { setTerrain(c, TILE.GREEN, 255); harvestFxLocal(c, "#ff4040"); }
                } else if (hour === h.pickHour) {
                  const cell = boardCell(board, idxAt(h.pickAt[0], h.pickAt[1]));
                  runOrbitalArcAnimation(board, cell, "pickup", h.seat.color, GLYPH_HARVESTER, () => {
                    if (state.stopped) return;
                    setEntity(cell, "");
                    pushLog("harvest", `H${String(hour).padStart(2,"0")} · ${h.seat.label} pickup — cargo up`, "mn-eventlog-6");
                  }, state);
                }
              }
            }, WALK_START + (hour - 2) * HOUR_MS);
          }
        },
        dur: 16300,
      },

      // 7 · Four seats, P1 VIEW — start fully fogged, only reveal each
      // P1 disk when its probe actually lands. All other rival policies
      // stay redacted (individually) in the 4-panel row.
      {
        label: "7 · 4 SEATS · P1 VIEW",
        body:
          '<p>Same game, your seat only. <span class="kw">Nothing</span> is revealed at start — your board is all fog until a probe lands.</p>' +
          '<p>Six probe orbitals visible (universal). Your two disks light up as they land. Rival probes show as entities on their cells; their disks stay dark. Rival harvesters are ghosts in the fog — you only see them when they walk into <span class="kw">your</span> vision.</p>' +
          '<p>Reading trails in your disk, entities that appear, and exit orbitals is <span class="kw">the whole game</span>. In this run, P2 and P3 cross into your vision; P4 stays entirely hidden.</p>',
        cite: "§3.8 · §3.11 · §3.10",
        settle() {
          resetBoardOpp();  // fully fogged
          // Reveal both P1 disks (end state)
          const p1DiskA = eucDisk(FOUR_PROBES[0].at[0], FOUR_PROBES[0].at[1], 4);
          const p1DiskB = eucDisk(FOUR_PROBES[4].at[0], FOUR_PROBES[4].at[1], 4);
          const revealed = new Set([...p1DiskA, ...p1DiskB]);
          revealed.forEach((i) => {
            const c = boardCell(board, i);
            setFog(c, false); c.classList.add("is-live");
          });
          for (const p of FOUR_PROBES) {
            setProbe(boardCell(board, idxAt(p.at[0], p.at[1])), 3, p.seat.color);
          }
          [policyNox1, policyNox2, policyNox3, policyNox4].forEach(el => el.textContent = "Nox 2");
          renderPolicy(policyList1, NOX2_4P.P1);
          renderRedactedPolicy(policyList2);
          renderRedactedPolicy(policyList3);
          renderRedactedPolicy(policyList4);
          policyPanel2.classList.add("is-redacted");
          policyPanel3.classList.add("is-redacted");
          policyPanel4.classList.add("is-redacted");
          // Bake harvest cells P1 can see (own walk + rival walks that
          // entered P1's disks)
          const stampVisible = (px, py) => {
            const c = boardCell(board, idxAt(px, py));
            const tr = c.querySelector(".mn-cell-trail");
            tr.textContent = CH_LIGHT; tr.classList.add("is-on");
            const b = base[idxAt(px, py)];
            if (b && b.tile === TILE.RED) setTerrain(c, TILE.GREEN, 255);
          };
          for (const h of FOUR_HARVESTERS) {
            let x = h.drop[0], y = h.drop[1];
            if (revealed.has(idxAt(x, y))) stampVisible(x, y);
            for (const s of h.steps) {
              const [dx, dy] = DIR[s]; x += dx; y += dy;
              if (inBounds(x, y) && revealed.has(idxAt(x, y))) stampVisible(x, y);
            }
          }
          [1, 2, 3, 4, 5, 6].forEach(h => markPolicySlot(policyList1, h, "done"));
        },
        animate() {
          resetBoardOpp();  // fully fogged, no disks visible
          [policyNox1, policyNox2, policyNox3, policyNox4].forEach(el => el.textContent = "Nox 1");
          renderPolicy(policyList1, NOX1_4P.P1);
          renderRedactedPolicy(policyList2);
          renderRedactedPolicy(policyList3);
          renderRedactedPolicy(policyList4);
          policyPanel2.classList.add("is-redacted");
          policyPanel3.classList.add("is-redacted");
          policyPanel4.classList.add("is-redacted");
          phase.textContent = "# 4 seats · your view · everything fogged · waiting for probes";
          status.textContent = "# Nox 1 begins — you see probes land, nothing else";
          pushLog("stage", "4-seat · P1 view · nothing revealed yet", "mn-eventlog-6");
          showNoxSticker("NOX 1 · PRAXIS");

          // Dynamic vision — grows only as P1 probes land.  Rival
          // harvesters and terrain outside this set stay invisible.
          const revealedP1Disks = new Set();
          const seenEver = new Set();
          const p1Pos = { alive: false, x: 0, y: 0 };
          const p1SeesCell = (x, y) => {
            if (revealedP1Disks.has(idxAt(x, y))) return true;
            if (p1Pos.alive && Math.abs(p1Pos.x - x) + Math.abs(p1Pos.y - y) <= 1) return true;
            return false;
          };
          function paintNow() {
            const liveNow = new Set(revealedP1Disks);
            if (p1Pos.alive) plusCells(p1Pos.x, p1Pos.y).forEach(i => liveNow.add(i));
            liveNow.forEach(i => seenEver.add(i));
            for (let i = 0; i < total; i++) {
              const c = boardCell(board, i);
              if (liveNow.has(i)) {
                setFog(c, false);
                c.classList.remove("is-echo");
                c.classList.add("is-live");
              } else if (seenEver.has(i)) {
                setFog(c, false);
                c.classList.remove("is-live");
                c.classList.add("is-echo");
              }
            }
          }

          // Nox 1 H01 — 4 probes land simultaneously. Only P1's own
          // probe reveals its disk; rival probes are entities only.
          timer(() => {
            fireHourAll(1, { P1: "probe", P2: null, P3: null, P4: null });
            FOUR_PROBES.filter(p => p.hour === 1).forEach((p) => {
              const cell = boardCell(board, idxAt(p.at[0], p.at[1]));
              spawnProbeTrail(cell, SEAT_HEX[p.seat.color], SEAT_HEX[p.seat.color], () => {
                if (state.stopped) return;
                setProbe(cell, 3, p.seat.color);
                if (p.seat === P1_S) {
                  // Reveal P1's first disk NOW (not before)
                  eucDisk(p.at[0], p.at[1], 4).forEach(i => revealedP1Disks.add(i));
                  paintNow();
                  pushLog("probe", `your probe A landed at (${p.at[0]},${p.at[1]}) — first disk goes LIVE`, "mn-eventlog-6");
                } else {
                  pushLog("probe", `${p.seat.label} probe visible as entity (universal broadcast) · their disk hidden`, "mn-eventlog-6");
                }
              }, 900, state);
            });
          }, 200);
          // Nox 1 H02 — P1's 2nd probe + P3's 2nd probe fire
          timer(() => {
            fireHourAll(2, { P1: "probe", P2: null, P3: null, P4: null });
            FOUR_PROBES.filter(p => p.hour === 2).forEach((p) => {
              const cell = boardCell(board, idxAt(p.at[0], p.at[1]));
              spawnProbeTrail(cell, SEAT_HEX[p.seat.color], SEAT_HEX[p.seat.color], () => {
                if (state.stopped) return;
                setProbe(cell, 3, p.seat.color);
                if (p.seat === P1_S) {
                  eucDisk(p.at[0], p.at[1], 4).forEach(i => revealedP1Disks.add(i));
                  paintNow();
                  pushLog("probe", `your probe B landed at (${p.at[0]},${p.at[1]}) — second disk goes LIVE`, "mn-eventlog-6");
                } else {
                  pushLog("probe", `${p.seat.label} 2nd probe visible as entity`, "mn-eventlog-6");
                }
              }, 900, state);
            });
          }, 2600);

          // Nox 2 handoff — sweep first, then swap panels
          const NOX2_START = 4800;
          timer(() => { playNoxSweep(); }, NOX2_START);
          timer(() => {
            renderPolicy(policyList1, NOX2_4P.P1);
            renderRedactedPolicy(policyList2);
            renderRedactedPolicy(policyList3);
            renderRedactedPolicy(policyList4);
            [policyNox1, policyNox2, policyNox3, policyNox4].forEach(el => el.textContent = "Nox 2");
            phase.textContent = "# 4 seats · P1 view · Nox 2 · watch your disks";
            status.textContent = "# your drop is visible · other 3 land off-vision (silent)";
            pushLog("stage", "4-seat · Nox 2 · your drop visible · rivals silent until they cross your disks", "mn-eventlog-6");
            showNoxSticker("NOX 2 · PRAXIS");
          }, NOX2_START + SWEEP_MS);
          // H01 — only your drop visible
          timer(() => {
            fireHourAll(1, { P1: "drop", P2: null, P3: null, P4: null });
            for (const h of FOUR_HARVESTERS) {
              if (h.seat === P1_S) {
                const dropCell = boardCell(board, idxAt(h.drop[0], h.drop[1]));
                runOrbitalArcAnimation(board, dropCell, "drop", h.seat.color, GLYPH_HARVESTER, () => {
                  if (state.stopped) return;
                  setEntity(dropCell, GLYPH_HARVESTER, h.seat.color);
                  const b = base[idxAt(h.drop[0], h.drop[1])];
                  if (b && b.tile === TILE.RED) { setTerrain(dropCell, TILE.GREEN, 255); harvestFxLocal(dropCell, "#ff4040"); }
                  const tr = dropCell.querySelector(".mn-cell-trail");
                  tr.textContent = CH_LIGHT; tr.classList.add("is-on");
                  p1Pos.alive = true; p1Pos.x = h.drop[0]; p1Pos.y = h.drop[1];
                  paintNow();
                  pushLog("harvest", "H01 · your harvester lands (inside your disk)", "mn-eventlog-6");
                }, state);
              } else {
                pushLog("cover", `H01 · ${h.seat.label} did something off-vision`, "mn-eventlog-6");
              }
            }
          }, NOX2_START + SWEEP_MS + 400);
          // H02..MAX — walks + pickups
          const positions = FOUR_HARVESTERS.map(h => ({ h, x: h.drop[0], y: h.drop[1] }));
          const HOUR_MS = 700;
          const WALK_START = NOX2_START + SWEEP_MS + 400 + 1400;
          const MAX_H = Math.max(...FOUR_HARVESTERS.map(h => h.pickHour));
          for (let hour = 2; hour <= MAX_H; hour++) {
            timer(() => {
              // Only mark P1's row; rivals stay redacted
              const p1Verb = hour < FOUR_HARVESTERS[0].pickHour ? "step"
                          : hour === FOUR_HARVESTERS[0].pickHour ? "pickup" : null;
              fireHourAll(hour, { P1: p1Verb, P2: null, P3: null, P4: null });
              for (const pos of positions) {
                const h = pos.h;
                const stepIdx = hour - 2;
                const isP1 = h.seat === P1_S;
                if (stepIdx < h.steps.length && hour < h.pickHour) {
                  // Clear previous entity if we had rendered it
                  const wasVisiblePrev = isP1 || p1SeesCell(pos.x, pos.y);
                  if (wasVisiblePrev) {
                    const prev = boardCell(board, idxAt(pos.x, pos.y));
                    setEntity(prev, "");
                    // Restore probe glyph if we stepped off it
                    const probeAtPrev = FOUR_PROBES.find(p => p.at[0] === pos.x && p.at[1] === pos.y);
                    if (probeAtPrev) setProbe(prev, 3, probeAtPrev.seat.color);
                  }
                  const s = h.steps[stepIdx];
                  const [dx, dy] = DIR[s];
                  pos.x += dx; pos.y += dy;
                  if (isP1) { p1Pos.x = pos.x; p1Pos.y = pos.y; }
                  if (isP1 || p1SeesCell(pos.x, pos.y)) {
                    const c = boardCell(board, idxAt(pos.x, pos.y));
                    setEntity(c, GLYPH_HARVESTER, h.seat.color);
                    const tr = c.querySelector(".mn-cell-trail");
                    tr.textContent = CH_LIGHT; tr.classList.add("is-on");
                    const b = base[idxAt(pos.x, pos.y)];
                    if (b && b.tile === TILE.RED) { setTerrain(c, TILE.GREEN, 255); harvestFxLocal(c, "#ff4040"); }
                    if (!isP1) pushLog("cover", `H${String(hour).padStart(2,"0")} · ${h.seat.label} enters your vision at (${pos.x},${pos.y})`, "mn-eventlog-6");
                  }
                } else if (hour === h.pickHour) {
                  const inVision = isP1 || p1SeesCell(h.pickAt[0], h.pickAt[1]);
                  if (inVision) {
                    const cell = boardCell(board, idxAt(h.pickAt[0], h.pickAt[1]));
                    runOrbitalArcAnimation(board, cell, "pickup", h.seat.color, GLYPH_HARVESTER, () => {
                      if (state.stopped) return;
                      setEntity(cell, "");
                      if (isP1) { p1Pos.alive = false; paintNow(); }
                      pushLog("harvest", `H${String(hour).padStart(2,"0")} · ${h.seat.label} pickup — cargo up (visible)`, "mn-eventlog-6");
                    }, state);
                  } else {
                    pushLog("cover", `H${String(hour).padStart(2,"0")} · ${h.seat.label} lifted off-vision — unknown`, "mn-eventlog-6");
                  }
                }
              }
              paintNow();
            }, WALK_START + (hour - 2) * HOUR_MS);
          }
        },
        dur: 16300,
      },
    ];

    function updateCaption(idx) {
      const s = STAGES[idx];
      labelEl.textContent = s.label;
      bodyEl.innerHTML    = s.body;
      citeEl.textContent  = s.cite;
    }
    function goStage(idx) {
      idx = ((idx % STAGES.length) + STAGES.length) % STAGES.length;
      state.timers.forEach((t) => clearTimeout(t));
      state.timers = [];
      state.fxNodes.forEach((n) => n.remove());
      state.fxNodes.clear();
      resetBoardOpp();
      clearRedactedFlags();
      // Hide any leftover nox sticker from a previous stage; the
      // current stage's animate() will re-show it at the right moment.
      if (noxSticker) { noxSticker.classList.remove("is-on"); noxSticker.hidden = true; }
      if (noxSweep) { noxSweep.classList.remove("is-on"); noxSweep.hidden = true; }
      // Two-panel layout for 2-seat stages (0-5) and four-panel for
      // the 4-seat stages (6, 7). Each stage's own settle/animate
      // then fills the panels with the right content.
      if (idx >= 6) configureFourPanel();
      else configureTwoPanel();
      state.stageIdx = idx;
      updateCaption(idx);
      STAGES[idx].animate();
      if (state.autoPlay) {
        state.timers.push(setTimeout(() => {
          if (state.stopped) return;
          goStage(idx + 1 >= STAGES.length ? 0 : idx + 1);
        }, STAGES[idx].dur));
      }
    }
    state.goStage = goStage;

    btnPrev.onclick    = () => goStage(state.stageIdx - 1);
    btnNext.onclick    = () => goStage(state.stageIdx + 1);
    btnToggle.textContent = "[ ⏵ PLAY ]";
    btnToggle.onclick  = () => {
      state.autoPlay = !state.autoPlay;
      btnToggle.textContent = state.autoPlay ? "[ ⏸ PAUSE ]" : "[ ⏵ PLAY ]";
      if (state.autoPlay) {
        state.timers.push(setTimeout(() => {
          if (state.stopped) return;
          const next = state.stageIdx + 1;
          goStage(next >= STAGES.length ? 0 : next);
        }, STAGES[state.stageIdx].dur));
      }
    };
    btnRestart.onclick = () => {
      state.autoPlay = false;
      btnToggle.textContent = "[ ⏵ PLAY ]";
      goStage(0);
    };

    goStage(0);
  }


  // ═══════════════════════════════════════════════════════════════
  // TAB 7 — MAP GENERATION
  //
  // Three seeded maps rendered side-by-side. Each starts fully fogged
  // and is revealed by a rAF-driven diagonal wave, mirroring the
  // "sensor sweep" feel of a probe going live.
  //
  // The map generator is a JS port of the essentials of
  // sea_of_colours/generator.py + noise.py:
  //   • value_noise_2d (bilinearly interpolated random lattice with
  //     smoothstep easing — noise.py:25)
  //   • fbm_2d (4-octave sum, renormalized — noise.py:63)
  //   • ridge_transform (1 - |2n - 1|, renormalized — noise.py:107)
  //   • red seams: top-percentile of the ridge field
  //   • green bands: one snap-to-8 angle × 1-3 parallel centers,
  //     smoothstep(half_width, 0, perpDist) × noise > threshold
  //   • blue pockets: sparse mask from a medium-freq fBm above
  //     threshold, cellular-automata smoothing, Chebyshev distance
  //     transform peaks, purity graded by distance from peak
  //
  // This is a teaching demo — the port faithfully mirrors the shape
  // and character of the engine's algorithm, not every micro-tuned
  // parameter. What matters is that every seed reliably produces:
  // linear red seams, one diagonal green band, tight blue blobs.
  // ═══════════════════════════════════════════════════════════════
  let tab7_state = null;
  let _tab7NextSeeds = null;    // stash for the next tab7_start after a reroll
  function tab7_stop() {
    if (tab7_state) {
      tab7_state.stopped = true;
      tab7_state.timers.forEach((t) => clearTimeout(t));
      tab7_state.timers = [];
      if (tab7_state.raf) cancelAnimationFrame(tab7_state.raf);
      tab7_state.raf = null;
      tab7_state = null;
    }
  }

  // ── Seeded PRNG ────────────────────────────────────────────────
  // Mulberry32 — small, deterministic, good enough for demo noise.
  function mulberry32(seed) {
    let a = seed >>> 0;
    return function () {
      a |= 0; a = (a + 0x6D2B79F5) | 0;
      let t = a;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  function smoothstepJs(t) { return t * t * (3.0 - 2.0 * t); }
  function lerpJs(a, b, t) { return a + (b - a) * t; }

  // ── value_noise_2d (port of noise.py:25) ───────────────────────
  function valueNoise2D(w, h, scale, seed) {
    if (scale <= 0) throw new Error("scale must be positive");
    const rng = mulberry32(seed);
    const lat_w = Math.floor(w / scale) + 2;
    const lat_h = Math.floor(h / scale) + 2;
    const lattice = new Array(lat_h);
    for (let y = 0; y < lat_h; y++) {
      const row = new Array(lat_w);
      for (let x = 0; x < lat_w; x++) row[x] = rng();
      lattice[y] = row;
    }
    const field = new Array(h);
    for (let y = 0; y < h; y++) {
      const gy = y / scale, y0 = Math.floor(gy), ty = smoothstepJs(gy - y0);
      const row = new Array(w);
      for (let x = 0; x < w; x++) {
        const gx = x / scale, x0 = Math.floor(gx), tx = smoothstepJs(gx - x0);
        const v00 = lattice[y0][x0];
        const v10 = lattice[y0][x0 + 1];
        const v01 = lattice[y0 + 1][x0];
        const v11 = lattice[y0 + 1][x0 + 1];
        const top = lerpJs(v00, v10, tx);
        const bot = lerpJs(v01, v11, tx);
        row[x] = lerpJs(top, bot, ty);
      }
      field[y] = row;
    }
    return field;
  }

  // ── fbm_2d (port of noise.py:63) ───────────────────────────────
  function fbm2D(w, h, baseScale, octaves, persistence, lacunarity, seed) {
    const field = Array.from({ length: h }, () => new Array(w).fill(0));
    let amplitude = 1.0, scale = baseScale;
    for (let i = 0; i < octaves; i++) {
      const octave = valueNoise2D(w, h, scale, seed + i * 9973);
      for (let y = 0; y < h; y++) {
        const row = field[y], orow = octave[y];
        for (let x = 0; x < w; x++) row[x] += orow[x] * amplitude;
      }
      amplitude *= persistence;
      scale = Math.max(1.0, scale / lacunarity);
    }
    // renormalize to [0,1]
    let lo = Infinity, hi = -Infinity;
    for (const row of field) for (const v of row) { if (v < lo) lo = v; if (v > hi) hi = v; }
    const span = hi > lo ? hi - lo : 1.0;
    for (const row of field) for (let x = 0; x < row.length; x++) row[x] = (row[x] - lo) / span;
    return field;
  }
  function ridgeTransform(field) {
    const h = field.length, w = field[0].length;
    let lo = Infinity, hi = -Infinity;
    const out = new Array(h);
    for (let y = 0; y < h; y++) {
      const row = field[y], orow = new Array(w);
      for (let x = 0; x < w; x++) {
        const r = 1.0 - Math.abs(2.0 * row[x] - 1.0);
        orow[x] = r;
        if (r < lo) lo = r;
        if (r > hi) hi = r;
      }
      out[y] = orow;
    }
    const span = hi > lo ? hi - lo : 1.0;
    for (const row of out) for (let x = 0; x < row.length; x++) row[x] = (row[x] - lo) / span;
    return out;
  }

  // ── percentile threshold (port of _percentile_threshold) ───────
  function percentileThreshold(field, topFraction) {
    if (topFraction <= 0) return Infinity;
    if (topFraction >= 1) return -Infinity;
    const flat = [];
    for (const row of field) for (const v of row) flat.push(v);
    flat.sort((a, b) => a - b);
    const idx = Math.max(0, Math.min(flat.length - 1, Math.floor(flat.length * (1 - topFraction))));
    return flat[idx];
  }

  /** Generate a Grid — array of { tile, purity } cells — for one seed.
   *  Faithful JS port of generator.py's generate_grid. Every parameter
   *  matches the engine defaults exactly — this is a rulebook, we
   *  show the game as it actually is, we don't retune for the demo. */
  function generateMap(cols, rows, seed) {
    // Engine defaults (generator.py:87-134). Do not change these.
    const P = {
      redCoverage: 0.30,           // GenerationParams.red_coverage
      redGamma: 5.0,               // .red_gamma
      redRidgeLinear: 0.28,        // .red_ridge_linear
      redCoreBoost: 0.35,          // .red_core_boost
      redPureMinDepth: 3,          // .red_pure_min_depth
      redDepthRef: 3.5,            // .red_depth_ref
      greenBandHalfWidth: 1.5,     // GREEN_BAND_HALF_WIDTH
      greenBandStrength: 1.0,      // .green_strength
      greenBandThreshold: 0.35,    // hardcoded 0.35 / green_strength (RULEBOOK §2.3)
      blueDensity: 0.03,           // .blue_density
      blueSmoothIters: 1,          // .blue_smooth_iters
      blueMinPurity: 40,           // .blue_min_purity
      blueGamma: 1.0,              // .blue_gamma
    };
    const rng = mulberry32(seed);

    // ── RED (ridge fBm, top-percentile mask) ─────────────────────
    // generator.py:331 — base_scale = max(8.0, min(w,h) / 4.0).
    // generator.py:339 — seed = params.seed + 1_000.
    const redScale = Math.max(8.0, Math.min(cols, rows) / 4.0);
    const redNoise = fbm2D(cols, rows, redScale, 4, 0.5, 2.0, seed + 1000);
    const ridge = ridgeTransform(redNoise);
    const redThresh = percentileThreshold(ridge, P.redCoverage);
    const redMask = Array.from({ length: rows }, () => new Array(cols).fill(false));
    // Record normalized ridge_t per cell (matches generator.py:359 — the
    // engine stores this on the Cell and uses it later in
    // _finalize_red_purity). Only defined where redMask is true.
    const ridgeT = Array.from({ length: rows }, () => new Array(cols).fill(0));
    const redSpan = Math.max(1e-6, 1.0 - redThresh);
    for (let y = 0; y < rows; y++) {
      for (let x = 0; x < cols; x++) {
        if (ridge[y][x] >= redThresh) {
          redMask[y][x] = true;
          let t = (ridge[y][x] - redThresh) / redSpan;
          if (t < 0) t = 0; else if (t > 1) t = 1;
          ridgeT[y][x] = t;
        }
      }
    }

    // ── GREEN (one snap-to-8 angle × 1-3 parallel bands) ─────────
    // generator.py:376 — green base_scale = max(4.0, w / 12.0).
    const bandCount = 1 + Math.floor(rng() * 3);       // 1, 2, or 3
    const angleIdx = Math.floor(rng() * 8);
    const angle = angleIdx * Math.PI / 8.0;
    const dirX = Math.cos(angle), dirY = Math.sin(angle);
    const perpX = -dirY, perpY = dirX;
    const centres = [];
    const halfSpan = 0.5 * (cols * Math.abs(perpX) + rows * Math.abs(perpY));
    for (let i = 0; i < bandCount; i++) {
      const t = (i + 1) / (bandCount + 1);
      const jitter = (rng() - 0.5) * 0.2 * (halfSpan * 2 / bandCount);
      centres.push((t - 0.5) * halfSpan * 2 + jitter);
    }
    const greenScale = Math.max(4.0, cols / 12.0);
    // generator.py:384 — green noise seed = params.seed + 2_000.
    const greenNoise = fbm2D(cols, rows, greenScale, 3, 0.5, 2.0, seed + 2000);
    const greenMask = Array.from({ length: rows }, () => new Array(cols).fill(false));
    const cx0 = (cols - 1) * 0.5, cy0 = (rows - 1) * 0.5;
    for (let y = 0; y < rows; y++) {
      for (let x = 0; x < cols; x++) {
        const px = (x - cx0) * perpX + (y - cy0) * perpY;
        let minAbs = Infinity;
        for (const c of centres) {
          const d = Math.abs(px - c);
          if (d < minAbs) minAbs = d;
        }
        const t = 1.0 - Math.min(1.0, minAbs / P.greenBandHalfWidth);
        const mask = smoothstepJs(t);
        const score = mask * greenNoise[y][x] * P.greenBandStrength;
        if (score >= P.greenBandThreshold) greenMask[y][x] = true;
      }
    }

    // ── BLUE (sparse fBm mask + cellular smoothing + peak grade) ─
    // generator.py:494 — blue base_scale = max(4.0, w / 16.0).
    // threshold = _percentile_threshold(field, blue_density) directly.
    // (My earlier port did `blue_density * 4` which produced ~15-19%
    // coverage instead of the intended ~3% — huge mega-pockets.)
    const blueScale = Math.max(4.0, cols / 16.0);
    // generator.py:502 — blue noise seed = params.seed + 3_000.
    const blueNoise = fbm2D(cols, rows, blueScale, 3, 0.5, 2.0, seed + 3000);
    const blueThresh = percentileThreshold(blueNoise, P.blueDensity);
    let blueMask = Array.from({ length: rows }, () => new Array(cols).fill(false));
    for (let y = 0; y < rows; y++) for (let x = 0; x < cols; x++) if (blueNoise[y][x] >= blueThresh) blueMask[y][x] = true;
    // Cellular-automata smoothing — a cell survives if ≥ 4 of its 8 neighbours
    // (or itself) are set; otherwise it dies. Coalesces specks into pockets.
    for (let it = 0; it < P.blueSmoothIters; it++) {
      const next = Array.from({ length: rows }, () => new Array(cols).fill(false));
      for (let y = 0; y < rows; y++) {
        for (let x = 0; x < cols; x++) {
          let n = 0;
          for (let dy = -1; dy <= 1; dy++) {
            for (let dx = -1; dx <= 1; dx++) {
              const ny = y + dy, nx = x + dx;
              if (ny < 0 || ny >= rows || nx < 0 || nx >= cols) continue;
              if (blueMask[ny][nx]) n++;
            }
          }
          next[y][x] = n >= 4;
        }
      }
      blueMask = next;
    }
    // Composite mask precedence: BLUE beats GREEN beats RED beats EMPTY.
    // But we also want to compute BLUE purity from Chebyshev distance to
    // the pocket peak — so identify connected components first.
    const cellsOut = new Array(rows * cols);
    for (let y = 0; y < rows; y++) {
      for (let x = 0; x < cols; x++) {
        cellsOut[y * cols + x] = { tile: 0, purity: 0 };
      }
    }
    // Fill RED first.
    //
    // Depth = 4-neighbour Manhattan distance from nearest non-RED cell,
    // computed by a BFS from the seam edges. This mirrors
    // generator.py:_red_edge_manhattan_depth exactly:
    //   • edge cells (any cardinal neighbour is non-RED or out-of-bounds)
    //     start at depth 1
    //   • deeper cells get +1 per BFS step
    //   • fully-enclosed islands never touched by BFS fall back to
    //     1 + min-corner-distance (rare; matches engine fallback).
    const inf = cols + rows + 100;
    const depthMap = Array.from({ length: rows }, () => new Array(cols).fill(inf));
    const q = [];
    for (let y = 0; y < rows; y++) {
      for (let x = 0; x < cols; x++) {
        if (!redMask[y][x]) continue;
        let isEdge = false;
        for (const [dy, dx] of [[-1,0],[1,0],[0,-1],[0,1]]) {
          const ny = y + dy, nx = x + dx;
          if (ny < 0 || ny >= rows || nx < 0 || nx >= cols) { isEdge = true; break; }
          if (!redMask[ny][nx]) { isEdge = true; break; }
        }
        if (isEdge) { depthMap[y][x] = 1; q.push([y, x]); }
      }
    }
    let head = 0;
    while (head < q.length) {
      const [y, x] = q[head++];
      const nd = depthMap[y][x] + 1;
      for (const [dy, dx] of [[-1,0],[1,0],[0,-1],[0,1]]) {
        const ny = y + dy, nx = x + dx;
        if (ny < 0 || ny >= rows || nx < 0 || nx >= cols) continue;
        if (!redMask[ny][nx]) continue;
        if (nd < depthMap[ny][nx]) { depthMap[ny][nx] = nd; q.push([ny, nx]); }
      }
    }

    // Now compute per-cell purity — port of _finalize_red_purity.
    const depthRef = P.redDepthRef;                   // 3.5
    const pureFloor = P.redPureMinDepth;              // 3
    const boostMax = P.redCoreBoost;                  // 0.35
    const lin = P.redRidgeLinear;                     // 0.28
    const gamma = P.redGamma;                         // 5.0
    for (let y = 0; y < rows; y++) {
      for (let x = 0; x < cols; x++) {
        if (!redMask[y][x]) continue;
        let d = depthMap[y][x];
        if (d >= inf) {
          d = 1 + Math.min(x, y, cols - 1 - x, rows - 1 - y);
        }
        const depthFactor = Math.min(1.0, d / depthRef);
        const t = ridgeT[y][x];
        const curved = Math.pow(t, gamma);
        const ridgeVal = (1.0 - lin) * curved + lin * t;
        let boost = 0.0;
        if (d >= pureFloor && boostMax > 0.0) {
          const denom = Math.max(1e-6, depthRef - pureFloor + 1.0);
          boost = boostMax * Math.min(1.0, (d - pureFloor + 1) / denom);
        }
        const combined = Math.min(1.0, ridgeVal + boost);
        let purity = Math.round(255 * depthFactor * combined);
        if (purity < 0) purity = 0;
        else if (purity > 255) purity = 255;
        if (d < pureFloor) purity = Math.min(purity, 254);
        cellsOut[y * cols + x] = { tile: 2, purity }; // TILE.RED = 2
      }
    }
    // GREEN overwrites RED on band cells
    for (let y = 0; y < rows; y++) {
      for (let x = 0; x < cols; x++) {
        if (greenMask[y][x]) cellsOut[y * cols + x] = { tile: 1, purity: 255 }; // TILE.GREEN
      }
    }
    // BLUE overwrites everything — with Chebyshev-graded purity.
    // Find connected components + peaks first.
    const visited = Array.from({ length: rows }, () => new Array(cols).fill(false));
    for (let y = 0; y < rows; y++) {
      for (let x = 0; x < cols; x++) {
        if (!blueMask[y][x] || visited[y][x]) continue;
        // BFS to find the component
        const stack = [[x, y]];
        const comp = [];
        visited[y][x] = true;
        while (stack.length) {
          const [cx, cy] = stack.pop();
          comp.push([cx, cy]);
          for (const [dx, dy] of [[-1,0],[1,0],[0,-1],[0,1]]) {
            const nx = cx + dx, ny = cy + dy;
            if (nx < 0 || nx >= cols || ny < 0 || ny >= rows) continue;
            if (blueMask[ny][nx] && !visited[ny][nx]) {
              visited[ny][nx] = true;
              stack.push([nx, ny]);
            }
          }
        }
        // Chebyshev distance transform on this component:
        // d(cell) = min over non-comp cells of max(|dx|, |dy|)
        // Peak = cell with max d.
        const distByKey = new Map();
        let peak = null, peakD = -1;
        for (const [cx, cy] of comp) {
          let minD = Infinity;
          for (let dy = -5; dy <= 5; dy++) {
            for (let dx = -5; dx <= 5; dx++) {
              const nx = cx + dx, ny = cy + dy;
              if (nx < 0 || nx >= cols || ny < 0 || ny >= rows || !blueMask[ny][nx]) {
                const d = Math.max(Math.abs(dx), Math.abs(dy));
                if (d < minD) minD = d;
              }
            }
          }
          distByKey.set(cx + "," + cy, minD);
          if (minD > peakD) { peakD = minD; peak = [cx, cy]; }
        }
        if (!peak) peak = comp[0];
        // Purity: 255 at peak, gradient away from peak by chebyshev-from-peak
        for (const [cx, cy] of comp) {
          const dp = Math.max(Math.abs(cx - peak[0]), Math.abs(cy - peak[1]));
          const t = peakD > 0 ? dp / peakD : 0;
          const clamped = Math.min(1, Math.max(0, t));
          const gradient = Math.pow(1 - clamped, P.blueGamma);
          const purity = Math.round(P.blueMinPurity + gradient * (255 - P.blueMinPurity));
          cellsOut[cy * cols + cx] = { tile: 3, purity };  // TILE.BLUE = 3
        }
      }
    }
    return cellsOut;
  }

  function tab7_start() {
    tab7_stop();
    const state = { stopped: false, timers: [], raf: null };
    tab7_state = state;

    // Map dimensions — game default (though the game usually runs
    // larger 80×50 sessions, 40×28 is the documented small-session
    // default and is what the manual demonstrates). Cell size chosen
    // so three cards fit side-by-side under ~1080px.
    const COLS = 40, ROWS = 28;
    const CELL = 8;

    // Pick three seeds. Reroll passes the new triple via _tab7NextSeeds
    // (module-level) since tab7_start clears state on entry.
    const seeds = _tab7NextSeeds || [7, 42, 1729];
    _tab7NextSeeds = null;

    const status = document.getElementById("mn-maps-status");
    const phase  = document.getElementById("mn-maps-phase");

    /** Render one map into its host + attach coord tooltips. Returns
     *  { board, cells } for the animation phase. */
    function renderOne(hostId, seedElId, capElId, seed) {
      const host = document.getElementById(hostId);
      const seedEl = document.getElementById(seedElId);
      const capEl  = document.getElementById(capElId);
      seedEl.textContent = String(seed);

      const cells = generateMap(COLS, ROWS, seed);
      // start fully fogged
      const view = cells.map((c) => ({ ...c, fog: true }));
      const board = renderBoard(host, view, { cols: COLS, rows: ROWS, cellW: CELL, cellH: CELL });

      // caption: tile counts
      let nR = 0, nB = 0, nG = 0;
      for (const c of cells) {
        if (c.tile === 2) nR++;
        else if (c.tile === 3) nB++;
        else if (c.tile === 1) nG++;
      }
      capEl.innerHTML =
        `<span class="fg-red">RED ${nR}</span> · ` +
        `<span class="fg-green">GREEN ${nG}</span> · ` +
        `<span class="fg-blue">BLUE ${nB}</span>`;
      return { board, cells };
    }

    const maps = [
      renderOne("mn-board-map-0", "mn-map-seed-0", "mn-map-cap-0", seeds[0]),
      renderOne("mn-board-map-1", "mn-map-seed-1", "mn-map-cap-1", seeds[1]),
      renderOne("mn-board-map-2", "mn-map-seed-2", "mn-map-cap-2", seeds[2]),
    ];

    /** Reveal every map from fog with a diagonal wave. Maps reveal
     *  sequentially — map 0 fully clears before map 1 starts, etc.
     *  A brief gap between maps lets the eye focus on each one before
     *  the next materialises. */
    function reveal() {
      status.textContent = "# revealing · sensor sweep · same seed → same map";
      const perMapDur = 1600;
      const gap = 320;

      // First refog everything (in case reveal is being replayed).
      maps.forEach(({ board }) => {
        Array.from(board.children).forEach((cell) => {
          const fog = cell.querySelector(".mn-cell-fog");
          if (fog) {
            fog.classList.remove("is-clear");
            cell.classList.add("is-fogged");
          }
        });
      });

      function revealMap(mi, onDone) {
        if (mi >= maps.length) { onDone && onDone(); return; }
        const { board } = maps[mi];
        const cellData = Array.from(board.children).map((el, i) => ({
          el,
          d: (i % COLS) * 0.9 + Math.floor(i / COLS) * 1.1,
        }));
        let maxD = 0;
        for (const c of cellData) if (c.d > maxD) maxD = c.d;
        const start = performance.now();
        function frame(now) {
          if (state.stopped) return;
          const t = Math.max(0, (now - start) / perMapDur);
          const front = t * (maxD + 2);
          let anyFogged = false;
          for (const c of cellData) {
            if (c.d <= front) {
              const fog = c.el.querySelector(".mn-cell-fog");
              if (fog && !fog.classList.contains("is-clear")) {
                fog.classList.add("is-clear");
                c.el.classList.remove("is-fogged");
              }
            } else {
              anyFogged = true;
            }
          }
          if (anyFogged && t < 1.4) {
            state.raf = requestAnimationFrame(frame);
          } else {
            // This map is done — hand off to the next after a beat.
            state.timers.push(setTimeout(() => {
              if (state.stopped) return;
              revealMap(mi + 1, onDone);
            }, gap));
          }
        }
        state.raf = requestAnimationFrame(frame);
      }

      revealMap(0, () => {
        status.textContent = "# three seeds · three worlds · same generator";
      });
    }

    // Buttons
    document.getElementById("mn-maps-reveal").onclick = () => reveal();
    document.getElementById("mn-maps-reroll").onclick = () => {
      // Roll three fresh seeds, stash them, and restart the tab —
      // tab7_stop then tab7_start picks up _tab7NextSeeds.
      _tab7NextSeeds = [
        Math.floor(Math.random() * 9999),
        Math.floor(Math.random() * 9999),
        Math.floor(Math.random() * 9999),
      ];
      tab7_stop();
      tab7_start();
    };
    // Auto-reveal on first entry
    state.timers.push(setTimeout(() => {
      if (!state.stopped) reveal();
    }, 500));
  }

  // ═══════════════════════════════════════════════════════════════
  // TAB 8 — SEASON · THE FULL LOOP
  //
  // Real board (like Tab 3) with:
  //   • left rail — the player's orbital STATION diamond (identity
  //     anchor, mirrors the game's os-station diamond from
  //     server/static/station.js). Vault region shows banked parcels.
  //   • centre — real board with fog, probes, harvester, seams
  //   • right rail — stage caption
  //   • far right — EARTH · shipping score
  //
  // Stages walk the full nomenclature + process:
  //   0 · NOX · 21 hours (mini-play: probe drop, harvest, vault fills)
  //   1 · AURORA (engine heat sweep — vault survives, planet doesn't)
  //   2 · DAY · orbital · 3 actions (repair / refine / SHIP → +earth)
  //   3 · VESPERA → new Nox (engine cool + refog + fresh drop)
  //   4 · SEASON · 7 nights + 7 days (zoom-out strip overlay)
  //   5 · FULL LOOP (compressed harvest→vault→ship pipeline)
  //
  // Reuses engine primitives: renderBoard, spawnProbeTrail,
  // runOrbitalArcAnimation, setEntity, setProbe, setTerrain, setFog,
  // TILE, GLYPH_HARVESTER, CH_LIGHT. Aurora/Vespera heat sweep and
  // harvester step animations are inlined from Tab 3/6.
  // ═══════════════════════════════════════════════════════════════
  let tab8_state = null;
  function tab8_stop() {
    if (tab8_state) {
      tab8_state.stopped = true;
      tab8_state.timers.forEach((t) => clearTimeout(t));
      tab8_state.timers = [];
      if (tab8_state.heatRaf) {
        cancelAnimationFrame(tab8_state.heatRaf);
        tab8_state.heatRaf = null;
      }
      tab8_state.fxNodes.forEach((n) => n.remove());
      tab8_state.fxNodes.clear();
      tab8_state = null;
    }
  }

  function tab8_start() {
    tab8_stop();

    // ── DOM refs ─────────────────────────────────────────────────
    const boardHost      = document.getElementById("mn-board-season");
    const stickerEl      = document.getElementById("mn-season-sticker");
    const hourStripEl    = document.getElementById("mn-season-hour-strip");
    const stripOverlayEl = document.getElementById("mn-season-strip-overlay");
    const stripBlocksEl  = document.getElementById("mn-season-strip-blocks");
    const diamondEl      = document.getElementById("mn-season-diamond");
    const vaultEl        = document.getElementById("mn-season-vault");
    const stationScoreEl = document.getElementById("mn-season-score");
    const stationDeltaEl = document.getElementById("mn-season-score-delta");
    const earthScoreEl   = document.getElementById("mn-season-earth-score");
    const earthDeltaEl   = document.getElementById("mn-season-earth-delta");
    const stationEl      = document.querySelector(".mn-season-station");
    const stageEl        = document.querySelector(".mn-season-stage");
    const labelEl        = document.getElementById("mn-stage-label-8");
    const bodyEl         = document.getElementById("mn-stage-body-8");
    const citeEl         = document.getElementById("mn-stage-cite-8");
    const phaseEl        = document.getElementById("mn-season-phase");
    const statusEl       = document.getElementById("mn-season-status");
    const btnPrev        = document.getElementById("mn-season-prev");
    const btnNext        = document.getElementById("mn-season-next");
    const btnToggle      = document.getElementById("mn-season-toggle");
    const btnRestart     = document.getElementById("mn-season-restart");

    // ── board setup ─────────────────────────────────────────────
    const cols = 22, rows = 12;
    const cellW = 24, cellH = 24;
    const total = cols * rows;

    // A small red seam cluster in the middle-left of the board — big
    // enough to give the harvester 5-6 things to walk through across
    // two loops.
    const RED_SEAM = [
      { x:  6, y: 5 },
      { x:  7, y: 5 }, { x:  7, y: 6 },
      { x:  8, y: 5 }, { x:  8, y: 6 }, { x:  8, y: 7 },
      { x:  9, y: 6 }, { x:  9, y: 7 },
      { x: 10, y: 7 }, { x: 11, y: 7 },
    ];
    const base = new Array(total);
    for (let i = 0; i < total; i++) {
      base[i] = { tile: TILE.EMPTY, purity: 0, fog: true };
    }
    for (const s of RED_SEAM) {
      const i = s.y * cols + s.x;
      base[i] = { tile: TILE.RED, purity: 180, fog: true };
    }
    const cells = base.map((c) => ({ ...c }));
    const board = renderBoard(boardHost, cells, { cols, rows, cellW, cellH });

    // ── state ───────────────────────────────────────────────────
    const state = {
      stopped: false, timers: [], fxNodes: new Set(),
      stageIdx: 0, autoPlay: false,
      // Engine heat-sweep state
      heatCells: null, heatRaf: null, heatApplied: false,
      // Game state
      vault: [],           // Array of {ch, color}
      stationScore: 0,     // vault-value display
      earthScore: 0,       // shipped-to-earth total
      harvester: { x: 0, y: 0, alive: false },
      probeCell: null,
    };
    tab8_state = state;

    const idxAt = (x, y) => y * cols + x;
    const timer = (fn, ms) => {
      const t = setTimeout(() => { if (state.stopped) return; fn(); }, ms);
      state.timers.push(t);
      return t;
    };
    const P1_COLOR = "--seat-p1";
    const P1_HEX   = "#8ac0ff";

    // ── engine Aurora / Vespera sweep (ported from Tab 6) ───────
    const CELL_BG_RGB = [14, 11, 22];
    function _heatClearAllCells() {
      Array.from(board.children).forEach((c) => {
        c.style.background = "";
        const terr = c.querySelector(".mn-cell-terrain");
        if (terr) { terr.style.filter = ""; terr.style.textShadow = ""; terr.style.transform = ""; }
        const fog = c.querySelector(".mn-cell-fog");
        if (fog) { fog.textContent = CH_LIGHT; fog.style.color = ""; fog.style.opacity = ""; }
        c.classList.remove("mn-cell-dawn-decay");
      });
    }
    function _applyHeat(c, h, wallT, probeIdxSet, onProbePassed, front) {
      const isFog = c.el.classList.contains("is-fogged");
      if (h < 0.015) {
        c.el.style.background = "";
        if (c.terr) { c.terr.style.filter = ""; c.terr.style.textShadow = ""; c.terr.style.transform = ""; }
        if (c.fog)  { c.fog.textContent = CH_LIGHT; c.fog.style.color = ""; }
        return;
      }
      if (isFog && c.fog) {
        c.fog.textContent = "\u2592\u2592";
        const w = Math.round(90 + h * 165);
        c.fog.style.color = `rgb(${w},${w},${w})`;
        const br = Math.round(15 + h * 22);
        const bg = Math.round(12 + h * 14);
        const bb = Math.round(24 + h * 16);
        c.el.style.background = `rgba(${br},${bg},${bb},0.96)`;
        if (c.terr) c.terr.style.filter = "";
      } else if (c.terr) {
        const sat = (1 + h * 1.5).toFixed(2);
        const bri = (1 + h * 0.45).toFixed(2);
        c.terr.style.filter = `saturate(${sat}) brightness(${bri})`;
        const [cr, cg, cb] = CELL_BG_RGB;
        const lr = Math.min(255, Math.round(cr + h * 42));
        const lg = Math.min(255, Math.round(cg + h * 32));
        const lb = Math.min(255, Math.round(cb + h * 24));
        c.el.style.background = `rgb(${lr},${lg},${lb})`;
      }
      if (c.terr) {
        const glowA = Math.max(0, (h - 0.2) / 0.8);
        const blur  = Math.round(3 + glowA * 5);
        const a     = (glowA * 0.7).toFixed(2);
        c.terr.style.textShadow = `0 0 ${blur}px rgba(255,200,80,${a})`;
        if (wallT > 0 && h > 0.15) {
          const t   = wallT * 0.001;
          const amp = 1.8 * Math.min(1, h * 1.6);
          const dx = (Math.sin(c.cx * 0.55 + t * 4.3 + c.cy * 0.31) * amp).toFixed(1);
          const dy = (Math.cos(c.cy * 0.63 + t * 3.8 + c.cx * 0.44) * amp * 0.5).toFixed(1);
          c.terr.style.transform = `translate(${dx}px, ${dy}px)`;
        }
      }
      if (probeIdxSet && probeIdxSet.has(c.idx) && front !== undefined && front - c.d > 0) {
        onProbePassed(c.idx);
      }
    }
    function _cancelHeatRaf() {
      if (state.heatRaf) { cancelAnimationFrame(state.heatRaf); state.heatRaf = null; }
    }
    function _liveProbeIdxs() {
      const out = [];
      for (let i = 0; i < total; i++) {
        const cellEl = boardCell(board, i);
        const ent = cellEl.querySelector(".mn-cell-entity");
        if (ent && ent.classList.contains("mn-cell-entity--probe")) out.push(i);
      }
      return out;
    }
    function playAuroraSweepLocal(probeIdxs, onDone) {
      const boardCells = Array.from(board.children);
      const cellData = boardCells.map((el, i) => ({
        el, idx: i,
        terr: el.querySelector(".mn-cell-terrain"),
        fog:  el.querySelector(".mn-cell-fog"),
        cx: i % cols,
        cy: Math.floor(i / cols),
        d:  (i % cols) * 0.85 + Math.floor(i / cols) * 1.15,
      }));
      state.heatCells = cellData;
      let maxD = 0;
      for (const c of cellData) if (c.d > maxD) maxD = c.d;
      const MIN_D = -4, MAX_D = maxD + 6;
      const durIn = 1100, rate = (MAX_D - MIN_D) / durIn, holdDur = 80;
      let front = MIN_D, lastTs = null, holdStart = 0, phase = "in", onDoneFired = false;
      const probeSet = new Set(probeIdxs || []);
      const probeFired = new Set();
      function heatLevel(d, front) {
        const dist = front - d;
        if (dist < -2) return 0;
        if (dist <  2) return Math.max(0, (dist + 2) / 4);
        if (dist <  6) return 1.0 - ((dist - 2) / 4) * 0.48;
        return 0.52;
      }
      function onProbePassed(idx) {
        if (probeFired.has(idx)) return;
        probeFired.add(idx);
        const probeCell = boardCell(board, idx);
        probeCell.classList.add("mn-cell-dawn-decay");
        state.timers.push(setTimeout(() => probeCell.classList.remove("mn-cell-dawn-decay"), 640));
      }
      function frame(ts) {
        if (state.stopped) return;
        if (lastTs === null) lastTs = ts;
        const dt = Math.min(ts - lastTs, 50); lastTs = ts;
        if (phase === "in") {
          front += rate * dt;
          for (const c of cellData) _applyHeat(c, heatLevel(c.d, front), ts, probeSet, onProbePassed, front);
          if (front >= MAX_D) { phase = "hold"; holdStart = ts; }
        } else {
          for (const c of cellData) _applyHeat(c, 0.52, ts, probeSet, () => {}, front);
          if (!onDoneFired && ts - holdStart >= holdDur) {
            onDoneFired = true;
            state.heatApplied = true;
            if (onDone) try { onDone(); } catch (_) {}
            return;
          }
        }
        state.heatRaf = requestAnimationFrame(frame);
      }
      state.heatRaf = requestAnimationFrame(frame);
    }
    function playVesperaSweepLocal(onDone) {
      const cellData = state.heatCells || Array.from(board.children).map((el, i) => ({
        el, idx: i,
        terr: el.querySelector(".mn-cell-terrain"),
        fog:  el.querySelector(".mn-cell-fog"),
        cx: i % cols,
        cy: Math.floor(i / cols),
        d:  (i % cols) * 0.85 + Math.floor(i / cols) * 1.15,
      }));
      let maxD = 0;
      for (const c of cellData) if (c.d > maxD) maxD = c.d;
      const MIN_D = -4, MAX_D = maxD + 6;
      const durOut = 900, rate = (MAX_D - MIN_D) / durOut;
      let front = MIN_D, lastTs = null;
      function coolLevel(d, front) {
        const dist = front - d;
        if (dist < -2) return 0.52;
        if (dist <  2) return 0.52 * (1 - (dist + 2) / 4);
        return 0;
      }
      function frame(ts) {
        if (state.stopped) return;
        if (lastTs === null) lastTs = ts;
        const dt = Math.min(ts - lastTs, 50); lastTs = ts;
        front += rate * dt;
        for (const c of cellData) _applyHeat(c, coolLevel(c.d, front), ts, null, () => {}, front);
        if (front < MAX_D) {
          state.heatRaf = requestAnimationFrame(frame);
        } else {
          _heatClearAllCells();
          state.heatApplied = false;
          state.heatCells = null;
          if (onDone) try { onDone(); } catch (_) {}
        }
      }
      state.heatRaf = requestAnimationFrame(frame);
    }

    // ── harvester step animation (ported from Tab 3/6) ──────────
    function spawnHarvestFxLocal(cell, color) {
      const rect = cell.getBoundingClientRect();
      const cx = rect.left + rect.width * 0.5;
      const cy = rect.top + rect.height * 0.5;
      const blink = document.createElement("div");
      blink.className = "mn-harvest-blink";
      blink.style.setProperty("--blink-color", color);
      cell.appendChild(blink);
      state.fxNodes.add(blink);
      blink.addEventListener("animationend", () => { blink.remove(); state.fxNodes.delete(blink); }, { once: true });
      const N = 8;
      for (let i = 0; i < N; i++) {
        const angle = (i / N) * Math.PI * 2 + (Math.random() - 0.5) * 0.4;
        const dist = rect.width * (1.8 + Math.random() * 1.4);
        const p = document.createElement("div");
        p.className = "mn-harvest-particle";
        p.style.left = `${cx.toFixed(1)}px`;
        p.style.top  = `${cy.toFixed(1)}px`;
        const sz = Math.max(2, Math.round(rect.width * 0.22));
        p.style.width  = `${sz}px`;
        p.style.height = `${sz}px`;
        p.style.setProperty("--dx", `${(Math.cos(angle) * dist).toFixed(1)}px`);
        p.style.setProperty("--dy", `${(Math.sin(angle) * dist).toFixed(1)}px`);
        p.style.background = color;
        p.style.animationDelay = `${Math.round(Math.random() * 40)}ms`;
        document.body.appendChild(p);
        state.fxNodes.add(p);
        p.addEventListener("animationend", () => { p.remove(); state.fxNodes.delete(p); }, { once: true });
      }
    }
    function animateStepLocal(prevCell, nextCell, seatVar, blinkColor, onArrive) {
      const prevEntity = prevCell.querySelector(".mn-cell-entity");
      const nextEntity = nextCell.querySelector(".mn-cell-entity");
      prevEntity.textContent = "";
      const savedNextText = nextEntity.textContent;
      nextEntity.textContent = "";
      const pr = prevCell.getBoundingClientRect();
      const nr = nextCell.getBoundingClientRect();
      const ghost = document.createElement("span");
      ghost.className = "mn-step-ghost";
      ghost.textContent = GLYPH_HARVESTER;
      ghost.style.left = `${pr.left}px`;
      ghost.style.top  = `${pr.top}px`;
      ghost.style.width  = `${pr.width}px`;
      ghost.style.height = `${pr.height}px`;
      ghost.style.color  = `var(${seatVar})`;
      ghost.style.fontSize = `${Math.round(pr.width * 0.7)}px`;
      document.body.appendChild(ghost);
      state.fxNodes.add(ghost);
      const dx = nr.left - pr.left;
      const dy = nr.top  - pr.top;
      let done = false;
      const finish = () => {
        if (done || state.stopped) return;
        done = true;
        ghost.remove();
        state.fxNodes.delete(ghost);
        if (savedNextText) nextEntity.textContent = savedNextText;
        onArrive();
        if (blinkColor) spawnHarvestFxLocal(nextCell, blinkColor);
      };
      requestAnimationFrame(() => requestAnimationFrame(() => {
        ghost.style.transform = `translate(${dx.toFixed(1)}px, ${dy.toFixed(1)}px)`;
      }));
      ghost.addEventListener("transitionend", finish, { once: true });
      state.timers.push(setTimeout(finish, 260));
    }

    // ── helpers ──────────────────────────────────────────────
    const boardCellAt = (x, y) => boardCell(board, idxAt(x, y));
    function pushLog(kind, msg) {
      const log = document.getElementById("mn-eventlog-8");
      if (!log) return;
      const line = document.createElement("div");
      line.className = `mn-log mn-log--${kind}`;
      line.textContent = `# ${msg}`;
      log.prepend(line);
      while (log.children.length > 40) log.removeChild(log.lastChild);
    }
    function clearLog() {
      const log = document.getElementById("mn-eventlog-8");
      if (log) log.innerHTML = "";
    }
    function setSticker(text, cls) {
      if (!stickerEl) return;
      stickerEl.textContent = text;
      stickerEl.classList.remove("is-aurora", "is-day", "is-vespera");
      if (cls) stickerEl.classList.add(cls);
      stickerEl.hidden = false;
      // eslint-disable-next-line no-unused-expressions
      stickerEl.offsetHeight;
      stickerEl.classList.add("is-on");
    }
    function hideSticker() {
      if (!stickerEl) return;
      stickerEl.classList.remove("is-on");
      timer(() => { if (stickerEl) stickerEl.hidden = true; }, 300);
    }

    // ── station diamond builder + vault paint ─────────────────
    // Mirrors _osRebuildDiamond in server/static/station.js:937 —
    // a rhombus of \u2588 with the top-left corner carved out for the
    // vault region. Left-side seat, so vault is top-LEFT.
    const DIA_SIZE  = 12;
    const DIA_HALF  = 6;
    const VAULT_ROWS = 2;
    const VAULT_COLS = 3;
    function buildDiamond() {
      let html = "";
      for (let r = 0; r < DIA_SIZE; r++) {
        const dist     = Math.abs(r - (DIA_HALF - 1));
        const diaStart = dist;
        const diaEnd   = DIA_SIZE - 1 - dist;
        for (let c = 0; c < DIA_SIZE; c++) {
          const inDiamond = c >= diaStart && c <= diaEnd;
          const inVault   = r < VAULT_ROWS && c < VAULT_COLS;
          html += (!inVault && inDiamond) ? "\u2588" : " ";
        }
        if (r < DIA_SIZE - 1) html += "\n";
      }
      diamondEl.textContent = html;
    }
    function paintVault(items) {
      // items is a flat array of {ch, color}; slots up to VAULT_ROWS*VAULT_COLS.
      let html = "";
      for (let r = 0; r < DIA_SIZE; r++) {
        for (let c = 0; c < DIA_SIZE; c++) {
          const inVault = r < VAULT_ROWS && c < VAULT_COLS;
          if (inVault) {
            const idx = r * VAULT_COLS + c;
            const item = items[idx];
            if (item) {
              html += `<span style="color:${item.color}">${item.ch}</span>`;
            } else {
              html += " ";
            }
          } else {
            html += " ";
          }
        }
        if (r < DIA_SIZE - 1) html += "\n";
      }
      vaultEl.innerHTML = html;
    }
    function bumpVault(color) {
      const cap = VAULT_ROWS * VAULT_COLS;
      if (state.vault.length >= cap) return;
      state.vault.push({ ch: "\u2588\u2588", color });
      paintVault(state.vault);
    }
    function drainVaultOne() {
      // Remove one parcel from the vault (used during SHIP)
      if (state.vault.length === 0) return;
      state.vault.pop();
      paintVault(state.vault);
    }
    function pulseStation() {
      stationEl.classList.add("is-pulse");
      timer(() => stationEl.classList.remove("is-pulse"), 500);
    }
    function tickEarthScore(delta) {
      state.earthScore += delta;
      earthScoreEl.textContent = state.earthScore.toLocaleString();
      earthScoreEl.classList.add("is-tick");
      earthDeltaEl.textContent = "+" + delta;
      earthDeltaEl.classList.add("is-on");
      timer(() => {
        earthScoreEl.classList.remove("is-tick");
        earthDeltaEl.classList.remove("is-on");
      }, 800);
    }

    // ── ship-parcel FX: fixed-position ghost arcs diamond → earth ─
    function shipParcel(onDone) {
      const diaRect   = diamondEl.getBoundingClientRect();
      const earthRect = earthScoreEl.getBoundingClientRect();
      const sx = diaRect.right - 4;
      const sy = diaRect.top + diaRect.height * 0.4;
      const ex = earthRect.left + earthRect.width * 0.5;
      const ey = earthRect.top  + earthRect.height * 0.4;
      const ghost = document.createElement("span");
      ghost.className = "mn-season-ship-fx";
      ghost.textContent = "\u25c6";
      ghost.style.left = `${sx.toFixed(1)}px`;
      ghost.style.top  = `${sy.toFixed(1)}px`;
      ghost.style.transition = "transform 900ms cubic-bezier(0.4, 0.1, 0.6, 1.0), opacity 900ms ease";
      document.body.appendChild(ghost);
      state.fxNodes.add(ghost);
      requestAnimationFrame(() => requestAnimationFrame(() => {
        ghost.classList.add("is-flying");
        ghost.style.transform = `translate(${(ex - sx).toFixed(1)}px, ${(ey - sy).toFixed(1)}px)`;
      }));
      timer(() => {
        ghost.style.opacity = "0";
      }, 750);
      timer(() => {
        ghost.remove();
        state.fxNodes.delete(ghost);
        if (onDone) onDone();
      }, 980);
    }

    // ── 21-hour strip (bottom of board) ──────────────────────
    function buildHourStrip() {
      hourStripEl.innerHTML = "";
      for (let h = 0; h < 21; h++) {
        const c = document.createElement("div");
        c.className = "mn-season-hour-cell";
        hourStripEl.appendChild(c);
      }
    }
    function clearHourStrip() {
      Array.from(hourStripEl.children).forEach((c) => c.classList.remove("is-live", "is-done"));
    }
    function lightHour(h) {
      const cells = Array.from(hourStripEl.children);
      cells.forEach((c) => c.classList.remove("is-live"));
      if (h < 1 || h > 21) return;
      cells[h - 1].classList.add("is-live");
      for (let i = 0; i < h - 1; i++) cells[i].classList.add("is-done");
    }
    function fillAllHours() {
      Array.from(hourStripEl.children).forEach((c) => {
        c.classList.remove("is-live");
        c.classList.add("is-done");
      });
    }

    // ── season strip overlay (only visible in stage 4) ───────
    function buildStripOverlay() {
      stripBlocksEl.innerHTML = "";
      for (let i = 0; i < 7; i++) {
        const n = document.createElement("div");
        n.className = "mn-season-strip-block";
        n.dataset.kind = "night";
        n.innerHTML =
          `<div class="mn-season-strip-block-name">N${i + 1}</div>` +
          `<div class="mn-season-strip-block-sub">nox</div>`;
        stripBlocksEl.appendChild(n);
        const d = document.createElement("div");
        d.className = "mn-season-strip-block";
        d.dataset.kind = "day";
        d.innerHTML =
          `<div class="mn-season-strip-block-name">D${i + 1}</div>` +
          `<div class="mn-season-strip-block-sub">day</div>`;
        stripBlocksEl.appendChild(d);
      }
    }
    function resetStripOverlay() {
      Array.from(stripBlocksEl.children).forEach((b) => {
        b.classList.remove("is-revealed", "is-current");
      });
    }
    function stepStripCurrent(idx) {
      Array.from(stripBlocksEl.children).forEach((b, i) => {
        b.classList.remove("is-current");
        if (i <= idx) b.classList.add("is-revealed");
        if (i === idx) b.classList.add("is-current");
      });
    }

    // ── full board reset (base state, keep earth-score option) ─
    function resetBoard(opts) {
      opts = opts || {};
      for (let i = 0; i < total; i++) {
        const cellEl = boardCell(board, i);
        setFog(cellEl, true);
        setEntity(cellEl, "");
        const t = cellEl.querySelector(".mn-cell-trail");
        t.classList.remove("is-on");
        t.textContent = "";
        cellEl.classList.remove("is-live", "is-echo");
        const b = base[i];
        setTerrain(cellEl, b.tile, b.purity);
      }
      state.harvester = { x: 0, y: 0, alive: false };
      state.probeCell = null;
      _cancelHeatRaf();
      _heatClearAllCells();
      state.heatCells = null;
      state.heatApplied = false;
      if (!opts.keepVault) {
        state.vault = [];
        paintVault([]);
      }
      if (!opts.keepEarth) {
        state.earthScore = 0;
        earthScoreEl.textContent = "0";
      }
      clearHourStrip();
    }

    // ── high-level operations ────────────────────────────────
    function dropProbeAt(x, y, onLanded) {
      const cell = boardCellAt(x, y);
      spawnProbeTrail(cell, P1_HEX, P1_HEX, () => {
        if (state.stopped) return;
        setProbe(cell, 3, P1_COLOR);
        state.probeCell = cell;
        // Reveal disk (radius 4)
        const r = 4, r2 = r * r;
        for (let y2 = y - r; y2 <= y + r; y2++) {
          for (let x2 = x - r; x2 <= x + r; x2++) {
            if (x2 < 0 || x2 >= cols || y2 < 0 || y2 >= rows) continue;
            const dx = x2 - x, dy = y2 - y;
            if (dx * dx + dy * dy <= r2) setFog(boardCellAt(x2, y2), false);
          }
        }
        pushLog("probe", `probe landed at (${x},${y}) — disk goes LIVE`);
        if (onLanded) onLanded();
      }, 900, state);
    }

    function dropHarvesterAt(x, y, onLanded) {
      const cell = boardCellAt(x, y);
      runOrbitalArcAnimation(board, cell, "drop", P1_COLOR, GLYPH_HARVESTER, () => {
        if (state.stopped) return;
        setEntity(cell, GLYPH_HARVESTER, P1_COLOR);
        setFog(cell, false);
        state.harvester = { x, y, alive: true };
        // Trail glyph on landing cell
        const t = cell.querySelector(".mn-cell-trail");
        t.textContent = CH_LIGHT; t.classList.add("is-on");
        // If landing on RED, harvest immediately
        const b = base[idxAt(x, y)];
        if (b && b.tile === TILE.RED) {
          setTerrain(cell, TILE.GREEN, 255);
          spawnHarvestFxLocal(cell, "#ff4040");
          bumpVault("#ff5040");
          pushLog("harvest", `H01 · harvester lands on RED (${x},${y}) · vault +1`);
        } else {
          pushLog("harvest", `harvester lands at (${x},${y})`);
        }
        if (onLanded) onLanded();
      }, state);
    }

    function pickupHarvester(onDone) {
      if (!state.harvester.alive) { if (onDone) onDone(); return; }
      const cell = boardCellAt(state.harvester.x, state.harvester.y);
      runOrbitalArcAnimation(board, cell, "pickup", P1_COLOR, GLYPH_HARVESTER, () => {
        if (state.stopped) return;
        setEntity(cell, "");
        state.harvester.alive = false;
        pushLog("harvest", "orblift — harvester + cargo returned to platform");
        if (onDone) onDone();
      }, state);
    }

    function walkSteps(steps, onDone) {
      let i = 0;
      const HOUR_MS = 380;
      function next() {
        if (state.stopped) return;
        if (i >= steps.length) { if (onDone) onDone(); return; }
        const [dx, dy] = steps[i];
        const px = state.harvester.x, py = state.harvester.y;
        const nx = px + dx, ny = py + dy;
        const prevCell = boardCellAt(px, py);
        const nextCell = boardCellAt(nx, ny);
        setEntity(prevCell, "");
        animateStepLocal(prevCell, nextCell, P1_COLOR, "#ff4040", () => {
          state.harvester.x = nx; state.harvester.y = ny;
          setEntity(nextCell, GLYPH_HARVESTER, P1_COLOR);
          setFog(nextCell, false);
          const t = nextCell.querySelector(".mn-cell-trail");
          t.textContent = CH_LIGHT; t.classList.add("is-on");
          const b = base[idxAt(nx, ny)];
          if (b && b.tile === TILE.RED) {
            setTerrain(nextCell, TILE.GREEN, 255);
            bumpVault("#ff5040");
            pushLog("harvest", `harvester scoops RED at (${nx},${ny}) · vault +1`);
          }
          i++;
          state.timers.push(setTimeout(next, HOUR_MS));
        });
      }
      next();
    }

    // ── stages ───────────────────────────────────────────────
    const STAGES = [
      // 0 · NOX · 21 HOURS — mini-play a Nox with real board graphics
      {
        label: "0 · NOX · 21 HOURS",
        body:
          '<p>A <span class="kw">NOX</span> is 21 hours of PRAXIS. Each seat pre-plans a 21-slot policy in orbit and it all fires simultaneously when night opens.</p>' +
          '<p>Watch the hour strip along the bottom — the harvester walks the seam, banks RED into the vault (top-left of your platform).</p>',
        cite: "§3.2 · Nox · §3.10 · policy",
        settle: () => {
          stageEl.classList.remove("is-zoomed");
          stripOverlayEl.hidden = true;
          resetBoard();
          setSticker("NOX 1 · PRAXIS", null);
          phaseEl.textContent = "# Nox 1 · 21 hours · policy fires";
          statusEl.textContent = "# stage 0 · Nox · 21 hours";
        },
        animate: () => {
          pushLog("stage", "NOX 1 · 21 hours of PRAXIS begin");
          // Probe drops from orbit → live disk opens
          timer(() => {
            dropProbeAt(8, 6, () => {
              // Harvester drops onto seam
              timer(() => {
                dropHarvesterAt(6, 5, () => {
                  // Walk through the seam over the remaining "hours"
                  const steps = [[1,0],[0,1],[1,0],[0,1],[1,0]];
                  // Kick off the hour ticker in parallel
                  const HOUR_TICK = 130;
                  for (let h = 1; h <= 21; h++) {
                    timer(() => lightHour(h), h * HOUR_TICK);
                  }
                  timer(() => fillAllHours(), 21 * HOUR_TICK + 60);
                  walkSteps(steps);
                });
              }, 300);
            });
          }, 200);
        },
        dur: 21 * 130 + 2600,
      },

      // 1 · AURORA — engine heat sweep; vault survives
      {
        label: "1 · AURORA",
        body:
          '<p><span class="kw">AURORA</span> ends the Nox. Heat sweeps the surface — anything left on the planet is incinerated. Probes are the only surface thing that survives.</p>' +
          '<p>The <span class="kw">vault</span> is banked in orbit already — it survives Aurora. That\'s why pickup timing matters.</p>',
        cite: "§3.2 · Aurora",
        settle: () => {
          stageEl.classList.remove("is-zoomed");
          stripOverlayEl.hidden = true;
          fillAllHours();
          setSticker("AURORA \u00b7 Nox 1 closes", "is-aurora");
          phaseEl.textContent = "# Aurora \u00b7 surface burn \u00b7 vault safe";
          statusEl.textContent = "# stage 1 · Aurora";
        },
        animate: () => {
          pushLog("aurora", "AURORA \u00b7 heat sweep begins \u00b7 surface burns");
          timer(() => {
            playAuroraSweepLocal(_liveProbeIdxs(), () => {
              pushLog("aurora", "Aurora peak \u00b7 vault intact \u00b7 " + state.vault.length + " parcels banked");
            });
          }, 200);
        },
        dur: 2200,
      },

      // 2 · DAY · ORBITAL · 3 actions — the SHIP action fires a parcel
      {
        label: "2 · DAY · ORBITAL",
        body:
          '<p>After Aurora comes <span class="kw">DAY</span> — 3 orbital actions. Repair equipment, refine RED, and <span class="kw">SHIP</span> parcels home to Earth.</p>' +
          '<p>Only shipped parcels count as score. Everything else — planet, orbit — is either lost or in-flight.</p>',
        cite: "§4 · orbital phase",
        settle: () => {
          stageEl.classList.remove("is-zoomed");
          stripOverlayEl.hidden = true;
          setSticker("DAY 1 \u00b7 ORBITAL \u00b7 S1 REPAIR", "is-day");
          phaseEl.textContent = "# Day 1 \u00b7 orbital \u00b7 3 actions";
          statusEl.textContent = "# stage 2 \u00b7 day \u00b7 orbital";
        },
        animate: () => {
          pushLog("stage", "DAY 1 opens \u00b7 3 orbital actions available");
          // Slot 1: REPAIR — diamond pulse
          timer(() => {
            setSticker("DAY 1 \u00b7 ORBITAL \u00b7 S1 REPAIR", "is-day");
            pulseStation();
            pushLog("stage", "S1 \u00b7 REPAIR \u00b7 platform pulses");
          }, 200);
          // Slot 2: REFINE
          timer(() => {
            setSticker("DAY 1 \u00b7 ORBITAL \u00b7 S2 REFINE", "is-day");
            pulseStation();
            pushLog("stage", "S2 \u00b7 REFINE \u00b7 red processed");
          }, 1200);
          // Slot 3: SHIP — parcel arcs from diamond to earth
          timer(() => {
            setSticker("DAY 1 \u00b7 ORBITAL \u00b7 S3 SHIP", "is-day");
            pulseStation();
            const parcels = Math.max(1, state.vault.length);
            const nShip = Math.min(3, parcels);
            for (let i = 0; i < nShip; i++) {
              timer(() => {
                shipParcel(() => {
                  drainVaultOne();
                  tickEarthScore(1);
                });
                pushLog("aurora", `S3 \u00b7 SHIP \u00b7 parcel launched to Earth (${i + 1}/${nShip})`);
              }, i * 500);
            }
          }, 2400);
        },
        dur: 5200,
      },

      // 3 · VESPERA → new Nox
      {
        label: "3 · VESPERA \u2192 NOX 2",
        body:
          '<p><span class="kw">VESPERA</span> at dusk cools the surface back down and the magnetic fog closes back in.</p>' +
          '<p>A fresh <span class="kw">NOX 2</span> opens with a new 21-hour policy. This is the loop the whole game runs on.</p>',
        cite: "§3.2 · Vespera",
        settle: () => {
          stageEl.classList.remove("is-zoomed");
          stripOverlayEl.hidden = true;
          setSticker("VESPERA \u00b7 Nox 2 opens", "is-vespera");
          phaseEl.textContent = "# Vespera \u00b7 fog closes \u00b7 new Nox";
          statusEl.textContent = "# stage 3 \u00b7 Vespera";
        },
        animate: () => {
          pushLog("aurora", "VESPERA \u00b7 heat cools \u00b7 fog closes back in");
          timer(() => {
            playVesperaSweepLocal(() => {
              // Refog + fresh Nox
              resetBoard({ keepVault: true, keepEarth: true });
              setSticker("NOX 2 \u00b7 PRAXIS", null);
              pushLog("stage", "NOX 2 opens \u00b7 fresh 21 hours \u00b7 same policy shape");
              // Fresh probe + harvester drop, partial walk to hint continuity
              timer(() => {
                dropProbeAt(9, 5, () => {
                  timer(() => {
                    dropHarvesterAt(8, 6, () => {
                      const HOUR_TICK = 100;
                      for (let h = 1; h <= 21; h++) {
                        timer(() => lightHour(h), h * HOUR_TICK);
                      }
                      walkSteps([[1,0],[0,1],[1,0]]);
                    });
                  }, 200);
                });
              }, 200);
            });
          }, 200);
        },
        dur: 5400,
      },

      // 4 · SEASON · 7 nights + 7 days (zoom out)
      {
        label: "4 · SEASON \u00b7 7 NIGHTS + 7 DAYS",
        body:
          '<p>Zoom out: the game is <span class="kw">7 nights + 7 days</span>. Between each Nox comes an <span class="kw">Aurora</span> (surface burn), a <span class="kw">day</span> of 3 orbital actions, and a <span class="kw">Vespera</span> (dusk).</p>' +
          '<p>The season ends on <b>Day 7</b>. Highest EARTH score wins.</p>',
        cite: "§3.2 · season length",
        settle: () => {
          stageEl.classList.add("is-zoomed");
          stripOverlayEl.hidden = false;
          resetStripOverlay();
          setSticker("SEASON \u00b7 14 PHASES", "is-day");
          phaseEl.textContent = "# season \u00b7 7 nights + 7 days";
          statusEl.textContent = "# stage 4 \u00b7 season \u00b7 zoom out";
        },
        animate: () => {
          pushLog("stage", "SEASON \u00b7 7 nights + 7 days \u00b7 ends on Day 7");
          const blocks = Array.from(stripBlocksEl.children);
          const step = 220;
          for (let i = 0; i < blocks.length; i++) {
            timer(() => {
              blocks[i].classList.add("is-revealed");
              stepStripCurrent(i);
              if (i % 2 === 1) {
                // Day slot — bump earth score a bit to show shipping
                timer(() => tickEarthScore(1 + Math.floor(Math.random() * 3)), 60);
              }
            }, i * step);
          }
        },
        dur: 14 * 220 + 500,
      },

      // 5 · FULL LOOP — compressed 2-loop harvest→vault→ship pipeline
      {
        label: "5 · FULL LOOP",
        body:
          '<p>Full pipeline: harvest RED in the night into the platform\'s <span class="kw">vault</span>, then ship from orbit to <span class="kw">Earth</span> during the day.</p>' +
          '<p>Aurora burns the planet between them. Watch the SHIPPED score climb — only what reaches Earth counts.</p>',
        cite: "§3.2 · loop · §4.7 · shipping",
        settle: () => {
          stageEl.classList.remove("is-zoomed");
          stripOverlayEl.hidden = true;
          resetBoard({ keepEarth: true });
          setSticker("NOX 1 \u00b7 PRAXIS", null);
          phaseEl.textContent = "# full loop \u00b7 harvest \u2192 vault \u2192 ship";
          statusEl.textContent = "# stage 5 \u00b7 full loop";
        },
        animate: () => {
          pushLog("stage", "FULL LOOP \u00b7 2 nights + 2 ships");
          // Loop 1
          const T0 = 200;
          timer(() => setSticker("NOX 1 \u00b7 PRAXIS", null), T0);
          timer(() => {
            dropProbeAt(8, 6, () => {
              timer(() => {
                dropHarvesterAt(6, 5, () => {
                  walkSteps([[1,0],[0,1],[1,0]]);
                });
              }, 200);
            });
          }, T0 + 100);
          // Aurora
          const T1 = T0 + 4200;
          timer(() => {
            setSticker("AURORA \u00b7 Nox 1 closes", "is-aurora");
            playAuroraSweepLocal(_liveProbeIdxs());
          }, T1);
          // Day 1: SHIP
          const T2 = T1 + 1400;
          timer(() => {
            setSticker("DAY 1 \u00b7 ORBITAL \u00b7 SHIP", "is-day");
            pulseStation();
            const n = Math.min(3, state.vault.length || 2);
            for (let i = 0; i < n; i++) {
              timer(() => shipParcel(() => { drainVaultOne(); tickEarthScore(1); }), i * 420);
            }
          }, T2);
          // Vespera → new Nox
          const T3 = T2 + 1800;
          timer(() => {
            setSticker("VESPERA \u00b7 Nox 2 opens", "is-vespera");
            playVesperaSweepLocal(() => {
              resetBoard({ keepVault: true, keepEarth: true });
              setSticker("NOX 2 \u00b7 PRAXIS", null);
              // Loop 2 (shorter)
              dropProbeAt(11, 7, () => {
                timer(() => {
                  dropHarvesterAt(9, 6, () => {
                    walkSteps([[0,1],[1,0]]);
                  });
                }, 200);
              });
            });
          }, T3);
          // Aurora 2 + Ship 2
          const T4 = T3 + 4000;
          timer(() => {
            setSticker("AURORA \u00b7 Nox 2 closes", "is-aurora");
            playAuroraSweepLocal(_liveProbeIdxs());
          }, T4);
          const T5 = T4 + 1400;
          timer(() => {
            setSticker("DAY 2 \u00b7 ORBITAL \u00b7 SHIP", "is-day");
            pulseStation();
            const n = Math.min(2, state.vault.length || 1);
            for (let i = 0; i < n; i++) {
              timer(() => shipParcel(() => { drainVaultOne(); tickEarthScore(1); }), i * 420);
            }
          }, T5);
          // Final settle
          timer(() => {
            setSticker("... and 5 more nights", "is-vespera");
            pushLog("stage", "the loop continues \u2014 5 more nights to Day 7");
          }, T5 + 1500);
        },
        dur: 14000,
      },
    ];

    function updateCaption(idx) {
      const s = STAGES[idx];
      labelEl.textContent = s.label;
      bodyEl.innerHTML    = s.body;
      citeEl.textContent  = s.cite;
    }

    function goStage(idx) {
      idx = ((idx % STAGES.length) + STAGES.length) % STAGES.length;
      state.timers.forEach((t) => clearTimeout(t));
      state.timers = [];
      state.fxNodes.forEach((n) => n.remove());
      state.fxNodes.clear();
      _cancelHeatRaf();
      if (idx === 0) clearLog();
      state.stageIdx = idx;
      STAGES[idx].settle();
      updateCaption(idx);
      STAGES[idx].animate();
      if (state.autoPlay) {
        state.timers.push(setTimeout(() => {
          if (state.stopped) return;
          goStage(idx + 1 >= STAGES.length ? 0 : idx + 1);
        }, STAGES[idx].dur));
      }
    }
    state.goStage = goStage;

    btnPrev.onclick    = () => goStage(state.stageIdx - 1);
    btnNext.onclick    = () => goStage(state.stageIdx + 1);
    btnToggle.textContent = "[ \u23f5 PLAY ]";
    btnToggle.onclick  = () => {
      state.autoPlay = !state.autoPlay;
      btnToggle.textContent = state.autoPlay ? "[ \u23f8 PAUSE ]" : "[ \u23f5 PLAY ]";
      if (state.autoPlay) {
        state.timers.push(setTimeout(() => {
          if (state.stopped) return;
          const next = state.stageIdx + 1;
          goStage(next >= STAGES.length ? 0 : next);
        }, STAGES[state.stageIdx].dur));
      }
    };
    btnRestart.onclick = () => {
      state.autoPlay = false;
      btnToggle.textContent = "[ \u23f5 PLAY ]";
      goStage(0);
    };

    // ── init ─────────────────────────────────────────────────
    buildDiamond();
    paintVault([]);
    buildHourStrip();
    buildStripOverlay();
    stationScoreEl.textContent = "0";
    earthScoreEl.textContent = "0";
    goStage(0);
  }

  // ═══════════════════════════════════════════════════════════════
  // TAB 9 — PROBES · deep dive (5 sections)
  //   0 · Probe = vision — probe drops, disk reveals red, harvester
  //       drops into the disk. Teaches "probes exist to see red."
  //   1 · Probe life — one Aurora at a time (3 ticks), rings drop
  //       3 → 2 → 1 → destroyed, disk turns ECHO.
  //   2 · Probe crush — two seats each drop a probe, harvesters walk
  //       over shared red seam, both leave ECHO. Then P1 crushes P2's
  //       probe by walking onto its cell.
  //   3 · EMP salvo — 3 cyan missiles fan out and detonate cyan r=2
  //       Chebyshev clouds; any probe inside is fried.
  //   4 · Placeholder — reserved for future explanation.
  // ═══════════════════════════════════════════════════════════════
  let tab9_state = null;
  function tab9_stop() {
    if (tab9_state) {
      tab9_state.stopped = true;
      tab9_state.timers.forEach((t) => clearTimeout(t));
      tab9_state.timers = [];
      if (tab9_state.heatRaf) {
        cancelAnimationFrame(tab9_state.heatRaf);
        tab9_state.heatRaf = null;
      }
      if (tab9_state.stageCleanup) {
        try { tab9_state.stageCleanup(); } catch (_) {}
        tab9_state.stageCleanup = null;
      }
      tab9_state.fxNodes.forEach((n) => n.remove());
      tab9_state.fxNodes.clear();
      tab9_state = null;
    }
  }

  function tab9_start() {
    tab9_stop();

    // ── DOM refs ─────────────────────────────────────────────────
    const boardHost  = document.getElementById("mn-board-probes");
    const stickerEl  = document.getElementById("mn-probes-sticker");
    const lifeBadgeEl= document.getElementById("mn-probes-life-badge");
    const lifeRingsEl= document.getElementById("mn-probes-life-rings");
    const lifeNightsEl=document.getElementById("mn-probes-life-nights");
    const labelEl    = document.getElementById("mn-stage-label-9");
    const bodyEl     = document.getElementById("mn-stage-body-9");
    const citeEl     = document.getElementById("mn-stage-cite-9");
    const phaseEl    = document.getElementById("mn-probes-phase");
    const statusEl   = document.getElementById("mn-probes-status");
    const btnPrev    = document.getElementById("mn-probes-prev");
    const btnNext    = document.getElementById("mn-probes-next");
    const btnToggle  = document.getElementById("mn-probes-toggle");
    const btnRestart = document.getElementById("mn-probes-restart");

    // ── board setup ─────────────────────────────────────────────
    const cols = 22, rows = 10;
    const cellW = 24, cellH = 24;
    const total = cols * rows;
    const base = new Array(total);
    for (let i = 0; i < total; i++) base[i] = { tile: TILE.EMPTY, purity: 0, fog: true };
    const cells = base.map((c) => ({ ...c }));
    const board = renderBoard(boardHost, cells, { cols, rows, cellW, cellH });

    // ── state ───────────────────────────────────────────────────
    const state = {
      stopped: false, timers: [], fxNodes: new Set(),
      stageIdx: 0, autoPlay: false,
      heatCells: null, heatRaf: null, heatApplied: false,
    };
    tab9_state = state;

    const idxAt = (x, y) => y * cols + x;
    const timer = (fn, ms) => {
      const t = setTimeout(() => { if (state.stopped) return; fn(); }, ms);
      state.timers.push(t);
      return t;
    };
    const P1_VAR = "--seat-p1"; const P1_HEX = "#8ac0ff";
    const P2_VAR = "--seat-p2"; const P2_HEX = "#ff6d6d";
    const P3_VAR = "--seat-p3"; const P3_HEX = "#7be49a";
    const RED_HEX   = "#ff4d4d";
    const GREEN_HEX = "#3fb950";  // matches GREEN_FG "rgb(63,185,80)"

    // ── helpers ─────────────────────────────────────────────────
    const boardCellAt = (x, y) => boardCell(board, idxAt(x, y));
    function pushLog(kind, msg) {
      const log = document.getElementById("mn-eventlog-9");
      if (!log) return;
      const line = document.createElement("div");
      line.className = `mn-log mn-log--${kind}`;
      line.textContent = `# ${msg}`;
      log.prepend(line);
      while (log.children.length > 40) log.removeChild(log.lastChild);
    }
    function clearLog() {
      const log = document.getElementById("mn-eventlog-9");
      if (log) log.innerHTML = "";
    }
    function setSticker(text, cls) {
      if (!stickerEl) return;
      stickerEl.textContent = text;
      stickerEl.classList.remove("is-aurora", "is-emp");
      if (cls) stickerEl.classList.add(cls);
      stickerEl.hidden = false;
      // eslint-disable-next-line no-unused-expressions
      stickerEl.offsetHeight;
      stickerEl.classList.add("is-on");
    }
    function hideSticker() {
      if (!stickerEl) return;
      stickerEl.classList.remove("is-on");
      timer(() => { if (stickerEl) stickerEl.hidden = true; }, 260);
    }
    function setLifeBadge(rings, nights, dead) {
      if (!lifeBadgeEl) return;
      lifeRingsEl.textContent = rings;
      lifeNightsEl.textContent = nights;
      lifeBadgeEl.classList.toggle("is-dead", !!dead);
      lifeBadgeEl.hidden = false;
      // eslint-disable-next-line no-unused-expressions
      lifeBadgeEl.offsetHeight;
      lifeBadgeEl.classList.add("is-on");
    }
    function hideLifeBadge() {
      if (!lifeBadgeEl) return;
      lifeBadgeEl.classList.remove("is-on");
      timer(() => { if (lifeBadgeEl) lifeBadgeEl.hidden = true; }, 260);
    }

    // ── disk helpers ────────────────────────────────────────────
    function eucDisk(cx, cy, r) {
      const out = [];
      const r2 = r * r;
      for (let y = Math.max(0, cy - r); y <= Math.min(rows - 1, cy + r); y++) {
        for (let x = Math.max(0, cx - r); x <= Math.min(cols - 1, cx + r); x++) {
          const dx = x - cx, dy = y - cy;
          if (dx * dx + dy * dy <= r2) out.push(idxAt(x, y));
        }
      }
      return out;
    }
    function chebDisk(cx, cy, r) {
      const out = [];
      for (let y = Math.max(0, cy - r); y <= Math.min(rows - 1, cy + r); y++) {
        for (let x = Math.max(0, cx - r); x <= Math.min(cols - 1, cx + r); x++) {
          out.push(idxAt(x, y));
        }
      }
      return out;
    }

    // ── board reset ─────────────────────────────────────────────
    function resetBoard(opts) {
      opts = opts || {};
      _heatClearAllCells();
      for (let i = 0; i < total; i++) {
        const cellEl = boardCell(board, i);
        setEntity(cellEl, "", null);
        cellEl.classList.remove("is-echo", "mn-cell-dawn-decay");
        // Clear terrain
        setTerrain(cellEl, TILE.EMPTY, 0);
        setFog(cellEl, true);
      }
      if (opts.reds) {
        for (const s of opts.reds) {
          const cellEl = boardCellAt(s.x, s.y);
          setTerrain(cellEl, TILE.RED, s.purity || 180);
        }
      }
    }

    // ── engine Aurora sweep (ported) ────────────────────────────
    const CELL_BG_RGB = [14, 11, 22];
    function _heatClearAllCells() {
      Array.from(board.children).forEach((c) => {
        c.style.background = "";
        const terr = c.querySelector(".mn-cell-terrain");
        if (terr) { terr.style.filter = ""; terr.style.textShadow = ""; terr.style.transform = ""; }
        const fog = c.querySelector(".mn-cell-fog");
        if (fog) { fog.textContent = CH_LIGHT; fog.style.color = ""; fog.style.opacity = ""; }
        c.classList.remove("mn-cell-dawn-decay");
      });
    }
    function _applyHeat(c, h, wallT, probeIdxSet, onProbePassed, front) {
      const isFog = c.el.classList.contains("is-fogged");
      if (h < 0.015) {
        c.el.style.background = "";
        if (c.terr) { c.terr.style.filter = ""; c.terr.style.textShadow = ""; c.terr.style.transform = ""; }
        if (c.fog)  { c.fog.textContent = CH_LIGHT; c.fog.style.color = ""; }
        return;
      }
      if (isFog && c.fog) {
        c.fog.textContent = "\u2592\u2592";
        const w = Math.round(90 + h * 165);
        c.fog.style.color = `rgb(${w},${w},${w})`;
        const br = Math.round(15 + h * 22);
        const bg = Math.round(12 + h * 14);
        const bb = Math.round(24 + h * 16);
        c.el.style.background = `rgba(${br},${bg},${bb},0.96)`;
        if (c.terr) c.terr.style.filter = "";
      } else if (c.terr) {
        const sat = (1 + h * 1.5).toFixed(2);
        const bri = (1 + h * 0.45).toFixed(2);
        c.terr.style.filter = `saturate(${sat}) brightness(${bri})`;
        const [cr, cg, cb] = CELL_BG_RGB;
        const lr = Math.min(255, Math.round(cr + h * 42));
        const lg = Math.min(255, Math.round(cg + h * 32));
        const lb = Math.min(255, Math.round(cb + h * 24));
        c.el.style.background = `rgb(${lr},${lg},${lb})`;
      }
      if (c.terr) {
        const glowA = Math.max(0, (h - 0.2) / 0.8);
        const blur  = Math.round(3 + glowA * 5);
        const a     = (glowA * 0.7).toFixed(2);
        c.terr.style.textShadow = `0 0 ${blur}px rgba(255,200,80,${a})`;
        if (wallT > 0 && h > 0.15) {
          const t   = wallT * 0.001;
          const amp = 1.8 * Math.min(1, h * 1.6);
          const dx = (Math.sin(c.cx * 0.55 + t * 4.3 + c.cy * 0.31) * amp).toFixed(1);
          const dy = (Math.cos(c.cy * 0.63 + t * 3.8 + c.cx * 0.44) * amp * 0.5).toFixed(1);
          c.terr.style.transform = `translate(${dx}px, ${dy}px)`;
        }
      }
      if (probeIdxSet && probeIdxSet.has(c.idx) && front !== undefined && front - c.d > 0) {
        onProbePassed(c.idx);
      }
    }
    function playAuroraSweepLocal(probeIdxs, onProbePassed, onDone) {
      const boardCells = Array.from(board.children);
      const cellData = boardCells.map((el, i) => ({
        el, idx: i,
        terr: el.querySelector(".mn-cell-terrain"),
        fog:  el.querySelector(".mn-cell-fog"),
        cx: i % cols,
        cy: Math.floor(i / cols),
        d:  (i % cols) * 0.85 + Math.floor(i / cols) * 1.15,
      }));
      state.heatCells = cellData;
      let maxD = 0;
      for (const c of cellData) if (c.d > maxD) maxD = c.d;
      const MIN_D = -4, MAX_D = maxD + 6;
      const durIn = 1000, rate = (MAX_D - MIN_D) / durIn, holdDur = 60;
      let front = MIN_D, lastTs = null, holdStart = 0, phase = "in", onDoneFired = false;
      const probeSet = new Set(probeIdxs || []);
      const probeFired = new Set();
      function heatLevel(d, front) {
        const dist = front - d;
        if (dist < -2) return 0;
        if (dist <  2) return Math.max(0, (dist + 2) / 4);
        if (dist <  6) return 1.0 - ((dist - 2) / 4) * 0.48;
        return 0.52;
      }
      function firedProbe(idx) {
        if (probeFired.has(idx)) return;
        probeFired.add(idx);
        const probeCell = boardCell(board, idx);
        probeCell.classList.add("mn-cell-dawn-decay");
        state.timers.push(setTimeout(() => probeCell.classList.remove("mn-cell-dawn-decay"), 640));
        if (onProbePassed) try { onProbePassed(idx); } catch (_) {}
      }
      function frame(ts) {
        if (state.stopped) return;
        if (lastTs === null) lastTs = ts;
        const dt = Math.min(ts - lastTs, 50); lastTs = ts;
        if (phase === "in") {
          front += rate * dt;
          for (const c of cellData) _applyHeat(c, heatLevel(c.d, front), ts, probeSet, firedProbe, front);
          if (front >= MAX_D) { phase = "hold"; holdStart = ts; }
        } else {
          for (const c of cellData) _applyHeat(c, 0.52, ts, probeSet, () => {}, front);
          if (!onDoneFired && ts - holdStart >= holdDur) {
            onDoneFired = true;
            state.heatApplied = true;
            if (onDone) try { onDone(); } catch (_) {}
            return;
          }
        }
        state.heatRaf = requestAnimationFrame(frame);
      }
      state.heatRaf = requestAnimationFrame(frame);
    }
    function playVesperaSweepLocal(onDone) {
      const cellData = state.heatCells || Array.from(board.children).map((el, i) => ({
        el, idx: i,
        terr: el.querySelector(".mn-cell-terrain"),
        fog:  el.querySelector(".mn-cell-fog"),
        cx: i % cols,
        cy: Math.floor(i / cols),
        d:  (i % cols) * 0.85 + Math.floor(i / cols) * 1.15,
      }));
      let maxD = 0;
      for (const c of cellData) if (c.d > maxD) maxD = c.d;
      const MIN_D = -4, MAX_D = maxD + 6;
      const durOut = 850, rate = (MAX_D - MIN_D) / durOut;
      let front = MIN_D, lastTs = null;
      function coolLevel(d, front) {
        const dist = front - d;
        if (dist < -2) return 0.52;
        if (dist <  2) return 0.52 * (1 - (dist + 2) / 4);
        return 0;
      }
      function frame(ts) {
        if (state.stopped) return;
        if (lastTs === null) lastTs = ts;
        const dt = Math.min(ts - lastTs, 50); lastTs = ts;
        front += rate * dt;
        for (const c of cellData) _applyHeat(c, coolLevel(c.d, front), ts, null, () => {}, front);
        if (front < MAX_D) {
          state.heatRaf = requestAnimationFrame(frame);
        } else {
          _heatClearAllCells();
          state.heatApplied = false;
          state.heatCells = null;
          if (onDone) try { onDone(); } catch (_) {}
        }
      }
      state.heatRaf = requestAnimationFrame(frame);
    }

    // ── harvester step (ported) ─────────────────────────────────
    function spawnHarvestFxLocal(cell, color) {
      const rect = cell.getBoundingClientRect();
      const cx = rect.left + rect.width * 0.5;
      const cy = rect.top + rect.height * 0.5;
      const blink = document.createElement("div");
      blink.className = "mn-harvest-blink";
      blink.style.setProperty("--blink-color", color);
      cell.appendChild(blink);
      state.fxNodes.add(blink);
      blink.addEventListener("animationend", () => { blink.remove(); state.fxNodes.delete(blink); }, { once: true });
      const N = 8;
      for (let i = 0; i < N; i++) {
        const angle = (i / N) * Math.PI * 2 + (Math.random() - 0.5) * 0.4;
        const dist = rect.width * (1.8 + Math.random() * 1.4);
        const p = document.createElement("div");
        p.className = "mn-harvest-particle";
        p.style.left = `${cx.toFixed(1)}px`;
        p.style.top  = `${cy.toFixed(1)}px`;
        const sz = Math.max(2, Math.round(rect.width * 0.22));
        p.style.width  = `${sz}px`;
        p.style.height = `${sz}px`;
        p.style.setProperty("--dx", `${(Math.cos(angle) * dist).toFixed(1)}px`);
        p.style.setProperty("--dy", `${(Math.sin(angle) * dist).toFixed(1)}px`);
        p.style.background = color;
        p.style.animationDelay = `${Math.round(Math.random() * 40)}ms`;
        document.body.appendChild(p);
        state.fxNodes.add(p);
        p.addEventListener("animationend", () => { p.remove(); state.fxNodes.delete(p); }, { once: true });
      }
    }
    function animateStepLocal(prevCell, nextCell, seatVar, blinkColor, onArrive) {
      const prevEntity = prevCell.querySelector(".mn-cell-entity");
      const nextEntity = nextCell.querySelector(".mn-cell-entity");
      prevEntity.textContent = "";
      const savedNextText = nextEntity.textContent;
      nextEntity.textContent = "";
      const pr = prevCell.getBoundingClientRect();
      const nr = nextCell.getBoundingClientRect();
      const ghost = document.createElement("span");
      ghost.className = "mn-step-ghost";
      ghost.textContent = GLYPH_HARVESTER;
      ghost.style.left = `${pr.left}px`;
      ghost.style.top  = `${pr.top}px`;
      ghost.style.width  = `${pr.width}px`;
      ghost.style.height = `${pr.height}px`;
      ghost.style.color  = `var(${seatVar})`;
      ghost.style.fontSize = `${Math.round(pr.width * 0.7)}px`;
      document.body.appendChild(ghost);
      state.fxNodes.add(ghost);
      const dx = nr.left - pr.left;
      const dy = nr.top  - pr.top;
      let done = false;
      const finish = () => {
        if (done || state.stopped) return;
        done = true;
        ghost.remove();
        state.fxNodes.delete(ghost);
        if (savedNextText) nextEntity.textContent = savedNextText;
        onArrive();
        if (blinkColor) spawnHarvestFxLocal(nextCell, blinkColor);
      };
      requestAnimationFrame(() => requestAnimationFrame(() => {
        ghost.style.transform = `translate(${dx.toFixed(1)}px, ${dy.toFixed(1)}px)`;
      }));
      ghost.addEventListener("transitionend", finish, { once: true });
      state.timers.push(setTimeout(finish, 260));
    }

    // ── destruction X overlay — ported from server/static/app.js:8928
    //   Canvas-drawn X: 4 arms grow inward from cell corners (GROW),
    //   snap to a smaller X (SHRINK), hold, then fade out. Used both
    //   for physical crush (red, #ff0000) and EMP fry (cyan, #00e8ff).
    function spawnXOverlayLocal(cellEl, color, delayMs, opts) {
      delayMs = delayMs || 0;
      const thin = !!(opts && opts.thin);
      const cellRect0 = cellEl.getBoundingClientRect();
      const fs = Math.round(cellRect0.width * 0.7);
      const lw   = thin ? Math.max(1.5, fs * 0.13) : Math.max(3, fs * 0.26);
      const SPREAD = thin ? 1.1 : 1.4;
      const GROW = 360, SHRINK = 280, HOLD = 200, FADE = 400;
      // Terminal size of the "settled" X (approx glyph metric).
      const rx_f = fs * 0.30, ry_f = fs * 0.36;
      const t = setTimeout(() => {
        if (state.stopped) return;
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
          `pointer-events:none;z-index:60;`;
        document.body.appendChild(cv);
        state.fxNodes.add(cv);
        const xctx = cv.getContext("2d");
        let t0 = null;
        function tick(ts) {
          if (state.stopped) { cv.remove(); state.fxNodes.delete(cv); return; }
          if (t0 === null) t0 = ts;
          const el = ts - t0;
          if (el >= GROW + SHRINK + HOLD + FADE) {
            xctx.clearRect(0, 0, W, H);
            cv.remove(); state.fxNodes.delete(cv);
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
      state.timers.push(t);
    }

    // EMP cloud density chars — ported from app.js:10138.
    const _EMP_CHARS = ["\u2591\u2591", "\u2591\u2592", "\u2592\u2592", "\u2592\u2593", "\u2593\u2593", "\u2588\u2588"];
    function _empCharAt(gx, gy, t) {
      const v = Math.sin(gx * 0.85 + t * 1.1)
              + Math.sin(gy * 0.72 + t * 0.8)
              + Math.sin((gx - gy) * 0.55 + t * 1.5) * 0.6;
      const norm = Math.max(0, Math.min(1, (v / 2.6 + 1) * 0.5));
      const biased = Math.pow(norm, 2.0);
      return _EMP_CHARS[Math.min(_EMP_CHARS.length - 1, Math.floor(biased * _EMP_CHARS.length))];
    }

    // ── EMP salvo — ported from server/static/app.js:10251 (expansion)
    //   + app.js:10293 (paint cloud) + app.js:8928 (destruction X).
    //   Each missile detonates a Manhattan r=2 cloud. Sequence:
    //     1. Cyan streak flies in (560ms)
    //     2. Ring-staggered .mn-emp-flash ripples out from center
    //        (each cell delay = manhattanDist * 28ms, 100ms per cell)
    //     3. .mn-emp-cloud tiles paint with ASCII density chars,
    //        ticker swirls the glyphs every ~90ms
    //     4. Any probe/harvester inside gets a cyan X overlay
    //     5. Cloud dissipates: density ramps down + fade out
    function fireEmpMissile(tx, ty, delay, onEachHit) {
      timer(() => {
        const targetCell = boardCellAt(tx, ty);
        const trect = targetCell.getBoundingClientRect();
        const cx = trect.left + trect.width * 0.5;
        const cy = trect.top  + trect.height * 0.5;
        // Ghost streak — starts from an off-board corner and travels
        // diagonally to the target.
        const ghost = document.createElement("div");
        ghost.className = "mn-emp-ghost";
        ghost.style.left = `${cx.toFixed(1)}px`;
        ghost.style.top  = `${cy.toFixed(1)}px`;
        const boardRect = boardHost.getBoundingClientRect();
        const startDX = (boardRect.left - cx) - 40;
        const startDY = (boardRect.top  - cy) - 40;
        const rot = Math.atan2(-startDY, -startDX) * 180 / Math.PI;
        ghost.style.transform = `translate(${startDX.toFixed(1)}px, ${startDY.toFixed(1)}px) rotate(${rot.toFixed(1)}deg)`;
        document.body.appendChild(ghost);
        state.fxNodes.add(ghost);
        requestAnimationFrame(() => requestAnimationFrame(() => {
          if (state.stopped) return;
          ghost.classList.add("is-flying");
          ghost.style.transform = `translate(0px, 0px) rotate(${rot.toFixed(1)}deg)`;
        }));
        pushLog("aurora", `EMP missile → (${tx},${ty})`);
        // Impact: ring-staggered flash + cloud after streak arrives.
        timer(() => {
          if (state.stopped) return;
          ghost.remove();
          state.fxNodes.delete(ghost);
          const R = 2;
          const RING_STAGGER = 28; // engine constant
          // 1. Ring-staggered expansion flash — Manhattan disk.
          for (let dy = -R; dy <= R; dy++) {
            for (let dx = -R; dx <= R; dx++) {
              const dist = Math.abs(dx) + Math.abs(dy);
              if (dist > R) continue;
              const gx = tx + dx, gy = ty + dy;
              if (gx < 0 || gx >= cols || gy < 0 || gy >= rows) continue;
              const cellEl = boardCellAt(gx, gy);
              const flash = document.createElement("div");
              flash.className = "mn-emp-flash";
              flash.style.left = "0"; flash.style.top = "0";
              flash.style.right = "0"; flash.style.bottom = "0";
              flash.style.animationDelay = `${dist * RING_STAGGER}ms`;
              cellEl.appendChild(flash);
              state.fxNodes.add(flash);
              flash.addEventListener("animationend", () => {
                flash.remove(); state.fxNodes.delete(flash);
              }, { once: true });
            }
          }
          // 2. Cloud tiles — Manhattan disk, ASCII density glyphs.
          const cloudTiles = [];
          for (let dy = -R; dy <= R; dy++) {
            for (let dx = -R; dx <= R; dx++) {
              if (Math.abs(dx) + Math.abs(dy) > R) continue;
              const gx = tx + dx, gy = ty + dy;
              if (gx < 0 || gx >= cols || gy < 0 || gy >= rows) continue;
              const cellEl = boardCellAt(gx, gy);
              const cloud = document.createElement("div");
              cloud.className = "mn-emp-cloud";
              cloud.style.left = "0"; cloud.style.top = "0";
              cloud.style.right = "0"; cloud.style.bottom = "0";
              cloud.dataset.gx = String(gx);
              cloud.dataset.gy = String(gy);
              cloud.textContent = _empCharAt(gx, gy, 0);
              cellEl.appendChild(cloud);
              state.fxNodes.add(cloud);
              cloudTiles.push(cloud);
            }
          }
          // 3. Fry any probe entity inside — cyan X, echo its disk,
          //    clear the probe.
          const disk = [];
          for (let dy = -R; dy <= R; dy++) {
            for (let dx = -R; dx <= R; dx++) {
              if (Math.abs(dx) + Math.abs(dy) > R) continue;
              const gx = tx + dx, gy = ty + dy;
              if (gx < 0 || gx >= cols || gy < 0 || gy >= rows) continue;
              disk.push({ x: gx, y: gy });
            }
          }
          for (const { x, y } of disk) {
            const cellEl = boardCellAt(x, y);
            const ent = cellEl.querySelector(".mn-cell-entity");
            if (ent && ent.classList.contains("mn-cell-entity--probe")) {
              const probeVis = eucDisk(x, y, 4);
              for (const j of probeVis) boardCell(board, j).classList.add("is-echo");
              spawnXOverlayLocal(cellEl, "#00e8ff", 0);
              // Give the X a beat to grow into place, then clear entity.
              const c = cellEl;
              state.timers.push(setTimeout(() => setEntity(c, "", null), 260));
              if (onEachHit) onEachHit(idxAt(x, y));
              pushLog("aurora", `probe fried at (${x},${y})`);
            }
          }
          // 4. Ticker — swirl the ASCII glyphs. The scramble self-stops
          //    when state.stopped flips (see check inside the interval),
          //    so we don't need to track its handle separately.
          let empT = 0;
          const scrambleTimer = setInterval(() => {
            if (state.stopped) { clearInterval(scrambleTimer); return; }
            empT += 0.18;
            for (const tile of cloudTiles) {
              if (!tile.isConnected) continue;
              tile.textContent = _empCharAt(Number(tile.dataset.gx), Number(tile.dataset.gy), empT);
            }
          }, 90);
          // 5. Dissipation — step density down through the ramp,
          //    then fade opacity to 0.
          state.timers.push(setTimeout(() => {
            clearInterval(scrambleTimer);
            const STEP_MS = 58, FADE_MS = 220;
            function stepTile(tile, idx) {
              if (state.stopped || !tile.isConnected) return;
              if (idx > 0) {
                tile.textContent = _EMP_CHARS[idx - 1];
                const jitter = (Math.random() - 0.5) * 18;
                state.timers.push(setTimeout(() => stepTile(tile, idx - 1), STEP_MS + jitter));
              } else {
                tile.style.transition = `opacity ${FADE_MS}ms ease-out`;
                tile.style.opacity = "0";
                state.timers.push(setTimeout(() => {
                  if (tile.isConnected) { tile.remove(); state.fxNodes.delete(tile); }
                }, FADE_MS + 20));
              }
            }
            for (const tile of cloudTiles) {
              const cur = tile.textContent;
              const idx = _EMP_CHARS.indexOf(cur);
              const startIdx = idx >= 0 ? idx : _EMP_CHARS.length - 1;
              const gx = Number(tile.dataset.gx) || 0;
              const gy = Number(tile.dataset.gy) || 0;
              const startDelay = ((gx * 17 + gy * 31) % 6) * 10;
              state.timers.push(setTimeout(() => stepTile(tile, startIdx), startDelay));
            }
          }, 2400));
        }, 580);
      }, delay || 0);
    }
    function fireEmpSalvo(centerX, centerY, spreadX, onDone) {
      const targets = [
        { x: centerX - spreadX, y: centerY },
        { x: centerX,           y: centerY },
        { x: centerX + spreadX, y: centerY },
      ];
      let hits = 0;
      targets.forEach((t, i) => {
        fireEmpMissile(t.x, t.y, i * 200, () => { hits++; });
      });
      timer(() => { if (onDone) onDone(hits); }, 200 * targets.length + 3600);
    }

    // ── stage machine ───────────────────────────────────────────
    const STAGES = [
      {
        label:  "0 · PROBE = VISION",
        body:   "The probe's whole job is to see. It lands, its 4-tile disk unfogs, and only revealed RED lets a harvester drop.",
        cite:   "§3.11 · probes · §5.1 · vision",
        status: "# stage 0 · probe grants vision",
        run:    stage0_probeGrantsVision,
      },
      {
        label:  "1 · PROBE LIFE · 3 NIGHTS",
        body:   "Probes are the ONLY things that survive the surface — for 3 nights. Each Aurora chews one heat ring. On the fourth dawn: gone. Vision drops to ECHO.",
        cite:   "§3.11 · probes · §3.2 · aurora",
        status: "# stage 1 · probe decays over 3 auroras",
        run:    stage1_probeLife,
      },
      {
        label:  "2 · PROBE CRUSH · X",
        body:   "Your harvester rolls a red seam with an enemy probe and your own probe on it. Enemy first (red X) — the enemy loses THEIR vision, you never had it. Own probe last (red X, your disk → ECHO) — YOU lose vision. Sometimes you HAVE to crush your own probe to reach the material underneath.",
        cite:   "§3.11 · §5.1 (echo vision)",
        status: "# stage 2 · harvesters crush probes",
        run:    stage2_probeCrush,
      },
      {
        label:  "3 · EMP SALVO",
        body:   "3 missiles fan across the field. Each detonation ripples out in Manhattan rings, then a pulsing cyan cloud (▒▓█) settles over the r=2 disk. Any probe caught inside is fried — cyan X on the cell, disk drops to ECHO.",
        cite:   "§4.9.3 · emp",
        status: "# stage 3 · emp salvo",
        run:    stage3_empSalvo,
      },
      {
        label:  "4 · SUPERSEDE · PROBE ON PROBE",
        body:   "Two scenarios on the same setup. BASELINE: enemy sees the seam via their probe, resolves first, banks the RED → all seam cells go GREEN, your harvester scoops after-harvest scraps. SUPERSEDE: you drop a probe ON their probe. Their probe dies (X). Their harvester drop has no live vision anymore → CANCELLED.",
        cite:   "§3.11 · probes · §4.4 · supersede",
        status: "# stage 4 · probe supersede",
        run:    stage4_supersede,
      },
    ];

    function goStage(next) {
      // Cancel timers + rAF, tear down current fx, but keep state alive.
      state.timers.forEach((t) => clearTimeout(t));
      state.timers = [];
      if (state.heatRaf) { cancelAnimationFrame(state.heatRaf); state.heatRaf = null; }
      state.fxNodes.forEach((n) => n.remove());
      state.fxNodes.clear();
      _heatClearAllCells();
      // Per-stage cleanup hook — used by stages that mutate DOM
      // outside state.fxNodes (e.g. stage 4 hides the caption).
      if (state.stageCleanup) {
        try { state.stageCleanup(); } catch (_) {}
        state.stageCleanup = null;
      }
      state.stopped = false;
      const idx = ((next % STAGES.length) + STAGES.length) % STAGES.length;
      state.stageIdx = idx;
      const s = STAGES[idx];
      labelEl.textContent  = s.label;
      bodyEl.textContent   = s.body;
      citeEl.textContent   = s.cite;
      if (statusEl) statusEl.textContent = s.status;
      if (phaseEl)  phaseEl.textContent  = `# stage ${idx + 1} of ${STAGES.length}`;
      clearLog();
      hideSticker();
      hideLifeBadge();
      // Reset board — reds are stage-specific.
      resetBoard({});
      // Give the layout a beat before the stage animation kicks off.
      timer(() => { if (!state.stopped) s.run(); }, 120);
    }
    state.goStage = goStage;

    // ── STAGE 0 · probe grants vision ───────────────────────────
    function stage0_probeGrantsVision() {
      // Small red seam behind fog. Probe lands nearby, its disk unfogs
      // the seam, harvester arcs down onto the seam.
      const reds = [
        { x: 10, y: 4 }, { x: 11, y: 4 }, { x: 11, y: 5 },
        { x: 12, y: 5 }, { x: 12, y: 6 },
      ];
      resetBoard({ reds });
      const probeXY = { x: 11, y: 5 };
      setSticker("NOX · FOG COVERS THE SURFACE", null);
      pushLog("info", "surface is fogged — red is invisible");
      timer(() => {
        pushLog("aurora", "orbital drops a probe");
        spawnProbeTrail(
          boardCellAt(probeXY.x, probeXY.y),
          P1_HEX,
          P1_HEX,
          () => {
            if (state.stopped) return;
            setProbe(boardCellAt(probeXY.x, probeXY.y), 3, P1_VAR);
            // Unfog the probe's r=4 disk.
            eucDisk(probeXY.x, probeXY.y, 4).forEach((i) => setFog(boardCell(board, i), false));
            pushLog("info", "probe disk goes LIVE — red revealed");
            setSticker("VISION LIVE · RED VISIBLE", null);
            // Give the reveal a beat, then arc a harvester into the seam.
            timer(() => {
              if (state.stopped) return;
              pushLog("aurora", "harvester drops on revealed red");
              const target = boardCellAt(12, 5);
              runOrbitalArcAnimation(
                board, target, "harvester", P1_VAR, GLYPH_HARVESTER,
                () => {
                  if (state.stopped) return;
                  setEntity(target, GLYPH_HARVESTER, P1_VAR);
                  spawnHarvestFxLocal(target, RED_HEX);
                  pushLog("info", "harvester on target — vision made it possible");
                  setSticker("NO PROBE → NO VISION → NO DROP", null);
                  if (state.autoPlay) timer(() => { if (!state.stopped) goStage(state.stageIdx + 1); }, 1600);
                },
                state
              );
            }, 700);
          },
          620,
          state
        );
      }, 300);
    }

    // ── STAGE 1 · probe life ────────────────────────────────────
    function stage1_probeLife() {
      // One probe over a small red seam. Three consecutive Auroras.
      // Rings drop 3 → 2 → 1 → destroyed. Disk goes ECHO after death.
      const reds = [
        { x:  9, y: 4 }, { x: 10, y: 4 }, { x: 11, y: 4 },
        { x: 10, y: 5 }, { x: 11, y: 5 }, { x: 12, y: 5 },
        { x: 11, y: 6 },
      ];
      resetBoard({ reds });
      const probeXY = { x: 10, y: 4 };
      const probeIdx = idxAt(probeXY.x, probeXY.y);
      let ringsLeft = 3;
      setLifeBadge("\u25c9 \u25c9 \u25c9", "3 nights", false);
      pushLog("info", "probe on the surface — 3 nights of vision");
      // Land the probe first.
      spawnProbeTrail(
        boardCellAt(probeXY.x, probeXY.y),
        P1_HEX,
        P1_HEX,
        () => {
          if (state.stopped) return;
          setProbe(boardCellAt(probeXY.x, probeXY.y), 3, P1_VAR);
          eucDisk(probeXY.x, probeXY.y, 4).forEach((i) => setFog(boardCell(board, i), false));
          setSticker("NOX 1 · PROBE LIVE (3)", null);
          timer(runAuroraCycle, 700);
        },
        620,
        state
      );

      function runAuroraCycle() {
        if (state.stopped) return;
        if (ringsLeft <= 0) return;
        setSticker(`AURORA · SURFACE BAKES`, "is-aurora");
        pushLog("aurora", `aurora sweep — probe loses a ring`);
        playAuroraSweepLocal(
          [probeIdx],
          () => {
            // Decrement one ring as the heat front passes this probe.
            ringsLeft -= 1;
            const cellEl = boardCell(board, probeIdx);
            if (ringsLeft > 0) {
              setProbe(cellEl, ringsLeft, P1_VAR);
              const ringsStr = "\u25c9 ".repeat(ringsLeft).trim();
              setLifeBadge(ringsStr, `${ringsLeft} night${ringsLeft === 1 ? "" : "s"}`, false);
            } else {
              // Destroyed — clear entity, flag disk as ECHO.
              setEntity(cellEl, "", null);
              const disk = eucDisk(probeXY.x, probeXY.y, 4);
              for (const j of disk) boardCell(board, j).classList.add("is-echo");
              setLifeBadge("\u2716", "destroyed", true);
              pushLog("aurora", "probe destroyed — disk drops to ECHO");
            }
          },
          () => {
            if (state.stopped) return;
            setSticker("VESPERA · DUSK RETURNS", null);
            playVesperaSweepLocal(() => {
              if (state.stopped) return;
              if (ringsLeft > 0) {
                setSticker(`NOX · PROBE LIVE (${ringsLeft})`, null);
                timer(runAuroraCycle, 700);
              } else {
                setSticker("PROBE DEAD · VISION → ECHO", null);
                if (state.autoPlay) timer(() => { if (!state.stopped) goStage(state.stageIdx + 1); }, 1800);
              }
            });
          }
        );
      }
    }

    // ── STAGE 2 · probe crush ───────────────────────────────────
    //   One P1 harvester lands on a red seam. Two probes sit on it:
    //   an enemy P2 probe (crushed FIRST — the enemy loses THEIR
    //   vision, you never had it, so YOUR display doesn't change)
    //   and your own P1 probe (crushed LAST — YOU lose your own
    //   vision; disk drops to ECHO). Teaches: harvesters crush
    //   every probe they touch, and sometimes you HAVE to crush
    //   your own probe to reach the material underneath it.
    function stage2_probeCrush() {
      const reds = [
        { x:  9, y: 5 }, { x: 10, y: 5 }, { x: 11, y: 5 },
        { x: 12, y: 5 }, { x: 13, y: 5 }, { x: 14, y: 5 },
      ];
      resetBoard({ reds });
      const pEnemy = { x: 10, y: 5 }; // enemy probe FIRST on the path
      const pOwn   = { x: 13, y: 5 }; // own probe LAST on the path
      const hStart = { x:  9, y: 5 }; // inside pOwn's r=4 disk (legal / unfogged)
      // Reveal YOUR OWN probe's disk (that's the vision you actually
      // have). Leave the enemy probe's disk fogged — from your POV you
      // don't have their vision. You still see the enemy probe glyph
      // because your own disk overlaps its cell.
      eucDisk(pOwn.x, pOwn.y, 4).forEach((i) => setFog(boardCell(board, i), false));
      setProbe(boardCellAt(pOwn.x,   pOwn.y),   3, P1_VAR);
      setProbe(boardCellAt(pEnemy.x, pEnemy.y), 3, P2_VAR);
      pushLog("info", "your probe (blue) grants YOU vision · enemy probe (red) grants THEM vision");
      setSticker("YOUR PROBE + ENEMY PROBE ON THE SEAM", null);

      // Drop your P1 harvester at the seam's edge.
      timer(() => {
        if (state.stopped) return;
        runOrbitalArcAnimation(
          board, boardCellAt(hStart.x, hStart.y), "harvester", P1_VAR, GLYPH_HARVESTER,
          () => {
            if (state.stopped) return;
            setEntity(boardCellAt(hStart.x, hStart.y), GLYPH_HARVESTER, P1_VAR);
            spawnHarvestFxLocal(boardCellAt(hStart.x, hStart.y), RED_HEX);
            timer(runCrushWalk, 700);
          },
          state
        );
      }, 400);

      // Walk 8→14 along y=5, crushing enemy first (no vision cost),
      // then own probe (real vision cost — but sometimes necessary).
      function runCrushWalk() {
        if (state.stopped) return;
        setSticker("HARVESTER ROLLS THROUGH THE SEAM", null);
        const path = [
          { x: 10, y: 5 }, // enemy probe here
          { x: 11, y: 5 },
          { x: 12, y: 5 },
          { x: 13, y: 5 }, // own probe here
          { x: 14, y: 5 },
        ];
        let curr = { ...hStart };
        let i = 0;
        const step = () => {
          if (state.stopped) return;
          if (i >= path.length) {
            setSticker("SOMETIMES YOU MUST CRUSH YOUR OWN PROBE", "is-emp");
            pushLog("info", "the red under the probe is worth more than the vision above it");
            if (state.autoPlay) timer(() => { if (!state.stopped) goStage(state.stageIdx + 1); }, 2400);
            return;
          }
          const nextCell = boardCellAt(path[i].x, path[i].y);
          const prevCell = boardCellAt(curr.x, curr.y);
          animateStepLocal(prevCell, nextCell, P1_VAR, RED_HEX, () => {
            setEntity(nextCell, GLYPH_HARVESTER, P1_VAR);
            const gotEnemy = path[i].x === pEnemy.x && path[i].y === pEnemy.y;
            const gotOwn   = path[i].x === pOwn.x   && path[i].y === pOwn.y;
            if (gotEnemy) {
              // Enemy loses THEIR vision — your display is unchanged.
              // No echo cells; just the X + entity clear.
              spawnXOverlayLocal(nextCell, "#ff5555", 0);
              setSticker("ENEMY PROBE CRUSHED · they lose their vision", "is-emp");
              pushLog("aurora", "enemy probe CRUSHED at (" + pEnemy.x + "," + pEnemy.y + ") — no vision cost to you");
            } else if (gotOwn) {
              // YOU lose your own vision — disk goes ECHO.
              spawnXOverlayLocal(nextCell, "#ff5555", 0);
              const disk = eucDisk(pOwn.x, pOwn.y, 4);
              for (const j of disk) boardCell(board, j).classList.add("is-echo");
              setSticker("YOUR OWN PROBE CRUSHED · vision → ECHO", "is-emp");
              pushLog("aurora", "own probe CRUSHED at (" + pOwn.x + "," + pOwn.y + ") — YOUR disk → ECHO");
            }
            curr = path[i];
            i += 1;
            timer(step, 320);
          });
        };
        timer(step, 240);
      }
    }

    // ── STAGE 3 · EMP salvo ─────────────────────────────────────
    function stage3_empSalvo() {
      // Red seam plus 5 probes from three seats. 3-missile salvo hits
      // the center of the probe cluster.
      const reds = [
        { x: 10, y: 5 }, { x: 11, y: 5 }, { x: 12, y: 5 }, { x: 13, y: 5 },
        { x: 11, y: 4 }, { x: 12, y: 6 },
      ];
      resetBoard({ reds });
      const probes = [
        { x:  7, y: 4, seat: P1_VAR },
        { x: 10, y: 4, seat: P1_VAR },
        { x: 12, y: 6, seat: P2_VAR },
        { x: 15, y: 5, seat: P2_VAR },
        { x: 13, y: 3, seat: P3_VAR },
      ];
      for (const p of probes) {
        eucDisk(p.x, p.y, 4).forEach((i) => setFog(boardCell(board, i), false));
        setProbe(boardCellAt(p.x, p.y), 3, p.seat);
      }
      pushLog("info", "field · red seam + 5 probes from three seats");
      setSticker("FIELD LOADED · READY TO FIRE", null);

      timer(() => {
        if (state.stopped) return;
        setSticker("EMP SALVO INBOUND · 3 MISSILES", "is-emp");
        pushLog("aurora", "EMP salvo · 3 missiles fired");
        fireEmpSalvo(11, 5, 3, () => {
          if (state.stopped) return;
          setSticker("PROBES FRIED · DISKS → ECHO", "is-emp");
          if (state.autoPlay) timer(() => { if (!state.stopped) goStage(state.stageIdx + 1); }, 2200);
        });
      }, 900);
    }

    // ── STAGE 4 · supersede ─────────────────────────────────────
    //   Right-rail POLICY + VAULT panels for both seats (using the
    //   real .mn-opp-policy and .mn-vault components), replacing
    //   the stage caption for this stage only.
    //
    //   Scenario A · BASELINE
    //     Enemy sees the seam via P_A, resolves first, walks 4 red
    //     cells (bank 4 × RED, ~1080 pts). Player harvester lands
    //     and walks the enemy's WAKE — 3 already-harvested cells
    //     bank as GREEN scraps (~300 pts).
    //
    //   Scenario B · SUPERSEDE
    //     Player probe lands ON P_A → P_A destroyed. Enemy has no
    //     live vision → their harvester drop is CANCELLED. Player's
    //     own harvester walks the seam and banks 3 × RED (~810 pts).
    function stage4_supersede() {
      // ── planning order markers (pulsing seat-coloured glyph on
      //    the destination cell, mirrors engine's cc-order-marker).
      const markerNodes = [];
      function spawnOrderMarker(cellEl, glyph, hex, kind) {
        const m = document.createElement("div");
        m.className = "mn-probes-order-marker";
        m.style.setProperty("--marker-color", hex);
        const gl = document.createElement("span");
        gl.textContent = glyph;
        const lbl = document.createElement("span");
        lbl.className = "mn-probes-order-marker-lbl";
        lbl.textContent = kind === "harvester" ? "HARV" : "PROBE";
        m.appendChild(gl);
        m.appendChild(lbl);
        cellEl.appendChild(m);
        state.fxNodes.add(m);
        markerNodes.push(m);
      }
      function clearMarkers() {
        for (const m of markerNodes) {
          if (m.isConnected) m.remove();
          state.fxNodes.delete(m);
        }
        markerNodes.length = 0;
      }
      function spawnCancelledBadge(cellEl) {
        const badge = document.createElement("div");
        badge.className = "mn-probes-cancelled";
        badge.textContent = "\u2718";
        cellEl.appendChild(badge);
        state.fxNodes.add(badge);
        const lbl = document.createElement("div");
        lbl.className = "mn-probes-cancelled-lbl";
        lbl.textContent = "CANCELLED";
        const rect = cellEl.getBoundingClientRect();
        const stageEl = document.querySelector(".mn-probes-stage");
        const stageRect = stageEl.getBoundingClientRect();
        lbl.style.left = `${rect.left - stageRect.left + rect.width * 0.5 - 32}px`;
        lbl.style.top  = `${rect.top  - stageRect.top  + rect.height + 3}px`;
        stageEl.appendChild(lbl);
        state.fxNodes.add(lbl);
      }

      // ── Strip is a THIRD column in the layout (right of caption).
      //    Board | Caption | [P2 policy+vault, P1 policy+vault].
      //    Auto-removed on stage exit via state.fxNodes.
      const layoutEl  = boardHost.closest(".mn-loop-layout");
      const stripEl = document.createElement("div");
      stripEl.className = "mn-probes-strategy-strip";
      if (layoutEl) layoutEl.appendChild(stripEl);
      state.fxNodes.add(stripEl);

      // One column per seat. Builds the DOM using the exact same
      // markup as tab 3 (vault) and tab 6 (opp-policy).
      function buildStrategyCol(seat /* "p1" | "p2" */, title) {
        const col = document.createElement("div");
        col.className = "mn-probes-strategy-col";
        col.innerHTML = `
          <aside class="mn-opp-policy" data-seat="${seat}">
            <div class="mn-opp-policy-head">
              <div class="mn-opp-policy-title">${title}</div>
              <div class="dim mn-opp-policy-nox">Nox · 21 hours</div>
            </div>
            <div class="mn-opp-policy-list mn-roster-list" data-role="policy"></div>
          </aside>
          <aside class="mn-vault">
            <div class="mn-vault-head">
              <div class="mn-vault-title">VAULT</div>
              <div class="mn-vault-score">score · <b data-role="score">0</b> pts</div>
              <div class="dim mn-vault-cap">6 / 6 hold · §3.9</div>
            </div>
            <div class="mn-vault-grid" data-role="grid"></div>
          </aside>
        `;
        stripEl.appendChild(col);
        const grid = col.querySelector('[data-role="grid"]');
        for (let i = 0; i < 6; i++) {
          const s = document.createElement("div");
          s.className = "mn-vault-slot mn-vault-slot--empty";
          s.setAttribute("data-slot", String(i + 1).padStart(2, "0"));
          const n = document.createElement("span");
          n.className = "mn-vault-slot-num";
          n.textContent = String(i + 1).padStart(2, "0");
          s.appendChild(n);
          grid.appendChild(s);
        }
        return col;
      }
      const p2col = buildStrategyCol("p2", "P2 · ENEMY");
      const p1col = buildStrategyCol("p1", "P1 · YOU");
      const verdictEl = document.createElement("div");
      verdictEl.className = "mn-probes-verdict";
      verdictEl.textContent = "PLANNING · both sides commit their policies for the next Nox";
      stripEl.appendChild(verdictEl);

      // ── local renderPolicy + markPolicySlot — byte-for-byte the
      //    same code path tab 6 uses (line 3823 / 3851).
      function renderPolicy(listEl, slots) {
        listEl.innerHTML = "";
        for (let i = 0; i < 21; i++) {
          const slot = slots[i] || { verb: "wait" };
          const row = document.createElement("div");
          row.className = "mn-roster-slot";
          row.dataset.hour = String(i + 1);
          row.dataset.verb = slot.verb;
          if (slot.verb === "wait") row.classList.add("is-empty");
          else row.classList.add("is-queued");
          const hourStr = "H" + String(i + 1).padStart(2, "0");
          let move = slot.verb.toUpperCase();
          if (slot.target) move += " " + slot.target.replace(/[()]/g, "");
          row.innerHTML =
            `<span class="mn-roster-hour">${hourStr}</span>` +
            `<span class="mn-roster-verb is-neutral">${move}</span>`;
          listEl.appendChild(row);
        }
      }
      function markPolicySlot(listEl, hour, mode) {
        const row = listEl.children[hour - 1];
        if (!row) return;
        row.classList.remove("is-running", "is-done");
        if (mode === "running") row.classList.add("is-running");
        else if (mode === "done") row.classList.add("is-done");
        else if (mode === "cancelled") {
          row.classList.add("is-done");
          row.style.textDecoration = "line-through";
          row.style.color = "var(--red)";
          row.style.opacity = "0.55";
        }
      }

      // ── vault fills (scoped clone of fillVaultSlot at line 834).
      function bankVault(col, slotIdx, tile, purity) {
        const grid = col.querySelector('[data-role="grid"]');
        const slot = grid.children[slotIdx];
        if (!slot) return;
        slot.classList.remove("mn-vault-slot--empty");
        slot.classList.add("mn-vault-slot--full");
        const prior = slot.querySelector(".mn-vault-slot-glyph");
        if (prior) prior.remove();
        const paint = paintTile(tile, purity);
        const gl = document.createElement("span");
        gl.className = "mn-vault-slot-glyph";
        gl.style.color = paint.fg;
        gl.style.background = paint.bg;
        gl.textContent = paint.ch;
        slot.appendChild(gl);
        const scoreEl = col.querySelector('[data-role="score"]');
        const cur = parseInt(scoreEl.textContent, 10) || 0;
        const mult = tile === TILE.RED ? 1.5 : tile === TILE.GREEN ? 0.75 : 1.0;
        const add = Math.round(purity * mult);
        scoreEl.textContent = String(cur + add);
      }
      function resetStrategyCol(col) {
        const scoreEl = col.querySelector('[data-role="score"]');
        scoreEl.textContent = "0";
        const grid = col.querySelector('[data-role="grid"]');
        grid.querySelectorAll(".mn-vault-slot").forEach((slot, i) => {
          slot.className = "mn-vault-slot mn-vault-slot--empty";
          slot.setAttribute("data-slot", String(i + 1).padStart(2, "0"));
          slot.innerHTML = `<span class="mn-vault-slot-num">${String(i + 1).padStart(2, "0")}</span>`;
        });
        col.querySelectorAll(".mn-roster-slot").forEach((r) => {
          r.style.textDecoration = "";
          r.style.color = "";
          r.style.opacity = "";
        });
      }
      function setVerdict(text, cls) {
        verdictEl.textContent = text;
        verdictEl.classList.remove("is-win", "is-loss");
        if (cls) verdictEl.classList.add(cls);
      }

      // Convenience: policy list handles for each column.
      const p2List = p2col.querySelector('[data-role="policy"]');
      const p1List = p1col.querySelector('[data-role="policy"]');

      // Board layout used by BOTH scenarios.
      const REDS = [
        { x:  9, y: 5 }, { x: 10, y: 5 }, { x: 11, y: 5 },
        { x: 12, y: 5 }, { x: 13, y: 5 },
      ];
      const P_A       = { x: 11, y: 3 };
      const ENEMY_PB  = { x: 17, y: 3 };
      const ENEMY_HRV = { x: 10, y: 5 };
      const PLAYER_PB      = { x: 11, y: 7 };  // baseline: player's own probe
      const PLAYER_HRV_A   = { x:  9, y: 5 };  // scenario A: land one BEHIND enemy
      const PLAYER_HRV_B   = { x: 10, y: 5 };  // scenario B: land at seam start
      const RED_PURITY   = 180;
      const GREEN_PURITY = 133; // post-harvest scraps: 133 × 0.75 ≈ 100 pts

      // Policies. Both are 21-hour scripts; the tail is WAIT. Actions
      // are executed IN PARALLEL by hour (both seats' H_h at the same
      // time), mirroring the game's simultaneous PRAXIS resolution.
      // STEP targets are the destination coord, not a direction.
      const P2_POLICY = [
        { verb: "probe",  target: "(17,3)" },  // H01
        { verb: "drop",   target: "(10,5)" },  // H02
        { verb: "step",   target: "(11,5)" },  // H03
        { verb: "step",   target: "(12,5)" },  // H04
        { verb: "step",   target: "(13,5)" },  // H05
        { verb: "pickup", target: ""       },  // H06
      ];
      // Scenario A · player drops ONE CELL BEHIND the enemy (west of
      // (10,5) → (9,5)) so their east walk lands on cells enemy has
      // already banked → 1 RED (drop cell) + 3 GREENS (the wake).
      const P1_POLICY_A = [
        { verb: "probe",  target: "(11,7)" },  // H01
        { verb: "drop",   target: "(9,5)"  },  // H02 · 1 RED
        { verb: "step",   target: "(10,5)" },  // H03 · GREEN (wake)
        { verb: "step",   target: "(11,5)" },  // H04 · GREEN (wake)
        { verb: "step",   target: "(12,5)" },  // H05 · GREEN (wake)
        { verb: "pickup", target: ""       },  // H06
      ];
      // Scenario B · same tempo but player's H01 probe supersedes
      // P_A. Enemy loses vision → their H02 drop is CANCELLED. The
      // player's own H02 drop (now with vision from the superseded
      // probe) walks the LIVE seam, banking 3 × RED.
      const P1_POLICY_B = [
        { verb: "probe",  target: "(11,3)" },  // H01 · supersede
        { verb: "drop",   target: "(10,5)" },  // H02 · 1 RED
        { verb: "step",   target: "(11,5)" },  // H03 · 1 RED
        { verb: "step",   target: "(12,5)" },  // H04 · 1 RED
        { verb: "pickup", target: ""       },  // H05
      ];

      // ── executor state (per seat + per cell) ────────────────────
      //   seatData tracks each seat's harvester position + how many
      //   parcels it has banked so far (which vault slot to fill
      //   next) + whether its plan has been cancelled.
      //   cellTiles is a shadow map of the current terrain of each
      //   seam cell — RED before harvest, GREEN after. Used to pick
      //   the right bank/paint at harvest time.
      const seatData = {
        p1: { hrvPos: null, hrvSlot: 0, cancelled: false, badgeShown: false },
        p2: { hrvPos: null, hrvSlot: 0, cancelled: false, badgeShown: false },
      };
      const cellTiles = new Map();
      function resetSeats() {
        seatData.p1 = { hrvPos: null, hrvSlot: 0, cancelled: false, badgeShown: false };
        seatData.p2 = { hrvPos: null, hrvSlot: 0, cancelled: false, badgeShown: false };
        cellTiles.clear();
        for (const s of REDS) cellTiles.set(`${s.x},${s.y}`, TILE.RED);
      }
      function parseXY(str) {
        const m = /(\d+)\s*,\s*(\d+)/.exec(str || "");
        return m ? { x: +m[1], y: +m[2] } : null;
      }
      function bankAt(seat, x, y) {
        const key = `${x},${y}`;
        const tile = cellTiles.get(key);
        const col = seat === "p1" ? p1col : p2col;
        const info = seatData[seat];
        if (tile === TILE.RED) {
          cellTiles.set(key, TILE.GREEN);
          setTerrain(boardCellAt(x, y), TILE.GREEN, GREEN_PURITY);
          bankVault(col, info.hrvSlot, TILE.RED, RED_PURITY);
          info.hrvSlot += 1;
          spawnHarvestFxLocal(boardCellAt(x, y), RED_HEX);
        } else if (tile === TILE.GREEN) {
          bankVault(col, info.hrvSlot, TILE.GREEN, GREEN_PURITY);
          info.hrvSlot += 1;
          spawnHarvestFxLocal(boardCellAt(x, y), GREEN_HEX);
        }
      }

      // ── execAction · one action for one seat · calls onDone when
      //    the action's animation completes.
      function execAction(seat, action, h, scenario, onDone) {
        const info = seatData[seat];
        const seatVar = seat === "p1" ? P1_VAR : P2_VAR;
        const hex     = seat === "p1" ? P1_HEX : P2_HEX;
        const verb = action && action.verb;

        if (verb === "probe") {
          const target = parseXY(action.target);
          spawnProbeTrail(
            boardCellAt(target.x, target.y), hex, hex,
            () => {
              if (state.stopped) return;
              // Supersede check — scenario B, player probe on P_A.
              if (scenario === "B" && seat === "p1"
                  && target.x === P_A.x && target.y === P_A.y) {
                const pAcell = boardCellAt(P_A.x, P_A.y);
                spawnXOverlayLocal(pAcell, "#00e8ff", 0);
                setEntity(pAcell, "", null);
                timer(() => {
                  if (state.stopped) return;
                  setProbe(pAcell, 3, P1_VAR);
                  eucDisk(target.x, target.y, 4).forEach(
                    (i) => setFog(boardCell(board, i), false),
                  );
                  // Enemy's plan is now dead from H02 onwards.
                  seatData.p2.cancelled = true;
                  pushLog("aurora", "P_A superseded — enemy loses vision of seam");
                  onDone();
                }, 460);
              } else {
                setProbe(boardCellAt(target.x, target.y), 3, seatVar);
                eucDisk(target.x, target.y, 4).forEach(
                  (i) => setFog(boardCell(board, i), false),
                );
                onDone();
              }
            },
            540, state,
          );
          return;
        }

        if (verb === "drop") {
          const target = parseXY(action.target);
          info.hrvPos = { x: target.x, y: target.y };
          runOrbitalArcAnimation(
            board, boardCellAt(target.x, target.y),
            "harvester", seatVar, GLYPH_HARVESTER,
            () => {
              if (state.stopped) return;
              setEntity(boardCellAt(target.x, target.y), GLYPH_HARVESTER, seatVar);
              bankAt(seat, target.x, target.y);
              onDone();
            },
            state,
          );
          return;
        }

        if (verb === "step") {
          // Target is now a destination coordinate string, e.g. "(11,5)".
          const target = parseXY(action.target);
          const prev = info.hrvPos;
          if (!prev || !target) { onDone(); return; }
          info.hrvPos = { x: target.x, y: target.y };
          animateStepLocal(
            boardCellAt(prev.x, prev.y),
            boardCellAt(target.x, target.y),
            seatVar, null,
            () => {
              if (state.stopped) return;
              setEntity(boardCellAt(target.x, target.y), GLYPH_HARVESTER, seatVar);
              bankAt(seat, target.x, target.y);
              onDone();
            },
          );
          return;
        }

        if (verb === "pickup") {
          if (info.hrvPos) {
            setEntity(boardCellAt(info.hrvPos.x, info.hrvPos.y), "", null);
            info.hrvPos = null;
          }
          timer(onDone, 200);
          return;
        }

        // wait / unknown
        onDone();
      }

      // ── runHour · both seats' H_h actions dispatch in parallel.
      //    Waits for both to finish before advancing to H_{h+1}.
      const MAX_H = 7;
      function runHour(h, scenario) {
        if (state.stopped) return;
        if (h > MAX_H) return finishScenario(scenario);

        const p2a = P2_POLICY[h - 1] || { verb: "wait" };
        const p1P = scenario === "A" ? P1_POLICY_A : P1_POLICY_B;
        const p1a = p1P[h - 1] || { verb: "wait" };

        const p2Cancel = seatData.p2.cancelled;
        const p1Cancel = seatData.p1.cancelled;

        // Mark row states.
        if (p2a.verb !== "wait") {
          markPolicySlot(p2List, h, p2Cancel ? "cancelled" : "running");
        }
        if (p1a.verb !== "wait") {
          markPolicySlot(p1List, h, p1Cancel ? "cancelled" : "running");
        }
        // First cancelled drop for enemy → show the board-side CANCELLED badge.
        if (p2Cancel && p2a.verb === "drop" && !seatData.p2.badgeShown) {
          const t = parseXY(p2a.target);
          if (t) spawnCancelledBadge(boardCellAt(t.x, t.y));
          seatData.p2.badgeShown = true;
        }

        setVerdict(`H${String(h).padStart(2, "0")} · both seats act simultaneously`);

        let pending = 0;
        let launched = false;
        const check = () => {
          pending -= 1;
          if (launched && pending <= 0) timer(advance, 200);
        };

        if (!p2Cancel && p2a.verb !== "wait") {
          pending += 1;
          execAction("p2", p2a, h, scenario, check);
        }
        if (!p1Cancel && p1a.verb !== "wait") {
          pending += 1;
          execAction("p1", p1a, h, scenario, check);
        }
        launched = true;

        function advance() {
          if (!p2Cancel && p2a.verb !== "wait") markPolicySlot(p2List, h, "done");
          if (!p1Cancel && p1a.verb !== "wait") markPolicySlot(p1List, h, "done");
          timer(() => runHour(h + 1, scenario), 250);
        }

        // Both WAIT (or both cancelled) — still tick with an audible pause.
        if (pending === 0) timer(advance, 450);
      }

      function finishScenario(scenario) {
        if (state.stopped) return;
        const enemyScore = p2col.querySelector('[data-role="score"]').textContent;
        const playerScore = p1col.querySelector('[data-role="score"]').textContent;
        if (scenario === "A") {
          setSticker("AFTER-HARVEST GREEN · you scoop scraps", "is-emp");
          setVerdict(`ENEMY ${enemyScore} pts · YOU ${playerScore} pts   ·   they own the seam · superseding flips this`, "is-loss");
          timer(runScenarioSupersede, 3200);
        } else {
          setSticker("FULL PIVOT · seam is yours", "is-emp");
          setVerdict(`ENEMY ${enemyScore} pts · YOU ${playerScore} pts   ·   blinded them + banked the RED`, "is-win");
          if (state.autoPlay) timer(() => { if (!state.stopped) goStage(0); }, 4000);
        }
      }

      runScenarioBaseline();

      function setupBoard() {
        resetBoard({ reds: REDS });
        eucDisk(P_A.x, P_A.y, 4).forEach((i) => setFog(boardCell(board, i), false));
        setProbe(boardCellAt(P_A.x, P_A.y), 3, P2_VAR);
        pushLog("info", "enemy probe (red) already sees the red seam");
      }

      function runScenarioBaseline() {
        setupBoard();
        resetSeats();
        renderPolicy(p2List, P2_POLICY);
        renderPolicy(p1List, P1_POLICY_A);
        resetStrategyCol(p2col); resetStrategyCol(p1col);
        setVerdict("SCENARIO A · BASELINE — both plan a harvest · you land ONE BEHIND the enemy");
        setSticker("PLANNING · both policies committed", null);
        spawnOrderMarker(boardCellAt(ENEMY_PB.x,  ENEMY_PB.y),  GLYPH_PROBE,     P2_HEX, "probe");
        spawnOrderMarker(boardCellAt(ENEMY_HRV.x, ENEMY_HRV.y), GLYPH_HARVESTER, P2_HEX, "harvester");
        spawnOrderMarker(boardCellAt(PLAYER_PB.x, PLAYER_PB.y), GLYPH_PROBE,     P1_HEX, "probe");
        spawnOrderMarker(boardCellAt(PLAYER_HRV_A.x, PLAYER_HRV_A.y), GLYPH_HARVESTER, P1_HEX, "harvester");
        timer(() => {
          if (state.stopped) return;
          setSticker("EXECUTING · simultaneous, hour by hour", null);
          clearMarkers();
          runHour(1, "A");
        }, 1800);
      }

      function runScenarioSupersede() {
        if (state.stopped) return;
        pushLog("info", "── SCENARIO B · SUPERSEDE ──");
        setupBoard();
        resetSeats();
        renderPolicy(p2List, P2_POLICY);
        renderPolicy(p1List, P1_POLICY_B);
        resetStrategyCol(p2col); resetStrategyCol(p1col);
        setVerdict("SCENARIO B · SUPERSEDE — same tempo, probe target moves to P_A");
        setSticker("PLANNING · you supersede P_A", null);
        spawnOrderMarker(boardCellAt(ENEMY_PB.x,  ENEMY_PB.y),  GLYPH_PROBE,     P2_HEX, "probe");
        spawnOrderMarker(boardCellAt(ENEMY_HRV.x, ENEMY_HRV.y), GLYPH_HARVESTER, P2_HEX, "harvester");
        spawnOrderMarker(boardCellAt(P_A.x,       P_A.y),       GLYPH_PROBE,     P1_HEX, "probe");
        spawnOrderMarker(boardCellAt(PLAYER_HRV_B.x, PLAYER_HRV_B.y), GLYPH_HARVESTER, P1_HEX, "harvester");
        timer(() => {
          if (state.stopped) return;
          setSticker("EXECUTING · simultaneous, hour by hour", null);
          clearMarkers();
          runHour(1, "B");
        }, 1800);
      }
    }

    // ── controls ────────────────────────────────────────────────
    btnPrev.onclick    = () => { state.autoPlay = false; btnToggle.textContent = "[ \u23f5 PLAY ]"; goStage(state.stageIdx - 1); };
    btnNext.onclick    = () => { state.autoPlay = false; btnToggle.textContent = "[ \u23f5 PLAY ]"; goStage(state.stageIdx + 1); };
    btnRestart.onclick = () => { state.autoPlay = false; btnToggle.textContent = "[ \u23f5 PLAY ]"; goStage(0); };
    btnToggle.onclick  = () => {
      state.autoPlay = !state.autoPlay;
      btnToggle.textContent = state.autoPlay ? "[ \u23f8 PAUSE ]" : "[ \u23f5 PLAY ]";
      if (state.autoPlay) goStage(state.stageIdx);
    };

    // ── init ────────────────────────────────────────────────────
    goStage(0);
  }

  // ═══════════════════════════════════════════════════════════════
  // TAB 10 — HARVESTERS · deep dive (3 sections)
  //   0 · LAND · MOVE · PICKUP — probe + harvester + walk into fog +
  //       pickup anywhere. Teaches: 5 moves, 6-parcel hold, auto-
  //       harvest on landing, step works in fog, pickup no vision.
  //   1 · CRASHES — three sub-scenarios (walk-into, simultaneous
  //       drops, drop-on-walker). All match §3.17 patterns.
  //   2 · HARVESTER vs EMP — placeholder for now.
  // ═══════════════════════════════════════════════════════════════
  let tab10_state = null;
  function tab10_stop() {
    if (tab10_state) {
      tab10_state.stopped = true;
      tab10_state.timers.forEach((t) => clearTimeout(t));
      tab10_state.timers = [];
      if (tab10_state.heatRaf) {
        cancelAnimationFrame(tab10_state.heatRaf);
        tab10_state.heatRaf = null;
      }
      if (tab10_state.stageCleanup) {
        try { tab10_state.stageCleanup(); } catch (_) {}
        tab10_state.stageCleanup = null;
      }
      tab10_state.fxNodes.forEach((n) => n.remove());
      tab10_state.fxNodes.clear();
      tab10_state = null;
    }
  }

  function tab10_start() {
    tab10_stop();

    // ── DOM refs ─────────────────────────────────────────────────
    const boardHost  = document.getElementById("mn-board-harv");
    const stickerEl  = document.getElementById("mn-harv-sticker");
    const labelEl    = document.getElementById("mn-stage-label-10");
    const bodyEl     = document.getElementById("mn-stage-body-10");
    const citeEl     = document.getElementById("mn-stage-cite-10");
    const phaseEl    = document.getElementById("mn-harv-phase");
    const statusEl   = document.getElementById("mn-harv-status");
    const btnPrev    = document.getElementById("mn-harv-prev");
    const btnNext    = document.getElementById("mn-harv-next");
    const btnToggle  = document.getElementById("mn-harv-toggle");
    const btnRestart = document.getElementById("mn-harv-restart");

    // ── board setup ─────────────────────────────────────────────
    const cols = 22, rows = 10;
    const cellW = 24, cellH = 24;
    const total = cols * rows;
    const base = new Array(total);
    for (let i = 0; i < total; i++) base[i] = { tile: TILE.EMPTY, purity: 0, fog: true };
    const cells = base.map((c) => ({ ...c }));
    const board = renderBoard(boardHost, cells, { cols, rows, cellW, cellH });

    // ── state ───────────────────────────────────────────────────
    const state = {
      stopped: false, timers: [], fxNodes: new Set(),
      stageIdx: 0, autoPlay: false,
      heatCells: null, heatRaf: null, heatApplied: false,
    };
    tab10_state = state;

    const idxAt = (x, y) => y * cols + x;
    const timer = (fn, ms) => {
      const t = setTimeout(() => { if (state.stopped) return; fn(); }, ms);
      state.timers.push(t);
      return t;
    };
    const P1_VAR = "--seat-p1"; const P1_HEX = "#8ac0ff";
    const P2_VAR = "--seat-p2"; const P2_HEX = "#ff6d6d";
    const RED_HEX   = "#ff4d4d";
    const GREEN_HEX = "#3fb950";
    const DAMAGED_HEX = "#ff8c40";

    // ── helpers ─────────────────────────────────────────────────
    const boardCellAt = (x, y) => boardCell(board, idxAt(x, y));
    function pushLog(kind, msg) {
      const log = document.getElementById("mn-eventlog-10");
      if (!log) return;
      const line = document.createElement("div");
      line.className = `mn-log mn-log--${kind}`;
      line.textContent = `# ${msg}`;
      log.prepend(line);
      while (log.children.length > 40) log.removeChild(log.lastChild);
    }
    function clearLog() {
      const log = document.getElementById("mn-eventlog-10");
      if (log) log.innerHTML = "";
    }
    function setSticker(text, cls) {
      if (!stickerEl) return;
      stickerEl.textContent = text;
      stickerEl.classList.remove("is-crash", "is-good");
      if (cls) stickerEl.classList.add(cls);
      stickerEl.hidden = false;
      // eslint-disable-next-line no-unused-expressions
      stickerEl.offsetHeight;
      stickerEl.classList.add("is-on");
    }
    function hideSticker() {
      if (!stickerEl) return;
      stickerEl.classList.remove("is-on");
      timer(() => { if (stickerEl) stickerEl.hidden = true; }, 260);
    }

    // ── disk helpers ────────────────────────────────────────────
    function eucDisk(cx, cy, r) {
      const out = [];
      const r2 = r * r;
      for (let y = Math.max(0, cy - r); y <= Math.min(rows - 1, cy + r); y++) {
        for (let x = Math.max(0, cx - r); x <= Math.min(cols - 1, cx + r); x++) {
          const dx = x - cx, dy = y - cy;
          if (dx * dx + dy * dy <= r2) out.push(idxAt(x, y));
        }
      }
      return out;
    }

    // ── board reset ─────────────────────────────────────────────
    function resetBoard(opts) {
      opts = opts || {};
      for (let i = 0; i < total; i++) {
        const cellEl = boardCell(board, i);
        setEntity(cellEl, "", null);
        cellEl.classList.remove("is-echo", "mn-cell-dawn-decay");
        // Reset any damaged flag on the entity span.
        const ent = cellEl.querySelector(".mn-cell-entity");
        if (ent) ent.classList.remove("is-damaged");
        setTerrain(cellEl, TILE.EMPTY, 0);
        setFog(cellEl, true);
      }
      if (opts.reds) {
        for (const s of opts.reds) {
          const cellEl = boardCellAt(s.x, s.y);
          setTerrain(cellEl, TILE.RED, s.purity || 180);
        }
      }
    }

    // ── destruction X overlay (ported) ──────────────────────────
    function spawnXOverlayLocal(cellEl, color, delayMs, opts) {
      delayMs = delayMs || 0;
      const thin = !!(opts && opts.thin);
      const cellRect0 = cellEl.getBoundingClientRect();
      const fs = Math.round(cellRect0.width * 0.7);
      const lw = thin ? Math.max(1.5, fs * 0.13) : Math.max(3, fs * 0.26);
      const SPREAD = thin ? 1.1 : 1.4;
      const GROW = 360, SHRINK = 280, HOLD = 200, FADE = 400;
      const rx_f = fs * 0.30, ry_f = fs * 0.36;
      const t = setTimeout(() => {
        if (state.stopped) return;
        const cellRect = cellEl.getBoundingClientRect();
        const cw = cellRect.width, ch = cellRect.height;
        const rx_s = cw / 2 * SPREAD;
        const ry_s = ch / 2 * SPREAD;
        const W = Math.ceil(cw * SPREAD) + 2, H = Math.ceil(ch * SPREAD) + 2;
        const lx = W / 2, ly = H / 2;
        const cv = document.createElement("canvas");
        cv.width = W; cv.height = H;
        cv.style.cssText = `position:fixed;left:${cellRect.left - (W - cw) / 2}px;top:${cellRect.top - (H - ch) / 2}px;pointer-events:none;z-index:60;`;
        document.body.appendChild(cv);
        state.fxNodes.add(cv);
        const xctx = cv.getContext("2d");
        let t0 = null;
        function tick(ts) {
          if (state.stopped) { cv.remove(); state.fxNodes.delete(cv); return; }
          if (t0 === null) t0 = ts;
          const el = ts - t0;
          if (el >= GROW + SHRINK + HOLD + FADE) {
            xctx.clearRect(0, 0, W, H);
            cv.remove(); state.fxNodes.delete(cv);
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
      state.timers.push(t);
    }

    // ── harvester step animation (ported) ───────────────────────
    function spawnHarvestFxLocal(cell, color) {
      const rect = cell.getBoundingClientRect();
      const cx = rect.left + rect.width * 0.5;
      const cy = rect.top + rect.height * 0.5;
      const blink = document.createElement("div");
      blink.className = "mn-harvest-blink";
      blink.style.setProperty("--blink-color", color);
      cell.appendChild(blink);
      state.fxNodes.add(blink);
      blink.addEventListener("animationend", () => { blink.remove(); state.fxNodes.delete(blink); }, { once: true });
      const N = 8;
      for (let i = 0; i < N; i++) {
        const angle = (i / N) * Math.PI * 2 + (Math.random() - 0.5) * 0.4;
        const dist = rect.width * (1.8 + Math.random() * 1.4);
        const p = document.createElement("div");
        p.className = "mn-harvest-particle";
        p.style.left = `${cx.toFixed(1)}px`;
        p.style.top  = `${cy.toFixed(1)}px`;
        const sz = Math.max(2, Math.round(rect.width * 0.22));
        p.style.width  = `${sz}px`;
        p.style.height = `${sz}px`;
        p.style.setProperty("--dx", `${(Math.cos(angle) * dist).toFixed(1)}px`);
        p.style.setProperty("--dy", `${(Math.sin(angle) * dist).toFixed(1)}px`);
        p.style.background = color;
        p.style.animationDelay = `${Math.round(Math.random() * 40)}ms`;
        document.body.appendChild(p);
        state.fxNodes.add(p);
        p.addEventListener("animationend", () => { p.remove(); state.fxNodes.delete(p); }, { once: true });
      }
    }
    function animateStepLocal(prevCell, nextCell, seatVar, blinkColor, onArrive) {
      const prevEntity = prevCell.querySelector(".mn-cell-entity");
      const nextEntity = nextCell.querySelector(".mn-cell-entity");
      prevEntity.textContent = "";
      prevEntity.classList.remove("is-damaged");
      const savedNextText = nextEntity.textContent;
      nextEntity.textContent = "";
      const pr = prevCell.getBoundingClientRect();
      const nr = nextCell.getBoundingClientRect();
      const ghost = document.createElement("span");
      ghost.className = "mn-step-ghost";
      ghost.textContent = GLYPH_HARVESTER;
      ghost.style.left = `${pr.left}px`;
      ghost.style.top  = `${pr.top}px`;
      ghost.style.width  = `${pr.width}px`;
      ghost.style.height = `${pr.height}px`;
      ghost.style.color  = `var(${seatVar})`;
      ghost.style.fontSize = `${Math.round(pr.width * 0.7)}px`;
      document.body.appendChild(ghost);
      state.fxNodes.add(ghost);
      const dx = nr.left - pr.left;
      const dy = nr.top  - pr.top;
      let done = false;
      const finish = () => {
        if (done || state.stopped) return;
        done = true;
        ghost.remove();
        state.fxNodes.delete(ghost);
        if (savedNextText) nextEntity.textContent = savedNextText;
        onArrive();
        if (blinkColor) spawnHarvestFxLocal(nextCell, blinkColor);
      };
      requestAnimationFrame(() => requestAnimationFrame(() => {
        ghost.style.transform = `translate(${dx.toFixed(1)}px, ${dy.toFixed(1)}px)`;
      }));
      ghost.addEventListener("transitionend", finish, { once: true });
      state.timers.push(setTimeout(finish, 260));
    }

    // ── order marker (pending drop / step target) ───────────────
    const markerNodes = [];
    function spawnOrderMarker(cellEl, glyph, hex, kind) {
      const m = document.createElement("div");
      m.className = "mn-harv-order-marker";
      m.style.setProperty("--marker-color", hex);
      const gl = document.createElement("span");
      gl.textContent = glyph;
      const lbl = document.createElement("span");
      lbl.className = "mn-harv-order-marker-lbl";
      lbl.textContent = kind === "harvester" ? "HARV" : "PROBE";
      m.appendChild(gl);
      m.appendChild(lbl);
      cellEl.appendChild(m);
      state.fxNodes.add(m);
      markerNodes.push(m);
    }
    function clearMarkers() {
      for (const m of markerNodes) {
        if (m.isConnected) m.remove();
        state.fxNodes.delete(m);
      }
      markerNodes.length = 0;
    }

    // ── walking-vision ping (own sensors light the fog) ─────────
    function spawnWalkPing(cellEl) {
      const ping = document.createElement("div");
      ping.className = "mn-harv-walk-ping";
      cellEl.appendChild(ping);
      state.fxNodes.add(ping);
      ping.addEventListener("animationend", () => {
        ping.remove();
        state.fxNodes.delete(ping);
      }, { once: true });
    }

    // ── CRASH scar overlay ──────────────────────────────────────
    function spawnCrashScar(cellEl, label) {
      const scar = document.createElement("div");
      scar.className = "mn-harv-crash-scar";
      cellEl.appendChild(scar);
      state.fxNodes.add(scar);
      if (label) {
        const lbl = document.createElement("div");
        lbl.className = "mn-harv-crash-scar-lbl";
        lbl.textContent = label;
        const rect = cellEl.getBoundingClientRect();
        const stageEl = document.querySelector(".mn-harv-stage");
        const stageRect = stageEl.getBoundingClientRect();
        lbl.style.left = `${rect.left - stageRect.left + rect.width * 0.5 - 26}px`;
        lbl.style.top  = `${rect.top  - stageRect.top  + rect.height + 3}px`;
        stageEl.appendChild(lbl);
        state.fxNodes.add(lbl);
      }
    }

    // ── ENGINE pixel-explosion port (server/static/app.js:8809+ ) ──
    //   Canvas-based pixel-art detonation on a crashed cell. One pixel
    //   is ~1/6 of the cell width; frames pulse outward in Manhattan
    //   rings; each pixel starts as a white flash then flips to an
    //   owner-seat colour before dropping out. Sparks scatter one ring
    //   past the main burst. Runs at 75 ms per frame.
    function spawnPixelExplosionLocal(cellEl, colors, delayMs) {
      delayMs = delayMs || 0;
      const cellRect0 = cellEl.getBoundingClientRect();
      const P    = Math.max(2, Math.round(cellRect0.width / 6));
      const R    = 3;
      const LIFE = 2;
      const palette = (colors && colors.length) ? colors : ["#ffffff"];
      const ringDensity = (d) => [1.0, 1.0, 0.95, 0.85, 0.70, 0.55, 0.40, 0.25][Math.min(d, 7)];
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
      const size = (2 * (R + 2)) * P + P;
      const half = Math.floor(P / 2);
      const ox = size / 2, oy = size / 2;
      const t = setTimeout(() => {
        if (state.stopped) return;
        const cellRect = cellEl.getBoundingClientRect();
        const cx = cellRect.left + cellRect.width  / 2;
        const cy = cellRect.top  + cellRect.height / 2;
        const canvas = document.createElement("canvas");
        canvas.width  = size;
        canvas.height = size;
        canvas.style.cssText = `position:fixed;left:${cx - size / 2}px;top:${cy - size / 2}px;pointer-events:none;image-rendering:pixelated;z-index:60;`;
        document.body.appendChild(canvas);
        state.fxNodes.add(canvas);
        const ctx2 = canvas.getContext("2d");
        let frame = 0;
        const tick = setInterval(() => {
          if (state.stopped || !canvas.isConnected) { clearInterval(tick); return; }
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
            clearInterval(tick);
            canvas.remove();
            state.fxNodes.delete(canvas);
          }
        }, 75);
      }, delayMs);
      state.timers.push(t);
    }

    // ── Brightness FLASH on a cell (mirrors engine's `cell-collision-flash`).
    function flashCellCollision(cellEl) {
      cellEl.classList.add("mn-cell--collision-flash");
      cellEl.addEventListener(
        "animationend",
        () => cellEl.classList.remove("mn-cell--collision-flash"),
        { once: true },
      );
    }

    // ── damaged-state helper ────────────────────────────────────
    function markDamaged(cellEl) {
      const ent = cellEl.querySelector(".mn-cell-entity");
      if (ent) ent.classList.add("is-damaged");
    }
    // Cargo spill burst — red particles bursting outward.
    function spillCargo(cellEl) {
      spawnHarvestFxLocal(cellEl, RED_HEX);
    }
    // Reversed orbital arc — harvester arcs BACK to orbit. We just
    // fade + shrink at the target cell for demo purposes.
    function liftBackToOrbit(cellEl, seatVar, onDone) {
      const ent = cellEl.querySelector(".mn-cell-entity");
      if (!ent) { if (onDone) onDone(); return; }
      const rect = cellEl.getBoundingClientRect();
      const ghost = document.createElement("span");
      ghost.className = "mn-step-ghost";
      ghost.textContent = GLYPH_HARVESTER;
      ghost.style.left = `${rect.left}px`;
      ghost.style.top  = `${rect.top}px`;
      ghost.style.width  = `${rect.width}px`;
      ghost.style.height = `${rect.height}px`;
      ghost.style.color  = DAMAGED_HEX;
      ghost.style.fontSize = `${Math.round(rect.width * 0.7)}px`;
      ghost.style.textShadow = "0 0 4px rgba(255,140,64,0.85)";
      ghost.style.transition = "transform 640ms cubic-bezier(0.42,0,0.58,1), opacity 640ms ease-out";
      document.body.appendChild(ghost);
      state.fxNodes.add(ghost);
      setEntity(cellEl, "", null);
      requestAnimationFrame(() => requestAnimationFrame(() => {
        ghost.style.transform = "translate(200px, -260px) scale(0.4)";
        ghost.style.opacity   = "0";
      }));
      state.timers.push(setTimeout(() => {
        ghost.remove(); state.fxNodes.delete(ghost);
        if (onDone) onDone();
      }, 680));
    }

    // ── strategy strip (right rail: policies + vaults) ──────────
    //   Same 3-column trick as tab 9. Injects on demand per stage.
    let stripEl = null, p2col = null, p1col = null, verdictEl = null;
    let p2List = null, p1List = null;
    function ensureStrip() {
      if (stripEl) return;
      const layoutEl = boardHost.closest(".mn-loop-layout");
      stripEl = document.createElement("div");
      stripEl.className = "mn-harv-strategy-strip";
      if (layoutEl) layoutEl.appendChild(stripEl);
      state.fxNodes.add(stripEl);
      p2col = buildStrategyCol("p2", "P2 · ENEMY");
      p1col = buildStrategyCol("p1", "P1 · YOU");
      verdictEl = document.createElement("div");
      verdictEl.className = "mn-harv-verdict";
      verdictEl.textContent = "PLANNING · commit your policies";
      stripEl.appendChild(verdictEl);
      p2List = p2col.querySelector('[data-role="policy"]');
      p1List = p1col.querySelector('[data-role="policy"]');
    }
    function ensureStripSolo() {
      // Single-seat variant (stage 0 · basics). Only P1 column.
      if (stripEl) return;
      const layoutEl = boardHost.closest(".mn-loop-layout");
      stripEl = document.createElement("div");
      stripEl.className = "mn-harv-strategy-strip";
      if (layoutEl) layoutEl.appendChild(stripEl);
      state.fxNodes.add(stripEl);
      p1col = buildStrategyCol("p1", "P1 · YOU");
      verdictEl = document.createElement("div");
      verdictEl.className = "mn-harv-verdict";
      verdictEl.textContent = "PLAN · one harvester, one Nox";
      stripEl.appendChild(verdictEl);
      p1List = p1col.querySelector('[data-role="policy"]');
    }
    function buildStrategyCol(seat, title) {
      const col = document.createElement("div");
      col.className = "mn-harv-strategy-col";
      col.innerHTML = `
        <aside class="mn-opp-policy" data-seat="${seat}">
          <div class="mn-opp-policy-head">
            <div class="mn-opp-policy-title">${title}</div>
            <div class="dim mn-opp-policy-nox">Nox · 21 hours</div>
          </div>
          <div class="mn-opp-policy-list mn-roster-list" data-role="policy"></div>
        </aside>
        <aside class="mn-vault">
          <div class="mn-vault-head">
            <div class="mn-vault-title">VAULT</div>
            <div class="mn-vault-score">score · <b data-role="score">0</b> pts</div>
            <div class="dim mn-vault-cap">6 / 6 hold · §3.9</div>
          </div>
          <div class="mn-vault-grid" data-role="grid"></div>
        </aside>
      `;
      stripEl.appendChild(col);
      const grid = col.querySelector('[data-role="grid"]');
      for (let i = 0; i < 6; i++) {
        const s = document.createElement("div");
        s.className = "mn-vault-slot mn-vault-slot--empty";
        s.setAttribute("data-slot", String(i + 1).padStart(2, "0"));
        const n = document.createElement("span");
        n.className = "mn-vault-slot-num";
        n.textContent = String(i + 1).padStart(2, "0");
        s.appendChild(n);
        grid.appendChild(s);
      }
      return col;
    }
    function renderPolicy(listEl, slots) {
      if (!listEl) return;
      listEl.innerHTML = "";
      for (let i = 0; i < 21; i++) {
        const slot = slots[i] || { verb: "wait" };
        const row = document.createElement("div");
        row.className = "mn-roster-slot";
        row.dataset.hour = String(i + 1);
        row.dataset.verb = slot.verb;
        if (slot.verb === "wait") row.classList.add("is-empty");
        else row.classList.add("is-queued");
        const hourStr = "H" + String(i + 1).padStart(2, "0");
        let move = slot.verb.toUpperCase();
        if (slot.target) move += " " + slot.target.replace(/[()]/g, "");
        row.innerHTML =
          `<span class="mn-roster-hour">${hourStr}</span>` +
          `<span class="mn-roster-verb is-neutral">${move}</span>`;
        listEl.appendChild(row);
      }
    }
    function markPolicySlot(listEl, hour, mode) {
      if (!listEl) return;
      const row = listEl.children[hour - 1];
      if (!row) return;
      row.classList.remove("is-running", "is-done");
      if (mode === "running") row.classList.add("is-running");
      else if (mode === "done") row.classList.add("is-done");
      else if (mode === "cancelled") {
        row.classList.add("is-done");
        row.style.textDecoration = "line-through";
        row.style.color = "var(--red)";
        row.style.opacity = "0.55";
      }
    }
    function bankVault(col, slotIdx, tile, purity) {
      if (!col) return;
      const grid = col.querySelector('[data-role="grid"]');
      const slot = grid.children[slotIdx];
      if (!slot) return;
      slot.classList.remove("mn-vault-slot--empty");
      slot.classList.add("mn-vault-slot--full");
      const prior = slot.querySelector(".mn-vault-slot-glyph");
      if (prior) prior.remove();
      const paint = paintTile(tile, purity);
      const gl = document.createElement("span");
      gl.className = "mn-vault-slot-glyph";
      gl.style.color = paint.fg;
      gl.style.background = paint.bg;
      gl.textContent = paint.ch;
      slot.appendChild(gl);
      const scoreEl = col.querySelector('[data-role="score"]');
      const cur = parseInt(scoreEl.textContent, 10) || 0;
      const mult = tile === TILE.RED ? 1.5 : tile === TILE.GREEN ? 0.75 : 1.0;
      const add = Math.round(purity * mult);
      scoreEl.textContent = String(cur + add);
    }
    function wreckVault(col) {
      if (!col) return;
      col.classList.add("is-wrecked");
      const scoreEl = col.querySelector('[data-role="score"]');
      scoreEl.textContent = "0";
    }
    function setVerdict(text, cls) {
      if (!verdictEl) return;
      verdictEl.textContent = text;
      verdictEl.classList.remove("is-win", "is-loss", "is-crash");
      if (cls) verdictEl.classList.add(cls);
    }

    // ── stage machine ───────────────────────────────────────────
    const STAGES = [
      {
        label:  "0 · LAND · MOVE · PICKUP",
        body:   "Harvester lands on a LIVE-vision cell (auto-harvests it). Steps up to 5 more times — including into FOG (own sensors). Pickup returns it to orbit from ANYWHERE — the policy never names a pickup coord. Hold: 6 parcels (drop + 5 steps).",
        cite:   "§3.9 · §3.10 · auto-harvest v0.9",
        status: "# stage 0 · land · move · pickup",
        run:    stage0_basics,
      },
      {
        label:  "1 · CRASHES · MUTUAL DAMAGE",
        body:   "Harvester-on-harvester collisions damage both units and SPILL ALL CARGO (§3.17). Three patterns: STEP-INTO (both wreck at origin), SIMULTANEOUS DROPS (none land, auto-harvest CANCELLED), DROP-ON (lifter recalled, walker wrecks in place).",
        cite:   "§3.17",
        status: "# stage 1 · three crash patterns",
        run:    stage1_crashes,
      },
      {
        label:  "2 · HARVESTER vs EMP",
        body:   "EMP clouds (Manhattan r=2 diamond, 8-hour lifetime) do three things to a harvest attempt. They FRY PROBES on formation and tick — killing the LIVE vision a drop needs. They REPLACE any hour's action with an `empd` no-op when the harvester's cell is inside the cloud. Cargo is preserved — an EMP wastes TIME, not RED.",
        cite:   "§4.9.3 · emp",
        status: "# stage 2 · emp denial + stuns",
        run:    stage2_emp,
      },
    ];

    function goStage(next) {
      state.timers.forEach((t) => clearTimeout(t));
      state.timers = [];
      if (state.heatRaf) { cancelAnimationFrame(state.heatRaf); state.heatRaf = null; }
      state.fxNodes.forEach((n) => n.remove());
      state.fxNodes.clear();
      if (state.stageCleanup) {
        try { state.stageCleanup(); } catch (_) {}
        state.stageCleanup = null;
      }
      state.stopped = false;
      // Any strip refs are stale after fxNodes clearing.
      stripEl = null; p2col = null; p1col = null;
      verdictEl = null; p2List = null; p1List = null;
      markerNodes.length = 0;
      const idx = ((next % STAGES.length) + STAGES.length) % STAGES.length;
      state.stageIdx = idx;
      const s = STAGES[idx];
      labelEl.textContent = s.label;
      bodyEl.textContent  = s.body;
      citeEl.textContent  = s.cite;
      if (statusEl) statusEl.textContent = s.status;
      if (phaseEl)  phaseEl.textContent  = `# stage ${idx + 1} of ${STAGES.length}`;
      clearLog();
      hideSticker();
      resetBoard({});
      timer(() => { if (!state.stopped) s.run(); }, 120);
    }
    state.goStage = goStage;

    // ─────────────────────────────────────────────────────────
    // STAGE 0 · basics — land, move into fog, pickup anywhere
    // ─────────────────────────────────────────────────────────
    function stage0_basics() {
      // Red seam 4-wide, one probe overhead.
      const reds = [
        { x:  9, y: 5 }, { x: 10, y: 5 }, { x: 11, y: 5 }, { x: 12, y: 5 },
      ];
      resetBoard({ reds });
      const probeXY = { x: 10, y: 3 };
      // Probe already deployed — grant vision on its r=4 disk.
      const probeDiskIdx = new Set(eucDisk(probeXY.x, probeXY.y, 4));
      probeDiskIdx.forEach((i) => setFog(boardCell(board, i), false));
      setProbe(boardCellAt(probeXY.x, probeXY.y), 3, P1_VAR);
      pushLog("info", `probe already at (${probeXY.x},${probeXY.y}) · disk in LIVE vision`);
      setSticker("PROBE IS LIVE · you can LAND under its disk", null);
      // Build the solo-seat strategy strip.
      ensureStripSolo();
      renderPolicy(p1List, [
        { verb: "drop",   target: "(10,5)" },  // H01 · auto-harvest
        { verb: "step",   target: "(11,5)" },  // H02
        { verb: "step",   target: "(12,5)" },  // H03 · still in disk
        { verb: "step",   target: "(13,5)" },  // H04 · steps INTO FOG (own sensors)
        { verb: "step",   target: "(14,5)" },  // H05 · still in fog
        { verb: "pickup", target: ""       },  // H06 · from anywhere
      ]);
      setVerdict("H01 · DROP is legal because probe disk covers the seam");

      const path = [
        { x: 11, y: 5 },  // H02
        { x: 12, y: 5 },  // H03
        { x: 13, y: 5 },  // H04 · leaves probe disk (dist from probe = 3.6, still ≤ 4)
        { x: 14, y: 5 },  // H05 · well into fog
      ];

      const DROP_XY = { x: 10, y: 5 };
      let hrvPos = null;
      let slot = 0;

      // ── HARVESTER LOS · plus-shape, radius 1 (§3.8 · HARVESTER_LOS_RADIUS = 1)
      //    Every step records the harvester's own cell + N/S/E/W cardinals
      //    (dx² + dy² ≤ 1 on the Euclidean disk) into the seat's echo tier.
      //    We track the union along the walk so pickup can fade the whole
      //    trail from LIVE → ECHO (probe-disk cells stay LIVE via the probe).
      const harvTrail = new Set();
      function revealPlus(cx, cy) {
        const OFFSETS = [[0, 0], [0, -1], [0, 1], [-1, 0], [1, 0]];
        const newlyLit = [];
        for (const [dx, dy] of OFFSETS) {
          const x = cx + dx, y = cy + dy;
          if (x < 0 || x >= cols || y < 0 || y >= rows) continue;
          const i = idxAt(x, y);
          const cellEl = boardCell(board, i);
          const wasFog = cellEl.classList.contains("is-fogged");
          if (wasFog) newlyLit.push(cellEl);
          setFog(cellEl, false);
          harvTrail.add(i);
        }
        // Ping any newly-lit cardinal so the "sensors light up" beat reads.
        for (const c of newlyLit) spawnWalkPing(c);
      }

      // H01 · drop.
      timer(() => {
        if (state.stopped) return;
        markPolicySlot(p1List, 1, "running");
        runOrbitalArcAnimation(
          board, boardCellAt(DROP_XY.x, DROP_XY.y),
          "harvester", P1_VAR, GLYPH_HARVESTER,
          () => {
            if (state.stopped) return;
            setEntity(boardCellAt(DROP_XY.x, DROP_XY.y), GLYPH_HARVESTER, P1_VAR);
            spawnHarvestFxLocal(boardCellAt(DROP_XY.x, DROP_XY.y), RED_HEX);
            setTerrain(boardCellAt(DROP_XY.x, DROP_XY.y), TILE.GREEN, 180);
            bankVault(p1col, slot, TILE.RED, 180);
            slot += 1;
            hrvPos = { ...DROP_XY };
            // Harvester now on the surface — pulse a plus of live vision.
            //   (10,4) is inside the probe disk; (10,6), (9,5), (11,5) are
            //   new own-sensor cells added to the trail.
            revealPlus(DROP_XY.x, DROP_XY.y);
            markPolicySlot(p1List, 1, "done");
            pushLog("aurora", `H01 · DROP (10,5) · auto-harvest → RED banked (slot 01)`);
            setSticker("LAND · auto-harvests · plus-shape LOS lights up", "is-good");
            timer(runWalk, 800);
          },
          state,
        );
      }, 800);

      function runWalk() {
        if (state.stopped) return;
        let i = 0;
        const step = () => {
          if (state.stopped) return;
          if (i >= path.length) {
            timer(runPickup, 600);
            return;
          }
          const hour = i + 2; // H02..H05
          markPolicySlot(p1List, hour, "running");
          const next = path[i];
          const inFog = boardCellAt(next.x, next.y).classList.contains("is-fogged");
          animateStepLocal(
            boardCellAt(hrvPos.x, hrvPos.y),
            boardCellAt(next.x, next.y),
            P1_VAR, inFog ? null : RED_HEX,
            () => {
              if (state.stopped) return;
              setEntity(boardCellAt(next.x, next.y), GLYPH_HARVESTER, P1_VAR);
              // If step lands on RED seam, auto-harvest (bank + tile→GREEN).
              const cellEl = boardCellAt(next.x, next.y);
              const isRedSeam = reds.some((r) => r.x === next.x && r.y === next.y);
              if (isRedSeam) {
                setTerrain(cellEl, TILE.GREEN, 180);
                bankVault(p1col, slot, TILE.RED, 180);
                slot += 1;
                spawnHarvestFxLocal(cellEl, RED_HEX);
                pushLog("aurora", `H${String(hour).padStart(2,"0")} · STEP (${next.x},${next.y}) · banked RED (slot ${String(slot).padStart(2,"0")})`);
              } else {
                pushLog("info", `H${String(hour).padStart(2,"0")} · STEP (${next.x},${next.y}) · empty`);
              }
              // If we've walked INTO fog, ping the own-sensor halo.
              if (inFog) {
                spawnWalkPing(cellEl);
                setSticker("STEP · plus-shape LOS extends into the fog", "is-good");
                setVerdict(`H${String(hour).padStart(2,"0")} · STEP into FOG · harvester lights self + N/S/E/W (§3.8)`);
              } else {
                setVerdict(`H${String(hour).padStart(2,"0")} · STEP on live-vision cell · auto-harvest`);
              }
              hrvPos = { ...next };
              // Extend the harvester's plus-shape LOS at the new position.
              revealPlus(next.x, next.y);
              markPolicySlot(p1List, hour, "done");
              i += 1;
              timer(step, 700);
            },
          );
        };
        step();
      }

      function runPickup() {
        if (state.stopped) return;
        markPolicySlot(p1List, 6, "running");
        pushLog("aurora", `H06 · PICKUP · lifter reaches wherever the harvester is`);
        setSticker("PICKUP · anywhere · no vision needed", "is-good");
        setVerdict("H06 · PICKUP · policy NEVER names a pickup coord");
        // Use the canonical orb-lift animation (same helper as DROP but
        // with kind="pickup"): triangle lifter arcs in, attaches the
        // harvester glyph at the midpoint, arcs back out to orbit.
        const cellEl = boardCellAt(hrvPos.x, hrvPos.y);
        runOrbitalArcAnimation(
          board, cellEl, "pickup", P1_VAR, GLYPH_HARVESTER,
          () => {
            // Midpoint callback — cargo has attached to the lifter, so
            // clear the harvester glyph off the cell.
            if (state.stopped) return;
            setEntity(cellEl, "", null);
          },
          state,
        );
        // The arc's total DURATION in runOrbitalArcAnimation is 1100ms
        // (see line 732). Kick the echo-fade + verdict wrap after it lands.
        state.timers.push(setTimeout(() => {
          if (state.stopped) return;
          markPolicySlot(p1List, 6, "done");
          // Harvester has left the surface. Every cell it lit via its
          // plus-shape LOS (that isn't still under a live probe disk)
          // demotes from LIVE → ECHO. The trail records what the House
          // learned, but the beacon is gone.
          const echoCells = [];
          for (const i of harvTrail) {
            if (probeDiskIdx.has(i)) continue;   // still lit by the probe
            echoCells.push(boardCell(board, i));
          }
          if (echoCells.length) {
            echoCells.forEach((cellEl, k) => {
              state.timers.push(setTimeout(() => {
                if (state.stopped) return;
                cellEl.classList.add("is-echo");
              }, 60 + k * 90));
            });
            pushLog("aurora", `TRAIL → ECHO · ${echoCells.length} cells demoted from LIVE to echo tier`);
            setSticker("TRAIL FADES TO ECHO · House remembers, doesn't SEE", "is-good");
            setVerdict(`OUTING COMPLETE · trail of ${echoCells.length} echo cells preserved · probe disk stays LIVE`);
          } else {
            setVerdict(`OUTING COMPLETE · 6-parcel hold, 5 steps max`);
            setSticker("6-PARCEL HOLD · 5 STEPS MAX", "is-good");
          }
          if (state.autoPlay) timer(() => { if (!state.stopped) goStage(state.stageIdx + 1); }, 3200);
        }, 1200));
      }
    }

    // ─────────────────────────────────────────────────────────
    // STAGE 1 · crashes — 3 sub-scenarios back-to-back
    // ─────────────────────────────────────────────────────────
    function stage1_crashes() {
      ensureStrip();
      pushLog("info", "── SCENARIOS · WALK-INTO → SIM-DROPS → DROP-ON ──");
      runWalkInto();
    }

    // Helper: set up the standard board for crash demos.
    //   7-cell red seam wide enough that each seat can bank a couple of
    //   RED parcels before the crash hour, leaving a visible GREEN wake.
    //   Returns the Set of RED cell indices — scenarios drain it as
    //   parcels are banked so we know when a step lands on live RED.
    function setupCrashBoard() {
      const reds = [
        { x:  8, y: 5 }, { x:  9, y: 5 }, { x: 10, y: 5 }, { x: 11, y: 5 },
        { x: 12, y: 5 }, { x: 13, y: 5 }, { x: 14, y: 5 },
      ];
      resetBoard({ reds });
      // Both seats have vision of the seam (one probe each).
      const p1Probe = { x:  8, y: 7 };
      const p2Probe = { x: 14, y: 7 };
      eucDisk(p1Probe.x, p1Probe.y, 4).forEach((i) => setFog(boardCell(board, i), false));
      eucDisk(p2Probe.x, p2Probe.y, 4).forEach((i) => setFog(boardCell(board, i), false));
      setProbe(boardCellAt(p1Probe.x, p1Probe.y), 3, P1_VAR);
      setProbe(boardCellAt(p2Probe.x, p2Probe.y), 3, P2_VAR);
      return new Set(reds.map((r) => idxAt(r.x, r.y)));
    }

    // Shared per-scenario runtime (positions, vault-slot cursors,
    // and the live RED-cell set — cells drop out of `reds` as harvesters
    // eat them, which is how execCrashAction detects "auto-harvest here").
    const crashRun = { p1Pos: null, p2Pos: null, p1Slot: 0, p2Slot: 0, reds: null };

    // Execute one seat's H_h action; calls onDone when animation finishes.
    //   verb ∈ {drop, step}. Auto-harvests RED under the arrival cell,
    //   flips terrain to GREEN, banks a parcel, and updates the seat's
    //   position cursor.
    function execCrashAction(seat, action, onDone) {
      const seatVar = seat === "p1" ? P1_VAR : P2_VAR;
      const to      = action.to;
      const arriveCell = boardCellAt(to.x, to.y);
      const bank = () => {
        // Consult the scenario-scoped Set of remaining RED cells.
        const cellIdx = idxAt(to.x, to.y);
        const wasRed = crashRun.reds && crashRun.reds.has(cellIdx);
        if (wasRed) {
          setTerrain(arriveCell, TILE.GREEN, 180);
          crashRun.reds.delete(cellIdx);
          if (seat === "p1") { bankVault(p1col, crashRun.p1Slot, TILE.RED, 180); crashRun.p1Slot += 1; }
          else               { bankVault(p2col, crashRun.p2Slot, TILE.RED, 180); crashRun.p2Slot += 1; }
          spawnHarvestFxLocal(arriveCell, RED_HEX);
        }
        setEntity(arriveCell, GLYPH_HARVESTER, seatVar);
        if (seat === "p1") crashRun.p1Pos = { ...to };
        else               crashRun.p2Pos = { ...to };
        onDone();
      };
      if (action.verb === "drop") {
        runOrbitalArcAnimation(
          board, arriveCell, "harvester", seatVar, GLYPH_HARVESTER,
          () => { if (!state.stopped) bank(); },
          state,
        );
      } else if (action.verb === "step") {
        const from = seat === "p1" ? crashRun.p1Pos : crashRun.p2Pos;
        animateStepLocal(
          boardCellAt(from.x, from.y), arriveCell,
          seatVar, null,   // do NOT auto-blink here; bank() paints its own
          () => { if (!state.stopped) bank(); },
        );
      }
    }

    // Dispatch a parallel hour: both seats' actions run at the same time
    // and we advance when both callbacks fire.
    function runCrashHour(h, p1a, p2a, onHourDone) {
      if (state.stopped) return;
      markPolicySlot(p1List, h, "running");
      markPolicySlot(p2List, h, "running");
      let pending = 2;
      const done = () => {
        pending -= 1;
        if (pending > 0 || state.stopped) return;
        markPolicySlot(p1List, h, "done");
        markPolicySlot(p2List, h, "done");
        timer(onHourDone, 400);
      };
      execCrashAction("p1", p1a, done);
      execCrashAction("p2", p2a, done);
    }

    // ── A · WALK-INTO (§3.17.3) ──────────────────────────────
    //   Both harvesters land at the edges of the seam and walk toward
    //   each other, banking RED → leaving a GREEN wake. On H04 they
    //   both try to step onto (11,5) at the same time — collision.
    //   Neither moves, both wreck in place at (10,5) and (12,5).
    function runWalkInto() {
      crashRun.reds = setupCrashBoard();
      crashRun.p1Pos = null; crashRun.p2Pos = null;
      crashRun.p1Slot = 0;   crashRun.p2Slot = 0;
      p2col.classList.remove("is-wrecked");
      p1col.classList.remove("is-wrecked");
      // Reset any prior vaults / scores from a previous scenario.
      const p1Score = p1col.querySelector('[data-role="score"]');
      const p2Score = p2col.querySelector('[data-role="score"]');
      if (p1Score) p1Score.textContent = "0";
      if (p2Score) p2Score.textContent = "0";
      p1col.querySelectorAll('.mn-vault-slot').forEach((s) => {
        s.classList.remove("mn-vault-slot--full");
        s.classList.add("mn-vault-slot--empty");
        const gl = s.querySelector(".mn-vault-slot-glyph"); if (gl) gl.remove();
      });
      p2col.querySelectorAll('.mn-vault-slot').forEach((s) => {
        s.classList.remove("mn-vault-slot--full");
        s.classList.add("mn-vault-slot--empty");
        const gl = s.querySelector(".mn-vault-slot-glyph"); if (gl) gl.remove();
      });
      const P1_ACTIONS = [
        { verb: "drop", to: { x:  8, y: 5 } },  // H01
        { verb: "step", to: { x:  9, y: 5 } },  // H02 · bank + GREEN wake
        { verb: "step", to: { x: 10, y: 5 } },  // H03 · bank + GREEN wake
        { verb: "step", to: { x: 11, y: 5 } },  // H04 · CRASH
      ];
      const P2_ACTIONS = [
        { verb: "drop", to: { x: 14, y: 5 } },  // H01
        { verb: "step", to: { x: 13, y: 5 } },  // H02 · bank + GREEN wake
        { verb: "step", to: { x: 12, y: 5 } },  // H03 · bank + GREEN wake
        { verb: "step", to: { x: 11, y: 5 } },  // H04 · CRASH
      ];
      renderPolicy(p1List, P1_ACTIONS.map((a) => ({ verb: a.verb, target: `(${a.to.x},${a.to.y})` })));
      renderPolicy(p2List, P2_ACTIONS.map((a) => ({ verb: a.verb, target: `(${a.to.x},${a.to.y})` })));
      setSticker("A · WALK-INTO · both harvesters walk toward each other", null);
      setVerdict("H01-H03 · both drop and walk, banking RED → GREEN wake behind them");
      pushLog("info", "A · walk-into · both eating toward the middle");

      // Play H01, H02, H03 in sequence (each dispatches both seats in parallel).
      timer(() => runCrashHour(1, P1_ACTIONS[0], P2_ACTIONS[0],
        () => runCrashHour(2, P1_ACTIONS[1], P2_ACTIONS[1],
          () => runCrashHour(3, P1_ACTIONS[2], P2_ACTIONS[2],
            () => runWalkIntoCrash()))), 800);
    }
    function runWalkIntoCrash() {
      if (state.stopped) return;
      const p1Cell   = boardCellAt(crashRun.p1Pos.x, crashRun.p1Pos.y);
      const p2Cell   = boardCellAt(crashRun.p2Pos.x, crashRun.p2Pos.y);
      const centerCell = boardCellAt(11, 5);
      setVerdict("H04 · both step-into (11,5) simultaneously — collision", "is-crash");
      setSticker("H04 · both aim for (11,5)", null);
      markPolicySlot(p1List, 4, "running");
      markPolicySlot(p2List, 4, "running");
      // Half-step nudge toward the target, then snap back — the crash
      // cancels both moves. Neither harvester actually reaches (11,5).
      function nudge(fromCell, toCell) {
        const fr = fromCell.getBoundingClientRect();
        const tr = toCell.getBoundingClientRect();
        const ghost = document.createElement("span");
        ghost.className = "mn-step-ghost";
        ghost.textContent = GLYPH_HARVESTER;
        ghost.style.left = `${fr.left}px`;
        ghost.style.top  = `${fr.top}px`;
        ghost.style.width  = `${fr.width}px`;
        ghost.style.height = `${fr.height}px`;
        const seatVar = fromCell === p1Cell ? P1_VAR : P2_VAR;
        ghost.style.color  = `var(${seatVar})`;
        ghost.style.fontSize = `${Math.round(fr.width * 0.7)}px`;
        ghost.style.transition = "transform 300ms cubic-bezier(0.34,1.56,0.64,1)";
        document.body.appendChild(ghost);
        state.fxNodes.add(ghost);
        // The origin entity is briefly hidden to sell the "moving" step.
        const originEnt = fromCell.querySelector(".mn-cell-entity");
        const savedText = originEnt.textContent;
        originEnt.textContent = "";
        const dx = (tr.left - fr.left) * 0.55;
        const dy = (tr.top  - fr.top)  * 0.55;
        requestAnimationFrame(() => requestAnimationFrame(() => {
          ghost.style.transform = `translate(${dx.toFixed(1)}px, ${dy.toFixed(1)}px)`;
        }));
        state.timers.push(setTimeout(() => {
          // Snap the ghost back.
          ghost.style.transition = "transform 220ms ease-in";
          ghost.style.transform = "translate(0px, 0px)";
          state.timers.push(setTimeout(() => {
            ghost.remove(); state.fxNodes.delete(ghost);
            // Restore origin harvester glyph (will be marked damaged next).
            originEnt.textContent = savedText;
          }, 240));
        }, 320));
      }
      nudge(p1Cell, centerCell);
      nudge(p2Cell, centerCell);

      timer(() => {
        if (state.stopped) return;
        // Engine-style crash graphics: brightness flash + pixel-art
        // explosion at the intended cell, then smaller bursts at each
        // origin so both wrecks read at a glance.
        flashCellCollision(centerCell);
        spawnPixelExplosionLocal(centerCell, ["#ff6644", "#ffcc66", P1_HEX, P2_HEX], 0);
        spawnCrashScar(centerCell, "SCAR · both cancelled");
        spillCargo(p1Cell);
        spillCargo(p2Cell);
        markDamaged(p1Cell);
        markDamaged(p2Cell);
        flashCellCollision(p1Cell);
        flashCellCollision(p2Cell);
        spawnPixelExplosionLocal(p1Cell, ["#ff8c40", P1_HEX], 120);
        spawnPixelExplosionLocal(p2Cell, ["#ff8c40", P2_HEX], 120);
        markPolicySlot(p1List, 4, "cancelled");
        markPolicySlot(p2List, 4, "cancelled");
        wreckVault(p1col);
        wreckVault(p2col);
        pushLog("aurora", "STEP-INTO · both wreck at ORIGIN (10,5) / (12,5) · ALL cargo SPILLED");
        setSticker("STEP-INTO · both wreck AT ORIGIN · CARGO GONE", "is-crash");
        setVerdict("A · STEP-INTO (§3.17.3) · neither moves · both damaged · all banked cargo forfeit", "is-crash");
        timer(runSimDrops, 3400);
      }, 720);
    }

    // ── B · SIMULTANEOUS DROPS (§3.17.2) ─────────────────────
    //   Both drop on the same seam cell in the same hour. NEITHER lands.
    //   The tile stays RED — auto-harvest is CANCELLED because there is
    //   no landing. Big visual proof: seam is untouched at the end.
    function runSimDrops() {
      if (state.stopped) return;
      crashRun.reds = setupCrashBoard();
      p2col.classList.remove("is-wrecked");
      p1col.classList.remove("is-wrecked");
      // Reset scores/vaults.
      const p1Score = p1col.querySelector('[data-role="score"]');
      const p2Score = p2col.querySelector('[data-role="score"]');
      if (p1Score) p1Score.textContent = "0";
      if (p2Score) p2Score.textContent = "0";
      p1col.querySelectorAll('.mn-vault-slot').forEach((s) => {
        s.classList.remove("mn-vault-slot--full");
        s.classList.add("mn-vault-slot--empty");
        const gl = s.querySelector(".mn-vault-slot-glyph"); if (gl) gl.remove();
      });
      p2col.querySelectorAll('.mn-vault-slot').forEach((s) => {
        s.classList.remove("mn-vault-slot--full");
        s.classList.add("mn-vault-slot--empty");
        const gl = s.querySelector(".mn-vault-slot-glyph"); if (gl) gl.remove();
      });
      renderPolicy(p2List, [{ verb: "drop", target: "(11,5)" }]);
      renderPolicy(p1List, [{ verb: "drop", target: "(11,5)" }]);
      setSticker("B · SIMULTANEOUS DROPS · both target (11,5)", null);
      setVerdict("H01 · both drops target the same cell — collision in mid-air", "is-crash");
      pushLog("info", "B · simultaneous drops on (11,5) · seam is UNTOUCHED going in");
      // Two pending markers stacked on (11,5).
      spawnOrderMarker(boardCellAt(11, 5), GLYPH_HARVESTER, P2_HEX, "harvester");
      const cell2 = boardCellAt(11, 5);
      const m2 = document.createElement("div");
      m2.className = "mn-harv-order-marker";
      m2.style.setProperty("--marker-color", P1_HEX);
      m2.style.transform = "translateX(6px)";
      const gl = document.createElement("span"); gl.textContent = GLYPH_HARVESTER;
      const lbl = document.createElement("span"); lbl.className = "mn-harv-order-marker-lbl"; lbl.textContent = "HARV";
      m2.appendChild(gl); m2.appendChild(lbl);
      cell2.appendChild(m2);
      state.fxNodes.add(m2);
      markerNodes.push(m2);

      timer(() => {
        if (state.stopped) return;
        markPolicySlot(p2List, 1, "running");
        markPolicySlot(p1List, 1, "running");
        clearMarkers();
        let arrived = 0;
        function onArrive() {
          arrived += 1;
          if (arrived < 2 || state.stopped) return;
          const centerCell = boardCellAt(11, 5);
          // NEITHER harvester lands — clear any glyph the arc dropped.
          setEntity(centerCell, "", null);
          flashCellCollision(centerCell);
          spawnPixelExplosionLocal(centerCell, ["#ff6644", "#ffcc66", P1_HEX, P2_HEX], 0);
          spawnCrashScar(centerCell, "NO LAND · NO HARVEST");
          spillCargo(centerCell);
          // Flash the seam cell to prove the tile is untouched.
          const terrSpan = centerCell.querySelector(".mn-cell-terrain");
          if (terrSpan) {
            terrSpan.style.transition = "filter 300ms ease-out, box-shadow 300ms ease-out";
            terrSpan.style.filter = "brightness(2.1) saturate(1.6)";
            terrSpan.style.boxShadow = "0 0 12px 3px rgba(255,80,80,0.85)";
            state.timers.push(setTimeout(() => {
              terrSpan.style.filter = "";
              terrSpan.style.boxShadow = "";
            }, 600));
          }
          // Add a persistent "STILL RED" label above the seam so the
          // reader keeps seeing that the tile was never touched.
          const stageEl = document.querySelector(".mn-harv-stage");
          const rect = centerCell.getBoundingClientRect();
          const stageRect = stageEl.getBoundingClientRect();
          const stillLbl = document.createElement("div");
          stillLbl.className = "mn-harv-crash-scar-lbl";
          stillLbl.textContent = "SEAM UNTOUCHED · STILL RED";
          stillLbl.style.left = `${rect.left - stageRect.left + rect.width * 0.5 - 68}px`;
          stillLbl.style.top  = `${rect.top  - stageRect.top  - 16}px`;
          stillLbl.style.borderColor = "rgba(255, 90, 90, 0.9)";
          stillLbl.style.color       = "rgb(255, 130, 130)";
          stageEl.appendChild(stillLbl);
          state.fxNodes.add(stillLbl);
          markPolicySlot(p2List, 1, "cancelled");
          markPolicySlot(p1List, 1, "cancelled");
          wreckVault(p1col);
          wreckVault(p2col);
          pushLog("aurora", "SIM-DROPS · NONE land · (11,5) STAYS RED · seam UNTOUCHED · vaults 0");
          setSticker("SEAM UNTOUCHED · vaults empty · both damaged in orbit", "is-crash");
          setVerdict("B · SIMULTANEOUS DROPS (§3.17.2) · none land · seam untouched · NO parcels banked", "is-crash");
          timer(runDropOnWalker, 3800);
        }
        runOrbitalArcAnimation(board, boardCellAt(11, 5), "harvester", P2_VAR, GLYPH_HARVESTER, () => onArrive(), state);
        runOrbitalArcAnimation(board, boardCellAt(11, 5), "harvester", P1_VAR, GLYPH_HARVESTER, () => onArrive(), state);
      }, 1400);
    }

    // ── C · DROP-ON-WALKER (§3.17.1) ─────────────────────────
    //   P1 lands, walks 2 steps banking RED into a visible GREEN wake
    //   on the LEFT half of the seam. The RIGHT half stays RED — P1
    //   never got there. On H04, P2 drops onto (10,5) where P1 stands.
    //   P2 lifter is recalled damaged; P1 wrecks in place; all cargo
    //   spilled. Contrast: left half GREEN (banked), right half RED
    //   (unbanked, orphaned).
    function runDropOnWalker() {
      if (state.stopped) return;
      crashRun.reds = setupCrashBoard();
      crashRun.p1Pos = null; crashRun.p2Pos = null;
      crashRun.p1Slot = 0;   crashRun.p2Slot = 0;
      p2col.classList.remove("is-wrecked");
      p1col.classList.remove("is-wrecked");
      const p1Score = p1col.querySelector('[data-role="score"]');
      const p2Score = p2col.querySelector('[data-role="score"]');
      if (p1Score) p1Score.textContent = "0";
      if (p2Score) p2Score.textContent = "0";
      p1col.querySelectorAll('.mn-vault-slot').forEach((s) => {
        s.classList.remove("mn-vault-slot--full");
        s.classList.add("mn-vault-slot--empty");
        const gl = s.querySelector(".mn-vault-slot-glyph"); if (gl) gl.remove();
      });
      p2col.querySelectorAll('.mn-vault-slot').forEach((s) => {
        s.classList.remove("mn-vault-slot--full");
        s.classList.add("mn-vault-slot--empty");
        const gl = s.querySelector(".mn-vault-slot-glyph"); if (gl) gl.remove();
      });
      // P1 plan: drop (8,5), step (9,5), step (10,5). Then P2 drops on (10,5).
      const P1_ACTIONS = [
        { verb: "drop", to: { x:  8, y: 5 } },  // H01
        { verb: "step", to: { x:  9, y: 5 } },  // H02
        { verb: "step", to: { x: 10, y: 5 } },  // H03
      ];
      renderPolicy(p1List, P1_ACTIONS.map((a) => ({ verb: a.verb, target: `(${a.to.x},${a.to.y})` })));
      renderPolicy(p2List, [
        { verb: "wait", target: "" },  // H01
        { verb: "wait", target: "" },  // H02
        { verb: "wait", target: "" },  // H03
        { verb: "drop", target: "(10,5)" },  // H04 · drops onto walker
      ]);
      setSticker("C · DROP-ON-WALKER · P1 walks, P2 waits then drops on it", null);
      setVerdict("H01-H03 · P1 lands and eats the LEFT half of the seam", null);
      pushLog("info", "C · drop-on · P1 walks alone · right half of seam untouched");

      // Play H01, H02, H03 solo for P1 (P2 is idle).
      function playP1Hour(h, onDone) {
        markPolicySlot(p1List, h, "running");
        execCrashAction("p1", P1_ACTIONS[h - 1], () => {
          markPolicySlot(p1List, h, "done");
          timer(onDone, 400);
        });
      }
      timer(() => playP1Hour(1, () => playP1Hour(2, () => playP1Hour(3, () => {
        // At H04 P2 declares its drop — show the pending marker.
        setSticker("H04 · P2 drops on (10,5) — P1 is right there", "is-crash");
        setVerdict("H04 · P2's DROP targets the cell P1 currently stands on", "is-crash");
        spawnOrderMarker(boardCellAt(10, 5), GLYPH_HARVESTER, P2_HEX, "harvester");
        timer(() => {
          if (state.stopped) return;
          clearMarkers();
          markPolicySlot(p2List, 4, "running");
          runOrbitalArcAnimation(
            board, boardCellAt(10, 5),
            "harvester", P2_VAR, GLYPH_HARVESTER,
            () => {
              if (state.stopped) return;
              const cell = boardCellAt(10, 5);
              // Clear any P2 glyph that landed momentarily.
              const ent = cell.querySelector(".mn-cell-entity");
              if (ent) ent.textContent = "";
              // Re-paint P1 as damaged in place.
              setEntity(cell, GLYPH_HARVESTER, P1_VAR);
              markDamaged(cell);
              flashCellCollision(cell);
              spawnPixelExplosionLocal(cell, ["#ff6644", "#ffcc66", P1_HEX, P2_HEX], 0);
              spawnCrashScar(cell, "DROP FAILED · lifter recalled");
              spillCargo(cell);
              wreckVault(p1col);
              wreckVault(p2col);
              markPolicySlot(p2List, 4, "cancelled");
              // Persistent "ORPHANED · STILL RED" label over the untouched
              // right half of the seam so the "only-one-side-harvested"
              // outcome is obvious.
              const stageEl = document.querySelector(".mn-harv-stage");
              const rightMid = boardCellAt(13, 5).getBoundingClientRect();
              const stageRect = stageEl.getBoundingClientRect();
              const orph = document.createElement("div");
              orph.className = "mn-harv-crash-scar-lbl";
              orph.textContent = "RIGHT HALF · ORPHANED · STILL RED";
              orph.style.left = `${rightMid.left - stageRect.left + rightMid.width * 0.5 - 80}px`;
              orph.style.top  = `${rightMid.top  - stageRect.top  - 16}px`;
              orph.style.borderColor = "rgba(255, 90, 90, 0.9)";
              orph.style.color       = "rgb(255, 130, 130)";
              stageEl.appendChild(orph);
              state.fxNodes.add(orph);
              pushLog("aurora", "DROP-ON · P1 wrecked at (10,5) · left wake GREEN · right seam still RED");
              setSticker("LEFT WAKE = P1's harvest · RIGHT SEAM = ORPHANED", "is-crash");
              setVerdict("C · DROP-ON (§3.17.1) · P1 lost 3 banked RED · right half never touched", "is-crash");
              if (state.autoPlay) timer(() => { if (!state.stopped) goStage(state.stageIdx + 1); }, 4200);
            },
            state,
          );
        }, 1200);
      }))), 700);
    }

    // ─────────────────────────────────────────────────────────
    // STAGE 2 · HARVESTER vs EMP — three sub-scenarios
    //   A · EMP fries the probe → landing DENIED (fog-of-war drop)
    //   B · Probe SURVIVES, harvester lands, then gets stunned (empd)
    //       until the cloud clears — cargo preserved
    //   C · Harvester WALKS INTO an existing cloud mid-Nox and gets
    //       empd for the rest of the outing — cargo preserved
    // ─────────────────────────────────────────────────────────

    // ── EMP graphics (port of tab 9's fireEmpMissile). Same helper,
    //    scoped inside tab10_start so it uses the harvester board's
    //    cell layout and state.fxNodes. Ring-staggered flash + ASCII-
    //    density cloud with a 90ms scramble ticker, exactly matching
    //    server/static/app.js:10251+ (see tab 9's original for
    //    reference lines).
    const _EMP_CHARS = ["\u2591\u2591", "\u2591\u2592", "\u2592\u2592", "\u2592\u2593", "\u2593\u2593", "\u2588\u2588"];
    function _empCharAt(gx, gy, t) {
      const v = Math.sin(gx * 0.85 + t * 1.1)
              + Math.sin(gy * 0.72 + t * 0.8)
              + Math.sin((gx - gy) * 0.55 + t * 1.5) * 0.6;
      const norm = Math.max(0, Math.min(1, (v / 2.6 + 1) * 0.5));
      const biased = Math.pow(norm, 2.0);
      return _EMP_CHARS[Math.min(_EMP_CHARS.length - 1, Math.floor(biased * _EMP_CHARS.length))];
    }
    // Fire an EMP missile at (tx, ty). Returns the Set of cell-idx
    // covered by the cloud so the scenario can consult it later for
    // disable-check and probe-kill logic. onEachHit(cellIdx) fires
    // for every probe destroyed inside the cloud.
    function fireEmpMissileHarv(tx, ty, delay, onEachHit, onCloudGone) {
      const R = 2;
      const RING_STAGGER = 28;
      const cloudCells = new Set();
      for (let dy = -R; dy <= R; dy++) {
        for (let dx = -R; dx <= R; dx++) {
          if (Math.abs(dx) + Math.abs(dy) > R) continue;
          const gx = tx + dx, gy = ty + dy;
          if (gx < 0 || gx >= cols || gy < 0 || gy >= rows) continue;
          cloudCells.add(idxAt(gx, gy));
        }
      }
      timer(() => {
        if (state.stopped) return;
        const targetCell = boardCellAt(tx, ty);
        const trect = targetCell.getBoundingClientRect();
        const cx = trect.left + trect.width  * 0.5;
        const cy = trect.top  + trect.height * 0.5;
        // 1. Streak — cyan ghost flies in from off-board.
        const ghost = document.createElement("div");
        ghost.className = "mn-emp-ghost";
        ghost.style.left = `${cx.toFixed(1)}px`;
        ghost.style.top  = `${cy.toFixed(1)}px`;
        const boardRect = boardHost.getBoundingClientRect();
        const startDX = (boardRect.left - cx) - 40;
        const startDY = (boardRect.top  - cy) - 40;
        const rot = Math.atan2(-startDY, -startDX) * 180 / Math.PI;
        ghost.style.transform = `translate(${startDX.toFixed(1)}px, ${startDY.toFixed(1)}px) rotate(${rot.toFixed(1)}deg)`;
        document.body.appendChild(ghost);
        state.fxNodes.add(ghost);
        requestAnimationFrame(() => requestAnimationFrame(() => {
          if (state.stopped) return;
          ghost.classList.add("is-flying");
          ghost.style.transform = `translate(0px, 0px) rotate(${rot.toFixed(1)}deg)`;
        }));
        pushLog("aurora", `EMP missile → (${tx},${ty})`);
        // 2. Impact — ring-staggered expansion flash + cloud paint.
        timer(() => {
          if (state.stopped) return;
          ghost.remove();
          state.fxNodes.delete(ghost);
          const cloudTiles = [];
          for (let dy = -R; dy <= R; dy++) {
            for (let dx = -R; dx <= R; dx++) {
              const dist = Math.abs(dx) + Math.abs(dy);
              if (dist > R) continue;
              const gx = tx + dx, gy = ty + dy;
              if (gx < 0 || gx >= cols || gy < 0 || gy >= rows) continue;
              const cellEl = boardCellAt(gx, gy);
              // Flash.
              const flash = document.createElement("div");
              flash.className = "mn-emp-flash";
              flash.style.left = "0"; flash.style.top = "0";
              flash.style.right = "0"; flash.style.bottom = "0";
              flash.style.animationDelay = `${dist * RING_STAGGER}ms`;
              cellEl.appendChild(flash);
              state.fxNodes.add(flash);
              flash.addEventListener("animationend", () => {
                flash.remove(); state.fxNodes.delete(flash);
              }, { once: true });
              // Cloud tile.
              const cloud = document.createElement("div");
              cloud.className = "mn-emp-cloud";
              cloud.style.left = "0"; cloud.style.top = "0";
              cloud.style.right = "0"; cloud.style.bottom = "0";
              cloud.dataset.gx = String(gx);
              cloud.dataset.gy = String(gy);
              cloud.textContent = _empCharAt(gx, gy, 0);
              cellEl.appendChild(cloud);
              state.fxNodes.add(cloud);
              cloudTiles.push(cloud);
            }
          }
          // 3. Fry any probe inside the cloud (§4.9.3 cross-system kill).
          for (const cellIdx of cloudCells) {
            const cellEl = boardCell(board, cellIdx);
            const ent = cellEl.querySelector(".mn-cell-entity");
            if (ent && ent.classList.contains("mn-cell-entity--probe")) {
              spawnPixelExplosionLocal(cellEl, ["#00e8ff", "#66f2ff"], 0);
              const c = cellEl;
              state.timers.push(setTimeout(() => setEntity(c, "", null), 260));
              if (onEachHit) onEachHit(cellIdx);
              pushLog("aurora", `probe fried at cell #${cellIdx}`);
            }
          }
          // 4. Scramble ticker — 90ms glyph swirl.
          let empT = 0;
          const scramble = setInterval(() => {
            if (state.stopped) { clearInterval(scramble); return; }
            empT += 0.18;
            for (const tile of cloudTiles) {
              if (!tile.isConnected) continue;
              tile.textContent = _empCharAt(Number(tile.dataset.gx), Number(tile.dataset.gy), empT);
            }
          }, 90);
          state.empCloud = { cells: cloudCells, tiles: cloudTiles, scramble };
          // 5. Dissipation is triggered externally so scenarios can
          //    control cloud lifetime for pedagogy (shorter than the
          //    default 8 hours). expireCloud() below tears it down.
        }, 580);
      }, delay || 0);
      return cloudCells;
    }
    function expireCloud() {
      const c = state.empCloud;
      if (!c) return;
      clearInterval(c.scramble);
      const STEP_MS = 58, FADE_MS = 220;
      function stepTile(tile, idx) {
        if (state.stopped || !tile.isConnected) return;
        if (idx > 0) {
          tile.textContent = _EMP_CHARS[idx - 1];
          const jitter = (Math.random() - 0.5) * 18;
          state.timers.push(setTimeout(() => stepTile(tile, idx - 1), STEP_MS + jitter));
        } else {
          tile.style.transition = `opacity ${FADE_MS}ms ease-out`;
          tile.style.opacity = "0";
          state.timers.push(setTimeout(() => {
            if (tile.isConnected) { tile.remove(); state.fxNodes.delete(tile); }
          }, FADE_MS + 20));
        }
      }
      for (const tile of c.tiles) {
        const cur = tile.textContent;
        const idx = _EMP_CHARS.indexOf(cur);
        const startIdx = idx >= 0 ? idx : _EMP_CHARS.length - 1;
        const gx = Number(tile.dataset.gx) || 0;
        const gy = Number(tile.dataset.gy) || 0;
        const startDelay = ((gx * 17 + gy * 31) % 6) * 10;
        state.timers.push(setTimeout(() => stepTile(tile, startIdx), startDelay));
      }
      state.empCloud = null;
    }

    // Helper: mark a policy row as EMPD (cyan strikethrough).
    function markEmpd(listEl, hour) {
      if (!listEl) return;
      const row = listEl.children[hour - 1];
      if (!row) return;
      row.classList.remove("is-running", "is-done");
      row.classList.add("is-done", "is-empd");
    }

    function stage2_emp() {
      ensureStrip();
      pushLog("info", "── SCENARIOS · EMP-DENIES-DROP → EMPD-ON-LAND → WALK-INTO-CLOUD ──");
      runEmpDeniesDrop();
    }

    // Helper: reset both vaults + scores at scenario boundary.
    function resetBothVaults() {
      p2col.classList.remove("is-wrecked");
      p1col.classList.remove("is-wrecked");
      const p1Score = p1col.querySelector('[data-role="score"]');
      const p2Score = p2col.querySelector('[data-role="score"]');
      if (p1Score) p1Score.textContent = "0";
      if (p2Score) p2Score.textContent = "0";
      [p1col, p2col].forEach((col) => {
        col.querySelectorAll('.mn-vault-slot').forEach((s) => {
          s.classList.remove("mn-vault-slot--full");
          s.classList.add("mn-vault-slot--empty");
          const gl = s.querySelector(".mn-vault-slot-glyph"); if (gl) gl.remove();
        });
      });
    }

    // Board setup for EMP demos — same seam as crashes, plus one seat's
    // probe placed relative to where the EMP will land.
    function setupEmpBoard(probeXY) {
      const reds = [
        { x:  8, y: 5 }, { x:  9, y: 5 }, { x: 10, y: 5 }, { x: 11, y: 5 },
        { x: 12, y: 5 }, { x: 13, y: 5 }, { x: 14, y: 5 },
      ];
      resetBoard({ reds });
      // P1's probe covers the seam (r=4 disk). We use a p1Probe placed
      // at probeXY so the disk covers as many cells of the seam as we
      // need for that scenario.
      const p1Probe = probeXY;
      eucDisk(p1Probe.x, p1Probe.y, 4).forEach((i) => setFog(boardCell(board, i), false));
      setProbe(boardCellAt(p1Probe.x, p1Probe.y), 3, P1_VAR);
      return new Set(reds.map((r) => idxAt(r.x, r.y)));
    }

    // ── A · EMP DENIES LANDING (§4.9.3 cross-system kill on probe) ──
    //   P1 has one probe over a rich seam. P2 fires an EMP at the
    //   probe. Probe is destroyed → P1's disk drops to ECHO. P1's
    //   queued DROP now needs LIVE vision — no live cell → cancelled.
    //   No harvester lands. Cargo neutral (there was none).
    function runEmpDeniesDrop() {
      const probeXY = { x: 10, y: 3 };
      crashRun.reds = setupEmpBoard(probeXY);
      crashRun.p1Pos = null; crashRun.p2Pos = null;
      crashRun.p1Slot = 0;   crashRun.p2Slot = 0;
      resetBothVaults();
      renderPolicy(p1List, [
        { verb: "drop", target: "(10,5)" },  // H01 · needs live probe disk
      ]);
      renderPolicy(p2List, [
        { verb: "emp",  target: "(10,3)" },  // H01 · targets the probe
      ]);
      setSticker("A · EMP frags the PROBE · landing denied", null);
      setVerdict("H01 · P2's EMP + P1's DROP dispatch in parallel — EMP resolves FIRST (§4.9.3 order)", "is-emp");
      pushLog("info", "A · emp-denies-drop · probe under fire, disk goes ECHO");
      spawnOrderMarker(boardCellAt(10, 5), GLYPH_HARVESTER, P1_HEX, "harvester");

      timer(() => {
        if (state.stopped) return;
        markPolicySlot(p2List, 1, "running");
        markPolicySlot(p1List, 1, "running");
        clearMarkers();
        // EMP launches, resolves. Probe caught → destroyed. When the
        // probe is destroyed we drop its disk to echo (mirrors tab 9).
        fireEmpMissileHarv(probeXY.x, probeXY.y, 100, () => {
          // On probe-fried: sweep the disk to echo.
          eucDisk(probeXY.x, probeXY.y, 4).forEach((i) => {
            boardCell(board, i).classList.add("is-echo");
          });
          pushLog("aurora", "P1 disk → ECHO · no live vision anywhere");
        }, null);
        // P1's DROP resolves LATER in the same hour. Landing needs
        // LIVE vision — echo doesn't count. The lifter aborts.
        timer(() => {
          if (state.stopped) return;
          markPolicySlot(p2List, 1, "done");
          markPolicySlot(p1List, 1, "cancelled");
          // Attach a persistent "DROP CANCELLED · fog-of-war landing"
          // callout above (10,5).
          const stageEl = document.querySelector(".mn-harv-stage");
          const rect = boardCellAt(10, 5).getBoundingClientRect();
          const stageRect = stageEl.getBoundingClientRect();
          const lbl = document.createElement("div");
          lbl.className = "mn-harv-crash-scar-lbl";
          lbl.textContent = "DROP CANCELLED · no LIVE vision";
          lbl.style.left = `${rect.left - stageRect.left + rect.width * 0.5 - 76}px`;
          lbl.style.top  = `${rect.top  - stageRect.top  - 16}px`;
          lbl.style.borderColor = "rgba(90, 220, 255, 0.9)";
          lbl.style.color       = "rgb(90, 220, 255)";
          stageEl.appendChild(lbl);
          state.fxNodes.add(lbl);
          setSticker("PROBE FRIED · DROP CANCELLED · cargo neutral (none banked)", "is-good");
          setVerdict("A · EMP → probe dead → P1's disk ECHO → landing needs LIVE → drop cancelled", "is-emp");
          pushLog("aurora", "P1 drop cancelled · fog-of-war landing rule (§3.9.8)");
          // Move on to scenario B.
          timer(() => { expireCloud(); runEmpdOnLand(); }, 3200);
        }, 2000);
      }, 1400);
    }

    // ── B · PROBE SURVIVES · HARVESTER EMPD ON LANDING ──────────
    //   P1's probe is placed FAR from the EMP target (outside the
    //   r=2 diamond) so the probe survives. P1 drops at (10,5); P2
    //   drops an EMP centered ON (10,5) the same hour. Order (§4.9.3):
    //   EMP forms → disable check (harvester not yet down) → dispatch
    //   → DROP resolves (live vision still valid, probe alive), harv
    //   lands + auto-harvests. Next few hours: harvester's cell is
    //   inside the cloud → each hour's action is EMPD. Cloud expires,
    //   harvester steps out, banks more RED, picks up. Cargo intact.
    function runEmpdOnLand() {
      if (state.stopped) return;
      // Place probe at (10,7) — 4 south of (10,5) so it's OUT of the
      // r=2 EMP diamond centered on (10,5) but still covers (10,5)
      // (dist sqrt(0+4)=2 ≤ 4). Perfect isolation.
      const probeXY = { x: 10, y: 8 };
      crashRun.reds = setupEmpBoard(probeXY);
      crashRun.p1Pos = null; crashRun.p2Pos = null;
      crashRun.p1Slot = 0;   crashRun.p2Slot = 0;
      resetBothVaults();
      renderPolicy(p1List, [
        { verb: "drop",   target: "(10,5)" },  // H01 · lands
        { verb: "step",   target: "(11,5)" },  // H02 · EMPD (in cloud)
        { verb: "step",   target: "(12,5)" },  // H03 · EMPD (in cloud)
        { verb: "step",   target: "(13,5)" },  // H04 · cloud expired → normal
        { verb: "pickup", target: ""       },  // H05
      ]);
      renderPolicy(p2List, [
        { verb: "emp",    target: "(10,5)" },  // H01 · targets the landing zone
      ]);
      setSticker("B · probe OUTSIDE blast · harvester lands, then STUNNED", null);
      setVerdict("H01 · EMP centred on (10,5) — probe is 3 south, safe. Harvester still lands.", "is-emp");
      pushLog("info", "B · empd-on-land · probe (10,8) is outside r=2 diamond");
      spawnOrderMarker(boardCellAt(10, 5), GLYPH_HARVESTER, P1_HEX, "harvester");

      timer(() => {
        if (state.stopped) return;
        markPolicySlot(p2List, 1, "running");
        markPolicySlot(p1List, 1, "running");
        clearMarkers();
        // EMP fires — cloud forms over (10,5) diamond. Probe is safe.
        fireEmpMissileHarv(10, 5, 100, () => {
          // Any probe hit? Shouldn't be — but log if so.
          pushLog("aurora", "unexpected probe hit — verify probe placement");
        }, null);
        // 2000ms later — DROP resolves. Landing legality was judged
        // at hour-start (probe was alive), so it lands.
        timer(() => {
          if (state.stopped) return;
          execCrashAction("p1", { verb: "drop", to: { x: 10, y: 5 } }, () => {
            markPolicySlot(p2List, 1, "done");
            markPolicySlot(p1List, 1, "done");
            setSticker("LANDED · auto-harvested slot 01 · now inside cloud", "is-emp");
            setVerdict("H01 · harvester at (10,5) sits inside cloud · next 2 hours will be EMPD", "is-emp");
            // H02, H03 — EMPD (harvester cell in cloud).
            timer(() => {
              if (state.stopped) return;
              markEmpd(p1List, 2);
              pushLog("aurora", "H02 · EMPD · harvester inside cloud · action skipped");
              setSticker("H02 · EMPD · turn burned · CARGO SAFE", "is-emp");
              timer(() => {
                if (state.stopped) return;
                markEmpd(p1List, 3);
                pushLog("aurora", "H03 · EMPD · still inside cloud");
                setSticker("H03 · EMPD · time is wasting, but RED stays banked", "is-emp");
                // H04 — cloud expires (short lifetime for demo).
                timer(() => {
                  if (state.stopped) return;
                  expireCloud();
                  setSticker("CLOUD DISSIPATED · harvester regains actions", "is-good");
                  setVerdict("H04 · cloud gone · P1 resumes stepping", "is-emp");
                  timer(() => {
                    markPolicySlot(p1List, 4, "running");
                    execCrashAction("p1", { verb: "step", to: { x: 11, y: 5 } }, () => {
                      markPolicySlot(p1List, 4, "done");
                      timer(() => {
                        // H05 — pickup.
                        markPolicySlot(p1List, 5, "running");
                        setSticker("H05 · PICKUP · cargo preserved through EMP", "is-good");
                        setVerdict("B · empd wastes TIME not RED · pickup returns 2 banked parcels", "is-emp");
                        runOrbitalArcAnimation(
                          board, boardCellAt(crashRun.p1Pos.x, crashRun.p1Pos.y),
                          "pickup", P1_VAR, GLYPH_HARVESTER,
                          () => setEntity(boardCellAt(crashRun.p1Pos.x, crashRun.p1Pos.y), "", null),
                          state,
                        );
                        timer(() => {
                          markPolicySlot(p1List, 5, "done");
                          pushLog("aurora", "B · outing complete · 2 RED banked despite 2 EMPD hours");
                          timer(runWalkIntoCloud, 2600);
                        }, 1200);
                      }, 500);
                    });
                  }, 700);
                }, 1600);
              }, 1400);
            }, 1400);
          });
        }, 2000);
      }, 1400);
    }

    // ── C · HARVESTER WALKS INTO CLOUD ──────────────────────────
    //   P1 lands early and starts eating the seam east. P2 fires an
    //   EMP mid-Nox further east. P1 steps ONE MORE into the cloud
    //   and immediately loses actions until the cloud dissipates.
    //   Cargo preserved.
    function runWalkIntoCloud() {
      if (state.stopped) return;
      const probeXY = { x: 8, y: 3 };
      crashRun.reds = setupEmpBoard(probeXY);
      crashRun.p1Pos = null; crashRun.p2Pos = null;
      crashRun.p1Slot = 0;   crashRun.p2Slot = 0;
      resetBothVaults();
      renderPolicy(p1List, [
        { verb: "drop",   target: "(8,5)" },   // H01 · lands + bank
        { verb: "step",   target: "(9,5)" },   // H02 · bank
        { verb: "step",   target: "(10,5)" },  // H03 · bank (cloud lands elsewhere same hour)
        { verb: "step",   target: "(11,5)" },  // H04 · STEPS INTO cloud + bank
        { verb: "step",   target: "(12,5)" },  // H05 · EMPD
        { verb: "pickup", target: ""       },  // H06 · cargo preserved
      ]);
      renderPolicy(p2List, [
        { verb: "wait",   target: "" },        // H01
        { verb: "wait",   target: "" },        // H02
        { verb: "emp",    target: "(11,5)" },  // H03 · cloud forms east of P1
      ]);
      setSticker("C · harvester walks INTO an existing cloud", null);
      setVerdict("H01-H03 · P1 lands and eats west→east · P2's EMP forms at (11,5) H03", "is-emp");
      pushLog("info", "C · walk-into-cloud · P1 keeps walking, doesn't know cloud is there");

      // H01 · P1 DROP (P2 waits).
      timer(() => {
        markPolicySlot(p1List, 1, "running");
        execCrashAction("p1", { verb: "drop", to: { x: 8, y: 5 } }, () => {
          markPolicySlot(p1List, 1, "done");
          // H02 · P1 STEP (P2 waits).
          timer(() => {
            markPolicySlot(p1List, 2, "running");
            execCrashAction("p1", { verb: "step", to: { x: 9, y: 5 } }, () => {
              markPolicySlot(p1List, 2, "done");
              // H03 · P2 EMP + P1 STEP in parallel.
              timer(() => {
                markPolicySlot(p2List, 3, "running");
                markPolicySlot(p1List, 3, "running");
                fireEmpMissileHarv(11, 5, 100, null, null);
                setSticker("H03 · cloud forms east · P1 steps to (10,5) — safe... this hour", "is-emp");
                // P1's step resolves after EMP.
                timer(() => {
                  execCrashAction("p1", { verb: "step", to: { x: 10, y: 5 } }, () => {
                    markPolicySlot(p2List, 3, "done");
                    markPolicySlot(p1List, 3, "done");
                    setSticker("H04 · P1 will step to (11,5) — walking INTO the cloud", "is-emp");
                    setVerdict("H04 · P1's next step lands INSIDE the cyan cloud", "is-emp");
                    // H04 · P1 STEP (11,5) — enters cloud. Disable check
                    // runs at hour-start on CURRENT position (10,5, not
                    // in cloud), so this step DOES resolve.
                    timer(() => {
                      markPolicySlot(p1List, 4, "running");
                      execCrashAction("p1", { verb: "step", to: { x: 11, y: 5 } }, () => {
                        markPolicySlot(p1List, 4, "done");
                        pushLog("aurora", "H04 · P1 stepped into cloud · banked RED · next hour is empd");
                        // H05 — hour-start disable check: now on (11,5)
                        // which IS in cloud → empd.
                        timer(() => {
                          markEmpd(p1List, 5);
                          setSticker("H05 · EMPD · stuck in cloud · CARGO SAFE (3 banked)", "is-emp");
                          setVerdict("H05 · disable rule fires · action wasted", "is-emp");
                          pushLog("aurora", "H05 · EMPD · harvester stunned in place");
                          // H06 · cloud expires; pickup.
                          timer(() => {
                            expireCloud();
                            setSticker("CLOUD GONE · H06 · PICKUP", "is-good");
                            setVerdict("C · walk-into-cloud · 3 RED banked · cargo preserved through EMP", "is-emp");
                            markPolicySlot(p1List, 6, "running");
                            runOrbitalArcAnimation(
                              board, boardCellAt(11, 5),
                              "pickup", P1_VAR, GLYPH_HARVESTER,
                              () => setEntity(boardCellAt(11, 5), "", null),
                              state,
                            );
                            timer(() => {
                              markPolicySlot(p1List, 6, "done");
                              pushLog("aurora", "C · outing complete · cargo preserved");
                              setSticker("EMP wastes TIME · not RED", "is-good");
                              if (state.autoPlay) timer(() => { if (!state.stopped) goStage(0); }, 3200);
                            }, 1200);
                          }, 1600);
                        }, 1300);
                      });
                    }, 700);
                  });
                }, 1400);
              }, 600);
            });
          }, 500);
        });
      }, 800);
    }

    // ── controls ────────────────────────────────────────────────
    btnPrev.onclick    = () => { state.autoPlay = false; btnToggle.textContent = "[ \u23f5 PLAY ]"; goStage(state.stageIdx - 1); };
    btnNext.onclick    = () => { state.autoPlay = false; btnToggle.textContent = "[ \u23f5 PLAY ]"; goStage(state.stageIdx + 1); };
    btnRestart.onclick = () => { state.autoPlay = false; btnToggle.textContent = "[ \u23f5 PLAY ]"; goStage(0); };
    btnToggle.onclick  = () => {
      state.autoPlay = !state.autoPlay;
      btnToggle.textContent = state.autoPlay ? "[ \u23f8 PAUSE ]" : "[ \u23f5 PLAY ]";
      if (state.autoPlay) goStage(state.stageIdx);
    };

    // ── init ────────────────────────────────────────────────────
    goStage(0);
  }

  // ─── boot ─────────────────────────────────────────────────────
  activateTab("tiles");
})();
