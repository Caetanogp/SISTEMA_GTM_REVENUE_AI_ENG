"""Shared helpers for the LangGraph restart/resume integration tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

from revops.application.dto import (
    CreateTaskDraft,
    PrioritizationOutput,
    RankedAccount,
)
from revops.application.use_cases.prioritize_accounts import PrioritizeAccounts
from revops.infrastructure.agent.nodes import AgentGraphDependencies, UnitOfWorkScope
from revops.infrastructure.llm.fake import FakeLLMGateway
from revops.infrastructure.persistence.models import (
    Account as AccountModel,
)
from revops.infrastructure.persistence.models import (
    AgentRun as AgentRunModel,
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
    User as UserModel,
)
from revops.infrastructure.persistence.repositories import SqlAlchemyAccountRepository
from revops.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class RuntimeInputs:
    organization_id: UUID
    actor_id: UUID
    request_text: str
    prioritization: PrioritizationOutput


class _FixedClock:
    def now(self) -> datetime:
        return _NOW


async def seed_reference_data(session: AsyncSession, marker: str) -> None:
    organization_id = uuid4()
    actor_id = uuid4()
    account_id = uuid4()
    session.add(
        OrganizationModel(
            id=organization_id,
            name=f"Acme Inc {marker}",
            demo_mode=True,
        )
    )
    await session.flush()
    session.add(
        UserModel(
            id=actor_id,
            organization_id=organization_id,
            email=f"{marker}@example.com",
            role="rep",
        )
    )
    await session.flush()
    session.add(
        AccountModel(
            id=account_id,
            organization_id=organization_id,
            company_name="Acme Inc",
            domain="acme.com",
            created_at=_NOW,
        )
    )
    session.add(
        InteractionModel(
            id=uuid4(),
            organization_id=organization_id,
            account_id=account_id,
            channel="email",
            occurred_at=_NOW - timedelta(days=1),
            summary="follow-up",
        )
    )
    session.add(
        OpportunityModel(
            id=uuid4(),
            organization_id=organization_id,
            account_id=account_id,
            stage="negotiation",
            value=Decimal("120000.00"),
        )
    )
    session.add(
        AgentRunModel(
            id=UUID(marker),
            organization_id=organization_id,
            requested_by=actor_id,
            request_text="prioritize",
            graph_version="account-prioritization.v1",
            prompt_version="prioritize_accounts.v1",
            model_config_json={},
            status="started",
            started_at=_NOW,
        )
    )
    await session.commit()


async def load_runtime_inputs(session: AsyncSession, marker: str) -> RuntimeInputs:
    row = (
        await session.execute(
            select(UserModel.organization_id, UserModel.id).where(
                UserModel.email == f"{marker}@example.com"
            )
        )
    ).first()
    if row is None:
        raise RuntimeError("seed data missing user")
    organization_id, actor_id = row

    account_repo = SqlAlchemyAccountRepository(session)
    candidates = await PrioritizeAccounts(
        accounts=account_repo,
        clock=_FixedClock(),
    ).execute(organization_id)
    candidate = candidates[0]
    prioritization = PrioritizationOutput(
        accounts=[
            RankedAccount(
                account_id=candidate.account_id,
                score=candidate.score,
                tier=candidate.tier,
                evidence=candidate.evidence,
                reasons=["recent engagement"],
            )
        ],
        task=CreateTaskDraft(
            account_id=candidate.account_id,
            title=f"Follow up with {candidate.company_name}",
            due_at=_NOW + timedelta(days=7),
        ),
    )
    return RuntimeInputs(
        organization_id=organization_id,
        actor_id=actor_id,
        request_text="prioritize",
        prioritization=prioritization,
    )


@asynccontextmanager
async def uow_factory(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[SqlAlchemyUnitOfWork]:
    async with session_factory() as session:
        yield SqlAlchemyUnitOfWork(session)


def make_session_factory(dsn: str) -> async_sessionmaker[AsyncSession]:
    async_dsn = (
        dsn if "+psycopg" in dsn else dsn.replace("postgresql://", "postgresql+psycopg://", 1)
    )
    engine = create_async_engine(async_dsn)
    return async_sessionmaker(engine, expire_on_commit=False)


def make_gateway(prioritization: PrioritizationOutput) -> FakeLLMGateway:
    return FakeLLMGateway(responses=[prioritization])


def make_dependencies(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    prioritization: PrioritizationOutput,
) -> AgentGraphDependencies:
    return AgentGraphDependencies(
        uow_factory=lambda: cast(UnitOfWorkScope, uow_factory(session_factory)),
        llm_gateway=make_gateway(prioritization),
        clock=_FixedClock(),
        graph_version="account-prioritization.v1",
        prompt_version="prioritize_accounts.v1",
    )
