"""Pure value objects and deterministic rules for knowledge retrieval."""

from __future__ import annotations

import math
import re
import struct
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Final
from unicodedata import normalize
from uuid import UUID

from revops.domain.entities.knowledge import KnowledgeCategory, KnowledgeLanguage
from revops.domain.errors import PolicyViolationError

MIN_RETRIEVAL_LIMIT: Final = 1
MAX_RETRIEVAL_LIMIT: Final = 20
SUPPORTED_EMBEDDING_DIMENSIONS: Final = frozenset({1536})
_DOCUMENT_KEY_PATTERN: Final = re.compile(r"[a-z0-9][a-z0-9._/-]*")


@dataclass(frozen=True, slots=True)
class RetrievalQuery:
    """A canonical non-empty task query suitable for one embedding request."""

    text: str

    def __post_init__(self) -> None:
        if not isinstance(self.text, str):
            raise PolicyViolationError("retrieval query must be text")
        normalized = " ".join(normalize("NFC", self.text).split())
        if not normalized:
            raise PolicyViolationError("retrieval query must not be empty")
        object.__setattr__(self, "text", normalized)


@dataclass(frozen=True, slots=True)
class RetrievalLimit:
    """A bounded number of retrieval results."""

    value: int

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or not isinstance(self.value, int):
            raise PolicyViolationError("retrieval limit must be an integer")
        if not MIN_RETRIEVAL_LIMIT <= self.value <= MAX_RETRIEVAL_LIMIT:
            raise PolicyViolationError(
                f"retrieval limit must be within [{MIN_RETRIEVAL_LIMIT}, {MAX_RETRIEVAL_LIMIT}]"
            )


@dataclass(frozen=True, slots=True)
class RetrievalTokenBudget:
    """A positive token allocation for retrieved task context."""

    value: int

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or not isinstance(self.value, int) or self.value <= 0:
            raise PolicyViolationError("retrieval token budget must be a positive integer")


@dataclass(frozen=True, slots=True)
class EmbeddingSpace:
    """The model and persisted vector dimension used for one retrieval comparison."""

    model: str
    dimension: int

    def __post_init__(self) -> None:
        if not isinstance(self.model, str) or not self.model.strip():
            raise PolicyViolationError("embedding model must not be empty")
        if isinstance(self.dimension, bool) or not isinstance(self.dimension, int):
            raise PolicyViolationError("embedding dimension must be an integer")
        if self.dimension not in SUPPORTED_EMBEDDING_DIMENSIONS:
            raise PolicyViolationError("embedding dimension is not supported by the active schema")
        object.__setattr__(self, "model", self.model.strip())


def validate_embedding_vector(values: Sequence[object], *, dimension: int) -> tuple[float, ...]:
    """Validate and quantize a query vector exactly as the pgvector column does."""
    if isinstance(dimension, bool) or not isinstance(dimension, int) or dimension <= 0:
        raise PolicyViolationError("embedding dimension must be a positive integer")
    if len(values) != dimension:
        raise PolicyViolationError("embedding vector dimension does not match its space")

    quantized: list[float] = []
    try:
        for value in values:
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise PolicyViolationError("embedding vector coordinates must be numeric")
            coordinate = float(value)
            if not math.isfinite(coordinate):
                raise PolicyViolationError("embedding vector coordinates must be finite")
            packed = struct.pack("!f", coordinate)
            quantized_coordinate = struct.unpack("!f", packed)[0]
            if not math.isfinite(quantized_coordinate):
                raise PolicyViolationError("embedding vector is not representable as float32")
            quantized.append(quantized_coordinate)
    except (OverflowError, struct.error) as exc:
        raise PolicyViolationError("embedding vector is not representable as float32") from exc

    norm = 0.0
    for coordinate in quantized:
        norm = math.hypot(norm, coordinate)
    if norm == 0.0:
        raise PolicyViolationError("embedding vector must not be zero")
    return tuple(quantized)


@dataclass(frozen=True, slots=True)
class RetrievalScore:
    """A finite normalized similarity score supplied by the retrieval adapter."""

    value: float

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or not isinstance(self.value, int | float):
            raise PolicyViolationError("retrieval score must be numeric")
        score = float(self.value)
        if not math.isfinite(score):
            raise PolicyViolationError("retrieval score must be finite")
        object.__setattr__(self, "value", score)


@dataclass(frozen=True, slots=True)
class RetrievalProvenance:
    """Immutable source identity required to reproduce one retrieved chunk."""

    document_key: str
    document_version_id: UUID
    chunk_id: UUID
    chunk_ordinal: int
    category: KnowledgeCategory
    language: KnowledgeLanguage
    active_revision_id: UUID

    def __post_init__(self) -> None:
        if not isinstance(self.document_key, str) or not _DOCUMENT_KEY_PATTERN.fullmatch(
            self.document_key
        ):
            raise PolicyViolationError("retrieval provenance document_key is invalid")
        if not isinstance(self.document_version_id, UUID):
            raise PolicyViolationError("retrieval provenance document_version_id is required")
        if not isinstance(self.chunk_id, UUID):
            raise PolicyViolationError("retrieval provenance chunk_id is required")
        if (
            isinstance(self.chunk_ordinal, bool)
            or not isinstance(self.chunk_ordinal, int)
            or self.chunk_ordinal < 0
        ):
            raise PolicyViolationError("retrieval provenance chunk_ordinal must be non-negative")
        if not isinstance(self.category, KnowledgeCategory):
            raise PolicyViolationError("retrieval provenance category is required")
        if not isinstance(self.language, KnowledgeLanguage):
            raise PolicyViolationError("retrieval provenance language is required")
        if not isinstance(self.active_revision_id, UUID):
            raise PolicyViolationError("retrieval provenance active_revision_id is required")


@dataclass(frozen=True, slots=True)
class RetrievedPassage:
    """One attributable untrusted knowledge passage and its retrieval score."""

    text: str
    provenance: RetrievalProvenance
    score: RetrievalScore

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not self.text.strip():
            raise PolicyViolationError("retrieved passage text must not be empty")
        if not isinstance(self.provenance, RetrievalProvenance):
            raise PolicyViolationError("retrieved passage provenance is required")
        if not isinstance(self.score, RetrievalScore):
            raise PolicyViolationError("retrieved passage score is required")


def order_retrieved_passages(passages: Iterable[RetrievedPassage]) -> tuple[RetrievedPassage, ...]:
    """Return passages in the repository's stable retrieval order."""
    return tuple(
        sorted(
            passages,
            key=lambda passage: (
                -passage.score.value,
                passage.provenance.document_key,
                str(passage.provenance.document_version_id),
                passage.provenance.chunk_ordinal,
                str(passage.provenance.chunk_id),
            ),
        )
    )
