"""End-to-end administrative deduplication API coverage."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from revops.domain.entities.account import Account as DomainAccount
from revops.domain.entities.deduplication import DeduplicationCandidateStatus
from revops.domain.policies.deduplication import account_fingerprint
from revops.domain.values.company_domain import CompanyDomain
from revops.infrastructure.persistence.models import (
    Account,
    AccountDeduplicationAlias,
    AccountDeduplicationCandidate,
    DeduplicationEvent,
    DeduplicationScan,
    Organization,
    User,
)
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.auth import create_access_token
from apps.api.main import create_app
from apps.api.settings import ApiSettings


@pytest.mark.integration
async def test_admin_deduplication_flow_and_security(database_url: str) -> None:
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    organization_id = uuid4()
    admin_id, rep_id = uuid4(), uuid4()
    scan_id, queued_scan_id = uuid4(), uuid4()
    left_id, right_id = sorted((uuid4(), uuid4()))
    stale_left_id, stale_right_id = sorted((uuid4(), uuid4()))
    candidate_id, stale_candidate_id = uuid4(), uuid4()
    now = datetime.now(UTC)
    left = DomainAccount(
        left_id, organization_id, "North Star LLC", CompanyDomain("north-star.example"), now
    )
    right = DomainAccount(
        right_id,
        organization_id,
        "North Star Incorporated",
        CompanyDomain("north-star.co"),
        now,
    )
    stale_left = DomainAccount(
        stale_left_id,
        organization_id,
        "Blue River LLC",
        CompanyDomain("blue-river.example"),
        now,
    )
    stale_right = DomainAccount(
        stale_right_id,
        organization_id,
        "Blue River Incorporated",
        CompanyDomain("blue-river.co"),
        now,
    )
    async with sessions() as session:
        session.add(Organization(id=organization_id, name="Dedupe API", demo_mode=True))
        await session.flush()
        session.add_all(
            [
                User(
                    id=admin_id,
                    organization_id=organization_id,
                    email=f"{admin_id}@test",
                    role="admin",
                ),
                User(
                    id=rep_id, organization_id=organization_id, email=f"{rep_id}@test", role="rep"
                ),
                Account(
                    id=left_id,
                    organization_id=organization_id,
                    company_name=left.company_name,
                    domain=left.domain.value,
                    created_at=now,
                ),
                Account(
                    id=right_id,
                    organization_id=organization_id,
                    company_name=right.company_name,
                    domain=right.domain.value,
                    created_at=now,
                ),
                Account(
                    id=stale_left_id,
                    organization_id=organization_id,
                    company_name=stale_left.company_name,
                    domain=stale_left.domain.value,
                    created_at=now,
                ),
                Account(
                    id=stale_right_id,
                    organization_id=organization_id,
                    company_name=stale_right.company_name,
                    domain=stale_right.domain.value,
                    created_at=now,
                ),
            ]
        )
        await session.flush()
        session.add_all(
            [
                DeduplicationScan(
                    id=scan_id,
                    organization_id=organization_id,
                    requested_by=admin_id,
                    record_types=["account"],
                    policy_version="dedupe_v1",
                    idempotency_key=str(scan_id),
                    status="completed",
                    created_at=now,
                    updated_at=now,
                ),
                DeduplicationScan(
                    id=queued_scan_id,
                    organization_id=organization_id,
                    requested_by=admin_id,
                    record_types=["account"],
                    policy_version="dedupe_v1",
                    idempotency_key=str(queued_scan_id),
                    status="queued",
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
        await session.flush()
        session.add(
            AccountDeduplicationCandidate(
                id=candidate_id,
                scan_id=scan_id,
                organization_id=organization_id,
                left_id=left_id,
                right_id=right_id,
                score=100,
                reasons=["account_domain_exact"],
                policy_version="dedupe_v1",
                left_fingerprint=account_fingerprint(left),
                right_fingerprint=account_fingerprint(right),
                status=DeduplicationCandidateStatus.PENDING.value,
            )
        )
        session.add(
            AccountDeduplicationCandidate(
                id=stale_candidate_id,
                scan_id=scan_id,
                organization_id=organization_id,
                left_id=stale_left_id,
                right_id=stale_right_id,
                score=80,
                reasons=["account_name_exact"],
                policy_version="dedupe_v1",
                left_fingerprint="0" * 64,
                right_fingerprint=account_fingerprint(stale_right),
                status=DeduplicationCandidateStatus.PENDING.value,
            )
        )
        await session.commit()

    settings = ApiSettings(
        database_url=database_url, jwt_secret="test-secret-test-secret-test-secret"
    )
    api = create_app(settings=settings)
    admin_token = create_access_token(
        subject=admin_id,
        organization_id=organization_id,
        email="admin@test",
        role="admin",
        settings=settings,
    )
    rep_token = create_access_token(
        subject=rep_id,
        organization_id=organization_id,
        email="rep@test",
        role="rep",
        settings=settings,
    )
    headers = {"Authorization": f"Bearer {admin_token}"}
    try:
        async with (
            api.router.lifespan_context(api),
            AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client,
        ):
            assert (await client.get(f"/admin/deduplication/scans/{scan_id}")).status_code == 401
            assert (
                await client.get(
                    f"/admin/deduplication/scans/{scan_id}",
                    headers={"Authorization": f"Bearer {rep_token}"},
                )
            ).status_code == 403
            assert (
                await client.get(
                    f"/admin/deduplication/scans/{scan_id}/candidates?limit=101",
                    headers=headers,
                )
            ).status_code == 422
            assert (
                await client.get(f"/admin/deduplication/scans/{uuid4()}", headers=headers)
            ).status_code == 404
            assert (
                await client.get(
                    f"/admin/deduplication/scans/{queued_scan_id}/candidates", headers=headers
                )
            ).status_code == 409
            status_response = await client.get(
                f"/admin/deduplication/scans/{scan_id}", headers=headers
            )
            assert status_response.status_code == 200
            assert status_response.json()["pending"] == 2
            page = await client.get(
                f"/admin/deduplication/scans/{scan_id}/candidates?offset=0&limit=100",
                headers=headers,
            )
            assert page.status_code == 200
            assert {item["id"] for item in page.json()} == {
                str(candidate_id),
                str(stale_candidate_id),
            }
            stale = await client.post(
                f"/admin/deduplication/candidates/{stale_candidate_id}/merge",
                headers={**headers, "Idempotency-Key": "api-stale-flow"},
                json={"master_record_id": str(stale_left_id)},
            )
            assert stale.status_code == 409
            stale_status = await client.get(
                f"/admin/deduplication/scans/{scan_id}", headers=headers
            )
            assert stale_status.json()["stale"] == 1
            merge_headers = {**headers, "Idempotency-Key": "api-merge-flow"}
            merged = await client.post(
                f"/admin/deduplication/candidates/{candidate_id}/merge",
                headers=merge_headers,
                json={"master_record_id": str(left_id)},
            )
            assert merged.status_code == 200, merged.text
            replay = await client.post(
                f"/admin/deduplication/candidates/{candidate_id}/merge",
                headers=merge_headers,
                json={"master_record_id": str(left_id)},
            )
            assert replay.status_code == 200
            assert replay.json()["replayed"] is True
            history = await client.get("/admin/deduplication/merges", headers=headers)
            assert history.status_code == 200
            assert history.json()[0]["action"] == "merge"
            reverted = await client.post(
                f"/admin/deduplication/merges/{merged.json()['event_id']}/revert",
                headers={**headers, "Idempotency-Key": "api-revert-flow"},
            )
            assert reverted.status_code == 200, reverted.text
    finally:
        async with sessions() as session:
            await session.execute(
                delete(AccountDeduplicationAlias).where(
                    AccountDeduplicationAlias.organization_id == organization_id
                )
            )
            await session.execute(
                delete(DeduplicationEvent).where(
                    DeduplicationEvent.organization_id == organization_id
                )
            )
            await session.execute(
                delete(AccountDeduplicationCandidate).where(
                    AccountDeduplicationCandidate.organization_id == organization_id
                )
            )
            await session.execute(
                delete(DeduplicationScan).where(
                    DeduplicationScan.organization_id == organization_id
                )
            )
            await session.execute(delete(Account).where(Account.organization_id == organization_id))
            await session.execute(delete(User).where(User.organization_id == organization_id))
            await session.execute(delete(Organization).where(Organization.id == organization_id))
            await session.commit()
        await engine.dispose()
