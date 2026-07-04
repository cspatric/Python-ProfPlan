"""Integration test for RAG retrieval: scoped cosine search over real data."""

import pytest

from app.core.constants import EMBEDDING_DIMENSIONS
from app.core.security import hash_password
from app.infrastructure.database.session import SessionFactory
from app.modules.documents.application.document_service import (
    DocumentContentService,
    DocumentService,
)
from app.modules.documents.infrastructure.repository import (
    DocumentContentRepository,
    DocumentRepository,
)
from app.modules.rag.application.indexing_service import IndexingService
from app.modules.rag.application.retrieval_service import RetrievalService
from app.modules.rag.application.search_service import SearchService
from app.modules.rag.domain.chunk import ChunkInput
from app.modules.rag.infrastructure.repository import ChunkRepository
from app.modules.subjects.infrastructure.models import Subject
from app.modules.subjects.infrastructure.repository import SubjectRepository
from app.modules.users.infrastructure.repository import UserRepository

pytestmark = pytest.mark.integration


class StubEmbedder:
    """Returns a fixed query embedding, so tests don't depend on Ollama."""

    def __init__(self, vector: list[float]) -> None:
        self._vector = vector

    async def embed_text(self, text: str) -> list[float]:
        return self._vector


def _vec(*head: float) -> list[float]:
    vector = [0.0] * EMBEDDING_DIMENSIONS
    for i, value in enumerate(head):
        vector[i] = float(value)
    return vector


async def test_retrieval_returns_nearest_and_scopes_to_owner() -> None:
    async with SessionFactory() as session:
        owner = await UserRepository(session).create(
            name="Owner",
            email="owner@test.com",
            password_hash=hash_password("Senha@123"),
        )
        subject = Subject(user_id=owner.uuid, name="Biology")
        session.add(subject)
        await session.commit()

        documents = DocumentService(
            session, DocumentRepository(session), SubjectRepository(session)
        )
        document = await documents.register(
            user_id=owner.uuid,
            subject_id=subject.uuid,
            title="Notes",
            document_path="notes.md",
        )
        contents = DocumentContentService(
            session,
            DocumentContentRepository(session),
            DocumentRepository(session),
        )
        content = await contents.add_content(
            user_id=owner.uuid, document_id=document.uuid, markdown="# Notes"
        )
        indexing = IndexingService(
            session, ChunkRepository(session), DocumentContentRepository(session)
        )
        await indexing.index_content(
            content_id=content.uuid,
            chunks=[
                ChunkInput(chunk_index=0, content="cats", embedding=_vec(1, 0)),
                ChunkInput(chunk_index=1, content="dogs", embedding=_vec(0, 1)),
            ],
        )

        # Second user with no documents.
        other = await UserRepository(session).create(
            name="Other",
            email="other@test.com",
            password_hash=hash_password("Senha@123"),
        )

        retrieval = RetrievalService(
            StubEmbedder(_vec(0.9, 0.1)),
            SearchService(ChunkRepository(session)),
            DocumentContentRepository(session),
        )
        owner_results = await retrieval.query(
            user_id=owner.uuid, query="felines", limit=2
        )
        other_results = await retrieval.query(user_id=other.uuid, query="felines")

    assert [r.content for r in owner_results] == ["cats", "dogs"]
    assert other_results == []
