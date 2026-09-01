from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from celery.exceptions import Reject
from revops.application.dto import ProcessIngestionResult
from revops.domain.entities.deduplication import DeduplicationScanStatus
from revops.domain.entities.ingestion import IngestionJobStatus
from revops.infrastructure.queue import (
    DEDUPLICATION_SCAN_TASK_NAME,
    INGESTION_TASK_NAME,
    ProcessDeduplicationScanResult,
)

from apps.worker import main


def test_worker_registers_the_stable_ingestion_task_name() -> None:
    assert main.app is main.celery_app
    assert main.process_ingestion.name == INGESTION_TASK_NAME


def test_worker_registers_bounded_replay_safe_deduplication_task() -> None:
    assert main.process_deduplication_scan.name == DEDUPLICATION_SCAN_TASK_NAME
    assert main.process_deduplication_scan.max_retries == 5
    assert main.process_deduplication_scan.acks_late is True
    assert main.process_deduplication_scan.reject_on_worker_lost is True


def test_worker_rejects_malformed_identifiers_without_requeueing() -> None:
    with pytest.raises(Reject) as caught:
        main.process_ingestion.run(organization_id="not-a-uuid", job_id=str(uuid4()))

    assert caught.value.requeue is False


def test_deduplication_worker_rejects_malformed_identifiers_without_requeueing() -> None:
    with pytest.raises(Reject) as caught:
        main.process_deduplication_scan.run(
            organization_id=str(uuid4()),
            scan_id="not-a-uuid",
        )

    assert caught.value.requeue is False


def test_worker_delegates_valid_identifiers_to_the_application_use_case(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization_id, job_id = uuid4(), uuid4()
    calls: list[tuple[UUID, UUID]] = []

    def fake_run_ingestion(*, organization_id: UUID, job_id: UUID) -> ProcessIngestionResult:
        calls.append((organization_id, job_id))
        return ProcessIngestionResult(job_id, IngestionJobStatus.COMPLETED, ("acme.test",))

    monkeypatch.setattr(main, "_run_async_ingestion", fake_run_ingestion)

    result = main.process_ingestion.run(
        organization_id=str(organization_id),
        job_id=str(job_id),
    )

    assert calls == [(organization_id, job_id)]
    assert result == {
        "job_id": str(job_id),
        "status": "completed",
        "processed_domains": ["acme.test"],
    }


def test_worker_delegates_deduplication_identifiers_to_the_processor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization_id, scan_id = uuid4(), uuid4()
    calls: list[tuple[UUID, UUID]] = []

    def fake_run_scan(*, organization_id: UUID, scan_id: UUID) -> ProcessDeduplicationScanResult:
        calls.append((organization_id, scan_id))
        return ProcessDeduplicationScanResult(
            scan_id,
            DeduplicationScanStatus.COMPLETED,
            4,
            2,
        )

    monkeypatch.setattr(main, "_run_async_deduplication_scan", fake_run_scan)

    result = main.process_deduplication_scan.run(
        organization_id=str(organization_id),
        scan_id=str(scan_id),
    )

    assert calls == [(organization_id, scan_id)]
    assert result == {
        "scan_id": str(scan_id),
        "status": "completed",
        "record_count": 4,
        "candidate_count": 2,
        "failure_code": None,
    }
