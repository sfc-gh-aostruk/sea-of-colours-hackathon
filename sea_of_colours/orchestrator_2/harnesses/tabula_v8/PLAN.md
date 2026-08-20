# Tabula v8 — CANONICAL PLAN: data + doctrine + observability (current stack)

> Status: **plan — being executed incrementally.** v8 is the *consolidation*
> release on the **current stack** (haiku, Agents API). It bundles the
> observability + engine/view data hooks + doctrine fixes that came out of the
> v7 audit. **No model change, no endpoint change** — those live in
> `../tabula_v9/PLAN.md` (native bounded thinking on the inference API).
>
> v8 fixes are model-agnostic: they make the agent *see the right facts* and
> *observe what it did*. v9 later swaps the reasoning engine on top of them.

---

## 0. Framing — why v8

v7 taught us the bottleneck was never the prompt — it was the **channels and the
data**. The token-opaque-budget fix (moves-first + reason-in-head) and the
containment fix stopped the truncation failures. What's left, and what v8
fixes, is:

1. **We can't *see* what the reasoning agent did.** A turn can fire several
   sub-agents; the UI shows only the final mover. Fix that first so every
   subsequent experiment is observable (§3).
2. **The agent reasons on incomplete / mis-framed inputs** — weapons as a global
   boolean, no redsign ownership, no enemy-probe cells, EMP framed as
   distance-from-a-cluster. Feed it facts (§4).
3. **Some of v7's logic is genuinely good, some confidently wrong.** Keep the
   highs, kill the lows with **data + doctrine**, not more prompt nagging (§5).

Gate: if v8 (still haiku, current stack) beats the frozen v6/v7 champion on the
seed set, that proves the data+doctrine thesis and greenlights the v9 model
upgrade. If it doesn't, we've learned the ceiling is the model, not the inputs.

---

## 0.5 The reasoning engine — the CONTAINED THINKER (haiku, no sonnet)

**The hard problem, stated honestly.** v6/v7's mover is *moves-first*: it emits the
`moves` array before any reasoning, so the moves are chosen with **no prior
reasoning tokens** — it collates our precomputed hints and picks. That is why it
feels "dumb": moves-first traded away chain-of-thought to guarantee completion.
Data + doctrine (§4/§5) alone can't fix that — you can hand the collator better
inputs, but **without a reasoning pass it won't actually reason about them** (the
redsign "poker" — contest? supersede? commit two harvesters? — is a *decision*,
not a lookup).

**Why we can now get contained thinking out of haiku.** The two-call split
failed before for ONE reason: the thinker ran on the **Agents API**, where
thinking is unbounded (~30–44s) → blew the wall. We fixed the *mover* by moving
it to the inference API; **we never applied that same fix to the thinker.** Do
so, and:

- **Thinker on the inference API**, `max_completion_tokens` hard-capped, output a
  **reasoning-FIRST** JSON schema:
  `{ reasoning: string, posture, targets[], chaff_react, avoid[], note }`.
- Because generation is autoregressive, the `reasoning` tokens are emitted
  **before** the decision fields and **condition** them — that is genuine
  chain-of-thought. This is the exact opposite of the moves-first mover, and it
  is the practical mechanism by which the split can out-decide the single mover.
- The hard token cap means the CoT is **bounded** — it reasons, but structurally
  **cannot ramble past the budget** (the containment fix, now applied to the
  thinker instead of only the mover).

**The handoff (thinker → mover).** Parse the decision fields into the existing
`Directive` (`directive.py`), sanitize (clamp targets in-bounds, cap lengths),
and inject the compact `STRATEGIST DIRECTIVE` block into the **contained mover**
prompt. The mover stays moves-first (fast, complete) but now executes a
*reasoned* decision instead of deriving one under byte pressure. Both halves
haiku, both on the inference API, both bounded.

**Honest caveat.** This is haiku's *bounded on-page CoT*, not sonnet-style native
extended thinking. It is genuinely more than the collator mover (the decision is
conditioned on reasoning tokens), but whether that reasoning is *good* is an
empirical question — which is why §3.5 makes the thinker's reasoning
**scannable across scenarios** before we trust it.

## 3.6 FINDINGS — contained thinker validated (seed 42, 2026-07-23)

First live scan of the contained thinker (`scripts/scan_thinker.py`, split +
`THINKER_API=chat` + `MOVER_API=chat`, both haiku on the inference API) vs one
heuristic opponent on seed 42:

