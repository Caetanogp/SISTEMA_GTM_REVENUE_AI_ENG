"""Queue adapters for asynchronous application use cases."""

from revops.infrastructure.queue.celery import (
    DEDUPLICATION_SCAN_TASK_NAME,
    INGESTION_TASK_NAME,
    CeleryDeduplicationDispatcher,
    CeleryIngestionDispatcher,
    create_celery_app,
)
from revops.infrastructure.queue.deduplication import (
    CANDIDATE_LIMIT_FAILURE,
    MAX_SCAN_CANDIDATES,
    MAX_SCAN_RECORDS,
    RECORD_LIMIT_FAILURE,
    DeduplicationScanLifecycle,
    DeduplicationScanNotFoundError,
    DeduplicationScanProcessor,
    ProcessDeduplicationScanResult,
)

__all__ = [
    "CANDIDATE_LIMIT_FAILURE",
    "DEDUPLICATION_SCAN_TASK_NAME",
    "INGESTION_TASK_NAME",
    "MAX_SCAN_CANDIDATES",
    "MAX_SCAN_RECORDS",
    "RECORD_LIMIT_FAILURE",
    "CeleryDeduplicationDispatcher",
    "CeleryIngestionDispatcher",
    "DeduplicationScanLifecycle",
    "DeduplicationScanNotFoundError",
    "DeduplicationScanProcessor",
    "ProcessDeduplicationScanResult",
    "create_celery_app",
]
