"""Reflexes: make what the agent HAS reachable without it having to remember it has it.

THE FAILURE THIS CLOSES
-----------------------
A tool can be installed, verified, and documented, and still never get used - because at the moment
a situation arises, nothing connects the situation to the tool. The agent hand-greps its way to a
worse answer with a better one sitting right there. Same for a lesson: recorded, indexed, and never
consulted, because consulting it requires already suspecting it exists.

    Loaded but unseen is not loaded.
    Resident without reflex is invisible.

A reflex is the missing link, and it is a specific shape:

    SITUATION  ->  REACH FOR THIS  ->  NOT THAT (the tempting wrong move)

The third column is what makes it a reflex rather than an index. Naming the trap is what stops the
agent doing the wrong thing faster - a list of capabilities does not compete with a habit, but
"not that" does.

GENERATED, NEVER HAND-MAINTAINED
--------------------------------
This file is assembled from things that were PROVEN this boot: tools whose probe returned, and
lessons that actually loaded. That is the whole reason it can be trusted at a glance.

A hand-written reflex table rots silently - it keeps advertising a tool that was removed, and the
agent reaches for something that is not there, at exactly the moment it is under pressure. Here, a
tool that fails its probe simply does not appear. The table cannot lie about the present because it
is rebuilt from the present.

RESIDENT, NOT RETRIEVABLE
-------------------------
The output is written where a hook can `cat` it every turn. Anything consulted on nearly every turn
should not be a lookup: the measured gradient (research/EXP-003) puts resident context at 0.1ms and
a multi-hop recall at 4.4s - four orders of magnitude. A reflex that has to be retrieved has already
failed to be a reflex.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .lessons import Ledger
from .tools import ToolRegistry

HEADER = ">>> REFLEXES - reach for these; the trap column is what NOT to do instead <<<"


@dataclass
class Reflexes:
    """Assemble a resident reflex table from what was actually proven this boot."""

    registry: ToolRegistry | None = None
    ledger: Ledger | None = None
    extra: tuple[tuple[str, str, str], ...] = field(default_factory=tuple)

    def rows(self) -> list[tuple[str, str, str]]:
        """Return (situation, reach, trap) rows, tools first, then lessons.

        Only VERIFIED tools appear. A tool whose probe failed is not a reflex, it is a lure.
        """
        out: list[tuple[str, str, str]] = []
        if self.registry is not None:
            for tool in (self.registry.verified or []):
                out.append((tool.when, tool.reach, tool.trap or "-"))
        if self.ledger is not None:
            for lesson in self.ledger.lessons:
                out.append((lesson.tell, lesson.trade, f"[{lesson.id}] the cost: {lesson.cost or 'an evening'}"))
        out.extend(self.extra)
        return out

    def render(self) -> str:
        """Return the resident reflex block, or an honest statement that there is nothing to reach for."""
        rows = self.rows()
        if not rows:
            return (f"{HEADER}\n\n  (nothing verified this boot - no tools probed green and no "
                    "lessons loaded. That is a finding, not an empty file.)\n")
        lines = [HEADER, ""]
        for situation, reach, trap in rows:
            lines.append(f"  WHEN  {situation}")
            lines.append(f"  REACH {reach}")
            if trap and trap != "-":
                lines.append(f"  NOT   {trap}")
            lines.append("")
        lines.append(f"  ({len(rows)} reflexes, assembled from what was PROVEN this boot - "
                     "a tool that failed its probe is absent by construction.)")
        return "\n".join(lines)

    def write(self, payload_dir: Path | str) -> Path:
        """Write the reflex block where a hook can make it resident, and return the path.

        Overwritten every boot ON PURPOSE - unlike the nags and the tattoo, this file is DERIVED.
        Preserving local edits here would mean preserving a claim about a tool that may no longer
        verify, which is the exact rot this module exists to prevent.
        """
        target = Path(payload_dir) / "reflexes.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.render() + "\n", encoding="utf-8")
        return target

    def summary(self) -> str:
        """Return a one-line count of what became reflexive."""
        tools = len(self.registry.verified) if self.registry and self.registry.verified else 0
        lessons = len(self.ledger.lessons) if self.ledger else 0
        return f"{len(self.rows())} reflexes ({tools} from verified tools, {lessons} from the ledger)"
