"""A Redis-backed circuit breaker for LLM providers.

State lives in Redis (not process memory) so every API/worker process — and
every replica in a horizontally-scaled deployment — shares the same view of
"is this provider down" instead of each maintaining its own, uncoordinated
guess and hammering a dead provider that a sibling process already gave up on.
"""

from redis.asyncio import Redis


class CircuitBreaker:
    """Skips a provider after repeated failures, retrying after a cooldown.

    States: closed (calls allowed) -> open (calls skipped for
    ``reset_seconds``) -> half-open (the open key's TTL expires, so the next
    ``allow()`` lets a trial through; success closes it, failure re-opens it).
    """

    def __init__(
        self,
        redis: Redis,
        *,
        name: str,
        failure_threshold: int,
        reset_seconds: float,
    ) -> None:
        self._redis = redis
        self._failures_key = f"cb:{name}:failures"
        self._open_key = f"cb:{name}:open"
        self._threshold = failure_threshold
        self._reset_seconds = reset_seconds

    async def allow(self) -> bool:
        """Return True if a call to the provider should be attempted."""
        return not await self._redis.exists(self._open_key)

    async def is_open(self) -> bool:
        """True while the breaker is open (calls skipped), without mutating."""
        return bool(await self._redis.exists(self._open_key))

    async def record_success(self) -> None:
        await self._redis.delete(self._failures_key, self._open_key)

    async def record_failure(self) -> None:
        failures = await self._redis.incr(self._failures_key)
        if failures == 1:
            # Bound the failure count to a rolling window so unrelated
            # failures far apart in time don't accumulate toward the threshold.
            await self._redis.expire(self._failures_key, int(self._reset_seconds))
        if failures >= self._threshold:
            await self._redis.set(self._open_key, "1", ex=int(self._reset_seconds))
