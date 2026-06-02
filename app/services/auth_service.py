"""
app/services/auth_service.py — Auth business logic
====================================================
Owner: B5 (SC-015)

Service layer — business logic lives here, not in routes.

Routes are thin: receive request → call service → return response.
Services are thick: all the actual logic of registering and logging in.

WHY THIS SEPARATION:
  - Business logic testable without HTTP
  - Logic reusable across multiple endpoints
  - Routes are readable at a glance

SECURITY DECISIONS:

1. Email enumeration prevention
   Wrong email AND wrong password return identical error message.
   Different messages reveal which emails are registered.

2. Timing attack prevention
   verify_password always runs even when user is not found.

PHI RULES:
  Never log email.
  Never log password.
  Log user_id only.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthError, ConflictError
from app.core.logger import get_logger
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from app.repositories import user_repository
from app.schemas.auth import TokenResponse

log = get_logger(__name__)

# Dummy hash for timing attack prevention
_DUMMY_HASH = (
    "$2b$12$dummyhashfortimingprotectionXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
)


async def register_user(
    db: AsyncSession,
    email: str,
    password: str,
) -> TokenResponse:
    """
    Register a new user account.

    Steps:
      1. Check duplicate email
      2. Hash password
      3. Create user
      4. Generate tokens
      5. Return tokens
    """

    # Check email already exists
    if await user_repository.email_exists(db, email):

        log.warning("registration_duplicate_email")

        raise ConflictError(
            "An account with this email address already exists."
        )

    # Hash password
    hashed = hash_password(password)

    # Create user
    user = await user_repository.create_user(
        db,
        email=email,
        hashed_password=hashed,
    )

    # Generate tokens
    access_token = create_access_token(user.id)

    refresh_token = create_refresh_token(user.id)

    # Log success
    log.info(
        "user_registered",
        user_id=str(user.id),
    )

    # Return response
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )


async def login_user(
    db: AsyncSession,
    email: str,
    password: str,
) -> TokenResponse:
    """
    Login existing user.

    Steps:
      1. Find user
      2. Verify password
      3. Check account
      4. Generate tokens
      5. Return response
    """

    INVALID_MSG = "Invalid email or password."

    # Find user
    user = await user_repository.get_user_by_email(
        db,
        email,
    )

    # Always run bcrypt verification
    password_correct = verify_password(
        password,
        user.hashed_password if user else _DUMMY_HASH,
    )

    # Reject invalid credentials
    if not user or not password_correct:

        log.warning("login_failed")

        raise AuthError(INVALID_MSG)

    # Reject inactive accounts
    if not user.is_active:

        raise AuthError(INVALID_MSG)

    # Generate tokens
    access_token = create_access_token(user.id)

    refresh_token = create_refresh_token(user.id)

    # Log success
    log.info(
        "user_logged_in",
        user_id=str(user.id),
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )

