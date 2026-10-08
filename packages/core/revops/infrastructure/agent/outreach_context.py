"""Composition for the read-only CRM and knowledge context used by outreach."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from types import TracebackType
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from revops.application.context.builder import ContextBuilder
from revops.application.dto import KnowledgeRetrievalContext, RetrieveKnowledgeArgs
from revops.application.ports import EmbeddingProvider, OutreachContextProvider, TrustedRunContext
from revops.application.use_cases.retrieve_knowledge import RetrieveKnowledge
from revops.infrastructure.persistence.deduplication_repositories import SqlAlchemyCanonicalResolver
from revops.infrastructure.persistence.knowledge_repositories import (
    SqlAlchemyKnowledgeRetrievalRepository,
)
from revops.infrastructure.persistence.repositories import (
    SqlAlchemyAccountRepository,
    SqlAlchemyContactRepository,
    SqlAlchemyTouchpointRepository,
)


class OutreachReadScope(Protocol):
    accounts: SqlAlchemyAccountRepository
    contacts: SqlAlchemyContactRepository
    touchpoints: SqlAlchemyTouchpointRepository

    async def __aenter__(self) -> OutreachReadScope: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None: ...


@dataclass(frozen=True, slots=True)
class SqlAlchemyOutreachReadScope:
    session: AsyncSession
    accounts: SqlAlchemyAccountRepository = field(init=False)
    contacts: SqlAlchemyContactRepository = field(init=False)
    touchpoints: SqlAlchemyTouchpointRepository = field(init=False)

    def __post_init__(self) -> None:
        canonical = SqlAlchemyCanonicalResolver(self.session)
        object.__setattr__(self, "accounts", SqlAlchemyAccountRepository(self.session, canonical))
        object.__setattr__(self, "contacts", SqlAlchemyContactRepository(self.session))
        object.__setattr__(self, "touchpoints", SqlAlchemyTouchpointRepository(self.session))

    async def __aenter__(self) -> SqlAlchemyOutreachReadScope:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None:
        if exc_type is not None:
            await self.session.rollback()
        return None


def outreach_read_scope_factory(
    session_factory: async_sessionmaker[AsyncSession],
) -> Callable[[], SqlAlchemyOutreachReadScope]:
    return lambda: SqlAlchemyOutreachReadScope(session_factory())


@dataclass(frozen=True, slots=True)
class SqlAlchemyOutreachContextProvider(OutreachContextProvider):
    session_factory: async_sessionmaker[AsyncSession]
    embeddings: EmbeddingProvider
    context_budget: int = 2_048

    async def build(
        self,
        *,
        context: TrustedRunContext,
        account_id: UUID,
        contact_id: UUID | None,
        objective: str,
    ) -> dict[str, object]:
        async with self.session_factory() as session:
            canonical = SqlAlchemyCanonicalResolver(session)
            accounts = SqlAlchemyAccountRepository(session, canonical)
            contacts = SqlAlchemyContactRepository(session)
            touchpoints = SqlAlchemyTouchpointRepository(session)
            account = await accounts.get(context.organization_id, account_id)
            contact = (
                await contacts.get(context.organization_id, contact_id) if contact_id else None
            )
            if contact is not None and contact.account_id != account.id:
                raise PermissionError("contact is not related to the authenticated account")
            interactions = await accounts.list_interactions(context.organization_id, account.id)
            opportunities = await accounts.list_open_opportunities(
                context.organization_id, account.id
            )
            touchpoint_rows = await touchpoints.list_for_account(
                context.organization_id, account.id
            )
            crm = ContextBuilder().build(
                account,
                list(interactions),
                list(opportunities),
                token_budget=self.context_budget,
            )
            knowledge = await RetrieveKnowledge(
                SqlAlchemyKnowledgeRetrievalRepository(session), self.embeddings
            ).execute(
                context=KnowledgeRetrievalContext(organization_id=context.organization_id),
                args=RetrieveKnowledgeArgs(
                    query=objective,
                    limit=5,
                    token_budget=self.context_budget,
                ),
            )
            return {
                "crm": {
                    "sections": [{"label": item.label, "text": item.text} for item in crm.sections],
                    "dropped_labels": crm.dropped_labels,
                    "token_count": crm.token_count,
                },
                "contact": (
                    {"full_name": contact.full_name, "title": contact.title}
                    if contact is not None
                    else None
                ),
                "touchpoints": [
                    {"type": item.type, "occurred_at": item.occurred_at.isoformat()}
                    for item in touchpoint_rows[:20]
                ],
                "knowledge": {
                    "text": knowledge.text,
                    "included": [
                        {
                            "document_key": item.provenance.document_key,
                            "version_id": str(item.provenance.document_version_id),
                            "chunk_id": str(item.provenance.chunk_id),
                            "category": item.provenance.category.value,
                        }
                        for item in knowledge.included
                    ],
                    "omitted_count": len(knowledge.omitted),
                },
            }
