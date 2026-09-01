"""Application ports: the only way inner layers talk to the outside world.

Each of these is a `typing.Protocol` — infrastructure adapters implement them structurally, with
no inheritance and no import from application back onto infrastructure. `lint-imports` enforces
this at the module level ("Application depends on no infrastructure library"); this file is what
makes that enforceable in the first place. Signatures only, per
`docs/specs/SPEC-001-vertical-slice-account-prioritization/plan.md`'s application section — no
implementations here.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from types import TracebackType
from typing import Protocol, TypeVar, runtime_checkable
from uuid import UUID

from revops.application.dto import (
    AccountEnrichmentRecord,
    ApprovalDecisionType,
    EnrichmentProfile,
    IngestionItemSummary,
    LLMResult,
    StagedIngestionItem,
    StagedIngestionJob,
)
from revops.domain.entities.account import Account
from revops.domain.entities.contact import Contact
from revops.domain.entities.deduplication import (
    DeduplicationCandidate,
    DeduplicationCandidateStatus,
    DeduplicationRecordType,
    DeduplicationScanStatus,
    RecordAlias,
)
from revops.domain.entities.ingestion import IngestionJobStatus
from revops.domain.entities.interaction import Interaction
from revops.domain.entities.opportunity import Opportunity
from revops.domain.entities.task import Task


@dataclass(frozen=True, slots=True)
class ApprovalRecord:
    id: UUID
    action_id: UUID
    organization_id: UUID
    decision: ApprovalDecisionType
    payload: Mapping[str, object]
    decided_by: UUID
    decided_at: datetime


@dataclass(frozen=True, slots=True)
class AgentRunRecord:
    id: UUID
    organization_id: UUID
    requested_by: UUID
    request_text: str
    graph_version: str
    prompt_version: str
    model_config_json: Mapping[str, object]
    started_at: datetime


@dataclass(frozen=True, slots=True)
class AgentRunEventRecord:
    id: UUID
    run_id: UUID
    organization_id: UUID
    event_type: str
    occurred_at: datetime
    graph_version: str
    prompt_version: str
    model_config_json: Mapping[str, object]
    latency_ms: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    token_cost_usd: Decimal | None = None
    error: str | None = None
    metadata: Mapping[str, object] | None = None


@runtime_checkable
class AccountRepository(Protocol):
    """Read access to accounts and the signals `policies.prioritization` scores them on."""

    async def get(self, organization_id: UUID, account_id: UUID) -> Account: ...

    async def list_for_organization(self, organization_id: UUID) -> Sequence[Account]: ...

    async def list_interactions(
        self, organization_id: UUID, account_ids: Sequence[UUID] | UUID
    ) -> Sequence[Interaction]: ...

    async def list_open_opportunities(
        self, organization_id: UUID, account_ids: Sequence[UUID] | UUID
    ) -> Sequence[Opportunity]: ...


@runtime_checkable
class TaskRepository(Protocol):
    """Persistence for `Task`, the entity `create_task` writes and HITL approval acts on."""

    async def add(self, task: Task) -> None: ...

    async def get(self, organization_id: UUID, task_id: UUID) -> Task: ...

    async def update(self, task: Task) -> None: ...


@runtime_checkable
class AuditTrail(Protocol):
    """Append-only record of every agent action, including failures and rejections.

    AGENTS.md, Security rules: the audit trail is append-only — no update or delete method exists
    on this port on purpose.
    """

    async def record(
        self,
        *,
        action_id: UUID,
        run_id: UUID,
        organization_id: UUID,
        actor_id: UUID,
        action: str,
        payload: Mapping[str, object],
        outcome: str,
        occurred_at: datetime,
        approved_by: UUID | None,
        executed_at: datetime | None,
    ) -> None: ...


@runtime_checkable
class ApprovalRepository(Protocol):
    async def get_for_action(
        self, organization_id: UUID, action_id: UUID
    ) -> ApprovalRecord | None: ...

    async def add(self, approval: ApprovalRecord) -> None: ...


@runtime_checkable
class AgentRunRepository(Protocol):
    async def add(self, run: AgentRunRecord) -> None: ...

    async def add_event(self, event: AgentRunEventRecord) -> None: ...


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class CreatedRecord[T]:
    value: T
    created: bool


@runtime_checkable
class LLMGateway(Protocol):
    """Structured-output access to the LLM. Free text never crosses this boundary unvalidated."""

    async def complete(self, *, prompt: str, response_model: type[T]) -> LLMResult[T]: ...


@runtime_checkable
class Clock(Protocol):
    """Injectable time source so use cases and tests never call `datetime.now()` directly."""

    def now(self) -> datetime: ...


@runtime_checkable
class UnitOfWork(Protocol):
    """Transactional boundary grouping the repositories and audit trail for one use case call."""

    accounts: AccountRepository
    tasks: TaskRepository
    audit: AuditTrail
    approvals: ApprovalRepository
    runs: AgentRunRepository
    canonical: CanonicalResolver | None

    async def __aenter__(self) -> UnitOfWork: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


@runtime_checkable
class IngestionJobRepository(Protocol):
    """Tenant-scoped job reservation and lifecycle persistence."""

    async def get(self, organization_id: UUID, job_id: UUID) -> StagedIngestionJob | None: ...

    async def get_by_idempotency_key(
        self, organization_id: UUID, idempotency_key: str
    ) -> StagedIngestionJob | None: ...

    async def add(self, job: StagedIngestionJob) -> None: ...

    async def get_for_update(
        self, organization_id: UUID, job_id: UUID
    ) -> StagedIngestionJob | None: ...

    async def set_status(
        self, organization_id: UUID, job_id: UUID, status: IngestionJobStatus
    ) -> StagedIngestionJob: ...


@runtime_checkable
class IngestionItemRepository(Protocol):
    """Staged records and the domain-group locking seam used by the worker."""

    async def add_many(self, job_id: UUID, items: Sequence[StagedIngestionItem]) -> None: ...

    async def list_for_job(
        self, organization_id: UUID, job_id: UUID, *, offset: int, limit: int
    ) -> Sequence[StagedIngestionItem]: ...

    async def list_processable_domains(
        self, organization_id: UUID, job_id: UUID
    ) -> Sequence[str]: ...

    async def lock_domain_items(
        self, organization_id: UUID, job_id: UUID, domain: str
    ) -> Sequence[StagedIngestionItem]: ...

    async def save_result(
        self, organization_id: UUID, job_id: UUID, item: StagedIngestionItem
    ) -> None: ...

    async def summarize(self, organization_id: UUID, job_id: UUID) -> IngestionItemSummary: ...


@runtime_checkable
class IngestionAccountRepository(Protocol):
    async def get_or_create(self, account: Account) -> CreatedRecord[Account]: ...


@runtime_checkable
class IngestionContactRepository(Protocol):
    async def get_or_create(self, contact: Contact) -> CreatedRecord[Contact]: ...


@runtime_checkable
class AccountEnrichmentRepository(Protocol):
    """Append-only enrichment snapshots; no update or delete operation exists."""

    async def get_or_create(
        self, enrichment: AccountEnrichmentRecord
    ) -> CreatedRecord[AccountEnrichmentRecord]: ...


@runtime_checkable
class IngestionUnitOfWork(Protocol):
    """Dedicated transaction boundary for ingestion, independent of SPEC-001 UoW."""

    jobs: IngestionJobRepository
    items: IngestionItemRepository
    accounts: IngestionAccountRepository
    contacts: IngestionContactRepository
    enrichments: AccountEnrichmentRepository
    canonical: CanonicalResolver | None

    async def __aenter__(self) -> IngestionUnitOfWork: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


type IngestionUnitOfWorkFactory = Callable[[], IngestionUnitOfWork]


@dataclass(frozen=True, slots=True)
class DeduplicationScanRecord:
    id: UUID
    organization_id: UUID
    requested_by: UUID
    record_types: tuple[DeduplicationRecordType, ...]
    status: DeduplicationScanStatus
    idempotency_key: str


@runtime_checkable
class DeduplicationScanRepository(Protocol):
    async def get(self, organization_id: UUID, scan_id: UUID) -> DeduplicationScanRecord | None: ...

    async def get_by_idempotency_key(
        self, organization_id: UUID, idempotency_key: str
    ) -> DeduplicationScanRecord | None: ...

    async def add(
        self,
        organization_id: UUID,
        requested_by: UUID,
        scan_id: UUID,
        record_types: Sequence[DeduplicationRecordType],
        idempotency_key: str,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class DeduplicationCandidateRecord:
    id: UUID
    scan_id: UUID
    organization_id: UUID
    candidate: DeduplicationCandidate


@dataclass(frozen=True, slots=True)
class CanonicalRecordGroup:
    """The canonical master and every active member of one logical identity group."""

    canonical_id: UUID
    member_ids: tuple[UUID, ...]


@runtime_checkable
class DeduplicationCandidateRepository(Protocol):
    async def get_for_update(
        self, organization_id: UUID, candidate_id: UUID
    ) -> DeduplicationCandidateRecord | None: ...

    async def list(
        self,
        organization_id: UUID,
        scan_id: UUID,
        *,
        status: DeduplicationCandidateStatus | None,
        record_type: DeduplicationRecordType | None,
        offset: int,
        limit: int,
    ) -> Sequence[DeduplicationCandidateRecord]: ...

    async def save(self, candidate: DeduplicationCandidateRecord) -> None: ...


@runtime_checkable
class DeduplicationAliasRepository(Protocol):
    async def get_active(
        self, organization_id: UUID, record_type: DeduplicationRecordType, record_id: UUID
    ) -> RecordAlias | None: ...

    async def add(self, alias: RecordAlias) -> None: ...

    async def get_for_update(
        self, organization_id: UUID, merge_event_id: UUID
    ) -> RecordAlias | None: ...

    async def save(self, alias: RecordAlias) -> None: ...


@runtime_checkable
class DeduplicationEventRepository(Protocol):
    async def get_by_idempotency_key(
        self, organization_id: UUID, idempotency_key: str
    ) -> Mapping[str, object] | None: ...

    async def add(self, event: Mapping[str, object]) -> None: ...


@runtime_checkable
class CanonicalResolver(Protocol):
    async def resolve(
        self, organization_id: UUID, record_type: DeduplicationRecordType, record_id: UUID
    ) -> CanonicalRecordGroup | None: ...

    async def resolve_for_write(
        self, organization_id: UUID, record_type: DeduplicationRecordType, record_id: UUID
    ) -> CanonicalRecordGroup | None: ...


@runtime_checkable
class DeduplicationUnitOfWork(Protocol):
    scans: DeduplicationScanRepository
    candidates: DeduplicationCandidateRepository
    aliases: DeduplicationAliasRepository
    events: DeduplicationEventRepository
    canonical: CanonicalResolver

    async def __aenter__(self) -> DeduplicationUnitOfWork: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


type DeduplicationUnitOfWorkFactory = Callable[[], DeduplicationUnitOfWork]


@runtime_checkable
class IngestionDispatcher(Protocol):
    """At-least-once dispatch boundary. Publication happens after the queue-state commit."""

    async def publish(self, *, organization_id: UUID, job_id: UUID) -> None: ...


@runtime_checkable
class EnrichmentGateway(Protocol):
    """Validated deterministic enrichment boundary implemented in infrastructure."""

    async def enrich(self, *, domain: str) -> EnrichmentProfile: ...


class EnrichmentGatewayError(Exception):
    """An expected provider failure that should become a per-item outcome."""
