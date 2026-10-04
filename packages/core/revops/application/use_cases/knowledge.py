"""Application orchestration for the versioned knowledge lifecycle."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Final
from uuid import NAMESPACE_URL, UUID, uuid5

from revops.application.dto import (
    CorpusRevision,
    KnowledgeAdminContext,
    KnowledgeChunkEmbedding,
    KnowledgeDocumentVersion,
    KnowledgeProcessingEvent,
    KnowledgeProcessingEventType,
    PlatformSeedDocument,
    SubmitKnowledgeDocumentArgs,
)
from revops.application.ports import (
    Clock,
    EmbeddingProvider,
    EmbeddingProviderError,
    KnowledgeJobDispatcher,
    KnowledgeUnitOfWork,
    KnowledgeUnitOfWorkFactory,
)
from revops.domain.entities.knowledge import (
    KnowledgeChunk,
    KnowledgeScope,
    KnowledgeVersionState,
    KnowledgeVersionStatus,
    chunk_content,
)
from revops.domain.errors import InvalidTransitionError

EMBEDDING_BATCH_SIZE = 64
PLATFORM_SEED_ACTOR_ID = UUID("928f8683-f542-550e-a13c-8e770ef19a57")
PLATFORM_SEED_MAX_REVISION: Final = 2_147_483_647


class KnowledgeLifecycleError(RuntimeError):
    """Safe application-level error for a rejected lifecycle operation."""


class KnowledgeNotFoundError(KnowledgeLifecycleError):
    """A tenant-scoped resource was not found."""


class KnowledgeConflictError(KnowledgeLifecycleError):
    """A request conflicts with idempotency or lifecycle state."""


class KnowledgeProcessingError(KnowledgeLifecycleError):
    """Safe processing failure carrying only a bounded code and retry classification."""

    def __init__(self, failure_code: str, *, retryable: bool) -> None:
        self.failure_code = failure_code[:128]
        self.retryable = retryable
        super().__init__(self.failure_code)


def validate_platform_seed_manifest(
    manifest: tuple[PlatformSeedDocument, ...],
) -> tuple[tuple[PlatformSeedDocument, tuple[KnowledgeChunk, ...]], ...]:
    """Validate all trusted entries before a seed loader opens a transaction.

    The seed source is code-reviewed, but this boundary still makes malformed edits fail before
    any database reservation or broker dispatch.  Chunking is intentionally performed here so
    the full source, rather than only a worker delivery, is subject to ingestion limits.
    """
    if not manifest:
        raise KnowledgeConflictError("platform_seed_manifest_empty")
    validated: list[tuple[PlatformSeedDocument, tuple[KnowledgeChunk, ...]]] = []
    seen: set[str] = set()
    for item in sorted(manifest, key=lambda candidate: candidate.document_key):
        if item.document_key in seen:
            raise KnowledgeConflictError("platform_seed_duplicate_document_key")
        seen.add(item.document_key)
        if (
            not isinstance(item.revision, int)
            or isinstance(item.revision, bool)
            or not 0 < item.revision <= PLATFORM_SEED_MAX_REVISION
        ):
            raise KnowledgeConflictError("platform_seed_revision_invalid")
        document = item.to_domain()
        if document.content_hash != item.content_hash:
            raise KnowledgeConflictError("platform_seed_content_hash_mismatch")
        validated.append((item, chunk_content(document.content)))
    return tuple(validated)


def _platform_seed_idempotency_key(document_key: str, revision: int) -> str:
    """Return the approved bounded key without placing document content in persistence."""
    document_hash = hashlib.sha256(document_key.encode("utf-8")).hexdigest()
    return f"platform-seed:v1:{document_hash}:{revision}"


def _same_platform_seed_payload(
    version: KnowledgeDocumentVersion, item: PlatformSeedDocument
) -> bool:
    """Compare every immutable seed field, never merely its content hash."""
    return (
        version.seed_revision == item.revision
        and version.document == item.to_domain()
        and version.document.scope is KnowledgeScope.PLATFORM
    )


@dataclass(frozen=True, slots=True)
class PlatformSeedResult:
    """Safe deployment result: counts and identifiers only, never source content."""

    corpus_id: UUID
    reserved_version_ids: tuple[UUID, ...]
    redispatched_version_ids: tuple[UUID, ...]
    ready_version_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class SeedPlatformKnowledge:
    """Stage approved platform seed versions atomically and dispatch only after commit."""

    uow_factory: KnowledgeUnitOfWorkFactory
    dispatcher: KnowledgeJobDispatcher
    clock: Clock

    async def execute(self, *, manifest: tuple[PlatformSeedDocument, ...]) -> PlatformSeedResult:
        validated = validate_platform_seed_manifest(manifest)
        dispatch_ids: list[UUID] = []
        reserved_ids: list[UUID] = []
        ready_ids: list[UUID] = []
        async with self.uow_factory() as uow:
            corpus = await uow.corpora.get_or_create_platform_for_update()
            if corpus.scope is not KnowledgeScope.PLATFORM or corpus.organization_id is not None:
                raise KnowledgeConflictError("platform_corpus_ownership_invalid")
            for item, _ in validated:
                latest = await uow.documents.get_latest_seed_version(corpus.id, item.document_key)
                if latest is not None:
                    if latest.seed_revision is None:
                        raise KnowledgeConflictError("platform_seed_revision_missing")
                    if item.revision < latest.seed_revision:
                        raise KnowledgeConflictError("platform_seed_revision_conflict")
                    if item.revision == latest.seed_revision:
                        if not _same_platform_seed_payload(latest, item):
                            raise KnowledgeConflictError("platform_seed_payload_conflict")
                        if latest.status is KnowledgeVersionStatus.DRAFT:
                            _transition(latest, KnowledgeVersionStatus.CONFIRMED)
                            latest = await uow.documents.transition_status(
                                corpus_id=corpus.id,
                                version_id=latest.id,
                                status=KnowledgeVersionStatus.CONFIRMED,
                            )
                            dispatch_ids.append(latest.id)
                        elif latest.status in {
                            KnowledgeVersionStatus.CONFIRMED,
                            KnowledgeVersionStatus.PROCESSING,
                        }:
                            dispatch_ids.append(latest.id)
                        elif latest.status is KnowledgeVersionStatus.READY:
                            ready_ids.append(latest.id)
                        else:
                            raise KnowledgeConflictError("platform_seed_revision_terminal")
                        continue
                    if latest.status not in {
                        KnowledgeVersionStatus.READY,
                        KnowledgeVersionStatus.FAILED,
                        KnowledgeVersionStatus.RETIRED,
                    }:
                        raise KnowledgeConflictError("seed_revision_in_progress")
                version = await uow.documents.reserve_platform_draft(
                    corpus_id=corpus.id,
                    requested_by_system=PLATFORM_SEED_ACTOR_ID,
                    document=item.to_domain(),
                    seed_revision=item.revision,
                    idempotency_key=_platform_seed_idempotency_key(
                        item.document_key, item.revision
                    ),
                    created_at=self.clock.now(),
                )
                _transition(version, KnowledgeVersionStatus.CONFIRMED)
                confirmed = await uow.documents.transition_status(
                    corpus_id=corpus.id,
                    version_id=version.id,
                    status=KnowledgeVersionStatus.CONFIRMED,
                )
                reserved_ids.append(confirmed.id)
                dispatch_ids.append(confirmed.id)
            await uow.commit()
        for version_id in dispatch_ids:
            await self.dispatcher.publish(corpus_id=corpus.id, version_id=version_id)
        return PlatformSeedResult(
            corpus_id=corpus.id,
            reserved_version_ids=tuple(reserved_ids),
            redispatched_version_ids=tuple(dispatch_ids),
            ready_version_ids=tuple(ready_ids),
        )


def _processing_event_id(
    corpus_id: UUID,
    version_id: UUID,
    delivery_id: str,
    attempt: int,
    event_type: KnowledgeProcessingEventType,
) -> UUID:
    identity = f"{corpus_id}:{version_id}:{delivery_id}:{attempt}:{event_type.value}"
    return uuid5(NAMESPACE_URL, f"revops:knowledge-processing:{identity}")


def _event(
    *,
    corpus_id: UUID,
    version_id: UUID,
    delivery_id: str,
    attempt: int,
    event_type: KnowledgeProcessingEventType,
    occurred_at: datetime,
    failure_code: str | None = None,
    retryable: bool = False,
) -> KnowledgeProcessingEvent:
    return KnowledgeProcessingEvent(
        id=_processing_event_id(corpus_id, version_id, delivery_id, attempt, event_type),
        corpus_id=corpus_id,
        version_id=version_id,
        delivery_id=delivery_id[:128],
        attempt=attempt,
        event_type=event_type,
        retryable=retryable,
        failure_code=failure_code[:128] if failure_code else None,
        occurred_at=occurred_at,
    )


async def _organization_corpus(uow: KnowledgeUnitOfWork, context: KnowledgeAdminContext) -> UUID:
    try:
        corpus = await uow.corpora.get_organization(context.organization_id)
    except LookupError as exc:
        raise KnowledgeNotFoundError("organization knowledge corpus was not found") from exc
    if (
        corpus.scope is not KnowledgeScope.ORGANIZATION
        or corpus.organization_id != context.organization_id
    ):
        raise KnowledgeConflictError("organization corpus ownership is invalid")
    return corpus.id


async def _version_for_context(
    uow: KnowledgeUnitOfWork, context: KnowledgeAdminContext, version_id: UUID
) -> tuple[UUID, KnowledgeDocumentVersion]:
    corpus_id = await _organization_corpus(uow, context)
    version = await uow.documents.get_version(corpus_id, version_id)
    if version is None:
        raise KnowledgeNotFoundError("knowledge version was not found")
    return corpus_id, version


def _transition(version: KnowledgeDocumentVersion, target: KnowledgeVersionStatus) -> None:
    state = KnowledgeVersionState(version.status)
    try:
        if target is KnowledgeVersionStatus.CONFIRMED:
            state.confirm()
        elif target is KnowledgeVersionStatus.PROCESSING:
            state.begin_processing()
        elif target is KnowledgeVersionStatus.READY:
            state.mark_ready()
        elif target is KnowledgeVersionStatus.FAILED:
            state.mark_failed()
        elif target is KnowledgeVersionStatus.RETIRED:
            state.retire()
        else:
            raise KnowledgeConflictError("unsupported lifecycle transition")
    except InvalidTransitionError as exc:
        raise KnowledgeConflictError(str(exc)) from exc


@dataclass(frozen=True, slots=True)
class SubmitKnowledgeDocument:
    uow_factory: KnowledgeUnitOfWorkFactory
    clock: Clock

    async def execute(
        self,
        *,
        context: KnowledgeAdminContext,
        args: SubmitKnowledgeDocumentArgs,
        idempotency_key: str,
    ) -> KnowledgeDocumentVersion:
        if not idempotency_key.strip():
            raise KnowledgeLifecycleError("Idempotency-Key is required")
        async with self.uow_factory() as uow:
            corpus_id = await _organization_corpus(uow, context)
            document = args.to_domain()
            existing = await uow.documents.get_by_idempotency_key(corpus_id, idempotency_key)
            if existing is not None and existing.document != document:
                raise KnowledgeConflictError(
                    "knowledge idempotency key conflicts with document payload"
                )
            try:
                version = await uow.documents.reserve_draft(
                    corpus_id=corpus_id,
                    requested_by=context.actor_id,
                    document=document,
                    idempotency_key=idempotency_key,
                    created_at=self.clock.now(),
                )
            except ValueError as exc:
                raise KnowledgeConflictError(str(exc)) from exc
            await uow.commit()
            return replace(version, replayed=existing is not None)


@dataclass(frozen=True, slots=True)
class GetKnowledgeVersion:
    """Read one organization-owned version without exposing another tenant's data."""

    uow_factory: KnowledgeUnitOfWorkFactory

    async def execute(
        self, *, context: KnowledgeAdminContext, version_id: UUID
    ) -> KnowledgeDocumentVersion:
        async with self.uow_factory() as uow:
            _, version = await _version_for_context(uow, context, version_id)
            return version


