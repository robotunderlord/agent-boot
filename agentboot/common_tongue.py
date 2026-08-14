"""The common tongue: the lite boot every dispatched agent speaks before it is allowed to work.

WHY EVERY ERRAND-RUNNER GETS A BOOT AT ALL
-------------------------------------------
An agent dispatched with nothing but a task prompt has no idea who it is, where it is, or what has
already gone wrong in this house. It will therefore do the reasonable thing, which is the thing that
burned the last one: guess a path, trust a 200, edit the shared checkout, cite a doc it half
remembers. The orchestrator knows better; the errand-runner was never told.

So there is a common tongue - a small orientation every agent boots with, no exceptions. It is
deliberately much less than a full boot, because an errand that spends its first minute unsealing
vaults and health-checking a lab has spent its context on being ready rather than on being useful.

WHAT IS IN IT, AND THE ONE THING DELIBERATELY LEFT OUT
--------------------------------------------------------
    IN   self-awareness      who am I, what am I for, what may I touch
    IN   locational awareness where am I, on what host, in what tree, in whose session
    IN   reflexes            the lessons that fire for THIS situation, not the whole ledger
    IN   the triple embedder findings go to the stores, not into a returned paragraph
    IN   librarian training  documentation encountered is accessioned, not skimmed
    IN   stenography         annotations laid into the session log, referenced and attributed

    OUT  monitors

Monitors are left out on purpose and it is not a size decision. A watcher armed by a dispatched
errand outlives the errand: dispatch twelve hobbits and you have twelve watchers on one thing,
all still running after every hobbit is gone, all reporting the same event. Watching is the
orchestrator's job precisely because the orchestrator is the one that persists.

FINDING IS NOT THE DELIVERABLE. THE RECORD IS.
-----------------------------------------------
The default failure of a dispatched agent is that it discovers something real, writes a good
paragraph about it, returns, and the paragraph is summarised into nothing. The finding existed for
one turn. Next week the same discovery is made again from scratch, at the same cost, and nobody
notices it is the second time.

So every agent here is certified in two trades before it may work:

    LIBRARIAN     documentation it encounters is ACCESSIONED - vendored, revisioned, classified,
                  embedded - so the next agent inherits a citation instead of a URL.
    STENOGRAPHER  what it did and found is ANNOTATED into the session log as it happens, keyed to
                  the session and laced with the external references it actually used.

Certified means demonstrated, not declared: `certify()` performs a real probe write and fails the
agent that cannot make one. An agent that cannot record is not permitted to find, because its
findings would evaporate and everyone downstream would believe the ground had been covered.

THE LOG IS MAJOR, NOT AN ARCHIVE
---------------------------------
It is tempting to treat the human-readable session log as the soft copy - nice to have, optional if
the backend is down. That is wrong for an agent seat, and this module overrides it: the log is
REQUIRED here.

The log is the only one of the three records that is ordered, session-keyed, and readable by a human
in the shape the work actually happened. The vector store knows what resembles what; the document
store knows what points at what; only the log knows what was done, in what order, by whom, and what
it was looking at when it decided. Losing it silently is losing the reasoning and keeping the
conclusions - which is the exact material an agent is worst at reconstructing.

CLIFFS NOTES, WITH THE PREVIOUS OWNER'S NOTATIONS
---------------------------------------------------
A second-hand textbook is worth more than a new one. You get the condensed text AND the margin
scribbles of whoever had it before - the worked example, the "this is wrong", the arrow to the page
that actually explains it.

So opening a work returns both: the digest, and every annotation prior seats left against it,
attributed and dated. And because annotations are anchored to `book@revision`, a note left against an
older edition is returned MARKED as such rather than quietly presented as current - a previous owner
was reading a different book, and their marginalia may be describing a paragraph that no longer
exists. That is still worth having. It is not worth mistaking for the current page.
"""
from __future__ import annotations

import os
import socket
import time
from dataclasses import dataclass, field
from pathlib import Path

from .library import Librarian
from .local_embedding import Destination, Role, TripleEmbedder
from .reflex_hook import ReflexHook


