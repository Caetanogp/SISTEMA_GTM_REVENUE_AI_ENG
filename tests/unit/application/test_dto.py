from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError
from revops.application.dto import AccountScore, CreateTaskArgs
from revops.domain.values.score import ScoreTier


def _create_task_args(**overrides: object) -> dict[str, object]:
    defaults: dict[str, object] = {
        "account_id": uuid4(),
        "owner_id": uuid4(),
        "title": "Follow up",
        "due_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    return {**defaults, **overrides}


def _account_score(**overrides: object) -> dict[str, object]:
    defaults: dict[str, object] = {
        "account_id": uuid4(),
        "score": 82,
        "tier": ScoreTier.HOT,
        "evidence": ["last touch 2 day(s) ago via email (2026-01-01)"],
    }
    return {**defaults, **overrides}


def test_create_task_args_accepts_a_valid_payload() -> None:
    args = CreateTaskArgs(**_create_task_args())
    assert args.title == "Follow up"


def test_create_task_args_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        CreateTaskArgs(**_create_task_args(urgent=True))


def test_create_task_args_rejects_empty_title() -> None:
    with pytest.raises(ValidationError):
        CreateTaskArgs(**_create_task_args(title=""))


def test_create_task_args_has_no_organization_id_field() -> None:
    """AGENTS.md: organization_id comes from the auth token, never from LLM/request output."""
    assert "organization_id" not in CreateTaskArgs.model_fields


def test_account_score_accepts_a_valid_payload() -> None:
    score = AccountScore(**_account_score())
    assert score.tier is ScoreTier.HOT


def test_account_score_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        AccountScore(**_account_score(rank=1))


@pytest.mark.parametrize("value", [-1, 101])
def test_account_score_rejects_out_of_range_score(value: int) -> None:
    with pytest.raises(ValidationError):
        AccountScore(**_account_score(score=value))
