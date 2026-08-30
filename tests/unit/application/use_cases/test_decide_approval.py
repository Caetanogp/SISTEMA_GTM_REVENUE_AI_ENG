from collections.abc import Mapping
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from revops.application.dto import CreateTaskArgs
from revops.application.ports import ApprovalRecord
from revops.application.use_cases.decide_approval import DecideApproval, PendingApproval
from revops.application.use_cases.propose_task import ProposeTask
from revops.domain.entities.task import Task
from revops.domain.errors import InvalidTransitionError

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _args(**overrides: object) -> CreateTaskArgs:
    defaults: dict[str, object] = {
        "account_id": uuid4(),
        "owner_id": uuid4(),
        "title": "Follow up",
        "due_at": _NOW,
    }
    return CreateTaskArgs(**{**defaults, **overrides})


def _pending(**overrides: object) -> PendingApproval:
    run_id = uuid4()
    action_id = uuid4()
    task_id = uuid4()
    return PendingApproval(
        proposal=ProposeTask().execute(_args(**overrides)),
        run_id=run_id,
        action_id=action_id,
        task_id=task_id,
    )


class _FakeTaskRepository:
    def __init__(self) -> None:
        self.added: list[Task] = []
        self.tasks_by_id: dict[UUID, Task] = {}

    async def add(self, task: Task) -> None:
        self.added.append(task)
        self.tasks_by_id[task.id] = task

    async def get(self, organization_id: UUID, task_id: UUID) -> Task:
        return self.tasks_by_id[task_id]

    async def update(self, task: Task) -> None:
        self.tasks_by_id[task.id] = task


class _ApprovalRecord:
    def __init__(
        self,
        action_id: UUID,
        decision: str,
        payload: Mapping[str, object],
        decided_by: UUID,
    ) -> None:
        self.action_id = action_id
        self.decision = decision
        self.payload = payload
        self.decided_by = decided_by


class _FakeApprovalRepository:
    def __init__(self) -> None:
        self.records: dict[UUID, ApprovalRecord] = {}

    async def get_for_action(self, organization_id: UUID, action_id: UUID) -> ApprovalRecord | None:
        return self.records.get(action_id)

    async def add(self, approval: ApprovalRecord) -> None:
        self.records[approval.action_id] = approval


class _AuditRecord:
    def __init__(
        self,
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
        self.action_id = action_id
        self.run_id = run_id
        self.organization_id = organization_id
        self.actor_id = actor_id
        self.action = action
        self.payload = payload
        self.outcome = outcome
        self.occurred_at = occurred_at
        self.approved_by = approved_by
        self.executed_at = executed_at


class _FakeAuditTrail:
    def __init__(self) -> None:
        self.records: list[_AuditRecord] = []

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
        self.records.append(
            _AuditRecord(
                action_id,
                run_id,
                organization_id,
                actor_id,
                action,
                payload,
                outcome,
                occurred_at,
                approved_by,
                executed_at,
            )
        )


class _FakeClock:
    def now(self) -> datetime:
        return _NOW


def _decide_approval() -> tuple[
    DecideApproval,
    _FakeTaskRepository,
    _FakeAuditTrail,
    _FakeApprovalRepository,
]:
    tasks = _FakeTaskRepository()
    audit = _FakeAuditTrail()
    approvals = _FakeApprovalRepository()
    return (
        DecideApproval(tasks=tasks, audit=audit, approvals=approvals, clock=_FakeClock()),
        tasks,
        audit,
        approvals,
    )


async def test_approve_creates_the_task_and_records_the_audit() -> None:
    decide, tasks, audit, approvals = _decide_approval()
    pending = _pending(title="Original title")
    org_id, actor_id = uuid4(), uuid4()

    task = await decide.approve(pending, organization_id=org_id, actor_id=actor_id)

    assert tasks.added == [task]
    assert task.title == "Original title"
    assert audit.records[0].outcome == "approved"
    assert audit.records[0].organization_id == org_id
    assert audit.records[0].actor_id == actor_id
    assert approvals.records[pending.action_id].decision.value == "approve"


async def test_edit_persists_the_edited_payload_not_the_original() -> None:
    decide, tasks, audit, approvals = _decide_approval()
    pending = _pending(title="Original title")
    edited = _args(title="Edited title")

    task = await decide.edit(pending, edited, organization_id=uuid4(), actor_id=uuid4())

    assert task.title == "Edited title"
    assert tasks.added == [task]
    assert audit.records[0].outcome == "edited"
    assert audit.records[0].payload["title"] == "Edited title"
    assert approvals.records[pending.action_id].decision.value == "edit"


async def test_reject_writes_only_the_audit_row() -> None:
    decide, tasks, audit, approvals = _decide_approval()
    pending = _pending()

    await decide.reject(pending, organization_id=uuid4(), actor_id=uuid4())

    assert tasks.added == []
    assert audit.records[0].outcome == "rejected"
    assert approvals.records[pending.action_id].decision.value == "reject"


@pytest.mark.parametrize("first", ["approve", "edit", "reject"])
@pytest.mark.parametrize("second", ["approve", "edit", "reject"])
async def test_redeciding_an_already_decided_proposal_raises(first: str, second: str) -> None:
    decide, _, _, _ = _decide_approval()
    pending = _pending()
    org_id = uuid4()
    actor_id = uuid4()
    edited_args = _args()

    async def _act(method: str) -> None:
        kwargs = {"organization_id": org_id, "actor_id": actor_id}
        if method == "approve":
            await decide.approve(pending, **kwargs)
        elif method == "edit":
            await decide.edit(pending, edited_args, **kwargs)
        else:
            await decide.reject(pending, **kwargs)

    await _act(first)
    if first == second:
        await _act(second)
    else:
        with pytest.raises(InvalidTransitionError):
            await _act(second)
