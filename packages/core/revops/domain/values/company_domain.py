"""CompanyDomain: the primary deduplication identifier for accounts.

See the project guide, section 5.1: "Accounts: domínio/website normalizado como identificador
forte." Named CompanyDomain (not Domain) to avoid colliding with the domain *layer* in imports
and discussion.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from revops.domain.errors import PolicyViolationError

_DOMAIN_PATTERN = re.compile(
    r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$"
)


def _normalize(raw: str) -> str:
    value = raw.strip().lower()
    value = re.sub(r"^[a-z][a-z0-9+.-]*://", "", value)  # strip scheme
    value = value.split("/", 1)[0]  # strip path
    value = value.split("?", 1)[0]  # strip query
    value = value.split(":", 1)[0]  # strip port
    if value.startswith("www."):
        value = value[len("www.") :]
    return value


@dataclass(frozen=True, slots=True)
class CompanyDomain:
    """A normalized company domain, e.g. "acme.com" from "https://www.acme.com/pricing"."""

    value: str

    def __post_init__(self) -> None:
        normalized = _normalize(self.value)
        if not _DOMAIN_PATTERN.match(normalized):
            raise PolicyViolationError(f"'{self.value}' is not a valid company domain")
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value
