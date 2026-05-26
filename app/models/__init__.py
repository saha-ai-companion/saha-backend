"""
app/models/__init__.py
========================
Import all models here so Alembic can discover them automatically.

When alembic/env.py does:
    from app.models import Base

This file runs, which triggers all the model imports below,
which makes all four table definitions visible to Alembic.

Without these imports, Alembic sees an empty Base.metadata
and generates empty migrations — no tables are created.

Import order matters:
  Base first — no dependencies.
  User second — no model dependencies.
  CompanionSession and ConversationLog after User
      — they have FK to users table.
  FoundationalMemory after User
      — it has FK to users table.
"""

from app.models.base import Base, TimestampMixin
from app.models.user import FrameworkOrientation, User
from app.models.session import CompanionSession, ConversationLog, MessageRole
from app.models.foundational_memory import FoundationalMemory

__all__ = [
    "Base",
    "TimestampMixin",
    "User",
    "FrameworkOrientation",
    "CompanionSession",
    "ConversationLog",
    "MessageRole",
    "FoundationalMemory",
]