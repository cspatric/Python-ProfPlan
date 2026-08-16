"""Unit tests for the RAG retrieval service using fakes."""

from uuid import UUID, uuid4

from app.modules.rag.application.retrieval_service import RetrievalService
from app.modules.rag.domain.chunk import SearchResult


class FakeEmbedder:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def embed_text(self, text: str) -> list[float]:
        self.calls.append(text)
        return [0.1, 0.2, 0.3]


class FakeSearch:
    def __init__(self) -> None:
        self.last_content_ids: list[UUID] | None = None
        self.last_query_text: str | None = None

    async def search(self, *, query_embedding, limit, content_ids, query_text=None):
        self.last_content_ids = list(content_ids) if content_ids else None
        self.last_query_text = query_text
        return [
            SearchResult(
                chunk_id=str(uuid4()),
                document_content_id=str(uuid4()),
                content="hit",
                distance=0.1,
            )
        ]


class FakeContents:
    def __init__(self, content_ids: list[UUID]) -> None:
        self._content_ids = content_ids

    async def list_content_ids_for_user(self, user_id, subject_id=None):
        return self._content_ids


async def test_query_embeds_and_scopes_to_user_contents() -> None:
    content_ids = [uuid4(), uuid4()]
    embedder, search = FakeEmbedder(), FakeSearch()
    service = RetrievalService(embedder, search, FakeContents(content_ids))

    results = await service.query(user_id=uuid4(), query="fotossintese", limit=3)

    assert embedder.calls == ["fotossintese"]
    assert search.last_content_ids == content_ids
    assert len(results) == 1


async def test_query_without_any_content_returns_empty() -> None:
    embedder, search = FakeEmbedder(), FakeSearch()
    service = RetrievalService(embedder, search, FakeContents([]))

    results = await service.query(user_id=uuid4(), query="x")

    assert results == []
    assert embedder.calls == []  # no embedding call when nothing to search


async def test_the_words_reach_the_search_not_only_their_embedding() -> None:
    """The lexical half of a hybrid search needs the text itself. Dropping it
    here would leave the feature switched on and doing nothing, which is worse
    than switched off: nobody would look."""
    content_id = uuid4()
    search = FakeSearch()
    service = RetrievalService(FakeEmbedder(), search, FakeContents([content_id]))

    await service.query(user_id=uuid4(), query="van Helmont willow experiment")

    assert search.last_query_text == "van Helmont willow experiment"
