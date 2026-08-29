#!/usr/bin/env python3
"""Generate the tutorial films by driving the real UI.

THE SCRIPT IS THE DELIVERABLE. The ``.webm`` files it writes are build
output, ignored by git, and re-shot by running this again. That is the
whole design: the ORDERS and ORBIT panels move, and a hand-recorded clip
of a moving UI is wrong within a week and then stays wrong, because
nobody re-records by hand. Re-running a script after a redesign costs a
minute.

Every film is a REAL session on the memory backend, driven with real
clicks through real selectors. There is no mock-up and no storyboard, so
a film cannot drift from the product without this script failing or the
frames visibly changing.

Usage::

    SOC_BACKEND=memory python run_web.py --no-reload --port 8022 --replace
    python scripts/make_tutorial_films.py --base http://127.0.0.1:8022
    python scripts/make_tutorial_films.py --only basic_probe

Point it at a server YOU started. See AGENTS.md — never at the user's.

WHAT THIS CANNOT CHECK. Each film asserts that the orders it meant to
give actually landed, which catches a selector that stopped matching.
It cannot tell you the film TEACHES the right thing. The spike this grew
from exited PASS while demonstrating an illegal move and stranding a
harvester. Watch every film before shipping it.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import time
import urllib.request
from typing import Any, Callable, Dict, List, Optional

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sea_of_colours.game import tutorial as soc_tutorial  # noqa: E402

OUT = ROOT / "server" / "static" / "films"

VIEWPORT = {"width": 1280, "height": 800}

# ── the Advanced board ──────────────────────────────────────────────
#
# Advanced teaches SIGNS and WEAPONS, and neither can be taught on a
# board that does not happen to have them. Unlike the Basic films —
# which work on any board and so ride whatever ``--seed`` the batch is
# running under — these pin one seed, picked by
# ``scripts/_probe_advseed.py`` against three things the generator only
# sometimes delivers on a 24x16:
#
#   * exactly ONE bright blue smear, so "that glow is a blue pocket"
#     points at one thing rather than three;
#   * TWO pure-255 jackpots far apart, so each House can light its own
#     and the contested-jackpot lesson has two sides;
#   * all of it inset from the edge, because a probe is a radius-4 disk
#     and a close-up on column 0 is a close-up of the bezel.
#
# The blue is also the arc: EMP is 200 blue and chaff is 255 against a
# 250 stipend, so the hot drop on night one is literally what pays for
# the weapons in orbit. Change the seed and that stops being true.
#
# It comes FROM the preset rather than being restated here, because the
# Advanced preset pins the same board for the player. That is the whole
# point of pinning it: the blue smear in the film is the blue smear on
# their map. A second copy of the number here could drift, and the way
# it would show up is a tutorial whose films quietly describe somewhere
# else — so there is only the one copy, and it lives with the mode.
ADVANCED_SEED = soc_tutorial.ADVANCED_TUTORIAL_SEED
ADV_SIGN = (12, 6)        # brightest bluesign cell — intensity 0.98
ADV_BLUE_LAND = (12, 4)   # BLUE 255 beneath the smear: the hot-drop prize
ADV_BLUE_STEP = (12, 5)   # BLUE 147, the second bite
ADV_MINE = (19, 5)        # our jackpot, sitting in a rich seam
ADV_THEIRS = (4, 12)      # theirs, right across the board
# Somewhere for the rival's early probes that lights nothing. Anything
# within radius 4 of a jackpot mints its beacon a night early and steals
# the only beat the redsign films have.
ADV_QUIET = (20, 12)
ADV_QUIET2 = (8, 2)
# Three radius-2 diamonds in a row overlap into one wall instead of
# three puddles — the "interwoven" pattern, centred on the rival's
# jackpot so the salvo takes their eye off it.
ADV_SALVO = [(2, 12), (4, 12), (6, 12)]
ADV_BESIDE = (8, 11)      # clear of every diamond, one square outside


# ── API helpers ─────────────────────────────────────────────────────

def _req(base: str, path: str, body: Optional[dict] = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        base + path, data=data,
        headers={"Content-Type": "application/json"} if data else {},
    )
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read().decode())


def seed_game(base: str, seed: int, preset: str = "basic") -> str:
    """A tutorial game — the exact board the films teach on.

    Posts the preset NAME so the film is shot on whatever
    ``game/tutorial.py`` currently says that mode is. Restating 24x16
    here would let the films quietly diverge from the mode.
    """
    game = _req(base, "/api/game/new", {"tutorial": preset, "seed": seed})
    return str(game["session_id"])


def seed_duel(base: str, seed: int, cap: int = 5,
              preset: str = "basic") -> str:
    """A preset-LOOKING board with both seats human.

    The outcome films — a crash, a stranding, a shipment — have to show
    a specific thing happen, and the Basic preset hands the other seat
    to a bot that will not take direction. Waiting for the bot to
    volunteer a collision is not a plan; a film that "usually" shows the
    lesson is a film that sometimes ships showing nothing.

    So both seats are human here and the rival's night is posted over
    HTTP before the camera rolls. Everything else is copied from the
    preset (via the module, not by restating 24x16) so the board the
    attendee learns on is the board they then play.
    """
    cfg = soc_tutorial.preset_config(preset) or {}
    game = _req(base, "/api/game/new", {
        "players": ["p1", "p2"],
        "agents": {"p1": "human", "p2": "human"},
        "width": int(cfg.get("width", 24)),
        "height": int(cfg.get("height", 16)),
        # Longer than Basic's three nights: these films need two nights
        # of build-up before the night that carries the lesson, and a
        # season-end card landing mid-film would upstage it.
        "season_day_cap": cap,
        "weapons_enabled": bool(cfg.get("weapons_enabled", False)),
        "signs_enabled": bool(cfg.get("signs_enabled", False)),
        "backend": "memory",
        "seed": seed,
    })
    return str(game["session_id"])


def submit_night(base: str, sid: str, moves: List[dict],
                 player: str = "p1") -> dict:
    return _req(base, f"/api/game/{sid}/policy",
                {"player": player, "moves": moves})


def submit_orbit(base: str, sid: str, actions: List[dict],
                 player: str = "p1") -> dict:
    return _req(base, f"/api/game/{sid}/orbit",
                {"player": player, "actions": actions})


def status(base: str, sid: str) -> dict:
    return _req(base, f"/api/game/{sid}/status")


def view(base: str, sid: str, player: str = "p1") -> dict:
    return _req(base, f"/api/game/{sid}/view?player={player}")


def live_squares(base: str, sid: str, player: str = "p1") -> Dict[tuple, dict]:
    """Squares a seat can land on right now, keyed ``(x, y)``.

    ``drop_mode`` is ``live_only``, so a stale echo is not a landing
    site. Setup picks its coordinates from this rather than from the
    rendered board, because setup runs before the page exists.
    """
    v = view(base, sid, player)
    w = int(v["width"])
    return {
        (i % w, i // w): c
        for i, c in enumerate(v["cells"])
        if c.get("kind") == "terrain" and not c.get("stale")
    }


def harvester_ids(base: str, sid: str, player: str = "p1") -> List[str]:
    v = view(base, sid, player)
    return [str(u["id"]) for u in v["units"] if u.get("type") == "harvester"]


# ── the film kit ────────────────────────────────────────────────────
#
# A cursor and a caption bar injected into the page. Both are plain DOM,
# so the recorder picks them up for free.
#
# The cursor is not decoration. Playwright paints no pointer into its
# video, and without one the UI appears to operate itself — which teaches
# nothing about WHERE TO CLICK, the single thing a first-timer is stuck
# on. The glide runs in JS on requestAnimationFrame rather than as a
# Python loop of evaluate() calls: 30 round-trips per move is jerky and
# slow, and the frame timing is what makes the motion read as a hand.

_KIT = """
() => {
  if (document.getElementById('film-cursor')) return;

  const c = document.createElement('div');
  c.id = 'film-cursor';
  c.style.cssText = [
    'position:fixed', 'left:0', 'top:0', 'width:26px', 'height:26px',
    'margin:-13px 0 0 -13px', 'border:3px solid #aaff00',
    'border-radius:50%', 'background:rgba(170,255,0,0.18)',
    'box-shadow:0 0 12px rgba(170,255,0,0.7)',
    'z-index:2147483647', 'pointer-events:none',
    'transition:transform 90ms ease-out, background 90ms ease-out',
  ].join(';');
  document.body.appendChild(c);

  const cap = document.createElement('div');
  cap.id = 'film-caption';
  cap.style.cssText = [
    'position:fixed', 'left:50%', 'bottom:28px', 'transform:translateX(-50%)',
    // Sized for the playback surface, not the capture: the modal shows
    // these at ~0.9x, and a caption set at the game's own 13px arrives
    // unreadable.
    'padding:12px 26px', 'background:rgba(0,0,0,0.88)',
    'border:1px solid #446600', 'color:#aaff00',
    'font:20px/1.35 ui-monospace,SFMono-Regular,Menlo,monospace',
    'letter-spacing:1.4px', 'text-transform:uppercase',
    'z-index:2147483647', 'pointer-events:none',
    'opacity:0', 'transition:opacity 260ms ease',
    'max-width:70vw', 'text-align:center',
  ].join(';');
  document.body.appendChild(cap);

  window.__film = {
    cursor: c,
    caption: cap,
    at: { x: 0, y: 0 },
    say(text) {
      if (!text) { cap.style.opacity = '0'; return; }
      cap.textContent = text;
      cap.style.opacity = '1';
    },
    put(x, y) {
      c.style.left = x + 'px';
      c.style.top = y + 'px';
      this.at = { x, y };
    },
    glide(x, y, ms) {
      const from = { ...this.at };
      const t0 = performance.now();
      // easeInOutQuad — accelerate away, settle onto the target. A
      // linear glide reads as a machine even at the right duration.
      const ease = (t) => (t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2);
      return new Promise((res) => {
        const step = (now) => {
          const t = Math.min(1, (now - t0) / ms);
          const e = ease(t);
          this.put(from.x + (x - from.x) * e, from.y + (y - from.y) * e);
          if (t < 1) requestAnimationFrame(step);
          else res();
        };
        requestAnimationFrame(step);
      });
    },
    press(right) {
      c.style.transform = 'scale(0.6)';
      c.style.background = right
        ? 'rgba(255,180,0,0.55)' : 'rgba(170,255,0,0.55)';
      return new Promise((res) => setTimeout(() => {
        c.style.transform = 'scale(1)';
        c.style.background = 'rgba(170,255,0,0.18)';
        res();
      }, 150));
    },
  };
}
"""

# Runs at document start, before any app script. Two jobs, both of which
# have to happen BEFORE the first paint or they end up on film: mute the
# tutorial modal (these films play inside it — it must never film itself),
# and drop a black curtain over the boot. Without the curtain the first
# second of every film is a white flash and a half-built UI.
_CURTAIN_INIT = """
(() => {
  try { localStorage.setItem('soc.tutorial.muted.v1', '1'); } catch (e) {}
  const paint = () => {
    // At true document start there is no documentElement yet on the
    // first frame; retry rather than throw a page error.
    const host = document.body || document.documentElement;
    if (!host) { requestAnimationFrame(paint); return; }
    if (document.getElementById('film-curtain')) return;
    const d = document.createElement('div');
    d.id = 'film-curtain';
    d.style.cssText = [
      'position:fixed', 'inset:0', 'background:#04060a',
      'z-index:2147483646', 'pointer-events:none',
      'opacity:1', 'transition:opacity 420ms ease',
    ].join(';');
    host.appendChild(d);
  };
  paint();
  document.addEventListener('DOMContentLoaded', paint);
})();
"""

# Camera push-in, framed on a SET of squares.
#
# Two lessons are baked in here. Origin is pinned to the viewport's
# top-left and the framing done with an explicit translate, because
# transform-origin ON the subject only guarantees the subject does not
# MOVE — on a board sitting in the top half of a tall viewport that
# leaves the close-up pointed at empty ground below it.
#
# And the scale is DERIVED, not passed. A hand-picked 2.1x framed a pair
# of crash sites five squares apart so tightly that the second one was
# off the bottom edge, and nothing failed: the film was a close-up of
# blank terrain with the captions still narrating explosions. Solving
# for a scale that fits every square the beat is about cannot make that
# mistake.
_PUSH_IN = """
([cells, pad, maxK, ms]) => {
  const vp = document.querySelector('.cc-map-viewport');
  if (!vp) return null;
  const els = cells.map(([x, y]) =>
    document.querySelector(`.cell[data-x="${x}"][data-y="${y}"]`));
  if (els.some((e) => !e)) return null;

  // Lift the FX layer OUT of the part that gets scaled, once.
  //
  // Every effect in app.js places itself with `cellRect.left -
  // hostRect.left` — a screen-space delta — and then writes that number
  // as a local offset inside the layer. That identity only holds while
  // the layer and the cells share a scale. Scale the cells with the
  // layer still under the transform and a collision X lands about four
  // hundred pixels off the board, over the left-hand station; undo the
  // scale on the layer instead and it lands correctly but at 1:1, a
  // hairline cross on a board zoomed 3x. Hosting the layer in the
  // unscaled frame satisfies both at once: the delta is measured
  // against zoomed cells and written into unzoomed local pixels, and
  // the effect is sized from the zoomed cell rect it was measured from.
  const frame = vp.closest('.cc-map-frame');
  if (frame) {
    frame.style.overflow = 'hidden';
    frame.style.position = 'relative';
    const fx = document.getElementById('collision-fx-layer');
    if (fx && fx.parentElement !== frame) frame.appendChild(fx);
  }
  vp.style.transition = 'none';
  vp.style.transform = 'none';
  vp.style.transformOrigin = '0 0';
  void vp.offsetWidth;

  const vb = vp.getBoundingClientRect();
  const base = els[0].getBoundingClientRect().width;
  let l = Infinity, t = Infinity, r = -Infinity, b = -Infinity;
  for (const e of els) {
    const cb = e.getBoundingClientRect();
    l = Math.min(l, cb.left - vb.left);
    t = Math.min(t, cb.top - vb.top);
    r = Math.max(r, cb.right - vb.left);
    b = Math.max(b, cb.bottom - vb.top);
  }
  // Breathing room is measured in CELLS, not pixels. The cinematic
  // re-fits the board between hours, so a pixel pad that reads as half
  // a square while planning reads as three squares once the night is
  // playing — and the close-up quietly opens back out into a wide shot.
  const padPx = pad * base;
  l -= padPx; t -= padPx; r += padPx; b += padPx;

  const k = Math.max(1, Math.min(maxK,
    vb.width / Math.max(1, r - l), vb.height / Math.max(1, b - t)));
  const cx = (l + r) / 2, cy = (t + b) / 2;
  const tx = vb.width / 2 - cx * k;
  const ty = vb.height / 2 - cy * k;

  vp.style.transition = `transform ${ms}ms cubic-bezier(.4,0,.2,1)`;
  vp.style.transform = `translate(${tx}px, ${ty}px) scale(${k})`;

  // Four overlays — planned orders, vision borders, blue sign, redsign
  // — are positioned in absolute pixels snapshotted from cell rects, so
  // a camera move strands all four exactly as the zoom dragger would.
  // Left alone they draw the previous board's geometry over the new
  // one: a vision border stapled across the middle of a zoomed map,
  // with the terrain magnified underneath it.
  // Re-anchor on EVERY frame of the glide, not just at both ends. The
  // overlays measure the cells as they are now, so a single call pins
  // them to a size the board is only passing through: the terrain
  // swells for 700ms with a small border sitting still on top of it,
  // which is the "zoom breaks the vision areas" the films were showing.
  if (typeof window._osReanchorOverlays === 'function') {
    if (window.__filmCam) cancelAnimationFrame(window.__filmCam);
    const until = performance.now() + ms + 80;
    const chase = () => {
      window._osReanchorOverlays();
      window.__filmCam =
        performance.now() < until ? requestAnimationFrame(chase) : 0;
    };
    chase();
  }
  return {k: Math.round(k * 100) / 100, base: base};
}
"""

_RAISE_CURTAIN = """
() => {
  const d = document.getElementById('film-curtain');
  if (d) { d.style.opacity = '0'; setTimeout(() => d.remove(), 520); }
  const m = document.querySelector('.soc-tut');
  if (m) m.hidden = true;
}
"""


class Film:
    """A page plus the cursor/caption kit, with human-paced verbs.

    Every verb dwells either side of its click. The dwells are not
    padding — automation clicks faster than anyone can follow, and a film
    with the dwells removed is a flicker.
    """

    def __init__(self, pg, plan: Optional[Dict[str, Any]] = None) -> None:
        self.pg = pg
        self.fails: List[str] = []
        #: Squares (and unit ids) that setup already committed the rival
        #: to. The outcome films must aim at exactly these — the rival's
        #: night is on the books before the page loads, so a film that
        #: picked its own target off the board would miss.
        self.plan: Dict[str, Any] = plan or {}
        #: The close-up currently held, as ``(cells, pad, max_scale)``.
        #: Kept so it can be re-solved whenever the grid is rebuilt under
        #: it — see ``_reaim``.
        self._cam: Optional[tuple] = None

    def kit(self) -> None:
        self.pg.evaluate(_KIT)

    def raise_curtain(self) -> None:
        self.pg.evaluate(_RAISE_CURTAIN)
        self.pg.wait_for_timeout(560)

    def say(self, text: Optional[str], hold: int = 0) -> None:
        self.pg.evaluate("(t) => window.__film.say(t)", text)
        if hold:
            self.pg.wait_for_timeout(hold)

    def wait(self, ms: int) -> None:
        self.pg.wait_for_timeout(ms)

    def _centre(self, selector: str) -> Optional[tuple[float, float]]:
        box = self.pg.locator(selector).first.bounding_box()
        if not box:
            # A matched-but-boxless element means the panel it lives in
            # is not on screen — a wrong-phase selector, not a crash.
            # Raising here used to abandon the shoot half way and leave
            # a film that ends mid-sentence.
            self.fails.append(f"nothing to point at: {selector!r} has no box "
                              f"(wrong phase, or hidden)")
            return None
        return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2

    def glide(self, selector: str, ms: int = 620) -> None:
        centre = self._centre(selector)
        if centre is None:
            return
        x, y = centre
        self.pg.evaluate("([x, y, ms]) => window.__film.glide(x, y, ms)", [x, y, ms])
        # Move the REAL pointer too, or nothing hovers: the fake cursor is
        # decoration and fires no events. Hover states and the AoE preview
        # are half of what these films exist to show.
        self.pg.mouse.move(x, y)
        self.wait(int(ms * 0.9))

    def click(self, selector: str, before: int = 420, after: int = 700,
              ms: int = 620) -> None:
        self.glide(selector, ms=ms)
        self.wait(before)
        self.pg.evaluate("() => window.__film.press(false)")
        self.wait(120)
        self.pg.locator(selector).first.click()
        self.wait(after)

    def right_click(self, selector: str, before: int = 420, after: int = 800,
                    ms: int = 620) -> None:
        self.glide(selector, ms=ms)
        self.wait(before)
        self.pg.evaluate("() => window.__film.press(true)")
        self.wait(120)
        self.pg.locator(selector).first.click(button="right")
        self.wait(after)

    def cell(self, x: int, y: int) -> str:
        return f'.cell[data-x="{x}"][data-y="{y}"]'

    def hover_cell(self, x: int, y: int, ms: int = 600, hold: int = 700) -> None:
        self.glide(self.cell(x, y), ms=ms)
        self.wait(hold)

    def escape(self, after: int = 400) -> None:
        """Disarm the sticky picker.

        A landing chains straight into steps by design (v0.9.5), so the
        pick-mode banner is still blinking when a beat ends. Leaving it up
        ends the film mid-instruction, telling the viewer to keep clicking
        after the lesson is over.
        """
        self.pg.keyboard.press("Escape")
        self.wait(after)

    def queue(self) -> List[str]:
        return self.pg.evaluate("""() => [...document.querySelectorAll('.solo-queue-row')]
            .map((r) => (r.textContent || '').replace(/\\s+/g, ' ').trim())""")

    def slots(self) -> int:
        """Hours committed, read off the panel's own ``N/21 slots``.

        Not a row count. The queue collapses a walk chain into a single
        ``02-04 walk`` row, so three real orders read as one row — which
        made the first version of this check fail a film that was
        perfectly correct.
        """
        txt = self.pg.evaluate("""() => {
          const el = document.getElementById('solo-queue-count');
          return el ? (el.textContent || '') : '';
        }""")
        head = str(txt).split("/")[0].strip()
        return int(head) if head.isdigit() else -1

    def expect_slots(self, n: int, what: str) -> None:
        got = self.slots()
        if got < n:
            self.fails.append(
                f"{what}: wanted {n}+ committed hour(s), got {got} — the film "
                f"would show a turn that does not happen. rows={self.queue()}"
            )

    # ── the fleet roster ────────────────────────────────────────────

    def fleet_verb(self, row: int, verb: str) -> str:
        """One harvester's verb button. Rows are in roster order.

        Indexed with Playwright's ``nth=`` rather than ``:nth-of-type``
        because the roster host holds more than fleet rows, so the CSS
        ordinal and the visible ordinal are not the same number.
        """
        return (f'.cc-fleet-row >> nth={row} '
                f'>> .cc-fleet-verb:has-text("{verb}")')

    def order(self, row: int, at: tuple, steps: tuple = ()) -> None:
        """DROP a harvester, then walk it. The picker re-arms as STEP
        after a landing (v0.9.5), so a walk really is just more clicks."""
        self.click(self.fleet_verb(row, "DROP"), before=380, after=440)
        self.click(self.cell(*at), before=300, after=560, ms=560)
        for st in steps:
            self.click(self.cell(*st), before=200, after=460, ms=340)
        self.escape(after=280)

    def lift(self, row: int) -> None:
        sel = self.fleet_verb(row, "LIFT")
        if not self.pg.locator(sel).count():
            self.fails.append(f"no LIFT verb on fleet row {row}")
            return
        self.click(sel, before=340, after=620)

    # ── riding a live night ─────────────────────────────────────────

    def slot(self) -> str:
        """The clock on screen: ``VESPERA``, ``H01``..``H21``, ``AURORA``."""
        return str(self.pg.evaluate("""() => {
          const e = document.getElementById('replay-slot');
          return e ? (e.textContent || '').trim() : '';
        }"""))

    def _resolving(self) -> bool:
        return bool(self.pg.evaluate(
            "() => document.body.classList.contains('cc-resolving')"))

    # ── replaying a night that has already happened ─────────────────
    #
    # The cinematic runs at the game's pace, which is the right pace for
    # playing and the wrong one for teaching: a collision is over in
    # under a second and the eye has nowhere to be beforehand. There is
    # no speed control to turn down — and adding one to the product for
    # the benefit of the film crew would be the tail wagging the dog —
    # but the replay bar already walks a resolved night an hour at a
    # click, and stepping FORWARD re-fires that hour's animations. So a
    # beat worth a second look gets shown twice: once at speed, then
    # again a hand-cranked hour at a time.

    def replay_rewind_to(self, slot: str, limit: int = 40) -> bool:
        """Step the replay cursor back until the clock reads ``slot``."""
        want = slot.upper()
        for _ in range(limit):
            if self.slot().upper() == want:
                return True
            self.pg.click("#replay-prev")
            self.pg.wait_for_timeout(90)
        self.fails.append(
            f"could not rewind the replay to {want} in {limit} step(s); "
            f"the clock stopped at {self.slot()!r}"
        )
        return False

    def replay_step(self, n: int = 1, hold: int = 1400) -> None:
        """Advance the replay one hour per click, dwelling on each."""
        for _ in range(max(1, n)):
            self.pg.click("#replay-next")
            self.wait(hold)

    def praxis(self, cues: Optional[List[tuple]] = None,
               timeout_ms: int = 150_000) -> None:
        """Commit the night and ride the cinematic, cueing off its clock.

        ``cues`` are ``(slot, text)``, ``(slot, text, delay_ms)`` or
        ``(slot, text, delay_ms, [squares])``. The caption changes when
        that hour reaches the screen rather than after a measured wait,
        because a night's runtime depends on how many hours carry frames
        — a stopwatch drifts off the beat the first time a film's orders
        change.

        The fourth element moves the camera, and exists because a night
        with two events far apart cannot be framed by one static shot:
        fitting both at once drops the zoom to about 1.4x, which is no
        close-up at all. Cue the move on the QUIET hour before the event
        so the camera has settled by the time anything happens.

        The strand guard (v0.9.15) eats the first TRANSMIT and asks
        again, so a single click is not a commit. That is a real thing
        the player meets, and ``basic_stranded`` films it deliberately.
        """
        btn = "#solo-commit-night"
        self.click(btn, before=420, after=1100)
        if self.pg.locator(btn).is_visible():
            self.pg.locator(btn).click()
            self.wait(700)

        # The class goes on at submit; if it never appears the click did
        # not commit and the rest of the film is a static board.
        t0 = time.monotonic()
        while not self._resolving() and (time.monotonic() - t0) < 12:
            time.sleep(0.1)
        if not self._resolving():
            self.fails.append(
                "PRAXIS did not start a night — no `cc-resolving` on <body>. "
                "A guard probably ate the click; the rest of this film is a "
                "still frame."
            )
            return

        pending, seen = self._ride(cues, timeout_ms)
        if pending:
            self.fails.append(
                f"cues never fired: {[c[0] for c in pending]} — the night "
                f"reached {sorted(seen)}, so those captions were never seen"
            )

    def _ride(self, cues: Optional[List[tuple]],
              timeout_ms: int) -> tuple:
        """Poll the on-screen clock and fire cues as their hour lands."""
        pending = list(cues or [])
        seen: set = set()
        deadline = time.monotonic() + timeout_ms / 1000.0
        while self._resolving() and time.monotonic() < deadline:
            now = self.slot()
            if now and now not in seen:
                seen.add(now)
                # Re-aim before anything else. The cinematic rebuilds the
                # grid between hours, and a rebuilt grid can sit at a
                # different offset inside the viewport — the scale
                # survives that, the translate does not, so a close-up
                # set up during planning drifts off its subject the
                # moment the night starts playing. Cheap to just solve it
                # again, and snapping is invisible mid-cinematic.
                self._reaim()
                for cue in list(pending):
                    if cue[0] != now:
                        continue
                    pending.remove(cue)
                    if len(cue) > 2 and cue[2]:
                        self.wait(int(cue[2]))
                    self.say(cue[1])
                    if len(cue) > 3 and cue[3]:
                        self.push_in(*cue[3], ms=560)
            time.sleep(0.1)
        return pending, seen

    def commit_orbit(self, cues: Optional[List[tuple]] = None,
                     timeout_ms: int = 60_000) -> None:
        """Commit the ORBIT phase and ride the beat that follows it.

        The catapults fire and the score folds in on the orbit RESOLVE,
        not on the night — which is the whole point of ``basic_score``.
        A phase only resolves once EVERY seat has committed, so on a
        duel board the rival's orbit has to be posted too; forgetting it
        is not an error, it is a film that quietly sits on a spinning
        board until the timeout.
        """
        btn = "#solo-commit-orbit"
        if not self.pg.locator(btn).is_visible():
            self.fails.append("no ORBIT commit button — wrong phase?")
            return
        self.click(btn, before=420, after=1200)
        t0 = time.monotonic()
        while not self._resolving() and (time.monotonic() - t0) < 12:
            time.sleep(0.1)
        self._ride(cues, timeout_ms)

    # ── looking closely ─────────────────────────────────────────────

    def _reaim(self) -> None:
        """Re-solve the current close-up against the grid as it is now."""
        if not self._cam:
            return
        cells, pad, max_scale = self._cam
        self.pg.evaluate(_PUSH_IN,
                         [[list(c) for c in cells], pad, max_scale, 0])

    def push_in(self, *cells: tuple, pad: float = 1.4, max_scale: float = 4.5,
                ms: int = 900) -> None:
        """Move the CAMERA in until every given square is in frame.

        Not the game's zoom control. The product's zoom dragger spans
        45%-127% of a fit-to-width board, which is a legibility
        preference, not a close-up: at full stretch a harvester wreck is
        still about ten pixels of grey, and a collision burst is gone in
        under a second. The first cut of the crash film used it and the
        two explosions it was built around were invisible.

        So this is a camera move — a CSS transform on the whole map
        viewport, which carries the grid, the FX layer and the daylight
        wash together. Scaling only the grid leaves the explosions
        behind, since ``#collision-fx-layer`` is its sibling, not its
        child.

        Pass every square the beat is about; the scale is solved for,
        never guessed. ``pad`` is in SQUARES and buys room for the burst,
        which is drawn well outside its cell.
        """
        self._cam = (cells, pad, max_scale)
        got0 = self.pg.evaluate(
            _PUSH_IN, [[list(c) for c in cells], pad, max_scale, ms])
        if not got0:
            self.fails.append(f"cannot push in on {list(cells)} — those "
                              f"squares are not on the board, so the "
                              f"close-up shows nothing")
            return
        self.wait(ms + 260)

        # Confirm the camera actually ended up where it was sent. A
        # close-up is the one effect that fails silently: the film still
        # runs, the captions still say "watch this square", and the
        # result is a wide shot with a caption lying over it. Measure the
        # subject on screen instead of trusting the style we just wrote.
        got = self.pg.evaluate("""(cells) => {
          const vp = document.querySelector('.cc-map-viewport');
          if (!vp) return null;
          const vb = vp.getBoundingClientRect();
          const out = [];
          for (const [x, y] of cells) {
            const e = document.querySelector(
              `.cell[data-x="${x}"][data-y="${y}"]`);
            if (!e) return null;
            const b = e.getBoundingClientRect();
            out.push([b.width, b.left >= vb.left - 1 && b.top >= vb.top - 1
              && b.right <= vb.right + 1 && b.bottom <= vb.bottom + 1]);
          }
          return out;
        }""", [list(c) for c in cells])
        if not got:
            self.fails.append(f"push in on {list(cells)}: the board went "
                              f"away mid-move")
            return
        off = [c for c, g in zip(cells, got) if not g[1]]
        if off:
            self.fails.append(
                f"push in on {list(cells)} left {off} outside the frame — "
                f"the close-up is pointed at the wrong ground"
            )
        k, base = float(got0["k"]), float(got0["base"]) or 1.0
        if k > 1.25 and got[0][0] < base * 1.2:
            self.fails.append(
                f"push in on {list(cells)} asked for {k}x but the squares "
                f"came out {got[0][0]:.0f}px against {base:.0f}px unzoomed — "
                f"something reset the camera, so this beat is a wide shot "
                f"with a close-up's caption over it"
            )
        self.expect_overlays_anchored(f"after pushing in on {list(cells)}")

    def expect_overlays_anchored(self, where: str) -> None:
        """The pixel-anchored overlays must match the grid they sit on.

        Vision borders and the planned-orders layer snapshot cell rects
        rather than living in the grid, so any camera move strands them
        at the previous board's geometry. Nothing errors: you get a
        vision border stapled across the middle of a magnified board and
        harvester chips a quarter of the size of the squares they are
        standing on. Compare the layer against the grid and say so.
        """
        got = self.pg.evaluate("""() => {
          const grid = document.querySelector('#map-player .map-grid');
          const svg = document.querySelector('.vision-border-layer');
          if (!grid) return null;
          const g = grid.getBoundingClientRect();
          if (!svg) return {drift: 0, gw: g.width};
          const s = svg.getBoundingClientRect();
          return {drift: Math.max(Math.abs(s.width - g.width),
                                  Math.abs(s.left - g.left),
                                  Math.abs(s.top - g.top)),
                  gw: g.width, sw: s.width};
        }""")
        if not got:
            return
        # A few pixels is rounding; anything more is the wrong geometry.
        if float(got["drift"]) > 8:
            self.fails.append(
                f"{where}: the vision border is drawn on the old grid "
                f"({got.get('sw', 0):.0f}px wide against a {got['gw']:.0f}px "
                f"board, off by {got['drift']:.0f}px) — it will sit across "
                f"the map at the wrong scale"
            )

    def watch_lifters(self) -> None:
        """Start tallying how many Houses have a lifter in the air at once.

        A collision beat is under a second and the craft are a glyph
        wide, so "did both lifters fly?" is not a question watching the
        film reliably answers — the first cut of `basic_crash` shipped
        with the rival's craft suppressed entirely and nobody caught it
        from the video.

        Two narrowings, both learned by writing the loose version first.
        Count DISTINCT seat colours, because one House launching twice
        is not the claim. And count only BOUNCE arcs: every lift at dawn
        is also an orbital ghost, so a census over the whole cinematic
        reaches two colours on the recoveries alone and passes happily
        with the collision itself rendered as a single craft.
        """
        self.pg.evaluate("""() => {
          window.__lifterPeak = 0;
          if (window.__lifterTimer) clearInterval(window.__lifterTimer);
          window.__lifterTimer = setInterval(() => {
            const seen = new Set();
            document.querySelectorAll('.replay-anim-ghost--bounce')
              .forEach((e) => seen.add(e.style.color || ''));
            window.__lifterPeak = Math.max(window.__lifterPeak, seen.size);
          }, 40);
        }""")

    def expect_lifters(self, n: int, where: str) -> None:
        peak = int(self.pg.evaluate("""() => {
          if (window.__lifterTimer) clearInterval(window.__lifterTimer);
          window.__lifterTimer = 0;
          return window.__lifterPeak || 0;
        }""") or 0)
        if peak < n:
            self.fails.append(
                f"{where}: only {peak} House(s) had a lifter on screen at "
                f"once, wanted {n} — the beat plays as one craft bouncing "
                f"off an empty square"
            )

    def pull_out(self, ms: int = 700) -> None:
        self.pg.evaluate("""(ms) => {
          const vp = document.querySelector('.cc-map-viewport');
          if (!vp) return;
          vp.style.transition = `transform ${ms}ms cubic-bezier(.4,0,.2,1)`;
          vp.style.transform = 'none';
          const fx = document.getElementById('collision-fx-layer');
          if (fx && fx.parentElement !== vp) vp.appendChild(fx);
          if (typeof window._osReanchorOverlays === 'function') {
            if (window.__filmCam) cancelAnimationFrame(window.__filmCam);
            const until = performance.now() + ms + 80;
            const chase = () => {
              window._osReanchorOverlays();
              window.__filmCam =
                performance.now() < until ? requestAnimationFrame(chase) : 0;
            };
            chase();
          }
        }""", ms)
        self._cam = None
        self.wait(ms + 200)

    def score(self) -> str:
        return str(self.pg.evaluate("""() => {
          const e = document.querySelector('[data-os-score="p1"]');
          return e ? (e.textContent || '').trim() : '';
        }"""))

    def point_near(self, selector: str, dx: int = 0, dy: int = 0,
                   ms: int = 700) -> None:
        """Put the cursor BESIDE something instead of on top of it.

        Two reasons, both learned from watching the first cut. The ring
        is 26px and a station score is smaller than that, so pointing at
        the number hides the number. And hovering anywhere inside a
        station pops a full observations card over the left third of the
        board, which at some beats is exactly the information you want
        and at others is an empty panel covering the map.
        """
        box = self.pg.locator(selector).first.bounding_box()
        if not box:
            self.fails.append(f"no box for {selector!r} — cannot point at it")
            return
        x = box["x"] + box["width"] / 2 + dx
        y = box["y"] + box["height"] / 2 + dy
        self.pg.evaluate("([x, y, ms]) => window.__film.glide(x, y, ms)",
                         [x, y, ms])
        self.wait(int(ms * 0.9))

    def park(self) -> None:
        """Move the pointer somewhere that pops nothing.

        Harder than it sounds, and worth the trouble. Hovering a station
        pops a large observations card over the left third of the
        screen; hovering a square pops that square's readout. Both are
        the right thing to show when they ARE the subject and pure
        vandalism when the next beat is elsewhere — the first cut parked
        on the middle of the board and left a stale cell card sitting
        over the map through the catapult beat.

        So park in the dead strip under the grid: inside the map frame,
        over no square and no station.
        """
        spot = self.pg.evaluate("""() => {
          const mp = document.getElementById('map-player');
          const vp = document.querySelector('.cc-map-viewport');
          if (!mp || !vp) return null;
          const m = mp.getBoundingClientRect();
          const v = vp.getBoundingClientRect();
          // Under the board if there is room, otherwise beside it.
          if (v.bottom - m.bottom > 40)
            return [m.left + m.width / 2, m.bottom + 22];
          if (v.right - m.right > 40) return [m.right + 22, m.top + 40];
          return null;
        }""")
        if not spot:
            spot = [VIEWPORT["width"] * 0.34, VIEWPORT["height"] * 0.95]
        self.pg.mouse.move(spot[0], spot[1])
        self.pg.evaluate("([x, y]) => window.__film.put(x, y)", spot)
        self.wait(420)
        left = self.tooltip()
        if left:
            self.fails.append(
                f"parked the cursor and a cell card stayed up ({left[:40]!r}) "
                f"— it will sit over the board for the whole next beat"
            )

    def tooltip(self) -> str:
        return str(self.pg.evaluate("""() => {
          const t = document.querySelector('.cell-tooltip');
          return (t && !t.hidden) ? (t.textContent || '')
            .replace(/\\s+/g, ' ').trim() : '';
        }"""))


# ── film registry ───────────────────────────────────────────────────

FILMS: Dict[str, Callable[..., None]] = {}

#: What must be on screen before a film starts. Per-film because the
#: ORDERS panel does not exist during ORBIT and vice versa — waiting on
#: the wrong one is a 25-second timeout, not a useful error.
READY: Dict[str, str] = {}


def film(name: str, ready: str = "#orders-asset-roster") -> Callable:
    def deco(fn: Callable) -> Callable:
        FILMS[name] = fn
        READY[name] = ready
        return fn
    return deco


#: Setup hands the film the squares it chose. The outcome films need
#: this: the rival's orders are already posted at specific coordinates
#: before the page loads, so the film cannot go and pick its own target
#: off the rendered board and hope the two agree.
Plan = Dict[str, Any]


#: The only moves a harvester has. ``session._adj`` is Manhattan-1, so a
#: diagonal step is refused — and refused SILENTLY as far as a film is
#: concerned, because the click still happened and the picker stays
#: armed. A chain builder that offers diagonals therefore produces films
#: that walk two squares while the caption says four.
STEP_RING = ((1, 0), (0, 1), (-1, 0), (0, -1))


def _mid_cells(pg) -> Dict[str, int]:
    """Board extent, so beats aim by fraction rather than by literal.

    A hardcoded (12, 8) breaks silently the day the Basic board changes
    size — it still clicks something, just not the square the caption is
    talking about.
    """
    return pg.evaluate("""() => {
      const cells = [...document.querySelectorAll('.cell')];
      let mx = 0, my = 0;
      for (const c of cells) {
        mx = Math.max(mx, +c.dataset.x);
        my = Math.max(my, +c.dataset.y);
      }
      return { mx, my, n: cells.length };
    }""")


@film("basic_probe")
def _probe(f: Film, base: str, sid: str) -> None:
    """Night one: the board is black, and probes are how you look.

    Shows both routes to the same order — the DEPLOY button and the
    right-click menu — because the second one is invisible until someone
    tells you it is there.
    """
    ext = _mid_cells(f.pg)
    ax, ay = int(ext["mx"] * 0.32), int(ext["my"] * 0.40)
    bx, by = int(ext["mx"] * 0.68), int(ext["my"] * 0.62)

    f.say("The whole board is fog. You cannot see the RED.", hold=2200)

    f.say("Probes are how you look")
    f.click(".cc-deploy-btn", before=520, after=520)

    f.say("The outline is what this probe will reveal")
    # Two hovers before committing: the footprint tracks the pointer, and
    # ONE hover looks like decoration rather than a thing you aim.
    f.hover_cell(int(ext["mx"] * 0.5), int(ext["my"] * 0.3), ms=700, hold=850)
    f.hover_cell(ax, ay, ms=650, hold=950)
    f.click(f.cell(ax, ay), before=350, after=1000, ms=260)
    f.escape()
    f.expect_slots(1, "first probe")

    f.say("Right-click any square for the same orders", hold=700)
    f.right_click(f.cell(bx, by), before=520, after=900)
    # The board menu labels its rows in prose; match on the verb so a
    # label reword does not silently shoot a film of nothing.
    menu_item = '.board-menu-item:has-text("launch probe")'
    if f.pg.locator(menu_item).count():
        f.click(menu_item, before=420, after=900, ms=420)
    else:
        f.fails.append("no 'launch probe' row in the board menu")
    f.escape()
    f.expect_slots(2, "second probe")

    f.say("You start with two. Spend both \u2014 an unspent probe sees nothing.",
          hold=2400)
    f.say(None)
    f.wait(500)


@film("basic_praxis")
def _praxis(f: Film, base: str, sid: str) -> None:
    """Night one: orders are a plan until PRAXIS, and both Houses commit blind."""
    ext = _mid_cells(f.pg)
    ax, ay = int(ext["mx"] * 0.35), int(ext["my"] * 0.45)
    bx, by = int(ext["mx"] * 0.66), int(ext["my"] * 0.55)

    # Put a plan on the books quickly and quietly — this film is about
    # what happens to a plan, not about composing one.
    f.say("Nothing happens until you say so", hold=1500)
    f.click(".cc-deploy-btn", before=320, after=380)
    f.click(f.cell(ax, ay), before=280, after=520, ms=520)
    f.escape(after=250)
    f.click(".cc-deploy-btn", before=320, after=380)
    f.click(f.cell(bx, by), before=280, after=620, ms=520)
    f.escape(after=250)
    f.expect_slots(2, "plan for the praxis film")

    f.say("Your orders stack up as a PLAN")
    if f.pg.locator(".solo-queue-row").count():
        f.glide(".solo-queue-row", ms=700)
        f.wait(1100)
        rows = f.pg.locator(".solo-queue-row")
        if rows.count() > 1:
            f.glide(".solo-queue-row:nth-of-type(2)", ms=460)
            f.wait(900)

    f.say("PRAXIS carries it out")
    f.glide("#solo-commit-night", ms=760)
    f.wait(1200)
    f.say("Your opponent is writing theirs at the same time", hold=2400)
    f.say(None)
    f.wait(500)


def _lit_cells(pg) -> List[Dict[str, int]]:
    """Squares this seat can see RIGHT NOW, nearest the middle first.

    `drop_mode` is `live_only`, so a landing is legal only on live
    ground. A film that drops onto fog is teaching an order the engine
    refuses — which is exactly what the spike did, and passed.
    """
    return pg.evaluate("""() => {
      const cells = [...document.querySelectorAll('.cell')];
      let mx = 0, my = 0;
      for (const c of cells) {
        mx = Math.max(mx, +c.dataset.x);
        my = Math.max(my, +c.dataset.y);
      }
      const cx = mx / 2, cy = my / 2;
      return cells
        .filter((c) => !c.classList.contains('cell--fog')
                    && !c.classList.contains('cell--stale'))
        .map((c) => ({
          x: +c.dataset.x,
          y: +c.dataset.y,
          d: Math.hypot(+c.dataset.x - cx, +c.dataset.y - cy),
        }))
        .sort((a, b) => a.d - b.d);
    }""")


@film("basic_drop")
def _drop(f: Film, base: str, sid: str) -> None:
    """Night two: the whole harvesting turn, done correctly.

    Drop, walk AND lift in one film, deliberately. Splitting the lift
    into its own film left this one ending on a harvester the UI had
    already stickered STRANDED — a film whose last frame is the game
    telling you that you have made a mistake. See ``basic_stranded``,
    which shows that on purpose.
    """
    lit = _lit_cells(f.pg)
    if len(lit) < 6:
        f.fails.append(
            f"only {len(lit)} live squares — nothing legal to land on, so the "
            "film would teach a drop the engine refuses"
        )
        return
    land = lit[0]

    f.say("Seeing RED scores nothing. Harvesting it is the game.", hold=2000)

    f.say("DROP puts a harvester on the surface")
    f.click('.cc-fleet-row .cc-fleet-verb', before=460, after=460)

    f.say("You can only land where you can see RIGHT NOW")
    f.click(f.cell(land["x"], land["y"]), before=520, after=800, ms=700)

    # The picker re-arms as STEP after a landing, by design, so the walk
    # is just more clicks — which is the point worth showing.
    f.say("Keep clicking to walk it \u2014 each step harvests that square")
    walked = 0
    for stepc in _neighbour_chain(lit, land, 3):
        sel = f.cell(stepc["x"], stepc["y"])
        if not f.pg.locator(sel).count():
            continue
        f.click(sel, before=240, after=480, ms=360)
        walked += 1
    if walked < 2:
        f.fails.append(f"only walked {walked} step(s) — no chain to show")
    f.escape(after=300)

    lift = '.cc-fleet-row .cc-fleet-verb:has-text("LIFT")'
    if not f.pg.locator(lift).count():
        f.fails.append("no LIFT verb on the fleet row")
        return
    f.say("Then LIFT, always \u2014 that is the whole turn")
    f.click(lift, before=460, after=1000)
    f.expect_slots(4, "drop + walk + lift")
    f.say(None)
    f.wait(600)


def _neighbour_chain(lit: List[Dict[str, int]], start: Dict[str, int],
                     n: int) -> List[Dict[str, int]]:
    """A short walk of adjacent LIVE squares from ``start``.

    Adjacency matters: a step to a non-adjacent square is refused, so a
    film that jumps is a film of an order that never happens.
    """
    live = {(c["x"], c["y"]) for c in lit}
    chain: List[Dict[str, int]] = []
    cur = (start["x"], start["y"])
    used = {cur}
    for _ in range(n):
        nxt = None
        for dx, dy in STEP_RING:
            cand = (cur[0] + dx, cur[1] + dy)
            if cand in live and cand not in used:
                nxt = cand
                break
        if nxt is None:
            break
        used.add(nxt)
        chain.append({"x": nxt[0], "y": nxt[1]})
        cur = nxt
    return chain


@film("basic_stranded")
def _stranded(f: Film, base: str, sid: str) -> None:
    """Night two: forgetting the lift, committed and paid for.

    The old cut of this stopped at the STRANDED sticker and said "at
    dawn it is destroyed". Telling someone a consequence is not the same
    as showing it, and a film that ends on a warning label is a film you
    can read as a suggestion. So this one commits anyway, rides the
    night to Aurora, and then zooms in on the wreck the sunrise left.
    """
    land = tuple(f.plan["land"])
    walk = [tuple(c) for c in f.plan["walk"]]
    grave = walk[-1] if walk else land

    f.say("Now the mistake everybody makes once", hold=1900)
    f.order(0, land, tuple(walk))

    sticker = '.cc-fleet-row:has-text("STRANDED")'
    if not f.pg.locator(sticker).count():
        f.fails.append(
            "no STRANDED sticker after a drop with no lift — this film has "
            "nothing to point at, and the warning it teaches may be gone"
        )
        return
    f.say("Drop, walk \u2014 and no LIFT. Look at the fleet row.")
    f.glide(sticker, ms=760)
    f.wait(2000)

    # The strand guard eats the first TRANSMIT and asks again. That
    # second chance is the most useful thing on screen and most people
    # click straight through it, so give it its own beat.
    f.say("The game stops you once")
    f.click("#solo-commit-night", before=460, after=1300)
    warn = "#err-solo"
    if f.pg.locator(warn).is_visible():
        f.glide(warn, ms=700)
        f.wait(2600)
    else:
        f.fails.append(
            "no strand warning on the first TRANSMIT — either the guard is "
            "gone or this plan no longer strands anything"
        )
    f.say("Say yes anyway, and watch what dawn does")
    f.praxis(cues=[
        ("H01", "It lands. It works. It fills its hold."),
        ("AURORA", "AURORA \u2014 sunrise sweeps the surface"),
    ])

    f.say("Gone. Harvester and cargo both.", hold=2000)
    f.push_in(grave)
    f.say("That cross is a permanent wreck")
    f.hover_cell(grave[0], grave[1], ms=700, hold=1900)
    # The tooltip renders a wreck as the dagger glyph plus the dead
    # unit's id and the day it died — the word "destroyed" is only the
    # ARIA label, so matching on it passes a film that shows bare ground.
    tip = f.tooltip()
    if "\u2020" not in tip or "lost day" not in tip.lower():
        f.fails.append(
            f"no wreck in the tooltip at {grave} — got {tip[:140]!r}. The "
            f"close-up is pointing at empty ground."
        )
    f.wait(1400)
    f.say("A harvester you do not lift is not yours any more.", hold=2800)
    f.say(None)
    f.wait(600)


@film("basic_crash")
def _crash(f: Film, base: str, sid: str) -> None:
    """Last night: two harvesters cannot share a square — both ways.

    A real crash, twice, in one night. The previous cut of this talked
    about collisions over a board where none happened, because the bot
    in the other seat will not take direction. Setup opens both seats as
    human and posts the rival's night before the camera rolls, so this
    is a genuine simultaneous resolve — the explosions are the engine's,
    not a mock-up.

    Both shapes in one night, deliberately: they look nothing alike on
    screen (one is two ships that never land, the other is a wreck left
    sitting in the road) and a player who has only seen one does not
    recognise the other.
    """
    same = tuple(f.plan["same_square"])
    mine = tuple(f.plan["walk_from"])
    meet = tuple(f.plan["walk_into"])
    theirs = tuple(f.plan["their_from"])

    f.say("Your rival is planning right now, and you cannot see it",
          hold=2400)

    f.say("Send one harvester here")
    f.order(0, same)
    f.lift(0)

    f.say("And walk the other one along this seam")
    f.order(1, mine, (meet,))
    f.lift(1)
    f.expect_slots(5, "two harvesters out, both lifted")

    # The two collisions want opposite cameras, which is why this used
    # to be wrong. A WALK-IN is one sprite arriving at another and reads
    # fine tight. A SIMULTANEOUS DROP is two orbital arcs converging on
    # one square from opposite corners of the board — punch in on the
    # square and both arcs start off-screen, so all you see is a flash
    # in a hole. Hour one is therefore played WIDE, with the whole board
    # in frame and both lifters visible from launch, and the close-up is
    # saved for hour three.
    f.say("Both Houses commit blind. PRAXIS.")
    f.watch_lifters()
    f.praxis(cues=[
        ("H01", "Hour 1 \u2014 you both chose the same landing square"),
        # Hour 2 is the quiet one, so the push happens between the two
        # collisions rather than across either of them.
        ("H02", "Neither lands. Both damaged, both still in orbit.",
         900, [meet, mine, theirs]),
        ("H03", "And yours walks into theirs. Neither moves."),
        ("AURORA", "Your lifts ran, so the wrecks came home"),
    ])

    f.expect_lifters(2, "the simultaneous-drop collision")

    # Hour one again, hand-cranked. At the cinematic's pace two craft
    # meet and are gone inside a second, and nobody watching for the
    # first time knows where to be looking. The replay bar walks the
    # same night an hour a click, and stepping forward re-fires the
    # animations, so this is the identical collision at a speed you can
    # actually read. Gentle push only — the arcs still have to fit.
    f.pull_out()
    f.say("That first one is worth a second look", hold=2000)
    f.push_in(same, pad=5.0, max_scale=1.9, ms=800)
    if f.replay_rewind_to("VESPERA"):
        f.say("Two orbital lifters, one square, neither House knowing")
        f.replay_step(1, hold=2600)
        f.say("Both set down on the same ground. Both bounce.")
        f.replay_step(1, hold=3000)
    f.pull_out()

    # By now the night has resolved, so the ORDERS roster is gone and
    # the aftermath lives in the ORBIT panel: two damaged hulls and a
    # price on the repair.
    f.pull_out()
    dmg = "[data-orbit-damaged-count]"
    if f.pg.locator(dmg).count():
        f.say("Two harvesters, one night, nothing harvested")
        f.glide(dmg, ms=760)
        f.wait(2000)
    count = str(f.pg.evaluate(
        "(s) => { const e = document.querySelector(s); "
        "return e ? (e.textContent || '').trim() : ''; }", dmg))
    if not any(ch.isdigit() and ch != "0" for ch in count):
        f.fails.append(
            f"orbit panel reports {count!r} damaged after two collisions — "
            f"the aftermath this film is built on did not happen"
        )
    f.say("Neither can work again until you pay for REPAIR")
    f.glide('[data-orbit-action="repair"]', ms=700)
    f.wait(2400)
    f.say("Read their trails. Do not share a square.", hold=2600)
    f.say(None)
    f.wait(600)


@film("basic_score")
def _score(f: Film, base: str, sid: str) -> None:
    """Where the number comes from: ground, hold, station, catapult, score.

    This is the one chain in the game that nobody works out by playing,
    because it straddles three phases. You harvest on a night and the
    scoreboard does not move. You commit the orbit and it still does not
    move — you only get a pending "+584" under it. The number itself
    climbs on the NEXT night's dusk, when a catapult you were not
    watching throws the load. Players read the gap as "harvesting does
    nothing" and stop doing it.

    So the film follows one load the whole way and refuses to cut.
    """
    land = tuple(f.plan["land"])
    walk = [tuple(c) for c in f.plan["walk"]]

    f.say("RED in the ground is worth nothing", hold=1700)
    f.hover_cell(land[0], land[1], ms=700, hold=2100)
    if not f.tooltip():
        f.fails.append(
            f"no tooltip over the seam at {land} — the film opens on a "
            f"cell readout that is not there"
        )

    f.say("Land on it, and walk it")
    f.order(0, land, tuple(walk))
    f.say("Every square it crosses goes into the hold", hold=1800)

    f.say("LIFT carries the hold up to your station")
    f.lift(0)
    f.expect_slots(len(walk) + 2, "drop + walk + lift")

    # Hour 1 is the landing, so the lift is one past the last step. Cue
    # off that number rather than a guess: the walk length comes from
    # the board, and a hardcoded H05 lands on the wrong beat the first
    # time the seam is a square shorter.
    lift_hour = f"H{len(walk) + 2:02d}"
    f.praxis(cues=[
        ("H01", "It lands"),
        ("H02", "Every square it cuts turns green \u2014 that is the ore"),
        (lift_hour, "Then the lift carries the hold home"),
    ])

    vault = '[data-os-vault="p1"]'
    if not f.pg.locator(vault).count():
        f.fails.append("no station vault on screen — the middle of the "
                       "chain this film exists to show is missing")
    else:
        f.say("Your station is holding it. Look at your score.")
        f.glide(vault, ms=780)
        f.wait(2200)

    before = f.score()
    f.say("Still nothing. Ore is not score.", hold=2000)

    # A phase resolves when every seat has committed, and on a duel
    # board nobody is playing the other one. Post it now: the ORBIT
    # phase does not exist until the night this film just played
    # resolved, so it could not have been pre-staged.
    submit_orbit(base, sid, [], "p2")
    f.say("Commit the orbit")
    f.commit_orbit()
    f.park()

    delta = '[data-os-score-delta="p1"]'
    pending = str(f.pg.evaluate(
        "(s) => { const e = document.querySelector(s); "
        "return e ? (e.textContent || '').trim() : ''; }", delta))
    if not pending.startswith("+"):
        f.fails.append(
            f"no pending ship delta under the score (got {pending!r}) — the "
            f"beat this film turns on is not on screen"
        )
    f.say(f"{pending or '+0'} is queued on the catapult")
    f.point_near(delta, dx=46, ms=760)
    f.wait(2200)

    # The load only flies on the NEXT night's dusk beat, so the film has
    # to play one more night to show the number move. That gap is not an
    # implementation detail to skip past — it IS the lesson.
    f.park()
    f.say("It ships on the next night. Watch the number.")
    v = view(base, sid)
    submit_night(base, sid, [{"a": "probe", "at": [int(v["width"] * 0.2),
                                                   int(v["height"] * 0.8)]}], "p2")
    f.click(".cc-deploy-btn", before=380, after=420)
    f.click(f.cell(int(v["width"] * 0.5), int(v["height"] * 0.25)),
            before=280, after=520, ms=520)
    f.escape(after=250)
    f.praxis(cues=[
        ("VESPERA", "The catapult loads \u2014 and throws"),
    ])

    after = f.score()
    if _num(after) <= _num(before):
        f.fails.append(
            f"score did not move ({before!r} -> {after!r}) — this film's "
            f"last beat is its whole point and it did not happen"
        )
    f.say("There it is \u2014 banked, and on the board")
    f.point_near('[data-os-score="p1"]', dx=46, ms=760)
    f.wait(2400)
    f.park()

    f.say("Harvest tonight, ship tomorrow. That is the whole loop.",
          hold=2800)
    f.say(None)
    f.wait(600)


def _num(text: str) -> float:
    keep = "".join(ch for ch in str(text) if ch.isdigit() or ch == ".")
    try:
        return float(keep) if keep else -1.0
    except ValueError:
        return -1.0


@film("basic_supersede")
def _supersede(f: Film, base: str, sid: str) -> None:
    """Last night: overlapping probes waste each other."""
    ext = _mid_cells(f.pg)

    f.say("Probes do not stack usefully", hold=1900)
    f.click(".cc-deploy-btn", before=440, after=460)

    # Aim the first at ground already lit, then move to dark ground, so
    # the overlap and the alternative are both visible in one gesture.
    lit = _lit_cells(f.pg)
    if lit:
        f.say("Aim one over ground you already hold \u2014 look how little is new")
        f.hover_cell(lit[0]["x"], lit[0]["y"], ms=700, hold=1700)

    dark = f.pg.evaluate("""() => {
      const cells = [...document.querySelectorAll('.cell.cell--fog')];
      if (!cells.length) return null;
      let mx = 0, my = 0;
      for (const c of document.querySelectorAll('.cell')) {
        mx = Math.max(mx, +c.dataset.x);
        my = Math.max(my, +c.dataset.y);
      }
      // Furthest fogged square from the board centre reads clearly as
      // "somewhere else" rather than as a nudge.
      let best = null, bd = -1;
      for (const c of cells) {
        const d = Math.hypot(+c.dataset.x - mx / 2, +c.dataset.y - my / 2);
        if (d > bd) { bd = d; best = c; }
      }
      return best ? { x: +best.dataset.x, y: +best.dataset.y } : null;
    }""")
    if dark:
        f.say("Somewhere dark buys you far more")
        f.hover_cell(dark["x"], dark["y"], ms=800, hold=1500)
        f.click(f.cell(dark["x"], dark["y"]), before=340, after=900, ms=280)
        f.escape()
        f.expect_slots(1, "spread probe")
    else:
        f.fails.append("no fogged square left to contrast with — board fully lit")

    f.say("Light the ground you mean to walk. Walk everything you light.",
          hold=2600)
    f.say(None)
    f.wait(600)


@film("basic_buy_harvester", ready='[data-orbit-action="build_harvester"]')
def _buy_harvester(f: Film, base: str, sid: str) -> None:
    """Orbit two: the big purchase, and why."""
    f.say("You have banked a night's work and saved a turn's credits",
          hold=2200)

    f.say("One harvester can only work one seam a night")
    f.click('[data-orbit-action="build_harvester"]', before=560, after=900)

    f.say("Watch what the buy leaves you", hold=1800)
    wallet = "[data-readout='wallet'], .cc-orbit-readout"
    if f.pg.locator(wallet).count():
        f.glide(wallet, ms=700)
        f.wait(1500)
    f.say(None)
    f.wait(500)


@film("basic_orbit_probes", ready='[data-orbit-action="build_probe"]')
def _orbit(f: Film, base: str, sid: str) -> None:
    """Orbit: 1000 credits a turn, and vision is what it buys you first."""
    f.say("Between nights you are in orbit", hold=1800)

    wallet = "[data-readout='wallet'], .cc-orbit-readout"
    if f.pg.locator(wallet).count():
        f.glide(wallet, ms=760)
        f.wait(1400)
    f.say("1000 credits arrive every turn", hold=1800)

    probe_buy = '[data-orbit-action="build_probe"]'
    f.say("A harvester costs more than one turn's income")
    f.glide('[data-orbit-action="build_harvester"]', ms=700)
    f.wait(1500)

    f.say("So buy vision \u2014 probes are what you can afford")
    f.click(probe_buy, before=460, after=700)
    f.click(probe_buy, before=320, after=900)

    commit = "#solo-commit-orbit, [data-orbit-commit]"
    if f.pg.locator(commit).count():
        f.say("Commit the phase, same as a night")
        f.glide(commit, ms=700)
        f.wait(1400)
    f.say(None)
    f.wait(500)


# ── ADVANCED: signs, and the two weapons ────────────────────────────
#
# Basic teaches the machine. Advanced teaches the other House: what you
# can read about them without seeing them (signs), and what you can do
# to them without touching them (EMP, chaff). Every one of these is a
# duel, because every lesson needs a rival who turns up on cue.

def _adv_deploy(f: Film, label: str) -> str:
    return f'.cc-deploy-btn:has-text("{label}")'


@film("adv_hotdrop")
def _adv_hotdrop(f: Film, base: str, sid: str) -> None:
    """Night one: read the smear, then land on ground you cannot see.

    The name is the lesson. You are not dropping onto blue you found —
    you are queueing a landing for hour two into a hole hour one has not
    cut yet, on the strength of a glow. The film has to show the drop
    being clicked onto FOG for that to land.
    """
    sign = tuple(f.plan["sign"])
    land = tuple(f.plan["land"])
    step = tuple(f.plan["step"])

    f.say("The board is dark \u2014 but it is not blank", hold=2000)
    f.hover_cell(sign[0], sign[1], ms=900, hold=1800)
    f.say("That glow is a BLUE SIGN. Blue is radioactive, and the smear "
          "has been there since the season opened.", hold=3200)
    f.say("It says a blue pocket is somewhere under here. Not which "
          "square, and it never fades \u2014 not even once the blue is gone.",
          hold=3400)

    f.say("Probe the brightest part of it")
    f.click('.cc-deploy-btn:has-text("LAUNCH PROBE")', before=460, after=420)
    f.click(f.cell(sign[0], sign[1]), before=520, after=900, ms=700)
    f.escape(after=300)

    f.say("Now the HOT DROP: land the harvester on hour two, into the "
          "hole hour one has not cut yet", hold=3000)
    f.click('.cc-fleet-row .cc-fleet-verb', before=460, after=460)
    f.say("Still fog. You are aiming at the sign, not at anything you "
          "can see.")
    f.click(f.cell(land[0], land[1]), before=620, after=900, ms=760)
    f.click(f.cell(step[0], step[1]), before=300, after=560, ms=420)
    f.escape(after=300)

    lift = '.cc-fleet-row .cc-fleet-verb:has-text("LIFT")'
    if not f.pg.locator(lift).count():
        f.fails.append("no LIFT verb on the fleet row")
        return
    f.click(lift, before=420, after=800)
    f.expect_slots(4, "probe + hot drop + step + lift")

    f.praxis(cues=[
        ("H01", "Hour one \u2014 the probe opens the disk"),
        ("H02", "Hour two \u2014 and the landing you already committed to",
         600, [land, step]),
        ("H03", "BLUE 255. The guess paid.", 700),
        ("AURORA", "Blue is not score. Blue is what buys weapons.", 500),
    ])
    f.pull_out()
    f.say("A hot drop can miss. A probe you never follow always does.",
          hold=2600)
    f.say(None)
    f.wait(600)


@film("adv_buy_emp", ready='[data-orbit-action="build_emp"]')
def _adv_buy_emp(f: Film, base: str, sid: str) -> None:
    """Orbit two: weapons are bought with blue, not credits."""
    f.say("Credits buy hulls. Weapons cost BLUE.", hold=2400)

    blue = "#cc-orbit-blue-total, [data-readout='blue']"
    if f.pg.locator(blue).count():
        f.say("This is the blue you brought home last night")
        f.point_near(blue, dx=0, dy=-26, ms=760)
        f.wait(1800)
    else:
        f.fails.append("no blue readout in the orbit panel to point at")

    cost = '[data-orbit-cost="build_emp"]'
    if f.pg.locator(cost).count():
        f.say("An EMP is 200 blue and 250 credits")
        f.point_near(cost, dx=0, dy=-26, ms=700)
        f.wait(1600)

    f.say("You start each season with 250 blue \u2014 one weapon's worth, "
          "and no more. Everything after that you have to go and dig up.",
          hold=3400)

    f.say("Buy one")
    f.click('[data-orbit-action="build_emp"]', before=520, after=900)
    f.wait(900)

    f.say("Now watch the projected blue drop", hold=2000)
    if f.pg.locator("#cc-orbit-blue-proj").count():
        f.point_near("#cc-orbit-blue-proj", dx=0, dy=-26, ms=700)
        f.wait(1600)
    f.say(None)
    f.wait(500)


@film("adv_redsign")
def _adv_redsign(f: Film, base: str, sid: str) -> None:
    """Night two: your probe finds a pure seam, and tells everyone.

    The beat that matters is not the discovery — it is the second after
    it, when the film says out loud that the rival is now looking at the
    same beacon. A jackpot you find quietly would be worth hoarding; a
    jackpot that announces itself is a race, and that is the whole
    reason the Advanced board plays differently from Basic.
    """
    mine = tuple(f.plan["mine"])

    quiet = tuple(f.plan["quiet"])

    f.say("Somewhere out there is PURE red \u2014 255, the richest square "
          "the map makes", hold=2800)
    f.say("Two probes, two guesses")
    # The jackpot goes SECOND. Queue position is the hour, a one-order
    # night is one hour long, and a discovery that lands in the same
    # breath as "here is your first probe" has no room to be a reveal.
    f.click('.cc-deploy-btn:has-text("LAUNCH PROBE")', before=460, after=420)
    f.click(f.cell(quiet[0], quiet[1]), before=520, after=800, ms=660)
    f.escape(after=300)
    f.click('.cc-deploy-btn:has-text("LAUNCH PROBE")', before=380, after=380)
    f.click(f.cell(mine[0], mine[1]), before=520, after=860, ms=660)
    f.escape(after=300)
    f.expect_slots(2, "a probe elsewhere, then one onto the jackpot")

    f.praxis(cues=[
        ("H01", "Hour one \u2014 the disk opens", 400),
        ("H02", "A RED SIGN. You have found a pure seam.", 900, [mine]),
    ])
    f.wait(1400)

    beacon = ".redsign-cell, .redsign-beacon"
    if not f.pg.locator(beacon).count():
        f.fails.append(
            "no redsign painted after probing a pure-255 cell \u2014 this "
            "film's entire subject is missing from the frame"
        )
    f.say("And so has everybody else.", hold=2400)
    f.say("A red sign is PUBLIC. It does not name who lit it, but the "
          "beacon is on every House's map from this hour.", hold=3400)
    f.pull_out()
    f.say("Pures are rationed \u2014 a couple on a board this size. That "
          "makes every one of them contested by default.", hold=3400)
    f.say(None)
    f.wait(600)


@film("adv_redsign_rival")
def _adv_redsign_rival(f: Film, base: str, sid: str) -> None:
    """Night two, the other way round: a beacon you did not light.

    Shot as the mirror of ``adv_redsign`` on purpose. Same night, same
    board, and the player does something harmless somewhere else — so
    the only thing that changes on their map is a beacon arriving out of
    empty fog, with no probe of theirs anywhere near it.
    """
    theirs = tuple(f.plan["theirs"])
    quiet = tuple(f.plan["quiet"])

    sign = tuple(f.plan["sign"])

    f.say("This time you go about your own business", hold=2200)
    f.click('.cc-deploy-btn:has-text("LAUNCH PROBE")', before=460, after=420)
    f.click(f.cell(quiet[0], quiet[1]), before=520, after=860, ms=700)
    f.escape(after=300)
    # Second probe for the same reason as in adv_redsign: one order is
    # one hour, and the beacon needs an hour of its own to arrive in.
    f.click('.cc-deploy-btn:has-text("LAUNCH PROBE")', before=380, after=380)
    f.click(f.cell(sign[0], sign[1]), before=460, after=800, ms=620)
    f.escape(after=300)

    f.praxis(cues=[
        ("H01", "Your probes open, over here", 400),
        ("H02", "\u2014 and a RED SIGN blazes over there.", 1100, [theirs]),
    ])
    f.wait(1500)

    beacon = ".redsign-cell, .redsign-beacon"
    if not f.pg.locator(beacon).count():
        f.fails.append(
            "no redsign on the board \u2014 the rival's discovery never "
            "reached this seat, which is the one thing the film claims"
        )
    f.say("You have no probe within a mile of it. That is the other "
          "House finding a pure seam.", hold=3200)
    f.say("You learn the same hour they do, and roughly where. You do "
          "NOT learn which square, or what they mean to do about it.",
          hold=3600)
    f.pull_out()
    f.say("Which is the point: a jackpot cannot be hidden. It can only "
          "be reached first.", hold=3000)
    f.say(None)
    f.wait(600)


@film("adv_emp")
def _adv_emp(f: Film, base: str, sid: str) -> None:
    """Night three: take their eye off the jackpot, then use it yourself.

    Two halves, and the second is the one people miss. Frying a probe
    is satisfying; the reason to do it is that ``live_only`` drops mean
    a House with no eye on a square cannot land on it. Eight hours of
    cloud is eight hours in which that seam is yours alone.
    """
    theirs = tuple(f.plan["theirs"])
    salvo = [tuple(c) for c in f.plan["salvo"]]
    beside = tuple(f.plan["beside"])

    f.say("The other House has an eye on their jackpot", hold=2400)
    f.hover_cell(theirs[0], theirs[1], ms=900, hold=1600)

    f.say("One EMP launch is a salvo of three")
    f.click(_adv_deploy(f, "EMP"), before=520, after=520)
    f.say("Each missile is a radius-2 diamond. Overlap them and you get "
          "a wall, not three puddles.", hold=2600)
    for c in salvo:
        f.click(f.cell(c[0], c[1]), before=300, after=520, ms=420)
    f.escape(after=400)

    f.say("Now a probe of your own \u2014 just OUTSIDE the wall")
    f.click('.cc-deploy-btn:has-text("LAUNCH PROBE")', before=460, after=420)
    f.click(f.cell(beside[0], beside[1]), before=520, after=800, ms=640)
    f.escape(after=300)

    f.say("And land on it. Beside a cloud still harvests \u2014 inside one "
          "does not.", hold=2800)
    f.click('.cc-fleet-row .cc-fleet-verb', before=460, after=460)
    f.click(f.cell(beside[0], beside[1]), before=520, after=800, ms=640)
    f.escape(after=300)
    lift = '.cc-fleet-row .cc-fleet-verb:has-text("LIFT")'
    if f.pg.locator(lift).count():
        f.click(lift, before=380, after=700)
    f.expect_slots(4, "salvo + probe + drop + lift")

    f.praxis(cues=[
        ("H01", "Three missiles, one wall", 500, salvo + [theirs]),
        ("H02", "Their probe is gone. The beacon stays lit.", 1200),
        ("H03", "They still know the seam is there \u2014 and can no longer "
         "see it, so they cannot land on it.", 900),
        ("H04", "You land one square clear of the cloud, and harvest "
         "normally.", 800, [beside]),
        ("AURORA", "Eight hours of denial. You choose when that ground "
         "is open.", 600),
    ])
    f.pull_out()
    f.say("EMP does not take the red. It takes the CLOCK.", hold=2800)
    f.say(None)
    f.wait(600)


@film("adv_buy_chaff", ready='[data-orbit-action="build_chaff"]')
def _adv_buy_chaff(f: Film, base: str, sid: str) -> None:
    """Orbit three: a second hull, and the dearest thing on the board."""
    f.say("Two seams need two harvesters", hold=2200)
    f.click('[data-orbit-action="build_harvester"]', before=520, after=860)

    cost = '[data-orbit-cost="build_chaff"]'
    if f.pg.locator(cost).count():
        f.say("Chaff costs no credits at all \u2014 and 255 blue")
        f.point_near(cost, dx=0, dy=-26, ms=700)
        f.wait(2000)
    f.say("That is more than the 250 you start a season with. Chaff is "
          "not something you can buy \u2014 it is something you mine for.",
          hold=3400)

    f.click('[data-orbit-action="build_chaff"]', before=520, after=900)
    f.wait(900)
    if f.pg.locator("#cc-orbit-blue-proj").count():
        f.point_near("#cc-orbit-blue-proj", dx=0, dy=-26, ms=700)
        f.wait(1600)
    f.say("If you cannot afford it this turn, that is not a mistake. "
          "Go and land on blue.", hold=3000)
    f.say(None)
    f.wait(500)


@film("adv_chaff")
def _adv_chaff(f: Film, base: str, sid: str) -> None:
    """Night four: cancel a lift, and let the sunrise do the rest.

    Chaff reads like a delay weapon — three hours where nobody acts —
    and used as one it mostly wastes your own turn too. Its real use is
    surgical: the lifter is the only way off the surface, a cancelled
    pickup cannot be re-queued, and dawn kills whatever is still down
    there. Three hours of jamming, aimed at one of them, is a kill.
    """
    grave = tuple(f.plan["grave"])

    f.say("Chaff jams every House for three hours. Yours included.",
          hold=2800)
    f.say("Used for denial that is an expensive shrug", hold=2400)
    f.say("Aim it at one hour instead \u2014 the hour they reach for the "
          "lifter", hold=2800)

    # Four waits, so the flare goes up on H05 and smothers H05-H07.
    # Three was a hour too early: it ate the rival's last STEP as well,
    # and a harvester that never finished walking dies in the wrong
    # square with the wrong lesson attached — it looks like chaff stops
    # movement, when the thing worth teaching is that it stops the exit.
    f.say("Let them land. Let them work. Let them fill the hold.",
          hold=2600)
    for _ in range(4):
        f.click('.cc-deploy-btn:has-text("WAIT")', before=240, after=340)

    f.say("Flare on the hour they reach for the lifter")
    f.click(_adv_deploy(f, "CHAFF"), before=520, after=900)
    f.say("Three slots: the flare, and two hours of jamming yourself",
          hold=2600)
    f.expect_slots(5, "four waits and a flare")

    f.praxis(cues=[
        ("H02", "They land and start working", 500),
        ("H05", "Flare. Nobody acts for three hours \u2014 you included.",
         700),
        ("H06", "That was their pickup hour. The lifter never came.",
         900, [grave]),
        ("AURORA", "And the dawn wave takes whatever is still standing.",
         800, [grave]),
    ])
    f.wait(1600)

    f.say("A harvester, and everything in its hold", hold=2400)
    f.push_in(grave, pad=2.4, ms=900)
    f.hover_cell(grave[0], grave[1], ms=800, hold=2400)
    tip = f.tooltip()
    if "\u2020" not in tip and "lost" not in tip.lower():
        f.fails.append(
            f"no wreck in the tooltip at {grave}: {tip!r} \u2014 the close-up "
            "is pointing at empty ground"
        )
    f.wait(1200)
    f.pull_out()
    f.say("You never touched it. You just took away the ride home.",
          hold=3000)
    f.say(None)
    f.wait(600)


# ── setup: getting a session to the turn a film needs ───────────────

#: Films that need a scriptable rival rather than the bot. Kept as a set
#: so ``setup_for`` routes on membership and nobody has to remember which
#: constructor a film wanted.
DUEL_FILMS = {"basic_crash", "basic_stranded", "basic_score"}


def setup_for(base: str, name: str, seed: int) -> tuple[str, Plan]:
    """Create a session, walk it to the state ``name`` films, and say
    which squares it committed the rival to.

    Driven over HTTP rather than by clicking, deliberately: setup is not
    the lesson, and clicking it would put four minutes of it in frame.
    """
    if name in ADVANCED_FILMS:
        return _setup_advanced(base, name)
    if name in DUEL_FILMS:
        return _setup_duel(base, name, seed)

    sid = seed_game(base, seed)
    st = status(base, sid)

    if name in ("basic_probe", "basic_praxis"):
        # Night one as the player meets it. If the game opens in ORBIT,
        # pass through it empty so the film starts on the planning board.
        if str(st.get("phase", "")).lower().startswith("orbit"):
            submit_orbit(base, sid, [])
        return sid, {}

    if name == "basic_orbit_probes":
        # The first ORBIT the player sees. A session opens on day 1
        # PLANNING, so that is one night away, not zero.
        if str(st.get("phase", "")).lower().startswith("orbit"):
            return sid, {}
        submit_night(base, sid, _probe_opening(base, sid))
        return sid, {}

    if name == "basic_drop":
        # Night two, with ground already lit. The film needs a harvester
        # in orbit AND live vision to land it on, and a probe outlives
        # the night that launched it (probe_lifetime_nights), so night
        # one's pair are still open here.
        submit_night(base, sid, _probe_opening(base, sid))
        submit_orbit(base, sid, [{"a": "build_probe", "count": 2}])
        return sid, {}

    if name == "basic_buy_harvester":
        # Orbit two, with a night's takings banked so the harvester is
        # a decision rather than an impossibility.
        submit_night(base, sid, _probe_opening(base, sid))
        submit_orbit(base, sid, [{"a": "build_probe", "count": 2}])
        submit_night(base, sid, _probe_opening(base, sid))
        return sid, {}

    if name == "basic_supersede":
        # The last night, with two nights of play behind it: trails on
        # the board and enough ground lit that "spread your probes" has
        # somewhere to point.
        submit_night(base, sid, _probe_opening(base, sid))
        submit_orbit(base, sid, [{"a": "build_probe", "count": 2}])
        submit_night(base, sid, _probe_opening(base, sid))
        submit_orbit(base, sid, [
            {"a": "build_harvester"},
            {"a": "build_probe", "count": 2},
        ])
        return sid, {}

    raise SystemExit(f"no setup defined for film {name!r}")


# ── setup for the outcome films (both seats human) ──────────────────
#
# Two probes on the SAME tile supersede each other, so the two seats are
# always offset here. Getting that wrong blinds both Houses and the
# resulting film is a drop onto fog that the engine then refuses — with
# every assertion still green, because the orders did reach the queue.

def _duel_probes(w: int, h: int, wave: int) -> tuple[List[dict], List[dict]]:
    """This night's probes for (player, rival), aimed off board extent."""
    my = [(0.42, 0.50), (0.62, 0.50)] if wave == 0 else [(0.46, 0.34), (0.58, 0.66)]
    yours = [(0.50, 0.42), (0.70, 0.58)] if wave == 0 else [(0.54, 0.30), (0.66, 0.62)]
    mk = lambda pts: [{"a": "probe", "at": [int(w * fx), int(h * fy)]}
                      for fx, fy in pts]
    return mk(my), mk(yours)


