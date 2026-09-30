"""Scope processing event idempotency to a corpus version."""

from collections.abc import Sequence

from alembic import op

revision: str = "f0a1b2c3d4e5"
down_revision: str | None = "e9f0a1b2c3d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_knowledge_processing_events_delivery",
        "knowledge_processing_events",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_knowledge_processing_events_identity",
        "knowledge_processing_events",
        ["corpus_id", "version_id", "delivery_id", "attempt", "event_type"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_knowledge_processing_events_identity",
        "knowledge_processing_events",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_knowledge_processing_events_delivery",
        "knowledge_processing_events",
        ["delivery_id", "attempt", "event_type"],
    )
