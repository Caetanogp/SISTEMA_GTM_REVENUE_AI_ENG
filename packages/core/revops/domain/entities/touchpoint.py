"""Touchpoint: an append-only, explicitly attributed engagement event."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from revops.domain.entities.campaign import _require_aware_timestamp


@dataclass(slots=True)
class Touchpoint:
    """An account event optionally linked to a contact and campaign."""

    id: UUID
    organization_id: UUID
    account_id: UUID
    type: str
    occurred_at: datetime
    created_at: datetime
    contact_id: UUID | None = None
    campaign_id: UUID | None = None
    metadata: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_aware_timestamp(self.occurred_at, field_name="occurred_at")
        _require_aware_timestamp(self.created_at, field_name="created_at")
