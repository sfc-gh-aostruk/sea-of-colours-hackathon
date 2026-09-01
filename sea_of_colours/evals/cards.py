"""Render an agent's turn as Markdown.

One renderer, two callers, because the same card is wanted in two
places and they hold it in different shapes:

* the server, from a persisted ``SOC_AGENT_INVOCATION`` row, so the
  AGENT tab's download button works for any season anyone has played;
* the headless season runner, from the harness envelope it has in hand,
  which additionally carries the structured extras the invocation row
  has no column for.

:func:`normalise` flattens both into one dict so the renderers only have
to know about the union. There are two, over the same normalised card,
because the audience splits:

* :func:`render` / :func:`render_many` — **Markdown**, for an LLM being
  asked why a turn went wrong. This is the format an attendee pastes
  into their coding agent, so it stays the primary artefact.
* :func:`render_html` — **HTML**, for the person reading it themselves:
  a day rail, section tabs and colour, because a season is ~1,400 lines
  of Markdown and scrolling that to find "day 3, p1, what was it
  offered" is miserable.
"""

from __future__ import annotations

import html
import json
import re
from typing import Any, Iterable, Mapping

#: Extras worth printing, in the order a reader wants them: what it was
#: told, what it thought, what it chose, what survived.
#:
#: The third element is the fence's language tag. Markdown has no colour
#: of its own, so the only portable way to tell sections apart at a
#: glance is to let the reader's syntax highlighter do it — ``json`` for
#: the structured decisions, ``ini`` because the option menu's ``[GRAB1]``
#: ids highlight as section headers, ``diff`` for anything that is a
#: before/after. A card is ~1,400 lines; without this it is a wall.
_EXTRA_SECTIONS: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("Plan directive", ("thinker_directive",), "json"),
    ("Options offered", ("option_menu_block",), "ini"),
    ("Options chosen", ("selected_option_ids",), "json"),
    ("Predicted outcome", ("predicted_outcome",), "json"),
)


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, Mapping) or isinstance(value, (list, tuple)):
        return json.dumps(value, indent=1, default=str)
    return str(value)


def _first(src: Mapping[str, Any], names: Iterable[str]) -> Any:
    for name in names:
        val = src.get(name)
        if val not in (None, "", [], {}):
            return val
    return None


def _fence(body: str, lang: str = "") -> list[str]:
    """Fence ``body`` with enough backticks to survive its own content.

    Prompts and model replies routinely contain fenced blocks of their
    own, and a plain three-tick fence around them ends early — the rest
    of the card then renders as prose and the *next* section's heading
    looks like it belongs to the model. Widen the fence past the longest
    run inside instead.
    """
    longest = max((len(m) for m in re.findall(r"`+", body)), default=0)
    ticks = "`" * max(3, longest + 1)
    return [f"{ticks}{lang}", body, ticks]


def _fmt_move(move: Any) -> str:
    """One engine order, readable.

    Moves reach us as ``{"a": "step", "unit": "harvester_p1", "at": [19, 16]}``
    and a card full of raw dicts is unreadable at the exact moment you
    need it — when you are checking what the engine was actually asked
    to do versus what the agent thought it asked for.
    """
    if not isinstance(move, Mapping):
        return _text(move)
    known = {"a", "action", "unit", "id", "at", "to"}
    bits = [str(_first(move, ("a", "action")) or "?")]
    unit = _first(move, ("unit", "id"))
    if unit:
        bits.append(str(unit))
    at = _first(move, ("at", "to"))
    if isinstance(at, (list, tuple)) and len(at) == 2:
        bits.append(f"({at[0]},{at[1]})")
    elif at:
        bits.append(_text(at))
    rest = {k: v for k, v in move.items() if k not in known}
    line = " ".join(bits)
    if rest:
        line += "  " + ", ".join(f"{k}={v}" for k, v in rest.items())
    return line


def _demote_headings(md: str) -> str:
    """Push every heading down one level, ignoring fenced content.

    Only headings *outside* a fence are the card's own. The model writes
    its own markdown — ``# THINK PASS`` — and that lives inside a fence;
    demoting it there would corrupt the block, and leaving it undemoted
    once a fence breaks makes it masquerade as a turn.
    """
    out: list[str] = []
    fence: str | None = None
    for line in md.split("\n"):
        opener = re.match(r"^(`{3,})", line)
        if opener:
            tag = opener.group(1)
            if fence is None:
                fence = tag
            elif line.strip() == fence:
                fence = None
            out.append(line)
            continue
        if fence is None and re.match(r"^#+ ", line):
            line = "#" + line
        out.append(line)
    return "\n".join(out)


