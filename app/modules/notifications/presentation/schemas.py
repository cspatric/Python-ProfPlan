"""Request/response schemas for notifications."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.modules.notifications.domain.entities import NotificationKind


class NotificationResponse(BaseModel):
    """One notification.

    There is no message field, and that is the design. ``kind`` is a stable
    code and ``params`` are its values; the client renders the sentence in the
    reader's language, exactly as it does for an API error's ``code``. A message
    written here would be frozen in the language the worker was configured with.
    """

    model_config = ConfigDict(from_attributes=True)

    uuid: UUID
    kind: NotificationKind
    params: dict[str, Any] | None
    #: What it is about, for a client that wants to link to it. Either may be
    #: null: not every event has a page, and the target may have been deleted.
    entity: str | None
    entity_id: UUID | None
    read_at: datetime | None
    created_at: datetime


class NotificationPageResponse(BaseModel):
    """A page of notifications and the unread count, in one answer."""

    items: list[NotificationResponse]
    unread: int


class MarkAllReadResponse(BaseModel):
    """How many notifications the call actually changed."""

    updated: int
