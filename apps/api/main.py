"""FastAPI application entrypoint."""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from revops.application.ports import LLMGateway
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from .dependencies import default_llm_gateway
from .routes.agent_runs import router as agent_runs_router
from .routes.deduplication import router as deduplication_router
from .routes.health import router as health_router
from .routes.ingestion import router as ingestion_router
from .routes.knowledge import router as knowledge_router
from .runtime import build_embedding_provider
from .settings import ApiSettings


def _ensure_windows_selector_policy() -> None:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: ApiSettings = app.state.settings
    engine = create_async_engine(settings.database_url)
    app.state.engine = engine
    app.state.session_factory = async_sessionmaker(engine, expire_on_commit=False)
    embedding_client: httpx.AsyncClient | None = None
    try:
        if settings.knowledge_embedding_provider == "openai":
            embedding_client = httpx.AsyncClient()
        app.state.embedding_provider = build_embedding_provider(settings, client=embedding_client)
        yield
    finally:
        gateway = app.state.llm_gateway
        close = getattr(gateway, "aclose", None)
        if close is not None:
            await close()
        if embedding_client is not None:
            await embedding_client.aclose()
        await engine.dispose()


def create_app(
    *,
    settings: ApiSettings | None = None,
    llm_gateway: LLMGateway | None = None,
) -> FastAPI:
    _ensure_windows_selector_policy()
    app = FastAPI(title="RevOps Agent API", lifespan=lifespan)
    app.state.settings = settings or ApiSettings()
    app.state.llm_gateway = llm_gateway or default_llm_gateway(app.state.settings)
    app.include_router(agent_runs_router)
    app.include_router(ingestion_router)
    app.include_router(knowledge_router)
    app.include_router(deduplication_router)
    app.include_router(health_router)
    return app


app = create_app()
