"""The KEYED tier: deterministic, millisecond recall that does not involve a model.

TWO-SPEED RECALL, AND WHY THIS TIER EXISTS
-------------------------------------------
An agent needs two different kinds of memory and the common mistake is to build one:

    KEYED     "expand this crumb", "what is X", "what did I do in session S"
              a find-by-key. Exact, ~1ms, deterministic, no embedding, no model.
    SEMANTIC  "what is related to this", "have I seen anything like this"
              nearest-meaning search. Fuzzy, slower, needs an embedder.

Classify by the SHAPE of the need. A "where/exact/expand-this" question answered by semantic search
is slower, costlier and less certain than a dictionary lookup - and it can return something plausible
that is simply not the thing you asked for. Keyed first; fall through to semantic only when the need
is genuinely fuzzy.

**MongoDB community has no ANN index. This tier is NOT a vector store and must not become one.** The
temptation is real, because it is the database that is already there. Resist it: put the semantic
tier where semantic search belongs.

A CRUMB IS A POINTER, NOT A COPY
--------------------------------
The single most useful thing in this store is the breadcrumb, and its value comes entirely from
being small: a marker plus a `ref` to where the detail actually lives. Copy the detail in and you
have made a second source of truth that will drift from the first, silently, and the agent will
eventually cite the stale one with total confidence.

So `Crumb` requires a `ref`. A crumb that cannot say where the real thing is has become the real
thing, badly.

STATE IS THE BEING
------------------
This store is not a cache. It is the continuity - what survives the process, the session, and the
container. Back it up off the box it runs on. A vessel is rebuildable from a Dockerfile; the state
is not rebuildable from anything.
"""
from __future__ import annotations

import os
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from .steps import Evidence, Step, StepFailed

DEFAULT_URL = "mongodb://mongo:27017"
DEFAULT_DB = "agent"


class StateUnavailable(Exception):
    """Raised when the keyed tier cannot be reached or is not usable."""


@dataclass(frozen=True)
class Crumb:
    """A keyed breadcrumb: a POINTER into a source, never a copy of it."""

    key: str
    summary: str
    ref: str
    session: str = ""
    ix: int = 0

    def __post_init__(self) -> None:
        """Reject a crumb with no key, no summary, or - critically - no ref."""
        if not self.key.strip():
            raise ValueError("a crumb needs a key; it is looked up by key or not at all")
        if not self.summary.strip():
            raise ValueError(f"crumb {self.key!r} needs a summary - an empty marker points nowhere")
        if not self.ref.strip():
            raise ValueError(
                f"crumb {self.key!r} needs a `ref`. A crumb is a POINTER, not a copy: without a "
                "reference to where the detail lives, this record IS the detail, and it will drift "
                "from the source it was meant to point at.")

    def render(self) -> str:
        """Return the crumb as it should appear when recalled."""
        return f"[[{self.key}]] {self.summary}  -> {self.ref}"


