"""Boot steps, and the evidence rule that stops a step reporting success it did not earn.

Two ideas carry this module.

**Evidence, or it did not happen.** A step reports `OK` by RETURNING an `Evidence` object naming
what it observed and where it came from. It cannot report `OK` by saying so. A step that returns
nothing is recorded as a failure, not a pass - because "the function ran and said nothing" and
"the function verified the thing" are otherwise indistinguishable.

**A check you have never watched fail is indistinguishable from a check wired to nothing.** Every
step therefore implements `failing_variant()`, returning a copy of itself rigged to fail. `prove()`
runs it and asserts it actually goes red. A step whose failing variant passes is a step wired to
nothing, and the framework says so out loud instead of quietly counting it as healthy.
"""
from __future__ import annotations

import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from .status import Status, StatusLine


class StepFailed(Exception):
    """Raised by a step that could not verify what it claims to verify."""


@dataclass(frozen=True)
class Evidence:
    """Proof that a step observed something real.

    `detail` is what the boot log shows. `source` is where it came from - a path, a command, a URL.
    Both are mandatory: evidence that cannot name its source is an assertion wearing a lab coat.
    """

    detail: str
    source: str

    def __post_init__(self) -> None:
        """Reject evidence with no detail or no source."""
        if not self.detail.strip():
            raise ValueError("evidence needs a detail")
        if not self.source.strip():
            raise ValueError("evidence needs a source - unsourced evidence is an assertion")


@dataclass(frozen=True)
class Result:
    """The outcome of running one step: a verdict plus the evidence or the reason there is none."""

    step: str
    status: Status
    detail: str

    def line(self, width: int = 14) -> StatusLine:
        """Return this result as a renderable boot-log line."""
        return StatusLine(self.status, self.step, self.detail, width)


class Step(ABC):
    """One thing a boot verifies.

    Subclasses implement `check()`, which either returns `Evidence` or raises `StepFailed`. They
    also implement `failing_variant()` so the step can be proven capable of failing.
    """

    def __init__(self, label: str, *, critical: bool = False) -> None:
        """Store the step's boot-log label and whether it can hold the gate."""
        self.label = label
        self.critical = critical

    @abstractmethod
    def check(self) -> Evidence:
        """Verify the thing and return evidence, or raise `StepFailed`."""

    @abstractmethod
    def failing_variant(self) -> Step:
        """Return a copy of this step rigged so that `check()` must fail."""

    def run(self) -> Result:
        """Run the step and convert its outcome into a `Result`.

        A step that returns no evidence is recorded FAIL. That is deliberate: silence is the
        signature of a check wired to nothing, and it must never render as a pass.
        """
        try:
            evidence = self.check()
        except StepFailed as exc:
            return Result(self.label, Status.FAIL, str(exc))
        except Exception as exc:  # noqa: BLE001 - a step must never take the whole boot down
            return Result(self.label, Status.FAIL, f"{type(exc).__name__}: {exc}")
        if evidence is None:
            return Result(self.label, Status.FAIL, "returned no evidence (a check wired to nothing)")
        return Result(self.label, Status.OK, evidence.detail)

    def prove(self) -> Result:
        """Run this step's failing variant and confirm it actually goes red.

        This is the only way to distinguish a check that passes from a check that cannot fail.
        """
        outcome = self.failing_variant().run()
        if outcome.status.is_red:
            return Result(self.label, Status.OK, "provably able to fail")
        return Result(self.label, Status.FAIL, "FAILING VARIANT PASSED - this check is wired to nothing")


class FileStep(Step):
    """Verify that a file exists, is non-trivial, and optionally contains a marker."""

    def __init__(self, label: str, path: Path | str, *, marker: str = "", min_bytes: int = 1,
                 critical: bool = False) -> None:
        """Store the path, the optional required marker, and the minimum acceptable size."""
        super().__init__(label, critical=critical)
        self.path = Path(path)
        self.marker = marker
        self.min_bytes = min_bytes

    def check(self) -> Evidence:
        """Confirm the file is present, large enough, and carries its marker."""
        if not self.path.exists():
            raise StepFailed(f"missing: {self.path}")
        size = self.path.stat().st_size
        if size < self.min_bytes:
            raise StepFailed(f"{self.path} is {size} b, under the {self.min_bytes} b floor")
        if self.marker:
            text = self.path.read_text(encoding="utf-8", errors="replace")
            if self.marker not in text:
                raise StepFailed(f"{self.path} lacks marker {self.marker!r} - present but not the real file")
        return Evidence(f"{self.path.name} ({size} b)", str(self.path))

    def failing_variant(self) -> FileStep:
        """Return the same step pointed at a path that cannot exist."""
        return FileStep(self.label, self.path.with_name(f"{self.path.name}.__nope__"),
                        marker=self.marker, min_bytes=self.min_bytes, critical=self.critical)


class CommandStep(Step):
    """Run a command and require a marker in its output.

    Exit 0 is not evidence. A command can succeed while producing nothing useful, and a fallback
    can answer in place of the thing you meant to probe, so the marker - not the return code - is
    what this step believes.
    """

    def __init__(self, label: str, command: str, *, marker: str, timeout: int = 10,
                 critical: bool = False) -> None:
        """Store the command, the marker its output must contain, and a timeout."""
        super().__init__(label, critical=critical)
        self.command = command
        self.marker = marker
        self.timeout = timeout

    def check(self) -> Evidence:
        """Execute the command and confirm the marker appears in stdout."""
        try:
            proc = subprocess.run(self.command, shell=True, capture_output=True, text=True,
                                  timeout=self.timeout)
        except subprocess.TimeoutExpired:
            raise StepFailed(f"timed out after {self.timeout}s: {self.command}") from None
        except OSError as exc:
            raise StepFailed(f"could not run: {exc}") from None
        if self.marker not in proc.stdout:
            raise StepFailed(f"ran (rc={proc.returncode}) but marker {self.marker!r} absent - wired to nothing")
        return Evidence(f"fired, {len(proc.stdout)} b, marker present", self.command)

    def failing_variant(self) -> CommandStep:
        """Return the same step demanding a marker no output can contain."""
        return CommandStep(self.label, self.command, marker="__MARKER_THAT_CANNOT_EXIST__",
                           timeout=self.timeout, critical=self.critical)


class LazyStep(Step):
    """A deliberately deferred step - declared, not loaded, and honestly labelled as such."""

    def __init__(self, label: str, detail: str = "on demand") -> None:
        """Store what would be loaded, so the boot log records the deferral rather than hiding it."""
        super().__init__(label, critical=False)
        self.detail = detail

    def check(self) -> Evidence:
        """Never called - `run()` is overridden to report LAZY."""
        raise StepFailed("lazy steps are not checked")

    def failing_variant(self) -> LazyStep:
        """Return self; a deferral has no failure mode to prove."""
        return self

    def run(self) -> Result:
        """Report the deferral as LAZY, which is neither a pass nor a failure."""
        return Result(self.label, Status.LAZY, self.detail)

    def prove(self) -> Result:
        """Report that a deferral has nothing to prove."""
        return Result(self.label, Status.LAZY, "deferred - nothing to prove")


__all__ = ["CommandStep", "Evidence", "FileStep", "LazyStep", "Result", "Step", "StepFailed"]
