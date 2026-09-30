"""Add append-only knowledge processing events.

Revision ID: e9f0a1b2c3d4
Revises: d8e9f0a1b2c3
Create Date: 2026-09-30 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e9f0a1b2c3d4"
down_revision: str | None = "d8e9f0a1b2c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "knowledge_processing_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("corpus_id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("delivery_id", sa.String(length=128), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("retryable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("failure_code", sa.String(length=128), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("attempt >= 1", name="ck_knowledge_processing_events_attempt"),
        sa.CheckConstraint(
            "event_type IN ('started', 'retry_scheduled', 'succeeded', 'failed', "
            "'duplicate_ignored')",
            name="ck_knowledge_processing_events_type",
        ),
        sa.ForeignKeyConstraint(["corpus_id"], ["knowledge_corpora.id"]),
        sa.ForeignKeyConstraint(["version_id"], ["knowledge_document_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "delivery_id",
            "attempt",
            "event_type",
            name="uq_knowledge_processing_events_delivery",
        ),
    )
    op.create_index(
        "ix_knowledge_processing_events_corpus", "knowledge_processing_events", ["corpus_id"]
    )
    op.create_index(
        "ix_knowledge_processing_events_version", "knowledge_processing_events", ["version_id"]
    )
    op.create_index(
        "ix_knowledge_processing_events_history",
        "knowledge_processing_events",
        ["corpus_id", "occurred_at", "id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_knowledge_processing_events_history", table_name="knowledge_processing_events"
    )
    op.drop_index(
        "ix_knowledge_processing_events_version", table_name="knowledge_processing_events"
    )
    op.drop_index("ix_knowledge_processing_events_corpus", table_name="knowledge_processing_events")
    op.drop_table("knowledge_processing_events")
