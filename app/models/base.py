"""
app/models/base.py — Shared model base
========================================
Owner: B3 (as part of SC-013)

All four database models inherit from two things:
  1. Base          — SQLAlchemy's DeclarativeBase (required for ORM)
  2. TimestampMixin — adds created_at and updated_at to every model

WHY A SHARED BASE?
  Every table in this application needs created_at and updated_at.
  Putting them in a mixin means we write them once and never repeat.
  If we ever add audit_log_id or tenant_id to all tables, we add it
  here once and every model inherits it automatically.

WHY UUID PRIMARY KEYS?
  We use UUID (random 128-bit identifier) instead of integer auto-increment.
  Reasons:
  1. Security: integer IDs are enumerable — an attacker can guess
     /users/1, /users/2, /users/3. UUID IDs are not guessable.
  2. Distributed: if we ever shard the database, UUIDs never collide
     across shards. Integers do.
  3. Privacy: a user should not be able to infer how many users exist
     from their own user ID.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """
    SQLAlchemy declarative base.
    All models inherit from this.
    Required by Alembic to discover models for migrations.
    """
    pass


class TimestampMixin:
    """
    Adds created_at and updated_at to any model that inherits it.

    created_at: set by PostgreSQL when the row is first inserted.
                Never changes after that.

    updated_at: set by PostgreSQL on insert. Automatically updated
                by PostgreSQL on every UPDATE to that row.

    Both use timezone=True — all timestamps stored in UTC.
    Never store naive (timezone-unaware) datetimes in a production database.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        doc="Row creation timestamp. Set by DB. Never changes.",
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        doc="Row last-modified timestamp. Updated automatically by DB on every UPDATE.",
    )
