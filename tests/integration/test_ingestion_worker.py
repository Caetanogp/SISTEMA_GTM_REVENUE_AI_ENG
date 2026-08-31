"""Live Redis/Celery proof for idempotent ingestion delivery."""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from celery.contrib.testing.worker import start_worker
from revops.domain.entities.ingestion import (
    AccountOutcome,
    ContactOutcome,
    EnrichmentOutcome,
    IngestionItemStatus,
    IngestionJobStatus,
)
from revops.infrastructure.persistence.models import (
    Account,
    AccountEnrichment,
    Contact,
    IngestionItem,
    IngestionJob,
    Organization,
    User,
)
from revops.infrastructure.queue import INGESTION_TASK_NAME
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.worker.main import celery_app


@pytest.fixture(scope="session")
def event_loop_policy() -> asyncio.AbstractEventLoopPolicy:
    if sys.platform != "win32":
        return asyncio.get_event_loop_policy()
    return asyncio.WindowsSelectorEventLoopPolicy()


@pytest.mark.integration
async def test_live_worker_duplicate_delivery_is_idempotent(database_url: str) -> None:
    engine = create_async_engine(database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    organization_id, actor_id, job_id, item_id = uuid4(), uuid4(), uuid4(), uuid4()
    now = datetime.now(UTC)
    async with session_factory() as session:
        session.add_all(
            [
                Organization(id=organization_id, name="Celery import org", demo_mode=True),
                User(
                    id=actor_id,
                    organization_id=organization_id,
                    email=f"{actor_id}@example.test",
                    role="admin",
                ),
            ]
        )
        await session.flush()
        session.add(
            IngestionJob(
                id=job_id,
                organization_id=organization_id,
                requested_by=actor_id,
                source="celery-test",
                idempotency_key=str(job_id),
                content_hash="b" * 64,
                status=IngestionJobStatus.QUEUED.value,
                created_at=now,
                updated_at=now,
            )
        )
        await session.flush()
        session.add(
            IngestionItem(
                id=item_id,
                ingestion_job_id=job_id,
                row_number=1,
                company_name="Worker Acme",
                domain=f"{organization_id}.example.test",
                email=f"contact-{organization_id}@example.test",
                full_name="Worker Contact",
                title="VP Revenue",
                validation_codes=[],
                status=IngestionItemStatus.PENDING.value,
                account_outcome=AccountOutcome.NOT_ATTEMPTED.value,
                contact_outcome=ContactOutcome.NOT_ATTEMPTED.value,
                enrichment_outcome=EnrichmentOutcome.NOT_ATTEMPTED.value,
            )
        )
        await session.commit()

    def deliver_twice() -> tuple[dict[str, object], dict[str, object]]:
        with start_worker(
            celery_app,
            pool="solo",
            perform_ping_check=False,
            loglevel="WARNING",
        ):
            kwargs = {"organization_id": str(organization_id), "job_id": str(job_id)}
            first = celery_app.send_task(INGESTION_TASK_NAME, kwargs=kwargs).get(timeout=20)
            second = celery_app.send_task(INGESTION_TASK_NAME, kwargs=kwargs).get(timeout=20)
            return first, second

    try:
        first, second = await asyncio.to_thread(deliver_twice)
        assert first["status"] == IngestionJobStatus.COMPLETED.value
        assert second["status"] == IngestionJobStatus.COMPLETED.value
        assert second["processed_domains"] == []
        async with session_factory() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(Account)
                    .where(Account.organization_id == organization_id)
                )
                == 1
            )
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(Contact)
                    .where(Contact.organization_id == organization_id)
                )
                == 1
            )
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(AccountEnrichment)
                    .where(AccountEnrichment.organization_id == organization_id)
                )
                == 1
            )
    finally:
        async with session_factory() as session:
            await session.execute(
                delete(IngestionItem).where(IngestionItem.ingestion_job_id == job_id)
            )
            await session.execute(
                delete(AccountEnrichment).where(AccountEnrichment.ingestion_job_id == job_id)
            )
            await session.execute(delete(Contact).where(Contact.organization_id == organization_id))
            await session.execute(delete(Account).where(Account.organization_id == organization_id))
            await session.execute(delete(IngestionJob).where(IngestionJob.id == job_id))
            await session.execute(delete(User).where(User.id == actor_id))
            await session.execute(delete(Organization).where(Organization.id == organization_id))
            await session.commit()
        await engine.dispose()