def _setup_duel(base: str, name: str, seed: int) -> tuple[str, Plan]:
    sid = seed_duel(base, seed)
    v = view(base, sid)
    w, h = int(v["width"]), int(v["height"])

    mine, theirs = _duel_probes(w, h, 0)
    submit_night(base, sid, mine, "p1")
    submit_night(base, sid, theirs, "p2")
    buy: List[dict] = [{"a": "build_probe", "count": 2}]
    submit_orbit(base, sid, buy, "p1")
    submit_orbit(base, sid, buy, "p2")

    mine, theirs = _duel_probes(w, h, 1)
    submit_night(base, sid, mine, "p1")
    submit_night(base, sid, theirs, "p2")

    if name == "basic_crash":
        # Both crash shapes have to fit in ONE night, which needs two
        # harvesters a seat. At 1500c against 1000c a turn that is why
        # this film costs two nights of build-up and the others do not.
        submit_orbit(base, sid, [{"a": "build_harvester"}], "p1")
        submit_orbit(base, sid, [{"a": "build_harvester"}], "p2")
        return sid, _plan_crash(base, sid)

    submit_orbit(base, sid, [{"a": "build_probe", "count": 2}], "p1")
    submit_orbit(base, sid, [{"a": "build_probe", "count": 2}], "p2")
    # The rival stays out of shot for these two: they are about what the
    # player's own orders do, and a second House wandering through frame
    # is just noise the caption has to compete with.
    submit_night(base, sid, [{"a": "probe", "at": [int(w * 0.12),
                                                   int(h * 0.15)]}], "p2")
    if name == "basic_score":
        return sid, _plan_seam(base, sid, steps=3, want_red=True)
    return sid, _plan_seam(base, sid, steps=2, want_red=True)


