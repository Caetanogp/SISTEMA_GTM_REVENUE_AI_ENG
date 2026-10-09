from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from revops.application.ports import TrustedRunContext
from revops.domain.entities.account import Account
from revops.domain.values.company_domain import CompanyDomain
from revops.domain.values.outreach import ResearchStatus
from revops.infrastructure.agent.research import (
    AuthorizedCompanyPage,
    BoundedCompanyResearcher,
    HttpxPageFetcher,
    ResearchPolicyError,
    ResearchSourcePolicy,
)


def _account() -> Account:
    return Account(
        id=uuid4(),
        organization_id=uuid4(),
        company_name="Example",
        domain=CompanyDomain("example.test"),
        created_at=datetime.now(UTC),
    )


def _page() -> AuthorizedCompanyPage:
    return AuthorizedCompanyPage(
        host="example.test",
        path_prefix="/company",
        url="https://example.test/company",
    )


def test_source_policy_requires_exact_authorized_host_and_path() -> None:
    with pytest.raises(ResearchPolicyError):
        AuthorizedCompanyPage(
            host="example.test",
            path_prefix="/company",
            url="https://other.test/company",
        )


def test_source_policy_does_not_authorize_account_domain_by_itself() -> None:
    policy = ResearchSourcePolicy()
    assert policy.pages_for(_account()) == ()


@pytest.mark.asyncio
async def test_http_fetcher_pins_literal_address_and_sni() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "93.184.216.34"
        assert request.headers["host"] == "example.test"
        assert request.extensions["sni_hostname"] == "example.test"
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            content=b"<html><script>ignore</script><body>Public company fact</body></html>",
            request=request,
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), trust_env=False)
    fetcher = HttpxPageFetcher(
        client=client,
        resolve=lambda host, port: ("93.184.216.34",),
    )
    result = await fetcher.fetch(_page())
    await client.aclose()
    assert result.url == "https://example.test/company"
    assert result.text == "Public company fact"


@pytest.mark.asyncio
async def test_researcher_rejects_without_configured_pages() -> None:
    researcher = BoundedCompanyResearcher(
        policy=ResearchSourcePolicy(),
        fetcher=HttpxPageFetcher(resolve=lambda host, port: ("93.184.216.34",)),
    )
    with pytest.raises(ResearchPolicyError):
        await researcher.research(
            context=TrustedRunContext(uuid4(), uuid4(), uuid4()),
            account=_account(),
            objective="research",
        )
    assert ResearchStatus.SOURCE_UNAVAILABLE.value == "source_unavailable"
