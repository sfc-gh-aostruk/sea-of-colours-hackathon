# Multiplayer & mobile — current method

This is the canonical "how we run a shared game right now" runbook (laptop +
phone, or friends across the internet). For the architecture/backend details
see the [README](../README.md) and [RULEBOOK.md](../RULEBOOK.md).

## TL;DR

1. Start the server (single worker, Snowflake backend):
   ```bash
   PYTHONPATH=. SOC_BACKEND=snowflake uvicorn server.app:app --host 0.0.0.0 --port 8000
   ```
2. Start a tunnel and copy the public URL it prints:
   ```bash
   cloudflared tunnel --url http://localhost:8000
   # -> https://<random-words>.trycloudflare.com
   ```
3. **Open the laptop on the tunnel URL** (not `localhost`). Play as `p1`.
4. Hit **NEW GAME** with 2+ seats set to **HUMAN**. The **INVITE PLAYERS**
   modal pops up with a **scannable QR + link per seat**.
5. Scan `p2`'s QR on the phone (works on cellular or any network). Both clients
   land in the same game and sync every 2.5s.

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

1. Find the laptop IP: macOS **System Settings → Wi-Fi → Details → IP address**,
   or `ipconfig getifaddr en0`. The server also reports it at `/api/meta/lan`.
2. On the laptop, browse `http://<LAN-IP>:8000/` and start the game; or open
   `localhost` and let the invite modal rewrite to the LAN IP automatically.
3. The phone must be on the **same Wi-Fi**, and the macOS firewall must allow
   incoming connections to Python (see troubleshooting).

## Mobile interface notes

- The phone client is the same SPA; a `?player=pN` link boots it into a
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

- **`SOC_BACKEND=snowflake`** (the default) so every browser shares one
  persisted session. `memory` is per-process and won't survive a restart or
  share across machines. A server restart is safe with Snowflake — sessions
  persist (Snowflake creds load from `SF_CONFIG_FILE` / `~/.ssh/sf_config`).
- **One uvicorn worker, no `--reload`.** The cross-player submit lock is a
  per-process `threading.Lock`.

## Troubleshooting

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
