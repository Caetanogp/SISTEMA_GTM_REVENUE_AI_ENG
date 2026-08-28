"""Application ports: the only way inner layers talk to the outside world.

Each of these is a `typing.Protocol` — infrastructure adapters implement them structurally, with
no inheritance and no import from application back onto infrastructure. `lint-imports` enforces
this at the module level ("Application depends on no infrastructure library"); this file is what
makes that enforceable in the first place. Signatures only, per
`docs/specs/SPEC-001-vertical-slice-account-prioritization/plan.md`'s application section — no
implementations here.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from types import TracebackType
from typing import Protocol, runtime_checkable
from uuid import UUID

from revops.domain.entities.account import Account
from revops.domain.entities.interaction import Interaction
from revops.domain.entities.opportunity import Opportunity
from revops.domain.entities.task import Task


@runtime_checkable
class AccountRepository(Protocol):
    """Read access to accounts and the signals `policies.prioritization` scores them on."""

    async def get(self, organization_id: UUID, account_id: UUID) -> Account: ...

    async def list_for_organization(self, organization_id: UUID) -> Sequence[Account]: ...

    async def list_interactions(
        self, organization_id: UUID, account_id: UUID
    ) -> Sequence[Interaction]: ...

    async def list_open_opportunities(
        self, organization_id: UUID, account_id: UUID
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
        organization_id: UUID,
        actor_id: UUID,
        action: str,
        payload: Mapping[str, object],
        outcome: str,
        occurred_at: datetime,
    ) -> None: ...


@runtime_checkable
class LLMGateway(Protocol):
    """Structured-output access to the LLM. Free text never crosses this boundary unvalidated."""

    async def complete[T](self, *, prompt: str, response_model: type[T]) -> T: ...


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

    async def __aenter__(self) -> UnitOfWork: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...
