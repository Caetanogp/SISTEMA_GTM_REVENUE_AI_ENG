"""JWT authentication for the API composition root."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, cast
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError, decode, encode
from pydantic import BaseModel, ConfigDict

from .settings import ApiSettings

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True, slots=True)
class ApiPrincipal:
    user_id: UUID
    organization_id: UUID
    email: str
    role: str


class AccessTokenClaims(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sub: UUID
    org_id: UUID
    email: str
    role: str
    exp: int | None = None


def create_access_token(
    *,
    subject: UUID,
    organization_id: UUID,
    email: str,
    role: str,
    settings: ApiSettings,
    expires_delta: timedelta | None = None,
) -> str:
    expires = expires_delta or timedelta(minutes=settings.access_token_ttl_minutes)
    payload = {
        "sub": str(subject),
        "org_id": str(organization_id),
        "email": email,
        "role": role,
        "exp": datetime.now(UTC) + expires,
    }
    return encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _settings(request: Request) -> ApiSettings:
    return cast(ApiSettings, request.app.state.settings)


def _missing_token() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="missing bearer token",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _invalid_token() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="invalid bearer token",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> ApiPrincipal:
    if credentials is None:
        raise _missing_token()

    settings = _settings(request)
    try:
        claims = AccessTokenClaims.model_validate(
            decode(
                credentials.credentials,
                settings.jwt_secret,
                algorithms=[settings.jwt_algorithm],
            )
        )
    except (InvalidTokenError, ValueError):
        raise _invalid_token() from None

    if claims.role not in {"admin", "rep"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="insufficient role",
        )

    return ApiPrincipal(
        user_id=claims.sub,
        organization_id=claims.org_id,
        email=claims.email,
        role=claims.role,
    )
