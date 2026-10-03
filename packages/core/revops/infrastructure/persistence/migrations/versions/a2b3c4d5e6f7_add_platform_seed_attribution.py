"""Add platform seed attribution and corpus integrity projections.

Revision ID: a2b3c4d5e6f7
Revises: f0a1b2c3d4e5
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a2b3c4d5e6f7"
down_revision: str | None = "f0a1b2c3d4e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SYSTEM_ACTOR = "928f8683-f542-550e-a13c-8e770ef19a57"


def _projection_columns(table: str) -> None:
    op.add_column(table, sa.Column("scope", sa.String(length=32), nullable=True))
    op.add_column(table, sa.Column("organization_id", sa.Uuid(), nullable=True))


def upgrade() -> None:
    op.add_column(
        "knowledge_document_versions", sa.Column("organization_id", sa.Uuid(), nullable=True)
    )
    op.add_column(
        "knowledge_document_versions", sa.Column("requested_by_system", sa.Uuid(), nullable=True)
    )
    op.add_column(
        "knowledge_document_versions", sa.Column("seed_revision", sa.Integer(), nullable=True)
    )
    _projection_columns("knowledge_revisions")
    op.add_column("knowledge_revisions", sa.Column("activated_by_system", sa.Uuid(), nullable=True))
    op.alter_column("knowledge_revisions", "activated_by", existing_type=sa.Uuid(), nullable=True)
    _projection_columns("knowledge_revision_activations")
    op.add_column(
        "knowledge_revision_activations", sa.Column("activated_by_system", sa.Uuid(), nullable=True)
    )
    op.alter_column(
        "knowledge_revision_activations", "activated_by", existing_type=sa.Uuid(), nullable=True
    )

    op.execute("""
        UPDATE knowledge_document_versions AS version
        SET organization_id = corpus.organization_id
        FROM knowledge_corpora AS corpus WHERE corpus.id = version.corpus_id;
        UPDATE knowledge_revisions AS revision
        SET scope = corpus.scope, organization_id = corpus.organization_id
        FROM knowledge_corpora AS corpus WHERE corpus.id = revision.corpus_id;
        UPDATE knowledge_revision_activations AS activation
        SET scope = corpus.scope, organization_id = corpus.organization_id
        FROM knowledge_corpora AS corpus WHERE corpus.id = activation.corpus_id;
    """)
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (
            SELECT 1 FROM knowledge_document_versions version
            JOIN knowledge_corpora corpus ON corpus.id = version.corpus_id
            LEFT JOIN users actor ON actor.id = version.requested_by
              AND actor.organization_id = corpus.organization_id
            WHERE corpus.scope = 'organization' AND actor.id IS NULL
          ) THEN RAISE EXCEPTION 'knowledge_attribution_backfill_invalid'; END IF;
        END $$;
    """)
    op.alter_column("knowledge_revisions", "scope", nullable=False)
    op.create_unique_constraint(
        "uq_knowledge_versions_document_seed_revision",
        "knowledge_document_versions",
        ["document_id", "seed_revision"],
    )
    op.create_index(
        "ix_knowledge_versions_seed_revision", "knowledge_document_versions", ["seed_revision"]
    )
    op.create_index(
        "ix_knowledge_revisions_scope_organization",
        "knowledge_revisions",
        ["scope", "organization_id"],
    )
    op.create_index(
        "ix_knowledge_revision_activations_scope_organization",
        "knowledge_revision_activations",
        ["scope", "organization_id"],
    )
    for table, user_actor, system_actor, revision_check in (
        (
            "knowledge_document_versions",
            "requested_by",
            "requested_by_system",
            "(scope = 'platform' AND seed_revision IS NOT NULL "
            "AND seed_revision > 0) OR (scope = 'organization' "
            "AND seed_revision IS NULL)",
        ),
        ("knowledge_revisions", "activated_by", "activated_by_system", "TRUE"),
        ("knowledge_revision_activations", "activated_by", "activated_by_system", "TRUE"),
    ):
        op.create_check_constraint(
            f"ck_{table}_actor_projection",
            table,
            f"({user_actor} IS NOT NULL AND {system_actor} IS NULL "
            "AND scope = 'organization' AND organization_id IS NOT NULL) OR "
            f"({user_actor} IS NULL AND {system_actor} = '{_SYSTEM_ACTOR}'::uuid "
            "AND scope = 'platform' AND organization_id IS NULL)",
        )
        op.create_check_constraint(f"ck_{table}_seed_revision", table, revision_check)
    op.execute("""
        CREATE FUNCTION knowledge_seed_projection_defaults() RETURNS trigger AS $$
        DECLARE corpus_scope text; corpus_organization uuid;
        BEGIN
          SELECT scope, organization_id INTO corpus_scope, corpus_organization
          FROM knowledge_corpora WHERE id = NEW.corpus_id;
          IF NEW.organization_id IS NULL AND corpus_organization IS NOT NULL THEN
            NEW.organization_id := corpus_organization;
          END IF;
          IF NEW.scope IS NULL THEN NEW.scope := corpus_scope; END IF;
          IF NEW.scope <> corpus_scope
            OR NEW.organization_id IS DISTINCT FROM corpus_organization THEN
            RAISE EXCEPTION 'knowledge_corpus_projection_conflict';
          END IF;
          RETURN NEW;
        END; $$ LANGUAGE plpgsql;
        CREATE TRIGGER knowledge_versions_projection_defaults
        BEFORE INSERT ON knowledge_document_versions
        FOR EACH ROW EXECUTE FUNCTION knowledge_seed_projection_defaults();
    """)