# ── setup for the Advanced arc ──────────────────────────────────────
#
# One board, one storyline, seven films cut out of different turns of
# it. Each shoot replays the same history from scratch and stops at the
# turn its film opens on, so the reels join up: the blue banked in the
# first film is the blue spent in the second, and the probe fried in the
# fifth is the one the rival launched in the fourth.

#: Advanced films, all of them duels — see ``_setup_advanced``.
ADVANCED_FILMS = {
    "adv_hotdrop", "adv_buy_emp", "adv_redsign", "adv_redsign_rival",
    "adv_emp", "adv_buy_chaff", "adv_chaff",
}

#: Where in the storyline each film opens. Order matters: the setup
#: replays every earlier turn before handing the session to the camera.
_ADV_TURN = {
    "adv_hotdrop": 0,        # night 1, as the player meets it
    "adv_buy_emp": 1,        # orbit 2
    "adv_redsign": 2,        # night 2
    "adv_redsign_rival": 2,  # night 2, mirrored
    "adv_buy_chaff": 3,      # orbit 3
    "adv_emp": 4,            # night 3
    "adv_chaff": 6,          # night 4
}


def _setup_advanced(base: str, name: str) -> tuple[str, Plan]:
    """Replay the Advanced storyline up to the turn ``name`` opens on.

    Both seats are human. Every Advanced lesson is about the OTHER
    House — a beacon they light, a probe you fry, a lift you cancel —
    and the bot will not do any of those on cue.

    The seed is pinned rather than taken from the batch: this board's
    blue pocket and two jackpots are load-bearing (see ``ADVANCED_SEED``),
    and a film of a hot drop onto ground that has no blue under it is a
    film of nothing.

    THE RULE THAT BITES: whenever the camera is going to commit a night,
    the rival's orders for THAT night must already be in. Two human
    seats means the first to transmit is put into "waiting for the other
    House", which locks the button — and locks it in a way that looks
    exactly like a hang, thirty seconds into a shoot that has already
    run a minute. So every branch below that hands over a PLANNING turn
    posts p2's night on the way out.
    """
    stop = _ADV_TURN[name]
    sid = seed_duel(base, ADVANCED_SEED, cap=6, preset="advanced")
    plan: Plan = {
        "sign": list(ADV_SIGN), "land": list(ADV_BLUE_LAND),
        "step": list(ADV_BLUE_STEP), "mine": list(ADV_MINE),
        "theirs": list(ADV_THEIRS), "quiet": list(ADV_QUIET),
        "salvo": [list(c) for c in ADV_SALVO], "beside": list(ADV_BESIDE),
    }
    mine_h = harvester_ids(base, sid, "p1")[0]

    def probe(at) -> dict:
        return {"a": "probe", "at": list(at)}

    # ── turn 0 · night 1 — the hot drop that funds everything ────────
    if stop <= 0:
        submit_night(base, sid, [probe(ADV_QUIET)], "p2")
        return sid, plan
    submit_night(base, sid, [
        probe(ADV_SIGN),
        {"a": "drop", "unit": mine_h, "at": list(ADV_BLUE_LAND)},
        {"a": "step", "unit": mine_h, "to": list(ADV_BLUE_STEP)},
        {"a": "pickup", "unit": mine_h},
    ], "p1")
    submit_night(base, sid, [probe(ADV_QUIET)], "p2")

    # ── turn 1 · orbit 2 — blue becomes an EMP ───────────────────────
    if stop <= 1:
        return sid, plan
    submit_orbit(base, sid, [
        {"a": "build_emp", "count": 1},
        {"a": "build_probe", "count": 2},
    ], "p1")
    # The rival buys the harvester here that the chaff film later
    # strands. Buying it later would leave them nothing to lose.
    submit_orbit(base, sid, [
        {"a": "build_probe", "count": 2},
        {"a": "build_harvester"},
    ], "p2")

    # ── turn 2 · night 2 — a beacon each ─────────────────────────────
    if stop <= 2:
        # Both redsign films open here, and they want opposite things of
        # the rival. The mirror film needs their discovery to happen
        # DURING the filmed night, so the camera catches the beacon
        # arriving out of nowhere. The other film needs them to light
        # NOTHING, or two beacons come up at once and "you found it"
        # stops being a sentence about the player.
        if name == "adv_redsign_rival":
            # A WAIT in front so their discovery lands on H02. Their
            # probe on H01 would put the beacon up in the same hour the
            # player's own first probe opens, and the film's one reveal
            # would arrive before anyone had a reason to look.
            submit_night(base, sid,
                         [{"a": "wait"}, probe(ADV_THEIRS)], "p2")
        else:
            submit_night(base, sid, [probe(ADV_QUIET2)], "p2")
        return sid, plan
    submit_night(base, sid, [probe(ADV_MINE)], "p1")
    submit_night(base, sid, [probe(ADV_THEIRS)], "p2")

    # ── turn 3 · orbit 3 — the second hull, and the chaff ────────────
    if stop <= 3:
        return sid, plan
    submit_orbit(base, sid, [
        {"a": "build_chaff", "count": 1},
        {"a": "build_harvester"},
        {"a": "build_probe", "count": 2},
    ], "p1")
    submit_orbit(base, sid, [{"a": "build_probe", "count": 2}], "p2")

    # ── turn 4 · night 3 — the salvo ─────────────────────────────────
    if stop <= 4:
        # The rival's eye has to still be ON the jackpot for the salvo
        # to take it, so they re-probe it this night.
        submit_night(base, sid, [probe(ADV_THEIRS)], "p2")
        return sid, plan
    submit_night(base, sid, [
        {"a": "emp_launch", "at": [list(c) for c in ADV_SALVO]},
        probe(ADV_BESIDE),
    ], "p1")
    submit_night(base, sid, [probe(ADV_THEIRS)], "p2")

    # ── turn 5 · orbit 4 ─────────────────────────────────────────────
    submit_orbit(base, sid, [{"a": "build_probe", "count": 2}], "p1")
    submit_orbit(base, sid, [{"a": "build_probe", "count": 2}], "p2")

    # ── turn 6 · night 4 — the lift that never comes ─────────────────
    # Their whole night is posted before the camera rolls: hot drop,
    # two squares of work, then reach for the lifter on H05. Our flare
    # goes up on H04 and smothers H04-H06.
    their_h = [
        u["id"] for u in view(base, sid, "p2")["units"]
        if u.get("type") == "harvester" and u.get("orbit")
    ]
    if not their_h:
        raise SystemExit(
            "advanced setup left the rival with no harvester in orbit — "
            "adv_chaff would have nothing to strand"
        )
    walk = [(ADV_THEIRS[0], ADV_THEIRS[1] - 1),
            (ADV_THEIRS[0] + 1, ADV_THEIRS[1] - 1)]
    submit_night(base, sid, [
        probe(ADV_THEIRS),
        {"a": "drop", "unit": their_h[0], "at": list(ADV_THEIRS)},
        {"a": "step", "unit": their_h[0], "to": list(walk[0])},
        {"a": "step", "unit": their_h[0], "to": list(walk[1])},
        {"a": "pickup", "unit": their_h[0]},
    ], "p2")
    plan["grave"] = list(walk[1])
    return sid, plan


