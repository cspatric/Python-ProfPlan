"""Fixtures for integration tests (real Postgres + Redis).

The test database and Redis logical db are provided via DATABASE_URL / REDIS_URL
(see the `test` service in docker-compose.yml) and are isolated from dev data.
"""

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.core.security import hash_password
from app.infrastructure.database.base import Base
from app.infrastructure.database.session import SessionFactory, engine
from app.infrastructure.redis.client import redis_client
from app.modules.auth.infrastructure import models as _auth_models  # noqa: F401
from app.modules.users.infrastructure import models as _user_models  # noqa: F401
from app.modules.users.infrastructure.repository import UserRepository

_settings = get_settings()
_TABLES = "users, providers, user_providers, refresh_tokens, auth_logs"


async def _prepare_database() -> None:
    """Create the test database (if needed) and all tables."""
    prefix, db_name = _settings.database_url.rsplit("/", 1)
    admin = create_async_engine(f"{prefix}/postgres", isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        exists = await conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": db_name},
        )
        if not exists:
            await conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    await admin.dispose()

    setup_engine = create_async_engine(_settings.database_url)
    async with setup_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await setup_engine.dispose()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _database_schema():
    """Create the test database/schema once per session (integration only)."""
    await _prepare_database()
    yield


@pytest_asyncio.fixture(autouse=True)
async def _clean_state():
    """Wipe tables and the Redis db after every test for isolation."""
    yield
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {_TABLES} RESTART IDENTITY CASCADE"))
    await redis_client.flushdb()


@pytest_asyncio.fixture
async def client():
    """In-process HTTP client bound to the FastAPI app."""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as http_client:
        yield http_client


@pytest_asyncio.fixture
async def user_factory():
    """Factory that inserts a user into the test database."""

    async def _create(
        email: str = "user@test.com",
        name: str = "Test User",
        password: str = "Senha@123",
    ):
        async with SessionFactory() as session:
            user = await UserRepository(session).create(
                name=name, email=email, password_hash=hash_password(password)
            )
            await session.commit()
            return user

    return _create
