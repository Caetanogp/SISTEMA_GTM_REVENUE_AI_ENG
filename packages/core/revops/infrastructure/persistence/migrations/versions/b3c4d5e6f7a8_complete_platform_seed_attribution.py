"""Complete safe platform-seed attribution projections.

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b3c4d5e6f7a8"
down_revision: str | None = "a2b3c4d5e6f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _block_seeded_downgrade() -> None:
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


def upgrade() -> None:
    op.alter_column(
        "knowledge_document_versions", "requested_by", existing_type=sa.Uuid(), nullable=True
    )
    op.alter_column("knowledge_revision_activations", "scope", nullable=False)
    op.create_index(
        "ix_knowledge_document_versions_organization_id",
        "knowledge_document_versions",
        ["organization_id"],
    )
    op.create_index(
        "ix_knowledge_document_versions_requested_by_system",
        "knowledge_document_versions",
        ["requested_by_system"],
    )
    op.create_index(
        "ix_knowledge_revisions_organization_id", "knowledge_revisions", ["organization_id"]
    )
    op.create_index(
        "ix_knowledge_revisions_activated_by_system",
        "knowledge_revisions",
        ["activated_by_system"],
    )
    op.create_index(
        "ix_knowledge_revision_activations_organization_id",
        "knowledge_revision_activations",
        ["organization_id"],
    )
    op.create_index(
        "ix_knowledge_revision_activations_activated_by_system",
        "knowledge_revision_activations",
        ["activated_by_system"],
    )


def downgrade() -> None:
    _block_seeded_downgrade()
    op.drop_index(
        "ix_knowledge_revision_activations_activated_by_system",
        table_name="knowledge_revision_activations",
    )
    op.drop_index(
        "ix_knowledge_revision_activations_organization_id",
        table_name="knowledge_revision_activations",
    )
    op.drop_index("ix_knowledge_revisions_activated_by_system", table_name="knowledge_revisions")
    op.drop_index("ix_knowledge_revisions_organization_id", table_name="knowledge_revisions")
    op.drop_index(
        "ix_knowledge_document_versions_requested_by_system",
        table_name="knowledge_document_versions",
    )
    op.drop_index(
        "ix_knowledge_document_versions_organization_id",
        table_name="knowledge_document_versions",
    )
    op.alter_column("knowledge_revision_activations", "scope", nullable=True)
    op.alter_column(
        "knowledge_document_versions", "requested_by", existing_type=sa.Uuid(), nullable=False
    )
