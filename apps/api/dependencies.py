"""FastAPI dependencies for the API composition root."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import cast

from fastapi import Request
from revops.application.ports import (
    DeduplicationUnitOfWork,
    DeduplicationUnitOfWorkFactory,
    IngestionUnitOfWork,
    IngestionUnitOfWorkFactory,
    KnowledgeUnitOfWork,
    KnowledgeUnitOfWorkFactory,
    LLMGateway,
)
from revops.infrastructure.llm.gateway import build_live_gateway
from revops.infrastructure.persistence.ingestion_unit_of_work import SqlAlchemyIngestionUnitOfWork
from revops.infrastructure.persistence.knowledge_unit_of_work import SqlAlchemyKnowledgeUnitOfWork
from revops.infrastructure.persistence.unit_of_work import SqlAlchemyDeduplicationUnitOfWork
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .runtime import UnconfiguredLLMGateway
from .settings import ApiSettings


async def get_session_factory(
    request: Request,
) -> async_sessionmaker[AsyncSession]:
    return cast(async_sessionmaker[AsyncSession], request.app.state.session_factory)


async def get_settings(request: Request) -> ApiSettings:
    return cast(ApiSettings, request.app.state.settings)


async def get_llm_gateway(request: Request) -> LLMGateway:
    return cast(LLMGateway, request.app.state.llm_gateway)


async def get_session(
    request: Request,
) -> AsyncIterator[AsyncSession]:
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        yield session


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
