from datetime import UTC, datetime
from uuid import uuid4

import pytest
from revops.application.ports import ResearchPage, TrustedRunContext
from revops.domain.entities.account import Account
from revops.domain.values.company_domain import CompanyDomain
from revops.infrastructure.agent.offline import (
    FixtureCompanyResearcher,
    StaticOutreachContextProvider,
)


@pytest.mark.asyncio
async def test_fixture_researcher_never_needs_network() -> None:
    page = ResearchPage(
        source_id="fixture",
        url="https://fixture.test/",
        retrieved_at=datetime.now(UTC),
        content_hash="a" * 64,
        text="Synthetic fact.",
    )
    account = Account(
        id=uuid4(),
        organization_id=uuid4(),
        company_name="Synthetic",
        domain=CompanyDomain("fixture.test"),
        created_at=datetime.now(UTC),
    )
    result = await FixtureCompanyResearcher((page,)).research(
        context=TrustedRunContext(uuid4(), uuid4(), uuid4()),
        account=account,
        objective="test",
    )
    assert result == (page,)


@pytest.mark.asyncio
async def test_static_context_returns_bounded_fixture() -> None:
    context = {"required_evidence": True, "evidence_ids": ["product:1"]}
    result = await StaticOutreachContextProvider(context).build(
        context=TrustedRunContext(uuid4(), uuid4(), uuid4()),
        account_id=uuid4(),
        contact_id=None,
        objective="test",
    )
    assert result == context
