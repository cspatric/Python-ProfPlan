"""Audit recording — stages an audit_logs row inside the caller's transaction.

Services call `recorder.record(...)` right before their own `commit()`, so the
business change and its audit entry are persisted atomically (all-or-nothing).
`entity_snapshot` and `jsonable` are module-level helpers so services can build
snapshots/diffs without depending on the recorder instance.
"""

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from sqlalchemy import inspect as sa_inspect

from app.modules.audit.domain.entities import AuditAction, AuditContext
from app.modules.audit.infrastructure.models import AuditLog
from app.modules.audit.infrastructure.repository import AuditRepository

# Never copy these column values into an audit payload.
_SNAPSHOT_EXCLUDE = frozenset({"password_hash"})


def jsonable(value: Any) -> Any:
    """Convert a value into something JSON/JSONB can store.

    Total by design: it never raises, so serializing an audit payload can never
    break the business transaction it accompanies. Anything unrecognised falls
    back to its string form.
    """
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, date):  # also covers datetime (a date subclass)
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if value is None or isinstance(value, (str | int | float | bool)):
        return value
    if isinstance(value, dict):
        return {key: jsonable(val) for key, val in value.items()}
    if isinstance(value, (list | tuple | set)):
        return [jsonable(val) for val in value]
    return str(value)


def entity_snapshot(obj: object) -> dict[str, Any]:
    """A JSON-safe snapshot of a model's column values."""
    mapper = sa_inspect(obj).mapper
    return {
        attr.key: jsonable(getattr(obj, attr.key))
        for attr in mapper.column_attrs
        if attr.key not in _SNAPSHOT_EXCLUDE
    }


class AuditRecorder:
    """Records business actions against the acting user's context."""

    def __init__(self, repository: AuditRepository, context: AuditContext) -> None:
        self._repo = repository
        self._context = context

    def record(
        self,
        *,
        action: AuditAction,
        entity: str,
        entity_id: UUID,
        changes: dict[str, Any] | None = None,
    ) -> None:
        """Stage an audit row (persisted when the caller commits)."""
        log = AuditLog(
            actor_id=self._context.actor_id,
            actor_email=self._context.actor_email,
            action=action,
            entity=entity,
            entity_id=entity_id,
            changes=jsonable(changes) if changes is not None else None,
            request_id=self._context.request_id,
        )
        self._repo.add(log)
