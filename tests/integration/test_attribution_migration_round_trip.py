"""Real PostgreSQL proof that the CRM attribution migration is reversible."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import psycopg

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ATTRIBUTION_TABLES = ("campaigns", "touchpoints")
_PRE_ATTRIBUTION_REVISION = "b7c9d1e2f304"


def _run_alembic(database_url: str, *arguments: str) -> None:
    environment = os.environ.copy()
    environment["DATABASE_URL"] = database_url
    subprocess.run(
        [sys.executable, "-m", "alembic", *arguments],
        cwd=_REPO_ROOT,
        env=environment,
        check=True,
    )


def _table_names(postgres_dsn: str) -> set[str]:
    with psycopg.connect(postgres_dsn) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename = ANY(%s)",
            (list(_ATTRIBUTION_TABLES),),
        )
        return {row[0] for row in cursor.fetchall()}


def test_crm_attribution_migration_round_trip(database_url: str, postgres_dsn: str) -> None:
    """Upgrade, revert attribution explicitly, then restore the current schema."""
    _run_alembic(database_url, "upgrade", "head")
    assert _table_names(postgres_dsn) == set(_ATTRIBUTION_TABLES)

    _run_alembic(database_url, "downgrade", _PRE_ATTRIBUTION_REVISION)
    assert _table_names(postgres_dsn).isdisjoint(_ATTRIBUTION_TABLES)

    _run_alembic(database_url, "upgrade", "head")
    assert _table_names(postgres_dsn) == set(_ATTRIBUTION_TABLES)
