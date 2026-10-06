from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from types import TracebackType
from uuid import UUID, uuid4

import pytest
from revops.application.dto import CreateTaskToolArgs, GetAccountContextArgs, SearchAccountsArgs
from revops.application.ports import TrustedRunContext
from revops.domain.entities.account import Account
from revops.domain.entities.interaction import Interaction
from revops.domain.entities.opportunity import Opportunity
from revops.domain.values.company_domain import CompanyDomain
from revops.infrastructure.agent.tools import (
    CreateTaskTool,
    GetAccountContextTool,
    SearchAccountsTool,
)

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


class _Accounts:
    def __init__(self, account: Account) -> None:
        self.account = account

    async def list_for_organization(self, organization_id: UUID) -> Sequence[Account]:
        return [self.account] if organization_id == self.account.organization_id else []

    async def list_interactions(
        self, organization_id: UUID, account_ids: Sequence[UUID] | UUID
    ) -> Sequence[Interaction]:
        return []

    async def list_open_opportunities(
        self, organization_id: UUID, account_ids: Sequence[UUID] | UUID
    ) -> Sequence[Opportunity]:
        return []


class _Uow:
    def __init__(self, account: Account) -> None:
        self.accounts = _Accounts(account)
        self.canonical = None

    async def __aenter__(self) -> _Uow:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None:
        return None


class _Clock:
    def now(self) -> datetime:
        return _NOW


def _account(organization_id: UUID) -> Account:
    return Account(
        id=uuid4(),
        organization_id=organization_id,
        company_name="Acme",
        domain=CompanyDomain("acme.com"),
        created_at=_NOW - timedelta(days=10),
    )


def _context(organization_id: UUID) -> TrustedRunContext:
    return TrustedRunContext(organization_id=organization_id, actor_id=uuid4(), run_id=uuid4())


@pytest.mark.asyncio
async def test_search_accounts_is_tenant_scoped_and_bounded() -> None:
    organization_id = uuid4()
    account = _account(organization_id)
    tool = SearchAccountsTool(lambda: _Uow(account), _Clock())

    result = await tool.execute(
        context=_context(organization_id),
        arguments=SearchAccountsArgs(query="acme", limit=1),
    )

    assert result.outcome == "completed"
    assert len(result.payload["accounts"]) == 1


@pytest.mark.asyncio
async def test_get_account_context_refuses_another_tenant() -> None:
    organization_id = uuid4()
    account = _account(organization_id)
    tool = GetAccountContextTool(lambda: _Uow(account), _Clock())

    with pytest.raises(PermissionError, match="authenticated organization"):
        await tool.execute(
            context=_context(uuid4()),
            arguments=GetAccountContextArgs(account_id=account.id),
        )


@pytest.mark.asyncio
async def test_create_task_tool_only_returns_an_approval_proposal() -> None:
    organization_id = uuid4()
    account = _account(organization_id)
    tool = CreateTaskTool()

    result = await tool.execute(
        context=_context(organization_id),
        arguments=CreateTaskToolArgs(
            account_id=account.id,
            title="Follow up",
            due_at=_NOW + timedelta(days=1),
        ),
    )

    assert result.requires_approval is True
    assert result.outcome == "approval_required"
    assert "args" in result.payload
