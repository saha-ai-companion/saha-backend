"""
app/core/security.py — JWT tokens and password hashing
========================================================
Owner: B4 (SC-014)

Two concerns in one file:

1. PASSWORD HASHING — bcrypt via passlib
   Plain password comes in. Hash goes to database.
   Plain password discarded immediately.
   Never stored. Never logged. Never returned.

2. JWT TOKEN CREATION AND VALIDATION — python-jose
   Access token : 15 minutes. Used on every API request.
   Refresh token: 7 days. Used only to get a new access token.

TIMING ATTACK PREVENTION:
   verify_password is always called even when the user does not exist.
   Without this, missing-user responses return faster than wrong-password
   responses because bcrypt is skipped. The timing difference reveals
   which email addresses are registered. On a health app, knowing
   someone has an account is sensitive information.

JWT PAYLOAD contains only:
   sub  → user_id as UUID string
   type → access or refresh
   exp  → expiry timestamp
   iat  → issued at timestamp

   Never include PHI, email, or health data in JWT payload.
   JWTs are base64 encoded — anyone can decode without the secret key.
   They are signed, not encrypted.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.core.exceptions import AuthError
from app.core.logger import get_logger

log = get_logger(__name__)

# ------------------------------------------------------------------ #
# Password hashing context
# ------------------------------------------------------------------ #
# CryptContext manages the hashing scheme.
# bcrypt is slow by design — prevents brute force.
# deprecated="auto" upgrades old weak hashes transparently on next login.

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    """
    Hash a plain-text password using bcrypt.

    The returned hash string is safe to store in the database.
    It includes algorithm identifier, cost factor, and salt.

    Args:
        plain_password: Password as typed by user. Discard after hashing.

    Returns:
        bcrypt hash string — e.g. '$2b$12$...'
    """
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain-text password against a stored bcrypt hash.

    Never raises — always returns True or False.
    Called even when the user does not exist (timing attack prevention).

    Args:
        plain_password: Password as typed.
        hashed_password: Stored bcrypt hash from database.

    Returns:
        True if passwords match, False otherwise.
    """
    return pwd_context.verify(plain_password, hashed_password)


# ------------------------------------------------------------------ #
# JWT token creation
# ------------------------------------------------------------------ #

def create_access_token(user_id: UUID) -> str:
    """
    Create a short-lived JWT access token for a user.

    Expires in settings.access_token_expire_minutes (15 minutes).
    Include in every API request: Authorization: Bearer <token>

    Args:
        user_id: The user's UUID primary key.

    Returns:
        Signed JWT string.
    """
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    payload = {
        "sub": str(user_id),
        "type": "access",
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    token = jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    log.debug("access_token_created", user_id=str(user_id))
    return token


def create_refresh_token(user_id: UUID) -> str:
    """
    Create a long-lived JWT refresh token for a user.

    Expires in settings.refresh_token_expire_days (7 days).
    Store securely client-side.
    Send ONLY to /auth/refresh endpoint — never to any other endpoint.

    Args:
        user_id: The user's UUID primary key.

    Returns:
        Signed JWT string.
    """
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.refresh_token_expire_days
    )
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    token = jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    log.debug("refresh_token_created", user_id=str(user_id))
    return token


def decode_token(token: str, expected_type: str = "access") -> dict:
    """
    Decode and validate a JWT token.

    Validates:
      - Signature: was this token signed with our secret key?
      - Expiry: has the token expired?
      - Type: is this the expected token type?

    Raises AuthError on any failure — never returns partial data.

    Args:
        token: The raw JWT string from the Authorization header.
        expected_type: "access" or "refresh".

    Returns:
        Decoded payload dict. Contains "sub" = user_id string.

    Raises:
        AuthError: If token is invalid, expired, tampered, or wrong type.
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError as e:
        log.warning("jwt_decode_failed", error=str(e))
        raise AuthError("Invalid or expired token.")

    # Verify token type — prevents using refresh token as access token
    token_type = payload.get("type")
    if token_type != expected_type:
        log.warning(
            "jwt_wrong_type",
            expected=expected_type,
            got=token_type,
        )
        raise AuthError("Invalid token type.")

    # Verify subject (user_id) exists in payload
    if not payload.get("sub"):
        log.warning("jwt_missing_subject")
        raise AuthError("Invalid token: missing subject.")

    return payload


# ------------------------------------------------------------------ #
# OAuth2 scheme — tells FastAPI where to find the token
# ------------------------------------------------------------------ #
# auto_error=False — we handle 401 ourselves via AuthError
# so the error shape matches our global error format consistently.

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.api_v1_prefix}/auth/login",
    auto_error=False,
)


# ------------------------------------------------------------------ #
# get_current_user_id — the protected route dependency
# ------------------------------------------------------------------ #
# This is the most important function in this file.
# Every protected route in Sprint 3 uses this dependency:
#
#   @router.get("/something")
#   async def my_route(
#       current_user_id: UUID = Depends(get_current_user_id),
#       db: AsyncSession = Depends(get_db),
#   ):
#       ...
#
# FastAPI calls get_current_user_id BEFORE the route handler runs.
# If token is invalid → AuthError raised → route never executes.
# If token is valid   → current_user_id is the authenticated user's UUID.

async def get_current_user_id(
    token: Optional[str] = Depends(oauth2_scheme),
) -> UUID:
    """
    Extract and validate the current user's ID from Authorization header.

    Raises AuthError if:
      - No Authorization header / no token provided
      - Token has expired
      - Token signature is invalid (tampered)
      - Refresh token used where access token required

    Returns:
        UUID of the authenticated user. Guaranteed valid if no exception.
    """
    if not token:
        raise AuthError(
            "Authentication required. "
            "Include Authorization: Bearer <token> header."
        )

    payload = decode_token(token, expected_type="access")

    try:
        user_id = UUID(payload["sub"])
    except (ValueError, KeyError):
        log.warning("jwt_invalid_subject", sub=payload.get("sub"))
        raise AuthError("Invalid token: malformed subject.")

    return user_id