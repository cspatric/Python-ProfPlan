"""Audit domain types."""

from dataclasses import dataclass
from enum import Enum
from uuid import UUID


class AuditAction(str, Enum):
    """The kind of mutation recorded in the audit trail."""

    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"


@dataclass(frozen=True, slots=True)
class AuditContext:
    """Who performed an action and under which request.

    Built once per HTTP request from the authenticated user and the
    request-logging middleware's request_id, so an audit row links back to the
    matching log line in Loki / span in Tempo.
    """

    actor_id: UUID | None
    actor_email: str | None
    request_id: str | None
