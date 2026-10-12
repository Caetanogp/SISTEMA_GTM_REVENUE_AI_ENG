"""PostgreSQL proof for retry-safe knowledge processing and audit events."""

from __future__ import annotations

import asyncio
import platform
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from revops.application.dto import EmbeddingBatch
from revops.application.ports import EmbeddingProviderError
from revops.domain.entities.knowledge import (
    KnowledgeCategory,
    KnowledgeDocument,
    KnowledgeFormat,
    KnowledgeLanguage,
    KnowledgeScope,
    KnowledgeVersionStatus,
)
from revops.infrastructure.embeddings.providers import DeterministicFakeEmbeddingProvider
from revops.infrastructure.persistence.knowledge_repositories import (
    SqlAlchemyKnowledgeDocumentRepository,
)
from revops.infrastructure.persistence.models import (
    KnowledgeChunk,
    KnowledgeCorpus,
    KnowledgeCorpusHead,
    KnowledgeDocumentVersion,
    KnowledgeProcessingEvent,
    KnowledgeRevision,
    Organization,
    User,
)
from revops.infrastructure.queue.knowledge import KnowledgeWorkerProcessor
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from tests.integration.event_loop_policy import windows_selector_event_loop_policy


class FailingEmbeddingProvider:
    model = "test-failure"
    dimension = 1536

    async def embed(self, texts: Sequence[str]) -> EmbeddingBatch:
        raise EmbeddingProviderError("embedding_unavailable", retryable=True)


class TestClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


@pytest.fixture
def event_loop_policy() -> asyncio.AbstractEventLoopPolicy:
    if platform.system() == "Windows":
        return windows_selector_event_loop_policy()
    return asyncio.get_event_loop_policy()


async def _create_confirmed_version(
    session: AsyncSession, *, content: str
) -> tuple[UUID, UUID, UUID]:
    organization_id = uuid4()
    actor_id = uuid4()
    corpus_id = uuid4()
    session.add(Organization(id=organization_id, name="Worker test organization"))
    await session.flush()
    session.add(
        User(
            id=actor_id,
            organization_id=organization_id,
            email=f"{actor_id}@worker.test.invalid",
            role="admin",
        )
    )
    session.add(
        KnowledgeCorpus(
            id=corpus_id,
            scope=KnowledgeScope.ORGANIZATION.value,
            organization_id=organization_id,
            created_at=datetime.now(UTC),
        )
    )
    await session.flush()
    repository = SqlAlchemyKnowledgeDocumentRepository(session)
    version = await repository.reserve_draft(
        corpus_id=corpus_id,
        requested_by=actor_id,
        document=KnowledgeDocument(
            document_key="worker/test",
            category=KnowledgeCategory.PRODUCT,
            language=KnowledgeLanguage.ENGLISH,
            format=KnowledgeFormat.MARKDOWN,
            scope=KnowledgeScope.ORGANIZATION,
            content=content,
            metadata={"source": "integration-test"},
        ),
        idempotency_key=f"worker:{uuid4()}",
        created_at=datetime.now(UTC),
    )
    await repository.transition_status(
        corpus_id=corpus_id,
        version_id=version.id,
        status=KnowledgeVersionStatus.CONFIRMED,
    )
    await session.commit()
    return corpus_id, version.id, actor_id


@pytest.mark.asyncio
async def test_worker_publishes_ready_version_and_ignores_replay(
    database_url: str,
) -> None:
    engine = create_async_engine(database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as setup_session:
            corpus_id, version_id, _ = await _create_confirmed_version(
                setup_session, content="A worker-safe knowledge document."
            )

        processor = KnowledgeWorkerProcessor(
            session_factory,
            DeterministicFakeEmbeddingProvider(dimension=1536),
            TestClock(),
        )
        first = await processor.process(
            corpus_id=corpus_id,
            version_id=version_id,
            delivery_id=f"delivery-worker-1-{version_id}",
            attempt=1,
            terminal_attempt=False,
        )
        replay = await processor.process(
            corpus_id=corpus_id,
            version_id=version_id,
            delivery_id=f"delivery-worker-1-{version_id}",
            attempt=1,
            terminal_attempt=False,
        )

        assert first.status is KnowledgeVersionStatus.READY
        assert replay.status is KnowledgeVersionStatus.READY
        async with session_factory() as verify:
            version = await verify.get(KnowledgeDocumentVersion, version_id)
            assert version is not None
            assert version.status == KnowledgeVersionStatus.READY.value
            assert version.embedding_model == "offline-fake-v1"
            assert version.embedding_dimension == 1536
            assert (
                await verify.scalar(
                    select(func.count(KnowledgeChunk.id)).where(
                        KnowledgeChunk.version_id == version_id
                    )
                )
            ) == 1
            assert (
                await verify.scalar(
                    select(func.count(KnowledgeRevision.id)).where(
                        KnowledgeRevision.version_id == version_id
                    )
                )
            ) == 1
            assert await verify.get(KnowledgeCorpusHead, corpus_id) is not None
            event_types = {
                event.event_type
                for event in (
                    await verify.execute(
                        select(KnowledgeProcessingEvent).where(
                            KnowledgeProcessingEvent.version_id == version_id
                        )
                    )
                ).scalars()
            }
            assert event_types == {"started", "succeeded", "duplicate_ignored"}
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_worker_records_retry_then_terminal_failure_without_head(
    database_url: str,
) -> None:
    engine = create_async_engine(database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as setup_session:
            corpus_id, version_id, _ = await _create_confirmed_version(
                setup_session, content="A document whose provider will fail."
            )
        processor = KnowledgeWorkerProcessor(
            session_factory,
            FailingEmbeddingProvider(),
            TestClock(),
        )

        retry = await processor.process(
            corpus_id=corpus_id,
            version_id=version_id,
            delivery_id=f"delivery-worker-2-{version_id}",
            attempt=1,
            terminal_attempt=False,
        )
        terminal = await processor.process(
            corpus_id=corpus_id,
            version_id=version_id,
            delivery_id=f"delivery-worker-2-{version_id}",
            attempt=2,
            terminal_attempt=True,
        )

        assert retry.should_retry is True
        assert retry.status is KnowledgeVersionStatus.PROCESSING
        assert terminal.status is KnowledgeVersionStatus.FAILED
        async with session_factory() as verify:
            version = await verify.get(KnowledgeDocumentVersion, version_id)
            assert version is not None
            assert version.failure_code == "embedding_unavailable"
            assert await verify.get(KnowledgeCorpusHead, corpus_id) is None
            events = (
                await verify.execute(
                    select(KnowledgeProcessingEvent)
                    .where(KnowledgeProcessingEvent.version_id == version_id)
                    .order_by(KnowledgeProcessingEvent.attempt)
                )
            ).scalars()
            assert [event.event_type for event in events] == [
                "started",
                "retry_scheduled",
                "started",
                "failed",
            ]
    finally:
        await engine.dispose()
