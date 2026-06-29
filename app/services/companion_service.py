"""
app/services/companion_service.py
SC-028 — Companion Service
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from openai import AsyncOpenAI

from app.core.config import settings
from app.models.user import User
from app.models.foundational_memory import FoundationalMemory
from app.models.session import CompanionSession, ConversationLog, MessageRole

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


async def build_system_prompt(db: AsyncSession, user_id: str) -> str:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    result = await db.execute(
        select(FoundationalMemory).where(FoundationalMemory.user_id == user_id)
    )
    memory = result.scalar_one_or_none()

    user_context = ""
    if user or memory:
        user_context = "\n\nAbout this person:\n"
        if user and user.framework_orientation:
            user_context += f"- Recovery framework: {user.framework_orientation}\n"
        if user and user.sobriety_start_date:
            user_context += f"- Sobriety start date: {user.sobriety_start_date}\n"
        if memory and memory.their_why:
            user_context += f"- Their reason for sobriety: {memory.their_why}\n"
        if memory and memory.sobriety_status:
            user_context += f"- Sobriety status: {memory.sobriety_status}\n"
        if memory and memory.trigger_map:
            user_context += f"- Their triggers: {memory.trigger_map}\n"
        user_context += "\nUse this to speak to them as someone you already know.\n"

    return SAHA_SYSTEM_PROMPT + user_context


async def get_companion_response(
    db: AsyncSession,
    user_id: str,
    user_message: str,
) -> str:
    # Step 1 — Find active session or create new one
    result = await db.execute(
        select(CompanionSession)
        .where(
            CompanionSession.user_id == user_id,
            CompanionSession.ended_at == None,
        )
        .order_by(CompanionSession.created_at.desc())
        .limit(1)
    )
    session = result.scalar_one_or_none()

    if not session:
        session = CompanionSession(user_id=user_id)
        db.add(session)
        await db.flush()

    # Step 2 — Save user message
    user_log = ConversationLog(
        session_id=session.id,
        role=MessageRole.USER,
        content=user_message,
    )
    db.add(user_log)
    await db.flush()

    # Step 3 — Get last 20 messages for history
    result = await db.execute(
        select(ConversationLog)
        .where(ConversationLog.session_id == session.id)
        .order_by(ConversationLog.created_at.desc())
        .limit(20)
    )
    history = result.scalars().all()
    history.reverse()

    # Step 4 — Build system prompt
    system_prompt = await build_system_prompt(db, user_id)

    # Step 5 — Build messages array for OpenAI
    messages = [{"role": "system", "content": system_prompt}]
    for msg in history:
        messages.append({"role": msg.role, "content": msg.content})

    # Step 6 — Call OpenAI
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    completion = await client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        max_tokens=200,
        temperature=0.7,
    )
    assistant_response = completion.choices[0].message.content

    # Step 7 — Save assistant response
    assistant_log = ConversationLog(
        session_id=session.id,
        role=MessageRole.ASSISTANT,
        content=assistant_response,
    )
    db.add(assistant_log)

    # Step 8 — Increment turn count
    session.turn_count += 1
    await db.commit()

    return assistant_response
