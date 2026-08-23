"""Staging a notification.

The notifier's whole job is to add a row to the caller's transaction without
ever being the reason that transaction fails. The caller is a worker that has
just finished real work — indexing a book, writing forty activities — and losing
an alert is a far smaller harm than rolling that back over a JSONB payload.
"""

from uuid import uuid4

from app.modules.notifications.application.notifier import Notifier
from app.modules.notifications.domain.entities import (
    ENTITY_PLAN,
    NotificationKind,
)


class FakeRepo:
    def __init__(self, explode: bool = False) -> None:
        self.rows: list = []
        self._explode = explode

    def add(self, notification) -> None:
        if self._explode:
            raise RuntimeError("no")
        self.rows.append(notification)


def test_a_notification_carries_its_kind_and_target() -> None:
    repo = FakeRepo()
    plan_id = uuid4()
    user_id = uuid4()

    Notifier(repo).notify(
        user_id=user_id,
        kind=NotificationKind.PLAN_READY,
        entity=ENTITY_PLAN,
        entity_id=plan_id,
        params={"subject_name": "Biology"},
    )

    [row] = repo.rows
    assert row.user_id == user_id
    assert row.kind is NotificationKind.PLAN_READY
    assert row.entity == ENTITY_PLAN
    assert row.entity_id == plan_id
    assert row.params == {"subject_name": "Biology"}
    # Unread until somebody reads it.
    assert row.read_at is None


def test_no_message_is_stored() -> None:
    """The row holds a code and its values, never a sentence.

    The interface is offered in three languages and the text is built by
    whoever displays it. A message written here would be frozen in whatever
    language the worker was configured with, which is a language nobody chose.
    """
    repo = FakeRepo()

    Notifier(repo).notify(user_id=uuid4(), kind=NotificationKind.DOCUMENT_INDEXED)

    [row] = repo.rows
    assert not hasattr(row, "message")
    assert row.params is None


def test_the_payload_is_reduced_to_what_jsonb_can_hold() -> None:
    repo = FakeRepo()
    subject_id = uuid4()

    Notifier(repo).notify(
        user_id=uuid4(),
        kind=NotificationKind.PLAN_PARTIAL,
        params={"subject_name": "Biology", "failed": 2, "subject_id": subject_id},
    )

    [row] = repo.rows
    assert row.params == {
        "subject_name": "Biology",
        "failed": 2,
        "subject_id": str(subject_id),
    }


def test_a_failure_here_never_reaches_the_caller() -> None:
    """The caller is a worker mid-commit. This must not be what breaks it."""
    Notifier(FakeRepo(explode=True)).notify(
        user_id=uuid4(), kind=NotificationKind.PLAN_FAILED
    )
    # No exception is the assertion.
