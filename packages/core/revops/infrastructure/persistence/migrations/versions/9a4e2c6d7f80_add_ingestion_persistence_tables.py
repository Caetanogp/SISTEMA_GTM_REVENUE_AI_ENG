"""add ingestion persistence tables

Revision ID: 9a4e2c6d7f80
Revises: 6d7c8e9f0a11
Create Date: 2026-08-30 20:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "9a4e2c6d7f80"
down_revision: str | None = "6d7c8e9f0a11"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ingestion_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("failure_code", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "idempotency_key", name="uq_ingestion_jobs_org_idempotency_key"
        ),
    )
    op.create_index(
        op.f("ix_ingestion_jobs_organization_id"), "ingestion_jobs", ["organization_id"]
    )
    op.create_table(
        "ingestion_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ingestion_job_id", sa.Uuid(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("company_name", sa.String(length=255), nullable=True),
        sa.Column("domain", sa.String(length=255), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("validation_codes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("account_outcome", sa.String(length=32), nullable=False),
        sa.Column("contact_outcome", sa.String(length=32), nullable=False),
        sa.Column("enrichment_outcome", sa.String(length=32), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=True),
        sa.Column("contact_id", sa.Uuid(), nullable=True),
        sa.Column("enrichment_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"]),
        sa.ForeignKeyConstraint(["ingestion_job_id"], ["ingestion_jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ingestion_job_id", "row_number", name="uq_ingestion_items_job_row"),
    )
    op.create_index(op.f("ix_ingestion_items_domain"), "ingestion_items", ["domain"])
    op.create_index(
        op.f("ix_ingestion_items_ingestion_job_id"), "ingestion_items", ["ingestion_job_id"]
    )
    op.create_table(
        "account_enrichments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ingestion_job_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.String(length=64), nullable=False),
        sa.Column("profile_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["ingestion_job_id"], ["ingestion_jobs.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "ingestion_job_id",
            "account_id",
            "provider",
            "schema_version",
            name="uq_account_enrichments_job_account_provider_schema",
        ),
    )
    op.create_index(
        op.f("ix_account_enrichments_account_id"), "account_enrichments", ["account_id"]
    )
    op.create_index(
        op.f("ix_account_enrichments_ingestion_job_id"), "account_enrichments", ["ingestion_job_id"]
    )
    op.create_index(
        op.f("ix_account_enrichments_organization_id"), "account_enrichments", ["organization_id"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_account_enrichments_organization_id"), table_name="account_enrichments")
    op.drop_index(op.f("ix_account_enrichments_ingestion_job_id"), table_name="account_enrichments")
    op.drop_index(op.f("ix_account_enrichments_account_id"), table_name="account_enrichments")
    op.drop_table("account_enrichments")
    op.drop_index(op.f("ix_ingestion_items_ingestion_job_id"), table_name="ingestion_items")
    op.drop_index(op.f("ix_ingestion_items_domain"), table_name="ingestion_items")
    op.drop_table("ingestion_items")
    op.drop_index(op.f("ix_ingestion_jobs_organization_id"), table_name="ingestion_jobs")
    op.drop_table("ingestion_jobs")
