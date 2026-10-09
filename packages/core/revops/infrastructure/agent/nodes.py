"""LangGraph node implementations for the SPEC-001 runtime."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from types import TracebackType
from typing import Protocol, cast
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from langgraph.types import interrupt

from revops.application.dto import (
    AccountCandidate,
    ApprovalDecisionInput,
    ApprovalDecisionType,
    CreateTaskArgs,
    CreateTaskDraft,
    LLMResult,
    PrioritizationOutput,
    RuntimeResult,
    RuntimeToolEvidence,
)
from revops.application.ports import (
    AgentToolRuntime,
    Clock,
    LLMGateway,
    TrustedRunContext,
    UnitOfWork,
)
from revops.application.use_cases.agent_tool_runtime import (
    BoundedAgentToolRuntime,
    RuntimeSelection,
)
from revops.application.use_cases.decide_approval import DecideApproval, PendingApproval
from revops.application.use_cases.prioritize_accounts import PrioritizeAccounts
from revops.application.use_cases.propose_task import ProposedAction, ProposeTask
from revops.application.use_cases.reason_about_accounts import ReasonAboutAccounts
from revops.domain.entities.task import Task
from revops.domain.values.risk import RiskLevel
from revops.domain.values.runtime import RuntimeFailureCode
from revops.infrastructure.agent.prompt_loader import load_prioritize_accounts_prompt
from revops.infrastructure.agent.state import (
    AccountCandidateSnapshot,
    AgentGraphState,
    CreateTaskArgsSnapshot,
    PendingApprovalSnapshot,
)


class UnitOfWorkScope(Protocol):
    async def __aenter__(self) -> UnitOfWork: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None: ...


@dataclass(frozen=True, slots=True)
class AgentGraphDependencies:
    uow_factory: Callable[[], UnitOfWorkScope]
    llm_gateway: LLMGateway
    clock: Clock
    graph_version: str
    prompt_version: str
    tool_runtime: AgentToolRuntime | None = None
    checkpointed_runtime: bool = False
    token_budget: int = 4096


def _uuid(value: str) -> UUID:
    return UUID(value)


def _parse_account_candidates(
    snapshots: list[AccountCandidateSnapshot],
) -> list[AccountCandidate]:
    return [AccountCandidate.model_validate(snapshot) for snapshot in snapshots]


def _proposal_snapshot(
    proposal: ProposedAction,
    *,
    run_id: UUID,
    task_id: UUID,
    action_id: UUID,
) -> PendingApprovalSnapshot:
    args = cast(CreateTaskArgsSnapshot, proposal.args.model_dump(mode="json"))
    return {
        "proposal": {
            "tool_name": proposal.tool_name,
            "args": args,
            "risk": proposal.risk.value,
            "requires_approval": proposal.requires_approval,
        },
        "run_id": str(run_id),
        "action_id": str(action_id),
        "task_id": str(task_id),
        "decided": False,
    }


def _pending_approval(snapshot: PendingApprovalSnapshot) -> PendingApproval:
    proposal_snapshot = snapshot["proposal"]
    return PendingApproval(
        proposal=ProposedAction(
            tool_name=proposal_snapshot["tool_name"],
            args=CreateTaskArgs.model_validate(proposal_snapshot["args"]),
            risk=RiskLevel(proposal_snapshot["risk"]),
            requires_approval=proposal_snapshot["requires_approval"],
        ),
        run_id=_uuid(snapshot["run_id"]),
        action_id=_uuid(snapshot["action_id"]),
        task_id=_uuid(snapshot["task_id"]),
        decided=snapshot["decided"],
    )


def _create_task_args(draft: CreateTaskDraft | None, owner_id: UUID) -> CreateTaskArgs:
    if draft is None:
        raise ValueError("edited task draft is required for edit decisions")
    return CreateTaskArgs(
        account_id=draft.account_id,
        owner_id=owner_id,
        title=draft.title,
        due_at=draft.due_at,
    )


def _task_snapshot(task: Task) -> dict[str, object]:
    snapshot = asdict(task)
    snapshot["status"] = task.status.value
    snapshot["id"] = str(task.id)
    snapshot["organization_id"] = str(task.organization_id)
    snapshot["owner_id"] = str(task.owner_id)
    snapshot["account_id"] = str(task.account_id)
    snapshot["due_at"] = task.due_at.isoformat()
    return snapshot


def _runtime_pending_approval(
    result: RuntimeResult,
    *,
    run_id: UUID,
) -> PendingApprovalSnapshot:
    if result.tool_name != "create_task" or result.tool_result is None:
        raise ValueError("runtime approval result is not a create_task proposal")
    args = CreateTaskArgs.model_validate(result.tool_result["args"])
    proposal = ProposeTask().execute(args)
    action_id = uuid5(NAMESPACE_URL, f"action:{run_id}")
    return _proposal_snapshot(
        proposal,
        run_id=run_id,
        task_id=uuid4(),
        action_id=action_id,
    )


async def route_runtime(state: AgentGraphState, deps: AgentGraphDependencies) -> dict[str, object]:
    """Route through the bounded runtime when the composition root provides it."""
    if deps.tool_runtime is None:
        raise RuntimeError("bounded agent tool runtime is not configured")
    context = TrustedRunContext(
        organization_id=_uuid(state["organization_id"]),
        actor_id=_uuid(state["actor_id"]),
        run_id=_uuid(state["run_id"]),
    )
    result = await deps.tool_runtime.run(
        context=context,
        request_text=state.get("request_text", ""),
    )
    update: dict[str, object] = {
        "runtime_evidence": [item.model_dump(mode="json") for item in result.evidence],
    }
    if result.outcome is not None:
        update["runtime_outcome"] = result.outcome.value
    if result.tool_name is not None:
        update["runtime_tool_name"] = result.tool_name
    if result.tool_arguments is not None:
        update["runtime_tool_arguments"] = result.tool_arguments
    if result.tool_result is not None:
        update["runtime_tool_result"] = result.tool_result
    if result.failure is not None:
        update["runtime_failure"] = result.failure.model_dump(mode="json")
    if result.requires_approval:
        update["pending_approval"] = _runtime_pending_approval(
            result,
            run_id=_uuid(state["run_id"]),
        )
    return update


def _checkpointed_runtime(deps: AgentGraphDependencies) -> BoundedAgentToolRuntime:
    if not isinstance(deps.tool_runtime, BoundedAgentToolRuntime):
        raise RuntimeError("checkpointed runtime is not configured")
    return deps.tool_runtime


def _runtime_context(state: AgentGraphState) -> TrustedRunContext:
    return TrustedRunContext(
        organization_id=_uuid(state["organization_id"]),
        actor_id=_uuid(state["actor_id"]),
        run_id=_uuid(state["run_id"]),
        prior_results=state.get("runtime_prior_results", {}),
    )


def _runtime_evidence(state: AgentGraphState) -> tuple[RuntimeToolEvidence, ...]:
    return tuple(
        RuntimeToolEvidence.model_validate(item) for item in state.get("runtime_evidence", [])
    )


def _runtime_failure_update(
    failure: RuntimeResult,
    *,
    step: str = "failed",
) -> dict[str, object]:
    update: dict[str, object] = {"runtime_lifecycle_step": step}
    if failure.failure is not None:
        update["runtime_failure"] = failure.failure.model_dump(mode="json")
    return update


async def select_runtime(state: AgentGraphState, deps: AgentGraphDependencies) -> dict[str, object]:
    runtime = _checkpointed_runtime(deps)
    selected = await runtime.select(
        context=_runtime_context(state),
        request_text=state.get("request_text", ""),
        context_text="",
        evidence=_runtime_evidence(state),
    )
    if isinstance(selected, RuntimeResult):
        return _runtime_failure_update(selected)
    return {
        "runtime_lifecycle_step": "selected",
        "runtime_selected_outcome": selected.decision.outcome.value,
        "runtime_selected_tool_name": selected.tool.name,
        "runtime_selected_arguments": selected.arguments.model_dump(mode="json"),
        "runtime_selected_continue_after": selected.decision.continue_after,
        "runtime_selected_usage": dict(selected.usage),
    }


def _restore_runtime_selection(
    state: AgentGraphState,
    runtime: BoundedAgentToolRuntime,
) -> RuntimeSelection | RuntimeResult:
    return runtime.restore_selection(
        outcome=state["runtime_selected_outcome"],
        tool_name=state["runtime_selected_tool_name"],
        arguments=state["runtime_selected_arguments"],
        continue_after=state.get("runtime_selected_continue_after", False),
        usage=state.get("runtime_selected_usage", {}),
    )


def reserve_runtime(state: AgentGraphState, deps: AgentGraphDependencies) -> dict[str, object]:
    runtime = _checkpointed_runtime(deps)
    selection = _restore_runtime_selection(state, runtime)
    if isinstance(selection, RuntimeResult):
        return _runtime_failure_update(selection)
    calls, writes, failure = runtime.reserve(
        selection=selection,
        calls=state.get("runtime_call_count", 0),
        writes=state.get("runtime_write_count", 0),
    )
    update: dict[str, object] = {
        "runtime_call_count": calls,
        "runtime_write_count": writes,
    }
    if failure is not None:
        update.update(
            {
                "runtime_lifecycle_step": "failed",
                "runtime_failure": {"code": failure.value},
            }
        )
    else:
        update["runtime_lifecycle_step"] = "reserved"
    return update


async def execute_runtime(
    state: AgentGraphState, deps: AgentGraphDependencies
) -> dict[str, object]:
    runtime = _checkpointed_runtime(deps)
    selection = _restore_runtime_selection(state, runtime)
    if isinstance(selection, RuntimeResult):
        return _runtime_failure_update(selection)
    if state.get("runtime_lifecycle_step") == "executed":
        return {}
    execution = await runtime.execute_selected(
        selection=selection,
        context=_runtime_context(state),
    )
    if isinstance(execution, RuntimeFailureCode):
        return {
            "runtime_lifecycle_step": "failed",
            "runtime_failure": {"code": execution.value},
        }
    return {
        "runtime_lifecycle_step": "executed",
        "runtime_execution_result": dict(execution.payload),
        "runtime_execution_requires_approval": execution.requires_approval,
        "runtime_execution_outcome": execution.outcome,
    }


def complete_runtime(state: AgentGraphState, deps: AgentGraphDependencies) -> dict[str, object]:
    runtime = _checkpointed_runtime(deps)
    selection = _restore_runtime_selection(state, runtime)
    if isinstance(selection, RuntimeResult):
        return _runtime_failure_update(selection)
    from revops.application.ports import ToolExecutionResult

    execution = ToolExecutionResult(
        payload=state.get("runtime_execution_result", {}),
        outcome=state.get("runtime_execution_outcome", "completed"),
        requires_approval=state.get("runtime_execution_requires_approval", False),
    )
    result = runtime.complete(
        selection=selection,
        execution=execution,
        evidence=list(_runtime_evidence(state)),
        calls=state.get("runtime_call_count", 0),
    )
    if result.failure is not None:
        return {
            "runtime_lifecycle_step": "failed",
            "runtime_failure": result.failure.model_dump(mode="json"),
        }
    update: dict[str, object] = {
        "runtime_lifecycle_step": "completed",
        "runtime_outcome": result.outcome.value if result.outcome else None,
        "runtime_tool_name": result.tool_name,
        "runtime_tool_arguments": result.tool_arguments,
        "runtime_tool_result": result.tool_result,
        "runtime_evidence": [item.model_dump(mode="json") for item in result.evidence],
        "runtime_prior_results": {
            **state.get("runtime_prior_results", {}),
            selection.tool.name: dict(result.tool_result or {}),
        },
    }
    if result.requires_approval:
        update["pending_approval"] = _runtime_pending_approval(
            result,
            run_id=_uuid(state["run_id"]),
        )
    return update


async def load_context(state: AgentGraphState, deps: AgentGraphDependencies) -> dict[str, object]:
    organization_id = _uuid(state["organization_id"])
    async with deps.uow_factory() as uow:
        candidates = await PrioritizeAccounts(
            accounts=uow.accounts,
            clock=deps.clock,
            canonical=getattr(uow, "canonical", None),
        ).execute(organization_id, token_budget=state.get("token_budget", deps.token_budget))
    return {
        "candidates": [candidate.model_dump(mode="json") for candidate in candidates],
    }


async def score_accounts(state: AgentGraphState, deps: AgentGraphDependencies) -> dict[str, object]:
    candidates = _parse_account_candidates(state.get("candidates", []))
    prompt = load_prioritize_accounts_prompt(
        request_text=state.get("request_text", ""),
        candidates=candidates,
    )
    result: LLMResult[PrioritizationOutput] = await ReasonAboutAccounts(
        gateway=deps.llm_gateway,
    ).execute(prompt=prompt, candidates=candidates, now=deps.clock.now())
    return {
        "prioritization": result.output.model_dump(mode="json"),
        "llm_usage": result.usage.model_dump(mode="json"),
    }


async def propose_action(state: AgentGraphState, deps: AgentGraphDependencies) -> dict[str, object]:
    prioritization = PrioritizationOutput.model_validate(state["prioritization"])
    actor_id = _uuid(state["actor_id"])
    task_draft = prioritization.task
    proposal = ProposeTask().execute(
        CreateTaskArgs(
            account_id=task_draft.account_id,
            owner_id=actor_id,
            title=task_draft.title,
            due_at=task_draft.due_at,
        )
    )
    run_id = _uuid(state["run_id"])
    action_id = uuid5(NAMESPACE_URL, f"action:{run_id}")
    task_id = uuid4()
    pending_snapshot = _proposal_snapshot(
        proposal,
        run_id=run_id,
        task_id=task_id,
        action_id=action_id,
    )
    return {"pending_approval": pending_snapshot}


async def execute_action(state: AgentGraphState, deps: AgentGraphDependencies) -> dict[str, object]:
    pending_snapshot = state["pending_approval"]
    decision_payload = interrupt(
        {
            "question": "approve_edit_reject",
            "run_id": pending_snapshot["run_id"],
            "action_id": pending_snapshot["action_id"],
            "task_id": pending_snapshot["task_id"],
            "proposal": pending_snapshot["proposal"],
        }
    )
    decision = ApprovalDecisionInput.model_validate(decision_payload)
    pending = _pending_approval(pending_snapshot)
    organization_id = _uuid(state["organization_id"])
    actor_id = _uuid(state["actor_id"])

    async with deps.uow_factory() as uow:
        decide = DecideApproval(
            tasks=uow.tasks,
            audit=uow.audit,
            approvals=uow.approvals,
            clock=deps.clock,
            canonical=getattr(uow, "canonical", None),
        )
        if decision.decision == ApprovalDecisionType.APPROVE:
            task = await decide.approve(pending, organization_id=organization_id, actor_id=actor_id)
        elif decision.decision == ApprovalDecisionType.EDIT:
            task = await decide.edit(
                pending,
                _create_task_args(decision.edited, actor_id),
                organization_id=organization_id,
                actor_id=actor_id,
            )
        else:
            await decide.reject(pending, organization_id=organization_id, actor_id=actor_id)
            task = None
        await uow.commit()

    update: dict[str, object] = {
        "pending_approval": {**pending_snapshot, "decided": True},
        "decision": decision.model_dump(mode="json"),
    }
    if task is not None:
        update["task"] = _task_snapshot(task)
    return update
