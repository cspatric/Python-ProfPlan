"""Cascading soft-delete helper.

Every entity in this codebase is soft-deleted (a `deleted_at` timestamp is
set, never a real `DELETE`), so the DB's `ON DELETE CASCADE` never fires.
This helper reproduces that cascade explicitly: it soft-deletes every
non-deleted row matching a filter and returns their ids, so a caller can
chain the next level down (e.g. subject -> its plans -> their modules).
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession


async def cascade_soft_delete(
    session: AsyncSession, model: type[Any], filter_clause: Any, deleted_at: datetime
) -> Sequence[UUID]:
    """Soft-delete every non-deleted row of `model` matching `filter_clause`.

    Returns the ids of the rows just soft-deleted, for chaining into the next
    cascade level.
    """
    result = await session.execute(
        update(model)
        .where(filter_clause, model.deleted_at.is_(None))
        .values(deleted_at=deleted_at)
        .returning(model.uuid)
    )
    return result.scalars().all()
