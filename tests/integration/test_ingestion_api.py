"""Integration coverage for the administrative ingestion API."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from revops.infrastructure.persistence.models import IngestionItem, IngestionJob, Organization, User
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.auth import create_access_token
from apps.api.main import create_app
from apps.api.settings import ApiSettings


@pytest.mark.integration
async def test_admin_ingestion_staging_replay_polling_and_role_guard(database_url: str) -> None:
    engine = create_async_engine(database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    organization_id, admin_id, rep_id = uuid4(), uuid4(), uuid4()
    async with session_factory() as session:
        session.add(Organization(id=organization_id, name="Ingestion API org", demo_mode=True))
        session.add_all(
            [
                User(
                    id=admin_id,
                    organization_id=organization_id,
                    email=f"{admin_id}@example.test",
                    role="admin",
                ),
                User(
                    id=rep_id,
                    organization_id=organization_id,
                    email=f"{rep_id}@example.test",
                    role="rep",
                ),
            ]
        )
        await session.commit()

    settings = ApiSettings(
        database_url=database_url,
        jwt_secret="test-secret-test-secret-test-secret-test-secret",
    )
    app = create_app(settings=settings)
    admin_token = create_access_token(
        subject=admin_id,
        organization_id=organization_id,
        email="admin@example.test",
        role="admin",
        settings=settings,
    )
    rep_token = create_access_token(
        subject=rep_id,
        organization_id=organization_id,
        email="rep@example.test",
        role="rep",
        settings=settings,
    )
    headers = {"Authorization": f"Bearer {admin_token}"}
    try:
        async with app.router.lifespan_context(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                payload = {
                    "source": "integration",
                    "idempotency_key": "api-1",
                    "records": [
                        {"company_name": "API Acme", "domain": "api-acme.example"},
                        {"company_name": "", "domain": "bad domain"},
                    ],
                }
                staged = await client.post("/admin/ingestion", headers=headers, json=payload)
                assert staged.status_code == 201, staged.text
                body = staged.json()
                job_id = UUID(body["id"])
                assert body["status"] == "staged"
                assert body["items"][1]["status"] == "validation_failed"

                replay = await client.post("/admin/ingestion", headers=headers, json=payload)
                assert replay.status_code == 201
                assert replay.json()["id"] == str(job_id)
                assert replay.json()["replayed"] is True

                page = await client.get(
                    f"/admin/ingestion/{job_id}/items?offset=1&limit=1", headers=headers
                )
                assert page.status_code == 200
                assert len(page.json()) == 1
                status_response = await client.get(f"/admin/ingestion/{job_id}", headers=headers)
                assert status_response.status_code == 200

                forbidden = await client.post(
                    "/admin/ingestion",
                    headers={"Authorization": f"Bearer {rep_token}"},
                    json=payload,
                )
                assert forbidden.status_code == 403

                malformed_csv = await client.post(
                    "/admin/ingestion/csv",
                    headers={
                        **headers,
                        "X-Import-Source": "integration",
                        "Idempotency-Key": "bad-csv",
                    },
                    content=b"company_name,domain,unknown\nAcme,acme.example,x\n",
                )
                assert malformed_csv.status_code == 422
    finally:
        async with session_factory() as session:
            await session.execute(
                delete(IngestionItem).where(IngestionItem.ingestion_job_id == job_id)
            )
            await session.execute(delete(IngestionJob).where(IngestionJob.id == job_id))
            await session.execute(delete(User).where(User.organization_id == organization_id))
            await session.execute(delete(Organization).where(Organization.id == organization_id))
            await session.commit()
        await engine.dispose()
