"""Celery worker composition root for asynchronous ingestion."""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from uuid import UUID

from celery import Task
from celery.exceptions import Reject
from revops.application.dto import ProcessIngestionResult
from revops.application.ports import Clock, IngestionUnitOfWork, IngestionUnitOfWorkFactory
from revops.application.use_cases.ingestion import ProcessIngestionJob
from revops.infrastructure.ingestion import SyntheticEnrichmentGateway
from revops.infrastructure.persistence.ingestion_unit_of_work import (
    SqlAlchemyIngestionUnitOfWork,
)
from revops.infrastructure.queue import create_celery_app
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from apps.worker.settings import WorkerSettings


class UtcClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


settings = WorkerSettings()
celery_app = create_celery_app(
    broker_url=settings.broker_url,
    result_backend=settings.result_backend,
)
app = celery_app


def _uow_factory(
    session_factory: async_sessionmaker[AsyncSession],
) -> IngestionUnitOfWorkFactory:
    def create() -> IngestionUnitOfWork:
        return SqlAlchemyIngestionUnitOfWork(session_factory(), close_on_exit=True)

    return create


async def run_ingestion(
    *, organization_id: UUID, job_id: UUID, worker_settings: WorkerSettings
) -> ProcessIngestionResult:
    engine = create_async_engine(worker_settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    clock: Clock = UtcClock()
    try:
        return await ProcessIngestionJob(
            _uow_factory(session_factory),
            SyntheticEnrichmentGateway(),
            clock,
        ).execute(organization_id=organization_id, job_id=job_id)
    finally:
        await engine.dispose()


def _run_async_ingestion(*, organization_id: UUID, job_id: UUID) -> ProcessIngestionResult:
    coroutine = run_ingestion(
        organization_id=organization_id,
        job_id=job_id,
        worker_settings=settings,
    )
    if sys.platform != "win32":
        return asyncio.run(coroutine)
    with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
        return runner.run(coroutine)


def _process_ingestion_task(self: Task, *, organization_id: str, job_id: str) -> dict[str, object]:
    try:
        parsed_organization_id = UUID(organization_id)
        parsed_job_id = UUID(job_id)
    except ValueError as exc:
        raise Reject("invalid ingestion task identifiers", requeue=False) from exc

    try:
        result = _run_async_ingestion(
            organization_id=parsed_organization_id,
            job_id=parsed_job_id,
        )
    except Exception as exc:
        retry_number = int(self.request.retries)
        countdown = min(2**retry_number, 60)
        raise self.retry(exc=exc, countdown=countdown, max_retries=5) from exc
    return {
        "job_id": str(result.job_id),
        "status": result.status.value,
        "processed_domains": list(result.processed_domains),
    }


process_ingestion: Task = celery_app.task(
    bind=True,
    name="revops.ingestion.process",
    max_retries=5,
    acks_late=True,
    reject_on_worker_lost=True,
)(_process_ingestion_task)
