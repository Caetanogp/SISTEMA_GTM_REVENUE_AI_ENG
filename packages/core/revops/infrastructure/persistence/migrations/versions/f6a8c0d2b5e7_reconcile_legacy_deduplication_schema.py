"""Reconcile legacy and typed deduplication schemas without deleting history.

Revision ID: f6a8c0d2b5e7
Revises: e4f6a8c0d2b5
Create Date: 2026-09-13 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f6a8c0d2b5e7"
down_revision: str | None = "e4f6a8c0d2b5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _execute(statement: str) -> None:
    op.execute(sa.text(statement))


def _ensure_prerequisites() -> None:
    _execute("ALTER TABLE ingestion_items ADD COLUMN IF NOT EXISTS phone VARCHAR(16)")
    _execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'uq_accounts_org_id'
                  AND conrelid = 'accounts'::regclass
            ) THEN
                ALTER TABLE accounts ADD CONSTRAINT uq_accounts_org_id
                    UNIQUE (organization_id, id);
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'uq_contacts_org_id'
                  AND conrelid = 'contacts'::regclass
            ) THEN
                ALTER TABLE contacts ADD CONSTRAINT uq_contacts_org_id
                    UNIQUE (organization_id, id);
            END IF;
        END $$;
        """
    )


def _create_typed_candidate_tables() -> None:
    for record_type, record_table in (("account", "accounts"), ("contact", "contacts")):
        table = f"deduplication_{record_type}_candidates"
        _execute(
            f"""
            CREATE TABLE IF NOT EXISTS {table} (
                id UUID NOT NULL PRIMARY KEY,
                scan_id UUID NOT NULL REFERENCES deduplication_scans(id),
                organization_id UUID NOT NULL REFERENCES organizations(id),
                left_id UUID NOT NULL,
                right_id UUID NOT NULL,
                score INTEGER NOT NULL,
                reasons JSONB NOT NULL,
                policy_version VARCHAR(64) NOT NULL,
                left_fingerprint VARCHAR(64) NOT NULL,
                right_fingerprint VARCHAR(64) NOT NULL,
                status VARCHAR(32) NOT NULL,
                CONSTRAINT uq_dedupe_{record_type}_candidate_pair
                    UNIQUE (scan_id, left_id, right_id),
                FOREIGN KEY (organization_id, left_id)
                    REFERENCES {record_table}(organization_id, id),
                FOREIGN KEY (organization_id, right_id)
                    REFERENCES {record_table}(organization_id, id)
            )
            """
        )
        _execute(
            f"CREATE INDEX IF NOT EXISTS ix_dedupe_{record_type}_candidates_scan "
            f"ON {table} (scan_id)"
        )
        _execute(
            f"CREATE INDEX IF NOT EXISTS ix_dedupe_{record_type}_candidates_org "
            f"ON {table} (organization_id)"
        )


