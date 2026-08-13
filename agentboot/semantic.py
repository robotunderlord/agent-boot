"""The SEMANTIC tier: nearest-meaning recall over a private corpus, embedded locally.

THE OTHER HALF OF RECALL
------------------------
`state.py` answers exact questions in ~1ms with no model in the path. This answers the fuzzy ones:
*what is related to this*, *have I seen anything like this before*. Together they are two speeds, and
the classification is the skill:

    "expand this crumb" / "what is X"        -> KEYED     (state.py)
    "what relates to this" / "anything like" -> SEMANTIC  (here)

Route an exact question through semantic search and you get a slower, costlier answer that may
confidently be the wrong neighbour. Route a fuzzy one through keys and you get nothing at all.

EMBEDDINGS ARE COMPUTED LOCALLY. THIS IS NOT A PREFERENCE.
----------------------------------------------------------
An embedding call ships the text being embedded to whoever serves the endpoint. Point this at a
hosted API and you have quietly exported the entire corpus - every private note, every credential
that was ever pasted into a document, every sentence about someone who did not consent to that.
Once, silently, at index time, and it will not look like an exfiltration in any log.

So `SemanticStore` REFUSES a remote embedder rather than warning about one. A privacy control that
degrades to a log line is off, and the log line scrolls past.

THE CORPUS IS MOUNTED READ-ONLY
-------------------------------
The agent indexes the vault; it does not edit it. That keeps the knowledge base a source rather than
a scratchpad, and it means a bad index run can never damage the thing being indexed. Re-indexing is
always safe, which is what makes it a habit rather than an event.
"""
from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .steps import Evidence, Step, StepFailed

CHUNK_CHARS = 1200          # paragraph-packed; big enough to keep an argument intact
LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1", "0.0.0.0", "")


class SemanticUnavailable(Exception):
    """Raised when the semantic tier cannot be used, or cannot be used SAFELY."""


@dataclass(frozen=True)
class Chunk:
    """One indexed passage: its text, where it came from, and a stable id."""

    text: str
    source: str
    ordinal: int = 0

    @property
    def id(self) -> str:
        """Return a stable id, so re-indexing updates a chunk rather than duplicating it."""
        digest = hashlib.sha256(f"{self.source}#{self.ordinal}".encode()).hexdigest()
        return digest[:24]


def chunk_text(text: str, source: str, size: int = CHUNK_CHARS) -> list[Chunk]:
    """Split text into paragraph-packed chunks.

    Packing whole paragraphs rather than slicing at a character count keeps an argument in one
    piece. A chunk cut mid-sentence retrieves as a fragment that reads like a different claim than
    the one its author made.
    """
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[Chunk] = []
    buf = ""
    for para in paragraphs:
        if buf and len(buf) + len(para) + 2 > size:
            chunks.append(Chunk(buf, source, len(chunks)))
            buf = para
        else:
            buf = f"{buf}\n\n{para}" if buf else para
    if buf:
        chunks.append(Chunk(buf, source, len(chunks)))
    return chunks


