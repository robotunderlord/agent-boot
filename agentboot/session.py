"""Hold the agent inside a multiplexer session, so its life is not the connection's life.

THE PROBLEM
-----------
The obvious way to run an agent in a container is to make it the container's foreground process, or
to reach it with `docker exec -it ... <agent>`. Both tie the agent's existence to a connection:

* as PID 1, every restart of the container is an amnesia event, and any crash takes the session
* under `exec`, closing the terminal - or losing the network for four seconds - kills the agent
  mid-thought, and whatever it had not written down is gone

Neither is survivable for something meant to run for days. The agent needs to be **isolated from the
session that reaches it**.

THE SHAPE
---------
Run a multiplexer inside the container and put the agent inside a named session in it:

    container
      |- zellij session "agent"     <- the agent lives HERE, keeps running when nobody is attached
      |- sshd / exec / attach       <- a WAY IN, not the thing the agent depends on

Three properties fall out, and all three are the point:

1. **Detach-survivable.** Closing your terminal detaches. The agent never notices.
2. **Re-attachable from anywhere.** `docker exec -it <c> zellij attach agent` is a remote connection
   method; so is ssh-then-attach. The way in is now interchangeable.
3. **Isolated lifecycle.** A wedged connection, a dropped VPN, a reboot of YOUR machine - none of
   them are events in the agent's life.

THE LANDMINE, VERIFIED (zellij 0.44.3)
--------------------------------------
`zellij list-sessions` PRINTS DEAD SESSIONS. An exited session is listed by name exactly like a live
one, and `--short` strips the very marker that distinguishes them:

    $ zellij list-sessions --short
    agent-side          <- EXITED weeks ago
    agent-main          <- actually running

So `list-sessions --short | grep <name>` is a check that cannot fail, and it will report a dead agent
as healthy. The liveness probe must use `--no-formatting` and reject any entry marked `EXITED`. This
is the module's own instance of the rule it exists to serve: the listing is the indicator, the
running session is the artifact.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .steps import Evidence, Step, StepFailed

EXITED = re.compile(r"\bEXITED\b", re.I)

# There is exactly ONE holding session and it IS the main loop.
#
# The temptation is a session per task - a side session for this ticket, another for that errand.
# Resist it: a second session is a second AGENT, with its own context and its own idea of where the
# work stands, and now two of them are writing the same running thread. That is not parallelism, it
# is a split brain with no merge.
#
# Bounded side-work belongs to a MINION (see minion.py): one errand, a generated brief, a result
# handed back to the one main loop. The loop stays single.
MAIN = "main"


@dataclass(frozen=True)
class Session:
    """The named multiplexer session that holds the agent's main loop."""

    name: str = MAIN
    layout: Path | None = None
    config_dir: Path | None = None

    def __post_init__(self) -> None:
        """Reject a session with no name - `attach` needs something to name."""
        if not self.name.strip():
            raise ValueError("a session needs a name; attach has to be able to ask for it")

    @classmethod
    def for_agent(cls, agent: str, **kw) -> Session:
        """Return the canonical holding session for a named agent: `<agent>-main`.

        The suffix is not decoration. It states in the session list that this is THE main loop, so a
        second session sitting beside it is visibly an anomaly rather than a peer.
        """
        return cls(name=f"{agent.strip()}-{MAIN}", **kw)


