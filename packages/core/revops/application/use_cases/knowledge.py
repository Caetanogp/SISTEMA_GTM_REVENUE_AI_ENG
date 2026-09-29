"""Application orchestration for the versioned knowledge lifecycle."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from revops.application.dto import (
    CorpusRevision,
    KnowledgeAdminContext,
    KnowledgeChunkEmbedding,
    KnowledgeDocumentVersion,
    SubmitKnowledgeDocumentArgs,
)
from revops.application.ports import (
    Clock,
    EmbeddingProvider,
    KnowledgeJobDispatcher,
    KnowledgeUnitOfWork,
    KnowledgeUnitOfWorkFactory,
)
from revops.domain.entities.knowledge import (
    KnowledgeScope,
    KnowledgeVersionState,
    KnowledgeVersionStatus,
    chunk_content,
)

EMBEDDING_BATCH_SIZE = 64


class KnowledgeLifecycleError(RuntimeError):
    """Safe application-level error for a rejected lifecycle operation."""


async def _organization_corpus(uow: KnowledgeUnitOfWork, context: KnowledgeAdminContext) -> UUID:
    corpus = await uow.corpora.get_organization(context.organization_id)
    if (
        corpus.scope is not KnowledgeScope.ORGANIZATION
        or corpus.organization_id != context.organization_id
    ):
        raise KnowledgeLifecycleError("organization corpus ownership is invalid")
    return corpus.id


async def _version_for_context(
    uow: KnowledgeUnitOfWork, context: KnowledgeAdminContext, version_id: UUID
) -> tuple[UUID, KnowledgeDocumentVersion]:
    corpus_id = await _organization_corpus(uow, context)
    version = await uow.documents.get_version(corpus_id, version_id)
    if version is None:
        raise KnowledgeLifecycleError("knowledge version was not found")
    return corpus_id, version


def _transition(version: KnowledgeDocumentVersion, target: KnowledgeVersionStatus) -> None:
    state = KnowledgeVersionState(version.status)
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
        raise KnowledgeLifecycleError("unsupported lifecycle transition")


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
            version = await uow.documents.reserve_draft(
                corpus_id=corpus_id,
                requested_by=context.actor_id,
                document=args.to_domain(),
                idempotency_key=idempotency_key,
                created_at=self.clock.now(),
            )
            await uow.commit()
            return version


@dataclass(frozen=True, slots=True)
class ConfirmKnowledgeDocument:
    uow_factory: KnowledgeUnitOfWorkFactory
    dispatcher: KnowledgeJobDispatcher
    clock: Clock

    async def execute(
        self, *, context: KnowledgeAdminContext, version_id: UUID
    ) -> KnowledgeDocumentVersion:
        async with self.uow_factory() as uow:
            corpus_id, version = await _version_for_context(uow, context, version_id)
            if version.status is not KnowledgeVersionStatus.DRAFT:
                return version
            _transition(version, KnowledgeVersionStatus.CONFIRMED)
            confirmed = await uow.documents.transition_status(
                corpus_id=corpus_id,
                version_id=version.id,
                status=KnowledgeVersionStatus.CONFIRMED,
            )
            await uow.commit()
        await self.dispatcher.publish(corpus_id=corpus_id, version_id=version_id)
        return confirmed


@dataclass(frozen=True, slots=True)
class ProcessKnowledgeDocument:
    uow_factory: KnowledgeUnitOfWorkFactory
    embeddings: EmbeddingProvider
    clock: Clock

    async def execute(
        self, *, context: KnowledgeAdminContext, version_id: UUID
    ) -> KnowledgeDocumentVersion:
        async with self.uow_factory() as uow:
            corpus_id, version = await _version_for_context(uow, context, version_id)
            if version.status is KnowledgeVersionStatus.READY:
                return version
            if version.status is KnowledgeVersionStatus.CONFIRMED:
                _transition(version, KnowledgeVersionStatus.PROCESSING)
                version = await uow.documents.transition_status(
                    corpus_id=corpus_id,
                    version_id=version.id,
                    status=KnowledgeVersionStatus.PROCESSING,
                )
                await uow.commit()
            elif version.status is not KnowledgeVersionStatus.PROCESSING:
                raise KnowledgeLifecycleError("knowledge version is not processable")
            else:
                await uow.commit()

        try:
            chunks = chunk_content(version.document.content)
            vectors: list[tuple[float, ...]] = []
            for start in range(0, len(chunks), EMBEDDING_BATCH_SIZE):
                batch = chunks[start : start + EMBEDDING_BATCH_SIZE]
                embedded = await self.embeddings.embed(tuple(chunk.text for chunk in batch))
                if embedded.vectors and embedded.dimension != len(embedded.vectors[0]):
                    raise KnowledgeLifecycleError("embedding dimension metadata is inconsistent")
                if len(embedded.vectors) != len(batch):
                    raise KnowledgeLifecycleError("embedding provider returned an invalid batch")
                vectors.extend(embedded.vectors)
            if len(vectors) != len(chunks):
                raise KnowledgeLifecycleError("embedding provider returned incomplete vectors")
            prepared = tuple(
                KnowledgeChunkEmbedding(
                    ordinal=chunk.ordinal,
                    text=chunk.text,
                    content_hash=chunk.content_hash,
                    vector=tuple(vector),
                )
                for chunk, vector in zip(chunks, vectors, strict=True)
            )
        except Exception as exc:
            await self._mark_failed(context, version_id, type(exc).__name__)
            raise

        async with self.uow_factory() as uow:
            corpus_id, current = await _version_for_context(uow, context, version_id)
            if current.status is not KnowledgeVersionStatus.PROCESSING:
                raise KnowledgeLifecycleError("knowledge version changed during processing")
            _transition(current, KnowledgeVersionStatus.READY)
            await uow.documents.transition_status(
                corpus_id=corpus_id,
                version_id=version_id,
                status=KnowledgeVersionStatus.READY,
            )
            try:
                await uow.revisions.publish(
                    corpus_id=corpus_id,
                    version_id=version_id,
                    chunks=prepared,
                    activated_by=context.actor_id,
                    created_at=self.clock.now(),
                )
                await uow.commit()
            except Exception as exc:
                await uow.rollback()
                await self._mark_failed(context, version_id, type(exc).__name__)
                raise
        return await self._get_version(context, version_id)

    async def _get_version(
        self, context: KnowledgeAdminContext, version_id: UUID
    ) -> KnowledgeDocumentVersion:
        async with self.uow_factory() as uow:
            _, version = await _version_for_context(uow, context, version_id)
            return version

    async def _mark_failed(
        self, context: KnowledgeAdminContext, version_id: UUID, failure_code: str
    ) -> None:
        async with self.uow_factory() as uow:
            corpus_id, version = await _version_for_context(uow, context, version_id)
            if version.status is KnowledgeVersionStatus.PROCESSING:
                await uow.documents.transition_status(
                    corpus_id=corpus_id,
                    version_id=version_id,
                    status=KnowledgeVersionStatus.FAILED,
                    failure_code=failure_code[:128],
                )
                await uow.commit()


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
            revision = await uow.revisions.activate(
                corpus_id=corpus_id,
                revision_id=revision_id,
                activated_by=context.actor_id,
                idempotency_key=idempotency_key,
                created_at=self.clock.now(),
            )
            await uow.commit()
            return revision
