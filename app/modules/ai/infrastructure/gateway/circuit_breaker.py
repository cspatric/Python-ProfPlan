"""A minimal in-process circuit breaker for LLM providers."""

import time


class CircuitBreaker:
    """Skips a provider after repeated failures, retrying after a cooldown.

    States: closed (calls allowed) → open (calls skipped for ``reset_seconds``)
    → half-open (one trial allowed; success closes, failure re-opens).
    """

    def __init__(self, *, failure_threshold: int, reset_seconds: float) -> None:
        self._threshold = failure_threshold
        self._reset_seconds = reset_seconds
        self._failures = 0
        self._opened_at: float | None = None

    def allow(self) -> bool:
        """Return True if a call to the provider should be attempted."""
        if self._opened_at is None:
            return True
        # Half-open: after the cooldown, allow a single trial.
        return (time.monotonic() - self._opened_at) >= self._reset_seconds

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self._threshold:
            self._opened_at = time.monotonic()
