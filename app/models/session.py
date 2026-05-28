"""
app/models/session.py — CompanionSession and ConversationLog
=============================================================
Owner: B3 (SC-013)

Two models in one file — they are tightly coupled.
  CompanionSession  → one conversation container (start → end)
  ConversationLog   → individual message turns inside a session

WHY TWO SEPARATE TABLES?
  Session holds metadata — when it started, ended, how many turns.
  ConversationLog holds content — the actual messages.
  Separating them means we can query session-level stats without
  loading all message content, and load only the last N messages
  for memory injection without touching the session record.

IMPORTANT — ConversationLog.content is PHI.
  The user's actual words are Protected Health Information.
  Never log this field. Never include it in error messages.
  Never return it in any response another user can access.
  Encryption at rest required before clinical launch.
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class MessageRole(str, Enum):
    """
    Who sent a message in a conversation turn.

    USER      → the human in recovery
    ASSISTANT → the AI companion (Saha)

    These exact strings are what the Claude API expects
    when building the messages array for each API call.
    """
    USER      = "user"
    ASSISTANT = "assistant"


class CompanionSession(Base, TimestampMixin):
    """
    One continuous companion conversation session.

    A session begins when a user opens the companion.
    It ends when they close the app or after an inactivity timeout.
    One user can have many sessions over their 90-day journey.

    ended_at is NULL while the session is active.
    Query for active sessions: WHERE ended_at IS NULL

    Relationships:
        user     → the User this session belongs to
        messages → all ConversationLog entries in this session
    """

    __tablename__ = "companion_sessions"

    # ------------------------------------------------------------------ #
    # Primary key
    # ------------------------------------------------------------------ #
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # ------------------------------------------------------------------ #
    # Foreign key
    # ------------------------------------------------------------------ #
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc=(
            "FK to users table. Indexed — 'get all sessions for user X' "
            "is a frequent query. CASCADE — deleting User deletes sessions."
        ),
    )

    # ------------------------------------------------------------------ #
    # Session timing
    # ------------------------------------------------------------------ #
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        doc="When this session began. Set by PostgreSQL on insert. UTC.",
    )

    ended_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc=(
            "When this session ended. NULL means session is still active. "
            "Set by code when session closes: session.ended_at = datetime.now(utc). "
            "Never set a default — must be truly NULL while active."
        ),
    )

    # ------------------------------------------------------------------ #
    # Metrics
    # ------------------------------------------------------------------ #
    turn_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        doc=(
            "Number of user messages in this session. "
            "Incremented each time the user sends a message. "
            "Starts at 0."
        ),
    )

    # ------------------------------------------------------------------ #
    # Relationships
    # ------------------------------------------------------------------ #
    user: Mapped["User"] = relationship(
        "User",
        back_populates="sessions",
    )

    messages: Mapped[List["ConversationLog"]] = relationship(
        "ConversationLog",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ConversationLog.created_at",
        lazy="select",
        doc=(
            "All messages in this session ordered by created_at. "
            "Memory injection reads the last 20 entries from this list."
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<CompanionSession id={self.id} "
            f"user_id={self.user_id} "
            f"turns={self.turn_count} "
            f"active={self.ended_at is None}>"
        )


class ConversationLog(Base):
    """
    One message turn in a companion session.

    Every user message and every companion response is a row here.
    This table is the longitudinal memory of the relationship.

    DOES NOT inherit TimestampMixin.
    Messages are never updated — only inserted.
    Only created_at exists here, not updated_at.
    Class declaration: class ConversationLog(Base) — Base only.

    content field is PHI — see module docstring for rules.
    """

    __tablename__ = "conversation_logs"

    # ------------------------------------------------------------------ #
    # Primary key
    # ------------------------------------------------------------------ #
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # ------------------------------------------------------------------ #
    # Foreign key
    # ------------------------------------------------------------------ #
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companion_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc=(
            "FK to companion_sessions. Indexed — memory injection queries "
            "'get last 20 messages in session X' on every AI call. "
            "This index makes that query fast."
        ),
    )

    # ------------------------------------------------------------------ #
    # Message content
    # ------------------------------------------------------------------ #
    role: Mapped[MessageRole] = mapped_column(
        String(20),
        nullable=False,
        doc=(
            "Who sent this message. 'user' or 'assistant'. "
            "These exact strings are passed to the Claude API messages array."
        ),
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc=(
            "The actual message text. PHI — Protected Health Information. "
            "NEVER log this field. NEVER include in error messages. "
            "NEVER return in any response another user can access. "
            "Text type — no length limit. String(255) would truncate long messages."
        ),
    )

    # ------------------------------------------------------------------ #
    # Timestamp — declared manually, not from TimestampMixin
    # ------------------------------------------------------------------ #
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
        doc=(
            "When this message was sent. Set by PostgreSQL. "
            "Indexed — memory injection queries ORDER BY created_at. "
            "Declared manually — ConversationLog does not use TimestampMixin."
        ),
    )

    # ------------------------------------------------------------------ #
    # Relationship
    # ------------------------------------------------------------------ #
    session: Mapped["CompanionSession"] = relationship(
        "CompanionSession",
        back_populates="messages",
    )

    def __repr__(self) -> str:
        preview = (
            self.content[:40] + "..."
            if len(self.content) > 40
            else self.content
        )
        return (
            f"<ConversationLog id={self.id} "
            f"role={self.role} "
            f"preview='{preview}'>"
        )