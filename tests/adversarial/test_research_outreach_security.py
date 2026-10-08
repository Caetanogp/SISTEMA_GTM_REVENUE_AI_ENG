from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError
from revops.application.dto import ResearchCompanyArgs
from revops.application.ports import TrustedRunContext
from revops.domain.entities.account import Account
from revops.domain.values.company_domain import CompanyDomain
from revops.infrastructure.agent.research import (
    AuthorizedCompanyPage,
    ResearchPolicyError,
    resolve_global_addresses,
)

pytestmark = pytest.mark.adversarial


def test_model_cannot_select_source_or_tenant_controls() -> None:
    with pytest.raises(ValidationError):
        ResearchCompanyArgs.model_validate(
            {
                "account_id": str(uuid4()),
                "objective": "research",
                "organization_id": str(uuid4()),
                "host": "169.254.169.254",
            }
        )


def test_research_page_rejects_credentials_and_query_data() -> None:
    with pytest.raises(ResearchPolicyError):
        AuthorizedCompanyPage(
            host="example.test",
            path_prefix="/",
            url="https://user:password@example.test/?token=secret",
        )


def test_loopback_resolution_is_rejected_before_http(monkeypatch) -> None:
    monkeypatch.setattr(
        "revops.infrastructure.agent.research.socket.getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("127.0.0.1", 443))],
    )
    with pytest.raises(ResearchPolicyError):
        resolve_global_addresses("example.test", 443)


def test_context_identity_remains_trusted_data() -> None:
    account = Account(
        id=uuid4(),
        organization_id=uuid4(),
        company_name="Synthetic",
        domain=CompanyDomain("example.test"),
        created_at=datetime.now(UTC),
    )
    context = TrustedRunContext(account.organization_id, uuid4(), uuid4())
    assert context.organization_id == account.organization_id
