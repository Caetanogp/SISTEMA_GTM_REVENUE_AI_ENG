"""Tenant-scoped application workflows for reversible deduplication decisions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import NAMESPACE_URL, UUID, uuid5

from revops.application.dto import (
    CanonicalRecordResult,
    DeduplicationCandidateResult,
    DeduplicationDecisionResult,
    DeduplicationMergeResult,
    DeduplicationScanArgs,
    DeduplicationScanResult,
)
from revops.application.ports import (
    DeduplicationCandidateRecord,
    DeduplicationUnitOfWorkFactory,
)
from revops.domain.entities.deduplication import (
    DeduplicationCandidateStatus,
    DeduplicationRecordType,
    DeduplicationScanState,
    RecordAlias,
)
from revops.domain.errors import InvalidTransitionError


class DeduplicationNotFoundError(Exception):
    """A tenant-scoped deduplication resource does not exist."""


class DeduplicationIdempotencyConflictError(Exception):
    """An idempotency key was reused with a different operation."""


class DeduplicationConflictError(Exception):
    """The requested decision is stale or violates alias policy."""


def _candidate_result(record: DeduplicationCandidateRecord) -> DeduplicationCandidateResult:
    candidate = record.candidate
    return DeduplicationCandidateResult(
        id=record.id,
        scan_id=record.scan_id,
        organization_id=record.organization_id,
        record_type=candidate.record_type,
        left_id=candidate.left_id,
        right_id=candidate.right_id,
        score=candidate.score,
        reasons=candidate.reasons,
        policy_version=candidate.policy_version,
        status=candidate.status,
    )


@dataclass(frozen=True, slots=True)
class StartDeduplicationScan:
    factory: DeduplicationUnitOfWorkFactory

    async def execute(
        self,
        *,
        organization_id: UUID,
        requested_by: UUID,
        idempotency_key: str,
        args: DeduplicationScanArgs,
    ) -> DeduplicationScanResult:
        async with self.factory() as uow:
            existing = await uow.scans.get_by_idempotency_key(organization_id, idempotency_key)
            if existing is not None:
                existing_types = existing.record_types
                if tuple(existing_types) != tuple(args.record_types):
                    raise DeduplicationIdempotencyConflictError(
                        "idempotency key has different content"
                    )
                return DeduplicationScanResult(
                    id=existing.id,
                    organization_id=organization_id,
                    record_types=tuple(existing_types),
                    status=existing.status,
                    replayed=True,
                )
            scan_id = uuid5(NAMESPACE_URL, f"dedupe-scan:{organization_id}:{idempotency_key}")
            await uow.scans.add(
                organization_id, requested_by, scan_id, args.record_types, idempotency_key
            )
            await uow.commit()
            return DeduplicationScanResult(
                id=scan_id,
                organization_id=organization_id,
                record_types=tuple(args.record_types),
                status=DeduplicationScanState().status,
            )


@dataclass(frozen=True, slots=True)
class ListDeduplicationCandidates:
    factory: DeduplicationUnitOfWorkFactory

    async def execute(
        self,
        *,
        organization_id: UUID,
        scan_id: UUID,
        offset: int = 0,
        limit: int = 100,
        status: DeduplicationCandidateStatus | None = None,
        record_type: DeduplicationRecordType | None = None,
    ) -> tuple[DeduplicationCandidateResult, ...]:
        if offset < 0 or not 0 < limit <= 100:
            raise ValueError("candidate pagination is out of bounds")
        async with self.factory() as uow:
            if await uow.scans.get(organization_id, scan_id) is None:
                raise DeduplicationNotFoundError("deduplication scan not found")
            rows = await uow.candidates.list(
                organization_id,
                scan_id,
                status=status,
                record_type=record_type,
                offset=offset,
                limit=limit,
            )
            return tuple(_candidate_result(row) for row in rows)


@dataclass(frozen=True, slots=True)
class DismissDeduplicationCandidate:
    factory: DeduplicationUnitOfWorkFactory

    async def execute(
        self,
        *,
        organization_id: UUID,
        candidate_id: UUID,
        idempotency_key: str,
        reason: str,
        actor_id: UUID,
        occurred_at: datetime,
    ) -> DeduplicationDecisionResult:
        async with self.factory() as uow:
            prior = await uow.events.get_by_idempotency_key(organization_id, idempotency_key)
            if prior is not None:
                if (
                    prior.get("candidate_id") != str(candidate_id)
                    or prior.get("action") != "dismiss"
                ):
                    raise DeduplicationIdempotencyConflictError(
                        "idempotency key has different content"
                    )
                return DeduplicationDecisionResult(
                    candidate_id, DeduplicationCandidateStatus.DISMISSED, True
                )
            candidate = await uow.candidates.get_for_update(organization_id, candidate_id)
            if candidate is None:
                raise DeduplicationNotFoundError("deduplication candidate not found")
            if reason not in {"not_duplicate", "insufficient_evidence"}:
                raise ValueError("unsupported dismissal reason")
            try:
                candidate.candidate.dismiss()
            except InvalidTransitionError as exc:
                raise DeduplicationConflictError(str(exc)) from exc
            await uow.candidates.save(candidate)
            await uow.events.add(
                {
                    "id": str(
                        uuid5(NAMESPACE_URL, f"dedupe-event:{organization_id}:{idempotency_key}")
                    ),
                    "organization_id": str(organization_id),
                    "candidate_id": str(candidate_id),
                    "action": "dismiss",
                    "idempotency_key": idempotency_key,
                    "reason": reason,
                    "actor_id": str(actor_id),
                    "occurred_at": occurred_at.isoformat(),
                }
            )
            await uow.commit()
            return DeduplicationDecisionResult(candidate_id, candidate.candidate.status)


@dataclass(frozen=True, slots=True)
class MergeDeduplicationCandidate:
    factory: DeduplicationUnitOfWorkFactory

    async def execute(
        self,
        *,
        organization_id: UUID,
        candidate_id: UUID,
        master_record_id: UUID,
        idempotency_key: str,
        actor_id: UUID,
        occurred_at: datetime,
    ) -> DeduplicationMergeResult:
        async with self.factory() as uow:
            prior = await uow.events.get_by_idempotency_key(organization_id, idempotency_key)
            if prior is not None:
                if prior.get("candidate_id") != str(candidate_id) or prior.get("action") != "merge":
                    raise DeduplicationIdempotencyConflictError(
                        "idempotency key has different content"
                    )
                return DeduplicationMergeResult(
                    UUID(str(prior["event_id"])),
                    UUID(str(prior["alias_id"])),
                    UUID(str(prior["canonical_id"])),
                    True,
                )
            candidate = await uow.candidates.get_for_update(organization_id, candidate_id)
            if candidate is None:
                raise DeduplicationNotFoundError("deduplication candidate not found")
            if candidate.candidate.status is not DeduplicationCandidateStatus.PENDING:
                raise DeduplicationConflictError("candidate is no longer pending")
            if master_record_id not in {
                candidate.candidate.left_id,
                candidate.candidate.right_id,
            }:
                raise DeduplicationConflictError("master must be a candidate member")
            alias_id = (
                candidate.candidate.right_id
                if master_record_id == candidate.candidate.left_id
                else candidate.candidate.left_id
            )
            if (
                await uow.resolver.resolve(
                    organization_id, candidate.candidate.record_type, master_record_id
                )
                != master_record_id
            ):
                raise DeduplicationConflictError("an alias cannot become master")
            if (
                await uow.aliases.get_active(
                    organization_id, candidate.candidate.record_type, alias_id
                )
                is not None
            ):
                raise DeduplicationConflictError("record already has an active alias")
            event_id = uuid5(NAMESPACE_URL, f"dedupe-event:{organization_id}:{idempotency_key}")
            alias = RecordAlias(
                organization_id,
                candidate.candidate.record_type,
                alias_id,
                master_record_id,
                event_id,
                occurred_at,
            )
            await uow.aliases.add(alias)
            candidate.candidate.mark_merged()
            await uow.candidates.save(candidate)
            await uow.events.add(
                {
                    "id": str(event_id),
                    "event_id": str(event_id),
                    "organization_id": str(organization_id),
                    "candidate_id": str(candidate_id),
                    "action": "merge",
                    "idempotency_key": idempotency_key,
                    "alias_id": str(alias_id),
                    "canonical_id": str(master_record_id),
                    "actor_id": str(actor_id),
                    "occurred_at": occurred_at.isoformat(),
                }
            )
            await uow.commit()
            return DeduplicationMergeResult(event_id, alias_id, master_record_id)


@dataclass(frozen=True, slots=True)
class RevertDeduplicationMerge:
    factory: DeduplicationUnitOfWorkFactory

    async def execute(
        self,
        *,
        organization_id: UUID,
        merge_event_id: UUID,
        idempotency_key: str,
        actor_id: UUID,
        occurred_at: datetime,
    ) -> DeduplicationDecisionResult:
        async with self.factory() as uow:
            prior = await uow.events.get_by_idempotency_key(organization_id, idempotency_key)
            if prior is not None:
                return DeduplicationDecisionResult(
                    UUID(str(prior["candidate_id"])),
                    DeduplicationCandidateStatus.MERGED,
                    True,
                )
            alias = await uow.aliases.get_for_update(organization_id, merge_event_id)
            if alias is None:
                raise DeduplicationNotFoundError("merge not found")
            try:
                alias.revert(occurred_at=occurred_at)
            except InvalidTransitionError as exc:
                raise DeduplicationConflictError(str(exc)) from exc
            await uow.aliases.save(alias)
            event_id = uuid5(NAMESPACE_URL, f"dedupe-event:{organization_id}:{idempotency_key}")
            await uow.events.add(
                {
                    "id": str(event_id),
                    "organization_id": str(organization_id),
                    "candidate_id": str(merge_event_id),
                    "action": "revert",
                    "idempotency_key": idempotency_key,
                    "actor_id": str(actor_id),
                    "occurred_at": occurred_at.isoformat(),
                }
            )
            await uow.commit()
            return DeduplicationDecisionResult(merge_event_id, DeduplicationCandidateStatus.MERGED)


@dataclass(frozen=True, slots=True)
class ResolveCanonicalRecord:
    factory: DeduplicationUnitOfWorkFactory

    async def execute(
        self, *, organization_id: UUID, record_type: DeduplicationRecordType, record_id: UUID
    ) -> CanonicalRecordResult:
        async with self.factory() as uow:
            canonical_id = await uow.resolver.resolve(organization_id, record_type, record_id)
            return CanonicalRecordResult(record_type, record_id, canonical_id)
