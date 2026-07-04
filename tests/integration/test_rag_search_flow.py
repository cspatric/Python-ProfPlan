"""Integration test for the RAG pipeline: index chunks and search by vector."""

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
from app.modules.rag.application.search_service import SearchService
from app.modules.rag.domain.chunk import ChunkInput
from app.modules.rag.infrastructure.repository import ChunkRepository
from app.modules.subjects.infrastructure.models import Subject
from app.modules.subjects.infrastructure.repository import SubjectRepository
from app.modules.users.infrastructure.repository import UserRepository

pytestmark = pytest.mark.integration


def _vec(*head: float) -> list[float]:
    """Build an embedding of the right dimension from a few leading values."""
    vector = [0.0] * EMBEDDING_DIMENSIONS
    for i, value in enumerate(head):
        vector[i] = float(value)
    return vector


async def test_index_and_vector_search_returns_nearest_chunk() -> None:
    async with SessionFactory() as session:
        user = await UserRepository(session).create(
            name="RAG",
            email="rag@test.com",
            password_hash=hash_password("Senha@123"),
        )
        subject = Subject(user_id=user.uuid, name="Biology")
        session.add(subject)
        await session.commit()

        documents = DocumentService(
            session, DocumentRepository(session), SubjectRepository(session)
        )
        document = await documents.register(
            user_id=user.uuid,
            subject_id=subject.uuid,
            title="Notes",
            document_path="notes.pdf",
        )

        contents = DocumentContentService(
            session,
            DocumentContentRepository(session),
            DocumentRepository(session),
        )
        content = await contents.add_content(
            user_id=user.uuid, document_id=document.uuid, markdown="# Notes"
        )

        indexing = IndexingService(
            session, ChunkRepository(session), DocumentContentRepository(session)
        )
        await indexing.index_content(
            content_id=content.uuid,
            chunks=[
                ChunkInput(chunk_index=0, content="about cats", embedding=_vec(1, 0)),
                ChunkInput(chunk_index=1, content="about dogs", embedding=_vec(0, 1)),
            ],
        )

        search = SearchService(ChunkRepository(session))
        results = await search.search(query_embedding=_vec(0.9, 0.1), limit=2)

    assert len(results) == 2
    assert results[0].content == "about cats"
    assert results[0].distance < results[1].distance


async def test_search_can_be_scoped_to_content_ids() -> None:
    async with SessionFactory() as session:
        user = await UserRepository(session).create(
            name="RAG2",
            email="rag2@test.com",
            password_hash=hash_password("Senha@123"),
        )
        subject = Subject(user_id=user.uuid, name="Chemistry")
        session.add(subject)
        await session.commit()

        documents = DocumentService(
            session, DocumentRepository(session), SubjectRepository(session)
        )
        document = await documents.register(
            user_id=user.uuid,
            subject_id=subject.uuid,
            title="Doc",
            document_path="d.pdf",
        )
        contents = DocumentContentService(
            session,
            DocumentContentRepository(session),
            DocumentRepository(session),
        )
        content = await contents.add_content(
            user_id=user.uuid, document_id=document.uuid, markdown="# Doc"
        )
        indexing = IndexingService(
            session, ChunkRepository(session), DocumentContentRepository(session)
        )
        await indexing.index_content(
            content_id=content.uuid,
            chunks=[ChunkInput(chunk_index=0, content="only", embedding=_vec(1, 0))],
        )

        search = SearchService(ChunkRepository(session))
        # Scoping to an unrelated content id yields nothing.
        from uuid import uuid4

        empty = await search.search(
            query_embedding=_vec(1, 0), limit=5, content_ids=[uuid4()]
        )
        scoped = await search.search(
            query_embedding=_vec(1, 0), limit=5, content_ids=[content.uuid]
        )

    assert empty == []
    assert len(scoped) == 1
