"""
SC-002 — API v1 router
========================
Central router for all /api/v1/* endpoints.

This is the file every backend intern touches when adding a new endpoint.
Pattern is simple: create your router in app/api/v1/endpoints/your_module.py,
then add one line here to include it.

The prefix and tags pattern:
    - prefix: URL segment added to all routes in that router ("/health", "/auth", etc.)
    - tags: Groups routes in the Swagger docs (/docs) — use the same tag in your router decorator

Adding a new endpoint module (example — auth in Sprint 2):
    from app.api.v1.endpoints import auth
    api_router.include_router(auth.router, prefix="/auth", tags=["auth"])

That is it. FastAPI discovers all routes automatically.
"""

from fastapi import APIRouter

from app.api.v1.endpoints import health

# The single router that main.py mounts at settings.api_v1_prefix
api_router = APIRouter()

# ------------------------------------------------------------------ #
# Registered endpoint modules
# Add one line here per Sprint — never modify existing lines.
# ------------------------------------------------------------------ #

# SC-003 — Health check (unauthenticated)
api_router.include_router(health.router, tags=["health"])

# Sprint 2 — Auth (SC-015)
# from app.api.v1.endpoints import auth
# api_router.include_router(auth.router, prefix="/auth", tags=["auth"])

# Sprint 2 — Users (SC-016)
# from app.api.v1.endpoints import users
# api_router.include_router(users.router, prefix="/users", tags=["users"])

# Sprint 3 — AI/Companion (SC-028)
# from app.api.v1.endpoints import companion
# api_router.include_router(companion.router, prefix="/companion", tags=["companion"])
