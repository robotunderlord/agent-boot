"""Truthiness: a stateful confidence on every remembered claim, re-evaluated whenever a similar one arrives.

WHY A MEMORY NEEDS A CONFIDENCE, AND WHY IT MUST CHANGE
-------------------------------------------------------
A store that treats every record as equally true is not a memory, it is a pile. Something written
once from a single guess sits beside something confirmed four times from unrelated directions, and
recall cannot tell them apart - so the guess gets cited with the same certainty as the finding.

So every claim carries a truthiness, 1 to 10, and it is **stateful**: it is not computed once at
write time and frozen. It moves when evidence arrives. That is the whole mechanism - the point at
which a similar claim is remembered is the point at which BOTH are re-evaluated.

    corroborated by an independent source  -> up
    contradicted                           -> down
    only ever repeated by its own source    -> stalls at a low ceiling
    falls past the purge line               -> dropped, automatically

Bad ideas do not need to be hunted down. They decay, because nothing corroborates them and
something eventually contradicts them.

INDEPENDENCE IS THE WHOLE OF CORROBORATION
-------------------------------------------
Two agreements are not worth the same. A claim repeated by the source that first made it has been
repeated, not confirmed - and an agent re-reading its own note and feeling more sure is the exact
failure this is built to prevent.

This module therefore weights corroboration by SOURCE INDEPENDENCE. The same source agreeing again
moves the needle almost not at all. A genuinely unrelated source agreeing moves it a lot. Partial
independence - a sibling instance, a mirror of the same upstream, a colleague who read the same
document - moves it somewhere in between, and the caller has to say which, because only the caller
knows.

This was learned rather than designed: an experiment in this repository was trusted far more than
its neighbours because a second seat derived it independently - and its own limits section had to
record that both seats were the same model family under shared priors, so the corroboration was
weaker than it first appeared. That judgement is now a number instead of a paragraph.

ANYTHING CAN BE A SOURCE
------------------------
A human, a document, a probe, another agent, a vendor's API, a stranger's blog. They all enter the
same way and all earn the same kind of score - a source's own standing rises and falls with the
claims it has backed. Nothing is trusted for what it IS; everything is trusted for what it has been
right about.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum

FLOOR = 1.0        # confidence never goes below this
PURGE = 2.0        # below this a claim is disbelieved and drops out of the catalogue
CEILING = 10.0
START = 5.0        # a new claim from an unproven source: neither believed nor dismissed


class Independence(Enum):
    """How unrelated a corroborating source is from the one that made the claim.

    The caller must choose this, because only the caller knows whether two sources share an
    upstream. Defaulting it would quietly turn repetition into confirmation.
    """

    SAME = 0.1        # the same source saying it again - repetition, not confirmation
    RELATED = 0.4     # a sibling instance, a mirror, someone who read the same document
    INDEPENDENT = 1.0  # genuinely unrelated origin


@dataclass
class Source:
    """Anything that can back a claim, and its own standing - earned, never assigned.

    A source is not trusted for what it is. It is trusted for what it has been right about, which
    means a respected source that starts being wrong loses standing on exactly the same terms as
    anything else.

    Standing is settled by OUTCOMES, never by the act of asserting. Crediting a source for speaking
    would let anything talk its way into authority by repeating itself - and then that inflated
    standing would weight its next corroboration more heavily. That loop is precisely the failure
    this module exists to prevent, so `corroborate()` deliberately does not touch standing; only a
    claim being upheld or refuted does.
    """

    name: str
    backed: int = 0
    upheld: int = 0

    @property
    def standing(self) -> float:
        """Return this source's earned reliability, 0..1, starting neutral while unproven."""
        if self.backed < 3:
            return 0.5
        return max(0.05, min(1.0, self.upheld / self.backed))

    def record(self, upheld: bool) -> None:
        """Record how one of this source's claims turned out."""
        self.backed += 1
        self.upheld += 1 if upheld else 0


