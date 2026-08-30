"""Repositories and `SqlAlchemyAuditTrail` against the real docker-compose Postgres.

SPEC-001 tasks.md item 4. Reuses `tests/integration/conftest.py`'s `database_url` fixture - no
second conftest. Each test runs inside its own connection-bound transaction with a SAVEPOINT
(`join_transaction_mode="create_savepoint"`), rolled back at teardown, so no test leaves rows
behind in the shared dev database and tests never see each other's data.

Covers, per `AUTONOMOUS_QUEUE.md` item 4's done criterion: every repository method round-tripped
against real rows, the three value objects (`CompanyDomain`, `EmailAddress`, `Score`) round-tripped
through the persistence boundary, a `Task`'s transitions persisted (including an illegal one still
raising after a real save/reload), and - explicitly, acceptance criterion 10 - tenant isolation:
a repository call scoped to one organization never returns or mutates another's rows.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from revops.domain.entities.task import Task, TaskStatus
from revops.domain.errors import InvalidTransitionError
from revops.domain.policies.prioritization import prioritize_account
from revops.domain.values.company_domain import CompanyDomain
from revops.domain.values.email import EmailAddress
from revops.infrastructure.persistence.models import Account as AccountModel
from revops.infrastructure.persistence.models import AgentAction as AgentActionModel
from revops.infrastructure.persistence.models import Contact as ContactModel
from revops.infrastructure.persistence.models import Interaction as InteractionModel
from revops.infrastructure.persistence.models import Opportunity as OpportunityModel
from revops.infrastructure.persistence.models import Organization as OrganizationModel
from revops.infrastructure.persistence.models import User as UserModel
from revops.infrastructure.persistence.repositories import (
    SqlAlchemyAccountRepository,
    SqlAlchemyAuditTrail,
    SqlAlchemyTaskRepository,
)
from sqlalchemy import select
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine


@pytest.fixture(scope="session")
def event_loop_policy() -> asyncio.AbstractEventLoopPolicy:
    """psycopg's async driver cannot run on Windows' default `ProactorEventLoop` (ADR-0002,
    `migrations/env.py`'s same fix) - pytest-asyncio needs the same override for this file's
    event loop, not just Alembic's standalone one.
    """
    if sys.platform == "win32":
        return asyncio.WindowsSelectorEventLoopPolicy()
    return asyncio.get_event_loop_policy()


@pytest.fixture
async def session(database_url: str) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(database_url)
    async with engine.connect() as connection:
        await connection.begin()
        async_session = AsyncSession(connection, join_transaction_mode="create_savepoint")
        yield async_session
        await async_session.close()
        await connection.rollback()
    await engine.dispose()


async def _seed_organization(session: AsyncSession, *, name: str = "Acme Inc") -> UUID:
    org_id = uuid4()
    session.add(OrganizationModel(id=org_id, name=name, demo_mode=True))
    await session.flush()
    return org_id


async def _seed_user(session: AsyncSession, organization_id: UUID) -> UUID:
    user_id = uuid4()
    session.add(
        UserModel(
            id=user_id,
            organization_id=organization_id,
            email=f"{user_id}@example.com",
            role="rep",
        )
    )
    await session.flush()
    return user_id


async def _seed_account(
    session: AsyncSession, organization_id: UUID, *, domain: str = "acme.com"
) -> UUID:
    account_id = uuid4()
    session.add(
        AccountModel(
            id=account_id,
            organization_id=organization_id,
            company_name="Acme Inc",
            domain=CompanyDomain(domain).value,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    await session.flush()
    return account_id


class TestAccountRepository:
    async def test_get_round_trips_the_company_domain_value_object(
        self, session: AsyncSession
    ) -> None:
        org_id = await _seed_organization(session)
        account_id = await _seed_account(session, org_id, domain="https://WWW.Example.COM/pricing")

        repo = SqlAlchemyAccountRepository(session)
        account = await repo.get(org_id, account_id)

        assert isinstance(account.domain, CompanyDomain)
        assert str(account.domain) == "example.com"

    async def test_get_raises_when_the_account_does_not_exist(self, session: AsyncSession) -> None:
        org_id = await _seed_organization(session)
        repo = SqlAlchemyAccountRepository(session)

        with pytest.raises(NoResultFound):
            await repo.get(org_id, uuid4())

    async def test_list_for_organization_returns_every_account_in_that_organization(
        self, session: AsyncSession
    ) -> None:
        org_id = await _seed_organization(session)
        first = await _seed_account(session, org_id, domain="acme.com")
        second = await _seed_account(session, org_id, domain="beta.io")

        repo = SqlAlchemyAccountRepository(session)
        accounts = await repo.list_for_organization(org_id)

        assert {a.id for a in accounts} == {first, second}

    async def test_list_interactions_returns_only_the_requested_accounts_interactions(
        self, session: AsyncSession
    ) -> None:
        org_id = await _seed_organization(session)
        account_id = await _seed_account(session, org_id)
        other_account_id = await _seed_account(session, org_id, domain="other.com")

        matching_id = uuid4()
        session.add(
            InteractionModel(
                id=matching_id,
                organization_id=org_id,
                account_id=account_id,
                channel="email",
                occurred_at=datetime(2026, 1, 5, tzinfo=UTC),
                summary="follow-up call scheduled",
            )
        )
        session.add(
            InteractionModel(
                id=uuid4(),
                organization_id=org_id,
                account_id=other_account_id,
                channel="call",
                occurred_at=datetime(2026, 1, 5, tzinfo=UTC),
                summary="unrelated account",
            )
        )
        await session.flush()

        repo = SqlAlchemyAccountRepository(session)
        interactions = await repo.list_interactions(org_id, account_id)

        assert [i.id for i in interactions] == [matching_id]
        assert interactions[0].summary == "follow-up call scheduled"

    async def test_list_open_opportunities_excludes_closed_stages(
        self, session: AsyncSession
    ) -> None:
        org_id = await _seed_organization(session)
        account_id = await _seed_account(session, org_id)

        open_id = uuid4()
        session.add(
            OpportunityModel(
                id=open_id,
                organization_id=org_id,
                account_id=account_id,
                stage="negotiation",
                value=Decimal("50000.00"),
            )
        )
        session.add(
            OpportunityModel(
                id=uuid4(),
                organization_id=org_id,
                account_id=account_id,
                stage="closed_won",
                value=Decimal("10000.00"),
            )
        )
        await session.flush()

        repo = SqlAlchemyAccountRepository(session)
        opportunities = await repo.list_open_opportunities(org_id, account_id)

        assert [o.id for o in opportunities] == [open_id]
        assert opportunities[0].value == Decimal("50000.00")


class TestTaskRepository:
    async def test_add_then_get_round_trips_the_task(self, session: AsyncSession) -> None:
        org_id = await _seed_organization(session)
        owner_id = await _seed_user(session, org_id)
        account_id = await _seed_account(session, org_id)
        task = Task(
            id=uuid4(),
            organization_id=org_id,
            owner_id=owner_id,
            account_id=account_id,
            title="Call the champion",
            due_at=datetime(2026, 2, 1, tzinfo=UTC),
        )

        repo = SqlAlchemyTaskRepository(session)
        await repo.add(task)
        fetched = await repo.get(org_id, task.id)

        assert fetched == task
        assert fetched.status is TaskStatus.OPEN

    async def test_update_persists_a_mark_done_transition(self, session: AsyncSession) -> None:
        org_id = await _seed_organization(session)
        owner_id = await _seed_user(session, org_id)
        account_id = await _seed_account(session, org_id)
        task = Task(
            id=uuid4(),
            organization_id=org_id,
            owner_id=owner_id,
            account_id=account_id,
            title="Send proposal",
            due_at=datetime(2026, 2, 1, tzinfo=UTC),
        )
        repo = SqlAlchemyTaskRepository(session)
        await repo.add(task)

        task.mark_done()
        await repo.update(task)

        reloaded = await repo.get(org_id, task.id)
        assert reloaded.status is TaskStatus.DONE

    async def test_illegal_transition_still_raises_after_a_real_save_reload_cycle(
        self, session: AsyncSession
    ) -> None:
        org_id = await _seed_organization(session)
        owner_id = await _seed_user(session, org_id)
        account_id = await _seed_account(session, org_id)
        task = Task(
            id=uuid4(),
            organization_id=org_id,
            owner_id=owner_id,
            account_id=account_id,
            title="Renew contract",
            due_at=datetime(2026, 2, 1, tzinfo=UTC),
        )
        repo = SqlAlchemyTaskRepository(session)
        await repo.add(task)
        task.mark_done()
        await repo.update(task)

        reloaded = await repo.get(org_id, task.id)
        with pytest.raises(InvalidTransitionError):
            reloaded.cancel()


class TestAuditTrail:
    async def test_record_persists_a_row_with_a_null_run_id(self, session: AsyncSession) -> None:
        org_id = await _seed_organization(session)
        actor_id = await _seed_user(session, org_id)
        audit = SqlAlchemyAuditTrail(session)

        await audit.record(
            organization_id=org_id,
            actor_id=actor_id,
            action="create_task",
            payload={"title": "call the customer"},
            outcome="approved",
            occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        )

        stmt = select(AgentActionModel).where(AgentActionModel.organization_id == org_id)
        row = (await session.execute(stmt)).scalar_one()
        assert row.run_id is None
        assert row.action == "create_task"
        assert row.outcome == "approved"
        assert row.payload == {"title": "call the customer"}


class TestValueObjectRoundTrips:
    async def test_email_address_round_trips_normalized_through_a_contact_row(
        self, session: AsyncSession
    ) -> None:
        org_id = await _seed_organization(session)
        account_id = await _seed_account(session, org_id)
        normalized = EmailAddress("  Jane.Doe@Example.COM  ")

        contact_id = uuid4()
        session.add(
            ContactModel(
                id=contact_id,
                organization_id=org_id,
                account_id=account_id,
                email=normalized.value,
                full_name="Jane Doe",
            )
        )
        await session.flush()

        stmt = select(ContactModel).where(ContactModel.id == contact_id)
        row = (await session.execute(stmt)).scalar_one()
        reidrated = EmailAddress(row.email)

        assert reidrated == normalized
        assert reidrated.value == "jane.doe@example.com"

    async def test_score_computes_correctly_from_persisted_interactions_and_opportunities(
        self, session: AsyncSession
    ) -> None:
        org_id = await _seed_organization(session)
        account_id = await _seed_account(session, org_id)
        now = datetime(2026, 3, 1, tzinfo=UTC)

        session.add(
            InteractionModel(
                id=uuid4(),
                organization_id=org_id,
                account_id=account_id,
                channel="call",
                occurred_at=now - timedelta(days=1),
                summary="strong interest",
            )
        )
        session.add(
            OpportunityModel(
                id=uuid4(),
                organization_id=org_id,
                account_id=account_id,
                stage="negotiation",
                value=Decimal("120000.00"),
            )
        )
        await session.flush()

        repo = SqlAlchemyAccountRepository(session)
        interactions = list(await repo.list_interactions(org_id, account_id))
        opportunities = list(await repo.list_open_opportunities(org_id, account_id))

        score, evidence = prioritize_account(interactions, opportunities, now)

        assert 0 <= score.value <= 100
        assert score.tier.value == "hot"
        assert len(evidence) == 4


class TestTenantIsolation:
    """Acceptance criterion 10: a repository call scoped to one org never touches another's rows."""

    async def test_repository_calls_never_return_or_mutate_another_organizations_rows(
        self, session: AsyncSession
    ) -> None:
        org_a = await _seed_organization(session, name="Org A")
        org_b = await _seed_organization(session, name="Org B")
        owner_a = await _seed_user(session, org_a)
        account_a = await _seed_account(session, org_a, domain="org-a.com")
        account_b = await _seed_account(session, org_b, domain="org-b.com")

        accounts = SqlAlchemyAccountRepository(session)
        tasks = SqlAlchemyTaskRepository(session)

        # list_for_organization never crosses the boundary.
        org_a_accounts = await accounts.list_for_organization(org_a)
        assert account_b not in {a.id for a in org_a_accounts}

        # get() scoped to org_a cannot fetch org_b's account, even by its real id.
        with pytest.raises(NoResultFound):
            await accounts.get(org_a, account_b)

        # A task that genuinely belongs to org_a...
        task = Task(
            id=uuid4(),
            organization_id=org_a,
            owner_id=owner_a,
            account_id=account_a,
            title="Org A only",
            due_at=datetime(2026, 2, 1, tzinfo=UTC),
        )
        await tasks.add(task)

        # ...cannot be read back scoped to org_b...
        with pytest.raises(NoResultFound):
            await tasks.get(org_b, task.id)

        # ...and cannot be mutated by an update() call scoped to org_b either.
        mutated = Task(
            id=task.id,
            organization_id=org_b,
            owner_id=owner_a,
            account_id=account_a,
            title="hijacked",
            due_at=task.due_at,
        )
        with pytest.raises(NoResultFound):
            await tasks.update(mutated)

        # The original row is untouched.
        untouched = await tasks.get(org_a, task.id)
        assert untouched.title == "Org A only"
