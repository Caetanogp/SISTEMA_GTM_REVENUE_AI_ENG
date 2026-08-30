from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from types import TracebackType
from typing import Self
from uuid import UUID, uuid4

import pytest
from revops.application.dto import IngestionRecordInput, StagedIngestionItem, StagedIngestionJob
from revops.application.ports import (
    IngestionItemRepository,
    IngestionJobRepository,
    IngestionUnitOfWork,
    IngestionUnitOfWorkFactory,
)
from revops.application.use_cases.ingestion import (
    ConfirmIngestion,
    GetIngestionJob,
    IngestionIdempotencyConflictError,
    ListIngestionItems,
    ProcessIngestionJob,
    StageIngestion,
)
from revops.domain.entities.ingestion import IngestionJobStatus


class _FakeJobs(IngestionJobRepository):
    def __init__(self) -> None:
        self.by_id: dict[UUID, StagedIngestionJob] = {}

    async def get(self, organization_id: UUID, job_id: UUID) -> StagedIngestionJob | None:
        job = self.by_id.get(job_id)
        return job if job and job.organization_id == organization_id else None

    async def get_by_idempotency_key(
        self, organization_id: UUID, idempotency_key: str
    ) -> StagedIngestionJob | None:
        return next(
            (
                job
                for job in self.by_id.values()
                if job.organization_id == organization_id and job.idempotency_key == idempotency_key
            ),
            None,
        )

    async def add(self, job: StagedIngestionJob) -> None:
        self.by_id[job.id] = job

    async def set_status(
        self, organization_id: UUID, job_id: UUID, status: IngestionJobStatus
    ) -> StagedIngestionJob:
        job = self.by_id[job_id]
        assert job.organization_id == organization_id
        updated = replace(job, status=status)
        self.by_id[job_id] = updated
        return updated


class _FakeItems(IngestionItemRepository):
    def __init__(self) -> None:
        self.by_job: dict[UUID, list[StagedIngestionItem]] = {}

    async def add_many(self, job_id: UUID, items: Sequence[StagedIngestionItem]) -> None:
        self.by_job[job_id] = list(items)

    async def list_for_job(
        self, organization_id: UUID, job_id: UUID, *, offset: int, limit: int
    ) -> list[StagedIngestionItem]:
        return self.by_job[job_id][offset : offset + limit]

    async def list_processable_domains(self, organization_id: UUID, job_id: UUID) -> list[str]:
        return sorted(
            {
                item.record.domain
                for item in self.by_job[job_id]
                if item.record is not None and item.status.value == "pending"
            }
        )

    async def lock_domain_items(
        self, organization_id: UUID, job_id: UUID, domain: str
    ) -> list[StagedIngestionItem]:
        return [
            item
            for item in self.by_job[job_id]
            if item.record is not None and item.record.domain == domain
        ]


class _FakeUow:
    jobs: IngestionJobRepository
    items: IngestionItemRepository

    def __init__(self, jobs: _FakeJobs, items: _FakeItems) -> None:
        self.jobs = jobs
        self.items = items
        self.commits = 0

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        return None


class _FakeDispatcher:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[UUID, UUID]] = []

    async def publish(self, *, organization_id: UUID, job_id: UUID) -> None:
        self.calls.append((organization_id, job_id))
        if self.fail:
            raise RuntimeError("broker unavailable")


def _factory() -> tuple[IngestionUnitOfWorkFactory, _FakeJobs, _FakeItems, list[_FakeUow]]:
    jobs = _FakeJobs()
    items = _FakeItems()
    uows: list[_FakeUow] = []

    def create() -> IngestionUnitOfWork:
        uow = _FakeUow(jobs, items)
        uows.append(uow)
        return uow

    return create, jobs, items, uows


def _record(**overrides: str | None) -> IngestionRecordInput:
    values: dict[str, str | None] = {
        "company_name": "Acme",
        "domain": "https://www.acme.test/path",
        "email": "Ada@Acme.test",
        "full_name": "Ada Lovelace",
        "title": "CTO",
    }
    values.update(overrides)
    return IngestionRecordInput(**values)


async def test_stage_normalizes_rows_and_keeps_business_errors_per_row() -> None:
    factory, _, _, _ = _factory()
    stage = StageIngestion(factory)

    result = await stage.execute(
        organization_id=uuid4(),
        requested_by=uuid4(),
        source="  csv  ",
        idempotency_key="batch-1",
        records=[_record(), _record(company_name="")],
    )

    valid, invalid = result.job.items
    assert result.job.status is IngestionJobStatus.STAGED
    assert valid.record is not None
    assert valid.record.domain == "acme.test"
    assert valid.record.email == "ada@acme.test"
    assert invalid.validation_codes == ("company_name_required",)


