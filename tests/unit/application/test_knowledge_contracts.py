"""Application contracts for versioned knowledge ingestion."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from types import TracebackType
from uuid import UUID

import pytest
from pydantic import ValidationError
from revops.application.dto import (
    CorpusRevision,
    EmbeddingBatch,
    KnowledgeChunkEmbedding,
    KnowledgeCorpus,
    KnowledgeDocumentVersion,
    KnowledgeRevisionActivation,
    SubmitKnowledgeDocumentArgs,
)
from revops.application.ports import (
    CorpusRevisionRepository,
    EmbeddingProvider,
    KnowledgeCorpusRepository,
    KnowledgeDocumentRepository,
    KnowledgeJobDispatcher,
    KnowledgeProcessingEventRepository,
    KnowledgeUnitOfWork,
)
from revops.domain.entities.knowledge import KnowledgeDocument, KnowledgeVersionStatus


def _args() -> SubmitKnowledgeDocumentArgs:
    return SubmitKnowledgeDocumentArgs(
        document_key="sales/discovery",
        category="sales_playbook",
        language="en",
        format="md",
        content="# Discovery\n\nUse approved discovery questions.",
        metadata={"source": "admin"},
    )


def test_tenant_submission_excludes_scope_and_converts_to_organization_document() -> None:
    assert "scope" not in SubmitKnowledgeDocumentArgs.model_fields
    document = _args().to_domain()
    assert document.scope == "organization"
    assert document.document_key == "sales/discovery"


def test_tenant_submission_rejects_untrusted_extra_fields() -> None:
    with pytest.raises(ValidationError):
        SubmitKnowledgeDocumentArgs.model_validate({**_args().model_dump(), "scope": "platform"})


class _FakeDocuments:
    async def get_version(
        self, corpus_id: UUID, version_id: UUID
    ) -> KnowledgeDocumentVersion | None:
        return None

    async def get_by_idempotency_key(
        self, corpus_id: UUID, idempotency_key: str
    ) -> KnowledgeDocumentVersion | None:
        return None

    async def reserve_draft(
        self,
        *,
        corpus_id: UUID,
        requested_by: UUID,
        document: KnowledgeDocument,
        idempotency_key: str,
        created_at: datetime,
    ) -> KnowledgeDocumentVersion:
        raise NotImplementedError

    async def get_version_for_update(
        self, corpus_id: UUID, version_id: UUID
    ) -> KnowledgeDocumentVersion | None:
        raise NotImplementedError

    async def transition_status(
        self,
        *,
        corpus_id: UUID,
        version_id: UUID,
        status: KnowledgeVersionStatus,
        failure_code: str | None = None,
    ) -> KnowledgeDocumentVersion:
        raise NotImplementedError

    async def mark_ready(
        self,
        *,
        corpus_id: UUID,
        version_id: UUID,
        embedding_model: str,
        embedding_dimension: int,
    ) -> KnowledgeDocumentVersion:
        raise NotImplementedError

    async def list_versions(
        self, corpus_id: UUID, *, offset: int, limit: int
    ) -> Sequence[KnowledgeDocumentVersion]:
        return []


class _FakeEmbeddings:
    async def embed(self, texts: Sequence[str]) -> EmbeddingBatch:
        return EmbeddingBatch(model="fake", dimension=2, vectors=tuple((1.0, 0.0) for _ in texts))


class _FakeRevisions:
    async def publish(
        self,
        *,
        corpus_id: UUID,
        version_id: UUID,
        chunks: Sequence[KnowledgeChunkEmbedding],
        activated_by: UUID,
        created_at: datetime,
    ) -> CorpusRevision:
        raise NotImplementedError

    async def get_active(self, corpus_id: UUID) -> CorpusRevision | None:
        return None

    async def activate(
        self,
        *,
        corpus_id: UUID,
        revision_id: UUID,
        activated_by: UUID,
        idempotency_key: str,
        created_at: datetime,
    ) -> CorpusRevision:
        raise NotImplementedError

    async def list_activation_history(
        self, corpus_id: UUID, *, offset: int, limit: int
    ) -> Sequence[KnowledgeRevisionActivation]:
        return []


class _FakeDispatcher:
    async def publish(self, *, corpus_id: UUID, version_id: UUID) -> None: ...


class _FakeProcessingEvents:
    async def append(self, event: object) -> None: ...


class _FakeCorpora:
    async def get_platform(self) -> KnowledgeCorpus:
        raise NotImplementedError

    async def get_organization(self, organization_id: UUID) -> KnowledgeCorpus:
        raise NotImplementedError


class _FakeKnowledgeUnitOfWork:
    documents: KnowledgeDocumentRepository
    corpora: KnowledgeCorpusRepository
    revisions: CorpusRevisionRepository
    processing_events: KnowledgeProcessingEventRepository

    def __init__(self) -> None:
        self.documents = _FakeDocuments()
        self.corpora = _FakeCorpora()
        self.revisions = _FakeRevisions()
        self.processing_events = _FakeProcessingEvents()

    async def __aenter__(self) -> _FakeKnowledgeUnitOfWork:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


def test_knowledge_ports_are_structural_protocols() -> None:
    assert isinstance(_FakeDocuments(), KnowledgeDocumentRepository)
    assert isinstance(_FakeCorpora(), KnowledgeCorpusRepository)
    assert isinstance(_FakeEmbeddings(), EmbeddingProvider)
    assert isinstance(_FakeRevisions(), CorpusRevisionRepository)
    assert isinstance(_FakeDispatcher(), KnowledgeJobDispatcher)
    assert isinstance(_FakeKnowledgeUnitOfWork(), KnowledgeUnitOfWork)


def test_knowledge_repositories_expose_no_delete_or_generic_update() -> None:
    for port in (KnowledgeDocumentRepository, CorpusRevisionRepository):
        for forbidden in ("delete", "remove", "update", "save"):
            assert not hasattr(port, forbidden)


async def test_embedding_provider_contract_preserves_ordered_batch_shape() -> None:
    batch = await _FakeEmbeddings().embed(("first", "second"))
    assert batch.vectors == ((1.0, 0.0), (1.0, 0.0))
