"""Pure policy values for the bounded single-agent tool runtime."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from revops.domain.values.risk import RiskLevel


class RuntimeOutcome(StrEnum):
    """The only request outcomes the first runtime is allowed to route."""

    ACCOUNT_CONTEXT_READ = "account_context_read"
    ACCOUNT_PRIORITIZATION = "account_prioritization"
    PROPOSED_TASK_ACTION = "proposed_task_action"
    COMPANY_RESEARCH = "company_research"
    FOLLOWUP_PREPARATION = "followup_preparation"


class RuntimeFailureCode(StrEnum):
    """Stable, non-sensitive reasons for a runtime refusal or failure."""

    UNSUPPORTED_REQUEST = "unsupported_request"
    AMBIGUOUS_REQUEST = "ambiguous_request"
    UNKNOWN_TOOL = "unknown_tool"
    INVALID_TOOL_ARGUMENTS = "invalid_tool_arguments"
    TENANT_SCOPE_VIOLATION = "tenant_scope_violation"
    CALL_BUDGET_EXCEEDED = "call_budget_exceeded"
    WRITE_BUDGET_EXCEEDED = "write_budget_exceeded"
    TOOL_EXECUTION_FAILED = "tool_execution_failed"


def expected_tool(outcome: RuntimeOutcome) -> str:
    """Return the only tool permitted for a supported outcome."""
    return {
        RuntimeOutcome.ACCOUNT_CONTEXT_READ: "get_account_context",
        RuntimeOutcome.ACCOUNT_PRIORITIZATION: "search_accounts",
        RuntimeOutcome.PROPOSED_TASK_ACTION: "create_task",
        RuntimeOutcome.COMPANY_RESEARCH: "research_company",
        RuntimeOutcome.FOLLOWUP_PREPARATION: "prepare_followup",
    }[outcome]


@dataclass(slots=True)
class ToolCallBudget:
    """Runtime-owned bounds; model output cannot increase either counter."""

    max_calls: int = 5
    max_writes: int = 1
    calls: int = 0
    writes: int = 0

    def reserve(self, risk: RiskLevel) -> RuntimeFailureCode | None:
        """Reserve one invocation before execution, returning a stable refusal code if bounded."""
        if self.calls >= self.max_calls:
            return RuntimeFailureCode.CALL_BUDGET_EXCEEDED
        if risk >= RiskLevel.MEDIUM and self.writes >= self.max_writes:
            return RuntimeFailureCode.WRITE_BUDGET_EXCEEDED
        self.calls += 1
        if risk >= RiskLevel.MEDIUM:
            self.writes += 1
        return None
