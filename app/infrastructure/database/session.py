"""Async database engine and session management."""

from collections.abc import AsyncGenerator
from typing import Any
from uuid import uuid4

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import get_settings

_settings = get_settings()


def _runtime_url() -> str:
    """The connection URL, with the pooler-safe options when one is in front.

    ``prepared_statement_cache_size`` is a dialect option, so it travels in the
    URL query string rather than as a ``create_engine`` keyword.
    """
    url = make_url(_settings.database_url)
    if _settings.db_pgbouncer:
        url = url.update_query_dict({"prepared_statement_cache_size": "0"})
    return url.render_as_string(hide_password=False)


def _pgbouncer_kwargs() -> dict[str, Any]:
    """Connect arguments required when connecting through PgBouncer.

    In transaction pooling mode the server connection goes back to the pool at
    COMMIT, so the next statement on the same client connection may land on a
    different Postgres backend. Two consequences, and both surface as
    intermittent failures under load rather than a clean error at boot:

    * a prepared statement created in one transaction may not exist in the
      next, so the statement cache has to be off (see ``_runtime_url``);
    * asyncpg names prepared statements in numeric order, so two clients
      sharing a backend can collide on a name. Unique names fix that.

    The cost is real: no server-side plan reuse. That is the price of
    multiplexing, and it is worth paying only when a pooler is actually there,
    which is why this is opt-in rather than always on.
    """
    if not _settings.db_pgbouncer:
        return {}
    return {
        "connect_args": {
            "statement_cache_size": 0,
            "prepared_statement_name_func": lambda: f"__asyncpg_{uuid4()}__",
        },
    }


engine: AsyncEngine = create_async_engine(
    _runtime_url(),
    pool_pre_ping=True,
    pool_size=_settings.db_pool_size,
    max_overflow=_settings.db_max_overflow,
    pool_timeout=_settings.db_pool_timeout,
    future=True,
    **_pgbouncer_kwargs(),
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
# Connecting through PgBouncer is what makes that cheap: the per-task connect is
# to the pooler, not a fresh Postgres backend.
worker_engine: AsyncEngine = create_async_engine(
    _runtime_url(),
    poolclass=NullPool,
    future=True,
    **_pgbouncer_kwargs(),
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
