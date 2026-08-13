"""The bench: measure your own recall, then TUNE THE BOOT against the number.

WHAT IS UNDER TEST IS THE BOOT, NOT THE MODEL
---------------------------------------------
This is the single most important thing about using a bench, and the easiest to get backwards.
The tempting experiment is "which model is better". That question is expensive, slow, and mostly
already answered (research/EXP-006: a small model with the right context matched or beat a large
one without it).

The useful experiment is: **hold the questions and the model fixed, and vary the BOOT.** Does
adding this file to the resident set make recall faster? Does reordering the tiers reduce misses?
Does that reflex table actually get reached for? Those are answerable in minutes and they compound,
because the boot runs on every session forever.

    fixed: the probe set, the model, the corpus
    varied: what loads at startup, in what order
    measured: hit, latency, and WHICH TIER answered

N >= 3, ALWAYS
--------------
A single run is noise. Cold caches, a busy host, one unlucky timeout - any of them will flip a
verdict, and a bench you only ran once will confidently tell you to make a change that does
nothing. Anything reported here from a single run is labelled as such.

SCORE DISCIPLINE, NOT ONLY CORRECTNESS
--------------------------------------
A correct answer reached by the wrong path is a lucky guess that will not repeat. So a probe
records WHICH TIER answered as well as whether the answer was right. An agent that gets the right
answer from a 4-second multi-hop search when a 90ms keyed lookup held it has not passed - it has
demonstrated the exact failure the tiers exist to prevent.

FADING IS THE ACTIONABLE VERDICT
--------------------------------
A probe that used to hit and now misses means a pointer rotted: content moved, a file was renamed,
a tool stopped answering. That is worth more than any latency number, because it is the only signal
that memory is DECAYING rather than merely slow.
"""
from __future__ import annotations

import statistics
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from enum import Enum


class Verdict(Enum):
    """How a probe answered, after N runs."""

    FAST = "FAST"        # resident-speed: reflexive
    WARM = "WARM"        # a real lookup, still cheap
    SLOW = "SLOW"        # answered, but by an expensive path
    FADING = "FADING"    # MISS - the pointer no longer resolves. The actionable one.

    @property
    def is_miss(self) -> bool:
        """Return True when the probe failed to answer at all."""
        return self is Verdict.FADING


@dataclass(frozen=True)
class Thresholds:
    """Where FAST ends and SLOW begins - CALIBRATED PER SEAT, never inherited.

    The defaults come from one measured gradient (research/EXP-003: resident 0.1ms, keyed ~90ms,
    semantic ~1.9s). They are a starting point and they are already wrong for at least one real
    stack, including mine.

    THE EVIDENCE THAT THESE MUST BE CALIBRATED: EXP-007 measured the same probe set with the tiers
    living in-stack rather than across a network - keyed went 90ms -> 0.6ms. Against the inherited
    thresholds, FOUR OF FIVE PROBES CAME BACK "FAST" and the bench lost all resolution. Every
    answer looked equally good, so the instrument could no longer tell a reflex from a lookup, and
    tuning against it would have been tuning against noise.

    A threshold borrowed from someone else's hardware does not measure your seat. It measures
    theirs, on your data, and reports the difference as if it were a verdict.
    """

    fast_ms: float = 150.0
    warm_ms: float = 2000.0

    def __post_init__(self) -> None:
        """Reject thresholds that cannot separate the bands they name."""
        if self.fast_ms <= 0 or self.warm_ms <= self.fast_ms:
            raise ValueError(
                f"thresholds must be ordered and positive (got fast={self.fast_ms}, "
                f"warm={self.warm_ms}). A band that cannot be entered is a verdict never reported.")

    @classmethod
    def from_baseline(cls, medians: list[float], *, spread: float = 8.0) -> Thresholds:
        """Derive thresholds from a seat's OWN measured baseline.

        The fastest observed tier defines the floor: whatever is quickest HERE is what "reflexive"
        means HERE. `spread` sets how many multiples of that floor still count as fast, and the
        warm band is an order beyond it.

        This deliberately produces different numbers on different hardware. That is the point - a
        verdict is a statement about THIS seat, and a bench whose bands do not move with the
        machine is reporting somebody else's architecture.
        """
        usable = [m for m in medians if m > 0]
        if not usable:
            return cls()
        floor = min(usable)
        return cls(fast_ms=max(floor * spread, 0.05), warm_ms=max(floor * spread * 10, 0.5))


@dataclass(frozen=True)
class Probe:
    """One question, and what a correct answer must contain.

    `expect` is a substring the answer must carry. Deliberately crude, and honest about it: a
    marker cannot judge quality, only that the right THING came back. It is enough to detect
    rot, which is what this measures.
    """

    name: str
    ask: Callable[[], str]
    expect: str
    tier: str = ""       # which tier SHOULD answer - scoring the path, not just the result
    negate: bool = False # the marker must be ABSENT - a probe that proves recall can say NO

    def __post_init__(self) -> None:
        """Refuse a probe with nothing to check against."""
        if not self.expect.strip():
            raise ValueError(
                f"probe {self.name!r} needs an `expect` marker. A probe that cannot fail measures "
                "nothing, and will report healthy forever.")


