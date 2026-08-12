"""Unit tests for the centralized exception handlers.

Builds a throwaway app with routes that raise each exception class, and
asserts the HTTP contract the handlers promise — most importantly that DB pool
exhaustion surfaces as retryable backpressure (503 + Retry-After), never as a
generic 500 (which dashboards would read as a defect and clients won't retry).
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

from app.api.exceptions import register_exception_handlers
from app.shared.exceptions.base import AppError


def _build_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/pool-exhausted")
    async def pool_exhausted() -> None:
        raise PoolTimeoutError(
            "QueuePool limit of size 10 overflow 20 reached", None, None
        )

    class _TeapotError(AppError):
        status_code = 418

    @app.get("/app-error")
    async def app_error() -> None:
        raise _TeapotError("nope")

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("unexpected")

    return app


class TestPoolTimeoutHandler:
    def test_pool_exhaustion_is_503_with_retry_after(self) -> None:
        client = TestClient(_build_app(), raise_server_exceptions=False)
        response = client.get("/pool-exhausted")
        assert response.status_code == 503
        assert response.headers["Retry-After"] == "1"
        assert "capacity" in response.json()["detail"]

    def test_app_error_keeps_its_status(self) -> None:
        client = TestClient(_build_app(), raise_server_exceptions=False)
        response = client.get("/app-error")
        assert response.status_code == 418

    def test_unexpected_error_is_generic_500(self) -> None:
        client = TestClient(_build_app(), raise_server_exceptions=False)
        response = client.get("/boom")
        assert response.status_code == 500
        assert response.json() == {"detail": "Internal server error"}
