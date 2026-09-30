"""Unit tests for the knowledge lifecycle application orchestration."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from types import TracebackType
from typing import cast
from uuid import UUID, uuid4

import pytest
from revops.application.dto import (
    CorpusRevision,
    EmbeddingBatch,
    KnowledgeAdminContext,
    KnowledgeCorpus,
    KnowledgeDocumentVersion,
    KnowledgeProcessingEvent,
    SubmitKnowledgeDocumentArgs,
)
from revops.application.ports import KnowledgeUnitOfWork
from revops.application.use_cases.knowledge import (
    ActivateKnowledgeRevision,
    ConfirmKnowledgeDocument,
    KnowledgeLifecycleError,
    KnowledgeProcessingError,
    ProcessKnowledgeDocument,
    RecordKnowledgeProcessingFailure,
    RetireKnowledgeVersion,
    SubmitKnowledgeDocument,
)
from revops.domain.entities.knowledge import (
    KnowledgeCategory,
    KnowledgeFormat,
    KnowledgeLanguage,
    KnowledgeScope,
    KnowledgeVersionStatus,
)

ACTOR_ID = UUID("00000000-0000-0000-0000-000000000001")
ORGANIZATION_ID = UUID("00000000-0000-0000-0000-000000000002")
CORPUS_ID = UUID("00000000-0000-0000-0000-000000000003")


class _Clock:
    def now(self) -> datetime:
        return datetime(2026, 9, 29, tzinfo=UTC)


class _Documents:
    def __init__(self) -> None:
        self.versions: dict[UUID, KnowledgeDocumentVersion] = {}

    async def get_version(
        self, corpus_id: UUID, version_id: UUID
    ) -> KnowledgeDocumentVersion | None:
        version = self.versions.get(version_id)
        return version if version is not None and version.corpus_id == corpus_id else None

    async def get_version_for_update(
        self, corpus_id: UUID, version_id: UUID
    ) -> KnowledgeDocumentVersion | None:
        return await self.get_version(corpus_id, version_id)

    async def get_by_idempotency_key(
        self, corpus_id: UUID, idempotency_key: str
    ) -> KnowledgeDocumentVersion | None:
        return next(
            (
                version
                for version in self.versions.values()
                if version.corpus_id == corpus_id and version.idempotency_key == idempotency_key
            ),
            None,
        )

    async def reserve_draft(
        self, *, corpus_id, requested_by, document, idempotency_key, created_at
    ):
        existing = await self.get_by_idempotency_key(corpus_id, idempotency_key)
        if existing is not None:
            return existing
        version = KnowledgeDocumentVersion(
            id=uuid4(),
            document_id=uuid4(),
            corpus_id=corpus_id,
            requested_by=requested_by,
            document=document,
            status=KnowledgeVersionStatus.DRAFT,
            idempotency_key=idempotency_key,
            created_at=created_at,
        )
        self.versions[version.id] = version
        return version

    async def transition_status(self, *, corpus_id, version_id, status, failure_code=None):
        version = await self.get_version(corpus_id, version_id)
        assert version is not None
        updated = replace(version, status=status, failure_code=failure_code)
        self.versions[version_id] = updated
        return updated

    async def mark_ready(self, *, corpus_id, version_id, embedding_model, embedding_dimension):
        version = await self.get_version(corpus_id, version_id)
        assert version is not None
        updated = replace(
            version,
            status=KnowledgeVersionStatus.READY,
            embedding_model=embedding_model,
            embedding_dimension=embedding_dimension,
            failure_code=None,
        )
        self.versions[version_id] = updated
        return updated

    async def list_versions(self, corpus_id, *, offset, limit):
        return tuple(
            version for version in self.versions.values() if version.corpus_id == corpus_id
        )[offset : offset + limit]


class _Corpora:
    async def get_platform(self):
        raise NotImplementedError

    async def get_organization(self, organization_id: UUID) -> KnowledgeCorpus:
        return KnowledgeCorpus(CORPUS_ID, KnowledgeScope.ORGANIZATION, organization_id)


class _Revisions:
    def __init__(self) -> None:
        self.published: list[tuple[UUID, tuple[object, ...]]] = []
        self.activated: list[UUID] = []

    async def publish(self, *, corpus_id, version_id, chunks, activated_by, created_at):
        self.published.append((version_id, tuple(chunks)))
        return CorpusRevision(uuid4(), corpus_id, version_id, "hash", activated_by, created_at)

    async def get_active(self, corpus_id):
        return None

    async def activate(self, *, corpus_id, revision_id, activated_by, idempotency_key, created_at):
        self.activated.append(revision_id)
        return CorpusRevision(uuid4(), corpus_id, uuid4(), "hash", activated_by, created_at)

    async def list_activation_history(self, corpus_id, *, offset, limit):
        return ()


class _ProcessingEvents:
    def __init__(self) -> None:
        self.events: list[KnowledgeProcessingEvent] = []

    async def append(self, event: KnowledgeProcessingEvent) -> None:
        self.events.append(event)


class _Dispatcher:
    def __init__(self) -> None:
        self.calls: list[tuple[UUID, UUID]] = []

    async def publish(self, *, corpus_id: UUID, version_id: UUID) -> None:
        self.calls.append((corpus_id, version_id))


class _Embeddings:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[str, ...]] = []

    async def embed(self, texts: Sequence[str]) -> EmbeddingBatch:
        self.calls.append(tuple(texts))
        if self.fail:
            raise RuntimeError("provider unavailable")
        return EmbeddingBatch("fake", 2, tuple((1.0, 0.0) for _ in texts))


class _Uow:
    def __init__(self, documents: _Documents, revisions: _Revisions) -> None:
        self.documents = documents
        self.corpora = _Corpora()
        self.revisions = revisions
        self.processing_events = _ProcessingEvents()

    async def __aenter__(self) -> _Uow:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


class _Factory:
    def __init__(self) -> None:
        self.documents = _Documents()
        self.revisions = _Revisions()
        self.processing_events = _ProcessingEvents()

    def __call__(self) -> KnowledgeUnitOfWork:
        uow = _Uow(self.documents, self.revisions)
        uow.processing_events = self.processing_events
        return cast(KnowledgeUnitOfWork, uow)


def _context() -> KnowledgeAdminContext:
    return KnowledgeAdminContext(actor_id=ACTOR_ID, organization_id=ORGANIZATION_ID, role="admin")


def _args(content: str = "# Product\n\nApproved content") -> SubmitKnowledgeDocumentArgs:
    return SubmitKnowledgeDocumentArgs(
        document_key="product/overview",
        category=KnowledgeCategory.PRODUCT,
        language=KnowledgeLanguage.ENGLISH,
        format=KnowledgeFormat.MARKDOWN,
        content=content,
    )


async def _submit(factory: _Factory) -> KnowledgeDocumentVersion:
    return await SubmitKnowledgeDocument(factory, _Clock()).execute(
        context=_context(), args=_args(), idempotency_key="draft-1"
    )


@pytest.mark.asyncio
async def test_confirmation_commits_then_dispatches_and_replays() -> None:
    factory = _Factory()
    dispatcher = _Dispatcher()
    version = await _submit(factory)
    confirm = ConfirmKnowledgeDocument(factory, dispatcher, _Clock())

    confirmed = await confirm.execute(context=_context(), version_id=version.id)
    replay = await confirm.execute(context=_context(), version_id=version.id)

    assert confirmed.status is KnowledgeVersionStatus.CONFIRMED
    assert replay.status is KnowledgeVersionStatus.CONFIRMED
    assert dispatcher.calls == [(CORPUS_ID, version.id), (CORPUS_ID, version.id)]


@pytest.mark.asyncio
async def test_processing_embeds_in_batches_and_publishes_only_after_ready() -> None:
    factory = _Factory()
    version = await _submit(factory)
    await ConfirmKnowledgeDocument(factory, _Dispatcher(), _Clock()).execute(
        context=_context(), version_id=version.id
    )
    embeddings = _Embeddings()

    result = await ProcessKnowledgeDocument(factory, embeddings, _Clock()).execute(
        corpus_id=CORPUS_ID, version_id=version.id, delivery_id="delivery-1", attempt=1
    )

    assert result.status is KnowledgeVersionStatus.READY
    assert result.embedding_model == "fake"
    assert result.embedding_dimension == 2
    assert embeddings.calls == [("# Product\n\nApproved content",)]
    assert len(factory.revisions.published) == 1


@pytest.mark.asyncio
async def test_processing_failure_marks_version_failed_and_does_not_publish() -> None:
    factory = _Factory()
    version = await _submit(factory)
    await ConfirmKnowledgeDocument(factory, _Dispatcher(), _Clock()).execute(
        context=_context(), version_id=version.id
    )

    with pytest.raises(KnowledgeProcessingError, match="embedding_provider_error"):
        await ProcessKnowledgeDocument(factory, _Embeddings(fail=True), _Clock()).execute(
            corpus_id=CORPUS_ID, version_id=version.id, delivery_id="delivery-1", attempt=1
        )

    assert factory.documents.versions[version.id].status is KnowledgeVersionStatus.PROCESSING
    assert factory.revisions.published == []
    failed = await RecordKnowledgeProcessingFailure(factory, _Clock()).execute(
        corpus_id=CORPUS_ID,
        version_id=version.id,
        delivery_id="delivery-1",
        attempt=1,
        failure_code="embedding_provider_error",
        retryable=False,
        terminal=True,
    )
    assert failed.status is KnowledgeVersionStatus.FAILED


@pytest.mark.asyncio
async def test_retirement_and_historical_activation_are_admin_operations() -> None:
    factory = _Factory()
    version = await _submit(factory)
    await ConfirmKnowledgeDocument(factory, _Dispatcher(), _Clock()).execute(
        context=_context(), version_id=version.id
    )
    await ProcessKnowledgeDocument(factory, _Embeddings(), _Clock()).execute(
        corpus_id=CORPUS_ID, version_id=version.id, delivery_id="delivery-1", attempt=1
    )

    retired = await RetireKnowledgeVersion(factory).execute(
        context=_context(), version_id=version.id
    )
    revision_id = uuid4()
    await ActivateKnowledgeRevision(factory, _Clock()).execute(
        context=_context(), revision_id=revision_id, idempotency_key="activate-1"
    )

    assert retired.status is KnowledgeVersionStatus.RETIRED
    assert factory.revisions.activated == [revision_id]


@pytest.mark.asyncio
async def test_required_idempotency_key_is_rejected_before_repository_call() -> None:
    factory = _Factory()

    with pytest.raises(KnowledgeLifecycleError, match="Idempotency-Key"):
        await SubmitKnowledgeDocument(factory, _Clock()).execute(
            context=_context(), args=_args(), idempotency_key=" "
        )
