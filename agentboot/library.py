"""The library: documentation vendored into local git, classified, and made answerable.

WHY DOCUMENTATION MUST BE VENDORED, NOT VISITED
------------------------------------------------
An agent that reads documentation off the live web has no idea what it read. The page is fetched,
paraphrased into an answer, and thrown away - so when the answer turns out to be wrong there is no
way to tell whether the doc was wrong, the doc CHANGED, or the reading was careless. Three very
different faults, indistinguishable after the fact.

So every encountered document is **accessioned**: copied into a local git repository, committed, and
from then on referred to by revision. That buys three things nothing else does:

1. **A diff.** When upstream changes, you see exactly what changed rather than silently reading
   something new and believing it was always so.
2. **A citation that survives.** `book@revision` still resolves after the vendor reorganises their
   site, deletes the page, or puts it behind a login.
3. **Offline truth.** The library answers with no network, which is the point of working in the can.

THE LIBRARY IS THE PROVENANCE LAYER UNDER TRUTHINESS
-----------------------------------------------------
This is the join that makes the whole thing more than a document cache, and it runs the other way
from how you would expect:

    a book is a SOURCE. its revision is WHEN it said so.
    when a book changes, every claim derived from the old revision is CHALLENGED, automatically.

That last line is the load-bearing one. Documentation drifting under an agent's feet is one of the
quietest ways for a memory to go stale - nothing errors, nothing looks different, and a confident
answer is now describing a version of the world that stopped existing. Because accessioning a
changed revision contradicts the claims that cited the old one, a doc update pushes exactly those
memories back down toward uncertainty and leaves everything else alone. Nobody audits anything.

COLLECTIONS OF COLLECTIONS, AND WHAT THAT ACTUALLY MEANS
---------------------------------------------------------
A shelf holds books and other shelves, without limit. Building an index over that shape is a
map-reduce and is implemented as one, in the three moves the operation is actually made of:

    unwind()   flatten the nested shelves into leaf books, each carrying its full path
    emit()     map every leaf to (key, value) pairs - one leaf may emit many, or none
    rewind()   group the emitted pairs back by key and reduce them

Which means the Dewey index, the per-collection vector namespace, the "what do we hold about TLS"
question and the staleness sweep are all the same operation with different mappers, rather than four
bespoke traversals that will disagree with each other by next month.

THE CLASSIFICATION IS THE ADDRESS, IN EVERY STORE
--------------------------------------------------
A notation like `340` is not a label, it is the address the record takes in all three stores at once:
the Mongo collection, the vector namespace, and the path on the shelf. One classification decision,
made by the Librarian at accession time, and the book is findable by browsing, by exact key, and by
meaning - without three separate registration steps that can each be forgotten independently.
"""
from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

# A Dewey for an agent's estate. Deliberately coarse: a scheme fine enough to argue about is a scheme
# nobody classifies consistently, and an inconsistent classification is worse than a broad one because
# it looks precise. Ten top-level classes, subdivided only where a shelf actually gets crowded.
SCHEME: dict[str, str] = {
    "000": "reference, meta, and the agent's own doctrine",
    "100": "languages and runtimes",
    "200": "protocols and data formats",
    "300": "networking",
    "400": "storage and databases",
    "500": "operating systems and containers",
    "600": "build, delivery, and automation",
    "700": "security, identity, and secrets",
    "800": "observability and diagnostics",
    "900": "vendors and upstream products",
}


class Unclassified(Exception):
    """Raised when a book would enter the library without an address in the scheme."""


@dataclass(frozen=True)
class Classification:
    """Where a work lives - simultaneously its shelf, its Mongo collection, and its vector namespace.

    One decision, three addresses. Deriving them all from a single notation is what stops a book
    being browsable but unsearchable, or embedded but uncitable, because someone registered it in two
    places out of three.
    """

    notation: str
    subject: str = ""

    def __post_init__(self) -> None:
        """Reject a notation that is not rooted in the scheme."""
        if not self.notation.strip():
            raise Unclassified("a work needs a notation; an unshelved book is a lost book")
        if self.root not in SCHEME:
            raise Unclassified(
                f"notation {self.notation!r} has no class {self.root!r} in the scheme "
                f"(known: {', '.join(sorted(SCHEME))})")

    @property
    def root(self) -> str:
        """Return the top-level class this notation belongs to."""
        return self.notation.split(".")[0][:3].ljust(3, "0")

    @property
    def collection(self) -> str:
        """Return the document-store collection name for this classification."""
        return "lib." + self.notation.replace(".", "_")

    @property
    def namespace(self) -> str:
        """Return the vector-store namespace, scoped to the top class.

        Scoped to the ROOT rather than the full notation on purpose: a semantic search for a
        networking question should reach everything about networking, not only the sub-shelf someone
        happened to file the answer under. Exactness is what the collection is for.
        """
        return f"lib/{self.root}"

    def describe(self) -> str:
        """Return a human-readable placement."""
        return f"{self.notation} {self.subject or SCHEME.get(self.root, '')}".strip()


