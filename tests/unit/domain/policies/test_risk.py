import pytest
from revops.domain.errors import PolicyViolationError
from revops.domain.policies.risk import classify, requires_hitl
from revops.domain.values.risk import RiskLevel


@pytest.mark.parametrize(
    ("tool_name", "expected"),
    [
        ("search_accounts", RiskLevel.LOW),
        ("get_account_context", RiskLevel.LOW),
        ("create_task", RiskLevel.MEDIUM),
    ],
)
def test_classify_known_tools(tool_name: str, expected: RiskLevel) -> None:
    assert classify(tool_name) is expected


def test_unregistered_tool_is_denied_by_default() -> None:
    """Deny by default (AGENTS.md, Security rules): no implicit low-risk fallback."""
    with pytest.raises(PolicyViolationError):
        classify("send_email")  # not in this slice's allowlist yet


def test_empty_tool_name_is_denied() -> None:
    with pytest.raises(PolicyViolationError):
        classify("")


@pytest.mark.parametrize("risk", [RiskLevel.MEDIUM, RiskLevel.HIGH])
def test_hitl_required_for_medium_and_high(risk: RiskLevel) -> None:
    """SPEC-001 explicitly requires HITL for MEDIUM too (spec.md, "Tools and risk")."""
    assert requires_hitl(risk) is True


def test_hitl_not_required_for_low() -> None:
    assert requires_hitl(RiskLevel.LOW) is False
