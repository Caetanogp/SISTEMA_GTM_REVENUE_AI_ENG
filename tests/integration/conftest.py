"""Shared fixtures for tests/integration.

`DATABASE_URL` follows the SQLAlchemy dialect form (`postgresql+psycopg://...`) used everywhere
else in this repo (docker-compose default, CI). Some adapters need the raw libpq/psycopg DSN
instead - LangGraph's checkpointer is one - so `postgres_dsn` strips the `+psycopg` driver
segment SQLAlchemy uses to pick a DBAPI. psycopg itself doesn't understand that segment.
"""

from __future__ import annotations

import os

import psycopg
import pytest

_DEFAULT_DATABASE_URL = "postgresql+psycopg://revops:revops@localhost:5432/revops"


def _database_url() -> str:
    return os.environ.get("DATABASE_URL", _DEFAULT_DATABASE_URL)


def _raw_postgres_dsn(sqlalchemy_url: str) -> str:
    return sqlalchemy_url.replace("postgresql+psycopg://", "postgresql://", 1)


@pytest.fixture(scope="session")
def database_url() -> str:
    """The SQLAlchemy-dialect DSN, for engines and sessions."""
    return _database_url()


@pytest.fixture(scope="session")
def postgres_dsn() -> str:
    """The raw libpq DSN, for psycopg or LangGraph's checkpointer directly."""
    return _raw_postgres_dsn(_database_url())


@pytest.fixture(scope="session", autouse=True)
def _require_postgres(postgres_dsn: str) -> None:
    """Fail loudly, not silently skip, when the integration database isn't reachable.

    `pytest tests/integration -q` is a required, non-optional step in CI - a silent skip here
    would look green while testing nothing. Locally, this means `docker compose up -d` first.
    """
    try:
        with psycopg.connect(postgres_dsn, connect_timeout=3):
            pass
    except psycopg.OperationalError as exc:
        pytest.fail(
            f"tests/integration needs a reachable Postgres at {postgres_dsn} - "
            f"run `docker compose up -d` first. Connection error: {exc}",
            pytrace=False,
        )