- **Result: 3450 vs 380** — decisive. Report: `reports/thinker_scan_s42.md`.
- **The reasoning is REAL, not narration.** Across nights the thinker: ranks
  candidate chains by tier-weighted EV; identifies enemy-*watched* cells and
  routes the chain around them (choosing a lower-EV but safe chain when the
  richer one is contested); distinguishes held-hoard from shipped score in its
  reflection instead of inventing an EMP loss; and on **day 4 detects the
  redsign, flips posture to `redsign_race`, checks whether the enemy probe
  actually contests the beacon, and commits the ~1974-pt pure seam.** Final
  night → `final_convert`. This is the deliberation the moves-first mover
  structurally cannot do.
- **Bounded, no wall blow-up:** 15–25s per thinker call (vs the Agents-API
  thinker's 40–45s runaway that killed the original split).
- **Truncation edge (fixed):** 2 of 7 nights (the longest, richest boards) ran
  the reasoning-first CoT past the 2500-token cap, so the JSON object never
  closed → no directive AND the CoT was lost. Fixes shipped: raised the cap to
  3600, and `directive._salvage_reasoning()` now recovers the CoT text even
  from a truncated object (directive stays None → mover safely degrades to
  single-call). **Re-scan confirmed 7/7 clean** (0 empty CoT, 3421 vs 1008;
  `reports/thinker_scan_s42_v2.md`).

**Bottom line for v8:** the contained thinker is the reasoning engine v8 needs —
this is what makes the §4 redsign data actually get *reasoned about* rather than
collated. The next A/B is contained-thinker+mover vs the single mover on the
frozen seed set to quantify the lift.

### 3.6b Head-to-head arena — v8 vs v7 vs v6 (seed 42, 3-player, 2026-07-23)

One map, three seats contesting the same tiles (`scripts/run_versus.py`;
`reports/versus_s42_v8_v7_v6.md`):

- **v8 3728 · v7 275 · v6 −100** — v8 lapped both frozen champions in a
  directly-contested game. Correct posture engagement (`redsign_race` on d3/d6).
- **Cost 1 — latency:** v8 split turns ran 38–54s vs v7's ~15s. **Day 4 hit 54s**
  (at the 55s live wall). The split's quality costs ~2–3× wall time → not yet
  comfortably live-safe on dense nights.
- **Cost 2 — truncation recurred (d4, `posture=None`):** reasoning-first CoT blew
  even the 3600 cap → degraded to mover-only that night. Same knot: bigger cap →
  better reasoning → slower turn.
- **Open levers:** (a) raise cap / tighten the thinker prompt for dense boards;
  (b) run the *controlled* A/B (v8-split vs v7 single **contained** mover) to
  isolate the split's lift from the channel; (c) latency budget for live play.

## 3.5 Scan the thinker's reasoning (validate it actually reasons)

Persist the thinker's `reasoning` field (via §3's multi-row audit — the thinker
gets its own `SOC_AGENT_INVOCATION` row) AND provide a standalone
`scan_thinker.py` that runs the thinker on a battery of crafted boards
(uncontested redsign, contested redsign with a weapon-capable enemy, post-chaff
night, thin-seam night, multi-opponent) and dumps `reasoning` + resulting
`Directive` side by side. This is how we judge — before any season A/B — whether
the contained CoT produces real strategy (contest/supersede/stagger) or just
narrates. Kill or keep on what the reasoning actually says.

---

## 1. v7 audit — highs to KEEP, lows to FIX

### Highs (the "blown away" parts — preserve, don't regress)
- **Grounded reflection actually lands.** Handed the engine's real prior-night
  numbers it stops hallucinating outcomes (post vault-red-value fix).
- **Probe-then-harvest sequencing + seam extension.** It reasons about frontier
  vision (`edge_promise`, `area_gain`) and seeds next-day probes coherently.
