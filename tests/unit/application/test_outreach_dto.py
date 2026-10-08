from uuid import uuid4

import pytest
from pydantic import ValidationError
from revops.application.dto import PrepareFollowupArgs, ResearchCompanyArgs
from revops.domain.values.outreach import DraftLanguage


def test_research_args_reject_tenant_and_source_controls() -> None:
    with pytest.raises(ValidationError):
        ResearchCompanyArgs.model_validate(
            {
                "account_id": str(uuid4()),
                "objective": "Understand the account",
                "organization_id": str(uuid4()),
                "url": "https://example.test",
            }
        )


def test_followup_args_require_explicit_supported_language() -> None:
    args = PrepareFollowupArgs(
        account_id=uuid4(),
        objective="Prepare a grounded follow-up",
        language=DraftLanguage.PORTUGUESE,
    )
    assert args.language is DraftLanguage.PORTUGUESE
