"""Unit tests for the Redis-backed circuit breaker."""

from app.modules.ai.infrastructure.gateway.circuit_breaker import CircuitBreaker


class FakeRedis:
    """A tiny in-memory stand-in for the handful of commands the breaker uses."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def exists(self, key: str) -> int:
        return int(key in self.values)

    async def incr(self, key: str) -> int:
        self.values[key] = str(int(self.values.get(key, "0")) + 1)
        return int(self.values[key])

    async def expire(self, key: str, seconds: int) -> None:
        pass  # TTL expiry isn't simulated; tests don't depend on real time.

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.values[key] = value

    async def delete(self, *keys: str) -> None:
        for key in keys:
            self.values.pop(key, None)


def make_breaker(*, threshold: int, reset_seconds: float = 60) -> CircuitBreaker:
    return CircuitBreaker(
        FakeRedis(),
        name="test",
        failure_threshold=threshold,
        reset_seconds=reset_seconds,
    )


async def test_opens_after_threshold_failures() -> None:
    breaker = make_breaker(threshold=2)
    assert await breaker.allow()

    await breaker.record_failure()
    assert await breaker.allow()  # still closed (1 < 2)
    await breaker.record_failure()
    assert not await breaker.allow()  # open


async def test_success_resets_the_breaker() -> None:
    breaker = make_breaker(threshold=1)
    await breaker.record_failure()
    assert not await breaker.allow()

    await breaker.record_success()
    assert await breaker.allow()