- **Hoard-vs-shipped awareness** (new, §2) — it now understands held value.
- **Self-limiting on wasteful re-probes** ("probe already active, 2 nights
  remaining, so I avoid re-probing") — correct EV reasoning.
- **Honest what-could-go-wrong** — it *names* the enemy-probe overlap risk.

### Lows (the "that's not right" parts — each gets a concrete fix below)
| # | Wrong behaviour observed | Root cause | Fix (section) |
|---|---|---|---|
| L1 | Judged EMP risk **low because the enemy was "clustered on the far east side"** | Thinks of opponents as ground units with a map position; they're **orbital** and can strike anywhere. A redsign + probe drop tells them EXACTLY where you'll land. | §5 doctrine reframe + §4d EMP constants in view |
| L2 | Weapon threat collapsed to a **global boolean** (`beware_emp` on/off) | `opponent_weapons` inference folds per-seat estimates into one flag | §4b per-seat weapon read + §5 "know who has what" |
| L3 | **Ignored `! WATCHED`** signal on a contested drop | No doctrine tying WATCHED → contest tactics | §5 contested-drop doctrine |
| L4 | Named enemy-probe overlap as a risk, then **harvested there anyway** with no mitigation | No supersede/denial or multi-harvester-commit doctrine | §4c enemy probes + §5 supersede denial |
| L5 | Couldn't tell **its own redsign from an opponent's** | Engine drops `discoverer` when minting redsign regions | §4a discoverer attribution (engine change) |
| L6 | Confused "harvested" with "scored" (`actual:0 → pickup failed`) | vault_score = shipped only; hoard scores 0 until shipped | **DONE in v7** (§2) — port to v8 |
| L7 | Banked **7 parcels in one outing** (over the 6-hold cap) | Engine never enforced hold cap | **DONE in v7** (§2) — port to v8 |

---

## 2. Carried-over fixes already landed in v7 (port verbatim to v8)

Done, tested, shipping in v7. v8 forks them unchanged:
- **Vault RED value line / hoard-vs-shipped grounding** (`prompt.format_state_block`
  + `format_reflect_block`, `view.py` `hud.hoard.red_value`). Kills L6.
- **Harvester 6-parcel hold cap** (`session.HARVESTER_HOLD_CAPACITY`,
  `try_step_unit`) + sanitizer `_clip_outing_steps`. Kills L7.
- **Grounded reflection** (`recorder.compute_banked_this_night`,
  `format_reflect_block`).
- **Moves-first contract + completion predicate + finisher + heuristic net.**

---

## 3. Observability — MULTI-AGENT REASONING UX (the explicit ask, build FIRST)

**Problem.** A turn can fire several sub-agents (thinker → mover → finisher).
Today the UI shows **only the mover's output**: the harness returns one
`response`, the runtime writes **one** `SOC_AGENT_INVOCATION` row, and the
thinker / finisher traces are discarded (only char-counts survive in `extras`).
So the operator cannot see the part of the pipeline that's "blowing me away /
that's not right."

**No schema migration needed.** `GET /api/game/{id}/agent-log` already returns
an **ordered array** of invocations (sorted by `seq`) and the frontend
(`ensureAgentLogForDay` → `captureAgentRationale` → `renderAgentFeed`) already
loops them. `append_agent_invocation` already auto-increments `seq`. The blockers
are three, all additive.

### 3.1 Storage — write ONE ROW PER SUB-AGENT (not per turn)
- Extend the harness result with `extras["sub_invocations"]`: a list of
  `{role, agent_id?, response_text, rationale?, prompt_excerpt?, ms_elapsed?,
  phase?}` for each non-primary reasoning artifact (thinker, finisher).
- `audit.write_invocation` writes each as its own row (reusing existing columns):
  - distinct `agent_id` suffix so the UI can label it
    (`TABULA_V8_THINKER`, `TABULA_V8_FINISHER`),
  - `phase: "pre"|"post"` controls order vs the primary (mover) row so `seq`
    reflects chronology (thinker=pre, finisher=post),
  - the **executed answer stays the last row** (mover, or finisher when it
    supersedes) so `evals`' "last-invocation-on-policy-day" logic still selects
    the real answer.
- Backward compatible: harnesses that don't set `sub_invocations` write one row
  exactly as today.

### 3.2 Frontend — group + label + order by seq
- `renderAgentFeed()`: **sort by `seq`**, **label each entry** with a role chip
  (THINKER / MOVER / FINISHER), colour-coded, grouped under the turn's day;
  guard the exact-text dedupe so distinct roles never collapse; render long
  reasoning bodies collapsible so the mover's moves-JSON stays readable.
- Keep the existing `[fallback]` cortex→heuristic split behaviour.

### 3.3 Live mode — fetch the log during bot turns
- `ensureAgentLogForDay` (full-log fetch) is currently called **only on replay**.
  Call it on status refresh once a bot turn resolves (guarded against
  over-fetching) so the labelled stack shows live, not just in replay scrub.

### 3.4 Acceptance
- With a multi-call variant running, the AGENT tab shows a labelled, seq-ordered
  stack (THINKER / MOVER / FINISHER) for the active seat + day, live and replay.
- v1–v7 single-row turns render unchanged. `evals` still reads the answer row.

---

## 4. Engine / view data hooks (feed the agent facts, not vibes)

Model-agnostic; fixes L1, L2, L4, L5.

### 4a. REDSIGN discoverer attribution (engine) — fixes L5
- `session._register_redsign` / `_mint_redsign_region` currently drop who
  discovered the region. Add a `discoverer` (seat) field to the redsign payload
  and thread it into the per-seat view.
- View: annotate each visible redsign with `discoverer: "p1"|...|null` (null for
  legacy/unknown). Prompt renders "REDSIGN (yours)" vs "REDSIGN (p2's —
  contested)". **Engine change — migrate carefully, default `null` for legacy.**