@dataclass
class KeyedState:
    """The keyed continuity store, backed by MongoDB.

    The driver is imported lazily so that `agentboot` stays importable - and the rest of the boot
    stays runnable - on a machine that has no pymongo. A faculty that is unavailable should degrade
    to an honest failure, never to an import error at the top of the program.
    """

    url: str = field(default_factory=lambda: os.environ.get("AGENT_MONGO_URL", DEFAULT_URL))
    db_name: str = field(default_factory=lambda: os.environ.get("AGENT_MONGO_DB", DEFAULT_DB))
    timeout_ms: int = 3000
    _db: Any = field(default=None, repr=False)

    # ── connection ──────────────────────────────────────────────────────────────────────────
    def open(self) -> KeyedState:
        """Connect and ensure indexes. Idempotent; raises StateUnavailable on failure."""
        if self._db is not None:
            return self
        try:
            from pymongo import MongoClient
            from pymongo.errors import PyMongoError
        except ImportError as exc:
            raise StateUnavailable(
                "pymongo is not installed - the keyed tier is declared but cannot run. A faculty "
                "that is present, wired and unable to work is worse than an absent one.") from exc
        try:
            client = MongoClient(self.url, serverSelectionTimeoutMS=self.timeout_ms)
            client.admin.command("ping")          # force a real round trip, not a lazy handle
            db = client[self.db_name]
            db.crumbs.create_index("key", unique=True)
            db.entities.create_index("name", unique=True)
            db.thoughts.create_index("ts")
        except PyMongoError as exc:
            raise StateUnavailable(f"cannot reach the keyed tier at {self.url}: {exc}") from exc
        self._db = db
        return self

    @property
    def db(self) -> Any:
        """Return the live database handle, opening the connection if needed."""
        if self._db is None:
            self.open()
        return self._db

    # ── crumbs ──────────────────────────────────────────────────────────────────────────────
    def drop_crumb(self, crumb: Crumb) -> str:
        """Store (or replace) a crumb and return its key."""
        self.db.crumbs.replace_one({"key": crumb.key}, asdict(crumb), upsert=True)
        return crumb.key

    def expand(self, key: str) -> Crumb | None:
        """Return the crumb for a key, or None. This is the ~1ms deterministic path."""
        doc = self.db.crumbs.find_one({"key": key}, {"_id": 0})
        return Crumb(**doc) if doc else None

    # ── entities ────────────────────────────────────────────────────────────────────────────
    def remember(self, name: str, **facts: Any) -> str:
        """Record what is known about a named thing, merging with what is already there."""
        if not name.strip():
            raise ValueError("an entity needs a name")
        self.db.entities.update_one({"name": name}, {"$set": facts}, upsert=True)
        return name

    def whois(self, name: str) -> dict | None:
        """Return everything known about a named thing, or None."""
        return self.db.entities.find_one({"name": name}, {"_id": 0})

    # ── the thought log ─────────────────────────────────────────────────────────────────────
    def think(self, text: str, **meta: Any) -> None:
        """Append to the thought log, so the next thought has something to continue from."""
        self.db.thoughts.insert_one({"ts": time.time(), "text": text, **meta})

    def last_thoughts(self, limit: int = 5) -> list[dict]:
        """Return the most recent thoughts, newest first."""
        return list(self.db.thoughts.find({}, {"_id": 0}).sort("ts", -1).limit(limit))

    # ── health ──────────────────────────────────────────────────────────────────────────────
    def roundtrip(self) -> str:
        """Write a probe record, read it back, delete it, and return what proves it worked.

        A TCP connect proves a port is open. A ping proves a server answers. Neither proves this
        agent can actually WRITE ITS MEMORY AND READ IT BACK, which is the only claim that matters -
        a read-only or wrong-permission mount answers ping perfectly.
        """
        marker = f"__probe__{time.time()}"
        self.db.probe.insert_one({"marker": marker})
        found = self.db.probe.find_one({"marker": marker})
        self.db.probe.delete_many({"marker": marker})
        if not found:
            raise StateUnavailable("wrote a probe record and could not read it back")
        return marker

    def summary(self) -> str:
        """Return a one-line count of what continuity is actually held."""
        return (f"{self.db.crumbs.count_documents({})} crumbs, "
                f"{self.db.entities.count_documents({})} entities, "
                f"{self.db.thoughts.count_documents({})} thoughts")

    def step(self, critical: bool = False) -> KeyedStateStep:
        """Return the boot step that proves the keyed tier is genuinely usable."""
        return KeyedStateStep(self, critical=critical)


class KeyedStateStep(Step):
    """Boot step proving the keyed tier accepts a write and returns it."""

    def __init__(self, state: KeyedState, critical: bool = False) -> None:
        """Store the state store this step verifies."""
        super().__init__("state:keyed", critical=critical)
        self.state = state

    def check(self) -> Evidence:
        """Confirm a real write/read round trip, not merely that something answers."""
        try:
            self.state.open()
            self.state.roundtrip()
            detail = self.state.summary()
        except StateUnavailable as exc:
            raise StepFailed(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 - a faculty must not take the boot down
            raise StepFailed(f"{type(exc).__name__}: {exc}") from exc
        return Evidence(f"write+read proven ({detail})", self.state.url)

    def failing_variant(self) -> KeyedStateStep:
        """Return the same step pointed at an address nothing serves."""
        ghost = KeyedState(url="mongodb://127.0.0.1:1/", db_name=self.state.db_name, timeout_ms=300)
        return KeyedStateStep(ghost, critical=self.critical)
