"""The triple embedder: one act of remembering, three homes, and an honest report of what landed.

WHY THREE, AND WHY ONE OF THEM IS NOT LIKE THE OTHERS
------------------------------------------------------
The same fact is needed in three shapes, and no single store serves all of them:

    SEMANTIC   a vector store   "what relates to this?"        fuzzy, needs an embedder
    LOG        a session log    "show me the conversation"     human-readable, chronological
    LINK       a document store "expand this exact thing"      exact, no model in the path

The first two are LEAVES. They each hold a representation of the memory and know nothing about the
other.

**The third is not a third copy. It is the JOIN**, and it is what makes the memory unwindable. It
records where every other representation went - the chunk id in the vector store, the message id in
the log - so that from one keyed lookup you can reach all of them. Without it you have three
archives of the same event that cannot be related to each other, which is not one memory in three
places: it is three memories that will drift apart and nobody will be able to prove which was first.

Two consequences fall out of that, and both are load-bearing:

1. **Order matters.** Leaves are written FIRST and return their ids; the link store is written LAST,
   with those ids in hand. A join written before the things it joins can only record intentions.
2. **The link store is required by default.** Losing a leaf costs you one way of finding a memory.
   Losing the join costs you the ability to unwind ANY of them - the other writes still succeeded,
   and are now orphans nobody can tie together.

EMBEDDINGS ARE COMPUTED LOCALLY. NOT A PREFERENCE.
---------------------------------------------------
An embedding call ships the text to whoever serves the endpoint. Point this at a hosted API and you
have exported everything you ever chose to remember - silently, at write time, looking like nothing
unusual in any log. This module refuses a remote embedder outright rather than warning about one
(see `semantic.py`, which enforces the same rule at the query end).

PARTIAL SUCCESS IS NOT SUCCESS
------------------------------
The dangerous failure here is not a crash. It is landing in two stores out of three and returning
happily, because a memory that is only in two places has begun drifting from itself and NOTHING
downstream will notice for weeks.

So `remember()` returns a result that names every destination and its outcome, and it is truthy only
when every REQUIRED destination accepted the write. A destination may be declared optional - the
session log usually is, because a human-readable archive being down should not stop the agent
remembering - but optional is a decision made once, in the open, not an accident discovered later.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .steps import Evidence, Step, StepFailed


class EmbedRefused(Exception):
    """Raised when remembering cannot be done safely, and so must not be done at all."""


class Role(Enum):
    """What a destination IS, which decides when it is written and what it receives."""

    LEAF = "leaf"    # holds a representation; written first; may return an id
    LINK = "link"    # holds the JOIN; written last; receives the leaves' ids


@dataclass(frozen=True)
class Destination:
    """One home for a memory: its name, how to write it, its role, and whether it is required.

    A LEAF writer is called `write(text, record)` and may RETURN an id - that id is what the link
    store needs in order to point back at it. Returning nothing is allowed; it simply means this
    representation cannot be addressed individually later.

    A LINK writer is called with the same arguments, and the record additionally carries `refs`:
    a mapping of every leaf name to the id it returned. That mapping IS the unwind path.
    """

    name: str
    write: Callable[[str, dict], Any]
    required: bool = True
    role: Role = Role.LEAF

    def __post_init__(self) -> None:
        """Reject a destination that cannot be written to."""
        if not self.name.strip():
            raise ValueError("a destination needs a name")
        if not callable(self.write):
            raise ValueError(f"destination {self.name!r} has no write callable")


@dataclass
class WriteResult:
    """What actually happened, per destination. Truthy only when every REQUIRED home accepted."""

    landed: dict[str, str] = field(default_factory=dict)
    failed: dict[str, str] = field(default_factory=dict)
    required_failed: set[str] = field(default_factory=set)
    refs: dict[str, str] = field(default_factory=dict)   # leaf name -> id, the unwind path
    orphaned: bool = False                                # leaves landed, the JOIN did not

    def __bool__(self) -> bool:
        """Return True only when no required destination failed."""
        return not self.required_failed

    def render(self) -> str:
        """Return a one-line summary naming what landed, what did not, and whether it can be unwound."""
        ok = ", ".join(sorted(self.landed)) or "nothing"
        if self.orphaned:
            return (f"ORPHANED: landed in {ok}, but the JOIN did not - these representations exist "
                    "and nothing can relate them to each other")
        if not self.failed:
            linked = f" (unwindable via {len(self.refs)} ref)" if self.refs else ""
            return f"remembered in {ok}{linked}"
        lost = ", ".join(f"{k} ({v[:40]})" for k, v in sorted(self.failed.items()))
        verdict = "INCOMPLETE" if self.required_failed else "partial, optional only"
        return f"{verdict}: landed in {ok}; did NOT land in {lost}"


@dataclass
class TripleEmbedder:
    """Remember something once, into every store that needs its own shape of it.

    Destinations are injected rather than constructed here. This module knows the DISCIPLINE of
    writing to several stores at once; it deliberately knows nothing about which vector database,
    which document store, or which log you happen to run - so it stays usable on a seat whose
    backends are nothing like the author's.
    """

    destinations: list[Destination] = field(default_factory=list)
    embed_endpoint: str = ""

    def add(self, *destinations: Destination) -> TripleEmbedder:
        """Add destinations and return self so an embedder can be built fluently."""
        self.destinations.extend(destinations)
        return self

    def _refuse_remote(self) -> None:
        """Raise if embedding would happen anywhere but this machine."""
        if not self.embed_endpoint:
            return
        from .semantic import SemanticStore, SemanticUnavailable
        try:
            SemanticStore(embed_endpoint=self.embed_endpoint)._refuse_remote_embedder()
        except SemanticUnavailable as exc:
            raise EmbedRefused(str(exc)) from exc

    def remember(self, text: str, **meta: Any) -> WriteResult:
        """Write one memory to every destination, and report exactly what landed.

        Never raises on a destination failure - a store being down is a fact to report, not a reason
        to lose the write to the stores that ARE up. Only an unsafe embedder raises, because that is
        a reason not to write at all.
        """
        if not text.strip():
            raise ValueError("refusing to remember an empty string - it will never be recalled")
        self._refuse_remote()

        record = {"text": text, "ts": time.time(), **meta}
        result = WriteResult()

        # LEAVES FIRST. They hold the representations and hand back the ids the join needs; a join
        # written before them could only record intentions.
        leaves = [d for d in self.destinations if d.role is Role.LEAF]
        links = [d for d in self.destinations if d.role is Role.LINK]

        for dest in leaves:
            try:
                ref = dest.write(text, dict(record))
                result.landed[dest.name] = "ok"
                if ref is not None:
                    result.refs[dest.name] = str(ref)
            except Exception as exc:  # noqa: BLE001 - one store failing must not lose the others
                result.failed[dest.name] = f"{type(exc).__name__}: {exc}"
                if dest.required:
                    result.required_failed.add(dest.name)

        # THE JOIN LAST, holding every id the leaves returned. This is the unwind path.
        for dest in links:
            try:
                dest.write(text, {**record, "refs": dict(result.refs)})
                result.landed[dest.name] = "ok"
            except Exception as exc:  # noqa: BLE001
                result.failed[dest.name] = f"{type(exc).__name__}: {exc}"
                if dest.required:
                    result.required_failed.add(dest.name)
                # Leaves survived, the join did not: those representations are now ORPHANS. This is
                # a worse outcome than losing a leaf and must not read as an ordinary partial write.
                if result.landed:
                    result.orphaned = True
        return result

    def summary(self) -> str:
        """Return a one-line description of the configured homes."""
        if not self.destinations:
            return "0 destinations - remembering would go nowhere"
        req = [d.name for d in self.destinations if d.required]
        opt = [d.name for d in self.destinations if not d.required]
        parts = [f"{len(self.destinations)} destinations", f"required: {', '.join(req) or 'none'}"]
        if opt:
            parts.append(f"optional: {', '.join(opt)}")
        return " | ".join(parts)

    def step(self, critical: bool = False) -> EmbedStep:
        """Return the boot step that proves a memory can actually be written and is not lost."""
        return EmbedStep(self, critical=critical)


class EmbedStep(Step):
    """Boot step proving every required destination accepts a real write."""

    def __init__(self, embedder: TripleEmbedder, critical: bool = False) -> None:
        """Store the embedder this step verifies."""
        super().__init__("memory:triple", critical=critical)
        self.embedder = embedder

    def check(self) -> Evidence:
        """Confirm a probe memory lands in every required destination.

        Configured destinations prove nothing. This writes a REAL record, because a store that is
        present but read-only, full, or pointed at the wrong database answers every health check
        perfectly right up until the first write.
        """
        if not self.embedder.destinations:
            raise StepFailed("no destinations - remembering would silently go nowhere")
        try:
            result = self.embedder.remember(f"__probe__ {time.time()}", kind="probe")
        except (EmbedRefused, ValueError) as exc:
            raise StepFailed(str(exc)) from exc
        if not result:
            raise StepFailed(result.render())
        return Evidence(result.render(), self.embedder.summary())

    def failing_variant(self) -> EmbedStep:
        """Return an embedder whose only destination cannot accept a write."""
        def explode(_text: str, _record: dict) -> None:
            raise RuntimeError("destination unreachable")

        broken = TripleEmbedder().add(Destination("unreachable", explode, required=True))
        return EmbedStep(broken, critical=self.critical)