def _copy_legacy_candidates() -> None:
    _execute(
        """
        DO $$
        BEGIN
            IF to_regclass(current_schema() || '.deduplication_candidates') IS NULL THEN
                RETURN;
            END IF;
            IF EXISTS (
                SELECT 1 FROM deduplication_candidates
                WHERE record_type NOT IN ('account', 'contact')
            ) THEN
                RAISE EXCEPTION 'legacy deduplication candidate has unsupported record_type';
            END IF;
            IF EXISTS (
                SELECT 1
                FROM deduplication_candidates candidate
                LEFT JOIN deduplication_scans scan ON scan.id = candidate.scan_id
                WHERE scan.id IS NULL OR scan.organization_id <> candidate.organization_id
            ) THEN
                RAISE EXCEPTION 'legacy deduplication candidate has an invalid tenant-scoped scan';
            END IF;
            IF EXISTS (
                SELECT 1
                FROM deduplication_candidates candidate
                LEFT JOIN accounts left_record
                    ON left_record.id = candidate.left_id
                   AND left_record.organization_id = candidate.organization_id
                LEFT JOIN accounts right_record
                    ON right_record.id = candidate.right_id
                   AND right_record.organization_id = candidate.organization_id
                WHERE candidate.record_type = 'account'
                  AND (left_record.id IS NULL OR right_record.id IS NULL)
            ) OR EXISTS (
                SELECT 1
                FROM deduplication_candidates candidate
                LEFT JOIN contacts left_record
                    ON left_record.id = candidate.left_id
                   AND left_record.organization_id = candidate.organization_id
                LEFT JOIN contacts right_record
                    ON right_record.id = candidate.right_id
                   AND right_record.organization_id = candidate.organization_id
                WHERE candidate.record_type = 'contact'
                  AND (left_record.id IS NULL OR right_record.id IS NULL)
            ) THEN
                RAISE EXCEPTION 'legacy candidate has orphaned or cross-tenant records';
            END IF;
            IF EXISTS (
                SELECT 1
                FROM deduplication_candidates legacy
                JOIN deduplication_account_candidates typed ON typed.id = legacy.id
                WHERE legacy.record_type = 'account'
                  AND ROW(
                      typed.scan_id, typed.organization_id, typed.left_id, typed.right_id,
                      typed.score, typed.reasons, typed.policy_version,
                      typed.left_fingerprint, typed.right_fingerprint, typed.status
                  ) IS DISTINCT FROM ROW(
                      legacy.scan_id, legacy.organization_id, legacy.left_id, legacy.right_id,
                      legacy.score, legacy.reasons, legacy.policy_version,
                      legacy.left_fingerprint, legacy.right_fingerprint, legacy.status
                  )
            ) OR EXISTS (
                SELECT 1
                FROM deduplication_candidates legacy
                JOIN deduplication_contact_candidates typed ON typed.id = legacy.id
                WHERE legacy.record_type = 'contact'
                  AND ROW(
                      typed.scan_id, typed.organization_id, typed.left_id, typed.right_id,
                      typed.score, typed.reasons, typed.policy_version,
                      typed.left_fingerprint, typed.right_fingerprint, typed.status
                  ) IS DISTINCT FROM ROW(
                      legacy.scan_id, legacy.organization_id, legacy.left_id, legacy.right_id,
                      legacy.score, legacy.reasons, legacy.policy_version,
                      legacy.left_fingerprint, legacy.right_fingerprint, legacy.status
                  )
            ) OR EXISTS (
                SELECT 1 FROM deduplication_candidates legacy
                JOIN deduplication_contact_candidates typed ON typed.id = legacy.id
                WHERE legacy.record_type = 'account'
            ) OR EXISTS (
                SELECT 1 FROM deduplication_candidates legacy
                JOIN deduplication_account_candidates typed ON typed.id = legacy.id
                WHERE legacy.record_type = 'contact'
            ) THEN
                RAISE EXCEPTION 'legacy deduplication candidate conflicts with typed data';
            END IF;

            INSERT INTO deduplication_account_candidates (
                id, scan_id, organization_id, left_id, right_id, score, reasons,
                policy_version, left_fingerprint, right_fingerprint, status
            )
            SELECT id, scan_id, organization_id, left_id, right_id, score, reasons,
                   policy_version, left_fingerprint, right_fingerprint, status
            FROM deduplication_candidates
            WHERE record_type = 'account'
            ON CONFLICT (id) DO NOTHING;

            INSERT INTO deduplication_contact_candidates (
                id, scan_id, organization_id, left_id, right_id, score, reasons,
                policy_version, left_fingerprint, right_fingerprint, status
            )
            SELECT id, scan_id, organization_id, left_id, right_id, score, reasons,
                   policy_version, left_fingerprint, right_fingerprint, status
            FROM deduplication_candidates
            WHERE record_type = 'contact'
            ON CONFLICT (id) DO NOTHING;
        END $$;
        """
    )


