"""Pure state and identity models for reversible deduplication decisions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from revops.domain.errors import InvalidTransitionError, PolicyViolationError


class DeduplicationRecordType(StrEnum):
    ACCOUNT = "account"
    CONTACT = "contact"


class DeduplicationScanStatus(StrEnum):
    QUEUED = "queued"
    QUEUE_FAILED = "queue_failed"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

    @property
    def is_terminal(self) -> bool:
        return self in {DeduplicationScanStatus.COMPLETED, DeduplicationScanStatus.FAILED}


class DeduplicationCandidateStatus(StrEnum):
    PENDING = "pending"
    DISMISSED = "dismissed"
    MERGED = "merged"
    STALE = "stale"


@dataclass(slots=True)
class DeduplicationScanState:
    status: DeduplicationScanStatus = DeduplicationScanStatus.QUEUED

    def begin_processing(self) -> None:
        self._transition_to(DeduplicationScanStatus.PROCESSING)

    def record_queue_failure(self) -> None:
        self._transition_to(DeduplicationScanStatus.QUEUE_FAILED)

    def retry_queue(self) -> None:
        self._transition_to(DeduplicationScanStatus.QUEUED)

    def complete(self) -> None:
        self._transition_to(DeduplicationScanStatus.COMPLETED)

    def fail(self) -> None:
        self._transition_to(DeduplicationScanStatus.FAILED)

    def _transition_to(self, target: DeduplicationScanStatus) -> None:
        if target not in _SCAN_TRANSITIONS[self.status]:
            raise InvalidTransitionError(
                f"cannot move a deduplication scan from {self.status} to {target}"
            )
        self.status = target


@dataclass(slots=True)
class DeduplicationCandidate:
    record_type: DeduplicationRecordType
    left_id: UUID
    right_id: UUID
    score: int
    reasons: tuple[str, ...]
    policy_version: str
    left_fingerprint: str
    right_fingerprint: str
    status: DeduplicationCandidateStatus = DeduplicationCandidateStatus.PENDING

    def __post_init__(self) -> None:
        if self.left_id >= self.right_id:
            raise PolicyViolationError("candidate IDs must be distinct and ordered")
        if not 0 < self.score <= 100:
            raise PolicyViolationError("candidate score must be between 1 and 100")
        if not self.reasons:
            raise PolicyViolationError("candidate requires at least one reason")
        if not self.policy_version:
            raise PolicyViolationError("candidate requires a policy version")

    def dismiss(self) -> None:
        self._decide(DeduplicationCandidateStatus.DISMISSED)

    def mark_merged(self) -> None:
        self._decide(DeduplicationCandidateStatus.MERGED)

    def mark_stale(self) -> None:
        self._decide(DeduplicationCandidateStatus.STALE)

    def _decide(self, target: DeduplicationCandidateStatus) -> None:
        if self.status is not DeduplicationCandidateStatus.PENDING:
            raise InvalidTransitionError(f"cannot decide a {self.status} candidate")
        self.status = target


@dataclass(slots=True)
class RecordAlias:
    record_type: DeduplicationRecordType
    alias_id: UUID
    canonical_id: UUID
    merge_event_id: UUID
    created_at: datetime
    reverted_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.alias_id == self.canonical_id:
            raise PolicyViolationError("a record cannot be an alias of itself")

    @property
    def is_active(self) -> bool:
        return self.reverted_at is None

    def revert(self, *, occurred_at: datetime) -> None:
        if not self.is_active:
            raise InvalidTransitionError("an inactive alias cannot be reverted twice")
        self.reverted_at = occurred_at


_SCAN_TRANSITIONS: dict[DeduplicationScanStatus, frozenset[DeduplicationScanStatus]] = {
    DeduplicationScanStatus.QUEUED: frozenset(
        {DeduplicationScanStatus.PROCESSING, DeduplicationScanStatus.QUEUE_FAILED}
    ),
    DeduplicationScanStatus.QUEUE_FAILED: frozenset({DeduplicationScanStatus.QUEUED}),
    DeduplicationScanStatus.PROCESSING: frozenset(
        {DeduplicationScanStatus.COMPLETED, DeduplicationScanStatus.FAILED}
    ),
    DeduplicationScanStatus.COMPLETED: frozenset(),
    DeduplicationScanStatus.FAILED: frozenset(),
}
