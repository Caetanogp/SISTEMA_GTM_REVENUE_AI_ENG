"""`DecideApproval`: Approve / Edit / Reject a `ProposedAction`, exactly once.

Approve or Edit executes the (possibly edited) payload through the repository ports and writes an
audit row; Reject writes the audit row and nothing else. AGENTS.md: the audit trail is append-only
and HITL is mandatory for this risk level - this use case is the only place a proposal turns into
a persisted `Task`, and only after a human decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from revops.application.dto import CreateTaskArgs
from revops.application.ports import AuditTrail, Clock, TaskRepository
from revops.application.use_cases.propose_task import ProposedAction
from revops.domain.entities.task import Task
from revops.domain.errors import InvalidTransitionError


@dataclass(slots=True)
class PendingApproval:
    """A `ProposedAction` awaiting exactly one Approve/Edit/Reject decision."""

    proposal: ProposedAction
    decided: bool = False


@dataclass(frozen=True, slots=True)
class DecideApproval:
    tasks: TaskRepository
    audit: AuditTrail
    clock: Clock

    async def approve(
        self, pending: PendingApproval, *, organization_id: UUID, actor_id: UUID
    ) -> Task:
        return await self._execute(
            pending,
            args=pending.proposal.args,
            outcome="approved",
            organization_id=organization_id,
            actor_id=actor_id,
        )

    async def edit(
        self,
        pending: PendingApproval,
        edited_args: CreateTaskArgs,
        *,
        organization_id: UUID,
        actor_id: UUID,
    ) -> Task:
        return await self._execute(
            pending,
            args=edited_args,
            outcome="edited",
            organization_id=organization_id,
            actor_id=actor_id,
        )

    async def reject(
        self, pending: PendingApproval, *, organization_id: UUID, actor_id: UUID
    ) -> None:
        self._mark_decided(pending)
        await self.audit.record(
            organization_id=organization_id,
            actor_id=actor_id,
            action=pending.proposal.tool_name,
            payload=pending.proposal.args.model_dump(mode="json"),
            outcome="rejected",
            occurred_at=self.clock.now(),
        )

    async def _execute(
        self,
        pending: PendingApproval,
        *,
        args: CreateTaskArgs,
        outcome: str,
        organization_id: UUID,
        actor_id: UUID,
    ) -> Task:
        self._mark_decided(pending)
        task = Task(
            id=uuid4(),
            organization_id=organization_id,
            owner_id=args.owner_id,
            account_id=args.account_id,
            title=args.title,
            due_at=args.due_at,
        )
        await self.tasks.add(task)
        await self.audit.record(
            organization_id=organization_id,
            actor_id=actor_id,
            action=pending.proposal.tool_name,
            payload=args.model_dump(mode="json"),
            outcome=outcome,
            occurred_at=self.clock.now(),
        )
        return task

    @staticmethod
    def _mark_decided(pending: PendingApproval) -> None:
        if pending.decided:
            raise InvalidTransitionError(
                "this proposal has already been decided and cannot be decided again"
            )
        pending.decided = True