def _plan_seam(base: str, sid: str, steps: int, want_red: bool) -> Plan:
    """A walkable run, richest RED first.

    Picked from the engine's own live set rather than from the rendered
    board, because setup runs before the page exists — and because
    "looks red" and "is live" are different questions.
    """
    live = live_squares(base, sid, "p1")
    if not live:
        raise SystemExit("duel setup left p1 with no live ground to land on")
    scored = sorted(
        live.items(),
        key=lambda kv: -_purity(kv[1]) if want_red else 0,
    )
    for start, _ in scored[:40]:
        run = _walk_run(live, start, steps, prefer_red=want_red)
        if len(run) == steps + 1:
            return {"land": list(run[0]), "walk": [list(c) for c in run[1:]]}
    raise SystemExit(
        f"no run of {steps + 1} adjacent live squares — cannot stage a walk"
    )


def _plan_crash(base: str, sid: str) -> Plan:
    """Pick the three squares both crashes need, then post the rival's night.

    ``same`` is where both Houses land at hour 1. ``meet`` is where the
    rival's second harvester will be standing when the player's walks
    into it. They have to be in BOTH seats' live vision or one of the
    two orders is refused and the film shows half a lesson.
    """
    mine = live_squares(base, sid, "p1")
    yours = live_squares(base, sid, "p2")
    shared = set(mine) & set(yours)
    if len(shared) < 12:
        raise SystemExit(
            f"only {len(shared)} squares lit for both seats — not enough "
            f"shared ground to stage a crash"
        )
    quad = _crash_quad(shared, mine)
    if quad is None:
        raise SystemExit("no adjacent trio in shared vision for the walk-in")
    same, from_mine, meet, from_theirs = quad

    ids_me = harvester_ids(base, sid, "p1")
    ids_you = harvester_ids(base, sid, "p2")
    if len(ids_me) < 2 or len(ids_you) < 2:
        raise SystemExit(
            f"a seat has fewer than two harvesters (p1={ids_me}, p2={ids_you})"
            f" — both crash shapes will not fit in one night"
        )

    # The rival's night, on the books before the camera rolls. Their
    # walk goes in at hour 2 and the player's at hour 3, so the player
    # arrives to find the square already taken — the shape a real player
    # meets, rather than a dead heat.
    submit_night(base, sid, [
        {"a": "drop", "unit": ids_you[0], "at": list(same)},
        {"a": "drop", "unit": ids_you[1], "at": list(from_theirs)},
        {"a": "step", "unit": ids_you[1], "to": list(meet)},
        {"a": "pickup", "unit": ids_you[1]},
    ], "p2")
    return {
        "same_square": list(same),
        "walk_from": list(from_mine),
        "walk_into": list(meet),
        "their_from": list(from_theirs),
    }