def normalise(
    row: Mapping[str, Any] | None = None,
    *,
    envelope: Mapping[str, Any] | None = None,
    season: str = "",
    session_id: str = "",
    day: int | None = None,
    player: str = "",
    agent: str = "",
    phase: str = "",
) -> dict:
    """Flatten a store row and/or a harness envelope into one card.

    Both are optional and either can fill a gap in the other: the row
    is what survives in the database, the envelope is what the harness
    actually returned this turn.
    """
    row = row or {}
    env = envelope or {}
    extras = env.get("extras")
    extras = extras if isinstance(extras, Mapping) else {}

    return {
        "season": season,
        "session_id": session_id or row.get("session_id") or "",
        "day": row.get("day") if day is None else day,
        "phase": phase or row.get("phase") or "",
        "player": player or row.get("player") or "",
        "agent": agent or row.get("agent_id") or "",
        "runtime": row.get("runtime") or "",
        "ms_elapsed": row.get("ms_elapsed"),
        "status": row.get("status") or "",
        "rationale": _first(row, ("rationale",))
        or _first(env, ("rationale", "agent_rationale"))
        or "",
        "prompt": _first(row, ("prompt_excerpt", "prompt"))
        or _first(extras, ("thinker_prompt", "plan_prompt"))
        or "",
        "response": _first(row, ("response_text",))
        or _first(extras, ("thinker_reasoning",))
        or _first(env, ("response",))
        or "",
        "tool_calls": row.get("tool_calls") or [],
        "extras": dict(extras),
        # ``orchestrator_2.runtime`` does not copy the harness's top-level
        # ``moves`` into the envelope it returns, so for every LLM seat
        # the only surviving copy is ``extras.final_moves`` — which is why
        # LLM cards showed the reasoning but never the orders it produced.
        # The heuristic runtime does pass ``moves``, hence both spellings.
        "moves": _first(env, ("moves",))
        or _first(extras, ("final_moves",))
        or [],
        # What the harness changed after the model spoke. Empty on a clean
        # turn; when it is not, it is usually the whole explanation for a
        # card whose reasoning looks right and whose result does not.
        "corrections": _first(extras, ("sanitizer_changes",)) or [],
        "fallback_reason": (
            _first(extras, ("fallback_reason",))
            if extras.get("fallback_used")
            else None
        ),
    }


def render(card: Mapping[str, Any]) -> str:
    """One turn as Markdown."""
    head = f"{card.get('player') or '?'} — day {card.get('day') or '?'}"
    if card.get("phase"):
        head += f" ({card['phase']})"
    out: list[str] = [f"# {head}", ""]

    facts = [
        ("season", card.get("season")),
        ("session", card.get("session_id")),
        ("agent", card.get("agent")),
        ("runtime", card.get("runtime")),
        ("took", f"{card['ms_elapsed']}ms" if card.get("ms_elapsed") else None),
        ("status", card.get("status")),
    ]
    for key, val in facts:
        if val:
            out.append(f"- **{key}**: {val}")
    out.append("")

    if card.get("rationale"):
        out += ["## Rationale", "", _text(card["rationale"]), ""]

    # ``diff`` so every order renders green: these are the moves that
    # survived to the engine, and they read against the Corrections
    # block below, which shows what did not.
    moves = card.get("moves") or []
    if moves:
        body = "\n".join(
            f"+ {i:2d}. {_fmt_move(m)}" for i, m in enumerate(moves, 1)
        )
        out += [f"## Orders issued ({len(moves)})", ""]
        out += _fence(body, "diff")
        out.append("")

    corrections = card.get("corrections") or []
    if corrections or card.get("fallback_reason"):
        lines = [f"- {_text(c)}" for c in corrections]
        if card.get("fallback_reason"):
            lines.append(f"! FELL BACK: {_text(card['fallback_reason'])}")
        out += [f"## Corrections ({len(corrections)})", ""]
        out += _fence("\n".join(lines), "diff")
        out.append("")

    extras = card.get("extras") or {}
    for title, names, lang in _EXTRA_SECTIONS:
        val = _first(extras, names)
        if val:
            out += [f"## {title}", ""]
            out += _fence(_text(val), lang)
            out.append("")

    if card.get("response"):
        out += ["## What the model said", ""]
        out += _fence(_text(card["response"]), "markdown")
        out.append("")

    if card.get("tool_calls"):
        out += ["## Tool calls", ""]
        out += _fence(_text(card["tool_calls"]), "json")
        out.append("")

    # Last, and fenced: it is the longest thing here by an order of
    # magnitude and almost never the thing you opened the card for.
    if card.get("prompt"):
        out += ["## The prompt it was given", ""]
        out += _fence(_text(card["prompt"]), "text")
        out.append("")

    if len(out) <= 3:
        out.append("_This turn recorded no card. A heuristic seat has no "
                   "prompt and no reasoning — only the orders it played._")

    return "\n".join(out).rstrip() + "\n"


