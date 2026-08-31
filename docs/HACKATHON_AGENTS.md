# Building and shipping your agent

Everything you need for the day, in the order you need it. If you read
one section, read [Publishing](#4-publishing-your-agent) — it is what
gets you into the league.

---

## 1. Mint your agent

```bash
python scripts/soc.py new --team redwatch --name reaper
```

That forks the shipped V12 harness into
`sea_of_colours/orchestrator_2/harnesses/redwatch_reaper/` and declares
it in an `agent.json` inside that folder.

**Your agent is one directory.** Nothing outside it was touched, and
nothing outside it needs to change again — not a registry, not a config,
not the UI. That is deliberate: it is what lets the whole room push to
one repo without conflicting, and what makes the end-of-day league a
directory scan rather than forty merges.

Restart the server and your agent is in the New Game dropdown.

> **Do not edit `tabula_v12` itself.** It is the baseline every fork is
> measured against, and it is the control group for the whole room. Take
> its label and every comparison on the day becomes meaningless — which
> is why the tooling refuses to let you.

---

## 2. Improve it

Your fork is a complete copy of V12, so everything is yours to change.
Its own `README.md` is the tour: the pipeline, the two gaps it ships
with on purpose, and where to change what.

Most people will do this through a coding assistant rather than by hand.
That works well, and the kit is built for it — but point the assistant
at the fork's README first, and give it something concrete to aim at:

> "Read `harnesses/redwatch_reaper/README.md`. Then run
> `python scripts/soc.py suite --agent redwatch_reaper --runs 3` and fix
> the predicate that fails most often."

### The two gaps worth knowing about

Stock V12 ships with two deliberate holes. They are the exercise:

1. **It buys weapons and never fires them.** Run
   `soc suite --loadout empty,both` and compare. If the two scores are
   identical, your agent has not learned to fight — and that is the
   largest single scoring opportunity in the kit.
2. **Its plan menu cannot express some correct plays.** Several boards
   were captured precisely because the agent's own reasoning found the
   right answer and the option list had no way to say it. `soc why
   <board>` quotes what happened.

---

## 3. Score it

```bash
python scripts/soc.py suite --agent redwatch_reaper --runs 3
```

Nine boards, escalating rungs, offline. Then, on anything that failed:

```bash
python scripts/soc.py why crowded_echo_seam redwatch_reaper
```

which prints the question, the canonical play, what stock V12 did, and
every move your agent made against every check.

See [the suite's README](../sea_of_colours/evals/battles/README.md) for
the rungs, the loadouts, and how scoring works.

Two things to be careful about:

- **Use `--runs 3` or more.** An LLM is not deterministic, and a board
  it passes three times in five is a board it does not understand. That
  distinction is invisible at `--runs 1`.
- **Watch for the fallback warning.** If your harness cannot reach its
  model it plays a built-in safety net, and that score is not yours. The
  report says so in a box you cannot miss.

If something looks wrong with the kit rather than your agent:

```bash
python scripts/soc.py doctor
```

---

## 4. Publishing your agent

**Push early and push often.** The league at the end of the day is built
from whatever is in the repo, so an agent that only exists on your
laptop does not compete.

```bash
python scripts/soc.py push
```

That commits **your agent's directory and nothing else**, then pushes.
Run it as many times as you like — every improvement, every hour, it
does not matter. There is no submission deadline ritual and no form to
fill in; the last thing you pushed is what plays.

### Why it refuses sometimes

If you have changed files outside your own folder, `push` stops and
lists them:

```
error: changes outside sea_of_colours/orchestrator_2/harnesses/redwatch_reaper/:
  server/static/app.js
```

This is the one rule the day depends on. Forty teams share this repo; if
everyone's changes stay inside their own directory then nobody's push
can break anybody else's agent, and no two pushes can conflict. Move
what you need into your folder, revert the rest with
`git checkout -- <path>`, and push again.

If you genuinely need a change outside your folder, that is a change to
the *kit* rather than to your agent — flag it to an organiser rather
than forcing it in.

### Checking you are in

```bash
python scripts/soc.py list      # your agent should be under AGENTS
python scripts/soc.py doctor    # and report no problems
```

---

## 5. The league

At the end of the day every discovered agent is run over the same boards
at the same rungs:

```bash
python scripts/soc.py league --runs 3 --up-to siege --cards reports/league
```

The entrant list is simply every directory with an `agent.json`, which
is exactly why registration stopped being a shared file: nobody can be
left out because a merge went wrong.

Agents whose harness never reached a model are marked with `*` and their
fallback rate is printed. They still appear — a silently missing entrant
is worse than a marked one — but the table says plainly that the score
is partly the safety net's.

---

## Command reference

| command | what it does |
|---|---|
| `soc new --team T --name N` | fork V12 into your own agent |
| `soc list` | boards, rungs, loadouts, and every registered agent |
| `soc suite --agent A` | score an agent against the battles |
| `soc why BOARD [AGENT]` | explain a board, and optionally play it |
| `soc doctor` | check the kit before blaming your agent |
| `soc push` | publish your agent (your folder only) |
| `soc league` | run every submitted agent and rank them |

Every command takes `--help`, and `soc` on its own lists them all.
