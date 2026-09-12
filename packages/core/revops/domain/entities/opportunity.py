"""Opportunity: a pipeline deal tied to an account.

Drives prioritization and revenue attribution.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from revops.domain.errors import PolicyViolationError


class OpportunityStage(StrEnum):
    PROSPECTING = "prospecting"
    QUALIFICATION = "qualification"
    PROPOSAL = "proposal"
    NEGOTIATION = "negotiation"
    CLOSED_WON = "closed_won"
    CLOSED_LOST = "closed_lost"

    @property
    def is_open(self) -> bool:
        return self not in (OpportunityStage.CLOSED_WON, OpportunityStage.CLOSED_LOST)


class OpportunityStatus(StrEnum):
    """The small, explicit revenue lifecycle independent of CRM stage names."""

    OPEN = "open"
    WON = "won"
    LOST = "lost"


@dataclass(slots=True)
class Opportunity:
    id: UUID
    organization_id: UUID
    account_id: UUID
    stage: OpportunityStage
    value: Decimal
    status: OpportunityStatus = OpportunityStatus.OPEN

    def __post_init__(self) -> None:
        if not isinstance(self.status, OpportunityStatus):
            raise PolicyViolationError("status must be an OpportunityStatus")
