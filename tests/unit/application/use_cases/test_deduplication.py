from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from revops.application.dto import DeduplicationScanArgs
from revops.application.ports import (
    DeduplicationCandidateRecord,
    DeduplicationScanRecord,
)
from revops.application.use_cases.deduplication import (
    DeduplicationConflictError,
    DeduplicationIdempotencyConflictError,
    DismissDeduplicationCandidate,
    ListDeduplicationCandidates,
    MergeDeduplicationCandidate,
    ResolveCanonicalRecord,
    RevertDeduplicationMerge,
    StartDeduplicationScan,
)
from revops.domain.entities.deduplication import (
    DeduplicationCandidate,
    DeduplicationCandidateStatus,
    DeduplicationRecordType,
    DeduplicationScanStatus,
)

NOW = datetime(2026, 8, 31, tzinfo=UTC)


class FakeUow:
    def __init__(self) -> None:
        self.scans = FakeScans()
        self.candidates = FakeCandidates()
        self.aliases = FakeAliases()
        self.events = FakeEvents()
        self.resolver = FakeResolver()
        self.commits = 0

    async def __aenter__(self) -> FakeUow:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        return None


class FakeScans:
    def __init__(self) -> None:
        self.rows: dict[UUID, DeduplicationScanRecord] = {}

    async def get_by_idempotency_key(
        self, organization_id: UUID, key: str
    ) -> DeduplicationScanRecord | None:
        return next(
            (
                r
                for r in self.rows.values()
                if r.organization_id == organization_id and r.idempotency_key == key
            ),
            None,
        )

    async def get(self, organization_id: UUID, scan_id: UUID) -> DeduplicationScanRecord | None:
        row = self.rows.get(scan_id)
        return row if row and row.organization_id == organization_id else None

    async def add(
        self,
        organization_id: UUID,
        scan_id: UUID,
        record_types: tuple[DeduplicationRecordType, ...],
        key: str,
    ) -> None:
        self.rows[scan_id] = DeduplicationScanRecord(
            scan_id, organization_id, tuple(record_types), DeduplicationScanStatus.QUEUED, key
        )


class FakeCandidates:
    def __init__(self) -> None:
        self.rows: dict[UUID, DeduplicationCandidateRecord] = {}

    async def get_for_update(
        self, organization_id: UUID, candidate_id: UUID
    ) -> DeduplicationCandidateRecord | None:
        row = self.rows.get(candidate_id)
        return row if row and row.organization_id == organization_id else None

    async def list(
        self,
        organization_id: UUID,
        scan_id: UUID,
        *,
        status: Any,
        record_type: Any,
        offset: int,
        limit: int,
    ) -> list[DeduplicationCandidateRecord]:
        rows = [
            r
            for r in self.rows.values()
            if r.organization_id == organization_id and r.scan_id == scan_id
        ]
        if status is not None:
            rows = [r for r in rows if r.candidate.status is status]
        if record_type is not None:
            rows = [r for r in rows if r.candidate.record_type is record_type]
        return rows[offset : offset + limit]

    async def save(self, record: DeduplicationCandidateRecord) -> None:
        self.rows[record.id] = record


class FakeAliases:
    def __init__(self) -> None:
        self.rows: dict[UUID, Any] = {}

    async def get_active(self, organization_id: UUID, record_type: Any, record_id: UUID) -> Any:
        return next(
            (a for a in self.rows.values() if a.alias_id == record_id and a.reverted_at is None),
            None,
        )

    async def add(self, alias: Any) -> None:
        self.rows[alias.merge_event_id] = alias

    async def get_for_update(self, organization_id: UUID, merge_event_id: UUID) -> Any:
        return self.rows.get(merge_event_id)

    async def save(self, alias: Any) -> None:
        self.rows[alias.merge_event_id] = alias


class FakeEvents:
    def __init__(self) -> None:
        self.rows: dict[tuple[UUID, str], dict[str, Any]] = {}

    async def get_by_idempotency_key(
        self, organization_id: UUID, key: str
    ) -> dict[str, Any] | None:
        return self.rows.get((organization_id, key))

    async def add(self, event: dict[str, Any]) -> None:
        self.rows[(UUID(event["organization_id"]), event.get("idempotency_key", event["id"]))] = (
            event
        )
        self.rows[(UUID(event["organization_id"]), event.get("key", event["id"]))] = event


class FakeResolver:
    def __init__(self) -> None:
        self.canonical: dict[UUID, UUID] = {}

    async def resolve(self, organization_id: UUID, record_type: Any, record_id: UUID) -> UUID:
        return self.canonical.get(record_id, record_id)


