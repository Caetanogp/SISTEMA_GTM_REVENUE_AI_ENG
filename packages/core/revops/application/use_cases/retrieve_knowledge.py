"""Read-only task-scoped knowledge retrieval orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field

from revops.application.context.knowledge import KnowledgeContextAssembler
from revops.application.dto import (
    EmbeddingBatch,
    KnowledgeRetrievalContext,
    RetrieveKnowledgeArgs,
    TaskKnowledgeContext,
)
from revops.application.ports import (
    EmbeddingProvider,
    EmbeddingProviderError,
    KnowledgeRetrievalRepository,
    KnowledgeRetrievalRepositoryError,
)
from revops.domain.errors import PolicyViolationError
from revops.domain.values.retrieval import (
    EmbeddingSpace,
    RetrievalLimit,
    RetrievalQuery,
    RetrievalTokenBudget,
    validate_embedding_vector,
)


class KnowledgeRetrievalError(RuntimeError):
    """Safe base error for task-scoped retrieval failures."""


class EmbeddingSpaceIncompatibleError(KnowledgeRetrievalError):
    """Ready active sources or the configured query provider cannot be compared safely."""

    failure_code = "embedding_space_incompatible"


class KnowledgeRetrievalProviderError(KnowledgeRetrievalError):
    """A sanitized configured embedding-provider failure."""

    def __init__(self, failure_code: str, *, retryable: bool) -> None:
        safe_codes = {
            "embedding_unavailable",
            "embedding_rejected",
            "embedding_invalid_response",
            "embedding_response_invalid",
            "provider_timeout",
            "embedding_provider_error",
            "retrieval_storage_error",
        }
        self.failure_code = (
            failure_code if failure_code in safe_codes else "embedding_provider_error"
        )
        self.retryable = retryable
        super().__init__(self.failure_code)


class KnowledgeRetrievalStorageError(KnowledgeRetrievalError):
    """A sanitized persistence failure that exposes no SQL or bound values."""

    failure_code = "retrieval_storage_error"

    def __init__(self) -> None:
        super().__init__(self.failure_code)


@dataclass(frozen=True, slots=True)
class RetrieveKnowledge:
    """Retrieve active platform and trusted-organization knowledge for one task query."""

    repository: KnowledgeRetrievalRepository
    embeddings: EmbeddingProvider
    assembler: KnowledgeContextAssembler = field(default_factory=KnowledgeContextAssembler)

    async def execute(
        self,
        *,
        context: KnowledgeRetrievalContext,
        args: RetrieveKnowledgeArgs,
    ) -> TaskKnowledgeContext:
        query = RetrievalQuery(args.query)
        limit = RetrievalLimit(args.limit)
        budget = RetrievalTokenBudget(args.token_budget)
        try:
            active_space = await self.repository.resolve_active_embedding_space(
                organization_id=context.organization_id
            )
        except KnowledgeRetrievalRepositoryError as exc:
            if exc.failure_code == "embedding_space_incompatible":
                raise EmbeddingSpaceIncompatibleError(
                    EmbeddingSpaceIncompatibleError.failure_code
                ) from None
            raise KnowledgeRetrievalStorageError() from None
        if active_space is None:
            return self.assembler.assemble((), token_budget=budget)
        embedded = await self._embed_query(query)
        query_space = _embedding_space(embedded.model, embedded.dimension)
        if query_space != active_space:
            raise EmbeddingSpaceIncompatibleError(EmbeddingSpaceIncompatibleError.failure_code)
        if len(embedded.vectors) != 1 or len(embedded.vectors[0]) != query_space.dimension:
            raise KnowledgeRetrievalProviderError("embedding_response_invalid", retryable=False)
        try:
            query_vector = validate_embedding_vector(
                embedded.vectors[0], dimension=query_space.dimension
            )
            candidates = await self.repository.search_active_chunks(
                organization_id=context.organization_id,
                query_vector=query_vector,
                embedding_model=query_space.model,
                embedding_dimension=query_space.dimension,
                limit=limit.value,
            )
        except KnowledgeRetrievalRepositoryError as exc:
            if exc.failure_code == "embedding_space_incompatible":
                raise EmbeddingSpaceIncompatibleError(
                    EmbeddingSpaceIncompatibleError.failure_code
                ) from None
            raise KnowledgeRetrievalStorageError() from None
        except PolicyViolationError:
            raise KnowledgeRetrievalProviderError(
                "embedding_response_invalid", retryable=False
            ) from None
        return self.assembler.assemble(
            tuple(candidate.passage for candidate in candidates), token_budget=budget
        )

    async def _embed_query(self, query: RetrievalQuery) -> EmbeddingBatch:
        try:
            return await self.embeddings.embed((query.text,))
        except EmbeddingProviderError as exc:
            raise KnowledgeRetrievalProviderError(
                exc.failure_code, retryable=exc.retryable
            ) from None
        except Exception:
            raise KnowledgeRetrievalProviderError(
                "embedding_provider_error", retryable=False
            ) from None


def _embedding_space(model: str, dimension: int) -> EmbeddingSpace:
    try:
        return EmbeddingSpace(model=model, dimension=dimension)
    except PolicyViolationError:
        raise KnowledgeRetrievalProviderError(
            "embedding_response_invalid", retryable=False
        ) from None
