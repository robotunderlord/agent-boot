"""Tests for the semantic tier.

The rules worth enforcing are the privacy refusal and the chunking, both testable without a model.
"""
import unittest
from pathlib import Path

from agentboot.semantic import CHUNK_CHARS, Chunk, SemanticStore, SemanticStep, SemanticUnavailable, chunk_text


class ARemoteEmbedderIsRefused(unittest.TestCase):
    """Embedding ships the text elsewhere. Indexing a private corpus remotely exports the corpus."""

    def test_remote_endpoint_is_refused(self):
        """A non-local embedder raises rather than warning."""
        store = SemanticStore(embed_endpoint="https://api.example.com/v1/embeddings")
        with self.assertRaises(SemanticUnavailable) as ctx:
            store._refuse_remote_embedder()
        self.assertIn("REMOTE", str(ctx.exception))

    def test_localhost_is_allowed(self):
        """A locally served model is fine - the text never leaves the machine."""
        for url in ("http://localhost:8080/embed", "http://127.0.0.1:11434/v1", "http://[::1]:9/x"):
            SemanticStore(embed_endpoint=url)._refuse_remote_embedder()   # must not raise

    def test_unset_is_allowed(self):
        """No endpoint means the bundled local embedder, which is the default and the safe path."""
        SemanticStore(embed_endpoint="")._refuse_remote_embedder()

    def test_refusal_happens_before_any_indexing(self):
        """open() must refuse first, so a remote endpoint can never index even one chunk."""
        store = SemanticStore(embed_endpoint="https://api.example.com/v1")
        with self.assertRaises(SemanticUnavailable):
            store.open()


class ChunksKeepAnArgumentIntact(unittest.TestCase):
    """A chunk cut mid-sentence retrieves as a fragment that reads like a different claim."""

    def test_paragraphs_are_packed_not_sliced(self):
        """Short paragraphs pack into one chunk rather than becoming many."""
        text = "one short para.\n\nanother short para.\n\na third."
        self.assertEqual(len(chunk_text(text, "f.md")), 1)

    def test_oversized_input_splits(self):
        """Packing stops before the size limit rather than producing one enormous chunk."""
        para = "x" * (CHUNK_CHARS // 2)
        chunks = chunk_text("\n\n".join([para] * 5), "f.md")
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(c.text) <= CHUNK_CHARS * 2 for c in chunks))

    def test_empty_text_yields_nothing(self):
        """Whitespace is not a chunk."""
        self.assertEqual(chunk_text("   \n\n  ", "f.md"), [])

    def test_chunk_ids_are_stable(self):
        """A re-index must UPDATE a chunk, not append a duplicate of it."""
        a = Chunk("some text", "doc.md", 2)
        b = Chunk("some DIFFERENT text", "doc.md", 2)
        self.assertEqual(a.id, b.id, "id must key on source+ordinal so re-indexing upserts")
        self.assertNotEqual(a.id, Chunk("some text", "doc.md", 3).id)


class TheFacultyFailsHonestly(unittest.TestCase):
    """An unusable semantic tier reports FAIL; it does not take the boot down."""

    def test_missing_corpus_raises_named_error(self):
        """No corpus is a named failure with the path in it."""
        store = SemanticStore(corpus=Path("/nonexistent-corpus"))
        with self.assertRaises(SemanticUnavailable):
            store.index()

    def test_step_goes_red_rather_than_raising(self):
        """A broken semantic tier is a red line, not an exception."""
        store = SemanticStore(embed_endpoint="https://api.example.com/v1")
        self.assertTrue(SemanticStep(store).run().status.is_red)

    def test_failing_variant_actually_fails(self):
        """The semantic check must be provable like every other check."""
        store = SemanticStore(embed_endpoint="https://api.example.com/v1")
        self.assertTrue(SemanticStep(store).failing_variant().run().status.is_red)

    def test_not_critical_by_default(self):
        """Losing fuzzy recall must not hold the gate that stops the agent acting."""
        self.assertFalse(SemanticStore().step().critical)


if __name__ == "__main__":
    unittest.main()
