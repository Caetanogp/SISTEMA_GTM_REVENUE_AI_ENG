"""Deterministic contract eval for versioned knowledge ingestion.

The suite uses only in-process fakes at application ports. It never opens a database connection,
contacts an embedding provider, or reads credentials.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

from pydantic import ValidationError
from revops.application.dto import (
    EmbeddingBatch,
    KnowledgeAdminContext,
    KnowledgeCorpus,
    KnowledgeDocumentVersion,
    SubmitKnowledgeDocumentArgs,
)
from revops.application.ports import KnowledgeUnitOfWork
from revops.application.use_cases.knowledge import (
    KnowledgeProcessingError,
    ProcessKnowledgeDocument,
    SubmitKnowledgeDocument,
)
from revops.domain.entities.knowledge import (
    KnowledgeCategory,
    KnowledgeDocument,
    KnowledgeFormat,
    KnowledgeLanguage,
    KnowledgeScope,
    KnowledgeVersionState,
    KnowledgeVersionStatus,
    chunk_content,
)
from revops.domain.errors import InvalidTransitionError, PolicyViolationError
from revops.infrastructure.embeddings.providers import DeterministicFakeEmbeddingProvider

DATASET_PATH = Path(__file__).resolve().parents[1] / "datasets" / "rag_ingestion_contract.jsonl"
ACTOR_ID = UUID("00000000-0000-0000-0000-000000000101")
ORGANIZATION_ID = UUID("00000000-0000-0000-0000-000000000102")
CORPUS_ID = UUID("00000000-0000-0000-0000-000000000103")


@dataclass(frozen=True, slots=True)
class ScoreResult:
    total: int
    correct: int
    failed_ids: list[str]

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0


def load_cases() -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in DATASET_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


class _Clock:
    def now(self) -> datetime:
        return datetime(2026, 10, 3, tzinfo=UTC)


class _Documents:
    def __init__(self) -> None:
        self.versions: dict[UUID, KnowledgeDocumentVersion] = {}

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
        self,
        *,
        corpus_id: UUID,
        requested_by: UUID,
        document: KnowledgeDocument,
        idempotency_key: str,
        created_at: datetime,
    ) -> KnowledgeDocumentVersion:
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

    async def get_version_for_update(
        self, corpus_id: UUID, version_id: UUID
    ) -> KnowledgeDocumentVersion | None:
        version = self.versions.get(version_id)
        return version if version is not None and version.corpus_id == corpus_id else None

    async def transition_status(
        self,
        *,
        corpus_id: UUID,
        version_id: UUID,
        status: KnowledgeVersionStatus,
        failure_code: str | None = None,
    ) -> KnowledgeDocumentVersion:
        version = await self.get_version_for_update(corpus_id, version_id)
        assert version is not None
        updated = replace(version, status=status, failure_code=failure_code)
        self.versions[version_id] = updated
        return updated


class _Corpora:
    async def get_organization(self, organization_id: UUID) -> KnowledgeCorpus:
        if organization_id != ORGANIZATION_ID:
            raise LookupError
        return KnowledgeCorpus(CORPUS_ID, KnowledgeScope.ORGANIZATION, organization_id)


class _Revisions:
    def __init__(self) -> None:
        self.published = 0

    async def publish(self, **_: object) -> object:
        self.published += 1
        return object()


class _Events:
    async def append(self, _: object) -> None:
        return None


class _Uow:
    def __init__(self, documents: _Documents, revisions: _Revisions) -> None:
        self.documents = documents
        self.corpora = _Corpora()
        self.revisions = revisions
        self.processing_events = _Events()

    async def __aenter__(self) -> _Uow:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def commit(self) -> None:
        return None


class _Factory:
    def __init__(self) -> None:
        self.documents = _Documents()
        self.revisions = _Revisions()

    def __call__(self) -> KnowledgeUnitOfWork:
        return cast(KnowledgeUnitOfWork, _Uow(self.documents, self.revisions))


class _FailingEmbeddings:
    async def embed(self, _: Sequence[str]) -> EmbeddingBatch:
        raise RuntimeError("provider unavailable")


def _args() -> SubmitKnowledgeDocumentArgs:
    return SubmitKnowledgeDocumentArgs(
        document_key="product/overview",
        category=KnowledgeCategory.PRODUCT,
        language=KnowledgeLanguage.ENGLISH,
        format=KnowledgeFormat.MARKDOWN,
        content="# Product\n\nApproved content.",
    )


def _context() -> KnowledgeAdminContext:
    return KnowledgeAdminContext(actor_id=ACTOR_ID, organization_id=ORGANIZATION_ID, role="admin")


async def _idempotency() -> bool:
    factory = _Factory()
    use_case = SubmitKnowledgeDocument(factory, _Clock())
    first = await use_case.execute(context=_context(), args=_args(), idempotency_key="eval-key")
    replay = await use_case.execute(context=_context(), args=_args(), idempotency_key="eval-key")
    return first.id == replay.id and replay.replayed


async def _failure_atomicity() -> bool:
    factory = _Factory()
    version = await factory.documents.reserve_draft(
        corpus_id=CORPUS_ID,
        requested_by=ACTOR_ID,
        document=_args().to_domain(),
        idempotency_key="failure-key",
        created_at=_Clock().now(),
    )
    await factory.documents.transition_status(
        corpus_id=CORPUS_ID, version_id=version.id, status=KnowledgeVersionStatus.CONFIRMED
    )
    try:
        await ProcessKnowledgeDocument(factory, _FailingEmbeddings(), _Clock()).execute(
            corpus_id=CORPUS_ID, version_id=version.id, delivery_id="eval-delivery", attempt=1
        )
    except KnowledgeProcessingError as exc:
        return exc.failure_code == "embedding_provider_error" and factory.revisions.published == 0
    return False


async def _fake_embeddings() -> bool:
    provider = DeterministicFakeEmbeddingProvider(dimension=8)
    return await provider.embed(("alpha", "beta")) == await provider.embed(("alpha", "beta"))


def _validation() -> bool:
    try:
        KnowledgeDocument(
            "Bad Key",
            KnowledgeCategory.PRODUCT,
            KnowledgeLanguage.ENGLISH,
            KnowledgeFormat.TEXT,
            KnowledgeScope.ORGANIZATION,
            "approved",
            {},
        )
    except PolicyViolationError:
        return True
    return False


def _chunking() -> bool:
    content = "# Heading\r\n\r\nParagraph one.\r\n\r\n## Next\r\n\r\nParagraph two."
    first = chunk_content(content)
    second = chunk_content(content.replace("\r\n", "\n"))
    return first == second and all(chunk.ordinal == index for index, chunk in enumerate(first))


def _lifecycle() -> bool:
    state = KnowledgeVersionState()
    try:
        state.mark_ready()
    except InvalidTransitionError:
        return state.status is KnowledgeVersionStatus.DRAFT
    return False


def _tenant_scope() -> bool:
    try:
        SubmitKnowledgeDocumentArgs.model_validate({**_args().model_dump(), "scope": "platform"})
    except ValidationError:
        return True
    return False


async def _score_case(case: dict[str, Any]) -> bool:
    contract = case["contract"]
    if contract == "idempotency":
        return await _idempotency()
    if contract == "failure_atomicity":
        return await _failure_atomicity()
    if contract == "fake_embeddings":
        return await _fake_embeddings()
    checks: dict[str, Callable[[], bool]] = {
        "validation": _validation,
        "chunking": _chunking,
        "lifecycle": _lifecycle,
        "tenant_scope": _tenant_scope,
    }
    return checks[contract]()


def score_rag_ingestion_contract_dataset() -> ScoreResult:
    cases = load_cases()
    failed_ids = [str(case["id"]) for case in cases if not asyncio.run(_score_case(case))]
    return ScoreResult(
        total=len(cases), correct=len(cases) - len(failed_ids), failed_ids=failed_ids
    )
