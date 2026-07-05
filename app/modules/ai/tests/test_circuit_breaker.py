"""Unit tests for the circuit breaker."""

from app.modules.ai.infrastructure.gateway.circuit_breaker import CircuitBreaker


def test_opens_after_threshold_failures() -> None:
    breaker = CircuitBreaker(failure_threshold=2, reset_seconds=60)
    assert breaker.allow()

    breaker.record_failure()
    assert breaker.allow()  # still closed (1 < 2)
    breaker.record_failure()
    assert not breaker.allow()  # open


def test_success_resets_the_breaker() -> None:
    breaker = CircuitBreaker(failure_threshold=1, reset_seconds=60)
    breaker.record_failure()
    assert not breaker.allow()

    breaker.record_success()
    assert breaker.allow()


def test_half_open_after_cooldown() -> None:
    # reset_seconds=0 → the cooldown has always elapsed, so a trial is allowed.
    breaker = CircuitBreaker(failure_threshold=1, reset_seconds=0)
    breaker.record_failure()
    assert breaker.allow()
