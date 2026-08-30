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
)
from revops.application.ports import Clock, LLMGateway, UnitOfWork
from revops.application.use_cases.decide_approval import DecideApproval, PendingApproval
from revops.application.use_cases.prioritize_accounts import PrioritizeAccounts
from revops.application.use_cases.propose_task import ProposedAction, ProposeTask
from revops.application.use_cases.reason_about_accounts import ReasonAboutAccounts
from revops.domain.entities.task import Task
from revops.domain.values.risk import RiskLevel
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


async def load_context(state: AgentGraphState, deps: AgentGraphDependencies) -> dict[str, object]:
    organization_id = _uuid(state["organization_id"])
    async with deps.uow_factory() as uow:
        candidates = await PrioritizeAccounts(
            accounts=uow.accounts,
            clock=deps.clock,
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
