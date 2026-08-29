# Adding (or re-adding) a weapon — the integration map

Written 2026-08-28, during the **retirement of the caltrop MINE**. Mines
were removed to free the third weapon slot for a replacement, so this is
deliberately written as a *forward* guide: everywhere a third weapon has
to plug in, with the mine implementation as the worked example.

If you are adding a new weapon, walk this list top to bottom. If you are
re-adding mines specifically, `git log` the retirement commit and this
file together — the doc says *where*, the diff says *what*.

**Two weapons ship today: EMP and CHAFF.** Anywhere you find a pair, it
used to be a triple.

---

## 0. The shape of a weapon

A weapon in this engine is two separate things, and a new one usually
needs both:

- **An orbit BUY** — `build_<name>`, paid in blue purity + credits,
  producing stock. Resolved by `OrbitResolver`.
- **A night ORDER** — a move tag, spending one stock and one queue slot.
  Dispatched by `NightSimulator`.

EMP and mine had both. Chaff has both but its order takes no target.
A weapon with only one half is possible but has no precedent.

---

## 1. Engine

### `sea_of_colours/game/weapons.py`
The dials. Mine had a block of five constants —
`MINE_COST_BLUE_PURITY`, `MINE_COST_CREDITS`, `MINES_PER_BUY`,
`MINE_BATCH_SHAPE`, `MINE_VISIBILITY` — plus entries in `__all__`.
Costs and shapes live here and **nowhere else**; never copy a literal.

### `sea_of_colours/game/policy.py`
Six separate touch points, easy to half-do:

1. `MoveTag` literal — add the night tag.
2. The move dataclass (e.g. `MineLayMove`) — `at` if it targets a cell.
3. The `Move` union.
4. The move parser branch, including punctuation variants
   (`mine`, `mine_lay`, `mine-lay`).
5. `move_to_wire` — serialise back out.
6. `OrbitTag`, the `Build*Action` dataclass, the `OrbitAction` union, and
   the orbit parser branch with its `count` clamp.

**Retirement pattern (v1.13, reused here).** Do not silently drop a
retired tag. `_RETIRED_ORBIT_TAGS` maps a dead tag to a *reason*, so a
stale client or a stale LLM gets a diagnosis instead of a shrug. The mine
retirement added the night-move mirror, `_RETIRED_MOVE_TAGS`. A new
weapon that later dies should use the same two dicts.

### `sea_of_colours/game/session.py`
The largest surface. Mine touched:

- `weapon_stock` / `weapons_used` default shape and the `__post_init__`
  backfill — these are **hardcoded key triples**, not a loop.
- A persisted state dict (`mines: Dict[...]`) for deployed ordnance, plus
  a non-persisted `pending_mine_events` list drained by the simulator
  into replay frames.
- Visibility: `mine_visible_to`, the witness set topped up by probe intel
  pulses, and per-cell packing into observer/agent views.
- `_apply_build_weapon` (generic, shared) plus a thin
  `apply_build_mine` wrapper.
- The subsystem proper: `_mine_key`, `_mine_cluster_cells`,
  `apply_mine_lay`, `mine_at`, `detonate_mine_at`.
- Step-collision damage in `try_step_unit`.
- EMP cross-kill: `_emp_sweep_destroy` / `neutralized_mines`.
- `to_dict` / `from_dict`.
- Replay: `_weapons_snap_payload`, `replay_push_scene`, and a
  `mines_active` snapshot on **every** frame.
- Activity tallies: `_empty_activity_tally`, `tally_orbital_activity`.

### `sea_of_colours/game/simulator.py`
Import, `_describe_move`, the dispatch branch, and draining
`pending_*_events` into `frame[...]`.

Note `_pre_hour_phase` pre-empts **EMP and chaff only** — mine ran in
normal dispatch. A new weapon must choose which, deliberately.

### `sea_of_colours/game/orbit_resolver.py`
Import the action, add the `apply_build_*` branch.

---

## 2. Persistence

