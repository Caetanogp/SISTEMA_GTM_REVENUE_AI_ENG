"""Bounded, fail-closed dispatch for the approved single-agent tool catalog."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace

from pydantic import BaseModel, ValidationError

from revops.application.dto import (
    AgentToolDecision,
    RuntimeFailure,
    RuntimeResult,
    RuntimeToolEvidence,
)
from revops.application.ports import (
    AgentTool,
    AgentToolRuntime,
    LLMGateway,
    ToolExecutionResult,
    TrustedRunContext,
)
from revops.domain.values.runtime import (
    RuntimeFailureCode,
    ToolCallBudget,
    expected_tool,
)

PromptBuilder = Callable[[str, str, tuple[RuntimeToolEvidence, ...]], str]


@dataclass(frozen=True, slots=True)
class RuntimeSelection:
    """Validated model choice held between checkpointed lifecycle nodes."""

    decision: AgentToolDecision
    tool: AgentTool
    arguments: BaseModel
    usage: Mapping[str, object]


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
    max_artifact_bytes: int = 128 * 1024

    async def select(
        self,
        *,
        context: TrustedRunContext,
        request_text: str,
        context_text: str,
        evidence: tuple[RuntimeToolEvidence, ...],
    ) -> RuntimeSelection | RuntimeResult:
        """Validate one model decision without reserving or executing a tool."""
        prompt = self.prompt_builder(request_text, context_text, evidence)
        try:
            response = await self.gateway.complete(
                prompt=prompt,
                response_model=AgentToolDecision,
            )
            decision = response.output
        except (ValidationError, ValueError):
            return _failure(RuntimeFailureCode.UNSUPPORTED_REQUEST, list(evidence))
        except Exception:
            return _failure(RuntimeFailureCode.TOOL_EXECUTION_FAILED, list(evidence))

        try:
            expected = expected_tool(decision.outcome)
        except (KeyError, ValueError):
            return _failure(RuntimeFailureCode.UNSUPPORTED_REQUEST, list(evidence))
        if decision.tool_name != expected:
            return _failure(RuntimeFailureCode.UNKNOWN_TOOL, list(evidence))
        tool = self.tools.get(decision.tool_name)
        if tool is None:
            return _failure(RuntimeFailureCode.UNKNOWN_TOOL, list(evidence))
        try:
            arguments = tool.arguments_model.model_validate(decision.arguments)
        except ValidationError:
            return _failure(RuntimeFailureCode.INVALID_TOOL_ARGUMENTS, list(evidence))
        return RuntimeSelection(
            decision=decision,
            tool=tool,
            arguments=arguments,
            usage=response.usage.model_dump(mode="json"),
        )

    def reserve(
        self,
        *,
        selection: RuntimeSelection,
        calls: int,
        writes: int,
    ) -> tuple[int, int, RuntimeFailureCode | None]:
        """Reserve a call before any side effect and return durable counters."""
        budget = ToolCallBudget(
            max_calls=self.max_calls,
            max_writes=self.max_writes,
            calls=calls,
            writes=writes,
        )
        failure = budget.reserve(selection.tool.risk)
        return budget.calls, budget.writes, failure

    def restore_selection(
        self,
        *,
        outcome: str,
        tool_name: str,
        arguments: Mapping[str, object],
        continue_after: bool,
        usage: Mapping[str, object],
    ) -> RuntimeSelection | RuntimeResult:
        """Rehydrate a selection from checkpoint JSON and validate it again."""
        try:
            decision = AgentToolDecision.model_validate(
                {
                    "outcome": outcome,
                    "tool_name": tool_name,
                    "arguments": dict(arguments),
                    "continue_after": continue_after,
                }
            )
            expected = expected_tool(decision.outcome)
        except (ValidationError, KeyError, ValueError):
            return _failure(RuntimeFailureCode.INVALID_TOOL_ARGUMENTS, [])
        if expected != tool_name:
            return _failure(RuntimeFailureCode.UNKNOWN_TOOL, [])
        tool = self.tools.get(tool_name)
        if tool is None:
            return _failure(RuntimeFailureCode.UNKNOWN_TOOL, [])
        try:
            parsed = tool.arguments_model.model_validate(arguments)
        except ValidationError:
            return _failure(RuntimeFailureCode.INVALID_TOOL_ARGUMENTS, [])
        return RuntimeSelection(
            decision=decision,
            tool=tool,
            arguments=parsed,
            usage=dict(usage),
        )

    async def execute_selected(
        self,
        *,
        selection: RuntimeSelection,
        context: TrustedRunContext,
    ) -> ToolExecutionResult | RuntimeFailureCode:
        """Execute only a previously validated and reserved selection."""
        try:
            return await selection.tool.execute(
                context=context,
                arguments=selection.arguments,
            )
        except PermissionError:
            return RuntimeFailureCode.TENANT_SCOPE_VIOLATION
        except (ValidationError, ValueError):
            return RuntimeFailureCode.INVALID_TOOL_ARGUMENTS
        except Exception:
            return RuntimeFailureCode.TOOL_EXECUTION_FAILED

    def complete(
        self,
        *,
        selection: RuntimeSelection,
        execution: ToolExecutionResult,
        evidence: list[RuntimeToolEvidence],
        calls: int,
    ) -> RuntimeResult:
        """Create the bounded result after execution has been checkpointed."""
        payload = dict(execution.payload)
        try:
            encoded_payload = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
        except (TypeError, ValueError):
            return _failure(RuntimeFailureCode.TOOL_EXECUTION_FAILED, evidence)
        if len(encoded_payload.encode("utf-8")) > self.max_artifact_bytes:
            return _failure(
                RuntimeFailureCode.TOOL_EXECUTION_FAILED,
                evidence,
            )
        event = RuntimeToolEvidence(
            sequence=calls,
            tool_name=selection.tool.name,
            risk=selection.tool.risk.name.lower(),
            outcome=execution.outcome,
            metadata={
                "result_keys": sorted(payload),
                "llm_usage": dict(selection.usage),
            },
        )
        return RuntimeResult(
            outcome=selection.decision.outcome,
            tool_name=selection.tool.name,
            tool_arguments=selection.arguments.model_dump(mode="json"),
            tool_result=payload,
            evidence=(*evidence, event),
            requires_approval=execution.requires_approval,
        )

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
