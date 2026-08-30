"""add langgraph runtime tables and tighten action idempotency

Revision ID: 6d7c8e9f0a11
Revises: cfdf788798d3
Create Date: 2026-08-30 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "6d7c8e9f0a11"
down_revision: str | None = "cfdf788798d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LEGACY_GRAPH_VERSION = "legacy"
_LEGACY_PROMPT_VERSION = "legacy"
_LEGACY_REQUEST_TEXT = "legacy/unattributed"


def _backfill_orphan_actions() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT id, organization_id, actor_id, occurred_at
            FROM agent_actions
            WHERE run_id IS NULL
            ORDER BY occurred_at, id
            """
        )
    ).mappings()
    for row in rows:
        run_id = uuid4()
        bind.execute(
            sa.text(
                """
                INSERT INTO agent_runs (
                    id,
                    organization_id,
                    requested_by,
                    request_text,
                    graph_version,
                    prompt_version,
                    model_config_json,
                    latency_ms,
                    token_cost_usd,
                    status,
                    error,
                    started_at,
                    completed_at
                ) VALUES (
                    :id,
                    :organization_id,
                    :requested_by,
                    :request_text,
                    :graph_version,
                    :prompt_version,
                    CAST(:model_config_json AS JSONB),
                    :latency_ms,
                    :token_cost_usd,
                    :status,
                    :error,
                    :started_at,
                    :completed_at
                )
                """
            ),
            {
                "id": run_id,
                "organization_id": row["organization_id"],
                "requested_by": row["actor_id"],
                "request_text": _LEGACY_REQUEST_TEXT,
                "graph_version": _LEGACY_GRAPH_VERSION,
                "prompt_version": _LEGACY_PROMPT_VERSION,
                "model_config_json": "{}",
                "latency_ms": None,  # nosec B105 - NULL migration value, not a credential
                "token_cost_usd": None,  # nosec B105 - NULL migration value, not a credential
                "status": "completed",
                "error": None,
                "started_at": row["occurred_at"],
                "completed_at": row["occurred_at"],
            },
        )
        bind.execute(
            sa.text(
                """
                UPDATE agent_actions
                SET run_id = :run_id
                WHERE id = :action_id
                """
            ),
            {"run_id": run_id, "action_id": row["id"]},
        )
        bind.execute(
            sa.text(
                """
                INSERT INTO agent_run_events (
                    id,
                    run_id,
                    organization_id,
                    event_type,
                    occurred_at,
                    graph_version,
                    prompt_version,
                    model_config_json,
                    latency_ms,
                    input_tokens,
                    output_tokens,
                    token_cost_usd,
                    error,
                    event_metadata
                ) VALUES (
                    :id,
                    :run_id,
                    :organization_id,
                    :event_type,
                    :occurred_at,
                    :graph_version,
                    :prompt_version,
                    CAST(:model_config_json AS JSONB),
                    :latency_ms,
                    :input_tokens,
                    :output_tokens,
                    :token_cost_usd,
                    :error,
                    CAST(:event_metadata AS JSONB)
                )
                """
            ),
            {
                "id": uuid4(),
                "run_id": run_id,
                "organization_id": row["organization_id"],
                "event_type": "legacy_backfill",
                "occurred_at": row["occurred_at"],
                "graph_version": _LEGACY_GRAPH_VERSION,
                "prompt_version": _LEGACY_PROMPT_VERSION,
                "model_config_json": "{}",
                "latency_ms": 0,
                "input_tokens": None,
                "output_tokens": None,
                "token_cost_usd": None,  # nosec B105 - NULL migration value, not a credential
                "error": None,
                "event_metadata": "{}",
            },
        )


def upgrade() -> None:
    op.add_column(
        "agent_runs",
        sa.Column(
            "requested_by",
            sa.Uuid(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
    )
    op.add_column(
        "agent_runs",
        sa.Column(
            "request_text",
            sa.String(length=2000),
            nullable=False,
            server_default=sa.text(f"'{_LEGACY_REQUEST_TEXT}'"),
        ),
    )
    op.alter_column(
        "agent_runs",
        "latency_ms",
        existing_type=sa.Integer(),
        nullable=True,
    )
    op.alter_column(
        "agent_runs",
        "token_cost_usd",
        existing_type=sa.Numeric(precision=10, scale=4),
        nullable=True,
    )
    op.create_table(
        "agent_run_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("graph_version", sa.String(length=64), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("model_config_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("token_cost_usd", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("error", sa.String(length=2000), nullable=True),
        sa.Column("event_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_agent_run_events_organization_id"),
        "agent_run_events",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_run_events_run_id"),
        "agent_run_events",
        ["run_id"],
        unique=False,
    )
    op.create_unique_constraint("uq_approvals_action_id", "approvals", ["action_id"])

    _backfill_orphan_actions()

    op.alter_column(
        "agent_actions",
        "run_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    legacy_run_ids = (
        bind.execute(
            sa.text(
                """
            SELECT id
            FROM agent_runs
            WHERE request_text = :request_text
              AND graph_version = :graph_version
              AND prompt_version = :prompt_version
            """
            ),
            {
                "request_text": _LEGACY_REQUEST_TEXT,
                "graph_version": _LEGACY_GRAPH_VERSION,
                "prompt_version": _LEGACY_PROMPT_VERSION,
            },
        )
        .scalars()
        .all()
    )

    for run_id in legacy_run_ids:
        bind.execute(
            sa.text("UPDATE agent_actions SET run_id = NULL WHERE run_id = :run_id"),
            {"run_id": run_id},
        )
        bind.execute(
            sa.text("DELETE FROM agent_run_events WHERE run_id = :run_id"),
            {"run_id": run_id},
        )
        bind.execute(
            sa.text("DELETE FROM agent_runs WHERE id = :run_id"),
            {"run_id": run_id},
        )

    op.drop_constraint("uq_approvals_action_id", "approvals", type_="unique")
    op.drop_index(op.f("ix_agent_run_events_run_id"), table_name="agent_run_events")
    op.drop_index(op.f("ix_agent_run_events_organization_id"), table_name="agent_run_events")
    op.drop_table("agent_run_events")
    op.alter_column(
        "agent_actions",
        "run_id",
        existing_type=sa.Uuid(),
        nullable=True,
    )
    op.execute("UPDATE agent_runs SET latency_ms = COALESCE(latency_ms, 0)")
    op.execute("UPDATE agent_runs SET token_cost_usd = COALESCE(token_cost_usd, 0)")
    op.alter_column(
        "agent_runs",
        "token_cost_usd",
        existing_type=sa.Numeric(precision=10, scale=4),
        nullable=False,
    )
    op.alter_column(
        "agent_runs",
        "latency_ms",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.drop_column("agent_runs", "request_text")
    op.drop_column("agent_runs", "requested_by")
