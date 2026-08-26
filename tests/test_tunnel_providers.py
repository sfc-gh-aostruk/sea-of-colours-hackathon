"""Multiplayer tunnel: provider selection, fallback and URL scraping.

Why this file exists (v1.16): the Multiplayer button used to spawn
cloudflared and nothing else, which fails silently on corporate networks
that sinkhole ``*.trycloudflare.com`` in DNS. The fix was an ordered
provider list, and the thing worth pinning is not "cloudflared runs" but
the *fallback behaviour* — that a dead first provider hands off to the
second instead of taking the whole feature down with it.

v1.17 added the DNS acceptance gate and flipped the order. Publishing a
URL turns out not to mean the URL is usable: if the host's own resolver
can't look the hostname up, no guest can reach it either, so the provider
has to be rejected in favour of the next one. And the order flipped
because anonymous localhost.run hostnames rotate within minutes, killing
every invite link already handed out, whereas a Cloudflare quick tunnel
keeps its name for the life of the process.

v1.18 corrected the *timing* of that gate, and this is the subtlest bug
in the file's history: the gate was querying the hostname in the 2.4–3.5s
window between the provider printing it and the DNS record existing, and
the resulting cached NXDOMAIN (negative TTL 1800s on
``trycloudflare.com``) made the name unresolvable on the host's own
machine for half an hour. The gate was manufacturing the exact failure it
was written to detect, which is why "cloudflare is blocked here" looked
reproducible. So there are now tests that nothing — gate or watchdog —
touches DNS before the record can exist.

These tests never touch the network. Fake providers are real subprocesses
(so the scrape/timeout/exit paths are genuinely exercised) that just print
a line or sleep, and the DNS gate is stubbed except where it is the thing
under test.
"""

from __future__ import annotations

import re
import sys
import time
import urllib.error
import urllib.request
from unittest import mock

import pytest

from server import tunnel as soc_tunnel

# Captured before the autouse stub below replaces it, so the gate's own
# tests can exercise the real implementation.
_REAL_RESOLVES = soc_tunnel._hostname_resolves


@pytest.fixture(autouse=True)
def _no_leftover_tunnel():
    """Every test starts and ends with nothing running."""
    soc_tunnel.stop()
    yield
    soc_tunnel.stop()


@pytest.fixture(autouse=True)
def _dns_resolves(monkeypatch):
    """Stub the acceptance gate open by default.

    Fake providers publish names like ``good.example.test`` that genuinely
    don't resolve, so without this every happy-path test would be rejected
    by the gate — and would also pay several seconds of real DNS retries
    to get there. Tests that are *about* the gate patch it themselves.
    """
    monkeypatch.setattr(soc_tunnel, "_hostname_resolves", lambda host, **kw: True)


def _fake(name: str, script: str, url_re: str, wait_s: float = 6.0,
          rotates: bool = False):
    """A provider that runs a short Python snippet instead of a tunnel."""
    return soc_tunnel.Provider(
        name=name,
        binary=sys.executable,
        argv=lambda port, _s=script: [sys.executable, "-c", _s],
        url_re=re.compile(url_re),
        install_hint=f"install {name}",
        wait_s=wait_s,
        rotates=rotates,
    )


_PUBLISHES = "print('tunnelled at https://good.example.test ok', flush=True)\nimport time; time.sleep(30)"
_PUBLISHES2 = "print('tunnelled at https://other.example.test ok', flush=True)\nimport time; time.sleep(30)"
_EXITS = "import sys; sys.exit(3)"
_SILENT = "import time; time.sleep(30)"


# ── ordering and availability ────────────────────────────────────────

def test_cloudflare_is_tried_before_localhost_run():
    """v1.17 — the order is decided by *hostname stability*, not by install
    cost. A Cloudflare quick tunnel keeps its name for the life of the
    process; an anonymous localhost.run name rotated after 13 minutes in
    testing and took every invite link with it. Reachability is settled at
    runtime by the DNS gate, so it can't justify the ordering."""
    names = [p.name for p in soc_tunnel.PROVIDERS]
    assert names.index("cloudflare") < names.index("localhost.run")


