"""Teaching-mode presets (v1.32).

One place decides what "Basic" means. The landing page posts a preset
NAME, not a bag of overrides, so the client cannot drift from the engine
— and a test, a film harness and the browser all spawn byte-identical
tutorials.

Presets are expressed as OVERRIDES on the ordinary new-game defaults
rather than as complete configurations. A field added to the New Game
modal later therefore reaches the tutorial paths automatically instead of
silently defaulting; the alternative (three independent literals) is a
drift bug that would surface months later as "the tutorial ignores X".

Note what is NOT here: nothing in this module is consulted at rule-check
time. A preset only chooses the values of ``GameSession.weapons_enabled``
and ``signs_enabled`` when the game is minted. The engine then asks the
session, never the preset name, so a future preset cannot quietly change
what is legal mid-season.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

#: Every teaching game runs three nights. Long enough to see a full loop
#: (orbit → plan → night → orbit), short enough that a first-timer
#: reaches a score card rather than abandoning a half-played season.
TUTORIAL_DAY_CAP = 3

#: The teaching board. Smaller than the 40x28 default so a probe's
#: radius-4 disk is a visible fraction of the map rather than a dot, and
#: so the fog clears fast enough to feel like progress.
TUTORIAL_WIDTH = 24
TUTORIAL_HEIGHT = 16

#: The opponent for every preset. The heuristic runs in-process, so a
#: tutorial needs no Snowflake credentials and no network — the attendee
#: can play before they have configured anything.
TUTORIAL_OPPONENT = "red_harvest_lite"


TUTORIAL_PRESETS: Dict[str, Dict[str, Any]] = {
    # Weapons and signs both off. Basic teaches the core loop only:
    # probe to see, drop to harvest, lift to bank. Signs are off TOGETHER
    # with weapons rather than separately — a board with signature
    # intelligence but no way to act on it teaches a game that does not
    # exist.
    "basic": {
        "width": TUTORIAL_WIDTH,
        "height": TUTORIAL_HEIGHT,
        "season_day_cap": TUTORIAL_DAY_CAP,
        "weapons_enabled": False,
        "signs_enabled": False,
        "opponent": TUTORIAL_OPPONENT,
    },
    # Same board size, everything switched on. The point of the second
    # run is what signs and weapons ADD to terrain you have already
    # learned to read.
    "advanced": {
        "width": TUTORIAL_WIDTH,
        "height": TUTORIAL_HEIGHT,
        "season_day_cap": TUTORIAL_DAY_CAP,
        "weapons_enabled": True,
        "signs_enabled": True,
        "opponent": TUTORIAL_OPPONENT,
    },
    # Not a tutorial: a full-size, full-rules season that is merely
    # short. It lives here because it is the third card on the same
    # chooser and shares the "three nights, heuristic opponent" shape.
    "quick": {
        "season_day_cap": TUTORIAL_DAY_CAP,
        "weapons_enabled": True,
        "signs_enabled": True,
        "opponent": TUTORIAL_OPPONENT,
    },
}

#: ``quick`` is a normal game that happens to be short, so it must not
#: put the player in a teaching UI. Only these presets set
#: ``GameSession.tutorial`` and therefore only these show the film modal.
TEACHING_PRESETS = ("basic", "advanced")


def normalise_preset(name: Any) -> str:
    """Return a known preset name, or ``""`` for anything else."""
    key = str(name or "").strip().lower().replace("tut-", "")
    return key if key in TUTORIAL_PRESETS else ""


def preset_config(name: Any) -> Optional[Mapping[str, Any]]:
    """Overrides for ``name``, or ``None`` when it names no preset."""
    key = normalise_preset(name)
    return TUTORIAL_PRESETS.get(key) if key else None


def is_teaching(name: Any) -> bool:
    """Does this preset put the player in the tutorial UI?"""
    return normalise_preset(name) in TEACHING_PRESETS
