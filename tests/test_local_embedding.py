"""Tests for the triple embedder.

The property under test is honesty about partial writes. A memory that landed in two stores out of
three has begun drifting from itself, and nothing downstream will notice for weeks unless the write
says so at the time.
"""
import unittest

from agentboot.local_embedding import Destination, EmbedRefused, EmbedStep, TripleEmbedder


def ok_write(_text, _record):
    """Accept a write."""
    return None


def dead_write(_text, _record):
    """Refuse a write the way a downed backend does."""
    raise ConnectionError("backend down")


class PartialSuccessIsNotSuccess(unittest.TestCase):
    """Landing in some stores and reporting success is the drift this class exists to prevent."""

    def test_all_destinations_landing_is_truthy(self):
        """The happy path names every store it reached."""
        e = TripleEmbedder().add(Destination("rag", ok_write), Destination("mongo", ok_write))
        result = e.remember("something worth keeping")
        self.assertTrue(result)
        self.assertIn("rag", result.render())

    def test_a_required_failure_is_falsy(self):
        """A required store failing must NOT report success, however many others accepted."""
        e = TripleEmbedder().add(Destination("rag", ok_write), Destination("mongo", dead_write))
        result = e.remember("x")
        self.assertFalse(result)
        self.assertIn("INCOMPLETE", result.render())
        self.assertIn("mongo", result.render())

    def test_an_optional_failure_still_succeeds_but_says_so(self):
        """Optional means the write stands - it does not mean the loss goes unmentioned."""
        e = TripleEmbedder().add(Destination("rag", ok_write),
                                 Destination("log", dead_write, required=False))
        result = e.remember("x")
        self.assertTrue(result)
        self.assertIn("did NOT land", result.render())

    def test_one_store_failing_does_not_lose_the_others(self):
        """A backend being down is a fact to report, not a reason to drop the working writes."""
        landed = []
        e = TripleEmbedder().add(Destination("dead", dead_write),
                                 Destination("live", lambda t, r: landed.append(t)))
        e.remember("keep me")
        self.assertEqual(landed, ["keep me"])


class ItRefusesWhatItCannotDoSafely(unittest.TestCase):
    """Some failures are reasons not to write at all."""

    def test_a_remote_embedder_is_refused(self):
        """Embedding remotely exports everything you chose to remember, silently, at write time."""
        e = TripleEmbedder(embed_endpoint="https://api.example.com/v1").add(
            Destination("rag", ok_write))
        with self.assertRaises(EmbedRefused):
            e.remember("private thing")

    def test_localhost_embedder_is_allowed(self):
        """A locally served model never puts the text on a wire."""
        e = TripleEmbedder(embed_endpoint="http://127.0.0.1:8080/v1").add(
            Destination("rag", ok_write))
        self.assertTrue(e.remember("private thing"))

    def test_empty_text_is_refused(self):
        """A memory that cannot be recalled is not a memory."""
        with self.assertRaises(ValueError):
            TripleEmbedder().add(Destination("rag", ok_write)).remember("   ")

    def test_a_destination_needs_a_writer(self):
        """A destination that cannot be written to is a silent hole."""
        with self.assertRaises(ValueError):
            Destination("broken", None)


class TheBootStepWritesForReal(unittest.TestCase):
    """Configured destinations prove nothing; a read-only store passes every check but the write."""

    def test_no_destinations_is_a_failure_not_a_pass(self):
        """Remembering into nothing must be loud, not quietly fine."""
        self.assertTrue(EmbedStep(TripleEmbedder()).run().status.is_red)

    def test_a_working_embedder_passes(self):
        """A real probe write through every required store is the evidence."""
        e = TripleEmbedder().add(Destination("rag", ok_write), Destination("mongo", ok_write))
        self.assertFalse(EmbedStep(e).run().status.is_red)

    def test_failing_variant_actually_fails(self):
        """The memory check must be provable like every other check."""
        e = TripleEmbedder().add(Destination("rag", ok_write))
        self.assertTrue(EmbedStep(e).failing_variant().run().status.is_red)


if __name__ == "__main__":
    unittest.main()
