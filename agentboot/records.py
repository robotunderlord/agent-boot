"""The document store: mongoengine classes that give the records a SHAPE, and pymongo underneath.

WHY AN ODM AND NOT JUST A DICT
-------------------------------
Mongo accepts anything. That is its virtue and, for a store an agent writes into unattended, its
worst property: a field renamed in one code path, a string where a list used to be, a session id
absent because that branch forgot it - all accepted, all silently, and none of it visible until a
query returns half of what it should and nobody can say when the drift started.

So the records are declared as classes. The class is the schema, and a write that does not fit it
fails AT THE WRITE, next to the code that got it wrong, rather than becoming a shape nobody knew was
in there. This matters more for an agent than for an application, because an agent writes at three in
the morning with nobody reading the output.

THE INDEXES ARE PART OF THE SCHEMA, NOT AN OPTIMISATION
---------------------------------------------------------
The log is queried three ways and only three ways: by SESSION (what happened in that run, in order),
by CITATION (what has anyone ever noted about this work), and by SEAT (what did this agent do). Those
indexes are declared on the class because they are the access pattern the design promises - an
unindexed session lookup does not fail, it just gets slower until someone stops using the feature,
which is how a record store quietly becomes write-only.

DEGRADE HONESTLY, NEVER SILENTLY
---------------------------------
mongoengine and pymongo are an OPTIONAL extra. The can must boot and work with neither installed,
because the whole point of the design is that nothing is required to be reachable.

But a missing driver must never turn into a no-op write. This module raises `MongoUnavailable` with
the exact command to fix it, and the triple embedder treats that as a failed destination - so a seat
with no Mongo reports INCOMPLETE writes rather than reporting success and losing the join. A store
that quietly accepts writes it cannot perform is worse than no store at all.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .local_embedding import Destination, Role

INSTALL_HINT = "uv pip install 'agent-boot[mongo]'"


class MongoUnavailable(Exception):
    """Raised when the document store cannot be used, naming exactly how to fix it."""


def _odm() -> Any:
    """Import mongoengine on demand, or raise with the command that installs it.

    Imported lazily and never at module scope: importing at the top would make the driver a hard
    dependency of `agentboot` itself, and the package is supposed to run in a can with nothing but
    the standard library.
    """
    try:
        import mongoengine  # noqa: PLC0415 - deliberate lazy import
    except ImportError as exc:  # pragma: no cover - exercised by the unavailable path
        raise MongoUnavailable(
            f"mongoengine is not installed - run: {INSTALL_HINT}") from exc
    return mongoengine


def define_models(me: Any) -> dict[str, Any]:
    """Build the document classes against a mongoengine module.

    Defined inside a function rather than at import time so the classes exist only when the driver
    does. Takes the module as an argument so the shapes can be exercised against a fake in tests -
    the schema is the thing worth testing, and it should not need a running database to check.
    """
    class Annotated(me.Document):
        """A stenographer's margin note: what a seat observed, against what it was reading."""

        note = me.StringField(required=True)
        seat = me.StringField(required=True)
        session = me.StringField()
        citation = me.StringField()          # book@revision - the EDITION, not just the title
        page = me.IntField()
        refs = me.ListField(me.StringField())
        where = me.StringField()
        at = me.FloatField(required=True)

        meta = {
            "collection": "annotations",
            # The three ways this is ever read. Declared because they are the promise, not a tuning.
            "indexes": ["session", "citation", "seat", ("session", "at")],
        }

    class Held(me.Document):
        """An accessioned work: its address in every store, and the revision that was read."""

        title = me.StringField(required=True)
        origin = me.StringField(required=True, unique=True)
        notation = me.StringField(required=True)
        revision = me.StringField(required=True)
        collection_name = me.StringField()
        namespace = me.StringField()
        accessioned = me.FloatField()

        meta = {"collection": "books", "indexes": ["notation", "origin", "revision"]}

    class Asserted(me.Document):
        """A claim and its stateful truthiness, with the sources that moved it."""

        text = me.StringField(required=True)
        truthiness = me.FloatField(required=True)
        backers = me.DictField()             # source name -> best independence weight
        challengers = me.ListField(me.StringField())
        updated = me.FloatField()

        meta = {"collection": "claims", "indexes": ["truthiness", "text"]}

    class Linked(me.Document):
        """The JOIN: where one remembered thing landed in every other store.

        This is the record that makes a memory unwindable, so `refs` is required. A join with no
        references is the shape of a join without being one, which is worse than its absence
        because it satisfies every check that looks for the document.
        """

        text = me.StringField(required=True)
        refs = me.DictField(required=True)
        session = me.StringField()
        kind = me.StringField()
        at = me.FloatField(required=True)

        meta = {"collection": "joins", "indexes": ["session", "kind"]}

    return {"Annotated": Annotated, "Held": Held, "Asserted": Asserted, "Linked": Linked}


@dataclass
class MongoRecords:
    """Connects the record classes to a database and hands out embedder destinations.

    Holds no opinion about WHERE the database is beyond refusing to invent one: the URI is passed in,
    because a store that defaults to localhost will one day appear to work while writing into a
    throwaway container nobody meant to keep.
    """

    uri: str
    db: str = "agentboot"
    connect: Callable[..., Any] | None = None    # injected for tests; real connect by default
    models: dict[str, Any] = field(default_factory=dict)
    connected: bool = False

    def open(self) -> MongoRecords:
        """Connect and define the models. Raises MongoUnavailable rather than degrading quietly."""
        if not self.uri.strip():
            raise MongoUnavailable("no mongo uri given - refusing to guess at localhost")
        me = _odm()
        connector = self.connect or me.connect
        try:
            connector(db=self.db, host=self.uri, alias="default")
        except Exception as exc:  # noqa: BLE001 - any driver failure is one failure to the caller
            raise MongoUnavailable(f"cannot reach mongo at {self.uri}: {exc}") from exc
        self.models = define_models(me)
        self.connected = True
        return self

    def _require(self, name: str) -> Any:
        """Return a model class, refusing to pretend a closed store is usable."""
        if not self.connected:
            raise MongoUnavailable(f"records not opened - call open() before writing {name}")
        return self.models[name]

    def annotation_destination(self) -> Destination:
        """Return the log destination: every annotation, session-keyed and reference-laced."""
        def write(text: str, record: dict) -> str:
            doc = self._require("Annotated")(
                note=text,
                seat=record.get("seat", ""),
                session=record.get("session", ""),
                citation=record.get("citation", ""),
                page=record.get("page"),
                refs=list(record.get("refs") or []),
                where=record.get("where", ""),
                at=record.get("ts", 0.0),
            )
            doc.save()
            return str(doc.id)

        return Destination("mongo:log", write, required=True)

    def join_destination(self) -> Destination:
        """Return the LINK destination: the record that ties every representation together."""
        def write(text: str, record: dict) -> str:
            refs = record.get("refs") or {}
            if not refs:
                # A join with nothing to join is the failure this store exists to make loud.
                raise ValueError("refusing to write a join with no references - it would be an "
                                 "orphan that satisfies every check for a join without being one")
            doc = self._require("Linked")(
                text=text, refs=dict(refs), session=record.get("session", ""),
                kind=record.get("kind", ""), at=record.get("ts", 0.0))
            doc.save()
            return str(doc.id)

        return Destination("mongo:join", write, required=True, role=Role.LINK)

    def summary(self) -> str:
        """Return a one-line description of the store's state."""
        if not self.connected:
            return f"mongo: not opened ({INSTALL_HINT} if the driver is missing)"
        return f"mongo: {self.db} at {self.uri}, {len(self.models)} record classes"
