# Why Tabula v6 now emits *all* its moves

## The failure it fixes

Through v5's early reruns the agent kept losing whole turns the same way:
the primary LLM would open its response with analysis — scoring every visible
RED cell, enumerating both probe disks, re-deriving chain scores, checking
Manhattan adjacency step-by-step — and burn its entire byte/token budget on
that prose. It got cut off **before it ever emitted `"moves"`**. The
downstream finisher then had nothing to extract and improvised a weak plan
(self-superseding probes, one-parcel drops, idle harvesters).

The smoking gun was a real day-7 turn: ~8 KB of correct spreadsheet reasoning
(Chain A = 256 pts fully worked out) and **zero moves emitted**. The right
idea never made it into JSON.

The fix is not "make the model smarter." It is a **six-layer system** that
makes emitting a complete `moves` array the cheapest, first, and most
protected thing the model does — and makes the plan complete even when the
model's output is partial.

---

## Layer 1 — Moves-first output contract (the breakthrough)

The single highest-leverage change. The response spec forces the JSON to lead
with the moves array and forbids any pre-amble:

- `soc_create_agent_tabula_v6.sql` → `instructions.response`:
  - "The FIRST characters you emit MUST be: `{"moves":[`"
  - "The full `moves` array MUST be complete within the first ~1500
    characters."
  - "OUTPUT ORDER MATTERS: emit `moves` FIRST, then the short prose fields."
  - "a truncated response that still contains a complete `moves` array is a
    SUCCESS."

The schema itself is declared in moves-first order (`moves` → `plan_this_turn`
→ `rationale` → `predicted_outcome` → `memory_note` →
`reflection_on_last_night`). Prose is explicitly demoted to "optional
garnish." So even a hard truncation now lands the only field that matters.

## Layer 2 — "Reason in your head", not on the page

The orchestration + response instructions repeatedly tell the model to do all
analysis silently:

- "Reason briefly IN YOUR HEAD (not on the page), then output ONE JSON object."
- "Do NOT enumerate cells, do NOT list drop-legal zones, do NOT re-derive
  chain scores, do NOT verify adjacency step-by-step on the page. That work
  belongs in your head."

This removes the exact prose that used to consume the whole budget. (Caveat:
for `claude-haiku-4-5` as currently configured this suppresses *visible*
chain-of-thought — it trades a reasoning trace for byte/latency budget. See
the v7 GOAL for the extended-thinking follow-up.)

## Layer 3 — The model is a *selector*, not a *solver*

The heavy reasoning that used to be written out is pre-computed by the harness
and handed to the model as a candidate menu, so there is far less for it to
derive (and therefore far less to write):

- `probe_hints.py` — probe placement hints, hot-drop probe+drop pairings
  (fog-gated, with a precomputed serpentine `comb_path`), and last-night
  supersede targets.
- `heuristic_chains.py` — ready-made RED chains (drop → steps → pickup) scored
  and ordered.
- The prompt lists these as blocks 12–15 ("Pick, alter, or reject").

The model picks from the menu instead of solving the optimization on the page.

## Layer 4 — Budgets that don't bind before the JSON arrives

Truncation used to happen because the caps were too tight for a full 21-move
plan plus prose:

- Response byte cap raised to **8000** (primary) / **4000** (finisher) in
  `cortex_invoker.py::RESPONSE_CAP_OVERRIDES`.
- Token budget raised to **16000** in the SQL (`orchestration.budget.tokens`),
  so tokens are never the binding limit.
- The **wallclock** stays the hard ceiling (55 s SQL / 60 s invoker). This is
  deliberate: with moves-first output, the completion predicate closes the
  socket as soon as a balanced JSON object has streamed, so the roomier byte
  cap costs no extra wallclock in the common case.

## Layer 5 — The finisher is no longer blind

If the primary still stops short, the continuation finisher gets real board
state, not just a text tail:

- `harness.py::_continuation_prompt` passes day, day cap, orbit harvesters,
  chain hints, and supersede hints.
- Safety net: if a finisher plan banks less than `_MIN_FINISHER_RED_VALUE` of
  reachable RED and chain hints exist, the harness swaps to the deterministic
  heuristic chain instead of shipping a weak improvisation.

## Layer 6 — The sanitizer guarantees a *complete, legal* plan

Even a partial or slightly-illegal LLM plan is mechanically finished and
corrected before it reaches the engine (`move_sanitizer.py`):

- **Deploy-all-harvesters guard** — any harvester still in orbit after the
  LLM's plan gets the top unused legal heuristic chain appended (drop → steps
  → pickup). No idle harvesters.
- **Self-crush guard + absorb-first-step** — a drop onto a still-useful probe
  is rerouted (or the first step absorbed into the drop) to spare the probe
  while keeping the harvest chain intact.
- **Reroute / re-thread (`drop_delta`)** — when a drop is relocated, every
  following step is translated by the same delta so the hand-built chain
  re-threads onto the new landing instead of being amputated. This alone
  recovered the ~68% of planned steps that used to be lost to reroute-orphaning.
- Collision, green-hazard, and crash-guard pickup fixes.

---

## The net effect

| Failure (v5 early) | Mechanism that removes it |
|---|---|
| Prose eats budget → no `moves` | L1 moves-first + L2 reason-in-head |
| Model over-solves on the page | L3 hints menu |
| Cap truncates a valid full plan | L4 roomier byte/token caps |
| Finisher guesses blindly | L5 board-state + heuristic net |
| Partial/illegal plan reaches engine | L6 sanitizer completes + legalizes |

Emitting a complete `moves` array is now the first thing the model does, the
cheapest thing it can do, and — failing all of that — something the harness
guarantees regardless. That is why v6 reliably does *all* the moves.
