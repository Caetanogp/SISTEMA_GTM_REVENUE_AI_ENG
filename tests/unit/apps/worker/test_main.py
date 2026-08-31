from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from celery.exceptions import Reject
from revops.application.dto import ProcessIngestionResult
from revops.domain.entities.ingestion import IngestionJobStatus
from revops.infrastructure.queue import INGESTION_TASK_NAME

from apps.worker import main


def test_worker_registers_the_stable_ingestion_task_name() -> None:
    assert main.app is main.celery_app
    assert main.process_ingestion.name == INGESTION_TASK_NAME


def test_worker_rejects_malformed_identifiers_without_requeueing() -> None:
    with pytest.raises(Reject) as caught:
        main.process_ingestion.run(organization_id="not-a-uuid", job_id=str(uuid4()))

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
