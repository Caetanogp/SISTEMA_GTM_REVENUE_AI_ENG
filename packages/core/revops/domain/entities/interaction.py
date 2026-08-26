"""Interaction: a record of engagement with an account - the recency/engagement signal source."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(slots=True)
class Interaction:
    id: UUID
    organization_id: UUID
    account_id: UUID
    channel: str
    occurred_at: datetime
    summary: str = ""
