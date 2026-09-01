"""SQLAlchemy adapters for tenant-scoped deduplication persistence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from revops.application.ports import (
    DeduplicationCandidateRecord,
    DeduplicationScanRecord,
)
from revops.domain.entities.deduplication import (
    DeduplicationCandidate,
    DeduplicationCandidateStatus,
    DeduplicationRecordType,
    DeduplicationScanStatus,
    RecordAlias,
)
from revops.infrastructure.persistence.models import (
    DeduplicationAlias as AliasModel,
)
from revops.infrastructure.persistence.models import (
    DeduplicationCandidate as CandidateModel,
)
from revops.infrastructure.persistence.models import (
    DeduplicationEvent as EventModel,
)
from revops.infrastructure.persistence.models import (
    DeduplicationScan as ScanModel,
)


def _scan(row: ScanModel) -> DeduplicationScanRecord:
    return DeduplicationScanRecord(
        row.id,
        row.organization_id,
        row.requested_by,
        tuple(DeduplicationRecordType(value) for value in row.record_types),
        DeduplicationScanStatus(row.status),
        row.idempotency_key,
    )


def _candidate(row: CandidateModel) -> DeduplicationCandidateRecord:
    value = DeduplicationCandidate(
        DeduplicationRecordType(row.record_type),
        row.left_id,
        row.right_id,
        row.score,
        tuple(row.reasons),
        row.policy_version,
        row.left_fingerprint,
        row.right_fingerprint,
        DeduplicationCandidateStatus(row.status),
    )
    return DeduplicationCandidateRecord(row.id, row.scan_id, row.organization_id, value)


class SqlAlchemyDeduplicationScanRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, organization_id: UUID, scan_id: UUID) -> DeduplicationScanRecord | None:
        row = (
            await self._session.execute(
                select(ScanModel).where(
                    ScanModel.organization_id == organization_id, ScanModel.id == scan_id
                )
            )
        ).scalar_one_or_none()
        return _scan(row) if row else None

    async def get_by_idempotency_key(
        self, organization_id: UUID, idempotency_key: str
    ) -> DeduplicationScanRecord | None:
        row = (
            await self._session.execute(
                select(ScanModel).where(
                    ScanModel.organization_id == organization_id,
                    ScanModel.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one_or_none()
        return _scan(row) if row else None

    async def add(
        self,
        organization_id: UUID,
        requested_by: UUID,
        scan_id: UUID,
        record_types: Sequence[DeduplicationRecordType],
        idempotency_key: str,
    ) -> None:
        now = datetime.now().astimezone()
        self._session.add(
            ScanModel(
                id=scan_id,
                organization_id=organization_id,
                requested_by=requested_by,
                record_types=[v.value for v in record_types],
                policy_version="dedupe_v1",
                idempotency_key=idempotency_key,
                status=DeduplicationScanStatus.QUEUED.value,
                created_at=now,
                updated_at=now,
            )
        )
        await self._session.flush()


class SqlAlchemyDeduplicationCandidateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_for_update(
        self, organization_id: UUID, candidate_id: UUID
    ) -> DeduplicationCandidateRecord | None:
        row = (
            await self._session.execute(
                select(CandidateModel)
                .where(
                    CandidateModel.organization_id == organization_id,
                    CandidateModel.id == candidate_id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        return _candidate(row) if row else None

    async def list(
        self,
        organization_id: UUID,
        scan_id: UUID,
        *,
        status: DeduplicationCandidateStatus | None,
        record_type: DeduplicationRecordType | None,
        offset: int,
        limit: int,
    ) -> Sequence[DeduplicationCandidateRecord]:
        stmt = (
            select(CandidateModel)
            .where(
                CandidateModel.organization_id == organization_id, CandidateModel.scan_id == scan_id
            )
            .offset(offset)
            .limit(limit)
        )
        if status is not None:
            stmt = stmt.where(CandidateModel.status == status.value)
        if record_type is not None:
            stmt = stmt.where(CandidateModel.record_type == record_type.value)
        return [_candidate(row) for row in (await self._session.execute(stmt)).scalars().all()]

    async def save(self, candidate: DeduplicationCandidateRecord) -> None:
        row = await self._session.get(CandidateModel, candidate.id)
        if row is None:
            raise LookupError("deduplication candidate not found")
        row.status = candidate.candidate.status.value
        await self._session.flush()


class SqlAlchemyDeduplicationAliasRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_active(
        self, organization_id: UUID, record_type: DeduplicationRecordType, record_id: UUID
    ) -> RecordAlias | None:
        row = (
            await self._session.execute(
                select(AliasModel).where(
                    AliasModel.organization_id == organization_id,
                    AliasModel.record_type == record_type.value,
                    AliasModel.alias_id == record_id,
                    AliasModel.reverted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        return self._to_domain(row) if row else None

    async def add(self, alias: RecordAlias) -> None:
        self._session.add(
            AliasModel(
                id=alias.merge_event_id,
                organization_id=alias.organization_id,
                record_type=alias.record_type.value,
                alias_id=alias.alias_id,
                canonical_id=alias.canonical_id,
                merge_event_id=alias.merge_event_id,
                created_at=alias.created_at,
                reverted_at=alias.reverted_at,
            )
        )
        await self._session.flush()

    async def get_for_update(
        self, organization_id: UUID, merge_event_id: UUID
    ) -> RecordAlias | None:
        row = (
            await self._session.execute(
                select(AliasModel)
                .where(
                    AliasModel.organization_id == organization_id,
                    AliasModel.merge_event_id == merge_event_id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        return self._to_domain(row) if row else None

    async def save(self, alias: RecordAlias) -> None:
        row = await self._session.get(AliasModel, alias.merge_event_id)
        if row is None:
            raise LookupError("deduplication alias not found")
        row.reverted_at = alias.reverted_at
        await self._session.flush()

    @staticmethod
    def _to_domain(row: AliasModel) -> RecordAlias:
        return RecordAlias(
            row.organization_id,
            DeduplicationRecordType(row.record_type),
            row.alias_id,
            row.canonical_id,
            row.merge_event_id,
            row.created_at,
            row.reverted_at,
        )


class SqlAlchemyDeduplicationEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_idempotency_key(
        self, organization_id: UUID, idempotency_key: str
    ) -> Mapping[str, object] | None:
        row = (
            await self._session.execute(
                select(EventModel).where(
                    EventModel.organization_id == organization_id,
                    EventModel.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        return {
            "id": str(row.id),
            "event_id": str(row.id),
            "organization_id": str(row.organization_id),
            "candidate_id": str(row.candidate_id) if row.candidate_id else None,
            "action": row.action,
            **row.payload,
        }

    async def add(self, event: Mapping[str, object]) -> None:
        self._session.add(
            EventModel(
                id=UUID(str(event["id"])),
                organization_id=UUID(str(event["organization_id"])),
                idempotency_key=str(event["idempotency_key"]),
                candidate_id=UUID(str(event["candidate_id"]))
                if event.get("candidate_id")
                else None,
                action=str(event["action"]),
                actor_id=UUID(str(event["actor_id"])),
                payload=dict(event),
                occurred_at=datetime.fromisoformat(str(event["occurred_at"])),
            )
        )
        await self._session.flush()


class SqlAlchemyCanonicalResolver:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def resolve(
        self, organization_id: UUID, record_type: DeduplicationRecordType, record_id: UUID
    ) -> UUID:
        row = (
            await self._session.execute(
                select(AliasModel.canonical_id).where(
                    AliasModel.organization_id == organization_id,
                    AliasModel.record_type == record_type.value,
                    AliasModel.alias_id == record_id,
                    AliasModel.reverted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        return row or record_id
