"""Celery publication adapters for asynchronous platform jobs."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from celery import Celery

INGESTION_TASK_NAME = "revops.ingestion.process"
DEDUPLICATION_SCAN_TASK_NAME = "revops.deduplication.scan"
_PUBLISH_RETRY_POLICY = {
    "max_retries": 3,
    "interval_start": 0.2,
    "interval_step": 0.5,
    "interval_max": 1.0,
}


class CeleryPublisher(Protocol):
    def send_task(
        self,
        name: str,
        args: list[object] | None = None,
        kwargs: dict[str, object] | None = None,
        **options: Any,
    ) -> object: ...


def create_celery_app(*, broker_url: str, result_backend: str) -> Celery:
    app = Celery("revops", broker=broker_url, backend=result_backend)
    app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        broker_connection_retry_on_startup=True,
        broker_connection_timeout=5,
    )
    return app


@dataclass(frozen=True, slots=True)
class CeleryIngestionDispatcher:
    publisher: CeleryPublisher

    async def publish(self, *, organization_id: UUID, job_id: UUID) -> None:
        await asyncio.to_thread(self._publish, organization_id, job_id)

    def _publish(self, organization_id: UUID, job_id: UUID) -> None:
        self.publisher.send_task(
            INGESTION_TASK_NAME,
            kwargs={
                "organization_id": str(organization_id),
                "job_id": str(job_id),
            },
            retry=True,
            retry_policy=_PUBLISH_RETRY_POLICY,
        )


@dataclass(frozen=True, slots=True)
class CeleryDeduplicationDispatcher:
    """Publish a tenant-scoped scan without placing CRM data on the broker."""

    publisher: CeleryPublisher

    async def publish(self, *, organization_id: UUID, scan_id: UUID) -> None:
        await asyncio.to_thread(self._publish, organization_id, scan_id)

    def _publish(self, organization_id: UUID, scan_id: UUID) -> None:
        self.publisher.send_task(
            DEDUPLICATION_SCAN_TASK_NAME,
            kwargs={
                "organization_id": str(organization_id),
                "scan_id": str(scan_id),
            },
            retry=True,
            retry_policy=_PUBLISH_RETRY_POLICY,
        )
