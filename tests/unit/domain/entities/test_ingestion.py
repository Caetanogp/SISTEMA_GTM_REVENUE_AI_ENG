"""Unit tests for the pure ingestion job and item state machines."""

import pytest
from revops.domain.entities.ingestion import (
    AccountOutcome,
    ContactOutcome,
    EnrichmentOutcome,
    IngestionItemState,
    IngestionItemStatus,
    IngestionJobState,
    IngestionJobStatus,
)
from revops.domain.errors import InvalidTransitionError


def test_job_requires_confirmed_queueing_before_processing_and_can_complete() -> None:
    job = IngestionJobState()

    job.queue()
    job.begin_processing()
    job.complete(has_errors=False)

    assert job.status is IngestionJobStatus.COMPLETED
    assert job.status.is_terminal


def test_all_invalid_preview_is_terminal_and_cannot_be_confirmed() -> None:
    job = IngestionJobState()

    job.mark_validation_failed()

    assert job.status is IngestionJobStatus.VALIDATION_FAILED
    assert job.status.is_terminal
    with pytest.raises(InvalidTransitionError, match="ingestion job"):
        job.queue()


def test_queue_failure_can_be_retried_and_completion_can_have_errors() -> None:
    job = IngestionJobState()

    job.queue()
    job.record_queue_failure()
    job.queue()
    job.begin_processing()
    job.complete(has_errors=True)

    assert job.status is IngestionJobStatus.COMPLETED_WITH_ERRORS


def test_valid_item_records_account_contact_and_enrichment_before_terminal() -> None:
    item = IngestionItemState(has_contact=True)

    item.begin_processing()
    item.record_account(AccountOutcome.CREATED)
    item.record_contact(ContactOutcome.CREATED)
    item.record_enrichment(EnrichmentOutcome.CREATED)

    assert item.status is IngestionItemStatus.COMPLETED
    assert item.status.is_terminal
    assert item.account_outcome is AccountOutcome.CREATED
    assert item.contact_outcome is ContactOutcome.CREATED
    assert item.enrichment_outcome is EnrichmentOutcome.CREATED


def test_duplicate_item_can_complete_with_an_enrichment_failure() -> None:
    item = IngestionItemState(has_contact=True)

    item.begin_processing()
    item.record_account(AccountOutcome.DUPLICATE)
    item.record_contact(ContactOutcome.DUPLICATE)
    item.record_enrichment(EnrichmentOutcome.FAILED)

    assert item.status is IngestionItemStatus.COMPLETED
    assert item.enrichment_outcome is EnrichmentOutcome.FAILED


def test_account_failure_skips_remaining_operations_and_completes_item() -> None:
    item = IngestionItemState(has_contact=True)

    item.begin_processing()
    item.record_account(AccountOutcome.FAILED)

    assert item.status is IngestionItemStatus.COMPLETED
    assert item.contact_outcome is ContactOutcome.SKIPPED
    assert item.enrichment_outcome is EnrichmentOutcome.SKIPPED


def test_item_rejects_outcomes_in_an_invalid_order() -> None:
    item = IngestionItemState()

    with pytest.raises(InvalidTransitionError, match="processing"):
        item.record_account(AccountOutcome.CREATED)

    item.begin_processing()
    with pytest.raises(InvalidTransitionError, match="successful account"):
        item.record_enrichment(EnrichmentOutcome.CREATED)


def test_existing_account_can_have_a_new_contact() -> None:
    item = IngestionItemState(has_contact=True)

    item.begin_processing()
    item.record_account(AccountOutcome.DUPLICATE)
    item.record_contact(ContactOutcome.CREATED)
    item.record_enrichment(EnrichmentOutcome.CREATED)

    assert item.account_outcome is AccountOutcome.DUPLICATE
    assert item.contact_outcome is ContactOutcome.CREATED


def test_absent_contact_is_distinct_from_a_skipped_or_failed_contact() -> None:
    item = IngestionItemState()

    item.begin_processing()
    item.record_account(AccountOutcome.CREATED)
    item.record_enrichment(EnrichmentOutcome.CREATED)

    assert item.contact_outcome is ContactOutcome.NOT_PROVIDED


def test_contact_failure_does_not_prevent_account_enrichment() -> None:
    item = IngestionItemState(has_contact=True)

    item.begin_processing()
    item.record_account(AccountOutcome.CREATED)
    item.record_contact(ContactOutcome.FAILED)
    item.record_enrichment(EnrichmentOutcome.CREATED)

    assert item.status is IngestionItemStatus.COMPLETED
    assert item.contact_outcome is ContactOutcome.FAILED


def test_invalid_item_is_terminal_without_processing() -> None:
    item = IngestionItemState()

    item.mark_validation_failed()

    assert item.status is IngestionItemStatus.VALIDATION_FAILED
    assert item.status.is_terminal
    with pytest.raises(InvalidTransitionError, match="ingestion item"):
        item.begin_processing()
