"""tabula_v8 — the consolidation release (true fork).

v8 owns its FEEDING layer and reuses v7's COMPUTATION layer:

  * :mod:`.harness` — its own turn loop; the contained two-call split
    (reasoning-first thinker + moves-first mover, both on the Cortex
    inference API) is NATIVE and on by default (``TABULA_V8_SINGLE=1``
    reverts to mover-only for A/B).
  * :mod:`.prompt` — the 3-pillar WORLDVIEW restructure (THE GAME /
    THE BOARD NOW / LAST NIGHT) with the new ENEMY PROBES + WEAPON
    GEOMETRY blocks and the collision-aware LAST NIGHT / REFLECT blocks.
  * :mod:`.doctrine` — v7 doctrine + the redsign-poker opening book and the
    weapons-as-orbital-strike reframe.
  * :mod:`.rules` — re-exports v7's frozen engine physics verbatim.

Hint compilers, the move sanitizer, the wishlist, memory, weapon inference
and the recorder are imported from ``tabula_v7`` unchanged.
"""