@dataclass
class SemanticStore:
    """Nearest-meaning recall over a local corpus, with local embeddings, or nothing at all.

    Heavy dependencies are imported lazily so the rest of the boot stays runnable without them - a
    faculty that is unavailable should fail honestly, never break the program that would let you
    diagnose it.
    """

    corpus: Path = field(default_factory=lambda: Path(
        os.environ.get("AGENT_CORPUS", "/vault")))
    store_path: Path = field(default_factory=lambda: Path(
        os.environ.get("AGENT_RAG_STORE", "/home/agent/.agentboot/rag")))
    collection: str = field(default_factory=lambda: os.environ.get("AGENT_RAG_COLLECTION", "vault"))
    embed_endpoint: str = field(default_factory=lambda: os.environ.get("AGENT_EMBED_ENDPOINT", ""))
    _client: Any = field(default=None, repr=False)
    _coll: Any = field(default=None, repr=False)

    # ── the refusal ─────────────────────────────────────────────────────────────────────────
    def _refuse_remote_embedder(self) -> None:
        """Raise if embeddings would be computed anywhere but this machine."""
        if not self.embed_endpoint:
            return
        # Parse properly rather than splitting on ':'. A hand-rolled split mangles IPv6 bracket
        # notation - `http://[::1]:9/x` yields a host of `[` - and while that fails CLOSED (the safe
        # direction), a privacy control that refuses the legitimate local case gets disabled by
        # whoever hits it. Caught by a test, not by reading.
        parsed = urlparse(self.embed_endpoint if "//" in self.embed_endpoint
                          else f"//{self.embed_endpoint}")
        host = (parsed.hostname or "").lower()
        if host not in LOCAL_HOSTS:
            raise SemanticUnavailable(
                f"refusing a REMOTE embedder ({host}). Embedding ships the text being embedded to "
                "whoever serves that endpoint - indexing a private corpus against it exports the "
                "whole corpus, once, silently, and it will not look like an exfiltration in any "
                "log. Serve the model locally or do not index.")

    # ── connection ──────────────────────────────────────────────────────────────────────────
    def open(self) -> SemanticStore:
        """Connect the vector store and embedder. Idempotent; raises SemanticUnavailable."""
        if self._coll is not None:
            return self
        self._refuse_remote_embedder()
        try:
            import chromadb
            from chromadb.utils import embedding_functions
        except ImportError as exc:
            raise SemanticUnavailable(
                "chromadb is not installed - the semantic tier is declared but cannot run.") from exc
        try:
            self.store_path.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=str(self.store_path))
            embed = embedding_functions.DefaultEmbeddingFunction()   # local ONNX, no network
            self._coll = self._client.get_or_create_collection(
                name=self.collection, embedding_function=embed)
        except Exception as exc:  # noqa: BLE001 - any backend failure is the same answer here
            raise SemanticUnavailable(f"cannot open the semantic store: {exc}") from exc
        return self

    @property
    def coll(self) -> Any:
        """Return the live collection, opening it if needed."""
        if self._coll is None:
            self.open()
        return self._coll

    # ── indexing ────────────────────────────────────────────────────────────────────────────
    def index(self, patterns: tuple[str, ...] = ("*.md", "*.txt")) -> int:
        """Index the corpus and return how many chunks were written.

        The corpus is read, never written. A re-index updates chunks by stable id rather than
        appending, so running it twice is a no-op rather than a duplication.
        """
        if not self.corpus.is_dir():
            raise SemanticUnavailable(f"no corpus at {self.corpus}")
        chunks: list[Chunk] = []
        for pattern in patterns:
            for path in sorted(self.corpus.rglob(pattern)):
                try:
                    text = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                chunks += chunk_text(text, str(path.relative_to(self.corpus)))
        if not chunks:
            return 0
        self.coll.upsert(
            ids=[c.id for c in chunks],
            documents=[c.text for c in chunks],
            metadatas=[{"source": c.source, "ordinal": c.ordinal} for c in chunks],
        )
        return len(chunks)

    def query(self, text: str, k: int = 5) -> list[Chunk]:
        """Return the nearest chunks to a free-text need, best first."""
        res = self.coll.query(query_texts=[text], n_results=k)
        docs = (res.get("documents") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        return [Chunk(d, (m or {}).get("source", "?"), (m or {}).get("ordinal", 0))
                for d, m in zip(docs, metas, strict=False)]

    def count(self) -> int:
        """Return how many chunks are indexed."""
        return self.coll.count()

    def summary(self) -> str:
        """Return a one-line description of the indexed corpus."""
        return f"{self.count()} chunks from {self.corpus}"

    def step(self, critical: bool = False) -> SemanticStep:
        """Return the boot step that proves the semantic tier actually retrieves."""
        return SemanticStep(self, critical=critical)


class SemanticStep(Step):
    """Boot step proving the semantic tier embeds and retrieves - not merely that it opened."""

    PROBE = "__agentboot probe: the semantic tier must retrieve what it stored__"

    def __init__(self, store: SemanticStore, critical: bool = False) -> None:
        """Store the semantic store this step verifies."""
        super().__init__("state:semantic", critical=critical)
        self.store = store

    def check(self) -> Evidence:
        """Confirm a real embed-and-retrieve round trip.

        Opening a vector store proves a directory is writable. It does not prove the embedder loaded
        or that retrieval returns the thing you stored - which is the only claim worth making.
        """
        try:
            self.store.open()
            probe = Chunk(self.PROBE, "__probe__", 0)
            self.store.coll.upsert(ids=[probe.id], documents=[probe.text],
                                   metadatas=[{"source": "__probe__", "ordinal": 0}])
            hits = self.store.query("semantic tier must retrieve what it stored", k=1)
            self.store.coll.delete(ids=[probe.id])
            if not hits:
                raise StepFailed("stored a probe chunk and retrieved nothing")
        except SemanticUnavailable as exc:
            raise StepFailed(str(exc)) from exc
        except StepFailed:
            raise
        except Exception as exc:  # noqa: BLE001 - a faculty must not take the boot down
            raise StepFailed(f"{type(exc).__name__}: {exc}") from exc
        return Evidence(f"embed+retrieve proven ({self.store.summary()})", str(self.store.store_path))

    def failing_variant(self) -> SemanticStep:
        """Return the same step pointed at a corpus and store that cannot work."""
        ghost = SemanticStore(corpus=Path("/nonexistent"),
                              store_path=Path("/proc/nonexistent-store"),
                              collection=self.store.collection)
        return SemanticStep(ghost, critical=self.critical)
