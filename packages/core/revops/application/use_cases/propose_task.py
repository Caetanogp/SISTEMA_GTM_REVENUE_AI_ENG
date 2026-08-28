"""`ProposeTask`: build the proposed `create_task` action and classify its risk.

Returns the proposal unexecuted - no repository port is used here on purpose, so nothing this use
case does can write anywhere. `DecideApproval` (item 5) is what executes a proposal, and only after
a human decision on anything the risk policy flags for HITL.
"""

from __future__ import annotations

from dataclasses import dataclass

from revops.application.dto import CreateTaskArgs
from revops.domain.policies.risk import classify, requires_hitl
from revops.domain.values.risk import RiskLevel

_CREATE_TASK_TOOL_NAME = "create_task"


@dataclass(frozen=True, slots=True)
class ProposedAction:
    """A `create_task` call awaiting a human decision - never yet applied to any repository."""

    tool_name: str
    args: CreateTaskArgs
    risk: RiskLevel
    requires_approval: bool


@dataclass(frozen=True, slots=True)
class ProposeTask:
    def execute(self, args: CreateTaskArgs) -> ProposedAction:
        risk = classify(_CREATE_TASK_TOOL_NAME)
        return ProposedAction(
            tool_name=_CREATE_TASK_TOOL_NAME,
            args=args,
            risk=risk,
            requires_approval=requires_hitl(risk),
        )
