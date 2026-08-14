"""Tests for the library.

The properties under test are provenance properties. A document cache is easy; what is hard is
noticing that documentation changed underneath an answer you already gave, and these tests exist
mostly to hold that behaviour in place.
"""
import unittest

from agentboot.library import (
    Accession,
    Book,
    Classification,
    Librarian,
    Shelf,
    Unclassified,
)
from agentboot.truthiness import Catalogue


def a_book(title="tls guide", notation="700", rev="abc123def456", pages=None, origin=""):
    """Return a shelvable book with sane defaults."""
    return Book(title=title, origin=origin or f"https://example.invalid/{title}",
                classification=Classification(notation), revision=rev,
                pages=pages if pages is not None else ["page one"])


class ARumourIsNotAReference(unittest.TestCase):
    """A copy you cannot cite or diff has no business in a library."""

    def test_a_book_without_a_revision_is_refused(self):
        """Without a revision there is no diff, no durable citation, and no drift check."""
        with self.assertRaises(ValueError):
            a_book(rev="   ")

    def test_a_citation_survives_the_source_moving(self):
        """The citation must not be the URL, which is the thing that stops resolving."""
        self.assertEqual(a_book(rev="deadbeefcafe99").citation, "tls guide@deadbeefcafe")

    def test_an_unshelved_book_is_refused(self):
        """A work with no address is findable by nothing."""
        with self.assertRaises(Unclassified):
            Classification("")

    def test_a_notation_outside_the_scheme_is_refused(self):
        """Inventing classes at accession time is how a scheme stops meaning anything."""
        with self.assertRaises(Unclassified):
            Classification("42")


class OneDecisionThreeAddresses(unittest.TestCase):
    """Classification places a work in every store at once, or it will be missing from one."""

    def test_collection_and_namespace_derive_from_the_same_notation(self):
        """Two registration steps are two chances to register in only one place."""
        c = Classification("300.6")
        self.assertEqual(c.collection, "lib.300_6")
        self.assertEqual(c.namespace, "lib/300")

    def test_the_vector_namespace_is_scoped_to_the_top_class(self):
        """A semantic question about networking must reach the whole class, not one sub-shelf."""
        self.assertEqual(Classification("300.6").namespace, Classification("300.91").namespace)


class CollectionsOfCollections(unittest.TestCase):
    """Nested shelves are the shape docs arrive in; the traversal has to survive the nesting."""

    def _nested(self):
        """Return a library three levels deep."""
        inner = Shelf("guides").add(a_book("mtls", "700"), a_book("bgp", "300"))
        middle = Shelf("vendor").add(inner, a_book("release notes", "900"))
        return Shelf("library").add(middle, a_book("doctrine", "000"))

    def test_unwind_reaches_every_depth(self):
        """A flatten that stops at the first level silently loses most of the library."""
        self.assertEqual(len(self._nested().holdings()), 4)

    def test_unwind_carries_the_path_that_reached_each_book(self):
        """The path is what a flatten normally destroys and what the rewind needs back."""
        paths = {book.title: path for path, book in self._nested().unwind()}
        self.assertEqual(paths["mtls"], ("library", "vendor", "guides"))
        self.assertEqual(paths["doctrine"], ("library",))

    def test_emit_may_return_nothing_for_a_work(self):
        """Forcing a value for every leaf is how an index fills up with invented entries."""
        def only_security(_path, book):
            if book.classification.root == "700":
                yield "sec", book.title

        self.assertEqual(list(self._nested().emit(only_security)), [("sec", "mtls")])

    def test_rewind_groups_the_emitted_pairs_back(self):
        """Unwind then rewind is one operation; every index in this module is that call."""
        index = self._nested().index()
        self.assertEqual(index["700"], ["mtls@abc123def456"])
        self.assertEqual(sorted(index), ["000", "300", "700", "900"])

    def test_a_reducer_may_collapse_the_group(self):
        """The reduce half must be the caller's, or every index needs its own traversal."""
        def counter(_path, book):
            yield book.classification.root, 1

        self.assertEqual(self._nested().rewind(counter, lambda _k, v: sum(v))["300"], 1)


