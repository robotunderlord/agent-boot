"""Tests for the dispatcher.

The property under test is economic, not functional: the cheap path must be the DEFAULT, the
expensive one must require a stated reason, and deciding between them must itself cost nothing.
"""
import unittest

from agentboot.dispatch import Dispatcher, DispatcherStep, Route, Tier


class AnEscalationMustJustifyItself(unittest.TestCase):
    """An unreasoned escalation is indistinguishable from a default to the expensive tier."""

    def test_route_without_why_is_refused(self):
        """A route that cannot say why it chose its tier is refused at construction."""
        with self.assertRaises(ValueError):
            Route(Tier.SPINE, "")

    def test_every_route_carries_a_reason(self):
        """Whatever the classifier decides, it explains."""
        d = Dispatcher(local_url="http://x/v1", spine_url="http://y/v1")
        for turn in ("expand [[a#1]]", "sure", "design a whole system", "x" * 500):
            self.assertTrue(d.classify(turn).why.strip())


class TheCheapPathIsTheDefault(unittest.TestCase):
    """Most turns must never reach a metered brain."""

    def setUp(self):
        """Build a dispatcher with both tiers configured."""
        self.d = Dispatcher(local_url="http://local/v1", spine_url="http://spine/v1")

    def test_lookup_questions_go_to_recall(self):
        """A lookup wants a fact. Memory answers it exactly; a model guesses at it."""
        for turn in ("what is the gate?", "expand [[db:s#1]]", "where were we", "status"):
            self.assertEqual(self.d.classify(turn).tier, Tier.RECALL, turn)

    def test_a_recall_hit_short_circuits(self):
        """If memory already holds the answer, no model is touched at all."""
        self.assertEqual(self.d.classify("anything at all", recall_hit=True).tier, Tier.RECALL)

    def test_chat_goes_local_not_spine(self):
        """Acknowledgements and small talk are exactly what the resident model is for."""
        self.assertEqual(self.d.classify("yeah that makes sense").tier, Tier.LOCAL)

    def test_real_work_escalates(self):
        """Design and debugging are where a small brain genuinely underperforms."""
        for turn in ("design a migration plan", "why does the build fail?", "refactor this module"):
            self.assertEqual(self.d.classify(turn).tier, Tier.SPINE, turn)

    def test_a_recall_hit_does_not_suppress_real_work(self):
        """A memory hit must not stop genuine work reaching a brain that can do it."""
        self.assertEqual(self.d.classify("design a new plan", recall_hit=True).tier, Tier.SPINE)


class ItWorksWithNoModelAtAll(unittest.TestCase):
    """An agent that can answer from memory with zero brains attached beats one that refuses to run."""

    def test_no_local_brain_degrades_to_recall(self):
        """With nothing configured, everything routes to recall and says so honestly."""
        d = Dispatcher(local_url="", spine_url="")
        route = d.classify("yeah ok")
        self.assertEqual(route.tier, Tier.RECALL)
        self.assertIn("no local brain", route.why)

    def test_no_spine_keeps_work_local_rather_than_failing(self):
        """Without a spine, hard work is answered locally with the limitation stated."""
        d = Dispatcher(local_url="http://local/v1", spine_url="")
        route = d.classify("design a migration plan")
        self.assertEqual(route.tier, Tier.LOCAL)
        self.assertIn("no spine", route.why)

    def test_the_step_passes_with_nothing_configured(self):
        """The main loop must never be a hard failure just because no brain is attached."""
        self.assertFalse(DispatcherStep(Dispatcher(local_url="", spine_url="")).run().status.is_red)

    def test_failing_variant_actually_fails(self):
        """The dispatch check must be provable like every other check."""
        self.assertTrue(DispatcherStep(Dispatcher()).failing_variant().run().status.is_red)


class TheSpendIsAuditable(unittest.TestCase):
    """You cannot manage a bill you cannot see the shape of."""

    def test_profile_counts_every_tier(self):
        """Each dispatched turn lands in exactly one tier's count."""
        d = Dispatcher(local_url="http://local/v1", spine_url="http://spine/v1")
        d.dispatch("what is x?")
        d.dispatch("sure thing")
        d.dispatch("design a system")
        self.assertEqual(d.spend_profile, {"RECALL": 1, "LOCAL": 1, "SPINE": 1})

    def test_summary_reports_the_free_share(self):
        """The number that matters is what fraction never reached a metered brain."""
        d = Dispatcher(local_url="http://local/v1", spine_url="http://spine/v1")
        for _ in range(3):
            d.dispatch("what is x?")
        d.dispatch("design a system")
        self.assertIn("75% free", d.summary())


if __name__ == "__main__":
    unittest.main()
