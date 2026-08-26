import pytest
from revops.domain.errors import PolicyViolationError
from revops.domain.values.score import Score, ScoreTier


@pytest.mark.parametrize(
    ("value", "expected_tier"),
    [
        (0, ScoreTier.COLD),
        (39, ScoreTier.COLD),
        (40, ScoreTier.WARM),  # lower boundary of WARM
        (69, ScoreTier.WARM),  # upper boundary of WARM
        (70, ScoreTier.HOT),  # lower boundary of HOT
        (100, ScoreTier.HOT),
    ],
)
def test_tier_boundaries(value: int, expected_tier: ScoreTier) -> None:
    assert Score(value).tier is expected_tier


@pytest.mark.parametrize("value", [-1, 101, 1000])
def test_rejects_out_of_range_values(value: int) -> None:
    with pytest.raises(PolicyViolationError):
        Score(value)
