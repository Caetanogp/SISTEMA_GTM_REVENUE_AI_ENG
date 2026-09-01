"""Real PostgreSQL coverage for the tenant-scoped deduplication persistence boundary."""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from revops.domain.entities.deduplication import DeduplicationRecordType, RecordAlias
from revops.domain.values.company_domain import CompanyDomain
from revops.infrastructure.persistence.models import Account, Organization, User
from revops.infrastructure.persistence.unit_of_work import SqlAlchemyDeduplicationUnitOfWork
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine


@pytest.fixture(scope="session")
def event_loop_policy() -> asyncio.AbstractEventLoopPolicy:
    if sys.platform == "win32":
        return asyncio.WindowsSelectorEventLoopPolicy()
    return asyncio.get_event_loop_policy()  # type: ignore[unreachable]
    # mypy specializes sys.platform to this Windows development host; the fallback keeps the
    # integration fixture portable for Linux CI, where the branch is reachable.


@pytest.fixture
async def session(database_url: str) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(database_url)
    async with engine.connect() as connection:
        await connection.begin()
        async_session = AsyncSession(connection, join_transaction_mode="create_savepoint")
        yield async_session
        await async_session.close()
        await connection.rollback()
    await engine.dispose()


async def _seed_actor(session: AsyncSession) -> tuple[UUID, UUID]:
    organization_id = uuid4()
    actor_id = uuid4()
    session.add(Organization(id=organization_id, name="Deduplication test", demo_mode=True))
    session.add(
        User(
            id=actor_id,
            organization_id=organization_id,
            email=f"{actor_id}@example.test",
            role="admin",
        )
    )
    await session.flush()
    return organization_id, actor_id


async def test_deduplication_repositories_round_trip_and_isolate_tenants(
    session: AsyncSession,
) -> None:
    organization_id, actor_id = await _seed_actor(session)
    other_organization_id, _ = await _seed_actor(session)
    scan_id = uuid4()

    uow = SqlAlchemyDeduplicationUnitOfWork(session)
    await uow.scans.add(
        organization_id,
        actor_id,
        scan_id,
        (DeduplicationRecordType.ACCOUNT, DeduplicationRecordType.CONTACT),
        "scan-key",
    )
    stored = await uow.scans.get(organization_id, scan_id)
    assert stored is not None
    assert stored.requested_by == actor_id
    assert await uow.scans.get(other_organization_id, scan_id) is None
    assert await uow.scans.get_by_idempotency_key(other_organization_id, "scan-key") is None

    alias_id, canonical_id, event_id = uuid4(), uuid4(), uuid4()
    occurred_at = datetime(2026, 8, 31, tzinfo=UTC)
    session.add_all(
        [
            Account(
                id=alias_id,
                organization_id=organization_id,
                company_name="Alias Co",
                domain=CompanyDomain("alias.test").value,
                created_at=occurred_at,
            ),
            Account(
                id=canonical_id,
                organization_id=organization_id,
                company_name="Canonical Co",
                domain=CompanyDomain("canonical.test").value,
                created_at=occurred_at,
            ),
        ]
    )
    await session.flush()
    await uow.events.add(
        {
            "id": str(event_id),
            "event_id": str(event_id),
            "organization_id": str(organization_id),
            "candidate_id": None,
            "action": "merge",
            "actor_id": str(actor_id),
            "idempotency_key": "merge-key",
            "occurred_at": occurred_at.isoformat(),
            "reason_code": "admin_reviewed",
        }
    )
    await uow.aliases.add(
        RecordAlias(
            organization_id,
            DeduplicationRecordType.ACCOUNT,
            alias_id,
            canonical_id,
            event_id,
            occurred_at,
        )
    )
    assert uow.canonical is not None
    resolved = await uow.canonical.resolve(
        organization_id, DeduplicationRecordType.ACCOUNT, alias_id
    )
    assert resolved is not None
    assert resolved.canonical_id == canonical_id
    assert resolved.member_ids == (canonical_id, alias_id)
    assert (
        await uow.canonical.resolve(
            other_organization_id, DeduplicationRecordType.ACCOUNT, alias_id
        )
        is None
    )
    event = await uow.events.get_by_idempotency_key(organization_id, "merge-key")
    assert event is not None
    assert event["reason_code"] == "admin_reviewed"
    assert await uow.events.get_by_idempotency_key(other_organization_id, "merge-key") is None
