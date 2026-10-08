"""Tenant-scoped administrative endpoints for knowledge version lifecycle operations."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from revops.application.dto import (
    CorpusRevision,
    KnowledgeAdminContext,
    KnowledgeDocumentVersion,
    KnowledgeRetrievalContext,
    RetrieveKnowledgeArgs,
    SubmitKnowledgeDocumentArgs,
    TaskKnowledgeContext,
)
from revops.application.use_cases.knowledge import (
    ActivateKnowledgeRevision,
    ConfirmKnowledgeDocument,
    GetKnowledgeVersion,
    KnowledgeConflictError,
    KnowledgeNotFoundError,
    ListKnowledgeVersions,
    RetireKnowledgeVersion,
    SubmitKnowledgeDocument,
)
from revops.application.use_cases.retrieve_knowledge import (
    EmbeddingSpaceIncompatibleError,
    KnowledgeRetrievalError,
    KnowledgeRetrievalProviderError,
    KnowledgeRetrievalStorageError,
    RetrieveKnowledge,
)
from revops.domain.errors import PolicyViolationError
from revops.domain.values.retrieval import RetrievalProvenance

from apps.api.auth import ApiPrincipal, get_current_principal, require_admin
from apps.api.dependencies import knowledge_uow_factory, retrieval_use_case
from apps.api.runtime import knowledge_services
from apps.api.schemas import (
    KnowledgeRetrievalOmittedResponse,
    KnowledgeRetrievalPassageResponse,
    KnowledgeRetrievalProvenanceResponse,
    KnowledgeRetrievalRequest,
    KnowledgeRetrievalResponse,
    KnowledgeRevisionResponse,
    KnowledgeVersionCreateRequest,
    KnowledgeVersionMetadataResponse,
    KnowledgeVersionResponse,
)

router = APIRouter(prefix="/v1/knowledge", tags=["knowledge"])


def _context(principal: ApiPrincipal) -> KnowledgeAdminContext:
    return KnowledgeAdminContext(
        actor_id=principal.user_id,
        organization_id=principal.organization_id,
        role="admin",
    )


def _version_metadata(version: KnowledgeDocumentVersion) -> KnowledgeVersionMetadataResponse:
    return KnowledgeVersionMetadataResponse(
        id=version.id,
        document_id=version.document_id,
        document_key=version.document.document_key,
        category=version.document.category,
        language=version.document.language,
        format=version.document.format,
        status=version.status.value,
        created_at=version.created_at,
        embedding_model=version.embedding_model,
        embedding_dimension=version.embedding_dimension,
        failure_code=version.failure_code,
    )


def _version(version: KnowledgeDocumentVersion) -> KnowledgeVersionResponse:
    return KnowledgeVersionResponse(
        **_version_metadata(version).model_dump(),
        content=version.document.content,
        metadata=dict(version.document.metadata),
    )


def _revision(revision: CorpusRevision) -> KnowledgeRevisionResponse:
    return KnowledgeRevisionResponse(
        id=revision.id,
        version_id=revision.version_id,
        manifest_hash=revision.manifest_hash,
        activated_by=revision.activated_by,
        created_at=revision.created_at,
    )


def _retrieval_provenance(
    provenance: RetrievalProvenance,
) -> KnowledgeRetrievalProvenanceResponse:
    return KnowledgeRetrievalProvenanceResponse(
        document_key=provenance.document_key,
        document_version_id=provenance.document_version_id,
        chunk_id=provenance.chunk_id,
        chunk_ordinal=provenance.chunk_ordinal,
        category=provenance.category,
        language=provenance.language,
        active_revision_id=provenance.active_revision_id,
    )


def _retrieval_response(result: TaskKnowledgeContext) -> KnowledgeRetrievalResponse:
    return KnowledgeRetrievalResponse(
        text=result.text,
        token_count=result.token_count,
        included=[
            KnowledgeRetrievalPassageResponse(
                text=passage.text,
                provenance=_retrieval_provenance(passage.provenance),
                score=passage.score.value,
            )
            for passage in result.included
        ],
        omitted=[
            KnowledgeRetrievalOmittedResponse(
                provenance=_retrieval_provenance(passage.provenance),
                score=passage.score.value,
                reason=passage.reason,
            )
            for passage in result.omitted
        ],
    )


def _services(
    request: Request,
) -> tuple[
    SubmitKnowledgeDocument,
    ConfirmKnowledgeDocument,
    GetKnowledgeVersion,
    ListKnowledgeVersions,
    RetireKnowledgeVersion,
    ActivateKnowledgeRevision,
]:
    return knowledge_services(
        uow_factory=knowledge_uow_factory(request), settings=request.app.state.settings
    )


def _not_found(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


def _conflict(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.post("/retrieve", response_model=KnowledgeRetrievalResponse)
async def retrieve_knowledge(
    payload: KnowledgeRetrievalRequest,
    principal: Annotated[ApiPrincipal, Depends(get_current_principal)],
    use_case: Annotated[RetrieveKnowledge, Depends(retrieval_use_case)],
) -> KnowledgeRetrievalResponse:
    """Retrieve only the authenticated tenant's active task context."""
    try:
        result = await use_case.execute(
            context=KnowledgeRetrievalContext(organization_id=principal.organization_id),
            args=RetrieveKnowledgeArgs(**payload.model_dump()),
        )
    except PolicyViolationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    except EmbeddingSpaceIncompatibleError as exc:
        raise _conflict(exc) from exc
    except KnowledgeRetrievalProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=exc.failure_code,
        ) from exc
    except KnowledgeRetrievalStorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=exc.failure_code,
        ) from exc
    except KnowledgeRetrievalError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="retrieval unavailable",
        ) from exc
    return _retrieval_response(result)


