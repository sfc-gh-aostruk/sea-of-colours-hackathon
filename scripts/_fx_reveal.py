#!/usr/bin/env python3
"""Time the probe vision reveal, ring by ring.

The disc used to lift in a single frame. It now lifts as a wavefront out
from the landing square, so the thing worth measuring is no longer "did it
lift" but "did it lift in distance order" — centre, then the four
orthogonals, then the diagonals, then outward.

Samples which cells still carry `.cell--probe-pending` and reports, per
Euclidean distance band from the origin, the moment that band cleared.

Usage: python scripts/_fx_reveal.py <tick> <ox> <oy> [base] [slug]
"""
from __future__ import annotations

import math
import sys

from playwright.sync_api import sync_playwright

TICK = int(sys.argv[1]) if len(sys.argv) > 1 else 0
OX = int(sys.argv[2]) if len(sys.argv) > 2 else 10
OY = int(sys.argv[3]) if len(sys.argv) > 3 else 10
BASE = sys.argv[4] if len(sys.argv) > 4 else "http://127.0.0.1:8013"
SLUG = sys.argv[5] if len(sys.argv) > 5 else "probe-fx-reel"
SEAT = sys.argv[6] if len(sys.argv) > 6 else "p1"

SAMPLE_JS = """() => {
  const out = [];
  for (const c of document.querySelectorAll('#map-player .cell--probe-pending')) {
    out.push([Number(c.dataset.x), Number(c.dataset.y)]);
  }
  return {t: performance.now(), pending: out};
}"""


def main() -> int:
    with sync_playwright() as p:
        br = p.chromium.launch(channel="chrome")
        pg = br.new_page(viewport={"width": 1600, "height": 1000})
        pg.goto(f"{BASE}/watch.html?season={SLUG}",
                wait_until="networkidle", timeout=60_000)
        pg.wait_for_timeout(2500)
        pg.evaluate("""() => {
          for (const id of ['cc-victor', 'cc-endgame', 'cc-report',
                            'cc-resolving-overlay']) {
            const el = document.getElementById(id);
            if (el) { el.style.display = 'none'; el.hidden = true; }
          }
        }""")
        # The watcher opens on OBS, which sees the whole board — so no cell
        # is ever fogged and nothing is ever masked. Take a seat's own
        # fog-of-war view or there is no reveal to measure.
        seat_btn = pg.query_selector(
            f'.cc-replay-view-btn--seat[data-seat="{SEAT}"]'
        )
        if seat_btn is None:
            print(f"! no seat button for {SEAT} — is this a replay?")
            br.close()
            return 1
        seat_btn.click()
        pg.wait_for_timeout(600)

        pg.evaluate(
            "() => { const s = document.getElementById('replay-scrub');"
            " if (s) { s.value = '0';"
            " s.dispatchEvent(new Event('input', {bubbles: true})); } }"
        )
        pg.wait_for_timeout(1200)

        nxt = pg.query_selector("#replay-next")
        for _ in range(TICK):
            nxt.click()
            pg.wait_for_timeout(1500)
        pg.wait_for_timeout(2000)

        nxt.click()
        t0 = None
        # cell -> first sample time at which it was no longer pending
        cleared: dict[tuple[int, int], float] = {}
        seen: set[tuple[int, int]] = set()
        prev: set[tuple[int, int]] = set()
        shape: list[tuple[float, set[tuple[int, int]]]] = []
        for _ in range(90):
            s = pg.evaluate(SAMPLE_JS)
            if t0 is None:
                t0 = s["t"]
            now = s["t"] - t0
            cur = {(int(x), int(y)) for x, y in s["pending"]}
            seen |= cur
            shape.append((now, cur))
            for cell in prev - cur:
                cleared.setdefault(cell, now)
            prev = cur
            pg.wait_for_timeout(40)

        if not seen:
            print("! no masked cells seen — wrong tick, or nothing revealed")
            br.close()
            return 1

        bands: dict[float, list[float]] = {}
        never = 0
        for cell in seen:
            d = round(math.hypot(cell[0] - OX, cell[1] - OY) * 2) / 2
            if cell in cleared:
                bands.setdefault(d, []).append(cleared[cell])
            else:
                never += 1

        print(f"origin ({OX},{OY}) · {len(seen)} masked cells")
        print(f"{'dist':>5}  {'cells':>5}  {'cleared at':>11}")
        base = None
        for d in sorted(bands):
            ts = bands[d]
            at = sum(ts) / len(ts)
            if base is None:
                base = at
            print(f"{d:>5}  {len(ts):>5}  {at:>8.0f}ms  (+{at - base:.0f}ms)")
        if never:
            print(f"! {never} cell(s) never cleared")

        # The numbers say the rings lift in order. This says what shape the
        # front actually is: `#` still fogged, `.` lifted.
        first = min(bands[min(bands)])
        lo_x = min(c[0] for c in seen)
        hi_x = max(c[0] for c in seen)
        lo_y = min(c[1] for c in seen)
        hi_y = max(c[1] for c in seen)
        for want in (first - 40, first + 60, first + 140, first + 220):
            t, cur = min(shape, key=lambda s: abs(s[0] - want))
            print(f"\n  t{t - first:+.0f}ms  ({len(cur)} still fogged)")
            for y in range(lo_y, hi_y + 1):
                row = "".join(
                    "#" if (x, y) in cur else "."
                    for x in range(lo_x, hi_x + 1)
                )
                print(f"    {row}")

        # Numbers say the rings lift in order; they don't say the front
        # reads as round. Replay the same tick and contact-sheet the disc
        # across the sweep.
        first = min(bands[min(bands)])
        pg.evaluate(
            "() => { const s = document.getElementById('replay-scrub');"
            " if (s) { s.value = '0';"
            " s.dispatchEvent(new Event('input', {bubbles: true})); } }"
        )
        pg.wait_for_timeout(1200)
        for _ in range(TICK):
            nxt.click()
            pg.wait_for_timeout(1500)
        pg.wait_for_timeout(2000)
        box = pg.evaluate(
            """([ox, oy]) => {
                 const e = document.querySelector(
                   `#map-player [data-x="${ox}"][data-y="${oy}"]`);
                 if (!e) return null;
                 const r = e.getBoundingClientRect();
                 return {x: r.left - r.width * 4, y: r.top - r.height * 4,
                         width: r.width * 9, height: r.height * 9};
               }""",
            [OX, OY],
        )
        if box:
            nxt.click()
            t_click = pg.evaluate("() => performance.now()")
            shots = []
            for i in range(8):
                target = first - 60 + i * 55
                while pg.evaluate("() => performance.now()") - t_click < target:
                    pg.wait_for_timeout(8)
                path = f"/tmp/reveal_{i:02d}.png"
                pg.screenshot(path=path, clip=box)
                shots.append((round(target - first), path))
            print("frames: " + ", ".join(f"{d:+}ms {p}" for d, p in shots))
        br.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
