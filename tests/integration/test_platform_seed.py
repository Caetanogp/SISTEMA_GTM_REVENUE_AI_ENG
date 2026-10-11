"""Isolated PostgreSQL evidence for the deployment-only platform seed."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from revops.application.use_cases.knowledge import PLATFORM_SEED_ACTOR_ID, SeedPlatformKnowledge
from revops.domain.entities.knowledge import (
    KnowledgeCategory,
    KnowledgeDocument,
    KnowledgeFormat,
    KnowledgeLanguage,
    KnowledgeScope,
)
from revops.infrastructure.embeddings.providers import DeterministicFakeEmbeddingProvider
from revops.infrastructure.knowledge_seed.manifest import PLATFORM_SEED_MANIFEST
from revops.infrastructure.persistence.knowledge_repositories import (
    SqlAlchemyKnowledgeDocumentRepository,
)
from revops.infrastructure.persistence.knowledge_unit_of_work import SqlAlchemyKnowledgeUnitOfWork
from revops.infrastructure.persistence.models import (
    KnowledgeCorpus,
    KnowledgeRevision,
    KnowledgeRevisionActivation,
    Organization,
    User,
)
from revops.infrastructure.persistence.models import (
    KnowledgeDocumentVersion as KnowledgeDocumentVersionModel,
)
from revops.infrastructure.queue.knowledge import KnowledgeWorkerProcessor
from sqlalchemy import Connection, create_engine, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PRE_SEED_REVISION = "f0a1b2c3d4e5"


class _Clock:
    def now(self) -> datetime:
        return datetime.now(UTC)


@pytest.fixture
def event_loop_policy() -> asyncio.AbstractEventLoopPolicy:
    if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
        return asyncio.WindowsSelectorEventLoopPolicy()
    return asyncio.get_event_loop_policy()


class _Dispatcher:
    def __init__(self) -> None:
        self.calls: list[tuple[UUID, UUID]] = []

    async def publish(self, *, corpus_id: UUID, version_id: UUID) -> None:
        self.calls.append((corpus_id, version_id))


def _config(connection: Connection, schema: str) -> Config:
    config = Config()
    config.set_main_option(
        "script_location",
        str(_REPO_ROOT / "packages/core/revops/infrastructure/persistence/migrations"),
    )
    config.attributes["connection"] = connection
    config.attributes["version_table_schema"] = schema
    return config


@contextmanager
def _isolated_schema(database_url: str) -> Iterator[tuple[str, Connection, Config]]:
    """Migrate one owned schema without writing platform seed records to public."""
    engine = create_engine(database_url)
    schema = f"platform_seed_{uuid4().hex}"
    with engine.connect() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(text(f'SET search_path TO "{schema}", public'))
        connection.commit()
        original_default_schema = connection.dialect.default_schema_name
        connection.dialect.default_schema_name = schema
        try:
            yield schema, connection, _config(connection, schema)
        finally:
            connection.rollback()
            connection.dialect.default_schema_name = original_default_schema
            connection.execute(text("SET search_path TO public"))
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            connection.commit()
    engine.dispose()


def _schema_url(database_url: str, schema: str) -> str:
    separator = "&" if "?" in database_url else "?"
    return f"{database_url}{separator}options=-csearch_path%3D{schema}%2Cpublic"


@pytest.fixture
async def seeded_database(
    database_url: str,
) -> AsyncIterator[tuple[async_sessionmaker[AsyncSession], _Dispatcher]]:
    with _isolated_schema(database_url) as (schema, _connection, config):
        command.upgrade(config, "head")
        engine = create_async_engine(_schema_url(database_url, schema))
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        dispatcher = _Dispatcher()
        try:
            yield sessions, dispatcher
        finally:
            await engine.dispose()


def _uow_factory(
    sessions: async_sessionmaker[AsyncSession],
) -> SqlAlchemyKnowledgeUnitOfWork:
    return SqlAlchemyKnowledgeUnitOfWork(sessions(), close_on_exit=True)


@pytest.mark.asyncio
async def test_platform_seed_serializes_replay_and_publishes_system_attribution(
    seeded_database: tuple[async_sessionmaker[AsyncSession], _Dispatcher],
) -> None:
    sessions, dispatcher = seeded_database
    seed = SeedPlatformKnowledge(lambda: _uow_factory(sessions), dispatcher, _Clock())

    first, second = await asyncio.gather(
        seed.execute(manifest=PLATFORM_SEED_MANIFEST),
        seed.execute(manifest=PLATFORM_SEED_MANIFEST),
    )

    assert first.corpus_id == second.corpus_id
    assert len(first.reserved_version_ids) + len(second.reserved_version_ids) == len(
        PLATFORM_SEED_MANIFEST
    )
    assert {version_id for _, version_id in dispatcher.calls} == set(
        first.reserved_version_ids + second.reserved_version_ids + second.redispatched_version_ids
    )

    processor = KnowledgeWorkerProcessor(sessions, DeterministicFakeEmbeddingProvider(), _Clock())
    reserved = first.reserved_version_ids + second.reserved_version_ids
    for version_id in reserved:
        result = await processor.process(
            corpus_id=first.corpus_id,
            version_id=version_id,
            delivery_id=f"platform-seed-{version_id}",
            attempt=1,
            terminal_attempt=False,
        )
        assert result.status.value == "ready"

    replay = await seed.execute(manifest=PLATFORM_SEED_MANIFEST)
    assert set(replay.ready_version_ids) == set(reserved)
    assert replay.reserved_version_ids == ()

    async with sessions() as session:
        corpus = await session.get(KnowledgeCorpus, first.corpus_id)
        versions = (
            (
                await session.execute(
                    select(KnowledgeDocumentVersionModel).where(
                        KnowledgeDocumentVersionModel.corpus_id == first.corpus_id
                    )
                )
            )
            .scalars()
            .all()
        )
        revisions = (
            (
                await session.execute(
                    select(KnowledgeRevision).where(KnowledgeRevision.corpus_id == first.corpus_id)
                )
            )
            .scalars()
            .all()
        )
        activations = (
            (
                await session.execute(
                    select(KnowledgeRevisionActivation).where(
                        KnowledgeRevisionActivation.corpus_id == first.corpus_id
                    )
                )
            )
            .scalars()
            .all()
        )

    assert corpus is not None
    assert corpus.scope == KnowledgeScope.PLATFORM.value
    assert corpus.organization_id is None
    assert len(versions) == len(PLATFORM_SEED_MANIFEST)
    assert all(
        row.requested_by is None
        and row.requested_by_system == PLATFORM_SEED_ACTOR_ID
        and row.seed_revision == 1
        for row in versions
    )
    assert revisions
    assert all(row.activated_by_system == PLATFORM_SEED_ACTOR_ID for row in revisions)
    assert activations
    assert all(row.activated_by_system == PLATFORM_SEED_ACTOR_ID for row in activations)


@pytest.mark.asyncio
async def test_platform_seed_leaves_same_key_tenant_document_tenant_owned(
    seeded_database: tuple[async_sessionmaker[AsyncSession], _Dispatcher],
) -> None:
    sessions, dispatcher = seeded_database
    seed = SeedPlatformKnowledge(lambda: _uow_factory(sessions), dispatcher, _Clock())
    platform = await seed.execute(manifest=PLATFORM_SEED_MANIFEST)
    organization_id, user_id, corpus_id = uuid4(), uuid4(), uuid4()
    async with sessions() as session:
        session.add(Organization(id=organization_id, name="Tenant isolation"))
        session.add(
            User(
                id=user_id,
                organization_id=organization_id,
                email="tenant@example.test",
                role="admin",
            )
        )
        await session.flush()
        session.add(
            KnowledgeCorpus(
                id=corpus_id,
                scope=KnowledgeScope.ORGANIZATION.value,
                organization_id=organization_id,
                created_at=datetime.now(UTC),
            )
        )
        await session.flush()
        tenant_version = await SqlAlchemyKnowledgeDocumentRepository(session).reserve_draft(
            corpus_id=corpus_id,
            requested_by=user_id,
            document=KnowledgeDocument(
                document_key="product/platform-overview",
                category=KnowledgeCategory.PRODUCT,
                language=KnowledgeLanguage.PORTUGUESE,
                format=KnowledgeFormat.MARKDOWN,
                scope=KnowledgeScope.ORGANIZATION,
                content="# Tenant override",
                metadata={"source": "integration-test"},
            ),
            idempotency_key="tenant-platform-key",
            created_at=datetime.now(UTC),
        )
        await session.commit()

    assert tenant_version.corpus_id != platform.corpus_id
    async with sessions() as session:
        row = await session.get(KnowledgeDocumentVersionModel, tenant_version.id)
    assert row is not None
    assert row.organization_id == organization_id
    assert row.requested_by == user_id
    assert row.requested_by_system is None
    assert row.seed_revision is None


def test_platform_seed_migration_allows_pre_seed_downgrade_and_blocks_post_seed(
    database_url: str,
) -> None:
    with _isolated_schema(database_url) as (schema, connection, config):
        command.upgrade(config, "head")
        command.downgrade(config, _PRE_SEED_REVISION)
        command.upgrade(config, "head")

        connection.execute(
            text(
                """
                INSERT INTO knowledge_corpora (id, scope, organization_id, created_at)
                VALUES (:id, 'platform', NULL, now())
                """
            ),
            {"id": str(uuid4())},
        )
        corpus_id = connection.execute(
            text("SELECT id FROM knowledge_corpora WHERE scope = 'platform'")
        ).scalar_one()
        document_id = uuid4()
        connection.execute(
            text(
                """
                INSERT INTO knowledge_documents (id, corpus_id, document_key, created_at)
                VALUES (:id, :corpus_id, 'product/downgrade-proof', now())
                """
            ),
            {"id": str(document_id), "corpus_id": corpus_id},
        )
        connection.execute(
            text(
                """
                INSERT INTO knowledge_document_versions (
                    id, document_id, corpus_id, requested_by, requested_by_system,
                    seed_revision, category, language, format, scope, content, metadata,
                    content_hash, status, idempotency_key, created_at, updated_at
                ) VALUES (
                    :id, :document_id, :corpus_id, NULL, :actor, 1, 'product', 'pt', 'md',
                    'platform', 'approved', '{}'::jsonb, :hash, 'confirmed', 'migration-proof',
                    now(), now()
                )
                """
            ),
            {
                "id": str(uuid4()),
                "document_id": str(document_id),
                "corpus_id": corpus_id,
                "actor": str(PLATFORM_SEED_ACTOR_ID),
                "hash": "a" * 64,
            },
        )
        connection.commit()

        with pytest.raises(Exception, match="platform_seed_downgrade_blocked"):
            command.downgrade(config, _PRE_SEED_REVISION)

        assert (
            connection.execute(
                text(f'SELECT version_num FROM "{schema}".alembic_version')
            ).scalar_one()
            == "c4d5e6f7a8b9"
        )
