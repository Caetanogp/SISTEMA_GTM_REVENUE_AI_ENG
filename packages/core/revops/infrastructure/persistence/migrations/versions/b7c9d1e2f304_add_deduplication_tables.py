"""add deduplication persistence tables"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b7c9d1e2f304"
down_revision: str | None = "9a4e2c6d7f80"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("contacts", sa.Column("phone", sa.String(length=16), nullable=True))
    op.create_table(
        "deduplication_scans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("record_types", postgresql.JSONB(), nullable=False),
        sa.Column("policy_version", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "idempotency_key", name="uq_dedupe_scans_org_key"),
    )
    op.create_index("ix_dedupe_scans_org", "deduplication_scans", ["organization_id"])
    op.create_table(
        "deduplication_candidates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("scan_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("record_type", sa.String(16), nullable=False),
        sa.Column("left_id", sa.Uuid(), nullable=False),
        sa.Column("right_id", sa.Uuid(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("reasons", postgresql.JSONB(), nullable=False),
        sa.Column("policy_version", sa.String(64), nullable=False),
        sa.Column("left_fingerprint", sa.String(64), nullable=False),
        sa.Column("right_fingerprint", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(["scan_id"], ["deduplication_scans.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scan_id", "left_id", "right_id", name="uq_dedupe_candidate_pair"),
    )
    op.create_index("ix_dedupe_candidates_scan", "deduplication_candidates", ["scan_id"])
    op.create_index("ix_dedupe_candidates_org", "deduplication_candidates", ["organization_id"])
    op.create_table(
        "deduplication_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["candidate_id"], ["deduplication_candidates.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "idempotency_key", name="uq_dedupe_events_org_key"),
    )
    op.create_index("ix_dedupe_events_org", "deduplication_events", ["organization_id"])
    op.create_table(
        "deduplication_aliases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("record_type", sa.String(16), nullable=False),
        sa.Column("alias_id", sa.Uuid(), nullable=False),
        sa.Column("canonical_id", sa.Uuid(), nullable=False),
        sa.Column("merge_event_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reverted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["merge_event_id"], ["deduplication_events.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "alias_id", name="uq_dedupe_alias_source"),
    )
    op.create_index("ix_dedupe_aliases_org", "deduplication_aliases", ["organization_id"])


def downgrade() -> None:
    op.drop_index("ix_dedupe_aliases_org", table_name="deduplication_aliases")
    op.drop_table("deduplication_aliases")
    op.drop_index("ix_dedupe_events_org", table_name="deduplication_events")
    op.drop_table("deduplication_events")
    op.drop_index("ix_dedupe_candidates_org", table_name="deduplication_candidates")
    op.drop_index("ix_dedupe_candidates_scan", table_name="deduplication_candidates")
    op.drop_table("deduplication_candidates")
    op.drop_index("ix_dedupe_scans_org", table_name="deduplication_scans")
    op.drop_table("deduplication_scans")
    op.drop_column("contacts", "phone")