@dataclass(frozen=True, slots=True)
class ListKnowledgeVersions:
    """Read a bounded page of organization-owned version metadata."""

    uow_factory: KnowledgeUnitOfWorkFactory

    async def execute(
        self, *, context: KnowledgeAdminContext, offset: int, limit: int
    ) -> tuple[KnowledgeDocumentVersion, ...]:
        async with self.uow_factory() as uow:
            corpus_id = await _organization_corpus(uow, context)
            return tuple(await uow.documents.list_versions(corpus_id, offset=offset, limit=limit))


@dataclass(frozen=True, slots=True)
class ConfirmKnowledgeDocument:
    uow_factory: KnowledgeUnitOfWorkFactory
    dispatcher: KnowledgeJobDispatcher
    clock: Clock

    async def execute(
        self, *, context: KnowledgeAdminContext, version_id: UUID
    ) -> KnowledgeDocumentVersion:
        dispatch = False
        async with self.uow_factory() as uow:
            corpus_id, version = await _version_for_context(uow, context, version_id)
            if version.status is KnowledgeVersionStatus.DRAFT:
                _transition(version, KnowledgeVersionStatus.CONFIRMED)
                confirmed = await uow.documents.transition_status(
                    corpus_id=corpus_id,
                    version_id=version.id,
                    status=KnowledgeVersionStatus.CONFIRMED,
                )
                await uow.commit()
                dispatch = True
            elif version.status in {
                KnowledgeVersionStatus.CONFIRMED,
                KnowledgeVersionStatus.PROCESSING,
            }:
                confirmed = version
                dispatch = True
            else:
                return version
        if dispatch:
            await self.dispatcher.publish(corpus_id=corpus_id, version_id=version_id)
        return confirmed


