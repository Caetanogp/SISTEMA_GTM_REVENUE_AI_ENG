from datetime import UTC, datetime
from uuid import uuid4

from revops.application.dto import CreateTaskArgs
from revops.application.use_cases.propose_task import ProposeTask
from revops.domain.policies.risk import classify, requires_hitl
from revops.domain.values.risk import RiskLevel


def _args() -> CreateTaskArgs:
    return CreateTaskArgs(
        account_id=uuid4(),
        owner_id=uuid4(),
        title="Follow up on renewal",
        due_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_proposal_carries_the_args_unchanged() -> None:
    args = _args()
    proposal = ProposeTask().execute(args)
    assert proposal.args == args
    assert proposal.tool_name == "create_task"


def test_risk_classification_matches_the_domain_policy() -> None:
    proposal = ProposeTask().execute(_args())
    assert proposal.risk == classify("create_task")


def test_create_task_proposal_requires_hitl() -> None:
    """SPEC-001 flags create_task (MEDIUM) for HITL - domain.policies.risk.requires_hitl(MEDIUM)."""
    proposal = ProposeTask().execute(_args())
    assert proposal.risk == RiskLevel.MEDIUM
    assert proposal.requires_approval is True
    assert proposal.requires_approval == requires_hitl(proposal.risk)
