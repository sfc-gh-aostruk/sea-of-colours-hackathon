# Sea of Colours

A turn-based, fog-of-war strategy game. You run a mining house: harvest
colour from a hidden map at night, spend the proceeds in orbit each
morning, and out-think the other houses. It ships with bot opponents
and an LLM agent, and the hackathon exercise is to build a better agent
than the one in the box.

## Quickstart — play a game in two minutes

**New here? Open [`guide/index.html`](guide/index.html) in a browser** —
an illustrated walkthrough from downloading this repo to finishing your
first season, including the Snowflake setup for the LLM agent. The rest
of this file is the reference version of the same ground.

Needs Python 3.10+. No Snowflake account, no config, no build step.

```bash
pip install -r requirements.txt
SOC_BACKEND=memory python run_web.py
```

Open <http://127.0.0.1:8000>, hit **NEW GAME**, leave your seat as
**HUMAN** and set a rival to **RED_HARVEST_LITE**, and play.

> `SOC_BACKEND=memory` keeps the whole game in the server process — no
> external services. It is required for now: the backend defaults to
> `snowflake` and will fail on your first move without a deployed
> schema. See [`docs/SNOWFLAKE_SETUP.md`](docs/SNOWFLAKE_SETUP.md) if
> you want persistence or the LLM agent.

### Where to go next

| I want to… | Go to |
| --- | --- |
| Be walked through the whole thing | [`guide/index.html`](guide/index.html) — install → first game → first agent change |
| Learn the rules interactively | `manual/index.html` — open it in a browser |
| Read the canonical rules | [RULEBOOK.md](RULEBOOK.md) |
| Win a harder game | Set the rival to `RED_HARVEST` (weapons on) |
| Play a friend | [`docs/MULTIPLAYER.md`](docs/MULTIPLAYER.md) — one-click tunnel + QR invite |
| Face or fork the LLM agent | [`docs/SNOWFLAKE_SETUP.md`](docs/SNOWFLAKE_SETUP.md) — a PAT is all you need |

### The opponents

- **`RED_HARVEST_LITE`** — the deterministic heuristic with weapons
  switched off. Start here; it won't mine or EMP you while you're still
  learning what a parcel is.
- **`RED_HARVEST`** — the same playbook with the full weapons economy.
  The real baseline.
- **`V12`** (`tabula_v12`) — the LLM agent, thinking via Snowflake
  Cortex. Needs a PAT. It's strong, and it has one deliberate blind
  spot for you to exploit or fix.

---

## The map generator CLI

The game's terrain comes from a standalone generator you can also run on
its own — a dependency-free Python CLI that generates topographical
colour grids and prints them as ANSI squares in your terminal.

Each tile is one of four states:

- empty (dark gray)
- green &mdash; 1&ndash;3 same-orientation diagonal bands stretching across the map (v0.8.0; previously polar)
- red &mdash; vast mountain ranges that sweep through the middle latitudes
- blue &mdash; dotted concentrations scattered across the map (lakes, oases)

Tiles are placed by layered value-noise + fractal Brownian motion so the
output reads as terrain rather than independent random scatter.

### Red concentration tiers

Every cell carries a `purity` value in `[0, 255]`. For **red** and **blue**
the same four **numeric** bands apply; only the rendering palette differs.
Unicode Block Elements — **homogeneous** pairs per band (`░░`, `▒▒`, `▓▓`) plus solid fills:

| Level | Name  | Purity    | Red pattern | Approx. fill (PNG dither) |
| --- | --- | --- | --- | --- |
| 1   | trace | 0–50      | `░░` | sparse |
| 2   | vein  | 51–150    | `▒▒` | mid |
| 3   | mass  | 151–254   | `▓▓` | heavy |
| 4   | pure  | **255 only** | solid red | 100% |

A power curve on ``t`` (plus a linear ``t`` mix via `--red-ridge-linear`,
default `0.28`) shapes ridge brightness; **thickness** is Manhattan distance to
the seam edge (`--red-depth-ref` default `3`). That spreads values into **vein**
and **mass** more than a pure ``t**gamma`` curve; thin traces stay light, thick
cores still climb toward **pure** when deep enough.

### Blue depth tiers

**Blue is a pocket**, not a seam: a Chebyshev distance transform finds the
center of each blob; purity falls off from that peak. The same four bands
as red:

| Level | Name     | Purity    | Blue pattern |
| --- | --- | --- | --- |
| 1   | shallow  | 0–50      | `░░` |
| 2   | mid      | 51–150    | `▒▒` |
| 3   | sink     | 151–254   | `▓▓` |
| 4   | deep     | **255 only** | solid blue |

The pocket **peak** reaches purity `255` (`deep`). `--blue-gamma` (default
`1.0`) controls the falloff toward the pocket edge: `>1` grows the outer
bands; `<1` keeps more cells near the peak.

The PNG renderer mirrors both red and blue tiers using **Bayer-dithered
pixel fills** at the matching densities so a tile in the PNG visually
matches the loading-bar style block character in the terminal.

Green currently defaults to full purity and will get its own tier rules
later.

## Requirements

- Python 3.10 or newer
- A terminal that supports ANSI background colors (24-bit preferred; 256-color
  fallback available via `--no-truecolor`)
- No third-party packages for the CLI / library / PNG / tensor paths.
  The optional Web UI uses [FastAPI](https://fastapi.tiangolo.com/) +
  [Uvicorn](https://www.uvicorn.org/) — see [Web UI](#web-ui).

## Usage

From the project root:

```bash
python main.py
```

That prints an 80x50 map with default settings. Pass `--help` to see every
flag. Use `--print-legend` to print a color key and the seed underneath the
grid.

### Reproducible maps

```bash
python main.py --seed 42 --print-legend
```

### Bigger map with thicker green bands

```bash
python main.py --width 120 --height 70 --green-band-half-width 2.5
```

### Heavier mountain coverage with blobby (non-ridged) mountains

```bash
python main.py --red-coverage 0.45 --no-ridges
```

### Dense lake clusters instead of single-pixel dots

```bash
python main.py --blue-density 0.10 --smooth-blue 1
```

### Older terminal (no true-color support)

```bash
python main.py --no-truecolor
```

### Save a PNG (also prints to terminal)

```bash
python main.py --seed 42 --png maps/map.png --pixel-size 16
```

### Only save a PNG, no terminal output

```bash
python main.py --seed 42 --png maps/map.png --no-print
```

### Save the grid as a tensor

```bash
python main.py --seed 42 --save-data maps/map.npy           # NumPy .npy, semantic view
python main.py --seed 42 --save-data maps/map.npy --data-view rgb
python main.py --seed 42 --save-data maps/map.bin           # stdlib-only .bin (no numpy needed)
```

Two views are available via `--data-view`:

- `semantic` *(default)* — `(H, W, 2)` `uint8`, two channels per cell:
  `[tile_id, purity]` where `tile_id` is `0=empty, 1=green, 2=red, 3=blue`.
  This is the game state, losslessly round-trippable.
- `rgb` — `(H, W, 3)` `uint8`. Red cells encode `(purity, 0, 0)` and blue
  cells encode `(0, 0, purity)`, so each substance's purity is directly
  readable from its channel; empty and green use the renderer's palette.

The output format follows the file extension: `.npy` writes a standard
NumPy file (requires NumPy installed); anything else writes a small
stdlib-only `.bin` container readable via `sea_of_colours.data.load_bin`.

## Web UI

The FastAPI SPA reuses `cell_visual` for every painted tile so palettes stay
coupled to the CLI renderer.

The page is split into **`GAME`** vs **`GRAPHICS`** shell tabs. The **Game**
tab runs the two-seat prototype orchestrator: **`[ > NEW GAME ]`** calls
`POST /api/game/new`, then each column issues JSON night policies through
`POST /api/game/{id}/policy`; the server never sends the unseen map to player
views (fog + stale memory only). Visible terrain cells include **`occupants`**
mouseover labels (friendly names for every stacked entity); **probe footage**
tiles that no longer overlap your harvester LOS show as faint **probe echo**
(opacity) with the last camera snapshot taken before dawn. **Vision is a
Euclidean disk**, not a square: at the canonical radius 4 a probe sees every
cell within travel-distance 4 (`dx²+dy²≤16`, ~49 cells), so the limit of a House's view reads as a
true circle (see RULEBOOK §3.11). **Harvesters see only the square they
stand on** (`HARVESTER_LOS_RADIUS = 0` — the disk degenerates to its
centre cell). As a harvester walks during the night, the per-step
intel pulse records every visited tile into the player's echo memory,
producing a trail of **historical-vision** cells along the path —
including any RED harvests that happened underfoot — that survives the
harvester's return to orbit. Wider scouting is still the probe's job
(probes sweep a ~49-cell disk — Euclidean radius 4 — every night and
persist across dawn until they expire after their lifetime).
Harvesters also leave **permanent shading trails** in the underlying
data model (visit counts per tile); those trails are universal and
respect fog-of-war on the per-player view (RULEBOOK §3.12). A fixed
**green ▒▒** still marks every tile where RED became GREEN once a probe
later illuminates it (see RULEBOOK §3.12). A harvester always
harvests the square it lands on (drop or step). Every grid cell carries a
deterministic 16-char `blake2b` hash assigned at generation; the hash travels
with each banked parcel and is rendered in the dedicated **VAULT** drawer as
the House's record of purchase. Policies may carry **up to 100 queue items**
and the orchestrator **skips invalid ones** (out-of-bounds, harvester
already orbital, etc.) without burning a slot — the next item in the queue
runs instead. Each skipped item is surfaced as a **yellow error line** next
to the attempted action in the LOG drawer, so a House can see exactly which
entries fell off. The **Graphics** tab opens a fullscreen
**drawer overlay** with grid-line + **CRT** knobs and the **observer** map
that shows the authoritative grid (see [RULEBOOK.md](RULEBOOK.md) §3.11 / §3.12).
Stateless map paint for debugging remains at `GET /api/generate`. From the repo
root, `python run_web.py` fixes `PYTHONPATH` so imports work without an editable
install; alternatively set `PYTHONPATH=.` when running Uvicorn by hand.

```bash
pip install -r requirements.txt
pytest   # optional orchestrator smoke checks
python run_web.py
# …or: PYTHONPATH=. uvicorn server.app:app --reload
# then open http://127.0.0.1:8000
```

### Play with friends (shareable multiplayer link)

Solo play is unchanged: open `http://127.0.0.1:8000`, hit **NEW GAME**, set
the rival seats to **RED_HARVEST** bots, and play in one browser. The local
seat is always `p1` when no `?player=` is in the URL.

To play a friend across the internet, give 2+ seats the **HUMAN** agent in the
NEW GAME modal. On spawn you get an **INVITE PLAYERS** panel with one link per
human seat:

```
http://<host>/?session=<session_id>&player=p2
```

Send each friend their seat link. The link opens a **playable, fog-of-war**
surface bound to that seat (not the read-only watcher) — they pick orders and
TRANSMIT just like the host. A standing 2.5s poll keeps every browser in sync
and a **waiting-for: …** strip shows who still owes a move; the night/orbit
resolves once every human seat has locked. A link with no `?player=` (or an
invalid one) shows a seat picker of the open human seats.

Hosting notes for a shared game:

- **Use the persistent backend.** Run with `SOC_BACKEND=snowflake` (the
  default) so all browsers read/write the same session. `SOC_BACKEND=memory`
  is per-process and won't survive a reload or share across machines.
- **Run a single worker, no `--reload`.** The cross-player submit lock is a
  per-process `threading.Lock`, so keep one `uvicorn` worker:
  `PYTHONPATH=. uvicorn server.app:app --host 0.0.0.0 --port 8000`.
- **Expose it with a tunnel.** e.g. `cloudflared tunnel --url http://localhost:8000`
  (or `ngrok http 8000`), then share the tunnel origin in place of
  `http://<host>` above.

```bash
# Terminal 1 — single-worker server, reachable on the LAN
PYTHONPATH=. uvicorn server.app:app --host 0.0.0.0 --port 8000

# Terminal 2 — public URL to send friends
cloudflared tunnel --url http://localhost:8000
```

> **Current method (laptop + phone, QR invites, mobile UI):** see
> [docs/MULTIPLAYER.md](docs/MULTIPLAYER.md). Key rule — **open the laptop on the
> tunnel URL (not `localhost`)** so every new game's invite QR is phone-reachable.

CRT cosmetics (global shell filter, scanlines, vignette, glitch, fake pointer)
still respect `localStorage` and **`prefers-reduced-motion: reduce`**.
Canonical fictional rules + changelog live in [RULEBOOK.md](RULEBOOK.md);
the web loop is illustrative until aligned with §4 mechanics.

### Snowflake architecture (v0.4)

The game state and logic now live in Snowflake. The FastAPI server is a
thin proxy that calls into the
[`sea_of_colours.snowpark.engine`](sea_of_colours/snowpark/engine.py)
module; the same module backs the Snowpark Python stored procedures
declared in [`snowflake/soc_procedures.sql`](snowflake/soc_procedures.sql).
See [RULEBOOK.md §5](RULEBOOK.md#5-snowflake-architecture-v04) for the
full table layout, view list, and procedure surface.

**New to this repo / setting up your own Snowflake account?** See
[`docs/SNOWFLAKE_SETUP.md`](docs/SNOWFLAKE_SETUP.md) for the from-scratch
BYO-trial-account walkthrough (getting a PAT for the V12 agent, and
optionally deploying the schema for persistent sessions). You don't
need any Snowflake account at all to play against `RED_HARVEST` /
`RED_HARVEST_LITE` — `SOC_BACKEND=memory` covers that fully offline.

Backend toggle (default `snowflake` — set `SOC_BACKEND=memory` for the
fully offline, pure-Python in-process store used by tests and the
zero-setup hackathon path):

```bash
python run_web.py                         # default: persists to Snowflake
SOC_BACKEND=memory   python run_web.py    # fully offline, in-process only
SOC_BACKEND=snowflake python run_web.py   # explicit Snowflake (same as default)
```

#### Season lifecycle: one season at a time, overwritten on NEW GAME

Every click of **NEW GAME** (and every direct call to `SOC_INIT_SESSION`
/ `soc_engine.init_session`) first wipes every row from every SOC_*
table — *including* the previous season's replay frames, agent
invocations, log lines, and policy queue — and then writes the freshly
generated session as the only row. This applies whether you're playing
through `RED_HARVEST`, a Cortex AI agent, or a human seat: nothing in
the Snowflake schema accumulates across seasons.

The "save / restore previous seasons" feature is intentionally
deferred — it will hook in by snapshotting SOC_* into per-season
archive tables *before* the wipe runs.

Deploying the Snowflake schema + procedures + Cortex agent (one shot):

```bash
python scripts/deploy_soc_schema.py
```

Flags:

| Flag | Effect |
| ---- | ------ |
| `--schema-only` | Stop after `soc_schema.sql` + `soc_views.sql`. |
| `--no-procs`    | Skip `soc_procedures.sql` (procedures will be missing). |
| `--config FILE` | Use a different Snowflake config (default: `~/.ssh/sf_config`). |
| `--dry-run`     | Print the resolved target database / schema / warehouse and exit without connecting. |

The deploy script also builds + uploads the engine package zip
(`build/sea_of_colours.zip`) to `@SOC_PY_STAGE` so every stored
procedure's `IMPORTS =` clause resolves to live code.

#### Snowflake cost notes

- Every executed move emits one row in `SOC_REPLAY_FRAME` (one per
  player action plus the per-night `[opening]` and `[dawn]` rows). A
  full 25-move night caps at ~27 rows; a 30-night season ≈ 750
  VARIANT rows per session — comfortably under any per-table limit.
- All stored procedures run on the warehouse resolved by
  [`sea_of_colours/snowpark/naming.py`](sea_of_colours/snowpark/naming.py)
  (default: `SOC_HACKATHON_WH` — a dedicated XSMALL warehouse the deploy
  script creates on first run with `AUTO_SUSPEND = 60` seconds).
  Override via `SOC_WAREHOUSE` or `warehouse=<name>` in `sf_config` if
  you'd rather reuse an existing warehouse.
- The **V12** LLM agent bills Cortex inference tokens per turn and does
  not use a warehouse at all — it calls the chat-completions endpoint
  directly with a PAT. See
  [`docs/SNOWFLAKE_SETUP.md`](docs/SNOWFLAKE_SETUP.md).

### Agents — the bots + V12

Sea of Colours ships three agents. They share the same view +
move-queue contract, so any of them can take any seat.

* **RED_HARVEST_LITE** — the deterministic heuristic with weapons
  disabled. The recommended first opponent, and the default rival in
  the NEW GAME menu.
* **RED_HARVEST** — the same pure-Python heuristic with chaff and EMP
  switched on
  ([`sea_of_colours/agent/heuristic_agent.py`](sea_of_colours/agent/heuristic_agent.py)).
  No Snowflake required, deterministic, fully tested. This is what the
  ORDERS panel's `[ >> LET THE AGENT PLAY ]` button runs.
* **V12** — the LLM agent
  ([`sea_of_colours/orchestrator_2/harnesses/tabula_v12/`](sea_of_colours/orchestrator_2/harnesses/tabula_v12/)),
  and the one you're here to beat. Runs in-process and calls Cortex
  *inference* over REST, so it needs a `SNOWFLAKE_PAT` but **no**
  deployed Snowflake agent object and no particular storage backend.

The two heuristics are driven by the think route:

```text
POST /api/game/{id}/agent/think?player=p1[&runtime=heuristic|red_harvest_lite]
  → reads the player view
  → runs the heuristic
  → submits the policy
  → writes a row to SOC_AGENT_INVOCATION with rationale + tool calls
  → returns { agent_id, runtime, rationale, night_resolved, ... }
```

V12 does **not** go through that route. Seat a player as `tabula_v12`
when you create the game and the orchestrator dispatches it each night.

> Removed in the hackathon distribution: the old Cortex *Agents-API*
> runtime (`SOC_AGENT_RUNTIME=cortex`, the `soc_create_agent*.sql`
> specs, `SOC_RED_REAPER` and friends). `?runtime=cortex` returns 410.

All three consume the same structured view payload
(`hud`, `grid_ascii`, `red_tiles`, `green_tiles`, `fog_clusters`,
`entities.mine`, `entity_detail`, `recent_log`) and emit the same
wire-format move queue, so RED_HARVEST is a faithful drop-in for V12 —
which is exactly what makes them comparable on a scoreboard.

## Parameter cheatsheet

| Flag | Default | What it does |
| --- | --- | --- |
| `--width` | `80` | Grid width in tiles. |
| `--height` | `50` | Grid height in tiles. |
| `--seed N` | random | Seed for reproducible output. |
| `--green-strength` | `1.0` | Higher = denser green inside the bands. |
| `--green-band-count` | random 1&ndash;3 | Force a specific green band count (0 disables green). |
| `--green-band-half-width` | `1.5` | Half-width of each band in cells (~3 cells thick). |
| `--band-depth` | `0.18` | DEPRECATED (v0.8.0). Polar-band knob; ignored by the new generator. |
| `--red-coverage` | `0.30` | Fraction of the map covered by mountains. |
| `--ridges` / `--no-ridges` | ridges on | Sharper ridge-line mountains vs. round blobs. |
| `--red-gamma` | `5.0` | Curved part ``t**gamma`` in ridge; lower ⇒ brighter mid-seam. |
| `--red-depth-ref` | `3.0` | Depth at which thickness factor saturates (lower ⇒ “fatter” cores sooner). |
| `--red-ridge-linear` | `0.28` | Blend toward linear `t` so maps are less trace-dominated. |
| `--red-pure-min-depth` | `3` | Minimum depth (tiles) before purity may be **255** (`pure`). |
| `--red-core-boost` | `0.35` | Extra ridge headroom in thick knots so **pure** appears without `t === 1`. |
| `--blue-density` | `0.03` | Fraction of the map covered by blue pockets. |
| `--smooth-blue N` | `1` | Cellular-automata passes to coalesce dots into chunkier pockets. |
| `--blue-gamma` | `1.0` | Falloff exponent for blue depth from pocket edge to center. `1.0` = linear; `>1` grows the shallow edge; `<1` keeps pockets mostly deep. |
| `--no-truecolor` | off | Use 256-color ANSI instead of 24-bit. |
| `--print-legend` | off | Print color legend and seed below the map. |
| `--png PATH` | off | Also save the grid as a PNG to `PATH`. |
| `--pixel-size N` | `12` | Pixels per tile in the saved PNG. |
| `--png-grid-lines` | off | Draw thin separator lines between tiles in the PNG. |
| `--no-print` | off | Skip terminal output (handy when only saving a PNG). |
| `--save-data PATH` | off | Also save the grid as a tensor. `.npy` ⇒ NumPy format; anything else ⇒ stdlib `.bin`. |
| `--data-view` | `semantic` | Tensor view: `semantic` `(H,W,2)` of `[tile, purity]`, or `rgb` `(H,W,3)`. |

## Project layout

```
sea_of_colours/
├── main.py                       CLI entrypoint
├── README.md
├── RULEBOOK.md                   Master rulebook + changelog
├── requirements.txt              FastAPI + Pytest
├── pytest.ini
├── tests/                        Orchestrator smoke tests + parity suite
├── scripts/
│   └── deploy_soc_schema.py      Non-destructive Snowflake schema/procs/agent deploy
├── snowflake/
│   ├── soc_schema.sql            SOC_* tables (CREATE TABLE IF NOT EXISTS)
│   ├── soc_views.sql             Leaderboard / day-index / latest-frame views
│   └── soc_procedures.sql        Snowpark Python stored-proc declarations
├── sea_of_colours/
│   ├── __init__.py
│   ├── game/                     Pure-Python engine (session, simulator, ledgers)
│   ├── snowpark/                 Storage-agnostic engine wrappers + Snowpark procs
│   ├── agent/                    RED_HARVEST heuristic + AI agents (Cortex) REST invoker
│   ├── noise.py                  Pure-Python value noise + fBm + ridge transform
│   ├── generator.py              Tile enum + layered biome generation
│   ├── render.py                 ANSI rendering (truecolor + 256-color)
│   ├── png.py                    Pure-Python PNG writer with Bayer-dithered red tiers
│   └── data.py                   Efficient tensor export (semantic + RGB)
└── server/
    ├── app.py                    FastAPI thin proxy: /, /api/generate, /api/game/*
    └── static/                   index.html + styles.css + app.js
```

## How the topography is generated

Three independent noise fields are sampled and then composited in priority
order:

1. **Red mountains** are sampled from a low-frequency fBm field. With ridges
   enabled, the field is passed through `1 - |2n - 1|` so high values form
   connected ridge lines. The top `--red-coverage` fraction becomes RED.
2. **Green diagonal bands** (v0.8.0) combine a band-distance mask (a
   smoothstep falloff over the perpendicular distance to each of 1&ndash;3
   parallel band centers) with a separate noise layer. The mask is 1 at the
   center of each band and 0 outside `green_band_half_width` cells, but the noise gives the
   band a ragged inner border instead of a flat stripe.
3. **Blue pockets** are sampled from a medium-frequency fBm field with a
   high threshold (top `--blue-density` fraction). One pass of cellular-
   automata smoothing coalesces specks into chunkier pockets by default.
   Once the pocket *shapes* are settled, a Chebyshev distance transform
   picks the geometric center of each connected component as the pocket's
   peak, and every other cell's purity is graded by its Chebyshev distance
   *from that one peak* — so each pocket renders as a single bright
   ``deep`` core surrounded by a ``mid`` ring and a ``shallow`` halo.

Each layer is allowed to overwrite the previous one, so green takes priority
over red where the bands meet the mountains, and blue takes priority over
everything for the small dotted features.

## Programmatic use

```python
from sea_of_colours import generate_grid, to_ansi
from sea_of_colours.generator import GenerationParams

grid = generate_grid(GenerationParams(width=100, height=60, seed=7))
print(to_ansi(grid))
```

### Grid as a tensor

`sea_of_colours.data` exposes the same grid as a packed `uint8` buffer. The
underlying storage is a `bytearray` (1 byte per channel per cell, row-major)
so it allocates no per-cell Python objects, and `GridTensor.numpy()` converts
it to a real `ndarray` of shape `(H, W, channels)` via `np.frombuffer` + a
reshape — zero copy if you ask for `copy=False`:

```python
from sea_of_colours import generate_grid, grid_to_rgb, grid_to_semantic
from sea_of_colours.generator import GenerationParams

grid = generate_grid(GenerationParams(width=100, height=60, seed=7))

semantic = grid_to_semantic(grid)        # (60, 100, 2): [tile_id, purity]
rgb      = grid_to_rgb(grid)             # (60, 100, 3): RGB; red cells = (purity, 0, 0)

# Stdlib-only: GridTensor exposes shape, channels, and raw bytes
print(semantic.shape, semantic.channels, len(semantic.data))

# Optional numpy view — true ndarray, ready for ML / image libs
arr = rgb.numpy()                         # writable copy
arr_view = rgb.numpy(copy=False)          # zero-copy, read-only

# Save / load without numpy:
from sea_of_colours import save_bin, load_bin
save_bin("map.bin", semantic)
roundtrip = load_bin("map.bin")           # same shape, dtype, data
```

## What's next

This is the foundation for a larger game; the package exports a `Tile` enum,
a `Grid` (list of lists of `Cell`), and `GridTensor` views so a game loop,
input layer, or alternative renderers (PNG, Pygame, ML pipelines) can be
layered on top without changing the generation code.