def render_many(cards: Iterable[Mapping[str, Any]], *, title: str = "") -> str:
    """A whole season's cards in one file, in play order."""
    cards = list(cards)
    out: list[str] = []
    if title:
        out += [f"# {title}", "", f"{len(cards)} recorded turn(s).", "", "---", ""]
    for card in cards:
        # Every heading demoted one level so the per-turn cards nest
        # under the title instead of competing with it — but only the
        # card's own headings, never the model's markdown inside a fence.
        out.append(_demote_headings(render(card)))
        out += ["", "---", ""]
    return ("\n".join(out)).rstrip() + "\n"


def filename(card: Mapping[str, Any], ext: str = "md") -> str:
    """A sortable, filesystem-safe name for one turn's card.

    The phase is part of the name because a seat plans twice on most
    days — orbit and night — and without it the night card silently
    overwrites the buying card, which is half the game.
    """
    day = card.get("day")
    day_s = f"d{int(day):02d}" if isinstance(day, int) else "dXX"
    seat = "".join(
        c for c in str(card.get("player") or "seat") if c.isalnum()
    ) or "seat"
    phase = "".join(
        c for c in str(card.get("phase") or "") if c.isalnum() or c == "_"
    )
    return f"{day_s}_{seat}{('_' + phase) if phase else ''}.{ext}"


# ── HTML view ───────────────────────────────────────────────────────────
#
# Same cards, different reader. Markdown is what you paste into a model
# when you want help fixing your agent; HTML is what you read yourself
# when you want "day 3, p1, what was it offered". A season is ~1,400
# lines of Markdown and scrolling it to answer that is miserable.
#
# Both come out of :func:`normalise`, so the two views cannot disagree.

#: Colour per section kind. Keys are CSS-safe and used verbatim as class
#: suffixes. The point is that a card is skimmable — orders green because
#: they are what reached the engine, corrections amber because they are
#: what did not.
_KINDS = {
    "rationale": "#d8d3c4",
    "orders": "#5fd77a",
    "corrections": "#e8a33d",
    "directive": "#54c8e8",
    "offered": "#7f9fe0",
    "chosen": "#5fd77a",
    "predicted": "#c08ae0",
    "response": "#b9b3a4",
    "tools": "#54c8e8",
    "prompt": "#7d776a",
}

#: Which extras map to which colour. Keyed by the title in
#: :data:`_EXTRA_SECTIONS` so the two lists cannot drift apart silently.
_EXTRA_KINDS = {
    "Plan directive": "directive",
    "Options offered": "offered",
    "Options chosen": "chosen",
    "Predicted outcome": "predicted",
}