class NotCertified(Exception):
    """Raised when an agent cannot record, and so must not be allowed to find."""


@dataclass
class Seat:
    """Who and where this agent is - the two questions an unprimed agent gets wrong first.

    Locational awareness is not decoration. Most of the expensive mistakes in this house are an agent
    acting correctly in the WRONG PLACE: editing the shared checkout instead of its worktree, hitting
    prod because the cwd looked familiar, reporting on a host it is not on. An agent that must state
    where it is before it works is an agent that has at least once compared that answer to what it
    expected.
    """

    name: str
    errand: str = ""
    session: str = ""
    host: str = field(default_factory=socket.gethostname)
    cwd: Path = field(default_factory=Path.cwd)
    isolated: bool = False        # working in its own tree, safe to write
    may_touch: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Refuse an anonymous seat - an unnamed agent cannot be held to anything it records."""
        if not self.name.strip():
            raise ValueError("a seat needs a name; unattributed annotations are worth little")
        self.session = self.session or os.environ.get("AGENT_SESSION", "")

    @property
    def where(self) -> str:
        """Return the one line that answers 'where am I' without ambiguity."""
        tree = "isolated tree" if self.isolated else "SHARED checkout"
        return f"{self.host}:{self.cwd} ({tree})"

    def orient(self) -> str:
        """Return the orientation block this agent boots with."""
        lines = [
            f"  I am        {self.name}" + (f" - {self.errand}" if self.errand else ""),
            f"  I am at     {self.where}",
            f"  session     {self.session or '(unkeyed - annotations will not group)'}",
        ]
        if self.may_touch:
            lines.append(f"  may touch   {', '.join(self.may_touch)}")
        if not self.isolated:
            lines.append("  CAUTION     this is the shared checkout - do not write here")
        return "\n".join(lines)


@dataclass
class Annotation:
    """One margin note: what a seat observed, against what it was reading, in which session.

    Anchored to `citation` rather than to a title, because a note about a paragraph is a note about
    an EDITION. Losing that anchor is how the previous owner's marginalia end up being read as though
    they described the current page.
    """

    note: str
    seat: str
    session: str = ""
    citation: str = ""            # book@revision this was written against, if any
    page: int | None = None
    refs: tuple[str, ...] = ()    # external references actually used
    at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        """Refuse an empty or unattributed note."""
        if not self.note.strip():
            raise ValueError("an empty annotation records nothing")
        if not self.seat.strip():
            raise ValueError("an annotation needs a seat; unattributed marginalia cannot be judged")

    def render(self, current_citation: str = "") -> str:
        """Return the note, marked when it was written against a different edition."""
        stamp = time.strftime("%Y-%m-%d", time.localtime(self.at))
        where = f" p{self.page}" if self.page is not None else ""
        stale = ""
        if current_citation and self.citation and self.citation != current_citation:
            stale = f"  [PREVIOUS EDITION {self.citation} - the page may no longer say this]"
        refs = f"  refs: {', '.join(self.refs)}" if self.refs else ""
        return f"  - ({self.seat}, {stamp}){where} {self.note}{refs}{stale}"


@dataclass
class Stenographer:
    """Lays annotations into the session log as the work happens, keyed and referenced.

    Writes through the triple embedder rather than to a file, so one note lands in all three records
    at once: searchable by meaning, joinable by key, and readable in order. A note written to only
    one of them is a note the other two will never surface.
    """

    seat: Seat
    embedder: TripleEmbedder
    notes: list[Annotation] = field(default_factory=list)

    def annotate(self, note: str, *, citation: str = "", page: int | None = None,
                 refs: tuple[str, ...] = ()) -> Annotation:
        """Record one observation, now, while the reason for it is still known.

        Deliberately called during the work rather than at the end. An agent that batches its notes
        to the final turn loses all of them the moment it is interrupted, and interruption is the
        normal end of a long errand.
        """
        entry = Annotation(note=note, seat=self.seat.name, session=self.seat.session,
                           citation=citation, page=page, refs=refs)
        self.notes.append(entry)
        self.embedder.remember(
            note,
            kind="annotation",
            seat=self.seat.name,
            session=self.seat.session,
            citation=citation,
            page=page,
            refs=list(refs),
            where=self.seat.where,
        )
        return entry

    def marginalia(self, citation: str = "", *, title: str = "") -> list[Annotation]:
        """Return prior notes against a work - the previous owner's scribbles.

        Matching on TITLE by default, not on the exact citation: a note left against an older edition
        is precisely what a new reader wants to see. It is returned marked, not withheld.
        """
        key = title or citation.split("@")[0]
        return [n for n in self.notes if n.citation.split("@")[0] == key and key]

    def cliffs(self, citation: str) -> str:
        """Return the condensed entry for a work plus every previous owner's notation.

        This is the shape a second-hand textbook arrives in, and it is more useful than a clean copy:
        the digest tells you what the work says, and the margins tell you what it cost the last
        reader to find that out.
        """
        prior = self.marginalia(citation)
        if not prior:
            return f"{citation}\n  (no previous owner's notations)"
        lines = [citation, f"  {len(prior)} notation(s) from previous readers:"]
        lines += [n.render(current_citation=citation) for n in prior]
        return "\n".join(lines)


@dataclass
class CommonTongue:
    """The lite boot: what every hobbit and sub-agent speaks before it is allowed to work.

    Assembles the seat, the reflexes, the stores and both trades - and arms no monitors, on purpose.
    """

    seat: Seat
    embedder: TripleEmbedder | None = None
    librarian: Librarian | None = None
    reflexes: ReflexHook | None = None
    certified: bool = False

    def __post_init__(self) -> None:
        """Wire the pieces that were not supplied, keeping the log REQUIRED."""
        if self.embedder is None:
            self.embedder = TripleEmbedder()
        if self.librarian is None:
            self.librarian = Librarian(embedder=self.embedder)
        if self.reflexes is None:
            self.reflexes = ReflexHook()
        self.steno = Stenographer(seat=self.seat, embedder=self.embedder)

    @staticmethod
    def stores(*, vector, log, join) -> TripleEmbedder:
        """Return an embedder wired for an AGENT seat, where the log is REQUIRED.

        This is the one place the general-purpose default is overridden. For a background service a
        human-readable archive being down is survivable; for an agent seat it is not, because the log
        is the only record that knows what was done, in what order, and what was being read at the
        time. Losing it keeps the conclusions and discards the reasoning.
        """
        return TripleEmbedder().add(
            Destination("vector", vector),
            Destination("log", log, required=True),
            Destination("join", join, role=Role.LINK),
        )

    def certify(self) -> CommonTongue:
        """Prove this agent can record before permitting it to find. Raises if it cannot.

        A declared capability is not a capability. This performs a real write through every required
        store, because a read-only store, a wrong database or a full disk answers every configuration
        check perfectly and then loses the first annotation.
        """
        if not self.embedder.destinations:
            raise NotCertified(
                f"{self.seat.name} has no stores wired - its findings would exist for one turn")
        result = self.embedder.remember(f"__certify__ {self.seat.name}", kind="probe")
        if not result:
            raise NotCertified(f"{self.seat.name} cannot record: {result.render()}")
        self.certified = True
        return self

    def reflex(self, situation: str) -> str:
        """Return only the lessons that fire for this situation - usually nothing."""
        return self.reflexes.render(situation)

    def brief(self, situation: str = "") -> str:
        """Return the whole lite boot as one block, to be read before the first action."""
        blocks = ["COMMON TONGUE - lite boot", self.seat.orient()]
        trades = "  trades      certified LIBRARIAN (accession what you read) and " \
                 "STENOGRAPHER (annotate as you go)"
        blocks.append(trades if self.certified else
                      "  trades      NOT CERTIFIED - this agent cannot record and must not find")
        blocks.append("  monitors    none by design - watching is the orchestrator's job")
        fired = self.reflex(situation) if situation else ""
        if fired:
            blocks.append("")
            blocks.append(fired)
        return "\n".join(blocks)
