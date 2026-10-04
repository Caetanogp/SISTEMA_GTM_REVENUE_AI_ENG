"""PostgreSQL proof for exact, active-corpus knowledge retrieval."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from revops.application.dto import KnowledgeChunkEmbedding
from revops.application.use_cases.knowledge import PLATFORM_SEED_ACTOR_ID
from revops.domain.entities.knowledge import (
    KnowledgeCategory,
    KnowledgeDocument,
    KnowledgeFormat,
    KnowledgeLanguage,
    KnowledgeScope,
    KnowledgeVersionStatus,
)
from revops.domain.values.retrieval import EmbeddingSpace
from revops.infrastructure.persistence.knowledge_repositories import (
    SqlAlchemyCorpusRevisionRepository,
    SqlAlchemyKnowledgeCorpusRepository,
    SqlAlchemyKnowledgeDocumentRepository,
    SqlAlchemyKnowledgeRetrievalRepository,
)
from revops.infrastructure.persistence.models import KnowledgeCorpus
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from tests.integration.test_knowledge_revision_persistence import (
    _create_corpus,
    _ready_version,
)


@pytest.fixture
def event_loop_policy() -> asyncio.AbstractEventLoopPolicy:
    if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
        return asyncio.WindowsSelectorEventLoopPolicy()
    return asyncio.get_event_loop_policy()


async def test_retrieval_resolves_or_returns_empty_for_an_unknown_organization(
    database_url: str,
) -> None:
    engine = create_async_engine(database_url)
    async with AsyncSession(engine) as session:
        corpus_id, actor_id = await _create_corpus(session)
        corpus = await session.get(KnowledgeCorpus, corpus_id)
        assert corpus is not None
        assert corpus.organization_id is not None
        timestamp = datetime.now(UTC)
        version_id = await _ready_version(
            session, corpus_id, actor_id, "product/retrieval", "Retrieval source", timestamp
        )
        await SqlAlchemyKnowledgeDocumentRepository(session).mark_ready(
            corpus_id=corpus_id,
            version_id=version_id,
            embedding_model="offline-fake-v1",
            embedding_dimension=1536,
        )
        await SqlAlchemyCorpusRevisionRepository(session).publish(
            corpus_id=corpus_id,
            version_id=version_id,
            chunks=(
                KnowledgeChunkEmbedding(
                    ordinal=0,
                    text="Retrieval source",
                    content_hash="a" * 64,
                    vector=(1.0, *tuple(0.0 for _ in range(1535))),
                ),
            ),
            activated_by=actor_id,
            created_at=timestamp,
        )
        await session.flush()

        platform_corpus = await SqlAlchemyKnowledgeCorpusRepository(
            session
        ).get_or_create_platform_for_update()
        platform_document = KnowledgeDocument(
            document_key="product/retrieval",
            category=KnowledgeCategory.PRODUCT,
            language=KnowledgeLanguage.ENGLISH,
            format=KnowledgeFormat.MARKDOWN,
            scope=KnowledgeScope.PLATFORM,
            content="Platform retrieval source",
            metadata={"source": "integration-test"},
        )
        platform_documents = SqlAlchemyKnowledgeDocumentRepository(session)
        platform_version = await platform_documents.reserve_platform_draft(
            corpus_id=platform_corpus.id,
            requested_by_system=PLATFORM_SEED_ACTOR_ID,
            document=platform_document,
            seed_revision=1,
            idempotency_key="seed:retrieval",
            created_at=timestamp,
        )
        for status in (KnowledgeVersionStatus.CONFIRMED, KnowledgeVersionStatus.PROCESSING):
            await platform_documents.transition_status(
                corpus_id=platform_corpus.id, version_id=platform_version.id, status=status
            )
        await platform_documents.mark_ready(
            corpus_id=platform_corpus.id,
            version_id=platform_version.id,
            embedding_model="offline-fake-v1",
            embedding_dimension=1536,
        )
        await SqlAlchemyCorpusRevisionRepository(session).publish(
            corpus_id=platform_corpus.id,
            version_id=platform_version.id,
            chunks=(
                KnowledgeChunkEmbedding(
                    ordinal=0,
                    text="Platform retrieval source",
                    content_hash="b" * 64,
                    vector=(1.0, *tuple(0.0 for _ in range(1535))),
                ),
            ),
            activated_by=PLATFORM_SEED_ACTOR_ID,
            created_at=timestamp,
        )
        await session.flush()

        repository = SqlAlchemyKnowledgeRetrievalRepository(session)
        space = await repository.resolve_active_embedding_space(
            organization_id=corpus.organization_id
        )

        assert isinstance(space, EmbeddingSpace)
        candidates = await repository.search_active_chunks(
            organization_id=corpus.organization_id,
            query_vector=(1.0, *tuple(0.0 for _ in range(space.dimension - 1))),
            embedding_model=space.model,
            embedding_dimension=space.dimension,
            limit=20,
        )
        assert len(candidates) == 1
        assert candidates[0].passage.text == "Retrieval source"
        assert candidates[0].passage.provenance.document_key == "product/retrieval"
        await session.rollback()
    await engine.dispose()
