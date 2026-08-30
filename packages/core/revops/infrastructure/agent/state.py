"""Checkpointed graph state for the SPEC-001 LangGraph runtime."""

from __future__ import annotations

from typing import Any, NotRequired, TypedDict


class ContextSectionSnapshot(TypedDict):
    label: str
    text: str


class AccountCandidateSnapshot(TypedDict):
    account_id: str
    company_name: str
    score: int
    tier: str
    evidence: list[str]
    context: list[ContextSectionSnapshot]
    dropped_context_labels: list[str]
    token_count: int


class RankedAccountSnapshot(TypedDict):
    account_id: str
    score: int
    tier: str
    reasons: list[str]


class CreateTaskDraftSnapshot(TypedDict):
    account_id: str
    title: str
    due_at: str


class PrioritizationSnapshot(TypedDict):
    accounts: list[RankedAccountSnapshot]
    task: CreateTaskDraftSnapshot


class CreateTaskArgsSnapshot(TypedDict):
    account_id: str
    owner_id: str
    title: str
    due_at: str


class ProposedActionSnapshot(TypedDict):
    tool_name: str
    args: CreateTaskArgsSnapshot
    risk: int
    requires_approval: bool


class PendingApprovalSnapshot(TypedDict):
    proposal: ProposedActionSnapshot
    run_id: str
    action_id: str
    task_id: str
    decided: bool


class ApprovalDecisionSnapshot(TypedDict):
    decision: str
    organization_id: str
    decided_by: str
    edited: NotRequired[CreateTaskDraftSnapshot | None]


class AgentGraphState(TypedDict, total=False):
    organization_id: str
    actor_id: str
    request_text: str
    run_id: str
    thread_id: str
    graph_version: str
    prompt_version: str
    model_config_json: dict[str, Any]
    token_budget: int
    candidates: list[AccountCandidateSnapshot]
    llm_usage: dict[str, Any]
    prioritization: PrioritizationSnapshot
    pending_approval: PendingApprovalSnapshot
    decision: ApprovalDecisionSnapshot
    task: dict[str, Any]
    error: str
