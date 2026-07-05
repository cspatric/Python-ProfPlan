"""Integration tests for the UserRepository against a real database."""

from datetime import UTC, datetime

import pytest

from app.core.security import hash_password
from app.infrastructure.database.session import SessionFactory
from app.modules.users.domain.entities import UserRole
from app.modules.users.infrastructure.repository import UserRepository

pytestmark = pytest.mark.integration


async def test_create_get_and_case_insensitive_email() -> None:
    async with SessionFactory() as session:
        repo = UserRepository(session)
        created = await repo.create(
            name="Ada",
            email="Ada@Test.com",
            password_hash=hash_password("Senha@123"),
        )
        await session.commit()

        assert created.email == "ada@test.com"  # stored lowercased
        by_email = await repo.get_by_email("ADA@test.com")
        by_id = await repo.get_by_id(created.uuid)

    assert by_email is not None and by_email.uuid == created.uuid
    assert by_id is not None and by_id.role == UserRole.USER


async def test_unknown_email_returns_none() -> None:
    async with SessionFactory() as session:
        assert await UserRepository(session).get_by_email("no@one.com") is None


async def test_soft_deleted_user_is_hidden() -> None:
    async with SessionFactory() as session:
        repo = UserRepository(session)
        user = await repo.create(
            name="Gone",
            email="gone@test.com",
            password_hash=hash_password("Senha@123"),
        )
        user.deleted_at = datetime.now(UTC)
        await session.commit()

        assert await repo.get_by_email("gone@test.com") is None
        assert await repo.get_by_id(user.uuid) is None


async def test_mark_logged_in_sets_timestamp() -> None:
    async with SessionFactory() as session:
        repo = UserRepository(session)
        user = await repo.create(
            name="Login",
            email="login@test.com",
            password_hash=hash_password("Senha@123"),
        )
        await session.commit()
        assert user.last_login_at is None

        await repo.mark_logged_in(user)
        await session.commit()

    assert user.last_login_at is not None


async def test_create_admin_role() -> None:
    async with SessionFactory() as session:
        repo = UserRepository(session)
        admin = await repo.create(
            name="Root",
            email="root@test.com",
            password_hash=hash_password("Senha@123"),
            role=UserRole.ADMIN,
        )
        await session.commit()

    assert admin.role == UserRole.ADMIN