- `to_dict` / `from_dict` in `session.py`. **Both tolerate missing keys**
  (stock defaults `0`, state defaults `{}`), which is why removing a
  weapon does not break old saves.
- `snowflake/soc_schema.sql` — mine had two replay columns, `mine`
  (per-frame events) and `mines_active` (snapshot), plus forward-migration
  `ALTER TABLE`s.
- `sea_of_colours/snowpark/snowpark_store.py` — INSERT/SELECT column
  lists and `PARSE_JSON` in the batch replay read.

**Columns are never dropped.** Archived seasons keep replaying, which is
why the mine retirement left the schema, the store and the FX intact.

---

## 3. Agent-facing view

`sea_of_colours/snowpark/view.py`:

- `weapon_stock_block[<name>]`
- `weapon_prices[<name>]`
- `weapon_specs[<name>]` — including `batch_shape`, which the **UI reads
  to draw the AoE preview**, so it is load-bearing, not documentation.
- `weapon_specs.emp.destroys` — the list of what an EMP kills. Mine was
  in it.

⚠️ **`entities.mine` in this file is NOT the weapon** — it is the seat's
own fleet. See §8.

---

## 4. Agents

- `sea_of_colours/agent/heuristic_agent.py` — never bought or fired
  mines; only EMP and chaff. A new weapon needs explicit support here or
  the heuristic bot will ignore it.
- `orchestrator_2/harnesses/tabula_v12/prompt.py` — the WEAPON GEOMETRY
  block, including the EMP `destroys` prose.
- `_v7/opponent_weapons.py` — the estimator infers rival stock from blue
  spend and activity; mine had `_MINE_BLUE_COST` and `mines_min/max` on
  the estimate dataclass.
- `_v7/orbit_wishlist.py` — what the agent asks to buy.
- `last_night.py` — tag sets and the caption map
  (`"mine_lay": "laid a mine"`).
- `_v7/move_sanitizer.py` — note it did **not** reject `mine_lay`; a
  stale model order passed straight through to engine policy.

---

## 5. UI — the buttons, and every place one hides

This is the part that is easy to leave half-done, so it is enumerated.
All paths relative to `server/static/`.

### `index.html`
- **Vault stock chip** — `data-weapon="mine"`.
- **Orbit purchase row** — the `[ MINE ×N ]` control, its `build_mine`
  hook, `#solo-orbit-mine-count`, and its `aria-label`.

### `app.js`
- **Deploy row** (`_buildDeployBlock`) — the `[ MINE ]` chip, its order
  tag, stock readout and AoE `title`.
- **Right-click board menu** — the "mine here" entry.
- **Queue counts** — the zeroed tag map.
- **Aim banner labels** — `MINE @`.
- **Order markers + hint text** on the board.
- **Policy wire normalisation** — three separate spots.
- **Orbit panel** — costs, labels, input id.
- **Three-chip readouts** — literal `["emp","mine","chaff"]` loops, in
  two places.
- **Weapon chip strip** — `makeChip("mine", "MINE", ...)`.
- **Tooltip / cell data** — the caltrop glyph `◆` and its label.
- **AoE preview** — kind mapping and `_actionFootprint` / `_mineShape()`,
  fed by `weapon_specs.<name>.batch_shape` stashed from the view.
- **Replay FX** — `paintMinesOverlay`, `_runMinelayerArc`, `mine_emit`,
  `mine_detonate`, weapons-used derivation, scoreboard `mines_laid`.
- **Glyph + orbital activity tally.**

### `station.js`
Log label, glyph, and the `mine_emit` delta animation.

### `styles.css`
`.aoe-shape--mine`, `.cc-celltip-aoe--mine`, `.cc-order-marker--mine`,
`.mine-cell-marker`, `.mine-detonate` + keyframes, `.cc-weapon-icon-mine`,
and weapon-chip active-target states.

---

## 6. Docs

