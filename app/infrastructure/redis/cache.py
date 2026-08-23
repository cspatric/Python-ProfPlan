"""Small JSON cache on top of the async Redis client.

Redis executes commands on one thread, so the cost of a command is the cost of
everybody's next command too. The bulk helpers here are therefore batched: the
number of keys in one request is bounded by configuration, never by how much
data a user happened to upload. A document is chunked before it is embedded, so
an unbounded MGET would make the worst-case Redis stall proportional to the
largest file anyone sends — which is an input, not an operational knob.
"""

import json
from collections.abc import Sequence
from typing import Any

from redis.asyncio import Redis


class RedisCache:
    """Namespaced get/set of JSON values with an optional default TTL."""

    def __init__(
        self,
        redis: Redis,
        *,
        prefix: str = "",
        ttl: int | None = None,
        batch_size: int = 64,
    ) -> None:
        self._redis = redis
        self._prefix = prefix
        self._ttl = ttl
        self._batch_size = max(1, batch_size)

    def _key(self, key: str) -> str:
        return f"{self._prefix}{key}"

    async def get_json(self, key: str) -> Any | None:
        raw = await self._redis.get(self._key(key))
        return json.loads(raw) if raw is not None else None

    async def set_json(self, key: str, value: Any, ttl: int | None = None) -> None:
        await self._redis.set(self._key(key), json.dumps(value), ex=ttl or self._ttl)

    def _batches(self, keys: Sequence[str]) -> list[Sequence[str]]:
        size = self._batch_size
        return [keys[i : i + size] for i in range(0, len(keys), size)]

    async def mget_json(self, keys: list[str]) -> list[Any | None]:
        """Read many keys, one bounded MGET per batch.

        Order is preserved, so callers can zip the result against their input.
        """
        if not keys:
            return []
        values: list[Any | None] = []
        for batch in self._batches(keys):
            raws = await self._redis.mget([self._key(k) for k in batch])
            values.extend(json.loads(r) if r is not None else None for r in raws)
        return values

    async def set_many_json(
        self, items: Sequence[tuple[str, Any]], ttl: int | None = None
    ) -> None:
        """Write many keys, one pipelined round trip per batch.

        Each value still needs its own SET because they have separate TTLs; the
        pipeline is what stops that from being one network round trip per key.
        """
        if not items:
            return
        expires = ttl or self._ttl
        for batch in self._batches(items):
            pipe = self._redis.pipeline(transaction=False)
            for key, value in batch:
                pipe.set(self._key(key), json.dumps(value), ex=expires)
            await pipe.execute()
