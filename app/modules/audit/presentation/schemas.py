"""Pydantic schemas for the audit API."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AuditLogResponse(BaseModel):
    """A single audit-trail entry."""

    model_config = ConfigDict(from_attributes=True)

    uuid: UUID
    actor_id: UUID | None
    actor_email: str | None
    action: str
    entity: str
    entity_id: UUID
    changes: dict[str, Any] | None
    request_id: str | None
    created_at: datetime