@dataclass
class Claim:
    """One remembered assertion, its confidence, and the history that moved it."""

    text: str
    truthiness: float = START
    sources: set[str] = field(default_factory=set)
    history: list[tuple[float, str, float]] = field(default_factory=list)
    backers: dict[str, float] = field(default_factory=dict)      # name -> best independence weight
    challengers: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        """Reject an empty claim and clamp any out-of-range starting confidence."""
        if not self.text.strip():
            raise ValueError("a claim needs text; an empty assertion cannot be corroborated")
        self.truthiness = max(FLOOR, min(CEILING, self.truthiness))

    @property
    def alive(self) -> bool:
        """Return False once confidence has decayed past the purge line."""
        return self.truthiness > PURGE

    @property
    def tested(self) -> bool:
        """Return True when something has actually tried to refute this.

        Surviving a challenge and never facing one are different states that produce nearly the same
        number, so the number cannot carry the distinction and this flag has to.
        """
        return bool(self.challengers)

    @property
    def breadth(self) -> float:
        """Return total independent support: each distinct backer counted at its best independence.

        A source is counted ONCE, at the strongest independence it ever brought. Saying the same
        thing five times adds nothing here, which is what stops repetition buying certainty.
        """
        return sum(self.backers.values())

    def reachable(self) -> float:
        """Return the highest confidence this claim's support can currently justify.

        This is the hard stop on repetition. A claim backed only by the source that made it can
        creep a little above neutral and then stall, no matter how many times it is restated -
        because the ceiling is a function of WHO backs it, not HOW OFTEN. Widening the support
        raises the ceiling; volume never does.
        """
        return START + (CEILING - START) * (1 - 0.6 ** self.breadth)

    def _move(self, delta: float, why: str) -> float:
        """Apply a change, clamp it, and record what caused it."""
        self.truthiness = max(FLOOR, min(CEILING, self.truthiness + delta))
        self.history.append((time.time(), why, round(self.truthiness, 2)))
        return self.truthiness

    def corroborate(self, source: Source, independence: Independence = Independence.RELATED) -> float:
        """Raise confidence toward what this claim's breadth of support can justify.

        Diminishing by design, and capped: the gain is measured against `reachable()`, not against
        certainty. Ten agreements from one source approach a low ceiling; one agreement from a
        genuinely unrelated origin raises the ceiling itself.
        """
        self.sources.add(source.name)
        self.backers[source.name] = max(self.backers.get(source.name, 0.0), independence.value)
        headroom = max(0.0, self.reachable() - self.truthiness)
        delta = headroom * 0.35 * independence.value * source.standing
        return self._move(delta, f"corroborated by {source.name} ({independence.name.lower()})")

    def contradict(self, source: Source, independence: Independence = Independence.RELATED) -> float:
        """Lower confidence. Contradiction bites harder than agreement lifts, deliberately.

        A claim that survives a serious challenge has earned something; a claim nobody has ever
        tried to refute has earned nothing. Weighting them equally would let volume of agreement
        drown a single sound objection - which is how a comfortable wrong idea survives.
        """
        self.challengers.add(source.name)
        delta = -(self.truthiness - FLOOR) * 0.5 * independence.value * source.standing
        return self._move(delta, f"contradicted by {source.name} ({independence.name.lower()})")

    def decay(self, factor: float = 0.97) -> float:
        """Nudge an untouched claim back toward uncertainty.

        Nothing stays true by inertia. A claim nothing has referenced or re-confirmed in a long
        while should quietly drift down rather than sit at high confidence forever on the strength
        of one good day.
        """
        return self._move(-(self.truthiness - START) * (1 - factor) if self.truthiness > START
                          else 0.0, "decayed (untouched)")

    def render(self) -> str:
        """Return the claim, its confidence, its sources, and whether anything ever tested it."""
        mark = "" if self.tested else " UNTESTED"
        return f"[{self.truthiness:4.1f}/10, {len(self.sources)} src{mark}] {self.text}"


