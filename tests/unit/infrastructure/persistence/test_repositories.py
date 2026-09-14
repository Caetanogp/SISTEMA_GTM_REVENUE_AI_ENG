"""Structural tests for the SqlAlchemy repository adapters and the unit of work - no database.

Each class satisfies its `application.ports` Protocol purely by shape (`isinstance` against a
`runtime_checkable` Protocol), the same convention `tests/unit/application/test_ports.py`
establishes for every fake. Real-database behaviour (round-trips, tenant isolation) is
`tests/integration/test_persistence_repositories.py`'s job (SPEC-001 tasks.md item 4).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from revops.application.ports import (
    AccountRepository,
    AgentRunRepository,
    ApprovalRepository,
    AuditTrail,
    CampaignRepository,
    ContactRepository,
    DeduplicationUnitOfWork,
    TaskRepository,
    TouchpointRepository,
    UnitOfWork,
)
from revops.domain.entities.campaign import Campaign
from revops.domain.entities.task import Task, TaskStatus
from revops.domain.entities.touchpoint import Touchpoint
from revops.infrastructure.persistence.deduplication_repositories import _event_record_type
from revops.infrastructure.persistence.models import DeduplicationEvent
from revops.infrastructure.persistence.repositories import (
    SqlAlchemyAccountRepository,
    SqlAlchemyAgentRunRepository,
    SqlAlchemyApprovalRepository,
    SqlAlchemyAuditTrail,
    SqlAlchemyCampaignRepository,
    SqlAlchemyContactRepository,
    SqlAlchemyTaskRepository,
    SqlAlchemyTouchpointRepository,
)
from revops.infrastructure.persistence.unit_of_work import (
    SqlAlchemyDeduplicationUnitOfWork,
    SqlAlchemyUnitOfWork,
)
from sqlalchemy.ext.asyncio import AsyncSession


def _mock_session() -> MagicMock:
    """`AsyncSession.add()` is synchronous; `execute`/`flush`/`commit`/`rollback` are async.

    `spec=AsyncSession` makes `MagicMock` mirror that per-method, so a call to the wrong one
    (sync where the real session is async or vice versa) fails loudly here instead of only in
    the real-database integration tests (item 4).
    """
    return MagicMock(spec=AsyncSession)


def _deduplication_event(
    *,
    account_candidate: bool = False,
    contact_candidate: bool = False,
    payload_type: str | None = None,
    related_event_id: UUID | None = None,
) -> DeduplicationEvent:
    candidate_id = uuid4()
    payload = {"record_type": payload_type} if payload_type is not None else {}
    return DeduplicationEvent(
        id=uuid4(),
        organization_id=uuid4(),
        idempotency_key="event",
        account_candidate_id=candidate_id if account_candidate else None,
        contact_candidate_id=candidate_id if contact_candidate else None,
        related_event_id=related_event_id,
        action="revert",
        actor_id=uuid4(),
        payload=payload,
        occurred_at=datetime.now(UTC),
    )


@pytest.mark.parametrize(
    ("event", "related_types", "expected"),
    [
        (_deduplication_event(account_candidate=True), {}, "account"),
        (_deduplication_event(contact_candidate=True), {}, "contact"),
        (_deduplication_event(payload_type="account"), {}, "account"),
    ],
)
def test_deduplication_event_type_uses_typed_link_or_payload(
    event: DeduplicationEvent, related_types: dict[UUID, str], expected: str
) -> None:
    assert _event_record_type(event, related_types) == expected


def test_deduplication_revert_type_falls_back_to_related_merge() -> None:
    merge_event_id = uuid4()
    event = _deduplication_event(related_event_id=merge_event_id)

    assert _event_record_type(event, {merge_event_id: "account"}) == "account"


def test_deduplication_event_type_fails_closed_when_unavailable() -> None:
    with pytest.raises(ValueError, match="record type is unavailable"):
        _event_record_type(_deduplication_event(), {})


def test_sql_alchemy_account_repository_satisfies_the_protocol_structurally() -> None:
    assert isinstance(SqlAlchemyAccountRepository(_mock_session()), AccountRepository)


def test_sql_alchemy_account_repository_has_no_write_methods() -> None:
    for forbidden in ("add", "update", "save", "delete"):
        assert not hasattr(SqlAlchemyAccountRepository, forbidden)


def test_sql_alchemy_task_repository_satisfies_the_protocol_structurally() -> None:
    assert isinstance(SqlAlchemyTaskRepository(_mock_session()), TaskRepository)


def test_attribution_repositories_satisfy_their_protocols_structurally() -> None:
    session = _mock_session()
    assert isinstance(SqlAlchemyCampaignRepository(session), CampaignRepository)
    assert isinstance(SqlAlchemyContactRepository(session), ContactRepository)
    assert isinstance(SqlAlchemyTouchpointRepository(session), TouchpointRepository)


def test_touchpoint_repository_has_no_history_mutation_operations() -> None:
    for forbidden in ("update", "delete", "remove"):
        assert not hasattr(SqlAlchemyTouchpointRepository, forbidden)


def test_sql_alchemy_approval_repository_satisfies_the_protocol_structurally() -> None:
    assert isinstance(SqlAlchemyApprovalRepository(_mock_session()), ApprovalRepository)


def test_sql_alchemy_agent_run_repository_satisfies_the_protocol_structurally() -> None:
    assert isinstance(SqlAlchemyAgentRunRepository(_mock_session()), AgentRunRepository)


def test_sql_alchemy_audit_trail_satisfies_the_protocol_structurally() -> None:
    assert isinstance(SqlAlchemyAuditTrail(_mock_session()), AuditTrail)


def test_sql_alchemy_unit_of_work_satisfies_the_protocol_structurally() -> None:
    assert isinstance(SqlAlchemyUnitOfWork(_mock_session()), UnitOfWork)


def test_sql_alchemy_deduplication_unit_of_work_satisfies_the_protocol_structurally() -> None:
    assert isinstance(SqlAlchemyDeduplicationUnitOfWork(_mock_session()), DeduplicationUnitOfWork)


def test_deduplication_unit_of_work_shares_one_session_across_all_ports() -> None:
    session = _mock_session()
    uow = SqlAlchemyDeduplicationUnitOfWork(session)
    assert uow.scans._session is session
    assert uow.candidates._session is session
    assert uow.aliases._session is session
    assert uow.events._session is session
    assert cast(Any, uow.resolver)._session is session


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


async def test_campaign_repository_add_stores_a_tenant_scoped_campaign() -> None:
    session = _mock_session()
    campaigns = SqlAlchemyCampaignRepository(session)
    organization_id = uuid4()
    campaign = Campaign(
        id=uuid4(),
        organization_id=organization_id,
        name="September webinar",
        source="paid-search",
        channel="search",
        metadata={"utm_campaign": "september-webinar"},
        created_at=datetime(2026, 9, 13, tzinfo=UTC),
        updated_at=datetime(2026, 9, 13, tzinfo=UTC),
    )

    await campaigns.add(campaign)

    added_row = session.add.call_args.args[0]
    assert added_row.organization_id == organization_id
    assert added_row.metadata_ == {"utm_campaign": "september-webinar"}
    session.flush.assert_awaited_once()


async def test_attribution_repository_queries_always_filter_by_tenant() -> None:
    session = _mock_session()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    result.scalars.return_value.all.return_value = []
    session.execute.return_value = result
    organization_id, record_id, account_id = uuid4(), uuid4(), uuid4()

    assert await SqlAlchemyCampaignRepository(session).get(organization_id, record_id) is None
    assert await SqlAlchemyContactRepository(session).get(organization_id, record_id) is None
    assert await SqlAlchemyTouchpointRepository(session).get(organization_id, record_id) is None
    assert (
        await SqlAlchemyTouchpointRepository(session).list_for_account(organization_id, account_id)
        == []
    )

    statements = [str(call.args[0]) for call in session.execute.call_args_list]
    assert all("organization_id" in statement for statement in statements)
    assert "campaigns.organization_id" in statements[0]
    assert "contacts.organization_id" in statements[1]
    assert "touchpoints.organization_id" in statements[2]
    assert "touchpoints.account_id" in statements[3]


async def test_touchpoint_repository_add_stores_only_the_append_only_event() -> None:
    session = _mock_session()
    touchpoints = SqlAlchemyTouchpointRepository(session)
    organization_id, account_id, contact_id, campaign_id = (uuid4() for _ in range(4))
    touchpoint = Touchpoint(
        id=uuid4(),
        organization_id=organization_id,
        account_id=account_id,
        contact_id=contact_id,
        campaign_id=campaign_id,
        type="form_submission",
        metadata={"form": "demo-request"},
        occurred_at=datetime(2026, 9, 13, tzinfo=UTC),
        created_at=datetime(2026, 9, 13, tzinfo=UTC),
    )

    await touchpoints.add(touchpoint)

    added_row = session.add.call_args.args[0]
    assert added_row.organization_id == organization_id
    assert added_row.account_id == account_id
    assert added_row.contact_id == contact_id
    assert added_row.campaign_id == campaign_id
    assert added_row.metadata_ == {"form": "demo-request"}
    session.flush.assert_awaited_once()
