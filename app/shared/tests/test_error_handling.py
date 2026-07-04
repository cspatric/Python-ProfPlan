"""Unit tests for the shared error bases and the tenacity retry decorator."""

import httpx
import pytest

from app.shared.decorators.retry import external_call
from app.shared.exceptions.base import (
    NotFoundError,
    RateLimitError,
    UnauthorizedError,
    UnprocessableError,
)


def test_error_bases_map_to_expected_status_codes() -> None:
    assert NotFoundError().status_code == 404
    assert UnprocessableError().status_code == 422
    assert UnauthorizedError().status_code == 401
    assert RateLimitError().status_code == 429


def test_error_detail_can_be_overridden() -> None:
    assert NotFoundError("Subject not found").detail == "Subject not found"
    assert NotFoundError().detail == "Resource not found"


async def test_retry_recovers_after_transient_failures() -> None:
    calls = {"n": 0}

    @external_call(max_attempts=3, initial_wait=0.001, max_wait=0.01)
    async def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise httpx.TimeoutException("temporary")
        return "ok"

    assert await flaky() == "ok"
    assert calls["n"] == 3


async def test_retry_reraises_after_max_attempts() -> None:
    @external_call(max_attempts=2, initial_wait=0.001, max_wait=0.01)
    async def always_fail() -> None:
        raise httpx.TimeoutException("down")

    with pytest.raises(httpx.TimeoutException):
        await always_fail()


async def test_retry_does_not_retry_non_transient_errors() -> None:
    calls = {"n": 0}

    @external_call(max_attempts=3, initial_wait=0.001, max_wait=0.01)
    async def bad() -> None:
        calls["n"] += 1
        raise ValueError("permanent")

    with pytest.raises(ValueError):
        await bad()
    assert calls["n"] == 1
