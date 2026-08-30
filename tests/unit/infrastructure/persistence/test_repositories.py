"""Structural tests for the SqlAlchemy repository adapters and the unit of work - no database.

Each class satisfies its `application.ports` Protocol purely by shape (`isinstance` against a
`runtime_checkable` Protocol), the same convention `tests/unit/application/test_ports.py`
establishes for every fake. Real-database behaviour (round-trips, tenant isolation) is
`tests/integration/test_persistence_repositories.py`'s job (SPEC-001 tasks.md item 4).
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from revops.application.ports import (
    AccountRepository,
    AgentRunRepository,
    ApprovalRepository,
    AuditTrail,
    TaskRepository,
    UnitOfWork,
)
from revops.domain.entities.task import Task, TaskStatus
from revops.infrastructure.persistence.repositories import (
    SqlAlchemyAccountRepository,
    SqlAlchemyAgentRunRepository,
    SqlAlchemyApprovalRepository,
    SqlAlchemyAuditTrail,
    SqlAlchemyTaskRepository,
)
from revops.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
from sqlalchemy.ext.asyncio import AsyncSession


def _mock_session() -> MagicMock:
    """`AsyncSession.add()` is synchronous; `execute`/`flush`/`commit`/`rollback` are async.

    `spec=AsyncSession` makes `MagicMock` mirror that per-method, so a call to the wrong one
    (sync where the real session is async or vice versa) fails loudly here instead of only in
    the real-database integration tests (item 4).
    """
    return MagicMock(spec=AsyncSession)


def test_sql_alchemy_account_repository_satisfies_the_protocol_structurally() -> None:
    assert isinstance(SqlAlchemyAccountRepository(_mock_session()), AccountRepository)


def test_sql_alchemy_account_repository_has_no_write_methods() -> None:
    for forbidden in ("add", "update", "save", "delete"):
        assert not hasattr(SqlAlchemyAccountRepository, forbidden)


def test_sql_alchemy_task_repository_satisfies_the_protocol_structurally() -> None:
    assert isinstance(SqlAlchemyTaskRepository(_mock_session()), TaskRepository)


def test_sql_alchemy_approval_repository_satisfies_the_protocol_structurally() -> None:
    assert isinstance(SqlAlchemyApprovalRepository(_mock_session()), ApprovalRepository)


def test_sql_alchemy_agent_run_repository_satisfies_the_protocol_structurally() -> None:
    assert isinstance(SqlAlchemyAgentRunRepository(_mock_session()), AgentRunRepository)


def test_sql_alchemy_audit_trail_satisfies_the_protocol_structurally() -> None:
    assert isinstance(SqlAlchemyAuditTrail(_mock_session()), AuditTrail)


def test_sql_alchemy_unit_of_work_satisfies_the_protocol_structurally() -> None:
    assert isinstance(SqlAlchemyUnitOfWork(_mock_session()), UnitOfWork)


def test_unit_of_work_shares_one_session_across_all_three_ports() -> None:
    session = _mock_session()
    uow = SqlAlchemyUnitOfWork(session)
    assert uow.accounts._session is session
    assert uow.tasks._session is session
    assert uow.audit._session is session
    assert uow.approvals._session is session
    assert uow.runs._session is session


async def test_unit_of_work_commit_delegates_to_the_session() -> None:
    session = _mock_session()
    uow = SqlAlchemyUnitOfWork(session)
    await uow.commit()
    session.commit.assert_awaited_once()


async def test_unit_of_work_rollback_delegates_to_the_session() -> None:
    session = _mock_session()
    uow = SqlAlchemyUnitOfWork(session)
    await uow.rollback()
    session.rollback.assert_awaited_once()


async def test_unit_of_work_rolls_back_on_exception_inside_the_context_manager() -> None:
    session = _mock_session()
    uow = SqlAlchemyUnitOfWork(session)
    with pytest.raises(RuntimeError):
        async with uow:
            raise RuntimeError("boom")
    session.rollback.assert_awaited_once()


async def test_unit_of_work_does_not_roll_back_on_clean_exit() -> None:
    session = _mock_session()
    uow = SqlAlchemyUnitOfWork(session)
    async with uow:
        pass
    session.rollback.assert_not_awaited()


async def test_audit_trail_record_writes_the_full_audit_row() -> None:
    session = _mock_session()
    audit = SqlAlchemyAuditTrail(session)
    run_id = uuid4()
    await audit.record(
        action_id=uuid4(),
        run_id=run_id,
        organization_id=uuid4(),
        actor_id=uuid4(),
        action="create_task",
        payload={"title": "call the customer"},
        outcome="approved",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        approved_by=uuid4(),
        executed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    session.add.assert_called_once()
    added_row = session.add.call_args.args[0]
    assert added_row.run_id == run_id
    session.flush.assert_awaited_once()


async def test_task_repository_add_stores_the_task_status_as_its_primitive_value() -> None:
    session = _mock_session()
    tasks = SqlAlchemyTaskRepository(session)
    task = Task(
        id=uuid4(),
        organization_id=uuid4(),
        owner_id=uuid4(),
        account_id=uuid4(),
        title="follow up",
        due_at=datetime(2026, 1, 1, tzinfo=UTC),
        status=TaskStatus.OPEN,
    )
    await tasks.add(task)
    added_row = session.add.call_args.args[0]
    assert added_row.status == "open"
    session.flush.assert_awaited_once()
