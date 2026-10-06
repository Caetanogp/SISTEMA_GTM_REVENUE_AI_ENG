"""Typed adapters for the three tools allowed by SPEC-009."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from types import TracebackType
from typing import Protocol

from revops.application.dto import (
    CreateTaskArgs,
    CreateTaskToolArgs,
    GetAccountContextArgs,
    SearchAccountsArgs,
)
from revops.application.ports import (
    AgentTool,
    Clock,
    ToolExecutionResult,
    TrustedRunContext,
    UnitOfWork,
)
from revops.application.use_cases.prioritize_accounts import PrioritizeAccounts
from revops.application.use_cases.propose_task import ProposeTask
from revops.domain.values.risk import RiskLevel


class UnitOfWorkScope(Protocol):
    async def __aenter__(self) -> UnitOfWork: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None: ...


UowFactory = Callable[[], UnitOfWorkScope]


@dataclass(frozen=True, slots=True)
class SearchAccountsTool:
    uow_factory: UowFactory
    clock: Clock

    name: str = "search_accounts"
    risk: RiskLevel = RiskLevel.LOW
    arguments_model: type[SearchAccountsArgs] = SearchAccountsArgs

    async def execute(
        self, *, context: TrustedRunContext, arguments: SearchAccountsArgs
    ) -> ToolExecutionResult:
        async with self.uow_factory() as uow:
            candidates = await PrioritizeAccounts(
                accounts=uow.accounts,
                clock=self.clock,
                canonical=getattr(uow, "canonical", None),
            ).execute(context.organization_id)
        query = arguments.query.casefold().strip()
        if query:
            candidates = [
                candidate for candidate in candidates if query in candidate.company_name.casefold()
            ]
        return ToolExecutionResult(
            payload={
                "accounts": [
                    candidate.model_dump(mode="json") for candidate in candidates[: arguments.limit]
                ]
            },
            outcome="completed",
        )


@dataclass(frozen=True, slots=True)
class GetAccountContextTool:
    uow_factory: UowFactory
    clock: Clock

    name: str = "get_account_context"
    risk: RiskLevel = RiskLevel.LOW
    arguments_model: type[GetAccountContextArgs] = GetAccountContextArgs

    async def execute(
        self, *, context: TrustedRunContext, arguments: GetAccountContextArgs
    ) -> ToolExecutionResult:
        async with self.uow_factory() as uow:
            candidates = await PrioritizeAccounts(
                accounts=uow.accounts,
                clock=self.clock,
                canonical=getattr(uow, "canonical", None),
            ).execute(context.organization_id)
        candidate = next(
            (item for item in candidates if item.account_id == arguments.account_id), None
        )
        if candidate is None:
            raise PermissionError("account is not in the authenticated organization")
        return ToolExecutionResult(
            payload={"account": candidate.model_dump(mode="json")},
            outcome="completed",
        )


@dataclass(frozen=True, slots=True)
class CreateTaskTool:
    name: str = "create_task"
    risk: RiskLevel = RiskLevel.MEDIUM
    arguments_model: type[CreateTaskToolArgs] = CreateTaskToolArgs

    async def execute(
        self, *, context: TrustedRunContext, arguments: CreateTaskToolArgs
    ) -> ToolExecutionResult:
        args = CreateTaskArgs(
            account_id=arguments.account_id,
            owner_id=context.actor_id,
            title=arguments.title,
            due_at=arguments.due_at,
        )
        proposal = ProposeTask().execute(args)
        return ToolExecutionResult(
            payload={
                "tool_name": proposal.tool_name,
                "args": args.model_dump(mode="json"),
                "risk": proposal.risk.value,
                "requires_approval": proposal.requires_approval,
            },
            outcome="approval_required",
            requires_approval=proposal.requires_approval,
        )


def build_agent_tools(uow_factory: UowFactory, clock: Clock) -> dict[str, AgentTool]:
    """Compose the explicit allowlist; unknown tools are never registered."""
    tools: tuple[AgentTool, ...] = (
        SearchAccountsTool(uow_factory, clock),
        GetAccountContextTool(uow_factory, clock),
        CreateTaskTool(),
    )
    return {tool.name: tool for tool in tools}
