"""Reusable retry decorators for unstable external calls.

Use these on functions that call external services (LLM providers, third-party
HTTP APIs) that may fail transiently. They retry only transient errors with
exponential backoff and re-raise the last error if all attempts fail.

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
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger("app.retry")

F = TypeVar("F", bound=Callable[..., object])

# Transient errors worth retrying for outbound HTTP/LLM calls.
RETRYABLE_EXCEPTIONS: tuple[type[Exception], ...] = (
    httpx.TimeoutException,
    httpx.TransportError,
)


def external_call(
    *,
    max_attempts: int = 3,
    initial_wait: float = 0.5,
    max_wait: float = 10.0,
    exceptions: tuple[type[Exception], ...] = RETRYABLE_EXCEPTIONS,
) -> Callable[[F], F]:
    """Retry a sync or async callable with exponential backoff.

    Retries only ``exceptions`` (transient by default) and re-raises the last
    error once ``max_attempts`` is reached.
    """
    return retry(  # type: ignore[return-value]
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=initial_wait, max=max_wait),
        retry=retry_if_exception_type(exceptions),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
