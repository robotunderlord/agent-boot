"""Tests for the common tongue.

The property under test is that a dispatched agent cannot get to work unprimed or unable to record.
Everything else here is convenience; those two are the reason the module exists.
"""
import unittest
from pathlib import Path

from agentboot.common_tongue import (
    Annotation,
    CommonTongue,
    NotCertified,
    Seat,
    Stenographer,
)
from agentboot.lessons import Ledger, Lesson
from agentboot.local_embedding import Destination, TripleEmbedder
from agentboot.reflex_hook import ReflexHook


def a_seat(**kw):
    """Return a named seat with sane defaults."""
    return Seat(**{"name": "hobbit-1", "errand": "audit the ingress", "session": "s-1", **kw})


def wired(**kw):
    """Return an embedder whose writes all succeed."""
    return TripleEmbedder().add(Destination("vector", lambda t, r: "v1"),
                                Destination("log", lambda t, r: "l1"), **kw)


class AnUnprimedAgentIsRefused(unittest.TestCase):
    """Who and where are the two questions an unprimed agent gets wrong first."""

    def test_a_seat_must_be_named(self):
        """An unnamed seat cannot be held to anything it records."""
        with self.assertRaises(ValueError):
            Seat(name="  ")

    def test_the_shared_checkout_is_called_out_loudly(self):
        """Acting correctly in the wrong place is the expensive mistake this prevents."""
        text = a_seat(isolated=False).orient()
        self.assertIn("SHARED checkout", text)
        self.assertIn("do not write here", text)

    def test_an_isolated_tree_does_not_raise_the_caution(self):
        """A warning that fires always is a warning nobody reads."""
        self.assertNotIn("CAUTION", a_seat(isolated=True).orient())

    def test_an_unkeyed_session_is_stated_not_hidden(self):
        """Annotations that cannot group are worth knowing about before the work, not after."""
        self.assertIn("unkeyed", Seat(name="x", session="").orient())

    def test_where_names_the_host_and_the_tree(self):
        """'Where am I' must be answerable without ambiguity."""
        where = a_seat(cwd=Path("/srv/work"), isolated=True).where
        self.assertIn("/srv/work", where)
        self.assertIn("isolated tree", where)


class CertificationIsDemonstratedNotDeclared(unittest.TestCase):
    """An agent that cannot record must not be permitted to find."""

    def test_no_stores_means_not_certified(self):
        """Findings that exist for one turn are findings nobody will inherit."""
        with self.assertRaises(NotCertified):
            CommonTongue(seat=a_seat()).certify()

    def test_a_store_that_refuses_writes_fails_certification(self):
        """Configured is not working; only a real write proves a real write."""
        def dead(_t, _r):
            raise ConnectionError("down")

        tongue = CommonTongue(seat=a_seat(),
                              embedder=TripleEmbedder().add(Destination("log", dead)))
        with self.assertRaises(NotCertified):
            tongue.certify()

    def test_a_working_seat_certifies(self):
        """The happy path performs an actual probe write."""
        self.assertTrue(CommonTongue(seat=a_seat(), embedder=wired()).certify().certified)

    def test_the_brief_says_so_when_uncertified(self):
        """An agent must not read a brief that implies it can record when it cannot."""
        self.assertIn("NOT CERTIFIED", CommonTongue(seat=a_seat()).brief())


class TheLogIsRequiredForAnAgentSeat(unittest.TestCase):
    """For a background service the log is optional. For an agent it is the reasoning."""

    def test_the_agent_profile_marks_the_log_required(self):
        """Losing the log silently keeps the conclusions and discards the reasoning."""
        emb = CommonTongue.stores(vector=lambda t, r: "v", log=lambda t, r: "l",
                                  join=lambda t, r: None)
        log = next(d for d in emb.destinations if d.name == "log")
        self.assertTrue(log.required)

    def test_a_dead_log_fails_the_write_for_an_agent(self):
        """This is the override: the general-purpose default would have called this a success."""
        def dead(_t, _r):
            raise ConnectionError("down")

        emb = CommonTongue.stores(vector=lambda t, r: "v", log=dead, join=lambda t, r: None)
        self.assertFalse(emb.remember("a finding"))


