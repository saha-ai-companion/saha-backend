"""
main.py — Application entry point
====================================
Creates the FastAPI app, registers all middleware, mounts the v1 router,
and registers exception handlers.

This file should stay short. Business logic never lives here.
If you are tempted to write logic in main.py, create a module for it instead.

Running locally:
    uvicorn app.main:app --reload --port 8000

Running in production (EC2, see infra/deploy.sh):
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
"""

import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logger import (
    bind_request_id,
    clear_request_context,
    get_logger,
    setup_logging,
)

log = get_logger(__name__)


# ------------------------------------------------------------------ #
# Lifespan — startup / shutdown events
# ------------------------------------------------------------------ #

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Code before 'yield' runs at startup.
    Code after 'yield' runs at shutdown.

    Add:
        - DB connection pool init (SC-011)
        - Pinecone client init (Sprint 3+)
        - Any warm-up tasks
    """
    setup_logging()
    log.info(
        "application_starting",
        app=settings.app_name,
        version=settings.app_version,
        environment=settings.environment.value,
        ai_enabled=settings.ai_enabled,
        memory_enabled=settings.memory_enabled,
    )

    yield  # Application runs here

    log.info("application_shutting_down", app=settings.app_name)


# ------------------------------------------------------------------ #
# FastAPI app
# ------------------------------------------------------------------ #

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "Saha — AI-powered alcohol recovery companion. "
        "Backend API for the companion relationship platform."
    ),
    # Disable Swagger and ReDoc in production — no API discovery for attackers
    docs_url="/docs" if settings.is_dev else None,
    redoc_url="/redoc" if settings.is_dev else None,
    openapi_url="/openapi.json" if settings.is_dev else None,
    lifespan=lifespan,
)


# ------------------------------------------------------------------ #
# Middleware — order matters, outermost registered last
# ------------------------------------------------------------------ #

# Request ID middleware — must be first so all subsequent middleware
# and handlers have access to the request_id
@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """
    Assign a unique request_id to every incoming request.

    The ID is:
      - Stored in request.state.request_id
      - Bound into structlog context (appears in all log lines for this request)
      - Returned in the X-Request-ID response header (for client-side correlation)
    """
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    bind_request_id(request_id)

    response = await call_next(request)

    response.headers["X-Request-ID"] = request_id
    clear_request_context()
    return response


# Request logging middleware
@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    """
    Log every request with method, path, status code, and duration.

    HIPAA note: request URL paths are logged but never query params or
    request body — those may contain PHI.
    """
    import time
    start = time.monotonic()

    response = await call_next(request)

    duration_ms = round((time.monotonic() - start) * 1000, 1)
    log.info(
        "http_request",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=duration_ms,
    )
    return response


# CORS — allow React Native Expo dev server locally
# In production, allowed_origins is set explicitly in environment config
app.add_middleware(
    CORSMiddleware,
    allow_origins=[str(origin) for origin in settings.allowed_origins],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)


# ------------------------------------------------------------------ #
# Exception handlers
# ------------------------------------------------------------------ #

register_exception_handlers(app)


# ------------------------------------------------------------------ #
# Routers
# ------------------------------------------------------------------ #

app.include_router(api_router, prefix=settings.api_v1_prefix)


# ------------------------------------------------------------------ #
# Root — redirect to docs in dev, 404 in prod
# ------------------------------------------------------------------ #

@app.get("/", include_in_schema=False)
async def root():
    if settings.is_dev:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/docs")
    from fastapi.responses import JSONResponse
    return JSONResponse({"message": "Saha API"}, status_code=200)
