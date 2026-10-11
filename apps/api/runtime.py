"""Runtime helpers for the API composition root."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, cast

import httpx
from revops.application.dto import LLMGatewayHealth, LLMHealthStatus
from revops.application.ports import Clock, EmbeddingProvider, LLMGateway, ReplyUnitOfWork
from revops.application.use_cases.agent_tool_runtime import BoundedAgentToolRuntime
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
from revops.application.use_cases.knowledge import (
    ActivateKnowledgeRevision,
    ConfirmKnowledgeDocument,
    GetKnowledgeVersion,
    ListKnowledgeVersions,
    RetireKnowledgeVersion,
    SubmitKnowledgeDocument,
)
from revops.infrastructure.agent.checkpointer import open_checkpointer
from revops.infrastructure.agent.graph import build_agent_graph
from revops.infrastructure.agent.nodes import AgentGraphDependencies, UnitOfWorkScope
from revops.infrastructure.agent.outreach_context import (
    SqlAlchemyOutreachContextProvider,
    outreach_read_scope_factory,
)
from revops.infrastructure.agent.prompt_loader import (
    load_agent_tool_runtime_prompt,
    load_legacy_agent_tool_runtime_prompt,
)
from revops.infrastructure.agent.reply_classifier import BoundedReplyClassifier
from revops.infrastructure.agent.reply_runtime import (
    ReplyArtifactReader,
    ReplyGraphDependencies,
    ReplyGraphRunner,
)
from revops.infrastructure.agent.research import (
    AuthorizedCompanyPage,
    BoundedCompanyResearcher,
    HttpxPageFetcher,
    ResearchSourcePolicy,
)
from revops.infrastructure.agent.runner import AgentGraphRunner
from revops.infrastructure.agent.tools import OutreachUnitOfWorkScope, build_agent_tools
from revops.infrastructure.embeddings.providers import (
    DeterministicFakeEmbeddingProvider,
    OpenAIEmbeddingProvider,
)
from revops.infrastructure.persistence.repositories import SqlAlchemyAgentRunJournal
from revops.infrastructure.persistence.unit_of_work import (
    SqlAlchemyReplyUnitOfWork,
    SqlAlchemyUnitOfWork,
)
from revops.infrastructure.queue import (
    CeleryDeduplicationDispatcher,
    CeleryIngestionDispatcher,
    CeleryKnowledgeDispatcher,
    create_celery_app,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .settings import ApiSettings

GRAPH_VERSION = "single-agent-tool-runtime.v2"
PROMPT_VERSION = "agent_tool_runtime.v2"
LEGACY_GRAPH_VERSION = "single-agent-tool-runtime.v1"
LEGACY_PROMPT_VERSION = "agent_tool_runtime.v1"


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


def build_embedding_provider(
    settings: ApiSettings, *, client: httpx.AsyncClient | None = None
) -> EmbeddingProvider:
    """Build the explicitly configured query embedding adapter for the API."""
    if settings.knowledge_embedding_provider == "fake":
        return DeterministicFakeEmbeddingProvider(dimension=settings.knowledge_embedding_dimension)
    if settings.openai_api_key is None:
        raise RuntimeError("knowledge embedding provider requires OPENAI_API_KEY")
    if client is None:
        raise RuntimeError("live knowledge embedding provider requires an HTTP client")
    return OpenAIEmbeddingProvider(
        client=client,
        api_key=settings.openai_api_key.get_secret_value(),
        model=settings.knowledge_embedding_model,
        dimension=settings.knowledge_embedding_dimension,
    )


def build_researcher(
    settings: ApiSettings, *, client: httpx.AsyncClient | None = None
) -> BoundedCompanyResearcher:
    """Build a disabled-by-default researcher from deployment-owned exact source paths."""
    import json

    pages: list[AuthorizedCompanyPage] = []
    if settings.research_enabled:
        try:
            configured = json.loads(settings.research_sources_json)
        except json.JSONDecodeError as exc:
            raise RuntimeError("RESEARCH_SOURCES_JSON is invalid") from exc
        if not isinstance(configured, dict):
            raise RuntimeError("RESEARCH_SOURCES_JSON must be an object")
        for host, paths in configured.items():
            if not isinstance(host, str) or not isinstance(paths, list):
                raise RuntimeError("research source configuration is invalid")
            for path in paths:
                if not isinstance(path, str):
                    raise RuntimeError("research source path configuration is invalid")
                pages.append(
                    AuthorizedCompanyPage(
                        host=host,
                        path_prefix=path,
                        url=f"https://{host}{path}",
                    )
                )
    return BoundedCompanyResearcher(
        policy=ResearchSourcePolicy(tuple(pages)),
        fetcher=HttpxPageFetcher(client=client),
        deadline_seconds=settings.research_deadline_seconds,
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


def knowledge_services(
    *, uow_factory: Any, settings: ApiSettings
) -> tuple[
    SubmitKnowledgeDocument,
    ConfirmKnowledgeDocument,
    GetKnowledgeVersion,
    ListKnowledgeVersions,
    RetireKnowledgeVersion,
    ActivateKnowledgeRevision,
]:
    clock: Clock = UtcClock()
    dispatcher = CeleryKnowledgeDispatcher(
        create_celery_app(broker_url=settings.broker_url, result_backend=settings.result_backend)
    )
    return (
        SubmitKnowledgeDocument(uow_factory, clock),
        ConfirmKnowledgeDocument(uow_factory, dispatcher, clock),
        GetKnowledgeVersion(uow_factory),
        ListKnowledgeVersions(uow_factory),
        RetireKnowledgeVersion(uow_factory),
        ActivateKnowledgeRevision(uow_factory, clock),
    )


def reply_runner(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    settings: ApiSettings,
    llm_gateway: LLMGateway,
) -> ReplyGraphRunner:
    """Compose only the reply runtime; it has no RAG or legacy graph dependencies."""
    clock: Clock = UtcClock()
    return ReplyGraphRunner(
        dsn=settings.postgres_dsn,
        dependencies=ReplyGraphDependencies(
            uow_factory=lambda: cast(
                ReplyUnitOfWork,
                SqlAlchemyReplyUnitOfWork(session_factory(), close_on_exit=True),
            ),
            classifier=BoundedReplyClassifier(llm_gateway),
        ),
        journal=SqlAlchemyAgentRunJournal(session_factory),
        clock=clock,
        model_config_json=dict(llm_gateway.configuration_snapshot()),
    )


def reply_artifact_reader(settings: ApiSettings) -> ReplyArtifactReader:
    """Compose the checkpoint reader without any graph, model, or retrieval component."""
    return ReplyArtifactReader(settings.postgres_dsn)


@asynccontextmanager
async def open_agent_runner(
    *,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    settings: ApiSettings,
    llm_gateway: LLMGateway,
    embedding_provider: EmbeddingProvider | None = None,
    graph_version: str | None = None,
) -> AsyncIterator[AgentGraphRunner]:
    clock: Clock = UtcClock()
    selected_graph_version = graph_version or GRAPH_VERSION
    is_legacy = selected_graph_version == LEGACY_GRAPH_VERSION
    selected_prompt_version = LEGACY_PROMPT_VERSION if is_legacy else PROMPT_VERSION
    research_client = (
        httpx.AsyncClient(follow_redirects=False, trust_env=False)
        if settings.research_enabled
        else None
    )
    try:
        if embedding_provider is None:
            embedding_provider = build_embedding_provider(settings)
        researcher = build_researcher(settings, client=research_client)
        outreach_context = SqlAlchemyOutreachContextProvider(session_factory, embedding_provider)
        tools = build_agent_tools(
            lambda: cast(UnitOfWorkScope, _uow_factory(session_factory)),
            clock,
        )
        if not is_legacy:
            tools = build_agent_tools(
                lambda: cast(UnitOfWorkScope, _uow_factory(session_factory)),
                clock,
                outreach_uow_factory=cast(
                    Callable[[], OutreachUnitOfWorkScope],
                    outreach_read_scope_factory(session_factory),
                ),
                researcher=researcher,
                outreach_context=outreach_context,
                outreach_gateway=llm_gateway,
            )
        deps = AgentGraphDependencies(
            uow_factory=lambda: cast(UnitOfWorkScope, _uow_factory(session_factory)),
            llm_gateway=llm_gateway,
            clock=clock,
            graph_version=selected_graph_version,
            prompt_version=selected_prompt_version,
            tool_runtime=BoundedAgentToolRuntime(
                gateway=llm_gateway,
                tools=tools,
                prompt_builder=(
                    load_legacy_agent_tool_runtime_prompt
                    if is_legacy
                    else load_agent_tool_runtime_prompt
                ),
            ),
            checkpointed_runtime=not is_legacy,
        )
        async with open_checkpointer(settings.postgres_dsn) as checkpointer:
            graph = build_agent_graph(deps, checkpointer)
            yield AgentGraphRunner(
                graph=graph,
                runs=SqlAlchemyAgentRunJournal(session_factory),
                clock=clock,
                graph_version=selected_graph_version,
                prompt_version=selected_prompt_version,
                model_config_json=dict(llm_gateway.configuration_snapshot()),
            )
    finally:
        if research_client is not None:
            await research_client.aclose()


@asynccontextmanager
async def _uow_factory(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[SqlAlchemyUnitOfWork]:
    async with session_factory() as session:
        yield SqlAlchemyUnitOfWork(session)
