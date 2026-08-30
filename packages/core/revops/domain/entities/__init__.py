"""Entities: identity-bearing objects with a lifecycle, scoped to one organization."""

from revops.domain.entities.account import Account
from revops.domain.entities.contact import Contact
from revops.domain.entities.ingestion import (
    AccountOutcome,
    ContactOutcome,
    EnrichmentOutcome,
    IngestionItemState,
    IngestionItemStatus,
    IngestionJobState,
    IngestionJobStatus,
)
from revops.domain.entities.interaction import Interaction
from revops.domain.entities.opportunity import Opportunity, OpportunityStage
from revops.domain.entities.organization import Organization
from revops.domain.entities.task import Task, TaskStatus
from revops.domain.entities.user import User

__all__ = [
    "Account",
    "AccountOutcome",
    "Contact",
    "ContactOutcome",
    "EnrichmentOutcome",
    "IngestionItemState",
    "IngestionItemStatus",
    "IngestionJobState",
    "IngestionJobStatus",
    "Interaction",
    "Opportunity",
    "OpportunityStage",
    "Organization",
    "Task",
    "TaskStatus",
    "User",
]
