# Building and shipping your agent

Everything you need for the day, in the order you need it. If you read
one section, read [Publishing](#5-publishing-your-agent) — it is what
gets you into the league.

---

## 1. Mint your agent

```bash
python scripts/soc.py new --team redwatch --name reaper \
    --participants "Ada Lovelace, Grace Hopper"
```

That forks the shipped V12 harness into
`sea_of_colours/orchestrator_2/harnesses/redwatch_reaper/` and declares
it in an `agent.json` inside that folder.

**All three are required, including the names.** The league table at the
end of the day is the public record of who built what, and a row reading
`redwatch_reaper` and nothing else cannot be credited to anybody or
chased if it breaks. List everyone at the table — real names, handles,
nicknames, whatever you answer to. You can edit the list in your
`agent.json` later when someone joins.

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

**That includes what it buys.** The orbit-phase buying policy is
`orbit_policy.py` *inside your fork* — credits, BLUE, when a weapon is
worth a harvester. It used to be shared code outside every harness,
which meant changing it was a change to the kit and `soc push` would
refuse it. Since v1.40 each agent owns its own, so "buy an EMP the first
day I can afford one" is a change to one file in your own directory.
Every fork starts with a copy that behaves exactly like V12's, so any
difference in what your agent buys is a difference you chose.

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
   largest single scoring opportunity in the kit. See
   [the four rungs](#the-four-rungs-of-firing-a-weapon) below.
2. **Its plan menu cannot express some correct plays.** Several boards
   were captured precisely because the agent's own reasoning found the
   right answer and the option list had no way to say it. `soc why
   <board>` quotes what happened.

### The four rungs of firing a weapon

Gap 1 is the one most teams pick, so it is worth knowing the shape
before you start. Firing needs **four independent things** to be true,
and they have to be built in order, because each is invisible until the
one before it works:

1. **The agent knows it owns a rack.** Today only the buying code reads
   `weapon_stock`; the night phase is never told. It cannot choose a
   weapon it does not know it has.
2. **The play is offerable and compilable.** Three places must agree —
   the move schema has to allow the verb, `agency.py` has to register an
   option that emits it, and the packager has to pass it through.
3. **The offer explains itself.** A menu line of bare geometry is not a
   decision. Say what firing here buys, in human terms: *"3 rival probes
   under 2 clouds — blinds their eye on your pure for 8h."* `Option` has
   `detail` and `rationale` fields waiting for exactly this.
4. **Doctrine says when, and at what tempo.** The shipped doctrine
   teaches surviving EMP and chaff, never using them. An option nobody
   is told to reach for stays unreached.

**This whole job has been done once, on a real fork, and written up.**
[`docs/TEACHING_WEAPONS.md`](TEACHING_WEAPONS.md) walks all four rungs
with every file named — the schema change that silently kills the play
if you miss it, the shaped salvo that leaves a hole you can stand in,
the orbit bug that left the rack empty with the blue already banked, and
what happened when it ran. Read it before starting; it will save you the
afternoon.

Its headline finding is worth having in advance: **building all four
rungs does not make an agent fire.** At the end of that build the menu
offered the salvo, the doctrine argued for it, and the model still chose
a harvest chain three times out of three. The four rungs get you to the
point where firing is *possible and reasoned about*. Making it actually
happen is a separate problem — ranking, framing, how the cost is
quoted — and you cannot start on it until the rungs are done.

You do not have to track that by hand:

```bash
python scripts/soc.py weapons --agent redwatch_reaper
```

prints the ladder, marks each rung, and names the single next action. It
reads your fork's source, so it needs no model and no credentials and
runs instantly.

**This is the split worth internalising.** Rungs 1–3 are *code* — make
the move possible, and compute where to aim. Rung 4 is *doctrine* —
prose telling the model when firing beats harvesting. Skip the code and
the model wants to fire but has no verb to say it with. Skip the
doctrine and the option sits in the menu, never chosen. When a play
never happens, check in that order: was the **option** offered, could
the **schema** express it, did the **packager** survive it. Only after
those three is it actually the model's judgement.

---

## 3. Score it

```bash
python scripts/soc.py suite --agent redwatch_reaper --runs 3
```

Ten boards, escalating rungs, offline. Then, on anything that failed:

```bash
python scripts/soc.py why crowded_echo_seam redwatch_reaper
```

which prints the question, the canonical play, every move your agent
made against every check — and then **stock V12's own orders on the same
battle**, so you can read the two side by side and see exactly what it
did differently. That comparison comes from a frozen run checked into
[`evals/battles/baseline/`](../sea_of_colours/evals/battles/baseline/README.md),
so it needs no credentials and no waiting.

### Nine jackpot nights and one ordinary one

Nine of the ten boards are redsign nights — a pure is on the table and
the decision is hard. The tenth, **`plain_night_armed`**, is the control
group: no pure, no sign, nothing dramatic, an ordinary working seam with
ordnance in the rack. It is there because an agent that only performs on
jackpot nights is not actually good, and because it is the one board
that asks what your agent does with a weapon when there is no jackpot to
justify it.

Nothing on that board scores weapon use, deliberately. If you told your
agent "charges are for redsign nights only", silence there is the
correct result and you have just proved your doctrine works. If you did
not tell it anything, silence means the rack is decoration. The ORDNANCE
section of the report tells you which battles were armed and silent; the
reading is yours.

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

## 4. Watch the turn back

A score tells you *that* a board went wrong. To see why, record the run
and open the battle room:

```bash
python scripts/soc.py suite --agent redwatch_reaper --runs 3 --record
open reports/battles/index.html      # or http://127.0.0.1:8000/battles/
```

Every turn in the run is replayable. Pick a board on the left, and you
get the position your agent was looking at with a transport under it —
step through hour by hour, or press play and watch the night. `FOG`
swaps ground truth for what your seat could actually see when it
planned, which matters more than it sounds: plenty of "bad" plays are an
agent behaving sensibly on information it did not have.

Down the right is the card, in the order you should debug in:

1. **Situation** and **the canonical play** — what was asked, and what a
   good house does here.
2. **Scored *n*%** — every predicate, with the reason it failed.
3. **Orders issued** — what actually reached the engine. Click a line to
   jump the board to that hour.
4. **Corrections** — where the compiler rewrote or dropped an order.
5. **Options** — the menu it chose from, and what it picked.
6. **Reasoning**, then **the prompt it was given**, verbatim.

That order is the debugging order, and it is worth following even when
you are sure you know the answer. A bad play with sound reasoning is a
**compiler** problem. Sound reasoning off a bad menu is an **options**
problem. Only when the menu and the prompt are both right is the model
itself worth blaming. Check the menu before you blame the model.

**Bakes stack up.** The `BAKE` dropdown lists every recorded run, newest
first, so the real loop is: record, watch, change one thing in your
fork, record again, then open the same board in both bakes and see
whether the change did what you meant. That comparison is the whole
point of the room.

---

## 5. Play a whole season

The suite and the room are for one night at a time. They will not tell
you whether your agent can hold a **season** together — bank early
enough, buy the right thing on day two, still be scoring on the last
night. An agent can play every individual night well and still finish
last, and the only way to find that out is to play the whole thing:

```bash
python scripts/soc.py season --p1 redwatch_reaper --p2 red_harvest
```

Pick whoever you like for the other seats — another fork, stock
`tabula_v12`, `red_harvest_lite` for an easier opponent, up to `--p4`.
It runs offline and prints the result:

```
  Aurum_Vallis  (8f2c19a4…)
  5/5 days  ·  22 turns  ·  41.3s

    p1   redwatch_reaper           2043  <- winner
    p2   red_harvest               1622
```

Two things come out of it.

**The season is in your replays.** It is written through the same store
the live server reads, so start the server and watch it back exactly
like a game you played by hand — the whole night, hour by hour, both
seats:

```bash
SOC_BACKEND=file python run_web.py
# then open the URL the command printed
```

`SOC_BACKEND=file` matters. A bare `python run_web.py` auto-detects,
which on most laptops means the in-memory store — and an in-memory
server cannot see a season on disk, so your replay list comes up empty
and it looks like the season was never written. The `soc season` output
prints the exact command to use.

**Every turn's card is kept.** One Markdown file per turn under
`reports/seasons/<season>/cards/`, plus an `all-cards.md` with the lot
in play order. Orbit and night are separate files, because buying is
half the game and a season lost on day two is usually lost in orbit.
Each card has the rationale, the orders, the option menu, what the model
said and the prompt it was given — the same things the battle room
shows, in a form you can read in an editor or paste to a coding agent
and ask what went wrong.

The same cards also come out as **`all-cards.html`**: one page with a
day rail down the side and a coloured tab per section, so finding "day
three, p1, what was it offered" is two clicks instead of scrolling
1,400 lines. Use whichever suits the reader — the HTML for you, the
Markdown for your coding agent, which does much better with plain text.
Both are rendered from the same data, so they cannot disagree.

You can also pull the cards from a game you played in the browser: the
AGENT tab has **`[ READ ]`** (opens the HTML in a new tab) and
**`[ .MD ]`** (downloads the Markdown).

A few flags worth knowing:

| flag | what it does |
|---|---|
| `--seed N` | same board every time — the way to compare two versions of your agent |
| `--days N` | shorter season while iterating |
| `--p3` / `--p4` | more seats |
| `--backend memory` | fastest, keeps nothing, not replayable |
| `--json` | machine-readable result |

**A season with an LLM seat takes real minutes**, since every seat calls
a model every night. Use the suite for the fast loop and a season to
confirm the change held up. If the run reports turns that *fell back*,
your agent never reached its model and that part of the season is the
built-in heuristic, not you — check `soc doctor`.

---

## 6. Publishing your agent

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

**Racing another team is normal and handled.** Forty people push to one
branch, so most pushes lose a race with somebody. When that happens
`soc push` rebases onto whatever landed first and pushes again, and says
so while it does it. You do not need to `git pull` yourself, and you
must never `--force`: your commit is never at risk, because the rebase
cannot conflict — two teams never write the same file. That is the
one-directory rule paying for itself rather than just being a rule.

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

## 7. The league

At the end of the day every discovered agent is run over the same boards
at the same rungs:

```bash
python scripts/soc.py league --runs 3 --up-to siege --cards reports/league
```

The entrant list is simply every directory with an `agent.json`, which
is exactly why registration stopped being a shared file: nobody can be
left out because a merge went wrong.

A broken entrant cannot take the league down with it. A manifest that
will not parse is skipped with a warning naming the file and the error;
an agent whose code will not import runs, fails and scores 0% rather
than aborting the run. Check you are not that entrant with `soc doctor`,
which lists the same problems before the day ends rather than after.

Agents whose harness never reached a model are marked with `*` and their
fallback rate is printed. They still appear — a silently missing entrant
is worse than a marked one — but the table says plainly that the score
is partly the safety net's.

---

## Command reference

| command | what it does |
|---|---|
| `soc new --team T --name N --participants "..."` | fork V12 into your own agent |
| `soc list` | boards, rungs, loadouts, and every registered agent |
| `soc suite --agent A` | score an agent against the battles |
| `soc suite --agent A --record` | ...and freeze every turn for the battle room |
| `soc why BOARD [AGENT]` | explain a board, and optionally play it |
| `soc weapons --agent A` | which of the four firing rungs you are stuck on |
| `soc doctor` | check the kit before blaming your agent |
| `soc push` | publish your agent (your folder only) |
| `soc league` | run every submitted agent and rank them |

Every command takes `--help`, and `soc` on its own lists them all.
