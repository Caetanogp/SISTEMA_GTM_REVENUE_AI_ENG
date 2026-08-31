from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from revops.infrastructure.queue import INGESTION_TASK_NAME, CeleryIngestionDispatcher


class _Publisher:
    def __init__(self, *, failure: Exception | None = None) -> None:
        self.failure = failure
        self.calls: list[tuple[str, dict[str, object], dict[str, object]]] = []

    def send_task(
        self,
        name: str,
        args: list[object] | None = None,
        kwargs: dict[str, object] | None = None,
        **options: Any,
    ) -> object:
        if self.failure is not None:
            raise self.failure
        self.calls.append((name, kwargs or {}, options))
        return object()


async def test_dispatcher_publishes_only_tenant_and_job_identifiers() -> None:
    publisher = _Publisher()
    organization_id, job_id = uuid4(), uuid4()

    await CeleryIngestionDispatcher(publisher).publish(
        organization_id=organization_id, job_id=job_id
    )

    name, kwargs, options = publisher.calls[0]
    assert name == INGESTION_TASK_NAME
    assert kwargs == {"organization_id": str(organization_id), "job_id": str(job_id)}
    assert options["retry"] is True
    assert options["retry_policy"] == {
        "max_retries": 3,
        "interval_start": 0.2,
        "interval_step": 0.5,
        "interval_max": 1.0,
    }


async def test_dispatcher_propagates_broker_failure_to_confirmation() -> None:
    dispatcher = CeleryIngestionDispatcher(_Publisher(failure=ConnectionError("offline")))

    with pytest.raises(ConnectionError, match="offline"):
        await dispatcher.publish(organization_id=uuid4(), job_id=uuid4())