def test_the_fallback_provider_needs_no_install():
    """Whatever leads, the *last* resort has to work on a bare machine, or
    a laptop without cloudflared can't host at all."""
    assert soc_tunnel.PROVIDERS[-1].binary == "ssh"


def test_only_the_rotating_provider_is_flagged_as_such():
    """The flag is what lets the UI warn while links are still good,
    rather than after a rotation has already broken them."""
    by_name = {p.name: p for p in soc_tunnel.PROVIDERS}
    assert by_name["localhost.run"].rotates is True
    assert by_name["cloudflare"].rotates is False


def test_installed_is_true_when_any_provider_exists(monkeypatch):
    monkeypatch.setattr(soc_tunnel, "PROVIDERS", [_fake("f", _SILENT, "x")])
    assert soc_tunnel.status()["installed"] is True


def test_installed_is_false_when_no_provider_exists(monkeypatch):
    gone = soc_tunnel.Provider(
        name="nope", binary="soc-not-a-real-binary",
        argv=lambda port: ["soc-not-a-real-binary"],
        url_re=re.compile("x"), install_hint="get it",
    )
    monkeypatch.setattr(soc_tunnel, "PROVIDERS", [gone])
    assert soc_tunnel.status()["installed"] is False


# ── starting ─────────────────────────────────────────────────────────

def test_a_working_provider_returns_its_url(monkeypatch):
    monkeypatch.setattr(
        soc_tunnel, "PROVIDERS",
        [_fake("good", _PUBLISHES, r"https://good\.example\.test")],
    )
    res = soc_tunnel.start(8000, wait_s=10)
    assert res["ok"] is True
    assert res["url"] == "https://good.example.test"
    assert res["provider"] == "good"


def test_a_dead_first_provider_falls_through_to_the_second(monkeypatch):
    """The regression this whole change exists to prevent."""
    monkeypatch.setattr(soc_tunnel, "PROVIDERS", [
        _fake("dead", _EXITS, r"https://never\.example\.test"),
        _fake("good", _PUBLISHES, r"https://good\.example\.test"),
    ])
    res = soc_tunnel.start(8000, wait_s=20)
    assert res["ok"] is True
    assert res["provider"] == "good"


def test_a_silent_first_provider_times_out_and_hands_over(monkeypatch):
    """A provider that connects but never publishes must not hold the
    whole feature hostage until the browser gives up."""
    monkeypatch.setattr(soc_tunnel, "PROVIDERS", [
        _fake("mute", _SILENT, r"https://never\.example\.test", wait_s=2.0),
        _fake("good", _PUBLISHES, r"https://good\.example\.test"),
    ])
    res = soc_tunnel.start(8000, wait_s=20)
    assert res["ok"] is True
    assert res["provider"] == "good"


def test_every_provider_failing_reports_each_reason(monkeypatch):
    monkeypatch.setattr(soc_tunnel, "PROVIDERS", [
        _fake("one", _EXITS, "x"),
        _fake("two", _EXITS, "x"),
    ])
    res = soc_tunnel.start(8000, wait_s=15)
    assert res["ok"] is False
    assert "one" in res["error"] and "two" in res["error"]


def test_no_provider_at_all_names_how_to_get_one(monkeypatch):
    gone = soc_tunnel.Provider(
        name="nope", binary="soc-not-a-real-binary",
        argv=lambda port: ["soc-not-a-real-binary"],
        url_re=re.compile("x"), install_hint="brew install nope",
    )
    monkeypatch.setattr(soc_tunnel, "PROVIDERS", [gone])
    res = soc_tunnel.start(8000, wait_s=5)
    assert res["ok"] is False
    assert res["installed"] is False
    assert "brew install nope" in res["error"]