### 4b. Per-seat weapon read, surfaced WITH position — fixes L2
- Stop collapsing `opponent_weapons` into a global `beware_emp` boolean. Surface
  a per-seat line: `p2: EMP≈1-2 (1 fired D3), chaff≈0, mines≈0`.
- Pass the evidence basis: **fired launches are exact; un-fired blue-band builds
  are `min..max` estimates.** The agent must treat fired = fact, un-fired =
  estimate (not guesswork, not certainty).

### 4c. Enemy probe cells + ages — fixes L4 (denial planning)
- Surface visible enemy probe cells with `age` / `nights_remaining` so the agent
  can plan a **supersede** (land a probe on the enemy's discovering probe to
  blind them) or route around it.

### 4d. Weapon geometry constants — fixes L1
- Surface `EMP_RADIUS`, `EMP_CLOUD_HOURS`, `CHAFF_DURATION_HOURS`,
  `MINE_BATCH_SHAPE` in the agent view (already in the results payload's
  `weapon_specs`). The agent must reason about EMP as a **targeted orbital strike
  with a known radius on a known beacon**, not a distance-from-a-cluster gamble.

---

## 5. Doctrine — the redsign "poker" opening book (fixes L1, L3, L4)

Encode the contested-race doctrine as state-triggered guidance (the v5/v6
pattern), gated on the §4 data so it only fires when relevant.

- **Attribution first.** Redsign **mine** (§4a) → I discovered it, my probe sees
  it: race the drop, comb short. **Theirs** → assume contested.
- **Contested (theirs / `! WATCHED`) → commit multiple harvesters, expect some to
  fail.** Short direct comb; commit H1 **and** H2; if the enemy seat is
  weapon-capable (§4b), **stagger H2 behind a fresh probe (~H9)**, exfil by ~H13,
  and drop a **fallback probe offset from the beacon** so a mass-nuke still
  leaves night-2 vision.
- **Denial via supersede.** In contested-vision harvests, consider **blinding the
  enemy first**: launch a probe onto the enemy's discovering probe to supersede
  it and deny future drops. Honest engine timing: **a drop committed in hour K
  still lands** even if you supersede in hour K (vision snapshots at hour-start);
  supersede denies K+1 onward. "H1 drop happens before H1 supersede — that's the
  risk you take."
- **Weapon-paced staging, not distance-paced.** EMP risk = *does this seat have
  EMP stock + a beacon to aim at*, **not** how far away they look. A redsign +
  your probe drop is a bullseye. Reframe L1 explicitly in the rules.
- **Up to 3 opponents.** More seats → higher contest odds → fallback probes and
  multi-harvester commits are worth *more*, not less.

All doctrine stays **bounded by the sanitizer + RULES** — it changes priorities,
never legality.

---

## 6. Validation

1. **Build §3 first** so everything after is observable.
2. **Single-seed spike** (seed 42) per lever, in order: §4a → §4b → §4c → §4d →
   §5. Eyeball decision quality with the new reasoning viewer; check
   truncation/fallback rate and wallclock hold steady.
3. **Full seed set** (42 / 7 / 99 / 2024): **v8 vs frozen v6/v7 + heuristic.**

### Success criteria
- **§3 UX:** each sub-agent's reasoning is visible, labelled, seq-ordered (live +
  replay).
- **Data/doctrine:** v8 beats v6/v7 on the seed set; measurable drop in
  harvesters lost to chaff/EMP on contested drops; the agent distinguishes its
  own redsign and acts on `! WATCHED`.
- **No regressions:** truncation/fallback rate ≤ v7; turn wallclock p95 within
  the current ceiling (no model/endpoint change to blame).
- **Gate to v9:** if v8 wins, greenlight the native-thinking model upgrade
  (`../tabula_v9/PLAN.md`).

---

## 7. Build order

1. **§3 observability MVP** (multi-row persist + frontend labeling + live fetch).
2. **Port §2 v7 fixes** into the v8 harness fork.
3. **§4 data hooks** (4a discoverer → 4b per-seat weapons → 4c enemy probes →
   4d weapon constants), each with tests.
4. **§5 doctrine** blocks, gated on §4 data.
5. **§6 validation**: spike → seed set → gate to v9.

## 8. Risks

- **§4a is an engine change** (redsign payload) — touches persisted state; migrate
  carefully, default `discoverer=null` for legacy regions.
- **§3 multi-row writes** change `seq` density per turn — verify no consumer
  assumes one row/turn (`evals` last-row logic must select the answer row via
  `agent_id` role / `phase`, not blindly the max `seq`).
- **Doctrine over-firing** → gate every §5 block on §4 data + game state; keep the
  sanitizer as the legality backstop.
- **Scope creep into v9** → v8 is strictly current-stack. Any `reasoning.max_tokens`
  / sonnet / inference-API work belongs in `../tabula_v9/PLAN.md`.
