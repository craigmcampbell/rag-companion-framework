"""
test_chroma_client.py — Tests for the ChromaDB client.

Tier 1: Pure logic tests using mocks. No ChromaDB connection required.
         Tests filtering, error handling, deduplication, metadata coercion.

Tier 3: Live integration tests. Requires ChromaDB running on configured port.
         Tests real upsert/query round-trips against a test collection.

Note: There is no tier 2 here — the ChromaDB client has no AI inference.
      Tier 3 replaces what would be tier 2 for this component.
"""

import sys
import os
import hashlib
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from components.chroma_client import ChromaClient, ChromaQueryError, ChromaStoreError
from components.models import RetrievedMemory, MemorySignificance


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_chroma_result(
    documents: list[str],
    distances: list[float],
    metadatas: list[dict] | None = None,
) -> dict:
    """Build a mock ChromaDB query result in the expected shape."""
    if metadatas is None:
        metadatas = [{"source": f"Sessions/test_{i}.md"} for i in range(len(documents))]
    return {
        "documents": [documents],
        "distances": [distances],
        "metadatas": [metadatas],
    }


def make_mock_client(query_result: dict | None = None) -> ChromaClient:
    """Return a ChromaClient with a fully mocked ChromaDB collection."""
    client = ChromaClient(collection_name="test_collection")
    mock_collection = MagicMock()
    if query_result is not None:
        mock_collection.query.return_value = query_result
    client._collection = mock_collection
    client._client = MagicMock()
    return client


# ── Tier 1: Pure logic ────────────────────────────────────────────────────────

def test_query_returns_retrieved_memories():
    result = make_chroma_result(
        documents=["Garion returned from the job"],
        distances=[0.15],
        metadatas=[{"source": "Sessions/2024-03-15.md", "significance": "normal"}],
    )
    client = make_mock_client(result)
    memories = client.query("job return")
    assert len(memories) == 1
    assert isinstance(memories[0], RetrievedMemory)
    assert memories[0].content == "Garion returned from the job"
    assert memories[0].distance == 0.15
    assert memories[0].source == "Sessions/2024-03-15.md"


def test_query_filters_by_max_distance():
    result = make_chroma_result(
        documents=["relevant memory", "irrelevant memory"],
        distances=[0.2, 0.8],
    )
    client = make_mock_client(result)
    memories = client.query("something", max_distance=0.5)
    assert len(memories) == 1
    assert memories[0].content == "relevant memory"


def test_query_all_filtered_returns_empty():
    result = make_chroma_result(
        documents=["very distant memory"],
        distances=[0.9],
    )
    client = make_mock_client(result)
    memories = client.query("something", max_distance=0.5)
    assert memories == []


def test_query_significance_defaults_to_normal():
    result = make_chroma_result(
        documents=["a memory"],
        distances=[0.2],
        metadatas=[{"source": "World/Vethara.md"}],  # no significance key
    )
    client = make_mock_client(result)
    memories = client.query("vethara")
    assert memories[0].significance == MemorySignificance.NORMAL


def test_query_preserves_milestone_significance():
    result = make_chroma_result(
        documents=["they bought the house"],
        distances=[0.1],
        metadatas=[{"source": "Sessions/2024-06-01.md", "significance": "milestone"}],
    )
    client = make_mock_client(result)
    memories = client.query("house")
    assert memories[0].significance == MemorySignificance.MILESTONE


def test_query_surfaces_session_date_from_date_key():
    result = make_chroma_result(
        documents=["a session memory"],
        distances=[0.2],
        metadatas=[{"source": "Sessions/test.md", "date": "2024-03-15"}],
    )
    client = make_mock_client(result)
    memories = client.query("memory")
    assert memories[0].session_date == "2024-03-15"


def test_query_surfaces_session_date_from_session_date_key():
    result = make_chroma_result(
        documents=["a session memory"],
        distances=[0.2],
        metadatas=[{"source": "Sessions/test.md", "session_date": "2024-03-22"}],
    )
    client = make_mock_client(result)
    memories = client.query("memory")
    assert memories[0].session_date == "2024-03-22"


def test_query_passes_where_filter():
    result = make_chroma_result(documents=[], distances=[])
    client = make_mock_client(result)
    client.query("something", where={"significance": "milestone"})
    call_kwargs = client._collection.query.call_args.kwargs
    assert call_kwargs["where"] == {"significance": "milestone"}


def test_query_no_where_filter_by_default():
    result = make_chroma_result(documents=[], distances=[])
    client = make_mock_client(result)
    client.query("something")
    call_kwargs = client._collection.query.call_args.kwargs
    assert "where" not in call_kwargs


def test_query_raises_chroma_query_error_on_failure():
    client = make_mock_client()
    client._collection.query.side_effect = Exception("connection refused")
    try:
        client.query("something")
        assert False, "Should have raised ChromaQueryError"
    except ChromaQueryError as e:
        assert "connection refused" in str(e)


def test_store_coerces_metadata_to_strings():
    client = make_mock_client()
    client.store(
        doc_id="test_id",
        content="some content",
        metadata={"chunk": 0, "significance": "high", "score": 0.95},
    )
    call_kwargs = client._collection.upsert.call_args.kwargs
    stored_meta = call_kwargs["metadatas"][0]
    assert all(isinstance(v, str) for v in stored_meta.values())
    assert stored_meta["chunk"] == "0"
    assert stored_meta["score"] == "0.95"


def test_store_raises_chroma_store_error_on_failure():
    client = make_mock_client()
    client._collection.upsert.side_effect = Exception("write failed")
    try:
        client.store("id", "content", {"source": "test.md"})
        assert False, "Should have raised ChromaStoreError"
    except ChromaStoreError as e:
        assert "write failed" in str(e)


