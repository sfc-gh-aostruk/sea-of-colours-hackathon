# Tabula v6 & v7 — the real changes

This is the ground-truth record of what *actually* changed in v6 (from v5) and
v7 (from v6) — code, not aspiration. Both versions are fully self-contained
packages under `harnesses/tabula_v6/` and `harnesses/tabula_v7/`; v1–v5 are
untouched at their own bindings.

Two of these changes are foundational discoveries that apply to **every** agent
in the project, not just tabula:

1. **The forced moves-first contract** (v5→v6 hardening) — make emitting a
   complete `moves` array the first, cheapest, most-protected thing the model
   does.
2. **The token-opaque-budget fix** (v7) — the Cortex *Agents* API conflates
   thinking + answer + tools into one opaque budget, which is why agents ran out
   before finishing a plan. The Cortex *inference* API separates them, giving a
   hard-capped answer + a separately-bounded think + a schema guarantee.

---

## v6 — comprehension, not new mechanics (fork of v5)

v6 kept the v5 breakthrough (moves-first output; see
`tabula_v6/MOVES_FIRST.md` for the full six-layer write-up) and added three
concrete upgrades aimed at *understanding the board and the prior night*.

### 1. Grounded reflection (stop guessing last night)

**Problem.** v5's `reflection_on_last_night` was self-authored from memory, so
the agent routinely mis-stated what happened — it lost harvesters to chaff and
never acknowledged it, or hallucinated engine mechanics.

**Change.** The harness now feeds the agent the engine-resolved truth of the
prior night and forces it to echo it:

- `recorder.py` closes the prior day with the real outcome — `actual_banked`
  and `probe_crushes` — computed from the turn-start snapshot vs the resolved
  board.
- `memory.py` persists those fields on the prior entry.
- `harness.py` pulls the `prior_day_entry` and passes it to `build_prompt`.
- `prompt.py::format_reflect_block` renders a `REFLECT ON LAST NIGHT` block:
  predicted vs **actual** banked points, and the concrete gap cause (chaff jam,
  EMP, probe crush, dawn crash, thin seam).
- The response schema now *requires* the agent to copy the exact `actual`
  integer and name the `gap_reason` from that block — it can no longer invent a
  number.

### 2. Fog-gated Redsign hot-drop with a precomputed comb path

**Problem.** "Hot drop" was misunderstood and misused — the agent would drop
onto an already-visible cell (no fog to exploit) or make a 2–3 step token
gesture instead of actually combing the newly revealed disk.

**Change (`probe_hints.py` + `prompt.py`):**

- `_known_green_cells` — identifies green cells already in live vision so the
  comb never steps on poison.
- `_comb_path` — precomputes a **blind serpentine** that covers the probe's
  Euclidean radius-4 disk, staying inside the disk, avoiding known green, and
  biased toward where value is likely (so the hot-drop actually *combs*).
- `top_hot_drop_hints` now carries a `target_in_fog` flag (only suggest a
  hot-drop when the target is genuinely fogged) and the ready `comb_path`.
- `prompt.py` renders a `READY COMB` block: "copy these steps after the drop" —
  turning a hot-drop from a vague intent into a ready-to-execute chain.

### 3. Absorb-first-step self-crush guard (`move_sanitizer.py`)

**Problem.** A harvester dropped onto a cell where you still hold a useful probe
crushes it. v5 either kept the crush (losing the probe's disk) or rerouted and
orphaned the hand-built step chain.

**Change.** When a drop lands on a still-valuable, empty probe *and a harvest
chain follows*, the sanitizer now **absorbs the first step into the drop**:
reroute the drop to the first step's target cell (if legal and not itself a
probe), then skip that now-redundant step (`absorb_skip`). This spares the probe
*and* keeps the chain intact. Falls back to keeping the crush only when the
first step cell isn't a legal landing. (`_first_following_step_cell`,
`absorb_skip`.)

> Net effect of v6: the agent finally *reads* the prior night correctly, hot-
> drops the way the mechanic intends (blind comb over fresh fog), and stops
> throwing away probes it still needs — all without touching game mechanics or
> the moves-first win.

---

## v7 — the reasoning-containment experiments (fork of v6)

v7 began as a byte-for-byte copy of v6 and added two independent bets at the
*reasoning* layer. One failed and is parked; one is a major discovery.

### 4. Two-call reasoning split — **PARKED (documented negative result)**

**Idea.** A dedicated "thinker" call commits a tiny `DECISION` directive
(posture + targets + chaff flag); the proven v6 moves-first "mover" then
executes it. Gated by `TABULA_V7_MODE=split` (default `single` = pure v6).

**Built:** `directive.py` (parse/sanitize/render the DECISION), `build_prompt
mode="thinker"|"mover"` + directive injection, the
`SOC_RED_REAPER_TABULA_V7_THINKER` agent spec, harness two-call wiring, invoker
caps, tests.

**Why it's parked (measured, seed 42):**

| Run | thinker cap | thinker fired | p1 (v7) | p2 (heur) | winner |
|---|---|---|---|---|---|
| A | 18s | 0/7 nights (silent v6) | 1768 | 1622 | p1 |
| B | 50s | 2/7 nights | 980 | 3083 | heuristic |

