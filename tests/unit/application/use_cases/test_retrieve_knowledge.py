"""Unit tests for task-scoped knowledge retrieval orchestration."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from revops.application.dto import (
    EmbeddingBatch,
    KnowledgeRetrievalCandidate,
    KnowledgeRetrievalContext,
    RetrieveKnowledgeArgs,
)
from revops.application.ports import (
    EmbeddingProviderError,
    KnowledgeRetrievalRepository,
)
from revops.application.use_cases.retrieve_knowledge import (
    EmbeddingSpaceIncompatibleError,
    KnowledgeRetrievalProviderError,
    RetrieveKnowledge,
)
from revops.domain.entities.knowledge import KnowledgeCategory, KnowledgeLanguage
from revops.domain.values.retrieval import (
    EmbeddingSpace,
    RetrievalProvenance,
    RetrievalScore,
    RetrievedPassage,
)

_ORGANIZATION_ID = UUID("00000000-0000-0000-0000-000000000001")
_DEFAULT_SPACE = EmbeddingSpace("configured-model", 1536)


def _passage(*, score: float = 0.8, key: str = "product/platform") -> RetrievedPassage:
    return RetrievedPassage(
        text="Approved product context.",
        provenance=RetrievalProvenance(
            document_key=key,
            document_version_id=uuid4(),
            chunk_id=uuid4(),
            chunk_ordinal=0,
            category=KnowledgeCategory.PRODUCT,
            language=KnowledgeLanguage.ENGLISH,
            active_revision_id=uuid4(),
        ),
        score=RetrievalScore(score),
    )


class _FakeRepository:
    def __init__(
        self,
        *,
        space: EmbeddingSpace = _DEFAULT_SPACE,
        candidates: Sequence[KnowledgeRetrievalCandidate] = (),
    ) -> None:
        self.space = space
        self.candidates = candidates
        self.resolved_organization_id: UUID | None = None
        self.search_call: dict[str, object] | None = None

    async def resolve_active_embedding_space(self, *, organization_id: UUID) -> EmbeddingSpace:
        self.resolved_organization_id = organization_id
        return self.space

    async def search_active_chunks(
        self,
        *,
        organization_id: UUID,
        query_vector: Sequence[float],
        embedding_model: str,
        embedding_dimension: int,
        limit: int,
    ) -> Sequence[KnowledgeRetrievalCandidate]:
        self.search_call = {
            "organization_id": organization_id,
            "query_vector": tuple(query_vector),
            "embedding_model": embedding_model,
            "embedding_dimension": embedding_dimension,
            "limit": limit,
        }
        return self.candidates


class _FakeEmbeddings:
    def __init__(self, batch: EmbeddingBatch) -> None:
        self.batch = batch
        self.texts: list[tuple[str, ...]] = []

    async def embed(self, texts: Sequence[str]) -> EmbeddingBatch:
        self.texts.append(tuple(texts))
        return self.batch


def _args(**overrides: object) -> RetrieveKnowledgeArgs:
    values: dict[str, object] = {
        "query": "  Product positioning  ",
        "limit": 2,
        "token_budget": 1_000,
    }
    values.update(overrides)
    return RetrieveKnowledgeArgs(**values)


def _embeddings() -> _FakeEmbeddings:
    return _FakeEmbeddings(
        EmbeddingBatch(
            model="configured-model",
            dimension=1536,
            vectors=(tuple(0.0 for _ in range(1536)),),
        )
    )


def test_retrieval_dtos_forbid_caller_tenant_or_corpus_selection() -> None:
    assert "organization_id" not in RetrieveKnowledgeArgs.model_fields
    assert "corpus_id" not in RetrieveKnowledgeArgs.model_fields
    with pytest.raises(ValidationError):
        RetrieveKnowledgeArgs.model_validate({**_args().model_dump(), "organization_id": uuid4()})


def test_retrieval_repository_is_a_structural_protocol() -> None:
    assert isinstance(_FakeRepository(), KnowledgeRetrievalRepository)


async def test_retrieve_uses_trusted_organization_and_one_normalized_embedding_query() -> None:
    candidate = KnowledgeRetrievalCandidate(passage=_passage())
    repository = _FakeRepository(candidates=(candidate,))
    embeddings = _embeddings()

    result = await RetrieveKnowledge(repository, embeddings).execute(
        context=KnowledgeRetrievalContext(organization_id=_ORGANIZATION_ID), args=_args()
    )

    assert repository.resolved_organization_id == _ORGANIZATION_ID
    assert repository.search_call is not None
    assert repository.search_call["organization_id"] == _ORGANIZATION_ID
    assert repository.search_call["limit"] == 2
    assert embeddings.texts == [("Product positioning",)]
    assert result.included == (candidate.passage,)


async def test_retrieve_returns_typed_compatibility_failure_without_searching() -> None:
    repository = _FakeRepository(space=EmbeddingSpace("other-model", 1536))

    with pytest.raises(EmbeddingSpaceIncompatibleError, match="embedding_space_incompatible"):
        await RetrieveKnowledge(repository, _embeddings()).execute(
            context=KnowledgeRetrievalContext(organization_id=_ORGANIZATION_ID), args=_args()
        )

    assert repository.search_call is None


async def test_retrieve_wraps_sanitized_embedding_provider_failure() -> None:
    class _FailingEmbeddings:
        async def embed(self, texts: Sequence[str]) -> EmbeddingBatch:
            raise EmbeddingProviderError("provider_timeout", retryable=True)

    with pytest.raises(KnowledgeRetrievalProviderError) as caught:
        await RetrieveKnowledge(_FakeRepository(), _FailingEmbeddings()).execute(
            context=KnowledgeRetrievalContext(organization_id=_ORGANIZATION_ID), args=_args()
        )

    assert caught.value.failure_code == "provider_timeout"
    assert caught.value.retryable is True
