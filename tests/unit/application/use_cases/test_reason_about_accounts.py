from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from revops.application.dto import (
    AccountCandidate,
    ContextSectionSnapshot,
    CreateTaskDraft,
    PrioritizationOutput,
    RankedAccount,
)
from revops.application.use_cases.reason_about_accounts import (
    ReasonAboutAccounts,
    StructuredOutputError,
)
from revops.domain.values.score import ScoreTier
from revops.infrastructure.llm.fake import FakeLLMGateway

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _candidate(*, company_name: str = "Acme") -> AccountCandidate:
    account_id = uuid4()
    return AccountCandidate(
        account_id=account_id,
        company_name=company_name,
        score=72,
        tier=ScoreTier.HOT,
        evidence=["recent engagement"],
        context=[ContextSectionSnapshot(label="account", text="Acme")],
        dropped_context_labels=[],
        token_count=10,
    )


def _output(candidate: AccountCandidate, *, due_days: int = 7) -> PrioritizationOutput:
    return PrioritizationOutput(
        accounts=[
            RankedAccount(
                account_id=candidate.account_id,
                score=candidate.score,
                tier=candidate.tier,
                evidence=candidate.evidence,
                reasons=["strong signal"],
            )
        ],
        task=CreateTaskDraft(
            account_id=candidate.account_id,
            title="Call the champion",
            due_at=_NOW + timedelta(days=due_days),
        ),
    )


async def test_valid_output_returns_the_structured_result() -> None:
    candidate = _candidate()
    gateway = FakeLLMGateway(responses=[_output(candidate)])
    use_case = ReasonAboutAccounts(gateway=gateway)

    result = await use_case.execute(prompt="prompt", candidates=[candidate], now=_NOW)

    assert result.output.task.account_id == candidate.account_id
    assert result.usage.provider == "fake"
    assert len(gateway.calls) == 1


async def test_invalid_output_is_retried_before_succeeding() -> None:
    candidate = _candidate()
    gateway = FakeLLMGateway(
        responses=[
            {
                "accounts": [
                    {
                        "account_id": str(uuid4()),
                        "score": candidate.score,
                        "tier": candidate.tier,
                        "evidence": candidate.evidence,
                        "reasons": ["wrong account"],
                    }
                ],
                "task": {
                    "account_id": str(candidate.account_id),
                    "title": "Call the champion",
                    "due_at": (_NOW + timedelta(days=7)).isoformat(),
                },
            },
            _output(candidate),
        ]
    )
    use_case = ReasonAboutAccounts(gateway=gateway)

    result = await use_case.execute(prompt="prompt", candidates=[candidate], now=_NOW)

    assert result.output.task.account_id == candidate.account_id
    assert len(gateway.calls) == 2


async def test_three_bad_attempts_raise() -> None:
    candidate = _candidate()
    gateway = FakeLLMGateway(
        responses=[
            {
                "accounts": [],
                "task": {
                    "account_id": str(candidate.account_id),
                    "title": "Call the champion",
                    "due_at": (_NOW + timedelta(days=7)).isoformat(),
                },
            },
            {
                "accounts": [],
                "task": {
                    "account_id": str(candidate.account_id),
                    "title": "Call the champion",
                    "due_at": (_NOW + timedelta(days=7)).isoformat(),
                },
            },
            {
                "accounts": [],
                "task": {
                    "account_id": str(candidate.account_id),
                    "title": "Call the champion",
                    "due_at": (_NOW + timedelta(days=7)).isoformat(),
                },
            },
        ]
    )
    use_case = ReasonAboutAccounts(gateway=gateway)

    with pytest.raises(StructuredOutputError):
        await use_case.execute(prompt="prompt", candidates=[candidate], now=_NOW)
