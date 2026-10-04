"""Integration coverage for the tenant-scoped knowledge administration API."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from revops.application.dto import KnowledgeChunkEmbedding
from revops.domain.entities.knowledge import (
    KnowledgeCategory,
    KnowledgeDocument,
    KnowledgeFormat,
    KnowledgeLanguage,
    KnowledgeScope,
    KnowledgeVersionStatus,
)
from revops.infrastructure.persistence.knowledge_repositories import (
    SqlAlchemyCorpusRevisionRepository,
    SqlAlchemyKnowledgeDocumentRepository,
)
from revops.infrastructure.persistence.models import (
    KnowledgeChunk,
    KnowledgeCorpus,
    KnowledgeCorpusHead,
    KnowledgeDocumentVersion,
    KnowledgeProcessingEvent,
    KnowledgeRevision,
    KnowledgeRevisionActivation,
    KnowledgeRevisionEntry,
    Organization,
    User,
)
from revops.infrastructure.persistence.models import (
    KnowledgeDocument as KnowledgeDocumentModel,
)
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.auth import create_access_token
from apps.api.main import create_app
from apps.api.settings import ApiSettings


@pytest.mark.integration
async def test_knowledge_admin_routes_enforce_contract_and_tenant_isolation(
    database_url: str,
) -> None:
    engine = create_async_engine(database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    organization_id, other_organization_id = uuid4(), uuid4()
    admin_id, rep_id, other_admin_id = uuid4(), uuid4(), uuid4()
    corpus_id, ready_version_id, revision_id = uuid4(), uuid4(), uuid4()
    settings = ApiSettings(
        database_url=database_url,
        jwt_secret="test-secret-test-secret-test-secret-test-secret",
    )
    app = create_app(settings=settings)
    admin_headers = {
        "Authorization": "Bearer "
        + create_access_token(
            subject=admin_id,
            organization_id=organization_id,
            email="admin@example.test",
            role="admin",
            settings=settings,
        )
    }
    rep_headers = {
        "Authorization": "Bearer "
        + create_access_token(
            subject=rep_id,
            organization_id=organization_id,
            email="rep@example.test",
            role="rep",
            settings=settings,
        )
    }
    other_admin_headers = {
        "Authorization": "Bearer "
        + create_access_token(
            subject=other_admin_id,
            organization_id=other_organization_id,
            email="other-admin@example.test",
            role="admin",
            settings=settings,
        )
    }
    draft_id: UUID | None = None
    try:
        async with session_factory() as session:
            now = datetime.now(UTC)
            session.add_all(
                [
                    Organization(id=organization_id, name="Knowledge API org", demo_mode=True),
                    Organization(
                        id=other_organization_id,
                        name="Other knowledge API org",
                        demo_mode=True,
                    ),
                    User(
                        id=admin_id,
                        organization_id=organization_id,
                        email="admin@example.test",
                        role="admin",
                    ),
                    User(
                        id=rep_id,
                        organization_id=organization_id,
                        email="rep@example.test",
                        role="rep",
                    ),
                    User(
                        id=other_admin_id,
                        organization_id=other_organization_id,
                        email="other-admin@example.test",
                        role="admin",
                    ),
                ]
            )
            await session.flush()
            session.add(
                KnowledgeCorpus(
                    id=corpus_id,
                    scope=KnowledgeScope.ORGANIZATION.value,
                    organization_id=organization_id,
                    created_at=now,
                )
            )
            await session.flush()
            documents = SqlAlchemyKnowledgeDocumentRepository(session)
            ready = await documents.reserve_draft(
                corpus_id=corpus_id,
                requested_by=admin_id,
                document=KnowledgeDocument(
                    document_key="product/ready",
                    category=KnowledgeCategory.PRODUCT,
                    language=KnowledgeLanguage.ENGLISH,
                    format=KnowledgeFormat.MARKDOWN,
                    scope=KnowledgeScope.ORGANIZATION,
                    content="# Ready\n\nPublished knowledge.",
                    metadata={},
                ),
                idempotency_key="ready-seed",
                created_at=now,
            )
            ready = await documents.transition_status(
                corpus_id=corpus_id,
                version_id=ready.id,
                status=KnowledgeVersionStatus.READY,
            )
            revision = await SqlAlchemyCorpusRevisionRepository(session).publish(
                corpus_id=corpus_id,
                version_id=ready.id,
                chunks=(
                    KnowledgeChunkEmbedding(
                        ordinal=0,
                        text=ready.document.content,
                        content_hash=ready.document.content_hash,
                        vector=tuple(0.0 for _ in range(1536)),
                    ),
                ),
                activated_by=admin_id,
                created_at=now,
            )
            ready_version_id, revision_id = ready.id, revision.id
            await session.commit()

        payload = {
            "document_key": "sales/discovery",
            "category": "sales_playbook",
            "language": "en",
            "format": "md",
            "content": "# Discovery\n\nApproved discovery questions.",
            "metadata": {"source": "api"},
        }
        headers = {**admin_headers, "Idempotency-Key": "draft-api-1"}
        async with app.router.lifespan_context(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                assert (await client.get("/v1/knowledge/versions")).status_code == 401
                assert (
                    await client.get("/v1/knowledge/versions", headers=rep_headers)
                ).status_code == 403

                created = await client.post("/v1/knowledge/versions", headers=headers, json=payload)
                assert created.status_code == 201, created.text
                draft_id = UUID(created.json()["id"])
                assert created.json()["content"] == payload["content"]

                replay = await client.post("/v1/knowledge/versions", headers=headers, json=payload)
                assert replay.status_code == 200, replay.text
                assert replay.json()["id"] == str(draft_id)

                conflicting = await client.post(
                    "/v1/knowledge/versions",
                    headers=headers,
                    json={**payload, "content": "different approved content"},
                )
                assert conflicting.status_code == 409
                assert (
                    await client.post(
                        "/v1/knowledge/versions",
                        headers={**admin_headers, "Idempotency-Key": "invalid"},
                        json={**payload, "document_key": "Invalid Key"},
                    )
                ).status_code == 400

                listed = await client.get("/v1/knowledge/versions", headers=admin_headers)
                assert listed.status_code == 200
                assert all(
                    "content" not in item and "metadata" not in item for item in listed.json()
                )
                assert any(item["id"] == str(draft_id) for item in listed.json())

                detail = await client.get(
                    f"/v1/knowledge/versions/{draft_id}", headers=admin_headers
                )
                assert detail.status_code == 200
                assert detail.json()["metadata"] == {"source": "api"}
                assert (
                    await client.get(
                        f"/v1/knowledge/versions/{draft_id}", headers=other_admin_headers
                    )
                ).status_code == 404

                confirmed = await client.post(
                    f"/v1/knowledge/versions/{ready_version_id}/confirm", headers=admin_headers
                )
                assert confirmed.status_code == 200
                retired = await client.post(
                    f"/v1/knowledge/versions/{ready_version_id}/retire", headers=admin_headers
                )
                assert retired.status_code == 200
                assert retired.json()["status"] == "retired"
                assert (
                    await client.post(
                        f"/v1/knowledge/versions/{ready_version_id}/retire", headers=admin_headers
                    )
                ).status_code == 409

                activation_headers = {**admin_headers, "Idempotency-Key": "activate-api-1"}
                activated = await client.post(
                    f"/v1/knowledge/revisions/{revision_id}/activate", headers=activation_headers
                )
                assert activated.status_code == 200
                assert activated.json()["id"] == str(revision_id)
                assert (
                    await client.post(
                        f"/v1/knowledge/revisions/{revision_id}/activate",
                        headers=activation_headers,
                    )
                ).status_code == 200
                assert (
                    await client.post(
                        f"/v1/knowledge/revisions/{revision_id}/activate",
                        headers=other_admin_headers | {"Idempotency-Key": "other-activate"},
                    )
                ).status_code == 404
    finally:
        async with session_factory() as session:
            await session.execute(
                delete(KnowledgeCorpusHead).where(KnowledgeCorpusHead.corpus_id == corpus_id)
            )
            await session.execute(
                delete(KnowledgeProcessingEvent).where(
                    KnowledgeProcessingEvent.corpus_id == corpus_id
                )
            )
            await session.execute(
                delete(KnowledgeRevisionActivation).where(
                    KnowledgeRevisionActivation.corpus_id == corpus_id
                )
            )
            await session.execute(
                delete(KnowledgeRevisionEntry).where(KnowledgeRevisionEntry.corpus_id == corpus_id)
            )
            await session.execute(
                delete(KnowledgeChunk).where(KnowledgeChunk.corpus_id == corpus_id)
            )
            await session.execute(
                delete(KnowledgeRevision).where(KnowledgeRevision.corpus_id == corpus_id)
            )
            await session.execute(
                delete(KnowledgeDocumentVersion).where(
                    KnowledgeDocumentVersion.corpus_id == corpus_id
                )
            )
            await session.execute(
                delete(KnowledgeDocumentModel).where(KnowledgeDocumentModel.corpus_id == corpus_id)
            )
            await session.execute(delete(KnowledgeCorpus).where(KnowledgeCorpus.id == corpus_id))
            await session.execute(
                delete(User).where(
                    User.organization_id.in_((organization_id, other_organization_id))
                )
            )
            await session.execute(
                delete(Organization).where(
                    Organization.id.in_((organization_id, other_organization_id))
                )
            )
            await session.commit()
        await engine.dispose()
