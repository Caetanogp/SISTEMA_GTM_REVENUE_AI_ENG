"""PostgreSQL evidence for immutable reply persistence and concurrent replay safety."""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from revops.application.dto import AppendReplyFeedbackArgs, RegisterReplyArgs, ReplyRunConfig
from revops.application.use_cases.reply import (
    AppendReplyFeedback,
    RegisterReply,
    ReserveReplyClassification,
)
from revops.domain.values.reply import ReplyCategory, ReplyLanguage
from revops.infrastructure.persistence.models import (
    Account,
    AgentRun,
    AgentRunEvent,
    Contact,
    Organization,
    Reply,
    ReplyClassificationRequest,
    ReplyFeedback,
    User,
)
from revops.infrastructure.persistence.unit_of_work import SqlAlchemyReplyUnitOfWork
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

_NOW = datetime(2026, 10, 10, tzinfo=UTC)


class _Clock:
    def now(self) -> datetime:
        return _NOW


@pytest.fixture(scope="session")
def event_loop_policy() -> asyncio.AbstractEventLoopPolicy:
    if sys.platform == "win32":
        return asyncio.WindowsSelectorEventLoopPolicy()
    return asyncio.get_event_loop_policy()


async def _seed_reply_subjects(
    session: AsyncSession,
) -> tuple[UUID, UUID, UUID, UUID]:
    organization_id, actor_id, account_id, contact_id = (uuid4() for _ in range(4))
    session.add_all(
        [
            Organization(id=organization_id, name="Reply persistence", demo_mode=True),
            User(
                id=actor_id,
                organization_id=organization_id,
                email=f"{actor_id}@example.test",
                role="admin",
            ),
            Account(
                id=account_id,
                organization_id=organization_id,
                company_name="Reply Co",
                domain=f"{account_id}.example.test",
                created_at=_NOW,
            ),
            Contact(
                id=contact_id,
                organization_id=organization_id,
                account_id=account_id,
                email=f"{contact_id}@example.test",
                full_name="Reply Contact",
                title="Operator",
            ),
        ]
    )
    await session.commit()
    return organization_id, actor_id, account_id, contact_id


async def _register(
    sessions: async_sessionmaker[AsyncSession],
    organization_id: UUID,
    actor_id: UUID,
    account_id: UUID,
    contact_id: UUID,
) -> UUID:
    async with sessions() as session:
        result = await RegisterReply(lambda: SqlAlchemyReplyUnitOfWork(session), _Clock()).execute(
            organization_id=organization_id,
            actor_id=actor_id,
            args=RegisterReplyArgs(
                account_id=account_id,
                contact_id=contact_id,
                text="Please send details.",
                language=ReplyLanguage.ENGLISH,
            ),
            idempotency_key="reply-key",
        )
        return result.reply.id


async def _cleanup_reply_subjects(
    sessions: async_sessionmaker[AsyncSession], organization_id: UUID
) -> None:
    async with sessions() as session:
        await session.execute(
            delete(ReplyFeedback).where(ReplyFeedback.organization_id == organization_id)
        )
        await session.execute(
            delete(ReplyClassificationRequest).where(
                ReplyClassificationRequest.organization_id == organization_id
            )
        )
        await session.execute(
            delete(AgentRunEvent).where(AgentRunEvent.organization_id == organization_id)
        )
        await session.execute(delete(AgentRun).where(AgentRun.organization_id == organization_id))
        await session.execute(delete(Reply).where(Reply.organization_id == organization_id))
        await session.execute(delete(Contact).where(Contact.organization_id == organization_id))
        await session.execute(delete(Account).where(Account.organization_id == organization_id))
        await session.execute(delete(User).where(User.organization_id == organization_id))
        await session.execute(delete(Organization).where(Organization.id == organization_id))
        await session.commit()


async def test_reply_registration_reservation_and_feedback_replay_are_atomic(
    database_url: str,
) -> None:
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        organization_id, actor_id, account_id, contact_id = await _seed_reply_subjects(session)
    try:
        first_reply_id, second_reply_id = await asyncio.gather(
            _register(sessions, organization_id, actor_id, account_id, contact_id),
            _register(sessions, organization_id, actor_id, account_id, contact_id),
        )
        assert first_reply_id == second_reply_id

        async def reserve() -> UUID:
            async with sessions() as session:
                result = await ReserveReplyClassification(
                    lambda: SqlAlchemyReplyUnitOfWork(session), _Clock()
                ).execute(
                    organization_id=organization_id,
                    actor_id=actor_id,
                    reply_id=first_reply_id,
                    run_config=ReplyRunConfig(
                        graph_version="reply-intelligence.v1",
                        prompt_version="classify_reply.v1",
                    ),
                )
                return result.request.run_id

        first_run_id, second_run_id = await asyncio.gather(reserve(), reserve())
        assert first_run_id == second_run_id

        async def append_feedback() -> UUID:
            async with sessions() as session:
                feedback = await AppendReplyFeedback(
                    lambda: SqlAlchemyReplyUnitOfWork(session), _Clock()
                ).execute(
                    organization_id=organization_id,
                    actor_id=actor_id,
                    run_id=first_run_id,
                    args=AppendReplyFeedbackArgs(
                        corrected_category=ReplyCategory.INTERESTED,
                        comment="Confirmed by operator",
                    ),
                    idempotency_key="feedback-key",
                )
                return feedback.id

        first_feedback_id, second_feedback_id = await asyncio.gather(
            append_feedback(), append_feedback()
        )
        assert first_feedback_id == second_feedback_id

        async with sessions() as session:
            for model, expected in (
                (Reply, 1),
                (ReplyClassificationRequest, 1),
                (AgentRun, 1),
                (AgentRunEvent, 1),
                (ReplyFeedback, 1),
            ):
                count = await session.scalar(
                    select(func.count())
                    .select_from(model)
                    .where(model.organization_id == organization_id)
                )
                assert count == expected
    finally:
        await _cleanup_reply_subjects(sessions, organization_id)
        await engine.dispose()
