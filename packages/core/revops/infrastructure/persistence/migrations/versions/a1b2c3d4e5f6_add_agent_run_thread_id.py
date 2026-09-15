"""Add the explicit LangGraph thread identity to agent runs."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "f6a8c0d2b5e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("agent_runs", sa.Column("thread_id", sa.String(length=128), nullable=True))
    op.execute(sa.text("UPDATE agent_runs SET thread_id = id::text WHERE thread_id IS NULL"))
    op.alter_column("agent_runs", "thread_id", existing_type=sa.String(length=128), nullable=False)
    op.create_unique_constraint("uq_agent_runs_thread_id", "agent_runs", ["thread_id"])


def downgrade() -> None:
    op.drop_constraint("uq_agent_runs_thread_id", "agent_runs", type_="unique")
    op.drop_column("agent_runs", "thread_id")
