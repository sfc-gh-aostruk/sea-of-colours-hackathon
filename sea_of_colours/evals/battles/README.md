# The redsign battles

Nine nights where a PURE was on the table and the decision was hard,
each one run against five rungs of escalating trouble.

```bash
python scripts/soc.py suite --agent my_agent      # score it
python scripts/soc.py why two_pures_poker         # what was the right play?
python scripts/soc.py why two_pures_poker my_agent  # ...and what did mine do?
```

Everything runs offline on `SOC_BACKEND=memory`. The whole suite is 45
turns in about a second against the heuristic; an LLM agent takes as
long as it takes.

## What is here

| file | what it holds |
|---|---|
| `boards.py` | the nine boards, each with its question, its canonical play in prose, and its predicates |
| `ladder.py` | the five difficulty rungs and the four weapon loadouts |
| `stage.py` | builds a playable night from a board + rung + loadout |
| `predicates.py` | the checks — shape predicates over engine truth |
| `runner.py` | plays a battle N times and scores it |
| `report.py` | renders results, ordered by what to fix |

## The three ideas worth knowing

**The boards are constructed, not restored.** The originals were frozen
Snowflake rows — exact, and useless for this: you cannot run them
without an account, and a frozen blob has exactly one difficulty. These
are rebuilt from their documented geometry, so the dials can move.

**Scoring is by shape, never by a stored move list.** A better line than
the canonical passes; a lucky cell-for-cell match with the ordering
wrong does not. This is why boards ship prose rather than answers.

**The ladder is what stops this being nine memorised boards.** Rungs
change the opposition, not the geometry. Where your agent stops tells
you what to teach it:

| rung | it teaches |
|---|---|
| `quiet` | that a free extension must be taken — here, stopping short is the failure |
| `watched` | tempo: they can land on the pure before you |
| `armed` | that a plan can be cancelled, so value must come first |
| `crowded` | that you do not hold hour one and must go anyway |
| `siege` | whether your agent can actually fight |

The `--loadout` axis is separate and answers a different question. Hold
the rung fixed, hand the agent a full rack, and see whether anything
changes. Stock V12 buys weapons and never fires them, so there is a
known answer to calibrate against.

## Reading a failure

`soc suite` leads with where on the ladder you stopped and which
predicate fails most often — fourteen scattered failures usually have
one cause. Then `soc why <board>` prints the question, the canonical
play, and what stock V12 did on the same board.

Two flags to take seriously:

- **`FLAKY`** — passed some runs, failed others. Usually more
  informative than a clean fail, and invisible at `--runs 1`. Use
  `--runs 3` before believing any result from an LLM agent.
- **the fallback warning** — the harness never reached its model and
  played its safety net. That share of the score is not your agent's.

## Adding a board

Copy the closest entry in `boards.py`, change the geometry, and **write
the canonical in prose first**. A canonical you cannot state in a
sentence is one you do not understand yet, and a predicate written
before the prose tends to encode the implementation you happen to have
rather than the play you want.

Then add the canonical as moves to `CANONICAL` in `tests/test_battles.py`.
That test asserts every board is winnable by its own prescribed play — a
suite nobody can pass is worse than no suite. It is not a formality: it
has already caught a predicate that forbade a probe two boards require,
a check that let a unit hide behind its partner, and a ladder rung that
was easier than the one below it.
