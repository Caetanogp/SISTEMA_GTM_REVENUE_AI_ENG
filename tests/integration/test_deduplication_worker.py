"""Live Redis/Celery proof for bounded, replay-safe deduplication scans."""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from celery.contrib.testing.worker import start_worker
from revops.domain.entities.deduplication import (
    DeduplicationCandidateStatus,
    DeduplicationRecordType,
    DeduplicationScanStatus,
)
from revops.infrastructure.persistence.models import (
    Account,
    AccountDeduplicationCandidate,
    Contact,
    ContactDeduplicationCandidate,
    DeduplicationScan,
    Organization,
    User,
)
from revops.infrastructure.queue import (
    DEDUPLICATION_SCAN_TASK_NAME,
    DeduplicationScanLifecycle,
)
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.worker.main import celery_app


@pytest.fixture(scope="session")
def event_loop_policy() -> asyncio.AbstractEventLoopPolicy:
    if sys.platform != "win32":
        return asyncio.get_event_loop_policy()
    return asyncio.WindowsSelectorEventLoopPolicy()


@pytest.mark.integration
async def test_live_worker_completes_scan_and_replays_without_duplicate_candidates(
    database_url: str,
) -> None:
    engine = create_async_engine(database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    organization_id, actor_id, scan_id = uuid4(), uuid4(), uuid4()
    account_ids = (uuid4(), uuid4())
    contact_ids = (uuid4(), uuid4())
    now = datetime.now(UTC)
    async with session_factory() as session:
        session.add_all(
            [
                Organization(id=organization_id, name="Celery dedupe org", demo_mode=True),
                User(
                    id=actor_id,
                    organization_id=organization_id,
                    email=f"{actor_id}@example.test",
                    role="admin",
                ),
            ]
        )
        await session.flush()
        session.add_all(
            [
                Account(
                    id=account_ids[0],
                    organization_id=organization_id,
                    company_name="Replay Labs LLC",
                    domain=f"left-{scan_id}.example.test",
                    created_at=now,
                ),
                Account(
                    id=account_ids[1],
                    organization_id=organization_id,
                    company_name="Replay Labs Incorporated",
                    domain=f"right-{scan_id}.example.test",
                    created_at=now,
                ),
            ]
        )
        await session.flush()
        session.add_all(
            [
                Contact(
                    id=contact_ids[0],
                    organization_id=organization_id,
                    account_id=account_ids[0],
                    email=f"left-{scan_id}@example.test",
                    full_name="Replay Person",
                    title="Revenue Lead",
                    phone="+15555550101",
                ),
                Contact(
                    id=contact_ids[1],
                    organization_id=organization_id,
                    account_id=account_ids[0],
                    email=f"right-{scan_id}@example.test",
                    full_name="Replay Person",
                    title="Revenue Lead",
                    phone="+15555550101",
                ),
                DeduplicationScan(
                    id=scan_id,
                    organization_id=organization_id,
                    requested_by=actor_id,
                    record_types=[
                        DeduplicationRecordType.ACCOUNT.value,
                        DeduplicationRecordType.CONTACT.value,
                    ],
                    policy_version="dedupe_v1",
                    idempotency_key=str(scan_id),
                    status=DeduplicationScanStatus.QUEUED.value,
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
        await session.commit()

    lifecycle = DeduplicationScanLifecycle(session_factory)
    assert await lifecycle.mark_queue_failed(organization_id, scan_id) is True
    async with session_factory() as session:
        assert (
            await session.scalar(
                select(DeduplicationScan.status).where(DeduplicationScan.id == scan_id)
            )
            == DeduplicationScanStatus.QUEUE_FAILED.value
        )

    def deliver_twice() -> tuple[dict[str, object], dict[str, object]]:
        with start_worker(
            celery_app,
            pool="solo",
            perform_ping_check=False,
            loglevel="WARNING",
        ):
            kwargs = {"organization_id": str(organization_id), "scan_id": str(scan_id)}
            first = celery_app.send_task(DEDUPLICATION_SCAN_TASK_NAME, kwargs=kwargs).get(
                timeout=20
            )
            second = celery_app.send_task(DEDUPLICATION_SCAN_TASK_NAME, kwargs=kwargs).get(
                timeout=20
            )
            return first, second

    try:
        first, second = await asyncio.to_thread(deliver_twice)
        assert first["status"] == DeduplicationScanStatus.COMPLETED.value
        assert second["status"] == DeduplicationScanStatus.COMPLETED.value
        assert first["candidate_count"] == 2
        assert second["candidate_count"] == 2
        async with session_factory() as session:
            assert (
                await session.scalar(
                    select(DeduplicationScan.status).where(DeduplicationScan.id == scan_id)
                )
                == DeduplicationScanStatus.COMPLETED.value
            )
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(AccountDeduplicationCandidate)
                    .where(AccountDeduplicationCandidate.scan_id == scan_id)
                )
                == 1
            )
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(ContactDeduplicationCandidate)
                    .where(ContactDeduplicationCandidate.scan_id == scan_id)
                )
                == 1
            )
            statuses = set(
                (
                    await session.scalars(
                        select(AccountDeduplicationCandidate.status).where(
                            AccountDeduplicationCandidate.scan_id == scan_id
                        )
                    )
                ).all()
            ) | set(
                (
                    await session.scalars(
                        select(ContactDeduplicationCandidate.status).where(
                            ContactDeduplicationCandidate.scan_id == scan_id
                        )
                    )
                ).all()
            )
            assert statuses == {DeduplicationCandidateStatus.PENDING.value}
    finally:
        async with session_factory() as session:
            await session.execute(
                delete(AccountDeduplicationCandidate).where(
                    AccountDeduplicationCandidate.scan_id == scan_id
                )
            )
            await session.execute(
                delete(ContactDeduplicationCandidate).where(
                    ContactDeduplicationCandidate.scan_id == scan_id
                )
            )
            await session.execute(delete(DeduplicationScan).where(DeduplicationScan.id == scan_id))
            await session.execute(delete(Contact).where(Contact.organization_id == organization_id))
            await session.execute(delete(Account).where(Account.organization_id == organization_id))
            await session.execute(delete(User).where(User.id == actor_id))
            await session.execute(delete(Organization).where(Organization.id == organization_id))
            await session.commit()
        await engine.dispose()
