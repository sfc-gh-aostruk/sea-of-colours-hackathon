"""Manage a single cloudflared *quick tunnel* from inside the server.

The Multiplayer button on the landing page wants a public URL with one
click instead of the player dropping to a terminal to run
``cloudflared tunnel --url http://localhost:8000`` by hand. This module
owns exactly one ephemeral quick-tunnel subprocess and exposes start /
status / stop for the API layer.

Notes:

* Quick tunnels need no Cloudflare account; the URL
  (``https://<random>.trycloudflare.com``) is parsed from cloudflared's
  own log output and changes every run.
* ``cloudflared`` must be on PATH; if it isn't, :func:`start` returns an
  ``error`` the UI can surface instead of crashing.
* A background reader thread scrapes the URL out of the process output so
  :func:`start` can return it within a few seconds; :func:`status` is
  cheap polling thereafter.
"""

from __future__ import annotations

import atexit
import re
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
from typing import Dict, Optional

# https://<sub>.trycloudflare.com — the public URL cloudflared prints.
_URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com", re.IGNORECASE)


class _TunnelManager:
    def __init__(self) -> None:
        self._proc: Optional[subprocess.Popen] = None
        self._url: Optional[str] = None
        self._port: Optional[int] = None
        self._ready = False
        self._reader: Optional[threading.Thread] = None
        self._prober: Optional[threading.Thread] = None
        self._lock = threading.RLock()

    # ── introspection ────────────────────────────────────────────────
    @staticmethod
    def installed() -> bool:
        return shutil.which("cloudflared") is not None

    def _running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def status(self) -> Dict[str, object]:
        with self._lock:
            return {
                "installed": self.installed(),
                "running": self._running(),
                "url": self._url if self._running() else None,
                "port": self._port if self._running() else None,
                # ``ready`` flips True once the server confirms the public
                # URL answers from *its own* process. This is INFORMATIONAL
                # ONLY — do not gate the Multiplayer flow on it. The probe
                # resolves the trycloudflare host via the OS resolver, which
                # a corporate VPN/security agent can block even while the
                # browser (DoH / encrypted DNS) reaches the tunnel fine.
                "ready": bool(self._ready) if self._running() else False,
            }

    # ── lifecycle ────────────────────────────────────────────────────
    def start(self, port: int, *, wait_s: float = 15.0) -> Dict[str, object]:
        """Start (or reuse) a quick tunnel to ``http://localhost:<port>``.

        Blocks up to ``wait_s`` for cloudflared to print its public URL.
        Returns a status dict; ``url`` may be ``None`` with
        ``status="starting"`` if the URL hasn't appeared yet (poll
        :func:`status`)."""
        with self._lock:
            if not self.installed():
                return {
                    "ok": False,
                    "error": "cloudflared is not installed (brew install cloudflared)",
                    "installed": False,
                }
            # Reuse an existing tunnel for the same port.
            if self._running() and self._port == port:
                return {"ok": True, "url": self._url, "running": True, "reused": True}
            # A tunnel to a different port is replaced.
            if self._running():
                self._stop_locked()

            self._url = None
            self._ready = False
            self._port = int(port)
            try:
                self._proc = subprocess.Popen(
                    [
                        "cloudflared", "tunnel",
                        "--url", f"http://localhost:{int(port)}",
                        "--no-autoupdate",
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
            except OSError as exc:
                self._proc = None
                return {"ok": False, "error": f"failed to launch cloudflared: {exc}"}

            self._reader = threading.Thread(
                target=self._scrape_url, args=(self._proc,), daemon=True,
            )
            self._reader.start()

        # Poll (outside the lock) for the URL to show up.
        deadline = time.time() + wait_s
        while time.time() < deadline:
            with self._lock:
                if self._url:
                    return {"ok": True, "url": self._url, "running": True}
                if not self._running():
                    return {"ok": False, "error": "cloudflared exited before publishing a URL"}
            time.sleep(0.25)
        return {"ok": True, "url": None, "running": self._running(), "status": "starting"}

    def _scrape_url(self, proc: subprocess.Popen) -> None:
        """Read cloudflared output until the trycloudflare URL appears."""
        if proc.stdout is None:
            return
        for line in proc.stdout:
            m = _URL_RE.search(line)
            if m:
                with self._lock:
                    if self._proc is proc and self._url is None:
                        self._url = m.group(0)
                        # Start a server-side readiness probe (no CORS).
                        self._prober = threading.Thread(
                            target=self._probe_ready,
                            args=(proc, self._url),
                            daemon=True,
                        )
                        self._prober.start()
                # Keep draining so the pipe buffer never blocks the child.

    def _probe_ready(self, proc: subprocess.Popen, url: str) -> None:
        """Best-effort: hit the public URL from the server to flip ``_ready``.

        Cloudflare quick-tunnel URLs take a few seconds before DNS resolves
        and the edge starts routing. We probe ``<url>/api/meta/backend``
        (any HTTP response means the round-trip works) and flip ``_ready``.

        IMPORTANT: this uses ``urllib`` → the OS resolver, which a corporate
        VPN/security agent may block for ``*.trycloudflare.com`` even when
        the user's browser (encrypted DNS) reaches the tunnel fine. So a
        ``ready=False`` result does NOT mean the tunnel is unreachable —
        ``ready`` is purely informational and must never gate the UI."""
        target = url.rstrip("/") + "/api/meta/backend"
        deadline = time.time() + 45.0
        while time.time() < deadline:
            # Bail if this tunnel was replaced/stopped.
            with self._lock:
                if self._proc is not proc:
                    return
            if proc.poll() is not None:
                return
            try:
                req = urllib.request.Request(target, method="GET")
                with urllib.request.urlopen(req, timeout=4) as resp:
                    resp.read(1)
                with self._lock:
                    if self._proc is proc:
                        self._ready = True
                return
            except urllib.error.HTTPError:
                # An HTTP error status still proves the tunnel routes back.
                with self._lock:
                    if self._proc is proc:
                        self._ready = True
                return
            except Exception:
                time.sleep(1.0)

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
        self._ready = False


_manager = _TunnelManager()


def start(port: int, *, wait_s: float = 15.0) -> Dict[str, object]:
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
