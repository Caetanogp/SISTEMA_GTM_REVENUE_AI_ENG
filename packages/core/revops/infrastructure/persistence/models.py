"""SQLAlchemy declarative models mapping domain entities and the audit trail to tables.

This is deliberately a bootstrap skeleton, not the real model set - only `Base` is defined
here. The actual table classes (SPEC-001 tasks.md section 3) belong to the queue item that
implements them, following the domain entities in `domain/entities/` (the model follows the
domain, never the reverse - see docs/playbooks/db-migration.md).

See the persistence ADR for the decisions that constrain this file: agent_actions.run_id is
nullable until the graph phase exists to populate it; agent_runs/agent_actions/approvals get
no domain entity (the audit trail is an infrastructure concern, already abstracted by the
AuditTrail port); the LangGraph checkpoint tables are owned by AsyncPostgresSaver.setup(), not
by a migration in this file.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base for every table in this schema."""
