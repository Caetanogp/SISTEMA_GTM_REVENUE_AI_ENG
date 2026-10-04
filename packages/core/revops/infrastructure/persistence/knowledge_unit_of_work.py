"""SQLAlchemy transaction boundary for knowledge lifecycle operations."""

from __future__ import annotations

from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession

from revops.application.ports import (
    CorpusRevisionRepository,
    KnowledgeCorpusRepository,
    KnowledgeDocumentRepository,
    KnowledgeProcessingEventRepository,
    KnowledgeUnitOfWork,
)
from revops.infrastructure.persistence.knowledge_repositories import (
    SqlAlchemyCorpusRevisionRepository,
    SqlAlchemyKnowledgeCorpusRepository,
    SqlAlchemyKnowledgeDocumentRepository,
    SqlAlchemyKnowledgeProcessingEventRepository,
)


class SqlAlchemyKnowledgeUnitOfWork:
    """Keep document, manifest, activation, and head writes in one session."""

    documents: KnowledgeDocumentRepository
    corpora: KnowledgeCorpusRepository
    revisions: CorpusRevisionRepository
    processing_events: KnowledgeProcessingEventRepository

    def __init__(self, session: AsyncSession, *, close_on_exit: bool = False) -> None:
        self._session = session
        self._close_on_exit = close_on_exit
        self.documents = SqlAlchemyKnowledgeDocumentRepository(session)
        self.corpora = SqlAlchemyKnowledgeCorpusRepository(session)
        self.revisions = SqlAlchemyCorpusRevisionRepository(session)
        self.processing_events = SqlAlchemyKnowledgeProcessingEventRepository(session)

    async def __aenter__(self) -> KnowledgeUnitOfWork:
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