async def test_stage_replays_identical_content_and_rejects_key_reuse() -> None:
    factory, _, _, _ = _factory()
    stage = StageIngestion(factory)
    organization_id = uuid4()
    requested_by = uuid4()
    first = await stage.execute(
        organization_id=organization_id,
        requested_by=requested_by,
        source="api",
        idempotency_key="same-key",
        records=[_record()],
    )
    replay = await stage.execute(
        organization_id=organization_id,
        requested_by=requested_by,
        source=" api ",
        idempotency_key="same-key",
        records=[_record(domain="acme.test")],
    )

    assert replay.replayed is True
    assert replay.job.id == first.job.id
    with pytest.raises(IngestionIdempotencyConflictError):
        await stage.execute(
            organization_id=organization_id,
            requested_by=requested_by,
            source="api",
            idempotency_key="same-key",
            records=[_record(company_name="Different")],
        )


async def test_stage_marks_conflicting_domain_rows_invalid_together() -> None:
    factory, _, _, _ = _factory()

    result = await StageIngestion(factory).execute(
        organization_id=uuid4(),
        requested_by=uuid4(),
        source="api",
        idempotency_key="conflict",
        records=[
            _record(company_name="Acme"),
            _record(company_name="Other", email=None, full_name=None, title=None),
        ],
    )

    assert [item.validation_codes for item in result.job.items] == [
        ("domain_company_conflict",),
        ("domain_company_conflict",),
    ]
    assert result.job.status is IngestionJobStatus.VALIDATION_FAILED


async def test_confirmation_commits_before_publish_and_safely_republishes_queued_job() -> None:
    factory, jobs, _, uows = _factory()
    stage = await StageIngestion(factory).execute(
        organization_id=uuid4(),
        requested_by=uuid4(),
        source="api",
        idempotency_key="confirm",
        records=[_record()],
    )
    dispatcher = _FakeDispatcher()
    confirm = ConfirmIngestion(factory, dispatcher)

    first = await confirm.execute(organization_id=stage.job.organization_id, job_id=stage.job.id)
    second = await confirm.execute(organization_id=stage.job.organization_id, job_id=stage.job.id)

    assert first.published is True
    assert second.replayed is True
    assert dispatcher.calls == [(stage.job.organization_id, stage.job.id)] * 2
    assert uows[-2].commits == 1
    assert jobs.by_id[stage.job.id].status is IngestionJobStatus.QUEUED


async def test_publication_failure_records_queue_failed_for_a_retry() -> None:
    factory, jobs, _, _ = _factory()
    stage = await StageIngestion(factory).execute(
        organization_id=uuid4(),
        requested_by=uuid4(),
        source="api",
        idempotency_key="failure",
        records=[_record()],
    )

    with pytest.raises(RuntimeError, match="broker"):
        await ConfirmIngestion(factory, _FakeDispatcher(fail=True)).execute(
            organization_id=stage.job.organization_id, job_id=stage.job.id
        )

    assert jobs.by_id[stage.job.id].status is IngestionJobStatus.QUEUE_FAILED


async def test_read_use_cases_are_tenant_scoped_and_processing_groups_domains() -> None:
    factory, _, _, _ = _factory()
    stage = await StageIngestion(factory).execute(
        organization_id=uuid4(),
        requested_by=uuid4(),
        source="api",
        idempotency_key="groups",
        records=[_record(), _record(domain="beta.test", email=None, full_name=None, title=None)],
    )
    dispatcher = _FakeDispatcher()
    await ConfirmIngestion(factory, dispatcher).execute(
        organization_id=stage.job.organization_id, job_id=stage.job.id
    )

    assert (
        await GetIngestionJob(factory).execute(
            organization_id=stage.job.organization_id, job_id=stage.job.id
        )
    ).id == stage.job.id
    assert (
        len(
            await ListIngestionItems(factory).execute(
                organization_id=stage.job.organization_id, job_id=stage.job.id, offset=0, limit=1
            )
        )
        == 1
    )
    assert await ProcessIngestionJob(factory).execute(
        organization_id=stage.job.organization_id, job_id=stage.job.id
    ) == ("acme.test", "beta.test")
