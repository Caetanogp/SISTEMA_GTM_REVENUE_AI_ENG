from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import TracebackType
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from revops.application.dto import (
    AccountCandidate,
    ApprovalDecisionInput,
    ApprovalDecisionType,
    ContextSectionSnapshot,
    CreateTaskDraft,
    PrioritizationOutput,
    RankedAccount,
)
from revops.domain.entities.account import Account
from revops.domain.entities.interaction import Interaction
from revops.domain.entities.opportunity import Opportunity, OpportunityStage
from revops.domain.values.company_domain import CompanyDomain
from revops.domain.values.score import ScoreTier
from revops.infrastructure.agent.nodes import (
    AgentGraphDependencies,
    UnitOfWorkScope,
    execute_action,
    load_context,
    propose_action,
    score_accounts,
)
from revops.infrastructure.agent.state import (
    AccountCandidateSnapshot,
    AgentGraphState,
    PendingApprovalSnapshot,
    PrioritizationSnapshot,
)
from revops.infrastructure.llm.fake import FakeLLMGateway

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _account(company_name: str = "Acme") -> Account:
    return Account(
        id=uuid4(),
        organization_id=_ORG_ID,
        company_name=company_name,
        domain=CompanyDomain("acme.com"),
        created_at=_NOW - timedelta(days=30),
    )


_ORG_ID = uuid4()
_ACCOUNT = _account()


class _FakeClock:
    def now(self) -> datetime:
        return _NOW


class _FakeAccountRepository:
    async def get(self, organization_id: UUID, account_id: UUID) -> Account:
        raise NotImplementedError

    async def list_for_organization(self, organization_id: UUID) -> Sequence[Account]:
        return [_ACCOUNT] if organization_id == _ORG_ID else []

    async def list_interactions(
        self, organization_id: UUID, account_id: UUID
    ) -> Sequence[Interaction]:
        return [
            Interaction(
                id=uuid4(),
                organization_id=organization_id,
                account_id=account_id,
                channel="email",
                occurred_at=_NOW - timedelta(days=1),
                summary="follow-up",
            )
        ]

    async def list_open_opportunities(
        self, organization_id: UUID, account_id: UUID
    ) -> Sequence[Opportunity]:
        return [
            Opportunity(
                id=uuid4(),
                organization_id=organization_id,
                account_id=account_id,
                stage=OpportunityStage.NEGOTIATION,
                value=Decimal("120000.00"),
            )
        ]


class _FakeTaskRepository:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.tasks_by_id: dict[UUID, object] = {}

    async def add(self, task: object) -> None:
        self.added.append(task)
        self.tasks_by_id[cast(Any, task).id] = task

    async def get(self, organization_id: UUID, task_id: UUID) -> object:
        return self.tasks_by_id[task_id]

    async def update(self, task: object) -> None:
        self.tasks_by_id[cast(Any, task).id] = task


class _FakeApprovalRepository:
    def __init__(self) -> None:
        self.records: dict[UUID, object] = {}

    async def get_for_action(self, organization_id: UUID, action_id: UUID) -> object | None:
        return self.records.get(action_id)

    async def add(self, approval: object) -> None:
        self.records[cast(Any, approval).action_id] = approval


class _FakeAuditTrail:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    async def record(self, **kwargs: object) -> None:
        self.records.append(kwargs)


class _FakeUnitOfWork:
    def __init__(self) -> None:
        self.accounts = _FakeAccountRepository()
        self.tasks = _FakeTaskRepository()
        self.approvals = _FakeApprovalRepository()
        self.audit = _FakeAuditTrail()
        self.runs = _FakeApprovalRepository()

    async def __aenter__(self) -> _FakeUnitOfWork:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None:
        return None

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


def _deps(
    gateway: FakeLLMGateway | None = None,
    *,
    uow: _FakeUnitOfWork | None = None,
) -> AgentGraphDependencies:
    shared_uow = uow or _FakeUnitOfWork()
    return AgentGraphDependencies(
        uow_factory=lambda: cast(UnitOfWorkScope, shared_uow),
        llm_gateway=gateway or FakeLLMGateway(),
        clock=_FakeClock(),
        graph_version="account-prioritization.v1",
        prompt_version="prioritize_accounts.v1",
    )


