"""Application DTOs: Pydantic models at the boundary where free text becomes a validated payload.

AGENTS.md: "LLM output is structured (Pydantic). Free text never reaches a write tool." Both models
use `extra="forbid"` so a field the LLM hallucinates onto a payload is rejected at the schema stage,
before it ever reaches a domain rule or an authorization check.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from revops.domain.values.score import ScoreTier


class CreateTaskArgs(BaseModel):
    """The validated payload behind the `create_task` tool call.

    No `organization_id` here on purpose - AGENTS.md/plan.md: the organization boundary is
    resolved from the auth token by the use case, never taken from LLM output or a request body.
    """

    model_config = ConfigDict(extra="forbid")

    account_id: UUID
    owner_id: UUID
    title: str = Field(min_length=1)
    due_at: datetime


class AccountScore(BaseModel):
    """One account's rank from `PrioritizeAccounts`, with the evidence behind the score."""

    model_config = ConfigDict(extra="forbid")

    account_id: UUID
    score: int = Field(ge=0, le=100)
    tier: ScoreTier
    evidence: list[str]
