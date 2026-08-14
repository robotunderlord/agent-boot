"""Tests for truthiness.

The properties under test are epistemic, not mechanical: repetition must not count as confirmation,
contradiction must bite harder than agreement lifts, and a claim nothing supports must leave on its
own rather than waiting to be found.
"""
import unittest

from agentboot.truthiness import CEILING, FLOOR, START, Catalogue, Claim, Independence, Source


class RepetitionIsNotConfirmation(unittest.TestCase):
    """A source agreeing with itself has repeated, not confirmed."""

    def test_the_same_source_barely_moves_it(self):
        """Ten agreements from one origin must not reach where one independent agreement does."""
        claim, src = Claim("a thing is so"), Source("only-me")
        for _ in range(10):
            claim.corroborate(src, Independence.SAME)
        solo = claim.truthiness

        other, fresh = Claim("a thing is so"), Source("elsewhere")
        other.corroborate(fresh, Independence.INDEPENDENT)
        self.assertGreater(other.truthiness, solo,
                           "one independent agreement must outweigh ten self-repetitions")

    def test_independence_is_ordered(self):
        """SAME < RELATED < INDEPENDENT, because that is the entire weighting."""
        got = []
        for mode in (Independence.SAME, Independence.RELATED, Independence.INDEPENDENT):
            claim = Claim("x y z")
            claim.corroborate(Source("s"), mode)
            got.append(claim.truthiness)
        self.assertEqual(got, sorted(got))
        self.assertNotEqual(got[0], got[-1])


class ContradictionBitesHarder(unittest.TestCase):
    """A claim nobody has tried to refute has earned nothing."""

    def test_one_contradiction_outweighs_one_agreement(self):
        """Volume of agreement must not drown a single sound objection."""
        up = Claim("x y z")
        up.corroborate(Source("a"), Independence.INDEPENDENT)
        gained = up.truthiness - START

        down = Claim("x y z")
        down.contradict(Source("b"), Independence.INDEPENDENT)
        lost = START - down.truthiness
        self.assertGreater(lost, gained)

    def test_sustained_contradiction_drives_it_toward_the_floor(self):
        """A wrong idea should be leaving, not merely marked."""
        claim = Claim("the deploy is fine because it returned 200")
        for name in ("p1", "p2", "p3", "p4", "p5", "p6"):
            claim.contradict(Source(name), Independence.INDEPENDENT)
        self.assertLess(claim.truthiness, 2.0)


class ConfidenceIsBounded(unittest.TestCase):
    """Nothing becomes certain, and nothing goes negative."""

    def test_it_never_exceeds_the_ceiling(self):
        """Endless agreement approaches certainty without reaching it."""
        claim, src = Claim("x y z"), Source("s")
        for _ in range(200):
            claim.corroborate(src, Independence.INDEPENDENT)
        self.assertLessEqual(claim.truthiness, CEILING)

    def test_it_never_falls_below_the_floor(self):
        """A purged claim is removed, not driven negative."""
        claim = Claim("x y z")
        for _ in range(200):
            claim.contradict(Source("s"), Independence.INDEPENDENT)
        self.assertGreaterEqual(claim.truthiness, FLOOR)

    def test_an_empty_claim_is_refused(self):
        """An empty assertion cannot be corroborated or contradicted."""
        with self.assertRaises(ValueError):
            Claim("   ")

    def test_history_records_what_moved_it(self):
        """A score with no history is an opinion; the trail is what makes it auditable."""
        claim = Claim("x y z")
        claim.corroborate(Source("a"), Independence.INDEPENDENT)
        claim.contradict(Source("b"), Independence.RELATED)
        self.assertEqual(len(claim.history), 2)
        self.assertIn("corroborated", claim.history[0][1])
        self.assertIn("contradicted", claim.history[1][1])


class SourcesEarnTheirStanding(unittest.TestCase):
    """Nothing is trusted for what it is; everything is trusted for what it got right."""

    def test_an_unproven_source_starts_neutral(self):
        """Too few data points is not the same as untrustworthy."""
        self.assertEqual(Source("new").standing, 0.5)

    def test_being_wrong_costs_standing(self):
        """A source that starts being wrong loses standing on the same terms as anything else."""
        good, bad = Source("good"), Source("bad")
        for _ in range(5):
            good.record(upheld=True)
            bad.record(upheld=False)
        self.assertGreater(good.standing, bad.standing)


