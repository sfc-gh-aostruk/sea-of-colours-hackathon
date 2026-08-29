"""Teaching mode: weapons and signs can be switched off (v1.32).

The browser harness (``scripts/_fx_tutorial.py``) covers what a player
SEES. This file covers what the engine ALLOWS, which is the half that
matters if the two ever disagree: a hidden button the engine would have
honoured is a cosmetic bug, but a visible-in-the-rules weapon the
tutorial claims does not exist is a lie the player later has to unlearn.

The other job here is the default. Every assertion about a flag being
off is paired with the same call on an ordinary session, because the
failure mode nobody would notice is teaching mode leaking into a real
season.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from sea_of_colours.game import tutorial as tut
from sea_of_colours.game.session import GameSession


def _sess(**kw) -> GameSession:
    return GameSession.new(20, 14, seed=4242, season_day_cap=3, **kw)


# ── the flags default to the full game ──────────────────────────────────

def test_an_ordinary_session_has_everything_on():
    """The flags are subtractive. Absent means 'the game as written'."""
    s = _sess()
    assert s.weapons_enabled is True
    assert s.signs_enabled is True
    assert s.tutorial == ""


def test_the_flags_survive_a_save_and_load():
    """A tutorial that forgets it is a tutorial after one round-trip is
    worse than no tutorial: the weapons come back mid-season."""
    s = _sess(weapons_enabled=False, signs_enabled=False, tutorial="basic")
    back = GameSession.from_dict(s.to_dict())
    assert back.weapons_enabled is False
    assert back.signs_enabled is False
    assert back.tutorial == "basic"


def test_a_pre_v132_save_loads_with_the_full_game():
    """Sessions written before these keys existed must not load as
    teaching games."""
    raw = _sess().to_dict()
    for key in ("weapons_enabled", "signs_enabled", "tutorial"):
        raw.pop(key, None)
    back = GameSession.from_dict(raw)
    assert back.weapons_enabled is True
    assert back.signs_enabled is True
    assert back.tutorial == ""


# ── weapons_enabled=False refuses, and says why ─────────────────────────

def _buy(s: GameSession, kind: str):
    return s._apply_build_weapon(
        "p1", kind=kind, count=1, blue_cost_each=200, credit_cost_each=250,
        display=kind.upper(),
    )


@pytest.mark.parametrize("kind", ["emp", "chaff"])
def test_weapons_cannot_be_bought_with_weapons_off(kind: str):
    ok, msg = _buy(_sess(weapons_enabled=False), kind)
    assert ok is False
    # Refused by NAME, the v1.13 retirement pattern — a bare False gives
    # an agent nothing to learn from.
    assert "weapons are disabled" in msg.lower()


@pytest.mark.parametrize("kind", ["emp", "chaff"])
def test_a_normal_game_never_refuses_for_that_reason(kind: str):
    """Asserted as negative space on purpose.

    A fresh seat cannot afford an EMP, so demanding success here would
    only be testing the starting wallet. What must hold is that whatever
    the engine says no to, it is not saying 'teaching mode'.
    """
    ok, msg = _buy(_sess(), kind)
    assert ok or "weapons are disabled" not in msg.lower(), msg


def test_emp_launch_is_refused_with_weapons_off():
    s = _sess(weapons_enabled=False)
    s.weapon_stock.setdefault("p1", {})["emp"] = 5
    ok, msg = s.apply_emp_launch("p1", 5, 5, hour=1)
    assert ok is False
    assert "weapons are disabled" in msg.lower()


def test_chaff_is_refused_with_weapons_off():
    s = _sess(weapons_enabled=False)
    s.weapon_stock.setdefault("p1", {})["chaff"] = 5
    ok, msg = s.apply_chaff_flare("p1", hour=1)
    assert ok is False
    assert "weapons are disabled" in msg.lower()


def test_stock_alone_does_not_re_enable_a_launch():
    """Belt and braces: the guard is on the ACTION, not on the wallet.

    A migrated save, a fixture or a future refund could put ammunition
    in a teaching session's stock; that must still not be firable.
    """
    s = _sess(weapons_enabled=False)
    s.weapon_stock.setdefault("p1", {}).update({"emp": 9, "chaff": 9})
    assert s.apply_emp_launch("p1", 4, 4, hour=1)[0] is False
    assert s.apply_chaff_flare("p1", hour=1)[0] is False
    assert s.weapon_stock["p1"]["emp"] == 9, "a refused launch must not bill"


# ── signs_enabled=False removes the layer, not just its contents ────────

def test_no_blue_sign_is_computed_with_signs_off():
    s = _sess(signs_enabled=False)
    assert s._compute_blue_sign() == []


def _a_pure_cell(s: GameSession):
    from sea_of_colours.game.session import Tile

    for y, row in enumerate(s.grid):
        for x, c in enumerate(row):
            if c.tile == Tile.RED and c.purity >= 255:
                return x, y
    pytest.skip("no pure-RED cell on this board — nothing to discover")


def test_no_redsign_is_registered_with_signs_off():
    s = _sess(signs_enabled=False)
    x, y = _a_pure_cell(s)
    s._register_redsign({(x, y): "p1"})
    assert s.redsign == []


def test_signs_off_does_not_SPEND_the_discovery():
    """The subtle half, and the reason the guard sits above the
    bookkeeping rather than below it.

    Marking the seam seen and then returning early would look identical
    today and be a real bug tomorrow: a save made in teaching mode, or a
    preset flipped mid-development, would come back with its jackpots
    already 'discovered' and no beacon would ever mint for them.
    """
    s = _sess(signs_enabled=False)
    x, y = _a_pure_cell(s)
    s._register_redsign({(x, y): "p1"})
    assert not s.redsign_seen


def test_the_same_discovery_does_mint_in_a_normal_game():
    """Pins the test above to the flag rather than to an inert board."""
    s = _sess()
    x, y = _a_pure_cell(s)
    s._register_redsign({(x, y): "p1"})
    assert s.redsign, "signs on but no beacon minted for a pure seam"
    assert s.redsign_seen


# ── the presets ─────────────────────────────────────────────────────────

def test_basic_is_the_reduced_ruleset():
    cfg = tut.preset_config("basic")
    assert cfg["weapons_enabled"] is False
    assert cfg["signs_enabled"] is False
    assert cfg["season_day_cap"] == 3
    assert (cfg["width"], cfg["height"]) == (24, 16)


def test_advanced_is_basic_sized_with_the_full_rules():
    """The second run's whole point is the same board, more game."""
    basic, adv = tut.preset_config("basic"), tut.preset_config("advanced")
    assert (adv["width"], adv["height"]) == (basic["width"], basic["height"])
    assert adv["weapons_enabled"] is True
    assert adv["signs_enabled"] is True