@router.post(
    "/versions", response_model=KnowledgeVersionResponse, status_code=status.HTTP_201_CREATED
)
async def create_version(
    payload: KnowledgeVersionCreateRequest,
    principal: Annotated[ApiPrincipal, Depends(require_admin)],
    request: Request,
    response: Response,
    idempotency_key: Annotated[str, Header(min_length=1, max_length=128, alias="Idempotency-Key")],
) -> KnowledgeVersionResponse:
    submit, *_ = _services(request)
    try:
        result = await submit.execute(
            context=_context(principal),
            args=SubmitKnowledgeDocumentArgs.model_validate(payload.model_dump()),
            idempotency_key=idempotency_key,
        )
    except PolicyViolationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except KnowledgeConflictError as exc:
        raise _conflict(exc) from exc
    if result.replayed:
        response.status_code = status.HTTP_200_OK
    return _version(result)


@router.get("/versions", response_model=list[KnowledgeVersionMetadataResponse])
async def list_versions(
    principal: Annotated[ApiPrincipal, Depends(require_admin)],
    request: Request,
    offset: int = 0,
    limit: int = 100,
) -> list[KnowledgeVersionMetadataResponse]:
    if offset < 0 or not 0 < limit <= 100:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="invalid pagination"
        )
    *_, list_use_case, _, _ = _services(request)
    try:
        versions = await list_use_case.execute(
            context=_context(principal), offset=offset, limit=limit
        )
    except KnowledgeNotFoundError as exc:
        raise _not_found(exc) from exc
    return [_version_metadata(version) for version in versions]


@router.get("/versions/{version_id}", response_model=KnowledgeVersionResponse)
async def get_version(
    version_id: UUID,
    principal: Annotated[ApiPrincipal, Depends(require_admin)],
    request: Request,
) -> KnowledgeVersionResponse:
    _, _, get_use_case, *_ = _services(request)
    try:
        version = await get_use_case.execute(context=_context(principal), version_id=version_id)
    except KnowledgeNotFoundError as exc:
        raise _not_found(exc) from exc
    return _version(version)


@router.post("/versions/{version_id}/confirm", response_model=KnowledgeVersionResponse)
async def confirm_version(
    version_id: UUID,
    principal: Annotated[ApiPrincipal, Depends(require_admin)],
    request: Request,
) -> KnowledgeVersionResponse:
    _, confirm, *_ = _services(request)
    try:
        version = await confirm.execute(context=_context(principal), version_id=version_id)
    except KnowledgeNotFoundError as exc:
        raise _not_found(exc) from exc
    except KnowledgeConflictError as exc:
        raise _conflict(exc) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="dispatch failed"
        ) from exc
    return _version(version)


@router.post("/versions/{version_id}/retire", response_model=KnowledgeVersionResponse)
async def retire_version(
    version_id: UUID,
    principal: Annotated[ApiPrincipal, Depends(require_admin)],
    request: Request,
) -> KnowledgeVersionResponse:
    *_, retire, _ = _services(request)
    try:
        version = await retire.execute(context=_context(principal), version_id=version_id)
    except KnowledgeNotFoundError as exc:
        raise _not_found(exc) from exc
    except KnowledgeConflictError as exc:
        raise _conflict(exc) from exc
    return _version(version)


@router.post("/revisions/{revision_id}/activate", response_model=KnowledgeRevisionResponse)
async def activate_revision(
    revision_id: UUID,
    principal: Annotated[ApiPrincipal, Depends(require_admin)],
    request: Request,
    idempotency_key: Annotated[str, Header(min_length=1, max_length=128, alias="Idempotency-Key")],
) -> KnowledgeRevisionResponse:
    *_, activate = _services(request)
    try:
        revision = await activate.execute(
            context=_context(principal),
            revision_id=revision_id,
            idempotency_key=idempotency_key,
        )
    except KnowledgeNotFoundError as exc:
        raise _not_found(exc) from exc
    except KnowledgeConflictError as exc:
        raise _conflict(exc) from exc
    return _revision(revision)
