from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

import pytest
from revops.application.dto import RuntimeResult, RuntimeToolEvidence
from revops.application.ports import AgentToolRuntime, LLMGateway, TrustedRunContext
from revops.domain.values.runtime import RuntimeOutcome
from revops.infrastructure.agent.nodes import AgentGraphDependencies, UnitOfWorkScope, route_runtime
from revops.infrastructure.agent.runner import AgentGraphRunner
from revops.infrastructure.agent.state import AgentGraphState, PendingApprovalSnapshot


class _Runtime:
    def __init__(self, result: RuntimeResult) -> None:
        self.result = result

    async def run(
        self,
        *,
        context: TrustedRunContext,
        request_text: str,
        context_text: str = "",
    ) -> RuntimeResult:
        assert context.organization_id
        assert request_text
        assert context_text == ""
        return self.result


class _Clock:
    def now(self) -> datetime:
        return datetime.now(UTC)


def _state() -> AgentGraphState:
    return {
        "organization_id": str(uuid4()),
        "actor_id": str(uuid4()),
        "request_text": "create a task",
        "run_id": str(uuid4()),
    }


def _deps(runtime: _Runtime) -> AgentGraphDependencies:
    return AgentGraphDependencies(
        uow_factory=lambda: cast(UnitOfWorkScope, None),
        llm_gateway=cast(LLMGateway, None),
        clock=_Clock(),
        graph_version="single-agent-tool-runtime.v1",
        prompt_version="agent_tool_runtime.v1",
        tool_runtime=cast(AgentToolRuntime, runtime),
    )


@pytest.mark.asyncio
async def test_route_runtime_builds_pending_approval_without_writing() -> None:
    account_id = uuid4()
    result = RuntimeResult(
        outcome=RuntimeOutcome.PROPOSED_TASK_ACTION,
        tool_name="create_task",
        tool_arguments={
            "account_id": str(account_id),
            "title": "Follow up",
            "due_at": "2026-10-10T12:00:00Z",
        },
        tool_result={
            "args": {
                "account_id": str(account_id),
                "owner_id": str(uuid4()),
                "title": "Follow up",
                "due_at": "2026-10-10T12:00:00Z",
            }
        },
        evidence=(
            RuntimeToolEvidence(
                sequence=1,
                tool_name="create_task",
                risk="medium",
                outcome="approval_required",
            ),
        ),
        requires_approval=True,
    )

    update = await route_runtime(_state(), _deps(_Runtime(result)))

    pending = cast(PendingApprovalSnapshot, update["pending_approval"])
    assert pending["proposal"]["tool_name"] == "create_task"
    assert pending["decided"] is False
    assert cast(list[dict[str, object]], update["runtime_evidence"])[0]["sequence"] == 1


def test_runtime_lifecycle_metadata_excludes_tool_payloads() -> None:
    metadata = AgentGraphRunner._snapshot_metadata(
        {
            "runtime_outcome": "account_prioritization",
            "runtime_tool_name": "search_accounts",
            "runtime_tool_arguments": {"secret": "must-not-persist"},
            "runtime_tool_result": {"email": "synthetic@example.com"},
            "runtime_evidence": [{"sequence": 1, "tool_name": "search_accounts"}],
        }
    )

    assert "runtime_evidence" in metadata
    assert "runtime_tool_arguments" not in metadata
    assert "runtime_tool_result" not in metadata