@dataclass(frozen=True, slots=True)
class ProcessKnowledgeDocument:
    uow_factory: KnowledgeUnitOfWorkFactory
    embeddings: EmbeddingProvider
    clock: Clock

    async def execute(
        self, *, corpus_id: UUID, version_id: UUID, delivery_id: str, attempt: int
    ) -> KnowledgeDocumentVersion:
        if not delivery_id.strip() or attempt < 1:
            raise KnowledgeProcessingError("invalid_delivery_metadata", retryable=False)
        async with self.uow_factory() as uow:
            version = await uow.documents.get_version_for_update(corpus_id, version_id)
            if version is None:
                raise KnowledgeProcessingError("knowledge_version_not_found", retryable=False)
            if version.status in {
                KnowledgeVersionStatus.READY,
                KnowledgeVersionStatus.FAILED,
                KnowledgeVersionStatus.RETIRED,
            }:
                await uow.processing_events.append(
                    _event(
                        corpus_id=corpus_id,
                        version_id=version_id,
                        delivery_id=delivery_id,
                        attempt=attempt,
                        event_type=KnowledgeProcessingEventType.DUPLICATE_IGNORED,
                        occurred_at=self.clock.now(),
                    )
                )
                await uow.commit()
                return version
            if version.status is KnowledgeVersionStatus.CONFIRMED:
                _transition(version, KnowledgeVersionStatus.PROCESSING)
                version = await uow.documents.transition_status(
                    corpus_id=corpus_id,
                    version_id=version.id,
                    status=KnowledgeVersionStatus.PROCESSING,
                )
            elif version.status is not KnowledgeVersionStatus.PROCESSING:
                raise KnowledgeProcessingError("knowledge_version_not_processable", retryable=False)
            await uow.processing_events.append(
                _event(
                    corpus_id=corpus_id,
                    version_id=version_id,
                    delivery_id=delivery_id,
                    attempt=attempt,
                    event_type=KnowledgeProcessingEventType.STARTED,
                    occurred_at=self.clock.now(),
                )
            )
            await uow.commit()

        try:
            chunks = chunk_content(version.document.content)
            vectors: list[tuple[float, ...]] = []
            embedding_model: str | None = None
            embedding_dimension: int | None = None
            for start in range(0, len(chunks), EMBEDDING_BATCH_SIZE):
                batch = chunks[start : start + EMBEDDING_BATCH_SIZE]
                try:
                    embedded = await self.embeddings.embed(tuple(chunk.text for chunk in batch))
                except EmbeddingProviderError:
                    raise
                except Exception as exc:
                    raise KnowledgeProcessingError(
                        "embedding_provider_error", retryable=False
                    ) from exc
                if embedding_model is None:
                    embedding_model = embedded.model
                    embedding_dimension = embedded.dimension
                if (
                    embedded.model != embedding_model
                    or embedded.dimension != embedding_dimension
                    or embedded.dimension <= 0
                ):
                    raise KnowledgeProcessingError(
                        "embedding_metadata_inconsistent", retryable=False
                    )
                if embedded.vectors and embedded.dimension != len(embedded.vectors[0]):
                    raise KnowledgeProcessingError(
                        "embedding_dimension_inconsistent", retryable=False
                    )
                if len(embedded.vectors) != len(batch):
                    raise KnowledgeProcessingError("embedding_batch_invalid", retryable=False)
                vectors.extend(embedded.vectors)
            if len(vectors) != len(chunks):
                raise KnowledgeProcessingError("embedding_batch_incomplete", retryable=False)
            if embedding_model is None or embedding_dimension is None:
                raise KnowledgeProcessingError("embedding_batch_empty", retryable=False)
            prepared = tuple(
                KnowledgeChunkEmbedding(
                    ordinal=chunk.ordinal,
                    text=chunk.text,
                    content_hash=chunk.content_hash,
                    vector=tuple(vector),
                )
                for chunk, vector in zip(chunks, vectors, strict=True)
            )
        except EmbeddingProviderError as exc:
            raise KnowledgeProcessingError(exc.failure_code, retryable=exc.retryable) from exc

        async with self.uow_factory() as uow:
            current = await uow.documents.get_version_for_update(corpus_id, version_id)
            if current is None:
                raise KnowledgeProcessingError("knowledge_version_not_found", retryable=False)
            if current.status is KnowledgeVersionStatus.READY:
                await uow.processing_events.append(
                    _event(
                        corpus_id=corpus_id,
                        version_id=version_id,
                        delivery_id=delivery_id,
                        attempt=attempt,
                        event_type=KnowledgeProcessingEventType.DUPLICATE_IGNORED,
                        occurred_at=self.clock.now(),
                    )
                )
                await uow.commit()
                return current
            if current.status is not KnowledgeVersionStatus.PROCESSING:
                raise KnowledgeProcessingError("processing_state_changed", retryable=False)
            ready = await uow.documents.mark_ready(
                corpus_id=corpus_id,
                version_id=version_id,
                embedding_model=embedding_model,
                embedding_dimension=embedding_dimension,
            )
            await uow.revisions.publish(
                corpus_id=corpus_id,
                version_id=version_id,
                chunks=prepared,
                activated_by=current.requested_by,
                created_at=self.clock.now(),
            )
            await uow.processing_events.append(
                _event(
                    corpus_id=corpus_id,
                    version_id=version_id,
                    delivery_id=delivery_id,
                    attempt=attempt,
                    event_type=KnowledgeProcessingEventType.SUCCEEDED,
                    occurred_at=self.clock.now(),
                )
            )
            await uow.commit()
            return ready


