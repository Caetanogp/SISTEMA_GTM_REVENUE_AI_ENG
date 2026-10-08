"""Request and response schemas for the API."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from revops.application.dto import FollowupResultDTO, ResearchResultDTO
from revops.domain.entities.knowledge import KnowledgeCategory, KnowledgeFormat, KnowledgeLanguage


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


class AgentRunResultResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    research: ResearchResultDTO | None = None
    followup: FollowupResultDTO | None = None
    limitations: tuple[str, ...] = ()


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


class DeduplicationScanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_types: tuple[str, ...] = Field(min_length=1)


class DeduplicationScanResponse(BaseModel):
    id: UUID
    organization_id: UUID
    record_types: tuple[str, ...]
    status: str
    replayed: bool = False


class DeduplicationStatusResponse(DeduplicationScanResponse):
    total: int
    pending: int
    dismissed: int
    merged: int
    stale: int


class DeduplicationCandidateResponse(BaseModel):
    id: UUID
    scan_id: UUID
    organization_id: UUID
    record_type: str
    left_id: UUID
    right_id: UUID
    score: int
    reasons: tuple[str, ...]
    policy_version: str
    status: str


class DeduplicationDismissRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(pattern=r"^(not_duplicate|insufficient_evidence)$")


class DeduplicationMergeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    master_record_id: UUID


class DeduplicationDecisionResponse(BaseModel):
    candidate_id: UUID
    status: str
    replayed: bool = False


class DeduplicationMergeResponse(BaseModel):
    event_id: UUID
    alias_id: UUID
    canonical_id: UUID
    replayed: bool = False


class DeduplicationHistoryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    record_type: str
    action: str
    candidate_id: UUID | None
    related_event_id: UUID | None
    alias_id: UUID | None
    canonical_id: UUID | None
    reason_codes: tuple[str, ...]
    actor_id: UUID
    occurred_at: datetime


class KnowledgeVersionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_key: str = Field(min_length=1, max_length=200)
    category: KnowledgeCategory
    language: KnowledgeLanguage
    format: KnowledgeFormat
    content: str = Field(min_length=1)
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class KnowledgeVersionMetadataResponse(BaseModel):
    id: UUID
    document_id: UUID
    document_key: str
    category: KnowledgeCategory
    language: KnowledgeLanguage
    format: KnowledgeFormat
    status: str
    created_at: datetime
    embedding_model: str | None = None
    embedding_dimension: int | None = None
    failure_code: str | None = None


class KnowledgeVersionResponse(KnowledgeVersionMetadataResponse):
    content: str
    metadata: dict[str, str | int | float | bool | None]


class KnowledgeRevisionResponse(BaseModel):
    id: UUID
    version_id: UUID
    manifest_hash: str
    activated_by: UUID
    created_at: datetime


class KnowledgeRetrievalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=4_000)
    limit: int = Field(default=5, ge=1, le=20)
    token_budget: int = Field(default=2_048, gt=0)


class KnowledgeRetrievalProvenanceResponse(BaseModel):
    document_key: str
    document_version_id: UUID
    chunk_id: UUID
    chunk_ordinal: int
    category: KnowledgeCategory
    language: KnowledgeLanguage
    active_revision_id: UUID


class KnowledgeRetrievalPassageResponse(BaseModel):
    text: str
    provenance: KnowledgeRetrievalProvenanceResponse
    score: float


class KnowledgeRetrievalOmittedResponse(BaseModel):
    provenance: KnowledgeRetrievalProvenanceResponse
    score: float
    reason: str


class KnowledgeRetrievalResponse(BaseModel):
    text: str
    token_count: int
    included: list[KnowledgeRetrievalPassageResponse]
    omitted: list[KnowledgeRetrievalOmittedResponse]