def _reconcile_events() -> None:
    for column in ("account_candidate_id", "contact_candidate_id", "related_event_id"):
        _execute(f"ALTER TABLE deduplication_events ADD COLUMN IF NOT EXISTS {column} UUID NULL")
    _execute(
        """
        DO $$
        BEGIN
            IF to_regclass(current_schema() || '.deduplication_candidates') IS NOT NULL THEN
                IF EXISTS (
                    SELECT 1
                    FROM deduplication_events event
                    LEFT JOIN deduplication_candidates candidate
                        ON candidate.id = event.candidate_id
                    WHERE event.candidate_id IS NOT NULL
                      AND event.action <> 'revert'
                      AND (
                          candidate.id IS NULL
                          OR candidate.organization_id <> event.organization_id
                      )
                ) THEN
                    RAISE EXCEPTION 'legacy deduplication event has an invalid candidate';
                END IF;
                IF EXISTS (
                    SELECT 1
                    FROM deduplication_events event
                    LEFT JOIN deduplication_events merge_event
                        ON merge_event.id = event.candidate_id
                       AND merge_event.organization_id = event.organization_id
                       AND merge_event.action = 'merge'
                    WHERE event.action = 'revert'
                      AND event.candidate_id IS NOT NULL
                      AND merge_event.id IS NULL
                ) THEN
                    RAISE EXCEPTION 'legacy revert event has an invalid merge event';
                END IF;
                IF EXISTS (
                    SELECT 1
                    FROM deduplication_events event
                    JOIN deduplication_candidates candidate
                        ON candidate.id = event.candidate_id
                    WHERE event.action <> 'revert'
                      AND (
                          (candidate.record_type = 'account' AND (
                              event.contact_candidate_id IS NOT NULL
                              OR event.account_candidate_id IS DISTINCT FROM event.candidate_id
                                  AND event.account_candidate_id IS NOT NULL
                          ))
                          OR (candidate.record_type = 'contact' AND (
                              event.account_candidate_id IS NOT NULL
                              OR event.contact_candidate_id IS DISTINCT FROM event.candidate_id
                                  AND event.contact_candidate_id IS NOT NULL
                          ))
                      )
                ) OR EXISTS (
                    SELECT 1 FROM deduplication_events
                    WHERE action = 'revert'
                      AND candidate_id IS NOT NULL
                      AND (
                          account_candidate_id IS NOT NULL
                          OR contact_candidate_id IS NOT NULL
                          OR related_event_id IS DISTINCT FROM candidate_id
                              AND related_event_id IS NOT NULL
                      )
                ) THEN
                    RAISE EXCEPTION 'legacy deduplication event conflicts with typed linkage';
                END IF;

                UPDATE deduplication_events event
                SET account_candidate_id = event.candidate_id
                FROM deduplication_candidates candidate
                WHERE candidate.id = event.candidate_id
                  AND candidate.record_type = 'account'
                  AND event.action <> 'revert'
                  AND event.account_candidate_id IS NULL;

                UPDATE deduplication_events event
                SET contact_candidate_id = event.candidate_id
                FROM deduplication_candidates candidate
                WHERE candidate.id = event.candidate_id
                  AND candidate.record_type = 'contact'
                  AND event.action <> 'revert'
                  AND event.contact_candidate_id IS NULL;

                UPDATE deduplication_events
                SET related_event_id = candidate_id
                WHERE action = 'revert'
                  AND candidate_id IS NOT NULL
                  AND related_event_id IS NULL;
            END IF;
        END $$;
        """
    )
    _execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conrelid = 'deduplication_events'::regclass
                  AND contype = 'f'
                  AND confrelid = 'deduplication_account_candidates'::regclass
                  AND conkey = ARRAY[(
                      SELECT attnum FROM pg_attribute
                      WHERE attrelid = 'deduplication_events'::regclass
                        AND attname = 'account_candidate_id'
                  )]
            ) THEN
                ALTER TABLE deduplication_events
                    ADD CONSTRAINT fk_dedupe_events_account_candidate
                    FOREIGN KEY (account_candidate_id)
                    REFERENCES deduplication_account_candidates(id);
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conrelid = 'deduplication_events'::regclass
                  AND contype = 'f'
                  AND confrelid = 'deduplication_contact_candidates'::regclass
                  AND conkey = ARRAY[(
                      SELECT attnum FROM pg_attribute
                      WHERE attrelid = 'deduplication_events'::regclass
                        AND attname = 'contact_candidate_id'
                  )]
            ) THEN
                ALTER TABLE deduplication_events
                    ADD CONSTRAINT fk_dedupe_events_contact_candidate
                    FOREIGN KEY (contact_candidate_id)
                    REFERENCES deduplication_contact_candidates(id);
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conrelid = 'deduplication_events'::regclass
                  AND contype = 'f'
                  AND confrelid = 'deduplication_events'::regclass
                  AND conkey = ARRAY[(
                      SELECT attnum FROM pg_attribute
                      WHERE attrelid = 'deduplication_events'::regclass
                        AND attname = 'related_event_id'
                  )]
            ) THEN
                ALTER TABLE deduplication_events
                    ADD CONSTRAINT fk_dedupe_events_related_event
                    FOREIGN KEY (related_event_id) REFERENCES deduplication_events(id);
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conrelid = 'deduplication_events'::regclass
                  AND conname = 'ck_dedupe_event_one_candidate'
            ) THEN
                ALTER TABLE deduplication_events
                    ADD CONSTRAINT ck_dedupe_event_one_candidate
                    CHECK (
                        account_candidate_id IS NULL OR contact_candidate_id IS NULL
                    );
            END IF;
        END $$;
        """
    )


def _create_typed_alias_tables() -> None:
    for record_type, record_table in (("account", "accounts"), ("contact", "contacts")):
        table = f"deduplication_{record_type}_aliases"
        _execute(
            f"""
            CREATE TABLE IF NOT EXISTS {table} (
                id UUID NOT NULL PRIMARY KEY,
                organization_id UUID NOT NULL REFERENCES organizations(id),
                alias_id UUID NOT NULL,
                canonical_id UUID NOT NULL,
                merge_event_id UUID NOT NULL REFERENCES deduplication_events(id),
                created_at TIMESTAMPTZ NOT NULL,
                reverted_at TIMESTAMPTZ NULL,
                reverted_by_event_id UUID NULL REFERENCES deduplication_events(id),
                FOREIGN KEY (organization_id, alias_id)
                    REFERENCES {record_table}(organization_id, id),
                FOREIGN KEY (organization_id, canonical_id)
                    REFERENCES {record_table}(organization_id, id)
            )
            """
        )
        _execute(
            f"CREATE INDEX IF NOT EXISTS ix_dedupe_{record_type}_aliases_org "
            f"ON {table} (organization_id)"
        )
        _execute(
            f"CREATE UNIQUE INDEX IF NOT EXISTS uq_dedupe_{record_type}_alias_source "
            f"ON {table} (organization_id, alias_id) WHERE reverted_at IS NULL"
        )


def _copy_legacy_aliases() -> None:
    _execute(
        """
        DO $$
        BEGIN
            IF to_regclass(current_schema() || '.deduplication_aliases') IS NULL THEN
                RETURN;
            END IF;
            IF EXISTS (
                SELECT 1 FROM deduplication_aliases
                WHERE record_type NOT IN ('account', 'contact')
            ) THEN
                RAISE EXCEPTION 'legacy deduplication alias has unsupported record_type';
            END IF;
            IF EXISTS (
                SELECT 1
                FROM deduplication_aliases alias
                JOIN deduplication_events event ON event.id = alias.merge_event_id
                LEFT JOIN deduplication_candidates candidate
                    ON candidate.id = event.candidate_id
                WHERE event.organization_id <> alias.organization_id
                   OR event.action <> 'merge'
                   OR candidate.id IS NULL
                   OR candidate.record_type <> alias.record_type
            ) OR EXISTS (
                SELECT 1
                FROM deduplication_aliases alias
                LEFT JOIN deduplication_events event ON event.id = alias.merge_event_id
                WHERE event.id IS NULL
            ) THEN
                RAISE EXCEPTION 'legacy deduplication alias has an invalid merge event';
            END IF;
            IF EXISTS (
                SELECT 1
                FROM deduplication_aliases alias
                LEFT JOIN accounts source
                    ON source.id = alias.alias_id
                   AND source.organization_id = alias.organization_id
                LEFT JOIN accounts canonical
                    ON canonical.id = alias.canonical_id
                   AND canonical.organization_id = alias.organization_id
                WHERE alias.record_type = 'account'
                  AND (source.id IS NULL OR canonical.id IS NULL)
            ) OR EXISTS (
                SELECT 1
                FROM deduplication_aliases alias
                LEFT JOIN contacts source
                    ON source.id = alias.alias_id
                   AND source.organization_id = alias.organization_id
                LEFT JOIN contacts canonical
                    ON canonical.id = alias.canonical_id
                   AND canonical.organization_id = alias.organization_id
                WHERE alias.record_type = 'contact'
                  AND (source.id IS NULL OR canonical.id IS NULL)
            ) THEN
                RAISE EXCEPTION 'legacy deduplication alias has orphaned or cross-tenant records';
            END IF;
            IF EXISTS (
                SELECT 1
                FROM deduplication_aliases legacy
                JOIN deduplication_account_aliases typed ON typed.id = legacy.id
                WHERE legacy.record_type = 'account'
                  AND ROW(
                      typed.organization_id, typed.alias_id, typed.canonical_id,
                      typed.merge_event_id, typed.created_at, typed.reverted_at
                  ) IS DISTINCT FROM ROW(
                      legacy.organization_id, legacy.alias_id, legacy.canonical_id,
                      legacy.merge_event_id, legacy.created_at, legacy.reverted_at
                  )
            ) OR EXISTS (
                SELECT 1
                FROM deduplication_aliases legacy
                JOIN deduplication_contact_aliases typed ON typed.id = legacy.id
                WHERE legacy.record_type = 'contact'
                  AND ROW(
                      typed.organization_id, typed.alias_id, typed.canonical_id,
                      typed.merge_event_id, typed.created_at, typed.reverted_at
                  ) IS DISTINCT FROM ROW(
                      legacy.organization_id, legacy.alias_id, legacy.canonical_id,
                      legacy.merge_event_id, legacy.created_at, legacy.reverted_at
                  )
            ) OR EXISTS (
                SELECT 1 FROM deduplication_aliases legacy
                JOIN deduplication_contact_aliases typed ON typed.id = legacy.id
                WHERE legacy.record_type = 'account'
            ) OR EXISTS (
                SELECT 1 FROM deduplication_aliases legacy
                JOIN deduplication_account_aliases typed ON typed.id = legacy.id
                WHERE legacy.record_type = 'contact'
            ) THEN
                RAISE EXCEPTION 'legacy deduplication alias conflicts with typed data';
            END IF;
            IF EXISTS (
                SELECT related_event_id
                FROM deduplication_events
                WHERE action = 'revert' AND related_event_id IS NOT NULL
                GROUP BY related_event_id
                HAVING count(*) > 1
            ) THEN
                RAISE EXCEPTION 'legacy merge event has multiple revert events';
            END IF;

            INSERT INTO deduplication_account_aliases (
                id, organization_id, alias_id, canonical_id, merge_event_id,
                created_at, reverted_at, reverted_by_event_id
            )
            SELECT alias.id, alias.organization_id, alias.alias_id, alias.canonical_id,
                   alias.merge_event_id, alias.created_at, alias.reverted_at,
                   revert_event.id
            FROM deduplication_aliases alias
            LEFT JOIN deduplication_events revert_event
                ON revert_event.related_event_id = alias.merge_event_id
               AND revert_event.organization_id = alias.organization_id
               AND revert_event.action = 'revert'
            WHERE alias.record_type = 'account'
            ON CONFLICT (id) DO NOTHING;

            INSERT INTO deduplication_contact_aliases (
                id, organization_id, alias_id, canonical_id, merge_event_id,
                created_at, reverted_at, reverted_by_event_id
            )
            SELECT alias.id, alias.organization_id, alias.alias_id, alias.canonical_id,
                   alias.merge_event_id, alias.created_at, alias.reverted_at,
                   revert_event.id
            FROM deduplication_aliases alias
            LEFT JOIN deduplication_events revert_event
                ON revert_event.related_event_id = alias.merge_event_id
               AND revert_event.organization_id = alias.organization_id
               AND revert_event.action = 'revert'
            WHERE alias.record_type = 'contact'
            ON CONFLICT (id) DO NOTHING;
        END $$;
        """
    )


def _ensure_attribution_relationships() -> None:
    _execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM interactions interaction
                LEFT JOIN accounts account ON account.id = interaction.account_id
                WHERE account.id IS NULL
                   OR account.organization_id <> interaction.organization_id
            ) THEN
                RAISE EXCEPTION 'interaction has an orphaned or cross-tenant account';
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conrelid = 'interactions'::regclass
                  AND contype = 'f'
                  AND confrelid = 'accounts'::regclass
                  AND conkey = ARRAY[
                      (
                          SELECT attnum FROM pg_attribute
                          WHERE attrelid = 'interactions'::regclass
                            AND attname = 'organization_id'
                      ),
                      (
                          SELECT attnum FROM pg_attribute
                          WHERE attrelid = 'interactions'::regclass
                            AND attname = 'account_id'
                      )
                  ]
            ) THEN
                ALTER TABLE interactions
                    ADD CONSTRAINT fk_interactions_org_account
                    FOREIGN KEY (organization_id, account_id)
                    REFERENCES accounts(organization_id, id);
            END IF;
            IF EXISTS (
                SELECT 1
                FROM opportunities opportunity
                LEFT JOIN accounts account ON account.id = opportunity.account_id
                WHERE account.id IS NULL
                   OR account.organization_id <> opportunity.organization_id
            ) THEN
                RAISE EXCEPTION 'opportunity has an orphaned or cross-tenant account';
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conrelid = 'opportunities'::regclass
                  AND contype = 'f'
                  AND confrelid = 'accounts'::regclass
                  AND conkey = ARRAY[
                      (
                          SELECT attnum FROM pg_attribute
                          WHERE attrelid = 'opportunities'::regclass
                            AND attname = 'organization_id'
                      ),
                      (
                          SELECT attnum FROM pg_attribute
                          WHERE attrelid = 'opportunities'::regclass
                            AND attname = 'account_id'
                      )
                  ]
            ) THEN
                ALTER TABLE opportunities
                    ADD CONSTRAINT fk_opportunities_org_account
                    FOREIGN KEY (organization_id, account_id)
                    REFERENCES accounts(organization_id, id);
            END IF;
        END $$;
        """
    )


def upgrade() -> None:
    _ensure_prerequisites()
    _create_typed_candidate_tables()
    _copy_legacy_candidates()
    _reconcile_events()
    _create_typed_alias_tables()
    _copy_legacy_aliases()
    _ensure_attribution_relationships()


def downgrade() -> None:
    # The repaired shape is what the existing e4f6a8c0d2b5 source already declares.
    pass
