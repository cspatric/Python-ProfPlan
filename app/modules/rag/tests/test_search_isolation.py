"""Unit tests for RAG tenant isolation at the search layer.

The similarity search must never run without an ownership scope, otherwise one
user's query could match another user's chunks.
"""

from uuid import uuid4

from app.modules.rag.application.search_service import SearchService


class _FakeChunk:
    def __init__(self):
        self.uuid = uuid4()
        self.document_content_id = uuid4()
        self.content = "chunk text"


class _RecordingChunks:
    """A repository stub that records whether it was queried."""

    def __init__(self):
        self.called = False

    async def search_similar(self, embedding, *, limit, content_ids):
        self.called = True
        return [(_FakeChunk(), 0.1)]


class TestSearchIsolation:
    async def test_empty_scope_returns_nothing_without_touching_the_db(self):
        repo = _RecordingChunks()
        service = SearchService(repo)

        results = await service.search(query_embedding=[0.1, 0.2], content_ids=[])

        assert results == []
        assert repo.called is False  # never runs an unscoped search

    async def test_scoped_search_returns_mapped_results(self):
        repo = _RecordingChunks()
        service = SearchService(repo)

        results = await service.search(
            query_embedding=[0.1, 0.2], content_ids=[uuid4()]
        )

        assert repo.called is True
        assert len(results) == 1
        assert results[0].content == "chunk text"
