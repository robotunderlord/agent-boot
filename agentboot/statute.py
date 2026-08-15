"""Statutes: rules written as LAW in plain English, enforceable by machine, and readable back again.

WHY A REGEX IS NOT A LAW
------------------------
A denylist entry is a single boolean over some text. It cannot say what it is *for*, cannot be
argued with, and cannot distinguish looking from doing. A real statute can, because it is built from
ELEMENTS - the separate facts a prosecutor must each establish before conduct is an offence.

That distinction is not academic. A live rule in this house read, in full::

    (r"192\\.168\\.\\d+\\.183|lothlorien|loth\\b", "touches loth (the hypervisor - HARD forbidden)")

One element: *does the text contain a name*. So it denied reading a document that mentioned the
host, denied `ping`, denied `grep`, and denied listing the guests - while a genuinely destructive
command that happened not to spell the name would sail through. It criminalised looking at the
courthouse. Written as a statute it needs two elements - the action TARGETS the hypervisor, and the
action IS destructive - and a judge would have thrown out the one-element version on sight.

THE SHAPE OF A LAW, WHICH IS ALSO A GOOD DATA STRUCTURE
--------------------------------------------------------
    ELEMENTS    every one must be proven. Conjunction.
    EXCEPTIONS  any one excuses the conduct. Disjunction, evaluated AFTER the elements.
    SANCTION    what follows - deny, require a human, or merely note it.

Elements are conjunctive and exceptions disjunctive because that is how liability actually works,
and it gives you something a denylist never has: when a rule fires you can say WHICH element was
satisfied, and when it does not fire you can say which element FAILED. That is an opinion, not a
verdict, and it is the difference between "BLOCKED" and a reason someone can act on.

BOTH DIRECTIONS, OR IT IS JUST A CONFIG FILE
---------------------------------------------
The plain-language text is the SOURCE, not documentation generated from code. `parse()` reads it
into an enforceable statute and `render()` writes it back, and the round-trip is tested: parsing a
rendered statute must reproduce it exactly. If those two ever drift, the English becomes a comment -
and a comment beside a rule is the oldest lie in the building.

This is why the corpus can live in a document store and be edited by someone who does not write
Python. The same shape holds for anything with the statute form - PCI-DSS requirements, state and
local code, a constitution: an identifier, a plain statement, the elements that must be met, the
exceptions, and what follows. One parser, many corpora, each its own collection.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum


class Sanction(Enum):
    """What follows when conduct satisfies a statute. Ordered: the gravest verdict wins."""

    NOTE = 0        # recorded, nothing prevented
    REQUIRE_HUMAN = 1   # the person who bears the consequence decides
    DENY = 2        # refused outright


class Malformed(Exception):
    """Raised when text cannot be read as a statute. Never guessed at."""


@dataclass
class Element:
    """One fact that must be established. Plain statement first, the test second.

    The statement is not a comment. It is what gets read out when the element decides a case, so it
    has to be true on its own terms - "the action is destructive", not "regex 2".
    """

    statement: str
    pattern: str = ""
    test: Callable[[str], bool] | None = None

    def __post_init__(self) -> None:
        """Refuse an element that states nothing or proves nothing."""
        if not self.statement.strip():
            raise Malformed("an element needs a plain statement of the fact it establishes")
        if not self.pattern and self.test is None:
            raise Malformed(f"element {self.statement!r} has no test - it could never be proven")
        if self.pattern:
            try:
                re.compile(self.pattern)
            except re.error as exc:
                raise Malformed(f"element {self.statement!r} has an unreadable test: {exc}") from exc

    def met_by(self, conduct: str) -> bool:
        """Return whether this element is established by the conduct."""
        if self.test is not None:
            return bool(self.test(conduct))
        return bool(re.search(self.pattern, conduct, re.I))


@dataclass
class Statute:
    """One law: an identifier, what it says, what must be proven, what excuses it, what follows."""

    id: str
    title: str
    text: str
    elements: list[Element] = field(default_factory=list)
    exceptions: list[Element] = field(default_factory=list)
    sanction: Sanction = Sanction.DENY

    def __post_init__(self) -> None:
        """Refuse a statute that cannot be cited or cannot be satisfied."""
        if not self.id.strip():
            raise Malformed("a statute needs an identifier; an uncitable rule cannot be appealed")
        if not self.elements:
            raise Malformed(
                f"{self.id} has no elements - a law that requires nothing forbids everything")

    def try_case(self, conduct: str) -> Finding:
        """Judge conduct against this statute and return a reasoned finding."""
        met = [e for e in self.elements if e.met_by(conduct)]
        failed = [e for e in self.elements if e not in met]
        excused = [x for x in self.exceptions if x.met_by(conduct)] if not failed else []
        return Finding(statute=self, met=met, failed=failed, excused=excused)

    def to_document(self) -> dict:
        """Return the statute as a plain document, for a document store.

        Keeps the SOURCE TEXT alongside the parsed structure, deliberately. A corpus stored only as
        parsed fields can no longer be read as law - you get a schema where you had a statute, and
        the thing a human is supposed to review has quietly become machine output. Storing both means
        the collection is simultaneously queryable and readable, and the round trip is checkable at
        rest rather than only at import.
        """
        return {
            "_id": self.id,
            "title": self.title,
            "text": self.text,
            "sanction": self.sanction.name,
            "elements": [{"statement": e.statement, "pattern": e.pattern} for e in self.elements],
            "exceptions": [{"statement": x.statement, "pattern": x.pattern}
                           for x in self.exceptions],
            "source": self.render(),
        }

    @classmethod
    def from_document(cls, doc: dict) -> Statute:
        """Rebuild a statute from a stored document, by re-parsing its own source text.

        Parses `source` rather than trusting the parsed fields: the text is authoritative, so a
        document whose fields were edited directly and no longer agree with its own law is caught
        here instead of silently enforcing something nobody wrote.
        """
        if "source" not in doc:
            raise Malformed(f"{doc.get('_id', '?')}: stored document has no source text")
        return parse(doc["source"])

    def render(self) -> str:
        """Write this statute back out as plain language. Must round-trip through parse()."""
        lines = [f"LAW {self.id} - {self.title}", self.text.strip()]
        for element in self.elements:
            lines.append(f"  ELEMENT {element.statement}")
            lines.append(f"    WHEN /{element.pattern}/")
        for exception in self.exceptions:
            lines.append(f"  UNLESS {exception.statement}")
            lines.append(f"    WHEN /{exception.pattern}/")
        lines.append(f"  THEN {self.sanction.name.lower()}")
        return "\n".join(lines)


@dataclass
class Finding:
    """The judgment: what was proven, what was not, and why - an opinion, not just a verdict."""

    statute: Statute
    met: list[Element]
    failed: list[Element]
    excused: list[Element]

    @property
    def liable(self) -> bool:
        """Return True when every element was established and nothing excused it."""
        return not self.failed and not self.excused

    @property
    def sanction(self) -> Sanction | None:
        """Return the sanction if liable, else nothing."""
        return self.statute.sanction if self.liable else None

    def opinion(self) -> str:
        """Return the reasoning. A verdict with no reasoning cannot be appealed or corrected.

        Deliberately explains ACQUITTALS too. "BLOCKED" tells you nothing you can act on; "element 2
        failed - the action is not destructive" tells you the rule works and your command is fine,
        which is the sentence that would have saved several hours in this house.
        """
        head = f"{self.statute.id} ({self.statute.title})"
        if self.failed:
            return (f"{head}: NOT satisfied - "
                    + "; ".join(f"failed to establish that {e.statement}" for e in self.failed))
        if self.excused:
            return (f"{head}: elements met BUT excused - "
                    + "; ".join(x.statement for x in self.excused))
        return (f"{head}: SATISFIED - "
                + "; ".join(e.statement for e in self.met)
                + f" -> {self.statute.sanction.name.lower()}")


# --------------------------------------------------------------------------------------------
# The parser. Plain language in, statute out; and back again without loss.
# --------------------------------------------------------------------------------------------

# CLAUSES MUST BE INDENTED; PROSE MUST NOT BE. That is the whole grammar, and it is a rule about
# structure rather than about vocabulary - which is the point. The first version matched any line
# beginning with ELEMENT/UNLESS/THEN wherever it appeared, so a statute whose plain-English body
# happened to start a wrapped line with the word "unless" was read as having a clause there and
# failed to parse. Reserving words is hopeless in a language meant to be written by humans; reserving
# a COLUMN costs nothing and cannot collide with what someone wants to say.
_HEAD = re.compile(r"^LAW\s+(?P<id>\S+)\s+[-–—]\s+(?P<title>.+?)\s*$", re.I)
_CLAUSE = re.compile(r"^\s+(?P<kind>ELEMENT|UNLESS)\s+(?P<statement>.+?)\s*$", re.I)
_WHEN = re.compile(r"^\s+WHEN\s+/(?P<pattern>.*)/\s*$", re.I)
_THEN = re.compile(r"^\s+THEN\s+(?P<sanction>\w+)\s*$", re.I)


def parse(source: str) -> Statute:
    """Read one statute from plain language.

    Refuses rather than guesses. A misread law is worse than an unreadable one: it enforces
    something nobody wrote, and it does so silently.
    """
    lines = [ln for ln in source.splitlines() if ln.strip()]
    if not lines:
        raise Malformed("empty source")

    head = _HEAD.match(lines[0])
    if not head:
        raise Malformed(f"expected 'LAW <id> - <title>', got: {lines[0]!r}")

    statute_id, title = head.group("id"), head.group("title")
    prose: list[str] = []
    elements: list[Element] = []
    exceptions: list[Element] = []
    sanction = Sanction.DENY
    pending: tuple[str, str] | None = None   # (kind, statement) awaiting its WHEN

    for line in lines[1:]:
        if (clause := _CLAUSE.match(line)) and not line.strip().upper().startswith("WHEN"):
            if pending:
                raise Malformed(f"{statute_id}: {pending[1]!r} has no WHEN clause")
            pending = (clause.group("kind").upper(), clause.group("statement"))
            continue
        if when := _WHEN.match(line):
            if not pending:
                raise Malformed(f"{statute_id}: a WHEN with no ELEMENT or UNLESS before it")
            kind, statement = pending
            target = elements if kind == "ELEMENT" else exceptions
            target.append(Element(statement=statement, pattern=when.group("pattern")))
            pending = None
            continue
        if then := _THEN.match(line):
            name = then.group("sanction").upper()
            if name not in Sanction.__members__:
                raise Malformed(f"{statute_id}: unknown sanction {name!r} "
                                f"(known: {', '.join(Sanction.__members__)})")
            sanction = Sanction[name]
            continue
        if not elements and not pending:
            prose.append(line.strip())
        else:
            raise Malformed(f"{statute_id}: unreadable line: {line!r}")

    if pending:
        raise Malformed(f"{statute_id}: {pending[1]!r} has no WHEN clause")

    return Statute(id=statute_id, title=title, text=" ".join(prose),
                   elements=elements, exceptions=exceptions, sanction=sanction)


@dataclass
class Code:
    """A corpus of statutes - one body of law, tried together.

    The corpus is deliberately just a list. What makes it a CODE rather than a pile is that trying a
    case runs every statute and returns every finding, so conduct that satisfies two laws reports
    both. A first-match-wins denylist hides the second reason, and the second reason is often the
    one that mattered.
    """

    name: str
    statutes: list[Statute] = field(default_factory=list)

    @classmethod
    def parse_all(cls, name: str, source: str) -> Code:
        """Read a whole corpus. Statutes are separated by blank lines before each LAW header."""
        chunks: list[list[str]] = []
        for line in source.splitlines():
            if _HEAD.match(line):
                chunks.append([line])
            elif chunks:
                chunks[-1].append(line)
        if not chunks:
            raise Malformed(f"{name}: no statutes found - expected at least one 'LAW <id> - <title>'")
        return cls(name=name, statutes=[parse("\n".join(c)) for c in chunks])

    def try_case(self, conduct: str) -> list[Finding]:
        """Judge conduct against every statute, gravest sanction first."""
        findings = [s.try_case(conduct) for s in self.statutes]
        return sorted((f for f in findings if f.liable),
                      key=lambda f: -f.statute.sanction.value)

    def verdict(self, conduct: str) -> tuple[Sanction | None, str]:
        """Return the operative sanction and the opinion supporting it."""
        liable = self.try_case(conduct)
        if not liable:
            return None, ""
        return liable[0].statute.sanction, "\n".join(f.opinion() for f in liable)

    def render(self) -> str:
        """Write the whole corpus back out as plain language."""
        return "\n\n".join(s.render() for s in self.statutes)

    def summary(self) -> str:
        """Return a one-line description of the corpus."""
        counts = {s.name.lower(): 0 for s in Sanction}
        for statute in self.statutes:
            counts[statute.sanction.name.lower()] += 1
        detail = ", ".join(f"{n} {k}" for k, n in counts.items() if n)
        return f"{self.name}: {len(self.statutes)} statutes ({detail})"
