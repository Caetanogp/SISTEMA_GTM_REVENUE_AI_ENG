"""SQLAlchemy adapters for corpus-scoped knowledge persistence."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import datetime
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from revops.application.dto import (
    CorpusRevision,
    KnowledgeActivationAction,
    KnowledgeChunkEmbedding,
    KnowledgeCorpus,
    KnowledgeDocumentVersion,
    KnowledgeProcessingEvent,
    KnowledgeRevisionActivation,
)
from revops.domain.entities.knowledge import (
    KnowledgeCategory,
    KnowledgeDocument,
    KnowledgeFormat,
    KnowledgeLanguage,
    KnowledgeScope,
    KnowledgeVersionStatus,
)
from revops.infrastructure.persistence.models import (
    KnowledgeChunk as KnowledgeChunkModel,
)
from revops.infrastructure.persistence.models import (
    KnowledgeCorpus as KnowledgeCorpusModel,
)
from revops.infrastructure.persistence.models import (
    KnowledgeCorpusHead,
)
from revops.infrastructure.persistence.models import (
    KnowledgeDocument as KnowledgeDocumentModel,
)
from revops.infrastructure.persistence.models import (
    KnowledgeDocumentVersion as KnowledgeDocumentVersionModel,
)
from revops.infrastructure.persistence.models import (
    KnowledgeProcessingEvent as KnowledgeProcessingEventModel,
)
from revops.infrastructure.persistence.models import (
    KnowledgeRevision as KnowledgeRevisionModel,
)
from revops.infrastructure.persistence.models import (
    KnowledgeRevisionActivation as KnowledgeRevisionActivationModel,
)
from revops.infrastructure.persistence.models import (
    KnowledgeRevisionEntry as KnowledgeRevisionEntryModel,
)


def _corpus(row: KnowledgeCorpusModel) -> KnowledgeCorpus:
    return KnowledgeCorpus(row.id, KnowledgeScope(row.scope), row.organization_id)


def _version(row: KnowledgeDocumentVersionModel, document_key: str) -> KnowledgeDocumentVersion:
    return KnowledgeDocumentVersion(
        id=row.id,
        document_id=row.document_id,
        corpus_id=row.corpus_id,
        requested_by=row.requested_by,
        document=KnowledgeDocument(
            document_key=document_key,
            category=KnowledgeCategory(row.category),
            language=KnowledgeLanguage(row.language),
            format=KnowledgeFormat(row.format),
            scope=KnowledgeScope(row.scope),
            content=row.content,
            metadata=cast(dict[str, str | int | float | bool | None], row.metadata_),
        ),
        status=KnowledgeVersionStatus(row.status),
        idempotency_key=row.idempotency_key,
        created_at=row.created_at,
        embedding_model=row.embedding_model,
        embedding_dimension=row.embedding_dimension,
        failure_code=row.failure_code,
    )


def _revision(row: KnowledgeRevisionModel) -> CorpusRevision:
    return CorpusRevision(
        row.id, row.corpus_id, row.version_id, row.manifest_hash, row.activated_by, row.created_at
    )


def _manifest(entries: dict[str, UUID]) -> str:
    payload = {
        "version": 1,
        "entries": [[key, str(entries[key])] for key in sorted(entries)],
    }
    return hashlib.sha256(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()


class SqlAlchemyKnowledgeDocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _row(
        self, corpus_id: UUID, version_id: UUID, *, for_update: bool = False
    ) -> KnowledgeDocumentVersionModel | None:
        query = (
            select(KnowledgeDocumentVersionModel)
            .join(KnowledgeDocumentModel)
            .where(
                KnowledgeDocumentVersionModel.corpus_id == corpus_id,
                KnowledgeDocumentVersionModel.id == version_id,
                KnowledgeDocumentModel.corpus_id == corpus_id,
            )
        )
        if for_update:
            query = query.with_for_update()
        return (await self._session.execute(query)).scalar_one_or_none()

    async def _to_version(self, row: KnowledgeDocumentVersionModel) -> KnowledgeDocumentVersion:
        key = await self._session.scalar(
            select(KnowledgeDocumentModel.document_key).where(
                KnowledgeDocumentModel.id == row.document_id,
                KnowledgeDocumentModel.corpus_id == row.corpus_id,
            )
        )
        if key is None:
            raise LookupError("knowledge document not found in corpus")
        return _version(row, key)

    async def get_version(
        self, corpus_id: UUID, version_id: UUID
    ) -> KnowledgeDocumentVersion | None:
        row = await self._row(corpus_id, version_id)
        return None if row is None else await self._to_version(row)

    async def get_version_for_update(
        self, corpus_id: UUID, version_id: UUID
    ) -> KnowledgeDocumentVersion | None:
        row = await self._row(corpus_id, version_id, for_update=True)
        return None if row is None else await self._to_version(row)

    async def get_by_idempotency_key(
        self, corpus_id: UUID, idempotency_key: str
    ) -> KnowledgeDocumentVersion | None:
        row = (
            await self._session.execute(
                select(KnowledgeDocumentVersionModel).where(
                    KnowledgeDocumentVersionModel.corpus_id == corpus_id,
                    KnowledgeDocumentVersionModel.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one_or_none()
        return None if row is None else await self._to_version(row)

    async def reserve_draft(
        self,
        *,
        corpus_id: UUID,
        requested_by: UUID,
        document: KnowledgeDocument,
        idempotency_key: str,
        created_at: datetime,
    ) -> KnowledgeDocumentVersion:
        existing = await self.get_by_idempotency_key(corpus_id, idempotency_key)
        if existing is not None:
            if existing.document != document:
                raise ValueError("knowledge idempotency key conflicts with document payload")
            return existing
        document_row = (
            await self._session.execute(
                select(KnowledgeDocumentModel).where(
                    KnowledgeDocumentModel.corpus_id == corpus_id,
                    KnowledgeDocumentModel.document_key == document.document_key,
                )
            )
        ).scalar_one_or_none()
        if document_row is None:
            document_row = KnowledgeDocumentModel(
                id=uuid4(),
                corpus_id=corpus_id,
                document_key=document.document_key,
                created_at=created_at,
            )
            self._session.add(document_row)
            await self._session.flush()
        row = KnowledgeDocumentVersionModel(
            id=uuid4(),
            document_id=document_row.id,
            corpus_id=corpus_id,
            requested_by=requested_by,
            category=document.category.value,
            language=document.language.value,
            format=document.format.value,
            scope=document.scope.value,
            content=document.content,
            metadata_=dict(document.metadata),
            content_hash=document.content_hash,
            status=KnowledgeVersionStatus.DRAFT.value,
            idempotency_key=idempotency_key,
            created_at=created_at,
            updated_at=created_at,
        )
        self._session.add(row)
        await self._session.flush()
        return _version(row, document.document_key)

    async def transition_status(
        self,
        *,
        corpus_id: UUID,
        version_id: UUID,
        status: KnowledgeVersionStatus,
        failure_code: str | None = None,
    ) -> KnowledgeDocumentVersion:
        row = await self._row(corpus_id, version_id)
        if row is None:
            raise LookupError("knowledge version not found in corpus")
        row.status = status.value
        row.failure_code = failure_code
        await self._session.flush()
        return await self._to_version(row)

    async def mark_ready(
        self,
        *,
        corpus_id: UUID,
        version_id: UUID,
        embedding_model: str,
        embedding_dimension: int,
    ) -> KnowledgeDocumentVersion:
        row = await self._row(corpus_id, version_id, for_update=True)
        if row is None:
            raise LookupError("knowledge version not found in corpus")
        row.status = KnowledgeVersionStatus.READY.value
        row.embedding_model = embedding_model
        row.embedding_dimension = embedding_dimension
        row.failure_code = None
        await self._session.flush()
        return await self._to_version(row)

    async def list_versions(
        self, corpus_id: UUID, *, offset: int, limit: int
    ) -> Sequence[KnowledgeDocumentVersion]:
        rows = (
            (
                await self._session.execute(
                    select(KnowledgeDocumentVersionModel)
                    .where(KnowledgeDocumentVersionModel.corpus_id == corpus_id)
                    .order_by(
                        KnowledgeDocumentVersionModel.created_at, KnowledgeDocumentVersionModel.id
                    )
                    .offset(offset)
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        return tuple([await self._to_version(row) for row in rows])


class SqlAlchemyKnowledgeCorpusRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_platform(self) -> KnowledgeCorpus:
        row = (
            await self._session.execute(
                select(KnowledgeCorpusModel).where(
                    KnowledgeCorpusModel.scope == KnowledgeScope.PLATFORM.value
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise LookupError("platform knowledge corpus not found")
        return _corpus(row)

    async def get_organization(self, organization_id: UUID) -> KnowledgeCorpus:
        row = (
            await self._session.execute(
                select(KnowledgeCorpusModel).where(
                    KnowledgeCorpusModel.scope == KnowledgeScope.ORGANIZATION.value,
                    KnowledgeCorpusModel.organization_id == organization_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise LookupError("organization knowledge corpus not found")
        return _corpus(row)


class SqlAlchemyKnowledgeProcessingEventRepository:
    """Persist sanitized processing facts without update or delete operations."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(self, event: KnowledgeProcessingEvent) -> None:
        statement = insert(KnowledgeProcessingEventModel).values(
            id=event.id,
            corpus_id=event.corpus_id,
            version_id=event.version_id,
            delivery_id=event.delivery_id,
            attempt=event.attempt,
            event_type=event.event_type.value,
            retryable=event.retryable,
            failure_code=event.failure_code,
            occurred_at=event.occurred_at,
        )
        await self._session.execute(statement.on_conflict_do_nothing(index_elements=["id"]))


class SqlAlchemyCorpusRevisionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _lock_corpus(self, corpus_id: UUID) -> None:
        if (
            await self._session.execute(
                select(KnowledgeCorpusModel)
                .where(KnowledgeCorpusModel.id == corpus_id)
                .with_for_update()
            )
        ).scalar_one_or_none() is None:
            raise LookupError("knowledge corpus not found")

    async def _entries(self, revision_id: UUID, corpus_id: UUID) -> dict[str, UUID]:
        rows = (
            (
                await self._session.execute(
                    select(KnowledgeRevisionEntryModel).where(
                        KnowledgeRevisionEntryModel.revision_id == revision_id,
                        KnowledgeRevisionEntryModel.corpus_id == corpus_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        return {row.document_key: row.version_id for row in rows}

    async def _revision_for_entries(
        self, corpus_id: UUID, entries: dict[str, UUID], actor: UUID, created_at: datetime
    ) -> KnowledgeRevisionModel:
        digest = _manifest(entries)
        revision = (
            await self._session.execute(
                select(KnowledgeRevisionModel).where(
                    KnowledgeRevisionModel.corpus_id == corpus_id,
                    KnowledgeRevisionModel.manifest_hash == digest,
                )
            )
        ).scalar_one_or_none()
        if revision is not None:
            if await self._entries(revision.id, corpus_id) != entries:
                raise ValueError("knowledge manifest hash collision or corrupted entries")
            return revision
        revision = KnowledgeRevisionModel(
            id=uuid4(),
            corpus_id=corpus_id,
            version_id=entries[sorted(entries)[0]],
            manifest_hash=digest,
            activated_by=actor,
            created_at=created_at,
        )
        self._session.add(revision)
        await self._session.flush()
        self._session.add_all(
            [
                KnowledgeRevisionEntryModel(
                    id=uuid4(),
                    corpus_id=corpus_id,
                    revision_id=revision.id,
                    document_key=key,
                    version_id=version_id,
                )
                for key, version_id in entries.items()
            ]
        )
        await self._session.flush()
        return revision

    async def _activate(
        self,
        *,
        corpus_id: UUID,
        version_id: UUID,
        actor: UUID,
        created_at: datetime,
        idempotency_key: str,
        action: KnowledgeActivationAction,
    ) -> CorpusRevision:
        await self._lock_corpus(corpus_id)
        version = (
            await self._session.execute(
                select(KnowledgeDocumentVersionModel, KnowledgeDocumentModel.document_key)
                .join(
                    KnowledgeDocumentModel,
                    KnowledgeDocumentModel.id == KnowledgeDocumentVersionModel.document_id,
                )
                .where(
                    KnowledgeDocumentVersionModel.id == version_id,
                    KnowledgeDocumentVersionModel.corpus_id == corpus_id,
                )
            )
        ).one_or_none()
        if version is None:
            raise LookupError("knowledge version not found in corpus")
        version_row, key = version
        if version_row.status != KnowledgeVersionStatus.READY.value:
            raise ValueError("only ready knowledge versions can be activated")
        existing_event = (
            await self._session.execute(
                select(KnowledgeRevisionActivationModel).where(
                    KnowledgeRevisionActivationModel.corpus_id == corpus_id,
                    KnowledgeRevisionActivationModel.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one_or_none()
        if existing_event is not None:
            if existing_event.target_version_id != version_id:
                raise ValueError("knowledge activation idempotency key conflicts")
            revision = await self._session.get(KnowledgeRevisionModel, existing_event.revision_id)
            if revision is None:
                raise LookupError("activation revision not found")
            return _revision(revision)
        head = (
            await self._session.execute(
                select(KnowledgeCorpusHead).where(KnowledgeCorpusHead.corpus_id == corpus_id)
            )
        ).scalar_one_or_none()
        entries = {} if head is None else await self._entries(head.revision_id, corpus_id)
        entries[key] = version_row.id
        revision = await self._revision_for_entries(corpus_id, entries, actor, created_at)
        self._session.add(
            KnowledgeRevisionActivationModel(
                id=uuid4(),
                corpus_id=corpus_id,
                revision_id=revision.id,
                target_version_id=version_id,
                action=action.value,
                activated_by=actor,
                idempotency_key=idempotency_key,
                created_at=created_at,
            )
        )
        await self._session.flush()
        await self._session.execute(
            insert(KnowledgeCorpusHead)
            .values(corpus_id=corpus_id, revision_id=revision.id, updated_at=created_at)
            .on_conflict_do_update(
                index_elements=["corpus_id"],
                set_={"revision_id": revision.id, "updated_at": created_at},
            )
        )
        await self._session.flush()
        return _revision(revision)

    async def publish(
        self,
        *,
        corpus_id: UUID,
        version_id: UUID,
        chunks: Sequence[KnowledgeChunkEmbedding],
        activated_by: UUID,
        created_at: datetime,
    ) -> CorpusRevision:
        if not chunks:
            raise ValueError("knowledge publication requires at least one chunk")
        await self._lock_corpus(corpus_id)
        publication_key = f"publication:{version_id}"
        existing_event = (
            await self._session.execute(
                select(KnowledgeRevisionActivationModel).where(
                    KnowledgeRevisionActivationModel.corpus_id == corpus_id,
                    KnowledgeRevisionActivationModel.idempotency_key == publication_key,
                )
            )
        ).scalar_one_or_none()
        if existing_event is not None:
            return await self._activate(
                corpus_id=corpus_id,
                version_id=version_id,
                actor=activated_by,
                created_at=created_at,
                idempotency_key=publication_key,
                action=KnowledgeActivationAction.PUBLICATION,
            )
        self._session.add_all(
            [
                KnowledgeChunkModel(
                    id=uuid4(),
                    corpus_id=corpus_id,
                    version_id=version_id,
                    ordinal=chunk.ordinal,
                    text=chunk.text,
                    content_hash=chunk.content_hash,
                    metadata_={},
                    embedding=list(chunk.vector),
                )
                for chunk in chunks
            ]
        )
        return await self._activate(
            corpus_id=corpus_id,
            version_id=version_id,
            actor=activated_by,
            created_at=created_at,
            idempotency_key=publication_key,
            action=KnowledgeActivationAction.PUBLICATION,
        )

    async def get_active(self, corpus_id: UUID) -> CorpusRevision | None:
        row = (
            await self._session.execute(
                select(KnowledgeRevisionModel)
                .join(
                    KnowledgeCorpusHead,
                    KnowledgeCorpusHead.revision_id == KnowledgeRevisionModel.id,
                )
                .where(KnowledgeCorpusHead.corpus_id == corpus_id)
            )
        ).scalar_one_or_none()
        return None if row is None else _revision(row)

    async def activate(
        self,
        *,
        corpus_id: UUID,
        revision_id: UUID,
        activated_by: UUID,
        idempotency_key: str,
        created_at: datetime,
    ) -> CorpusRevision:
        await self._lock_corpus(corpus_id)
        revision = (
            await self._session.execute(
                select(KnowledgeRevisionModel).where(
                    KnowledgeRevisionModel.id == revision_id,
                    KnowledgeRevisionModel.corpus_id == corpus_id,
                )
            )
        ).scalar_one_or_none()
        if revision is None:
            raise LookupError("knowledge revision not found in corpus")
        existing_event = (
            await self._session.execute(
                select(KnowledgeRevisionActivationModel).where(
                    KnowledgeRevisionActivationModel.corpus_id == corpus_id,
                    KnowledgeRevisionActivationModel.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one_or_none()
        if existing_event is not None:
            if existing_event.revision_id != revision.id:
                raise ValueError("knowledge activation idempotency key conflicts")
            return _revision(revision)
        self._session.add(
            KnowledgeRevisionActivationModel(
                id=uuid4(),
                corpus_id=corpus_id,
                revision_id=revision.id,
                target_version_id=revision.version_id,
                action=KnowledgeActivationAction.HISTORICAL_ACTIVATION.value,
                activated_by=activated_by,
                idempotency_key=idempotency_key,
                created_at=created_at,
            )
        )
        await self._session.flush()
        await self._session.execute(
            insert(KnowledgeCorpusHead)
            .values(corpus_id=corpus_id, revision_id=revision.id, updated_at=created_at)
            .on_conflict_do_update(
                index_elements=["corpus_id"],
                set_={"revision_id": revision.id, "updated_at": created_at},
            )
        )
        await self._session.flush()
        return _revision(revision)

    async def list_activation_history(
        self, corpus_id: UUID, *, offset: int, limit: int
    ) -> Sequence[KnowledgeRevisionActivation]:
        rows = (
            (
                await self._session.execute(
                    select(KnowledgeRevisionActivationModel)
                    .where(KnowledgeRevisionActivationModel.corpus_id == corpus_id)
                    .order_by(
                        KnowledgeRevisionActivationModel.created_at,
                        KnowledgeRevisionActivationModel.id,
                    )
                    .offset(offset)
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        return tuple(
            KnowledgeRevisionActivation(
                row.id,
                row.corpus_id,
                row.revision_id,
                row.target_version_id,
                KnowledgeActivationAction(row.action),
                row.activated_by,
                row.idempotency_key,
                row.created_at,
            )
            for row in rows
        )