def test_store_batch_empty_list_is_noop():
    client = make_mock_client()
    client.store_batch([])
    client._collection.upsert.assert_not_called()


def test_store_batch_coerces_all_metadata():
    client = make_mock_client()
    client.store_batch([
        {"id": "a", "content": "first", "metadata": {"chunk": 0}},
        {"id": "b", "content": "second", "metadata": {"chunk": 1}},
    ])
    call_kwargs = client._collection.upsert.call_args.kwargs
    for meta in call_kwargs["metadatas"]:
        assert all(isinstance(v, str) for v in meta.values())


def test_query_milestones_uses_relaxed_distance():
    """Milestones should use a more relaxed distance threshold than standard queries."""
    result = make_chroma_result(documents=[], distances=[])
    client = make_mock_client(result)

    original_query = client.query
    with patch.object(client, "query", wraps=original_query) as mock_query:
        client.query_milestones("house on thresher lane")
        call_kwargs = mock_query.call_args.kwargs
        assert call_kwargs["max_distance"] > 0.5  # relaxed vs standard 0.5


def test_query_high_and_above_deduplicates():
    """If the same content appears in both milestone and high results, dedup it."""
    shared_content = "they bought the house on Thresher Lane"

    milestone_result = make_chroma_result(
        documents=[shared_content],
        distances=[0.1],
        metadatas=[{"source": "Sessions/2024-06-01.md", "significance": "milestone"}],
    )
    high_result = make_chroma_result(
        documents=[shared_content],
        distances=[0.15],
        metadatas=[{"source": "Sessions/2024-06-01.md", "significance": "high"}],
    )

    client = make_mock_client()
    call_count = 0

    def side_effect(**kwargs):
        nonlocal call_count
        result = milestone_result if call_count == 0 else high_result
        call_count += 1
        # Parse the where filter to return appropriate result
        return result

    client._collection.query.side_effect = side_effect
    memories = client.query_high_and_above("house")

    contents = [m.content for m in memories]
    assert contents.count(shared_content) == 1


def test_heartbeat_returns_true_when_connected():
    client = make_mock_client()
    client._client.heartbeat.return_value = True
    assert client.heartbeat() is True


def test_heartbeat_returns_false_on_failure():
    client = make_mock_client()
    client._client.heartbeat.side_effect = Exception("unreachable")
    assert client.heartbeat() is False


def test_count_delegates_to_collection():
    client = make_mock_client()
    client._collection.count.return_value = 42
    assert client.count() == 42


# ── Tier 3: Live integration ──────────────────────────────────────────────────

async def run_live_integration():
    """
    Requires ChromaDB running at configured host:port.
    Uses an isolated test collection that is cleaned up after.
    """
    TEST_COLLECTION = "middleware_test_collection"

    client = ChromaClient(collection_name=TEST_COLLECTION)

    try:
        client.connect()
    except Exception as e:
        raise AssertionError(f"Could not connect to ChromaDB: {e}")

    try:
        # Store a known document
        doc_id = hashlib.md5(b"test_doc_senna").hexdigest()
        client.store(
            doc_id=doc_id,
            content="Senna solved the resonance problem — components match the caster, not the spell.",
            metadata={
                "source": "Sessions/test.md",
                "significance": "high",
                "date": "2024-03-22",
                "note_title": "test",
            },
        )

        # Query for it
        memories = client.query("resonance caster spell", n_results=3)
        assert len(memories) >= 1, "Expected at least one result for known content"
        assert any("resonance" in m.content for m in memories), \
            "Expected stored content to be retrievable"

        # Verify distance is reasonable
        best = min(memories, key=lambda m: m.distance)
        assert best.distance < 0.5, f"Distance {best.distance} too high for known content"

        # Verify metadata survived
        assert best.significance == MemorySignificance.HIGH
        assert best.session_date == "2024-03-22"

        # Verify count increased
        count = client.count()
        assert count >= 1

        # Batch store
        items = [
            {
                "id": hashlib.md5(f"batch_{i}".encode()).hexdigest(),
                "content": f"Batch test document {i}",
                "metadata": {"source": f"Sessions/batch_{i}.md", "chunk": str(i)},
            }
            for i in range(3)
        ]
        client.store_batch(items)
        assert client.count() >= 4

    finally:
        # Clean up test collection
        if client._client:
            try:
                client._client.delete_collection(TEST_COLLECTION)
            except Exception:
                pass


# ── Test runner ───────────────────────────────────────────────────────────────

async def run(tier: int = 1):
    tier1_tests = [
        test_query_returns_retrieved_memories,
        test_query_filters_by_max_distance,
        test_query_all_filtered_returns_empty,
        test_query_significance_defaults_to_normal,
        test_query_preserves_milestone_significance,
        test_query_surfaces_session_date_from_date_key,
        test_query_surfaces_session_date_from_session_date_key,
        test_query_passes_where_filter,
        test_query_no_where_filter_by_default,
        test_query_raises_chroma_query_error_on_failure,
        test_store_coerces_metadata_to_strings,
        test_store_raises_chroma_store_error_on_failure,
        test_store_batch_empty_list_is_noop,
        test_store_batch_coerces_all_metadata,
        test_query_milestones_uses_relaxed_distance,
        test_query_high_and_above_deduplicates,
        test_heartbeat_returns_true_when_connected,
        test_heartbeat_returns_false_on_failure,
        test_count_delegates_to_collection,
    ]

    failed = []
    for test in tier1_tests:
        try:
            test()
        except Exception as e:
            failed.append((test.__name__, str(e)))

    if failed:
        msg = "\n".join(f"  {name}: {err}" for name, err in failed)
        raise AssertionError(f"{len(failed)} tier 1 test(s) failed:\n{msg}")

    if tier >= 3:
        await run_live_integration()