class NoMonitorsByDesign(unittest.TestCase):
    """Twelve hobbits arming watchers is twelve watchers on one event, outliving all of them."""

    def test_the_brief_states_the_omission_and_the_reason(self):
        """A silent omission reads as an oversight and gets 'helpfully' added back."""
        text = CommonTongue(seat=a_seat(), embedder=wired()).certify().brief()
        self.assertIn("monitors", text)
        self.assertIn("orchestrator", text)


class StenographyHappensDuringTheWork(unittest.TestCase):
    """An agent that batches its notes to the last turn loses them all when interrupted."""

    def _steno(self):
        """Return a stenographer over a recording embedder."""
        seen = []
        emb = TripleEmbedder().add(Destination("log", lambda t, r: seen.append(r)))
        return Stenographer(seat=a_seat(), embedder=emb), seen

    def test_an_annotation_reaches_the_stores_immediately(self):
        """Written now, while the reason for it is still known."""
        steno, seen = self._steno()
        steno.annotate("the ingress VIP answers but does not route")
        self.assertEqual(len(seen), 1)

    def test_the_record_carries_session_seat_and_refs(self):
        """A log indexed by session and laced with references is what makes it retrievable."""
        steno, seen = self._steno()
        steno.annotate("checked", citation="bgp@abc123", refs=("https://x.invalid/rfc",))
        record = seen[0]
        self.assertEqual(record["session"], "s-1")
        self.assertEqual(record["seat"], "hobbit-1")
        self.assertEqual(record["refs"], ["https://x.invalid/rfc"])
        self.assertEqual(record["citation"], "bgp@abc123")

    def test_an_unattributed_note_is_refused(self):
        """Marginalia nobody can attribute cannot be judged."""
        with self.assertRaises(ValueError):
            Annotation(note="something", seat="  ")

    def test_an_empty_note_is_refused(self):
        """An empty annotation records nothing while looking like a record."""
        with self.assertRaises(ValueError):
            Annotation(note="   ", seat="x")


class CliffsNotesWithThePreviousOwnersNotations(unittest.TestCase):
    """A second-hand textbook is worth more than a clean one."""

    def _read(self):
        """Return a stenographer holding notes from two prior readers of one work."""
        steno = Stenographer(seat=a_seat(), embedder=wired())
        steno.annotate("section 4 is wrong about defaults", citation="mtls@aaaa1111", page=4)
        steno.annotate("the real answer is in appendix B", citation="mtls@aaaa1111", page=9)
        steno.annotate("unrelated note", citation="bgp@ffff9999")
        return steno

    def test_marginalia_are_scoped_to_the_work(self):
        """Notes from a different book are noise, not context."""
        self.assertEqual(len(self._read().marginalia("mtls@aaaa1111")), 2)

    def test_notes_from_an_older_edition_are_returned_but_marked(self):
        """Withholding them loses hard-won knowledge; presenting them plainly misleads."""
        text = self._read().cliffs("mtls@bbbb2222")
        self.assertIn("section 4 is wrong", text)
        self.assertIn("PREVIOUS EDITION", text)

    def test_notes_on_the_current_edition_are_not_marked_stale(self):
        """A caveat that fires on everything is a caveat that means nothing."""
        self.assertNotIn("PREVIOUS EDITION", self._read().cliffs("mtls@aaaa1111"))

    def test_a_work_with_no_prior_readers_says_so(self):
        """Silence would read as 'nothing worth noting', which is a different claim."""
        self.assertIn("no previous owner", self._read().cliffs("new@0000"))


class ReflexesFireForTheSituationOnly(unittest.TestCase):
    """The brief must not degenerate into the whole ledger."""

    def _tongue(self):
        """Return a certified tongue over a one-lesson ledger."""
        ledger = Ledger()
        ledger.add(Lesson(id="L-001", tell="deleting a docker volume with state in it",
                          trade="check what is IN the volume before removing it",
                          cost="lost a database"))
        return CommonTongue(seat=a_seat(), embedder=wired(),
                            reflexes=ReflexHook(ledger=ledger)).certify()

    def test_a_matching_situation_fires(self):
        """The one line that mattered has to arrive at the moment of action."""
        self.assertIn("L-001", self._tongue().brief("deleting a docker volume with state in it"))

    def test_an_unrelated_situation_stays_silent(self):
        """Silence is the normal case; a brief that always speaks is a poster."""
        self.assertNotIn("L-001", self._tongue().brief("rename a variable in the css"))


if __name__ == "__main__":
    unittest.main()
