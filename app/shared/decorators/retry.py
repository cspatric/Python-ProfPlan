"""Reusable retry decorators for unstable external calls.

Use these on functions that call external services (LLM providers, third-party
HTTP APIs) that may fail transiently. They retry only transient errors with
exponential backoff and re-raise the last error if all attempts fail.

"Transient" means network errors (timeouts/connection) AND HTTP 429 (rate
limit) or 5xx (server error) responses — e.g. a provider briefly returning
503. Client errors (4xx other than 429) are NOT retried: they won't succeed
on a retry.

Example:
    from app.shared.decorators.retry import external_call

    @external_call()
    async def generate_plan(prompt: str) -> str:
        resp = await client.post(url, json={"prompt": prompt})
        resp.raise_for_status()
        return resp.text
"""

import logging
from collections.abc import Callable
from typing import TypeVar

import httpx
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger("app.retry")

F = TypeVar("F", bound=Callable[..., object])

# Network-level transient errors (no HTTP response at all).
_NETWORK_ERRORS = (httpx.TimeoutException, httpx.TransportError)


def _is_transient(exc: BaseException) -> bool:
    """True for retryable failures: network errors, HTTP 429 or 5xx."""
    if isinstance(exc, _NETWORK_ERRORS):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return status == 429 or status >= 500
    return False


def external_call(
    *,
    max_attempts: int = 3,
    initial_wait: float = 0.5,
    max_wait: float = 10.0,
) -> Callable[[F], F]:
    """Retry a sync or async callable with exponential backoff.

    Retries transient failures (network errors, HTTP 429/5xx) and re-raises the
    last error once ``max_attempts`` is reached.
    """
    return retry(  # type: ignore[return-value]
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=initial_wait, max=max_wait),
        retry=retry_if_exception(_is_transient),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
