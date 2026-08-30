"""FastAPI dependencies for the API composition root."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import cast

from fastapi import Request
from revops.application.ports import LLMGateway
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


def default_llm_gateway() -> LLMGateway:
    return UnconfiguredLLMGateway()
