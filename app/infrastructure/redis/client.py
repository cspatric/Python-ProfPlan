"""Async Redis client provider.

``redis_client`` is the process-wide singleton for the API, where every
request shares one long-lived event loop, so pooled connections stay valid.

Celery tasks must NOT use it: each task runs inside its own ``asyncio.run()``,
and a pooled connection created in one task's loop resurfaces in the next
task's loop already dead ("RuntimeError: Event loop is closed" — same failure
class the DB layer avoids with ``WorkerSessionFactory``/NullPool). Tasks build
a private client with ``new_redis_client()`` and close it when the run ends.
"""

from redis.asyncio import Redis, from_url

from app.core.config import get_settings

_settings = get_settings()


def new_redis_client() -> Redis:
    """A fresh client whose connections belong to the caller's event loop."""
    return from_url(
        _settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
    )


redis_client: Redis = new_redis_client()


async def get_redis() -> Redis:
    """FastAPI dependency that returns the shared Redis client."""
    return redis_client
