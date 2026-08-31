"""FastAPI application entrypoint."""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from revops.application.ports import LLMGateway
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from .dependencies import default_llm_gateway
from .routes.agent_runs import router as agent_runs_router
from .routes.ingestion import router as ingestion_router
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
    try:
        yield
    finally:
        await engine.dispose()


def create_app(
    *,
    settings: ApiSettings | None = None,
    llm_gateway: LLMGateway | None = None,
) -> FastAPI:
    _ensure_windows_selector_policy()
    app = FastAPI(title="RevOps Agent API", lifespan=lifespan)
    app.state.settings = settings or ApiSettings()
    app.state.llm_gateway = llm_gateway or default_llm_gateway()
    app.include_router(agent_runs_router)
    app.include_router(ingestion_router)
    return app


app = create_app()
