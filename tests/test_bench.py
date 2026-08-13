"""Tests for the bench.

The properties worth enforcing are methodological: a probe must be able to fail, a miss must be
distinguishable from slowness, and a verdict must come from the median rather than the best run.
"""
import unittest

from agentboot.bench import Bench, Probe, Verdict


class AProbeMustBeAbleToFail(unittest.TestCase):
    """A probe with nothing to check against reports healthy forever."""

    def test_probe_without_expect_is_refused(self):
        """No marker means no measurement."""
        with self.assertRaises(ValueError):
            Probe("empty", lambda: "anything", "")


class AMissIsNotSlowness(unittest.TestCase):
    """FADING is the actionable verdict and must never be confused with a slow hit."""

    def test_a_miss_is_fading_however_fast_it_returned(self):
        """Returning the wrong thing instantly is still a miss, not a FAST pass."""
        bench = Bench().add(Probe("gone", lambda: "", "never-present"))
        bench.run(n=3)
        self.assertIs(bench.results[0].verdict, Verdict.FADING)
        self.assertTrue(bench.results[0].verdict.is_miss)

    def test_a_hit_is_graded_by_latency(self):
        """A correct answer from a resident source is FAST."""
        bench = Bench().add(Probe("resident", lambda: "the marker is here", "marker"))
        bench.run(n=3)
        self.assertIs(bench.results[0].verdict, Verdict.FAST)

    def test_a_raising_probe_is_fading_not_a_crash(self):
        """A broken probe must degrade to a result, never take the bench down."""

        def boom():
            raise RuntimeError("backend gone")

        bench = Bench().add(Probe("broken", boom, "anything"))
        bench.run(n=3)
        self.assertIs(bench.results[0].verdict, Verdict.FADING)
        self.assertIn("RuntimeError", bench.results[0].error)

    def test_report_names_the_fading_probes(self):
        """The report must surface what rotted, because that is the only decay signal."""
        bench = Bench(label="x").add(Probe("gone", lambda: "", "never-present"))
        bench.run(n=3)
        self.assertIn("FADING is the actionable verdict", bench.report())
        self.assertIn("gone", bench.report())


class TheBootIsWhatIsUnderTest(unittest.TestCase):
    """Comparing two runs is the only output that answers the question worth asking."""

    def _bench(self, label, answer):
        """Return a run of one fixed probe against a given answer."""
        b = Bench(label=label).add(Probe("p1", lambda: answer, "marker"))
        b.run(n=3)
        return b

    def test_compare_reports_per_probe_deltas(self):
        """A comparison is per-probe, because an average hides which change mattered."""
        a = self._bench("boot A", "marker here")
        b = self._bench("boot B", "marker here")
        out = a.compare(b)
        self.assertIn("boot A", out)
        self.assertIn("boot B", out)
        self.assertIn("p1", out)

    def test_compare_refuses_when_no_probes_are_shared(self):
        """Different questions make two runs incomparable, and it says so rather than averaging."""
        a = Bench(label="A").add(Probe("p1", lambda: "marker", "marker"))
        b = Bench(label="B").add(Probe("p2", lambda: "marker", "marker"))
        a.run(n=3)
        b.run(n=3)
        self.assertIn("not comparable", a.compare(b))

    def test_a_verdict_change_is_called_out(self):
        """A tier change matters more than a millisecond count and must be visible."""
        a = self._bench("A", "marker")
        b = self._bench("B", "")
        self.assertIn("FADING", a.compare(b))


if __name__ == "__main__":
    unittest.main()