#: How far apart the two crash sites must be, in squares. Close enough
#: that one zoomed frame holds both, far enough that they read as two
#: events rather than one pile-up. The first cut put them diagonally
#: adjacent and the second collision looked like debris from the first.
CRASH_SPREAD = (3, 5)


def _crash_quad(shared: set, live: Dict[tuple, dict]):
    """``(same, from_mine, meet, from_theirs)`` — all lit for both seats.

    ``meet`` needs two free neighbours, one for each House to walk in
    from, and has to sit ``CRASH_SPREAD`` away from ``same``.
    """
    lo, hi = CRASH_SPREAD
    ordered = sorted(shared, key=lambda c: -_purity(live.get(c, {})))
    for meet in ordered:
        nbrs = [(meet[0] + dx, meet[1] + dy) for dx, dy in STEP_RING]
        nbrs = [n for n in nbrs if n in shared]
        if len(nbrs) < 2:
            continue
        for same in ordered:
            gap = max(abs(same[0] - meet[0]), abs(same[1] - meet[1]))
            if not (lo <= gap <= hi):
                continue
            spare = [n for n in nbrs if n != same]
            if len(spare) >= 2:
                return same, spare[0], meet, spare[1]
    return None


def _purity(cell: dict) -> int:
    if str(cell.get("tile")) != "RED":
        return -1
    return int(cell.get("purity") or 0)


