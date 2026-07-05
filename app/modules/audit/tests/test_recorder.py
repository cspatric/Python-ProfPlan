"""Unit tests for the audit recorder and its JSON helpers."""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

from app.modules.audit.application.recorder import (
    AuditRecorder,
    entity_snapshot,
    jsonable,
)
from app.modules.audit.domain.entities import AuditAction, AuditContext
from app.modules.subjects.infrastructure.models import Subject


class FakeRepo:
    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, log: object) -> None:
        self.added.append(log)


def _context() -> AuditContext:
    return AuditContext(actor_id=uuid4(), actor_email="a@b.com", request_id="req-1")


def test_jsonable_converts_uuid_datetime_and_enum() -> None:
    uid = uuid4()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    assert jsonable(uid) == str(uid)
    assert jsonable(now) == now.isoformat()
    assert jsonable(AuditAction.CREATE) == "CREATE"
    assert jsonable({"id": uid, "items": [now]}) == {
        "id": str(uid),
        "items": [now.isoformat()],
    }


def test_jsonable_handles_date_and_decimal() -> None:
    # date (not datetime) and Decimal both appear on plan/module models.
    assert jsonable(date(2026, 8, 1)) == "2026-08-01"
    assert jsonable(Decimal("10.5")) == "10.5"


def test_entity_snapshot_is_json_safe() -> None:
    subject = Subject(user_id=uuid4(), name="Math", knowledge_area="STEM")
    subject.uuid = uuid4()

    snapshot = entity_snapshot(subject)

    assert snapshot["name"] == "Math"
    assert snapshot["uuid"] == str(subject.uuid)
    assert isinstance(snapshot["user_id"], str)


def test_record_builds_log_from_context() -> None:
    repo = FakeRepo()
    context = _context()
    recorder = AuditRecorder(repo, context)
    entity_id = uuid4()

    recorder.record(
        action=AuditAction.UPDATE,
        entity="subject",
        entity_id=entity_id,
        changes={"name": {"old": "A", "new": "B"}},
    )

    (log,) = repo.added
    assert log.actor_id == context.actor_id
    assert log.actor_email == "a@b.com"
    assert log.action == AuditAction.UPDATE
    assert log.entity == "subject"
    assert log.entity_id == entity_id
    assert log.changes == {"name": {"old": "A", "new": "B"}}
    assert log.request_id == "req-1"
