"""Pure, bounded values for company research and grounded follow-up preparation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from revops.domain.errors import PolicyViolationError


class ResearchStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    SOURCE_UNAVAILABLE = "source_unavailable"
    CONFLICTING = "conflicting"
    REFUSED = "refused"
    FAILED = "failed"


class FollowupStatus(StrEnum):
    COMPLETE = "complete"
    EVIDENCE_INSUFFICIENT = "evidence_insufficient"
    CONFLICTING = "conflicting"
    REFUSED = "refused"
    FAILED = "failed"


class DraftLanguage(StrEnum):
    ENGLISH = "en"
    PORTUGUESE = "pt"


@dataclass(frozen=True, slots=True)
class ResearchSource:
    """A source actually acquired by the bounded research adapter."""

    source_id: str
    url: str
    retrieved_at: datetime
    content_hash: str
    excerpt: str

    def __post_init__(self) -> None:
        if not self.source_id or len(self.source_id) > 128:
            raise PolicyViolationError("research source_id must be 1-128 characters")
        if not self.url.startswith("https://"):
            raise PolicyViolationError("research sources must use HTTPS")
        if not self.content_hash or len(self.content_hash) != 64:
            raise PolicyViolationError("research source content_hash must be SHA-256")
        if not self.excerpt or len(self.excerpt) > 2_000:
            raise PolicyViolationError("research source excerpt must be 1-2,000 characters")


@dataclass(frozen=True, slots=True)
class ResearchFact:
    """A bounded company fact with references to acquired sources."""

    key: str
    value: str
    source_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.key or len(self.key) > 128 or not self.value or len(self.value) > 2_000:
            raise PolicyViolationError("research facts have invalid key or value bounds")
        if not self.source_ids:
            raise PolicyViolationError("research facts require at least one source")


@dataclass(frozen=True, slots=True)
class ClaimReference:
    """A reference from a generated claim to an acquired evidence item."""

    claim_id: str
    source_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.claim_id or not self.source_ids:
            raise PolicyViolationError("claim references require claim and source identifiers")


@dataclass(frozen=True, slots=True)
class GeneratedClaim:
    claim_id: str
    text: str
    references: tuple[ClaimReference, ...]

    def __post_init__(self) -> None:
        if not self.claim_id or not self.text or len(self.text) > 1_000:
            raise PolicyViolationError("generated claims have invalid bounds")


@dataclass(frozen=True, slots=True)
class VerificationResult:
    accepted: bool
    unsupported_claim_ids: tuple[str, ...] = ()
    contradictory_claim_ids: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.accepted and (self.unsupported_claim_ids or self.contradictory_claim_ids):
            raise PolicyViolationError("accepted verification cannot contain rejected claims")


@dataclass(frozen=True, slots=True)
class FollowupArtifact:
    """The bounded tenant-protected result exposed by the result endpoint."""

    account_id: UUID
    status: FollowupStatus
    language: DraftLanguage | None
    subject: str | None
    body: str | None
    rationale: str | None
    claims: tuple[GeneratedClaim, ...]
    source_ids: tuple[str, ...]
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.subject is not None and len(self.subject) > 160:
            raise PolicyViolationError("follow-up subject exceeds 160 characters")
        if self.body is not None and len(self.body) > 6_000:
            raise PolicyViolationError("follow-up body exceeds 6,000 characters")
        if self.status is FollowupStatus.COMPLETE and not (
            self.language and self.subject and self.body and self.claims
        ):
            raise PolicyViolationError("complete follow-up artifacts require a draft")


def validate_claim_references(
    claims: tuple[GeneratedClaim, ...], allowed_source_ids: frozenset[str]
) -> None:
    """Reject references that were not acquired for the current run."""
    for claim in claims:
        for reference in claim.references:
            if not set(reference.source_ids).issubset(allowed_source_ids):
                raise PolicyViolationError("claim references an unavailable research source")
