"""Bounded, idempotent persistence adapter for asynchronous deduplication scans."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import combinations
from typing import Any, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import exists, func, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from revops.domain.entities.account import Account as DomainAccount
from revops.domain.entities.contact import Contact as DomainContact
from revops.domain.entities.deduplication import (
    DeduplicationCandidate,
    DeduplicationCandidateStatus,
    DeduplicationRecordType,
    DeduplicationScanState,
    DeduplicationScanStatus,
)
from revops.domain.policies.deduplication import (
    POLICY_VERSION,
    account_fingerprint,
    company_name_key,
    contact_fingerprint,
    match_accounts,
    match_contacts,
    person_name_key,
)
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
    DeduplicationScan,
)

MAX_SCAN_RECORDS = 50_000
MAX_SCAN_CANDIDATES = 10_000
RECORD_LIMIT_FAILURE = "record_limit_exceeded"
CANDIDATE_LIMIT_FAILURE = "candidate_limit_exceeded"
SCAN_FAILURE = "scan_failed"


class DeduplicationScanNotFoundError(LookupError):
    """The tenant-scoped scan does not exist."""


class DeduplicationScanBoundError(RuntimeError):
    """A configured non-PII scan bound was exceeded."""

    def __init__(self, failure_code: str) -> None:
        super().__init__(failure_code)
        self.failure_code = failure_code


@dataclass(frozen=True, slots=True)
class ProcessDeduplicationScanResult:
    scan_id: UUID
    status: DeduplicationScanStatus
    record_count: int
    candidate_count: int
    failure_code: str | None = None


@dataclass(frozen=True, slots=True)
class _CandidateRow:
    id: UUID
    candidate: DeduplicationCandidate


class DeduplicationScanLifecycle:
    """Persist broker and terminal failures with tenant-safe conditional transitions."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def mark_queue_failed(self, organization_id: UUID, scan_id: UUID) -> bool:
        async with self._session_factory() as session, session.begin():
            row = await self._lock_scan(session, organization_id, scan_id)
            if row is None:
                return False
            state = DeduplicationScanState(DeduplicationScanStatus(row.status))
            if state.status is DeduplicationScanStatus.QUEUE_FAILED:
                return True
            if state.status is not DeduplicationScanStatus.QUEUED:
                return False
            state.record_queue_failure()
            self._set_status(row, state.status)
            return True

    async def mark_failed(self, organization_id: UUID, scan_id: UUID) -> bool:
        async with self._session_factory() as session, session.begin():
            row = await self._lock_scan(session, organization_id, scan_id)
            if row is None:
                return False
            state = DeduplicationScanState(DeduplicationScanStatus(row.status))
            if state.status is DeduplicationScanStatus.FAILED:
                return True
            if state.status.is_terminal:
                return False
            if state.status is DeduplicationScanStatus.QUEUED:
                state.begin_processing()
            elif state.status is DeduplicationScanStatus.QUEUE_FAILED:
                state.retry_queue()
                state.begin_processing()
            state.fail()
            self._set_status(row, state.status)
            return True

    @staticmethod
    async def _lock_scan(
        session: AsyncSession, organization_id: UUID, scan_id: UUID
    ) -> DeduplicationScan | None:
        return cast(
            DeduplicationScan | None,
            await session.scalar(
                select(DeduplicationScan)
                .where(
                    DeduplicationScan.organization_id == organization_id,
                    DeduplicationScan.id == scan_id,
                )
                .with_for_update()
            ),
        )

    @staticmethod
    def _set_status(row: DeduplicationScan, status: DeduplicationScanStatus) -> None:
        row.status = status.value
        row.updated_at = datetime.now(UTC)


