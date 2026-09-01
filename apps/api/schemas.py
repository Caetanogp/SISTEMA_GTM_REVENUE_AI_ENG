"""Request and response schemas for the API."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CreateTaskDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: UUID
    title: str = Field(min_length=1)
    due_at: datetime


class StartAgentRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_text: str = Field(min_length=1)
    token_budget: int = Field(default=4096, ge=1)


class StartAgentRunResponse(BaseModel):
    agent_run_id: UUID
    thread_id: str
    status: str
    interrupt: dict[str, object] | None = None


class AgentRunListItem(BaseModel):
    agent_run_id: UUID
    organization_id: UUID
    requested_by: UUID | None
    request_text: str
    graph_version: str
    prompt_version: str
    status: str
    started_at: datetime
    completed_at: datetime | None
    latest_event_type: str | None


class ApprovalDecisionType(StrEnum):
    APPROVE = "approve"
    EDIT = "edit"
    REJECT = "reject"


class ApprovalDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: ApprovalDecisionType
    edited: CreateTaskDraftRequest | None = None

    @model_validator(mode="after")
    def _validate_edit_payload(self) -> Self:
        if self.decision is ApprovalDecisionType.EDIT and self.edited is None:
            raise ValueError("edited payload is required when decision is edit")
        if self.decision is not ApprovalDecisionType.EDIT and self.edited is not None:
            raise ValueError("edited payload is only allowed when decision is edit")
        return self


class TaskResponse(BaseModel):
    id: UUID
    organization_id: UUID
    owner_id: UUID
    account_id: UUID
    title: str
    due_at: datetime
    status: str


class ApprovalResponse(BaseModel):
    agent_run_id: UUID
    status: str
    task: TaskResponse | None = None


class IngestionRecordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    company_name: str | None = None
    domain: str | None = None
    email: str | None = None
    full_name: str | None = None
    title: str | None = None
    phone: str | None = None


class IngestionStageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str = Field(min_length=1, max_length=128)
    idempotency_key: str = Field(min_length=1, max_length=128)
    records: list[IngestionRecordRequest] = Field(min_length=1, max_length=1000)


class IngestionItemResponse(BaseModel):
    row_number: int
    status: str
    validation_codes: tuple[str, ...]
    account_outcome: str
    contact_outcome: str
    enrichment_outcome: str
    account_id: UUID | None = None
    contact_id: UUID | None = None
    enrichment_id: UUID | None = None


class IngestionJobResponse(BaseModel):
    id: UUID
    organization_id: UUID
    source: str
    idempotency_key: str
    status: str
    items: list[IngestionItemResponse] | None = None
    replayed: bool = False
    published: bool | None = None
