"""Add CRM attribution schema.

Revision ID: e4f6a8c0d2b5
Revises: b7c9d1e2f304
Create Date: 2026-09-13 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e4f6a8c0d2b5"
down_revision: str | None = "b7c9d1e2f304"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "campaigns",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("channel", sa.String(length=128), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id", name="uq_campaigns_org_id"),
    )
    op.create_index("ix_campaigns_organization_id", "campaigns", ["organization_id"])

    op.create_table(
        "touchpoints",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("contact_id", sa.Uuid(), nullable=True),
        sa.Column("campaign_id", sa.Uuid(), nullable=True),
        sa.Column("type", sa.String(length=128), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["organization_id", "account_id"], ["accounts.organization_id", "accounts.id"]
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "contact_id"], ["contacts.organization_id", "contacts.id"]
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "campaign_id"], ["campaigns.organization_id", "campaigns.id"]
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_touchpoints_organization_id", "touchpoints", ["organization_id"])
    op.create_index(
        "ix_touchpoints_org_account_occurred_at",
        "touchpoints",
        ["organization_id", "account_id", "occurred_at"],
    )
    op.create_index(
        "ix_touchpoints_org_campaign_occurred_at",
        "touchpoints",
        ["organization_id", "campaign_id", "occurred_at"],
    )

    op.add_column("interactions", sa.Column("contact_id", sa.Uuid(), nullable=True))
    op.add_column("interactions", sa.Column("content", sa.String(length=2000), nullable=True))
    op.create_foreign_key(
        "fk_interactions_org_contact",
        "interactions",
        "contacts",
        ["organization_id", "contact_id"],
        ["organization_id", "id"],
    )
    op.create_index(
        "ix_interactions_org_contact_occurred_at",
        "interactions",
        ["organization_id", "contact_id", "occurred_at"],
    )

    op.add_column("opportunities", sa.Column("status", sa.String(length=16), nullable=True))
    op.execute(sa.text("UPDATE opportunities SET status = 'open' WHERE status IS NULL"))
    op.alter_column("opportunities", "status", nullable=False)
    op.create_check_constraint(
        "ck_opportunities_status", "opportunities", "status IN ('open', 'won', 'lost')"
    )
    op.create_foreign_key(
        "fk_opportunities_org_account",
        "opportunities",
        "accounts",
        ["organization_id", "account_id"],
        ["organization_id", "id"],
    )
    op.create_index("ix_opportunities_org_status", "opportunities", ["organization_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_opportunities_org_status", table_name="opportunities")
    op.drop_constraint("fk_opportunities_org_account", "opportunities", type_="foreignkey")
    op.drop_constraint("ck_opportunities_status", "opportunities", type_="check")
    op.drop_column("opportunities", "status")

    op.drop_index("ix_interactions_org_contact_occurred_at", table_name="interactions")
    op.drop_constraint("fk_interactions_org_contact", "interactions", type_="foreignkey")
    op.drop_column("interactions", "content")
    op.drop_column("interactions", "contact_id")

    op.drop_index("ix_touchpoints_org_campaign_occurred_at", table_name="touchpoints")
    op.drop_index("ix_touchpoints_org_account_occurred_at", table_name="touchpoints")
    op.drop_index("ix_touchpoints_organization_id", table_name="touchpoints")
    op.drop_table("touchpoints")

    op.drop_index("ix_campaigns_organization_id", table_name="campaigns")
    op.drop_table("campaigns")
