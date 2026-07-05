"""Async database engine and session management."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import get_settings

_settings = get_settings()

engine: AsyncEngine = create_async_engine(
    _settings.database_url,
    pool_pre_ping=True,
    future=True,
)

SessionFactory = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    autoflush=False,
)

# Celery tasks each run their own short-lived event loop (asyncio.run), and may
# open more than one loop per task (e.g. run + mark-failed). A pooled connection
# bound to a previous loop cannot be reused ("attached to a different loop"), so
# the worker uses a NullPool engine that opens/closes a fresh connection per use.
worker_engine: AsyncEngine = create_async_engine(
    _settings.database_url,
    poolclass=NullPool,
    future=True,
)

WorkerSessionFactory = async_sessionmaker(
    bind=worker_engine,
    expire_on_commit=False,
    autoflush=False,
)


async def get_session() -> AsyncGenerator[AsyncSession]:
    """FastAPI dependency that yields a transactional database session."""
    async with SessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
