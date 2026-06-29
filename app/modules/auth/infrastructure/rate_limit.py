"""Redis-backed fixed-window rate limiting for login attempts."""

from redis.asyncio import Redis

from app.core.config import get_settings

_settings = get_settings()


class LoginRateLimiter:
    """Limits login attempts per client within a sliding fixed window."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis
        self._max_attempts = _settings.login_rate_limit_max_attempts
        self._window = _settings.login_rate_limit_window_seconds

    @staticmethod
    def _key(identifier: str) -> str:
        return f"login:ratelimit:{identifier}"

    async def is_blocked(self, identifier: str) -> bool:
        """Return True when the identifier has exceeded the allowed attempts."""
        value = await self._redis.get(self._key(identifier))
        return value is not None and int(value) >= self._max_attempts

    async def register_failure(self, identifier: str) -> None:
        """Count a failed attempt, setting the window TTL on the first one."""
        key = self._key(identifier)
        current = await self._redis.incr(key)
        if current == 1:
            await self._redis.expire(key, self._window)

    async def reset(self, identifier: str) -> None:
        """Clear the counter after a successful login."""
        await self._redis.delete(self._key(identifier))
