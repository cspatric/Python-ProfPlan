"""Unit tests for the RAG indexing service using in-memory fakes."""

from uuid import UUID, uuid4

import pytest

from app.modules.rag.application.indexing_service import IndexingService
from app.modules.rag.domain.chunk import ChunkInput
from app.modules.rag.domain.exceptions import InvalidContentError
from app.modules.rag.infrastructure.models import Chunk


class FakeSession:
    async def commit(self) -> None:
        pass


class FakeChunkRepository:
    def __init__(self) -> None:
        self.rows: list[Chunk] = []

    def add_many(self, chunks) -> None:
        self.rows.extend(chunks)

    async def list_by_content(self, content_id: UUID) -> list[Chunk]:
        return [c for c in self.rows if c.document_content_id == content_id]

    async def delete_by_content(self, content_id: UUID) -> None:
        self.rows = [c for c in self.rows if c.document_content_id != content_id]


class FakeContentRepository:
    def __init__(self, existing: set[UUID]) -> None:
        self._existing = existing

    async def get_by_id(self, content_id: UUID) -> object | None:
        return object() if content_id in self._existing else None


def make_service(existing: set[UUID]) -> tuple[IndexingService, FakeChunkRepository]:
    chunks = FakeChunkRepository()
    service = IndexingService(FakeSession(), chunks, FakeContentRepository(existing))
    return service, chunks


async def test_index_stores_chunks() -> None:
    content_id = uuid4()
    service, chunks = make_service({content_id})

    rows = await service.index_content(
        content_id=content_id,
        chunks=[
            ChunkInput(chunk_index=0, content="a", embedding=[0.1, 0.2]),
            ChunkInput(chunk_index=1, content="b", embedding=[0.3, 0.4]),
        ],
    )
    assert len(rows) == 2
    assert len(chunks.rows) == 2
    assert {c.chunk_index for c in chunks.rows} == {0, 1}


async def test_index_invalid_content_raises() -> None:
    service, _ = make_service(set())
    with pytest.raises(InvalidContentError):
        await service.index_content(
            content_id=uuid4(),
            chunks=[ChunkInput(chunk_index=0, content="a")],
        )


async def test_index_replace_removes_old_chunks() -> None:
    content_id = uuid4()
    service, chunks = make_service({content_id})

    await service.index_content(
        content_id=content_id,
        chunks=[ChunkInput(chunk_index=0, content="old")],
    )
    await service.index_content(
        content_id=content_id,
        chunks=[ChunkInput(chunk_index=0, content="new")],
        replace=True,
    )
    assert len(chunks.rows) == 1
    assert chunks.rows[0].content == "new"
