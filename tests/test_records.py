"""Tests for the document store.

The schema is the thing worth testing and it should not need a running database to check, so the
models are exercised against a stand-in mongoengine. What is under test is the PROMISE: the required
fields, the declared indexes, and that a missing driver never becomes a silent no-op write.
"""
import unittest

from agentboot.records import INSTALL_HINT, MongoRecords, MongoUnavailable, define_models


class FakeField:
    """Records how a field was declared."""

    def __init__(self, *args, **kw):
        """Keep the declaration for inspection."""
        self.args, self.kw = args, kw


class FakeDocument:
    """Stand-in base recording nothing; the class body is what the tests read."""


class FakeME:
    """A mongoengine-shaped module good enough to declare classes against."""

    Document = FakeDocument
    StringField = IntField = FloatField = DictField = ListField = FakeField

    def __init__(self):
        """Record connect() calls."""
        self.connected = []

    def connect(self, **kw):
        """Record a connection attempt."""
        self.connected.append(kw)
        return object()


def models():
    """Return the declared model classes."""
    return define_models(FakeME())


class TheClassIsTheSchema(unittest.TestCase):
    """Mongo accepts anything; the class is what makes a wrong write fail next to the wrong code."""

    def test_every_record_type_is_declared(self):
        """A record with no class is a shape nobody knows is in there."""
        self.assertEqual(sorted(models()), ["Annotated", "Asserted", "Held", "Linked"])

    def test_an_annotation_requires_its_note_and_its_seat(self):
        """Unattributed marginalia cannot be judged, and an empty note records nothing."""
        annotated = models()["Annotated"]
        self.assertTrue(annotated.note.kw["required"])
        self.assertTrue(annotated.seat.kw["required"])

    def test_a_join_requires_its_references(self):
        """A join with no refs satisfies every check for a join without being one."""
        self.assertTrue(models()["Linked"].refs.kw["required"])

    def test_a_held_work_requires_a_revision(self):
        """Without a revision there is no diff, no durable citation, and no drift check."""
        self.assertTrue(models()["Held"].revision.kw["required"])


class TheIndexesArePartOfThePromise(unittest.TestCase):
    """An unindexed lookup does not fail; it gets slower until the feature stops being used."""

    def test_the_log_is_indexed_the_three_ways_it_is_read(self):
        """By session, by citation, by seat - the access pattern the design promises."""
        indexes = models()["Annotated"].meta["indexes"]
        for expected in ("session", "citation", "seat"):
            self.assertIn(expected, indexes)

    def test_the_session_timeline_is_indexed_as_a_compound(self):
        """'What happened in that run, in order' is one query, not a sort over everything."""
        self.assertIn(("session", "at"), models()["Annotated"].meta["indexes"])

    def test_a_work_is_findable_by_notation_and_by_origin(self):
        """Browsing by shelf and looking up by source are both first-class."""
        indexes = models()["Held"].meta["indexes"]
        self.assertIn("notation", indexes)
        self.assertIn("origin", indexes)


class ItDegradesLoudlyNeverSilently(unittest.TestCase):
    """A store that quietly accepts writes it cannot perform is worse than no store."""

    def test_writing_before_opening_raises(self):
        """A closed store must not pretend to be usable."""
        with self.assertRaises(MongoUnavailable):
            MongoRecords(uri="mongodb://x").annotation_destination().write("note", {})

    def test_an_empty_uri_is_refused_rather_than_guessed(self):
        """Defaulting to localhost writes into a throwaway nobody meant to keep."""
        with self.assertRaises(MongoUnavailable) as caught:
            MongoRecords(uri="  ").open()
        self.assertIn("refusing to guess", str(caught.exception))

    def test_the_error_names_the_command_that_fixes_it(self):
        """An unusable store should not also be a puzzle."""
        self.assertIn("agent-boot[mongo]", INSTALL_HINT)
        self.assertIn(INSTALL_HINT, MongoRecords(uri="").summary())

    def test_a_failed_write_is_a_failed_destination_not_a_no_op(self):
        """The triple embedder must see INCOMPLETE, not success with a missing join."""
        from agentboot.local_embedding import TripleEmbedder

        records = MongoRecords(uri="mongodb://unreachable")
        embedder = TripleEmbedder().add(records.annotation_destination())
        self.assertFalse(embedder.remember("a finding"))


class TheJoinRefusesToBeAnOrphan(unittest.TestCase):
    """Losing the join costs the ability to unwind anything, so it fails loudly."""

    def _opened(self):
        """Return an opened store backed by the stand-in."""
        fake = FakeME()
        records = MongoRecords(uri="mongodb://x", connect=fake.connect)
        records.models = define_models(fake)
        records.connected = True
        return records

    def test_a_join_with_no_refs_is_refused(self):
        """It would be an orphan that passes every check that looks for a join."""
        write = self._opened().join_destination().write
        with self.assertRaises(ValueError):
            write("text", {"refs": {}})

    def test_the_join_destination_is_declared_as_the_link_role(self):
        """The join must be written LAST, with the leaves' ids in hand."""
        from agentboot.local_embedding import Role

        self.assertIs(self._opened().join_destination().role, Role.LINK)


if __name__ == "__main__":
    unittest.main()