def factory(uow: FakeUow) -> Any:
    @asynccontextmanager
    async def create() -> AsyncIterator[FakeUow]:
        yield uow

    return create


def candidate(organization_id: UUID, scan_id: UUID) -> DeduplicationCandidateRecord:
    left, right = sorted((uuid4(), uuid4()))
    value = DeduplicationCandidate(
        DeduplicationRecordType.ACCOUNT,
        left,
        right,
        100,
        ("account_domain_exact",),
        "dedupe_v1",
        "a" * 64,
        "b" * 64,
    )
    return DeduplicationCandidateRecord(uuid4(), scan_id, organization_id, value)


@pytest.mark.asyncio
async def test_scan_is_idempotent_and_tenant_scoped() -> None:
    uow = FakeUow()
    org = uuid4()
    use_case = StartDeduplicationScan(factory(uow))
    args = DeduplicationScanArgs(record_types=(DeduplicationRecordType.ACCOUNT,))
    first = await use_case.execute(organization_id=org, idempotency_key="scan", args=args)
    replay = await use_case.execute(organization_id=org, idempotency_key="scan", args=args)
    assert replay.replayed
    assert replay.id == first.id
    assert uow.commits == 1
    with pytest.raises(DeduplicationIdempotencyConflictError):
        await use_case.execute(
            organization_id=org,
            idempotency_key="scan",
            args=DeduplicationScanArgs(record_types=(DeduplicationRecordType.CONTACT,)),
        )
    assert await uow.scans.get(org, first.id) is not None
    assert await uow.scans.get(uuid4(), first.id) is None


@pytest.mark.asyncio
async def test_dismiss_is_idempotent_and_non_pending_is_conflict() -> None:
    uow = FakeUow()
    org, scan_id = uuid4(), uuid4()
    row = candidate(org, scan_id)
    uow.candidates.rows[row.id] = row
    use_case = DismissDeduplicationCandidate(factory(uow))
    result = await use_case.execute(
        organization_id=org,
        candidate_id=row.id,
        idempotency_key="dismiss",
        reason="not_duplicate",
        actor_id=uuid4(),
        occurred_at=NOW,
    )
    assert result.status is DeduplicationCandidateStatus.DISMISSED
    uow.events.rows[(org, "dismiss")] = {"candidate_id": str(row.id), "action": "dismiss"}
    replay = await use_case.execute(
        organization_id=org,
        candidate_id=row.id,
        idempotency_key="dismiss",
        reason="not_duplicate",
        actor_id=uuid4(),
        occurred_at=NOW,
    )
    assert replay.replayed
    with pytest.raises(DeduplicationConflictError):
        await use_case.execute(
            organization_id=org,
            candidate_id=row.id,
            idempotency_key="other",
            reason="not_duplicate",
            actor_id=uuid4(),
            occurred_at=NOW,
        )


@pytest.mark.asyncio
async def test_merge_selects_master_and_revert_deactivates_alias() -> None:
    uow = FakeUow()
    org, scan_id = uuid4(), uuid4()
    row = candidate(org, scan_id)
    uow.candidates.rows[row.id] = row
    master = row.candidate.left_id
    merged = await MergeDeduplicationCandidate(factory(uow)).execute(
        organization_id=org,
        candidate_id=row.id,
        master_record_id=master,
        idempotency_key="merge",
        actor_id=uuid4(),
        occurred_at=NOW,
    )
    assert merged.canonical_id == master
    assert row.candidate.status is DeduplicationCandidateStatus.MERGED
    reverted = await RevertDeduplicationMerge(factory(uow)).execute(
        organization_id=org,
        merge_event_id=merged.event_id,
        idempotency_key="revert",
        actor_id=uuid4(),
        occurred_at=NOW,
    )
    assert not reverted.replayed
    assert not uow.aliases.rows[merged.event_id].is_active


@pytest.mark.asyncio
async def test_list_bounds_and_canonical_resolution_are_tenant_scoped() -> None:
    uow = FakeUow()
    with pytest.raises(ValueError, match="candidate pagination"):
        await ListDeduplicationCandidates(factory(uow)).execute(
            organization_id=uuid4(), scan_id=uuid4(), limit=101
        )
    record_id, canonical_id = uuid4(), uuid4()
    uow.resolver.canonical[record_id] = canonical_id
    result = await ResolveCanonicalRecord(factory(uow)).execute(
        organization_id=uuid4(), record_type=DeduplicationRecordType.CONTACT, record_id=record_id
    )
    assert result.canonical_id == canonical_id
