"""SQLAlchemy ingestion adapters."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from revops.application.dto import CanonicalIngestionRecord, StagedIngestionItem, StagedIngestionJob
from revops.domain.entities.ingestion import (
    AccountOutcome,
    ContactOutcome,
    EnrichmentOutcome,
    IngestionItemStatus,
    IngestionJobStatus,
)
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
