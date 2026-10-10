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
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator

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
from revops.domain.entities.knowledge import (
    KnowledgeCategory,
    KnowledgeDocument,
    KnowledgeFormat,
    KnowledgeLanguage,
    KnowledgeScope,
    KnowledgeVersionStatus,
)
from revops.domain.values.outreach import DraftLanguage, FollowupStatus, ResearchStatus
from revops.domain.values.reply import (
    ReplyCategory,
    ReplyClassificationStatus,
    ReplyLanguage,
    ReplyNextAction,
    ReplyText,
)
from revops.domain.values.retrieval import RetrievalProvenance, RetrievalScore, RetrievedPassage
from revops.domain.values.runtime import RuntimeFailureCode, RuntimeOutcome
from revops.domain.values.score import ScoreTier


class DeduplicationScanArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_types: tuple[DeduplicationRecordType, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _canonicalize_record_types(self) -> Self:
        values = tuple(self.record_types)
        if len(set(values)) != len(values):
            raise ValueError("record_types must not contain duplicates")
        order = {value: index for index, value in enumerate(DeduplicationRecordType)}
        object.__setattr__(self, "record_types", tuple(sorted(values, key=order.__getitem__)))
        return self


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


@dataclass(frozen=True, slots=True)
class DeduplicationStatusResult:
    scan: DeduplicationScanResult
    total: int
    pending: int
    dismissed: int
    merged: int
    stale: int


@dataclass(frozen=True, slots=True)
class DeduplicationRecordSummary:
    record_type: DeduplicationRecordType
    id: UUID
    account_id: UUID | None = None
    company_name: str | None = None
    domain: str | None = None
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None


@dataclass(frozen=True, slots=True)
class DeduplicationHistoryResult:
    id: UUID
    record_type: DeduplicationRecordType
    action: str
    candidate_id: UUID | None
    related_event_id: UUID | None
    alias_id: UUID | None
    canonical_id: UUID | None
    reason_codes: tuple[str, ...]
    actor_id: UUID
    occurred_at: datetime


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


class CreateCampaignArgs(BaseModel):
    """Validated untrusted campaign fields before the authenticated tenant is injected."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    source: str = Field(min_length=1)
    channel: str = Field(min_length=1)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class CreateTouchpointArgs(BaseModel):
    """Validated untrusted touchpoint fields before the authenticated tenant is injected."""

    model_config = ConfigDict(extra="forbid")

    account_id: UUID
    contact_id: UUID | None = None
    campaign_id: UUID | None = None
    type: str = Field(min_length=1)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)
    occurred_at: datetime

    @field_validator("occurred_at")
    @classmethod
    def _require_aware_occurred_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")
        return value


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


class SearchAccountsArgs(BaseModel):
    """Validated read arguments; tenant identity is supplied by the authenticated run."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(default="", max_length=200)
    limit: int = Field(default=10, ge=1, le=20)


class GetAccountContextArgs(BaseModel):
    """Validated account lookup arguments without a caller-selectable organization."""

    model_config = ConfigDict(extra="forbid")

    account_id: UUID


class CreateTaskToolArgs(BaseModel):
    """Model-authored task fields; owner and tenant come from trusted run context."""

    model_config = ConfigDict(extra="forbid")

    account_id: UUID
    title: str = Field(min_length=1, max_length=255)
    due_at: datetime


class AgentToolDecision(BaseModel):
    """Structured model decision consumed by the bounded runtime."""

    model_config = ConfigDict(extra="forbid")

    outcome: RuntimeOutcome
    tool_name: str = Field(min_length=1, max_length=64)
    arguments: dict[str, JsonValue] = Field(default_factory=dict)
    continue_after: bool = False


class RuntimeFailure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: RuntimeFailureCode


class RuntimeToolEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sequence: int = Field(ge=1)
    tool_name: str
    risk: str
    outcome: str
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RuntimeResult:
    """Serializable application result returned to the graph boundary."""

    outcome: RuntimeOutcome | None
    tool_name: str | None
    tool_arguments: dict[str, object] | None
    tool_result: dict[str, object] | None
    evidence: tuple[RuntimeToolEvidence, ...]
    failure: RuntimeFailure | None = None
    requires_approval: bool = False


class ResearchCompanyArgs(BaseModel):
    """Model-authored research fields; tenant and source policy are trusted context."""

    model_config = ConfigDict(extra="forbid")

    account_id: UUID
    contact_id: UUID | None = None
    objective: str = Field(min_length=1, max_length=500)


class PrepareFollowupArgs(BaseModel):
    """Model-authored follow-up fields without recipient or authorization controls."""

    model_config = ConfigDict(extra="forbid")

    account_id: UUID
    contact_id: UUID | None = None
    objective: str = Field(min_length=1, max_length=500)
    language: DraftLanguage


class ResearchSourceDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1, max_length=128)
    url: str = Field(min_length=1, max_length=2_048)
    retrieved_at: datetime
    content_hash: str = Field(min_length=64, max_length=64)
    excerpt: str = Field(min_length=1, max_length=2_000)


class ResearchFactDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=128)
    value: str = Field(min_length=1, max_length=2_000)
    source_ids: tuple[str, ...] = Field(min_length=1, max_length=16)


class ResearchResultDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: UUID
    status: ResearchStatus
    facts: tuple[ResearchFactDTO, ...] = Field(max_length=64)
    sources: tuple[ResearchSourceDTO, ...] = Field(max_length=3)
    limitations: tuple[str, ...] = Field(default_factory=tuple, max_length=16)


class ResearchExtractionFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=128)
    value: str = Field(min_length=1, max_length=2_000)
    source_ids: tuple[str, ...] = Field(min_length=1, max_length=16)


class ResearchExtractionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    facts: tuple[ResearchExtractionFact, ...] = Field(max_length=64)
    limitations: tuple[str, ...] = Field(default_factory=tuple, max_length=16)


class GeneratedClaimDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=1_000)
    source_ids: tuple[str, ...] = Field(min_length=1, max_length=16)


class FollowupResultDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: UUID
    status: FollowupStatus
    language: DraftLanguage | None = None
    subject: str | None = Field(default=None, max_length=160)
    body: str | None = Field(default=None, max_length=6_000)
    rationale: str | None = Field(default=None, max_length=2_000)
    claims: tuple[GeneratedClaimDTO, ...] = Field(default_factory=tuple, max_length=64)
    source_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=64)
    limitations: tuple[str, ...] = Field(default_factory=tuple, max_length=16)


class FollowupGenerationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=6_000)
    language: DraftLanguage
    rationale: str = Field(min_length=1, max_length=2_000)
    claims: tuple[GeneratedClaimDTO, ...] = Field(min_length=1, max_length=64)


class ClaimVerificationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accepted: bool
    unsupported_claim_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=64)
    contradictory_claim_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=64)
    limitations: tuple[str, ...] = Field(default_factory=tuple, max_length=16)


class AgentRunArtifactDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    research: ResearchResultDTO | None = None
    followup: FollowupResultDTO | None = None
    status: str = Field(min_length=1, max_length=64)
    limitations: tuple[str, ...] = Field(default_factory=tuple, max_length=16)


class RegisterReplyArgs(BaseModel):
    """Untrusted reply fields; organization and author come from authentication."""

    model_config = ConfigDict(extra="forbid")

    account_id: UUID
    contact_id: UUID | None = None
    text: str = Field(min_length=1, max_length=8_000)
    language: ReplyLanguage

    def to_domain(self) -> ReplyText:
        return ReplyText(value=self.text, language=self.language)


class ReplyEvidenceDTO(BaseModel):
    """One half-open evidence range into the authorized current reply."""

    model_config = ConfigDict(extra="forbid")

    start_offset: int = Field(ge=0)
    end_offset: int = Field(ge=1)


