"""tabula — phase-1 harvest-only arena pilot.

The orchestrator sees exactly one public entry point: :func:`.harness.run`.
Everything else in this package is implementation detail.

Phase 1 (this version):
  * Night-only LLM, orbit stubs to empty
  * Predict → act → reflect memory loop
  * Candidates as hints (no scores), agent computes EV itself
  * Python validators reject illegal moves; heuristic fallback on parse/validate failure

Later phases add probes-with-purpose, orbit LLM, blue harvesting, and
denial primitives — each extends this scaffold rather than replacing it.
"""
