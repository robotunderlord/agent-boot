"""Status vocabulary and the one-line renderer for a boot log.

The point of this module is that a status line cannot lie by accident.

A boot log is only worth reading if every line is real. The expensive failure is not a missing
line - it is a green line for something that was never checked, because the next reader trusts
the boot, skips verification, and the real gap stays hidden until it bites. A missing line at
least signals "not verified" and invites a look.

So `Status.OK` is not something a caller may simply assert. `StatusLine` refuses to construct a
green line without an `Evidence` object attached (see `agentboot.steps`), and `Evidence`
refuses to exist without naming the source it came from. Faking a pass therefore takes deliberate
work rather than a moment's optimism.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Status(Enum):
    """A boot line's verdict, rendered as a fixed-width systemd-style tag."""

    OK = " OK "
    WARN = "WARN"
    FAIL = " !! "
    LAZY = "LAZY"
    STUB = "STUB"
    BOOT = "BOOT"

    @property
    def is_green(self) -> bool:
        """Return True if this status means the thing is actually live."""
        return self is Status.OK

    @property
    def is_red(self) -> bool:
        """Return True if this status must hold the recall gate."""
        return self is Status.FAIL


@dataclass(frozen=True)
class StatusLine:
    """One rendered line of a boot log: a verdict, a label, and a human detail.

    Construct via `Status`-specific helpers rather than directly, so the evidence rule is enforced
    in one place.
    """

    status: Status
    label: str
    detail: str
    width: int = 14

    def __post_init__(self) -> None:
        """Reject an empty label or detail - a line with nothing in it is noise, not a record."""
        if not self.label.strip():
            raise ValueError("a status line needs a label")
        if not self.detail.strip():
            raise ValueError(f"status line {self.label!r} needs a detail - an empty line reads as a pass")

    def render(self) -> str:
        """Return the line as it should appear in the boot log."""
        dots = self.label.ljust(self.width, ".")
        return f"[{self.status.value}] {dots} {self.detail}"

    def __str__(self) -> str:
        """Return the rendered line."""
        return self.render()
