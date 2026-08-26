"""User: an actor inside one organization. Role drives authorization and who can approve actions."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from revops.domain.values.email import EmailAddress


@dataclass(slots=True)
class User:
    id: UUID
    organization_id: UUID
    email: EmailAddress
    role: str