class SessionHost:
    """Start, probe and reach a multiplexer session holding the agent.

    Nothing here assumes it is running inside the container. The commands are rendered as strings so
    an operator, an entrypoint or an installing agent can all use the same source of truth for how
    this seat is reached.
    """

    def __init__(self, session: Session | None = None, binary: str = "zellij") -> None:
        """Store the session definition and which multiplexer binary to drive."""
        self.session = session or Session()
        self.binary = binary

    # ── availability ────────────────────────────────────────────────────────────────────────
    def available(self) -> bool:
        """Return True when the multiplexer is actually installed."""
        return shutil.which(self.binary) is not None

    def _list(self) -> str:
        """Return the raw, unformatted session listing, or an empty string if it cannot be read."""
        try:
            proc = subprocess.run([self.binary, "list-sessions", "--no-formatting"],
                                  capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            return ""
        # zellij exits non-zero when there are no sessions at all; that is not an error here.
        return proc.stdout

    def sessions(self) -> dict[str, bool]:
        """Return every listed session mapped to whether it is actually ALIVE.

        The `alive` flag is the whole reason this returns a dict rather than a list of names: a dead
        session is listed identically to a live one, so the name alone is not an answer.
        """
        out: dict[str, bool] = {}
        for line in self._list().splitlines():
            line = line.strip()
            if not line:
                continue
            name = line.split()[0]
            out[name] = not EXITED.search(line)
        return out

    def alive(self, name: str | None = None) -> bool:
        """Return True only when the named session exists AND is not exited."""
        return self.sessions().get(name or self.session.name, False)

    # ── commands (rendered, never guessed at the call site) ─────────────────────────────────
    def start_command(self) -> str:
        """Return the command that starts the holding session.

        What runs inside it is the layout's business, not this function's - the layout is the single
        place that decides what the main loop actually is.
        """
        parts = [self.binary]
        if self.session.layout:
            parts += ["--layout", str(self.session.layout)]
        parts += ["--session", self.session.name]
        return " ".join(parts)

    def attach_command(self, container: str = "", host: str = "") -> str:
        """Return the command that reaches the running agent, from wherever you are.

        Four addresses, one session. The way in is interchangeable precisely because the agent does
        not depend on any of them:

            local             zellij attach <name>
            container         docker exec -it <c> zellij attach <name>
            remote            ssh -t <host> zellij attach <name>
            remote+container  ssh -t <host> docker exec -it <c> zellij attach <name>

        `ssh -t` is not optional. Without a forced TTY, ssh runs the command non-interactively, and a
        multiplexer attach with no terminal either refuses outright or renders unusable garbage - a
        failure that reads like "the agent is broken" when the agent is perfectly fine and you simply
        did not give it a terminal. Same reason `docker exec` needs `-it`.
        """
        cmd = f"{self.binary} attach {self.session.name}"
        if container:
            cmd = f"docker exec -it {container} {cmd}"
        if host:
            cmd = f"ssh -t {host} {cmd}"
        return cmd

    def kill_command(self) -> str:
        """Return the command that ends the session deliberately."""
        return f"{self.binary} delete-session {self.session.name} --force"

    # ── boot integration ────────────────────────────────────────────────────────────────────
    def step(self, critical: bool = True) -> SessionStep:
        """Return the boot step that proves the agent's session is live, not merely listed."""
        return SessionStep(self, critical=critical)


class SessionStep(Step):
    """Boot step proving the holding session exists AND is running."""

    def __init__(self, host: SessionHost, critical: bool = True) -> None:
        """Store the host whose session this step verifies."""
        super().__init__(f"session:{host.session.name}", critical=critical)
        self.host = host

    def check(self) -> Evidence:
        """Confirm the session is present and not exited."""
        if not self.host.available():
            raise StepFailed(f"{self.host.binary} is not installed - nothing is holding the agent")
        found = self.host.sessions()
        name = self.host.session.name
        if name not in found:
            raise StepFailed(f"no session named {name!r} (listed: {sorted(found) or 'none'})")
        if not found[name]:
            raise StepFailed(
                f"session {name!r} is listed but EXITED - the agent is dead and the listing "
                "still shows its name, which is exactly the trap this probe exists for")
        return Evidence(f"live, detach-survivable ({self.host.attach_command()})", "list-sessions")

    def failing_variant(self) -> SessionStep:
        """Return the same step pointed at a session name that cannot exist."""
        ghost = Session(name=f"{self.host.session.name}--absent",
                        layout=self.host.session.layout,
                        config_dir=self.host.session.config_dir)
        return SessionStep(SessionHost(ghost, self.host.binary), critical=self.critical)
