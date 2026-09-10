"""Adversarial validation for the administrative deduplication boundary."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from revops.application.dto import DeduplicationScanArgs
from revops.domain.entities.deduplication import DeduplicationRecordType

from apps.api.schemas import DeduplicationHistoryResponse


def test_scan_input_rejects_unknown_values_and_duplicate_types() -> None:
    with pytest.raises(ValueError, match="not a valid"):
        DeduplicationScanArgs(record_types=("organization",))
    with pytest.raises(ValidationError):
        DeduplicationScanArgs(
            record_types=(DeduplicationRecordType.ACCOUNT, DeduplicationRecordType.ACCOUNT)
        )


def test_history_response_rejects_payload_and_idempotency_fields() -> None:
    with pytest.raises(ValidationError):
        DeduplicationHistoryResponse.model_validate(
            {
                "id": "00000000-0000-0000-0000-000000000001",
                "record_type": "account",
                "action": "merge",
                "candidate_id": None,
                "related_event_id": None,
                "alias_id": None,
                "canonical_id": None,
                "reason_codes": (),
                "actor_id": "00000000-0000-0000-0000-000000000002",
                "occurred_at": "2026-01-01T00:00:00Z",
                "payload": {"email": "secret@example.test"},
                "idempotency_key": "secret-key",
            }
        )
