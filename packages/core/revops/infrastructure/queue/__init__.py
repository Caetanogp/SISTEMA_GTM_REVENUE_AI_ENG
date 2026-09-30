"""Queue adapters for asynchronous application use cases."""

from revops.infrastructure.queue.celery import (
    DEDUPLICATION_SCAN_TASK_NAME,
    INGESTION_TASK_NAME,
    KNOWLEDGE_PROCESSING_TASK_NAME,
    CeleryDeduplicationDispatcher,
    CeleryIngestionDispatcher,
    CeleryKnowledgeDispatcher,
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
from revops.infrastructure.queue.knowledge import (
    MAX_KNOWLEDGE_TASK_RETRIES,
    KnowledgeWorkerError,
    KnowledgeWorkerProcessor,
    KnowledgeWorkerResult,
    KnowledgeWorkerRetryError,
)

__all__ = [
    "CANDIDATE_LIMIT_FAILURE",
    "DEDUPLICATION_SCAN_TASK_NAME",
    "INGESTION_TASK_NAME",
    "KNOWLEDGE_PROCESSING_TASK_NAME",
    "MAX_KNOWLEDGE_TASK_RETRIES",
    "MAX_SCAN_CANDIDATES",
    "MAX_SCAN_RECORDS",
    "RECORD_LIMIT_FAILURE",
    "CeleryDeduplicationDispatcher",
    "CeleryIngestionDispatcher",
    "CeleryKnowledgeDispatcher",
    "DeduplicationScanLifecycle",
    "DeduplicationScanNotFoundError",
    "DeduplicationScanProcessor",
    "KnowledgeWorkerError",
    "KnowledgeWorkerProcessor",
    "KnowledgeWorkerResult",
    "KnowledgeWorkerRetryError",
    "ProcessDeduplicationScanResult",
    "create_celery_app",
]