def _html_sections(card: Mapping[str, Any]) -> list[dict]:
    """The card's sections as data, in the order a reader wants them."""
    out: list[dict] = []

    def add(title: str, kind: str, body: Any) -> None:
        text = _text(body).strip()
        if text:
            out.append({"title": title, "kind": kind, "body": text})

    add("Rationale", "rationale", card.get("rationale"))

    moves = card.get("moves") or []
    if moves:
        add(
            f"Orders ({len(moves)})", "orders",
            "\n".join(
                f"{i:2d}.  {_fmt_move(m)}" for i, m in enumerate(moves, 1)
            ),
        )

    corrections = card.get("corrections") or []
    if corrections or card.get("fallback_reason"):
        lines = [f"• {_text(c)}" for c in corrections]
        if card.get("fallback_reason"):
            lines.append(f"! FELL BACK: {_text(card['fallback_reason'])}")
        add(f"Corrections ({len(corrections)})", "corrections",
            "\n".join(lines))

    extras = card.get("extras") or {}
    for title, names, _lang in _EXTRA_SECTIONS:
        add(title, _EXTRA_KINDS.get(title, "response"), _first(extras, names))

    add("Model reply", "response", card.get("response"))
    add("Tool calls", "tools", card.get("tool_calls"))
    # Last: the longest thing here by an order of magnitude and almost
    # never what you opened the card for.
    add("Prompt", "prompt", card.get("prompt"))
    return out


def _turn_payload(card: Mapping[str, Any]) -> dict:
    return {
        "day": card.get("day"),
        "player": card.get("player") or "?",
        "phase": card.get("phase") or "",
        "agent": card.get("agent") or "",
        "runtime": card.get("runtime") or "",
        "ms": card.get("ms_elapsed"),
        "status": card.get("status") or "",
        "sections": _html_sections(card),
    }


def render_html(cards: Iterable[Mapping[str, Any]], *, title: str = "") -> str:
    """A whole season's cards as one self-contained page.

    Self-contained on purpose: these are opened straight off disk out of
    ``reports/seasons/…``, so the data is registered by a ``<script>``
    tag and there is no ``fetch`` anywhere. A fetch cannot work over
    ``file://`` — the same rule the battle room lives by.
    """
    cards = list(cards)
    payload = {
        "title": title or "Agent cards",
        "season": next((c.get("season") for c in cards if c.get("season")), ""),
        "session": next(
            (c.get("session_id") for c in cards if c.get("session_id")), ""
        ),
        "turns": [_turn_payload(c) for c in cards],
    }
    # ``</`` would close the script element early and blank the page.
    blob = json.dumps(payload, default=str).replace("</", "<\\/")
    kind_css = "\n".join(
        f"  .k-{k} {{ --accent: {v}; }}" for k, v in _KINDS.items()
    )
    return (
        _HTML_TEMPLATE
        .replace("/*KINDS*/", kind_css)
        .replace("__TITLE__", html.escape(payload["title"]))
        .replace("__DATA__", blob)
    )


