"""SQLAlchemy adapters implementing `application/ports.py`'s repository Protocols.

Structural, not nominal: none of these classes import or inherit from `application.ports` (the
convention `tests/unit/application/test_ports.py` already establishes for every other fake).
`organization_id` is filtered inside every method here, never left to the caller to remember
(`spec.md`'s security considerations, `AGENTS.md`) - this is what proves acceptance criterion 10
in `tests/integration/test_persistence_repositories.py`.

Value objects (`CompanyDomain`) are reidrated here at the repository boundary, per
`docs/playbooks/db-migration.md` - the model stores the primitive, the domain entity holds the
value object.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from revops.application.dto import ApprovalDecisionType
from revops.application.ports import (
    AgentRunEventRecord,
    AgentRunRecord,
    ApprovalRecord,
    CanonicalResolver,
)
from revops.domain.entities.account import Account
from revops.domain.entities.deduplication import DeduplicationRecordType
from revops.domain.entities.interaction import Interaction
from revops.domain.entities.opportunity import Opportunity, OpportunityStage
from revops.domain.entities.task import Task, TaskStatus
from revops.domain.values.company_domain import CompanyDomain
from revops.infrastructure.persistence.models import Account as AccountModel
from revops.infrastructure.persistence.models import AccountDeduplicationAlias as AccountAliasModel
from revops.infrastructure.persistence.models import AgentAction as AgentActionModel
from revops.infrastructure.persistence.models import AgentRun as AgentRunModel
from revops.infrastructure.persistence.models import AgentRunEvent as AgentRunEventModel
from revops.infrastructure.persistence.models import Approval as ApprovalModel
from revops.infrastructure.persistence.models import Interaction as InteractionModel
from revops.infrastructure.persistence.models import Opportunity as OpportunityModel
from revops.infrastructure.persistence.models import Task as TaskModel

_OPEN_STAGE_VALUES = tuple(stage.value for stage in OpportunityStage if stage.is_open)


def _to_account(row: AccountModel) -> Account:
    return Account(
        id=row.id,
        organization_id=row.organization_id,
        company_name=row.company_name,
        domain=CompanyDomain(row.domain),
        created_at=row.created_at,
    )


def _to_interaction(row: InteractionModel) -> Interaction:
    return Interaction(
        id=row.id,
        organization_id=row.organization_id,
        account_id=row.account_id,
        channel=row.channel,
        occurred_at=row.occurred_at,
        summary=row.summary,
    )


def _to_opportunity(row: OpportunityModel) -> Opportunity:
    return Opportunity(
        id=row.id,
        organization_id=row.organization_id,
        account_id=row.account_id,
        stage=OpportunityStage(row.stage),
        value=row.value,
    )


def _to_task(row: TaskModel) -> Task:
    return Task(
        id=row.id,
        organization_id=row.organization_id,
        owner_id=row.owner_id,
        account_id=row.account_id,
        title=row.title,
        due_at=row.due_at,
        status=TaskStatus(row.status),
    )


class SqlAlchemyAccountRepository:
    """Read-only access to accounts and the signals `policies.prioritization` scores them on.

    No write method by design (`AccountRepository` port has none either) - accounts are seeded
    by data scripts, not written through this boundary.
    """

    def __init__(self, session: AsyncSession, canonical: CanonicalResolver | None = None) -> None:
        self._session = session
        self._canonical = canonical

    async def get(self, organization_id: UUID, account_id: UUID) -> Account:
        if self._canonical is not None:
            group = await self._canonical.resolve(
                organization_id, DeduplicationRecordType.ACCOUNT, account_id
            )
            if group is None:
                raise LookupError("account not found")
            account_id = group.canonical_id
        stmt = select(AccountModel).where(
            AccountModel.organization_id == organization_id, AccountModel.id == account_id
        )
        row = (await self._session.execute(stmt)).scalar_one()
        return _to_account(row)

    async def list_for_organization(self, organization_id: UUID) -> Sequence[Account]:
        stmt = select(AccountModel).where(
            AccountModel.organization_id == organization_id,
            ~select(AccountAliasModel.id)
            .where(
                AccountAliasModel.organization_id == organization_id,
                AccountAliasModel.alias_id == AccountModel.id,
                AccountAliasModel.reverted_at.is_(None),
            )
            .exists(),
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_to_account(row) for row in rows]

    async def list_interactions(
        self, organization_id: UUID, account_ids: Sequence[UUID] | UUID
    ) -> Sequence[Interaction]:
        ids = (account_ids,) if isinstance(account_ids, UUID) else account_ids
        stmt = select(InteractionModel).where(
            InteractionModel.organization_id == organization_id,
            InteractionModel.account_id.in_(ids),
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_to_interaction(row) for row in rows]

    async def list_open_opportunities(
        self, organization_id: UUID, account_ids: Sequence[UUID] | UUID
    ) -> Sequence[Opportunity]:
        ids = (account_ids,) if isinstance(account_ids, UUID) else account_ids
        stmt = select(OpportunityModel).where(
            OpportunityModel.organization_id == organization_id,
            OpportunityModel.account_id.in_(ids),
            OpportunityModel.stage.in_(_OPEN_STAGE_VALUES),
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_to_opportunity(row) for row in rows]


class SqlAlchemyTaskRepository:
    """Persistence for `Task`, the entity `create_task` writes and HITL approval acts on."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, task: Task) -> None:
        self._session.add(
            TaskModel(
                id=task.id,
                organization_id=task.organization_id,
                owner_id=task.owner_id,
                account_id=task.account_id,
                title=task.title,
                due_at=task.due_at,
                status=task.status.value,
            )
        )
        await self._session.flush()

    async def get(self, organization_id: UUID, task_id: UUID) -> Task:
        stmt = select(TaskModel).where(
            TaskModel.organization_id == organization_id, TaskModel.id == task_id
        )
        row = (await self._session.execute(stmt)).scalar_one()
        return _to_task(row)

    async def update(self, task: Task) -> None:
        stmt = select(TaskModel).where(
            TaskModel.organization_id == task.organization_id, TaskModel.id == task.id
        )
        row = (await self._session.execute(stmt)).scalar_one()
        row.owner_id = task.owner_id
        row.title = task.title
        row.due_at = task.due_at
        row.status = task.status.value
        await self._session.flush()


