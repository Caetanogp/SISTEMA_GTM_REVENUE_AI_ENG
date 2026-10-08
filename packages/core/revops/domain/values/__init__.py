"""Value objects: immutable, defined by their content, validated on construction."""

from revops.domain.values.company_domain import CompanyDomain
from revops.domain.values.email import EmailAddress
from revops.domain.values.phone import PhoneNumber
from revops.domain.values.retrieval import (
    MAX_RETRIEVAL_LIMIT,
    MIN_RETRIEVAL_LIMIT,
    SUPPORTED_EMBEDDING_DIMENSIONS,
    EmbeddingSpace,
    RetrievalLimit,
    RetrievalProvenance,
    RetrievalQuery,
    RetrievalScore,
    RetrievalTokenBudget,
    RetrievedPassage,
    order_retrieved_passages,
)
from revops.domain.values.risk import RiskLevel
from revops.domain.values.score import Score, ScoreTier

__all__ = [
    "MAX_RETRIEVAL_LIMIT",
    "MIN_RETRIEVAL_LIMIT",
    "SUPPORTED_EMBEDDING_DIMENSIONS",
    "CompanyDomain",
    "EmailAddress",
    "EmbeddingSpace",
    "PhoneNumber",
    "RetrievalLimit",
    "RetrievalProvenance",
    "RetrievalQuery",
    "RetrievalScore",
    "RetrievalTokenBudget",
    "RetrievedPassage",
    "RiskLevel",
    "Score",
    "ScoreTier",
    "order_retrieved_passages",
]