class DeduplicationScanProcessor:
    """Execute one bounded scan with replay-safe candidate persistence."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._lifecycle = DeduplicationScanLifecycle(session_factory)

    async def process(
        self, *, organization_id: UUID, scan_id: UUID
    ) -> ProcessDeduplicationScanResult:
        claimed_status = await self._claim(organization_id, scan_id)
        if claimed_status.is_terminal:
            return await self._terminal_result(organization_id, scan_id, claimed_status)

        try:
            async with self._session_factory() as session, session.begin():
                scan = await DeduplicationScanLifecycle._lock_scan(
                    session, organization_id, scan_id
                )
                if scan is None:
                    raise DeduplicationScanNotFoundError("deduplication scan not found")
                current_status = DeduplicationScanStatus(scan.status)
                if current_status.is_terminal:
                    return await self._result_in_session(
                        session, scan_id, current_status, record_count=0
                    )

                account_rows, contact_rows = await self._load_records(
                    session,
                    organization_id=organization_id,
                    record_types=tuple(
                        DeduplicationRecordType(value) for value in scan.record_types
                    ),
                )
                account_candidates = await self._account_candidates(
                    session,
                    organization_id=organization_id,
                    scan_id=scan_id,
                    rows=account_rows,
                )
                contact_candidates = await self._contact_candidates(
                    session,
                    organization_id=organization_id,
                    scan_id=scan_id,
                    rows=contact_rows,
                    remaining_limit=MAX_SCAN_CANDIDATES - len(account_candidates),
                )
                candidates = (*account_candidates, *contact_candidates)
                await self._insert_candidates(
                    session,
                    organization_id=organization_id,
                    scan_id=scan_id,
                    candidates=candidates,
                )
                DeduplicationScanLifecycle._set_status(scan, DeduplicationScanStatus.COMPLETED)
                return ProcessDeduplicationScanResult(
                    scan_id,
                    DeduplicationScanStatus.COMPLETED,
                    len(account_rows) + len(contact_rows),
                    len(candidates),
                )
        except DeduplicationScanBoundError as exc:
            await self._lifecycle.mark_failed(organization_id, scan_id)
            return ProcessDeduplicationScanResult(
                scan_id,
                DeduplicationScanStatus.FAILED,
                0,
                0,
                exc.failure_code,
            )

    async def mark_failed(self, *, organization_id: UUID, scan_id: UUID) -> bool:
        return await self._lifecycle.mark_failed(organization_id, scan_id)

    async def _claim(self, organization_id: UUID, scan_id: UUID) -> DeduplicationScanStatus:
        async with self._session_factory() as session, session.begin():
            scan = await DeduplicationScanLifecycle._lock_scan(session, organization_id, scan_id)
            if scan is None:
                raise DeduplicationScanNotFoundError("deduplication scan not found")
            state = DeduplicationScanState(DeduplicationScanStatus(scan.status))
            if state.status is DeduplicationScanStatus.QUEUED:
                state.begin_processing()
                DeduplicationScanLifecycle._set_status(scan, state.status)
            elif state.status is DeduplicationScanStatus.QUEUE_FAILED:
                state.retry_queue()
                state.begin_processing()
                DeduplicationScanLifecycle._set_status(scan, state.status)
            return state.status

    async def _terminal_result(
        self,
        organization_id: UUID,
        scan_id: UUID,
        status: DeduplicationScanStatus,
    ) -> ProcessDeduplicationScanResult:
        async with self._session_factory() as session:
            scan_exists = await session.scalar(
                select(DeduplicationScan.id).where(
                    DeduplicationScan.organization_id == organization_id,
                    DeduplicationScan.id == scan_id,
                )
            )
            if scan_exists is None:
                raise DeduplicationScanNotFoundError("deduplication scan not found")
            return await self._result_in_session(session, scan_id, status, record_count=0)

    @staticmethod
    async def _result_in_session(
        session: AsyncSession,
        scan_id: UUID,
        status: DeduplicationScanStatus,
        *,
        record_count: int,
    ) -> ProcessDeduplicationScanResult:
        account_count = await session.scalar(
            select(func.count())
            .select_from(AccountDeduplicationCandidate)
            .where(AccountDeduplicationCandidate.scan_id == scan_id)
        )
        contact_count = await session.scalar(
            select(func.count())
            .select_from(ContactDeduplicationCandidate)
            .where(ContactDeduplicationCandidate.scan_id == scan_id)
        )
        return ProcessDeduplicationScanResult(
            scan_id,
            status,
            record_count,
            int(account_count or 0) + int(contact_count or 0),
            SCAN_FAILURE if status is DeduplicationScanStatus.FAILED else None,
        )

    @staticmethod
    async def _load_records(
        session: AsyncSession,
        *,
        organization_id: UUID,
        record_types: Sequence[DeduplicationRecordType],
    ) -> tuple[list[Account], list[Contact]]:
        accounts: list[Account] = []
        contacts: list[Contact] = []
        remaining = MAX_SCAN_RECORDS
        if DeduplicationRecordType.ACCOUNT in record_types:
            accounts = list(
                (
                    await session.scalars(
                        select(Account)
                        .where(
                            Account.organization_id == organization_id,
                            ~exists(
                                select(AccountDeduplicationAlias.id).where(
                                    AccountDeduplicationAlias.organization_id == organization_id,
                                    AccountDeduplicationAlias.alias_id == Account.id,
                                    AccountDeduplicationAlias.reverted_at.is_(None),
                                )
                            ),
                        )
                        .order_by(Account.id)
                        .limit(remaining + 1)
                    )
                ).all()
            )
            if len(accounts) > remaining:
                raise DeduplicationScanBoundError(RECORD_LIMIT_FAILURE)
            remaining -= len(accounts)
        if DeduplicationRecordType.CONTACT in record_types:
            contacts = list(
                (
                    await session.scalars(
                        select(Contact)
                        .where(
                            Contact.organization_id == organization_id,
                            ~exists(
                                select(ContactDeduplicationAlias.id).where(
                                    ContactDeduplicationAlias.organization_id == organization_id,
                                    ContactDeduplicationAlias.alias_id == Contact.id,
                                    ContactDeduplicationAlias.reverted_at.is_(None),
                                )
                            ),
                        )
                        .order_by(Contact.id)
                        .limit(remaining + 1)
                    )
                ).all()
            )
            if len(contacts) > remaining:
                raise DeduplicationScanBoundError(RECORD_LIMIT_FAILURE)
        return accounts, contacts

    async def _account_candidates(
        self,
        session: AsyncSession,
        *,
        organization_id: UUID,
        scan_id: UUID,
        rows: Sequence[Account],
    ) -> list[_CandidateRow]:
        records = {
            row.id: DomainAccount(
                row.id,
                row.organization_id,
                row.company_name,
                CompanyDomain(row.domain),
                row.created_at,
            )
            for row in rows
        }
        buckets: list[dict[object, list[UUID]]] = [defaultdict(list), defaultdict(list)]
        for record in records.values():
            buckets[0][record.domain.value].append(record.id)
            if name_key := company_name_key(record.company_name):
                buckets[1][name_key].append(record.id)
        pairs = self._candidate_pairs(buckets, MAX_SCAN_CANDIDATES)
        candidates: list[_CandidateRow] = []
        for left_id, right_id in sorted(pairs):
            left, right = records[left_id], records[right_id]
            evidence = match_accounts(left, right)
            if evidence is None:
                continue
            candidates.append(
                self._candidate_row(
                    scan_id,
                    DeduplicationRecordType.ACCOUNT,
                    left_id,
                    right_id,
                    evidence.score,
                    evidence.reasons,
                    account_fingerprint(left),
                    account_fingerprint(right),
                )
            )
        return await self._remove_suppressed(
            session,
            organization_id=organization_id,
            record_type=DeduplicationRecordType.ACCOUNT,
            candidates=candidates,
        )

    async def _contact_candidates(
        self,
        session: AsyncSession,
        *,
        organization_id: UUID,
        scan_id: UUID,
        rows: Sequence[Contact],
        remaining_limit: int,
    ) -> list[_CandidateRow]:
        alias_rows = (
            (
                await session.execute(
                    select(
                        AccountDeduplicationAlias.alias_id,
                        AccountDeduplicationAlias.canonical_id,
                    ).where(
                        AccountDeduplicationAlias.organization_id == organization_id,
                        AccountDeduplicationAlias.reverted_at.is_(None),
                    )
                )
            )
            .tuples()
            .all()
        )
        canonical_accounts: dict[UUID, UUID] = dict(alias_rows)
        records = {
            row.id: DomainContact(
                row.id,
                row.organization_id,
                row.account_id,
                EmailAddress(row.email),
                row.full_name,
                row.title,
                PhoneNumber(row.phone) if row.phone is not None else None,
            )
            for row in rows
        }
        buckets: list[dict[object, list[UUID]]] = [
            defaultdict(list),
            defaultdict(list),
            defaultdict(list),
        ]
        for record in records.values():
            canonical_account_id = canonical_accounts.get(record.account_id, record.account_id)
            buckets[0][record.email.value].append(record.id)
            if record.phone is not None:
                buckets[1][record.phone.value].append(record.id)
            if name_key := person_name_key(record.full_name):
                buckets[2][(canonical_account_id, name_key)].append(record.id)
        pairs = self._candidate_pairs(buckets, remaining_limit)
        candidates: list[_CandidateRow] = []
        for left_id, right_id in sorted(pairs):
            left, right = records[left_id], records[right_id]
            left_account = canonical_accounts.get(left.account_id, left.account_id)
            right_account = canonical_accounts.get(right.account_id, right.account_id)
            evidence = match_contacts(
                left,
                right,
                same_canonical_account=left_account == right_account,
            )
            if evidence is None:
                continue
            candidates.append(
                self._candidate_row(
                    scan_id,
                    DeduplicationRecordType.CONTACT,
                    left_id,
                    right_id,
                    evidence.score,
                    evidence.reasons,
                    contact_fingerprint(left, canonical_account_id=left_account),
                    contact_fingerprint(right, canonical_account_id=right_account),
                )
            )
        return await self._remove_suppressed(
            session,
            organization_id=organization_id,
            record_type=DeduplicationRecordType.CONTACT,
            candidates=candidates,
        )

    @staticmethod
    def _candidate_pairs(
        buckets: Iterable[dict[object, list[UUID]]], limit: int
    ) -> set[tuple[UUID, UUID]]:
        pairs: set[tuple[UUID, UUID]] = set()
        for bucket in buckets:
            for identifiers in bucket.values():
                for left_id, right_id in combinations(sorted(set(identifiers)), 2):
                    pairs.add((left_id, right_id))
                    if len(pairs) > limit:
                        raise DeduplicationScanBoundError(CANDIDATE_LIMIT_FAILURE)
        return pairs

    @staticmethod
    def _candidate_row(
        scan_id: UUID,
        record_type: DeduplicationRecordType,
        left_id: UUID,
        right_id: UUID,
        score: int,
        reasons: tuple[str, ...],
        left_fingerprint: str,
        right_fingerprint: str,
    ) -> _CandidateRow:
        candidate = DeduplicationCandidate(
            record_type,
            left_id,
            right_id,
            score,
            reasons,
            POLICY_VERSION,
            left_fingerprint,
            right_fingerprint,
        )
        candidate_id = uuid5(
            NAMESPACE_URL,
            f"dedupe-candidate:{scan_id}:{record_type.value}:{left_id}:{right_id}",
        )
        return _CandidateRow(candidate_id, candidate)

    @staticmethod
    async def _remove_suppressed(
        session: AsyncSession,
        *,
        organization_id: UUID,
        record_type: DeduplicationRecordType,
        candidates: Sequence[_CandidateRow],
    ) -> list[_CandidateRow]:
        if not candidates:
            return []
        model: Any = (
            AccountDeduplicationCandidate
            if record_type is DeduplicationRecordType.ACCOUNT
            else ContactDeduplicationCandidate
        )
        identifiers = {
            identifier
            for row in candidates
            for identifier in (row.candidate.left_id, row.candidate.right_id)
        }
        dismissed_rows = (
            await session.execute(
                select(
                    model.left_id,
                    model.right_id,
                    model.left_fingerprint,
                    model.right_fingerprint,
                    model.policy_version,
                ).where(
                    model.organization_id == organization_id,
                    model.status == DeduplicationCandidateStatus.DISMISSED.value,
                    model.policy_version == POLICY_VERSION,
                    model.left_id.in_(identifiers),
                    model.right_id.in_(identifiers),
                )
            )
        ).all()
        suppressed = set(dismissed_rows)
        return [
            row
            for row in candidates
            if (
                row.candidate.left_id,
                row.candidate.right_id,
                row.candidate.left_fingerprint,
                row.candidate.right_fingerprint,
                row.candidate.policy_version,
            )
            not in suppressed
        ]

    @staticmethod
    async def _insert_candidates(
        session: AsyncSession,
        *,
        organization_id: UUID,
        scan_id: UUID,
        candidates: Sequence[_CandidateRow],
    ) -> None:
        for record_type, model in (
            (DeduplicationRecordType.ACCOUNT, AccountDeduplicationCandidate),
            (DeduplicationRecordType.CONTACT, ContactDeduplicationCandidate),
        ):
            values = [
                {
                    "id": row.id,
                    "scan_id": scan_id,
                    "organization_id": organization_id,
                    "left_id": row.candidate.left_id,
                    "right_id": row.candidate.right_id,
                    "score": row.candidate.score,
                    "reasons": list(row.candidate.reasons),
                    "policy_version": row.candidate.policy_version,
                    "left_fingerprint": row.candidate.left_fingerprint,
                    "right_fingerprint": row.candidate.right_fingerprint,
                    "status": row.candidate.status.value,
                }
                for row in candidates
                if row.candidate.record_type is record_type
            ]
            if not values:
                continue
            for start in range(0, len(values), 1_000):
                statement = (
                    postgresql_insert(model)
                    .values(values[start : start + 1_000])
                    .on_conflict_do_nothing(index_elements=["scan_id", "left_id", "right_id"])
                )
                await session.execute(statement)