def test_quick_does_not_shrink_the_board():
    """Quick is a short real season, not a tutorial — it must not
    inherit the teaching board."""
    cfg = tut.preset_config("quick")
    assert "width" not in cfg and "height" not in cfg
    assert cfg["season_day_cap"] == 3


def test_quick_is_not_a_teaching_game():
    assert tut.is_teaching("quick") is False
    assert tut.is_teaching("basic") is True
    assert tut.is_teaching("advanced") is True


@pytest.mark.parametrize("junk", ["", None, "BASIC-ish", "expert", 7])
def test_an_unknown_preset_resolves_to_nothing(junk):
    """The name arrives from the client, so it is untrusted input; an
    unrecognised one must fall through to an ordinary game rather than
    half-configuring one."""
    assert tut.normalise_preset(junk) == ""
    assert tut.preset_config(junk) is None


def test_preset_names_are_case_and_prefix_forgiving():
    assert tut.normalise_preset("  BASIC ") == "basic"
    assert tut.normalise_preset("tut-advanced") == "advanced"


def test_only_advanced_pins_its_board():
    """Basic teaches the machine and lands on any terrain. Advanced
    teaches signs and weapons, which need the board to co-operate — so
    it is the one preset that names a seed."""
    assert tut.preset_config("advanced")["seed"] == tut.ADVANCED_TUTORIAL_SEED
    assert "seed" not in tut.preset_config("basic")
    assert "seed" not in tut.preset_config("quick")


