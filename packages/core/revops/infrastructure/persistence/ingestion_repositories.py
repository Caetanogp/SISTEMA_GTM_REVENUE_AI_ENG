"""SQLAlchemy ingestion adapters."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from revops.application.dto import (
    AccountEnrichmentRecord,
    CanonicalIngestionRecord,
    EnrichmentProfile,
    IngestionItemSummary,
    StagedIngestionItem,
    StagedIngestionJob,
)
from revops.application.ports import CreatedRecord
from revops.domain.entities.account import Account
from revops.domain.entities.contact import Contact
from revops.domain.entities.ingestion import (
    AccountOutcome,
    ContactOutcome,
    EnrichmentOutcome,
    IngestionItemStatus,
    IngestionJobStatus,
)
from revops.domain.values.company_domain import CompanyDomain
from revops.domain.values.email import EmailAddress
from revops.infrastructure.persistence.models import Account as AccountModel
from revops.infrastructure.persistence.models import AccountEnrichment as AccountEnrichmentModel
from revops.infrastructure.persistence.models import Contact as ContactModel
from revops.infrastructure.persistence.models import IngestionItem as IngestionItemModel
from revops.infrastructure.persistence.models import IngestionJob as IngestionJobModel


def _item(row: IngestionItemModel) -> StagedIngestionItem:
    record = (
        None
        if row.company_name is None
        else CanonicalIngestionRecord(
            company_name=row.company_name,
            domain=row.domain or "",
            email=row.email,
            full_name=row.full_name,
            title=row.title,
        )
    )
    return StagedIngestionItem(
        row_number=row.row_number,
        record=record,
        validation_codes=tuple(row.validation_codes),
        status=IngestionItemStatus(row.status),
        account_outcome=AccountOutcome(row.account_outcome),
        contact_outcome=ContactOutcome(row.contact_outcome),
        enrichment_outcome=EnrichmentOutcome(row.enrichment_outcome),
        account_id=row.account_id,
        contact_id=row.contact_id,
        enrichment_id=row.enrichment_id,
    )


def _account(row: AccountModel) -> Account:
    return Account(
        id=row.id,
        organization_id=row.organization_id,
        company_name=row.company_name,
        domain=CompanyDomain(row.domain),
        created_at=row.created_at,
    )


def _contact(row: ContactModel) -> Contact:
    return Contact(
        id=row.id,
        organization_id=row.organization_id,
        account_id=row.account_id,
        email=EmailAddress(row.email),
        full_name=row.full_name,
        title=row.title,
    )


def _enrichment(row: AccountEnrichmentModel) -> AccountEnrichmentRecord:
    return AccountEnrichmentRecord(
        id=row.id,
        ingestion_job_id=row.ingestion_job_id,
        organization_id=row.organization_id,
        account_id=row.account_id,
        profile=EnrichmentProfile.model_validate(row.profile_json),
        created_at=row.created_at,
    )


class SqlAlchemyIngestionJobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _items(self, job_id: UUID) -> tuple[StagedIngestionItem, ...]:
        rows = (
            (
                await self._session.execute(
                    select(IngestionItemModel)
                    .where(IngestionItemModel.ingestion_job_id == job_id)
                    .order_by(IngestionItemModel.row_number)
                )
            )
            .scalars()
            .all()
        )
        return tuple(_item(row) for row in rows)

    async def _job(self, row: IngestionJobModel) -> StagedIngestionJob:
        return StagedIngestionJob(
            id=row.id,
            organization_id=row.organization_id,
            requested_by=row.requested_by,
            source=row.source,
            idempotency_key=row.idempotency_key,
            content_hash=row.content_hash,
            status=IngestionJobStatus(row.status),
            items=await self._items(row.id),
        )

    async def get(self, organization_id: UUID, job_id: UUID) -> StagedIngestionJob | None:
        row = (
            await self._session.execute(
                select(IngestionJobModel).where(
                    IngestionJobModel.organization_id == organization_id,
                    IngestionJobModel.id == job_id,
                )
            )
        ).scalar_one_or_none()
        return None if row is None else await self._job(row)

    async def get_by_idempotency_key(
        self, organization_id: UUID, idempotency_key: str
    ) -> StagedIngestionJob | None:
        row = (
            await self._session.execute(
                select(IngestionJobModel).where(
                    IngestionJobModel.organization_id == organization_id,
                    IngestionJobModel.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one_or_none()
        return None if row is None else await self._job(row)

    async def add(self, job: StagedIngestionJob) -> None:
        now = datetime.now(UTC)
        self._session.add(
            IngestionJobModel(
                id=job.id,
                organization_id=job.organization_id,
                requested_by=job.requested_by,
                source=job.source,
                idempotency_key=job.idempotency_key,
                content_hash=job.content_hash,
                status=job.status.value,
                created_at=now,
                updated_at=now,
            )
        )
        await self._session.flush()

    async def get_for_update(
        self, organization_id: UUID, job_id: UUID
    ) -> StagedIngestionJob | None:
        row = (
            await self._session.execute(
                select(IngestionJobModel)
                .where(
                    IngestionJobModel.organization_id == organization_id,
                    IngestionJobModel.id == job_id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        return None if row is None else await self._job(row)

    async def set_status(
        self, organization_id: UUID, job_id: UUID, status: IngestionJobStatus
    ) -> StagedIngestionJob:
        row = (
            await self._session.execute(
                select(IngestionJobModel)
                .where(
                    IngestionJobModel.organization_id == organization_id,
                    IngestionJobModel.id == job_id,
                )
                .with_for_update()
            )
        ).scalar_one()
        row.status = status.value
        row.updated_at = datetime.now(UTC)
        await self._session.flush()
        return await self._job(row)


class SqlAlchemyIngestionItemRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_many(self, job_id: UUID, items: Sequence[StagedIngestionItem]) -> None:
        self._session.add_all(
            [
                IngestionItemModel(
                    id=uuid4(),
                    ingestion_job_id=job_id,
                    row_number=item.row_number,
                    company_name=item.record.company_name if item.record else None,
                    domain=item.record.domain if item.record else None,
                    email=item.record.email if item.record else None,
                    full_name=item.record.full_name if item.record else None,
                    title=item.record.title if item.record else None,
                    validation_codes=list(item.validation_codes),
                    status=item.status.value,
                    account_outcome=item.account_outcome.value,
                    contact_outcome=item.contact_outcome.value,
                    enrichment_outcome=item.enrichment_outcome.value,
                )
                for item in items
            ]
        )
        await self._session.flush()

    async def list_for_job(
        self, organization_id: UUID, job_id: UUID, *, offset: int, limit: int
    ) -> Sequence[StagedIngestionItem]:
        rows = (
            (
                await self._session.execute(
                    select(IngestionItemModel)
                    .join(IngestionJobModel)
                    .where(
                        IngestionJobModel.organization_id == organization_id,
                        IngestionItemModel.ingestion_job_id == job_id,
                    )
                    .order_by(IngestionItemModel.row_number)
                    .offset(offset)
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        return [_item(row) for row in rows]

    async def list_processable_domains(self, organization_id: UUID, job_id: UUID) -> Sequence[str]:
        rows = (
            (
                await self._session.execute(
                    select(IngestionItemModel.domain)
                    .join(IngestionJobModel)
                    .where(
                        IngestionJobModel.organization_id == organization_id,
                        IngestionItemModel.ingestion_job_id == job_id,
                        IngestionItemModel.status == IngestionItemStatus.PENDING.value,
                        IngestionItemModel.domain.is_not(None),
                    )
                    .distinct()
                    .order_by(IngestionItemModel.domain)
                )
            )
            .scalars()
            .all()
        )
        return [row for row in rows if row is not None]

    async def lock_domain_items(
        self, organization_id: UUID, job_id: UUID, domain: str
    ) -> Sequence[StagedIngestionItem]:
        rows = (
            (
                await self._session.execute(
                    select(IngestionItemModel)
                    .join(IngestionJobModel)
                    .where(
                        IngestionJobModel.organization_id == organization_id,
                        IngestionItemModel.ingestion_job_id == job_id,
                        IngestionItemModel.domain == domain,
                    )
                    .order_by(IngestionItemModel.row_number)
                    .with_for_update()
                )
            )
            .scalars()
            .all()
        )
        return [_item(row) for row in rows]

    async def save_result(
        self, organization_id: UUID, job_id: UUID, item: StagedIngestionItem
    ) -> None:
        row = (
            await self._session.execute(
                select(IngestionItemModel)
                .join(IngestionJobModel)
                .where(
                    IngestionJobModel.organization_id == organization_id,
                    IngestionItemModel.ingestion_job_id == job_id,
                    IngestionItemModel.row_number == item.row_number,
                )
            )
        ).scalar_one()
        row.status = item.status.value
        row.account_outcome = item.account_outcome.value
        row.contact_outcome = item.contact_outcome.value
        row.enrichment_outcome = item.enrichment_outcome.value
        row.account_id = item.account_id
        row.contact_id = item.contact_id
        row.enrichment_id = item.enrichment_id
        await self._session.flush()

    async def summarize(self, organization_id: UUID, job_id: UUID) -> IngestionItemSummary:
        rows = (
            await self._session.execute(
                select(
                    IngestionItemModel.status,
                    IngestionItemModel.account_outcome,
                    IngestionItemModel.contact_outcome,
                    IngestionItemModel.enrichment_outcome,
                )
                .join(IngestionJobModel)
                .where(
                    IngestionJobModel.organization_id == organization_id,
                    IngestionItemModel.ingestion_job_id == job_id,
                )
            )
        ).all()
        terminal = {
            IngestionItemStatus.VALIDATION_FAILED.value,
            IngestionItemStatus.COMPLETED.value,
        }
        return IngestionItemSummary(
            nonterminal_count=sum(row.status not in terminal for row in rows),
            error_count=sum(
                row.status == IngestionItemStatus.VALIDATION_FAILED.value
                or row.account_outcome == AccountOutcome.FAILED.value
                or row.contact_outcome == ContactOutcome.FAILED.value
                or row.enrichment_outcome == EnrichmentOutcome.FAILED.value
                for row in rows
            ),
        )


class SqlAlchemyIngestionAccountRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create(self, account: Account) -> CreatedRecord[Account]:
        created = (
            await self._session.execute(
                insert(AccountModel)
                .values(
                    id=account.id,
                    organization_id=account.organization_id,
                    company_name=account.company_name,
                    domain=account.domain.value,
                    created_at=account.created_at,
                )
                .on_conflict_do_nothing(index_elements=["organization_id", "domain"])
                .returning(AccountModel)
            )
        ).scalar_one_or_none()
        if created is not None:
            return CreatedRecord(_account(created), True)
        existing = (
            await self._session.execute(
                select(AccountModel).where(
                    AccountModel.organization_id == account.organization_id,
                    AccountModel.domain == account.domain.value,
                )
            )
        ).scalar_one()
        return CreatedRecord(_account(existing), False)


class SqlAlchemyIngestionContactRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create(self, contact: Contact) -> CreatedRecord[Contact]:
        created = (
            await self._session.execute(
                insert(ContactModel)
                .values(
                    id=contact.id,
                    organization_id=contact.organization_id,
                    account_id=contact.account_id,
                    email=contact.email.value,
                    full_name=contact.full_name,
                    title=contact.title,
                )
                .on_conflict_do_nothing(index_elements=["organization_id", "email"])
                .returning(ContactModel)
            )
        ).scalar_one_or_none()
        if created is not None:
            return CreatedRecord(_contact(created), True)
        existing = (
            await self._session.execute(
                select(ContactModel).where(
                    ContactModel.organization_id == contact.organization_id,
                    ContactModel.email == contact.email.value,
                )
            )
        ).scalar_one()
        return CreatedRecord(_contact(existing), False)


class SqlAlchemyAccountEnrichmentRepository:
    """Append-only adapter; conflicts return the immutable existing snapshot."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create(
        self, enrichment: AccountEnrichmentRecord
    ) -> CreatedRecord[AccountEnrichmentRecord]:
        profile = enrichment.profile
        created = (
            await self._session.execute(
                insert(AccountEnrichmentModel)
                .values(
                    id=enrichment.id,
                    ingestion_job_id=enrichment.ingestion_job_id,
                    organization_id=enrichment.organization_id,
                    account_id=enrichment.account_id,
                    provider=profile.provider,
                    schema_version=profile.schema_version,
                    profile_json=profile.model_dump(),
                    created_at=enrichment.created_at,
                )
                .on_conflict_do_nothing(
                    index_elements=[
                        "ingestion_job_id",
                        "account_id",
                        "provider",
                        "schema_version",
                    ]
                )
                .returning(AccountEnrichmentModel)
            )
        ).scalar_one_or_none()
        if created is not None:
            return CreatedRecord(_enrichment(created), True)
        existing = (
            await self._session.execute(
                select(AccountEnrichmentModel).where(
                    AccountEnrichmentModel.ingestion_job_id == enrichment.ingestion_job_id,
                    AccountEnrichmentModel.organization_id == enrichment.organization_id,
                    AccountEnrichmentModel.account_id == enrichment.account_id,
                    AccountEnrichmentModel.provider == profile.provider,
                    AccountEnrichmentModel.schema_version == profile.schema_version,
                )
            )
        ).scalar_one()
        return CreatedRecord(_enrichment(existing), False)
