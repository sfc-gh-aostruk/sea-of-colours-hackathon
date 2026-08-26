"""Manage a single public *quick tunnel* from inside the server.

The Multiplayer button wants a public URL with one click instead of the
player dropping to a terminal. This module owns exactly one ephemeral
tunnel subprocess and exposes start / status / stop for the API layer.

v1.16 — this used to hard-code cloudflared, which broke on locked-down
corporate networks in a way that looked like our bug. Two independent
policies bite, and they bite different providers:

* **DNS blocklists.** A corporate resolver can return NXDOMAIN for a
  tunnel hostname while the same name resolves fine on 1.1.1.1. The
  provider's *transport* is untouched (a request with DNS bypassed
  returns 200), so the tunnel is perfectly healthy and simply unnameable.
  Nothing in our code can fix that: the guest's browser has to resolve
  the host. All we can do is notice and use a different provider.
* **Egress filtering.** The same network allows outbound 443 but drops
  SSH to some hosts and the high ports localtunnel and bore rely on.

So no single provider is safe. We keep an ordered list and use the first
one that actually publishes a *reachable* URL, which turns two partial
answers into one that covers nearly every network — the failure modes are
complementary, since a network that blocks SSH egress generally permits
Cloudflare and vice versa.

v1.17 — the order flipped, and a gate was added. Two measurements drove
it, both on a Snowflake laptop with the VPN up:

1. **Anonymous localhost.run hostnames rotate, fast.** A tunnel published
   ``cf80a4d4c4839b.lhr.life``, served 200 for thirteen minutes, then
   moved to a new name — and the old one returned 503. Every invite link
   and QR handed out before that point was dead, and the *host* was worst
   off, because the Multiplayer flow parks their browser on the tunnel
   origin. Their docs claim "a few hours"; we measured thirteen minutes.
   The documented fix is a **registered** SSH key rather than ``nokey``,
   but an unregistered key is refused outright, so a stable name needs an
   account per person — the exact setup cost this transport exists to
   avoid. Cloudflare quick tunnels keep their hostname for the life of
   the process, so they are the better default *when reachable*.
2. **Cloudflare names sometimes would not resolve here at all**, while
   the same name resolved on 1.1.1.1 and served 200 with DNS bypassed.
   That was read as a corporate filter on newly-observed subdomains and
   motivated ``_hostname_resolves``: accept a provider only once its
   hostname resolves through the same OS resolver the host's browser will
   use, else fall through. **The reading was wrong — see v1.18.** The gate
   is still the right idea; its timing was not.

v1.18 — there is no DNS block. *We* were the DNS block, and the gate was
the thing causing the failure it was written to detect.

Publishing a URL and the DNS record existing are two separate events.
Measured on cloudflared over three runs: the URL is printed at 5.4–5.8s
and the name first resolves anywhere at 8.0–9.3s, a window of **2.4–3.5s**.
The old gate started querying the instant the URL appeared and retried
every 0.8s, so its first lookups always landed *before* the record
existed. A resolver that is asked for a name that does not exist caches
that answer, and ``trycloudflare.com`` publishes a negative TTL of
**1800 seconds**. One premature lookup therefore made the hostname dead
on this machine for half an hour — on the *host's* resolver, the one
whose answer decides whether the invite links work at all.

The A/B that settled it: two quick tunnels started seconds apart, one
queried eight times at birth and one left alone. After 75s the untouched
name resolved locally; the hammered one was still NXDOMAIN locally while
1.1.1.1 happily returned an address for it. Same laptop, same VPN, same
resolver, opposite outcomes — the only variable was our own impatience.

So the gate now **waits for the record to plausibly exist before it opens
its mouth** (see :data:`_DNS_GRACE_S`), and the liveness watchdog is held
back behind the same gate, because its probe goes through the OS resolver
too and would otherwise poison the name the gate is about to test.

Notes:

* Quick tunnels need no account; the public URL is parsed from the
  provider's own log output and changes every run.
* If no provider is available or all fail, :func:`start` returns an
  ``error`` the UI surfaces instead of crashing, and the caller falls
  back to a local game.
"""