@dataclass
class Catalogue:
    """A stateful collection of claims: re-evaluates neighbours on write, purges what decays out.

    The re-evaluation trigger is the whole point. A claim is not scored once at write time - it is
    scored again every time something SIMILAR arrives, because that is the only moment new evidence
    about it actually exists.
    """

    claims: list[Claim] = field(default_factory=list)
    sources: dict[str, Source] = field(default_factory=dict)
    similarity: float = 0.5

    def source(self, name: str) -> Source:
        """Return the named source, creating it unproven if it is new."""
        return self.sources.setdefault(name, Source(name))

    @staticmethod
    def _overlap(a: str, b: str) -> float:
        """Return crude token overlap between two claims, 0..1."""
        from .lessons import SIGNAL_TERMS, _tokens
        ta, tb = _tokens(a), _tokens(b)
        if not ta or not tb:
            return 0.0
        return len(ta & tb) / min(len(ta), len(tb), SIGNAL_TERMS)

    def remember(self, text: str, source_name: str,
                 independence: Independence = Independence.RELATED,
                 agrees: bool = True) -> Claim:
        """Record a claim, re-evaluating every similar claim already held.

        This is where bad ideas start dying. A new claim that AGREES with a neighbour lifts it; one
        that DISAGREES pushes it down. Neither happens on a schedule or a sweep - it happens at the
        moment the similar thing is remembered, which is the only moment the evidence exists.
        """
        src = self.source(source_name)
        for existing in self.claims:
            if self._overlap(existing.text, text) >= self.similarity:
                if agrees:
                    existing.corroborate(src, independence)
                else:
                    existing.contradict(src, independence)

        claim = Claim(text=text, sources={source_name})
        self.claims.append(claim)
        self.purge()
        return claim

    def challenge(self, text: str, source_name: str,
                  independence: Independence = Independence.INDEPENDENT) -> list[Claim]:
        """Contradict every held claim similar to `text`, without storing a new claim.

        The difference from `remember(..., agrees=False)` matters: this is a source saying "that is
        WRONG", not a source asserting a rival account. A probe that disproves something has evidence
        to contribute and nothing of its own to file, and forcing it to file a claim in order to be
        heard would fill the catalogue with negations.
        """
        src = self.source(source_name)
        hit = [c for c in self.claims if self._overlap(c.text, text) >= self.similarity]
        for claim in hit:
            claim.contradict(src, independence)
        self.purge()
        return hit

    def settle(self, claim: Claim, upheld: bool) -> None:
        """Record how a claim actually turned out, and move its sources' standing accordingly.

        This is the only thing that moves standing. Whoever backed a claim that proved wrong loses
        ground; whoever challenged it gains, and vice versa. Standing is therefore a record of
        outcomes rather than of volume - a source cannot talk its way up.
        """
        for name in claim.backers:
            self.source(name).record(upheld=upheld)
        for name in claim.challengers:
            self.source(name).record(upheld=not upheld)

    def purge(self) -> list[Claim]:
        """Drop claims that have decayed past the purge line, settling their sources' standing.

        Automatic, not a chore. An idea nothing corroborates and something contradicts leaves on its
        own - which is the difference between a memory that improves and an archive that only grows.

        Its departure is also the verdict on everyone involved, so the accounts are settled here: the
        sources that backed it were wrong, and the ones that challenged it were right. That is how
        being repeatedly wrong eventually costs a source the weight its future claims carry.
        """
        dead = [c for c in self.claims if not c.alive]
        for claim in dead:
            self.settle(claim, upheld=False)
        self.claims = [c for c in self.claims if c.alive]
        return dead

    def believed(self, floor: float = 6.0) -> list[Claim]:
        """Return the claims currently standing above a confidence floor, strongest first."""
        return sorted((c for c in self.claims if c.truthiness >= floor),
                      key=lambda c: -c.truthiness)

    def horizon(self, floor: float = 6.0) -> list[Claim]:
        """Return what is BELIEVED but has never been challenged - the edge of actual knowledge.

        The most dangerous records in any store are here. A claim at 6.4 that nobody ever questioned
        and a claim at 6.5 that was attacked and survived score almost identically and are not
        remotely the same thing: one has been over the horizon and come back, the other has never
        been asked a hard question. Ranking by confidence alone cannot tell them apart, so the
        untested one gets cited with the authority the tested one earned.

        Naming this as a list is the point. Untested knowledge is normally an ABSENCE - it does not
        appear anywhere, and an absence reads as fine. This makes the boundary an addressable place
        you can look at, and therefore a work queue: these are the beliefs to go and attack next.
        """
        return [c for c in self.believed(floor) if not c.tested]

    def summary(self) -> str:
        """Return the DISTRIBUTION of confidence held. Never a mean - the scale is not linear.

        Truthiness is a bounded map of unbounded evidence: the gap from 5 to 6 is a little
        corroboration and the gap from 9 to 9.5 is an enormous amount, because the ceiling is
        approached and never reached. Distances in that mapped space are not comparable, so
        averaging them produces a number describing nothing.

        Concretely: a store holding one near-certain claim at 9.5 and one about to be purged at 2.1
        averages to 5.8, which reads NEUTRAL. Neither claim is neutral, and no claim in the store is
        anywhere near 5.8. The mean was a confident summary of a fact that did not exist.

        So this reports the shape instead - how many stand, how many are contested, how many are on
        their way out. Aggregate in the evidence domain if you must aggregate; never in this one.
        """
        if not self.claims:
            return "0 claims"
        believed = len(self.believed())
        doubted = len([c for c in self.claims if c.truthiness < START])
        contested = len(self.claims) - believed - doubted
        # The horizon goes IN THE SUMMARY, not behind a method nobody calls. Untested belief that is
        # only visible when you already suspect it exists is not visible at all.
        untested = len(self.horizon())
        edge = f" ({untested} UNTESTED)" if untested else ""
        return (f"{len(self.claims)} claims: {believed} believed{edge}, {contested} unsettled, "
                f"{doubted} doubted | {len(self.sources)} sources")
