"""Sanitized operational health endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from revops.application.dto import LLMGatewayHealth, LLMHealthStatus
from revops.application.ports import LLMGateway

from apps.api.dependencies import get_llm_gateway

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/llm", response_model=LLMGatewayHealth)
async def llm_health(
    llm_gateway: Annotated[LLMGateway, Depends(get_llm_gateway)],
) -> LLMGatewayHealth:
    health = llm_gateway.health_snapshot()
    if health.mode == "live" and health.status is LLMHealthStatus.UNAVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": health.status.value},
        )
    return health
