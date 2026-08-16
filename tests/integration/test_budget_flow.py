"""The monthly AI budget, against real rows.

Rate limits cap requests per minute, which is a different thing from money: a
request a minute on an expensive model is still a bill at the end of it. This
is the only limit on spend, so what it does at the boundary is worth pinning
down.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.infrastructure.database.session import SessionFactory
from app.modules.generation.domain.entities import GenerationRunStatus
from app.modules.generation.infrastructure.models import PlanGeneration
from app.modules.teaching_plans.infrastructure.models import Plan

pytestmark = pytest.mark.integration


async def _spend(user_id, plan_id, usd: str, *, when: datetime | None = None) -> None:
    """A run that cost this much, optionally dated into the past."""
    async with SessionFactory() as session:
        run = PlanGeneration(
            plan_id=plan_id,
            user_id=user_id,
            status=GenerationRunStatus.COMPLETED,
            llm_calls=1,
            llm_input_tokens=1000,
            llm_output_tokens=500,
            llm_cost_usd=Decimal(usd),
        )
        session.add(run)
        await session.flush()
        if when is not None:
            run.created_at = when
        await session.commit()


async def _a_plan(user_id) -> "Plan.uuid":
    """A subject and a plan for this account, straight into the database."""
    from datetime import date

    from app.modules.subjects.infrastructure.models import Subject

    async with SessionFactory() as session:
        subject = Subject(user_id=user_id, name="Subject")
        session.add(subject)
        await session.flush()
        plan = Plan(
            user_id=user_id,
            subject_id=subject.uuid,
            starts_at=date(2026, 9, 1),
            ends_at=date(2026, 9, 30),
            class_duration=50,
            class_per_week=2,
        )
        session.add(plan)
        await session.commit()
        return plan.uuid


async def test_a_new_plan_is_refused_once_the_budget_is_gone(auth_client, plan_id):
    """402, not 429: this is not "too fast", it is "no more money this month",
    and a client retrying a 429 in a minute would be doing the wrong thing."""
    async with SessionFactory() as session:
        plan = await session.scalar(select(Plan).where(Plan.uuid == plan_id))
    budget = get_settings().llm_monthly_budget_usd
    await _spend(plan.user_id, plan.uuid, str(budget))

    response = await auth_client.post(
        "/api/v1/plans",
        json={
            "subject_id": str(plan.subject_id),
            "starts_at": "2026-08-01",
            "ends_at": "2026-12-15",
            "class_duration": 50,
            "class_per_week": 2,
        },
    )

    assert response.status_code == 402
    detail = response.json()["detail"]
    # The message has to say what to do next, or it is a support ticket.
    assert "resets on the first" in detail

    # And nothing was written: no plan the teacher can see and no task queued.
    async with SessionFactory() as session:
        plans = (
            await session.scalars(select(Plan).where(Plan.user_id == plan.user_id))
        ).all()
    assert len(plans) == 1


async def test_spending_just_under_the_budget_still_works(auth_client, plan_id):
    async with SessionFactory() as session:
        plan = await session.scalar(select(Plan).where(Plan.uuid == plan_id))
    budget = Decimal(str(get_settings().llm_monthly_budget_usd))
    await _spend(plan.user_id, plan.uuid, str(budget - Decimal("0.01")))

    usage = await auth_client.get("/api/v1/usage/me")

    assert usage.status_code == 200
    assert usage.json()["remaining_usd"] == pytest.approx(0.01)


async def test_last_month_does_not_count_against_this_one(auth_client, plan_id):
    """The window is the calendar month. A run from the 31st must not still be
    holding somebody's budget on the 1st."""
    async with SessionFactory() as session:
        plan = await session.scalar(select(Plan).where(Plan.uuid == plan_id))
    budget = get_settings().llm_monthly_budget_usd
    first_of_this_month = datetime.now(UTC).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    await _spend(
        plan.user_id,
        plan.uuid,
        str(budget * 10),
        when=first_of_this_month - timedelta(seconds=1),
    )

    usage = await auth_client.get("/api/v1/usage/me")

    assert usage.json()["spent_usd"] == 0.0


async def test_one_account_cannot_spend_another_account_budget(
    auth_client, plan_id, user_factory
):
    """Spend is scoped to the account, which is the whole point of a per-user
    cap: one heavy user must not lock everybody else out."""
    stranger = await user_factory(email="stranger@test.com")
    async with SessionFactory() as session:
        plan = await session.scalar(select(Plan).where(Plan.uuid == plan_id))
    await _spend(stranger.uuid, plan.uuid, "100.00")

    usage = await auth_client.get("/api/v1/usage/me")

    assert usage.json()["spent_usd"] == 0.0


async def test_the_admin_listing_is_admin_only(auth_client):
    assert (await auth_client.get("/api/v1/usage")).status_code == 403


async def test_the_admin_listing_ranks_accounts_by_spend(admin_client, user_factory):
    # The rows are built directly rather than through the API: `auth_client`
    # and `admin_client` share one HTTP client, so asking for a plan through
    # the first one would sign the second one out and the admin listing would
    # come back 403.
    heavy = await user_factory(email="heavy@test.com")
    light = await user_factory(email="light@test.com")
    await _spend(heavy.uuid, await _a_plan(heavy.uuid), "3.00")
    await _spend(light.uuid, await _a_plan(light.uuid), "0.50")

    rows = (await admin_client.get("/api/v1/usage")).json()
    by_email = {row["email"]: row for row in rows}

    assert [row["email"] for row in rows][:2] == ["heavy@test.com", "light@test.com"]
    assert by_email["heavy@test.com"]["spent_usd"] == 3.0
    assert by_email["heavy@test.com"]["tokens"] == 1500


async def test_a_zero_budget_means_no_limit(auth_client, plan_id, monkeypatch):
    """Zero is off, not "nothing allowed". A deployment that has not thought
    about a limit must not be one where nobody can work."""
    monkeypatch.setattr(get_settings(), "llm_monthly_budget_usd", 0.0)
    async with SessionFactory() as session:
        plan = await session.scalar(select(Plan).where(Plan.uuid == plan_id))
    await _spend(plan.user_id, plan.uuid, "1000.00")

    usage = await auth_client.get("/api/v1/usage/me")

    assert usage.json()["remaining_usd"] is None
