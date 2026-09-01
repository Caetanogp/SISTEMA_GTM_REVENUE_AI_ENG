"""Add typed deduplication persistence and optional contact phone."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b7c9d1e2f304"
down_revision: str | None = "9a4e2c6d7f80"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _candidate_columns() -> list[sa.Column[object]]:
    return [
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("scan_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("left_id", sa.Uuid(), nullable=False),
        sa.Column("right_id", sa.Uuid(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("reasons", postgresql.JSONB(), nullable=False),
        sa.Column("policy_version", sa.String(64), nullable=False),
        sa.Column("left_fingerprint", sa.String(64), nullable=False),
        sa.Column("right_fingerprint", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
    ]


def upgrade() -> None:
    op.add_column("contacts", sa.Column("phone", sa.String(length=16), nullable=True))
    op.add_column("ingestion_items", sa.Column("phone", sa.String(length=16), nullable=True))
    op.create_unique_constraint("uq_accounts_org_id", "accounts", ["organization_id", "id"])
    op.create_unique_constraint("uq_contacts_org_id", "contacts", ["organization_id", "id"])
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
    for table, record_table, unique_name in (
        ("deduplication_account_candidates", "accounts", "uq_dedupe_account_candidate_pair"),
        ("deduplication_contact_candidates", "contacts", "uq_dedupe_contact_candidate_pair"),
    ):
        op.create_table(
            table,
            *_candidate_columns(),
            sa.ForeignKeyConstraint(["scan_id"], ["deduplication_scans.id"]),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
            sa.ForeignKeyConstraint(
                ["organization_id", "left_id"],
                [f"{record_table}.organization_id", f"{record_table}.id"],
            ),
            sa.ForeignKeyConstraint(
                ["organization_id", "right_id"],
                [f"{record_table}.organization_id", f"{record_table}.id"],
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("scan_id", "left_id", "right_id", name=unique_name),
        )
        prefix = "account" if record_table == "accounts" else "contact"
        op.create_index(f"ix_dedupe_{prefix}_candidates_scan", table, ["scan_id"])
        op.create_index(f"ix_dedupe_{prefix}_candidates_org", table, ["organization_id"])

    op.create_table(
        "deduplication_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("account_candidate_id", sa.Uuid(), nullable=True),
        sa.Column("contact_candidate_id", sa.Uuid(), nullable=True),
        sa.Column("related_event_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["account_candidate_id"], ["deduplication_account_candidates.id"]),
        sa.ForeignKeyConstraint(["contact_candidate_id"], ["deduplication_contact_candidates.id"]),
        sa.ForeignKeyConstraint(["related_event_id"], ["deduplication_events.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "idempotency_key", name="uq_dedupe_events_org_key"),
        sa.CheckConstraint(
            "(account_candidate_id IS NULL) OR (contact_candidate_id IS NULL)",
            name="ck_dedupe_event_one_candidate",
        ),
    )
    op.create_index("ix_dedupe_events_org", "deduplication_events", ["organization_id"])
    for table, record_table, unique_name in (
        ("deduplication_account_aliases", "accounts", "uq_dedupe_account_alias_source"),
        ("deduplication_contact_aliases", "contacts", "uq_dedupe_contact_alias_source"),
    ):
        op.create_table(
            table,
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("organization_id", sa.Uuid(), nullable=False),
            sa.Column("alias_id", sa.Uuid(), nullable=False),
            sa.Column("canonical_id", sa.Uuid(), nullable=False),
            sa.Column("merge_event_id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("reverted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("reverted_by_event_id", sa.Uuid(), nullable=True),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
            sa.ForeignKeyConstraint(
                ["organization_id", "alias_id"],
                [f"{record_table}.organization_id", f"{record_table}.id"],
            ),
            sa.ForeignKeyConstraint(
                ["organization_id", "canonical_id"],
                [f"{record_table}.organization_id", f"{record_table}.id"],
            ),
            sa.ForeignKeyConstraint(["merge_event_id"], ["deduplication_events.id"]),
            sa.ForeignKeyConstraint(["reverted_by_event_id"], ["deduplication_events.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        prefix = "account" if record_table == "accounts" else "contact"
        op.create_index(f"ix_dedupe_{prefix}_aliases_org", table, ["organization_id"])
        op.create_index(
            unique_name,
            table,
            ["organization_id", "alias_id"],
            unique=True,
            postgresql_where=sa.text("reverted_at IS NULL"),
        )


def downgrade() -> None:
    for table, prefix in (
        ("deduplication_contact_aliases", "contact"),
        ("deduplication_account_aliases", "account"),
    ):
        op.drop_index(f"ix_dedupe_{prefix}_aliases_org", table_name=table)
        op.drop_table(table)
    op.drop_index("ix_dedupe_events_org", table_name="deduplication_events")
    op.drop_table("deduplication_events")
    for table, prefix in (
        ("deduplication_contact_candidates", "contact"),
        ("deduplication_account_candidates", "account"),
    ):
        op.drop_index(f"ix_dedupe_{prefix}_candidates_org", table_name=table)
        op.drop_index(f"ix_dedupe_{prefix}_candidates_scan", table_name=table)
        op.drop_table(table)
    op.drop_index("ix_dedupe_scans_org", table_name="deduplication_scans")
    op.drop_table("deduplication_scans")
    op.drop_constraint("uq_contacts_org_id", "contacts", type_="unique")
    op.drop_constraint("uq_accounts_org_id", "accounts", type_="unique")
    op.drop_column("contacts", "phone")
    op.drop_column("ingestion_items", "phone")
