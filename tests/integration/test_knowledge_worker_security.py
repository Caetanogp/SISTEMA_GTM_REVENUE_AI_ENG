"""Integration evidence that worker audit records redact unexpected failures."""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from revops.application.dto import EmbeddingBatch
from revops.domain.entities.knowledge import KnowledgeVersionStatus
from revops.infrastructure.persistence.models import (
    KnowledgeDocumentVersion,
    KnowledgeProcessingEvent,
)
from revops.infrastructure.queue.knowledge import KnowledgeWorkerProcessor
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests.integration.test_knowledge_worker import TestClock, _create_confirmed_version


class _UnexpectedSecretProvider:
    model = "test-unexpected-secret"
    dimension = 1536

    async def embed(self, texts: Sequence[str]) -> EmbeddingBatch:
        raise RuntimeError("https://example.invalid/embed?api_key=raw-secret-value")


@pytest.mark.integration
async def test_worker_does_not_persist_unexpected_exception_secret(
    database_url: str,
) -> None:
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as setup:
            corpus_id, version_id, _ = await _create_confirmed_version(
                setup, content="A document whose provider raises an untrusted error."
            )

        result = await KnowledgeWorkerProcessor(
            sessions, _UnexpectedSecretProvider(), TestClock()
        ).process(
            corpus_id=corpus_id,
            version_id=version_id,
            delivery_id=f"secret-error-{version_id}",
            attempt=1,
            terminal_attempt=True,
        )

        assert result.status is KnowledgeVersionStatus.FAILED
        assert result.failure_code == "embedding_provider_error"
        async with sessions() as verify:
            version = await verify.get(KnowledgeDocumentVersion, version_id)
            events = (
                (
                    await verify.execute(
                        select(KnowledgeProcessingEvent).where(
                            KnowledgeProcessingEvent.version_id == version_id
                        )
                    )
                )
                .scalars()
                .all()
            )

        assert version is not None
        assert version.failure_code == "embedding_provider_error"
        assert {event.failure_code for event in events} <= {
            None,
            "embedding_provider_error",
        }
        assert all("raw-secret-value" not in str(event.failure_code) for event in events)
    finally:
        await engine.dispose()
