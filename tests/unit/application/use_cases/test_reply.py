"""Application contracts for tenant-safe, immutable reply intelligence."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from revops.application.dto import AppendReplyFeedbackArgs, RegisterReplyArgs, ReplyRunConfig
from revops.application.ports import (
    AgentRunEventRecord,
    AgentRunRecord,
    CanonicalRecordGroup,
    ReplyClassificationRequestRecord,
    ReplyFeedbackRecord,
    ReplyRecord,
    ReplyUnitOfWork,
)
from revops.application.use_cases.reply import (
    AppendReplyFeedback,
    ListReplyFeedback,
    RegisterReply,
    ReplyConflictError,
    ReserveReplyClassification,
)
from revops.domain.entities.account import Account
from revops.domain.entities.contact import Contact
from revops.domain.entities.deduplication import DeduplicationRecordType
from revops.domain.errors import PolicyViolationError
from revops.domain.values.company_domain import CompanyDomain
from revops.domain.values.email import EmailAddress
from revops.domain.values.reply import ReplyCategory, ReplyLanguage


class _Clock:
    def now(self) -> datetime:
        return datetime(2026, 10, 10, tzinfo=UTC)


class _Accounts:
    def __init__(self, account: Account) -> None:
        self.account = account

    async def get(self, organization_id: UUID, account_id: UUID) -> Account:
        assert organization_id == self.account.organization_id
        assert account_id == self.account.id
        return self.account

    async def list_for_organization(self, organization_id: UUID) -> Sequence[Account]:
        return ()

    async def list_interactions(
        self, organization_id: UUID, account_ids: object
    ) -> Sequence[object]:
        return ()

    async def list_open_opportunities(
        self, organization_id: UUID, account_ids: object
    ) -> Sequence[object]:
        return ()


class _Contacts:
    def __init__(self, contact: Contact) -> None:
        self.contact = contact

    async def get(self, organization_id: UUID, contact_id: UUID) -> Contact | None:
        if organization_id == self.contact.organization_id and contact_id == self.contact.id:
            return self.contact
        return None


class _Canonical:
    def __init__(
        self, groups: dict[tuple[DeduplicationRecordType, UUID], CanonicalRecordGroup]
    ) -> None:
        self.groups = groups
        self.writes: list[tuple[DeduplicationRecordType, UUID]] = []

    async def resolve(
        self, organization_id: UUID, record_type: DeduplicationRecordType, record_id: UUID
    ) -> CanonicalRecordGroup | None:
        return self.groups.get((record_type, record_id))

    async def resolve_for_write(
        self, organization_id: UUID, record_type: DeduplicationRecordType, record_id: UUID
    ) -> CanonicalRecordGroup | None:
        self.writes.append((record_type, record_id))
        return self.groups.get((record_type, record_id))

    async def fingerprint_for_write(
        self, organization_id: UUID, record_type: DeduplicationRecordType, record_id: UUID
    ) -> str | None:
        return None


class _Replies:
    def __init__(self) -> None:
        self.records: dict[UUID, ReplyRecord] = {}

    async def get(self, organization_id: UUID, reply_id: UUID) -> ReplyRecord | None:
        record = self.records.get(reply_id)
        return record if record is not None and record.organization_id == organization_id else None

    async def get_by_idempotency_key(
        self, organization_id: UUID, idempotency_key: str
    ) -> ReplyRecord | None:
        return next(
            (
                record
                for record in self.records.values()
                if record.organization_id == organization_id
                and record.idempotency_key == idempotency_key
            ),
            None,
        )

    async def add(self, reply: ReplyRecord) -> None:
        self.records[reply.id] = reply


class _Requests:
    def __init__(self) -> None:
        self.records: dict[UUID, ReplyClassificationRequestRecord] = {}

    async def get_by_reply_id(
        self, organization_id: UUID, reply_id: UUID
    ) -> ReplyClassificationRequestRecord | None:
        return next(
            (
                record
                for record in self.records.values()
                if record.organization_id == organization_id and record.reply_id == reply_id
            ),
            None,
        )

    async def get_by_run_id(
        self, organization_id: UUID, run_id: UUID
    ) -> ReplyClassificationRequestRecord | None:
        return next(
            (
                record
                for record in self.records.values()
                if record.organization_id == organization_id and record.run_id == run_id
            ),
            None,
        )

    async def add(self, request: ReplyClassificationRequestRecord) -> None:
        self.records[request.id] = request


class _Feedback:
    def __init__(self) -> None:
        self.records: dict[UUID, ReplyFeedbackRecord] = {}

    async def get_by_idempotency_key(
        self, organization_id: UUID, idempotency_key: str
    ) -> ReplyFeedbackRecord | None:
        return next(
            (
                record
                for record in self.records.values()
                if record.organization_id == organization_id
                and record.idempotency_key == idempotency_key
            ),
            None,
        )

    async def append(self, feedback: ReplyFeedbackRecord) -> None:
        self.records[feedback.id] = feedback

    async def list_for_run(
        self, organization_id: UUID, run_id: UUID
    ) -> Sequence[ReplyFeedbackRecord]:
        return tuple(
            record
            for record in self.records.values()
            if record.organization_id == organization_id and record.run_id == run_id
        )


class _Runs:
    def __init__(self) -> None:
        self.runs: list[AgentRunRecord] = []
        self.events: list[AgentRunEventRecord] = []

    async def add(self, run: AgentRunRecord) -> None:
        self.runs.append(run)

    async def add_event(self, event: AgentRunEventRecord) -> None:
        self.events.append(event)


class _Uow:
    def __init__(self, account: Account, contact: Contact, account_alias: UUID) -> None:
        self.accounts = _Accounts(account)
        self.contacts = _Contacts(contact)
        self.canonical = _Canonical(
            {
                (DeduplicationRecordType.ACCOUNT, account.id): CanonicalRecordGroup(
                    account.id, (account.id, account_alias)
                ),
                (DeduplicationRecordType.ACCOUNT, account_alias): CanonicalRecordGroup(
                    account.id, (account.id, account_alias)
                ),
                (DeduplicationRecordType.CONTACT, contact.id): CanonicalRecordGroup(
                    contact.id, (contact.id,)
                ),
            }
        )
        self.replies = _Replies()
        self.classification_requests = _Requests()
        self.feedback = _Feedback()
        self.runs = _Runs()
        self.commits = 0

    async def __aenter__(self) -> _Uow:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        return None


def _records() -> tuple[UUID, UUID, Account, Contact, _Uow]:
    organization_id, actor_id, account_id, alias_id, contact_id = (uuid4() for _ in range(5))
    account = Account(
        id=account_id,
        organization_id=organization_id,
        company_name="Example",
        domain=CompanyDomain("example.test"),
        created_at=datetime(2026, 10, 10, tzinfo=UTC),
    )
    contact = Contact(
        id=contact_id,
        organization_id=organization_id,
        account_id=alias_id,
        email=EmailAddress("buyer@example.test"),
        full_name="Buyer",
    )
    return organization_id, actor_id, account, contact, _Uow(account, contact, alias_id)


def _args(account_id: UUID, contact_id: UUID | None) -> RegisterReplyArgs:
    return RegisterReplyArgs(
        account_id=account_id,
        contact_id=contact_id,
        text="Please send pricing details.",
        language=ReplyLanguage.ENGLISH,
    )


async def test_register_reply_canonicalizes_relationships_and_replays_alias_payload() -> None:
    organization_id, actor_id, account, contact, uow = _records()
    alias_id = contact.account_id
    use_case = RegisterReply(lambda: uow, _Clock())

    created = await use_case.execute(
        organization_id=organization_id,
        actor_id=actor_id,
        args=_args(alias_id, contact.id),
        idempotency_key="reply-1",
    )
    replayed = await use_case.execute(
        organization_id=organization_id,
        actor_id=actor_id,
        args=_args(account.id, contact.id),
        idempotency_key="reply-1",
    )

    assert created.reply.account_id == account.id
    assert created.reply.contact_id == contact.id
    assert replayed.reply == created.reply
    assert replayed.replayed is True
    assert uow.commits == 1


async def test_register_reply_rejects_mismatched_contact_account() -> None:
    organization_id, actor_id, _account, contact, uow = _records()
    other_account = uuid4()
    uow.accounts = _Accounts(
        Account(
            id=other_account,
            organization_id=organization_id,
            company_name="Other",
            domain=CompanyDomain("other.test"),
            created_at=datetime(2026, 10, 10, tzinfo=UTC),
        )
    )
    uow.canonical.groups[(DeduplicationRecordType.ACCOUNT, other_account)] = CanonicalRecordGroup(
        other_account, (other_account,)
    )

    with pytest.raises(PolicyViolationError, match="does not belong"):
        await RegisterReply(lambda: uow, _Clock()).execute(
            organization_id=organization_id,
            actor_id=actor_id,
            args=_args(other_account, contact.id),
            idempotency_key="reply-1",
        )
    assert uow.commits == 0


async def test_reservation_is_singleton_and_never_puts_reply_text_in_run_records() -> None:
    organization_id, actor_id, account, contact, uow = _records()
    reply = (
        await RegisterReply(lambda: uow, _Clock()).execute(
            organization_id=organization_id,
            actor_id=actor_id,
            args=_args(account.id, contact.id),
            idempotency_key="reply-1",
        )
    ).reply
    reserve = ReserveReplyClassification(lambda: uow, _Clock())
    config = ReplyRunConfig(
        graph_version="reply-intelligence.v1",
        prompt_version="classify_reply.v1",
        model_config_json={"model": "fake"},
    )

    created = await reserve.execute(
        organization_id=organization_id,
        actor_id=actor_id,
        reply_id=reply.id,
        run_config=config,
    )
    replayed = await reserve.execute(
        organization_id=organization_id,
        actor_id=actor_id,
        reply_id=reply.id,
        run_config=config,
    )

    assert replayed.replayed is True
    assert replayed.request == created.request
    assert len(uow.runs.runs) == len(uow.runs.events) == 1
    assert reply.reply.value not in uow.runs.runs[0].request_text
    assert uow.runs.events[0].metadata == {"reply_id": str(reply.id)}


async def test_feedback_is_append_only_tenant_scoped_and_idempotent() -> None:
    organization_id, actor_id, account, contact, uow = _records()
    reply = (
        await RegisterReply(lambda: uow, _Clock()).execute(
            organization_id=organization_id,
            actor_id=actor_id,
            args=_args(account.id, contact.id),
            idempotency_key="reply-1",
        )
    ).reply
    reservation = await ReserveReplyClassification(lambda: uow, _Clock()).execute(
        organization_id=organization_id,
        actor_id=actor_id,
        reply_id=reply.id,
        run_config=ReplyRunConfig(
            graph_version="reply-intelligence.v1", prompt_version="classify_reply.v1"
        ),
    )
    append = AppendReplyFeedback(lambda: uow, _Clock())
    args = AppendReplyFeedbackArgs(
        corrected_category=ReplyCategory.QUESTION, comment="Asked for pricing."
    )

    feedback = await append.execute(
        organization_id=organization_id,
        actor_id=actor_id,
        run_id=reservation.request.run_id,
        args=args,
        idempotency_key="feedback-1",
    )
    replayed = await append.execute(
        organization_id=organization_id,
        actor_id=actor_id,
        run_id=reservation.request.run_id,
        args=args,
        idempotency_key="feedback-1",
    )
    history = await ListReplyFeedback(lambda: uow).execute(
        organization_id=organization_id, run_id=reservation.request.run_id
    )

    assert replayed == feedback
    assert history.records == (feedback,)
    with pytest.raises(ReplyConflictError):
        await append.execute(
            organization_id=organization_id,
            actor_id=actor_id,
            run_id=reservation.request.run_id,
            args=AppendReplyFeedbackArgs(corrected_category=ReplyCategory.INTERESTED),
            idempotency_key="feedback-1",
        )
    with pytest.raises(PermissionError, match="unavailable"):
        await ListReplyFeedback(lambda: uow).execute(
            organization_id=uuid4(), run_id=reservation.request.run_id
        )


def test_reply_dtos_forbid_tenant_identity_and_invalid_untrusted_fields() -> None:
    assert "organization_id" not in RegisterReplyArgs.model_fields
    with pytest.raises(ValidationError):
        RegisterReplyArgs.model_validate(
            {
                "account_id": uuid4(),
                "text": "Reply text",
                "language": ReplyLanguage.ENGLISH,
                "organization_id": uuid4(),
            }
        )
    with pytest.raises(ValidationError):
        AppendReplyFeedbackArgs(corrected_category=ReplyCategory.QUESTION, comment="")


def test_reply_uow_is_a_structural_protocol() -> None:
    _, _, _, _, uow = _records()
    assert isinstance(uow, ReplyUnitOfWork)
