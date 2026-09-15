"""Runtime helpers for the API composition root."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, cast

from revops.application.dto import LLMGatewayHealth, LLMHealthStatus
from revops.application.ports import Clock, LLMGateway
from revops.application.use_cases.deduplication import (
    DismissDeduplicationCandidate,
    GetDeduplicationStatus,
    ListDeduplicationCandidates,
    ListDeduplicationHistory,
    MergeDeduplicationCandidate,
    RevertDeduplicationMerge,
    StartDeduplicationScan,
)
from revops.application.use_cases.ingestion import (
    ConfirmIngestion,
    GetIngestionJob,
    ListIngestionItems,
    StageIngestion,
)
from revops.infrastructure.agent.checkpointer import open_checkpointer
from revops.infrastructure.agent.graph import build_agent_graph
from revops.infrastructure.agent.nodes import AgentGraphDependencies, UnitOfWorkScope
from revops.infrastructure.agent.runner import AgentGraphRunner
from revops.infrastructure.persistence.repositories import SqlAlchemyAgentRunJournal
from revops.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
from revops.infrastructure.queue import (
    CeleryDeduplicationDispatcher,
    CeleryIngestionDispatcher,
    create_celery_app,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .settings import ApiSettings

GRAPH_VERSION = "account-prioritization.v1"
PROMPT_VERSION = "prioritize_accounts.v2"


class UtcClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class UnconfiguredLLMGateway:
    async def complete(self, *, prompt: str, response_model: type[Any]) -> Any:
        raise RuntimeError("LLM gateway is not configured for this API instance")

    def configuration_snapshot(self) -> dict[str, object]:
        return {"gateway_version": "disabled.v1", "mode": "disabled"}

    def health_snapshot(self) -> LLMGatewayHealth:
        return LLMGatewayHealth(
            mode="disabled",
            status=LLMHealthStatus.DISABLED,
            providers=(),
        )


def ingestion_services(
    *, uow_factory: Any, settings: ApiSettings
) -> tuple[StageIngestion, ConfirmIngestion, GetIngestionJob, ListIngestionItems]:
    dispatcher = CeleryIngestionDispatcher(
        create_celery_app(broker_url=settings.broker_url, result_backend=settings.result_backend)
    )
    return (
        StageIngestion(uow_factory),
        ConfirmIngestion(uow_factory, dispatcher),
        GetIngestionJob(uow_factory),
        ListIngestionItems(uow_factory),
    )


def deduplication_services(
    *, uow_factory: Any, settings: ApiSettings
) -> tuple[
    StartDeduplicationScan,
    GetDeduplicationStatus,
    ListDeduplicationCandidates,
    DismissDeduplicationCandidate,
    MergeDeduplicationCandidate,
    RevertDeduplicationMerge,
    ListDeduplicationHistory,
]:
    dispatcher = CeleryDeduplicationDispatcher(
        create_celery_app(broker_url=settings.broker_url, result_backend=settings.result_backend)
    )
    return (
        StartDeduplicationScan(uow_factory, dispatcher),
        GetDeduplicationStatus(uow_factory),
        ListDeduplicationCandidates(uow_factory),
        DismissDeduplicationCandidate(uow_factory),
        MergeDeduplicationCandidate(uow_factory),
        RevertDeduplicationMerge(uow_factory),
        ListDeduplicationHistory(uow_factory),
    )


@asynccontextmanager
async def open_agent_runner(
    *,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    settings: ApiSettings,
    llm_gateway: LLMGateway,
) -> AsyncIterator[AgentGraphRunner]:
    clock: Clock = UtcClock()
    deps = AgentGraphDependencies(
        uow_factory=lambda: cast(UnitOfWorkScope, _uow_factory(session_factory)),
        llm_gateway=llm_gateway,
        clock=clock,
        graph_version=GRAPH_VERSION,
        prompt_version=PROMPT_VERSION,
    )
    async with open_checkpointer(settings.postgres_dsn) as checkpointer:
        graph = build_agent_graph(deps, checkpointer)
        yield AgentGraphRunner(
            graph=graph,
            runs=SqlAlchemyAgentRunJournal(session_factory),
            clock=clock,
            graph_version=GRAPH_VERSION,
            prompt_version=PROMPT_VERSION,
            model_config_json=dict(llm_gateway.configuration_snapshot()),
        )


@asynccontextmanager
async def _uow_factory(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[SqlAlchemyUnitOfWork]:
    async with session_factory() as session:
        yield SqlAlchemyUnitOfWork(session)
