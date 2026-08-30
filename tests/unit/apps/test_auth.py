from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import Request

from apps.api.auth import ApiPrincipal, create_access_token, get_current_principal
from apps.api.settings import ApiSettings


@dataclass(slots=True)
class _RequestStub:
    app: object


def _settings() -> ApiSettings:
    return ApiSettings(
        jwt_secret="test-secret-test-secret-test-secret-test-secret",
        jwt_algorithm="HS256",
    )


def test_create_access_token_round_trips_with_pyjwt() -> None:
    settings = _settings()
    subject = uuid4()
    organization_id = uuid4()

    token = create_access_token(
        subject=subject,
        organization_id=organization_id,
        email="rep@example.com",
        role="rep",
        settings=settings,
    )

    claims = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])

    assert claims["sub"] == str(subject)
    assert claims["org_id"] == str(organization_id)
    assert claims["email"] == "rep@example.com"
    assert claims["role"] == "rep"


@pytest.mark.asyncio
async def test_get_current_principal_rejects_invalid_token() -> None:
    request = _RequestStub(app=SimpleNamespace(state=SimpleNamespace(settings=_settings())))

    with pytest.raises(HTTPException, match="invalid bearer token"):
        await get_current_principal(
            cast(Request, request),
            HTTPAuthorizationCredentials(scheme="Bearer", credentials="bad-token"),
        )


@pytest.mark.asyncio
async def test_get_current_principal_decodes_token() -> None:
    settings = _settings()
    subject = uuid4()
    organization_id = uuid4()
    token = create_access_token(
        subject=subject,
        organization_id=organization_id,
        email="rep@example.com",
        role="rep",
        settings=settings,
    )
    request = _RequestStub(app=SimpleNamespace(state=SimpleNamespace(settings=settings)))

    principal = await get_current_principal(
        cast(Request, request),
        HTTPAuthorizationCredentials(scheme="Bearer", credentials=token),
    )

    assert principal == ApiPrincipal(
        user_id=subject,
        organization_id=organization_id,
        email="rep@example.com",
        role="rep",
    )