class ReplyClassificationOutput(BaseModel):
    """Strict provider output; domain policy decides whether it is safe to use."""

    model_config = ConfigDict(extra="forbid")

    category: ReplyCategory
    confidence: float = Field(ge=0, le=1)
    language: ReplyLanguage
    evidence: tuple[ReplyEvidenceDTO, ...] = Field(default_factory=tuple, max_length=32)
    ambiguous: bool = False
    limitations: tuple[str, ...] = Field(default_factory=tuple, max_length=16)


@dataclass(frozen=True, slots=True)
class ReplyResultDTO:
    """Typed, sanitized classification result stored in a run artifact."""

    category: ReplyCategory
    status: ReplyClassificationStatus
    recommended_action: ReplyNextAction
    confidence: float
    language: ReplyLanguage
    evidence: tuple[ReplyEvidenceDTO, ...]
    limitations: tuple[str, ...]


class AppendReplyFeedbackArgs(BaseModel):
    """A correction is append-only and may not replace the original result."""

    model_config = ConfigDict(extra="forbid")

    corrected_category: ReplyCategory
    comment: str | None = Field(default=None, min_length=1, max_length=2_000)


class ReplyRunConfig(BaseModel):
    """Trusted runtime provenance required before a classification run is reserved."""

    model_config = ConfigDict(extra="forbid")

    graph_version: str = Field(min_length=1, max_length=128)
    prompt_version: str = Field(min_length=1, max_length=128)
    model_config_json: dict[str, JsonValue] = Field(default_factory=dict)


class LLMUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    model: str
    model_config_json: dict[str, object]
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    token_cost_usd: Decimal = Field(ge=0)
    latency_ms: int = Field(ge=0)


class LLMHealthStatus(StrEnum):
    DISABLED = "disabled"
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class LLMFailureKind(StrEnum):
    NETWORK = "network"
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    SERVER = "server"
    AUTHENTICATION = "authentication"
    PERMISSION = "permission"
    BILLING = "billing"
    CONFIGURATION = "configuration"
    INVALID_REQUEST = "invalid_request"
    SAFETY_REFUSAL = "safety_refusal"
    INVALID_RESPONSE = "invalid_response"


class LLMProviderHealth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    status: LLMHealthStatus


class LLMGatewayHealth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: str
    status: LLMHealthStatus
    providers: tuple[LLMProviderHealth, ...]


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
    phone: str | None = None


@dataclass(frozen=True, slots=True)
class CanonicalIngestionRecord:
    """Normalized business values persisted only after a confirmed import."""

    company_name: str
    domain: str
    email: str | None
    full_name: str | None
    title: str | None
    phone: str | None = None

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


class SubmitKnowledgeDocumentArgs(BaseModel):
    """Untrusted tenant fields before the authenticated context is injected.

    Tenant callers cannot select scope. The application creates organization-private
    documents only; platform content is reserved for deployment-controlled seeding.
    """

    model_config = ConfigDict(extra="forbid")

    document_key: str = Field(min_length=1, max_length=200)
    category: KnowledgeCategory
    language: KnowledgeLanguage
    format: KnowledgeFormat
    content: str = Field(min_length=1)
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)

    def to_domain(self) -> KnowledgeDocument:
        """Build the pure document after schema validation, before persistence."""
        return KnowledgeDocument(
            document_key=self.document_key,
            category=self.category,
            language=self.language,
            format=self.format,
            scope=KnowledgeScope.ORGANIZATION,
            content=self.content,
            metadata=self.metadata,
        )


@dataclass(frozen=True, slots=True)
class PlatformSeedDocument:
    """Trusted, reviewed platform content supplied only by the deployment composition root."""

    document_key: str
    category: KnowledgeCategory
    language: KnowledgeLanguage
    format: KnowledgeFormat
    content: str
    metadata: dict[str, str | int | float | bool | None]
    revision: int
    content_hash: str

    def to_domain(self) -> KnowledgeDocument:
        return KnowledgeDocument(
            document_key=self.document_key,
            category=self.category,
            language=self.language,
            format=self.format,
            scope=KnowledgeScope.PLATFORM,
            content=self.content,
            metadata=self.metadata,
        )