def _walk_run(live: Dict[tuple, dict], start: tuple, n: int,
              prefer_red: bool) -> List[tuple]:
    out = [start]
    used = {start}
    cur = start
    for _ in range(n):
        best = None
        for dx, dy in STEP_RING:
            c = (cur[0] + dx, cur[1] + dy)
            if c in used or c not in live:
                continue
            p = _purity(live[c])
            if prefer_red and p < 0:
                continue
            if best is None or p > best[1]:
                best = (c, p)
        if best is None:
            break
        used.add(best[0])
        out.append(best[0])
        cur = best[0]
    return out


def _probe_opening(base: str, sid: str) -> List[dict]:
    """Two probes into the middle of the board — the honest first turn.

    Aimed off the board's real extent rather than at literal coordinates,
    so a change to the Basic board size moves the probes with it instead
    of silently putting them in a corner.
    """
    v = view(base, sid)
    w = int(v.get("width") or 24)
    h = int(v.get("height") or 16)
    return [
        {"a": "probe", "at": [int(w * 0.35), int(h * 0.45)]},
        {"a": "probe", "at": [int(w * 0.65), int(h * 0.55)]},
    ]


# ── shoot ───────────────────────────────────────────────────────────

def _post(final: pathlib.Path, lead: float, trim: bool) -> str:
    """Cut the boot off the front and re-encode.

    Two problems, one pass. The recording starts when the page is
    created, so every film opens on several seconds of curtain — dead
    weight in a clip the modal LOOPS. And Playwright's raw webm is ~3x
    larger than it needs to be for a near-static UI, which matters
    because these ship in the repo and load in a modal.

    Best-effort: no ffmpeg, or a failed encode, leaves the raw file in
    place. A slightly long film is worth having; no film is not.
    """
    if not trim:
        return ""
    start = max(0.0, lead - 0.35)  # keep a beat of black, then the fade
    tmp = final.with_suffix(".post.webm")
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-ss", f"{start:.2f}", "-i", str(final),
        "-c:v", "libvpx", "-crf", "32", "-b:v", "0",
        "-qmin", "4", "-qmax", "44",
        "-deadline", "good", "-cpu-used", "2", "-an", str(tmp),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=300)
    except (OSError, subprocess.SubprocessError):
        tmp.unlink(missing_ok=True)
        return "  (raw — no ffmpeg?)"
    if tmp.stat().st_size < 20_000:
        tmp.unlink(missing_ok=True)
        return "  (raw — post-pass output looked empty)"
    final.unlink()
    tmp.rename(final)
    return f"  (-{start:.1f}s boot)"