def test_a_second_start_on_the_same_port_reuses_the_tunnel(monkeypatch):
    monkeypatch.setattr(
        soc_tunnel, "PROVIDERS",
        [_fake("good", _PUBLISHES, r"https://good\.example\.test")],
    )
    first = soc_tunnel.start(8000, wait_s=10)
    second = soc_tunnel.start(8000, wait_s=10)
    assert second.get("reused") is True
    assert second["url"] == first["url"]


# ── the DNS acceptance gate (v1.17) ──────────────────────────────────
#
# Publishing a URL is not the same as being usable. If the host's resolver
# can't look the hostname up, the host's browser can't either, so every
# invite link would be dead on arrival — and the tunnel process would sit
# there looking perfectly healthy the whole time.

def test_an_unresolvable_hostname_is_rejected(monkeypatch):
    monkeypatch.setattr(soc_tunnel, "_hostname_resolves", lambda host, **kw: False)
    monkeypatch.setattr(
        soc_tunnel, "PROVIDERS",
        [_fake("blocked", _PUBLISHES, r"https://good\.example\.test")],
    )
    res = soc_tunnel.start(8000, wait_s=10)
    assert res["ok"] is False
    # The message has to name DNS, or the user goes hunting for a bug that
    # isn't in this repo.
    assert "resolve" in res["error"]
    assert "good.example.test" in res["error"]


def test_a_dns_blocked_provider_falls_through_to_the_next(monkeypatch):
    """The exact corporate-network case: cloudflared runs fine and prints a
    URL, but the name is sinkholed, so localhost.run has to take over."""
    monkeypatch.setattr(soc_tunnel, "PROVIDERS", [
        _fake("sinkholed", _PUBLISHES, r"https://good\.example\.test"),
        _fake("reachable", _PUBLISHES2, r"https://other\.example\.test"),
    ])
    monkeypatch.setattr(
        soc_tunnel, "_hostname_resolves",
        lambda host, **kw: host != "good.example.test",
    )
    res = soc_tunnel.start(8000, wait_s=20)
    assert res["ok"] is True
    assert res["provider"] == "reachable"


def test_a_rejected_provider_leaves_nothing_running(monkeypatch):
    """An orphan holding the port forward would poison the next attempt."""
    monkeypatch.setattr(soc_tunnel, "_hostname_resolves", lambda host, **kw: False)
    monkeypatch.setattr(
        soc_tunnel, "PROVIDERS",
        [_fake("blocked", _PUBLISHES, r"https://good\.example\.test")],
    )
    soc_tunnel.start(8000, wait_s=10)
    st = soc_tunnel.status()
    assert st["running"] is False
    assert st["url"] is None


def test_the_gate_retries_before_giving_up(monkeypatch):
    """A freshly minted hostname legitimately takes a moment to become
    resolvable; failing on the first miss would discard a good provider."""
    seen = {"n": 0}

    def _resolver(*_a, **_k):
        seen["n"] += 1
        if seen["n"] < 3:
            raise soc_tunnel.socket.gaierror("not yet")
        return [("fam", "type", "proto", "", ("1.2.3.4", 443))]

    monkeypatch.setattr(soc_tunnel.socket, "getaddrinfo", _resolver)
    assert _REAL_RESOLVES("x.test", tries=5, delay=0.01, grace=0) is True
    assert seen["n"] == 3


def test_the_gate_gives_up_on_a_name_that_never_resolves(monkeypatch):
    def _nxdomain(*_a, **_k):
        raise soc_tunnel.socket.gaierror("NXDOMAIN")

    monkeypatch.setattr(soc_tunnel.socket, "getaddrinfo", _nxdomain)
    assert _REAL_RESOLVES("x.test", tries=3, delay=0.01, grace=0) is False