class KnowledgeAdminContext(BaseModel):
    """Authenticated tenant identity accepted by knowledge lifecycle use cases."""

    model_config = ConfigDict(extra="forbid")

    actor_id: UUID
    organization_id: UUID
    role: Literal["admin"]


class KnowledgeRetrievalContext(BaseModel):
    """Trusted task identity injected by the authenticated application boundary."""

    model_config = ConfigDict(extra="forbid")

    organization_id: UUID


class RetrieveKnowledgeArgs(BaseModel):
    """Untrusted query parameters; corpus and tenant selection are intentionally absent."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=4_000)
    limit: int = Field(ge=1, le=20)
    token_budget: int = Field(gt=0)


@dataclass(frozen=True, slots=True)
class KnowledgeCorpus:
    """Explicit owner boundary for platform or organization knowledge."""

    id: UUID
    scope: KnowledgeScope
    organization_id: UUID | None = None


class KnowledgeActivationAction(StrEnum):
    PUBLICATION = "publication"
    HISTORICAL_ACTIVATION = "historical_activation"


class KnowledgeProcessingEventType(StrEnum):
    STARTED = "started"
    RETRY_SCHEDULED = "retry_scheduled"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DUPLICATE_IGNORED = "duplicate_ignored"


@dataclass(frozen=True, slots=True)
class KnowledgeProcessingEvent:
    """Sanitized append-only fact about one asynchronous processing delivery."""

    id: UUID
    corpus_id: UUID
    version_id: UUID
    delivery_id: str
    attempt: int
    event_type: KnowledgeProcessingEventType
    retryable: bool
    failure_code: str | None
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class KnowledgeRevisionActivation:
    """Safe provenance for one append-only corpus activation event."""

    id: UUID
    corpus_id: UUID
    revision_id: UUID
    target_version_id: UUID
    action: KnowledgeActivationAction
    activated_by: UUID
    idempotency_key: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class KnowledgeDocumentVersion:
    """An immutable content version and its lifecycle state."""

    id: UUID
    document_id: UUID
    corpus_id: UUID
    requested_by: UUID
    document: KnowledgeDocument
    status: KnowledgeVersionStatus
    idempotency_key: str
    created_at: datetime
    embedding_model: str | None = None
    embedding_dimension: int | None = None
    failure_code: str | None = None
    seed_revision: int | None = None
    replayed: bool = False


@dataclass(frozen=True, slots=True)
class KnowledgeChunkEmbedding:
    """One chunk and its vector, retained together until atomic publication."""

    ordinal: int
    text: str
    content_hash: str
    vector: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class EmbeddingBatch:
    """Ordered provider output; vectors correspond positionally to submitted texts."""

    model: str
    dimension: int
    vectors: tuple[tuple[float, ...], ...]


@dataclass(frozen=True, slots=True)
class KnowledgeRetrievalCandidate:
    """A fully filtered, attributable passage returned by the retrieval adapter."""

    passage: RetrievedPassage


@dataclass(frozen=True, slots=True)
class OmittedKnowledgePassage:
    """A ranked passage excluded solely because its fenced section did not fit."""

    provenance: RetrievalProvenance
    score: RetrievalScore
    reason: Literal["token_budget_exceeded"] = "token_budget_exceeded"


@dataclass(frozen=True, slots=True)
class TaskKnowledgeContext:
    """Fenced retrieved context, its stable token estimate, and explicit omissions."""

    text: str
    token_count: int
    included: tuple[RetrievedPassage, ...]
    omitted: tuple[OmittedKnowledgePassage, ...]


@dataclass(frozen=True, slots=True)
class CorpusRevision:
    """Immutable publication manifest for an organization corpus."""

    id: UUID
    corpus_id: UUID
    version_id: UUID
    manifest_hash: str
    activated_by: UUID
    created_at: datetime
