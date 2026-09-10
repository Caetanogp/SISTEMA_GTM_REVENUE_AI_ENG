from __future__ import annotations

from uuid import UUID

import pytest
from revops.infrastructure.queue.deduplication import (
    CANDIDATE_LIMIT_FAILURE,
    DeduplicationScanBoundError,
    DeduplicationScanProcessor,
)


def test_candidate_pairs_are_ordered_unique_and_bounded() -> None:
    first = UUID(int=1)
    second = UUID(int=2)
    third = UUID(int=3)
    buckets = [
        {"shared": [third, first, second]},
        {"repeated": [second, first]},
    ]

    assert DeduplicationScanProcessor._candidate_pairs(buckets, 3) == {
        (first, second),
        (first, third),
        (second, third),
    }

    with pytest.raises(DeduplicationScanBoundError) as caught:
        DeduplicationScanProcessor._candidate_pairs(buckets, 2)
    assert caught.value.failure_code == CANDIDATE_LIMIT_FAILURE
