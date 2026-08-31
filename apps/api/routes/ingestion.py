"""Administrative ingestion endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from revops.application.dto import IngestionRecordInput, StagedIngestionItem, StagedIngestionJob
from revops.application.use_cases.ingestion import (
    ConfirmIngestion,
    GetIngestionJob,
    IngestionIdempotencyConflictError,
    IngestionNotFoundError,
    ListIngestionItems,
    StageIngestion,
)
from revops.domain.errors import PolicyViolationError
from revops.infrastructure.ingestion import IngestionTransportError, parse_csv_records

from apps.api.auth import ApiPrincipal, require_admin
from apps.api.dependencies import ingestion_uow_factory
from apps.api.runtime import ingestion_services
from apps.api.schemas import (
    IngestionItemResponse,
    IngestionJobResponse,
    IngestionStageRequest,
)

router = APIRouter(prefix="/admin/ingestion", tags=["ingestion"])


def _item(item: StagedIngestionItem) -> IngestionItemResponse:
    return IngestionItemResponse(
        row_number=item.row_number,
        status=item.status.value,
        validation_codes=item.validation_codes,
        account_outcome=item.account_outcome.value,
        contact_outcome=item.contact_outcome.value,
        enrichment_outcome=item.enrichment_outcome.value,
        account_id=item.account_id,
        contact_id=item.contact_id,
        enrichment_id=item.enrichment_id,
    )


def _job(job: StagedIngestionJob, **kwargs: object) -> IngestionJobResponse:
    return IngestionJobResponse(
        id=job.id,
        organization_id=job.organization_id,
        source=job.source,
        idempotency_key=job.idempotency_key,
        status=job.status.value,
        items=[_item(item) for item in job.items] if kwargs.pop("include_items", False) else None,
        **kwargs,
    )


def _services(
    request: Request,
) -> tuple[StageIngestion, ConfirmIngestion, GetIngestionJob, ListIngestionItems]:
    return ingestion_services(
        uow_factory=ingestion_uow_factory(request), settings=request.app.state.settings
    )


@router.post("", response_model=IngestionJobResponse, status_code=status.HTTP_201_CREATED)
async def stage_json(
    payload: IngestionStageRequest,
    principal: Annotated[ApiPrincipal, Depends(require_admin)],
    request: Request,
) -> IngestionJobResponse:
    stage, _, _, _ = _services(request)
    try:
        result = await stage.execute(
            organization_id=principal.organization_id,
            requested_by=principal.user_id,
            source=payload.source,
            idempotency_key=payload.idempotency_key,
            records=[
                IngestionRecordInput.model_validate(row.model_dump()) for row in payload.records
            ],
        )
    except (PolicyViolationError, IngestionIdempotencyConflictError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _job(result.job, include_items=True, replayed=result.replayed)


@router.post("/csv", response_model=IngestionJobResponse, status_code=status.HTTP_201_CREATED)
async def stage_csv(
    request: Request,
    principal: Annotated[ApiPrincipal, Depends(require_admin)],
    source: Annotated[str, Header(min_length=1, max_length=128, alias="X-Import-Source")],
    idempotency_key: Annotated[str, Header(min_length=1, max_length=128, alias="Idempotency-Key")],
) -> IngestionJobResponse:
    try:
        records = parse_csv_records(await request.body())
    except IngestionTransportError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    stage, _, _, _ = _services(request)
    try:
        result = await stage.execute(
            organization_id=principal.organization_id,
            requested_by=principal.user_id,
            source=source,
            idempotency_key=idempotency_key,
            records=records,
        )
    except (PolicyViolationError, IngestionIdempotencyConflictError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _job(result.job, include_items=True, replayed=result.replayed)


@router.post("/{job_id}/confirm", response_model=IngestionJobResponse)
async def confirm(
    job_id: UUID, principal: Annotated[ApiPrincipal, Depends(require_admin)], request: Request
) -> IngestionJobResponse:
    _, confirm_use_case, _, _ = _services(request)
    try:
        result = await confirm_use_case.execute(
            organization_id=principal.organization_id, job_id=job_id
        )
    except IngestionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="ingestion dispatch failed") from exc
    return _job(result.job, replayed=result.replayed, published=result.published)


@router.get("/{job_id}", response_model=IngestionJobResponse)
async def get_status(
    job_id: UUID, principal: Annotated[ApiPrincipal, Depends(require_admin)], request: Request
) -> IngestionJobResponse:
    _, _, get_job, _ = _services(request)
    try:
        job = await get_job.execute(organization_id=principal.organization_id, job_id=job_id)
    except IngestionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _job(job, include_items=True)


@router.get("/{job_id}/items", response_model=list[IngestionItemResponse])
async def get_items(
    job_id: UUID,
    principal: Annotated[ApiPrincipal, Depends(require_admin)],
    request: Request,
    offset: int = 0,
    limit: int = 100,
) -> list[IngestionItemResponse]:
    if offset < 0 or limit < 1 or limit > 1000:
        raise HTTPException(status_code=422, detail="invalid pagination")
    _, _, _, list_items = _services(request)
    try:
        items = await list_items.execute(
            organization_id=principal.organization_id, job_id=job_id, offset=offset, limit=limit
        )
    except IngestionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [_item(item) for item in items]
