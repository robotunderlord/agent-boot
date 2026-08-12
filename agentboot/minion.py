"""Minions: lite agents that get DOCTRINE and a bounded brief, but not the stack.

WHY A MINION IS NOT A SMALL AGENT
---------------------------------
The tempting design is a cut-down boot - same tiers, fewer steps. That is wrong, and it is wrong in
a way that costs real time: a spawned agent with a vague scope chases context everywhere, re-derives
what the parent already knew, and returns something the parent must then re-verify.

What actually keeps a spawned agent oriented is not more context. It is **boundaries**:

    a bounded errand beats a sprawling system

An errand that names its scope, its constraints, its stopping condition and its return shape keeps a
lite agent on task without any of the continuity machinery. Scope is not a limitation here - it IS
the orientation. So a minion gets no memory namespace, no tool discovery of its own, and no gate. It
gets a brief.

THE BRIEF IS GENERATED, NOT WRITTEN
-----------------------------------
This is the payoff of indexing everything by situation. Both `Ledger` and `ToolRegistry` are keyed
by how a situation is RECOGNISED, so an errand described in a sentence can be matched against both:

    errand text -> Ledger.match()        -> "you may have been here before"
                -> registry.reflex_table -> "reach for this, not that"

The parent already paid to learn those lessons and to verify those tools. Handing them down with
the errand is what stops the minion repeating work the parent already did - which is the entire
reason the ledger exists.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .lessons import Ledger, Lesson
from .tools import Tool, ToolRegistry

DEFAULT_CONSTRAINTS: tuple[str, ...] = (
    "Do only this errand. If you find other problems, REPORT them - do not fix them.",
    "Read before you assert. If you did not read it this session, say INFERRED or go look.",
    "If you cannot check something, say CANNOT CHECK and why. Never guess fluently.",
    "Do not re-derive something the brief already tells you.",
)


@dataclass(frozen=True)
class Errand:
    """One bounded task, with the four things that keep a lite agent from sprawling."""

    task: str
    done_when: str
    returns: str = "a short plain-text answer"
    constraints: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Reject an errand missing a task or a stopping condition."""
        if not self.task.strip():
            raise ValueError("an errand needs a task")
        if not self.done_when.strip():
            raise ValueError("an errand needs `done_when` - an errand with no stopping rule sprawls")


@dataclass
class Minion:
    """A lite agent: doctrine plus a bounded brief, assembled from what the parent already knows."""

    errand: Errand
    name: str = "minion"
    ledger: Ledger | None = None
    registry: ToolRegistry | None = None
    extra_constraints: tuple[str, ...] = field(default_factory=tuple)

    def lessons(self, limit: int = 3) -> list[Lesson]:
        """Return the ledger entries whose tell resembles this errand."""
        if self.ledger is None:
            return []
        return self.ledger.match(f"{self.errand.task} {self.errand.done_when}", limit=limit)

    def tools(self) -> list[Tool]:
        """Return the verified tools the parent has proven reachable."""
        if self.registry is None:
            return []
        return self.registry.verified or self.registry.tools

    def constraints(self) -> tuple[str, ...]:
        """Return the full constraint list: defaults, errand-specific, then caller-supplied."""
        return DEFAULT_CONSTRAINTS + self.errand.constraints + self.extra_constraints

    def brief(self) -> str:
        """Return the complete text to hand a spawned agent.

        Everything here is either bounded scope or something the parent already paid to learn. There
        is deliberately no continuity, no memory and no gate - a minion that needs those is not a
        minion, it is a second full agent and should be booted as one.
        """
        out = [
            f"ERRAND FOR: {self.name}",
            "",
            "You have ONE task. Do it, report, and stop.",
            "",
            f"TASK:      {self.errand.task}",
            f"DONE WHEN: {self.errand.done_when}",
            f"RETURN:    {self.errand.returns}",
            "",
            "CONSTRAINTS:",
        ]
        out += [f"  - {c}" for c in self.constraints()]

        hits = self.lessons()
        if hits:
            out += ["", "ALREADY LEARNED THE HARD WAY - do not rediscover these:", ""]
            out += [lesson.render() for lesson in hits]

        available = self.tools()
        if available:
            out += ["", "TOOLS PROVEN AVAILABLE (verified by the parent, so trust them):"]
            out += [f"  - {t.when} -> `{t.reach}`" + (f"   NOT: {t.trap}" if t.trap else "")
                    for t in available]

        out += [
            "",
            "If the errand turns out to be impossible or wrongly scoped, say so immediately and",
            "stop. Returning early with a clear reason is a success; returning something plausible",
            "you did not verify is the only real failure.",
        ]
        return "\n".join(out)

    def summary(self) -> str:
        """Return a one-line description of what this minion was handed."""
        return (f"{self.name}: 1 errand, {len(self.constraints())} constraints, "
                f"{len(self.lessons())} lessons, {len(self.tools())} tools")
