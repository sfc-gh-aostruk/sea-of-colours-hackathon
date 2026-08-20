# TABULA_V4 backlog — improvements deferred from v3 development

This file collects design notes, observed weaknesses, and doctrine
extensions that came up during v3 debugging but weren't landed in v3.
Each item is scoped so it can be picked up standalone.

Add entries at the TOP with a date-tag so the newest signal is most
visible. Keep entries short and concrete — one paragraph max, plus a
"how to know it worked" line.

---

## 2026-07 — Categorized probe recommendations (from v4 seed=42 win)

### 7. Type-tag probe hints by strategic purpose

**Observed:** in the v4 slim-MANDATE winning run
(`ae0206410dfb495f8128d920dbf16f08`, 3690 pts, 14 probes) EVERY
compiler-generated probe hint carried `extends_from: "blue_sign"`.
Not because bluesign was always the right target — because the
compiler's seed priority order surfaces bluesign cells first when
they exist, and downstream the LLM only sees the top 3 hints. The
result: probes clustered on bluesign areas even when redsign or
raw fog expansion would have paid better.

**V4 direction:** replace the current
`extends_from: "blue_sign" | "redsign" | "fog_centroid" | ...`
label with a first-class STRATEGIC PURPOSE tag on each probe hint
so the LLM can weight them differently:

```
PROBE PLACEMENT HINTS:
  Probe A (REDSIGN CHASE):    at=(3,13)  area_gain=81  edge_promise=0
    Race-to-pure candidate — the seat that lands+chains+picks first wins.
  Probe B (BLUESIGN COVERAGE): at=(19,15) area_gain=72  edge_promise=0
    Public bluesign hotspot — high-density blue likely somewhere in the disk.
  Probe C (PURE EXPANSION):    at=(27,10) area_gain=81  edge_promise=54
    New fog reveal — no signal, but adjacent to a high-purity red seam.
  Probe D (SEAM EXTENSION):    at=(15,11) area_gain=45  edge_promise=112
    Extends visible-red edge — likely to reveal continuation of a chain.
```

The LLM can then reason "REDSIGN is 2295 pts base, worth all my
probes tonight if the disk overlaps the broadcast area" separately
from "BLUESIGN is a fallback if red is trace-only."

**How to know it worked:** the LLM's `plan_this_turn` on redsign
turns explicitly cites "chasing REDSIGN" rather than treating the
probe as generic exploration. Probe distribution shifts away from
100% bluesign-labeled toward a mix of strategic categories.

---

## 2026-07 — Threat-gated weapon awareness (from 2p seed=42 run)

Observed in session `0ff6fc015189472e8d41b5fb9970ce3b` (TABULA_V3 vs
heuristic, seed=42, days=7, final score 1630 vs 2242).

### 4. Weapon-aware behaviour must be CONDITIONAL on real threat

**Current v3 behaviour:** the OPPONENT WEAPONS block + BEWARE_EMP /
BEWARE_CHAFF doctrine appendices make the agent play defensively even
when the opponent has NOT built any weapons. Concrete example on day 6
of the 2p run: a redsign published two adjacent pure(255) cells at
approximately (3,13) and (4,13). The agent's day-6 probe placement at
(4,9) was deliberately DEFENSIVE — clipping the redsign area at the
Chebyshev-4 disk edge rather than centring on it — likely hedging
against a possible opponent EMP. This meant the agent only saw ONE of
the two pure cells on day 7, and the heuristic (which had zero
weapons) grabbed the second pure at (3,13) via a hot-drop before the
agent's slower 3-harvester chain could reach it.

The agent also spread all three harvesters across the redsign cluster
on the final night — great redundancy for a weapons-live game (some
would be denied by EMP), wasteful when zero weapons are deployed
(three harvesters compete for the same synthetic-green cells).

**V4 direction:** weapon-defense doctrine should be gated on
CONFIRMED opponent weapon stock, not the possibility of it. Read
`competitor_intel.weapons_seen` or the derived
`opponent_weapon_estimates` bucket. When the highest estimate is 0
across all opponents:

  * Drop the BEWARE_EMP / BEWARE_CHAFF appendices from the prompt.
  * Change probe-placement doctrine from "defensive edge" to
    "aggressive center of high-value seams."
  * Change multi-harvester doctrine from "spread for redundancy" to
    "concentrate on the highest-EV cluster with de-conflicted
    ownership."

