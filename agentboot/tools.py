"""The tool registry: connect the tools the agent ships with, then discover what the environment adds.

THE PROBLEM THIS SOLVES
-----------------------
An agent that *has* a capability but does not reach for it does not have it. The characteristic
waste is not a missing tool - it is a tool sitting on disk, documented, while the agent hand-greps
its way to a worse answer because nothing connected the SITUATION to the TOOL.

So a `Tool` here is not a path. It is a triple:

    when   - the question shape that should trigger it   ("where does a credential live?")
    reach  - what to actually run
    trap   - the tempting wrong move it replaces         (grepping the whole vault)

The `when` field is the part that matters and the part usually missing. A registry keyed by tool
name answers "what do I have"; a registry keyed by situation answers "what do I do now", which is
the only question an agent actually asks.

TWO SOURCES, ONE RULE
---------------------
**Connected** tools ship with the image - the agent knows them because it was built with them.
**Learned** tools are discovered from the environment at boot: a container gets mounted a store, a
workstation has a CLI on PATH, a seat has credentials the image never carried. The image cannot
know these, and hardcoding them makes the image unportable.

The rule that applies to both: **a tool you claim but never probe is a lie.** `as_tier()` turns
every registered tool into a verified boot step, and `reflex_table()` renders only the tools that
actually came back green - so an agent can never be pointed at a capability that is not there.
"""
from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .boot import Tier
from .steps import CommandStep

MANIFEST_ENV = "AGENTBOOT_TOOLS"


@dataclass(frozen=True)
class Tool:
    """A capability, described by the situation that should trigger it.

    `probe` and `marker` are what make the entry honest: the boot runs the probe and requires the
    marker in its output before the tool is allowed to appear in the reflex table.
    """

    name: str
    when: str
    reach: str
    probe: str = ""
    marker: str = ""
    trap: str = ""
    origin: str = "connected"
    critical: bool = False

    def __post_init__(self) -> None:
        """Reject a tool that cannot say when it should be used."""
        if not self.name.strip():
            raise ValueError("a tool needs a name")
        if not self.when.strip():
            raise ValueError(f"tool {self.name!r} needs a `when` - a tool with no trigger is never reached for")

    @property
    def probe_command(self) -> str:
        """Return the command used to verify the tool, defaulting to a presence check."""
        if self.probe:
            return self.probe
        binary = self.reach.split()[0] if self.reach.strip() else self.name
        return f"command -v {binary}"

    @property
    def probe_marker(self) -> str:
        """Return the marker the probe output must contain."""
        if self.marker:
            return self.marker
        return self.reach.split()[0] if self.reach.strip() else self.name

    def step(self) -> CommandStep:
        """Return the boot step that verifies this tool is genuinely reachable."""
        return CommandStep(self.name, self.probe_command, marker=self.probe_marker,
                           critical=self.critical)

    @classmethod
    def from_dict(cls, data: dict, origin: str = "learned") -> Tool:
        """Build a tool from a manifest entry, ignoring unknown keys."""
        known = {f for f in cls.__dataclass_fields__}
        payload = {k: v for k, v in data.items() if k in known}
        payload.setdefault("origin", origin)
        return cls(**payload)


@dataclass
class ToolRegistry:
    """Hold the connected tools, discover learned ones, and prove every claim before publishing it."""

    tools: list[Tool] = field(default_factory=list)
    verified: list[Tool] = field(default_factory=list)

    def register(self, *tools: Tool) -> ToolRegistry:
        """Add tools to the registry and return self so registration can chain."""
        self.tools.extend(tools)
        return self

    # ── discovery ───────────────────────────────────────────────────────────────────────────
    def discover(self, env: dict | None = None, tools_dir: Path | str | None = None) -> list[Tool]:
        """Find tools the environment offers that the image never carried.

        Two sources, both optional and both non-fatal - a malformed manifest must never take the
        boot down, because the boot is what you need in order to diagnose it.

        1. `AGENTBOOT_TOOLS` - os.pathsep-separated JSON manifest paths
        2. `<tools_dir>/*.json` - dropped-in manifests, the way a container declares what it mounted
        """
        env = os.environ if env is None else env
        found: list[Tool] = []
        paths: list[Path] = []

        raw = env.get(MANIFEST_ENV, "")
        paths += [Path(p) for p in raw.split(os.pathsep) if p.strip()]

        directory = Path(tools_dir) if tools_dir else Path.home() / ".agentboot" / "tools.d"
        if directory.is_dir():
            paths += sorted(directory.glob("*.json"))

        for path in paths:
            found += self._load_manifest(path)

        self.tools.extend(found)
        return found

    @staticmethod
    def _load_manifest(path: Path) -> list[Tool]:
        """Parse one manifest, reporting and skipping anything malformed."""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"[WARN] tool manifest unreadable, skipped: {path} ({exc})")
            return []
        entries = data.get("tools", data) if isinstance(data, dict) else data
        if not isinstance(entries, list):
            print(f"[WARN] tool manifest is not a list of tools, skipped: {path}")
            return []
        out = []
        for entry in entries:
            try:
                out.append(Tool.from_dict(entry))
            except (TypeError, ValueError) as exc:
                print(f"[WARN] bad tool entry in {path}, skipped: {exc}")
        return out

    def discover_on_path(self, *names: str, when: str = "", trap: str = "") -> list[Tool]:
        """Register any of `names` that are present on PATH, as learned tools."""
        found = [
            Tool(name=n, when=when or f"a task that {n} handles", reach=n, origin="learned")
            for n in names if shutil.which(n)
        ]
        self.tools.extend(found)
        return found

    # ── verification ────────────────────────────────────────────────────────────────────────
    def as_tier(self, number: int = 3, name: str = "resources") -> Tier:
        """Return a boot tier that probes every registered tool.

        Nothing is taken on faith: a tool appears in the reflex table only after its probe returns
        the marker it promised.
        """
        return Tier(number, name).add(*[t.step() for t in self.tools])

    def verify(self) -> list[Tool]:
        """Probe every tool and record which ones are genuinely reachable."""
        self.verified = [t for t in self.tools if not t.step().run().status.is_red]
        return self.verified

    # ── the reflex table ────────────────────────────────────────────────────────────────────
    def reflex_table(self, only_verified: bool = True) -> str:
        """Render SITUATION -> REACH -> TRAP for tools proven to exist.

        This is the artifact the agent actually consumes. It is generated rather than hand-written
        precisely so it cannot rot: a tool that stopped answering drops out of the table instead of
        luring the next session toward something that is gone.
        """
        tools = self.verified if only_verified else self.tools
        if not tools:
            return "(no verified tools - nothing to reach for)"
        rows = ["| when you need... | reach for | not (the trap) |", "|---|---|---|"]
        rows += [f"| {t.when} | `{t.reach}` | {t.trap or '-'} |" for t in tools]
        return "\n".join(rows)

    def summary(self) -> str:
        """Return a one-line count of connected vs learned vs verified."""
        connected = sum(1 for t in self.tools if t.origin == "connected")
        learned = len(self.tools) - connected
        return f"{len(self.tools)} tools ({connected} connected, {learned} learned), {len(self.verified)} verified"
