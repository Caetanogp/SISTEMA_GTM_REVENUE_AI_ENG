"""Campaign: tenant-scoped acquisition provenance."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from revops.domain.errors import PolicyViolationError


def _require_aware_timestamp(value: datetime, *, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise PolicyViolationError(f"{field_name} must be timezone-aware")


@dataclass(slots=True)
class Campaign:
    """A named, explicitly recorded marketing campaign."""

    id: UUID
    organization_id: UUID
    name: str
    source: str
    channel: str
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_aware_timestamp(self.created_at, field_name="created_at")
        _require_aware_timestamp(self.updated_at, field_name="updated_at")
        if self.updated_at < self.created_at:
            raise PolicyViolationError("updated_at must not be earlier than created_at")
