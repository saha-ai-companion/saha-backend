"""
app/api/v1/endpoints/companion.py
==================================

SC-028 — Companion Chat Endpoint

This route receives a user's chat message, forwards it to the
companion service, and returns the AI-generated response.

Routes should remain thin:
    Request → Service → Response

All business logic lives inside companion_service.py.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user_id
from app.schemas.companion import ChatRequest, ChatResponse
from app.services import companion_service

# Router for all companion-related endpoints
router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """
    Chat with the AI sobriety companion.

    Flow:
        1. Receive user's message.
        2. Get authenticated user's ID.
        3. Call companion service.
        4. Return AI-generated response.

    Authentication:
        Requires a valid JWT access token.

    Request:
        {
            "message": "I'm feeling anxious today."
        }

    Response:
        {
            "response": "I'm here with you. Would you like to tell me what has been making today feel difficult?"
        }
    """

    # Call the service layer to generate an AI response
    response = await companion_service.get_companion_response(
        db=db,
        user_id=user_id,
        user_message=request.message,
    )

    # Return the assistant's response using the response schema
    return ChatResponse(response=response)