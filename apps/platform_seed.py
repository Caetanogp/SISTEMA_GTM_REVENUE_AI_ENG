"""Deployment-only composition root for the approved platform knowledge seed."""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from celery import Celery
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from revops.application.use_cases.knowledge import PlatformSeedResult, SeedPlatformKnowledge
from revops.infrastructure.knowledge_seed.manifest import PLATFORM_SEED_MANIFEST
from revops.infrastructure.persistence.knowledge_unit_of_work import SqlAlchemyKnowledgeUnitOfWork
from revops.infrastructure.queue.celery import CeleryKnowledgeDispatcher, create_celery_app
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


class UtcClock:
    """Provide UTC timestamps without importing an application composition root."""

    def now(self) -> datetime:
        return datetime.now(UTC)


class PlatformSeedSettings(BaseSettings):
    """Minimal deployment settings, intentionally matching the worker's broker aliases."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    database_url: str = Field(
        default="postgresql+psycopg://revops:revops@localhost:5432/revops",
        alias="DATABASE_URL",
    )
    broker_url: str = Field(default="redis://localhost:6379/1", alias="CELERY_BROKER_URL")
    result_backend: str = Field(default="redis://localhost:6379/2", alias="CELERY_RESULT_BACKEND")
    # Deliberately unused by this command: accepting the alias makes its configuration surface
    # consistent with the worker without accepting an operator-provided seed payload.
    openai_api_key: SecretStr | None = Field(default=None, alias="OPENAI_API_KEY")


@dataclass(frozen=True, slots=True)
class PlatformSeedCliResult:
    """Safe printable outcome: only stable identifiers and counts."""

    corpus_id: UUID
    reserved_count: int
    redispatched_count: int
    ready_count: int


def _uow_factory(
    session_factory: async_sessionmaker[AsyncSession],
) -> SqlAlchemyKnowledgeUnitOfWork:
    return SqlAlchemyKnowledgeUnitOfWork(session_factory(), close_on_exit=True)


async def run_platform_seed(
    *, settings: PlatformSeedSettings, celery_app: Celery | None = None
) -> PlatformSeedCliResult:
    """Validate, reserve, commit, and only then dispatch the immutable source manifest."""
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        broker = celery_app or create_celery_app(
            broker_url=settings.broker_url,
            result_backend=settings.result_backend,
        )
        result: PlatformSeedResult = await SeedPlatformKnowledge(
            lambda: _uow_factory(session_factory),
            CeleryKnowledgeDispatcher(broker),
            UtcClock(),
        ).execute(manifest=PLATFORM_SEED_MANIFEST)
        return PlatformSeedCliResult(
            corpus_id=result.corpus_id,
            reserved_count=len(result.reserved_version_ids),
            redispatched_count=len(result.redispatched_version_ids),
            ready_count=len(result.ready_version_ids),
        )
    finally:
        await engine.dispose()


def _run_async(*, settings: PlatformSeedSettings) -> PlatformSeedCliResult:
    coroutine = run_platform_seed(settings=settings)
    if sys.platform != "win32":
        return asyncio.run(coroutine)
    with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
        return runner.run(coroutine)


def main(argv: list[str] | None = None) -> int:
    """Run with no arguments; never render exception text that could contain source or secrets."""
    if argv is None:
        argv = sys.argv[1:]
    if argv:
        print("platform_seed_invalid_arguments", file=sys.stderr)  # noqa: T201
        return 2
    try:
        result = _run_async(settings=PlatformSeedSettings())
    except Exception:
        print("platform_seed_failed", file=sys.stderr)  # noqa: T201
        return 1
    print(  # noqa: T201
        "platform_seed_success "
        f"corpus_id={result.corpus_id} "
        f"reserved={result.reserved_count} "
        f"redispatched={result.redispatched_count} "
        f"ready={result.ready_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
