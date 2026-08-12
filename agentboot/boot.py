"""The tiered boot runner, and the gate that stops an agent reasoning from memory it has not proven.

WHY THE ORDER IS THE ORDER
--------------------------
Procedural and semantic memory survive amnesia; episodic memory does not. An agent never wakes
unable to use a tool or unaware that it has a filesystem - what it loses is *what it was doing*,
and that is uninterpretable without the frame. So the frame loads first and the volatile tier
loads last, nearest the first real request:

    1  ENABLERS ....... can I act, and as whom
    2  PERSONALITY .... who I am
    3  RESOURCES ...... what I can do and reach
    -- GATE --------------------------------------
    4  MEMORIES ....... what I was doing        <- LAST, and only if the gate is green

Enablers come first because everything downstream is unreachable without them, and you find out
by failing at the worst moment rather than at boot.

THE GATE IS THE POINT
---------------------
A boot that prints warnings and proceeds anyway is decoration. `Boot` refuses to run the
memory tier when any critical step is red, because the failure this prevents is *reasoning
confidently from a memory of a fact instead of the fact* - which is precisely the failure that a
long agent session produces, and precisely the one that costs a human their evening.

The gate is a hard stop, not a warning.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .status import Status, StatusLine
from .steps import Result, Step


@dataclass
class Tier:
    """One numbered stage of the boot, holding the steps that belong to it."""

    number: int
    name: str
    steps: list[Step] = field(default_factory=list)
    gated: bool = False

    def add(self, *steps: Step) -> Tier:
        """Append steps to this tier and return self, so tiers can be built fluently."""
        self.steps.extend(steps)
        return self

    def header(self) -> str:
        """Return the tier's banner line."""
        return f"--- Tier {self.number} - {self.name.upper()} " + "-" * max(0, 52 - len(self.name))


class Boot:
    """Run a tiered boot, render it as a systemd-style log, and hold a hard gate before memory.

    Build it with the tiers you want, then call `run()`. Nothing here knows about any particular
    environment - a step is whatever you make it, and the framework only enforces that steps
    cannot claim more than they proved.
    """

    def __init__(self, tiers: list[Tier], *, width: int = 14) -> None:
        """Store the tiers to run and the label width used to align the log."""
        self.tiers = tiers
        self.width = width
        self.results: list[Result] = []
        self._gate_open = True

    @property
    def critical_failures(self) -> list[Result]:
        """Return the results of every critical step that came back red."""
        critical = {s.label for tier in self.tiers for s in tier.steps if s.critical}
        return [r for r in self.results if r.status.is_red and r.step in critical]

    def _emit(self, line: StatusLine | str) -> None:
        """Print one line of the boot log."""
        print(line if isinstance(line, str) else line.render())

    def _run_tier(self, tier: Tier) -> None:
        """Run every step in a tier and emit its lines."""
        self._emit("")
        self._emit(tier.header())
        for step in tier.steps:
            result = step.run()
            self.results.append(result)
            self._emit(result.line(self.width))

    def _emit_gate(self) -> None:
        """Emit the recall gate verdict and record whether the memory tier may load."""
        failures = self.critical_failures
        self._emit("")
        self._emit("-" * 62)
        if failures:
            self._gate_open = False
            names = ", ".join(f.step for f in failures)
            self._emit(StatusLine(Status.FAIL, "Recall gate", f"HELD - critical red: {names}").render())
            self._emit("  REGROUND. Do not reason from memory; do not improvise. Fix the red lines first.")
        else:
            self._emit(StatusLine(Status.OK, "Recall gate", "GREEN - cleared to work").render())
        self._emit("-" * 62)

    def run(self) -> int:
        """Run every tier in order, holding the gated tiers if a critical step failed.

        Returns 0 when the gate is green, 1 when it is held.
        """
        for tier in self.tiers:
            if tier.gated:
                self._emit_gate()
                if not self._gate_open:
                    self._emit("")
                    self._emit(StatusLine(Status.STUB, f"Tier {tier.number}", "NOT LOADED - gate held").render())
                    continue
            self._run_tier(tier)
        self._emit("")
        self._emit(" " * 56 + "Ready." if self._gate_open else " " * 48 + "NOT READY - reground.")
        return 0 if self._gate_open else 1

    def prove(self) -> int:
        """Run every step's failing variant and report any check that cannot fail.

        A green `run()` proves the estate is healthy. Only this proves the BOOT is.
        """
        print("--- prove: every check must be able to fail ---")
        bad = 0
        for tier in self.tiers:
            for step in tier.steps:
                result = step.prove()
                if result.status.is_red:
                    bad += 1
                print(result.line(self.width).render())
        print()
        if bad:
            print(f"[ !! ] {bad} check(s) CANNOT FAIL - they are wired to nothing and prove nothing.")
            return 1
        print("[ OK ] every check demonstrated a real failure mode.")
        return 0
