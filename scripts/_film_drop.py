#!/usr/bin/env python3
"""SPIKE: can a tutorial film be GENERATED rather than hand-recorded?

The tutorial plan (docs/TUTORIAL_PLAN.md §4) wants short silent films of
real turns as the front door, and rests on one bet: that films can be
produced by running a script, so a UI change costs a re-run instead of a
re-shoot. Hand-recorded video of a UI we are actively redesigning is
wrong within a week and then stays wrong forever.

This proves the bet on ONE film — "drop a harvester" — and specifically
proves the three things that are not obvious:

* **A CURSOR EXISTS.** Playwright paints no pointer into its video, so a
  naive recording shows the UI operating itself, which teaches nothing
  about *where to click*. We inject a fake one and glide it.
* **THE PACING IS HUMAN.** Automation clicks faster than anyone can
  follow. Every beat dwells either side of the click.
* **IT IS THE REAL UI.** No mock-up, no storyboard: a real session on
  the memory backend, real selectors, real clicks, real animations. That
  is the whole point — it cannot drift from the product without the
  script noticing.

Scratch harness like the other ``scripts/_fx_*.py`` — not pytest.

Usage::

    python run_web.py --port 8022 --replace &     # a server YOU own
    python scripts/_film_drop.py --base http://127.0.0.1:8022

Point it at an AGENT-RUN server, never the user's. See AGENTS.md.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

OUT = pathlib.Path(__file__).resolve().parents[1] / "reports" / "films"


def _post(base: str, path: str, body: dict) -> dict:
    req = urllib.request.Request(
        base + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


# ── the film kit ────────────────────────────────────────────────────
#
# A cursor and a caption bar, injected into the page. Both are plain DOM
# so the video picks them up for free, and both sit at the top of the
# stacking order so no panel can cover them.
#
# The glide runs in JS on requestAnimationFrame rather than as a Python
# loop of evaluate() calls: 30 round-trips per move is both jerky and
# slow, and the frame timing is what makes the motion read as a hand
# rather than a teleport.
_KIT = """
() => {
  if (document.getElementById('film-cursor')) return;

  const c = document.createElement('div');
  c.id = 'film-cursor';
  c.style.cssText = [
    'position:fixed', 'left:0', 'top:0', 'width:20px', 'height:20px',
    'margin:-10px 0 0 -10px', 'border:2px solid #aaff00',
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
    'padding:10px 22px', 'background:rgba(0,0,0,0.82)',
    'border:1px solid #446600', 'color:#aaff00',
    'font:13px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace',
    'letter-spacing:1.2px', 'text-transform:uppercase',
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
    press() {
      c.style.transform = 'scale(0.6)';
      c.style.background = 'rgba(170,255,0,0.55)';
      return new Promise((res) => setTimeout(() => {
        c.style.transform = 'scale(1)';
        c.style.background = 'rgba(170,255,0,0.18)';
        res();
      }, 150));
    },
  };
}
"""


class Film:
    """A page plus the cursor/caption kit, with human-paced verbs."""

    def __init__(self, pg) -> None:
        self.pg = pg
        self.beats: list[str] = []

    def kit(self) -> None:
        self.pg.evaluate(_KIT)

    def say(self, text: str | None, hold: int = 0) -> None:
        self.pg.evaluate("(t) => window.__film.say(t)", text)
        if hold:
            self.pg.wait_for_timeout(hold)

    def _centre(self, selector: str) -> tuple[float, float]:
        box = self.pg.locator(selector).first.bounding_box()
        if not box:
            raise RuntimeError(f"no box for {selector!r} — is it on screen?")
        return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2

    def glide(self, selector: str, ms: int = 620) -> tuple[float, float]:
        x, y = self._centre(selector)
        self.pg.evaluate(
            "([x, y, ms]) => window.__film.glide(x, y, ms)", [x, y, ms])
        # Move the REAL pointer too, or nothing hovers: the fake cursor is
        # decoration and fires no events. Tooltips and :hover states are
        # half of what these films are showing.
        self.pg.mouse.move(x, y)
        return x, y

    def click(self, selector: str, before: int = 420, after: int = 700,
              ms: int = 620) -> None:
        """Glide, dwell, press, click, dwell. The dwells are the film."""
        self.glide(selector, ms=ms)
        self.pg.wait_for_timeout(before)
        self.pg.evaluate("() => window.__film.press()")
        self.pg.wait_for_timeout(90)
        self.pg.locator(selector).first.click()
        self.pg.wait_for_timeout(after)
        self.beats.append(selector)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8022")
    ap.add_argument("--keep-webm", action="store_true",
                    help="keep the raw playwright filename too")
    args = ap.parse_args()
    base = args.base.rstrip("/")
    OUT.mkdir(parents=True, exist_ok=True)

    # 24x16 — the size docs/TUTORIAL_PLAN.md §3 picks for the Basic
    # tutorial, so the film is shot on the board it teaches.
    game = _post(base, "/api/game/new", {
        "width": 24, "height": 16, "season_day_cap": 3,
        "players": ["p1", "p2"],
        "agents": {"p1": "human", "p2": "red_harvest_lite"},
        "visibility_mode": "hidden",
    })
    sid = game["session_id"]
    print(f"session {sid}")

    fails: list[str] = []
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        ctx = br.new_context(
            viewport={"width": 1280, "height": 800},
            record_video_dir=str(OUT),
            record_video_size={"width": 1280, "height": 800},
        )
        pg = ctx.new_page()
        film = Film(pg)

        pg.goto(f"{base}/?session={sid}&player=p1", wait_until="networkidle")
        pg.wait_for_selector("#orders-asset-roster", timeout=20000)
        pg.wait_for_timeout(900)
        film.kit()
        pg.evaluate("() => window.__film.put(640, 700)")

        t_start = time.time()

        # ── beat 1: what you have ──
        film.say("Your harvester is waiting in orbit", hold=1500)
        film.glide(".cc-fleet-row", ms=700)
        pg.wait_for_timeout(900)

        # ── beat 2: arm the verb ──
        film.say("Click DROP to send it down")
        drop = ".cc-fleet-row .cc-fleet-verb"
        film.click(drop)

        armed = pg.evaluate("""() => {
          const b = document.querySelector('.cc-fleet-verb--armed');
          const el = document.querySelector('.pick-mode-banner');
          const cs = el && getComputedStyle(el);
          return {
            verb: b ? b.textContent.trim() : null,
            banner: !!(cs && cs.display !== 'none' && cs.visibility !== 'hidden'),
          };
        }""")
        print(f"armed           : {armed}")
        if armed["verb"] != "[DROP]":
            fails.append(f"clicking the first verb armed {armed['verb']!r}")
        if not armed["banner"]:
            fails.append("no pick-mode banner after arming DROP")

        # ── beat 3: pick a landing cell ──
        #
        # NOT filtered to unfogged cells. Night one is blind — the whole
        # board is fog until a probe goes up — and the panel is an
        # ANNOTATOR, not a gate (v1.24): clicking fog queues the order and
        # says what is wrong with it. Filtering to "visible" here found
        # nothing to click and stalled the shoot.
        #
        # Centre-most cell by grid coordinate, so the click lands in frame
        # and away from the rail, without hardcoding a coordinate that a
        # board-size change would invalidate.
        target = pg.evaluate("""() => {
          const cells = [...document.querySelectorAll('.cell')];
          if (!cells.length) return null;
          let mx = 0, my = 0;
          for (const c of cells) {
            mx = Math.max(mx, +c.dataset.x);
            my = Math.max(my, +c.dataset.y);
          }
          const cx = Math.round(mx / 2), cy = Math.round(my / 2);
          const best = document.querySelector(
            `.cell[data-x="${cx}"][data-y="${cy}"]`);
          return best
            ? { x: best.dataset.x, y: best.dataset.y, total: cells.length,
                fogged: best.classList.contains('cell--fog') }
            : null;
        }""")
        print(f"landing cell    : {target}")
        if not target:
            fails.append("no unfogged cell to land on — nothing to film")
            ctx.close()
            br.close()
            for f in fails:
                print(f"FAIL: {f}")
            return 1

        film.say("Pick where it lands")
        sel = f'.cell[data-x="{target["x"]}"][data-y="{target["y"]}"]'
        film.click(sel, before=520, after=900, ms=780)

        # The picker is STICKY — a landing chains straight into steps, so
        # the banner is still up and still blinking. Leaving it up would
        # end the film mid-instruction, telling the viewer to keep
        # clicking after the lesson is over.
        pg.keyboard.press("Escape")
        pg.wait_for_timeout(400)

        # ── beat 4: the order is on the books ──
        film.say("The order is queued — TRANSMIT sends the night", hold=600)
        film.glide("#solo-commit-night", ms=700)
        pg.wait_for_timeout(1600)
        film.say(None)
        pg.wait_for_timeout(600)

        secs = time.time() - t_start

        queued = pg.evaluate("""() => {
          const rows = [...document.querySelectorAll('.solo-queue-row')];
          return {
            count: rows.length,
            labels: rows.map((r) => {
              const l = r.querySelector('.solo-queue-label');
              return l ? l.textContent.trim() : null;
            }),
            targets: rows.map((r) => {
              const a = r.querySelector('.solo-queue-at');
              return a ? a.textContent.trim() : null;
            }),
          };
        }""")
        print(f"queue after     : {queued}")
        if queued["count"] < 1:
            fails.append(
                "the film clicked DROP and a cell but queued nothing — the "
                "film would show a turn that does not happen"
            )

        raw = pg.video.path()
        ctx.close()          # video is only finalised on context close
        br.close()

    final = OUT / "drop_a_harvester.webm"
    src = pathlib.Path(raw)
    if src.exists():
        if final.exists():
            final.unlink()
        if args.keep_webm:
            final.write_bytes(src.read_bytes())
        else:
            src.rename(final)
        size_kb = final.stat().st_size / 1024
        print(f"\nfilm            : {final}")
        print(f"length / size   : {secs:.1f}s · {size_kb:.0f} KB")
    else:
        fails.append(f"playwright reported a video at {raw} and it is not there")

    for f in fails:
        print(f"FAIL: {f}")
    print("PASS" if not fails else f"{len(fails)} FAILURE(S)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
