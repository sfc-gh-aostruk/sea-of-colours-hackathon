# Multiplayer & mobile — current method

This is the canonical "how we run a shared game right now" runbook (laptop +
phone, or friends across the internet). For the architecture/backend details
see the [README](../README.md) and [RULEBOOK.md](../RULEBOOK.md).

## TL;DR

There are two ways to let other devices in. Pick by where the players are.

### Everyone on the same Wi-Fi (simplest)

```bash
python run_web.py --lan
# [soc] LAN hosting: other devices join at http://192.168.1.42:8000/
```

`--lan` binds every interface and turns auto-reload off. Then hit
**NEW GAME** with 2+ seats set to **HUMAN**; the **INVITE PLAYERS** modal
gives a scannable QR and link per seat, already addressed to your LAN IP.

> **`python run_web.py` on its own will not work for this.** It binds
> `127.0.0.1`, so other devices can't reach it at all — and until v1.15
> the invite modal still printed a LAN QR, which simply timed out on the
> phone. The modal now checks and tells you.

### Players elsewhere, or a firewall in the way

```bash
python run_web.py                                  # loopback is fine here
cloudflared tunnel --url http://localhost:8000     # -> https://<words>.trycloudflare.com
```

**Open the laptop on the tunnel URL** (not `localhost`), then create the
game. Invite links are built from whatever URL the laptop is browsing, so
this is what makes them work for everyone. The tunnel reaches `localhost`
itself, which is why `--lan` isn't needed on this path.

Both clients sync every 2.5s.

### Storage

The **STORAGE** row in the launcher decides whether the match survives a
restart. Memory is fine for one sitting and needs no setup; Snowflake
keeps the season (schema deploy required — `docs/SNOWFLAKE_SETUP.md` §2).
Since v1.14 that is a per-game choice, so `SOC_BACKEND` no longer needs
pinning before a party.

## Seat links live at `/play`, not `/`

A seat link is `http://<host>/play?session=<id>&player=p2`. The `/play`
matters: `/` is the title screen and has no session-loading code, so a
link pointed there silently opens the title screen instead of the game.
Until v1.12 the LAN invite QR codes did exactly that — `fetchLanOrigin()`
returns a bare origin whose path is `/`, so every QR a phone scanned on
the same Wi-Fi landed on the title screen. Generation now pins `/play`,
and `/` redirects when it sees a `?session=`, so older links still work.

## Why open the laptop on the tunnel URL (the key gotcha)

Invite links and QR codes are built from **whatever URL the laptop is browsing**
(`window.location`). So:

| Laptop is on…            | QR/links point at…        | Phone result                    |
| ------------------------ | ------------------------- | ------------------------------- |
| **tunnel URL**           | the public tunnel URL     | ✅ works anywhere               |
| LAN IP (`192.168.x.x`)   | the LAN IP                | ✅ only on same Wi-Fi + firewall allows |
| `localhost` / `127.0.0.1`| the LAN IP (auto-rewrite) | ❌ unless same Wi-Fi **and** firewall allows incoming |

The invite modal only rewrites links to the LAN IP when you're on
`localhost`/loopback (so a single-machine dev session still produces a
phone-reachable link on the same Wi-Fi). On a tunnel or LAN-IP origin it leaves
the origin as-is. **Bottom line: browse the laptop on the tunnel URL and every
new game's QR just works.**

The tunnel URL is **per-server, not per-game** — it keeps working for every new
game; only the `?session=<id>` part changes (the modal handles that). It only
changes if you restart `cloudflared` (a free quick-tunnel gets a new random
`trycloudflare.com` name each run). For a permanent URL, use a
[named Cloudflare tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/).

## LAN-only alternative (no internet)

For phone-next-to-laptop with no tunnel:

1. Start with `python run_web.py --lan`. It prints the address other
   devices should use, and binds the interfaces they'll arrive on.
2. On the laptop, browse `localhost` as usual and start the game — the
   invite modal rewrites links to the LAN IP for you. (Browsing the LAN
   IP directly works too.)
3. The phone must be on the **same Wi-Fi**, and the macOS firewall must
   allow incoming connections (see troubleshooting). `GET /api/meta/lan`
   reports both facts — whether the server is actually listening on the
   LAN, and whether the firewall is set to block — so check it there
   before debugging the phone.

## Mobile interface notes

> **`/mobile` was retired in v1.13.** It was a 953-line standalone fork,
> frozen since the initial commit while `app.js` moved on, and the main
> SPA had long since grown the better phone UX. `/mobile` now redirects
> to `/play` and the invite modal offers one QR per seat rather than two.

- The phone client is the main SPA; a `?player=pN` link boots it into a
  playable, fog-of-war seat (not the read-only watcher).
- **Map**: one-finger drag pans, two-finger pinch zooms, tap a cell to deploy.
  A tap-vs-drag guard stops a pan/pinch from firing a stray order.
- **Map-first layout**: on a phone the map fills the screen. A fixed bottom
  bar shows **▤ ORDERS · n** and **» TRANSMIT** — that's it when you're just
  looking at the map.
- **Orders sheet**: tapping **ORDERS** slides the panel up as a sheet *over*
  the map (no page scrolling). The tab strip rides on top of the sheet so you
  can switch to VAULT / GRAPHICS / LOG. Tapping the visible map, or ORDERS
  again, dismisses it.
- **Deploy loop**: open ORDERS → tap an asset chip (probe/harvester/EMP/…) →
  the sheet auto-drops so the map is tappable → tap the target cell → reopen
  ORDERS to review the queue → **TRANSMIT** (always one tap in the bottom bar).

## Hosting rules (don't break sync)

- **One uvicorn worker, no `--reload`.** The cross-player submit lock is
  a per-process `threading.Lock`, and a memory-backed season lives in
  that process — so an incidental file save mid-party doesn't just
  hiccup, it resets everyone. `run_web.py --lan` turns reload off for
  you; if you hand-roll a uvicorn command, leave `--reload` out.
- **Choose storage when you create the game**, in the launcher's STORAGE
  row. All browsers hit the same process either way.

## Troubleshooting

- **Start here:** open `http://localhost:8000/api/meta/lan`. It answers
  the two questions that cause almost every LAN failure —
  `lan_reachable` (is this server actually listening where the QR
  points?) and `lan_firewalled` (is macOS set to block incoming?) — and
  `lan_hint` names the fix. The invite modal shows the same thing.
- **Phone opens the QR and nothing happens / it times out:** you almost
  certainly started with plain `python run_web.py`, which is loopback
  only. Restart with `--lan`.
- **`ERR_CONNECTION_RESET` on the phone (LAN):** the macOS firewall is blocking
  incoming connections. Check with
  `/usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate` and
  `--getstealthmode`. "Block all incoming" + stealth mode actively resets
  unsolicited connections. Fix via **System Settings → Network → Firewall**
  (turn off "Block all incoming connections" / stealth, or allow the Python
  binary), or just use a tunnel to bypass it entirely.
- **Phone can't reach the LAN IP but `localhost` works on the laptop:** firewall
  or different Wi-Fi network (guest/VLAN isolation). Use a tunnel.
- **QR points at `192.168.x.x` when you wanted the public URL:** you're browsing
  the laptop on `localhost`. Reopen it on the tunnel URL.
- **Tunnel URL stopped working:** `cloudflared` was stopped/restarted; rerun
  `cloudflared tunnel --url http://localhost:8000` and reshare the new URL (or
  set up a named tunnel for a stable address).