def _prioritization(candidate: AccountCandidate) -> PrioritizationOutput:
    return PrioritizationOutput(
        accounts=[
            RankedAccount(
                account_id=candidate.account_id,
                score=candidate.score,
                tier=candidate.tier,
                evidence=candidate.evidence,
                reasons=["recent engagement"],
            )
        ],
        task=CreateTaskDraft(
            account_id=candidate.account_id,
            title="Call the champion",
            due_at=_NOW + timedelta(days=7),
        ),
    )


async def test_load_context_builds_candidate_snapshots() -> None:
    run_id = uuid4()
    state: AgentGraphState = {
        "organization_id": str(_ORG_ID),
        "actor_id": str(uuid4()),
        "request_text": "prioritize",
        "run_id": str(run_id),
        "thread_id": str(run_id),
        "graph_version": "account-prioritization.v1",
        "prompt_version": "prioritize_accounts.v1",
        "model_config_json": {},
    }

    result = await load_context(state, _deps())

    candidates = cast(list[AccountCandidateSnapshot], result["candidates"])

    assert len(candidates) == 1
    assert candidates[0]["account_id"] == str(_ACCOUNT.id)


async def test_score_accounts_validates_the_llm_output() -> None:
    run_id = uuid4()
    candidate = AccountCandidate(
        account_id=_ACCOUNT.id,
        company_name=_ACCOUNT.company_name,
        score=72,
        tier=ScoreTier.HOT,
        evidence=["recent engagement"],
        context=[ContextSectionSnapshot(label="account", text="Acme")],
        dropped_context_labels=[],
        token_count=10,
    )
    gateway = FakeLLMGateway(responses=[_prioritization(candidate)])
    state: AgentGraphState = {
        "organization_id": str(_ORG_ID),
        "actor_id": str(uuid4()),
        "request_text": "prioritize",
        "run_id": str(run_id),
        "thread_id": str(run_id),
        "graph_version": "account-prioritization.v1",
        "prompt_version": "prioritize_accounts.v1",
        "model_config_json": {},
        "candidates": [cast(AccountCandidateSnapshot, candidate.model_dump(mode="json"))],
    }

    result = await score_accounts(state, _deps(gateway))

    prioritization = cast(dict[str, object], result["prioritization"])

    assert cast(dict[str, object], prioritization["task"])["account_id"] == str(_ACCOUNT.id)
    assert len(gateway.calls) == 1


async def test_execute_action_reuses_the_persisted_approval_on_repeat_resume(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = uuid4()
    candidate = AccountCandidate(
        account_id=_ACCOUNT.id,
        company_name=_ACCOUNT.company_name,
        score=72,
        tier=ScoreTier.HOT,
        evidence=["recent engagement"],
        context=[ContextSectionSnapshot(label="account", text="Acme")],
        dropped_context_labels=[],
        token_count=10,
    )
    state: AgentGraphState = {
        "organization_id": str(_ORG_ID),
        "actor_id": str(uuid4()),
        "request_text": "prioritize",
        "run_id": str(run_id),
        "thread_id": str(run_id),
        "graph_version": "account-prioritization.v1",
        "prompt_version": "prioritize_accounts.v1",
        "model_config_json": {},
        "prioritization": cast(
            PrioritizationSnapshot,
            _prioritization(candidate).model_dump(mode="json"),
        ),
    }
    shared_uow = _FakeUnitOfWork()
    deps = _deps(uow=shared_uow)
    proposal = await propose_action(state, deps)
    state["pending_approval"] = cast(PendingApprovalSnapshot, proposal["pending_approval"])
    decision = ApprovalDecisionInput(
        decision=ApprovalDecisionType.APPROVE,
        organization_id=_ORG_ID,
        decided_by=uuid4(),
    )
    monkeypatch.setattr(
        "revops.infrastructure.agent.nodes.interrupt",
        lambda payload: decision.model_dump(mode="json"),
    )

    first = await execute_action(state, deps)
    second = await execute_action(state, deps)

    assert cast(dict[str, object], first["task"]) == cast(dict[str, object], second["task"])
    assert len(shared_uow.tasks.added) == 1
