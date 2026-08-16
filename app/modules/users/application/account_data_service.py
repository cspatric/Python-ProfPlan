"""Taking your data with you, and leaving.

Two rights that only look like features. Somebody who cannot get their material
out is somebody the product has taken hostage, and somebody who cannot leave is
somebody whose consent stopped meaning anything the day they gave it.

The teacher's uploaded material is theirs, and passages of it are sent to
third-party models. That is what makes both of these a legal obligation here
rather than a courtesy.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.academic_items.infrastructure.models import (
    AcademicItem,
    AcademicItemSource,
)
from app.modules.audit.infrastructure.models import AuditLog
from app.modules.auth.infrastructure.models import AuthLog
from app.modules.documents.infrastructure.models import Document, DocumentContent
from app.modules.generation.infrastructure.models import PlanGeneration
from app.modules.plan_modules.infrastructure.models import Module
from app.modules.subjects.infrastructure.models import Subject
from app.modules.teaching_plans.infrastructure.models import Plan
from app.modules.users.infrastructure.models import User

logger = logging.getLogger("app.users")

#: What a deleted account leaves behind in the security logs. The events stay,
#: because "somebody signed in from this address 400 times and then the account
#: was deleted" is exactly the record an intrusion is found in, and they are
#: kept without the person: the id goes to NULL by the foreign key and the
#: address is overwritten here.
ERASED_EMAIL = "erased@deleted.invalid"


class AccountDataService:
    """Export everything an account owns, or erase it."""

    def __init__(self, session: AsyncSession, storage) -> None:
        self._session = session
        self._storage = storage

    async def export(self, user: User) -> dict[str, Any]:
        """Everything this account owns, as one JSON document.

        Structured and self-describing rather than a database dump: the point
        of portability is that another system, or a person with a text editor,
        can read it.

        The uploaded files themselves are not inlined. They are the originals
        the teacher already has, a single plan can carry a hundred megabytes of
        PDF, and an export nobody can open is not an export; what is included
        is every document's metadata and the parsed text the AI actually read,
        which is the part this product created and the part nobody else has.
        """
        subjects = (
            await self._session.scalars(
                select(Subject).where(Subject.user_id == user.uuid)
            )
        ).all()
        subject_ids = [subject.uuid for subject in subjects]

        plans = (
            await self._session.scalars(select(Plan).where(Plan.user_id == user.uuid))
        ).all()
        modules = (
            await self._session.scalars(
                select(Module).where(Module.user_id == user.uuid)
            )
        ).all()
        items = (
            await self._session.scalars(
                select(AcademicItem).where(AcademicItem.user_id == user.uuid)
            )
        ).all()
        runs = (
            await self._session.scalars(
                select(PlanGeneration).where(PlanGeneration.user_id == user.uuid)
            )
        ).all()
        documents = (
            (
                await self._session.scalars(
                    select(Document).where(Document.subject_id.in_(subject_ids))
                )
            ).all()
            if subject_ids
            else []
        )
        contents = (
            (
                await self._session.scalars(
                    select(DocumentContent).where(
                        DocumentContent.document_id.in_([d.uuid for d in documents])
                    )
                )
            ).all()
            if documents
            else []
        )
        sources = (
            (
                await self._session.scalars(
                    select(AcademicItemSource).where(
                        AcademicItemSource.academic_item_id.in_(
                            [item.uuid for item in items]
                        )
                    )
                )
            ).all()
            if items
            else []
        )

        return {
            "exported_at": datetime.now(UTC).isoformat(),
            "format": "profplan/account-export/1",
            "account": {
                "uuid": str(user.uuid),
                "name": user.name,
                "email": user.email,
                "role": user.role.value if user.role else None,
                "status": user.status.value if user.status else None,
                "created_at": _when(user.created_at),
                "email_verified_at": _when(user.email_verified_at),
                "last_login_at": _when(user.last_login_at),
                "has_password": user.password_hash is not None,
            },
            "subjects": [
                {
                    "uuid": str(s.uuid),
                    "name": s.name,
                    "created_at": _when(s.created_at),
                }
                for s in subjects
            ],
            "documents": [
                {
                    "uuid": str(d.uuid),
                    "subject_id": str(d.subject_id),
                    "title": d.title,
                    "original_filename": d.original_filename,
                    "ingestion_status": getattr(d.ingestion_status, "value", None),
                    "created_at": _when(d.created_at),
                    # The parsed text the AI read, which is what this product
                    # made out of the file. The file itself stays where it is.
                    "parsed_markdown": next(
                        (c.markdown for c in contents if c.document_id == d.uuid), None
                    ),
                }
                for d in documents
            ],
            "plans": [
                {
                    "uuid": str(p.uuid),
                    "subject_id": str(p.subject_id),
                    "starts_at": _when(p.starts_at),
                    "ends_at": _when(p.ends_at),
                    "class_duration": p.class_duration,
                    "class_per_week": p.class_per_week,
                }
                for p in plans
            ],
            "modules": [
                {
                    "uuid": str(m.uuid),
                    "plan_id": str(m.plan_id),
                    "title": m.title,
                    "start_at": _when(m.start_at),
                    "ends_at": _when(m.ends_at),
                }
                for m in modules
            ],
            "activities": [
                {
                    "uuid": str(i.uuid),
                    "module_id": str(i.module_id),
                    "title": i.title,
                    "description": i.description,
                    "content": i.content,
                    "metadata": i.item_metadata,
                    "generation_status": getattr(i.generation_status, "value", None),
                    # Where it came from, which is the part that makes the
                    # material checkable by whoever receives this file.
                    "written_from": [
                        {
                            "rank": src.rank,
                            "document_id": str(src.document_id)
                            if src.document_id
                            else None,
                            "section": src.section,
                            "excerpt": src.excerpt,
                        }
                        for src in sources
                        if src.academic_item_id == i.uuid
                    ],
                }
                for i in items
            ],
            "ai_usage": [
                {
                    "generation_id": str(r.uuid),
                    "plan_id": str(r.plan_id),
                    "created_at": _when(r.created_at),
                    "calls": r.llm_calls,
                    "input_tokens": r.llm_input_tokens,
                    "output_tokens": r.llm_output_tokens,
                    "cost_usd": float(r.llm_cost_usd),
                }
                for r in runs
            ],
        }

    async def erase(self, user: User) -> dict[str, int]:
        """Delete the account and everything it owns. Not a soft delete.

        Soft deletion is right for a teacher who removes a subject by accident.
        It is the wrong answer to "delete my account", where the whole point is
        that the data stops existing: a `deleted_at` on a row that still holds
        somebody's teaching material and email address has erased nothing.

        The rows go by cascade, the uploaded files are removed from object
        storage first, and the security logs keep their events with the person
        taken out of them. That last part is deliberate: an audit trail that
        can be emptied by the account it incriminates is not an audit trail,
        and one that keeps names forever is not erasure. Keeping the events
        without the identity is the honest middle.
        """
        subject_ids = list(
            (
                await self._session.scalars(
                    select(Subject.uuid).where(Subject.user_id == user.uuid)
                )
            ).all()
        )
        paths = (
            list(
                (
                    await self._session.scalars(
                        select(Document.document_path).where(
                            Document.subject_id.in_(subject_ids)
                        )
                    )
                ).all()
            )
            if subject_ids
            else []
        )

        # Objects first: a row deleted with its file left behind is a file
        # nobody can find and nobody will ever delete.
        removed = 0
        for path in paths:
            try:
                self._storage.remove_object(path)
                removed += 1
            except Exception:  # noqa: BLE001 — a missing object is still gone
                logger.warning("could not remove %s while erasing an account", path)

        await self._session.execute(
            update(AuthLog)
            .where(AuthLog.user_id == user.uuid)
            .values(email=ERASED_EMAIL)
        )
        await self._session.execute(
            update(AuditLog)
            .where(AuditLog.actor_id == user.uuid)
            .values(actor_email=ERASED_EMAIL)
        )
        await self._session.execute(delete(User).where(User.uuid == user.uuid))
        await self._session.commit()

        logger.info(
            "account erased",
            extra={"user_id": str(user.uuid), "objects_removed": removed},
        )
        return {"documents_removed": removed, "subjects": len(subject_ids)}


def _when(value: Any) -> str | None:
    return value.isoformat() if value is not None else None
