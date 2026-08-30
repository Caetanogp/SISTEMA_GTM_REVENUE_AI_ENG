"""SQLAlchemy declarative models mapping domain entities and the audit trail to tables.

The model follows the domain, never the reverse (docs/playbooks/db-migration.md): every column
here matches a field already fixed in `domain/entities/*.py`. Value objects (`Score`, `RiskLevel`,
`EmailAddress`, `CompanyDomain`) persist as their primitive value — reidration into the value
object happens at the repository boundary (SPEC-001 tasks.md item 3), not here.

`agent_runs`, `agent_actions`, `approvals` are infrastructure tables with no domain entity — see
docs/decisions/ADR-0002-persistence-layer.md. `agent_actions.run_id` is nullable on purpose: there
is no real `agent_run` to reference until the graph phase exists (ADR-0002); tightening it to
`NOT NULL` is a deliberate future migration, not an oversight. All three audit tables are
append-only: no column carries `onupdate`, and no foreign key here uses `ondelete="CASCADE"`.

The LangGraph checkpoint tables are NOT declared here — they are owned by
`AsyncPostgresSaver.setup()` and deliberately excluded from this schema (see `migrations/env.py`'s
`include_name` filter and ADR-0002).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, ClassVar
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeEngine


class Base(DeclarativeBase):
    """Shared declarative base for every table in this schema.

    `type_annotation_map` makes every `Mapped[datetime]` column `TIMESTAMPTZ` (`DateTime(timezone
    =True)`) instead of SQLAlchemy's naive-by-default `TIMESTAMP WITHOUT TIME ZONE` - a project-wide
    convention applied once here, rather than repeated per column, so a future datetime column never
    has to remember it. Every timestamp elsewhere in this codebase is timezone-aware by convention
    (`Clock.now()`, the fakes in `tests/unit/application/test_ports.py`) - the schema now matches.
    Found live: SPEC-001 persistence Item 4's integration tests, which exist specifically to catch
    this kind of gap between the schema and the rest of the system.
    """

    type_annotation_map: ClassVar[dict[type, TypeEngine[Any]]] = {datetime: DateTime(timezone=True)}


class Organization(Base):
    """The multi-tenant boundary. Every other table is scoped to exactly one of these."""

    __tablename__ = "organizations"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    demo_mode: Mapped[bool] = mapped_column(default=True)


class User(Base):
    """An actor inside one organization."""

    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    email: Mapped[str] = mapped_column(String(320))
    role: Mapped[str] = mapped_column(String(64))


class Account(Base):
    """A company — the unit of prioritization. Deduplicated on its normalized domain per org."""

    __tablename__ = "accounts"
    __table_args__ = (UniqueConstraint("organization_id", "domain", name="uq_accounts_org_domain"),)

    id: Mapped[UUID] = mapped_column(primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    company_name: Mapped[str] = mapped_column(String(255))
    domain: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime]


class Contact(Base):
    """A person in an account's buying group. Deduplicated on normalized email per org."""

    __tablename__ = "contacts"
    __table_args__ = (UniqueConstraint("organization_id", "email", name="uq_contacts_org_email"),)

    id: Mapped[UUID] = mapped_column(primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id"))
    email: Mapped[str] = mapped_column(String(320))
    full_name: Mapped[str] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(255), default="")


class Opportunity(Base):
    """A pipeline deal tied to an account."""

    __tablename__ = "opportunities"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id"))
    stage: Mapped[str] = mapped_column(String(32))
    value: Mapped[Decimal] = mapped_column(Numeric(14, 2))


class Interaction(Base):
    """A record of engagement with an account — the recency/engagement signal source."""

    __tablename__ = "interactions"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id"))
    channel: Mapped[str] = mapped_column(String(64))
    occurred_at: Mapped[datetime]
    summary: Mapped[str] = mapped_column(String(2000), default="")


class Task(Base):
    """A next action for a user, with a small state machine (see `domain/entities/task.py`)."""

    __tablename__ = "tasks"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id"))
    title: Mapped[str] = mapped_column(String(255))
    due_at: Mapped[datetime]
    status: Mapped[str] = mapped_column(String(32), default="open")


class AgentRun(Base):
    """One agent invocation. Infrastructure-only — no domain entity (ADR-0002).

    Append-only: no column here carries `onupdate`, and the foreign key uses no cascade delete.
    Columns cover acceptance criterion 9 (`graph_version`, `prompt_version`, model config, latency,
    token cost) and AGENTS.md's "a failure must be reproducible from the row alone" (`status`,
    `error`).
    """

    __tablename__ = "agent_runs"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    graph_version: Mapped[str] = mapped_column(String(64))
    prompt_version: Mapped[str] = mapped_column(String(64))
    model_config_json: Mapped[dict[str, object]] = mapped_column(JSONB)
    latency_ms: Mapped[int]
    token_cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 4))
    status: Mapped[str] = mapped_column(String(32))
    error: Mapped[str | None] = mapped_column(String(2000), default=None)
    started_at: Mapped[datetime]
    completed_at: Mapped[datetime | None] = mapped_column(default=None)


class AgentAction(Base):
    """Append-only record of every agent action, including failures and rejections.

    Backs the `AuditTrail` port (`application/ports.py`): `action`, `payload`, `outcome` and
    `occurred_at` mirror `AuditTrail.record()`'s parameters exactly. `run_id` is nullable —
    ADR-0002, there is no real `agent_run` to reference until the graph phase exists. `approved_by`
    and `executed_at` cover acceptance criterion 4. No `onupdate` on any column, no cascade delete
    on any foreign key.
    """

    __tablename__ = "agent_actions"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    run_id: Mapped[UUID | None] = mapped_column(ForeignKey("agent_runs.id"), nullable=True)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, object]] = mapped_column(JSONB)
    outcome: Mapped[str] = mapped_column(String(32))
    occurred_at: Mapped[datetime]
    approved_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), default=None)
    executed_at: Mapped[datetime | None] = mapped_column(default=None)


class Approval(Base):
    """The human decision (approve / edit / reject) on one `agent_action`.

    Acceptance criterion 5: an edited payload is what is stored here, alongside the decision.
    Append-only: no `onupdate` on any column, no cascade delete on any foreign key.
    """

    __tablename__ = "approvals"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    action_id: Mapped[UUID] = mapped_column(ForeignKey("agent_actions.id"))
    decision: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict[str, object]] = mapped_column(JSONB)
    decided_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime]
