"""Use cases for immutable, tenant-scoped reply registration and correction."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from revops.application.dto import (
    AppendReplyFeedbackArgs,
    RegisterReplyArgs,
    ReplyClassificationOutput,
    ReplyEvidenceDTO,
    ReplyResultDTO,
    ReplyRunConfig,
)
from revops.application.ports import (
    AgentRunEventRecord,
    AgentRunRecord,
    Clock,
    ReplyClassificationRequestRecord,
    ReplyClassifier,
    ReplyFeedbackRecord,
    ReplyRecord,
    ReplyUnitOfWork,
    ReplyUnitOfWorkFactory,
)
from revops.domain.entities.deduplication import DeduplicationRecordType
from revops.domain.errors import PolicyViolationError
from revops.domain.values.reply import (
    ReplyClassification,
    ReplyEvidence,
    evaluate_reply_classification,
)

_MAX_IDEMPOTENCY_KEY_LENGTH = 128


class ReplyConflictError(Exception):
    """An idempotency key was reused for different immutable reply data."""


@dataclass(frozen=True, slots=True)
class RegisteredReply:
    reply: ReplyRecord
    replayed: bool = False


@dataclass(frozen=True, slots=True)
class ReplyClassificationReservation:
    reply: ReplyRecord
    request: ReplyClassificationRequestRecord
    replayed: bool = False


@dataclass(frozen=True, slots=True)
class ReplyFeedbackHistory:
    records: tuple[ReplyFeedbackRecord, ...]


@dataclass(frozen=True, slots=True)
class ClassifiedReply:
    """A validated outcome plus truthful usage for the append-only run journal."""

    result: ReplyResultDTO
    usage: object


@dataclass(frozen=True, slots=True)
class ClassifyReply:
    """Validate one provider result against the authorized immutable reply."""

    uow_factory: ReplyUnitOfWorkFactory
    classifier: ReplyClassifier

    async def execute(self, *, organization_id: UUID, reply_id: UUID) -> ClassifiedReply:
        async with self.uow_factory() as uow:
            reply = await uow.replies.get(organization_id, reply_id)
            if reply is None:
                raise PermissionError("reply is unavailable")
            provider_result = await self.classifier.classify(reply)
        result = _reply_result(reply.reply, provider_result.output)
        return ClassifiedReply(result=result, usage=provider_result.usage)


@dataclass(frozen=True, slots=True)
class RegisterReply:
    uow_factory: ReplyUnitOfWorkFactory
    clock: Clock

    async def execute(
        self,
        *,
        organization_id: UUID,
        actor_id: UUID,
        args: RegisterReplyArgs,
        idempotency_key: str,
    ) -> RegisteredReply:
        key = _idempotency_key(idempotency_key)
        async with self.uow_factory() as uow:
            account_id, contact_id = await _resolve_relationships(
                uow,
                organization_id=organization_id,
                account_id=args.account_id,
                contact_id=args.contact_id,
            )
            existing = await uow.replies.get_by_idempotency_key(organization_id, key)
            if existing is not None:
                _assert_same_reply(existing, args, account_id, contact_id, actor_id)
                return RegisteredReply(reply=existing, replayed=True)
            reply = ReplyRecord(
                id=uuid4(),
                organization_id=organization_id,
                account_id=account_id,
                contact_id=contact_id,
                submitted_by=actor_id,
                reply=args.to_domain(),
                idempotency_key=key,
                created_at=self.clock.now(),
            )
            await uow.replies.add(reply)
            await uow.commit()
            return RegisteredReply(reply=reply)


@dataclass(frozen=True, slots=True)
class ReserveReplyClassification:
    """Reserve exactly one run and its start event before model execution."""

    uow_factory: ReplyUnitOfWorkFactory
    clock: Clock

    async def execute(
        self,
        *,
        organization_id: UUID,
        actor_id: UUID,
        reply_id: UUID,
        run_config: ReplyRunConfig,
    ) -> ReplyClassificationReservation:
        async with self.uow_factory() as uow:
            reply = await uow.replies.get(organization_id, reply_id)
            if reply is None:
                raise PermissionError("reply is unavailable")
            existing = await uow.classification_requests.get_by_reply_id(organization_id, reply_id)
            if existing is not None:
                return ReplyClassificationReservation(reply=reply, request=existing, replayed=True)

            now = self.clock.now()
            run_id = uuid4()
            request = ReplyClassificationRequestRecord(
                id=uuid4(),
                organization_id=organization_id,
                reply_id=reply.id,
                run_id=run_id,
                requested_by=actor_id,
                created_at=now,
            )
            run = AgentRunRecord(
                id=run_id,
                thread_id=f"reply:{reply.id}",
                organization_id=organization_id,
                requested_by=actor_id,
                request_text=f"reply_classification:{reply.id}",
                graph_version=run_config.graph_version,
                prompt_version=run_config.prompt_version,
                model_config_json=run_config.model_config_json,
                started_at=now,
            )
            event = AgentRunEventRecord(
                id=uuid4(),
                run_id=run_id,
                organization_id=organization_id,
                event_type="started",
                occurred_at=now,
                graph_version=run_config.graph_version,
                prompt_version=run_config.prompt_version,
                model_config_json=run_config.model_config_json,
                metadata={"reply_id": str(reply.id)},
            )
            await uow.runs.add(run)
            await uow.runs.add_event(event)
            await uow.classification_requests.add(request)
            await uow.commit()
            return ReplyClassificationReservation(reply=reply, request=request)


@dataclass(frozen=True, slots=True)
class AppendReplyFeedback:
    uow_factory: ReplyUnitOfWorkFactory
    clock: Clock

    async def execute(
        self,
        *,
        organization_id: UUID,
        actor_id: UUID,
        run_id: UUID,
        args: AppendReplyFeedbackArgs,
        idempotency_key: str,
    ) -> ReplyFeedbackRecord:
        key = _idempotency_key(idempotency_key)
        async with self.uow_factory() as uow:
            request = await uow.classification_requests.get_by_run_id(organization_id, run_id)
            if request is None:
                raise PermissionError("reply classification run is unavailable")
            existing = await uow.feedback.get_by_idempotency_key(organization_id, key)
            if existing is not None:
                _assert_same_feedback(existing, run_id, args, actor_id)
                return existing
            feedback = ReplyFeedbackRecord(
                id=uuid4(),
                organization_id=organization_id,
                run_id=run_id,
                corrected_category=args.corrected_category,
                comment=args.comment,
                submitted_by=actor_id,
                idempotency_key=key,
                created_at=self.clock.now(),
            )
            await uow.feedback.append(feedback)
            await uow.commit()
            return feedback


@dataclass(frozen=True, slots=True)
class ListReplyFeedback:
    uow_factory: ReplyUnitOfWorkFactory

    async def execute(self, *, organization_id: UUID, run_id: UUID) -> ReplyFeedbackHistory:
        async with self.uow_factory() as uow:
            request = await uow.classification_requests.get_by_run_id(organization_id, run_id)
            if request is None:
                raise PermissionError("reply classification run is unavailable")
            records = await uow.feedback.list_for_run(organization_id, run_id)
            return ReplyFeedbackHistory(records=tuple(records))


async def _resolve_relationships(
    uow: ReplyUnitOfWork,
    *,
    organization_id: UUID,
    account_id: UUID,
    contact_id: UUID | None,
) -> tuple[UUID, UUID | None]:
    account_group = await uow.canonical.resolve_for_write(
        organization_id, DeduplicationRecordType.ACCOUNT, account_id
    )
    if account_group is None:
        raise PolicyViolationError("account is unavailable")
    account = await uow.accounts.get(organization_id, account_group.canonical_id)
    if account.organization_id != organization_id:
        raise PolicyViolationError("account is unavailable")
    if contact_id is None:
        return account_group.canonical_id, None

    contact_group = await uow.canonical.resolve_for_write(
        organization_id, DeduplicationRecordType.CONTACT, contact_id
    )
    if contact_group is None:
        raise PolicyViolationError("contact is unavailable")
    contact = await uow.contacts.get(organization_id, contact_group.canonical_id)
    if contact is None or contact.organization_id != organization_id:
        raise PolicyViolationError("contact is unavailable")
    contact_account_group = await uow.canonical.resolve_for_write(
        organization_id, DeduplicationRecordType.ACCOUNT, contact.account_id
    )
    if (
        contact_account_group is None
        or contact_account_group.canonical_id != account_group.canonical_id
    ):
        raise PolicyViolationError("contact does not belong to the reply account")
    return account_group.canonical_id, contact_group.canonical_id


def _idempotency_key(value: str) -> str:
    key = value.strip()
    if not key or len(key) > _MAX_IDEMPOTENCY_KEY_LENGTH:
        raise PolicyViolationError("idempotency key must be between 1 and 128 characters")
    return key


def _assert_same_reply(
    existing: ReplyRecord,
    args: RegisterReplyArgs,
    account_id: UUID,
    contact_id: UUID | None,
    actor_id: UUID,
) -> None:
    candidate = args.to_domain()
    if (
        existing.account_id != account_id
        or existing.contact_id != contact_id
        or existing.submitted_by != actor_id
        or existing.reply != candidate
    ):
        raise ReplyConflictError("idempotency key conflicts with reply payload")


def _assert_same_feedback(
    existing: ReplyFeedbackRecord, run_id: UUID, args: AppendReplyFeedbackArgs, actor_id: UUID
) -> None:
    if (
        existing.run_id != run_id
        or existing.corrected_category is not args.corrected_category
        or existing.comment != args.comment
        or existing.submitted_by != actor_id
    ):
        raise ReplyConflictError("idempotency key conflicts with reply feedback")


def _reply_result(reply: object, output: ReplyClassificationOutput) -> ReplyResultDTO:
    """Convert strict schema output into domain policy without leaking provider data."""
    from revops.domain.values.reply import ReplyText

    if not isinstance(reply, ReplyText):
        raise TypeError("reply must be an authorized ReplyText")
    classification = ReplyClassification(
        category=output.category,
        confidence=output.confidence,
        language=output.language,
        evidence=tuple(
            ReplyEvidence(item.start_offset, item.end_offset) for item in output.evidence
        ),
        ambiguous=output.ambiguous,
    )
    outcome = evaluate_reply_classification(reply, classification)
    valid_evidence = tuple(
        ReplyEvidenceDTO(start_offset=item.start_offset, end_offset=item.end_offset)
        for item in classification.evidence
        if item.is_valid_for(reply)
    )
    return ReplyResultDTO(
        category=outcome.category,
        status=outcome.status,
        recommended_action=outcome.recommended_action,
        confidence=classification.confidence,
        language=classification.language,
        evidence=valid_evidence,
        limitations=output.limitations,
        review_reasons=outcome.review_reasons,
    )
