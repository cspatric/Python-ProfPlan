"""Async Redis client provider."""

from redis.asyncio import Redis, from_url

from app.core.config import get_settings

_settings = get_settings()

redis_client: Redis = from_url(
    _settings.redis_url,
    encoding="utf-8",
    decode_responses=True,
)


async def get_redis() -> Redis:
    """FastAPI dependency that returns the shared Redis client."""
    return redis_client