class TheCatalogueReEvaluatesOnWrite(unittest.TestCase):
    """The moment a similar claim arrives is the only moment new evidence about it exists."""

    def test_a_similar_agreeing_claim_lifts_the_neighbour(self):
        """Corroboration happens on write, not on a sweep."""
        cat = Catalogue()
        first = cat.remember("false failures train the reader to ignore the report", "seat-A")
        before = first.truthiness
        cat.remember("false failures teach you to ignore the report entirely", "seat-B",
                     Independence.INDEPENDENT)
        self.assertGreater(first.truthiness, before)

    def test_a_similar_disagreeing_claim_lowers_it(self):
        """Disagreement is evidence too, and arrives the same way."""
        cat = Catalogue()
        first = cat.remember("the artifact changed after the deploy", "guesser")
        before = first.truthiness
        cat.remember("the artifact never changed after the deploy", "probe",
                     Independence.INDEPENDENT, agrees=False)
        self.assertLess(first.truthiness, before)

    def test_unrelated_claims_do_not_interfere(self):
        """Only SIMILAR claims re-evaluate each other; a catalogue is not a mood."""
        cat = Catalogue()
        first = cat.remember("network isolation needs a route table check", "a")
        before = first.truthiness
        cat.remember("the logo should probably be green", "b", Independence.INDEPENDENT)
        self.assertEqual(first.truthiness, before)

    def test_decayed_claims_purge_themselves(self):
        """A bad idea leaves on its own; nobody has to hunt it."""
        cat = Catalogue()
        cat.remember("a wrong thing about widgets", "guesser")
        for name in ("p1", "p2", "p3", "p4", "p5"):
            cat.challenge("a wrong thing about widgets", name)
        self.assertEqual(cat.claims, [])

    def test_a_challenge_files_no_claim_of_its_own(self):
        """A probe that disproves something has evidence to add and nothing to file."""
        cat = Catalogue()
        cat.remember("the port is open", "guesser")
        cat.challenge("the port is open", "probe")
        self.assertEqual(len(cat.claims), 1, "challenging must not add a negation to the catalogue")


class StandingIsSettledByOutcomes(unittest.TestCase):
    """A source cannot talk its way up; only being right moves it."""

    def test_repetition_does_not_buy_standing(self):
        """Crediting a source for asserting would let volume inflate the weight of its next claim."""
        cat = Catalogue()
        for _ in range(10):
            cat.remember("the same assertion repeated", "loudmouth", Independence.SAME)
        self.assertEqual(cat.source("loudmouth").standing, 0.5)

    def test_a_purge_settles_the_accounts_both_ways(self):
        """The claim's departure is the verdict on everyone who took a side."""
        cat = Catalogue()
        cat.remember("a doomed assertion about widgets", "backer")
        for name in ("p1", "p2", "p3", "p4", "p5"):
            cat.challenge("a doomed assertion about widgets", name)
        # The backer only ever originated it, so settle credits the challengers.
        self.assertGreater(cat.source("p1").upheld, 0)

    def test_backing_wrong_claims_repeatedly_costs_weight(self):
        """Being consistently wrong must eventually cost a source the weight its claims carry."""
        cat = Catalogue()
        subjects = ["the firewall permits inbound telemetry",
                    "the scheduler retries poisoned jobs",
                    "the replica streams without lag",
                    "the certificate covers every hostname"]
        for n, subject in enumerate(subjects):
            claim = cat.remember(subject, "guesser")
            claim.corroborate(cat.source("guesser"), Independence.SAME)
            for probe in range(5):
                cat.challenge(subject, f"probe-{n}-{probe}")
        self.assertEqual(cat.claims, [], "every guess should have been refuted out")
        self.assertLess(cat.source("guesser").standing, 0.5)


class TheScaleIsNotLinearSoItIsNeverAveraged(unittest.TestCase):
    """A bounded map of unbounded evidence has no meaningful distances to average."""

    def test_the_summary_reports_a_shape_not_a_mean(self):
        """A mean of 9.5 and 2.1 is 5.8, which reads neutral and describes no claim held."""
        cat = Catalogue()
        cat.claims = [Claim("nearly proven", truthiness=9.5),
                      Claim("nearly gone", truthiness=2.1)]
        text = cat.summary()
        self.assertNotIn("mean", text)
        self.assertIn("1 believed", text)
        self.assertIn("1 doubted", text)

    def test_the_three_bands_account_for_every_claim(self):
        """A summary that loses claims between its own bands is worse than no summary."""
        cat = Catalogue()
        cat.claims = [Claim("a", truthiness=9.0), Claim("b", truthiness=5.5),
                      Claim("c", truthiness=3.0), Claim("d", truthiness=6.5)]
        believed, unsettled, doubted = (int(n) for n in
                                        __import__("re").findall(r"(\d+) (?:believed|unsettled|doubted)",
                                                                 cat.summary()) or [0, 0, 0])
        self.assertEqual(believed + unsettled + doubted, len(cat.claims))

    def test_an_empty_catalogue_says_so_plainly(self):
        """Zero claims must not render as zero confidence."""
        self.assertEqual(Catalogue().summary(), "0 claims")


if __name__ == "__main__":
    unittest.main()
