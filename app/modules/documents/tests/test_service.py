"""Unit tests for the document services using in-memory fakes."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.modules.documents.application.document_service import (
    DocumentContentService,
    DocumentService,
)
from app.modules.documents.domain.exceptions import (
    DocumentNotFoundError,
    InvalidSubjectError,
)
from app.modules.documents.infrastructure.models import (
    Document,
    DocumentContent,
)


class FakeSession:
    async def commit(self) -> None:
        pass

    async def refresh(self, obj: object) -> None:
        pass


class FakeSubjectRepository:
    def __init__(self, owned: set[tuple[UUID, UUID]]) -> None:
        self._owned = owned

    async def get_by_id(self, subject_id: UUID, user_id: UUID) -> object | None:
        return object() if (subject_id, user_id) in self._owned else None


class FakeDocumentRepository:
    def __init__(self, owned: set[tuple[UUID, UUID]]) -> None:
        self.items: dict[UUID, Document] = {}
        self._owned = owned

    def add(self, document: Document) -> None:
        if document.uuid is None:
            document.uuid = uuid4()
        document.created_at = document.updated_at = datetime.now(UTC)
        document.deleted_at = None
        self.items[document.uuid] = document

    async def get_by_id(self, document_id: UUID, user_id: UUID) -> Document | None:
        doc = self.items.get(document_id)
        if doc is None or doc.deleted_at is not None:
            return None
        if (doc.subject_id, user_id) not in self._owned:
            return None
        return doc

    async def list_by_subject(
        self, subject_id: UUID, user_id: UUID, *, limit: int, offset: int
    ) -> list[Document]:
        owned = [
            d
            for d in self.items.values()
            if d.subject_id == subject_id
            and d.deleted_at is None
            and (d.subject_id, user_id) in self._owned
        ]
        return owned[offset : offset + limit]


class FakeContentRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, DocumentContent] = {}

    def add(self, content: DocumentContent) -> None:
        if content.uuid is None:
            content.uuid = uuid4()
        self.items[content.uuid] = content

    async def get_latest(self, document_id: UUID) -> DocumentContent | None:
        versions = [c for c in self.items.values() if c.document_id == document_id]
        return max(versions, key=lambda c: c.version, default=None)

    async def list_by_document(self, document_id: UUID) -> list[DocumentContent]:
        return sorted(
            (c for c in self.items.values() if c.document_id == document_id),
            key=lambda c: c.version,
            reverse=True,
        )


def make_document_service(
    owned: set[tuple[UUID, UUID]],
) -> tuple[DocumentService, FakeDocumentRepository]:
    docs = FakeDocumentRepository(owned)
    service = DocumentService(FakeSession(), docs, FakeSubjectRepository(owned))
    return service, docs


async def test_register_requires_owned_subject() -> None:
    service, _ = make_document_service(set())
    with pytest.raises(InvalidSubjectError):
        await service.register(
            user_id=uuid4(),
            subject_id=uuid4(),
            title="Doc",
            document_path="path/doc.pdf",
        )


async def test_register_and_get() -> None:
    user_id, subject_id = uuid4(), uuid4()
    service, _ = make_document_service({(subject_id, user_id)})

    document = await service.register(
        user_id=user_id,
        subject_id=subject_id,
        title="Doc",
        document_path="path/doc.pdf",
    )
    fetched = await service.get(user_id=user_id, document_id=document.uuid)
    assert fetched.uuid == document.uuid
    assert fetched.title == "Doc"


async def test_get_missing_raises() -> None:
    service, _ = make_document_service(set())
    with pytest.raises(DocumentNotFoundError):
        await service.get(user_id=uuid4(), document_id=uuid4())


async def test_soft_delete_hides_document() -> None:
    user_id, subject_id = uuid4(), uuid4()
    service, docs = make_document_service({(subject_id, user_id)})
    document = await service.register(
        user_id=user_id,
        subject_id=subject_id,
        title="Doc",
        document_path="p",
    )

    await service.soft_delete(user_id=user_id, document_id=document.uuid)
    assert docs.items[document.uuid].deleted_at is not None
    with pytest.raises(DocumentNotFoundError):
        await service.get(user_id=user_id, document_id=document.uuid)


async def test_add_content_autoincrements_version() -> None:
    user_id, subject_id = uuid4(), uuid4()
    doc_service, docs = make_document_service({(subject_id, user_id)})
    document = await doc_service.register(
        user_id=user_id,
        subject_id=subject_id,
        title="Doc",
        document_path="p",
    )
    content_service = DocumentContentService(
        FakeSession(), FakeContentRepository(), docs
    )

    first = await content_service.add_content(
        user_id=user_id, document_id=document.uuid, markdown="# v1"
    )
    second = await content_service.add_content(
        user_id=user_id, document_id=document.uuid, markdown="# v2"
    )
    assert first.version == 1
    assert second.version == 2
