"""Where an activity came from, end to end.

This is the feature that answers the question the product could not answer
before: the AI wrote three paragraphs about software architecture and nothing
in the application could say whether they came from the book the teacher
uploaded or from the model's own memory. Now the answer is a row.
"""

import uuid
from datetime import date

import pytest
from sqlalchemy import select

from app.infrastructure.database.session import SessionFactory
from app.modules.academic_items.infrastructure.models import (
    AcademicItem,
    AcademicItemSource,
)
from app.modules.academic_items.infrastructure.source_repository import (
    AcademicItemSourceRepository,
)
from app.modules.rag.domain.chunk import SearchResult

pytestmark = pytest.mark.integration


def _result(chunk_id, content_id, content, distance):
    return SearchResult(
        chunk_id=str(chunk_id),
        document_content_id=str(content_id),
        content=content,
        distance=distance,
    )


async def _an_item(user_factory) -> AcademicItem:
    """An item with the module and plan it needs, and nothing else."""
    from app.modules.plan_modules.infrastructure.models import Module
    from app.modules.subjects.infrastructure.models import Subject
    from app.modules.teaching_plans.infrastructure.models import Plan

    user = await user_factory(email=f"sources-{uuid.uuid4().hex[:8]}@test.com")
    async with SessionFactory() as session:
        subject = Subject(user_id=user.uuid, name="Biology")
        session.add(subject)
        await session.flush()
        plan = Plan(
            user_id=user.uuid,
            subject_id=subject.uuid,
            starts_at=date(2026, 9, 1),
            ends_at=date(2026, 9, 30),
            class_duration=50,
            class_per_week=2,
        )
        session.add(plan)
        await session.flush()
        module = Module(
            user_id=user.uuid,
            plan_id=plan.uuid,
            title="Module 1",
            start_at=date(2026, 9, 1),
            ends_at=date(2026, 9, 30),
        )
        session.add(module)
        await session.flush()
        item = AcademicItem(
            user_id=user.uuid, module_id=module.uuid, title="Photosynthesis"
        )
        session.add(item)
        await session.commit()
        return item


async def test_the_passages_are_stored_in_the_order_the_prompt_used(user_factory):
    item = await _an_item(user_factory)

    async with SessionFactory() as session:
        await AcademicItemSourceRepository(session).replace(
            item.uuid,
            [
                _result(
                    uuid.uuid4(), uuid.uuid4(), "The Calvin cycle\n\nRuBisCO.", 0.2
                ),
                _result(uuid.uuid4(), uuid.uuid4(), "Light reactions\n\nPSII.", 0.5),
            ],
        )
        await session.commit()

    async with SessionFactory() as session:
        rows = (
            await session.scalars(
                select(AcademicItemSource)
                .where(AcademicItemSource.academic_item_id == item.uuid)
                .order_by(AcademicItemSource.rank)
            )
        ).all()

    assert [r.rank for r in rows] == [1, 2]
    # The rank is the number the prompt printed, so "[1]" in the generated text
    # points at this row and not at a different one.
    assert rows[0].section == "The Calvin cycle"
    assert rows[0].distance == 0.2
    assert "RuBisCO" in rows[0].excerpt


async def test_regenerating_replaces_the_citations(user_factory):
    """An item rewritten from other passages must not keep the old ones: they
    would attribute the new text to material that had nothing to do with it."""
    item = await _an_item(user_factory)

    async with SessionFactory() as session:
        repo = AcademicItemSourceRepository(session)
        await repo.replace(item.uuid, [_result(uuid.uuid4(), uuid.uuid4(), "old", 0.3)])
        await session.commit()
    async with SessionFactory() as session:
        repo = AcademicItemSourceRepository(session)
        await repo.replace(item.uuid, [_result(uuid.uuid4(), uuid.uuid4(), "new", 0.1)])
        await session.commit()

    async with SessionFactory() as session:
        rows = (
            await session.scalars(
                select(AcademicItemSource).where(
                    AcademicItemSource.academic_item_id == item.uuid
                )
            )
        ).all()

    assert len(rows) == 1
    assert rows[0].excerpt == "new"


async def test_an_item_written_from_nothing_has_no_sources(user_factory):
    """Not an error. It is the honest answer, and the one the reader most
    needs: this paragraph is the model's, not the teacher's material."""
    item = await _an_item(user_factory)

    async with SessionFactory() as session:
        await AcademicItemSourceRepository(session).replace(item.uuid, [])
        await session.commit()

    async with SessionFactory() as session:
        rows = await AcademicItemSourceRepository(session).list_for_item(item.uuid)

    assert rows == []


async def test_the_citation_survives_the_chunk_being_deleted(user_factory):
    """Re-ingesting a document replaces every chunk. A citation that were only
    a foreign key would break exactly then, which is the moment somebody
    uploads a corrected file and wonders what the plan was based on."""
    from app.modules.documents.infrastructure.models import (
        Document,
        DocumentContent,
        DocumentFormat,
    )
    from app.modules.rag.infrastructure.models import Chunk
    from app.modules.subjects.infrastructure.models import Subject

    item = await _an_item(user_factory)

    async with SessionFactory() as session:
        subject_id = await session.scalar(
            select(Subject.uuid).where(Subject.user_id == item.user_id)
        )
        fmt = DocumentFormat(format="md")
        session.add(fmt)
        await session.flush()
        document = Document(
            subject_id=subject_id,
            document_format_id=fmt.uuid,
            title="Photosynthesis notes",
            document_path="s3://bucket/x.md",
        )
        session.add(document)
        await session.flush()
        content = DocumentContent(document_id=document.uuid, markdown="# x", version=1)
        session.add(content)
        await session.flush()
        chunk = Chunk(document_content_id=content.uuid, chunk_index=0, content="body")
        session.add(chunk)
        await session.flush()

        await AcademicItemSourceRepository(session).replace(
            item.uuid,
            [_result(chunk.uuid, content.uuid, "The Calvin cycle\n\nRuBisCO.", 0.2)],
        )
        await session.commit()
        chunk_id = chunk.uuid

    # What re-ingestion does.
    async with SessionFactory() as session:
        await session.execute(Chunk.__table__.delete().where(Chunk.uuid == chunk_id))
        await session.commit()

    async with SessionFactory() as session:
        rows = await AcademicItemSourceRepository(session).list_for_item(item.uuid)

    assert len(rows) == 1
    source, title = rows[0]
    # The chunk is gone and the citation is intact, which is the whole point.
    # The id is kept as it was: it is a soft reference with no foreign key, so
    # it now points at nothing, and uuids are never reused, so a dangling id
    # is dangling rather than pointing at somebody else's passage.
    assert source.chunk_id == chunk_id
    assert "RuBisCO" in source.excerpt
    assert title == "Photosynthesis notes"


async def test_sources_belong_to_their_owner(auth_client, client, user_factory):
    """The excerpts quote the teacher's own uploaded material, so the endpoint
    must not answer for somebody else's item."""
    item = await _an_item(user_factory)

    response = await auth_client.get(f"/api/v1/academic-items/{item.uuid}/sources")

    assert response.status_code == 404
