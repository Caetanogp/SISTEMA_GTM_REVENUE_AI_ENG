"""Unit coverage for the API's authenticated retrieval composition root."""

from __future__ import annotations

from typing import cast
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from revops.application.dto import KnowledgeRetrievalContext, TaskKnowledgeContext
from revops.application.use_cases.retrieve_knowledge import RetrieveKnowledge
from revops.infrastructure.embeddings.providers import DeterministicFakeEmbeddingProvider
from revops.infrastructure.persistence.knowledge_repositories import (
    SqlAlchemyKnowledgeRetrievalRepository,
)
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth import create_access_token
from apps.api.dependencies import retrieval_use_case
from apps.api.main import create_app
from apps.api.runtime import build_embedding_provider
from apps.api.settings import ApiSettings


def test_retrieval_composition_uses_configured_provider_and_sql_repository() -> None:
    settings = ApiSettings()
    provider = build_embedding_provider(settings)

    assert isinstance(provider, DeterministicFakeEmbeddingProvider)
    composed = retrieval_use_case(
        session=cast(AsyncSession, object()),
        embeddings=provider,
    )

    assert isinstance(composed, RetrieveKnowledge)
    assert isinstance(composed.repository, SqlAlchemyKnowledgeRetrievalRepository)
    assert composed.embeddings is provider


@pytest.mark.asyncio
async def test_retrieval_route_derives_tenant_from_jwt_and_rejects_tenant_payload() -> None:
    settings = ApiSettings(
        jwt_secret="test-secret-test-secret-test-secret-test-secret",
    )
    app = create_app(settings=settings)
    organization_id = uuid4()
    captured: list[KnowledgeRetrievalContext] = []

    class FakeRetrieval:
        async def execute(
            self, *, context: KnowledgeRetrievalContext, args: object
        ) -> TaskKnowledgeContext:
            captured.append(context)
            return TaskKnowledgeContext(text="", token_count=0, included=(), omitted=())

    fake = FakeRetrieval()

    def override_retrieval() -> FakeRetrieval:
        return fake

    app.dependency_overrides[retrieval_use_case] = override_retrieval
    token = create_access_token(
        subject=uuid4(),
        organization_id=organization_id,
        email="rep@example.test",
        role="rep",
        settings=settings,
    )
    headers = {"Authorization": f"Bearer {token}"}

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/v1/knowledge/retrieve",
                headers=headers,
                json={"query": "pricing", "organization_id": str(uuid4())},
            )
            assert response.status_code == 422

            response = await client.post(
                "/v1/knowledge/retrieve",
                headers=headers,
                json={"query": "pricing"},
            )

        assert response.status_code == 200, response.text
        assert captured == [KnowledgeRetrievalContext(organization_id=organization_id)]
    finally:
        app.dependency_overrides.clear()