class ChangedDocumentationChallengesWhatItTaught(unittest.TestCase):
    """The property this module exists for: docs drifting must not silently strand an answer."""

    def _librarian(self):
        """Return a librarian wired to a live catalogue."""
        return Librarian(catalogue=Catalogue())

    def test_a_first_accession_is_fresh_and_challenges_nothing(self):
        """Arriving for the first time is not news about anything."""
        result = self._librarian().accession("bgp handbook", "u://bgp", "300", [], "rev1")
        self.assertTrue(result.fresh)
        self.assertEqual(result.challenged, [])

    def test_the_same_revision_again_is_not_news(self):
        """Re-reading an unchanged document must not disturb anything derived from it."""
        lib = self._librarian()
        lib.accession("bgp handbook", "u://bgp", "300", [], "rev1")
        again = lib.accession("bgp handbook", "u://bgp", "300", [], "rev1")
        self.assertFalse(again.fresh)
        self.assertEqual(again.changed_from, "")

    def test_a_changed_revision_challenges_claims_that_cited_it(self):
        """A doc changing under an answer is exactly the failure nothing else notices."""
        lib = self._librarian()
        lib.catalogue.remember("bgp handbook says sessions never flap", "reader")
        lib.accession("bgp handbook", "u://bgp", "300", [], "rev1")
        before = lib.catalogue.claims[0].truthiness

        changed = lib.accession("bgp handbook", "u://bgp", "300", [], "rev2")
        self.assertEqual(changed.changed_from, "rev1")
        self.assertLess(lib.catalogue.claims[0].truthiness, before)

    def test_unrelated_claims_are_untouched_by_a_doc_change(self):
        """Only what cited the changed work loses standing; this is not a global reset."""
        lib = self._librarian()
        lib.catalogue.remember("the storage array prefers sequential writes", "reader")
        lib.accession("bgp handbook", "u://bgp", "300", [], "rev1")
        before = lib.catalogue.claims[0].truthiness
        lib.accession("bgp handbook", "u://bgp", "300", [], "rev2")
        self.assertEqual(lib.catalogue.claims[0].truthiness, before)

    def test_a_superseded_revision_leaves_the_shelf(self):
        """Holding two revisions of one work means half the answers cite the dead one."""
        lib = self._librarian()
        lib.accession("bgp handbook", "u://bgp", "300", [], "rev1")
        lib.accession("bgp handbook", "u://bgp", "300", [], "rev2")
        held = lib.shelf.holdings()
        self.assertEqual([b.revision for b in held], ["rev2"])

    def test_challenging_survives_having_no_catalogue(self):
        """The provenance join is optional wiring, not a hard dependency."""
        lib = Librarian()
        lib.accession("bgp handbook", "u://bgp", "300", [], "rev1")
        self.assertEqual(lib.accession("bgp handbook", "u://bgp", "300", [], "rev2").challenged, [])


class PagesReachTheStoresCitably(unittest.TestCase):
    """A page recalled without its revision is a fact from nowhere."""

    class _Embedder:
        """Minimal stand-in recording what it was asked to remember."""

        def __init__(self):
            self.seen = []

        def remember(self, text, **meta):
            """Record the write and report success."""
            self.seen.append((text, meta))
            return True

    def test_every_page_is_written_with_its_citation_and_addresses(self):
        """The recall path needs the revision, the collection and the namespace, or it guesses."""
        emb = self._Embedder()
        lib = Librarian(embedder=emb)
        result = lib.accession("mtls", "u://mtls", "700.1", ["a", "b"], "cafe1234")
        self.assertEqual(result.embedded, 2)
        _text, meta = emb.seen[0]
        self.assertEqual(meta["citation"], "mtls@cafe1234")
        self.assertEqual(meta["collection"], "lib.700_1")
        self.assertEqual(meta["namespace"], "lib/700")

    def test_a_pageless_work_still_accessions(self):
        """A work held for its provenance alone is legitimate and must not read as a failure."""
        self.assertTrue(Librarian().accession("index", "u://i", "000", [], "rev1"))

    def test_a_refused_write_is_not_counted_as_embedded(self):
        """Counting attempted writes as landed is how a half-empty library reports full."""
        class Refuses:
            def remember(self, _text, **_meta):
                """Refuse every write the way a downed store does."""
                return False

        result = Librarian(embedder=Refuses()).accession("x", "u://x", "000", ["a"], "rev1")
        self.assertEqual(result.embedded, 0)
        self.assertFalse(result)


class DriftIsReportedNotHidden(unittest.TestCase):
    """Knowing the library has gone stale is worth more than quietly refreshing it."""

    def test_stale_lists_only_works_whose_upstream_moved(self):
        """A sweep that reports everything is the same as reporting nothing."""
        lib = Librarian()
        lib.accession("a", "u://a", "000", [], "rev1")
        lib.accession("b", "u://b", "000", [], "rev1")
        stale = lib.stale({"u://a": "rev9", "u://b": "rev1"})
        self.assertEqual([b.title for b in stale], ["a"])

    def test_an_unknown_origin_is_not_reported_stale(self):
        """Absent evidence is not evidence of drift."""
        lib = Librarian()
        lib.accession("a", "u://a", "000", [], "rev1")
        self.assertEqual(lib.stale({}), [])


class AccessionReportsWhatHappened(unittest.TestCase):
    """The render is what a human reads; it has to distinguish the three cases."""

    def test_a_change_is_rendered_loudly(self):
        """New, unchanged and CHANGED must not look alike in the log."""
        book = a_book(pages=[])
        text = Accession(book=book, fresh=False, changed_from="0011223344",
                         challenged=["x"]).render()
        self.assertIn("UPSTREAM CHANGED", text)
        self.assertIn("1 claim(s) challenged", text)

    def test_a_new_acquisition_reads_differently_from_a_re_verification(self):
        """Silence about which case occurred is what makes a log unreadable."""
        book = a_book(pages=[])
        self.assertIn("new acquisition", Accession(book=book, fresh=True).render())
        self.assertIn("re-verified", Accession(book=book, fresh=False).render())


if __name__ == "__main__":
    unittest.main()
