"""Administrative deduplication endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import ValidationError
from revops.application.dto import DeduplicationScanArgs
from revops.application.use_cases.deduplication import (
    DeduplicationConflictError,
    DeduplicationIdempotencyConflictError,
    DeduplicationNotFoundError,
)
from revops.domain.entities.deduplication import DeduplicationRecordType

from apps.api.auth import ApiPrincipal, require_admin
from apps.api.dependencies import deduplication_uow_factory
from apps.api.runtime import deduplication_services
from apps.api.schemas import (
    DeduplicationCandidateResponse,
    DeduplicationDecisionResponse,
    DeduplicationDismissRequest,
    DeduplicationHistoryResponse,
    DeduplicationMergeRequest,
    DeduplicationMergeResponse,
    DeduplicationScanRequest,
    DeduplicationScanResponse,
    DeduplicationStatusResponse,
)

router = APIRouter(prefix="/admin/deduplication", tags=["deduplication"])


def _services(request: Request) -> tuple[Any, ...]:
    return deduplication_services(
        uow_factory=deduplication_uow_factory(request), settings=request.app.state.settings
    )


def _scan(value: Any) -> DeduplicationScanResponse:
    return DeduplicationScanResponse(
        id=value.id,
        organization_id=value.organization_id,
        record_types=tuple(item.value for item in value.record_types),
        status=value.status.value,
        replayed=value.replayed,
    )


def _candidate(value: Any) -> DeduplicationCandidateResponse:
    return DeduplicationCandidateResponse(
        id=value.id,
        scan_id=value.scan_id,
        organization_id=value.organization_id,
        record_type=value.record_type.value,
        left_id=value.left_id,
        right_id=value.right_id,
        score=value.score,
        reasons=value.reasons,
        policy_version=value.policy_version,
        status=value.status.value,
    )


def _conflict(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.post("/scans", response_model=DeduplicationScanResponse, status_code=201)
async def start_scan(
    payload: DeduplicationScanRequest,
    principal: Annotated[ApiPrincipal, Depends(require_admin)],
    request: Request,
    idempotency_key: Annotated[str, Header(min_length=1, max_length=128, alias="Idempotency-Key")],
) -> DeduplicationScanResponse:
    try:
        args = DeduplicationScanArgs(
            record_types=tuple(DeduplicationRecordType(value) for value in payload.record_types)
        )
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail="invalid record_types") from exc
    start, *_ = _services(request)
    try:
        return _scan(
            await start.execute(
                organization_id=principal.organization_id,
                requested_by=principal.user_id,
                idempotency_key=idempotency_key,
                args=args,
            )
        )
    except DeduplicationIdempotencyConflictError as exc:
        raise _conflict(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="deduplication dispatch failed") from exc


@router.get("/scans/{scan_id}/candidates", response_model=list[DeduplicationCandidateResponse])
async def list_candidates(
    scan_id: UUID,
    principal: Annotated[ApiPrincipal, Depends(require_admin)],
    request: Request,
    offset: int = 0,
    limit: int = 100,
) -> list[DeduplicationCandidateResponse]:
    if offset < 0 or not 0 < limit <= 100:
        raise HTTPException(status_code=422, detail="invalid pagination")
    _, _, list_use_case, *_ = _services(request)
    try:
        values = await list_use_case.execute(
            organization_id=principal.organization_id, scan_id=scan_id, offset=offset, limit=limit
        )
    except DeduplicationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DeduplicationConflictError as exc:
        raise _conflict(exc) from exc
    return [_candidate(value) for value in values]


@router.get("/scans/{scan_id}", response_model=DeduplicationStatusResponse)
async def scan_status(
    scan_id: UUID,
    principal: Annotated[ApiPrincipal, Depends(require_admin)],
    request: Request,
) -> DeduplicationStatusResponse:
    _, get_status, *_ = _services(request)
    try:
        result = await get_status.execute(
            organization_id=principal.organization_id, scan_id=scan_id
        )
    except DeduplicationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return DeduplicationStatusResponse(
        **_scan(result.scan).model_dump(),
        total=result.total,
        pending=result.pending,
        dismissed=result.dismissed,
        merged=result.merged,
        stale=result.stale,
    )


@router.post("/candidates/{candidate_id}/dismiss", response_model=DeduplicationDecisionResponse)
async def dismiss_candidate(
    candidate_id: UUID,
    payload: DeduplicationDismissRequest,
    principal: Annotated[ApiPrincipal, Depends(require_admin)],
    request: Request,
    idempotency_key: Annotated[str, Header(min_length=1, max_length=128, alias="Idempotency-Key")],
) -> DeduplicationDecisionResponse:
    _, _, _, dismiss, *_ = _services(request)
    try:
        result = await dismiss.execute(
            organization_id=principal.organization_id,
            candidate_id=candidate_id,
            idempotency_key=idempotency_key,
            reason=payload.reason,
            actor_id=principal.user_id,
            occurred_at=datetime.now(UTC),
        )
    except DeduplicationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DeduplicationConflictError as exc:
        raise _conflict(exc) from exc
    return DeduplicationDecisionResponse(
        candidate_id=result.candidate_id, status=result.status.value, replayed=result.replayed
    )


@router.post("/candidates/{candidate_id}/merge", response_model=DeduplicationMergeResponse)
async def merge_candidate(
    candidate_id: UUID,
    payload: DeduplicationMergeRequest,
    principal: Annotated[ApiPrincipal, Depends(require_admin)],
    request: Request,
    idempotency_key: Annotated[str, Header(min_length=1, max_length=128, alias="Idempotency-Key")],
) -> DeduplicationMergeResponse:
    _, _, _, _, merge, _ = _services(request)
    try:
        result = await merge.execute(
            organization_id=principal.organization_id,
            candidate_id=candidate_id,
            master_record_id=payload.master_record_id,
            idempotency_key=idempotency_key,
            actor_id=principal.user_id,
            occurred_at=datetime.now(UTC),
        )
    except DeduplicationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (DeduplicationConflictError, DeduplicationIdempotencyConflictError) as exc:
        raise _conflict(exc) from exc
    return DeduplicationMergeResponse(
        event_id=result.event_id,
        alias_id=result.alias_id,
        canonical_id=result.canonical_id,
        replayed=result.replayed,
    )


@router.post("/merges/{merge_event_id}/revert", response_model=DeduplicationDecisionResponse)
async def revert_merge(
    merge_event_id: UUID,
    principal: Annotated[ApiPrincipal, Depends(require_admin)],
    request: Request,
    idempotency_key: Annotated[str, Header(min_length=1, max_length=128, alias="Idempotency-Key")],
) -> DeduplicationDecisionResponse:
    _, _, _, _, _, revert, _ = _services(request)
    try:
        result = await revert.execute(
            organization_id=principal.organization_id,
            merge_event_id=merge_event_id,
            idempotency_key=idempotency_key,
            actor_id=principal.user_id,
            occurred_at=datetime.now(UTC),
        )
    except DeduplicationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DeduplicationConflictError as exc:
        raise _conflict(exc) from exc
    return DeduplicationDecisionResponse(
        candidate_id=result.candidate_id, status=result.status.value, replayed=result.replayed
    )


@router.get("/merges", response_model=list[DeduplicationHistoryResponse])
async def merge_history(
    principal: Annotated[ApiPrincipal, Depends(require_admin)],
    request: Request,
    offset: int = 0,
    limit: int = 100,
) -> list[DeduplicationHistoryResponse]:
    if offset < 0 or not 0 < limit <= 100:
        raise HTTPException(status_code=422, detail="invalid pagination")
    _, _, _, _, _, _, history = _services(request)
    return [
        DeduplicationHistoryResponse(
            id=value.id,
            record_type=value.record_type.value,
            action=value.action,
            candidate_id=value.candidate_id,
            related_event_id=value.related_event_id,
            alias_id=value.alias_id,
            canonical_id=value.canonical_id,
            reason_codes=value.reason_codes,
            actor_id=value.actor_id,
            occurred_at=value.occurred_at,
        )
        for value in await history.execute(
            organization_id=principal.organization_id, offset=offset, limit=limit
        )
    ]