_HTML_TEMPLATE = """<!doctype html>
<meta charset="utf-8">
<title>__TITLE__</title>
<style>
  :root {
    --bg: #0e0f0d; --panel: #161815; --line: #2a2d27;
    --ink: #d8d3c4; --dim: #7d776a; --accent: #5fd77a;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--bg); color: var(--ink);
    font: 13px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace;
    display: grid; grid-template-columns: 250px 1fr; height: 100vh;
  }
/*KINDS*/
  /* ── day rail ── */
  #rail { border-right: 1px solid var(--line); overflow-y: auto; }
  #rail h1 {
    font-size: 12px; letter-spacing: .14em; text-transform: uppercase;
    margin: 0; padding: 14px 12px; color: var(--dim);
    border-bottom: 1px solid var(--line); position: sticky; top: 0;
    background: var(--bg);
  }
  .day { padding: 8px 0 4px; }
  .day > b {
    display: block; padding: 2px 12px; color: var(--dim);
    font-weight: 400; letter-spacing: .1em; font-size: 11px;
  }
  .turn {
    display: block; width: 100%; text-align: left; cursor: pointer;
    background: none; border: 0; border-left: 2px solid transparent;
    color: var(--ink); font: inherit; padding: 5px 12px;
  }
  .turn:hover { background: var(--panel); }
  .turn.on { background: var(--panel); border-left-color: var(--accent); }
  .turn small { color: var(--dim); }
  /* ── main ── */
  #main { overflow-y: auto; display: flex; flex-direction: column; }
  #facts {
    padding: 14px 18px; border-bottom: 1px solid var(--line);
    display: flex; gap: 8px; flex-wrap: wrap; align-items: baseline;
  }
  #facts h2 { margin: 0 10px 0 0; font-size: 15px; }
  .chip {
    border: 1px solid var(--line); border-radius: 2px;
    padding: 1px 7px; color: var(--dim); font-size: 11px;
  }
  #tabs {
    display: flex; gap: 4px; flex-wrap: wrap; padding: 10px 18px;
    border-bottom: 1px solid var(--line); position: sticky; top: 0;
    background: var(--bg); z-index: 2;
  }
  /* Tinted even when inactive: the whole point of the colour is that a
     turn with Corrections on it reads amber before you click anything. */
  .tab {
    cursor: pointer; background: none; font: inherit; color: var(--accent);
    border: 1px solid var(--line); border-radius: 2px; padding: 3px 10px;
    opacity: .6;
  }
  .tab:hover { opacity: 1; }
  .tab.on {
    color: #0e0f0d; background: var(--accent);
    border-color: var(--accent); opacity: 1;
  }
  #body { padding: 16px 18px 60px; }
  #body pre {
    margin: 0; white-space: pre-wrap; word-break: break-word;
    border-left: 2px solid var(--accent); padding: 10px 14px;
    background: var(--panel);
  }
  .empty { color: var(--dim); padding: 24px 18px; }
</style>
<div id="rail"><h1>__TITLE__</h1><div id="days"></div></div>
<div id="main">
  <div id="facts"></div><div id="tabs"></div><div id="body"></div>
</div>
<script id="cards" type="application/json">__DATA__</script>
<script>
(function () {
  var D = JSON.parse(document.getElementById('cards').textContent);
  var turns = D.turns || [];
  var cur = 0, tab = 0;

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  // Rail: grouped by day, one button per seat/phase within it. That
  // grouping IS the navigation — a seat plans twice most days.
  function buildRail() {
    var days = document.getElementById('days'), seen = {};
    turns.forEach(function (t, i) {
      var key = String(t.day);
      if (!seen[key]) {
        var g = el('div', 'day');
        g.appendChild(el('b', null, 'DAY ' + (t.day == null ? '?' : t.day)));
        days.appendChild(g);
        seen[key] = g;
      }
      var b = el('button', 'turn');
      b.appendChild(document.createTextNode(t.player + ' '));
      b.appendChild(el('small', null, t.phase || ''));
      b.onclick = function () { cur = i; tab = 0; draw(); };
      b.dataset.i = i;
      seen[key].appendChild(b);
    });
  }

  function draw() {
    var t = turns[cur];
    Array.prototype.forEach.call(
      document.querySelectorAll('.turn'),
      function (b) { b.classList.toggle('on', +b.dataset.i === cur); }
    );

    var facts = document.getElementById('facts');
    facts.textContent = '';
    if (!t) { facts.appendChild(el('h2', null, 'No turns recorded')); return; }
    facts.appendChild(el('h2', null,
      t.player + ' — day ' + t.day + (t.phase ? ' · ' + t.phase : '')));
    [t.agent, t.runtime, t.ms ? t.ms + 'ms' : '', t.status, D.season]
      .filter(Boolean)
      .forEach(function (v) { facts.appendChild(el('span', 'chip', v)); });

    var tabs = document.getElementById('tabs'), body = document.getElementById('body');
    tabs.textContent = ''; body.textContent = '';
    var secs = t.sections || [];
    if (!secs.length) {
      body.appendChild(el('div', 'empty',
        'This turn recorded no card. A heuristic seat has no prompt and ' +
        'no reasoning — only the orders it played.'));
      return;
    }
    if (tab >= secs.length) tab = 0;
    secs.forEach(function (s, i) {
      var b = el('button', 'tab k-' + s.kind + (i === tab ? ' on' : ''), s.title);
      b.onclick = function () { tab = i; draw(); };
      tabs.appendChild(b);
    });
    var pre = el('pre', null, secs[tab].body);
    pre.className = 'k-' + secs[tab].kind;
    body.appendChild(pre);
  }

  // j/k step through turns; the whole point is fast comparison of the
  // same section across consecutive turns, so the tab is kept.
  document.addEventListener('keydown', function (e) {
    if (e.key === 'j' && cur < turns.length - 1) { cur++; draw(); }
    if (e.key === 'k' && cur > 0) { cur--; draw(); }
  });

  buildRail();
  draw();
})();
</script>
"""
