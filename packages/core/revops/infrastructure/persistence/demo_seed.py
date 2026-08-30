"""Build and persist the deterministic synthetic tenant used by local demos."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid5

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from revops.infrastructure.persistence.models import (
    Account,
    Contact,
    Interaction,
    Opportunity,
    Organization,
    User,
)

DEMO_NAMESPACE = UUID("4d4f3f43-9f24-4e9e-9a36-4b17a4f1a001")
SEED_EPOCH = datetime(2026, 1, 1, tzinfo=UTC)
DEMO_ORGANIZATION_ID = uuid5(DEMO_NAMESPACE, "organization")
DEMO_USER_ID = uuid5(DEMO_NAMESPACE, "user:rep")


@dataclass(frozen=True, slots=True)
class DemoSeedRows:
    organization: Organization
    user: User
    accounts: tuple[Account, ...]
    contacts: tuple[Contact, ...]
    opportunities: tuple[Opportunity, ...]
    interactions: tuple[Interaction, ...]


def _stable_id(kind: str, index: int) -> UUID:
    return uuid5(DEMO_NAMESPACE, f"{kind}:{index}")


def build_demo_seed() -> DemoSeedRows:
    """Build all synthetic rows without I/O, using stable identities on every run."""
    organization = Organization(
        id=DEMO_ORGANIZATION_ID,
        name="RevOps Demo Organization",
        demo_mode=True,
    )
    user = User(
        id=DEMO_USER_ID,
        organization_id=DEMO_ORGANIZATION_ID,
        email="rep@demo.revops.example",
        role="rep",
    )
    accounts = tuple(
        Account(
            id=_stable_id("account", index),
            organization_id=DEMO_ORGANIZATION_ID,
            company_name=f"Demo Account {index:02d}",
            domain=f"demo-account-{index:02d}.example.com",
            created_at=SEED_EPOCH,
        )
        for index in range(1, 31)
    )
    contacts = tuple(
        Contact(
            id=_stable_id("contact", index),
            organization_id=DEMO_ORGANIZATION_ID,
            account_id=account.id,
            email=f"contact-{index:02d}@demo-account-{index:02d}.example.com",
            full_name=f"Demo Contact {index:02d}",
            title="Revenue Operations Lead",
        )
        for index, account in enumerate(accounts, start=1)
    )
    opportunities = tuple(
        Opportunity(
            id=_stable_id("opportunity", index),
            organization_id=DEMO_ORGANIZATION_ID,
            account_id=account.id,
            stage="negotiation" if index % 5 == 0 else "qualification",
            value=Decimal(10000 + index * 1250),
        )
        for index, account in enumerate(accounts, start=1)
    )
    interactions = tuple(
        Interaction(
            id=_stable_id("interaction", (index - 1) * 2 + offset),
            organization_id=DEMO_ORGANIZATION_ID,
            account_id=account.id,
            channel="email" if offset == 1 else "call",
            occurred_at=SEED_EPOCH + timedelta(days=-(index + offset)),
            summary=f"Synthetic engagement {index:02d}.{offset}",
        )
        for index, account in enumerate(accounts, start=1)
        for offset in (1, 2)
    )
    return DemoSeedRows(organization, user, accounts, contacts, opportunities, interactions)


async def seed_database(session_factory: async_sessionmaker[AsyncSession]) -> DemoSeedRows:
    """Merge the demo tenant into the database and return the rows that were seeded."""
    rows = build_demo_seed()
    async with session_factory() as session:
        # Serialize concurrent invocations so deterministic merges cannot race on the root row.
        await session.execute(text("SELECT pg_advisory_xact_lock(2026083001)"))
        for row in (
            rows.organization,
            rows.user,
            *rows.accounts,
            *rows.contacts,
            *rows.opportunities,
            *rows.interactions,
        ):
            await session.merge(row)
        await session.commit()
    return rows
