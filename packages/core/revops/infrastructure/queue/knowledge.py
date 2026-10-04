"""Bounded worker orchestration for versioned knowledge processing."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from revops.application.ports import Clock, EmbeddingProvider, KnowledgeUnitOfWorkFactory
from revops.application.use_cases.knowledge import (
    KnowledgeProcessingError,
    ProcessKnowledgeDocument,
    RecordKnowledgeProcessingFailure,
)
from revops.domain.entities.knowledge import KnowledgeVersionStatus
from revops.infrastructure.persistence.knowledge_unit_of_work import (
    SqlAlchemyKnowledgeUnitOfWork,
)

MAX_KNOWLEDGE_TASK_RETRIES = 2


class KnowledgeWorkerError(RuntimeError):
    """Sanitized infrastructure failure safe to expose to Celery."""

    def __init__(self, failure_code: str) -> None:
        self.failure_code = failure_code[:128]
        super().__init__(self.failure_code)


class KnowledgeWorkerRetryError(KnowledgeWorkerError):
    """A retryable failure that contains no raw provider or database message."""


@dataclass(frozen=True, slots=True)
class KnowledgeWorkerResult:
    version_id: UUID
    status: KnowledgeVersionStatus
    failure_code: str | None = None
    should_retry: bool = False


class KnowledgeWorkerProcessor:
    """Compose the application use cases and classify only safe operational failures."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        embeddings: EmbeddingProvider,
        clock: Clock,
    ) -> None:
        self._session_factory = session_factory
        self._embeddings = embeddings
        self._clock = clock

    def _uow_factory(self) -> KnowledgeUnitOfWorkFactory:
        def create() -> SqlAlchemyKnowledgeUnitOfWork:
            return SqlAlchemyKnowledgeUnitOfWork(self._session_factory(), close_on_exit=True)

        return create

    async def process(
        self,
        *,
        corpus_id: UUID,
        version_id: UUID,
        delivery_id: str,
        attempt: int,
        terminal_attempt: bool,
    ) -> KnowledgeWorkerResult:
        factory = self._uow_factory()
        try:
            version = await ProcessKnowledgeDocument(
                factory, self._embeddings, self._clock
            ).execute(
                corpus_id=corpus_id,
                version_id=version_id,
                delivery_id=delivery_id,
                attempt=attempt,
            )
            return KnowledgeWorkerResult(version.id, version.status)
        except KnowledgeProcessingError as exc:
            return await self._record_failure(
                factory=factory,
                corpus_id=corpus_id,
                version_id=version_id,
                delivery_id=delivery_id,
                attempt=attempt,
                failure_code=exc.failure_code,
                retryable=exc.retryable,
                terminal=terminal_attempt or not exc.retryable,
            )
        except (OperationalError, DBAPIError):
            return await self._record_failure(
                factory=factory,
                corpus_id=corpus_id,
                version_id=version_id,
                delivery_id=delivery_id,
                attempt=attempt,
                failure_code="persistence_unavailable",
                retryable=True,
                terminal=terminal_attempt,
            )
        except Exception:
            return await self._record_failure(
                factory=factory,
                corpus_id=corpus_id,
                version_id=version_id,
                delivery_id=delivery_id,
                attempt=attempt,
                failure_code="unexpected_processing_error",
                retryable=False,
                terminal=True,
            )

    async def _record_failure(
        self,
        *,
        factory: KnowledgeUnitOfWorkFactory,
        corpus_id: UUID,
        version_id: UUID,
        delivery_id: str,
        attempt: int,
        failure_code: str,
        retryable: bool,
        terminal: bool,
    ) -> KnowledgeWorkerResult:
        try:
            version = await RecordKnowledgeProcessingFailure(factory, self._clock).execute(
                corpus_id=corpus_id,
                version_id=version_id,
                delivery_id=delivery_id,
                attempt=attempt,
                failure_code=failure_code,
                retryable=retryable,
                terminal=terminal,
            )
        except Exception as exc:
            raise KnowledgeWorkerRetryError("processing_failure_audit_unavailable") from exc
        return KnowledgeWorkerResult(
            version.id,
            version.status,
            failure_code,
            should_retry=retryable and not terminal,
        )
