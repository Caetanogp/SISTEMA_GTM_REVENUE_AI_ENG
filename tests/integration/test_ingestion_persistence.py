"""Real PostgreSQL coverage for ingestion repositories and migration-backed schema."""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from revops.application.dto import CanonicalIngestionRecord, StagedIngestionItem, StagedIngestionJob
from revops.domain.entities.ingestion import (
    AccountOutcome,
    ContactOutcome,
    EnrichmentOutcome,
    IngestionItemStatus,
    IngestionJobStatus,
)
from revops.infrastructure.persistence.ingestion_repositories import (
    SqlAlchemyIngestionItemRepository,
    SqlAlchemyIngestionJobRepository,
)
from revops.infrastructure.persistence.models import Organization, User
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine


@pytest.fixture(scope="session")
def event_loop_policy() -> asyncio.AbstractEventLoopPolicy:
    if sys.platform != "win32":
        return asyncio.get_event_loop_policy()
    return asyncio.WindowsSelectorEventLoopPolicy()


@pytest.fixture
async def session(database_url: str) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(database_url)
    async with engine.connect() as connection:
        await connection.begin()
        value = AsyncSession(connection, join_transaction_mode="create_savepoint")
        yield value
        await value.close()
        await connection.rollback()
    await engine.dispose()


async def test_ingestion_repositories_round_trip_staged_rows_and_keep_tenants_isolated(
    session: AsyncSession,
) -> None:
    organization_id, other_organization_id, actor_id = uuid4(), uuid4(), uuid4()
    session.add_all(
        [
            Organization(id=organization_id, name="Import org", demo_mode=True),
            Organization(id=other_organization_id, name="Other org", demo_mode=True),
            User(
                id=actor_id,
                organization_id=organization_id,
                email="operator@example.test",
                role="admin",
            ),
        ]
    )
    await session.flush()
    item = StagedIngestionItem(
        row_number=1,
        record=CanonicalIngestionRecord("Acme", "acme.test", "ada@acme.test", "Ada", "CTO"),
        validation_codes=(),
        status=IngestionItemStatus.PENDING,
        account_outcome=AccountOutcome.NOT_ATTEMPTED,
        contact_outcome=ContactOutcome.NOT_ATTEMPTED,
        enrichment_outcome=EnrichmentOutcome.NOT_ATTEMPTED,
    )
    job = StagedIngestionJob(
        id=uuid4(),
        organization_id=organization_id,
        requested_by=actor_id,
        source="test",
        idempotency_key="key-1",
        content_hash="a" * 64,
        status=IngestionJobStatus.STAGED,
        items=(item,),
    )
    jobs, items = (
        SqlAlchemyIngestionJobRepository(session),
        SqlAlchemyIngestionItemRepository(session),
    )
    await jobs.add(job)
    await items.add_many(job.id, job.items)

    stored = await jobs.get_by_idempotency_key(organization_id, "key-1")
    assert stored == job
    assert await jobs.get(other_organization_id, job.id) is None
    assert await items.list_for_job(other_organization_id, job.id, offset=0, limit=10) == []
    assert await items.list_processable_domains(organization_id, job.id) == ["acme.test"]
    assert await items.lock_domain_items(organization_id, job.id, "acme.test") == [item]

    queued = await jobs.set_status(organization_id, job.id, IngestionJobStatus.QUEUED)
    assert queued.status is IngestionJobStatus.QUEUED
