"""Sending a notification — stages a row inside the caller's transaction.

Mirrors the audit recorder, and for the same reason: a worker that finished a
plan and a notification saying so must be persisted together. Emitting after the
commit would mean a crash in between produces a finished plan nobody is told
about; emitting in its own transaction would mean the opposite, an alert about
work that was rolled back.

Best effort in one direction only. Failing to *build* a notification must never
fail the work it describes, so the caller is expected to be tolerant — but a
notification that was staged is as durable as the change beside it.
"""

import logging
from typing import Any
from uuid import UUID

from app.modules.notifications.domain.entities import NotificationKind
from app.modules.notifications.infrastructure.models import Notification
from app.modules.notifications.infrastructure.repository import (
    NotificationRepository,
)

logger = logging.getLogger("app.notifications")


class Notifier:
    """Stages notifications for a recipient."""

    def __init__(self, repository: NotificationRepository) -> None:
        self._repo = repository

    def notify(
        self,
        *,
        user_id: UUID,
        kind: NotificationKind,
        entity: str | None = None,
        entity_id: UUID | None = None,
        params: dict[str, Any] | None = None,
    ) -> None:
        """Stage a notification (persisted when the caller commits).

        Swallows its own failures on purpose: the caller is a worker that has
        just finished real work, and losing an alert is a smaller harm than
        rolling that work back over a JSONB payload.
        """
        try:
            self._repo.add(
                Notification(
                    user_id=user_id,
                    kind=kind,
                    entity=entity,
                    entity_id=entity_id,
                    params=_jsonable(params) if params else None,
                )
            )
        except Exception as exc:  # noqa: BLE001 - never break the caller
            logger.warning("could not stage notification %s: %s", kind, exc)


def _jsonable(params: dict[str, Any]) -> dict[str, Any]:
    """Keep the payload to what JSONB can hold, without raising.

    Deliberately small: a notification's parameters are a title and a count,
    not an object graph. Anything else becomes its string form rather than an
    exception in a worker.
    """
    out: dict[str, Any] = {}
    for key, value in params.items():
        if value is None or isinstance(value, (str | int | float | bool)):
            out[key] = value
        elif isinstance(value, UUID):
            out[key] = str(value)
        else:
            out[key] = str(value)
    return out
