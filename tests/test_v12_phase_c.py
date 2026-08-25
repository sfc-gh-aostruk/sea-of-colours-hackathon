"""Phase C menu contracts that are not pure seam geometry — tabula_v12.

Seam SHAPE lives in ``test_v12_seam_geometry``; this file covers what reaches
the option registry (fix 1.5) and the sign-age datum it hangs on.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping

from sea_of_colours.orchestrator_2.harnesses.tabula_v12 import agency
from sea_of_colours.orchestrator_2.harnesses.tabula_v12 import option_economics as oe

_PURE = (16, 6)


def _view(day: int = 6, found: Any = 5) -> Dict[str, Any]:
    sign: Dict[str, Any] = {
        "center": [_PURE[0], _PURE[1]], "mine": True,
        "cells": [[_PURE[0], _PURE[1]]],
    }
    if found is not None:
        sign["found_day"] = found
    return {
        "day": day,
        "world": {"width": 40, "height": 40, "live": []},
        "red_tiles": [],
        "redsign": [sign],
    }


def _chain(drop: List[int], cells: List[List[int]]) -> Dict[str, Any]:
    return {"drop_at": drop, "cells": cells, "length": len(cells)}


_ON_SEAM = _chain([16, 7], [[16, 7], [16, 8]])
_OFF_SEAM = _chain([30, 30], [[30, 30], [30, 31]])


def _kept(hints, view, has_seam=True) -> List[List[int]]:
    return [h["drop_at"] for h in agency._chains_off_the_seam(hints, view, has_seam)]


# ── fix 1.5 — geometric, not categorical ───────────────────────────────
def test_a_chain_inside_the_footprint_is_dropped_as_a_duplicate():
    """The seam patterns already offer that ground in shapes built for a
    contested race; the chain competes with the play it duplicates."""
    assert _kept([_ON_SEAM, _OFF_SEAM], _view()) == [[30, 30]]


def test_a_chain_elsewhere_on_the_board_survives():
    """Exactly what a spare harvester should take when it is not attacking. A
    blanket "no chains on redsign nights" rule would delete it."""
    assert [30, 30] in _kept([_OFF_SEAM], _view())


def test_nothing_is_suppressed_when_no_seam_pattern_was_built():
    """With no seam option on the menu the chain is not a duplicate of
    anything — it is the only way that ground gets offered at all."""
    assert _kept([_ON_SEAM, _OFF_SEAM], _view(), has_seam=False) == [
        [16, 7], [30, 30],
    ]


def test_the_pressure_eases_once_the_sign_is_no_longer_fresh():
    """A fresh sign dominates because its pure is almost certainly still there.
    After a couple of nights of being fought over that stops being true."""
    old = _view(day=5 + oe._SIGN_FRESH_NIGHTS + 1, found=5)
    assert _kept([_ON_SEAM, _OFF_SEAM], old) == [[16, 7], [30, 30]]


def test_an_undated_sign_never_eases():
    """We cannot show it is old, so we must not act as though it is."""
    assert _kept([_ON_SEAM, _OFF_SEAM], _view(found=None)) == [[30, 30]]


# ── the sign-age datum itself ──────────────────────────────────────────
def test_sign_age_counts_nights_since_the_broadcast():
    assert oe.sign_age_nights(_view(day=6, found=5)) == 1
    assert oe.sign_age_nights(_view(day=5, found=5)) == 0


def test_sign_age_is_none_when_nothing_dates_it():
    assert oe.sign_age_nights(_view(found=None)) is None
    assert oe.sign_age_nights({"day": 6, "redsign": []}) is None


def test_sign_age_reports_the_freshest_of_several_signs():
    """Menu pressure is set by the newest broadcast — an old seam beside a new
    one must not ease the new one's grip on the menu."""
    view = _view(day=9, found=3)
    view["redsign"].append({
        "center": [30, 30], "mine": False, "found_day": 8, "cells": [[30, 30]],
    })
    assert oe.sign_age_nights(view) == 1


def test_the_footprint_covers_the_ring_the_fight_is_over_not_just_the_smear():
    """The broadcast is jittered, so the exact pure is usually a cell or two off
    the advertised centre."""
    cells = oe.redsign_footprint(_view())
    assert _PURE in cells
    assert (_PURE[0] + oe._REDSIGN_PUBLIC_RADIUS, _PURE[1]) in cells
    assert (_PURE[0] + oe._REDSIGN_PUBLIC_RADIUS + 1, _PURE[1]) not in cells
