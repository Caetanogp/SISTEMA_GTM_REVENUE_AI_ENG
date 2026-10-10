"""Add immutable reply intelligence persistence tables.

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-10-10 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4d5e6f7a8b9"
down_revision: str | None = "b3c4d5e6f7a8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "replies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("contact_id", sa.Uuid(), nullable=True),
        sa.Column("submitted_by", sa.Uuid(), nullable=False),
        sa.Column("text", sa.String(length=8_000), nullable=False),
        sa.Column("language", sa.String(length=2), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "account_id"], ["accounts.organization_id", "accounts.id"]
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "contact_id"], ["contacts.organization_id", "contacts.id"]
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["submitted_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "idempotency_key", name="uq_replies_org_idempotency"
        ),
        sa.UniqueConstraint("organization_id", "id", name="uq_replies_org_id"),
    )
    op.create_index(op.f("ix_replies_organization_id"), "replies", ["organization_id"])
    op.create_index(op.f("ix_replies_account_id"), "replies", ["account_id"])
    op.create_index(op.f("ix_replies_contact_id"), "replies", ["contact_id"])
    op.create_index(op.f("ix_replies_submitted_by"), "replies", ["submitted_by"])
    op.create_index("ix_replies_organization_account", "replies", ["organization_id", "account_id"])

    op.create_table(
        "reply_classification_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("reply_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["organization_id", "reply_id"], ["replies.organization_id", "replies.id"]
        ),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reply_id", name="uq_reply_classification_requests_reply"),
        sa.UniqueConstraint("run_id", name="uq_reply_classification_requests_run"),
    )
    op.create_index(
        op.f("ix_reply_classification_requests_organization_id"),
        "reply_classification_requests",
        ["organization_id"],
    )
    op.create_index(
        op.f("ix_reply_classification_requests_reply_id"),
        "reply_classification_requests",
        ["reply_id"],
    )
    op.create_index(
        op.f("ix_reply_classification_requests_run_id"),
        "reply_classification_requests",
        ["run_id"],
    )
    op.create_index(
        op.f("ix_reply_classification_requests_requested_by"),
        "reply_classification_requests",
        ["requested_by"],
    )

    op.create_table(
        "reply_feedback",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("corrected_category", sa.String(length=32), nullable=False),
        sa.Column("comment", sa.String(length=2_000), nullable=True),
        sa.Column("submitted_by", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"]),
        sa.ForeignKeyConstraint(["submitted_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "idempotency_key", name="uq_reply_feedback_org_idempotency"
        ),
    )
    op.create_index(
        op.f("ix_reply_feedback_organization_id"), "reply_feedback", ["organization_id"]
    )
    op.create_index(op.f("ix_reply_feedback_run_id"), "reply_feedback", ["run_id"])
    op.create_index(op.f("ix_reply_feedback_submitted_by"), "reply_feedback", ["submitted_by"])
    op.create_index(
        "ix_reply_feedback_organization_run", "reply_feedback", ["organization_id", "run_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_reply_feedback_organization_run", table_name="reply_feedback")
    op.drop_index(op.f("ix_reply_feedback_submitted_by"), table_name="reply_feedback")
    op.drop_index(op.f("ix_reply_feedback_run_id"), table_name="reply_feedback")
    op.drop_index(op.f("ix_reply_feedback_organization_id"), table_name="reply_feedback")
    op.drop_table("reply_feedback")
    op.drop_index(
        op.f("ix_reply_classification_requests_requested_by"),
        table_name="reply_classification_requests",
    )
    op.drop_index(
        op.f("ix_reply_classification_requests_run_id"),
        table_name="reply_classification_requests",
    )
    op.drop_index(
        op.f("ix_reply_classification_requests_reply_id"),
        table_name="reply_classification_requests",
    )
    op.drop_index(
        op.f("ix_reply_classification_requests_organization_id"),
        table_name="reply_classification_requests",
    )
    op.drop_table("reply_classification_requests")
    op.drop_index("ix_replies_organization_account", table_name="replies")
    op.drop_index(op.f("ix_replies_submitted_by"), table_name="replies")
    op.drop_index(op.f("ix_replies_contact_id"), table_name="replies")
    op.drop_index(op.f("ix_replies_account_id"), table_name="replies")
    op.drop_index(op.f("ix_replies_organization_id"), table_name="replies")
    op.drop_table("replies")