def downgrade() -> None:
    op.execute(
        "LOCK TABLE knowledge_document_versions, knowledge_revisions, "
        "knowledge_revision_activations IN ACCESS EXCLUSIVE MODE"
    )
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (
            SELECT 1 FROM knowledge_document_versions
            WHERE requested_by_system IS NOT NULL OR seed_revision IS NOT NULL
          )
             OR EXISTS (SELECT 1 FROM knowledge_revisions WHERE activated_by_system IS NOT NULL)
             OR EXISTS (
               SELECT 1 FROM knowledge_revision_activations
               WHERE activated_by_system IS NOT NULL
             )
          THEN RAISE EXCEPTION 'platform_seed_downgrade_blocked'; END IF;
        END $$;
    """)
    op.execute("DROP TRIGGER knowledge_versions_projection_defaults ON knowledge_document_versions")
    op.execute("DROP FUNCTION knowledge_seed_projection_defaults()")
    for table in (
        "knowledge_revision_activations",
        "knowledge_revisions",
        "knowledge_document_versions",
    ):
        op.drop_constraint(f"ck_{table}_actor_projection", table, type_="check")
        op.drop_constraint(f"ck_{table}_seed_revision", table, type_="check")
    op.drop_index(
        "ix_knowledge_revision_activations_scope_organization",
        table_name="knowledge_revision_activations",
    )
    op.drop_index("ix_knowledge_revisions_scope_organization", table_name="knowledge_revisions")
    op.drop_index("ix_knowledge_versions_seed_revision", table_name="knowledge_document_versions")
    op.drop_constraint(
        "uq_knowledge_versions_document_seed_revision",
        "knowledge_document_versions",
        type_="unique",
    )
    op.alter_column(
        "knowledge_revision_activations", "activated_by", existing_type=sa.Uuid(), nullable=False
    )
    op.drop_column("knowledge_revision_activations", "activated_by_system")
    op.drop_column("knowledge_revision_activations", "organization_id")
    op.drop_column("knowledge_revision_activations", "scope")
    op.alter_column("knowledge_revisions", "activated_by", existing_type=sa.Uuid(), nullable=False)
    op.drop_column("knowledge_revisions", "activated_by_system")
    op.drop_column("knowledge_revisions", "organization_id")
    op.drop_column("knowledge_revisions", "scope")
    op.drop_column("knowledge_document_versions", "seed_revision")
    op.drop_column("knowledge_document_versions", "requested_by_system")
    op.drop_column("knowledge_document_versions", "organization_id")
