"""Ingestion job and item state machines for the explicit bulk-import workflow."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from revops.domain.errors import InvalidTransitionError


class IngestionJobStatus(StrEnum):
    """The persisted lifecycle of an import batch."""

    STAGED = "staged"
    VALIDATION_FAILED = "validation_failed"
    QUEUED = "queued"
    PROCESSING = "processing"
    QUEUE_FAILED = "queue_failed"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"

    @property
    def is_terminal(self) -> bool:
        return self in {
            IngestionJobStatus.VALIDATION_FAILED,
            IngestionJobStatus.COMPLETED,
            IngestionJobStatus.COMPLETED_WITH_ERRORS,
        }


class IngestionItemStatus(StrEnum):
    """The lifecycle of one normalized record inside a staged import."""

    PENDING = "pending"
    VALIDATION_FAILED = "validation_failed"
    PROCESSING = "processing"
    COMPLETED = "completed"

    @property
    def is_terminal(self) -> bool:
        return self in {IngestionItemStatus.VALIDATION_FAILED, IngestionItemStatus.COMPLETED}


class AccountOutcome(StrEnum):
    """The non-PII result of attempting to persist an item's account."""

    NOT_ATTEMPTED = "not_attempted"
    PENDING = "pending"
    CREATED = "created"
    DUPLICATE = "duplicate"
    FAILED = "failed"


class ContactOutcome(StrEnum):
    """The result of the optional contact operation, distinct from account persistence."""

    NOT_PROVIDED = "not_provided"
    NOT_ATTEMPTED = "not_attempted"
    PENDING = "pending"
    CREATED = "created"
    DUPLICATE = "duplicate"
    FAILED = "failed"
    SKIPPED = "skipped"


class EnrichmentOutcome(StrEnum):
    """The result of the optional deterministic enrichment step."""

    NOT_ATTEMPTED = "not_attempted"
    PENDING = "pending"
    CREATED = "created"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(slots=True)
class IngestionJobState:
    """Pure transition rules for a preview/confirm import job."""

    status: IngestionJobStatus = IngestionJobStatus.STAGED

    def mark_validation_failed(self) -> None:
        self._transition_to(IngestionJobStatus.VALIDATION_FAILED)

    def queue(self) -> None:
        self._transition_to(IngestionJobStatus.QUEUED)

    def begin_processing(self) -> None:
        self._transition_to(IngestionJobStatus.PROCESSING)

    def record_queue_failure(self) -> None:
        self._transition_to(IngestionJobStatus.QUEUE_FAILED)

    def complete(self, *, has_errors: bool) -> None:
        target = (
            IngestionJobStatus.COMPLETED_WITH_ERRORS if has_errors else IngestionJobStatus.COMPLETED
        )
        self._transition_to(target)

    def _transition_to(self, target: IngestionJobStatus) -> None:
        allowed = _JOB_TRANSITIONS[self.status]
        if target not in allowed:
            raise InvalidTransitionError(
                f"cannot move an ingestion job from {self.status} to {target}"
            )
        self.status = target


