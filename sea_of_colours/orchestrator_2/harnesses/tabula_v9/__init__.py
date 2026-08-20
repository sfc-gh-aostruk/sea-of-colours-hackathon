"""tabula_v9 — the COMPREHENSION release (true fork of v8).

v9 keeps v8's contained two-call split + 3-pillar worldview and adds the
layer the v8 audit proved missing: the agent should be able to explain
*why* it lost a probe / a harvest / a night, with attribution and
consequence, and treat contested placement as a deliberate choice.

What v9 owns (its FEEDING layer):
  * :mod:`.digest` — turns the new attributed event channels
    (incoming_attacks / my_denials / emp_scars) into plain causal lines,
    both directions ("to you" and "by you").
  * :mod:`.prompt` — v8's 3-pillar prompt PLUS the two-way WHAT HAPPENED
    digest in SECTION 3, EMP scars as a SECTION 2 hazard, and a REFLECT
    block that FORCES a consequence acknowledgment for probe/EMP/chaff loss.
  * :mod:`.doctrine` — clarity/dedupe rewrite with the two-case
    WEAPON-FREE redsign poker (my-redsign vs not-mine), branching on the
    new engine-truth ``redsign.mine`` flag.
  * :mod:`.rules` — re-exports the frozen engine physics verbatim.
  * :mod:`.harness` — its own turn loop (relabelled TABULA_V9), reusing
    v7's proven COMPUTATION layer (hint compilers, sanitizer, wishlist,
    memory, weapon inference, recorder) by import.

v6/v7/v8 stay frozen. The data/engine/heuristic changes v9 relies on are
additive to shared modules, so the frozen agents are unaffected. The
native-thinking-Sonnet bet is a separate later release (v11).

v9 COMPLETED its objectives (won seed 69 three ways). The executor-faithfulness
follow-on (deterministic packager + anti-crowd, see the audit) is developed in
the fork :mod:`..tabula_v10`; v9 is now frozen as its reference.
"""
