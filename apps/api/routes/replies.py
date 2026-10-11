"""Authenticated, immutable reply-intelligence endpoints."""

from __future__ import annotations

from typing import Annotated, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from revops.application.dto import AppendReplyFeedbackArgs, RegisterReplyArgs, ReplyResultDTO
from revops.application.ports import LLMGateway, ReplyUnitOfWork
from revops.application.use_cases.reply import (
    AppendReplyFeedback,
    ListReplyFeedback,
    RegisterReply,
    ReplyConflictError,
)
from revops.domain.errors import PolicyViolationError
from revops.infrastructure.persistence.reply_repositories import SqlAlchemyReplyRepository
from revops.infrastructure.persistence.unit_of_work import SqlAlchemyReplyUnitOfWork
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from apps.api.auth import ApiPrincipal, get_current_principal
from apps.api.dependencies import get_llm_gateway, get_session, get_session_factory, get_settings
from apps.api.runtime import UtcClock, reply_runner
from apps.api.schemas import (
    RegisterReplyRequest,
    ReplyClassificationResponse,
    ReplyFeedbackRequest,
    ReplyFeedbackResponse,
    ReplyResponse,
)
from apps.api.settings import ApiSettings

router = APIRouter(tags=["replies"])

IdempotencyKey = Annotated[str, Header(min_length=1, max_length=128, alias="Idempotency-Key")]


def _reply_response(reply: object, *, replayed: bool = False) -> ReplyResponse:
    from revops.application.ports import ReplyRecord

    if not isinstance(reply, ReplyRecord):
        raise TypeError("expected reply record")
    return ReplyResponse(
        id=reply.id,
        account_id=reply.account_id,
        contact_id=reply.contact_id,
        language=reply.reply.language,
        created_at=reply.created_at,
        replayed=replayed,
    )


def _feedback_response(record: object) -> ReplyFeedbackResponse:
    from revops.application.ports import ReplyFeedbackRecord

    if not isinstance(record, ReplyFeedbackRecord):
        raise TypeError("expected reply feedback record")
    return ReplyFeedbackResponse(
        id=record.id,
        run_id=record.run_id,
        corrected_category=record.corrected_category,
        comment=record.comment,
        submitted_by=record.submitted_by,
        created_at=record.created_at,
    )


def _classification_status(
    outcome: str,
) -> Literal["in_progress", "completed", "failed", "recovery_required"]:
    if outcome == "in_progress":
        return "in_progress"
    if outcome == "completed":
        return "completed"
    if outcome == "checkpoint_recovery_required":
        return "recovery_required"
    return "failed"


@router.post("/replies", response_model=ReplyResponse, status_code=status.HTTP_201_CREATED)
async def register_reply(
    payload: RegisterReplyRequest,
    idempotency_key: IdempotencyKey,
    current_user: Annotated[ApiPrincipal, Depends(get_current_principal)],
    session_factory: Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)],
) -> ReplyResponse:
    try:
        registered = await RegisterReply(
            lambda: cast(
                ReplyUnitOfWork,
                SqlAlchemyReplyUnitOfWork(session_factory(), close_on_exit=True),
            ),
            UtcClock(),
        ).execute(
            organization_id=current_user.organization_id,
            actor_id=current_user.user_id,
            args=RegisterReplyArgs.model_validate(payload.model_dump()),
            idempotency_key=idempotency_key,
        )
    except (PolicyViolationError, ReplyConflictError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _reply_response(registered.reply, replayed=registered.replayed)


@router.get("/replies/{reply_id}", response_model=ReplyResponse)
async def get_reply(
    reply_id: UUID,
    current_user: Annotated[ApiPrincipal, Depends(get_current_principal)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ReplyResponse:
    reply = await SqlAlchemyReplyRepository(session).get(current_user.organization_id, reply_id)
    if reply is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="reply not found")
    return _reply_response(reply)


@router.post("/replies/{reply_id}/classify", response_model=ReplyClassificationResponse)
async def classify_reply(
    reply_id: UUID,
    idempotency_key: IdempotencyKey,
    current_user: Annotated[ApiPrincipal, Depends(get_current_principal)],
    session_factory: Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)],
    settings: Annotated[ApiSettings, Depends(get_settings)],
    llm_gateway: Annotated[LLMGateway, Depends(get_llm_gateway)],
) -> ReplyClassificationResponse:
    # Classification is intrinsically idempotent per reply through its unique reservation. The
    # required key remains a validated request-level write guard under the API-wide convention.
    del idempotency_key
    try:
        outcome = await reply_runner(
            session_factory=session_factory, settings=settings, llm_gateway=llm_gateway
        ).classify(
            organization_id=current_user.organization_id,
            actor_id=current_user.user_id,
            reply_id=reply_id,
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="reply not found"
        ) from exc
    result = None
    if outcome.artifact is not None:
        raw_result = outcome.artifact.get("result")
        if isinstance(raw_result, dict):
            try:
                result = ReplyResultDTO.model_validate(raw_result)
            except ValueError:
                result = None
    return ReplyClassificationResponse(
        run_id=outcome.run_id,
        status=_classification_status(outcome.outcome),
        replayed=outcome.replayed,
        result=result,
    )


@router.post("/agent/runs/{run_id}/reply-feedback", response_model=ReplyFeedbackResponse)
async def append_reply_feedback(
    run_id: UUID,
    payload: ReplyFeedbackRequest,
    idempotency_key: IdempotencyKey,
    current_user: Annotated[ApiPrincipal, Depends(get_current_principal)],
    session_factory: Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)],
) -> ReplyFeedbackResponse:
    try:
        record = await AppendReplyFeedback(
            lambda: cast(
                ReplyUnitOfWork,
                SqlAlchemyReplyUnitOfWork(session_factory(), close_on_exit=True),
            ),
            UtcClock(),
        ).execute(
            organization_id=current_user.organization_id,
            actor_id=current_user.user_id,
            run_id=run_id,
            args=AppendReplyFeedbackArgs.model_validate(payload.model_dump()),
            idempotency_key=idempotency_key,
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="reply run not found"
        ) from exc
    except (PolicyViolationError, ReplyConflictError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _feedback_response(record)


@router.get("/agent/runs/{run_id}/reply-feedback", response_model=list[ReplyFeedbackResponse])
async def list_reply_feedback(
    run_id: UUID,
    current_user: Annotated[ApiPrincipal, Depends(get_current_principal)],
    session_factory: Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)],
) -> list[ReplyFeedbackResponse]:
    try:
        history = await ListReplyFeedback(
            lambda: cast(
                ReplyUnitOfWork,
                SqlAlchemyReplyUnitOfWork(session_factory(), close_on_exit=True),
            )
        ).execute(organization_id=current_user.organization_id, run_id=run_id)
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="reply run not found"
        ) from exc
    return [_feedback_response(record) for record in history.records]
