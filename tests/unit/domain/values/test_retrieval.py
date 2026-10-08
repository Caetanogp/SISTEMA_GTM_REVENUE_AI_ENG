"""Unit tests for pure knowledge-retrieval domain value objects."""

from typing import cast
from uuid import UUID

import pytest
from revops.domain.entities.knowledge import KnowledgeCategory, KnowledgeLanguage
from revops.domain.errors import PolicyViolationError
from revops.domain.values.retrieval import (
    EmbeddingSpace,
    RetrievalLimit,
    RetrievalProvenance,
    RetrievalQuery,
    RetrievalScore,
    RetrievalTokenBudget,
    RetrievedPassage,
    order_retrieved_passages,
    validate_embedding_vector,
)

_VERSION_ID = UUID("00000000-0000-0000-0000-000000000002")
_REVISION_ID = UUID("00000000-0000-0000-0000-000000000003")


def _provenance(**overrides: object) -> RetrievalProvenance:
    values: dict[str, object] = {
        "document_key": "product/platform-overview",
        "document_version_id": _VERSION_ID,
        "chunk_id": UUID("00000000-0000-0000-0000-000000000004"),
        "chunk_ordinal": 0,
        "category": KnowledgeCategory.PRODUCT,
        "language": KnowledgeLanguage.PORTUGUESE,
        "active_revision_id": _REVISION_ID,
    }
    values.update(overrides)
    return RetrievalProvenance(
        document_key=cast(str, values["document_key"]),
        document_version_id=cast(UUID, values["document_version_id"]),
        chunk_id=cast(UUID, values["chunk_id"]),
        chunk_ordinal=cast(int, values["chunk_ordinal"]),
        category=cast(KnowledgeCategory, values["category"]),
        language=cast(KnowledgeLanguage, values["language"]),
        active_revision_id=cast(UUID, values["active_revision_id"]),
    )


def _passage(**overrides: object) -> RetrievedPassage:
    values: dict[str, object] = {
        "text": "Platform context.",
        "provenance": _provenance(),
        "score": RetrievalScore(0.9),
    }
    values.update(overrides)
    return RetrievedPassage(
        text=cast(str, values["text"]),
        provenance=cast(RetrievalProvenance, values["provenance"]),
        score=cast(RetrievalScore, values["score"]),
    )


def test_query_is_nfc_normalized_and_whitespace_bounded() -> None:
    query = RetrievalQuery("  Cafe\u0301\n\t platform context  ")

    assert query.text == "Caf\u00e9 platform context"


@pytest.mark.parametrize("text", ["", " \t\n", 3])
def test_query_rejects_empty_or_non_text_values(text: object) -> None:
    with pytest.raises(PolicyViolationError, match="retrieval query"):
        RetrievalQuery(cast(str, text))


@pytest.mark.parametrize("limit", [0, 21, -1, True, 1.5])
def test_limit_enforces_the_approved_closed_range(limit: object) -> None:
    with pytest.raises(PolicyViolationError, match="retrieval limit"):
        RetrievalLimit(cast(int, limit))


def test_limit_accepts_each_boundary() -> None:
    assert RetrievalLimit(1).value == 1
    assert RetrievalLimit(20).value == 20


@pytest.mark.parametrize("budget", [0, -1, True, 1.5])
def test_budget_requires_a_positive_integer(budget: object) -> None:
    with pytest.raises(PolicyViolationError, match="token budget"):
        RetrievalTokenBudget(cast(int, budget))


@pytest.mark.parametrize("score", [float("nan"), float("inf"), float("-inf"), True, "0.8"])
def test_score_rejects_non_finite_or_non_numeric_values(score: object) -> None:
    with pytest.raises(PolicyViolationError, match="retrieval score"):
        RetrievalScore(cast(float, score))


def test_score_normalizes_ints_to_floats() -> None:
    assert RetrievalScore(1).value == 1.0


@pytest.mark.parametrize(("model", "dimension"), [("", 1536), (" model ", 2), ("model", True)])
def test_embedding_space_requires_a_model_and_schema_dimension(
    model: object, dimension: object
) -> None:
    with pytest.raises(PolicyViolationError, match="embedding"):
        EmbeddingSpace(cast(str, model), cast(int, dimension))


def test_embedding_space_normalizes_its_model_name() -> None:
    assert EmbeddingSpace(" model ", 1536).model == "model"


def test_embedding_vector_returns_float32_quantized_non_zero_values() -> None:
    vector = validate_embedding_vector((1, 2.5), dimension=2)

    assert vector == (1.0, 2.5)
    assert all(type(value) is float for value in vector)


@pytest.mark.parametrize(
    "vector",
    [
        (0.0, 0.0),
        (float("nan"), 1.0),
        (float("inf"), 1.0),
        (True, 1.0),
        (10**400, 1.0),
    ],
)
def test_embedding_vector_rejects_invalid_float32_values(vector: tuple[object, ...]) -> None:
    with pytest.raises(PolicyViolationError, match="embedding vector"):
        validate_embedding_vector(vector, dimension=2)


def test_embedding_vector_rejects_underflow_to_zero() -> None:
    with pytest.raises(PolicyViolationError, match="must not be zero"):
        validate_embedding_vector((1e-50, 0.0), dimension=2)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("document_key", "invalid key", "document_key"),
        ("document_version_id", "not-a-uuid", "document_version_id"),
        ("chunk_id", "not-a-uuid", "chunk_id"),
        ("chunk_ordinal", -1, "chunk_ordinal"),
        ("category", "product", "category"),
        ("language", "pt", "language"),
        ("active_revision_id", "not-a-uuid", "active_revision_id"),
    ],
)
def test_provenance_requires_all_reproducibility_fields(
    field: str, value: object, message: str
) -> None:
    with pytest.raises(PolicyViolationError, match=message):
        _provenance(**{field: value})


def test_passage_requires_non_empty_text_and_typed_source_data() -> None:
    with pytest.raises(PolicyViolationError, match="passage text"):
        _passage(text=" ")
    with pytest.raises(PolicyViolationError, match="passage provenance"):
        _passage(provenance="missing")
    with pytest.raises(PolicyViolationError, match="passage score"):
        _passage(score=0.9)


def test_ordering_is_score_descending_then_provenance_ascending() -> None:
    lower_score = _passage(score=RetrievalScore(0.5))
    later_chunk = _passage(
        provenance=_provenance(
            chunk_id=UUID("00000000-0000-0000-0000-000000000006"), chunk_ordinal=1
        )
    )
    earlier_key = _passage(
        provenance=_provenance(
            document_key="brand/voice",
            chunk_id=UUID("00000000-0000-0000-0000-000000000005"),
        )
    )

    assert order_retrieved_passages((lower_score, later_chunk, earlier_key)) == (
        earlier_key,
        later_chunk,
        lower_score,
    )
