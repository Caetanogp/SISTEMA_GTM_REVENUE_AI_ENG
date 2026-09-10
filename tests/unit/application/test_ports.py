"""Ports are Protocols: structural typing is the whole point of this file.

An adapter that never imports `application.ports` should still satisfy `isinstance` against it,
since that is what lets infrastructure implement these without a dependency pointing outward.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from types import TracebackType
from uuid import UUID

from pydantic import BaseModel
from revops.application.ports import (
    AccountRepository,
    AgentRunRepository,
    ApprovalRecord,
    ApprovalRepository,
    AuditTrail,
    Clock,
    LLMGateway,
    TaskRepository,
    UnitOfWork,
)
from revops.domain.entities.account import Account
from revops.domain.entities.interaction import Interaction
from revops.domain.entities.opportunity import Opportunity
from revops.domain.entities.task import Task
from revops.infrastructure.llm.fake import FakeLLMGateway


def test_all_eight_ports_are_protocols() -> None:
    for port in (
        AccountRepository,
        TaskRepository,
        AuditTrail,
        ApprovalRepository,
        AgentRunRepository,
        LLMGateway,
        Clock,
        UnitOfWork,
    ):
        assert getattr(port, "_is_protocol", False) is True


class _FakeAccountRepository:
    async def get(self, organization_id: UUID, account_id: UUID) -> Account:
        raise NotImplementedError

    async def list_for_organization(self, organization_id: UUID) -> list[Account]:
        return []

    async def list_interactions(
        self, organization_id: UUID, account_ids: Sequence[UUID] | UUID
    ) -> list[Interaction]:
        return []

    async def list_open_opportunities(
        self, organization_id: UUID, account_ids: Sequence[UUID] | UUID
    ) -> list[Opportunity]:
        return []


def test_fake_account_repository_satisfies_the_protocol_structurally() -> None:
    assert isinstance(_FakeAccountRepository(), AccountRepository)


class _FakeTaskRepository:
    async def add(self, task: Task) -> None: ...

    async def get(self, organization_id: UUID, task_id: UUID) -> Task:
        raise NotImplementedError

    async def update(self, task: Task) -> None: ...


def test_fake_task_repository_satisfies_the_protocol_structurally() -> None:
    assert isinstance(_FakeTaskRepository(), TaskRepository)


class _FakeAuditTrail:
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
    ) -> None: ...


class _FakeApprovalRepository:
    async def get_for_action(self, organization_id: UUID, action_id: UUID) -> ApprovalRecord | None:
        return None

    async def add(self, approval: ApprovalRecord) -> None: ...


class _FakeAgentRunRepository:
    async def add(self, run: object) -> None: ...

    async def add_event(self, event: object) -> None: ...


def test_fake_audit_trail_satisfies_the_protocol_structurally() -> None:
    assert isinstance(_FakeAuditTrail(), AuditTrail)


def test_audit_trail_has_no_update_or_delete() -> None:
    """AGENTS.md: the audit trail is append-only - the port must not offer a way to violate that."""
    for forbidden in ("update", "delete", "remove"):
        assert not hasattr(AuditTrail, forbidden)


class _FakeClock:
    def now(self) -> datetime:
        return datetime(2026, 1, 1, tzinfo=UTC)


def test_fake_clock_satisfies_the_protocol_structurally() -> None:
    assert isinstance(_FakeClock(), Clock)


class _FakeUnitOfWork:
    accounts: AccountRepository
    tasks: TaskRepository
    audit: AuditTrail
    approvals: ApprovalRepository
    runs: AgentRunRepository
    canonical: object | None

    def __init__(self) -> None:
        self.accounts = _FakeAccountRepository()
        self.tasks = _FakeTaskRepository()
        self.audit = _FakeAuditTrail()
        self.approvals = _FakeApprovalRepository()
        self.runs = _FakeAgentRunRepository()
        self.canonical = object()

    async def __aenter__(self) -> _FakeUnitOfWork:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


def test_fake_unit_of_work_satisfies_the_protocol_structurally() -> None:
    assert isinstance(_FakeUnitOfWork(), UnitOfWork)


def test_account_repository_read_only_no_write_methods() -> None:
    for forbidden in ("add", "update", "save", "delete"):
        assert not hasattr(AccountRepository, forbidden)


async def test_llm_gateway_complete_is_generic_over_response_model() -> None:
    class _Answer(BaseModel):
        value: str

    gateway = FakeLLMGateway(responses=[_Answer(value="hello")])
    assert isinstance(gateway, LLMGateway)
    result = await gateway.complete(prompt="hello", response_model=_Answer)
    assert result.output.value == "hello"
