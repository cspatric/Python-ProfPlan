"""The probe's contract: it measures, and it never raises.

A probe that propagated an exception would take down the very endpoint the
alerts are scraped from, which is the failure mode these tests exist to prevent.
"""

from contextlib import asynccontextmanager

import pytest
from prometheus_client import REGISTRY

from app.infrastructure.telemetry import metrics


def _dependency(name: str) -> float | None:
    return REGISTRY.get_sample_value("profplan_dependency_up", {"dependency": name})


def _queue(name: str) -> float | None:
    return REGISTRY.get_sample_value("profplan_celery_queue_depth", {"queue": name})


class _Broker:
    """Minimal stand-in for the broker's Redis client."""

    def __init__(self, depths: dict[str, int | Exception]) -> None:
        self._depths = depths

    async def llen(self, queue: str) -> int:
        value = self._depths[queue]
        if isinstance(value, Exception):
            raise value
        return value


class _Engine:
    def __init__(self, error: Exception | None = None) -> None:
        self._error = error

    @asynccontextmanager
    async def connect(self):
        if self._error:
            raise self._error
        yield self

    async def execute(self, _statement):
        return None


class _Redis:
    def __init__(self, error: Exception | None = None) -> None:
        self._error = error

    async def ping(self) -> bool:
        if self._error:
            raise self._error
        return True


@pytest.fixture
def wire(monkeypatch):
    """Point the probe at fake dependencies."""

    def _wire(*, db_error=None, redis_error=None):
        import app.infrastructure.database.session as session
        import app.infrastructure.redis.client as redis_module

        monkeypatch.setattr(session, "engine", _Engine(db_error))
        monkeypatch.setattr(redis_module, "redis_client", _Redis(redis_error))

    return _wire


async def test_healthy_dependencies_report_one(wire):
    wire()
    await metrics.probe_once(_Broker({"celery": 0}), ["celery"])

    assert _dependency("database") == 1
    assert _dependency("redis") == 1


async def test_unreachable_dependency_reports_zero_without_raising(wire):
    wire(db_error=OSError("connection refused"))

    await metrics.probe_once(_Broker({"celery": 0}), ["celery"])

    assert _dependency("database") == 0
    # Redis is independent: one dependency failing must not skip the others.
    assert _dependency("redis") == 1


async def test_queue_depth_is_exported(wire):
    wire()
    await metrics.probe_once(_Broker({"celery": 42}), ["celery"])

    assert _queue("celery") == 42


async def test_broker_failure_leaves_the_probe_alive(wire):
    wire()
    await metrics.probe_once(_Broker({"celery": 7}), ["celery"])

    # The broker goes away: the depth keeps its last known value rather than
    # dropping to a zero that would read as "the queue drained".
    await metrics.probe_once(
        _Broker({"celery": ConnectionError("broker gone")}), ["celery"]
    )

    assert _queue("celery") == 7
    assert _dependency("database") == 1