def test_a_non_dns_socket_error_does_not_condemn_the_provider(monkeypatch):
    """Only a name-resolution failure is evidence about DNS. Anything else
    is a blip, and failing the provider for it would be a false negative."""
    def _blip(*_a, **_k):
        raise OSError("network down for a moment")

    monkeypatch.setattr(soc_tunnel.socket, "getaddrinfo", _blip)
    assert _REAL_RESOLVES("x.test", tries=2, delay=0.01, grace=0) is True


def test_an_empty_hostname_is_not_accepted():
    assert _REAL_RESOLVES("", tries=1) is False


# ── the gate must not poison the name it is testing (v1.18) ──────────
# A lookup issued before the record exists is not a harmless "no": the
# resolver caches it for the zone's negative TTL, so one early query makes
# the hostname dead on the host's own machine long after the tunnel is
# healthy. Everything below exists to keep us patient.

def test_the_gate_stays_silent_during_the_grace_period(monkeypatch):
    asked: list[float] = []

    def _record(*_a, **_k):
        asked.append(time.monotonic())
        return [("fam", "type", "proto", "", ("1.2.3.4", 443))]

    monkeypatch.setattr(soc_tunnel.socket, "getaddrinfo", _record)
    t0 = time.monotonic()
    assert _REAL_RESOLVES("x.test", grace=0.5, tries=1) is True
    assert asked, "the gate never looked the name up at all"
    assert asked[0] - t0 >= 0.5, "asked before the record could exist"


def test_the_grace_period_is_wide_enough_for_a_real_tunnel():
    """Measured lag between cloudflared printing its URL and the name
    resolving anywhere: 2.4–3.5s over three runs. Cutting it fine is a coin
    flip where losing costs 1800s of dead hostname, so keep a multiple."""
    assert soc_tunnel._DNS_GRACE_S >= 10.0


def test_retries_back_off_slowly_rather_than_hammering():
    """Each miss re-caches the negative answer, so a tight retry loop
    extends the outage rather than catching a slow record."""
    assert soc_tunnel._DNS_RETRY_S >= 5.0


def test_the_watchdog_does_not_probe_before_the_gate_opens(monkeypatch):
    """The liveness probe resolves the same hostname through the same
    resolver, so an eager watchdog poisons the name just as effectively as
    an eager gate — and it used to start the moment the URL was scraped."""
    events: list[str] = []

    def _gate(host, **_kw):
        events.append("gate:start")
        time.sleep(0.75)
        events.append("gate:open")
        return True

    monkeypatch.setattr(soc_tunnel, "_hostname_resolves", _gate)
    monkeypatch.setattr(
        soc_tunnel._TunnelManager, "_probe_once",
        staticmethod(lambda url: events.append("probe") or True),
    )
    monkeypatch.setattr(
        soc_tunnel, "PROVIDERS",
        [_fake("slow-dns", _PUBLISHES, r"https://good\.example\.test")],
    )
    assert soc_tunnel.start(8000, wait_s=10)["ok"] is True
    time.sleep(0.3)  # let a rogue watchdog incriminate itself
    assert "gate:open" in events
    before_open = events[: events.index("gate:open")]
    assert "probe" not in before_open, f"probed too early: {events}"


# ── status shape ─────────────────────────────────────────────────────

def test_status_names_the_running_provider(monkeypatch):
    monkeypatch.setattr(
        soc_tunnel, "PROVIDERS",
        [_fake("good", _PUBLISHES, r"https://good\.example\.test")],
    )
    soc_tunnel.start(8000, wait_s=10)
    st = soc_tunnel.status()
    assert st["running"] is True
    assert st["provider"] == "good"
    assert st["port"] == 8000


def test_stopping_clears_the_url(monkeypatch):
    monkeypatch.setattr(
        soc_tunnel, "PROVIDERS",
        [_fake("good", _PUBLISHES, r"https://good\.example\.test")],
    )
    soc_tunnel.start(8000, wait_s=10)
    soc_tunnel.stop()
    st = soc_tunnel.status()
    assert st["running"] is False
    assert st["url"] is None
    assert st["provider"] is None


