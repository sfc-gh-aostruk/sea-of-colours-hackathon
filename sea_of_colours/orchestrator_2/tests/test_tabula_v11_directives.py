"""Unit tests for the v10 orbit->night directive channel (Workstream D).

``orbit_wishlist`` gained a ``compute_night_directives`` helper + a
``Wishlist.directives`` field, populated by the shared ``compute_wishlist``.
v10 renders them via ``format_orbit_directives_block``. The shared
``as_prompt_lines`` is untouched, so frozen v6/v7/v8 prompts are unaffected.
"""

from __future__ import annotations

from sea_of_colours.orchestrator_2.harnesses.tabula_v7 import orbit_wishlist as wl
from sea_of_colours.orchestrator_2.harnesses.tabula_v11 import prompt as prompt_mod


def _view(**extra):
    base = {
        "world": {"width": 20, "height": 20, "live": []},
        "blue_tiles": [],
        "hud": {"hoard": {"pct_full": 0.0}},
        "orbit": {"probe_stock": 5},
        "my_assets": [],
        "station_intel": {"self": {"blue": {"grade": "high"}}},
    }
    base.update(extra)
    return base


def test_need_blue_directive_when_blue_low_and_visible():
    av = _view(
        blue_tiles=[{"x": 1, "y": 1}],
        station_intel={"self": {"blue": {"grade": "low"}}},
    )
    ds = wl.compute_night_directives(av, day=2)
    assert any("NEED BLUE" in d for d in ds)


def test_no_need_blue_when_blue_not_visible():
    av = _view(station_intel={"self": {"blue": {"grade": "low"}}})  # no blue_tiles
    ds = wl.compute_night_directives(av, day=2)
    assert not any("NEED BLUE" in d for d in ds)


def test_vault_nearly_full_directive_high_value_only():
    av = _view(hud={"hoard": {"pct_full": 0.85}})
    ds = wl.compute_night_directives(av, day=2)
    line = next((d for d in ds if "VAULT NEARLY FULL" in d), "")
    assert line and "HIGH-VALUE ONLY" in line


def test_conserve_probes_directive_when_stock_low():
    av = _view(orbit={"probe_stock": 1})
    ds = wl.compute_night_directives(av, day=2)
    assert any("CONSERVE PROBES" in d for d in ds)


def test_no_directives_on_healthy_state():
    assert wl.compute_night_directives(_view(), day=2) == []


def test_compute_wishlist_populates_directives():
    av = _view(orbit={"probe_stock": 0})
    w = wl.compute_wishlist(av, day=2)
    assert any("CONSERVE PROBES" in d for d in w.directives)


def test_as_prompt_lines_unaffected_by_directives():
    """Back-compat: the shared wishlist block never renders directives."""
    w = wl.Wishlist(entries=[], directives=["NEED BLUE: ..."])
    assert w.as_prompt_lines() == []


def test_v9_renders_orbit_directives_block():
    w = wl.Wishlist(directives=["CONSERVE PROBES: only 1 probe left"])
    block = prompt_mod.format_orbit_directives_block(w)
    assert "ORBIT DIRECTIVES" in block
    assert "CONSERVE PROBES" in block


def test_v9_orbit_directives_block_empty_when_none():
    assert prompt_mod.format_orbit_directives_block(wl.Wishlist()) == ""
    assert prompt_mod.format_orbit_directives_block(None) == ""
