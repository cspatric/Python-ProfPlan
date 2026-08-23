"""The pool is derived per container, so the worker count stops mattering.

These assert the property the derivation exists for: whatever UVICORN_WORKERS
is, one container's total client connections stay at (or just under) the budget,
so adding workers never silently multiplies the database footprint.
"""

import importlib

import pytest

import app.core.config as config


def _pool_sizes(
    monkeypatch: pytest.MonkeyPatch, *, budget: int, workers: int, **overrides: str
) -> tuple[int, int]:
    """Reload the session module under a given environment and read its sizes."""
    monkeypatch.setenv("DB_CLIENT_CONN_BUDGET", str(budget))
    monkeypatch.setenv("UVICORN_WORKERS", str(workers))
    for key, value in overrides.items():
        monkeypatch.setenv(key, value)
    config.get_settings.cache_clear()
    session = importlib.import_module("app.infrastructure.database.session")
    importlib.reload(session)
    try:
        return session._pool_sizes()
    finally:
        config.get_settings.cache_clear()


@pytest.mark.parametrize("workers", [1, 2, 4, 8])
def test_the_container_total_never_exceeds_the_budget(
    monkeypatch: pytest.MonkeyPatch, workers: int
) -> None:
    size, overflow = _pool_sizes(monkeypatch, budget=64, workers=workers)
    assert (size + overflow) * workers <= 64


def test_one_worker_keeps_the_previous_hardcoded_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The default budget with one worker is exactly the old 10 + 20."""
    assert _pool_sizes(monkeypatch, budget=30, workers=1) == (10, 20)


def test_more_workers_shrink_each_pool_instead_of_growing_the_total(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    one = _pool_sizes(monkeypatch, budget=60, workers=1)
    four = _pool_sizes(monkeypatch, budget=60, workers=4)
    assert sum(four) < sum(one)
    assert sum(four) * 4 == sum(one)


def test_an_explicit_pool_size_wins_over_the_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    size, overflow = _pool_sizes(
        monkeypatch, budget=30, workers=4, DB_POOL_SIZE="7", DB_MAX_OVERFLOW="3"
    )
    assert (size, overflow) == (7, 3)


def test_a_pool_is_never_zero_sized(monkeypatch: pytest.MonkeyPatch) -> None:
    """More workers than budget still has to serve requests, not deadlock."""
    size, overflow = _pool_sizes(monkeypatch, budget=1, workers=32)
    assert size >= 1
    assert overflow >= 1