# ── liveness watchdog ────────────────────────────────────────────────
#
# A live subprocess is not a live tunnel. Observed: localhost.run served
# 503 for twelve minutes while ssh sat there perfectly happy, because the
# free tier rotates hostnames out from under an open session.

_ROTATES = (
    "print('https://first.example.test', flush=True)\n"
    "import time; time.sleep(1)\n"
    "print('https://second.example.test', flush=True)\n"
    "time.sleep(30)"
)


def test_a_url_that_never_answered_is_not_called_broken(monkeypatch):
    """The corporate-DNS trap: our probe uses the OS resolver, which can
    be blocked for tunnel domains while browsers get through. Never
    having confirmed a URL is not evidence against it."""
    monkeypatch.setattr(
        soc_tunnel, "PROVIDERS",
        [_fake("good", _PUBLISHES, r"https://good\.example\.test")],
    )
    soc_tunnel.start(8000, wait_s=10)
    # good.example.test does not resolve, so the probe cannot succeed.
    assert soc_tunnel.status()["serving"] is None


def test_a_rotated_hostname_is_picked_up_and_counted(monkeypatch):
    monkeypatch.setattr(
        soc_tunnel, "PROVIDERS",
        [_fake("rot", _ROTATES, r"https://[a-z]+\.example\.test")],
    )
    res = soc_tunnel.start(8000, wait_s=10)
    assert res["url"] == "https://first.example.test"
    deadline = time.time() + 8
    while time.time() < deadline:
        if soc_tunnel.status()["rotations"] >= 1:
            break
        time.sleep(0.2)
    st = soc_tunnel.status()
    assert st["rotations"] == 1
    assert st["url"] == "https://second.example.test"


def test_a_5xx_from_the_edge_counts_as_not_serving():
    """503 is precisely the rotation symptom: the edge is up, but no
    longer routed to us."""
    err = urllib.error.HTTPError("u", 503, "Service Unavailable", None, None)
    with mock.patch.object(urllib.request, "urlopen", side_effect=err):
        assert soc_tunnel._TunnelManager._probe_once("https://x.test") is False


def test_a_4xx_still_proves_the_round_trip():
    err = urllib.error.HTTPError("u", 404, "Not Found", None, None)
    with mock.patch.object(urllib.request, "urlopen", side_effect=err):
        assert soc_tunnel._TunnelManager._probe_once("https://x.test") is True


def test_a_stopped_tunnel_reports_no_rotations():
    soc_tunnel.stop()
    st = soc_tunnel.status()
    assert st["serving"] is None
    assert st["rotations"] == 0


# ── the regexes, against real observed output ────────────────────────

def test_localhost_run_regex_matches_its_real_banner():
    """Verbatim from a live run — the banner mentions the host twice, and
    only the second is a URL."""
    line = ("cf0377d8977167.lhr.life tunneled with tls termination, "
            "https://cf0377d8977167.lhr.life")
    prov = next(p for p in soc_tunnel.PROVIDERS if p.name == "localhost.run")
    assert prov.url_re.search(line).group(0) == "https://cf0377d8977167.lhr.life"


def test_cloudflare_regex_matches_its_real_banner():
    line = "|  https://ottawa-finite-hosts-answering.trycloudflare.com   |"
    prov = next(p for p in soc_tunnel.PROVIDERS if p.name == "cloudflare")
    got = prov.url_re.search(line).group(0)
    assert got == "https://ottawa-finite-hosts-answering.trycloudflare.com"


def test_the_regexes_do_not_match_each_others_hosts():
    lhr = next(p for p in soc_tunnel.PROVIDERS if p.name == "localhost.run")
    cf = next(p for p in soc_tunnel.PROVIDERS if p.name == "cloudflare")
    assert lhr.url_re.search("https://x.trycloudflare.com") is None
    assert cf.url_re.search("https://x.lhr.life") is None