@dataclass(slots=True)
class IngestionItemState:
    """Pure transition rules and outcomes for one staged import record."""

    has_contact: bool = False
    status: IngestionItemStatus = IngestionItemStatus.PENDING
    account_outcome: AccountOutcome = AccountOutcome.NOT_ATTEMPTED
    contact_outcome: ContactOutcome = ContactOutcome.NOT_PROVIDED
    enrichment_outcome: EnrichmentOutcome = EnrichmentOutcome.NOT_ATTEMPTED

    def __post_init__(self) -> None:
        if self.has_contact and self.contact_outcome is ContactOutcome.NOT_PROVIDED:
            self.contact_outcome = ContactOutcome.NOT_ATTEMPTED

    def mark_validation_failed(self) -> None:
        self._transition_to(IngestionItemStatus.VALIDATION_FAILED)

    def begin_processing(self) -> None:
        self._transition_to(IngestionItemStatus.PROCESSING)
        self.account_outcome = AccountOutcome.PENDING
        if self.has_contact:
            self.contact_outcome = ContactOutcome.PENDING

    def record_account(self, outcome: AccountOutcome) -> None:
        if self.status is not IngestionItemStatus.PROCESSING:
            raise InvalidTransitionError(
                "an ingestion item must be processing before recording an account"
            )
        if self.account_outcome is not AccountOutcome.PENDING:
            raise InvalidTransitionError("an account outcome was already recorded")
        if outcome not in {AccountOutcome.CREATED, AccountOutcome.DUPLICATE, AccountOutcome.FAILED}:
            raise InvalidTransitionError("an account outcome must be final")
        self.account_outcome = outcome
        if outcome is AccountOutcome.FAILED:
            if self.has_contact:
                self.contact_outcome = ContactOutcome.SKIPPED
            self.enrichment_outcome = EnrichmentOutcome.SKIPPED
            self._transition_to(IngestionItemStatus.COMPLETED)

    def record_contact(self, outcome: ContactOutcome) -> None:
        if self.status is not IngestionItemStatus.PROCESSING:
            raise InvalidTransitionError(
                "an ingestion item must be processing before recording a contact"
            )
        if not self.has_contact:
            raise InvalidTransitionError(
                "an item without a contact cannot record a contact outcome"
            )
        if self.account_outcome not in {AccountOutcome.CREATED, AccountOutcome.DUPLICATE}:
            raise InvalidTransitionError("an item must have a successful account before a contact")
        if self.contact_outcome is not ContactOutcome.PENDING:
            raise InvalidTransitionError("a contact outcome was already recorded")
        if outcome not in {ContactOutcome.CREATED, ContactOutcome.DUPLICATE, ContactOutcome.FAILED}:
            raise InvalidTransitionError("a contact outcome must be final")
        self.contact_outcome = outcome

    def record_enrichment(self, outcome: EnrichmentOutcome) -> None:
        if self.status is not IngestionItemStatus.PROCESSING:
            raise InvalidTransitionError(
                "an ingestion item must be processing before recording enrichment"
            )
        if self.account_outcome not in {AccountOutcome.CREATED, AccountOutcome.DUPLICATE}:
            raise InvalidTransitionError("an item must have a successful account before enrichment")
        if self.has_contact and self.contact_outcome is ContactOutcome.PENDING:
            raise InvalidTransitionError(
                "an item must have a final contact outcome before enrichment"
            )
        if self.enrichment_outcome is not EnrichmentOutcome.NOT_ATTEMPTED:
            raise InvalidTransitionError("an enrichment outcome was already recorded")
        if outcome not in {EnrichmentOutcome.CREATED, EnrichmentOutcome.FAILED}:
            raise InvalidTransitionError("an enrichment outcome must be final")
        self.enrichment_outcome = outcome
        self._transition_to(IngestionItemStatus.COMPLETED)

    def _transition_to(self, target: IngestionItemStatus) -> None:
        allowed = _ITEM_TRANSITIONS[self.status]
        if target not in allowed:
            raise InvalidTransitionError(
                f"cannot move an ingestion item from {self.status} to {target}"
            )
        self.status = target


_JOB_TRANSITIONS: dict[IngestionJobStatus, frozenset[IngestionJobStatus]] = {
    IngestionJobStatus.STAGED: frozenset(
        {IngestionJobStatus.VALIDATION_FAILED, IngestionJobStatus.QUEUED}
    ),
    IngestionJobStatus.VALIDATION_FAILED: frozenset(),
    IngestionJobStatus.QUEUED: frozenset(
        {IngestionJobStatus.PROCESSING, IngestionJobStatus.QUEUE_FAILED}
    ),
    IngestionJobStatus.PROCESSING: frozenset(
        {IngestionJobStatus.COMPLETED, IngestionJobStatus.COMPLETED_WITH_ERRORS}
    ),
    IngestionJobStatus.QUEUE_FAILED: frozenset({IngestionJobStatus.QUEUED}),
    IngestionJobStatus.COMPLETED: frozenset(),
    IngestionJobStatus.COMPLETED_WITH_ERRORS: frozenset(),
}

_ITEM_TRANSITIONS: dict[IngestionItemStatus, frozenset[IngestionItemStatus]] = {
    IngestionItemStatus.PENDING: frozenset(
        {IngestionItemStatus.VALIDATION_FAILED, IngestionItemStatus.PROCESSING}
    ),
    IngestionItemStatus.VALIDATION_FAILED: frozenset(),
    IngestionItemStatus.PROCESSING: frozenset({IngestionItemStatus.COMPLETED}),
    IngestionItemStatus.COMPLETED: frozenset(),
}
