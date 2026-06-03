"""
app/api/v1/endpoints/auth.py — Auth endpoints
===============================================

Two endpoints:
  POST /api/v1/auth/register → create account
  POST /api/v1/auth/login    → verify credentials

ROUTE HANDLERS ARE THIN.

Each handler:
  1. Receives validated request body
  2. Calls service function
  3. Returns response

Business logic lives in auth_service.py.
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logger import get_logger
from app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
)
from app.services import auth_service

log = get_logger(__name__)

router = APIRouter()


@router.post(
    "/register",

    # Response model
    response_model=TokenResponse,

    # HTTP status code
    status_code=status.HTTP_201_CREATED,

    # Swagger summary
    summary="Register a new account",

    # Swagger description
    description=(
        "Create a new user account. "
        "Returns access and refresh tokens immediately. "
        "User is logged in immediately after registration."
    ),

    # API documentation responses
    responses={
        201: {
            "description": "Account created successfully."
        },
        409: {
            "description": "Email already exists."
        },
        422: {
            "description": "Validation error."
        },
    },
)
async def register(
    body: RegisterRequest,

    # Database dependency
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Register a new user account.

    Request validation happens automatically
    before this function executes.
    """

    # Log registration attempt
    log.info("registration_attempt")

    # Call service layer
    return await auth_service.register_user(
        db=db,
        email=body.email,
        password=body.password,
    )


@router.post(
    "/login",

    # Response schema
    response_model=TokenResponse,

    # HTTP status
    status_code=status.HTTP_200_OK,

    # Swagger summary
    summary="Login to existing account",

    # Swagger description
    description=(
        "Authenticate using email and password. "
        "Returns identical error for invalid email "
        "or invalid password."
    ),

    # API response documentation
    responses={
        200: {
            "description": "Login successful."
        },
        401: {
            "description": "Invalid credentials."
        },
        422: {
            "description": "Malformed request body."
        },
    },
)
async def login(
    body: LoginRequest,

    # Database dependency
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Login existing user.

    Same error message returned for:
      - wrong email
      - wrong password

    This prevents email enumeration attacks.
    """

    # Log login attempt
    log.info("login_attempt")

    # Call service layer
    return await auth_service.login_user(
        db=db,
        email=body.email,
        password=body.password,
    )

