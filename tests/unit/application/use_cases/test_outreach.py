from datetime import UTC, datetime
from uuid import uuid4

import pytest
from revops.application.dto import (
    ClaimVerificationOutput,
    FollowupGenerationOutput,
    LLMResult,
    LLMUsage,
    PrepareFollowupArgs,
    ResearchCompanyArgs,
    ResearchExtractionFact,
    ResearchExtractionOutput,
    ResearchResultDTO,
    ResearchSourceDTO,
)
from revops.application.ports import ResearchPage, TrustedRunContext
from revops.application.use_cases.outreach import PrepareFollowup, ResearchCompany
from revops.domain.entities.account import Account
from revops.domain.entities.contact import Contact
from revops.domain.values.company_domain import CompanyDomain
from revops.domain.values.email import EmailAddress
from revops.domain.values.outreach import DraftLanguage, FollowupStatus, ResearchStatus


class _Accounts:
    def __init__(self, account: Account) -> None:
        self.account = account

    async def get(self, organization_id, account_id):
        assert organization_id == self.account.organization_id
        assert account_id == self.account.id
        return self.account


class _Contacts:
    def __init__(self, contact: Contact) -> None:
        self.contact = contact

    async def get(self, organization_id, contact_id):
        if organization_id != self.contact.organization_id or contact_id != self.contact.id:
            return None
        return self.contact


class _Researcher:
    async def research(self, *, context, account, objective):
        return (
            ResearchPage(
                source_id="company-home",
                url="https://example.test/",
                retrieved_at=datetime.now(UTC),
                content_hash="a" * 64,
                text="The company serves technology teams.",
            ),
        )


class _Gateway:
    def __init__(self, outputs) -> None:
        self.outputs = iter(outputs)

    async def complete(self, *, prompt, response_model):
        del prompt
        return LLMResult(
            output=next(self.outputs),
            usage=LLMUsage(
                provider="fake",
                model="fake",
                model_config_json={},
                input_tokens=1,
                output_tokens=1,
                token_cost_usd=0,
                latency_ms=1,
            ),
        )

    def configuration_snapshot(self):
        return {}

    def health_snapshot(self):
        raise NotImplementedError


class _Context:
    async def build(self, *, context, account_id, contact_id, objective):
        return {
            "account_id": str(account_id),
            "objective": objective,
            "required_evidence": True,
            "evidence_ids": ["crm:account:context"],
        }


def _records():
    organization_id = uuid4()
    account = Account(
        id=uuid4(),
        organization_id=organization_id,
        company_name="Example",
        domain=CompanyDomain("example.test"),
        created_at=datetime.now(UTC),
    )
    contact = Contact(
        id=uuid4(),
        organization_id=organization_id,
        account_id=account.id,
        email=EmailAddress("buyer@example.test"),
        full_name="Buyer",
    )
    return organization_id, account, contact


@pytest.mark.asyncio
async def test_research_extracts_only_acquired_source_references() -> None:
    organization_id, account, contact = _records()
    result = await ResearchCompany(
        accounts=_Accounts(account),
        contacts=_Contacts(contact),
        researcher=_Researcher(),
        gateway=_Gateway(
            [
                ResearchExtractionOutput(
                    facts=(
                        ResearchExtractionFact(
                            key="segment", value="technology", source_ids=("company-home",)
                        ),
                    )
                )
            ]
        ),
    ).execute(
        context=TrustedRunContext(organization_id, uuid4(), uuid4()),
        args=ResearchCompanyArgs(
            account_id=account.id,
            contact_id=contact.id,
            objective="Understand the segment",
        ),
    )
    assert result.status is ResearchStatus.COMPLETE
    assert result.sources[0].source_id == "company-home"


@pytest.mark.asyncio
async def test_followup_verifier_rejection_does_not_regenerate() -> None:
    organization_id, account, contact = _records()
    result = await PrepareFollowup(
        _Context(),
        _Gateway(
            [
                FollowupGenerationOutput(
                    subject="A grounded subject",
                    body="A grounded body.",
                    language=DraftLanguage.ENGLISH,
                    rationale="Evidence-based.",
                    claims=(
                        {
                            "claim_id": "claim-1",
                            "text": "Supported context.",
                            "source_ids": ("company-home",),
                        },
                    ),
                ),
                ClaimVerificationOutput(
                    accepted=False,
                    unsupported_claim_ids=("claim-1",),
                    limitations=("unsupported_claim",),
                ),
            ]
        ),
    ).execute(
        context=TrustedRunContext(organization_id, uuid4(), uuid4()),
        args=PrepareFollowupArgs(
            account_id=account.id,
            contact_id=contact.id,
            objective="Prepare a relevant follow-up",
            language=DraftLanguage.ENGLISH,
        ),
        research=ResearchResultDTO(
            account_id=account.id,
            status=ResearchStatus.COMPLETE,
            facts=(),
            sources=(
                ResearchSourceDTO(
                    source_id="company-home",
                    url="https://example.test/",
                    retrieved_at=datetime.now(UTC),
                    content_hash="a" * 64,
                    excerpt="Supported context.",
                ),
            ),
        ),
    )
    assert result.status is FollowupStatus.EVIDENCE_INSUFFICIENT
    assert "unsupported_claim" in result.limitations
