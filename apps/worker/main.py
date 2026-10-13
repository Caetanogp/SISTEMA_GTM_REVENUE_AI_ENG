"""Celery worker composition root for asynchronous ingestion and deduplication."""

from __future__ import annotations

import asyncio
import platform
from datetime import UTC, datetime
from uuid import UUID

import httpx
from celery import Task
from celery.exceptions import Reject
from revops.application.dto import ProcessIngestionResult
from revops.application.ports import (
    Clock,
    EmbeddingProvider,
    IngestionUnitOfWork,
    IngestionUnitOfWorkFactory,
)
from revops.application.use_cases.ingestion import ProcessIngestionJob
from revops.infrastructure.embeddings.providers import (
    DeterministicFakeEmbeddingProvider,
    OpenAIEmbeddingProvider,
)
from revops.infrastructure.ingestion import SyntheticEnrichmentGateway
from revops.infrastructure.persistence.ingestion_unit_of_work import (
    SqlAlchemyIngestionUnitOfWork,
)
from revops.infrastructure.queue import (
    DEDUPLICATION_SCAN_TASK_NAME,
    KNOWLEDGE_PROCESSING_TASK_NAME,
    MAX_KNOWLEDGE_TASK_RETRIES,
    DeduplicationScanProcessor,
    KnowledgeWorkerError,
    KnowledgeWorkerProcessor,
    KnowledgeWorkerResult,
    KnowledgeWorkerRetryError,
    ProcessDeduplicationScanResult,
    create_celery_app,
)
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
    if platform.system() != "Windows":
        return asyncio.run(coroutine)
    with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
        return runner.run(coroutine)


