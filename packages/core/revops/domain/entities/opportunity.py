"""Opportunity: a pipeline deal tied to an account.

Drives prioritization and revenue attribution.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from uuid import UUID


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


@dataclass(slots=True)
class Opportunity:
    id: UUID
    organization_id: UUID
    account_id: UUID
    stage: OpportunityStage
    value: Decimal
