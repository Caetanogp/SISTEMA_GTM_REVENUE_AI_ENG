"""Score: a 0-100 account priority score with a derived tier.

Tier boundaries are a business rule, not a UI concern — they belong here, not in a frontend
component or a formatting helper.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from revops.domain.errors import PolicyViolationError

_HOT_THRESHOLD = 70
_WARM_THRESHOLD = 40


class ScoreTier(StrEnum):
    HOT = "hot"
    WARM = "warm"
    COLD = "cold"


@dataclass(frozen=True, slots=True)
class Score:
    """A priority score in the closed interval [0, 100]."""

    value: int

    def __post_init__(self) -> None:
        if not 0 <= self.value <= 100:
            raise PolicyViolationError(f"score must be within [0, 100], got {self.value}")

    @property
    def tier(self) -> ScoreTier:
        if self.value >= _HOT_THRESHOLD:
            return ScoreTier.HOT
        if self.value >= _WARM_THRESHOLD:
            return ScoreTier.WARM
        return ScoreTier.COLD
