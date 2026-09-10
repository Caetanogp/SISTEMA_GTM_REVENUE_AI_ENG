"""SQLAlchemy transaction boundary dedicated to ingestion use cases."""

from __future__ import annotations

from types import TracebackType
from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession

from revops.application.ports import (
    AccountEnrichmentRepository,
    CanonicalResolver,
    IngestionAccountRepository,
    IngestionContactRepository,
    IngestionItemRepository,
    IngestionJobRepository,
)
from revops.infrastructure.persistence.deduplication_repositories import SqlAlchemyCanonicalResolver
from revops.infrastructure.persistence.ingestion_repositories import (
    SqlAlchemyAccountEnrichmentRepository,
    SqlAlchemyIngestionAccountRepository,
    SqlAlchemyIngestionContactRepository,
    SqlAlchemyIngestionItemRepository,
    SqlAlchemyIngestionJobRepository,
)


class SqlAlchemyIngestionUnitOfWork:
    jobs: IngestionJobRepository
    items: IngestionItemRepository
    accounts: IngestionAccountRepository
    contacts: IngestionContactRepository
    enrichments: AccountEnrichmentRepository

    def __init__(self, session: AsyncSession, *, close_on_exit: bool = False) -> None:
        self._session = session
        self._close_on_exit = close_on_exit
        self.jobs = SqlAlchemyIngestionJobRepository(session)
        self.items = SqlAlchemyIngestionItemRepository(session)
        self.accounts = SqlAlchemyIngestionAccountRepository(session)
        self.contacts = SqlAlchemyIngestionContactRepository(session)
        self.enrichments = SqlAlchemyAccountEnrichmentRepository(session)
        self.canonical: CanonicalResolver | None = cast(
            CanonicalResolver, SqlAlchemyCanonicalResolver(session)
        )

    async def __aenter__(self) -> SqlAlchemyIngestionUnitOfWork:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if exc_type is not None:
            await self.rollback()
        if self._close_on_exit:
            await self._session.close()

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()
