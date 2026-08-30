"""`DecideApproval`: Approve / Edit / Reject a `ProposedAction`, exactly once.

Approve or Edit executes the (possibly edited) payload through the repository ports and writes an
audit row; Reject writes the audit row and nothing else. AGENTS.md: the audit trail is append-only
and HITL is mandatory for this risk level - this use case is the only place a proposal turns into
a persisted `Task`, and only after a human decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import NAMESPACE_URL, UUID, uuid5

from revops.application.dto import ApprovalDecisionType, CreateTaskArgs
from revops.application.ports import (
    ApprovalRecord,
    ApprovalRepository,
    AuditTrail,
    Clock,
    TaskRepository,
)
from revops.application.use_cases.propose_task import ProposedAction
from revops.domain.entities.task import Task
from revops.domain.errors import InvalidTransitionError


@dataclass(slots=True)
class PendingApproval:
    """A `ProposedAction` awaiting exactly one Approve/Edit/Reject decision."""

    proposal: ProposedAction
    run_id: UUID
    action_id: UUID
    task_id: UUID
    decided: bool = False


@dataclass(frozen=True, slots=True)
class DecideApproval:
    tasks: TaskRepository
    audit: AuditTrail
    approvals: ApprovalRepository
    clock: Clock

    async def approve(
        self, pending: PendingApproval, *, organization_id: UUID, actor_id: UUID
    ) -> Task:
        existing = await self._existing(
            pending,
            ApprovalDecisionType.APPROVE,
            pending.proposal.args,
            organization_id,
            actor_id,
        )
        if existing is not None:
            return existing
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
        existing = await self._existing(
            pending,
            ApprovalDecisionType.EDIT,
            edited_args,
            organization_id,
            actor_id,
        )
        if existing is not None:
            return existing
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
        existing = await self.approvals.get_for_action(organization_id, pending.action_id)
        if existing is not None:
            self._assert_same(
                existing,
                ApprovalDecisionType.REJECT,
                pending.proposal.args,
                actor_id,
            )
            return
        self._mark_decided(pending)
        now = self.clock.now()
        await self.audit.record(
            action_id=pending.action_id,
            run_id=pending.run_id,
            organization_id=organization_id,
            actor_id=actor_id,
            action=pending.proposal.tool_name,
            payload=pending.proposal.args.model_dump(mode="json"),
            outcome="rejected",
            occurred_at=now,
            approved_by=None,
            executed_at=None,
        )
        await self._record_approval(
            pending,
            ApprovalDecisionType.REJECT,
            pending.proposal.args,
            organization_id,
            actor_id,
            now,
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
        now = self.clock.now()
        task = Task(
            id=pending.task_id,
            organization_id=organization_id,
            owner_id=args.owner_id,
            account_id=args.account_id,
            title=args.title,
            due_at=args.due_at,
        )
        await self.tasks.add(task)
        await self.audit.record(
            action_id=pending.action_id,
            run_id=pending.run_id,
            organization_id=organization_id,
            actor_id=actor_id,
            action=pending.proposal.tool_name,
            payload=args.model_dump(mode="json"),
            outcome=outcome,
            occurred_at=now,
            approved_by=actor_id,
            executed_at=now,
        )
        decision = (
            ApprovalDecisionType.APPROVE if outcome == "approved" else ApprovalDecisionType.EDIT
        )
        await self._record_approval(
            pending,
            decision,
            args,
            organization_id,
            actor_id,
            now,
        )
        return task

    async def _existing(
        self,
        pending: PendingApproval,
        decision: ApprovalDecisionType,
        args: CreateTaskArgs,
        organization_id: UUID,
        actor_id: UUID,
    ) -> Task | None:
        existing = await self.approvals.get_for_action(organization_id, pending.action_id)
        if existing is None:
            return None
        self._assert_same(existing, decision, args, actor_id)
        return await self.tasks.get(organization_id, pending.task_id)

    async def _record_approval(
        self,
        pending: PendingApproval,
        decision: ApprovalDecisionType,
        args: CreateTaskArgs,
        organization_id: UUID,
        actor_id: UUID,
        now: datetime,
    ) -> None:
        await self.approvals.add(
            ApprovalRecord(
                id=uuid5(NAMESPACE_URL, f"approval:{pending.action_id}"),
                action_id=pending.action_id,
                organization_id=organization_id,
                decision=decision,
                payload=args.model_dump(mode="json"),
                decided_by=actor_id,
                decided_at=now,
            )
        )

    @staticmethod
    def _assert_same(
        existing: ApprovalRecord,
        decision: ApprovalDecisionType,
        args: CreateTaskArgs,
        actor_id: UUID,
    ) -> None:
        if (
            existing.decision != decision
            or dict(existing.payload) != args.model_dump(mode="json")
            or existing.decided_by != actor_id
        ):
            raise InvalidTransitionError("this proposal already has a different decision")

    @staticmethod
    def _mark_decided(pending: PendingApproval) -> None:
        if pending.decided:
            raise InvalidTransitionError(
                "this proposal has already been decided and cannot be decided again"
            )
        pending.decided = True
