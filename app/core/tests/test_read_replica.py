"""The read session is a no-op until a replica exists.

The property worth protecting: a route may depend on the read session
unconditionally. With no replica it reads the primary and behaves exactly as
before; the day DATABASE_REPLICA_URL is set, the same route reads the replica
without anybody editing it.
"""

import importlib

import pytest

import app.core.config as config

REPLICA = "postgresql+asyncpg://profplan:pw@replica:6432/profplan"


def _session_module(monkeypatch: pytest.MonkeyPatch, replica_url: str = ""):
    monkeypatch.setenv("DATABASE_REPLICA_URL", replica_url)
    config.get_settings.cache_clear()
    module = importlib.import_module("app.infrastructure.database.session")
    return importlib.reload(module)


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    yield
    config.get_settings.cache_clear()


def test_without_the_variable_there_is_no_second_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _session_module(monkeypatch)
    assert session.replica_engine is None
    assert session.ReplicaSessionFactory is None
    assert session.has_replica() is False


def test_setting_the_variable_builds_the_replica_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _session_module(monkeypatch, REPLICA)
    assert session.replica_engine is not None
    assert session.has_replica() is True
    assert session.replica_engine.url.host == "replica"


def test_the_replica_is_a_different_engine_from_the_primary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reads must leave the primary's pool, not be added to it."""
    session = _session_module(monkeypatch, REPLICA)
    assert session.replica_engine is not session.engine


def test_the_replica_pool_matches_the_derived_primary_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No second budget to maintain: the replica inherits the derivation."""
    monkeypatch.setenv("DB_CLIENT_CONN_BUDGET", "60")
    monkeypatch.setenv("UVICORN_WORKERS", "2")
    session = _session_module(monkeypatch, REPLICA)
    assert session.replica_engine.pool.size() == session.engine.pool.size()


def test_the_pooler_statement_cache_option_reaches_the_replica_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A replica behind its own PgBouncer needs the same asyncpg handling."""
    monkeypatch.setenv("DB_PGBOUNCER", "true")
    session = _session_module(monkeypatch, REPLICA)
    assert "prepared_statement_cache_size=0" in str(session.replica_engine.url)
