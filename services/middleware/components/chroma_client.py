"""
chroma_client.py — ChromaDB retrieval and storage for the Senna middleware.

Responsibilities:
- Query the campaign collection by semantic similarity
- Store new memory chunks written by the write-back pipeline
- Filter by significance for milestone retrieval
- Apply distance threshold so low-quality results don't pollute context

Does NOT:
- Know anything about prompts or injection
- Handle embedding directly (delegated to get_embedding_function())
- Know which campaign it's serving (collection_name is passed in)
"""

from __future__ import annotations
from typing import Any, Optional

from components.config import (
    get_chroma_client,
    get_embedding_function,
    TOP_K,
    MAX_DISTANCE,
    COLLECTION,
)
from components.models import RetrievedMemory, MemorySignificance


class ChromaClient:
    """
    Thin, testable wrapper around ChromaDB for the middleware.

    collection_name is a first-class parameter so the same client class
    serves any campaign — just instantiate with a different collection.
    """

    def __init__(self, collection_name: str = COLLECTION):
        self.collection_name = collection_name
        # Runtime: chromadb Client; tests may assign MagicMock.
        self._client: Any = None
        # Runtime: Chroma Collection; tests may assign MagicMock.
        self._collection: Any = None
        # Any: Chroma's EmbeddingFunction[Embeddable] stubs reject SentenceTransformerEmbeddingFunction.
        self._embedding_fn: Any = None

    def connect(self) -> None:
        """
        Establish connection and get or create the collection.
        Called once at startup. Safe to call multiple times.
        """
        if self._collection is not None:
            return

        import chromadb  # noqa: F401 — imported here so tier 1 tests run without chromadb installed
        if self._embedding_fn is None:
            self._embedding_fn = get_embedding_function()
        self._client = get_chroma_client()
        self._collection = self._client.get_or_create_collection(
            name=self.collection_name,
            embedding_function=self._embedding_fn,
            metadata={"hnsw:space": "cosine"},
        )

    def _ensure_connected(self) -> None:
        if self._collection is None:
            self.connect()

    # ── Retrieval ──────────────────────────────────────────────────────────────

    def query(
        self,
        query_text: str,
        n_results: int = TOP_K,
        max_distance: float = MAX_DISTANCE,
        where: Optional[dict[str, Any]] = None,
    ) -> list[RetrievedMemory]:
        """
        Query the collection by semantic similarity.

        Returns RetrievedMemory objects sorted by relevance (closest first),
        filtered to max_distance. Empty list if nothing relevant is found.

        Args:
            query_text:   Natural language query — embedded automatically.
            n_results:    Maximum results to return before distance filtering.
            max_distance: Cosine distance ceiling. 0.0 = identical, 1.0 = unrelated.
                          Results beyond this are dropped even if n_results isn't filled.
            where:        Optional ChromaDB metadata filter dict.
                          Example: {"tags": {"$contains": "session"}}
        """
        self._ensure_connected()

        try:
            kwargs: dict[str, Any] = {
                "query_texts": [query_text],
                "n_results": n_results,
                "include": ["documents", "metadatas", "distances"],
            }
            if where:
                kwargs["where"] = where

            results = self._collection.query(**kwargs)
        except Exception as e:
            # Return empty rather than crashing the middleware
            # Caller decides whether to surface the error
            raise ChromaQueryError(f"Query failed: {e}") from e

        memories = []
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for doc, meta, dist in zip(documents, metadatas, distances):
            if dist > max_distance:
                continue

            significance = MemorySignificance(
                meta.get("significance", MemorySignificance.NORMAL.value)
            )

            memories.append(RetrievedMemory(
                content=doc,
                source=meta.get("source", "unknown"),
                significance=significance,
                distance=dist,
                session_date=meta.get("date") or meta.get("session_date"),
            ))

        return memories

    def query_milestones(self, query_text: str, n_results: int = 3) -> list[RetrievedMemory]:
        """
        Retrieve milestone-significance memories specifically.

        Milestones use a relaxed distance threshold — they should surface
        even when not tightly semantically matched, because they define
        the relationship and are always worth having in context.
        """
        return self.query(
            query_text=query_text,
            n_results=n_results,
            max_distance=0.75,  # relaxed threshold for milestones
            where={"significance": MemorySignificance.MILESTONE.value},
        )

    def query_high_and_above(
        self, query_text: str, n_results: int = TOP_K
    ) -> list[RetrievedMemory]:
        """
        Retrieve high-significance and milestone memories.
        Useful for pre-session briefs where you want the most important
        content regardless of current topic.
        """
        results = []
        for sig in [MemorySignificance.MILESTONE.value, MemorySignificance.HIGH.value]:
            try:
                results.extend(self.query(
                    query_text=query_text,
                    n_results=n_results,
                    max_distance=0.65,
                    where={"significance": sig},
                ))
            except ChromaQueryError:
                pass  # one significance level failing shouldn't block the other

        # Deduplicate by content, sort by distance
        seen = set()
        deduped = []
        for mem in sorted(results, key=lambda m: m.distance):
            if mem.content not in seen:
                seen.add(mem.content)
                deduped.append(mem)

        return deduped[:n_results]

    # ── Storage ────────────────────────────────────────────────────────────────

    def store(
        self,
        doc_id: str,
        content: str,
        metadata: dict[str, Any],
    ) -> None:
        """
        Store a single memory chunk.

        The embedding function handles embedding automatically.
        metadata must contain only string values (ChromaDB requirement).

        Args:
            doc_id:   Unique identifier. Use a stable hash for upsert safety.
            content:  Text content to embed and store.
            metadata: Flat dict of string values. Must include at least 'source'.
        """
        self._ensure_connected()

        # Enforce ChromaDB's string-only metadata requirement
        safe_meta = {k: str(v) for k, v in metadata.items()}

        try:
            self._collection.upsert(
                ids=[doc_id],
                documents=[content],
                metadatas=[safe_meta],
            )
        except Exception as e:
            raise ChromaStoreError(f"Store failed for {doc_id}: {e}") from e

    def store_batch(self, items: list[dict[str, Any]]) -> None:
        """
        Store multiple chunks in a single upsert call.

        Each item must have: id, content, metadata (flat string dict).
        More efficient than calling store() in a loop.
        """
        self._ensure_connected()

        if not items:
            return

        try:
            self._collection.upsert(
                ids=[item["id"] for item in items],
                documents=[item["content"] for item in items],
                metadatas=[
                    {k: str(v) for k, v in item["metadata"].items()}
                    for item in items
                ],
            )
        except Exception as e:
            raise ChromaStoreError(f"Batch store failed: {e}") from e

    # ── Diagnostics ───────────────────────────────────────────────────────────

    def count(self) -> int:
        """Return total number of chunks in the collection."""
        self._ensure_connected()
        return self._collection.count()

    def heartbeat(self) -> bool:
        """Return True if ChromaDB is reachable."""
        try:
            self._ensure_connected()
            self._client.heartbeat()
            return True
        except Exception:
            return False


# ── Exceptions ────────────────────────────────────────────────────────────────

class ChromaQueryError(Exception):
    """Raised when a ChromaDB query fails."""


class ChromaStoreError(Exception):
    """Raised when a ChromaDB store operation fails."""