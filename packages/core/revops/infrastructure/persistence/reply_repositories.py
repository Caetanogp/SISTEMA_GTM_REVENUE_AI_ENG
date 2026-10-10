"""PostgreSQL repositories for immutable reply registration and correction history."""

from __future__ import annotations

from collections.abc import Sequence
from hashlib import sha256
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from revops.application.ports import (
    ReplyClassificationRequestRecord,
    ReplyFeedbackRecord,
    ReplyRecord,
)
from revops.domain.values.reply import ReplyCategory, ReplyLanguage, ReplyText
from revops.infrastructure.persistence.models import (
    Reply,
    ReplyClassificationRequest,
    ReplyFeedback,
)


def _advisory_key(value: UUID | tuple[UUID, str]) -> int:
    """Map a UUID or tenant-scoped idempotency key to a stable PostgreSQL lock key."""
    if isinstance(value, UUID):
        return int.from_bytes(value.bytes[-8:], byteorder="big", signed=True)
    organization_id, idempotency_key = value
    digest = sha256(f"{organization_id}:{idempotency_key}".encode()).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


async def _lock(session: AsyncSession, value: UUID | tuple[UUID, str]) -> None:
    """Serialize a create-or-replay decision until the surrounding UoW commits or rolls back."""
    await session.execute(select(func.pg_advisory_xact_lock(_advisory_key(value))))


def _to_reply_record(row: Reply) -> ReplyRecord:
    return ReplyRecord(
        id=row.id,
        organization_id=row.organization_id,
        account_id=row.account_id,
        contact_id=row.contact_id,
        submitted_by=row.submitted_by,
        reply=ReplyText(value=row.text, language=ReplyLanguage(row.language)),
        idempotency_key=row.idempotency_key,
        created_at=row.created_at,
    )


def _to_request_record(row: ReplyClassificationRequest) -> ReplyClassificationRequestRecord:
    return ReplyClassificationRequestRecord(
        id=row.id,
        organization_id=row.organization_id,
        reply_id=row.reply_id,
        run_id=row.run_id,
        requested_by=row.requested_by,
        created_at=row.created_at,
    )


def _to_feedback_record(row: ReplyFeedback) -> ReplyFeedbackRecord:
    return ReplyFeedbackRecord(
        id=row.id,
        organization_id=row.organization_id,
        run_id=row.run_id,
        corrected_category=ReplyCategory(row.corrected_category),
        comment=row.comment,
        submitted_by=row.submitted_by,
        idempotency_key=row.idempotency_key,
        created_at=row.created_at,
    )


class SqlAlchemyReplyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, organization_id: UUID, reply_id: UUID) -> ReplyRecord | None:
        row = await self._session.scalar(
            select(Reply).where(Reply.organization_id == organization_id, Reply.id == reply_id)
        )
        return _to_reply_record(row) if row is not None else None

    async def get_by_idempotency_key(
        self, organization_id: UUID, idempotency_key: str
    ) -> ReplyRecord | None:
        await _lock(self._session, (organization_id, idempotency_key))
        row = await self._session.scalar(
            select(Reply).where(
                Reply.organization_id == organization_id,
                Reply.idempotency_key == idempotency_key,
            )
        )
        return _to_reply_record(row) if row is not None else None

    async def add(self, reply: ReplyRecord) -> None:
        self._session.add(
            Reply(
                id=reply.id,
                organization_id=reply.organization_id,
                account_id=reply.account_id,
                contact_id=reply.contact_id,
                submitted_by=reply.submitted_by,
                text=reply.reply.value,
                language=reply.reply.language.value,
                idempotency_key=reply.idempotency_key,
                created_at=reply.created_at,
            )
        )
        await self._session.flush()


class SqlAlchemyReplyClassificationRequestRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_reply_id(
        self, organization_id: UUID, reply_id: UUID
    ) -> ReplyClassificationRequestRecord | None:
        await _lock(self._session, reply_id)
        row = await self._session.scalar(
            select(ReplyClassificationRequest).where(
                ReplyClassificationRequest.organization_id == organization_id,
                ReplyClassificationRequest.reply_id == reply_id,
            )
        )
        return _to_request_record(row) if row is not None else None

    async def get_by_run_id(
        self, organization_id: UUID, run_id: UUID
    ) -> ReplyClassificationRequestRecord | None:
        row = await self._session.scalar(
            select(ReplyClassificationRequest).where(
                ReplyClassificationRequest.organization_id == organization_id,
                ReplyClassificationRequest.run_id == run_id,
            )
        )
        return _to_request_record(row) if row is not None else None

    async def add(self, request: ReplyClassificationRequestRecord) -> None:
        self._session.add(
            ReplyClassificationRequest(
                id=request.id,
                organization_id=request.organization_id,
                reply_id=request.reply_id,
                run_id=request.run_id,
                requested_by=request.requested_by,
                created_at=request.created_at,
            )
        )
        await self._session.flush()


class SqlAlchemyReplyFeedbackRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_idempotency_key(
        self, organization_id: UUID, idempotency_key: str
    ) -> ReplyFeedbackRecord | None:
        await _lock(self._session, (organization_id, idempotency_key))
        row = await self._session.scalar(
            select(ReplyFeedback).where(
                ReplyFeedback.organization_id == organization_id,
                ReplyFeedback.idempotency_key == idempotency_key,
            )
        )
        return _to_feedback_record(row) if row is not None else None

    async def append(self, feedback: ReplyFeedbackRecord) -> None:
        self._session.add(
            ReplyFeedback(
                id=feedback.id,
                organization_id=feedback.organization_id,
                run_id=feedback.run_id,
                corrected_category=feedback.corrected_category.value,
                comment=feedback.comment,
                submitted_by=feedback.submitted_by,
                idempotency_key=feedback.idempotency_key,
                created_at=feedback.created_at,
            )
        )
        await self._session.flush()

    async def list_for_run(
        self, organization_id: UUID, run_id: UUID
    ) -> Sequence[ReplyFeedbackRecord]:
        rows = (
            await self._session.scalars(
                select(ReplyFeedback)
                .where(
                    ReplyFeedback.organization_id == organization_id,
                    ReplyFeedback.run_id == run_id,
                )
                .order_by(ReplyFeedback.created_at, ReplyFeedback.id)
            )
        ).all()
        return tuple(_to_feedback_record(row) for row in rows)
