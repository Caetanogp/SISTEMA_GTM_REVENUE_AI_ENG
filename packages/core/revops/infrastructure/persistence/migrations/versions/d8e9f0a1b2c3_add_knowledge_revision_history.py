"""Add immutable revision membership and activation history.

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
Create Date: 2026-09-28 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d8e9f0a1b2c3"
down_revision: str | None = "c7d8e9f0a1b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "knowledge_revision_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("corpus_id", sa.Uuid(), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("document_key", sa.String(length=200), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["corpus_id"], ["knowledge_corpora.id"]),
        sa.ForeignKeyConstraint(["revision_id"], ["knowledge_revisions.id"]),
        sa.ForeignKeyConstraint(["version_id"], ["knowledge_document_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "revision_id", "document_key", name="uq_knowledge_revision_entry_document"
        ),
        sa.UniqueConstraint(
            "revision_id", "document_key", "version_id", name="uq_knowledge_revision_entry_version"
        ),
    )
    op.create_index(
        "ix_knowledge_revision_entries_corpus", "knowledge_revision_entries", ["corpus_id"]
    )
    op.create_index(
        "ix_knowledge_revision_entries_revision_id", "knowledge_revision_entries", ["revision_id"]
    )
    op.create_index(
        "ix_knowledge_revision_entries_version_id", "knowledge_revision_entries", ["version_id"]
    )

    op.create_table(
        "knowledge_revision_activations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("corpus_id", sa.Uuid(), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("target_version_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("activated_by", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "action IN ('publication', 'historical_activation')",
            name="ck_knowledge_revision_activations_action",
        ),
        sa.ForeignKeyConstraint(["activated_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["corpus_id"], ["knowledge_corpora.id"]),
        sa.ForeignKeyConstraint(["revision_id"], ["knowledge_revisions.id"]),
        sa.ForeignKeyConstraint(["target_version_id"], ["knowledge_document_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "corpus_id", "idempotency_key", name="uq_knowledge_revision_activation_idempotency"
        ),
    )
    op.create_index(
        "ix_knowledge_revision_activations_corpus_id",
        "knowledge_revision_activations",
        ["corpus_id"],
    )
    op.create_index(
        "ix_knowledge_revision_activations_revision_id",
        "knowledge_revision_activations",
        ["revision_id"],
    )
    op.create_index(
        "ix_knowledge_revision_activations_target_version_id",
        "knowledge_revision_activations",
        ["target_version_id"],
    )
    op.create_index(
        "ix_knowledge_revision_activations_history",
        "knowledge_revision_activations",
        ["corpus_id", "created_at", "id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_knowledge_revision_activations_history", table_name="knowledge_revision_activations"
    )
    op.drop_index(
        "ix_knowledge_revision_activations_target_version_id",
        table_name="knowledge_revision_activations",
    )
    op.drop_index(
        "ix_knowledge_revision_activations_revision_id", table_name="knowledge_revision_activations"
    )
    op.drop_index(
        "ix_knowledge_revision_activations_corpus_id", table_name="knowledge_revision_activations"
    )
    op.drop_table("knowledge_revision_activations")
    op.drop_index(
        "ix_knowledge_revision_entries_version_id", table_name="knowledge_revision_entries"
    )
    op.drop_index(
        "ix_knowledge_revision_entries_revision_id", table_name="knowledge_revision_entries"
    )
    op.drop_index("ix_knowledge_revision_entries_corpus", table_name="knowledge_revision_entries")
    op.drop_table("knowledge_revision_entries")
