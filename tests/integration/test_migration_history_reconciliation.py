"""PostgreSQL proofs for reconciling both published deduplication schema shapes."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, create_engine, text
from sqlalchemy.exc import DBAPIError

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LEGACY_REVISION = "b7c9d1e2f304"
_ATTRIBUTION_REVISION = "e4f6a8c0d2b5"
_PLATFORM_SEED_REVISION = "b3c4d5e6f7a8"

_ORG = "00000000-0000-0000-0000-000000000001"
_USER = "00000000-0000-0000-0000-000000000002"
_ACCOUNT_LEFT = "00000000-0000-0000-0000-000000000010"
_ACCOUNT_RIGHT = "00000000-0000-0000-0000-000000000011"
_CONTACT_LEFT = "00000000-0000-0000-0000-000000000020"
_CONTACT_RIGHT = "00000000-0000-0000-0000-000000000021"
_JOB = "00000000-0000-0000-0000-000000000030"
_ITEM = "00000000-0000-0000-0000-000000000031"
_SCAN = "00000000-0000-0000-0000-000000000040"
_ACCOUNT_CANDIDATE = "00000000-0000-0000-0000-000000000041"
_CONTACT_CANDIDATE = "00000000-0000-0000-0000-000000000042"
_ACCOUNT_EVENT = "00000000-0000-0000-0000-000000000051"
_CONTACT_EVENT = "00000000-0000-0000-0000-000000000052"


def _config(connection: Connection, schema: str) -> Config:
    config = Config()
    config.set_main_option(
        "script_location",
        str(_REPO_ROOT / "packages/core/revops/infrastructure/persistence/migrations"),
    )
    config.attributes["connection"] = connection
    config.attributes["version_table_schema"] = schema
    return config


@contextmanager
def _isolated_schema(database_url: str) -> Iterator[tuple[Connection, Config]]:
    engine = create_engine(database_url)
    with engine.connect() as connection:
        transaction = connection.begin()
        schema = f"migration_reconciliation_{uuid4().hex}"
        original_default_schema = connection.dialect.default_schema_name
        try:
            connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
            connection.exec_driver_sql(f'SET search_path TO "{schema}", public')
            connection.dialect.default_schema_name = schema
            yield connection, _config(connection, schema)
        finally:
            connection.dialect.default_schema_name = original_default_schema
            transaction.rollback()
    engine.dispose()


def _execute(connection: Connection, statements: Sequence[str]) -> None:
    for statement in statements:
        connection.execute(text(statement))


def _install_original_legacy_revision(connection: Connection) -> None:
    _execute(
        connection,
        (
            "ALTER TABLE contacts ADD COLUMN phone VARCHAR(16) NULL",
            """
            CREATE TABLE deduplication_scans (
                id UUID PRIMARY KEY,
                organization_id UUID NOT NULL REFERENCES organizations(id),
                requested_by UUID NOT NULL REFERENCES users(id),
                record_types JSONB NOT NULL,
                policy_version VARCHAR(64) NOT NULL,
                idempotency_key VARCHAR(128) NOT NULL,
                status VARCHAR(32) NOT NULL,
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL,
                CONSTRAINT uq_dedupe_scans_org_key
                    UNIQUE (organization_id, idempotency_key)
            )
            """,
            "CREATE INDEX ix_dedupe_scans_org ON deduplication_scans (organization_id)",
            """
            CREATE TABLE deduplication_candidates (
                id UUID PRIMARY KEY,
                scan_id UUID NOT NULL REFERENCES deduplication_scans(id),
                organization_id UUID NOT NULL REFERENCES organizations(id),
                record_type VARCHAR(16) NOT NULL,
                left_id UUID NOT NULL,
                right_id UUID NOT NULL,
                score INTEGER NOT NULL,
                reasons JSONB NOT NULL,
                policy_version VARCHAR(64) NOT NULL,
                left_fingerprint VARCHAR(64) NOT NULL,
                right_fingerprint VARCHAR(64) NOT NULL,
                status VARCHAR(32) NOT NULL,
                CONSTRAINT uq_dedupe_candidate_pair UNIQUE (scan_id, left_id, right_id)
            )
            """,
            "CREATE INDEX ix_dedupe_candidates_scan ON deduplication_candidates (scan_id)",
            "CREATE INDEX ix_dedupe_candidates_org ON deduplication_candidates (organization_id)",
            """
            CREATE TABLE deduplication_events (
                id UUID PRIMARY KEY,
                organization_id UUID NOT NULL REFERENCES organizations(id),
                idempotency_key VARCHAR(128) NOT NULL,
                candidate_id UUID NULL REFERENCES deduplication_candidates(id),
                action VARCHAR(32) NOT NULL,
                actor_id UUID NOT NULL REFERENCES users(id),
                payload JSONB NOT NULL,
                occurred_at TIMESTAMPTZ NOT NULL,
                CONSTRAINT uq_dedupe_events_org_key
                    UNIQUE (organization_id, idempotency_key)
            )
            """,
            "CREATE INDEX ix_dedupe_events_org ON deduplication_events (organization_id)",
            """
            CREATE TABLE deduplication_aliases (
                id UUID PRIMARY KEY,
                organization_id UUID NOT NULL REFERENCES organizations(id),
                record_type VARCHAR(16) NOT NULL,
                alias_id UUID NOT NULL,
                canonical_id UUID NOT NULL,
                merge_event_id UUID NOT NULL REFERENCES deduplication_events(id),
                created_at TIMESTAMPTZ NOT NULL,
                reverted_at TIMESTAMPTZ NULL,
                CONSTRAINT uq_dedupe_alias_source UNIQUE (organization_id, alias_id)
            )
            """,
            "CREATE INDEX ix_dedupe_aliases_org ON deduplication_aliases (organization_id)",
        ),
    )


def _seed_base_records(connection: Connection, *, ingestion_has_phone: bool) -> None:
    ingestion_columns = ", phone" if ingestion_has_phone else ""
    ingestion_values = ", '+15550100'" if ingestion_has_phone else ""
    _execute(
        connection,
        (
            f"INSERT INTO organizations VALUES ('{_ORG}', 'Migration test', false)",
            f"INSERT INTO users VALUES ('{_USER}', '{_ORG}', 'migration@example.test', 'admin')",
            f"""
            INSERT INTO accounts (id, organization_id, company_name, domain, created_at)
            VALUES
                ('{_ACCOUNT_LEFT}', '{_ORG}', 'Left account', 'left.example', now()),
                ('{_ACCOUNT_RIGHT}', '{_ORG}', 'Right account', 'right.example', now())
            """,
            f"""
            INSERT INTO contacts (
                id, organization_id, account_id, email, full_name, title, phone
            ) VALUES
                (
                    '{_CONTACT_LEFT}', '{_ORG}', '{_ACCOUNT_LEFT}',
                    'left@example.test', 'Left contact', 'Buyer', '+15550101'
                ),
                (
                    '{_CONTACT_RIGHT}', '{_ORG}', '{_ACCOUNT_RIGHT}',
                    'right@example.test', 'Right contact', 'Buyer', '+15550102'
                )
            """,
            f"""
            INSERT INTO ingestion_jobs (
                id, organization_id, requested_by, source, idempotency_key,
                content_hash, status, failure_code, created_at, updated_at
            ) VALUES (
                '{_JOB}', '{_ORG}', '{_USER}', 'csv', 'migration-job',
                'hash', 'completed', NULL, now(), now()
            )
            """,
            f"""
            INSERT INTO ingestion_items (
                id, ingestion_job_id, row_number, company_name, domain, email,
                full_name, title, validation_codes, status, account_outcome,
                contact_outcome, enrichment_outcome, account_id, contact_id,
                enrichment_id{ingestion_columns}
            ) VALUES (
                '{_ITEM}', '{_JOB}', 1, 'Left account', 'left.example',
                'left@example.test', 'Left contact', 'Buyer', '[]'::jsonb,
                'completed', 'created', 'created', 'not_requested',
                '{_ACCOUNT_LEFT}', '{_CONTACT_LEFT}', NULL{ingestion_values}
            )
            """,
            f"""
            INSERT INTO interactions (
                id, organization_id, account_id, channel, occurred_at, summary,
                contact_id, content
            ) VALUES (
                '00000000-0000-0000-0000-000000000060', '{_ORG}',
                '{_ACCOUNT_LEFT}', 'email', now(), 'Legacy interaction', NULL, NULL
            )
            """,
            f"""
            INSERT INTO opportunities (
                id, organization_id, account_id, stage, value, status
            ) VALUES (
                '00000000-0000-0000-0000-000000000061', '{_ORG}',
                '{_ACCOUNT_LEFT}', 'prospecting', 1000, 'open'
            )
            """,
            f"""
            INSERT INTO deduplication_scans (
                id, organization_id, requested_by, record_types, policy_version,
                idempotency_key, status, created_at, updated_at
            ) VALUES (
                '{_SCAN}', '{_ORG}', '{_USER}', '["account", "contact"]'::jsonb,
                'dedupe_v1', 'migration-scan', 'completed', now(), now()
            )
            """,
        ),
    )


def _seed_legacy_deduplication_records(connection: Connection) -> None:
    _execute(
        connection,
        (
            f"""
            INSERT INTO deduplication_candidates (
                id, scan_id, organization_id, record_type, left_id, right_id, score,
                reasons, policy_version, left_fingerprint, right_fingerprint, status
            ) VALUES
                (
                    '{_ACCOUNT_CANDIDATE}', '{_SCAN}', '{_ORG}', 'account',
                    '{_ACCOUNT_LEFT}', '{_ACCOUNT_RIGHT}', 100, '["domain_exact"]'::jsonb,
                    'dedupe_v1', 'left-account', 'right-account', 'merged'
                ),
                (
                    '{_CONTACT_CANDIDATE}', '{_SCAN}', '{_ORG}', 'contact',
                    '{_CONTACT_LEFT}', '{_CONTACT_RIGHT}', 90, '["email_exact"]'::jsonb,
                    'dedupe_v1', 'left-contact', 'right-contact', 'merged'
                )
            """,
            f"""
            INSERT INTO deduplication_events (
                id, organization_id, idempotency_key, candidate_id, action,
                actor_id, payload, occurred_at
            ) VALUES
                (
                    '{_ACCOUNT_EVENT}', '{_ORG}', 'account-merge',
                    '{_ACCOUNT_CANDIDATE}', 'merge', '{_USER}',
                    '{{"marker": "preserve-account"}}'::jsonb, now()
                ),
                (
                    '{_CONTACT_EVENT}', '{_ORG}', 'contact-merge',
                    '{_CONTACT_CANDIDATE}', 'merge', '{_USER}',
                    '{{"marker": "preserve-contact"}}'::jsonb, now()
                )
            """,
            f"""
            INSERT INTO deduplication_aliases (
                id, organization_id, record_type, alias_id, canonical_id,
                merge_event_id, created_at, reverted_at
            ) VALUES
                (
                    '{_ACCOUNT_EVENT}', '{_ORG}', 'account', '{_ACCOUNT_RIGHT}',
                    '{_ACCOUNT_LEFT}', '{_ACCOUNT_EVENT}', now(), NULL
                ),
                (
                    '{_CONTACT_EVENT}', '{_ORG}', 'contact', '{_CONTACT_RIGHT}',
                    '{_CONTACT_LEFT}', '{_CONTACT_EVENT}', now(), NULL
                )
            """,
        ),
    )


def _seed_typed_deduplication_record(connection: Connection) -> None:
    _execute(
        connection,
        (
            f"""
            INSERT INTO deduplication_account_candidates (
                id, scan_id, organization_id, left_id, right_id, score, reasons,
                policy_version, left_fingerprint, right_fingerprint, status
            ) VALUES (
                '{_ACCOUNT_CANDIDATE}', '{_SCAN}', '{_ORG}', '{_ACCOUNT_LEFT}',
                '{_ACCOUNT_RIGHT}', 100, '["domain_exact"]'::jsonb, 'dedupe_v1',
                'left-account', 'right-account', 'merged'
            )
            """,
            f"""
            INSERT INTO deduplication_events (
                id, organization_id, idempotency_key, account_candidate_id,
                contact_candidate_id, related_event_id, action, actor_id, payload, occurred_at
            ) VALUES (
                '{_ACCOUNT_EVENT}', '{_ORG}', 'account-merge', '{_ACCOUNT_CANDIDATE}',
                NULL, NULL, 'merge', '{_USER}',
                '{{"record_type": "account", "marker": "typed"}}'::jsonb, now()
            )
            """,
            f"""
            INSERT INTO deduplication_account_aliases (
                id, organization_id, alias_id, canonical_id, merge_event_id,
                created_at, reverted_at, reverted_by_event_id
            ) VALUES (
                '{_ACCOUNT_EVENT}', '{_ORG}', '{_ACCOUNT_RIGHT}', '{_ACCOUNT_LEFT}',
                '{_ACCOUNT_EVENT}', now(), NULL, NULL
            )
            """,
        ),
    )


def _scalar(connection: Connection, query: str) -> object:
    return connection.execute(text(query)).scalar_one()


def test_legacy_schema_is_reconciled_without_losing_data(database_url: str) -> None:
    with _isolated_schema(database_url) as (connection, config):
        command.upgrade(config, "9a4e2c6d7f80")
        _install_original_legacy_revision(connection)
        command.stamp(config, _LEGACY_REVISION)
        command.upgrade(config, _ATTRIBUTION_REVISION)
        _seed_base_records(connection, ingestion_has_phone=False)
        _seed_legacy_deduplication_records(connection)

        command.upgrade(config, "head")

        assert (
            _scalar(connection, "SELECT version_num FROM alembic_version")
            == _PLATFORM_SEED_REVISION
        )
        assert _scalar(connection, "SELECT count(*) FROM deduplication_candidates") == 2
        assert _scalar(connection, "SELECT count(*) FROM deduplication_aliases") == 2
        assert _scalar(connection, "SELECT count(*) FROM deduplication_account_candidates") == 1
        assert _scalar(connection, "SELECT count(*) FROM deduplication_contact_candidates") == 1
        assert _scalar(connection, "SELECT count(*) FROM deduplication_account_aliases") == 1
        assert _scalar(connection, "SELECT count(*) FROM deduplication_contact_aliases") == 1
        assert (
            _scalar(
                connection,
                """
            SELECT payload->>'marker' FROM deduplication_events
            WHERE account_candidate_id IS NOT NULL
            """,
            )
            == "preserve-account"
        )
        assert (
            _scalar(
                connection,
                """
            SELECT payload->>'marker' FROM deduplication_events
            WHERE contact_candidate_id IS NOT NULL
            """,
            )
            == "preserve-contact"
        )
        assert (
            _scalar(
                connection,
                """
            SELECT count(*) FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = 'ingestion_items' AND column_name = 'phone'
            """,
            )
            == 1
        )
        assert _scalar(connection, "SELECT count(*) FROM interactions WHERE content IS NULL") == 1
        command.check(config)


def test_current_typed_schema_repair_is_a_data_preserving_no_op(database_url: str) -> None:
    with _isolated_schema(database_url) as (connection, config):
        command.upgrade(config, _ATTRIBUTION_REVISION)
        _seed_base_records(connection, ingestion_has_phone=True)
        _seed_typed_deduplication_record(connection)

        command.upgrade(config, "head")
        command.downgrade(config, _ATTRIBUTION_REVISION)
        command.upgrade(config, "head")

        assert (
            _scalar(connection, "SELECT version_num FROM alembic_version")
            == _PLATFORM_SEED_REVISION
        )
        assert _scalar(connection, "SELECT count(*) FROM deduplication_account_candidates") == 1
        assert _scalar(connection, "SELECT count(*) FROM deduplication_account_aliases") == 1
        assert (
            _scalar(
                connection,
                "SELECT payload->>'marker' FROM deduplication_events WHERE id = "
                f"'{_ACCOUNT_EVENT}'",
            )
            == "typed"
        )
        assert (
            _scalar(
                connection,
                f"SELECT phone FROM ingestion_items WHERE id = '{_ITEM}'",
            )
            == "+15550100"
        )
        command.check(config)


@pytest.mark.parametrize(
    ("invalid_candidate", "expected_error"),
    [
        (
            f"""
            INSERT INTO deduplication_candidates (
                id, scan_id, organization_id, record_type, left_id, right_id, score,
                reasons, policy_version, left_fingerprint, right_fingerprint, status
            ) VALUES (
                '{_ACCOUNT_CANDIDATE}', '{_SCAN}', '{_ORG}', 'organization',
                '{_ACCOUNT_LEFT}', '{_ACCOUNT_RIGHT}', 100, '[]'::jsonb,
                'dedupe_v1', 'left', 'right', 'pending'
            )
            """,
            "unsupported record_type",
        ),
        (
            f"""
            INSERT INTO deduplication_candidates (
                id, scan_id, organization_id, record_type, left_id, right_id, score,
                reasons, policy_version, left_fingerprint, right_fingerprint, status
            ) VALUES (
                '{_ACCOUNT_CANDIDATE}', '{_SCAN}', '{_ORG}', 'account',
                '00000000-0000-0000-0000-000000000099', '{_ACCOUNT_RIGHT}',
                100, '[]'::jsonb, 'dedupe_v1', 'left', 'right', 'pending'
            )
            """,
            "orphaned or cross-tenant records",
        ),
    ],
)
def test_legacy_repair_fails_atomically_for_invalid_candidates(
    database_url: str, invalid_candidate: str, expected_error: str
) -> None:
    with _isolated_schema(database_url) as (connection, config):
        command.upgrade(config, "9a4e2c6d7f80")
        _install_original_legacy_revision(connection)
        command.stamp(config, _LEGACY_REVISION)
        command.upgrade(config, _ATTRIBUTION_REVISION)
        _seed_base_records(connection, ingestion_has_phone=False)
        connection.execute(text(invalid_candidate))

        with pytest.raises(DBAPIError, match=expected_error):
            command.upgrade(config, "head")
