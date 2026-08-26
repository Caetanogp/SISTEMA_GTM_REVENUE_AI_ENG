"""Contact: a person in an account's buying group. Deduplicated on normalized email."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from revops.domain.values.email import EmailAddress


@dataclass(slots=True)
class Contact:
    id: UUID
    organization_id: UUID
    account_id: UUID
    email: EmailAddress
    full_name: str
    title: str = ""
