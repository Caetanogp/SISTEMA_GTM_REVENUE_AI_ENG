"""Application orchestration for staged, confirmed account ingestion."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from typing import Final
from uuid import UUID, uuid4

from revops.application.dto import (
    AccountEnrichmentRecord,
    CanonicalIngestionRecord,
    ConfirmIngestionResult,
    IngestionRecordInput,
    ProcessIngestionResult,
    StagedIngestionItem,
    StagedIngestionJob,
    StageIngestionResult,
)
from revops.application.ports import (
    CanonicalRecordGroup,
    Clock,
    EnrichmentGateway,
    EnrichmentGatewayError,
    IngestionDispatcher,
    IngestionUnitOfWorkFactory,
)
from revops.domain.entities.account import Account
from revops.domain.entities.contact import Contact
from revops.domain.entities.deduplication import DeduplicationRecordType
from revops.domain.entities.ingestion import (
    AccountOutcome,
    ContactOutcome,
    EnrichmentOutcome,
    IngestionItemState,
    IngestionItemStatus,
    IngestionJobStatus,
)
from revops.domain.errors import PolicyViolationError
from revops.domain.values.company_domain import CompanyDomain
from revops.domain.values.email import EmailAddress
from revops.domain.values.phone import PhoneNumber

_MAX_TEXT_LENGTH: Final = 512
_MAX_SOURCE_LENGTH: Final = 128
_MAX_IDEMPOTENCY_KEY_LENGTH: Final = 128


class IngestionIdempotencyConflictError(Exception):
    """An idempotency key was reused with different canonical import content."""


class IngestionNotFoundError(Exception):
    """A tenant-scoped ingestion job does not exist."""


def _trim(value: str | None) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


def _canonicalize(row_number: int, input_row: IngestionRecordInput) -> StagedIngestionItem:
    values = {
        "company_name": _trim(input_row.company_name),
        "domain": _trim(input_row.domain),
        "email": _trim(input_row.email),
        "full_name": _trim(input_row.full_name),
        "title": _trim(input_row.title),
        "phone": _trim(input_row.phone),
    }
    errors: list[str] = []
    for field, value in values.items():
        if value is not None and len(value) > _MAX_TEXT_LENGTH:
            errors.append(f"{field}_too_long")
    if values["company_name"] is None:
        errors.append("company_name_required")
    if values["domain"] is None:
        errors.append("domain_required")

    has_any_contact_field = any(
        values[field] is not None for field in ("email", "full_name", "title", "phone")
    )
    if has_any_contact_field and values["email"] is None:
        errors.append("email_required")
    if has_any_contact_field and values["full_name"] is None:
        errors.append("full_name_required")

    normalized_domain: str | None = None
    if values["domain"] is not None and "domain_too_long" not in errors:
        try:
            normalized_domain = CompanyDomain(values["domain"]).value
        except PolicyViolationError:
            errors.append("domain_invalid")

    normalized_email: str | None = None
    if values["email"] is not None and "email_too_long" not in errors:
        try:
            normalized_email = EmailAddress(values["email"]).value
        except PolicyViolationError:
            errors.append("email_invalid")

    normalized_phone: str | None = None
    if values["phone"] is not None and "phone_too_long" not in errors:
        try:
            normalized_phone = PhoneNumber(values["phone"]).value
        except PolicyViolationError:
            errors.append("invalid_phone")

    record = None
    if not errors:
        company_name = values["company_name"]
        assert normalized_domain is not None
        assert company_name is not None
        record = CanonicalIngestionRecord(
            company_name=company_name,
            domain=normalized_domain,
            email=normalized_email,
            full_name=values["full_name"],
            title=values["title"],
            phone=normalized_phone,
        )
    has_contact = values["email"] is not None
    return StagedIngestionItem(
        row_number=row_number,
        record=record,
        validation_codes=tuple(sorted(set(errors))),
        status=(IngestionItemStatus.PENDING if record else IngestionItemStatus.VALIDATION_FAILED),
        account_outcome=(AccountOutcome.NOT_ATTEMPTED if record else AccountOutcome.FAILED),
        contact_outcome=(
            ContactOutcome.NOT_ATTEMPTED
            if record and has_contact
            else ContactOutcome.NOT_PROVIDED
            if record
            else ContactOutcome.SKIPPED
        ),
        enrichment_outcome=(
            EnrichmentOutcome.NOT_ATTEMPTED if record else EnrichmentOutcome.SKIPPED
        ),
    )


def _mark_conflicts(items: list[StagedIngestionItem]) -> list[StagedIngestionItem]:
    by_domain: dict[str, list[StagedIngestionItem]] = {}
    by_email: dict[str, list[StagedIngestionItem]] = {}
    for item in items:
        if item.record is None:
            continue
        by_domain.setdefault(item.record.domain, []).append(item)
        if item.record.email is not None:
            by_email.setdefault(item.record.email, []).append(item)

    conflicted_rows: dict[int, set[str]] = {}
    for group in by_domain.values():
        if len({item.record.company_name.casefold() for item in group if item.record}) > 1:
            for item in group:
                conflicted_rows.setdefault(item.row_number, set()).add("domain_company_conflict")
    for group in by_email.values():
        if len({item.record.domain for item in group if item.record}) > 1:
            for item in group:
                conflicted_rows.setdefault(item.row_number, set()).add("email_domain_conflict")

    return [
        replace(
            item,
            record=None,
            validation_codes=tuple(sorted(conflicted_rows[item.row_number])),
            status=IngestionItemStatus.VALIDATION_FAILED,
            account_outcome=AccountOutcome.FAILED,
            contact_outcome=ContactOutcome.SKIPPED,
            enrichment_outcome=EnrichmentOutcome.SKIPPED,
        )
        if item.row_number in conflicted_rows
        else item
        for item in items
    ]


def _content_hash(source: str, items: list[StagedIngestionItem]) -> str:
    payload = {
        "source": source,
        "records": [
            {
                "company_name": item.record.company_name if item.record else None,
                "domain": item.record.domain if item.record else None,
                "email": item.record.email if item.record else None,
                "full_name": item.record.full_name if item.record else None,
                "title": item.record.title if item.record else None,
                "phone": item.record.phone if item.record else None,
                "validation_codes": item.validation_codes,
            }
            for item in items
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class StageIngestion:
    uow_factory: IngestionUnitOfWorkFactory

    async def execute(
        self,
        *,
        organization_id: UUID,
        requested_by: UUID,
        source: str,
        idempotency_key: str,
        records: list[IngestionRecordInput],
    ) -> StageIngestionResult:
        normalized_source = _trim(source)
        normalized_key = _trim(idempotency_key)
        if normalized_source is None or len(normalized_source) > _MAX_SOURCE_LENGTH:
            raise PolicyViolationError("source must be between 1 and 128 characters")
        if normalized_key is None or len(normalized_key) > _MAX_IDEMPOTENCY_KEY_LENGTH:
            raise PolicyViolationError("idempotency key must be between 1 and 128 characters")

        items = _mark_conflicts([_canonicalize(index, row) for index, row in enumerate(records, 1)])
        content_hash = _content_hash(normalized_source, items)
        status = (
            IngestionJobStatus.VALIDATION_FAILED
            if all(item.status is IngestionItemStatus.VALIDATION_FAILED for item in items)
            else IngestionJobStatus.STAGED
        )
        async with self.uow_factory() as uow:
            existing = await uow.jobs.get_by_idempotency_key(organization_id, normalized_key)
            if existing is not None:
                if existing.content_hash != content_hash:
                    raise IngestionIdempotencyConflictError("idempotency key has different content")
                return StageIngestionResult(job=existing, replayed=True)
            job = StagedIngestionJob(
                id=uuid4(),
                organization_id=organization_id,
                requested_by=requested_by,
                source=normalized_source,
                idempotency_key=normalized_key,
                content_hash=content_hash,
                status=status,
                items=tuple(items),
            )
            await uow.jobs.add(job)
            await uow.items.add_many(job.id, items)
            await uow.commit()
        return StageIngestionResult(job=job, replayed=False)


@dataclass(frozen=True, slots=True)
class ConfirmIngestion:
    uow_factory: IngestionUnitOfWorkFactory
    dispatcher: IngestionDispatcher

    async def execute(self, *, organization_id: UUID, job_id: UUID) -> ConfirmIngestionResult:
        async with self.uow_factory() as uow:
            job = await uow.jobs.get(organization_id, job_id)
            if job is None:
                raise IngestionNotFoundError("ingestion job was not found")
            if job.status in {
                IngestionJobStatus.PROCESSING,
                IngestionJobStatus.COMPLETED,
                IngestionJobStatus.COMPLETED_WITH_ERRORS,
                IngestionJobStatus.VALIDATION_FAILED,
            }:
                return ConfirmIngestionResult(job=job, published=False, replayed=True)
            queued = await uow.jobs.set_status(organization_id, job_id, IngestionJobStatus.QUEUED)
            await uow.commit()
        try:
            await self.dispatcher.publish(organization_id=organization_id, job_id=job_id)
        except Exception:
            async with self.uow_factory() as uow:
                current = await uow.jobs.get(organization_id, job_id)
                if current is not None and current.status is IngestionJobStatus.QUEUED:
                    await uow.jobs.set_status(
                        organization_id, job_id, IngestionJobStatus.QUEUE_FAILED
                    )
                    await uow.commit()
            raise
        return ConfirmIngestionResult(
            job=queued,
            published=True,
            replayed=job.status is IngestionJobStatus.QUEUED,
        )


@dataclass(frozen=True, slots=True)
class GetIngestionJob:
    uow_factory: IngestionUnitOfWorkFactory

    async def execute(self, *, organization_id: UUID, job_id: UUID) -> StagedIngestionJob:
        async with self.uow_factory() as uow:
            job = await uow.jobs.get(organization_id, job_id)
        if job is None:
            raise IngestionNotFoundError("ingestion job was not found")
        return job


@dataclass(frozen=True, slots=True)
class ListIngestionItems:
    uow_factory: IngestionUnitOfWorkFactory

    async def execute(
        self, *, organization_id: UUID, job_id: UUID, offset: int, limit: int
    ) -> tuple[StagedIngestionItem, ...]:
        async with self.uow_factory() as uow:
            return tuple(
                await uow.items.list_for_job(organization_id, job_id, offset=offset, limit=limit)
            )


@dataclass(frozen=True, slots=True)
class ProcessIngestionJob:
    """Process a confirmed import with one atomic transaction per normalized domain."""

    uow_factory: IngestionUnitOfWorkFactory
    enrichment_gateway: EnrichmentGateway
    clock: Clock

    async def execute(self, *, organization_id: UUID, job_id: UUID) -> ProcessIngestionResult:
        initial_status = await self._begin_or_resume(organization_id, job_id)
        if initial_status is not IngestionJobStatus.PROCESSING:
            return ProcessIngestionResult(job_id, initial_status, ())

        async with self.uow_factory() as uow:
            domains = tuple(await uow.items.list_processable_domains(organization_id, job_id))

        processed_domains = []
        for domain in domains:
            if await self._process_domain(organization_id, job_id, domain):
                processed_domains.append(domain)

        final_status = await self._complete_if_ready(organization_id, job_id)
        return ProcessIngestionResult(job_id, final_status, tuple(processed_domains))

    async def _begin_or_resume(self, organization_id: UUID, job_id: UUID) -> IngestionJobStatus:
        async with self.uow_factory() as uow:
            job = await uow.jobs.get_for_update(organization_id, job_id)
            if job is None:
                raise IngestionNotFoundError("ingestion job was not found")
            if job.status is IngestionJobStatus.QUEUED:
                job = await uow.jobs.set_status(
                    organization_id, job_id, IngestionJobStatus.PROCESSING
                )
                await uow.commit()
            return job.status

    async def _process_domain(self, organization_id: UUID, job_id: UUID, domain: str) -> bool:
        async with self.uow_factory() as uow:
            locked = await uow.items.lock_domain_items(organization_id, job_id, domain)
            items = [item for item in locked if item.status is IngestionItemStatus.PENDING]
            if not items:
                return False

            first_record = items[0].record
            if first_record is None:
                return False
            now = self.clock.now()
            account_result = await uow.accounts.get_or_create(
                Account(
                    id=uuid4(),
                    organization_id=organization_id,
                    company_name=first_record.company_name,
                    domain=CompanyDomain(first_record.domain),
                    created_at=now,
                )
            )
            canonical = getattr(uow, "canonical", None)
            account_group = (
                await canonical.resolve_for_write(
                    organization_id, DeduplicationRecordType.ACCOUNT, account_result.value.id
                )
                if canonical is not None
                else None
            )
            if canonical is None:
                account_group = CanonicalRecordGroup(
                    account_result.value.id, (account_result.value.id,)
                )
            if account_group is None:
                raise PolicyViolationError("account is unavailable")
            canonical_account_id = account_group.canonical_id

            contact_results: dict[int, tuple[UUID, bool]] = {}
            for item in items:
                record = item.record
                if record is None or not record.has_contact:
                    continue
                assert record.email is not None
                assert record.full_name is not None
                result = await uow.contacts.get_or_create(
                    Contact(
                        id=uuid4(),
                        organization_id=organization_id,
                        account_id=canonical_account_id,
                        email=EmailAddress(record.email),
                        full_name=record.full_name,
                        title=record.title or "",
                        phone=PhoneNumber(record.phone) if record.phone else None,
                    )
                )
                contact_group = (
                    await canonical.resolve_for_write(
                        organization_id, DeduplicationRecordType.CONTACT, result.value.id
                    )
                    if canonical is not None
                    else CanonicalRecordGroup(result.value.id, (result.value.id,))
                )
                if contact_group is None:
                    raise PolicyViolationError("contact is unavailable")
                contact_results[item.row_number] = (
                    contact_group.canonical_id,
                    result.created,
                )

            enrichment_id: UUID | None = None
            enrichment_outcome = EnrichmentOutcome.CREATED
            try:
                profile = await self.enrichment_gateway.enrich(domain=domain)
                enrichment = await uow.enrichments.get_or_create(
                    AccountEnrichmentRecord(
                        id=uuid4(),
                        ingestion_job_id=job_id,
                        organization_id=organization_id,
                        account_id=canonical_account_id,
                        profile=profile,
                        created_at=now,
                    )
                )
                enrichment_id = enrichment.value.id
            except EnrichmentGatewayError:
                enrichment_outcome = EnrichmentOutcome.FAILED

            for index, item in enumerate(items):
                record = item.record
                if record is None:
                    continue
                state = IngestionItemState(has_contact=record.has_contact)
                state.begin_processing()
                account_outcome = (
                    AccountOutcome.CREATED
                    if account_result.created and index == 0
                    else AccountOutcome.DUPLICATE
                )
                state.record_account(account_outcome)
                contact_id = None
                if record.has_contact:
                    contact_id, contact_created = contact_results[item.row_number]
                    state.record_contact(
                        ContactOutcome.CREATED if contact_created else ContactOutcome.DUPLICATE
                    )
                state.record_enrichment(enrichment_outcome)
                await uow.items.save_result(
                    organization_id,
                    job_id,
                    replace(
                        item,
                        status=state.status,
                        account_outcome=state.account_outcome,
                        contact_outcome=state.contact_outcome,
                        enrichment_outcome=state.enrichment_outcome,
                        account_id=canonical_account_id,
                        contact_id=contact_id,
                        enrichment_id=enrichment_id,
                    ),
                )
            await uow.commit()
        return True

    async def _complete_if_ready(self, organization_id: UUID, job_id: UUID) -> IngestionJobStatus:
        async with self.uow_factory() as uow:
            job = await uow.jobs.get_for_update(organization_id, job_id)
            if job is None:
                raise IngestionNotFoundError("ingestion job was not found")
            if job.status is not IngestionJobStatus.PROCESSING:
                return job.status
            summary = await uow.items.summarize(organization_id, job_id)
            if summary.nonterminal_count:
                return job.status
            target = (
                IngestionJobStatus.COMPLETED_WITH_ERRORS
                if summary.error_count
                else IngestionJobStatus.COMPLETED
            )
            job = await uow.jobs.set_status(organization_id, job_id, target)
            await uow.commit()
            return job.status
