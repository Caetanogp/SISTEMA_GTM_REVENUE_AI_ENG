"""Real PostgreSQL coverage for SPEC-005 attribution relationships and lifecycle."""

from __future__ import annotations

import asyncio
import platform
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from revops.domain.entities.campaign import Campaign
from revops.domain.entities.opportunity import OpportunityStatus
from revops.domain.entities.touchpoint import Touchpoint
from revops.infrastructure.persistence.models import (
    Account as AccountModel,
)
from revops.infrastructure.persistence.models import (
    Contact as ContactModel,
)
from revops.infrastructure.persistence.models import (
    Interaction as InteractionModel,
)
from revops.infrastructure.persistence.models import (
    Opportunity as OpportunityModel,
)
from revops.infrastructure.persistence.models import (
    Organization as OrganizationModel,
)
from revops.infrastructure.persistence.models import (
    Touchpoint as TouchpointModel,
)
from revops.infrastructure.persistence.repositories import (
    SqlAlchemyAccountRepository,
    SqlAlchemyCampaignRepository,
    SqlAlchemyTouchpointRepository,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from tests.integration.event_loop_policy import windows_selector_event_loop_policy


@pytest.fixture(scope="session")
def event_loop_policy() -> asyncio.AbstractEventLoopPolicy:
    """Use the selector loop required by psycopg on Windows."""
    if platform.system() == "Windows":
        return windows_selector_event_loop_policy()
    return asyncio.get_event_loop_policy()


@pytest.fixture
async def session(database_url: str) -> AsyncIterator[AsyncSession]:
    """Isolate every behavior scenario in a rolled-back database transaction."""
    engine = create_async_engine(database_url)
    async with engine.connect() as connection:
        await connection.begin()
        async_session = AsyncSession(connection, join_transaction_mode="create_savepoint")
        yield async_session
        await async_session.close()
        await connection.rollback()
    await engine.dispose()


async def _seed_organization(session: AsyncSession, name: str) -> UUID:
    organization_id = uuid4()
    session.add(OrganizationModel(id=organization_id, name=name, demo_mode=True))
    await session.flush()
    return organization_id


async def _seed_account(session: AsyncSession, organization_id: UUID, domain: str) -> UUID:
    account_id = uuid4()
    session.add(
        AccountModel(
            id=account_id,
            organization_id=organization_id,
            company_name=domain,
            domain=domain,
            created_at=datetime(2026, 9, 13, tzinfo=UTC),
        )
    )
    await session.flush()
    return account_id


async def _seed_contact(session: AsyncSession, organization_id: UUID, account_id: UUID) -> UUID:
    contact_id = uuid4()
    session.add(
        ContactModel(
            id=contact_id,
            organization_id=organization_id,
            account_id=account_id,
            email=f"{contact_id}@example.com",
            full_name="Ada Lovelace",
        )
    )
    await session.flush()
    return contact_id


class TestAttributionRelationships:
    async def test_relationships_round_trip_and_are_tenant_scoped(
        self, session: AsyncSession
    ) -> None:
        org_a = await _seed_organization(session, "Org A")
        org_b = await _seed_organization(session, "Org B")
        account_a = await _seed_account(session, org_a, "org-a.example")
        contact_a = await _seed_contact(session, org_a, account_a)
        occurred_at = datetime(2026, 9, 13, 12, tzinfo=UTC)
        campaign = Campaign(
            id=uuid4(),
            organization_id=org_a,
            name="September webinar",
            source="paid-search",
            channel="search",
            metadata={"utm_campaign": "september-webinar"},
            created_at=occurred_at,
            updated_at=occurred_at,
        )
        campaigns = SqlAlchemyCampaignRepository(session)
        touchpoints = SqlAlchemyTouchpointRepository(session)
        await campaigns.add(campaign)
        touchpoint = Touchpoint(
            id=uuid4(),
            organization_id=org_a,
            account_id=account_a,
            contact_id=contact_a,
            campaign_id=campaign.id,
            type="form_submission",
            metadata={"form": "demo-request"},
            occurred_at=occurred_at,
            created_at=occurred_at,
        )
        await touchpoints.add(touchpoint)

        assert await campaigns.get(org_a, campaign.id) == campaign
        assert await campaigns.get(org_b, campaign.id) is None
        assert await touchpoints.get(org_a, touchpoint.id) == touchpoint
        assert await touchpoints.get(org_b, touchpoint.id) is None
        assert list(await touchpoints.list_for_account(org_a, account_a)) == [touchpoint]
        assert list(await touchpoints.list_for_account(org_b, account_a)) == []

    async def test_database_rejects_cross_tenant_relationships(self, session: AsyncSession) -> None:
        org_a = await _seed_organization(session, "Org A")
        org_b = await _seed_organization(session, "Org B")
        account_a = await _seed_account(session, org_a, "org-a.example")
        account_b = await _seed_account(session, org_b, "org-b.example")
        contact_b = await _seed_contact(session, org_b, account_b)

        session.add(
            TouchpointModel(
                id=uuid4(),
                organization_id=org_a,
                account_id=account_a,
                contact_id=contact_b,
                campaign_id=None,
                type="form_submission",
                metadata_={},
                occurred_at=datetime(2026, 9, 13, tzinfo=UTC),
                created_at=datetime(2026, 9, 13, tzinfo=UTC),
            )
        )
        with pytest.raises(IntegrityError):
            await session.flush()

    async def test_interaction_contact_relationship_round_trips_and_is_tenant_scoped(
        self, session: AsyncSession
    ) -> None:
        org_a = await _seed_organization(session, "Org A")
        org_b = await _seed_organization(session, "Org B")
        account_a = await _seed_account(session, org_a, "org-a.example")
        contact_a = await _seed_contact(session, org_a, account_a)
        interaction_id = uuid4()
        session.add(
            InteractionModel(
                id=interaction_id,
                organization_id=org_a,
                account_id=account_a,
                contact_id=contact_a,
                channel="email",
                summary="Requested a demo",
                content="Please send a calendar link.",
                occurred_at=datetime(2026, 9, 13, tzinfo=UTC),
            )
        )
        await session.flush()

        row = (
            await session.execute(
                select(InteractionModel).where(
                    InteractionModel.organization_id == org_a,
                    InteractionModel.id == interaction_id,
                )
            )
        ).scalar_one()
        assert row.contact_id == contact_a
        assert row.content == "Please send a calendar link."
        assert (
            await session.execute(
                select(InteractionModel).where(
                    InteractionModel.organization_id == org_b,
                    InteractionModel.id == interaction_id,
                )
            )
        ).scalar_one_or_none() is None


class TestOpportunityLifecycle:
    async def test_status_round_trips_and_open_query_excludes_closed_lifecycles(
        self, session: AsyncSession
    ) -> None:
        organization_id = await _seed_organization(session, "Org")
        account_id = await _seed_account(session, organization_id, "org.example")
        open_id, won_id, lost_id = uuid4(), uuid4(), uuid4()
        for opportunity_id, status in (
            (open_id, OpportunityStatus.OPEN),
            (won_id, OpportunityStatus.WON),
            (lost_id, OpportunityStatus.LOST),
        ):
            session.add(
                OpportunityModel(
                    id=opportunity_id,
                    organization_id=organization_id,
                    account_id=account_id,
                    stage="negotiation",
                    value=Decimal("100.00"),
                    status=status.value,
                )
            )
        await session.flush()

        opportunities = await SqlAlchemyAccountRepository(session).list_open_opportunities(
            organization_id, account_id
        )
        assert [(opportunity.id, opportunity.status) for opportunity in opportunities] == [
            (open_id, OpportunityStatus.OPEN)
        ]

    async def test_duplicate_touchpoint_delivery_is_intentionally_append_only(
        self, session: AsyncSession
    ) -> None:
        organization_id = await _seed_organization(session, "Org")
        account_id = await _seed_account(session, organization_id, "org.example")
        touchpoints = SqlAlchemyTouchpointRepository(session)
        occurred_at = datetime(2026, 9, 13, tzinfo=UTC)
        for touchpoint_id in (uuid4(), uuid4()):
            await touchpoints.add(
                Touchpoint(
                    id=touchpoint_id,
                    organization_id=organization_id,
                    account_id=account_id,
                    type="page_view",
                    metadata={"path": "/pricing"},
                    occurred_at=occurred_at,
                    created_at=occurred_at,
                )
            )

        persisted = await touchpoints.list_for_account(organization_id, account_id)
        assert len(persisted) == 2
