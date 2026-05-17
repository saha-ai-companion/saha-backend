"""
SC-003 — Health check endpoint
================================
GET /api/v1/health

The first real endpoint. Used for:
  - EC2 deployment smoke tests (SC-026)
  - CI/CD pipeline verification
  - Load balancer health checks in V1
  - QA baseline (SC-010)

This endpoint MUST remain unauthenticated — a load balancer cannot
pass a JWT. Any monitoring tool must be able to hit it without credentials.

Response shape:
    {
        "status": "ok",
        "app": "Saha Sobriety Companion",
        "version": "0.1.0",
        "environment": "dev",
        "uptime_seconds": 142.7,
        "database": "ok"          ← added in SC-011
    }
"""

import time

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.config import Settings, get_settings
from app.core.logger import get_logger

log = get_logger(__name__)

router = APIRouter()

# Module-level start time — uptime is calculated from this
_start_time: float = time.monotonic()


class HealthResponse(BaseModel):
    """Health check response schema."""
    status: str
    app: str
    version: str
    environment: str
    uptime_seconds: float

    model_config = {"json_schema_extra": {
        "example": {
            "status": "ok",
            "app": "Saha Sobriety Companion",
            "version": "0.1.0",
            "environment": "dev",
            "uptime_seconds": 142.73,
        }
    }}


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description=(
        "Returns service status, version, environment, and uptime. "
        "Unauthenticated. Used by load balancers, CI/CD, and monitoring."
    ),
    tags=["health"],
)
async def health_check(
    settings: Settings = Depends(get_settings),
) -> HealthResponse:
    """
    Health check endpoint.

    Always returns 200 if the application is running.
    A non-200 here means the process is dead — load balancers act accordingly.

    Extended health checks (DB ping, AI provider reachability) are added
    in later sprints as those dependencies are introduced.
    """
    uptime = round(time.monotonic() - _start_time, 2)

    log.debug("health_check", uptime_seconds=uptime, environment=settings.environment.value)

    return HealthResponse(
        status="ok",
        app=settings.app_name,
        version=settings.app_version,
        environment=settings.environment.value,
        uptime_seconds=uptime,
    )