- `RULEBOOK.md` — the mechanic's own section (mine was **§4.9.4**), the
  order-footprint line in §3.11, the orbit action table in §4.2, the blue
  economy worked example in §4.9.1, EMP interaction in §4.9.3, the replay
  frame/persistence notes in §4.9.6–7, the move tag list, and the board
  menu list in §7. Plus a new changelog entry and a header bump.
  **Never edit past changelog entries.**
- `manual/manual.js` — prose. Note there was never a MINE tab, only EMP
  and CHAFF; a new weapon probably wants one (`manual/index.html`).
- `manual/agent-data.js` — **generated**. Regenerate via
  `scripts/export_agent_guide_data.py` (needs Snowflake + a local card
  file; see the tracker).
- `guide/index.html`, `README.md`, `docs/HACKATHON_BUILD_PLAN.md`,
  `docs/AGENT_ARCHITECTURE.md`, `manual/ANIMATION_LOOPS.md`, and the
  harness's own `ENGINE_INTERFACE.md` (which must say which night verbs
  the engine accepts, and which it now refuses by name).
- `AGENTS.md` names the live dials in `weapons.py`; it reads
  "EMP/chaff dials" since the retirement, so a third weapon puts itself
  back in that list.
- `snowflake/soc_schema.sql` and `soc_procedures.sql` carry comments
  describing the columns and the accepted action list. The mine columns
  are annotated retired-but-preserved rather than deleted.

---

## 7. Tests, evals, scripts

- `tests/test_v09_weapons.py` — the weapons suite; mine had the bulk of
  it (parse, build, lay, cluster, visibility, EMP neutralise, round-trip).
- `tests/test_game_mvp.py` — damaged-harvester chain after a caltrop step.
- `tests/test_snowpark_batching.py` — replay columns.
- `tests/test_v18_combat_events.py`, `tests/test_v16_killfeed.py`,
  `tests/test_agent.py` — `weapon_stock` **default shape** assertions.
  These break on any change to the key set.
- `sea_of_colours/evals/assertions.py` — weapon deny/allow tuples.
- `sea_of_colours/evals/builder.py` — `give_weapon_stock(...)`.
- `sea_of_colours/evals/season_metrics.py` — `kills_<name>`.
- `scripts/fake_weapons_season.py` — one scripted night per weapon per
  seat; `scripts/fake_graphics_season.py` derives its weapons half from
  it, so adding a night there lengthens both reels automatically.
- `scripts/_fx_aoe.py` (footprint parity vs the engine) and
  `scripts/_fx_vision_geom.mjs` (the client's own shape maths) both
  enumerate the area-claiming actions by name.
- `scripts/_fx_orbitpublic.py` — the station glyph. Note it **injects**
  the frame by rewriting the replay response, so it still covers the
  caltrop's archived-playback path even though nothing can emit one.

### What a retirement must NOT delete

Learned from the caltrop, which got this right by accident more than
design. A weapon's **replay** surface outlives the weapon: the frame
channel, the Snowflake column, the `station.js` glyph and label, and the
orbital activity tally all keep classifying frames recorded before the
retirement. Strip them and every archived season that used the weapon
plays back with holes in it. The engine, the buy, the order and the
prompt text are what go.

---

## 8. ⚠️ The word "mine" is overloaded — read before grepping

A find-and-replace on `mine` **will destroy the V12 agent**. These are
unrelated to the weapon and must never be touched:

| Pattern | Actually means |
|---|---|
| `entities.mine` | the seat's **own fleet** (harvesters/probes) |
| `situational.mine`, `redsign[].mine` | a redsign **you discovered** |
| `probe: "mine"` | probe **owned by you** |
| `cells_mined`, `unmined_value` | harvest statistics |
| "mine/enemy split" | per-seat scoreboard colour |
| "mines BLUE in even chunks", "fully mined out" | English verb, in `RULEBOOK.md` |
| "frontier cells already mined" | English verb, in `ENGINE_INTERFACE.md` |

The same trap applies to a future weapon named after a common word.
