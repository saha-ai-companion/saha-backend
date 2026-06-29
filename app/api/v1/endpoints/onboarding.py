"""
app/api/v1/endpoints/onboarding.py
====================================
SC-029 — Onboarding endpoint

Saves the user's onboarding answers to FoundationalMemory.
Called from closing.tsx after the user completes all onboarding screens.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import get_current_user_id
from app.schemas.onboarding import OnboardingRequest, OnboardingResponse
from app.models.foundational_memory import FoundationalMemory

router = APIRouter()


@router.post("/complete", response_model=OnboardingResponse)
async def save_onboarding(
    request: OnboardingRequest,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    result = await db.execute(
        select(FoundationalMemory).where(
            FoundationalMemory.user_id == user_id
        )
    )
    memory = result.scalar_one_or_none()

    if memory:
        if request.sobriety_status:
            memory.sobriety_status = request.sobriety_status
        if request.framework_orientation:
            memory.framework_orientation = request.framework_orientation
        if request.trigger_map:
            memory.trigger_map = request.trigger_map
        if request.their_why:
            memory.their_why = request.their_why
    else:
        memory = FoundationalMemory(
            user_id=user_id,
            sobriety_status=request.sobriety_status,
            framework_orientation=request.framework_orientation,
            trigger_map=request.trigger_map,
            their_why=request.their_why,
        )
        db.add(memory)

    memory.onboarding_complete = True
    await db.commit()
    return OnboardingResponse(message="Onboarding saved successfully")
