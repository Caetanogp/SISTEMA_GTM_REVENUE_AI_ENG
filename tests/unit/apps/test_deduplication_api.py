"""Unit coverage for the administrative deduplication API boundary."""

from __future__ import annotations

from uuid import uuid4

import pytest
from revops.application.dto import DeduplicationScanArgs
from revops.domain.entities.deduplication import DeduplicationRecordType
from revops.domain.policies.deduplication import MergeEligibilityPolicy


def test_scan_args_canonicalize_order_and_reject_duplicates() -> None:
    args = DeduplicationScanArgs(
        record_types=(DeduplicationRecordType.CONTACT, DeduplicationRecordType.ACCOUNT)
    )
    assert args.record_types == (
        DeduplicationRecordType.ACCOUNT,
        DeduplicationRecordType.CONTACT,
    )
    with pytest.raises(ValueError, match="duplicates"):
        DeduplicationScanArgs(
            record_types=(DeduplicationRecordType.ACCOUNT, DeduplicationRecordType.ACCOUNT)
        )


def test_merge_policy_rejects_alias_reuse_and_accepts_standalone_absorption() -> None:
    master, member, standalone = uuid4(), uuid4(), uuid4()
    policy = MergeEligibilityPolicy()
    decision = policy.evaluate(
        requested_master_id=master,
        candidate_member_ids=(master, standalone),
        master_group=(master,),
        alias_group=(),
        active_alias_ids=frozenset(),
    )
    assert decision.eligible
    rejected = policy.evaluate(
        requested_master_id=master,
        candidate_member_ids=(master, member),
        master_group=(master,),
        alias_group=(),
        active_alias_ids=frozenset({member}),
    )
    assert not rejected.eligible
    assert rejected.reason_code == "record_already_has_active_alias"
