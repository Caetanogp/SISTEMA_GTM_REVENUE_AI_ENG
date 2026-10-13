"""PostgreSQL proof for complete corpus snapshots and activation history."""

from __future__ import annotations

import asyncio
import platform
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from revops.application.dto import KnowledgeChunkEmbedding
from revops.domain.entities.knowledge import (
    KnowledgeCategory,
    KnowledgeDocument,
    KnowledgeFormat,
    KnowledgeLanguage,
    KnowledgeScope,
    KnowledgeVersionStatus,
)
from revops.infrastructure.persistence.knowledge_repositories import (
    SqlAlchemyCorpusRevisionRepository,
    SqlAlchemyKnowledgeDocumentRepository,
)
from revops.infrastructure.persistence.models import (
    KnowledgeCorpus,
    KnowledgeRevisionEntry,
    Organization,
    User,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from tests.integration.event_loop_policy import windows_selector_event_loop_policy


@pytest.fixture
def event_loop_policy() -> asyncio.AbstractEventLoopPolicy:
    if platform.system() == "Windows":
        return windows_selector_event_loop_policy()
    return asyncio.get_event_loop_policy()


def _document(key: str, content: str) -> KnowledgeDocument:
    return KnowledgeDocument(
        document_key=key,
        category=KnowledgeCategory.PRODUCT,
        language=KnowledgeLanguage.ENGLISH,
        format=KnowledgeFormat.MARKDOWN,
        scope=KnowledgeScope.ORGANIZATION,
        content=content,
        metadata={"source": "integration-test"},
    )


def _chunk(content: str) -> tuple[KnowledgeChunkEmbedding, ...]:
    return (
        KnowledgeChunkEmbedding(
            ordinal=0,
            text=content,
            content_hash="a" * 64,
            vector=(0.0,) * 1536,
        ),
    )


async def _ready_version(
    session: AsyncSession,
    corpus_id: UUID,
    actor_id: UUID,
    key: str,
    content: str,
    stamp: datetime,
) -> UUID:
    repository = SqlAlchemyKnowledgeDocumentRepository(session)
    version = await repository.reserve_draft(
        corpus_id=corpus_id,
        requested_by=actor_id,
        document=_document(key, content),
        idempotency_key=f"draft:{key}:{content}",
        created_at=stamp,
    )
    for status in (
        KnowledgeVersionStatus.CONFIRMED,
        KnowledgeVersionStatus.PROCESSING,
        KnowledgeVersionStatus.READY,
    ):
        await repository.transition_status(
            corpus_id=corpus_id, version_id=version.id, status=status
        )
    return version.id


@pytest.fixture
async def knowledge_session(database_url: str) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        session = AsyncSession(connection, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            await session.close()
    await engine.dispose()


async def _create_corpus(session: AsyncSession) -> tuple[UUID, UUID]:
    organization_id = uuid4()
    actor_id = uuid4()
    corpus_id = uuid4()
    session.add(Organization(id=organization_id, name="Knowledge test organization"))
    await session.flush()
    session.add(
        User(
            id=actor_id,
            organization_id=organization_id,
            email=f"{actor_id}@test.invalid",
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
    return corpus_id, actor_id


@pytest.mark.asyncio
async def test_publication_builds_complete_snapshot_and_reuses_it(
    knowledge_session: AsyncSession,
) -> None:
    corpus_id, actor_id = await _create_corpus(knowledge_session)
    stamp = datetime.now(UTC)
    first_id = await _ready_version(
        knowledge_session, corpus_id, actor_id, "product/a", "A1", stamp
    )
    second_id = await _ready_version(
        knowledge_session, corpus_id, actor_id, "product/b", "B1", stamp
    )
    revisions = SqlAlchemyCorpusRevisionRepository(knowledge_session)

    first = await revisions.publish(
        corpus_id=corpus_id,
        version_id=first_id,
        chunks=_chunk("A1"),
        activated_by=actor_id,
        created_at=stamp,
    )
    second = await revisions.publish(
        corpus_id=corpus_id,
        version_id=second_id,
        chunks=_chunk("B1"),
        activated_by=actor_id,
        created_at=stamp,
    )
    historical = await revisions.activate(
        corpus_id=corpus_id,
        revision_id=first.id,
        activated_by=actor_id,
        idempotency_key="activate:product-a-1",
        created_at=stamp,
    )
    repeated = await revisions.activate(
        corpus_id=corpus_id,
        revision_id=first.id,
        activated_by=actor_id,
        idempotency_key="activate:product-a-1",
        created_at=stamp,
    )
    history = await revisions.list_activation_history(corpus_id, offset=0, limit=20)

    assert first.id != second.id
    assert historical.id == first.id
    assert repeated.id == historical.id
    assert len(history) == 3
    assert sum(event.target_version_id == first.version_id for event in history) == 2
    entries = (
        (
            await knowledge_session.execute(
                select(KnowledgeRevisionEntry).where(
                    KnowledgeRevisionEntry.revision_id == second.id
                )
            )
        )
        .scalars()
        .all()
    )
    assert {entry.document_key for entry in entries} == {"product/a", "product/b"}


@pytest.mark.asyncio
async def test_activation_idempotency_conflict_is_rejected(knowledge_session: AsyncSession) -> None:
    corpus_id, actor_id = await _create_corpus(knowledge_session)
    stamp = datetime.now(UTC)
    first_id = await _ready_version(
        knowledge_session, corpus_id, actor_id, "product/a", "A1", stamp
    )
    second_id = await _ready_version(
        knowledge_session, corpus_id, actor_id, "product/b", "B1", stamp
    )
    revisions = SqlAlchemyCorpusRevisionRepository(knowledge_session)
    await revisions.publish(
        corpus_id=corpus_id,
        version_id=first_id,
        chunks=_chunk("A1"),
        activated_by=actor_id,
        created_at=stamp,
    )
    second = await revisions.publish(
        corpus_id=corpus_id,
        version_id=second_id,
        chunks=_chunk("B1"),
        activated_by=actor_id,
        created_at=stamp,
    )

    with pytest.raises(ValueError, match="idempotency key conflicts"):
        await revisions.activate(
            corpus_id=corpus_id,
            revision_id=second.id,
            activated_by=actor_id,
            idempotency_key=f"publication:{first_id}",
            created_at=stamp,
        )