@dataclass(frozen=True, slots=True)
class RecordKnowledgeProcessingFailure:
    uow_factory: KnowledgeUnitOfWorkFactory
    clock: Clock

    async def execute(
        self,
        *,
        corpus_id: UUID,
        version_id: UUID,
        delivery_id: str,
        attempt: int,
        failure_code: str,
        retryable: bool,
        terminal: bool,
    ) -> KnowledgeDocumentVersion:
        async with self.uow_factory() as uow:
            version = await uow.documents.get_version_for_update(corpus_id, version_id)
            if version is None:
                raise KnowledgeProcessingError("knowledge_version_not_found", retryable=False)
            if version.status in {
                KnowledgeVersionStatus.READY,
                KnowledgeVersionStatus.FAILED,
                KnowledgeVersionStatus.RETIRED,
            }:
                await uow.processing_events.append(
                    _event(
                        corpus_id=corpus_id,
                        version_id=version_id,
                        delivery_id=delivery_id,
                        attempt=attempt,
                        event_type=KnowledgeProcessingEventType.DUPLICATE_IGNORED,
                        occurred_at=self.clock.now(),
                        failure_code=failure_code,
                        retryable=retryable,
                    )
                )
                await uow.commit()
                return version
            if terminal and version.status is KnowledgeVersionStatus.CONFIRMED:
                _transition(version, KnowledgeVersionStatus.PROCESSING)
                await uow.documents.transition_status(
                    corpus_id=corpus_id,
                    version_id=version_id,
                    status=KnowledgeVersionStatus.PROCESSING,
                )
            event_type = KnowledgeProcessingEventType.RETRY_SCHEDULED
            if terminal:
                if version.status is KnowledgeVersionStatus.PROCESSING:
                    _transition(version, KnowledgeVersionStatus.FAILED)
                    version = await uow.documents.transition_status(
                        corpus_id=corpus_id,
                        version_id=version_id,
                        status=KnowledgeVersionStatus.FAILED,
                        failure_code=failure_code,
                    )
                event_type = KnowledgeProcessingEventType.FAILED
            await uow.processing_events.append(
                _event(
                    corpus_id=corpus_id,
                    version_id=version_id,
                    delivery_id=delivery_id,
                    attempt=attempt,
                    event_type=event_type,
                    occurred_at=self.clock.now(),
                    failure_code=failure_code,
                    retryable=retryable,
                )
            )
            await uow.commit()
            return version


