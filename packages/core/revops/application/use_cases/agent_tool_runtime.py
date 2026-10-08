"""Bounded, fail-closed dispatch for the approved single-agent tool catalog."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace

from pydantic import ValidationError

from revops.application.dto import (
    AgentToolDecision,
    RuntimeFailure,
    RuntimeResult,
    RuntimeToolEvidence,
)
from revops.application.ports import AgentTool, AgentToolRuntime, LLMGateway, TrustedRunContext
from revops.domain.values.runtime import (
    RuntimeFailureCode,
    ToolCallBudget,
    expected_tool,
)

PromptBuilder = Callable[[str, str, tuple[RuntimeToolEvidence, ...]], str]


def _failure(
    code: RuntimeFailureCode,
    evidence: list[RuntimeToolEvidence],
) -> RuntimeResult:
    return RuntimeResult(
        outcome=None,
        tool_name=None,
        tool_arguments=None,
        tool_result=None,
        evidence=tuple(evidence),
        failure=RuntimeFailure(code=code),
    )


@dataclass(frozen=True, slots=True)
class BoundedAgentToolRuntime(AgentToolRuntime):
    """Run structured tool decisions under an application-owned hard budget."""

    gateway: LLMGateway
    tools: Mapping[str, AgentTool]
    prompt_builder: PromptBuilder
    max_calls: int = 5
    max_writes: int = 1

    async def run(
        self,
        *,
        context: TrustedRunContext,
        request_text: str,
        context_text: str = "",
    ) -> RuntimeResult:
        budget = ToolCallBudget(max_calls=self.max_calls, max_writes=self.max_writes)
        evidence: list[RuntimeToolEvidence] = []
        current_context = context
        for _ in range(self.max_calls + 1):
            prompt = self.prompt_builder(request_text, context_text, tuple(evidence))
            try:
                response = await self.gateway.complete(
                    prompt=prompt,
                    response_model=AgentToolDecision,
                )
                decision = response.output
            except (ValidationError, ValueError):
                return _failure(RuntimeFailureCode.UNSUPPORTED_REQUEST, evidence)
            except Exception:
                return _failure(RuntimeFailureCode.TOOL_EXECUTION_FAILED, evidence)

            try:
                expected = expected_tool(decision.outcome)
            except (KeyError, ValueError):
                return _failure(RuntimeFailureCode.UNSUPPORTED_REQUEST, evidence)
            if decision.tool_name != expected:
                return _failure(RuntimeFailureCode.UNKNOWN_TOOL, evidence)

            tool = self.tools.get(decision.tool_name)
            if tool is None:
                return _failure(RuntimeFailureCode.UNKNOWN_TOOL, evidence)
            try:
                arguments = tool.arguments_model.model_validate(decision.arguments)
            except ValidationError:
                return _failure(RuntimeFailureCode.INVALID_TOOL_ARGUMENTS, evidence)

            budget_failure = budget.reserve(tool.risk)
            if budget_failure is not None:
                return _failure(budget_failure, evidence)

            try:
                execution = await tool.execute(context=current_context, arguments=arguments)
            except PermissionError:
                return _failure(RuntimeFailureCode.TENANT_SCOPE_VIOLATION, evidence)
            except (ValidationError, ValueError):
                return _failure(RuntimeFailureCode.INVALID_TOOL_ARGUMENTS, evidence)
            except Exception:
                return _failure(RuntimeFailureCode.TOOL_EXECUTION_FAILED, evidence)

            event = RuntimeToolEvidence(
                sequence=budget.calls,
                tool_name=tool.name,
                risk=tool.risk.name.lower(),
                outcome=execution.outcome,
                metadata={
                    "result_keys": sorted(execution.payload),
                    "llm_usage": response.usage.model_dump(mode="json"),
                },
            )
            evidence.append(event)
            prior_results = dict(current_context.prior_results)
            prior_results[tool.name] = dict(execution.payload)
            current_context = replace(current_context, prior_results=prior_results)
            result = RuntimeResult(
                outcome=decision.outcome,
                tool_name=tool.name,
                tool_arguments=arguments.model_dump(mode="json"),
                tool_result=dict(execution.payload),
                evidence=tuple(evidence),
                requires_approval=execution.requires_approval,
            )
            if execution.requires_approval or not decision.continue_after:
                return result

        return _failure(RuntimeFailureCode.CALL_BUDGET_EXCEEDED, evidence)