async def run_deduplication_scan(
    *, organization_id: UUID, scan_id: UUID, worker_settings: WorkerSettings
) -> ProcessDeduplicationScanResult:
    engine = create_async_engine(worker_settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        return await DeduplicationScanProcessor(session_factory).process(
            organization_id=organization_id,
            scan_id=scan_id,
        )
    finally:
        await engine.dispose()


def _run_async_deduplication_scan(
    *, organization_id: UUID, scan_id: UUID
) -> ProcessDeduplicationScanResult:
    coroutine = run_deduplication_scan(
        organization_id=organization_id,
        scan_id=scan_id,
        worker_settings=settings,
    )
    if platform.system() != "Windows":
        return asyncio.run(coroutine)
    with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
        return runner.run(coroutine)


async def mark_deduplication_scan_failed(
    *, organization_id: UUID, scan_id: UUID, worker_settings: WorkerSettings
) -> bool:
    engine = create_async_engine(worker_settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        return await DeduplicationScanProcessor(session_factory).mark_failed(
            organization_id=organization_id,
            scan_id=scan_id,
        )
    finally:
        await engine.dispose()


def _run_async_mark_deduplication_scan_failed(*, organization_id: UUID, scan_id: UUID) -> bool:
    coroutine = mark_deduplication_scan_failed(
        organization_id=organization_id,
        scan_id=scan_id,
        worker_settings=settings,
    )
    if platform.system() != "Windows":
        return asyncio.run(coroutine)
    with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
        return runner.run(coroutine)


async def run_knowledge(
    *,
    corpus_id: UUID,
    version_id: UUID,
    delivery_id: str,
    attempt: int,
    terminal_attempt: bool,
    worker_settings: WorkerSettings,
) -> KnowledgeWorkerResult:
    engine = create_async_engine(worker_settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    clock: Clock = UtcClock()
    try:
        provider: EmbeddingProvider
        if worker_settings.knowledge_embedding_provider == "fake":
            provider = DeterministicFakeEmbeddingProvider(
                dimension=worker_settings.knowledge_embedding_dimension
            )
            return await KnowledgeWorkerProcessor(session_factory, provider, clock).process(
                corpus_id=corpus_id,
                version_id=version_id,
                delivery_id=delivery_id,
                attempt=attempt,
                terminal_attempt=terminal_attempt,
            )
        if worker_settings.knowledge_embedding_provider != "openai":
            raise KnowledgeWorkerError("embedding_configuration_invalid")
        if worker_settings.openai_api_key is None:
            raise KnowledgeWorkerError("embedding_configuration_missing")
        async with httpx.AsyncClient() as client:
            provider = OpenAIEmbeddingProvider(
                client=client,
                api_key=worker_settings.openai_api_key.get_secret_value(),
                model=worker_settings.knowledge_embedding_model,
                dimension=worker_settings.knowledge_embedding_dimension,
            )
            return await KnowledgeWorkerProcessor(session_factory, provider, clock).process(
                corpus_id=corpus_id,
                version_id=version_id,
                delivery_id=delivery_id,
                attempt=attempt,
                terminal_attempt=terminal_attempt,
            )
    finally:
        await engine.dispose()


def _run_async_knowledge(
    *,
    corpus_id: UUID,
    version_id: UUID,
    delivery_id: str,
    attempt: int,
    terminal_attempt: bool,
) -> KnowledgeWorkerResult:
    coroutine = run_knowledge(
        corpus_id=corpus_id,
        version_id=version_id,
        delivery_id=delivery_id,
        attempt=attempt,
        terminal_attempt=terminal_attempt,
        worker_settings=settings,
    )
    if platform.system() != "Windows":
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


def _process_deduplication_scan_task(
    self: Task, *, organization_id: str, scan_id: str
) -> dict[str, object]:
    try:
        parsed_organization_id = UUID(organization_id)
        parsed_scan_id = UUID(scan_id)
    except ValueError as exc:
        raise Reject("invalid deduplication task identifiers", requeue=False) from exc

    try:
        result = _run_async_deduplication_scan(
            organization_id=parsed_organization_id,
            scan_id=parsed_scan_id,
        )
    except Exception as exc:
        retry_number = int(self.request.retries)
        if retry_number >= 5:
            _run_async_mark_deduplication_scan_failed(
                organization_id=parsed_organization_id,
                scan_id=parsed_scan_id,
            )
            raise
        countdown = min(2**retry_number, 60)
        raise self.retry(exc=exc, countdown=countdown, max_retries=5) from exc
    return {
        "scan_id": str(result.scan_id),
        "status": result.status.value,
        "record_count": result.record_count,
        "candidate_count": result.candidate_count,
        "failure_code": result.failure_code,
    }


process_deduplication_scan: Task = celery_app.task(
    bind=True,
    name=DEDUPLICATION_SCAN_TASK_NAME,
    max_retries=5,
    acks_late=True,
    reject_on_worker_lost=True,
)(_process_deduplication_scan_task)


def _process_knowledge_task(self: Task, *, corpus_id: str, version_id: str) -> dict[str, object]:
    try:
        parsed_corpus_id = UUID(corpus_id)
        parsed_version_id = UUID(version_id)
    except ValueError as exc:
        raise Reject("invalid knowledge task identifiers", requeue=False) from exc

    delivery_id = str(self.request.id or f"local-knowledge-{parsed_version_id}")
    attempt = int(self.request.retries) + 1
    terminal_attempt = int(self.request.retries) >= MAX_KNOWLEDGE_TASK_RETRIES
    try:
        result = _run_async_knowledge(
            corpus_id=parsed_corpus_id,
            version_id=parsed_version_id,
            delivery_id=delivery_id,
            attempt=attempt,
            terminal_attempt=terminal_attempt,
        )
    except KnowledgeWorkerRetryError as exc:
        if int(self.request.retries) >= MAX_KNOWLEDGE_TASK_RETRIES:
            raise
        countdown = min(5 * (2 ** int(self.request.retries)), 60)
        raise self.retry(
            exc=KnowledgeWorkerRetryError(exc.failure_code),
            countdown=countdown,
            max_retries=MAX_KNOWLEDGE_TASK_RETRIES,
        ) from exc
    except KnowledgeWorkerError as exc:
        raise Reject(exc.failure_code, requeue=False) from exc

    if result.should_retry:
        countdown = min(5 * (2 ** int(self.request.retries)), 60)
        raise self.retry(
            exc=KnowledgeWorkerRetryError(result.failure_code or "knowledge_processing_retry"),
            countdown=countdown,
            max_retries=MAX_KNOWLEDGE_TASK_RETRIES,
        )
    return {
        "version_id": str(result.version_id),
        "status": result.status.value,
        "failure_code": result.failure_code,
    }


process_knowledge: Task = celery_app.task(
    bind=True,
    name=KNOWLEDGE_PROCESSING_TASK_NAME,
    max_retries=MAX_KNOWLEDGE_TASK_RETRIES,
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=900,
    time_limit=960,
)(_process_knowledge_task)
