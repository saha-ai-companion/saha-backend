"""
alembic/env.py — Alembic migration environment
================================================
Owner: B1 (SC-012)

This file tells Alembic:
  1. Which database to connect to (DATABASE_URL from config)
  2. Which models to inspect when generating migrations (Base.metadata)
  3. How to run in async mode (required for asyncpg driver)

CRITICAL: import app.models at the bottom of this file.
Without that import, Alembic sees an empty Base.metadata and generates
empty migrations — it does not know any tables exist.

HOW MIGRATIONS WORK:
  When B3 adds a new SQLAlchemy model (SC-013), B1 runs:
    alembic revision --autogenerate -m "add user and memory tables"
  Alembic compares Base.metadata (the Python model definitions) to
  the actual database schema and generates a migration file with the diff.
  Then:
    alembic upgrade head
  Applies all pending migrations to the database.
"""

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Load alembic.ini logging config
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ------------------------------------------------------------------ #
# Import models — CRITICAL
# Without this, Alembic generates empty migrations
# ------------------------------------------------------------------ #
from app.models import Base  # noqa: E402 — import after alembic setup

# Override DATABASE_URL from app config (not hardcoded in alembic.ini)
from app.core.config import settings
config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata


# ------------------------------------------------------------------ #
# Offline migrations (generates SQL without a live DB connection)
# ------------------------------------------------------------------ #
def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


# ------------------------------------------------------------------ #
# Online migrations (connects to DB and runs migrations)
# ------------------------------------------------------------------ #
def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations using the async engine."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # NullPool for migrations — no connection pooling
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