from __future__ import annotations

import atexit
import re
import shutil
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Pattern


@dataclass(frozen=True)
class Provider:
    """One way of getting a public URL for a local port.

    ``argv`` builds the command; ``url_re`` finds the public URL in
    whatever the process prints. ``binary`` is what must exist on PATH for
    the provider to be usable at all.
    """

    name: str
    binary: str
    argv: Callable[[int], List[str]]
    url_re: Pattern[str]
    install_hint: str
    # Per-provider patience. localhost.run negotiates an SSH session and
    # takes noticeably longer than cloudflared to print its URL, so give it
    # more room before falling through.
    wait_s: float = 20.0
    # Does this provider change the hostname out from under a live session?
    # Anonymous localhost.run does (measured: 13 minutes), which kills every
    # invite link already handed out, so the UI has to warn about it.
    rotates: bool = False

    def available(self) -> bool:
        return shutil.which(self.binary) is not None


def _lhr_argv(port: int) -> List[str]:
    return [
        "ssh",
        "-T",
        "-n",
        # accept-new (rather than "no") still pins the host key after the
        # first connection, so we get unattended startup without silently
        # re-trusting a changed key on every later run.
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "ServerAliveInterval=30",
        "-o", "ServerAliveCountMax=3",
        # Without this ssh happily stays up after a failed forward, and we
        # would sit out the whole timeout waiting for a URL that can never
        # arrive instead of failing over to the next provider.
        "-o", "ExitOnForwardFailure=yes",
        "-o", "ConnectTimeout=15",
        "-R", f"80:localhost:{int(port)}",
        "nokey@localhost.run",
    ]


def _cloudflared_argv(port: int) -> List[str]:
    return [
        "cloudflared", "tunnel",
        "--url", f"http://localhost:{int(port)}",
        "--no-autoupdate",
    ]


# v1.17 — cloudflare leads because its hostname survives the whole
# session; localhost.run's anonymous names rotate in minutes and take
# every shared invite link with them. localhost.run stays as the fallback
# precisely because it needs no install and no account, so a laptop
# without cloudflared, or on a network that drops it, can still host.
# Whether cloudflare is *reachable* is decided at runtime by the DNS gate
# in ``_try_provider``, never by assumption.
PROVIDERS: List[Provider] = [
    Provider(
        name="cloudflare",
        binary="cloudflared",
        argv=_cloudflared_argv,
        url_re=re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com", re.IGNORECASE),
        install_hint="brew install cloudflared",
        wait_s=20.0,
    ),
    Provider(
        name="localhost.run",
        binary="ssh",
        argv=_lhr_argv,
        url_re=re.compile(r"https://[a-z0-9-]+\.lhr\.life", re.IGNORECASE),
        install_hint="ssh is preinstalled on macOS, Linux and Windows 10+",
        wait_s=25.0,
        rotates=True,
    ),
]


# How long to stay silent after a provider prints its URL, before asking
# the resolver about it. Measured gap between "URL printed" and "name
# resolvable" on cloudflared quick tunnels: 2.4–3.5s over three runs. This
# is deliberately ~3x the worst of those, because the two outcomes are
# wildly asymmetric — a few seconds of spinner against a name that a
# premature lookup renders unusable for the next 1800 seconds (the zone's
# negative-cache TTL).
_DNS_GRACE_S = 12.0
# Gap between retries once we do start asking. Long, for the same reason:
# every miss re-caches the negative answer, so an impatient retry loop
# actively extends the damage instead of catching a slow record.
_DNS_RETRY_S = 8.0


