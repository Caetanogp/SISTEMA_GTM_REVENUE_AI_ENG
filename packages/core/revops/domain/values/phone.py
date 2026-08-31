"""Validated E.164 phone numbers used as a secondary contact identity signal."""

from __future__ import annotations

import re
from dataclasses import dataclass

from revops.domain.errors import PolicyViolationError

_E164_PATTERN = re.compile(r"^\+[1-9][0-9]{7,14}$")


@dataclass(frozen=True, slots=True)
class PhoneNumber:
    """A phone number in its canonical E.164 textual representation."""

    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip()
        if not _E164_PATTERN.fullmatch(normalized):
            raise PolicyViolationError("phone must be an E.164 number with 8 to 15 digits")
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value
