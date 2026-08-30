"""Unit tests for the pure ingestion job and item state machines."""

import pytest
from revops.domain.entities.ingestion import (
    EnrichmentOutcome,
    ImportOutcome,
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


def test_valid_item_records_import_and_enrichment_before_becoming_terminal() -> None:
    item = IngestionItemState()

    item.begin_processing()
    item.record_import(ImportOutcome.CREATED)
    item.record_enrichment(EnrichmentOutcome.CREATED)

    assert item.status is IngestionItemStatus.COMPLETED
    assert item.status.is_terminal
    assert item.import_outcome is ImportOutcome.CREATED
    assert item.enrichment_outcome is EnrichmentOutcome.CREATED


def test_duplicate_item_can_complete_with_an_enrichment_failure() -> None:
    item = IngestionItemState()

    item.begin_processing()
    item.record_import(ImportOutcome.DUPLICATE)
    item.record_enrichment(EnrichmentOutcome.FAILED)

    assert item.status is IngestionItemStatus.COMPLETED
    assert item.enrichment_outcome is EnrichmentOutcome.FAILED


def test_import_failure_completes_item_without_enrichment() -> None:
    item = IngestionItemState()

    item.begin_processing()
    item.record_import(ImportOutcome.FAILED)

    assert item.status is IngestionItemStatus.COMPLETED
    assert item.enrichment_outcome is EnrichmentOutcome.NOT_REQUESTED


def test_item_rejects_outcomes_in_an_invalid_order() -> None:
    item = IngestionItemState()

    with pytest.raises(InvalidTransitionError, match="processing"):
        item.record_import(ImportOutcome.CREATED)

    item.begin_processing()
    with pytest.raises(InvalidTransitionError, match="successful import"):
        item.record_enrichment(EnrichmentOutcome.CREATED)


def test_invalid_item_is_terminal_without_processing() -> None:
    item = IngestionItemState()

    item.mark_validation_failed()

    assert item.status is IngestionItemStatus.VALIDATION_FAILED
    assert item.status.is_terminal
    with pytest.raises(InvalidTransitionError, match="ingestion item"):
        item.begin_processing()
