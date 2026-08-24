"""Bulk Redis commands are bounded by configuration, not by user input.

Redis runs one command at a time, so the size of a command is everybody's
latency. A document's chunk count is a user input; the batch size is not.
"""

import json
from typing import Any

from app.infrastructure.redis.cache import RedisCache


class RecordingRedis:
    """Records the shape of every command instead of talking to Redis."""

    def __init__(self) -> None:
        self.mget_sizes: list[int] = []
        self.pipelines: list[int] = []
        self.store: dict[str, str] = {}

    async def mget(self, keys: list[str]) -> list[str | None]:
        self.mget_sizes.append(len(keys))
        return [self.store.get(k) for k in keys]

    def pipeline(self, transaction: bool = True) -> "RecordingPipeline":
        return RecordingPipeline(self)


class RecordingPipeline:
    def __init__(self, redis: RecordingRedis) -> None:
        self._redis = redis
        self._queued: list[tuple[str, str]] = []

    def set(self, key: str, value: str, ex: int | None = None) -> None:
        self._queued.append((key, value))

    async def execute(self) -> None:
        self._redis.pipelines.append(len(self._queued))
        self._redis.store.update(self._queued)


def _cache(redis: Any, batch_size: int) -> RedisCache:
    return RedisCache(redis, prefix="t:", ttl=60, batch_size=batch_size)


async def test_a_read_of_many_keys_is_split_into_bounded_batches() -> None:
    redis = RecordingRedis()
    await _cache(redis, 10).mget_json([f"k{i}" for i in range(25)])
    assert redis.mget_sizes == [10, 10, 5]


async def test_a_read_preserves_order_across_batches() -> None:
    redis = RecordingRedis()
    for i in range(5):
        redis.store[f"t:k{i}"] = json.dumps(i)
    values = await _cache(redis, 2).mget_json([f"k{i}" for i in range(5)])
    assert values == [0, 1, 2, 3, 4]


async def test_a_missing_key_is_none_not_an_error() -> None:
    redis = RecordingRedis()
    redis.store["t:present"] = json.dumps({"v": 1})
    assert await _cache(redis, 8).mget_json(["absent", "present"]) == [None, {"v": 1}]


async def test_a_write_of_many_keys_is_one_round_trip_per_batch() -> None:
    """The point of the pipeline: not one network wait per chunk."""
    redis = RecordingRedis()
    items = [(f"k{i}", [float(i)]) for i in range(25)]
    await _cache(redis, 10).set_many_json(items)
    assert redis.pipelines == [10, 10, 5]
    assert json.loads(redis.store["t:k24"]) == [24.0]


async def test_empty_input_issues_no_command_at_all() -> None:
    redis = RecordingRedis()
    cache = _cache(redis, 10)
    assert await cache.mget_json([]) == []
    await cache.set_many_json([])
    assert redis.mget_sizes == []
    assert redis.pipelines == []


async def test_a_batch_size_of_zero_is_clamped_rather_than_dividing_by_zero() -> None:
    redis = RecordingRedis()
    await _cache(redis, 0).mget_json(["a", "b"])
    assert redis.mget_sizes == [1, 1]
