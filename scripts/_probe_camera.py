"""Scratch: what do the overlays actually do when the camera moves?

The film harness scales `.cc-map-viewport`. Four overlays are positioned
in absolute pixels snapshotted from cell rects, so they have to be
re-anchored afterwards or they draw the previous board's geometry over
the new one. This dumps every rect involved, before and after, and
screenshots both — reading it off a film frame is guesswork.

It settled issue 29 in one run: a 433px-wide vision border sitting on a
1299px board, both 1299px after `_osReanchorOverlays`. Keep it for the
next time an overlay and the terrain disagree, and note the setup trap
below — the border only exists on a PLANNING board with live ground
under it, so a probe that never launched measures nothing and looks
exactly like the bug.

    python scripts/_probe_camera.py --port 8022
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request

DUMP = """
() => {
  const q = (s) => document.querySelector(s);
  const r = (e) => {
    if (!e) return null;
    const b = e.getBoundingClientRect();
    return [Math.round(b.left), Math.round(b.top),
            Math.round(b.width), Math.round(b.height)];
  };
  const cell = q('#map-player [data-x="9"][data-y="7"]');
  return {
    viewport: r(q('.cc-map-viewport')),
    frame: r(q('.cc-map-frame')),
    grid: r(q('#map-player .map-grid')),
    fxLayer: r(q('#collision-fx-layer')),
    fxParent: (q('#collision-fx-layer') || {}).parentElement
      ? q('#collision-fx-layer').parentElement.className : null,
    visionSvg: r(q('.vision-border-layer')),
    plannedSvg: r(q('.cc-planned-layer')) || r(q('.planned-orders-layer')),
    cell97: r(cell),
    hasHook: typeof window._osReanchorOverlays === 'function',
  };
}
"""


def api(base, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        base + path, data=data,
        headers={"Content-Type": "application/json"} if data else {})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def show(tag, d):
    print(f"\n== {tag}")
    for k in ("viewport", "frame", "grid", "fxLayer", "visionSvg",
              "plannedSvg", "cell97"):
        print(f"   {k:11s} {d.get(k)}")
    print(f"   fxParent    {d.get('fxParent')}")
    print(f"   hasHook     {d.get('hasHook')}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8022)
    args = ap.parse_args()
    base = f"http://127.0.0.1:{args.port}"

    from playwright.sync_api import sync_playwright

    sid = api(base, "/api/game/new",
              {"tutorial": "basic", "seed": 4242})["session_id"]
    # Two probes so there is a lit region with a border to look at, then
    # through the orbit phase: the border only draws on the PLANNING
    # board, so stopping at day 2 orbit measures nothing.
    api(base, f"/api/game/{sid}/policy",
        {"player": "p1", "moves": [{"a": "probe", "at": [9, 7]},
                                   {"a": "probe", "at": [14, 10]}]})
    api(base, f"/api/game/{sid}/orbit", {"player": "p1", "actions": []})
    st = api(base, f"/api/game/{sid}/status")
    print(f"staged: phase {st.get('phase')!r} day {st.get('day')}")

    with sync_playwright() as pw:
        br = pw.chromium.launch()
        pg = br.new_page(viewport={"width": 1024, "height": 640})
        pg.goto(f"{base}/play?session={sid}&player=p1", wait_until="networkidle")
        pg.wait_for_timeout(4000)
        pg.evaluate("() => { const m = document.querySelector('.soc-tut');"
                    " if (m) m.hidden = true; }")
        # No border until a probe has actually resolved and lit ground.
        try:
            pg.wait_for_selector(".vision-border-layer", timeout=90000)
        except Exception:
            st = api(base, f"/api/game/{sid}/status")
            print(f"!! no vision border at all (phase {st.get('phase')!r}, "
                  f"day {st.get('day')}) — nothing to measure")
            br.close()
            return 1
        pg.wait_for_timeout(800)

        show("BEFORE", pg.evaluate(DUMP))
        pg.screenshot(path="/tmp/cam_before.png")

        pg.evaluate("""() => {
          const vp = document.querySelector('.cc-map-viewport');
          const frame = vp.closest('.cc-map-frame');
          frame.style.overflow = 'hidden';
          frame.style.position = 'relative';
          const fx = document.getElementById('collision-fx-layer');
          if (fx && fx.parentElement !== frame) frame.appendChild(fx);
          vp.style.transition = 'none';
          vp.style.transformOrigin = '0 0';
          const vb = vp.getBoundingClientRect();
          const c = document.querySelector('#map-player [data-x="9"][data-y="7"]');
          const cb = c.getBoundingClientRect();
          const k = 3;
          const sx = cb.left + cb.width / 2 - vb.left;
          const sy = cb.top + cb.height / 2 - vb.top;
          vp.style.transform =
            `translate(${vb.width / 2 - sx * k}px, ${vb.height / 2 - sy * k}px)`
            + ` scale(${k})`;
        }""")
        pg.wait_for_timeout(400)
        show("AFTER TRANSFORM (no re-anchor)", pg.evaluate(DUMP))
        pg.screenshot(path="/tmp/cam_zoom_raw.png")

        pg.evaluate("() => window._osReanchorOverlays "
                    "&& window._osReanchorOverlays()")
        pg.wait_for_timeout(700)
        show("AFTER RE-ANCHOR", pg.evaluate(DUMP))
        pg.screenshot(path="/tmp/cam_zoom_fixed.png")

        br.close()
    print("\nshots: /tmp/cam_before.png /tmp/cam_zoom_raw.png "
          "/tmp/cam_zoom_fixed.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
