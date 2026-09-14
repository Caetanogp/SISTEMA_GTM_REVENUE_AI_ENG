"""SQLAlchemy adapters for tenant-scoped deduplication persistence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from revops.application.ports import (
    CanonicalRecordGroup,
    DeduplicationCandidateRecord,
    DeduplicationScanRecord,
)
from revops.domain.entities.account import Account as DomainAccount
from revops.domain.entities.contact import Contact as DomainContact
from revops.domain.entities.deduplication import (
    DeduplicationCandidate,
    DeduplicationCandidateStatus,
    DeduplicationRecordType,
    DeduplicationScanStatus,
    RecordAlias,
)
from revops.domain.policies.deduplication import account_fingerprint, contact_fingerprint
from revops.domain.values.company_domain import CompanyDomain
from revops.domain.values.email import EmailAddress
from revops.domain.values.phone import PhoneNumber
from revops.infrastructure.persistence.models import (
    Account,
    AccountDeduplicationAlias,
    AccountDeduplicationCandidate,
    Contact,
    ContactDeduplicationAlias,
    ContactDeduplicationCandidate,
    DeduplicationEvent,
    DeduplicationScan,
)


def _scan(row: DeduplicationScan) -> DeduplicationScanRecord:
    return DeduplicationScanRecord(
        row.id,
        row.organization_id,
        row.requested_by,
        tuple(DeduplicationRecordType(value) for value in row.record_types),
        DeduplicationScanStatus(row.status),
        row.idempotency_key,
    )


def _candidate(row: Any, record_type: DeduplicationRecordType) -> DeduplicationCandidateRecord:
    value = DeduplicationCandidate(
        record_type,
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


def _candidate_model(record_type: DeduplicationRecordType) -> Any:
    return (
        AccountDeduplicationCandidate
        if record_type is DeduplicationRecordType.ACCOUNT
        else ContactDeduplicationCandidate
    )


def _alias_model(record_type: DeduplicationRecordType) -> Any:
    return (
        AccountDeduplicationAlias
        if record_type is DeduplicationRecordType.ACCOUNT
        else ContactDeduplicationAlias
    )


class SqlAlchemyDeduplicationScanRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, organization_id: UUID, scan_id: UUID) -> DeduplicationScanRecord | None:
        row = (
            await self._session.execute(
                select(DeduplicationScan).where(
                    DeduplicationScan.organization_id == organization_id,
                    DeduplicationScan.id == scan_id,
                )
            )
        ).scalar_one_or_none()
        return _scan(row) if row else None

    async def get_by_idempotency_key(
        self, organization_id: UUID, idempotency_key: str
    ) -> DeduplicationScanRecord | None:
        row = (
            await self._session.execute(
                select(DeduplicationScan).where(
                    DeduplicationScan.organization_id == organization_id,
                    DeduplicationScan.idempotency_key == idempotency_key,
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
            DeduplicationScan(
                id=scan_id,
                organization_id=organization_id,
                requested_by=requested_by,
                record_types=[value.value for value in record_types],
                policy_version="dedupe_v1",
                idempotency_key=idempotency_key,
                status=DeduplicationScanStatus.QUEUED.value,
                created_at=now,
                updated_at=now,
            )
        )
        await self._session.flush()

    async def set_status(
        self, organization_id: UUID, scan_id: UUID, status: DeduplicationScanStatus
    ) -> DeduplicationScanRecord | None:
        row = (
            await self._session.execute(
                select(DeduplicationScan)
                .where(
                    DeduplicationScan.organization_id == organization_id,
                    DeduplicationScan.id == scan_id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        row.status = status.value
        await self._session.flush()
        return _scan(row)


class SqlAlchemyDeduplicationCandidateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_for_update(
        self, organization_id: UUID, candidate_id: UUID
    ) -> DeduplicationCandidateRecord | None:
        for record_type in DeduplicationRecordType:
            model = _candidate_model(record_type)
            row = (
                await self._session.execute(
                    select(model)
                    .where(model.organization_id == organization_id, model.id == candidate_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if row:
                return _candidate(row, record_type)
        return None

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
        types = (record_type,) if record_type else tuple(DeduplicationRecordType)
        collected: list[DeduplicationCandidateRecord] = []
        for current_type in types:
            model = _candidate_model(current_type)
            stmt = select(model).where(
                model.organization_id == organization_id, model.scan_id == scan_id
            )
            if status is not None:
                stmt = stmt.where(model.status == status.value)
            rows = (await self._session.execute(stmt)).scalars().all()
            collected.extend(_candidate(row, current_type) for row in rows)
        collected.sort(
            key=lambda item: (
                item.candidate.record_type.value,
                item.candidate.left_id,
                item.candidate.right_id,
                item.id,
            )
        )
        return collected[offset : offset + limit]

    async def save(self, candidate: DeduplicationCandidateRecord) -> None:
        row = await self._session.get(
            _candidate_model(candidate.candidate.record_type), candidate.id
        )
        if row is None:
            raise LookupError("deduplication candidate not found")
        row.status = candidate.candidate.status.value
        await self._session.flush()

    async def counts(
        self, organization_id: UUID, scan_id: UUID
    ) -> Mapping[DeduplicationCandidateStatus, int]:
        result: dict[DeduplicationCandidateStatus, int] = {}
        for record_type in DeduplicationRecordType:
            model = _candidate_model(record_type)
            rows = await self._session.execute(
                select(model.status, func.count())
                .where(model.organization_id == organization_id, model.scan_id == scan_id)
                .group_by(model.status)
            )
            for value, count in rows:
                status = DeduplicationCandidateStatus(value)
                result[status] = result.get(status, 0) + int(count)
        return result


class SqlAlchemyDeduplicationAliasRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_active(
        self, organization_id: UUID, record_type: DeduplicationRecordType, record_id: UUID
    ) -> RecordAlias | None:
        model = _alias_model(record_type)
        row = (
            await self._session.execute(
                select(model).where(
                    model.organization_id == organization_id,
                    model.alias_id == record_id,
                    model.reverted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        return self._to_domain(row, record_type) if row else None

    async def add(self, alias: RecordAlias) -> None:
        model = _alias_model(alias.record_type)
        self._session.add(
            model(
                id=alias.merge_event_id,
                organization_id=alias.organization_id,
                alias_id=alias.alias_id,
                canonical_id=alias.canonical_id,
                merge_event_id=alias.merge_event_id,
                created_at=alias.created_at,
                reverted_at=alias.reverted_at,
                reverted_by_event_id=alias.reverted_by_event_id,
            )
        )
        await self._session.flush()

    async def get_for_update(
        self, organization_id: UUID, merge_event_id: UUID
    ) -> RecordAlias | None:
        for record_type in DeduplicationRecordType:
            model = _alias_model(record_type)
            row = (
                await self._session.execute(
                    select(model)
                    .where(
                        model.organization_id == organization_id,
                        model.merge_event_id == merge_event_id,
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if row:
                return self._to_domain(row, record_type)
        return None

    async def save(self, alias: RecordAlias) -> None:
        row = await self._session.get(_alias_model(alias.record_type), alias.merge_event_id)
        if row is None:
            raise LookupError("deduplication alias not found")
        row.reverted_at = alias.reverted_at
        row.reverted_by_event_id = alias.reverted_by_event_id
        await self._session.flush()

    @staticmethod
    def _to_domain(row: Any, record_type: DeduplicationRecordType) -> RecordAlias:
        return RecordAlias(
            row.organization_id,
            record_type,
            row.alias_id,
            row.canonical_id,
            row.merge_event_id,
            row.created_at,
            row.reverted_at,
            row.reverted_by_event_id,
        )


class SqlAlchemyDeduplicationEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_idempotency_key(
        self, organization_id: UUID, idempotency_key: str
    ) -> Mapping[str, object] | None:
        row = (
            await self._session.execute(
                select(DeduplicationEvent).where(
                    DeduplicationEvent.organization_id == organization_id,
                    DeduplicationEvent.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        return {
            "id": str(row.id),
            "event_id": str(row.id),
            "organization_id": str(row.organization_id),
            "candidate_id": str(row.account_candidate_id or row.contact_candidate_id)
            if (row.account_candidate_id or row.contact_candidate_id)
            else None,
            "action": row.action,
            **row.payload,
        }

    async def add(self, event: Mapping[str, object]) -> None:
        candidate_id = UUID(str(event["candidate_id"])) if event.get("candidate_id") else None
        record_type = str(event.get("record_type", ""))
        self._session.add(
            DeduplicationEvent(
                id=UUID(str(event["id"])),
                organization_id=UUID(str(event["organization_id"])),
                idempotency_key=str(event["idempotency_key"]),
                account_candidate_id=candidate_id if record_type == "account" else None,
                contact_candidate_id=candidate_id if record_type == "contact" else None,
                related_event_id=UUID(str(event["related_event_id"]))
                if event.get("related_event_id")
                else None,
                action=str(event["action"]),
                actor_id=UUID(str(event["actor_id"])),
                payload=dict(event),
                occurred_at=datetime.fromisoformat(str(event["occurred_at"])),
            )
        )
        await self._session.flush()

    async def add_if_absent(self, event: Mapping[str, object]) -> Mapping[str, object]:
        candidate_id = UUID(str(event["candidate_id"])) if event.get("candidate_id") else None
        record_type = str(event.get("record_type", ""))
        values = {
            "id": UUID(str(event["id"])),
            "organization_id": UUID(str(event["organization_id"])),
            "idempotency_key": str(event["idempotency_key"]),
            "account_candidate_id": candidate_id if record_type == "account" else None,
            "contact_candidate_id": candidate_id if record_type == "contact" else None,
            "related_event_id": UUID(str(event["related_event_id"]))
            if event.get("related_event_id")
            else None,
            "action": str(event["action"]),
            "actor_id": UUID(str(event["actor_id"])),
            "payload": dict(event),
            "occurred_at": datetime.fromisoformat(str(event["occurred_at"])),
        }
        statement = (
            insert(DeduplicationEvent)
            .values(**values)
            .on_conflict_do_nothing(index_elements=["organization_id", "idempotency_key"])
        )
        await self._session.execute(statement)
        row = await self._session.scalar(
            select(DeduplicationEvent).where(
                DeduplicationEvent.organization_id == values["organization_id"],
                DeduplicationEvent.idempotency_key == values["idempotency_key"],
            )
        )
        if row is None:
            raise LookupError("reserved deduplication event disappeared")
        return {
            "id": str(row.id),
            "event_id": str(row.id),
            "organization_id": str(row.organization_id),
            "candidate_id": str(row.account_candidate_id or row.contact_candidate_id)
            if (row.account_candidate_id or row.contact_candidate_id)
            else None,
            "action": row.action,
            **row.payload,
        }

    async def list_history(
        self, organization_id: UUID, *, offset: int, limit: int
    ) -> Sequence[Mapping[str, object]]:
        rows = (
            (
                await self._session.execute(
                    select(DeduplicationEvent)
                    .where(
                        DeduplicationEvent.organization_id == organization_id,
                        DeduplicationEvent.action.in_(("merge", "revert")),
                    )
                    .order_by(DeduplicationEvent.occurred_at.desc(), DeduplicationEvent.id.desc())
                    .offset(offset)
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        related_ids = {row.related_event_id for row in rows if row.related_event_id is not None}
        related_types: dict[UUID, str] = {}
        if related_ids:
            related_rows = (
                await self._session.execute(
                    select(DeduplicationEvent).where(
                        DeduplicationEvent.organization_id == organization_id,
                        DeduplicationEvent.id.in_(related_ids),
                    )
                )
            ).scalars()
            related_types = {row.id: _event_record_type(row, {}) for row in related_rows}
        return [
            {
                "id": row.id,
                "record_type": _event_record_type(row, related_types),
                "action": row.action,
                "candidate_id": row.account_candidate_id or row.contact_candidate_id,
                "related_event_id": row.related_event_id,
                "alias_id": row.payload.get("alias_id"),
                "canonical_id": row.payload.get("canonical_id"),
                "reason_codes": tuple(
                    cast(tuple[object, ...], row.payload.get("reason_codes", ()))
                ),
                "actor_id": row.actor_id,
                "occurred_at": row.occurred_at,
            }
            for row in rows
        ]


def _event_record_type(row: DeduplicationEvent, related_types: Mapping[UUID, str]) -> str:
    if row.account_candidate_id is not None:
        return DeduplicationRecordType.ACCOUNT.value
    if row.contact_candidate_id is not None:
        return DeduplicationRecordType.CONTACT.value
    payload_type = row.payload.get("record_type")
    if payload_type in {item.value for item in DeduplicationRecordType}:
        return str(payload_type)
    if row.related_event_id is not None and row.related_event_id in related_types:
        return related_types[row.related_event_id]
    raise ValueError("deduplication event record type is unavailable")


class SqlAlchemyCanonicalResolver:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def resolve(
        self, organization_id: UUID, record_type: DeduplicationRecordType, record_id: UUID
    ) -> CanonicalRecordGroup | None:
        return await self._resolve(organization_id, record_type, record_id, lock=False)

    async def resolve_for_write(
        self, organization_id: UUID, record_type: DeduplicationRecordType, record_id: UUID
    ) -> CanonicalRecordGroup | None:
        return await self._resolve(organization_id, record_type, record_id, lock=True)

    async def _resolve(
        self,
        organization_id: UUID,
        record_type: DeduplicationRecordType,
        record_id: UUID,
        *,
        lock: bool,
    ) -> CanonicalRecordGroup | None:
        record_model = Account if record_type is DeduplicationRecordType.ACCOUNT else Contact
        alias_model = _alias_model(record_type)
        exists = await self._session.scalar(
            select(record_model.id).where(
                record_model.organization_id == organization_id, record_model.id == record_id
            )
        )
        if exists is None:
            return None
        canonical_id = (
            await self._session.scalar(
                select(alias_model.canonical_id).where(
                    alias_model.organization_id == organization_id,
                    alias_model.alias_id == record_id,
                    alias_model.reverted_at.is_(None),
                )
            )
            or record_id
        )
        if lock:
            await self._session.execute(
                select(record_model.id)
                .where(
                    record_model.organization_id == organization_id,
                    record_model.id == record_id,
                )
                .with_for_update()
            )
            if record_type is DeduplicationRecordType.CONTACT:
                account_id = await self._session.scalar(
                    select(Contact.account_id).where(
                        Contact.organization_id == organization_id,
                        Contact.id == record_id,
                    )
                )
                if account_id is not None:
                    await self._session.execute(
                        select(Account.id)
                        .where(Account.organization_id == organization_id, Account.id == account_id)
                        .with_for_update()
                    )
            await self._session.execute(
                select(record_model.id)
                .where(
                    record_model.organization_id == organization_id,
                    record_model.id == canonical_id,
                )
                .with_for_update()
            )
        stmt = (
            select(alias_model.alias_id)
            .where(
                alias_model.organization_id == organization_id,
                alias_model.canonical_id == canonical_id,
                alias_model.reverted_at.is_(None),
            )
            .order_by(alias_model.alias_id)
        )
        if lock:
            stmt = stmt.with_for_update()
        aliases = list((await self._session.execute(stmt)).scalars().all())
        return CanonicalRecordGroup(canonical_id, (canonical_id, *aliases))

    async def fingerprint_for_write(
        self, organization_id: UUID, record_type: DeduplicationRecordType, record_id: UUID
    ) -> str | None:
        group = await self._resolve(organization_id, record_type, record_id, lock=True)
        if group is None:
            return None
        record_id = group.canonical_id if record_id not in group.member_ids else record_id
        if record_type is DeduplicationRecordType.ACCOUNT:
            row = await self._session.scalar(
                select(Account).where(
                    Account.organization_id == organization_id, Account.id == record_id
                )
            )
            return (
                account_fingerprint(
                    DomainAccount(
                        row.id,
                        row.organization_id,
                        row.company_name,
                        CompanyDomain(row.domain),
                        row.created_at,
                    )
                )
                if row
                else None
            )
        row = await self._session.scalar(
            select(Contact).where(
                Contact.organization_id == organization_id, Contact.id == record_id
            )
        )
        if row is None:
            return None
        return contact_fingerprint(
            DomainContact(
                row.id,
                row.organization_id,
                row.account_id,
                EmailAddress(row.email),
                row.full_name,
                row.title,
                PhoneNumber(row.phone) if row.phone else None,
            ),
            canonical_account_id=row.account_id,
        )
