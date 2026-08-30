"""`SqlAlchemyUnitOfWork`: one shared `AsyncSession` across accounts/tasks/audit (ADR-0002).

`DecideApproval`'s constructor and call signature do not change - the transaction boundary is
composed by whoever calls the use case, not by the use case itself:

    async with SqlAlchemyUnitOfWork(session) as uow:
        task = await decide_approval.approve(pending, organization_id=..., actor_id=...)
        await uow.commit()

The session itself is created and owned by the caller (the eventual composition root - the API or
the graph); this class only groups the three ports that must commit or roll back together.
"""

from __future__ import annotations

from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession

from revops.infrastructure.persistence.repositories import (
    SqlAlchemyAccountRepository,
    SqlAlchemyAuditTrail,
    SqlAlchemyTaskRepository,
)


class SqlAlchemyUnitOfWork:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.accounts = SqlAlchemyAccountRepository(session)
        self.tasks = SqlAlchemyTaskRepository(session)
        self.audit = SqlAlchemyAuditTrail(session)

    async def __aenter__(self) -> SqlAlchemyUnitOfWork:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if exc_type is not None:
            await self.rollback()

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()
