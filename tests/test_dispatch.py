"""Tests for the dispatcher.

The property under test is economic, not functional: the cheap path must be the DEFAULT, the
expensive one must require a stated reason, and deciding between them must itself cost nothing.
"""
import unittest

from agentboot.dispatch import Dispatcher, DispatcherStep, Region, Route, Tier


class AnEscalationMustJustifyItself(unittest.TestCase):
    """An unreasoned escalation is indistinguishable from a default to the expensive tier."""

    def test_route_without_why_is_refused(self):
        """A route that cannot say why it chose its tier is refused at construction."""
        with self.assertRaises(ValueError):
            Route(Tier.CORTEX, "")

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
            self.assertEqual(self.d.classify(turn).tier, Tier.CORTEX, turn)

    def test_a_recall_hit_does_not_suppress_real_work(self):
        """A memory hit must not stop genuine work reaching a brain that can do it."""
        self.assertEqual(self.d.classify("design a new plan", recall_hit=True).tier, Tier.CORTEX)


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
        self.assertEqual(d.spend_profile, {"RECALL": 1, "LOCAL": 1, "CORTEX": 1})

    def test_summary_reports_the_free_share(self):
        """The number that matters is what fraction never reached a metered brain."""
        d = Dispatcher(local_url="http://local/v1", spine_url="http://spine/v1")
        for _ in range(3):
            d.dispatch("what is x?")
        d.dispatch("design a system")
        self.assertIn("75% free", d.summary())


if __name__ == "__main__":
    unittest.main()


class ThePrefrontalIsPluralAndRecruited(unittest.TestCase):
    """A model is a REGION the agent recruits, not the thing the agent is."""

    REGIONS = (
        Region("triage", "haiku", "triage summarise classify quick", cost=1),
        Region("bulk", "local-gpu", "bulk repetitive transform batch", cost=1),
        Region("deep", "opus", "design architect refactor plan debug", cost=5),
    )

    def setUp(self):
        """Build a dispatcher with a plural roster."""
        self.d = Dispatcher(local_url="http://l/v1", spine_url="http://s/v1", regions=self.REGIONS)

    def test_a_region_must_say_what_it_is_for(self):
        """A roster with no stated purposes is a list, and a list gets used top-down."""
        with self.assertRaises(ValueError):
            Region("nameless", "m", "")

    def test_design_work_recruits_the_deep_region_despite_its_cost(self):
        """REGRESSION: substring matching sent everything to the cheapest region.

        The word "a" in "design A migration plan" is a substring of "tri-A-ge", so every region
        matched every turn and cost alone decided - which looks like thrift and is actually design
        work being handed to a triage model. Whole-token overlap only.
        """
        self.assertEqual(self.d.classify("design a migration plan").region, "deep")

    def test_bulk_work_recruits_the_cheap_local_region(self):
        """Fit beats cost, but among fits the cheap one wins - that is the whole point."""
        self.assertEqual(self.d.classify("implement a transform over the batch").region, "bulk")

    def test_no_match_falls_back_to_cheapest_not_priciest(self):
        """An unrecognised need must not default to the most expensive region."""
        region = self.d.recruit("zzzz qqqq wwww")
        self.assertIn(region.name, ("triage", "bulk"))

    def test_no_roster_is_not_an_error(self):
        """With no regions declared, escalation still routes over the default spine."""
        d = Dispatcher(local_url="http://l/v1", spine_url="http://s/v1")
        self.assertIsNone(d.recruit("anything"))
        self.assertEqual(d.classify("design a system").tier, Tier.CORTEX)
