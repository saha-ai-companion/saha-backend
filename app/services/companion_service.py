"""
app/services/companion_service.py
=================================

SC-028 — Companion Service

Service layer for the AI Sobriety Companion.

Responsibilities:
    - Build the personalized system prompt
    - Retrieve user context from the database
    - Load recent conversation history
    - Send the conversation to OpenAI
    - Save both user and assistant messages
    - Return the assistant's response

Business logic belongs here.
Routes should remain thin and simply call this service.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from openai import AsyncOpenAI

from app.core.config import settings
from app.models.user import User
from app.models.foundational_memory import FoundationalMemory
from app.models.conversation_log import ConversationLog


# ------------------------------------------------------------------ #
# Base system prompt for the AI companion
# ------------------------------------------------------------------ #

SAHA_SYSTEM_PROMPT = """
You are Saha, a sobriety companion. You are not a therapist, not a doctor,
and not an AA sponsor. You are a calm, warm, non-judgmental presence that
walks alongside people in early recovery.

Your approach:
- Listen first. Reflect back what you hear before offering anything.
- Ask one question at a time. Never overwhelm.
- Use the person's own words. Do not reframe or reinterpret.
- Never give advice unless directly asked.
- Never diagnose. Never prescribe. Never judge.
- Keep responses short — 2 to 4 sentences maximum.
- Speak like a thoughtful human, not a chatbot.

Tone: warm, present, unhurried. Like a friend sitting with someone,
not fixing them.

If someone is in crisis or mentions self-harm, gently encourage them
to contact iCall India: 9152987821 or
Vandrevala Foundation: 1860-2662-345.
"""


# ------------------------------------------------------------------ #
# Build personalized system prompt
# ------------------------------------------------------------------ #

async def build_system_prompt(
    db: AsyncSession,
    user_id: str,
) -> str:
    """
    Builds the system prompt by combining the base prompt with the
    user's recovery profile stored in the database.

    The AI receives information such as:
        - Recovery orientation
        - Sobriety start date
        - Their personal reason ("their why")
        - Personal trigger map
    """

    # -------------------------------------------------------------- #
    # Load user profile
    # -------------------------------------------------------------- #

    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    # -------------------------------------------------------------- #
    # Load foundational memory
    # -------------------------------------------------------------- #

    result = await db.execute(
        select(FoundationalMemory).where(
            FoundationalMemory.user_id == user_id
        )
    )
    memory = result.scalar_one_or_none()

    # -------------------------------------------------------------- #
    # Build personalized context
    # -------------------------------------------------------------- #

    user_context = ""

    if user or memory:

        user_context = "\n\nAbout this person:\n"

        if user and user.framework_orientation:
            user_context += (
                f"- Recovery framework: "
                f"{user.framework_orientation}\n"
            )

        if user and user.sobriety_start_date:
            user_context += (
                f"- Sobriety start date: "
                f"{user.sobriety_start_date}\n"
            )

        if memory and memory.their_why:
            user_context += (
                f"- Their reason for sobriety: "
                f"{memory.their_why}\n"
            )

        if memory and memory.trigger_map:
            user_context += (
                f"- Their triggers: "
                f"{memory.trigger_map}\n"
            )

        user_context += (
            "\nUse this to speak to them as "
            "someone you already know.\n"
        )

    # Return complete prompt
    return SAHA_SYSTEM_PROMPT + user_context


# ------------------------------------------------------------------ #
# Main companion workflow
# ------------------------------------------------------------------ #

async def get_companion_response(
    db: AsyncSession,
    user_id: str,
    user_message: str,
) -> str:
    """
    Complete companion flow.

    Steps:
        1. Save user message
        2. Load recent conversation history
        3. Build personalized system prompt
        4. Call OpenAI
        5. Save assistant response
        6. Return assistant response
    """

    # -------------------------------------------------------------- #
    # Step 1 — Save user's message
    # -------------------------------------------------------------- #

    user_log = ConversationLog(
        user_id=user_id,
        role="user",
        content=user_message,
    )

    db.add(user_log)
    await db.flush()

    # -------------------------------------------------------------- #
    # Step 2 — Retrieve last 20 conversation messages
    # -------------------------------------------------------------- #

    result = await db.execute(
        select(ConversationLog)
        .where(ConversationLog.user_id == user_id)
        .order_by(ConversationLog.created_at.desc())
        .limit(20)
    )

    history = result.scalars().all()

    # Reverse so oldest message appears first
    history.reverse()

    # -------------------------------------------------------------- #
    # Step 3 — Build personalized system prompt
    # -------------------------------------------------------------- #

    system_prompt = await build_system_prompt(
        db,
        user_id,
    )

    # -------------------------------------------------------------- #
    # Step 4 — Build messages for OpenAI
    # -------------------------------------------------------------- #

    messages = [
        {
            "role": "system",
            "content": system_prompt,
        }
    ]

    for msg in history:
        messages.append(
            {
                "role": msg.role,
                "content": msg.content,
            }
        )

    # -------------------------------------------------------------- #
    # Step 5 — Generate AI response
    # -------------------------------------------------------------- #

    client = AsyncOpenAI(
        api_key=settings.openai_api_key,
    )

    completion = await client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        max_tokens=200,
        temperature=0.7,
    )

    assistant_response = (
        completion.choices[0].message.content
    )

    # -------------------------------------------------------------- #
    # Step 6 — Save assistant response
    # -------------------------------------------------------------- #

    assistant_log = ConversationLog(
        user_id=user_id,
        role="assistant",
        content=assistant_response,
    )

    db.add(assistant_log)

    await db.commit()

    # Return generated response
    return assistant_response