def test_the_advanced_board_can_teach_what_advanced_teaches():
    """The guard on the pinned seed.

    Every Advanced reel asserts something about this specific map: a
    blue smear bright enough to aim a hot drop at, and two pure seams
    far enough apart to be one each. None of that is guaranteed by the
    generator — it was searched for. So a retune of the generator, or a
    fat-fingered seed, must fail HERE rather than as a tutorial that
    describes terrain the player cannot find.
    """
    cfg = tut.preset_config("advanced")
    s = GameSession.new(
        cfg["width"], cfg["height"], seed=cfg["seed"],
        season_day_cap=cfg["season_day_cap"],
        weapons_enabled=True, signs_enabled=True, tutorial="advanced",
    )

    pures = [
        (x, y)
        for y in range(s.height) for x in range(s.width)
        if getattr(s.grid[y][x].tile, "name", "") == "RED"
        and int(getattr(s.grid[y][x], "purity", 0) or 0) == 255
    ]
    assert len(pures) >= 2, f"advanced board has {len(pures)} pure seam(s)"
    apart = max(
        ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5
        for a in pures for b in pures
    )
    assert apart >= 10, (
        f"the two jackpots are only {apart:.1f} apart — 'one each' is not "
        "a thing you can say about this board"
    )

    bright = [
        (int(c[0]), int(c[1]))
        for region in (s.blue_sign or [])
        for c in (region.get("cells") or [])
        if float(c[2]) >= 0.75
    ]
    assert bright, "no bright blue sign — the hot-drop film aims at nothing"
    # Inset, or a radius-4 probe disk and a close-up both run off the edge.
    assert any(
        3 <= x < s.width - 3 and 2 <= y < s.height - 2 for x, y in bright
    ), f"every bright sign cell is jammed against the edge: {bright}"


def test_every_preset_names_an_in_process_opponent():
    """No teaching game may need credentials. The heuristic runs in
    process; anything else would make the tutorial the first thing to
    break on a laptop with no Snowflake setup."""
    for name, cfg in tut.TUTORIAL_PRESETS.items():
        assert cfg["opponent"] == "red_harvest_lite", name


# ── the reels and the shot films must agree ─────────────────────────────

_REPO = pathlib.Path(__file__).resolve().parents[1]
_REEL_FILM = re.compile(r'film:\s*"([A-Za-z0-9_]+\.webm)"')


def _referenced_films() -> set:
    src = (_REPO / "server" / "static" / "tutorial.js").read_text("utf-8")
    return set(_REEL_FILM.findall(src))


def _shot_films() -> set:
    return {p.name for p in (_REPO / "server" / "static" / "films").glob("*.webm")}


def test_every_reel_points_at_a_film_that_exists():
    """A reel naming a film nobody shot degrades to prose in silence.

    That is the right runtime behaviour and a terrible way to find out:
    the attendee gets a chapter about collisions with no collision in
    it, and the modal reports nothing. Renaming a film in
    ``scripts/make_tutorial_films.py`` without renaming it here is the
    exact way this happens.
    """
    missing = sorted(_referenced_films() - _shot_films())
    assert not missing, (
        f"tutorial.js asks for {missing}, which is not in "
        f"server/static/films/ — those chapters will play nothing"
    )


def test_no_film_is_carried_without_a_reel_using_it():
    """Films are checked-in build output of a few MB each, so an orphan
    is dead weight in every clone — and usually the leftover half of a
    rename that half-happened."""
    orphans = sorted(_shot_films() - _referenced_films())
    assert not orphans, (
        f"{orphans} are committed but no reel plays them; delete them or "
        f"wire them into server/static/tutorial.js"
    )
