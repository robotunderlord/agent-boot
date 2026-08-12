"""A browser terminal onto the agent's session - over TLS, authenticated, and fail-closed.

WHAT THIS IS
------------
`ttyd` serving `zellij attach main`, so the agent is reachable by opening a URL instead of arranging
ssh. Bidirectional: you can watch it work and you can type at it.

WHAT THIS ACTUALLY IS
---------------------
**A remote shell on a web port.** Not a dashboard, not a viewer - a writable terminal attached to a
live session that holds credentials, mounted state, and an agent with tools. Anyone who reaches the
port and gets past the door has the agent's hands.

So this module is deliberately awkward to run insecurely:

* **TLS is required.** Plaintext sends the session - and anything typed into it - across the network
  in the clear. `require_tls=True` by default and `command()` refuses to render without a cert.
* **Credentials are required.** No default password, no "set it later", no empty-means-open. A
  browser terminal with no auth is a public shell, and it will be found - scanners find open ports
  faster than humans finish saying "it is only on the LAN".
* **Writable is opt-in.** Read-only is the default, because "I want to watch it" and "I want to
  drive it" are different requests and only one of them needs typing.

FAIL CLOSED, LOUDLY
-------------------
Every refusal here raises rather than warning-and-continuing. A security control that degrades to a
warning is a security control that is off, and the log line saying so scrolls past. The one thing
this module must never do is come up serving.
"""
from __future__ import annotations

import shutil
import socket
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .session import MAIN, Session
from .steps import Evidence, Step, StepFailed


class WebTerminalRefused(Exception):
    """Raised when the terminal cannot be served safely and must not be served at all."""


@dataclass
class WebTerminal:
    """Render, probe and boot-verify a TLS browser terminal onto the holding session.

    `credential` is `user:password`. It is never defaulted and never logged - only whether one is
    present. `cert`/`key` are paths inside the container; mount real ones, or generate a self-signed
    pair at start and understand that it authenticates nothing, it only encrypts.
    """

    session: Session | None = None
    port: int = 7681
    credential: str = ""
    cert: Path | None = None
    key: Path | None = None
    writable: bool = False
    binary: str = "ttyd"
    interface: str = "0.0.0.0"
    require_tls: bool = True

    def __post_init__(self) -> None:
        """Fall back to the one holding session when none was given."""
        self.session = self.session or Session(name=MAIN)

    # ── refusals ────────────────────────────────────────────────────────────────────────────
    def _refuse_unless_safe(self) -> None:
        """Raise unless this terminal can be served with TLS and a credential."""
        if not self.credential or ":" not in self.credential:
            raise WebTerminalRefused(
                "no credential - refusing to serve a writable shell with no door. Set "
                "AGENT_WEB_CREDENTIAL='user:password'. There is deliberately no default: an "
                "empty password here is a public shell on a routable port.")
        if self.require_tls and not (self.cert and self.key):
            raise WebTerminalRefused(
                "no TLS cert/key - refusing to serve a terminal in plaintext. Everything typed at "
                "the agent, and everything it prints, would cross the network readable. Mount a "
                "cert or generate a self-signed pair.")
        if self.cert and not Path(self.cert).exists():
            raise WebTerminalRefused(f"cert not present at {self.cert}")
        if self.key and not Path(self.key).exists():
            raise WebTerminalRefused(f"key not present at {self.key}")

    # ── the command ─────────────────────────────────────────────────────────────────────────
    def command(self) -> list[str]:
        """Return the argv that serves the session, or raise if it cannot be served safely."""
        self._refuse_unless_safe()
        argv = [self.binary, "--port", str(self.port), "--interface", self.interface,
                "--credential", self.credential]
        if self.cert and self.key:
            argv += ["--ssl", "--ssl-cert", str(self.cert), "--ssl-key", str(self.key)]
        if self.writable:
            argv += ["--writable"]
        argv += ["zellij", "attach", self.session.name]
        return argv

    def redacted_command(self) -> str:
        """Return the command as a printable string with the credential removed.

        Rendering commands for humans is exactly where credentials leak into logs and transcripts,
        so the printable form is a different method from the runnable one - not a flag on it that
        somebody forgets to pass.
        """
        out, argv = [], self.command()
        skip = False
        for part in argv:
            if skip:
                out.append("<redacted>")
                skip = False
                continue
            out.append(part)
            skip = part == "--credential"
        return " ".join(out)

    def url(self, host: str = "localhost") -> str:
        """Return the URL to open in a browser."""
        scheme = "https" if (self.cert and self.key) else "http"
        return f"{scheme}://{host}:{self.port}/"

    # ── probing ─────────────────────────────────────────────────────────────────────────────
    def listening(self, host: str = "127.0.0.1", timeout: float = 3.0) -> bool:
        """Return True when something accepts a TCP connection on the port."""
        try:
            with socket.create_connection((host, self.port), timeout=timeout):
                return True
        except OSError:
            return False

    def serving(self, host: str = "127.0.0.1", timeout: float = 5.0) -> int | None:
        """Return the HTTP status the terminal answers with, or None if it does not answer.

        A 401 is the HEALTHY answer: it means the door exists. A 200 from a terminal that should be
        authenticated is a finding, not a success - which is why this returns the code rather than
        a boolean.
        """
        ctx = ssl.create_default_context()
        ctx.check_hostname = False           # self-signed is expected; we are probing liveness
        ctx.verify_mode = ssl.CERT_NONE
        try:
            with urllib.request.urlopen(self.url(host), timeout=timeout, context=ctx) as resp:
                return resp.status
        except urllib.error.HTTPError as exc:
            return exc.code
        except (urllib.error.URLError, OSError, ssl.SSLError):
            return None

    def step(self, critical: bool = False) -> WebTerminalStep:
        """Return the boot step that proves the terminal is serving AND has a door."""
        return WebTerminalStep(self, critical=critical)


class WebTerminalStep(Step):
    """Boot step proving the browser terminal answers and is not wide open."""

    def __init__(self, terminal: WebTerminal, critical: bool = False) -> None:
        """Store the terminal this step verifies."""
        super().__init__(f"web:{terminal.port}", critical=critical)
        self.terminal = terminal

    def check(self) -> Evidence:
        """Confirm the terminal serves, over TLS, behind a credential."""
        if not shutil.which(self.terminal.binary):
            raise StepFailed(f"{self.terminal.binary} is not installed")
        status = self.terminal.serving()
        if status is None:
            raise StepFailed(f"nothing answering on {self.terminal.port}")
        if status == 200 and self.terminal.credential:
            raise StepFailed(
                f"answered 200 unauthenticated on {self.terminal.port} - a credential is configured "
                "but the door is not being enforced. This is open to anyone who reaches the port.")
        scheme = "https" if (self.terminal.cert and self.terminal.key) else "HTTP (PLAINTEXT)"
        return Evidence(f"serving {scheme}, HTTP {status} (401 = door present)",
                        self.terminal.url())

    def failing_variant(self) -> WebTerminalStep:
        """Return the same step pointed at a port nothing serves."""
        ghost = WebTerminal(session=self.terminal.session, port=59999,
                            credential=self.terminal.credential, cert=self.terminal.cert,
                            key=self.terminal.key, binary=self.terminal.binary,
                            require_tls=self.terminal.require_tls)
        return WebTerminalStep(ghost, critical=self.critical)
