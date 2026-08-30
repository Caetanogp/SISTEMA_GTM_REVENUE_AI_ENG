"""Agent run endpoints for the API composition root."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from langchain_core.runnables import RunnableConfig
from revops.application.dto import ApprovalDecisionInput, ApprovalDecisionType, CreateTaskDraft
from revops.application.ports import LLMGateway
from revops.domain.errors import InvalidTransitionError, NotAuthorizedError, PolicyViolationError
from revops.infrastructure.persistence.models import AgentRun as AgentRunModel
from revops.infrastructure.persistence.models import AgentRunEvent as AgentRunEventModel
from revops.infrastructure.persistence.models import Task as TaskModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from apps.api.auth import ApiPrincipal, get_current_principal
from apps.api.dependencies import get_llm_gateway, get_session_factory, get_settings
from apps.api.runtime import open_agent_runner
from apps.api.schemas import (
    AgentRunListItem,
    ApprovalDecisionRequest,
    ApprovalResponse,
    StartAgentRunRequest,
    StartAgentRunResponse,
    TaskResponse,
)
from apps.api.settings import ApiSettings

router = APIRouter(prefix="/agent/runs", tags=["agent-runs"])


def _run_config(run_id: UUID) -> RunnableConfig:
    return {"configurable": {"thread_id": str(run_id)}}


def _sse_event(event: str, payload: dict[str, object]) -> str:
    data = json.dumps(jsonable_encoder(payload), separators=(",", ":"))
    return f"event: {event}\ndata: {data}\n\n"


async def _visible_run_or_404(
    session: AsyncSession, *, organization_id: UUID, run_id: UUID
) -> AgentRunModel:
    row = await session.scalar(select(AgentRunModel).where(AgentRunModel.id == run_id))
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="agent run not found")
    if row.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    return row


async def _latest_event_type(session: AsyncSession, run_id: UUID) -> str | None:
    stmt = (
        select(AgentRunEventModel.event_type)
        .where(AgentRunEventModel.run_id == run_id)
        .order_by(desc(AgentRunEventModel.occurred_at), desc(AgentRunEventModel.id))
        .limit(1)
    )
    return cast(str | None, await session.scalar(stmt))


def _task_response(task: TaskModel) -> TaskResponse:
    return TaskResponse(
        id=task.id,
        organization_id=task.organization_id,
        owner_id=task.owner_id,
        account_id=task.account_id,
        title=task.title,
        due_at=task.due_at,
        status=task.status,
    )


@router.post("", response_model=StartAgentRunResponse, status_code=status.HTTP_201_CREATED)
async def start_agent_run(
    payload: StartAgentRunRequest,
    current_user: Annotated[ApiPrincipal, Depends(get_current_principal)],
    session_factory: Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)],
    settings: Annotated[ApiSettings, Depends(get_settings)],
    llm_gateway: Annotated[LLMGateway, Depends(get_llm_gateway)],
) -> StartAgentRunResponse:
    result = None
    snapshot = None
    async with (
        session_factory() as session,
        open_agent_runner(
            session=session,
            session_factory=session_factory,
            settings=settings,
            llm_gateway=llm_gateway,
        ) as runner,
    ):
        try:
            result = await runner.start(
                organization_id=current_user.organization_id,
                actor_id=current_user.user_id,
                request_text=payload.request_text,
                token_budget=payload.token_budget,
            )
            snapshot = await runner.graph.aget_state(_run_config(result.run_id))
            await session.commit()
        except (InvalidTransitionError, NotAuthorizedError, PolicyViolationError) as exc:
            await session.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        except RuntimeError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc
    if result is None or snapshot is None:
        raise RuntimeError("agent run did not produce a result")
    interrupt = snapshot.interrupts[0].value if snapshot.interrupts else None
    return StartAgentRunResponse(
        agent_run_id=result.run_id,
        thread_id=result.thread_id,
        status="interrupted" if snapshot.interrupts else "completed",
        interrupt=interrupt,
    )


@router.get("", response_model=list[AgentRunListItem])
async def list_agent_runs(
    current_user: Annotated[ApiPrincipal, Depends(get_current_principal)],
    session_factory: Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)],
) -> list[AgentRunListItem]:
    async with session_factory() as session:
        rows = (
            await session.scalars(
                select(AgentRunModel)
                .where(AgentRunModel.organization_id == current_user.organization_id)
                .order_by(desc(AgentRunModel.started_at), desc(AgentRunModel.id))
            )
        ).all()
        items: list[AgentRunListItem] = []
        for row in rows:
            latest_event = await _latest_event_type(session, row.id)
            items.append(
                AgentRunListItem(
                    agent_run_id=row.id,
                    organization_id=row.organization_id,
                    requested_by=row.requested_by,
                    request_text=row.request_text,
                    graph_version=row.graph_version,
                    prompt_version=row.prompt_version,
                    status=latest_event or row.status,
                    started_at=row.started_at,
                    completed_at=row.completed_at,
                    latest_event_type=latest_event,
                )
            )
        return items


@router.get("/{run_id}/stream")
async def stream_agent_run(
    run_id: UUID,
    current_user: Annotated[ApiPrincipal, Depends(get_current_principal)],
    session_factory: Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)],
    settings: Annotated[ApiSettings, Depends(get_settings)],
    llm_gateway: Annotated[LLMGateway, Depends(get_llm_gateway)],
) -> StreamingResponse:
    async def _events() -> AsyncIterator[str]:
        async with session_factory() as session:
            await _visible_run_or_404(
                session,
                organization_id=current_user.organization_id,
                run_id=run_id,
            )
            async with open_agent_runner(
                session=session,
                session_factory=session_factory,
                settings=settings,
                llm_gateway=llm_gateway,
            ) as runner:
                snapshot = await runner.graph.aget_state(_run_config(run_id))
                rows = (
                    await session.scalars(
                        select(AgentRunEventModel)
                        .where(AgentRunEventModel.run_id == run_id)
                        .order_by(AgentRunEventModel.occurred_at, AgentRunEventModel.id)
                    )
                ).all()
                for row in rows:
                    yield _sse_event(
                        row.event_type,
                        {
                            "run_id": row.run_id,
                            "organization_id": row.organization_id,
                            "occurred_at": row.occurred_at,
                            "graph_version": row.graph_version,
                            "prompt_version": row.prompt_version,
                            "metadata": row.event_metadata,
                            "error": row.error,
                        },
                    )
                if snapshot.interrupts:
                    yield _sse_event("interrupt", {"interrupt": snapshot.interrupts[0].value})

    return StreamingResponse(_events(), media_type="text/event-stream")


@router.post("/{run_id}/approve", response_model=ApprovalResponse)
async def approve_agent_run(
    run_id: UUID,
    payload: ApprovalDecisionRequest,
    current_user: Annotated[ApiPrincipal, Depends(get_current_principal)],
    session_factory: Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)],
    settings: Annotated[ApiSettings, Depends(get_settings)],
    llm_gateway: Annotated[LLMGateway, Depends(get_llm_gateway)],
) -> ApprovalResponse:
    result = None
    final_snapshot = None
    async with session_factory() as session:
        await _visible_run_or_404(
            session,
            organization_id=current_user.organization_id,
            run_id=run_id,
        )
        async with open_agent_runner(
            session=session,
            session_factory=session_factory,
            settings=settings,
            llm_gateway=llm_gateway,
        ) as runner:
            snapshot = await runner.graph.aget_state(_run_config(run_id))
            if not snapshot.interrupts:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="run is not waiting for approval",
                )
            decision = ApprovalDecisionInput(
                decision=ApprovalDecisionType(payload.decision.value),
                organization_id=current_user.organization_id,
                decided_by=current_user.user_id,
                edited=(
                    CreateTaskDraft(
                        account_id=payload.edited.account_id,
                        title=payload.edited.title,
                        due_at=payload.edited.due_at,
                    )
                    if payload.edited is not None
                    else None
                ),
            )
            try:
                result = await runner.resume(
                    thread_id=str(run_id),
                    decision=decision.model_dump(mode="json"),
                )
                final_snapshot = await runner.graph.aget_state(_run_config(run_id))
                await session.commit()
            except (InvalidTransitionError, NotAuthorizedError, PolicyViolationError) as exc:
                await session.rollback()
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
            except RuntimeError as exc:
                await session.rollback()
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=str(exc),
                ) from exc

    if result is None or final_snapshot is None:
        raise RuntimeError("approval resume did not produce a result")
    task_snapshot: TaskResponse | None = None
    task_payload = result.state.get("task")
    if isinstance(task_payload, dict):
        async with session_factory() as session:
            task_row = await session.scalar(
                select(TaskModel).where(TaskModel.id == UUID(task_payload["id"]))
            )
            if task_row is not None:
                task_snapshot = _task_response(task_row)

    return ApprovalResponse(
        agent_run_id=result.run_id,
        status="interrupted" if final_snapshot.interrupts else "completed",
        task=task_snapshot,
    )
