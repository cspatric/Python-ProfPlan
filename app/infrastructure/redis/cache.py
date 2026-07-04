"""Small JSON cache on top of the async Redis client."""

import json
from typing import Any

from redis.asyncio import Redis


class RedisCache:
    """Namespaced get/set of JSON values with an optional default TTL."""

    def __init__(
        self, redis: Redis, *, prefix: str = "", ttl: int | None = None
    ) -> None:
        self._redis = redis
        self._prefix = prefix
        self._ttl = ttl

    def _key(self, key: str) -> str:
        return f"{self._prefix}{key}"

    async def get_json(self, key: str) -> Any | None:
        raw = await self._redis.get(self._key(key))
        return json.loads(raw) if raw is not None else None

    async def set_json(self, key: str, value: Any, ttl: int | None = None) -> None:
        await self._redis.set(self._key(key), json.dumps(value), ex=ttl or self._ttl)

    async def mget_json(self, keys: list[str]) -> list[Any | None]:
        if not keys:
            return []
        raws = await self._redis.mget([self._key(k) for k in keys])
        return [json.loads(r) if r is not None else None for r in raws]
