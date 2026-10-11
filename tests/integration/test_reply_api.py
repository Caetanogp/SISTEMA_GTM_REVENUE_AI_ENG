"""API evidence for authenticated reply registration, analysis, artifact reads, and feedback."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from revops.application.dto import ReplyClassificationOutput, ReplyEvidenceDTO
from revops.domain.values.reply import ReplyCategory, ReplyLanguage
from revops.infrastructure.llm.fake import FakeLLMGateway
from revops.infrastructure.persistence.models import Account, Contact, Organization, User
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from apps.api.auth import create_access_token
from apps.api.main import create_app
from apps.api.settings import ApiSettings


async def _seed_subjects(
    sessions: async_sessionmaker[AsyncSession],
) -> tuple[UUID, UUID, UUID, UUID]:
    organization_id, actor_id, account_id, contact_id = (uuid4() for _ in range(4))
    async with sessions() as session:
        session.add(Organization(id=organization_id, name="Reply API", demo_mode=True))
        await session.flush()
        session.add(
            User(
                id=actor_id,
                organization_id=organization_id,
                email=f"{actor_id}@example.test",
                role="rep",
            )
        )
        await session.flush()
        session.add(
            Account(
                id=account_id,
                organization_id=organization_id,
                company_name="Reply API Co",
                domain=f"{account_id}.example.test",
                created_at=datetime(2026, 10, 11, tzinfo=UTC),
            )
        )
        await session.flush()
        session.add(
            Contact(
                id=contact_id,
                organization_id=organization_id,
                account_id=account_id,
                email=f"{contact_id}@example.test",
                full_name="Reply Operator",
                title="Rep",
            )
        )
        await session.commit()
    return organization_id, actor_id, account_id, contact_id


@pytest.mark.integration
async def test_reply_api_reads_terminal_artifact_without_a_second_provider_call(
    database_url: str,
) -> None:
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    organization_id, actor_id, account_id, contact_id = await _seed_subjects(sessions)
    settings = ApiSettings(
        database_url=database_url,
        jwt_secret="test-secret-test-secret-test-secret-test-secret",
        knowledge_embedding_provider="openai",
    )
    gateway = FakeLLMGateway(
        responses=[
            ReplyClassificationOutput(
                category=ReplyCategory.INTERESTED,
                confidence=0.95,
                language=ReplyLanguage.ENGLISH,
                evidence=(ReplyEvidenceDTO(start_offset=0, end_offset=9),),
            )
        ]
    )
    app = create_app(settings=settings, llm_gateway=gateway)
    token = create_access_token(
        subject=actor_id,
        organization_id=organization_id,
        email="reply-api@example.test",
        role="rep",
        settings=settings,
    )
    headers = {"Authorization": f"Bearer {token}"}
    try:
        async with app.router.lifespan_context(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                registered = await client.post(
                    "/replies",
                    headers={**headers, "Idempotency-Key": "reply-api-register"},
                    json={
                        "account_id": str(account_id),
                        "contact_id": str(contact_id),
                        "text": "Interested in your pricing.",
                        "language": "en",
                    },
                )
                assert registered.status_code == 201, registered.text
                reply_id = UUID(registered.json()["id"])

                classified = await client.post(
                    f"/replies/{reply_id}/classify",
                    headers={**headers, "Idempotency-Key": "reply-api-classify"},
                )
                assert classified.status_code == 200, classified.text
                assert classified.json()["status"] == "completed"
                assert classified.json()["result"]["category"] == "interested"
                run_id = UUID(classified.json()["run_id"])
                assert len(gateway.calls) == 1

                result = await client.get(f"/agent/runs/{run_id}/result", headers=headers)
                assert result.status_code == 200, result.text
                assert result.json()["reply"]["category"] == "interested"
                assert len(gateway.calls) == 1

                feedback = await client.post(
                    f"/agent/runs/{run_id}/reply-feedback",
                    headers={**headers, "Idempotency-Key": "reply-api-feedback"},
                    json={"corrected_category": "interested", "comment": "Confirmed"},
                )
                assert feedback.status_code == 200, feedback.text
                history = await client.get(f"/agent/runs/{run_id}/reply-feedback", headers=headers)
                assert history.status_code == 200, history.text
                assert len(history.json()) == 1
    finally:
        await engine.dispose()


@pytest.mark.integration
async def test_reply_api_rejects_cross_tenant_reply_and_run_access(
    database_url: str,
) -> None:
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    organization_id, actor_id, account_id, contact_id = await _seed_subjects(sessions)
    other_organization_id, other_actor_id, _, _ = await _seed_subjects(sessions)
    settings = ApiSettings(
        database_url=database_url,
        jwt_secret="test-secret-test-secret-test-secret-test-secret",
    )
    gateway = FakeLLMGateway(
        responses=[
            ReplyClassificationOutput(
                category=ReplyCategory.INTERESTED,
                confidence=0.95,
                language=ReplyLanguage.ENGLISH,
                evidence=(ReplyEvidenceDTO(start_offset=0, end_offset=9),),
            )
        ]
    )
    app = create_app(settings=settings, llm_gateway=gateway)
    owner_token = create_access_token(
        subject=actor_id,
        organization_id=organization_id,
        email="owner@example.test",
        role="rep",
        settings=settings,
    )
    other_token = create_access_token(
        subject=other_actor_id,
        organization_id=other_organization_id,
        email="other@example.test",
        role="rep",
        settings=settings,
    )
    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    other_headers = {"Authorization": f"Bearer {other_token}"}
    try:
        async with app.router.lifespan_context(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                registered = await client.post(
                    "/replies",
                    headers={**owner_headers, "Idempotency-Key": "tenant-register"},
                    json={
                        "account_id": str(account_id),
                        "contact_id": str(contact_id),
                        "text": "Interested in your pricing.",
                        "language": "en",
                    },
                )
                assert registered.status_code == 201, registered.text
                reply_id = UUID(registered.json()["id"])
                classified = await client.post(
                    f"/replies/{reply_id}/classify",
                    headers={**owner_headers, "Idempotency-Key": "tenant-classify"},
                )
                assert classified.status_code == 200, classified.text
                run_id = UUID(classified.json()["run_id"])
                assert len(gateway.calls) == 1

                assert (
                    await client.get(f"/replies/{reply_id}", headers=other_headers)
                ).status_code == 404
                assert (
                    await client.post(
                        f"/replies/{reply_id}/classify",
                        headers={**other_headers, "Idempotency-Key": "other-classify"},
                    )
                ).status_code == 404
                assert (
                    await client.get(f"/agent/runs/{run_id}/result", headers=other_headers)
                ).status_code == 403
                assert (
                    await client.get(f"/agent/runs/{run_id}/reply-feedback", headers=other_headers)
                ).status_code == 404
                assert len(gateway.calls) == 1
    finally:
        await engine.dispose()


@pytest.mark.integration
async def test_reply_api_restart_replays_checkpoint_without_a_second_provider_call(
    database_url: str,
) -> None:
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    organization_id, actor_id, account_id, contact_id = await _seed_subjects(sessions)
    settings = ApiSettings(
        database_url=database_url,
        jwt_secret="test-secret-test-secret-test-secret-test-secret",
    )
    first_gateway = FakeLLMGateway(
        responses=[
            ReplyClassificationOutput(
                category=ReplyCategory.INTERESTED,
                confidence=0.95,
                language=ReplyLanguage.ENGLISH,
                evidence=(ReplyEvidenceDTO(start_offset=0, end_offset=9),),
            )
        ]
    )
    token = create_access_token(
        subject=actor_id,
        organization_id=organization_id,
        email="restart@example.test",
        role="rep",
        settings=settings,
    )
    headers = {"Authorization": f"Bearer {token}"}
    try:
        first_app = create_app(settings=settings, llm_gateway=first_gateway)
        async with first_app.router.lifespan_context(first_app):
            transport = ASGITransport(app=first_app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                registered = await client.post(
                    "/replies",
                    headers={**headers, "Idempotency-Key": "restart-register"},
                    json={
                        "account_id": str(account_id),
                        "contact_id": str(contact_id),
                        "text": "Interested in your pricing.",
                        "language": "en",
                    },
                )
                assert registered.status_code == 201, registered.text
                reply_id = UUID(registered.json()["id"])
                first = await client.post(
                    f"/replies/{reply_id}/classify",
                    headers={**headers, "Idempotency-Key": "restart-first"},
                )
                assert first.status_code == 200, first.text
                assert first.json()["status"] == "completed"
                assert len(first_gateway.calls) == 1

        restarted_gateway = FakeLLMGateway()
        restarted_app = create_app(settings=settings, llm_gateway=restarted_gateway)
        async with restarted_app.router.lifespan_context(restarted_app):
            transport = ASGITransport(app=restarted_app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                replay = await client.post(
                    f"/replies/{reply_id}/classify",
                    headers={**headers, "Idempotency-Key": "restart-replay"},
                )
                assert replay.status_code == 200, replay.text
                assert replay.json()["status"] == "completed"
                assert replay.json()["replayed"] is True
                assert restarted_gateway.calls == []
    finally:
        await engine.dispose()