@dataclass
class Book:
    """One accessioned work: where it came from, which revision was read, and what it holds.

    `revision` is the whole point of the type. A book without one is a rumour: it cannot be diffed,
    cited after the source moves, or checked for drift - so this refuses to exist without it.
    """

    title: str
    origin: str
    classification: Classification
    revision: str
    pages: list[str] = field(default_factory=list)
    accessioned: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        """Refuse a book that cannot be cited later."""
        if not self.title.strip():
            raise ValueError("a book needs a title")
        if not self.revision.strip():
            raise ValueError(
                f"{self.title!r} has no revision - an uncitable copy is a rumour, not a reference")

    @property
    def citation(self) -> str:
        """Return the durable reference: still resolvable after upstream moves or deletes it."""
        return f"{self.title}@{self.revision[:12]}"

    def render(self) -> str:
        """Return a one-line shelf entry."""
        return (f"[{self.classification.notation:>7}] {self.title} "
                f"({len(self.pages)} pages, rev {self.revision[:8]})")


@dataclass
class Shelf:
    """A collection that holds books AND other shelves, to any depth.

    The composite is not architectural taste - it is the shape documentation actually arrives in. A
    vendor's docs contain sections that contain guides that contain pages, and flattening that at
    ingest throws away the only structure the author gave you.
    """

    name: str
    books: list[Book] = field(default_factory=list)
    shelves: list[Shelf] = field(default_factory=list)

    def add(self, *works: Book | Shelf) -> Shelf:
        """Shelve books or sub-shelves, returning self so a library can be built fluently."""
        for work in works:
            (self.books if isinstance(work, Book) else self.shelves).append(work)
        return self

    def unwind(self, path: tuple[str, ...] = ()) -> Iterator[tuple[tuple[str, ...], Book]]:
        """Flatten nested shelves into leaf books, each carrying the full path that reached it.

        The path travels WITH the book because that is the information a flatten normally destroys,
        and it is the information the rewind needs to put things back. An unwind you cannot reverse
        is a loss, not a traversal.
        """
        here = (*path, self.name)
        for book in self.books:
            yield here, book
        for shelf in self.shelves:
            yield from shelf.unwind(here)

    def emit(self, mapper: Callable[[tuple[str, ...], Book], Iterator[tuple[str, object]]],
             ) -> Iterator[tuple[str, object]]:
        """Map every leaf to zero or more (key, value) pairs.

        Zero is deliberate and load-bearing: a mapper that must return something forces every
        traversal to invent a value for works it does not care about, and those inventions are what
        an index ends up full of.
        """
        for path, book in self.unwind():
            yield from mapper(path, book)

    def rewind(self, mapper: Callable[[tuple[str, ...], Book], Iterator[tuple[str, object]]],
               reducer: Callable[[str, list[object]], object] | None = None) -> dict[str, object]:
        """Group emitted pairs by key and reduce them - the wind-up half of the unwind.

        Every index this library has is this call with a different mapper: the Dewey index, the
        per-namespace embedding plan, the staleness sweep. One traversal, so they cannot drift out of
        agreement with each other the way four hand-written walks would.
        """
        grouped: dict[str, list[object]] = {}
        for key, value in self.emit(mapper):
            grouped.setdefault(key, []).append(value)
        if reducer is None:
            return dict(grouped)
        return {key: reducer(key, values) for key, values in grouped.items()}

    def index(self) -> dict[str, object]:
        """Return the Dewey index: every top-level class to the titles held beneath it."""
        def by_class(_path, book):
            yield book.classification.root, book.citation

        return self.rewind(by_class, lambda _k, v: sorted(set(v)))

    def holdings(self) -> list[Book]:
        """Return every book held, at any depth."""
        return [book for _path, book in self.unwind()]

    def summary(self) -> str:
        """Return a one-line description of what this collection holds."""
        idx = self.index()
        held = len(self.holdings())
        classes = ", ".join(f"{k}:{len(v)}" for k, v in sorted(idx.items()))  # type: ignore[arg-type]
        return f"{self.name}: {held} works across {len(idx)} classes ({classes or 'empty'})"