@dataclass
class Result:
    """What one probe did across N runs."""

    probe: str
    hits: int
    runs: int
    median_ms: float
    tier: str = ""
    error: str = ""
    negate: bool = False
    thresholds: Thresholds = field(default_factory=Thresholds)

    @property
    def verdict(self) -> Verdict:
        """Return the verdict, judged on the median rather than the best run."""
        if self.hits == 0:
            return Verdict.FADING
        if self.median_ms < self.thresholds.fast_ms:
            return Verdict.FAST
        if self.median_ms < self.thresholds.warm_ms:
            return Verdict.WARM
        return Verdict.SLOW

    def line(self) -> str:
        """Return the result as one readable row."""
        kind = "correctly-absent" if self.negate else "hit"
        flag = "" if self.hits == self.runs else f"  ({self.hits}/{self.runs} {kind})"
        where = f"  via {self.tier}" if self.tier else ""
        note = f"  {self.error}" if self.error else ""
        return f"  {self.verdict.value:<7} {self.median_ms:8.1f} ms  {self.probe}{where}{flag}{note}"


@dataclass
class Bench:
    """Run a fixed probe set N times and report what actually answered.

    Keep the probes stable across runs. The moment the questions change, two runs are no longer
    comparable and the bench has stopped being an instrument - it has become an anecdote.
    """

    probes: list[Probe] = field(default_factory=list)
    label: str = "unlabelled boot"
    results: list[Result] = field(default_factory=list)
    thresholds: Thresholds = field(default_factory=Thresholds)

    def add(self, *probes: Probe) -> Bench:
        """Add probes and return self so a bench can be built fluently."""
        self.probes.extend(probes)
        return self

    def run(self, n: int = 3) -> list[Result]:
        """Run every probe n times and record hits and median latency.

        n defaults to 3 because 1 is noise. Anything below 3 is reported with a warning rather
        than quietly presented as a measurement.
        """
        if n < 3:
            print(f"[WARN] n={n} is not a measurement. One unlucky run flips a verdict; "
                  "3 is the floor for anything you intend to act on.")
        self.results = []
        for probe in self.probes:
            times, hits, error = [], 0, ""
            for _ in range(n):
                start = time.perf_counter()
                try:
                    answer = probe.ask() or ""
                except Exception as exc:  # noqa: BLE001 - a broken probe is a FADING result, not a crash
                    error = f"{type(exc).__name__}: {exc}"
                    answer = ""
                times.append((time.perf_counter() - start) * 1000)
                found = probe.expect.lower() in answer.lower()
                hits += 1 if (found != probe.negate) else 0
            self.results.append(Result(probe.name, hits, n, statistics.median(times),
                                       probe.tier, error, probe.negate, self.thresholds))
        return self.results

    def calibrate(self, spread: float = 8.0) -> Thresholds:
        """Re-derive thresholds from this run and re-grade it against the seat's own floor.

        Run once on a healthy baseline, then keep the result. Re-calibrating on every run would
        make every seat look identical and hide the very regressions the bench exists to catch -
        the bands would chase the measurements instead of judging them.
        """
        self.thresholds = Thresholds.from_baseline([r.median_ms for r in self.results], spread=spread)
        self.results = [replace(r, thresholds=self.thresholds) for r in self.results]
        return self.thresholds

    # ── reporting ───────────────────────────────────────────────────────────────────────────
    def report(self) -> str:
        """Return the full run as a readable block."""
        if not self.results:
            return "(bench not run)"
        lines = [f"BENCH: {self.label}", ""]
        lines += [r.line() for r in self.results]
        lines += ["", f"  {self.summary()}"]
        fading = [r.probe for r in self.results if r.verdict.is_miss]
        if fading:
            lines += ["",
                      "  FADING is the actionable verdict - these pointers no longer resolve:",
                      *[f"    - {name}" for name in fading],
                      "  Re-point or re-ingest them. A miss is memory DECAYING, not memory slow."]
        return "\n".join(lines)

    def summary(self) -> str:
        """Return a one-line score for this boot configuration."""
        if not self.results:
            return "not run"
        counts = {v: sum(1 for r in self.results if r.verdict is v) for v in Verdict}
        median = statistics.median([r.median_ms for r in self.results])
        return (f"{len(self.results)} probes: {counts[Verdict.FAST]} fast, {counts[Verdict.WARM]} warm, "
                f"{counts[Verdict.SLOW]} slow, {counts[Verdict.FADING]} FADING "
                f"| median {median:.1f} ms")

    def compare(self, other: Bench) -> str:
        """Compare this run against another boot configuration, probe by probe.

        This is the ONLY output that answers the question worth asking - not "is my recall good"
        but "did that change to the boot make it better". Keep the probes identical between the
        two runs or the comparison is meaningless.
        """
        mine = {r.probe: r for r in self.results}
        theirs = {r.probe: r for r in other.results}
        shared = [p for p in mine if p in theirs]
        if not shared:
            return "(no probes in common - the two runs are not comparable)"
        lines = [f"COMPARE: {self.label}  vs  {other.label}", ""]
        for name in shared:
            a, b = mine[name], theirs[name]
            delta = b.median_ms - a.median_ms
            arrow = "faster" if delta < 0 else "slower"
            change = ""
            if a.verdict is not b.verdict:
                change = f"   {a.verdict.value} -> {b.verdict.value}"
            lines.append(f"  {name:<28} {a.median_ms:8.1f} -> {b.median_ms:8.1f} ms  "
                         f"({abs(delta):.1f} ms {arrow}){change}")
        return "\n".join(lines)
