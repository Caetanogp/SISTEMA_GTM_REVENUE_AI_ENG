from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from revops.application.dto import CreateTaskDraft, PrioritizationOutput, RankedAccount
from revops.application.use_cases.prioritize_accounts import PrioritizeAccounts
from revops.infrastructure.llm.fake import FakeLLMGateway
from revops.infrastructure.persistence.models import (
    Account as AccountModel,
)
from revops.infrastructure.persistence.models import (
    AgentAction as AgentActionModel,
)
from revops.infrastructure.persistence.models import (
    AgentRun as AgentRunModel,
)
from revops.infrastructure.persistence.models import (
    Approval as ApprovalModel,
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
    Task as TaskModel,
)
from revops.infrastructure.persistence.models import (
    User as UserModel,
)
from revops.infrastructure.persistence.repositories import SqlAlchemyAccountRepository
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from apps.api.auth import create_access_token
from apps.api.main import create_app
from apps.api.settings import ApiSettings

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture(scope="session")
def event_loop_policy() -> asyncio.AbstractEventLoopPolicy:
    policy: asyncio.AbstractEventLoopPolicy = asyncio.get_event_loop_policy()
    if sys.platform == "win32":
        policy = asyncio.WindowsSelectorEventLoopPolicy()
    return policy


class _FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


@asynccontextmanager
async def _session_factory(
    database_url: str,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(database_url)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


async def _seed_demo_data(
    session_factory: async_sessionmaker[AsyncSession],
    marker: str,
) -> tuple[UUID, UUID, PrioritizationOutput]:
    now = datetime.now(UTC)
    async with session_factory() as session:
        organization_id = uuid4()
        actor_id = uuid4()
        account_id = uuid4()
        session.add(
            OrganizationModel(
                id=organization_id,
                name=f"API Demo {marker}",
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
        await session.flush()
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
        await session.commit()

    async with session_factory() as session:
        candidates = await PrioritizeAccounts(
            accounts=SqlAlchemyAccountRepository(session),
            clock=_FixedClock(now),
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
                due_at=now + timedelta(days=7),
            ),
        )
    return organization_id, actor_id, prioritization


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.integration
async def test_agent_run_start_stream_and_approval_flow(
    database_url: str,
) -> None:
    async with _session_factory(database_url) as session_factory:
        org_id, actor_id, prioritization = await _seed_demo_data(session_factory, "happy")
        settings = ApiSettings(
            database_url=database_url,
            jwt_secret="test-secret-test-secret-test-secret-test-secret",
        )
        app = create_app(
            settings=settings,
            llm_gateway=FakeLLMGateway(responses=[prioritization] * 20),
        )
        token = create_access_token(
            subject=actor_id,
            organization_id=org_id,
            email="happy@example.com",
            role="rep",
            settings=settings,
        )

        async with app.router.lifespan_context(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                start = await client.post(
                    "/agent/runs",
                    headers=_headers(token),
                    json={"request_text": "which accounts need attention today?"},
                )
                assert start.status_code == 201, start.text
                started = start.json()
                run_id = UUID(started["agent_run_id"])
                assert started["status"] == "interrupted"
                assert started["interrupt"]["question"] == "approve_edit_reject"

                stream = await client.get(
                    f"/agent/runs/{run_id}/stream",
                    headers=_headers(token),
                )
                assert stream.status_code == 200, stream.text
                assert stream.headers["content-type"].startswith("text/event-stream")
                assert "event: started" in stream.text
                assert "event: interrupted" in stream.text
                assert "approve_edit_reject" in stream.text

                approve = await client.post(
                    f"/agent/runs/{run_id}/approve",
                    headers=_headers(token),
                    json={"decision": "approve"},
                )
                assert approve.status_code == 200, approve.text
                approved = approve.json()
                assert approved["status"] == "completed"
                assert approved["task"]["title"].startswith("Follow up with")

                runs = await client.get("/agent/runs", headers=_headers(token))
                assert runs.status_code == 200, runs.text
                assert runs.json()[0]["latest_event_type"] == "completed"

        async with session_factory() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(AgentRunModel)
                    .where(AgentRunModel.organization_id == org_id)
                )
                == 1
            )
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(AgentActionModel)
                    .where(AgentActionModel.organization_id == org_id)
                )
                == 1
            )
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(ApprovalModel)
                    .where(ApprovalModel.organization_id == org_id)
                )
                == 1
            )
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(TaskModel)
                    .where(TaskModel.organization_id == org_id)
                )
                == 1
            )


@pytest.mark.integration
async def test_agent_run_endpoints_reject_missing_auth(database_url: str) -> None:
    async with _session_factory(database_url) as session_factory:
        _org_id, _actor_id, prioritization = await _seed_demo_data(session_factory, "missing-auth")
        settings = ApiSettings(
            database_url=database_url,
            jwt_secret="test-secret-test-secret-test-secret-test-secret",
        )
        app = create_app(
            settings=settings,
            llm_gateway=FakeLLMGateway(responses=[prioritization] * 20),
        )

        async with app.router.lifespan_context(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/agent/runs",
                    json={"request_text": "which accounts need attention today?"},
                )
                assert response.status_code == 401


@pytest.mark.integration
async def test_agent_run_endpoints_reject_cross_org_access(database_url: str) -> None:
    async with _session_factory(database_url) as session_factory:
        org_id, actor_id, prioritization = await _seed_demo_data(session_factory, "cross-org")
        settings = ApiSettings(
            database_url=database_url,
            jwt_secret="test-secret-test-secret-test-secret-test-secret",
        )
        app = create_app(
            settings=settings,
            llm_gateway=FakeLLMGateway(responses=[prioritization] * 20),
        )
        token = create_access_token(
            subject=actor_id,
            organization_id=org_id,
            email="cross-org@example.com",
            role="rep",
            settings=settings,
        )
        other_token = create_access_token(
            subject=uuid4(),
            organization_id=uuid4(),
            email="other@example.com",
            role="rep",
            settings=settings,
        )

        async with app.router.lifespan_context(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                start = await client.post(
                    "/agent/runs",
                    headers=_headers(token),
                    json={"request_text": "which accounts need attention today?"},
                )
                run_id = start.json()["agent_run_id"]

                forbidden = await client.post(
                    f"/agent/runs/{run_id}/approve",
                    headers=_headers(other_token),
                    json={"decision": "approve"},
                )
                assert forbidden.status_code == 403


@pytest.mark.integration
async def test_agent_run_endpoints_reject_invalid_payload(database_url: str) -> None:
    async with _session_factory(database_url) as session_factory:
        org_id, actor_id, prioritization = await _seed_demo_data(session_factory, "invalid")
        settings = ApiSettings(
            database_url=database_url,
            jwt_secret="test-secret-test-secret-test-secret-test-secret",
        )
        app = create_app(
            settings=settings,
            llm_gateway=FakeLLMGateway(responses=[prioritization] * 20),
        )
        token = create_access_token(
            subject=actor_id,
            organization_id=org_id,
            email="invalid@example.com",
            role="rep",
            settings=settings,
        )

        async with app.router.lifespan_context(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/agent/runs",
                    headers=_headers(token),
                    json={
                        "request_text": "which accounts need attention today?",
                        "organization_id": str(org_id),
                    },
                )
                assert response.status_code == 422
