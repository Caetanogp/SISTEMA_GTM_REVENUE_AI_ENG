from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import ClassVar, cast
from uuid import uuid4

import pytest
from pydantic import BaseModel, ConfigDict, Field
from revops.application.dto import LLMUsage, RuntimeFailure
from revops.application.ports import AgentTool, ToolExecutionResult, TrustedRunContext
from revops.application.use_cases.agent_tool_runtime import BoundedAgentToolRuntime
from revops.domain.values.risk import RiskLevel
from revops.infrastructure.llm.fake import FakeLLMGateway


class _ReadArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str = Field(min_length=1)


@dataclass
class _FakeTool:
    name: str
    risk: ClassVar[RiskLevel] = RiskLevel.LOW
    arguments_model: ClassVar[type[BaseModel]] = _ReadArgs
    calls: int = 0
    requires_approval: bool = False
    prior_results_seen: list[dict[str, object]] = field(default_factory=list)

    async def execute(
        self, *, context: TrustedRunContext, arguments: BaseModel
    ) -> ToolExecutionResult:
        assert context.organization_id
        assert isinstance(arguments, _ReadArgs)
        self.calls += 1
        self.prior_results_seen.append(dict(context.prior_results))
        return ToolExecutionResult(
            payload={"value": arguments.value},
            outcome="approval_required" if self.requires_approval else "completed",
            requires_approval=self.requires_approval,
        )


def _context() -> TrustedRunContext:
    return TrustedRunContext(organization_id=uuid4(), actor_id=uuid4(), run_id=uuid4())


def _gateway(responses: Sequence[object]) -> FakeLLMGateway:
    return FakeLLMGateway(
        responses=list(responses),
        usage=LLMUsage(
            provider="fake",
            model="fake",
            model_config_json={},
            input_tokens=0,
            output_tokens=0,
            token_cost_usd=0,
            latency_ms=0,
        ),
    )


def _decision(*, continue_after: bool = False, value: str = "safe") -> dict[str, object]:
    return {
        "outcome": "account_prioritization",
        "tool_name": "search_accounts",
        "arguments": {"value": value},
        "continue_after": continue_after,
    }


def _runtime(gateway: FakeLLMGateway, tool: _FakeTool) -> BoundedAgentToolRuntime:
    return BoundedAgentToolRuntime(
        gateway=gateway,
        tools={tool.name: cast(AgentTool, tool)},
        prompt_builder=lambda request, context, evidence: request,
    )


@pytest.mark.asyncio
async def test_runtime_executes_only_the_expected_allowlisted_tool() -> None:
    tool = _FakeTool("search_accounts")
    result = await _runtime(_gateway([_decision()]), tool).run(
        context=_context(), request_text="prioritize accounts"
    )

    assert result.failure is None
    assert result.tool_name == "search_accounts"
    assert result.evidence[0].sequence == 1
    assert tool.calls == 1


@pytest.mark.asyncio
async def test_runtime_rejects_extra_tenant_argument_before_tool_invocation() -> None:
    tool = _FakeTool("search_accounts")
    response = _decision()
    response["arguments"] = {"value": "safe", "organization_id": str(uuid4())}
    result = await _runtime(_gateway([response]), tool).run(
        context=_context(), request_text="prioritize accounts"
    )

    assert result.failure == RuntimeFailure(code="invalid_tool_arguments")
    assert tool.calls == 0


@pytest.mark.asyncio
async def test_runtime_rejects_tool_name_confusion() -> None:
    tool = _FakeTool("search_accounts")
    response = _decision()
    response["tool_name"] = "delete_accounts"
    result = await _runtime(_gateway([response]), tool).run(
        context=_context(), request_text="delete accounts"
    )

    assert result.failure is not None
    assert result.failure.code.value == "unknown_tool"
    assert tool.calls == 0


@pytest.mark.asyncio
async def test_runtime_rejects_the_sixth_call_outside_model_control() -> None:
    tool = _FakeTool("search_accounts")
    responses = [_decision(continue_after=True, value=str(index)) for index in range(6)]
    result = await _runtime(_gateway(responses), tool).run(
        context=_context(), request_text="prioritize accounts"
    )

    assert result.failure is not None
    assert result.failure.code.value == "call_budget_exceeded"
    assert len(result.evidence) == 5
    assert tool.calls == 5


@pytest.mark.asyncio
async def test_runtime_stops_at_approval_boundary() -> None:
    tool = _FakeTool("create_task", requires_approval=True)
    response = {
        "outcome": "proposed_task_action",
        "tool_name": "create_task",
        "arguments": {"value": "proposal"},
    }
    result = await _runtime(_gateway([response]), tool).run(
        context=_context(), request_text="create a task"
    )

    assert result.failure is None
    assert result.requires_approval is True
    assert result.evidence[0].outcome == "approval_required"


@pytest.mark.asyncio
async def test_runtime_reuses_completed_result_in_the_next_tool_context() -> None:
    tool = _FakeTool("search_accounts")
    responses = [_decision(continue_after=True), _decision()]
    result = await _runtime(_gateway(responses), tool).run(
        context=_context(), request_text="research then prepare"
    )

    assert result.failure is None
    assert tool.calls == 2
    assert tool.prior_results_seen[0] == {}
    assert tool.prior_results_seen[1] == {"search_accounts": {"value": "safe"}}
    assert "llm_usage" in result.evidence[0].metadata


@pytest.mark.asyncio
async def test_runtime_maps_malformed_structured_output_to_safe_refusal() -> None:
    tool = _FakeTool("search_accounts")
    result = await _runtime(_gateway([{"not": "a runtime decision"}]), tool).run(
        context=_context(), request_text="ambiguous request"
    )

    assert result.failure is not None
    assert result.failure.code.value == "unsupported_request"
    assert tool.calls == 0
