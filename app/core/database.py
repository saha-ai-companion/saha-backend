"""
SC-011 — Database connection layer
====================================
Owner: B1
Sprint: 2, Week 3 — complete this BEFORE any other backend intern starts their ticket.

This file is the foundation of the entire data layer.
It creates:
  1. The async SQLAlchemy engine (the actual PostgreSQL connection)
  2. The session factory (creates individual database sessions)
  3. The get_db() dependency (injected into every route that touches the DB)
  4. A check_db_connection() utility (used by the health endpoint)

WHY ASYNC?
  FastAPI is an async framework. If we use synchronous SQLAlchemy, every
  database query blocks the entire server — no other requests can be served
  while one query is running. Async SQLAlchemy lets the server handle other
  requests while waiting for PostgreSQL to respond.

WHY SESSION PER REQUEST?
  A database session is like a transaction. We open one at the start of a
  request, use it for all DB operations in that request, and close it when
  the request ends. If anything fails mid-request, the session rolls back —
  no partial writes ever reach the database.

INTERN NOTE — B1:
  Run this file's verification steps in SPRINT2_BRIEFING.md before
  opening your PR. Every other backend intern is blocked on your merge.
"""

from collections.abc import AsyncGenerator
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.core.logger import get_logger

log = get_logger(__name__)

# ------------------------------------------------------------------ #
# Engine
# ------------------------------------------------------------------ #
# The engine is the actual connection to PostgreSQL.
# It manages a pool of connections that are reused across requests.
# Creating it is expensive — we do it once at module import time.
#
# pool_size=5        → keep 5 connections open always
# max_overflow=10    → allow up to 10 extra connections under load
# pool_pre_ping=True → test each connection before using it; discards
#                      stale connections silently instead of failing
# echo=is_dev        → log all SQL statements in dev (very noisy in prod)

engine: AsyncEngine = create_async_engine(
    settings.database_url,
    echo=settings.is_dev,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=3600,  # Recycle connections after 1 hour to avoid timeouts
)

# ------------------------------------------------------------------ #
# Session factory
# ------------------------------------------------------------------ #
# AsyncSessionLocal is a factory that creates new AsyncSession objects.
# Call it like: async with AsyncSessionLocal() as session: ...
#
# expire_on_commit=False → objects remain usable after commit without
#                          triggering additional SELECT queries. This is
#                          important for FastAPI responses — we commit
#                          inside get_db() AFTER the route has returned
#                          its response, so the response must be built
#                          before commit.

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


# ------------------------------------------------------------------ #
# get_db — the FastAPI dependency
# ------------------------------------------------------------------ #
# This is the function every route handler uses to get a database session.
# It is injected via FastAPI's Depends() system:
#
#   @router.get("/something")
#   async def my_route(db: AsyncSession = Depends(get_db)):
#       result = await db.execute(select(User))
#
# What happens in every request:
#   1. FastAPI calls get_db() before the route handler runs
#   2. A new AsyncSession is created from the factory
#   3. The session is yielded to the route handler
#   4. Route handler runs, uses the session for DB operations
#   5. If the route succeeds: session.commit() is called (writes persist)
#   6. If the route raises an exception: session.rollback() (no partial writes)
#   7. session.close() always runs — connection returned to pool

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that provides a database session per request.

    Usage:
        from app.core.database import get_db

        @router.post("/users")
        async def create_user(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ------------------------------------------------------------------ #
# Health check utility
# ------------------------------------------------------------------ #
# Used by the health endpoint (SC-003) to report DB connectivity.
# Returns True if PostgreSQL responds to SELECT 1, False otherwise.
# Never raises — the health endpoint must always return 200.

async def check_db_connection() -> bool:
    """
    Ping the database. Returns True if reachable, False otherwise.

    Called by GET /api/v1/health to include db_status in the response.
    Catches all exceptions — a DB failure never crashes the health endpoint.
    """
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        log.warning("db_ping_failed", error=str(e))
        return False


# ------------------------------------------------------------------ #
# Lifecycle helpers — called from main.py lifespan
# ------------------------------------------------------------------ #

async def init_db() -> None:
    """
    Run at application startup.
    Verifies the database is reachable and logs connection status.
    Does NOT create tables — Alembic migrations handle that.
    """
    log.info("db_connecting", url_host=settings.database_url.split("@")[-1])
    is_connected = await check_db_connection()
    if is_connected:
        log.info("db_connected")
    else:
        # Log the error but don't crash — the health endpoint will report it
        log.error("db_connection_failed_on_startup")


async def close_db() -> None:
    """
    Run at application shutdown.
    Disposes the engine — closes all pooled connections cleanly.
    """
    await engine.dispose()
    log.info("db_disconnected")