@dataclass
class Accession:
    """What happened when a work entered the library."""

    book: Book
    fresh: bool                       # first time this work has been seen at all
    changed_from: str = ""            # the revision it replaced, when upstream had moved
    embedded: int = 0
    challenged: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        """Return True when the work is shelved and its pages reached the stores."""
        return self.embedded > 0 or not self.book.pages

    def render(self) -> str:
        """Return a one-line report of the accession."""
        if self.changed_from:
            note = (f"UPSTREAM CHANGED {self.changed_from[:8]} -> {self.book.revision[:8]}"
                    f"; {len(self.challenged)} claim(s) challenged")
        else:
            note = "new acquisition" if self.fresh else "unchanged, re-verified"
        return f"{self.book.render()} - {note}, {self.embedded} pages embedded"


@dataclass
class Librarian:
    """Accessions documentation: vendors it, classifies it, embeds it, and keeps it honest.

    Nothing here fetches anything. `vendor` is injected and returns the revision it committed, so
    this module holds the DISCIPLINE of accessioning while staying indifferent to whether the docs
    arrived by git clone, a crawl, or a copied folder - and stays testable without a network.
    """

    shelf: Shelf = field(default_factory=lambda: Shelf("library"))
    embedder: object | None = None          # a TripleEmbedder, or anything with .remember(text, **m)
    catalogue: object | None = None         # a truthiness Catalogue, for the provenance join
    known: dict[str, Book] = field(default_factory=dict)   # origin -> the book as last accessioned

    def accession(self, title: str, origin: str, notation: str, pages: list[str],
                  revision: str, subject: str = "") -> Accession:
        """Take a work into the library at a known revision, and sew it into every store.

        The interesting branch is the one where a work already held comes back at a DIFFERENT
        revision. That is not a re-import, it is news: something the agent may have already reasoned
        from has changed underneath it. So the old revision's claims are challenged rather than
        quietly overwritten, and the confidence in anything derived from the stale text falls on its
        own - which is the difference between a library and a cache.
        """
        classification = Classification(notation, subject)
        book = Book(title=title, origin=origin, classification=classification,
                    revision=revision, pages=list(pages))

        previous = self.known.get(origin)
        changed = bool(previous and previous.revision != revision)
        result = Accession(book=book, fresh=previous is None,
                           changed_from=previous.revision if changed else "")

        if previous is not None:
            self._unshelve(previous)
        self.shelf.add(book)
        self.known[origin] = book

        if changed:
            result.challenged = self._challenge_stale(previous)
        result.embedded = self._embed(book)
        return result

    def _unshelve(self, book: Book) -> None:
        """Remove a superseded revision so the shelf never holds two versions of one work."""
        def drop(shelf: Shelf) -> None:
            shelf.books = [b for b in shelf.books if b is not book]
            for sub in shelf.shelves:
                drop(sub)

        drop(self.shelf)

    def _challenge_stale(self, previous: Book) -> list[str]:
        """Contradict claims that cited a revision which no longer exists upstream.

        Not a purge. The old text may still have been right - it is the CONFIDENCE that is no longer
        earned, because the evidence it rested on has been superseded. So the claims are pushed back
        toward uncertainty and left to be re-corroborated against the new revision, and only the ones
        nothing supports any more fall out.
        """
        if self.catalogue is None:
            return []
        challenged = self.catalogue.challenge(  # type: ignore[attr-defined]
            previous.title, f"library:{previous.citation}")
        return [claim.text for claim in challenged]

    def _embed(self, book: Book) -> int:
        """Write every page into the stores, addressed by its classification.

        Each page carries its citation, so anything recalled from a vector hit can name the exact
        revision it came from instead of asserting a fact from nowhere.
        """
        if self.embedder is None or not book.pages:
            return 0
        landed = 0
        for number, page in enumerate(book.pages):
            result = self.embedder.remember(  # type: ignore[attr-defined]
                page,
                citation=book.citation,
                collection=book.classification.collection,
                namespace=book.classification.namespace,
                page=number,
            )
            landed += 1 if result else 0
        return landed

    def stale(self, current: dict[str, str]) -> list[Book]:
        """Return held works whose upstream revision no longer matches what was accessioned.

        Takes the current revisions as an argument rather than going to look: whoever runs the check
        owns the network call, and a library that silently reaches out is a library that behaves
        differently in the can than it does on a workstation.
        """
        return [book for origin, book in sorted(self.known.items())
                if origin in current and current[origin] != book.revision]

    def summary(self) -> str:
        """Return a one-line description of the library's state."""
        return self.shelf.summary()