@dataclass(frozen=True, slots=True)
class RetireKnowledgeVersion:
    uow_factory: KnowledgeUnitOfWorkFactory

    async def execute(
        self, *, context: KnowledgeAdminContext, version_id: UUID
    ) -> KnowledgeDocumentVersion:
        async with self.uow_factory() as uow:
            corpus_id, version = await _version_for_context(uow, context, version_id)
            _transition(version, KnowledgeVersionStatus.RETIRED)
            retired = await uow.documents.transition_status(
                corpus_id=corpus_id,
                version_id=version_id,
                status=KnowledgeVersionStatus.RETIRED,
            )
            await uow.commit()
            return retired


@dataclass(frozen=True, slots=True)
class ActivateKnowledgeRevision:
    uow_factory: KnowledgeUnitOfWorkFactory
    clock: Clock

    async def execute(
        self,
        *,
        context: KnowledgeAdminContext,
        revision_id: UUID,
        idempotency_key: str,
    ) -> CorpusRevision:
        if not idempotency_key.strip():
            raise KnowledgeLifecycleError("Idempotency-Key is required")
        async with self.uow_factory() as uow:
            corpus_id = await _organization_corpus(uow, context)
            try:
                revision = await uow.revisions.activate(
                    corpus_id=corpus_id,
                    revision_id=revision_id,
                    activated_by=context.actor_id,
                    idempotency_key=idempotency_key,
                    created_at=self.clock.now(),
                )
            except LookupError as exc:
                raise KnowledgeNotFoundError("knowledge revision was not found") from exc
            except ValueError as exc:
                raise KnowledgeConflictError(str(exc)) from exc
            await uow.commit()
            return revision
