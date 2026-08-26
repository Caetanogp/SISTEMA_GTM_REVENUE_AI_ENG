"""EmailAddress: the primary deduplication identifier for contacts.

See the NORMALIZE -> MATCH -> MERGE -> MASTER RECORD -> PRESERVE HISTORY rule in the project guide
(section 5.1). Normalization here is what "NORMALIZE" means for a contact.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from revops.domain.errors import PolicyViolationError

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass(frozen=True, slots=True)
class EmailAddress:
    """A validated, lowercase-normalized email address."""

    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip().lower()
        if not _EMAIL_PATTERN.match(normalized):
            raise PolicyViolationError(f"'{self.value}' is not a valid email address")
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value
