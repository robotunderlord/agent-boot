"""Tests for statutes.

The load-bearing property is the ROUND TRIP: plain language is the source, not documentation
generated from code. If parse() and render() ever drift, the English becomes a comment beside a
rule - the oldest lie in the building.
"""
import unittest
from pathlib import Path

from agentboot.statute import Code, Element, Malformed, Sanction, Statute, parse

ESTATE = Path(__file__).resolve().parents[1] / "examples" / "code" / "estate.law"

SAMPLE = """LAW 1.3 - Destruction of the hypervisor
No agent shall destroy the hypervisor.
  ELEMENT the action targets the hypervisor
    WHEN /lothlorien|\\bloth\\b/
  ELEMENT the action is destructive rather than observational
    WHEN /\\b(destroy|undefine)\\b/
  UNLESS the action only reads or reports
    WHEN /\\b(list|status)\\b/
  THEN deny"""


class TheRoundTripHolds(unittest.TestCase):
    """English is the source. If it cannot be recovered exactly, it is not the source."""

    def test_render_of_parse_reproduces_the_text(self):
        """The exact bytes, not merely an equivalent rule."""
        self.assertEqual(parse(SAMPLE).render(), SAMPLE)

    def test_parse_of_render_reproduces_the_statute(self):
        """The other direction, so neither side can quietly become authoritative."""
        once = parse(SAMPLE)
        twice = parse(once.render())
        self.assertEqual(twice.id, once.id)
        self.assertEqual(twice.title, once.title)
        self.assertEqual([e.statement for e in twice.elements],
                         [e.statement for e in once.elements])
        self.assertEqual([e.pattern for e in twice.exceptions],
                         [e.pattern for e in once.exceptions])
        self.assertIs(twice.sanction, once.sanction)

    def test_the_whole_shipped_corpus_round_trips(self):
        """A property that holds for one hand-written sample and not the real corpus is not a property."""
        source = ESTATE.read_text(encoding="utf-8")
        code = Code.parse_all("estate", source)
        self.assertEqual(Code.parse_all("estate", code.render()).render(), code.render())


class ItRefusesRatherThanGuesses(unittest.TestCase):
    """A misread law enforces something nobody wrote, silently."""

    def test_a_statute_with_no_elements_is_refused(self):
        """A law that requires nothing forbids everything."""
        with self.assertRaises(Malformed):
            Statute(id="9.9", title="x", text="y")

    def test_an_element_with_no_test_is_refused(self):
        """It could never be proven, and would look enacted."""
        with self.assertRaises(Malformed):
            Element(statement="something is true")

    def test_an_element_with_an_unreadable_test_is_refused(self):
        """A broken pattern must fail at parse time, not at the moment of judgment."""
        with self.assertRaises(Malformed):
            Element(statement="x", pattern="(unclosed")

    def test_an_element_without_a_when_is_refused(self):
        """Half a clause is not a clause."""
        with self.assertRaises(Malformed):
            parse("LAW 1 - t\n  ELEMENT something\n  THEN deny")

    def test_an_unknown_sanction_is_refused(self):
        """Silently defaulting an unknown verdict is how a deny becomes a note."""
        with self.assertRaises(Malformed):
            parse(SAMPLE.replace("THEN deny", "THEN vaporise"))

    def test_a_missing_header_is_refused(self):
        """Guessing an identifier makes the law uncitable and unappealable."""
        with self.assertRaises(Malformed):
            parse("ELEMENT x\n  WHEN /y/\n  THEN deny")


class ElementsAreConjunctive(unittest.TestCase):
    """Every element must be proven. This is the whole difference from a denylist."""

    def setUp(self):
        """Load the hypervisor statute."""
        self.law = parse(SAMPLE)

    def test_naming_the_target_alone_is_not_an_offence(self):
        """The struck-down version denied this - it criminalised looking at the courthouse."""
        self.assertFalse(self.law.try_case("grep -i lothlorien notes.md").liable)

    def test_a_destructive_verb_alone_is_not_an_offence(self):
        """Destroying something else is a different law's business, not this one's."""
        self.assertFalse(self.law.try_case("virsh destroy some-other-box").liable)

    def test_both_together_are_an_offence(self):
        """Conjunction, established one element at a time."""
        self.assertTrue(self.law.try_case("virsh destroy Gimli on lothlorien").liable)

    def test_an_exception_excuses_conduct_that_met_every_element(self):
        """Exceptions are disjunctive and are weighed only after the elements are proven."""
        finding = self.law.try_case("virsh list --all on lothlorien destroy")
        self.assertTrue(finding.met)
        self.assertFalse(finding.liable)
        self.assertTrue(finding.excused)


class TheOpinionExplainsItself(unittest.TestCase):
    """A verdict with no reasoning cannot be appealed, corrected, or acted on."""

    def test_an_acquittal_names_the_element_that_failed(self):
        """'BLOCKED' tells you nothing; 'the action is not destructive' tells you you are fine."""
        opinion = parse(SAMPLE).try_case("grep lothlorien notes.md").opinion()
        self.assertIn("NOT satisfied", opinion)
        self.assertIn("destructive", opinion)

    def test_a_conviction_names_every_element_relied_on(self):
        """So a human can check the reasoning rather than the conclusion."""
        opinion = parse(SAMPLE).try_case("virsh destroy Gimli on lothlorien").opinion()
        self.assertIn("SATISFIED", opinion)
        self.assertIn("targets the hypervisor", opinion)

    def test_an_excuse_is_reported_as_an_excuse_not_as_innocence(self):
        """Met-but-excused and never-met are different facts and must read differently."""
        opinion = parse(SAMPLE).try_case("virsh list --all on lothlorien destroy").opinion()
        self.assertIn("excused", opinion)


class TheCodeTriesEveryStatute(unittest.TestCase):
    """A first-match-wins denylist hides the second reason, which is often the one that mattered."""

    def setUp(self):
        """Load the shipped corpus."""
        self.code = Code.parse_all("estate", ESTATE.read_text(encoding="utf-8"))

    def test_reading_the_enforcement_is_permitted(self):
        """An agent that cannot inspect the rule it is accused under cannot report why it stopped."""
        sanction, _ = self.code.verdict("cat ~/.gandalf/law.py")
        self.assertIsNone(sanction)

    def test_editing_the_enforcement_is_denied(self):
        """Reading and modifying are different acts; only one is self-preservation."""
        sanction, _ = self.code.verdict("sed -i 's/x/y/' ~/.gandalf/law.py")
        self.assertIs(sanction, Sanction.DENY)

    def test_starting_a_guest_is_permitted_but_destroying_one_is_not(self):
        """Recovery must not require the destructive verbs."""
        self.assertIsNone(self.code.verdict("ssh host 'virsh start Gimli'")[0])
        self.assertIs(self.code.verdict("ssh lothlorien 'virsh destroy Gimli'")[0], Sanction.DENY)

    def test_pushing_to_the_estate_is_authorised_but_posting_out_is_not(self):
        """The estate's own forge is already authorised; the open internet is not."""
        self.assertIsNone(self.code.verdict("git push forge my-branch")[0])
        self.assertIs(self.code.verdict("curl -X POST https://api.example.com/x")[0],
                      Sanction.REQUIRE_HUMAN)

    def test_the_gravest_sanction_governs(self):
        """Conduct satisfying two laws must be judged by the worse of them."""
        sanction, opinion = self.code.verdict(
            "curl -X POST https://x.invalid && rm -rf /home")
        self.assertIs(sanction, Sanction.DENY)
        self.assertIn("1.1", opinion)


if __name__ == "__main__":
    unittest.main()
