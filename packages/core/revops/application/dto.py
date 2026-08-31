"""Application DTOs: Pydantic models at the boundary where free text becomes a validated payload.

AGENTS.md: "LLM output is structured (Pydantic). Free text never reaches a write tool." Both models
use `extra="forbid"` so a field the LLM hallucinates onto a payload is rejected at the schema stage,
before it ever reaches a domain rule or an authorization check.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from revops.domain.entities.deduplication import (
    DeduplicationCandidateStatus,
    DeduplicationRecordType,
    DeduplicationScanStatus,
)
from revops.domain.entities.ingestion import (
    AccountOutcome,
    ContactOutcome,
    EnrichmentOutcome,
    IngestionItemStatus,
    IngestionJobStatus,
)
from revops.domain.values.score import ScoreTier


class DeduplicationScanArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_types: tuple[DeduplicationRecordType, ...] = Field(min_length=1)


class DismissCandidateArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(pattern=r"^(not_duplicate|insufficient_evidence)$")


@dataclass(frozen=True, slots=True)
class DeduplicationScanResult:
    id: UUID
    organization_id: UUID
    record_types: tuple[DeduplicationRecordType, ...]
    status: DeduplicationScanStatus
    replayed: bool = False


@dataclass(frozen=True, slots=True)
class DeduplicationCandidateResult:
    id: UUID
    scan_id: UUID
    organization_id: UUID
    record_type: DeduplicationRecordType
    left_id: UUID
    right_id: UUID
    score: int
    reasons: tuple[str, ...]
    policy_version: str
    status: DeduplicationCandidateStatus


@dataclass(frozen=True, slots=True)
class DeduplicationDecisionResult:
    candidate_id: UUID
    status: DeduplicationCandidateStatus
    replayed: bool = False


@dataclass(frozen=True, slots=True)
class CanonicalRecordResult:
    record_type: DeduplicationRecordType
    requested_id: UUID
    canonical_id: UUID


@dataclass(frozen=True, slots=True)
class DeduplicationMergeResult:
    event_id: UUID
    alias_id: UUID
    canonical_id: UUID
    replayed: bool = False


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


class ContextSectionSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    text: str


class AccountCandidate(AccountScore):
    """Trusted CRM context and deterministic score passed to the reasoning step."""

    company_name: str
    context: list[ContextSectionSnapshot]
    dropped_context_labels: list[str]
    token_count: int = Field(ge=0)


class CreateTaskDraft(BaseModel):
    """LLM-authored task fields. Ownership is injected from authenticated run state."""

    model_config = ConfigDict(extra="forbid")

    account_id: UUID
    title: str = Field(min_length=1)
    due_at: datetime


class RankedAccount(AccountScore):
    reasons: list[str] = Field(min_length=1)


class PrioritizationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accounts: list[RankedAccount] = Field(min_length=1)
    task: CreateTaskDraft


class LLMUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    model: str
    model_config_json: dict[str, object]
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    token_cost_usd: Decimal = Field(ge=0)
    latency_ms: int = Field(ge=0)


@dataclass(frozen=True, slots=True)
class LLMResult[T]:
    output: T
    usage: LLMUsage


class ApprovalDecisionType(StrEnum):
    APPROVE = "approve"
    EDIT = "edit"
    REJECT = "reject"


class ApprovalDecisionInput(BaseModel):
    """Validated resume payload. Identity fields are injected by the authenticated API."""

    model_config = ConfigDict(extra="forbid")

    decision: ApprovalDecisionType
    organization_id: UUID
    decided_by: UUID
    edited: CreateTaskDraft | None = None


class IngestionRecordInput(BaseModel):
    """One structurally safe import record before business-value validation."""

    model_config = ConfigDict(extra="forbid")

    company_name: str | None = None
    domain: str | None = None
    email: str | None = None
    full_name: str | None = None
    title: str | None = None


@dataclass(frozen=True, slots=True)
class CanonicalIngestionRecord:
    """Normalized business values persisted only after a confirmed import."""

    company_name: str
    domain: str
    email: str | None
    full_name: str | None
    title: str | None

    @property
    def has_contact(self) -> bool:
        return self.email is not None


@dataclass(frozen=True, slots=True)
class IngestionValidationIssue:
    row_number: int
    code: str


@dataclass(frozen=True, slots=True)
class StagedIngestionItem:
    row_number: int
    record: CanonicalIngestionRecord | None
    validation_codes: tuple[str, ...]
    status: IngestionItemStatus
    account_outcome: AccountOutcome
    contact_outcome: ContactOutcome
    enrichment_outcome: EnrichmentOutcome
    account_id: UUID | None = None
    contact_id: UUID | None = None
    enrichment_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class StagedIngestionJob:
    id: UUID
    organization_id: UUID
    requested_by: UUID
    source: str
    idempotency_key: str
    content_hash: str
    status: IngestionJobStatus
    items: tuple[StagedIngestionItem, ...]


@dataclass(frozen=True, slots=True)
class StageIngestionResult:
    job: StagedIngestionJob
    replayed: bool


@dataclass(frozen=True, slots=True)
class ConfirmIngestionResult:
    job: StagedIngestionJob
    published: bool
    replayed: bool


class EnrichmentProfile(BaseModel):
    """Canonical provider output accepted by the ingestion use case."""

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1, max_length=64)
    schema_version: str = Field(min_length=1, max_length=64)
    industry: str = Field(min_length=1, max_length=128)
    employee_band: str = Field(min_length=1, max_length=64)
    country: str = Field(min_length=1, max_length=128)
    summary: str = Field(min_length=1, max_length=2000)


@dataclass(frozen=True, slots=True)
class AccountEnrichmentRecord:
    id: UUID
    ingestion_job_id: UUID
    organization_id: UUID
    account_id: UUID
    profile: EnrichmentProfile
    created_at: datetime


@dataclass(frozen=True, slots=True)
class IngestionItemSummary:
    nonterminal_count: int
    error_count: int


@dataclass(frozen=True, slots=True)
class ProcessIngestionResult:
    job_id: UUID
    status: IngestionJobStatus
    processed_domains: tuple[str, ...]