haiku on the Agents API does ~27 KB / ~30–44 s of **unbounded extended
thinking** before it emits the DECISION, so an 18 s cap truncated it every night
(silent fall-through to v6); a wall-breaking 50 s cap landed a usable directive
only ~2/7 nights and it was low-information (`aggressive, targets=[]`). The
split cost ~+40 s/night, broke the 55 s wall, and showed no benefit. Kept behind
the flag as evidence, not a champion.

### 5. The token-opaque-budget fix — inference-API mover (**the big one**)

**Root cause finally isolated.** It was never the model — it was the Cortex
**Agents** API (`agents/{name}:run`). Its server-side orchestration loop
conflates thinking + answer + tools into **one opaque budget**. Invite reasoning
and it runs away (the thinker); suppress it and you get a fast but *dumb*
collator (the v6 "reason in your head" mover). There is no "think a bounded
amount, then answer" — which is the exact failure mode the whole project kept
hitting: **agents run out before they emit a full plan.**

**The fix.** Run the strategic surface on the Cortex **inference**
`/chat/completions` API instead, where the budgets are *separate dials*:

- `max_completion_tokens` — a **hard, honored answer budget**. The model
  self-budgets to fit and always finishes (normal chat behavior). Measured:
  haiku returns a complete moves plan in ~6–14 s, never runs away.
- `reasoning` — a **separate, bounded thinking channel** for thinking-capable
  models (sonnet-4-6): `reasoning.max_tokens` bounds the think (latency scales
  with the budget: 1500→16 s, 4000→25 s), answer budget untouched. haiku has no
  native thinking here and doesn't need it.
- `response_format: {type: json_schema}` — the output shape is **guaranteed at
  the API level**, so "prose ate the budget, no moves emitted" is structurally
  impossible.

**Built:**

- `orchestrator_2/cortex_chat.py::CortexChatInvoker` — the inference client:
  PAT auth, hard `max_completion_tokens`, optional bounded `reasoning`,
  isolated thinking/answer channels, and safe degradation (non-200 / timeout →
  the harness finisher/heuristic net engages).
- `tabula_v7/chat_schema.py::MOVES_RESPONSE_FORMAT` — the validated moves
  json-schema (heterogeneous move items; only `a` required; `additionalProperties
  false`; no `type`-arrays / `minItems` which Cortex rejects).
- `harness.py` — mover routes through the inference path when
  `TABULA_V7_MOVER_API=chat` (default `agents`, so nothing live changed).
- Unit tests (`tests/test_cortex_chat.py`) + schema wellformedness.
- No new Snowflake object — this path is pure inference (no `CREATE AGENT`).

**Result (seed 42, same board):**

| Mover backend | turn time | fallbacks | p1 score | winner |
|---|---|---|---|---|
| Agents API (v6-equiv) | ~30 s | some | 1768 | p1 |
| Agents two-call split | ~60 s | — | 980 | heuristic |
| **inference /chat/completions** | **~12 s** | **0** | **3591** | **p1** |

0 fallbacks all season, every plan complete + schema-valid, 2.5–5× faster.
(n=1 per config with a stochastic model, so the *score* lift wants multi-seed
confirmation — but the *containment* is proven: fast, complete, no runaway.)

### 5b. Restore grounded reflection on the inference path (`chat_schema.py`)

**Problem (found in the 4-season audit).** The inference mover won 4/4 but got
chaffed and lost a loaded harvester to a dawn crash in *every* seed — and never
adapted, even after being chaffed the prior night. Root cause: the chat
`response_format` json-schema omitted `reflection_on_last_night`, so strict
schema mode silently dropped it. v6's grounded-reflection pipeline still ran
(recorder fills `actual_banked`/`probe_crushes`; `build_prompt` injects the
REFLECT block), but the model was structurally unable to *emit* a reflection —
the night-to-night learning loop was severed on the winning path.

**Change.** Add `reflection_on_last_night` to `_PLAN_SCHEMA`, shape mirroring the
prompt's ACTION SCHEMA (`{predicted, actual:int, gap_reason}`). Kept **optional**
at the top level (night 1 has no prior night, and Cortex strict mode can't
express a nullable object — `type` arrays are rejected); the prompt drives *when*
to fill it, the schema only makes it *expressible*. Live-verified: the model now
emits e.g. `{"predicted":"high","actual":120,"gap_reason":"harvester_p1
destroyed at (5,5) due to chaff_jam"}`. Test coverage added in
`tests/test_cortex_chat.py::test_schema_constant_wellformed`.

> Lesson banked: a field you drop from the schema is a capability you delete.

### 6. Invoker thinking/answer channel isolation (`agent/cortex_invoker.py`)

Shared groundwork: reasoning tokens (`response.thinking.*`) are diverted to a
separate audit-only buffer, excluded from the answer byte cap and completion
predicate, so a long think can never eat the answer. Tests in
`tests/test_cortex_invoker_thinking.py`. This is what lets the inference path
surface a bounded reasoning trace for audit without it ever touching the answer.

---

## The two findings that generalize beyond tabula

1. **Forced moves-first contract.** Emitting the complete answer must be the
   first, cheapest, most-protected act — reinforced structurally by
   `response_format: json_schema` on the inference path (the shape is
   guaranteed, not merely requested).
2. **Separate the budgets.** Answer tokens and thinking tokens must be distinct,
   individually-capped resources. The Agents API's single opaque budget is the
   source of the recurring "no full plan" failure; the inference API's split
   budgets are the fix — a portable pattern for every future agent.