def _hostname_resolves(
    host: str,
    *,
    tries: int = 3,
    delay: float = _DNS_RETRY_S,
    grace: float = _DNS_GRACE_S,
) -> bool:
    """Can this machine's resolver look the hostname up?

    This is the gate that decides whether a provider is usable *now*. It
    deliberately uses the OS resolver, because that is what the host's
    browser will use, and a name the host cannot resolve is a name they
    cannot hand to a guest.

    v1.18 — it waits ``grace`` seconds before the *first* lookup, which is
    the whole point of the function rather than a politeness. Asking about
    a name in the window between the provider printing it and the record
    existing does not just return a useless "no", it caches that "no" for
    the zone's negative TTL and so **creates** the outage this gate exists
    to detect. Waiting is free; being early costs half an hour.

    Only a genuine name-resolution failure counts: any other socket error
    is not evidence about DNS, so we give the provider the benefit of the
    doubt rather than failing it for, say, a transient network blip.
    """
    if not host:
        return False
    if grace > 0:
        time.sleep(grace)
    for attempt in range(max(1, tries)):
        try:
            socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
            return True
        except socket.gaierror:
            if attempt + 1 < tries:
                time.sleep(delay)
        except OSError:
            return True
    return False


class _TunnelManager:
    def __init__(self) -> None:
        self._proc: Optional[subprocess.Popen] = None
        self._url: Optional[str] = None
        self._port: Optional[int] = None
        self._provider: Optional[str] = None
        self._rotates = False
        self._ready = False
        # None until the public URL has answered once. After that, False
        # means it answered and then stopped — see _watch for why the
        # distinction matters.
        self._serving: Optional[bool] = None
        self._rotations = 0
        self._reader: Optional[threading.Thread] = None
        self._prober: Optional[threading.Thread] = None
        # v1.18 — opened once the DNS gate accepts the provider. Until then
        # the liveness watchdog must not probe: its request resolves the
        # public hostname through the OS resolver, and a lookup before the
        # record exists poisons that resolver for the negative TTL.
        self._probe_gate: Optional[threading.Event] = None
        self._lock = threading.RLock()

    # ── introspection ────────────────────────────────────────────────
    @staticmethod
    def available_providers() -> List[Provider]:
        return [p for p in PROVIDERS if p.available()]

    @classmethod
    def installed(cls) -> bool:
        """Is *any* provider usable? The UI only needs the yes/no."""
        return bool(cls.available_providers())

    def _running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def status(self) -> Dict[str, object]:
        with self._lock:
            running = self._running()
            return {
                "installed": self.installed(),
                "providers": [p.name for p in self.available_providers()],
                "running": running,
                "provider": self._provider if running else None,
                "url": self._url if running else None,
                "port": self._port if running else None,
                # ``ready`` flips True once the server confirms the public
                # URL answers from *its own* process. This is INFORMATIONAL
                # ONLY — do not gate the Multiplayer flow on it. The probe
                # resolves the public host via the OS resolver, which a
                # corporate VPN/security agent can block even while the
                # browser (DoH / encrypted DNS) reaches the tunnel fine.
                "ready": bool(self._ready) if running else False,
                # Tri-state, unlike ``running``: True = confirmed answering,
                # False = answered before and has since stopped, None = never
                # confirmed, so we genuinely cannot tell. Only False is
                # actionable.
                "serving": self._serving if running else None,
                # Anonymous localhost.run names "change regularly" (their
                # docs), which silently invalidates every invite link already
                # handed out. Surfacing the count lets the UI say so.
                "rotations": self._rotations if running else 0,
                # v1.17 — known *in advance* from the provider, unlike
                # ``rotations`` which can only report a rotation that has
                # already broken someone's link. This is what lets the UI
                # warn while the links are still good.
                "rotates": bool(self._rotates) if running else False,
            }

    # ── lifecycle ────────────────────────────────────────────────────
    def start(self, port: int, *, wait_s: Optional[float] = None) -> Dict[str, object]:
        """Start (or reuse) a public tunnel to ``http://localhost:<port>``.

        Tries each available provider in order and returns as soon as one
        publishes a URL. ``wait_s`` caps the *total* budget across
        providers; omit it to use each provider's own patience.
        """
        with self._lock:
            usable = self.available_providers()
            if not usable:
                hints = "; ".join(f"{p.name}: {p.install_hint}" for p in PROVIDERS)
                return {
                    "ok": False,
                    "installed": False,
                    "error": f"no tunnel provider available ({hints})",
                }
            # Reuse an existing tunnel for the same port.
            if self._running() and self._port == port:
                return {
                    "ok": True, "url": self._url, "running": True,
                    "reused": True, "provider": self._provider,
                }
            # A tunnel to a different port is replaced.
            if self._running():
                self._stop_locked()

        deadline = None if wait_s is None else time.time() + wait_s
        failures: List[str] = []

        for prov in usable:
            remaining = prov.wait_s
            if deadline is not None:
                remaining = min(remaining, deadline - time.time())
                if remaining <= 0:
                    failures.append(f"{prov.name}: out of time")
                    break
            outcome = self._try_provider(prov, port, remaining)
            if outcome.get("ok"):
                return outcome
            failures.append(f"{prov.name}: {outcome.get('error', 'failed')}")

        return {
            "ok": False,
            "installed": True,
            "error": "no tunnel could be established (" + "; ".join(failures) + ")",
        }

    def _try_provider(
        self, prov: Provider, port: int, wait_s: float,
    ) -> Dict[str, object]:
        """Spawn one provider and wait for it to publish a URL."""
        with self._lock:
            self._url = None
            self._ready = False
            self._serving = None
            self._rotations = 0
            self._port = int(port)
            self._provider = prov.name
            self._rotates = prov.rotates
            # Created before the reader thread starts, so the watchdog it
            # spawns can never find this unset and probe unguarded.
            gate = self._probe_gate = threading.Event()
            try:
                self._proc = subprocess.Popen(
                    prov.argv(port),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
            except OSError as exc:
                self._proc = None
                self._provider = None
                self._rotates = False
                return {"ok": False, "error": f"failed to launch: {exc}"}

            proc = self._proc
            self._reader = threading.Thread(
                target=self._scrape_url, args=(proc, prov), daemon=True,
            )
            self._reader.start()

        # Poll (outside the lock) for the URL to show up.
        end = time.time() + max(wait_s, 0.0)
        published: Optional[str] = None
        while time.time() < end:
            with self._lock:
                if self._url and self._proc is proc:
                    published = self._url
                elif self._proc is proc and not self._running():
                    self._stop_locked()
                    return {"ok": False, "error": "exited before publishing a URL"}
            if published:
                break
            time.sleep(0.25)

        if published:
            # v1.17 — publishing a URL is not the same as being usable. If
            # this machine can't resolve the hostname, neither can the
            # host's browser, so the invite links would all be dead on
            # arrival. Reject and let the next provider try, rather than
            # handing back a URL that looks fine in the response body.
            host = urllib.parse.urlsplit(published).hostname or ""
            if _hostname_resolves(host):
                # Name is known good, so the watchdog can start probing it
                # without risk of caching a miss.
                gate.set()
                return {
                    "ok": True, "url": published,
                    "running": True, "provider": prov.name,
                    "rotates": prov.rotates,
                }
            with self._lock:
                if self._proc is proc:
                    self._stop_locked()
            return {
                "ok": False,
                "error": (
                    f"published {published} but this machine cannot resolve "
                    f"{host} — DNS here is blocking it, so guests could not "
                    "reach it either"
                ),
            }

        # Timed out: tear this one down so the next provider starts clean
        # rather than leaving an orphan holding the port forwarding.
        with self._lock:
            if self._proc is proc:
                self._stop_locked()
        return {"ok": False, "error": "timed out waiting for a URL"}

    def _scrape_url(self, proc: subprocess.Popen, prov: Provider) -> None:
        """Read provider output for its public URL, including changes.

        The URL is not write-once. localhost.run rotates anonymous
        hostnames while the session stays up, and if it announces the new
        one we want to be holding it rather than a name that now 404s.
        """
        if proc.stdout is None:
            return
        started_watch = False
        for line in proc.stdout:
            m = prov.url_re.search(line)
            if m:
                with self._lock:
                    if self._proc is proc and m.group(0) != self._url:
                        if self._url is not None:
                            self._rotations += 1
                            self._serving = None
                        self._url = m.group(0)
                        if not started_watch:
                            started_watch = True
                            self._prober = threading.Thread(
                                target=self._watch,
                                args=(proc, self._probe_gate),
                                daemon=True,
                            )
                            self._prober.start()
            # Keep draining so the pipe buffer never blocks the child.

    def _watch(
        self, proc: subprocess.Popen, gate: Optional[threading.Event] = None,
    ) -> None:
        """Keep checking that the public URL still answers.

        A live subprocess is not proof of a live tunnel: localhost.run has
        been observed serving 503 for twelve minutes while ssh sat there
        perfectly happy, because the free tier rotates names out from
        under you. Without this, the UI would keep advertising an invite
        link that stopped working, which is worse than failing loudly.

        The probe goes through ``urllib`` → the OS resolver, which a
        corporate VPN can block for tunnel domains even when browsers get
        through. So a failure is only meaningful **after** a success:
        before that we report ``None`` (can't tell) rather than accusing a
        perfectly good tunnel of being dead.

        v1.18 — that same OS resolver dependency is why this waits for
        ``gate``. Probing the moment the URL is scraped would look up a
        name that does not exist yet and cache the miss for half an hour,
        breaking the tunnel we are here to supervise. The DNS gate opens
        this once the record is known to exist.
        """
        while gate is not None and not gate.wait(0.5):
            with self._lock:
                if self._proc is not proc:
                    return
            if proc.poll() is not None:
                return

        while True:
            with self._lock:
                if self._proc is not proc:
                    return
                url = self._url
            if proc.poll() is not None:
                return
            if not url:
                time.sleep(2.0)
                continue

            ok = self._probe_once(url)
            with self._lock:
                if self._proc is not proc:
                    return
                if ok:
                    self._ready = True
                    self._serving = True
                elif self._ready:
                    # Answered before, doesn't now — a real regression.
                    self._serving = False
                # else: never answered, so silence rather than a guess.
            time.sleep(30.0)

    @staticmethod
    def _probe_once(url: str) -> bool:
        """Does the public URL respond at all? Any HTTP status counts —
        we're testing the round trip, not the app."""
        target = url.rstrip("/") + "/api/meta/backend"
        try:
            req = urllib.request.Request(target, method="GET")
            with urllib.request.urlopen(req, timeout=6) as resp:
                resp.read(1)
            return True
        except urllib.error.HTTPError as exc:
            # 5xx from the tunnel edge means the tunnel is NOT routing back
            # to us — that is exactly the rotation failure we're hunting —
            # whereas a 4xx proves the round trip works.
            return exc.code < 500
        except Exception:
            return False

    def stop(self) -> Dict[str, object]:
        with self._lock:
            self._stop_locked()
            return {"ok": True, "running": False}

    def _stop_locked(self) -> None:
        proc = self._proc
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
            except OSError:
                pass
        self._proc = None
        self._url = None
        self._port = None
        self._provider = None
        self._rotates = False
        self._ready = False
        self._serving = None
        self._rotations = 0
        # Release any watchdog still parked on the gate; it re-checks the
        # process identity on wake and retires itself.
        if self._probe_gate is not None:
            self._probe_gate.set()
            self._probe_gate = None


_manager = _TunnelManager()


def start(port: int, *, wait_s: Optional[float] = None) -> Dict[str, object]:
    return _manager.start(port, wait_s=wait_s)


def status() -> Dict[str, object]:
    return _manager.status()


def stop() -> Dict[str, object]:
    return _manager.stop()


@atexit.register
def _cleanup() -> None:
    try:
        _manager.stop()
    except Exception:
        pass
