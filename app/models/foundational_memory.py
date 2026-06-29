"""
app/models/foundational_memory.py — FoundationalMemory model
=============================================================
Owner: B3 (SC-013)

This is the most important model in the product.

The build documentation states:
    Memory is not a backend feature. It is the soul of the companion.

FoundationalMemory stores the companion's persistent knowledge of the user:
  - their_why         → personal reason for sobriety, in their own words
  - trigger_map       → structured map of personal triggers (JSON)
  - support_network   → people who support their recovery (JSON)
  - framework_orientation → which recovery language to use

On every single conversation turn, the companion reads this record
and injects it into the Claude API system prompt via to_prompt_context().
Without this model, the companion treats every conversation as a blank slate.

PHI RULES:
  their_why, trigger_map, sobriety content — all PHI.
  Never log. Never expose to another user. Encrypt at rest before launch.
"""

import uuid
from typing import TYPE_CHECKING, Any, Dict, Optional

from sqlalchemy import Boolean, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.user import FrameworkOrientation

if TYPE_CHECKING:
    from app.models.user import User


class FoundationalMemory(Base, TimestampMixin):
    """
    The companion's persistent knowledge of the user.

    One record per user — enforced by unique=True on user_id.
    Created at the end of the onboarding conversation.
    Updated as the companion learns more about the person.

    Relationship:
        user → the User this memory belongs to (one-to-one)
    """

    __tablename__ = "foundational_memories"

    # ------------------------------------------------------------------ #
    # Primary key
    # ------------------------------------------------------------------ #
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # ------------------------------------------------------------------ #
    # Foreign key — one-to-one with User
    # ------------------------------------------------------------------ #
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
        doc=(
            "FK to users. unique=True enforces the one-to-one relationship "
            "at the database level. PostgreSQL rejects a second record "
            "for the same user_id."
        ),
    )

    # ------------------------------------------------------------------ #
    # The four memory fields
    # ------------------------------------------------------------------ #
    their_why: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc=(
            "The user's personal reason for sobriety in their own words. "
            "Example: 'I want to be present for my daughter's childhood.' "
            "Nullable — filled during onboarding, record created first. "
            "PHI — the most sensitive field in the database. Never log."
        ),
    )

    sobriety_status: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc=(
            "The user's current sobriety status collected during onboarding. "
            "Example: 'I have been sober for 2 weeks.' "
            "Used by the companion to personalize conversations. PHI."
        ),
    )

    trigger_map: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        default=dict,
        doc=(
            "Structured map of the user's personal triggers. "
            "Keys: emotional, situational, people, places. "
            "Values: lists of trigger descriptions. "
            "Example: {'emotional': ['loneliness', 'work stress'], "
            "'situational': ['Friday evenings']}. "
            "Used for proactive companion check-ins on high-risk days. PHI."
        ),
    )

    support_network: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        default=dict,
        doc=(
            "People in the user's life who support their recovery. "
            "Example: {'close': [{'name': 'Priya', 'relation': 'wife', "
            "'aware': True}], 'recovery': [{'name': 'Ravi', "
            "'relation': 'AA sponsor'}]}. "
            "Used when companion suggests reaching out for human support."
        ),
    )

    framework_orientation: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default=FrameworkOrientation.UNDECIDED.value,
        doc=(
            "Recovery framework — duplicated from User.framework_orientation. "
            "Intentional design — the companion reads this on every message turn. "
            "Storing it here avoids a JOIN with the User table on every AI call. "
            "This is a performance decision, not a mistake."
        ),
    )

    # ------------------------------------------------------------------ #
    # Onboarding state
    # ------------------------------------------------------------------ #
    onboarding_complete: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        doc=(
            "False until user has answered all onboarding questions. "
            "When True: their_why, trigger_map, support_network are populated. "
            "The companion behaves differently during vs after onboarding."
        ),
    )

    # ------------------------------------------------------------------ #
    # Relationship
    # ------------------------------------------------------------------ #
    user: Mapped["User"] = relationship(
        "User",
        back_populates="foundational_memory",
    )

    # ------------------------------------------------------------------ #
    # The most important method in the entire codebase
    # ------------------------------------------------------------------ #
    def to_prompt_context(self) -> str:
        """
        Format this memory record as a string for Claude API injection.

        Called by the memory injection layer on every conversation turn.
        The output is injected into the companion system prompt so the
        companion knows who it is talking to.

        Example output:
            User profile:
            - Their why: I want to be present for my daughter's childhood.
            - Framework: aa
            - Triggers: loneliness, work stress, Friday evenings
            - Support: Priya (wife), Ravi (AA sponsor)

        Token limit: keep output under 500 tokens.
        Max 6 triggers, max 4 support people to stay within limit.
        """
        lines = ["User profile:"]

        if self.their_why:
            lines.append(f"- Their why: {self.their_why}")

        lines.append(f"- Framework: {self.framework_orientation}")

        if self.trigger_map:
            all_triggers = []
            for triggers in self.trigger_map.values():
                if isinstance(triggers, list):
                    all_triggers.extend(triggers)
            if all_triggers:
                lines.append(f"- Triggers: {', '.join(all_triggers[:6])}")

        if self.support_network:
            support_people = []
            for people in self.support_network.values():
                if isinstance(people, list):
                    for person in people[:2]:
                        name = person.get("name", "")
                        relation = person.get("relation", "")
                        if name:
                            support_people.append(f"{name} ({relation})")
            if support_people:
                lines.append(f"- Support: {', '.join(support_people[:4])}")

        return "\n".join(lines)

    def __repr__(self) -> str:
        return (
            f"<FoundationalMemory "
            f"user_id={self.user_id} "
            f"onboarding_complete={self.onboarding_complete}>"
        )
