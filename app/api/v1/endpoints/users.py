"""
app/api/v1/endpoints/users.py — User endpoints
================================================
Owner: B2 (SC-016)

One endpoint:
  GET /api/v1/users/me → return the authenticated user's profile

THIS IS THE TEMPLATE FOR ALL SPRINT 3 ENDPOINTS.
  Every companion endpoint in Sprint 3 follows this exact pattern.
  B2 must write it with absolute clarity — other interns copy it.

THE PROTECTED ROUTE PATTERN explained:

  async def get_my_profile(
      current_user_id: UUID = Depends(get_current_user_id),
      db: AsyncSession = Depends(get_db),
  ):

  FastAPI resolves dependencies before calling the function.
  get_current_user_id validates the JWT from the Authorization header.
  If JWT is invalid, expired, or missing → AuthError → function never runs.
  If JWT is valid → current_user_id is the authenticated UUID.
  Trust it completely inside the function.

ALWAYS RETURN SCHEMA — NEVER RAW ORM OBJECT:
  UserProfileResponse defines exactly what the client receives.
  hashed_password is not in UserProfileResponse → cannot leak.
  is_active is not in UserProfileResponse → cannot leak.
"""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import NotFoundError
from app.core.logger import get_logger
from app.core.security import get_current_user_id
from app.repositories import user_repository
from app.schemas.auth import UserProfileResponse

log = get_logger(__name__)

router = APIRouter()


@router.get(
    "/me",
    response_model=UserProfileResponse,
    summary="Get current user profile",
    description=(
        "Returns the authenticated user's profile. "
        "Requires valid access token in Authorization: Bearer header. "
        "This endpoint demonstrates the protected route pattern — "
        "all Sprint 3 endpoints follow this exact structure."
    ),
    responses={
        200: {"description": "User profile returned."},
        401: {"description": "No token, expired token, or invalid token."},
        404: {"description": "User account not found (rare edge case)."},
    },
)
async def get_my_profile(
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> UserProfileResponse:
    """
    Return the authenticated user's profile.

    Execution flow:
      1. FastAPI calls get_current_user_id before this function
      2. get_current_user_id validates JWT, returns user_id UUID
      3. If JWT invalid → AuthError → this function never runs
      4. If JWT valid → current_user_id is trusted, authenticated UUID
      5. Fetch User from database using that UUID
      6. Return only schema-defined fields — never raw ORM object
    """
    log.info("get_profile", user_id=str(current_user_id))

    user = await user_repository.get_user_by_id(db, current_user_id)

    if not user:
        log.warning(
            "profile_user_not_found",
            user_id=str(current_user_id),
        )
        raise NotFoundError("User account not found.")

    return UserProfileResponse(
        id=user.id,
        email=user.email,
        framework_orientation=user.framework_orientation,
        sobriety_start_date=(
            str(user.sobriety_start_date)
            if user.sobriety_start_date
            else None
        ),
        created_at=user.created_at,
    )
