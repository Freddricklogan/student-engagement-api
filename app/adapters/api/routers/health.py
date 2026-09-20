"""Liveness and readiness probes (the legacy app had neither)."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from app.adapters.api.deps import DbSession, SettingsDep
from app.application.dto import HealthResponse, ReadinessResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
async def health(settings: SettingsDep) -> HealthResponse:
    """Unauthenticated: container and load-balancer probes must not need a token."""
    return HealthResponse(
        status="ok", version=settings.app_version, environment=settings.environment
    )


@router.get("/health/ready", response_model=ReadinessResponse, summary="Readiness probe")
async def readiness(session: DbSession) -> ReadinessResponse:
    """Confirms the process can actually reach its database."""
    try:
        await session.execute(text("SELECT 1"))
    except Exception:  # pragma: no cover - exercised only on a real outage
        return ReadinessResponse(status="not-ready", database="unavailable")
    return ReadinessResponse(status="ready", database="ok")
