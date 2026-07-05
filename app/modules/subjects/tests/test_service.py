"""Unit tests for SubjectService using in-memory fakes."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.modules.audit.domain.entities import AuditAction
from app.modules.subjects.application.service import SubjectService
from app.modules.subjects.domain.exceptions import SubjectNotFoundError
from app.modules.subjects.infrastructure.models import Subject


class FakeSession:
    async def commit(self) -> None:
        pass

    async def refresh(self, obj: object) -> None:
        pass

    async def flush(self) -> None:
        pass


class FakeAuditRecorder:
    def __init__(self) -> None:
        self.records: list[dict] = []

    def record(self, **kwargs: object) -> None:
        self.records.append(kwargs)


class FakeSubjectRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, Subject] = {}

    def add(self, subject: Subject) -> None:
        if subject.uuid is None:
            subject.uuid = uuid4()
        subject.created_at = subject.updated_at = datetime.now(UTC)
        self.items[subject.uuid] = subject

    async def get_by_id(self, subject_id: UUID, user_id: UUID) -> Subject | None:
        subject = self.items.get(subject_id)
        if subject is None or subject.user_id != user_id:
            return None
        return subject

    async def list_by_user(
        self, user_id: UUID, *, limit: int, offset: int
    ) -> list[Subject]:
        owned = [s for s in self.items.values() if s.user_id == user_id]
        return owned[offset : offset + limit]

    async def delete(self, subject: Subject) -> None:
        self.items.pop(subject.uuid, None)


def make_service() -> tuple[SubjectService, FakeSubjectRepository]:
    repo = FakeSubjectRepository()
    return SubjectService(FakeSession(), repo, FakeAuditRecorder()), repo


async def test_create_sets_owner_and_persists() -> None:
    service, repo = make_service()
    user_id = uuid4()

    subject = await service.create(
        user_id=user_id, data={"name": "Math", "knowledge_area": "STEM"}
    )

    assert subject.uuid in repo.items
    assert subject.user_id == user_id
    assert subject.name == "Math"
    assert service._audit.records[0]["action"] == AuditAction.CREATE
    assert service._audit.records[0]["entity_id"] == subject.uuid


async def test_get_of_other_users_subject_raises() -> None:
    service, _ = make_service()
    owner = uuid4()
    created = await service.create(user_id=owner, data={"name": "Math"})

    with pytest.raises(SubjectNotFoundError):
        await service.get(user_id=uuid4(), subject_id=created.uuid)


async def test_update_changes_fields() -> None:
    service, _ = make_service()
    user_id = uuid4()
    created = await service.create(user_id=user_id, data={"name": "Old"})

    updated = await service.update(
        user_id=user_id, subject_id=created.uuid, data={"name": "New"}
    )
    assert updated.name == "New"


async def test_update_missing_raises() -> None:
    service, _ = make_service()
    with pytest.raises(SubjectNotFoundError):
        await service.update(user_id=uuid4(), subject_id=uuid4(), data={"name": "x"})


async def test_delete_removes_subject() -> None:
    service, repo = make_service()
    user_id = uuid4()
    created = await service.create(user_id=user_id, data={"name": "Temp"})

    await service.delete(user_id=user_id, subject_id=created.uuid)
    assert created.uuid not in repo.items


async def test_list_returns_only_owner_subjects() -> None:
    service, _ = make_service()
    owner = uuid4()
    await service.create(user_id=owner, data={"name": "A"})
    await service.create(user_id=uuid4(), data={"name": "B"})

    owned = await service.list(user_id=owner, limit=50, offset=0)
    assert len(owned) == 1
    assert owned[0].name == "A"