Keep the current defensive posture ONLY when weapon estimates flag
at least one opponent as `emps_max > 0` or `chaff_max > 0`.

**How to know it worked:** on a 2p run where the opponent never
builds weapons, the agent's probe placements are within Chebyshev-2
of the highest-value visible red or redsign centroid (not at the
disk edge). Multi-harvester chains reference explicit cell ownership
in the LLM rationale ("harvester_p1 owns (3,13), harvester_p1_2
owns (4,11-14), harvester_p1_3 owns (2,11-12)").

### 5. Aggressive redsign response — probe-blanket + same-night hot-drop

**Current v3 behaviour:** the redsign block in the RULES text tells
the agent the pure(255) cell is worth 765×3.0=2295 base pts and says
"race the opponent." But when a redsign fired on day 5 of the 2p
seed=42 run (session `0ff6fc0…`), the agent's day 6 response
treated it as a generic fog cluster. It launched ONE probe at (4,9)
— clipping the redsign area at the Chebyshev-4 disk edge — and
called it a "nomadic probe." The harvester chains for day 6 stayed
in the (13-14, 7-10) corridor harvesting trace-tier red for ~160
pts, while the redsign area was left unexplored. By day 7 (final
night), the heuristic had already harvested one of the two adjacent
pure cells in a same-night hot-drop; the agent could only chase
what remained.

Note: the redsign is an AREA broadcast (a seam pointer near a coord,
not a precise cell). The agent doesn't need to know the exact pure
coord to race — it needs to blanket the area with probes and hot-drop
immediately.

**V4 direction:** when a redsign is active in
`competitor_intel.redsigns` (or the equivalent view field), the
agent should:

  * Launch MULTIPLE probes into the redsign area (2-3 probes in a
    tight cluster around the broadcast coord, filling the ~9x9 area)
    to guarantee full disk coverage of the seam.
  * SAME-NIGHT hot-drop: probe at hour K, drop-and-chain at hour K+1
    inside the newly-live disk. Do NOT wait a night for "the data to
    come in" — waiting cedes the pure to the opponent.
  * Do this on the FIRST NIGHT after the broadcast, not the second.
  * Override the normal probe budget — a redsign is worth up to 6
    probes committed to a single area, because the payoff is 2295+
    pts vs the ~500 opportunity cost.
  * DEPLOY WEAPONS on/around the redsign area to deny opponent
    access. EMP on the opponent's likely approach path, chaff to
    jam their pickup window, mines on the approach cells. A pure(255)
    is 2295 pts base — losing it to the opponent means a ~4000-pt
    swing (they gain, you lose the opportunity). One EMP (400 blue
    vault cost) that reroutes the opponent for a night is a bargain.
    Weapons are the ONLY way to actively contest a redsign — probing
    faster only wins the race if you're geographically closer.

This behaviour can be a first-class doctrine block ("REDSIGN
RESPONSE") in `strategies.py` OR a structural harness override
(when `redsigns_active > 0`, harness auto-injects 2 probes at the
broadcast area into the LLM's prompt as `must_include` moves).

**How to know it worked:** on any 2p or 3p run where a redsign
fires, the LLM's response on the NEXT planning turn contains at
least 2 probes within Chebyshev-4 of the broadcast coord, AND a
drop move on that same turn inside one of those probe disks (a
hot-drop, not a next-night hedge).

### 6. Cross-harvester deconfliction pass

**Current v3 behaviour:** each harvester's chain is planned
independently in the LLM's response. On concentrated targets like a
redsign cluster this produces overlap — e.g. day 7 of the 2p run,
harvester_p1_2 stepped onto (3,12) at H06, already synthetic-green
from harvester_p1's H02 harvest. 3-5 wasted hours across the two
follow-on harvesters.

**V4 direction:** add a "harvester ownership" section to the
response schema that forces the LLM to declare cell partitions
before emitting moves:

```
"harvester_ownership": {
  "harvester_p1":   [[3,13],[2,13]],
  "harvester_p1_2": [[4,11],[4,10],[3,10]],
  "harvester_p1_3": [[5,9],[5,10]]
}
```

Then move-emission is constrained by this partition. Could also be
enforced structurally in the harness (post-parse, deduplicate any
cell that appears in more than one chain).

**How to know it worked:** on multi-harvester nights, the set of
cells harvested across all p1 units contains zero duplicates. Verify
via `SOC_REPLAY_FRAME` — count unique cells across harvest events
by seat + day.

---

## 2026-07 — Probe doctrine

### 1. Final-night probe repurpose: use probes to BLIND the opponent

**Current v3 behaviour:** on day N (final night) the agent correctly
reasons "a probe here reveals red I can't harvest before dawn — skip
probing." Observed verbatim in the session
`e85f08c16b4844229d002be8c56e87c1` day 7 response:

> "Do NOT probe. A probe on night 7 (final night) is wasted — the
> revealed cells won't exist tomorrow."

This is CORRECT under the current model of "probe = my vision only."

**V4 direction:** probes are also PUBLIC intel — every seat sees the
probe's own position via `station_intel` even though the disk's
contents are private. Dropping a probe near an OPPONENT'S known
cluster forces them to burn hours dealing with the intrusion or
crashes their EMP planning. On the final night specifically, an
otherwise-wasted probe becomes a BLIND / DENIAL weapon:

  * Probe on a cell the opponent is expected to drop into next hour →
    they see a friendly-visible marker there and reroute.
  * Probe adjacent to their harvester's likely chain → forces them
    to consider probe-crush costs mid-chain.
  * Probe at their bluesign lock → contests it or forces an EMP
    response we can now anticipate.

**How to know it worked:** on final nights with `probe_stock >= 1`
and `competitor_intel.active_units > 0`, the v4 agent submits at
least one probe adjacent to a known opponent unit. Verify in
`SOC_AGENT_INVOCATION` that final-night responses include
`{"a":"probe", ...}` moves that map near opponent positions.

### 2. Aggressive probing as a first-order tactical primitive

**HEADLINE DATA POINT (2p seed=42 run,
session `0ff6fc015189472e8d41b5fb9970ce3b`):**
  * TABULA_V3 launched **7 probes** over 7 nights
  * Heuristic RED_HARVEST launched **18 probes** over the same 7 nights
  * The agent probes at 39% of the deterministic baseline's rate. This
    is the single biggest gap between the LLM agent and the heuristic,
    and it compounds every night — fewer probes → less revealed fog
    → fewer harvestable cells → smaller chains → lower score.

**Current v3 behaviour:** the "USE MULTIPLE PROBES per night" line
in `strategies.py` was added late in v3 dev after the agent kept
launching only 1 probe per night. The advisory tone remains soft
("if possible"), and haiku still under-probes when there's fog +
stock available.

**V4 direction:** treat probing as a MANDATE, not advice. Bake
concrete thresholds into the doctrine block AND enforce them
structurally in the harness:

  * Doctrine: `probe_stock >= 2 AND fog_count > 300` → SHOULD launch
    2+ probes. Present as a first-class MANDATE section, not buried
    in prose.

  * Structural: if the LLM's plan doesn't include a probe and the
    thresholds above are met, the harness auto-prepends one at the
    top compiler candidate. Same pattern as the "auto-launch on
    setup night" advisory but generalised across the season. Match
    the heuristic's ~2.5 probes/night rate as a floor.

**Why it matters:** every under-probed night is a compounding loss.
Fog that isn't cleared on night N stays fog on night N+1, which
means the LLM has fewer red cells to reason about, which means
smaller chains, which means less bank, which means the run
converges on the same 400-700 pt ceiling we've been hitting.

**How to know it worked:** on solo `seed=42, days=7` runs, probes
deployed across the season goes from 2-5 (v3) to 8-12 (v4). On 2p
runs against RED_HARVEST, the LLM's probe count is within 20% of
the heuristic's (~15-18 for a 7-night season). Vault score ceiling
correspondingly lifts.

### 3. Probe-history in memory replay

**Current v3 behaviour:** `probe_hints.py` filters out cells within
5 tiles of ANY historical probe (active or expired) — but this is
harness-side only. The LLM's memory block only shows the last 3
turns; older probe launches disappear from what haiku sees.

**V4 direction:** add a persistent `probe_deploy_history` field to
the STATE block listing every probe cell this season with its
expiry night. Reads directly from `_SNAPSHOTS.moves_by_day`. Lets
haiku reason about coverage decay without pulling from stale
memory.

**How to know it worked:** SOC_AGENT_INVOCATION prompts on days 4+
contain the full probe history and haiku's `plan_this_turn`
references past probe positions explicitly ("probe_p1_1 at (7,4)
expired last night, launching replacement…").
