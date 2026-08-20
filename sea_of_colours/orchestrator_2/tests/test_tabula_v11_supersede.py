"""v11 SUPERSEDE targeting — owner/score + recency ranking, near-expiry filter.

Locks the redsign-combat behaviour: supersedes are offered every night (not just
the final one), target the LEADER's probes first when trailing, then by owner
score and recency, and never waste a probe on a target about to expire.
"""

from __future__ import annotations

from sea_of_colours.orchestrator_2.harnesses.tabula_v11 import (
    agency,
    supersede as ss,
)


def _view(*, probe_stock=2, launches=(), scores=None, mine_probes=()):
    """Minimal agent_view for the supersede builder.

    ``launches`` = iterable of (x, y, owner, day_seen) enemy probe launches.
    ``mine_probes`` = iterable of (x, y) friendly probe positions.
    """
    return {
        "orbit": {"probe_stock": probe_stock},
        "competitor_intel": {
            "new_this_day": [
                {
                    "kind": "enemy_probe_launch",
                    "owner": owner,
                    "at": [x, y],
                    "day_seen": d,
                }
                for (x, y, owner, d) in launches
            ],
            "persistent_echoes": [],
        },
        "hud": {"scores": scores or {}},
        "entities": {
            "mine": [
                {"type": "probe", "at": [x, y], "nights_remaining": 3}
                for (x, y) in mine_probes
            ]
        },
    }


def test_no_hints_without_probe_stock():
    av = _view(probe_stock=0, launches=[(5, 5, "p2", 5)])
    assert ss.top_supersede_hints(av, day=5, my_player="p1") == []


def test_no_hints_without_enemy_probes():
    av = _view(launches=[])
    assert ss.top_supersede_hints(av, day=5, my_player="p1") == []


def test_near_expiry_probe_is_dropped():
    # lifetime = 3. day 5, launched day 3 → remaining 1 → about to expire → drop.
    av = _view(launches=[(5, 5, "p2", 3)], scores={"p1": 0, "p2": 100})
    assert ss.top_supersede_hints(av, day=5, my_player="p1") == []
    # launched day 4 → remaining 2 → kept.
    av2 = _view(launches=[(5, 5, "p2", 4)], scores={"p1": 0, "p2": 100})
    assert len(ss.top_supersede_hints(av2, day=5, my_player="p1")) == 1


def test_leader_probe_ranked_first_when_trailing():
    # p2 leads (500), p3 second (200); we (p1) trail. p2's probe must rank first.
    av = _view(
        launches=[(9, 9, "p3", 5), (5, 5, "p2", 5)],
        scores={"p1": 100, "p2": 500, "p3": 200},
    )
    hints = ss.top_supersede_hints(av, day=5, my_player="p1")
    assert [tuple(h["probe_at"]) for h in hints] == [(5, 5), (9, 9)]
    assert hints[0]["owner"] == "p2" and hints[0]["is_leader"] is True


def test_recency_breaks_ties_within_owner():
    # Same owner, different launch days → freshest (most vision to deny) first.
    av = _view(
        launches=[(1, 1, "p2", 4), (2, 2, "p2", 5)],
        scores={"p1": 0, "p2": 100},
    )
    hints = ss.top_supersede_hints(av, day=5, my_player="p1")
    assert [tuple(h["probe_at"]) for h in hints] == [(2, 2), (1, 1)]


def test_friendly_occupied_cell_is_skipped():
    av = _view(
        launches=[(5, 5, "p2", 5)],
        scores={"p1": 0, "p2": 100},
        mine_probes=[(5, 5)],
    )
    assert ss.top_supersede_hints(av, day=5, my_player="p1") == []


def test_stock_caps_hint_count():
    av = _view(
        probe_stock=1,
        launches=[(5, 5, "p2", 5), (6, 6, "p2", 5)],
        scores={"p1": 0, "p2": 100},
    )
    assert len(ss.top_supersede_hints(av, day=5, my_player="p1")) == 1


def test_option_renders_owner_leader_and_vision_left():
    av = _view(launches=[(5, 5, "p2", 5)], scores={"p1": 100, "p2": 500})
    hint = ss.top_supersede_hints(av, day=5, my_player="p1")[0]
    opt = agency._supersede_option(1, hint)
    assert "p2" in opt.title
    assert "LEADER" in opt.detail
    assert "night(s) of vision left" in opt.detail


def test_exclude_cells_drops_probe_a_seam_pattern_already_blinds():
    # A chosen seam pattern (e.g. BLIND_GRAB) already supersedes (5,5). The SS menu
    # must NOT re-offer (5,5) — that would double-spend a probe on one blind — but
    # a DIFFERENT enemy probe (6,6) stays offered.
    av = _view(
        launches=[(5, 5, "p2", 5), (6, 6, "p2", 5)],
        scores={"p1": 0, "p2": 100},
    )
    hints = ss.top_supersede_hints(
        av, day=5, my_player="p1", exclude_cells=[(5, 5)],
    )
    cells = [tuple(h["probe_at"]) for h in hints]
    assert (5, 5) not in cells
    assert (6, 6) in cells


def test_no_leader_label_when_not_trailing():
    # Day-2 tie at 0: nobody is "the LEADER" — the option names the owner plainly
    # (no misleading "LEADER (score 0)"), and ranking falls back to recency.
    av = _view(launches=[(5, 5, "p2", 5)], scores={"p1": 0, "p2": 0})
    hint = ss.top_supersede_hints(av, day=5, my_player="p1")[0]
    assert hint["is_leader"] is False
    detail = agency._supersede_option(1, hint).detail
    assert "LEADER" not in detail
    assert "score 0" not in detail