class SqlAlchemyAuditTrail:
    """Append-only writes to `agent_actions`, backing the `AuditTrail` port."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        *,
        action_id: UUID,
        run_id: UUID,
        organization_id: UUID,
        actor_id: UUID,
        action: str,
        payload: Mapping[str, object],
        outcome: str,
        occurred_at: datetime,
        approved_by: UUID | None,
        executed_at: datetime | None,
    ) -> None:
        self._session.add(
            AgentActionModel(
                id=action_id,
                run_id=run_id,
                organization_id=organization_id,
                actor_id=actor_id,
                action=action,
                payload=dict(payload),
                outcome=outcome,
                occurred_at=occurred_at,
                approved_by=approved_by,
                executed_at=executed_at,
            )
        )
        await self._session.flush()


class SqlAlchemyApprovalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_for_action(self, organization_id: UUID, action_id: UUID) -> ApprovalRecord | None:
        stmt = select(ApprovalModel).where(
            ApprovalModel.organization_id == organization_id,
            ApprovalModel.action_id == action_id,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        return ApprovalRecord(
            id=row.id,
            action_id=row.action_id,
            organization_id=row.organization_id,
            decision=ApprovalDecisionType(row.decision),
            payload=row.payload,
            decided_by=row.decided_by,
            decided_at=row.decided_at,
        )

    async def add(self, approval: ApprovalRecord) -> None:
        self._session.add(
            ApprovalModel(
                id=approval.id,
                action_id=approval.action_id,
                organization_id=approval.organization_id,
                decision=approval.decision.value,
                payload=dict(approval.payload),
                decided_by=approval.decided_by,
                decided_at=approval.decided_at,
            )
        )
        await self._session.flush()


class SqlAlchemyAgentRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, run: AgentRunRecord) -> None:
        self._session.add(
            AgentRunModel(
                id=run.id,
                organization_id=run.organization_id,
                requested_by=run.requested_by,
                request_text=run.request_text,
                graph_version=run.graph_version,
                prompt_version=run.prompt_version,
                model_config_json=dict(run.model_config_json),
                status="started",
                started_at=run.started_at,
            )
        )
        await self._session.flush()

    async def add_event(self, event: AgentRunEventRecord) -> None:
        self._session.add(
            AgentRunEventModel(
                id=event.id,
                run_id=event.run_id,
                organization_id=event.organization_id,
                event_type=event.event_type,
                occurred_at=event.occurred_at,
                graph_version=event.graph_version,
                prompt_version=event.prompt_version,
                model_config_json=dict(event.model_config_json),
                latency_ms=event.latency_ms,
                input_tokens=event.input_tokens,
                output_tokens=event.output_tokens,
                token_cost_usd=event.token_cost_usd,
                error=event.error,
                event_metadata=dict(event.metadata) if event.metadata is not None else None,
            )
        )
        await self._session.flush()
