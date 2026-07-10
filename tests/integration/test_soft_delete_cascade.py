"""Integration tests for cascading soft deletes against a real Postgres.

Confirms two things a fake-repository unit test can't: the cascade bulk
UPDATE statements actually work against real tables, and deleted rows are
truly *kept* (not removed) with `deleted_at` set.
"""

import pytest
from sqlalchemy import select

from app.infrastructure.database.session import SessionFactory
from app.modules.academic_items.infrastructure.models import AcademicItem
from app.modules.plan_modules.infrastructure.models import Module
from app.modules.subjects.infrastructure.models import Subject
from app.modules.teaching_plans.infrastructure.models import Plan

pytestmark = pytest.mark.integration


async def test_deleting_subject_cascades_and_keeps_rows(auth_client, module_id):
    item = await auth_client.post(
        "/api/v1/academic-items",
        json={"module_id": module_id, "title": "Exam 1"},
    )
    item_id = item.json()["uuid"]

    module = await auth_client.get(f"/api/v1/modules/{module_id}")
    plan_id = module.json()["plan_id"]
    plan = await auth_client.get(f"/api/v1/plans/{plan_id}")
    subject_id = plan.json()["subject_id"]

    deleted = await auth_client.delete(f"/api/v1/subjects/{subject_id}")
    assert deleted.status_code == 204

    # Cascaded: every descendant disappears from reads too.
    assert (await auth_client.get(f"/api/v1/subjects/{subject_id}")).status_code == 404
    assert (await auth_client.get(f"/api/v1/plans/{plan_id}")).status_code == 404
    assert (await auth_client.get(f"/api/v1/modules/{module_id}")).status_code == 404
    item_get = await auth_client.get(f"/api/v1/academic-items/{item_id}")
    assert item_get.status_code == 404

    # Not actually gone: every row still exists with deleted_at set.
    async with SessionFactory() as session:
        subject = await session.scalar(
            select(Subject).where(Subject.uuid == subject_id)
        )
        plan = await session.scalar(select(Plan).where(Plan.uuid == plan_id))
        module = await session.scalar(select(Module).where(Module.uuid == module_id))
        academic_item = await session.scalar(
            select(AcademicItem).where(AcademicItem.uuid == item_id)
        )

    assert subject is not None and subject.deleted_at is not None
    assert plan is not None and plan.deleted_at is not None
    assert module is not None and module.deleted_at is not None
    assert academic_item is not None and academic_item.deleted_at is not None


async def test_deleting_icon_clears_subject_reference_and_frees_name(admin_client):
    # admin_client and auth_client share one underlying httpx client (see
    # conftest.py) — using both in one test makes the second login clobber
    # the first's cookies. An admin is also a normal user, so do it all here.
    icon = await admin_client.post(
        "/api/v1/icons", json={"name": "Star", "file_path": "icons/star.svg"}
    )
    icon_id = icon.json()["uuid"]

    subject = await admin_client.post(
        "/api/v1/subjects", json={"name": "Astronomy", "icon_id": icon_id}
    )
    subject_id = subject.json()["uuid"]
    assert subject.json()["icon_id"] == icon_id

    assert (await admin_client.delete(f"/api/v1/icons/{icon_id}")).status_code == 204
    assert (await admin_client.get(f"/api/v1/icons/{icon_id}")).status_code == 404

    fetched = await admin_client.get(f"/api/v1/subjects/{subject_id}")
    assert fetched.json()["icon_id"] is None

    # The name is free again — a new icon can reuse it.
    recreated = await admin_client.post(
        "/api/v1/icons", json={"name": "Star", "file_path": "icons/star-v2.svg"}
    )
    assert recreated.status_code == 201


async def test_deleting_color_clears_subject_reference_and_frees_name(admin_client):
    color = await admin_client.post(
        "/api/v1/colors", json={"name": "Sky", "hex_code": "#AEE2FF"}
    )
    color_id = color.json()["uuid"]

    subject = await admin_client.post(
        "/api/v1/subjects", json={"name": "Geography", "color_id": color_id}
    )
    subject_id = subject.json()["uuid"]

    assert (await admin_client.delete(f"/api/v1/colors/{color_id}")).status_code == 204

    fetched = await admin_client.get(f"/api/v1/subjects/{subject_id}")
    assert fetched.json()["color_id"] is None

    recreated = await admin_client.post(
        "/api/v1/colors", json={"name": "Sky", "hex_code": "#123456"}
    )
    assert recreated.status_code == 201