def shoot(base: str, name: str, seed: int, keep_raw: bool,
          trim: bool = True) -> tuple[bool, str]:
    fn = FILMS[name]
    sid, plan = setup_for(base, name, seed)
    if plan:
        print(f"  {name:24s} staged {json.dumps(plan)}")
    OUT.mkdir(parents=True, exist_ok=True)
    # OUT is a SERVED directory. Playwright names its raw capture after
    # the page, and a shoot that dies before the rename leaves that file
    # behind — where it would otherwise get committed and shipped.
    for stray in OUT.glob("page@*.webm"):
        stray.unlink(missing_ok=True)

    fails: List[str] = []
    t0 = time.time()
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        ctx = br.new_context(
            viewport=VIEWPORT,
            record_video_dir=str(OUT),
            record_video_size=VIEWPORT,
        )
        ctx.add_init_script(_CURTAIN_INIT)
        pg = ctx.new_page()
        # Recording starts here, so this is frame zero. Everything until
        # the curtain lifts is boot, and gets cut in the post-pass.
        t_page = time.monotonic()
        lead = 0.0
        errors: List[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))

        f = Film(pg, plan)
        try:
            pg.goto(f"{base}/?session={sid}&player=p1", wait_until="networkidle")
            pg.wait_for_selector(READY[name], state="visible", timeout=25000)
            pg.wait_for_timeout(1200)
            f.kit()
            pg.evaluate("() => window.__film.put(640, 720)")
            lead = time.monotonic() - t_page
            f.raise_curtain()
            fn(f, base, sid)
        except Exception as exc:  # noqa: BLE001 — report, don't kill the batch
            fails.append(f"{name} raised {type(exc).__name__}: {exc}")
        fails.extend(f.fails)
        if errors:
            fails.append(f"page errors: {errors[:3]}")

        raw = pg.video.path()
        ctx.close()  # the video is only finalised on context close
        br.close()

    secs = time.time() - t0
    final = OUT / f"{name}.webm"
    src = pathlib.Path(raw)
    if src.exists():
        if final.exists():
            final.unlink()
        if keep_raw:
            final.write_bytes(src.read_bytes())
        else:
            src.rename(final)
        note = _post(final, lead, trim)
        kb = final.stat().st_size / 1024
        print(f"  {name:24s} {secs:5.1f}s  {kb:6.0f} KB  {final.name}{note}")
    else:
        fails.append(f"playwright reported a video at {raw} and it is not there")

    for msg in fails:
        print(f"  FAIL [{name}] {msg}")
    return (not fails), name


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8022")
    ap.add_argument("--only", action="append", default=None,
                    help="shoot just this film (repeatable)")
    ap.add_argument("--seed", type=int, default=20260828)
    ap.add_argument("--keep-raw", action="store_true")
    ap.add_argument("--no-trim", action="store_true",
                    help="skip the ffmpeg boot-trim / re-encode pass")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    if args.list:
        for n in FILMS:
            print(n)
        return 0

    base = args.base.rstrip("/")
    names = args.only or list(FILMS)
    unknown = [n for n in names if n not in FILMS]
    if unknown:
        print(f"unknown film(s): {unknown}. --list to see them all.")
        return 2

    print(f"shooting {len(names)} film(s) into {OUT}")
    bad: List[str] = []
    for i, n in enumerate(names):
        ok, _ = shoot(base, n, args.seed + i, args.keep_raw,
                      trim=not args.no_trim)
        if not ok:
            bad.append(n)

    print()
    if bad:
        print(f"FAIL — {len(bad)} film(s) with problems: {', '.join(bad)}")
        return 1
    print(f"PASS — {len(names)} film(s). Now WATCH them; no check here can "
          f"tell you a film teaches the right thing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
