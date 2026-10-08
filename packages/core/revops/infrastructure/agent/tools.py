"""Typed adapters for the three tools allowed by SPEC-009."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from types import TracebackType
from typing import Protocol, cast

from revops.application.dto import (
    CreateTaskArgs,
    CreateTaskToolArgs,
    GetAccountContextArgs,
    PrepareFollowupArgs,
    ResearchCompanyArgs,
    ResearchResultDTO,
    SearchAccountsArgs,
)
from revops.application.ports import (
    AccountRepository,
    AgentTool,
    Clock,
    CompanyResearcher,
    ContactRepository,
    LLMGateway,
    OutreachContextProvider,
    ToolExecutionResult,
    TrustedRunContext,
    UnitOfWork,
)
from revops.application.use_cases.outreach import PrepareFollowup, ResearchCompany
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


class OutreachUnitOfWorkScope(Protocol):
    accounts: AccountRepository
    contacts: ContactRepository

    async def __aenter__(self) -> OutreachUnitOfWorkScope: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None: ...


@dataclass(frozen=True, slots=True)
class ResearchCompanyTool:
    outreach_uow_factory: Callable[[], OutreachUnitOfWorkScope]
    researcher: CompanyResearcher
    gateway: LLMGateway

    name: str = "research_company"
    risk: RiskLevel = RiskLevel.LOW
    arguments_model: type[ResearchCompanyArgs] = ResearchCompanyArgs

    async def execute(
        self, *, context: TrustedRunContext, arguments: ResearchCompanyArgs
    ) -> ToolExecutionResult:
        async with self.outreach_uow_factory() as uow:
            result = await ResearchCompany(
                accounts=uow.accounts,
                contacts=uow.contacts,
                researcher=self.researcher,
                gateway=self.gateway,
            ).execute(context=context, args=arguments)
        return ToolExecutionResult(
            payload=result.model_dump(mode="json"),
            outcome=result.status.value,
        )


@dataclass(frozen=True, slots=True)
class PrepareFollowupTool:
    context_provider: OutreachContextProvider
    gateway: LLMGateway

    name: str = "prepare_followup"
    risk: RiskLevel = RiskLevel.LOW
    arguments_model: type[PrepareFollowupArgs] = PrepareFollowupArgs

    async def execute(
        self, *, context: TrustedRunContext, arguments: PrepareFollowupArgs
    ) -> ToolExecutionResult:
        raw_research = context.prior_results.get("research_company")
        research = ResearchResultDTO.model_validate(raw_research) if raw_research else None
        result = await PrepareFollowup(self.context_provider, self.gateway).execute(
            context=context,
            args=arguments,
            research=research,
        )
        return ToolExecutionResult(
            payload=result.model_dump(mode="json"),
            outcome=result.status.value,
        )


def build_agent_tools(
    uow_factory: UowFactory,
    clock: Clock,
    *,
    outreach_uow_factory: Callable[[], OutreachUnitOfWorkScope] | None = None,
    researcher: CompanyResearcher | None = None,
    outreach_context: OutreachContextProvider | None = None,
    outreach_gateway: LLMGateway | None = None,
) -> dict[str, AgentTool]:
    """Compose the explicit allowlist; unknown tools are never registered."""
    tools: list[AgentTool] = [
        cast(AgentTool, SearchAccountsTool(uow_factory, clock)),
        cast(AgentTool, GetAccountContextTool(uow_factory, clock)),
        cast(AgentTool, CreateTaskTool()),
    ]
    if outreach_uow_factory is not None and researcher is not None and outreach_gateway is not None:
        tools.append(
            cast(
                AgentTool,
                ResearchCompanyTool(
                    outreach_uow_factory=outreach_uow_factory,
                    researcher=researcher,
                    gateway=outreach_gateway,
                ),
            )
        )
    if outreach_context is not None and outreach_gateway is not None:
        tools.append(
            cast(
                AgentTool,
                PrepareFollowupTool(
                    context_provider=outreach_context,
                    gateway=outreach_gateway,
                ),
            )
        )
    return {tool.name: tool for tool in tools}
