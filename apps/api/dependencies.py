"""FastAPI dependencies for the API composition root."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated, cast

import httpx
from fastapi import Depends, Request
from revops.application.ports import (
    DeduplicationUnitOfWork,
    DeduplicationUnitOfWorkFactory,
    EmbeddingProvider,
    IngestionUnitOfWork,
    IngestionUnitOfWorkFactory,
    KnowledgeUnitOfWork,
    KnowledgeUnitOfWorkFactory,
    LLMGateway,
)
from revops.application.use_cases.retrieve_knowledge import RetrieveKnowledge
from revops.infrastructure.llm.gateway import build_live_gateway
from revops.infrastructure.persistence.ingestion_unit_of_work import SqlAlchemyIngestionUnitOfWork
from revops.infrastructure.persistence.knowledge_repositories import (
    SqlAlchemyKnowledgeRetrievalRepository,
)
from revops.infrastructure.persistence.knowledge_unit_of_work import SqlAlchemyKnowledgeUnitOfWork
from revops.infrastructure.persistence.unit_of_work import SqlAlchemyDeduplicationUnitOfWork
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .runtime import UnconfiguredLLMGateway, build_embedding_provider
from .settings import ApiSettings


async def get_session_factory(
    request: Request,
) -> async_sessionmaker[AsyncSession]:
    return cast(async_sessionmaker[AsyncSession], request.app.state.session_factory)


async def get_settings(request: Request) -> ApiSettings:
    return cast(ApiSettings, request.app.state.settings)


async def get_llm_gateway(request: Request) -> LLMGateway:
    return cast(LLMGateway, request.app.state.llm_gateway)


async def get_embedding_provider(request: Request) -> EmbeddingProvider:
    provider = request.app.state.embedding_provider
    if provider is None:
        settings = await get_settings(request)
        client = httpx.AsyncClient() if settings.knowledge_embedding_provider == "openai" else None
        request.app.state.embedding_client = client
        provider = build_embedding_provider(settings, client=client)
        request.app.state.embedding_provider = provider
    return cast(EmbeddingProvider, provider)


async def get_session(
    request: Request,
) -> AsyncIterator[AsyncSession]:
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        yield session


def retrieval_use_case(
    session: Annotated[AsyncSession, Depends(get_session)],
    embeddings: Annotated[EmbeddingProvider, Depends(get_embedding_provider)],
) -> RetrieveKnowledge:
    """Compose retrieval with a request-scoped session and configured provider."""
    return RetrieveKnowledge(SqlAlchemyKnowledgeRetrievalRepository(session), embeddings)


def ingestion_uow_factory(request: Request) -> IngestionUnitOfWorkFactory:
    session_factory = request.app.state.session_factory

    def factory() -> IngestionUnitOfWork:
        return SqlAlchemyIngestionUnitOfWork(session_factory())

    return factory


def deduplication_uow_factory(request: Request) -> DeduplicationUnitOfWorkFactory:
    session_factory = request.app.state.session_factory

    def factory() -> DeduplicationUnitOfWork:
        return cast(
            DeduplicationUnitOfWork,
            SqlAlchemyDeduplicationUnitOfWork(session_factory(), close_on_exit=True),
        )

    return factory


def knowledge_uow_factory(request: Request) -> KnowledgeUnitOfWorkFactory:
    session_factory = request.app.state.session_factory

    def factory() -> KnowledgeUnitOfWork:
        return SqlAlchemyKnowledgeUnitOfWork(session_factory(), close_on_exit=True)

    return factory


def default_llm_gateway(settings: ApiSettings) -> LLMGateway:
    if settings.llm_gateway_mode == "live":
        return build_live_gateway(settings)
    return UnconfiguredLLMGateway()
